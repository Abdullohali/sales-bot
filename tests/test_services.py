from datetime import date
from decimal import Decimal as D
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.db.models import Sale
from app.services import catalog
from app.services.excel import (
    build_invoice_xlsx,
    build_products_template,
    build_sales_export,
    parse_products_xlsx,
)
from app.services.reports import daily_report, render_report
from app.services.sales import SaleError, build_item, create_sale, list_sales, sale_totals, soft_delete_sale
from app.services.vat import NO_VAT, WITH_VAT

DAY = date(2026, 11, 12)


async def _setup(session):
    c1, _ = await catalog.add_client(session, "Ресторан А")
    c2, _ = await catalog.add_client(session, "Сеть Б")
    tomato = (await catalog.upsert_product(session, "Помидоры", "кг", "12345678901234567", "166")).product
    cucumber = (await catalog.upsert_product(session, "Огурцы")).product
    courier, _ = await catalog.set_courier(session, 555, "Али")
    return c1, c2, tomato, cucumber, courier


async def _sale(session, client, courier, items, day=DAY):
    return await create_sale(session, client_id=client.id, courier_id=courier.tg_id, items=items, sale_date=day)


# ---------- catalog ----------


async def test_upsert_does_not_erase_ikpu_and_reactivates(session):
    await catalog.upsert_product(session, "Помидоры", "кг", "12345678901234567", "166")
    await catalog.deactivate_product(session, "помидоры")
    res = await catalog.upsert_product(session, "Помидоры", "", "", "")
    assert res.product.ikpu == "12345678901234567"
    assert res.product.unit_code == "166"
    assert res.product.unit == "кг"
    assert res.product.active and res.created


async def test_bad_ikpu_saved_with_warning(session):
    res = await catalog.upsert_product(session, "Лук", "кг", "123")
    assert res.product.ikpu == "123"
    assert res.warnings and "17" in res.warnings[0]


async def test_soft_delete_hides_from_lists(session):
    await catalog.add_client(session, "Alpha")
    await catalog.add_client(session, "Beta")
    assert await catalog.deactivate_client(session, "alpha")
    rows, total = await catalog.list_page(session, catalog.Client)
    assert [c.name for c in rows] == ["Beta"] and total == 1
    rows, total = await catalog.list_page(session, catalog.Client, search="bet")
    assert total == 1


async def test_roles(session):
    await catalog.set_courier(session, 555, "Али")
    assert await catalog.get_role(session, 1000, [1000]) == "admin"
    assert await catalog.get_role(session, 555, [1000]) == "courier"
    assert await catalog.get_role(session, 777, [1000]) is None
    await catalog.deactivate_courier(session, 555)
    assert await catalog.get_role(session, 555, [1000]) is None


# ---------- sales / reports ----------


async def test_sale_numbers_increment_and_totals(session):
    c1, c2, tomato, cucumber, courier = await _setup(session)
    s1 = await _sale(session, c1, courier, [build_item(tomato, D("25"), D("11200"), WITH_VAT, D("12"))])
    s2 = await _sale(session, c2, courier, [build_item(cucumber, D("10"), D("12000"), NO_VAT, D("12"))])
    assert s2.id == s1.id + 1
    assert s1.items[0].price_ex_vat == D("10000")
    t = sale_totals(s1)
    assert (t.ex, t.vat, t.total) == (D("250000.00"), D("30000.00"), D("280000.00"))


async def test_empty_sale_rejected(session):
    c1, _, _, _, courier = await _setup(session)
    with pytest.raises(SaleError):
        await _sale(session, c1, courier, [])


async def test_vat_rate_snapshot_protects_old_invoices(session):
    c1, _, tomato, _, courier = await _setup(session)
    old = await _sale(session, c1, courier, [build_item(tomato, D("1"), D("100"), NO_VAT, D("12"))])
    new = await _sale(session, c1, courier, [build_item(tomato, D("1"), D("100"), NO_VAT, D("15"))])
    assert sale_totals(old).vat == D("12.00")
    assert sale_totals(new).vat == D("15.00")


async def test_report_matches_tz_example_and_excludes_deleted(session):
    c1, c2, tomato, cucumber, courier = await _setup(session)
    await _sale(session, c1, courier, [build_item(tomato, D("27.675"), D("10000"), NO_VAT, D("12"))])
    await _sale(session, c2, courier, [build_item(cucumber, D("10"), D("12000"), NO_VAT, D("12"))])
    gone = await _sale(session, c2, courier, [build_item(cucumber, D("1"), D("99999"), NO_VAT, D("12"))])
    await _sale(session, c2, courier, [build_item(cucumber, D("1"), D("1"), NO_VAT, D("12"))], day=date(2026, 11, 11))

    assert await soft_delete_sale(session, gone.id, by="tg:1000") == "ok"
    assert await soft_delete_sale(session, gone.id, by="tg:1000") == "already"
    assert await soft_delete_sale(session, 99999, by="tg:1000") == "not_found"

    text = render_report(await daily_report(session, DAY))
    assert text == (
        "Продажи за 2026-11-12 (накладных: 2)\n\n"
        "• Ресторан А: 276 750\n"
        "• Сеть Б: 120 000\n\n"
        "Итого без НДС: 396 750\n"
        "НДС 12%: 47 610\n"
        "Итого с НДС: 444 360"
    )
    # deleted invoice still in DB, with audit
    deleted = await session.get(Sale, gone.id)
    assert deleted.is_deleted and deleted.deleted_by == "tg:1000" and deleted.deleted_at


async def test_courier_report_only_own_sales(session):
    c1, _, tomato, _, courier = await _setup(session)
    other, _ = await catalog.set_courier(session, 666, "Вали")
    await _sale(session, c1, courier, [build_item(tomato, D("1"), D("100"), NO_VAT, D("12"))])
    await _sale(session, c1, other, [build_item(tomato, D("1"), D("500"), NO_VAT, D("12"))])
    rep = await daily_report(session, DAY, courier_id=courier.tg_id)
    assert rep.sale_count == 1 and rep.totals.ex == D("100.00")


# ---------- Excel ----------


async def test_invoice_xlsx_contents(session):
    c1, _, tomato, cucumber, courier = await _setup(session)
    sale = await _sale(
        session,
        c1,
        courier,
        [
            build_item(tomato, D("25"), D("10000"), WITH_VAT, D("12")),
            build_item(cucumber, D("12.5"), D("8500"), NO_VAT, D("12")),
        ],
    )
    ws = load_workbook(BytesIO(build_invoice_xlsx(sale, "ООО Тест", "123456789"))).active
    assert ws["A1"].value == f"НАКЛАДНАЯ № {sale.id} от 2026-11-12"
    assert "ИНН 123456789" in ws["A3"].value
    assert ws["A4"].value == "Покупатель: Ресторан А"
    header = [c.value for c in ws[8]]
    assert header == ["№", "Товар", "ИКПУ", "Ед.", "Кол-во", "Цена без НДС", "Сумма без НДС", "НДС 12%", "Сумма с НДС"]
    assert ws["C9"].value == "12345678901234567" and ws["C9"].number_format == "@"
    # totals row equals manual calculation: 25*10000 (with VAT) + 12.5*8500*1.12
    total_row = 11
    assert ws.cell(row=total_row, column=2).value == "ИТОГО"
    manual_total = D("250000") + D("12.5") * D("8500") * D("1.12")
    assert D(str(ws.cell(row=total_row, column=9).value)) == manual_total
    ex, vat = ws.cell(row=total_row, column=7).value, ws.cell(row=total_row, column=8).value
    assert D(str(ex)) + D(str(vat)) == manual_total


async def test_export_one_row_per_item(session):
    c1, _, tomato, cucumber, courier = await _setup(session)
    await _sale(
        session,
        c1,
        courier,
        [build_item(tomato, D("1"), D("100"), NO_VAT, D("12")), build_item(cucumber, D("2"), D("50"), NO_VAT, D("12"))],
    )
    ws = load_workbook(BytesIO(build_sales_export(await list_sales(session, DAY)))).active
    assert ws.max_row == 3
    row = [c.value for c in ws[2]][:8]
    assert row == ["2026-11-12", 1, "Ресторан А", None, "Али", "Помидоры", "12345678901234567", "кг"]


async def test_client_inn_in_invoice_and_export(session):
    c1, _, tomato, _, courier = await _setup(session)
    await catalog.add_client(session, c1.name, "123 456 789")  # existing client: INN is set
    sale = await _sale(session, c1, courier, [build_item(tomato, D("1"), D("100"), NO_VAT, D("12"))])
    ws = load_workbook(BytesIO(build_invoice_xlsx(sale, "ООО Тест", ""))).active
    assert ws["A4"].value == "Покупатель: Ресторан А, ИНН 123456789"
    ws = load_workbook(BytesIO(build_sales_export(await list_sales(session, DAY)))).active
    assert ws["C1"].value == "Клиент" and ws["D1"].value == "ИНН клиента"
    assert ws["D2"].value == "123456789" and ws["D2"].number_format == "@"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, None), ("", None), ("  ", None), ("123 456 789", "123456789"), ("123-456-789", "123456789"),
     (123456789, "123456789"), (12345678901234.0, "12345678901234"), ("31234567890123", "31234567890123")],
)  # fmt: skip
def test_normalize_inn(raw, expected):
    assert catalog.normalize_inn(raw) == expected


@pytest.mark.parametrize("raw", ["12345678", "1234567890", "12345678a", "1234567890123456"])
def test_normalize_inn_rejects(raw):
    with pytest.raises(catalog.InvalidInn):
        catalog.normalize_inn(raw)


async def test_add_client_inn_rules(session):
    c, _ = await catalog.add_client(session, "Alpha", "123456789")
    await catalog.add_client(session, "alpha")  # empty INN keeps the stored one
    assert c.inn == "123456789"
    with pytest.raises(catalog.InvalidInn):
        await catalog.add_client(session, "Beta", "12")
    assert (await catalog.list_page(session, catalog.Client))[1] == 1  # nothing saved
    await catalog.add_client(session, "Gamma", "123456789")  # branches may share an INN
    rows, total = await catalog.list_page(session, catalog.Client, search="456 78")
    assert total == 2 and [r.name for r in rows] == ["Alpha", "Gamma"]


async def test_template_and_import_roundtrip(session):
    rows, errors = parse_products_xlsx(build_products_template())
    assert errors == []
    assert rows == [{"name": "Помидоры", "unit": "кг", "ikpu": "00000000000000000", "unit_code": None}]
    ws = load_workbook(BytesIO(build_products_template())).active
    assert ws["C2"].number_format == "@" and ws["D500"].number_format == "@"

    res = await catalog.import_products(session, rows + [{"name": "Лук", "unit": None, "ikpu": "1", "unit_code": None}])
    assert (res.created, res.updated) == (2, 0)
    assert len(res.warnings) == 1
    luk = (await catalog.upsert_product(session, "Лук")).product
    assert luk.unit == "кг"


def test_import_rejects_garbage():
    rows, errors = parse_products_xlsx(b"not an excel file")
    assert rows == [] and errors
