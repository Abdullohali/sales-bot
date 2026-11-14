"""Bulk import of directories from a file: products, clients, couriers.

Formats: .xlsx (Excel 2007+) and .csv (UTF-8 or Windows-1251, separator "," ";" or tab).
The first row is the header. Columns are matched by name in any language (uz/ru/en),
so the order of columns does not matter. If no header is recognised, columns are
taken in template order.

The rules for users are in docs/import-format.md — keep it in sync with SCHEMAS.
"""

import csv
import io
from dataclasses import dataclass
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.i18n import CATALOGS, t

KINDS = ("products", "clients", "couriers")
MAX_ROWS = 5000
MAX_BYTES = 10 * 1024 * 1024
TEXT_FMT = "@"


@dataclass(frozen=True)
class Column:
    field: str
    label: str  # i18n key of the template header
    required: bool = False
    text: bool = False  # keep as text in the template (long digit codes)
    width: int = 20


SCHEMAS: dict[str, list[Column]] = {
    "products": [
        Column("name", "tpl.name", required=True, width=32),
        Column("unit", "tpl.unit", width=16),
        Column("ikpu", "tpl.ikpu", text=True, width=22),
        Column("unit_code", "tpl.unit_code", text=True, width=14),
    ],
    "clients": [Column("name", "tpl.client_name", required=True, width=40)],
    "couriers": [
        Column("tg_id", "tpl.tg_id", required=True, text=True, width=18),
        Column("name", "tpl.courier_name", required=True, width=32),
    ],
}

# Header spellings people actually type (lower case), in addition to the template
# headers of every language.
ALIASES: dict[str, dict[str, str]] = {
    "products": {
        "название": "name", "наименование": "name", "товар": "name", "nomi": "name", "nom": "name",
        "mahsulot": "name", "product": "name", "product name": "name",
        "ед.изм.": "unit", "ед.": "unit", "единица": "unit", "birlik": "unit", "oʻlchov": "unit",
        "o'lchov birligi": "unit", "units": "unit",
        "икпу": "ikpu", "mxik": "ikpu", "ikpu": "ikpu",
        "код ед.изм.": "unit_code", "код ед.": "unit_code", "код единицы": "unit_code", "kod": "unit_code",
        "code": "unit_code",
    },
    "clients": {
        "клиент": "name", "название клиента": "name", "клиенты": "name", "покупатель": "name",
        "mijoz": "name", "mijoz nomi": "name", "mijozlar": "name", "xaridor": "name",
        "client": "name", "client name": "name", "clients": "name", "customer": "name",
    },
    "couriers": {
        "telegram id": "tg_id", "telegram": "tg_id", "tg id": "tg_id", "tg_id": "tg_id", "id": "tg_id",
        "имя": "name", "доставщик": "name", "имя доставщика": "name", "фио": "name",
        "ism": "name", "kuryer": "name", "kuryer ismi": "name", "f.i.sh.": "name",
        "name": "name", "courier": "name", "courier name": "name",
    },
}  # fmt: skip


def _header_map(kind: str) -> dict[str, str]:
    m = dict(ALIASES[kind])
    for lang in CATALOGS:
        for col in SCHEMAS[kind]:
            m[CATALOGS[lang][col.label].strip().lower()] = col.field
    return m


HEADERS = {kind: _header_map(kind) for kind in KINDS}


# ---------- templates ----------


def _examples(kind: str, lang: str | None) -> list[list[str]]:
    if kind == "products":
        return [[t(lang, "tpl.sample_name"), t(lang, "tpl.sample_unit"), "00000000000000000", ""]]
    if kind == "clients":
        return [[t(lang, "tpl.sample_client")]]
    return [["123456789", t(lang, "tpl.sample_courier")]]


def template_filename(kind: str, lang: str | None = None) -> str:
    return t(lang, f"xl.tpl_file.{kind}")


def build_template(kind: str, lang: str | None = None) -> bytes:
    cols = SCHEMAS[kind]
    wb = Workbook()
    ws = wb.active
    ws.title = t(lang, f"p.{kind}")[:31]
    ws.append([t(lang, c.label) for c in cols])
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in _examples(kind, lang):
        ws.append(row)
    for i, col in enumerate(cols, start=1):
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = col.width
        if col.text:  # so Excel doesn't turn 17 digits into 1.23E+16
            for r in range(2, 1001):
                ws[f"{letter}{r}"].number_format = TEXT_FMT
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------- reading ----------


class ReadError(ValueError):
    """`key` is an i18n message key."""

    def __init__(self, key: str, **kwargs) -> None:
        super().__init__(key)
        self.key = key
        self.kwargs = kwargs


def _read_xlsx(data: bytes) -> list[tuple]:
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        raise ReadError("xl.read_error") from e
    try:
        return [tuple(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    finally:
        wb.close()


def _read_csv(data: bytes) -> list[tuple]:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ReadError("xl.read_error")
    if "\x00" in text:
        raise ReadError("xl.read_error")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    return [tuple(r) for r in csv.reader(io.StringIO(text), delimiter=delimiter)]


def read_table(data: bytes, filename: str = "") -> list[tuple]:
    """Rows of the first sheet (xlsx) or of the csv file. Format by extension, then by content."""
    name = (filename or "").lower()
    if name.endswith(".xls") or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # old binary Excel
        raise ReadError("xl.xls_old")
    if name.endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        return _read_xlsx(data)
    if name.endswith((".csv", ".txt")) or not name:
        return _read_csv(data)
    raise ReadError("xl.bad_format")


def _cell(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = " ".join(str(v).split())
    return s or None


def _map_header(kind: str, header: tuple) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for idx, title in enumerate(header):
        field = HEADERS[kind].get(str(title or "").strip().lower())
        if field and field not in mapping.values():
            mapping[idx] = field
    return mapping


def _recognised(kind: str, mapping: dict[int, str]) -> bool:
    return all(c.field in mapping.values() for c in SCHEMAS[kind] if c.required)


def detect_kind(header: tuple) -> str | None:
    """Which directory a file is for, judging by its header. Couriers have a Telegram ID column,
    clients a client column; product headers ("Name", "Unit", ...) are checked last."""
    for kind in ("couriers", "clients", "products"):
        if _recognised(kind, _map_header(kind, header)):
            return kind
    return None


# ---------- parsing ----------


@dataclass
class Parsed:
    kind: str
    rows: list[dict]
    errors: list[str]  # skipped rows and warnings, already translated


def parse(kind: str, data: bytes, filename: str = "", lang: str | None = None) -> Parsed:
    """Read and validate a file for `kind`. Never raises: problems come back in `errors`."""
    try:
        table = read_table(data, filename)
    except ReadError as e:
        return Parsed(kind, [], [t(lang, e.key, **e.kwargs)])
    if not table or not any(_cell(v) for v in table[0]):
        return Parsed(kind, [], [t(lang, "xl.empty")])
    if len(table) - 1 > MAX_ROWS:
        return Parsed(kind, [], [t(lang, "xl.too_many_rows", n=len(table) - 1, max=MAX_ROWS)])

    header = table[0]
    mapping = _map_header(kind, header)
    if not _recognised(kind, mapping):
        other = detect_kind(header)
        if other and other != kind:
            return Parsed(kind, [], [t(lang, "xl.wrong_kind", kind=t(lang, f"p.{other}"))])
        mapping = {i: c.field for i, c in enumerate(SCHEMAS[kind])}  # no header: template column order

    cols = {c.field: c for c in SCHEMAS[kind]}
    rows: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()
    for line_no, raw in enumerate(table[1:], start=2):
        rec = {field: _cell(raw[idx]) if idx < len(raw) else None for idx, field in mapping.items()}
        if not any(rec.values()):
            continue
        missing = [f for f, c in cols.items() if c.required and not rec.get(f)]
        if missing:
            errors.append(t(lang, "xl.row_missing", n=line_no, col=t(lang, cols[missing[0]].label)))
            continue

        if kind == "couriers":
            tg_id = rec["tg_id"].replace(" ", "")
            if not tg_id.isdigit() or len(tg_id) > 15:
                errors.append(t(lang, "xl.row_bad_tg_id", n=line_no, v=rec["tg_id"]))
                continue
            rec["tg_id"] = tg_id
            key = tg_id
        else:
            key = rec["name"].lower()
        if key in seen:
            errors.append(t(lang, "xl.row_duplicate", n=line_no, v=rec.get("name") or key))
            continue
        seen.add(key)

        if kind == "products":
            ikpu_idx = next((i for i, f in mapping.items() if f == "ikpu"), None)
            raw_ikpu = raw[ikpu_idx] if ikpu_idx is not None and ikpu_idx < len(raw) else None
            if isinstance(raw_ikpu, int | float) and not isinstance(raw_ikpu, bool):
                errors.append(t(lang, "xl.row_ikpu_number", n=line_no))
        rows.append(rec)
    return Parsed(kind, rows, errors)


def parse_any(data: bytes, filename: str = "", lang: str | None = None) -> Parsed:
    """Like parse(), with the kind detected from the header (bot: a file sent without context).
    Unrecognised header -> products (the oldest and most common case)."""
    try:
        table = read_table(data, filename)
    except ReadError as e:
        return Parsed("products", [], [t(lang, e.key, **e.kwargs)])
    kind = detect_kind(table[0]) if table else None
    return parse(kind or "products", data, filename, lang)
