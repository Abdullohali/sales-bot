"""Main flow: courier records a sale (TZ §4)."""

import logging
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    BTN_NEW_SALE,
    BTN_REPORT,
    PAGE_SIZE,
    DraftCB,
    ModeCB,
    PageCB,
    PickCB,
    cancel_kb,
    draft_kb,
    main_menu,
    picker_kb,
    price_mode_kb,
)
from app.bot.middlewares import RoleFilter
from app.bot.notify import send_invoice
from app.bot.parsers import parse_positive
from app.bot.states import SaleFlow
from app.config import Settings
from app.db.models import Client, Product
from app.i18n import t, variants
from app.services.catalog import ensure_courier, get_langs, list_page
from app.services.clock import today_local
from app.services.formatting import fmt_money, fmt_price, fmt_qty
from app.services.reports import daily_report, render_courier_report, render_report, vat_label
from app.services.sales import SaleError, build_item, create_sale, draft_item_amounts, draft_totals
from app.services.vat import NO_VAT, WITH_VAT

log = logging.getLogger(__name__)

router = Router(name="sale")
router.message.filter(RoleFilter("admin", "courier"))
router.callback_query.filter(RoleFilter("admin", "courier"))

KINDS = {"c": Client, "p": Product}


# ---------- helpers ----------


async def _send_picker(
    target: Message, state: FSMContext, session: AsyncSession, kind: str, lang: str, page: int = 0, edit: bool = False
) -> None:
    data = await state.get_data()
    q = data.get(f"q_{kind}")
    rows, total = await list_page(session, KINDS[kind], search=q, offset=page * PAGE_SIZE, limit=PAGE_SIZE)
    if not rows and page > 0:  # list shrank (e.g. item deactivated) -> back to first page
        page = 0
        rows, total = await list_page(session, KINDS[kind], search=q, limit=PAGE_SIZE)

    lines = []
    if kind == "p":
        lines.append(t(lang, "picker.client", name=data.get("client_name")))
    lines.append(t(lang, "picker.choose_client" if kind == "c" else "picker.choose_product"))
    if q:
        lines.append(t(lang, "picker.found", q=q, n=total))
    elif total == 0:
        lines.append(t(lang, "picker.empty"))
    text = "\n".join(lines)
    kb = picker_kb(kind, rows, page, total, searching=bool(q), lang=lang)
    if edit:
        await target.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


def _price_prompt(data: dict, lang: str) -> str:
    cur = data["cur"]
    mode_label = t(lang, "mode.with_vat" if data.get("mode") == WITH_VAT else "mode.no_vat")
    qty = fmt_qty(Decimal(data["qty"]))
    return t(lang, "price.prompt", name=cur["name"], qty=qty, unit=cur["unit"], mode=mode_label)


def render_draft(data: dict, lang: str) -> str:
    items = data.get("items") or []
    lines = [t(lang, "draft.title"), t(lang, "picker.client", name=data.get("client_name")), ""]
    if not items:
        lines.append(t(lang, "draft.empty"))
        return "\n".join(lines)
    for n, it in enumerate(items, start=1):
        a = draft_item_amounts(it)
        lines.append(
            f"{n}. {it['name']} — {fmt_qty(Decimal(it['qty']))} {it['unit']} × "
            f"{fmt_price(Decimal(it['price_ex']))} = {fmt_money(a.ex)}"
        )
        if it["mode"] == WITH_VAT:
            lines.append("    " + t(lang, "draft.entered_with_vat", price=fmt_price(Decimal(it["entered_price"]))))
    tot = draft_totals(items)
    rates = {Decimal(i["vat_rate"]) for i in items}
    lines += [
        "",
        t(lang, "draft.sum_ex", v=fmt_money(tot.ex)),
        f"{vat_label(rates, lang)}: {fmt_money(tot.vat)}",
        t(lang, "draft.total", v=fmt_money(tot.total)),
    ]
    return "\n".join(lines)


async def _drop_kb(cb: CallbackQuery) -> None:
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # message too old / already edited
        pass


# ---------- menu ----------


@router.message(F.text.in_(variants(BTN_NEW_SALE)))
@router.message(Command("sale"))
async def new_sale(msg: Message, state: FSMContext, session: AsyncSession, lang: str) -> None:
    await state.clear()
    await state.set_state(SaleFlow.choose_client)
    await state.update_data(mode=NO_VAT, items=[])
    await _send_picker(msg, state, session, "c", lang)


@router.message(F.text.in_(variants(BTN_REPORT)))
async def today_report(msg: Message, session: AsyncSession, role: str, lang: str) -> None:
    day = today_local()
    if role == "admin":
        await msg.answer(render_report(await daily_report(session, day), lang), reply_markup=main_menu(lang))
    else:
        rep = await daily_report(session, day, courier_id=msg.from_user.id)
        await msg.answer(render_courier_report(rep, lang), reply_markup=main_menu(lang))


@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await msg.answer(t(lang, "sale.cancelled"), reply_markup=main_menu(lang))


# ---------- choose client / product ----------


@router.message(StateFilter(SaleFlow.choose_client, SaleFlow.choose_product), F.text, ~F.text.startswith("/"))
async def search(msg: Message, state: FSMContext, session: AsyncSession, lang: str) -> None:
    kind = "c" if await state.get_state() == SaleFlow.choose_client.state else "p"
    await state.update_data(**{f"q_{kind}": msg.text.strip()[:50]})
    await _send_picker(msg, state, session, kind, lang)


@router.callback_query(StateFilter(SaleFlow.choose_client, SaleFlow.choose_product), PageCB.filter())
async def paginate(
    cb: CallbackQuery, callback_data: PageCB, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    expected = "c" if await state.get_state() == SaleFlow.choose_client.state else "p"
    if callback_data.kind != expected:
        await cb.answer(t(lang, "stale"), show_alert=True)
        return
    if callback_data.reset:
        await state.update_data(**{f"q_{expected}": None})
    await _send_picker(cb.message, state, session, expected, lang, callback_data.page, edit=True)
    await cb.answer()


@router.callback_query(SaleFlow.choose_client, PickCB.filter(F.kind == "c"))
async def pick_client(
    cb: CallbackQuery, callback_data: PickCB, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    client = await session.get(Client, callback_data.id)
    if not client or not client.active:
        await cb.answer(t(lang, "client.unavailable"), show_alert=True)
        return
    await state.update_data(client_id=client.id, client_name=client.name, q_c=None, q_p=None)
    await state.set_state(SaleFlow.choose_product)
    await cb.message.edit_text(t(lang, "client.chosen", name=client.name))
    await _send_picker(cb.message, state, session, "p", lang)
    await cb.answer()


@router.callback_query(SaleFlow.choose_product, PickCB.filter(F.kind == "p"))
async def pick_product(
    cb: CallbackQuery, callback_data: PickCB, state: FSMContext, session: AsyncSession, lang: str
) -> None:
    product = await session.get(Product, callback_data.id)
    if not product or not product.active:
        await cb.answer(t(lang, "product.unavailable"), show_alert=True)
        return
    await state.update_data(cur={"id": product.id, "name": product.name, "unit": product.unit}, q_p=None)
    await state.set_state(SaleFlow.enter_qty)
    await cb.message.edit_text(t(lang, "product.chosen", name=product.name))
    await cb.message.answer(t(lang, "qty.prompt", unit=product.unit), reply_markup=cancel_kb(lang))
    await cb.answer()


# ---------- qty / price ----------


@router.message(SaleFlow.enter_qty, F.text, ~F.text.startswith("/"))
async def got_qty(msg: Message, state: FSMContext, lang: str) -> None:
    qty = parse_positive(msg.text)
    if qty is None or qty.quantize(Decimal("0.001")) <= 0:
        await msg.answer(t(lang, "qty.invalid"))
        return
    await state.update_data(qty=str(qty))
    await state.set_state(SaleFlow.enter_price)
    data = await state.get_data()
    await msg.answer(_price_prompt(data, lang), reply_markup=price_mode_kb(data.get("mode", NO_VAT), lang))


@router.callback_query(SaleFlow.enter_price, ModeCB.filter())
async def toggle_mode(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    mode = NO_VAT if data.get("mode") == WITH_VAT else WITH_VAT
    await state.update_data(mode=mode)  # kept until the end of this invoice
    data["mode"] = mode
    await cb.message.edit_text(_price_prompt(data, lang), reply_markup=price_mode_kb(mode, lang))
    await cb.answer(t(lang, "mode.toast_with_vat" if mode == WITH_VAT else "mode.toast_no_vat"))


@router.message(SaleFlow.enter_price, F.text, ~F.text.startswith("/"))
async def got_price(msg: Message, state: FSMContext, session: AsyncSession, settings: Settings, lang: str) -> None:
    price = parse_positive(msg.text)
    if price is None:
        await msg.answer(t(lang, "price.invalid"))
        return
    data = await state.get_data()
    product = await session.get(Product, data["cur"]["id"])
    if product is None:
        await state.clear()
        await msg.answer(t(lang, "stale"), reply_markup=main_menu(lang))
        return
    try:
        item = build_item(product, Decimal(data["qty"]), price, data.get("mode", NO_VAT), settings.VAT_RATE)
    except SaleError as e:
        await msg.answer(t(lang, e.key))
        return
    items = [*data.get("items", []), item]
    await state.update_data(items=items, cur=None, qty=None)
    await state.set_state(SaleFlow.draft)
    data["items"] = items
    await msg.answer(render_draft(data, lang), reply_markup=draft_kb(True, lang))


# ---------- draft actions ----------


@router.callback_query(StateFilter(SaleFlow), DraftCB.filter(F.action == "cancel"))
async def draft_cancel(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    if await state.get_state() == SaleFlow.saving.state:
        await cb.answer(t(lang, "sale.already_saving"))
        return
    await state.clear()
    await _drop_kb(cb)
    await cb.message.answer(t(lang, "sale.cancelled"), reply_markup=main_menu(lang))
    await cb.answer()


@router.callback_query(SaleFlow.draft, DraftCB.filter(F.action == "add"))
async def draft_add(cb: CallbackQuery, state: FSMContext, session: AsyncSession, lang: str) -> None:
    await state.set_state(SaleFlow.choose_product)
    await state.update_data(q_p=None)
    await _drop_kb(cb)
    await _send_picker(cb.message, state, session, "p", lang)
    await cb.answer()


@router.callback_query(SaleFlow.draft, DraftCB.filter(F.action == "undo"))
async def draft_undo(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    items = data.get("items") or []
    if items:
        items.pop()
    await state.update_data(items=items)
    data["items"] = items
    await cb.message.edit_text(render_draft(data, lang), reply_markup=draft_kb(bool(items), lang))
    await cb.answer(t(lang, "draft.undone"))


@router.callback_query(SaleFlow.draft, DraftCB.filter(F.action == "finish"))
async def draft_finish(
    cb: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings, bot: Bot, role: str, lang: str
) -> None:
    data = await state.get_data()
    items = data.get("items") or []
    if not items:
        await cb.answer(t(lang, "sale.no_items"), show_alert=True)
        return
    await state.set_state(SaleFlow.saving)
    user = cb.from_user
    try:
        if role == "admin":
            await ensure_courier(session, user.id, user.full_name)
        sale = await create_sale(session, client_id=data["client_id"], courier_id=user.id, items=items)
    except Exception:
        log.exception("failed to save sale")
        await session.rollback()
        await state.set_state(SaleFlow.draft)
        await cb.answer(t(lang, "sale.save_error"), show_alert=True)
        return

    await state.clear()
    await _drop_kb(cb)
    await cb.answer(t(lang, "sale.saved_toast", id=sale.id))
    await cb.message.answer(t(lang, "sale.saved", id=sale.id), reply_markup=main_menu(lang))
    recipients = [user.id, *settings.ADMIN_IDS]
    langs = {**await get_langs(session, recipients), user.id: lang}
    await send_invoice(bot, sale, settings, recipients, langs)


# ---------- stale buttons (state lost: restart, TTL expired, old message) ----------


@router.callback_query(PickCB.filter())
@router.callback_query(PageCB.filter())
@router.callback_query(ModeCB.filter())
@router.callback_query(DraftCB.filter())
async def stale(cb: CallbackQuery, lang: str) -> None:
    await _drop_kb(cb)
    await cb.answer(t(lang, "stale"), show_alert=True)
