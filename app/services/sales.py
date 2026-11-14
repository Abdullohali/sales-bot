"""Sales (накладные): draft items, saving, listing, soft delete."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Product, Sale, SaleItem
from app.services.clock import now_utc, today_local
from app.services.vat import QTY_Q, WITH_VAT, Amounts, line_amounts, price_ex_from_input, sum_amounts


class SaleError(ValueError):
    """`key` is an i18n message key (app/i18n), translated by the caller."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


# ---------- draft (lives in FSM storage, so it must be JSON-serialisable) ----------


def build_item(product: Product, qty: Decimal, entered_price: Decimal, mode: str, rate: Decimal) -> dict:
    qty = qty.quantize(QTY_Q)
    if qty <= 0:
        raise SaleError("sale.qty_positive")
    price_ex = price_ex_from_input(entered_price, mode, rate)
    if price_ex <= 0:
        raise SaleError("sale.price_positive")
    return {
        "product_id": product.id,
        "name": product.name,
        "unit": product.unit,
        "qty": str(qty),
        "entered_price": str(entered_price),
        "mode": mode,
        "price_ex": str(price_ex),
        "vat_rate": str(rate),
    }


def draft_item_amounts(item: dict) -> Amounts:
    entered = Decimal(item["entered_price"]) if item["mode"] == WITH_VAT else None
    return line_amounts(Decimal(item["qty"]), Decimal(item["price_ex"]), Decimal(item["vat_rate"]), entered)


def draft_totals(items: list[dict]) -> Amounts:
    return sum_amounts(draft_item_amounts(i) for i in items)


# ---------- persisted sales ----------


def item_amounts(item: SaleItem) -> Amounts:
    entered = item.entered_price if item.entered_mode == WITH_VAT else None
    return line_amounts(item.qty, item.price_ex_vat, item.vat_rate, entered)


def sale_totals(sale: Sale) -> Amounts:
    return sum_amounts(item_amounts(i) for i in sale.items)


def _with_relations(stmt):
    return stmt.options(
        selectinload(Sale.items).selectinload(SaleItem.product),
        selectinload(Sale.client),
        selectinload(Sale.courier),
    )


async def get_sale(session: AsyncSession, sale_id: int) -> Sale | None:
    return await session.scalar(_with_relations(select(Sale).where(Sale.id == sale_id)))


async def create_sale(
    session: AsyncSession,
    *,
    client_id: int,
    courier_id: int,
    items: list[dict],
    sale_date: date | None = None,
) -> Sale:
    if not items:
        raise SaleError("sale.no_items")
    sale = Sale(
        sale_date=sale_date or today_local(),
        created_at=now_utc(),
        client_id=client_id,
        courier_id=courier_id,
    )
    for it in items:
        sale.items.append(
            SaleItem(
                product_id=it["product_id"],
                qty=Decimal(it["qty"]),
                price_ex_vat=Decimal(it["price_ex"]),
                entered_price=Decimal(it["entered_price"]),
                entered_mode=it["mode"],
                vat_rate=Decimal(it["vat_rate"]),
            )
        )
    session.add(sale)
    await session.commit()
    loaded = await get_sale(session, sale.id)
    assert loaded is not None
    return loaded


async def list_sales(
    session: AsyncSession,
    date_from: date,
    date_to: date | None = None,
    *,
    courier_id: int | None = None,
    include_deleted: bool = False,
) -> list[Sale]:
    date_to = date_to or date_from
    stmt = select(Sale).where(Sale.sale_date >= date_from, Sale.sale_date <= date_to)
    if courier_id is not None:
        stmt = stmt.where(Sale.courier_id == courier_id)
    if not include_deleted:
        stmt = stmt.where(Sale.is_deleted.is_(False))
    stmt = _with_relations(stmt.order_by(Sale.id))
    return list((await session.scalars(stmt)).all())


async def soft_delete_sale(session: AsyncSession, sale_id: int, by: str) -> str:
    """Hide invoice from reports, keep it in DB with audit info. Returns 'ok' | 'not_found' | 'already'."""
    sale = await session.get(Sale, sale_id)
    if sale is None:
        return "not_found"
    if sale.is_deleted:
        return "already"
    sale.is_deleted = True
    sale.deleted_by = by
    sale.deleted_at = now_utc()
    await session.commit()
    return "ok"
