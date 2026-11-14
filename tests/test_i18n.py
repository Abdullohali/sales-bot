"""Localization: catalogs are complete, the bot and Excel files follow the user's language."""

import string
from io import BytesIO

import pytest
from aiogram.methods import SendDocument, SendMessage
from openpyxl import load_workbook

from app.bot.keyboards import BTN_LANG, BTN_NEW_SALE, BTN_REPORT, DraftCB, LangCB, PickCB
from app.i18n import CATALOGS, LANGS, normalize, resolve, t, variants
from app.i18n.sqladmin_uz import MESSAGES as SQLADMIN_UZ
from app.services import catalog
from app.services.excel import build_products_template, parse_products_xlsx
from tests.test_bot_flow import ADMIN, COURIER, Harness, texts


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


# ---------- catalogs ----------


def test_all_languages_have_the_same_keys():
    keys = set(CATALOGS["ru"])
    for lang in LANGS:
        assert set(CATALOGS[lang]) == keys, lang


@pytest.mark.parametrize("lang", LANGS)
def test_placeholders_match_russian(lang):
    for key, text in CATALOGS["ru"].items():
        assert _fields(CATALOGS[lang][key]) == _fields(text), (lang, key)


def test_reply_buttons_are_unique_across_languages():
    # a button text must not mean two different things in different languages
    keys = (BTN_NEW_SALE, BTN_REPORT, BTN_LANG)
    for a in keys:
        for b in keys:
            if a != b:
                assert not variants(a) & variants(b)


def test_sqladmin_uzbek_catalog_covers_sqladmin_strings():
    from babel.messages.pofile import read_po
    from sqladmin import i18n

    pot = read_po(open(i18n.__file__.replace("i18n.py", "translations/admin.pot"), "rb"))
    missing = {m.id for m in pot if m.id and isinstance(m.id, str)} - set(SQLADMIN_UZ)
    assert not missing


def test_normalize_and_fallback():
    assert normalize("uz") == "uz" and normalize("ru-RU") == "ru" and normalize("en_US") == "en"
    assert normalize("tr") is None and normalize(None) is None
    assert resolve("de") == "ru"  # DEFAULT_LANGUAGE
    assert t("xx", "vat") == t("ru", "vat")
    assert t("en", "sale.saved", id=5) == "✅ Invoice №5 saved."


# ---------- bot ----------


@pytest.fixture
async def h(session_maker, session):
    await catalog.add_client(session, "Ресторан А")
    await catalog.upsert_product(session, "Помидоры", "кг", "12345678901234567")
    await catalog.set_courier(session, COURIER, "Али")
    harness = Harness(session_maker)
    yield harness
    await harness.dp.storage.close()


async def test_language_detected_from_telegram(h, session):
    h.language_codes[COURIER] = "uz"
    out = await h.text(COURIER, "/help")
    assert texts(out).startswith("Sotuvni qanday yozish kerak")
    h.language_codes[COURIER] = "en"
    out = await h.text(COURIER, "/help")
    assert texts(out).startswith("How to record a sale")

    # /start remembers the detected language (invoices sent later use it)
    out = await h.text(COURIER, "/start")
    assert "Hello" in texts(out)
    assert out[0].reply_markup.keyboard[0][0].text == t("en", BTN_NEW_SALE)
    assert await catalog.get_lang(session, COURIER) == "en"
    h.language_codes[COURIER] = "uz"
    out = await h.text(COURIER, "/help")
    assert texts(out).startswith("How to record a sale")


async def test_unknown_telegram_language_uses_default(h):
    h.language_codes[COURIER] = "de"
    out = await h.text(COURIER, "/start")
    assert "Здравствуйте" in texts(out)


async def test_stranger_gets_no_access_in_own_language(h):
    h.language_codes[777] = "en"
    out = await h.text(777, "hi")
    assert t("en", "auth.ask_phone") in texts(out)


async def test_lang_command_switches_and_persists(h, session):
    out = await h.text(COURIER, t("ru", BTN_LANG))  # the menu button works too
    assert "Tilni tanlang" in texts(out) and "Выберите язык" in texts(out) and "Choose a language" in texts(out)

    out = await h.click(COURIER, LangCB(code="uz").pack())
    msg = next(c for c in out if isinstance(c, SendMessage))
    assert msg.text == t("uz", "lang.set")
    assert msg.reply_markup.keyboard[0][0].text == t("uz", BTN_NEW_SALE)
    assert await catalog.get_lang(session, COURIER) == "uz"

    # saved choice beats the Telegram app language
    h.language_codes[COURIER] = "en"
    out = await h.text(COURIER, t("uz", BTN_REPORT))
    assert "yetkazmalaringiz" in texts(out)
    out = await h.text(COURIER, "/cancel")
    assert texts(out) == t("uz", "sale.cancelled")


async def test_bad_lang_callback_is_ignored(h, session):
    await h.click(COURIER, LangCB(code="xx").pack())
    assert await catalog.get_lang(session, COURIER) is None


async def test_sale_flow_in_uzbek_and_invoice_per_recipient_language(h, session):
    await catalog.set_lang(session, COURIER, "uz")
    await catalog.set_lang(session, ADMIN, "en")

    out = await h.text(COURIER, t("uz", BTN_NEW_SALE))
    assert "Mijozni tanlang" in texts(out)
    await h.click(COURIER, PickCB(kind="c", id=1).pack())
    await h.click(COURIER, PickCB(kind="p", id=1).pack())
    out = await h.text(COURIER, "abc")
    assert texts(out) == t("uz", "qty.invalid")
    out = await h.text(COURIER, "10")
    assert "QQSsiz" in texts(out)
    out = await h.text(COURIER, "1000")
    assert "Yuk xati qoralamasi" in texts(out)

    out = await h.click(COURIER, DraftCB(action="finish").pack())
    assert t("uz", "sale.saved", id=1) in texts(out)
    docs = {c.chat_id: c for c in out if isinstance(c, SendDocument)}
    assert docs[COURIER].document.filename == "yuk_xati_1.xlsx"
    assert docs[COURIER].caption.startswith("№1 yuk xati")
    assert docs[ADMIN].document.filename == "invoice_1.xlsx"
    assert docs[ADMIN].caption.startswith("Invoice №1")

    ws = load_workbook(BytesIO(docs[ADMIN].document.data)).active
    assert ws["A1"].value.startswith("INVOICE № 1")
    assert ws["A4"].value == "Buyer: Ресторан А"  # business data is not translated


async def test_admin_commands_in_english(h):
    await h.click(ADMIN, LangCB(code="en").pack())
    out = await h.text(ADMIN, "/addclient")
    assert texts(out) == "Format: /addclient Name"
    out = await h.text(ADMIN, "/report 12-11-2026")
    assert "YYYY-MM-DD" in texts(out) and "/report" in texts(out)
    out = await h.text(ADMIN, "/addproduct Огурцы; кг; 123")
    assert "Product added: Огурцы" in texts(out) and "is not 17 digits" in texts(out)


# ---------- Excel ----------


@pytest.mark.parametrize("lang", LANGS)
def test_template_of_every_language_imports(lang):
    rows, errors = parse_products_xlsx(build_products_template(lang), lang)
    assert errors == []
    assert rows == [
        {"name": t(lang, "tpl.sample_name"), "unit": t(lang, "tpl.sample_unit"), "ikpu": "0" * 17, "unit_code": None}
    ]


def test_import_errors_are_translated():
    rows, errors = parse_products_xlsx(b"not an xlsx", "en")
    assert rows == [] and errors == [t("en", "xl.read_error")]


# ---------- admin panel ----------


@pytest.fixture
def panel(monkeypatch, session_maker):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from app.admin import setup_admin
    from app.db.session import engine

    monkeypatch.setattr("app.admin.auth.SessionLocal", session_maker)  # login looks users up in the test DB
    app = FastAPI()
    setup_admin(app, engine, "test-secret")
    return TestClient(app)


@pytest.mark.parametrize(
    ("lang", "title", "button"),
    [("uz", "Sotuv hisobi", "Kirish"), ("ru", "Учёт продаж", "Вход"), ("en", "Sales accounting", "Login")],
)
def test_panel_login_page_language(panel, lang, title, button):
    r = panel.get(f"/admin/login?lang={lang}")
    assert r.status_code == 200
    assert title in r.text and f">{button}</button>" in r.text
    assert r.cookies.get("language") == lang
    # the choice is remembered by the cookie
    assert title in panel.get("/admin/login").text


def test_panel_language_from_browser_header(panel):
    r = panel.get("/admin/login", headers={"Accept-Language": "uz-UZ,uz;q=0.9"})
    assert "Sotuv hisobi" in r.text


def test_panel_failed_login_message_is_translated(panel):
    r = panel.post("/admin/login?lang=en", data={"username": "nobody", "password": "x"})
    assert r.status_code == 400 and "Invalid login or password" in r.text
