"""Custom admin pages: daily report, Excel export by date range, product import/template."""

from datetime import date

from fastapi import HTTPException
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.admin.auth import is_admin
from app.admin.i18n import lazy, panel_lang, pt
from app.db.session import SessionLocal
from app.services import catalog, importer
from app.services.clock import today_local
from app.services.excel import build_sales_export, export_filename
from app.services.formatting import fmt_money
from app.services.reports import daily_report, vat_label
from app.services.sales import list_sales

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_RANGE_DAYS = 366


def _date(value: str | None, default: date) -> date:
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        return default


def _xlsx(data: bytes, filename: str) -> Response:
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


class ReportsView(BaseView):
    name = lazy("p.reports")
    icon = "fa-solid fa-chart-line"

    @expose("/reports", methods=["GET"])
    async def reports(self, request: Request):
        today = today_local()
        day = _date(request.query_params.get("day"), today)
        async with SessionLocal() as session:
            rep = await daily_report(session, day)
        return await self.templates.TemplateResponse(
            request,
            "reports.html",
            {
                "title": pt("p.reports"),
                "day": day.isoformat(),
                "today": today.isoformat(),
                "rep": rep,
                "fmt": fmt_money,
                "vat_title": vat_label(rep.vat_rates, panel_lang()),
            },
        )

    @expose("/reports/export", methods=["GET"])
    async def export(self, request: Request):
        today = today_local()
        d_from = _date(request.query_params.get("from"), today)
        d_to = _date(request.query_params.get("to"), d_from)
        if d_to < d_from:
            d_from, d_to = d_to, d_from
        if (d_to - d_from).days > MAX_RANGE_DAYS:
            raise HTTPException(status_code=400, detail=pt("p.err.range"))
        async with SessionLocal() as session:
            sales = await list_sales(session, d_from, d_to)
        lang = panel_lang()
        return _xlsx(build_sales_export(sales, lang), export_filename(d_from, d_to, lang))


# list page identity of each importable directory (sqladmin: slug of the model class name)
IMPORT_LISTS = {"products": "product", "clients": "client", "couriers": "courier"}


class ImportView(BaseView):
    """Bulk import of products / clients / couriers from .xlsx or .csv (rules: docs/import-format.md).

    Not a menu item: each list page (Clients, Products, Couriers) has an "Import from file"
    button that opens a modal (templates/list_import.html) and posts here."""

    name = lazy("p.import")
    icon = "fa-solid fa-file-import"

    def is_accessible(self, request: Request) -> bool:
        return is_admin(request)

    def is_visible(self, request: Request) -> bool:
        return False

    @staticmethod
    def _kind(value) -> str:
        return value if value in importer.KINDS else "products"

    def _list_url(self, request: Request, kind: str):
        return request.url_for("admin:list", identity=IMPORT_LISTS[kind])

    @expose("/import", methods=["GET", "POST"])
    async def import_file(self, request: Request):
        if request.method == "GET":  # old links / bookmarks
            kind = self._kind(request.query_params.get("kind"))
            return RedirectResponse(self._list_url(request, kind), status_code=302)

        form = await request.form()
        kind = self._kind(form.get("kind"))
        upload = form.get("file")
        data = await upload.read(importer.MAX_BYTES + 1) if upload and hasattr(upload, "read") else b""
        lang = panel_lang()
        if not data:
            return JSONResponse({"ok": False, "error": pt("p.i.choose")})
        if len(data) > importer.MAX_BYTES:
            return JSONResponse({"ok": False, "error": pt("p.i.too_big")})

        parsed = importer.parse(kind, data, getattr(upload, "filename", "") or "", lang)
        if not parsed.rows:
            reasons = "; ".join(parsed.errors or [pt("import.no_rows")])
            return JSONResponse({"ok": False, "error": pt("p.i.failed", reasons=reasons)})
        async with SessionLocal() as session:
            res = await catalog.import_rows(session, kind, parsed.rows, lang)
        message = pt(
            "p.i.done", what=pt(f"p.{kind}"), created=res.created, updated=res.updated, unchanged=res.unchanged
        )
        return JSONResponse({"ok": True, "message": message, "notes": parsed.errors + res.warnings})

    @expose("/import/template", methods=["GET"])
    async def template(self, request: Request):
        kind = self._kind(request.query_params.get("kind"))
        lang = panel_lang()
        return _xlsx(importer.build_template(kind, lang), importer.template_filename(kind, lang))

    @expose("/products-import", methods=["GET"])
    async def old_url(self, request: Request):
        return RedirectResponse(self._list_url(request, "products"), status_code=302)
