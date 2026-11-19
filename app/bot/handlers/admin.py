"""Admin commands (TZ §6)."""

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.middlewares import RoleFilter
from app.bot.notify import answer_long, send_invoice
from app.config import Settings
from app.db.models import Client, Courier, Product
from app.i18n import t
from app.services import catalog, importer
from app.services.clock import parse_date, today_local
from app.services.excel import build_sales_export, export_filename
from app.services.reports import daily_report, render_report, render_sales_list
from app.services.sales import get_sale, list_sales, soft_delete_sale

router = Router(name="admin")
router.message.filter(RoleFilter("admin"))


def _arg(command: CommandObject) -> str:
    return (command.args or "").strip()


# ---------- clients ----------


@router.message(Command("addclient"))
async def addclient(msg: Message, command: CommandObject, session: AsyncSession, lang: str) -> None:
    name, _, inn = _arg(command).partition(";")
    if not name.strip():
        await msg.answer(t(lang, "fmt.addclient"))
        return
    try:
        client, created = await catalog.add_client(session, name, inn)
    except catalog.InvalidInn as e:
        await msg.answer(t(lang, "client.bad_inn", inn=str(e)))
        return
    text = t(lang, "client.added" if created else "client.exists", name=client.name)
    if client.inn:
        text += "\n" + t(lang, "client.inn", inn=client.inn)
    await msg.answer(text)


@router.message(Command("delclient"))
async def delclient(msg: Message, command: CommandObject, session: AsyncSession, lang: str) -> None:
    name = _arg(command)
    if not name:
        await msg.answer(t(lang, "fmt.delclient"))
        return
    ok = await catalog.deactivate_client(session, name)
    await msg.answer(t(lang, "client.hidden", name=name) if ok else t(lang, "client.not_found"))


@router.message(Command("clients"))
async def clients(msg: Message, session: AsyncSession, lang: str) -> None:
    rows, total = await catalog.list_page(session, Client)
    if not rows:
        await msg.answer(t(lang, "clients.none"))
        return
    lines = [
        f"{i}. {c.name}" + (f" · {t(lang, 'client.inn', inn=c.inn)}" if c.inn else "") for i, c in enumerate(rows, 1)
    ]
    text = t(lang, "clients.title", n=total) + "\n" + "\n".join(lines)
    await answer_long(msg, text)


# ---------- products ----------


@router.message(Command("addproduct"))
async def addproduct(msg: Message, command: CommandObject, session: AsyncSession, lang: str) -> None:
    parts = [p.strip() for p in _arg(command).split(";")]
    if not parts or not parts[0]:
        await msg.answer(t(lang, "fmt.addproduct"))
        return
    parts += [""] * (4 - len(parts))
    res = await catalog.upsert_product(session, *parts[:4], lang=lang)
    p = res.product
    text = (
        t(lang, "product.added" if res.created else "product.updated", name=p.name)
        + "\n"
        + t(lang, "product.details", unit=p.unit, ikpu=p.ikpu or "—", code=p.unit_code or "—")
    )
    if res.warnings:
        text += "\n⚠️ " + "\n⚠️ ".join(res.warnings)
    await msg.answer(text)


@router.message(Command("delproduct"))
async def delproduct(msg: Message, command: CommandObject, session: AsyncSession, lang: str) -> None:
    name = _arg(command)
    if not name:
        await msg.answer(t(lang, "fmt.delproduct"))
        return
    ok = await catalog.deactivate_product(session, name)
    await msg.answer(t(lang, "product.hidden", name=name) if ok else t(lang, "product.not_found"))


@router.message(Command("products"))
async def products(msg: Message, session: AsyncSession, lang: str) -> None:
    rows, total = await catalog.list_page(session, Product)
    if not rows:
        await msg.answer(t(lang, "products.none"))
        return
    lines = [t(lang, "products.title", n=total)]
    for i, p in enumerate(rows, 1):
        ikpu, code = p.ikpu or "—", p.unit_code or "—"
        lines.append(t(lang, "products.line", i=i, name=p.name, unit=p.unit, ikpu=ikpu, code=code))
    await answer_long(msg, "\n".join(lines))


@router.message(Command("template"))
async def template(msg: Message, lang: str) -> None:
    for n, kind in enumerate(importer.KINDS):
        await msg.answer_document(
            BufferedInputFile(importer.build_template(kind, lang), filename=importer.template_filename(kind, lang)),
            caption=t(lang, "template.caption") if n == 0 else None,
        )


@router.message(F.document)
async def import_file(msg: Message, session: AsyncSession, bot: Bot, lang: str) -> None:
    """Products, clients or couriers from .xlsx/.csv; the kind is detected from the header row."""
    doc = msg.document
    if not (doc.file_name or "").lower().endswith((".xlsx", ".csv")):
        await msg.answer(t(lang, "import.not_xlsx"))
        return
    if (doc.file_size or 0) > importer.MAX_BYTES:
        await msg.answer(t(lang, "import.too_big"))
        return
    buf = await bot.download(doc)
    parsed = importer.parse_any(buf.read(), doc.file_name or "", lang)
    if not parsed.rows:
        await msg.answer(t(lang, "import.failed") + "\n" + "\n".join(parsed.errors or [t(lang, "import.no_rows")]))
        return
    res = await catalog.import_rows(session, parsed.kind, parsed.rows, lang)
    text = t(
        lang,
        "import.done",
        what=t(lang, f"p.{parsed.kind}"),
        created=res.created,
        updated=res.updated,
        unchanged=res.unchanged,
    )
    notes = parsed.errors + res.warnings
    if notes:
        shown = notes[:40]
        text += "\n\n" + t(lang, "import.warnings") + "\n" + "\n".join(shown)
        if len(notes) > len(shown):
            text += "\n" + t(lang, "import.more", n=len(notes) - len(shown))
    await answer_long(msg, text)


# ---------- couriers ----------


@router.message(Command("courier"))
async def courier(msg: Message, command: CommandObject, session: AsyncSession, lang: str) -> None:
    parts = _arg(command).split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit():
        await msg.answer(t(lang, "fmt.courier"))
        return
    c, created = await catalog.set_courier(session, int(parts[0]), parts[1])
    await msg.answer(t(lang, "courier.added" if created else "courier.updated", name=c.name, id=c.tg_id))


@router.message(Command("delcourier"))
async def delcourier(msg: Message, command: CommandObject, session: AsyncSession, lang: str) -> None:
    arg = _arg(command)
    if not arg.isdigit():
        await msg.answer(t(lang, "fmt.delcourier"))
        return
    ok = await catalog.deactivate_courier(session, int(arg))
    await msg.answer(t(lang, "courier.disabled") if ok else t(lang, "courier.not_found"))


@router.message(Command("couriers"))
async def couriers(msg: Message, session: AsyncSession, lang: str) -> None:
    rows, total = await catalog.list_page(session, Courier)
    if not rows:
        await msg.answer(t(lang, "couriers.none"))
        return
    await answer_long(
        msg, t(lang, "couriers.title", n=total) + "\n" + "\n".join(f"• {c.name} — {c.tg_id}" for c in rows)
    )


# ---------- reports ----------


@router.message(Command("report"))
async def report(msg: Message, command: CommandObject, session: AsyncSession, lang: str) -> None:
    day = parse_date(command.args)
    if day is None:
        await msg.answer(t(lang, "fmt.date", cmd="report"))
        return
    await msg.answer(render_report(await daily_report(session, day), lang))


@router.message(Command("export"))
async def export(msg: Message, command: CommandObject, session: AsyncSession, lang: str) -> None:
    day = parse_date(command.args)
    if day is None:
        await msg.answer(t(lang, "fmt.date", cmd="export"))
        return
    sales = await list_sales(session, day)
    if not sales:
        await msg.answer(t(lang, "export.none", date=day.isoformat()))
        return
    await msg.answer_document(
        BufferedInputFile(build_sales_export(sales, lang), filename=export_filename(day, lang=lang))
    )


@router.message(Command("sales"))
async def sales_today(msg: Message, session: AsyncSession, lang: str) -> None:
    day = today_local()
    await answer_long(msg, render_sales_list(await list_sales(session, day), day, lang))


@router.message(Command("invoice"))
async def invoice(
    msg: Message, command: CommandObject, session: AsyncSession, bot: Bot, settings: Settings, lang: str
) -> None:
    arg = _arg(command).lstrip("№")
    if not arg.isdigit():
        await msg.answer(t(lang, "fmt.invoice"))
        return
    sale = await get_sale(session, int(arg))
    if sale is None:
        await msg.answer(t(lang, "invoice.not_found"))
        return
    await send_invoice(bot, sale, settings, [msg.chat.id], {msg.chat.id: lang})


@router.message(Command("delsale"))
async def delsale(msg: Message, command: CommandObject, session: AsyncSession, lang: str) -> None:
    arg = _arg(command).lstrip("№")
    if not arg.isdigit():
        await msg.answer(t(lang, "fmt.delsale"))
        return
    status = await soft_delete_sale(session, int(arg), by=f"tg:{msg.from_user.id}")
    await msg.answer(
        {
            "ok": t(lang, "delsale.ok", id=arg),
            "not_found": t(lang, "invoice.not_found"),
            "already": t(lang, "delsale.already", id=arg),
        }[status]
    )
