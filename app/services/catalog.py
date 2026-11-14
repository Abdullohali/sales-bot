"""Directory CRUD: clients, products, couriers. Deletion is always soft (active=False)."""

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, Client, Courier, Product, Staff
from app.i18n import t

IKPU_RE = re.compile(r"^\d{17}$")


def _norm_name(name: str) -> str:
    return " ".join(name.split())


def _clean(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


# ---------- generic list with search + pagination ----------


async def list_page(
    session: AsyncSession,
    model,
    *,
    search: str | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> tuple[list, int]:
    """Active rows ordered by name. Returns (rows, total_count)."""
    cond = [model.active.is_(True)]
    if search:
        cond.append(model.name.ilike(f"%{search.strip()}%"))
    total = await session.scalar(select(func.count()).select_from(model).where(*cond))
    stmt = select(model).where(*cond).order_by(model.name).offset(offset)
    if limit:
        stmt = stmt.limit(limit)
    rows = (await session.scalars(stmt)).all()
    return list(rows), int(total or 0)


async def _by_name(session: AsyncSession, model, name: str):
    return await session.scalar(select(model).where(func.lower(model.name) == name.lower()))


# ---------- clients ----------


async def add_client(session: AsyncSession, name: str) -> tuple[Client, bool]:
    """Create client, or re-activate a soft-deleted one. Returns (client, created)."""
    name = _norm_name(name)
    if not name:
        raise ValueError("Пустое название клиента")
    client = await _by_name(session, Client, name)
    if client:
        created = not client.active
        client.active = True
    else:
        client = Client(name=name, active=True)
        session.add(client)
        created = True
    await session.commit()
    return client, created


async def deactivate_client(session: AsyncSession, name: str) -> bool:
    client = await _by_name(session, Client, _norm_name(name))
    if not client or not client.active:
        return False
    client.active = False
    await session.commit()
    return True


# ---------- products ----------


@dataclass
class UpsertResult:
    product: Product
    created: bool
    warnings: list[str] = field(default_factory=list)


async def upsert_product(
    session: AsyncSession,
    name: str,
    unit: str | None = None,
    ikpu=None,
    unit_code=None,
    *,
    commit: bool = True,
    lang: str | None = None,
) -> UpsertResult:
    """Create or update product by name (TZ §3.1).

    Empty unit/IKPU/code on update do NOT erase stored values.
    Invalid IKPU (not 17 digits) is saved anyway, with a warning.
    """
    name = _norm_name(name or "")
    if not name:
        raise ValueError("Пустое название товара")
    unit, ikpu, unit_code = _clean(unit), _clean(ikpu), _clean(unit_code)

    warnings: list[str] = []
    if ikpu and not IKPU_RE.match(ikpu):
        warnings.append(t(lang, "warn.ikpu", name=name, ikpu=ikpu))

    product = await _by_name(session, Product, name)
    created = product is None or not product.active
    if product is None:
        product = Product(name=name, unit=unit or "кг", ikpu=ikpu, unit_code=unit_code, active=True)
        session.add(product)
    else:
        product.active = True
        if unit:
            product.unit = unit
        if ikpu:
            product.ikpu = ikpu
        if unit_code:
            product.unit_code = unit_code
    if commit:
        await session.commit()
    else:
        await session.flush()
    return UpsertResult(product, created, warnings)


async def deactivate_product(session: AsyncSession, name: str) -> bool:
    product = await _by_name(session, Product, _norm_name(name))
    if not product or not product.active:
        return False
    product.active = False
    await session.commit()
    return True


@dataclass
class ImportResult:
    created: int = 0  # new, or hidden/disabled and now active again
    updated: int = 0  # existed, data changed
    unchanged: int = 0  # existed with the same data
    warnings: list[str] = field(default_factory=list)


async def import_products(session: AsyncSession, rows: list[dict], lang: str | None = None) -> ImportResult:
    """Bulk upsert from parsed file rows (all-or-nothing transaction)."""
    res = ImportResult()
    for row in rows:
        r = await upsert_product(
            session, row["name"], row.get("unit"), row.get("ikpu"), row.get("unit_code"), commit=False, lang=lang
        )
        if r.created:
            res.created += 1
        else:
            res.updated += 1
        res.warnings.extend(r.warnings)
    await session.commit()
    return res


async def import_clients(session: AsyncSession, rows: list[dict]) -> ImportResult:
    """Bulk add clients by name (all-or-nothing). Existing ones are not duplicated,
    hidden ones become active again."""
    res = ImportResult()
    for row in rows:
        name = _norm_name(row["name"])
        client = await _by_name(session, Client, name)
        if client is None:
            session.add(Client(name=name, active=True))
            res.created += 1
        elif not client.active:
            client.active = True
            res.created += 1
        else:
            res.unchanged += 1
        await session.flush()
    await session.commit()
    return res


async def import_couriers(session: AsyncSession, rows: list[dict]) -> ImportResult:
    """Bulk add couriers by Telegram ID (all-or-nothing). Existing: name updated, disabled: enabled again."""
    res = ImportResult()
    for row in rows:
        tg_id, name = int(row["tg_id"]), _norm_name(row["name"])
        courier = await session.get(Courier, tg_id)
        if courier is None:
            session.add(Courier(tg_id=tg_id, name=name, active=True))
            res.created += 1
        elif not courier.active:
            courier.name, courier.active = name, True
            res.created += 1
        elif courier.name != name:
            courier.name = name
            res.updated += 1
        else:
            res.unchanged += 1
        await session.flush()
    await session.commit()
    return res


async def import_rows(session: AsyncSession, kind: str, rows: list[dict], lang: str | None = None) -> ImportResult:
    if kind == "products":
        return await import_products(session, rows, lang)
    if kind == "clients":
        return await import_clients(session, rows)
    if kind == "couriers":
        return await import_couriers(session, rows)
    raise ValueError(kind)


# ---------- couriers ----------


async def set_courier(session: AsyncSession, tg_id: int, name: str) -> tuple[Courier, bool]:
    name = _norm_name(name)
    if not name:
        raise ValueError("Пустое имя доставщика")
    courier = await session.get(Courier, tg_id)
    created = courier is None or not courier.active
    if courier is None:
        courier = Courier(tg_id=tg_id, name=name, active=True)
        session.add(courier)
    else:
        courier.name = name
        courier.active = True
    await session.commit()
    return courier, created


async def deactivate_courier(session: AsyncSession, tg_id: int) -> bool:
    courier = await session.get(Courier, tg_id)
    if not courier or not courier.active:
        return False
    courier.active = False
    await session.commit()
    return True


async def ensure_courier(session: AsyncSession, tg_id: int, name: str) -> Courier:
    """Admins may record sales too: make sure they exist in `couriers` (FK of sales)."""
    courier = await session.get(Courier, tg_id)
    if courier is None:
        courier = Courier(tg_id=tg_id, name=_norm_name(name) or str(tg_id), active=False)
        session.add(courier)
        await session.commit()
    return courier


async def get_role(session: AsyncSession, tg_id: int, admin_ids: list[int]) -> str | None:
    """'admin' | 'courier' | None (stranger).
    Order: ADMIN_IDS from .env -> staff linked by phone (authoritative once linked) -> couriers by Telegram ID."""
    if tg_id in admin_ids:
        return "admin"
    staff = await session.scalar(select(Staff).where(Staff.tg_id == tg_id))
    if staff is not None:
        return staff.role if staff.active and staff.role in STAFF_ROLES else None
    courier = await session.get(Courier, tg_id)
    if courier and courier.active:
        return "courier"
    return None


# ---------- staff (login by phone number) ----------

STAFF_ROLES = ("admin", "courier")


def normalize_phone(raw: str | None) -> str | None:
    """'+998 (90) 123-45-67' / '90 123 45 67' -> '998901234567'; None if it does not look like a phone."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:  # local Uzbek number without the country code
        digits = "998" + digits
    return digits if 10 <= len(digits) <= 15 else None


async def link_staff_by_phone(session: AsyncSession, tg_id: int, phone: str | None) -> Staff | None:
    """Attach the Telegram account to the active staff row with this phone.
    Couriers also get a `couriers` row (FK of sales) under the staff name."""
    norm = normalize_phone(phone)
    if norm is None:
        return None
    staff = await session.scalar(select(Staff).where(Staff.phone == norm, Staff.active.is_(True)))
    if staff is None or staff.role not in STAFF_ROLES:
        return None
    if staff.tg_id is not None and staff.tg_id != tg_id:
        return None  # the number is already bound to another Telegram account
    # Another staff row may hold this Telegram ID (e.g. phone changed): release it.
    other = await session.scalar(select(Staff).where(Staff.tg_id == tg_id, Staff.id != staff.id))
    if other is not None:
        other.tg_id = None
        await session.flush()
    staff.tg_id = tg_id
    courier = await session.get(Courier, tg_id)
    if courier is None:
        courier = Courier(tg_id=tg_id, name=staff.name, active=staff.role == "courier")
        session.add(courier)
    else:
        courier.name = staff.name
        courier.active = staff.role == "courier"
    await session.commit()
    return staff


async def admin_recipient_ids(session: AsyncSession, admin_ids: list[int]) -> list[int]:
    """Telegram IDs that receive copies of invoices: ADMIN_IDS + linked active staff admins."""
    rows = await session.scalars(
        select(Staff.tg_id).where(Staff.role == "admin", Staff.active.is_(True), Staff.tg_id.is_not(None))
    )
    return list(dict.fromkeys([*admin_ids, *rows]))


# ---------- bot user language ----------


async def get_lang(session: AsyncSession, tg_id: int) -> str | None:
    """Saved language of a Telegram user, None if never saved."""
    return await session.scalar(select(BotUser.lang).where(BotUser.tg_id == tg_id))


async def get_langs(session: AsyncSession, tg_ids) -> dict[int, str]:
    ids = list(set(tg_ids))
    if not ids:
        return {}
    rows = await session.execute(select(BotUser.tg_id, BotUser.lang).where(BotUser.tg_id.in_(ids)))
    return {tg_id: lang for tg_id, lang in rows.all()}


async def set_lang(session: AsyncSession, tg_id: int, lang: str) -> None:
    user = await session.get(BotUser, tg_id)
    if user is None:
        session.add(BotUser(tg_id=tg_id, lang=lang))
    else:
        user.lang = lang
    await session.commit()
