from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import BTN_LANG, LangCB, lang_kb, main_menu
from app.bot.middlewares import RoleFilter
from app.i18n import LANGS, t, variants
from app.services.catalog import set_lang

router = Router(name="common")


def no_access_text(user_id: int, lang: str) -> str:
    return t(lang, "no_access", user_id=user_id)


def help_text(role: str, lang: str) -> str:
    text = t(lang, "help.courier")
    if role == "admin":
        text += "\n\n" + t(lang, "help.admin")
    return text


@router.message(CommandStart())
async def cmd_start(
    msg: Message, state: FSMContext, session: AsyncSession, role: str | None, lang: str, lang_saved: bool
) -> None:
    if role is None:
        await msg.answer(no_access_text(msg.from_user.id, lang))
        return
    if not lang_saved:
        # Remember the detected language, so invoices sent to this user later use it too.
        await set_lang(session, msg.from_user.id, lang)
    await state.clear()
    who = t(lang, "role.admin") if role == "admin" else t(lang, "role.courier")
    await msg.answer(t(lang, "start.hello", name=msg.from_user.full_name, who=who), reply_markup=main_menu(lang))


@router.message(Command("help"))
async def cmd_help(msg: Message, role: str | None, lang: str) -> None:
    if role is None:
        await msg.answer(no_access_text(msg.from_user.id, lang))
    else:
        await msg.answer(help_text(role, lang), reply_markup=main_menu(lang))


@router.message(Command("myid"))
async def cmd_myid(msg: Message, lang: str) -> None:
    await msg.answer(t(lang, "myid", user_id=msg.from_user.id))


@router.message(Command("lang", "language"), RoleFilter("admin", "courier"))
@router.message(F.text.in_(variants(BTN_LANG)), RoleFilter("admin", "courier"))
async def cmd_lang(msg: Message) -> None:
    # The prompt is shown in all three languages: the user may not read the current one.
    await msg.answer(" / ".join(t(code, "lang.choose") for code in LANGS), reply_markup=lang_kb())


@router.callback_query(LangCB.filter(), RoleFilter("admin", "courier"))
async def choose_lang(cb: CallbackQuery, callback_data: LangCB, session: AsyncSession) -> None:
    code = callback_data.code if callback_data.code in LANGS else None
    if code is None:
        await cb.answer()
        return
    await set_lang(session, cb.from_user.id, code)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # message too old / already edited
        pass
    # A new message is needed to replace the reply keyboard with buttons in the new language.
    await cb.message.answer(t(code, "lang.set"), reply_markup=main_menu(code))
    await cb.answer()


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery) -> None:
    await cb.answer()
