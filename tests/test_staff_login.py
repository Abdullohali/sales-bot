"""Login by phone: staff added in the admin panel get their role after sharing their own contact."""

from datetime import datetime

import pytest
from aiogram.types import Update
from sqlalchemy import select

from app.db.models import Courier, Staff
from app.i18n import t
from app.services import catalog
from tests.test_bot_flow import Harness, texts

NEW_COURIER, NEW_ADMIN, NOBODY = 9001, 9002, 9003


async def send_contact(h: Harness, uid: int, phone: str, owner: int | None = None):
    mark = len(h.api.calls)
    upd = {
        "update_id": next(h._upd),
        "message": {
            "message_id": next(h._msg),
            "date": int(datetime.now().timestamp()),
            "chat": {"id": uid, "type": "private"},
            "from": h._user(uid),
            "contact": {"phone_number": phone, "first_name": "X", "user_id": owner or uid},
        },
    }
    await h.dp.feed_update(h.bot, Update.model_validate(upd, context={"bot": h.bot}))
    return h.api.calls[mark:]


@pytest.fixture
async def h(session_maker, session):
    session.add_all(
        [
            Staff(name="Bobur", phone="998901112233", role="courier"),
            Staff(name="Dilnoza", phone="998935556677", role="admin"),
            Staff(name="Old", phone="998977778899", role="courier", active=False),
        ]
    )
    await session.commit()
    harness = Harness(session_maker)
    yield harness
    await harness.dp.storage.close()


def test_normalize_phone():
    assert catalog.normalize_phone("+998 (90) 111-22-33") == "998901112233"
    assert catalog.normalize_phone("90 111 22 33") == "998901112233"
    assert catalog.normalize_phone("123") is None
    assert catalog.normalize_phone(None) is None


async def test_stranger_is_asked_for_phone(h):
    calls = await h.text(NOBODY, "/start")
    assert t("ru", "auth.ask_phone") in texts(calls)
    markup = calls[-1].reply_markup
    assert markup.keyboard[0][0].request_contact is True


async def test_courier_logs_in_by_phone(h, session):
    calls = await send_contact(h, NEW_COURIER, "+998901112233")
    assert t("ru", "role.courier") in texts(calls)
    staff = await session.scalar(select(Staff).where(Staff.phone == "998901112233"))
    assert staff.tg_id == NEW_COURIER
    courier = await session.get(Courier, NEW_COURIER)
    assert courier.name == "Bobur" and courier.active
    # role sticks: next /start greets without asking again
    assert t("ru", "role.courier") in texts(await h.text(NEW_COURIER, "/start"))


async def test_admin_logs_in_by_phone_and_gets_invoice_copies(h, session):
    calls = await send_contact(h, NEW_ADMIN, "998935556677")
    assert t("ru", "role.admin") in texts(calls)
    assert NEW_ADMIN in await catalog.admin_recipient_ids(session, [1000])
    # admin commands work
    assert t("ru", "clients.none") in texts(await h.text(NEW_ADMIN, "/clients"))


async def test_unknown_inactive_and_foreign_contacts_are_rejected(h, session):
    assert "9003" in texts(await send_contact(h, NOBODY, "998900000000"))
    assert t("ru", "auth.ask_phone") in texts(await h.text(NOBODY, "/start"))
    # deactivated staff
    texts_ = texts(await send_contact(h, NOBODY, "998977778899"))
    assert t("ru", "role.courier") not in texts_
    # someone else's contact
    calls = await send_contact(h, NOBODY, "998901112233", owner=NEW_COURIER)
    assert t("ru", "auth.not_own") in texts(calls)
    assert (await session.scalar(select(Staff).where(Staff.phone == "998901112233"))).tg_id is None


async def test_number_bound_to_other_account_and_deactivation(h, session_maker):
    await send_contact(h, NEW_COURIER, "998901112233")
    # same number from another Telegram account does not steal the login
    assert t("ru", "role.courier") not in texts(await send_contact(h, NOBODY, "998901112233"))
    # deactivating the staff row revokes access
    async with session_maker() as s:
        row = await s.scalar(select(Staff).where(Staff.tg_id == NEW_COURIER))
        row.active = False
        await s.commit()
    assert t("ru", "auth.ask_phone") in texts(await h.text(NEW_COURIER, "/start"))
