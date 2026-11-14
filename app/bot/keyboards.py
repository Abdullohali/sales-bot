from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.i18n import LANG_NAMES, LANGS, t
from app.services.vat import WITH_VAT

PAGE_SIZE = 8

# Reply-keyboard buttons are matched by their text in any language (see app.i18n.variants).
BTN_NEW_SALE = "btn.new_sale"
BTN_REPORT = "btn.report"
BTN_LANG = "btn.lang"
BTN_SHARE_PHONE = "btn.share_phone"


class PickCB(CallbackData, prefix="pick"):
    kind: str  # "c" client | "p" product
    id: int


class PageCB(CallbackData, prefix="pg"):
    kind: str
    page: int
    reset: bool = False  # drop search query


class ModeCB(CallbackData, prefix="mode"):
    pass


class DraftCB(CallbackData, prefix="dr"):
    action: str  # add | finish | undo | cancel


class LangCB(CallbackData, prefix="lang"):
    code: str


def main_menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, BTN_NEW_SALE)), KeyboardButton(text=t(lang, BTN_REPORT))],
            [KeyboardButton(text=t(lang, BTN_LANG))],
        ],
        resize_keyboard=True,
    )


def phone_kb(lang: str) -> ReplyKeyboardMarkup:
    """Single button that sends the user's own contact (Telegram asks for confirmation)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, BTN_SHARE_PHONE), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def lang_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code in LANGS:
        b.button(text=LANG_NAMES[code], callback_data=LangCB(code=code))
    b.adjust(3)
    return b.as_markup()


def _cancel_button(lang: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=t(lang, "btn.cancel"), callback_data=DraftCB(action="cancel").pack())


def picker_kb(kind: str, rows: list, page: int, total: int, searching: bool, lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in rows:
        b.button(text=r.name if kind == "c" else f"{r.name} ({r.unit})", callback_data=PickCB(kind=kind, id=r.id))
    b.adjust(2)

    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=PageCB(kind=kind, page=page - 1).pack()))
    if pages > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=PageCB(kind=kind, page=page + 1).pack()))
    if nav:
        b.row(*nav)
    if searching:
        b.row(
            InlineKeyboardButton(
                text=t(lang, "btn.reset_search"), callback_data=PageCB(kind=kind, page=0, reset=True).pack()
            )
        )
    b.row(_cancel_button(lang))
    return b.as_markup()


def price_mode_kb(mode: str, lang: str) -> InlineKeyboardMarkup:
    text = t(lang, "btn.mode_to_no_vat") if mode == WITH_VAT else t(lang, "btn.mode_to_with_vat")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=ModeCB().pack())],
            [_cancel_button(lang)],
        ]
    )


def cancel_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_cancel_button(lang)]])


def draft_kb(has_items: bool, lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "btn.add_more"), callback_data=DraftCB(action="add"))
    if has_items:
        b.button(text=t(lang, "btn.finish"), callback_data=DraftCB(action="finish"))
        b.button(text=t(lang, "btn.undo"), callback_data=DraftCB(action="undo"))
    b.button(text=t(lang, "btn.cancel"), callback_data=DraftCB(action="cancel"))
    b.adjust(2)
    return b.as_markup()
