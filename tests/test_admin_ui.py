"""Admin panel look: dashboard, theme assets, layout."""

from decimal import Decimal as D

from app.services import catalog
from app.services.sales import build_item, create_sale
from app.services.vat import NO_VAT
from tests.test_import import login, panel  # noqa: F401  (fixture)


async def test_dashboard_empty(panel):  # noqa: F811
    login(panel, "boss")
    r = panel.get("/admin/?lang=en")
    assert r.status_code == 200
    assert "Welcome, boss" in r.text and "Sales, last 7 days" in r.text and "No invoices yet" in r.text


async def test_dashboard_numbers(panel, session):  # noqa: F811
    client, _ = await catalog.add_client(session, "Ресторан А")
    product = (await catalog.upsert_product(session, "Помидоры", "кг")).product
    await catalog.set_courier(session, 555, "Али")
    await create_sale(
        session, client_id=client.id, courier_id=555, items=[build_item(product, D("10"), D("1000"), NO_VAT, D("12"))]
    )

    login(panel, "boss")
    r = panel.get("/admin/?lang=uz")
    assert r.status_code == 200
    assert "Bugungi savdo (QQS bilan)" in r.text
    assert '<div class="app-stat-value">11 200</div>' in r.text  # 10 × 1000 + 12% VAT
    assert "№1" in r.text and "Ресторан А" in r.text
    assert r.text.count('class="app-bar') >= 7


async def test_theme_assets_and_layout(panel):  # noqa: F811
    r = panel.get("/admin/login?lang=ru")
    assert "/admin-assets/theme.css?v=" in r.text and "fa-basket-shopping" in r.text

    css = panel.get("/admin-assets/theme.css")
    assert css.status_code == 200 and "prefers-reduced-motion" in css.text

    login(panel, "buh")
    r = panel.get("/admin/client/list?lang=ru")
    assert 'class="app-chip"' in r.text and "Бухгалтер" in r.text  # user chip in the top bar
    assert "Главная" in r.text  # dashboard link in the sidebar
