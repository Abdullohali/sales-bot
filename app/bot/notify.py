import logging
from collections.abc import Iterable, Mapping

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, Message

from app.config import Settings
from app.db.models import Sale
from app.i18n import default_lang, t
from app.services.excel import build_invoice_xlsx, invoice_filename
from app.services.formatting import fmt_date, fmt_money
from app.services.sales import sale_totals

log = logging.getLogger(__name__)
TG_LIMIT = 4000


def invoice_caption(sale: Sale, lang: str) -> str:
    tot = sale_totals(sale)
    return t(
        lang,
        "invoice.caption",
        id=sale.id,
        date=fmt_date(sale.sale_date),
        client=sale.client.name,
        courier=sale.courier.name,
        n=len(sale.items),
        ex=fmt_money(tot.ex),
        vat=fmt_money(tot.vat),
        total=fmt_money(tot.total),
    )


async def send_invoice(
    bot: Bot, sale: Sale, settings: Settings, chat_ids: Iterable[int], langs: Mapping[int, str]
) -> None:
    """Send invoice xlsx to every chat once, each in the recipient's language
    (`langs`; missing -> DEFAULT_LANGUAGE). A failing recipient (e.g. admin who never
    pressed /start) must not break delivery to the others."""
    files: dict[str, bytes] = {}  # built once per language
    seen: set[int] = set()
    for chat_id in chat_ids:
        if chat_id in seen:
            continue
        seen.add(chat_id)
        lang = langs.get(chat_id) or default_lang()
        if lang not in files:
            files[lang] = build_invoice_xlsx(sale, settings.COMPANY_NAME, settings.COMPANY_INN, lang)
        try:
            await bot.send_document(
                chat_id,
                BufferedInputFile(files[lang], filename=invoice_filename(sale, lang)),
                caption=invoice_caption(sale, lang),
            )
        except TelegramAPIError as e:
            log.warning("cannot deliver invoice %s to %s: %s", sale.id, chat_id, e)


async def answer_long(msg: Message, text: str, **kwargs) -> None:
    """Split long text by lines into Telegram-sized messages."""
    chunk = ""
    for line in text.split("\n"):
        if len(chunk) + len(line) + 1 > TG_LIMIT:
            await msg.answer(chunk, **kwargs)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await msg.answer(chunk, **kwargs)
