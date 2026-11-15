"""Safe hard delete in the admin panel: admins only, never anything used in an invoice."""

from decimal import Decimal as D
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.db.models import AdminUser, Client, Courier, Product, Sale, Staff
from app.services import catalog
from app.services.sales import build_item, create_sale, soft_delete_sale
from app.services.vat import NO_VAT
from tests.test_import import login, panel  # noqa: F401  (fixture)


def delete(client, identity: str, *pks) -> str | None:
    """Calls the panel's delete route like the modal does; returns the error shown on the list page."""
    r = client.delete(f"/admin/{identity}/delete?pks={','.join(map(str, pks))}&lang=uz")
    assert r.status_code == 200, r.text
    return parse_qs(urlparse(r.text).query).get("error", [None])[0]


async def make_sale(session, client_name="Ресторан А", product_name="Помидоры", courier_id=555):
    client, _ = await catalog.add_client(session, client_name)
    product = (await catalog.upsert_product(session, product_name, "кг")).product
    await catalog.set_courier(session, courier_id, "Али")
    item = build_item(product, D("1"), D("10"), NO_VAT, D("12"))
    sale = await create_sale(session, client_id=client.id, courier_id=courier_id, items=[item])
    return client, product, sale


async def test_unused_rows_are_deleted(panel, session):  # noqa: F811
    client, _ = await catalog.add_client(session, "Bo'sh mijoz")
    product = (await catalog.upsert_product(session, "Olma", "кг")).product
    await catalog.set_courier(session, 777, "Vali")
    client_id, product_id = client.id, product.id
    login(panel, "boss")

    assert delete(panel, "client", client_id) is None
    assert delete(panel, "product", product_id) is None
    assert delete(panel, "courier", 777) is None
    session.expire_all()
    assert await session.get(Client, client_id) is None
    assert await session.get(Product, product_id) is None
    assert await session.get(Courier, 777) is None


async def test_rows_used_in_invoices_are_kept(panel, session):  # noqa: F811
    client, product, sale = await make_sale(session)
    ids = client.id, product.id, sale.id
    await soft_delete_sale(session, sale.id, by="test")  # even soft-deleted invoices protect their rows
    login(panel, "boss")

    err = delete(panel, "product", ids[1])
    assert "«Помидоры» 1 ta yuk xatida ishlatilgan" in err
    assert "«Ресторан А»" in delete(panel, "client", ids[0])
    assert "«Али»" in delete(panel, "courier", 555)
    session.expire_all()
    assert await session.get(Product, ids[1]) is not None
    assert await session.get(Client, ids[0]) is not None
    assert await session.get(Courier, 555) is not None
    assert await session.get(Sale, ids[2]) is not None


async def test_accountant_cannot_delete(panel, session):  # noqa: F811
    client_id = (await catalog.add_client(session, "Mijoz"))[0].id
    login(panel, "buh")
    r = panel.get("/admin/client/list?lang=uz")
    assert r.status_code == 200 and 'id="modal-delete"' not in r.text
    assert panel.delete(f"/admin/client/delete?pks={client_id}").status_code == 403
    session.expire_all()
    assert await session.get(Client, client_id) is not None


async def test_admin_sees_delete_button_with_translated_text(panel, session):  # noqa: F811
    await catalog.add_client(session, "Mijoz")
    login(panel, "boss")
    r = panel.get("/admin/client/list?lang=uz")
    assert 'id="modal-delete"' in r.text and "butunlay o\\u02bbchiriladi" in r.text  # JSON-escaped in the script


async def test_deleted_staff_loses_bot_access(panel, session):  # noqa: F811
    staff = Staff(name="Bobur", phone="998901112233", role="courier", tg_id=9001)
    session.add_all([staff, Courier(tg_id=9001, name="Bobur", active=True)])
    await session.commit()
    staff_id = staff.id
    assert await catalog.get_role(session, 9001, []) == "courier"
    login(panel, "boss")

    assert delete(panel, "staff", staff_id) is None
    session.expire_all()
    assert await session.get(Staff, staff_id) is None
    assert (await session.get(Courier, 9001)).active is False  # kept for old invoices, but no access
    assert await catalog.get_role(session, 9001, []) is None


async def test_panel_user_delete_rules(panel, session):  # noqa: F811
    login(panel, "boss")
    boss = await session.scalar(select(AdminUser).where(AdminUser.username == "boss"))
    buh = await session.scalar(select(AdminUser).where(AdminUser.username == "buh"))

    assert delete(panel, "admin-user", boss.id) == "Oʻzingizni oʻchira olmaysiz."
    assert await catalog.delete_blocker(session, boss) == ("p.del.last_admin", {})
    boss_id, buh_id = boss.id, buh.id
    assert delete(panel, "admin-user", buh_id) is None
    session.expire_all()
    assert await session.get(AdminUser, buh_id) is None
    assert await session.get(AdminUser, boss_id) is not None


async def test_invoices_are_never_hard_deleted(panel, session):  # noqa: F811
    sale_id = (await make_sale(session))[2].id
    login(panel, "boss")
    assert panel.delete(f"/admin/sale/delete?pks={sale_id}").status_code == 403
    session.expire_all()
    assert await session.get(Sale, sale_id) is not None


async def test_bulk_delete_skips_blocked_rows_and_reports_them(panel, session):  # noqa: F811
    used, _, _ = await make_sale(session)  # «Ресторан А» is in an invoice
    free1 = (await catalog.add_client(session, "Bo'sh 1"))[0].id
    free2 = (await catalog.add_client(session, "Bo'sh 2"))[0].id
    used_id = used.id
    login(panel, "boss")

    # the blocked row sits in the middle: the rows after it must still be deleted
    err = delete(panel, "client", free1, used_id, free2)
    assert "«Ресторан А»" in err
    session.expire_all()
    assert await session.get(Client, free1) is None
    assert await session.get(Client, free2) is None
    assert await session.get(Client, used_id) is not None


async def test_list_has_header_delete_button_instead_of_row_icons(panel, session):  # noqa: F811
    await catalog.add_client(session, "Mijoz")
    login(panel, "boss")
    r = panel.get("/admin/client/list?lang=uz")
    assert "bulk-delete" in r.text and '"O\\u02bbchirish"' in r.text
    assert "Tanlangan {n} ta yozuv" in r.text
