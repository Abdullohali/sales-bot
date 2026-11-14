from pathlib import Path

from fastapi import FastAPI
from sqladmin import Admin
from sqladmin.authentication import login_required
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from starlette.requests import Request
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from app.admin.auth import AdminAuth, is_admin
from app.admin.dashboard import dashboard_data
from app.admin.i18n import install_locales, lazy, panel_lang, pt
from app.admin.pages import ImportView, ReportsView
from app.admin.views import ALL_VIEWS
from app.i18n import LANG_NAMES
from app.services.formatting import fmt_money

ADMIN_DIR = Path(__file__).parent
TEMPLATES_DIR = str(ADMIN_DIR / "templates")
STATIC_DIR = ADMIN_DIR / "static"
ASSETS_URL = "/admin-assets"  # referenced in templates/_theme_head.html


class PanelAdmin(Admin):
    """sqladmin with our dashboard as the home page."""

    def __init__(self, *args, **kwargs) -> None:
        engine = args[1] if len(args) > 1 else kwargs["engine"]
        self._dashboard_sessions = async_sessionmaker(engine, expire_on_commit=False)
        super().__init__(*args, **kwargs)

    @login_required
    async def index(self, request: Request) -> Response:
        async with self._dashboard_sessions() as session:
            data = await dashboard_data(session)
        return await self.templates.TemplateResponse(request, "sqladmin/index.html", {"d": data, "fmt": fmt_money})


def _theme_version() -> str:
    """Changes whenever theme.css changes: browsers cache the file and re-download only after edits."""
    return str(int((STATIC_DIR / "theme.css").stat().st_mtime))


def setup_admin(app: FastAPI, engine: AsyncEngine, secret_key: str) -> Admin:
    admin = PanelAdmin(
        app,
        engine,
        title=lazy("p.title"),
        base_url="/admin",
        templates_dir=TEMPLATES_DIR,
        authentication_backend=AdminAuth(secret_key=secret_key),
        i18n_config=install_locales(),
    )
    app.mount(ASSETS_URL, StaticFiles(directory=STATIC_DIR), name="admin-assets")
    # our own texts in templates: {{ t("p.r.daily") }}
    admin.templates.env.globals.update(
        t=pt, panel_lang=panel_lang, lang_names=LANG_NAMES, is_admin=is_admin, theme_version=_theme_version()
    )
    for view in ALL_VIEWS:
        admin.add_view(view)
    admin.add_base_view(ReportsView)
    admin.add_base_view(ImportView)
    return admin
