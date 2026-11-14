"""End-to-end bot flow through the real Dispatcher with a fake Telegram API session."""

from datetime import datetime
from decimal import Decimal as D
from itertools import count

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, SendDocument, SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update
from sqlalchemy import select

from app.bot import keyboards
from app.bot.handlers import admin, common, fallback, sale
from app.bot.keyboards import DraftCB, ModeCB, PickCB
from app.bot.setup import create_dispatcher
from app.config import get_settings
from app.db.models import Sale
from app.i18n import t
from app.services import catalog
from app.services.sales import sale_totals

ADMIN, COURIER, STRANGER = 1000, 555, 777
# Test users have no Telegram language_code -> DEFAULT_LANGUAGE (ru)
BTN_NEW_SALE = t("ru", keyboards.BTN_NEW_SALE)
BTN_REPORT = t("ru", keyboards.BTN_REPORT)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self._ids = count(1)

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, AnswerCallbackQuery) or method.__returning__ is bool:
            return True
        return Message(
            message_id=next(self._ids),
            date=datetime.now(),
            chat=Chat(id=int(getattr(method, "chat_id", 0) or 0), type="private"),
            text=getattr(method, "text", None),
        )

    async def stream_content(self, *a, **kw):  # pragma: no cover
        yield b""

    async def close(self) -> None:
        pass


class Harness:
    def __init__(self, session_maker) -> None:
        self.api = FakeSession()
        self.bot = Bot("42:TEST", session=self.api)
        for r in (common.router, admin.router, sale.router, fallback.router):
            r._parent_router = None  # module-level routers are re-attached to a fresh Dispatcher per test
        self.dp = create_dispatcher(get_settings(), session_maker)
        self._upd = count(1)
        self._msg = count(1000)
        self.language_codes: dict[int, str] = {}  # Telegram app language per user (none by default)

    def _user(self, uid):
        user = {"id": uid, "is_bot": False, "first_name": f"U{uid}"}
        if uid in self.language_codes:
            user["language_code"] = self.language_codes[uid]
        return user

    async def text(self, uid: int, text: str):
        mark = len(self.api.calls)
        upd = {
            "update_id": next(self._upd),
            "message": {
                "message_id": next(self._msg),
                "date": int(datetime.now().timestamp()),
                "chat": {"id": uid, "type": "private"},
                "from": self._user(uid),
                "text": text,
                **({"entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]}
                   if text.startswith("/") else {}),
            },
        }  # fmt: skip
        await self.dp.feed_update(self.bot, Update.model_validate(upd, context={"bot": self.bot}))
        return self.api.calls[mark:]

    async def click(self, uid: int, data: str):
        mark = len(self.api.calls)
        upd = {
            "update_id": next(self._upd),
            "callback_query": {
                "id": str(next(self._upd)),
                "from": self._user(uid),
                "chat_instance": "x",
                "data": data,
                "message": {
                    "message_id": 1,
                    "date": int(datetime.now().timestamp()),
                    "chat": {"id": uid, "type": "private"},
                    "text": "…",
                },
            },
        }
        await self.dp.feed_update(self.bot, Update.model_validate(upd, context={"bot": self.bot}))
        return self.api.calls[mark:]


def texts(calls) -> str:
    return "\n".join(c.text for c in calls if isinstance(c, SendMessage | AnswerCallbackQuery) and c.text)


@pytest.fixture
async def h(session_maker, session):
    await catalog.add_client(session, "Ресторан А")
    await catalog.upsert_product(session, "Помидоры", "кг", "12345678901234567")
    await catalog.set_courier(session, COURIER, "Али")
    harness = Harness(session_maker)
    yield harness
    await harness.dp.storage.close()


async def test_stranger_has_no_access(h, session):
    out = await h.text(STRANGER, BTN_NEW_SALE)
    assert t("ru", "auth.ask_phone") in texts(out)
    out = await h.click(STRANGER, PickCB(kind="c", id=1).pack())
    assert "Нет доступа" in texts(out)
    assert (await session.scalars(select(Sale))).all() == []


async def test_courier_cannot_see_company_report(h):
    out = await h.text(COURIER, "/report")
    assert "только администратору" in texts(out)
    out = await h.text(COURIER, BTN_REPORT)
    assert texts(out).startswith("Ваши доставки")


async def test_full_sale_flow_with_vat_mode(h, session):
    out = await h.text(COURIER, BTN_NEW_SALE)
    kb = out[0].reply_markup.inline_keyboard
    assert kb[0][0].text == "Ресторан А"
    client_cb = kb[0][0].callback_data

    out = await h.click(COURIER, client_cb)
    product_msg = [c for c in out if isinstance(c, SendMessage)][0]
    product_cb = product_msg.reply_markup.inline_keyboard[0][0].callback_data

    await h.click(COURIER, product_cb)
    out = await h.text(COURIER, "0")
    assert "положительное" in texts(out)
    out = await h.text(COURIER, "25")
    assert "без НДС" in texts(out)

    await h.click(COURIER, ModeCB().pack())  # switch to "price with VAT"
    out = await h.text(COURIER, "11 200")
    draft = texts(out)
    assert "введено с НДС: 11 200" in draft
    assert "Итого: 280 000" in draft

    out = await h.click(COURIER, DraftCB(action="finish").pack())
    docs = [c for c in out if isinstance(c, SendDocument)]
    assert sorted(d.chat_id for d in docs) == sorted([COURIER, ADMIN])  # courier + every admin
    assert docs[0].document.filename == "nakladnaya_1.xlsx"

    sale = (await session.scalars(select(Sale))).one()
    await session.refresh(sale, ["items"])
    assert sale.courier_id == COURIER
    assert sale.items[0].price_ex_vat == D("10000")
    assert sale.items[0].entered_mode == "with_vat"
    assert sale_totals(sale).total == D("280000.00")

    # pressing "finish" again on the old message must not create a second invoice
    out = await h.click(COURIER, DraftCB(action="finish").pack())
    assert "устарела" in texts(out)
    assert len((await session.scalars(select(Sale))).all()) == 1


async def test_undo_and_cannot_finish_empty(h):
    await h.text(COURIER, BTN_NEW_SALE)
    await h.click(COURIER, PickCB(kind="c", id=1).pack())
    await h.click(COURIER, PickCB(kind="p", id=1).pack())
    await h.text(COURIER, "1")
    await h.text(COURIER, "100")
    out = await h.click(COURIER, DraftCB(action="undo").pack())
    assert "Последняя позиция убрана" in texts(out)
    out = await h.click(COURIER, DraftCB(action="finish").pack())
    assert "без позиций" in texts(out)


async def test_admin_can_sell_and_delete(h, session):
    await h.text(ADMIN, BTN_NEW_SALE)
    await h.click(ADMIN, PickCB(kind="c", id=1).pack())
    await h.click(ADMIN, PickCB(kind="p", id=1).pack())
    await h.text(ADMIN, "2")
    await h.text(ADMIN, "500")
    out = await h.click(ADMIN, DraftCB(action="finish").pack())
    assert len([c for c in out if isinstance(c, SendDocument)]) == 1  # admin is both seller and recipient

    out = await h.text(ADMIN, "/report")
    assert "накладных: 1" in texts(out)
    out = await h.text(ADMIN, "/delsale 1")
    assert "удалена" in texts(out)
    out = await h.text(ADMIN, "/report")
    assert "накладных: 0" in texts(out)


async def test_search_client_by_text(h):
    await h.text(COURIER, BTN_NEW_SALE)
    out = await h.text(COURIER, "ресторан")
    assert "найдено" in texts(out)
