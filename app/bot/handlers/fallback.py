"""Last router: strangers get "no access", known users get a hint."""

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.common import no_access_text
from app.bot.keyboards import main_menu
from app.i18n import t

router = Router(name="fallback")


@router.message()
async def any_message(msg: Message, role: str | None, lang: str) -> None:
    if role is None:
        await msg.answer(no_access_text(msg.from_user.id, lang))
    elif role == "courier" and msg.text and msg.text.startswith("/"):
        await msg.answer(t(lang, "only_admin"), reply_markup=main_menu(lang))
    else:
        await msg.answer(t(lang, "not_understood"), reply_markup=main_menu(lang))


@router.callback_query()
async def any_callback(cb: CallbackQuery, role: str | None, lang: str) -> None:
    await cb.answer(t(lang, "cb.no_access") if role is None else t(lang, "cb.outdated"), show_alert=role is None)
