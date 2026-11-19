"""Bulk import of products / clients / couriers from .xlsx and .csv."""

from datetime import datetime
from io import BytesIO

import pytest
from aiogram.types import Update
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app.admin.auth import hash_password
from app.db.models import AdminUser, Client, Courier
from app.i18n import LANGS, t
from app.services import catalog, importer
from tests.test_bot_flow import ADMIN, Harness, texts


def xlsx(*rows) -> bytes:
    wb = Workbook()
    for r in rows:
        wb.active.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- templates ----------


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", importer.KINDS)
def test_every_template_parses_and_is_detected(kind, lang):
    data = importer.build_template(kind, lang)
    parsed = importer.parse(kind, data, "t.xlsx", lang)
    assert parsed.errors == [] and len(parsed.rows) == 1
    assert importer.parse_any(data, "t.xlsx", lang).kind == kind


def test_template_keeps_codes_as_text():
    ws = load_workbook(BytesIO(importer.build_template("couriers"))).active
    assert ws["A2"].number_format == "@" and ws["A1"].value == "Telegram ID"


# ---------- reading ----------


def test_csv_semicolon_windows_1251():
    data = "Клиент;Комментарий\nРесторан А;x\nКафе Б;\n".encode("cp1251")
    parsed = importer.parse("clients", data, "clients.csv")
    assert [r["name"] for r in parsed.rows] == ["Ресторан А", "Кафе Б"] and parsed.errors == []


def test_csv_comma_utf8_bom_any_column_order():
    data = "﻿Kuryer ismi,Telegram ID\nAli,555\nVali, 777 \n".encode()
    parsed = importer.parse("couriers", data, "c.csv")
    assert parsed.rows == [{"name": "Ali", "tg_id": "555"}, {"name": "Vali", "tg_id": "777"}]


def test_headerless_file_uses_template_order():
    parsed = importer.parse("couriers", xlsx([123, "Ali"], [456, "Vali"]), "c.xlsx")
    # first row is treated as the header row, the rest is data in template order
    assert parsed.rows == [{"tg_id": "456", "name": "Vali"}]


def test_old_xls_and_unknown_formats_are_rejected():
    assert importer.parse("clients", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest", "a.xls").errors == [t(None, "xl.xls_old")]
    assert importer.parse("clients", b"%PDF-1.4", "a.pdf").errors == [t(None, "xl.bad_format")]
    assert importer.parse("clients", b"", "a.csv").errors == [t(None, "xl.empty")]


def test_too_many_rows(monkeypatch):
    monkeypatch.setattr(importer, "MAX_ROWS", 2)
    parsed = importer.parse("clients", xlsx(["Клиент"], ["a"], ["b"], ["c"]), "c.xlsx", "en")
    assert parsed.rows == [] and "Too many rows: 3" in parsed.errors[0]


# ---------- validation ----------


def test_row_errors_are_reported_and_skipped():
    data = xlsx(
        ["Telegram ID", "Имя доставщика"],
        [555, "Али"],
        ["abc", "Вали"],  # bad id
        [None, "Без ID"],  # missing id
        [777, None],  # missing name
        [555.0, "Али 2"],  # duplicate (Excel float)
        [None, None],  # empty row: ignored silently
        [888, "Сардор"],
    )
    parsed = importer.parse("couriers", data, "c.xlsx", "en")
    assert [r["tg_id"] for r in parsed.rows] == ["555", "888"]
    assert parsed.errors == [
        "Row 3: Telegram ID «abc» must contain digits only — skipped",
        "Row 4: «Telegram ID» is empty — skipped",
        "Row 5: «Courier name» is empty — skipped",
        "Row 6: «Али 2» already appears above in the file — skipped",
    ]


def test_duplicate_names_are_case_insensitive():
    parsed = importer.parse("clients", xlsx(["Mijoz"], ["Kafe A"], ["kafe a"]), "c.xlsx", "uz")
    assert len(parsed.rows) == 1 and "3-qator" in parsed.errors[0]


def test_wrong_kind_is_explained():
    parsed = importer.parse("products", importer.build_template("clients", "uz"), "c.xlsx", "uz")
    assert parsed.rows == [] and parsed.errors == [t("uz", "xl.wrong_kind", kind=t("uz", "p.clients"))]


# ---------- saving ----------


async def test_import_clients(session):
    await catalog.add_client(session, "Ресторан А")
    await catalog.add_client(session, "Старый")
    await catalog.deactivate_client(session, "Старый")

    rows = importer.parse("clients", xlsx(["Клиент"], ["ресторан а"], ["Старый"], ["Новый  клиент"]), "c.xlsx").rows
    res = await catalog.import_clients(session, rows)
    assert (res.created, res.updated, res.unchanged) == (2, 0, 1)
    names = (await session.scalars(select(Client.name).where(Client.active.is_(True)).order_by(Client.name))).all()
    assert names == ["Новый клиент", "Ресторан А", "Старый"]


async def test_import_clients_inn(session):
    await catalog.add_client(session, "Kafe A", "111111111")
    await catalog.add_client(session, "Kafe B", "222222222")
    data = xlsx(
        ["Mijoz", "STIR"],
        ["Kafe A", None],  # empty INN: unchanged, stored INN kept
        ["Kafe B", "333 333 333"],  # new INN: updated
        ["Kafe C", 12345678901234],  # number cell, 14 digits (JShShIR)
        ["Kafe D", "12345"],  # invalid: skipped
    )
    parsed = importer.parse("clients", data, "c.xlsx", "uz")
    assert parsed.errors == [t("uz", "xl.row_bad_inn", n=5, v="12345")]
    res = await catalog.import_clients(session, parsed.rows)
    assert (res.created, res.updated, res.unchanged) == (1, 1, 1)
    inns = dict((await session.execute(select(Client.name, Client.inn))).all())
    assert inns == {"Kafe A": "111111111", "Kafe B": "333333333", "Kafe C": "12345678901234"}


def test_clients_file_without_inn_column_still_works():
    parsed = importer.parse_any(xlsx(["Клиент"], ["Ресторан"]), "c.xlsx")
    assert parsed.kind == "clients" and parsed.rows == [{"name": "Ресторан"}]


async def test_import_couriers(session):
    await catalog.set_courier(session, 1, "Ali")
    await catalog.set_courier(session, 2, "Vali")
    await catalog.set_courier(session, 3, "Off")
    await catalog.deactivate_courier(session, 3)

    rows = [{"tg_id": "1", "name": "Ali"}, {"tg_id": "2", "name": "Vali Valiyev"}, {"tg_id": "3", "name": "On"}]
    rows.append({"tg_id": "4", "name": "New"})
    res = await catalog.import_couriers(session, rows)
    assert (res.created, res.updated, res.unchanged) == (2, 1, 1)
    couriers = {c.tg_id: (c.name, c.active) for c in (await session.scalars(select(Courier))).all()}
    assert couriers == {1: ("Ali", True), 2: ("Vali Valiyev", True), 3: ("On", True), 4: ("New", True)}


# ---------- bot ----------


@pytest.fixture
async def h(session_maker):
    harness = Harness(session_maker)
    yield harness
    await harness.dp.storage.close()


async def send_file(h: Harness, uid: int, filename: str, data: bytes):
    async def download(file, destination=None, **kw):
        return BytesIO(data)

    h.bot.download = download
    mark = len(h.api.calls)
    upd = {
        "update_id": 999,
        "message": {
            "message_id": 999,
            "date": int(datetime.now().timestamp()),
            "chat": {"id": uid, "type": "private"},
            "from": h._user(uid),
            "document": {"file_id": "f", "file_unique_id": "u", "file_name": filename, "file_size": len(data)},
        },
    }
    await h.dp.feed_update(h.bot, Update.model_validate(upd, context={"bot": h.bot}))
    return h.api.calls[mark:]


async def test_bot_detects_kind_and_imports(h, session):
    out = await send_file(h, ADMIN, "mijozlar.csv", "Клиент\nКафе 1\nКафе 2\n".encode())
    assert texts(out).strip() == "✅ Клиенты: новых 2, обновлено 0, без изменений 0."
    out = await send_file(h, ADMIN, "k.xlsx", importer.build_template("couriers", "uz"))
    assert texts(out).startswith("✅ Доставщики: новых 1")
    out = await send_file(h, ADMIN, "p.xlsx", importer.build_template("products", "en"))
    assert texts(out).startswith("✅ Товары: новых 1")
    out = await send_file(h, ADMIN, "a.pdf", b"x")
    assert texts(out) == t("ru", "import.not_xlsx")


async def test_bot_template_sends_three_files(h):
    out = await h.text(ADMIN, "/template")
    names = [c.document.filename for c in out if hasattr(c, "document")]
    assert names == [importer.template_filename(k, "ru") for k in importer.KINDS]


# ---------- admin panel ----------


@pytest.fixture
async def panel(monkeypatch, engine, session_maker, session):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from app.admin import setup_admin

    session.add(AdminUser(username="boss", password_hash=hash_password("secret123"), role="admin"))
    session.add(AdminUser(username="buh", password_hash=hash_password("secret123"), role="accountant"))
    await session.commit()
    monkeypatch.setattr("app.admin.auth.SessionLocal", session_maker)
    monkeypatch.setattr("app.admin.pages.SessionLocal", session_maker)
    app = FastAPI()
    setup_admin(app, engine, "test-secret")
    return TestClient(app)


def login(client, username: str) -> None:
    r = client.post("/admin/login", data={"username": username, "password": "secret123"}, follow_redirects=False)
    assert r.status_code == 302


@pytest.mark.parametrize(
    ("identity", "kind"), [("client", "clients"), ("product", "products"), ("courier", "couriers")]
)
async def test_panel_list_pages_have_import_button(panel, identity, kind):
    login(panel, "boss")
    r = panel.get(f"/admin/{identity}/list?lang=uz")
    assert r.status_code == 200
    assert "Fayldan yuklash" in r.text and 'id="modal-file-import"' in r.text
    assert f'name="kind" value="{kind}"' in r.text and f"/admin/import/template?kind={kind}" in r.text


async def test_panel_import_is_not_a_menu_item(panel):
    login(panel, "boss")
    r = panel.get("/admin/client/list?lang=en")
    assert 'action="http://testserver/admin/import"' in r.text  # the modal posts here
    assert 'href="http://testserver/admin/import"' not in r.text  # but there is no menu link


async def test_panel_import_clients(panel, session):
    login(panel, "boss")
    data = xlsx(["Client"], ["Shop 1"], ["Shop 2"], [None], ["shop 1"])
    r = panel.post("/admin/import?lang=en", data={"kind": "clients"}, files={"file": ("clients.xlsx", data)})
    assert r.json() == {
        "ok": True,
        "message": "Clients: new 2, updated 0, unchanged 0.",
        "notes": ["Row 5: «shop 1» already appears above in the file — skipped"],
    }
    assert len((await session.scalars(select(Client))).all()) == 2


async def test_panel_import_errors_and_template(panel):
    login(panel, "boss")
    files = {"file": ("p.xlsx", importer.build_template("couriers", "uz"))}
    r = panel.post("/admin/import?lang=uz", data={"kind": "products"}, files=files)
    assert r.json()["ok"] is False and "«Kuryerlar» boʻlimi" in r.json()["error"]

    r = panel.get("/admin/import/template?kind=couriers&lang=uz")
    assert r.status_code == 200 and 'filename="namuna_kuryerlar.xlsx"' in r.headers["content-disposition"]
    r = panel.get("/admin/import?kind=couriers", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].endswith("/admin/courier/list")
    assert panel.get("/admin/products-import", follow_redirects=False).headers["location"].endswith("/product/list")


async def test_panel_import_is_admin_only(panel):
    login(panel, "buh")
    r = panel.get("/admin/client/list?lang=uz")
    assert r.status_code == 200 and 'id="modal-file-import"' not in r.text
    files = {"file": ("c.csv", b"Client\nX\n")}
    assert panel.post("/admin/import", data={"kind": "clients"}, files=files).status_code in (403, 404)
