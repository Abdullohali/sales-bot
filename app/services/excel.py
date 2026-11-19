"""Excel files: invoice (§5.4), sales export (§5.5), product template and import (§5.7)."""

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from app.db.models import Sale
from app.i18n import t
from app.services import importer
from app.services.formatting import fmt_date
from app.services.reports import vat_label
from app.services.sales import item_amounts, sale_totals

MONEY_FMT = "#,##0.00"
QTY_FMT = "#,##0.###"
TEXT_FMT = "@"
THIN = Side(style="thin")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BOLD = Font(bold=True)


def _to_bytes(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _num(x: Decimal) -> float | int:
    """openpyxl writes Decimal fine, but normalise to keep cells numeric and clean."""
    return int(x) if x == x.to_integral_value() else float(x)


def _widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


# ---------- invoice ----------


def invoice_filename(sale: Sale, lang: str | None = None) -> str:
    return t(lang, "xl.invoice_file", id=sale.id)


def build_invoice_xlsx(sale: Sale, company_name: str, company_inn: str, lang: str | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = t(lang, "xl.invoice_sheet", id=sale.id)[:31]  # Excel sheet title limit

    ws["A1"] = t(lang, "xl.invoice_title", id=sale.id, date=fmt_date(sale.sale_date))
    ws["A1"].font = Font(bold=True, size=14)
    ws["A3"] = t(lang, "xl.supplier", name=company_name) + (t(lang, "xl.inn", inn=company_inn) if company_inn else "")
    buyer_inn = t(lang, "xl.inn", inn=sale.client.inn) if sale.client.inn else ""
    ws["A4"] = t(lang, "xl.buyer", name=sale.client.name) + buyer_inn
    ws["A5"] = t(lang, "xl.courier", name=sale.courier.name)
    if sale.is_deleted:
        ws["A6"] = t(lang, "xl.deleted")
        ws["A6"].font = Font(bold=True, color="C00000")

    rates = {i.vat_rate for i in sale.items}
    header = [
        t(lang, "col.n"), t(lang, "col.product"), t(lang, "col.ikpu"), t(lang, "col.unit"), t(lang, "col.qty"),
        t(lang, "col.price_ex"), t(lang, "col.sum_ex"), vat_label(rates, lang), t(lang, "col.sum_total"),
    ]  # fmt: skip
    hr = 8
    for col, title in enumerate(header, start=1):
        c = ws.cell(row=hr, column=col, value=title)
        c.font = BOLD
        c.border = BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    r = hr
    for n, item in enumerate(sale.items, start=1):
        r += 1
        a = item_amounts(item)
        values = [
            n,
            item.product.name,
            item.product.ikpu or "",
            item.product.unit,
            _num(item.qty),
            _num(item.price_ex_vat.quantize(Decimal("0.01"))),
            _num(a.ex),
            _num(a.vat),
            _num(a.total),
        ]
        for col, v in enumerate(values, start=1):
            c = ws.cell(row=r, column=col, value=v)
            c.border = BORDER
        ws.cell(row=r, column=3).number_format = TEXT_FMT
        ws.cell(row=r, column=5).number_format = QTY_FMT
        for col in (6, 7, 8, 9):
            ws.cell(row=r, column=col).number_format = MONEY_FMT

    tot = sale_totals(sale)
    r += 1
    ws.cell(row=r, column=2, value=t(lang, "xl.total")).font = BOLD
    for col, v in ((7, tot.ex), (8, tot.vat), (9, tot.total)):
        c = ws.cell(row=r, column=col, value=_num(v))
        c.font = BOLD
        c.number_format = MONEY_FMT
    for col in range(1, 10):
        ws.cell(row=r, column=col).border = BORDER

    r += 3
    ws.cell(row=r, column=2, value=t(lang, "xl.released"))
    ws.cell(row=r, column=6, value=t(lang, "xl.received"))

    _widths(ws, [5, 32, 20, 7, 10, 14, 16, 14, 16])
    return _to_bytes(wb)


# ---------- sales export ----------

EXPORT_COLUMNS = [
    "col.date", "col.invoice_no", "col.client", "col.client_inn", "col.courier", "col.product", "col.ikpu", "col.unit",
    "col.qty", "col.price_ex", "col.sum_ex", "vat", "col.sum_total",
]  # fmt: skip


def export_header(lang: str | None = None) -> list[str]:
    return [t(lang, key) for key in EXPORT_COLUMNS]


def export_filename(date_from: date, date_to: date | None = None, lang: str | None = None) -> str:
    period = fmt_date(date_from)
    if date_to and date_to != date_from:
        period = f"{fmt_date(date_from)}_{fmt_date(date_to)}"
    return t(lang, "xl.export_file", period=period)


def build_sales_export(sales: list[Sale], lang: str | None = None) -> bytes:
    """One row = one invoice line."""
    wb = Workbook()
    ws = wb.active
    ws.title = t(lang, "xl.sales_sheet")
    ws.append(export_header(lang))
    for c in ws[1]:
        c.font = BOLD
    for s in sales:
        for item in s.items:
            a = item_amounts(item)
            ws.append([
                fmt_date(s.sale_date),
                s.id,
                s.client.name,
                s.client.inn or "",
                s.courier.name,
                item.product.name,
                item.product.ikpu or "",
                item.product.unit,
                _num(item.qty),
                _num(item.price_ex_vat.quantize(Decimal("0.01"))),
                _num(a.ex),
                _num(a.vat),
                _num(a.total),
            ])  # fmt: skip
            row = ws.max_row
            for col in (4, 7):  # INN, IKPU: digit codes stay text
                ws.cell(row=row, column=col).number_format = TEXT_FMT
            ws.cell(row=row, column=9).number_format = QTY_FMT
            for col in (10, 11, 12, 13):
                ws.cell(row=row, column=col).number_format = MONEY_FMT
    ws.freeze_panes = "A2"
    _widths(ws, [12, 12, 28, 16, 18, 28, 20, 7, 10, 14, 16, 14, 16])
    return _to_bytes(wb)


# ---------- product template / import (kept for existing callers; see app/services/importer.py) ----------


def template_filename(lang: str | None = None) -> str:
    return importer.template_filename("products", lang)


def build_products_template(lang: str | None = None) -> bytes:
    return importer.build_template("products", lang)


def parse_products_xlsx(data: bytes, lang: str | None = None) -> tuple[list[dict], list[str]]:
    res = importer.parse("products", data, "products.xlsx", lang)
    return res.rows, res.errors
