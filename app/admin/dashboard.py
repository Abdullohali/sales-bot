"""Admin panel home page: today's numbers, last 7 days, latest invoices."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Client, Courier, Product, Sale, SaleItem
from app.services.clock import today_local
from app.services.sales import list_sales, sale_totals

DAYS = 7
RECENT = 6


@dataclass
class DayBar:
    day: date
    total: Decimal
    count: int
    height: int  # 0..100, % of the best day
    is_today: bool


async def _active_count(session: AsyncSession, model) -> int:
    return int(await session.scalar(select(func.count()).select_from(model).where(model.active.is_(True))) or 0)


async def dashboard_data(session: AsyncSession) -> dict:
    today = today_local()
    start = today - timedelta(days=DAYS - 1)
    sales = await list_sales(session, start, today)

    by_day: dict[date, tuple[Decimal, int]] = {start + timedelta(days=i): (Decimal(0), 0) for i in range(DAYS)}
    for s in sales:
        total, count = by_day[s.sale_date]
        by_day[s.sale_date] = (total + sale_totals(s).total, count + 1)
    best = max((v[0] for v in by_day.values()), default=Decimal(0))
    bars = [
        DayBar(d, total, count, int(total * 100 / best) if best else 0, d == today)
        for d, (total, count) in by_day.items()
    ]

    recent = (
        await session.scalars(
            select(Sale)
            .where(Sale.is_deleted.is_(False))
            .options(selectinload(Sale.items).selectinload(SaleItem.product), selectinload(Sale.client))
            .order_by(Sale.id.desc())
            .limit(RECENT)
        )
    ).all()

    today_total, today_count = by_day[today]
    week_total = sum((v[0] for v in by_day.values()), Decimal(0))
    return {
        "today": today,
        "today_total": today_total,
        "today_count": today_count,
        "week_total": week_total,
        "clients": await _active_count(session, Client),
        "products": await _active_count(session, Product),
        "couriers": await _active_count(session, Courier),
        "bars": bars,
        "recent": [(s, sale_totals(s).total) for s in recent],
    }
