"""Daily report (TZ §5.6)."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Sale
from app.i18n import t
from app.services.clock import local_tz
from app.services.formatting import fmt_date, fmt_money
from app.services.sales import list_sales, sale_totals
from app.services.vat import Amounts


@dataclass
class DailyReport:
    day: date
    sale_count: int = 0
    by_client: list[tuple[str, Amounts]] = field(default_factory=list)
    totals: Amounts = field(default_factory=Amounts)
    vat_rates: set[Decimal] = field(default_factory=set)
    sales: list[Sale] = field(default_factory=list)


def build_report(day: date, sales: list[Sale]) -> DailyReport:
    per_client: dict[str, Amounts] = defaultdict(Amounts)
    rep = DailyReport(day=day, sale_count=len(sales), sales=sales)
    for s in sales:
        t = sale_totals(s)
        per_client[s.client.name] = per_client[s.client.name] + t
        rep.totals = rep.totals + t
        rep.vat_rates.update(i.vat_rate for i in s.items)
    rep.by_client = sorted(per_client.items(), key=lambda kv: kv[0].lower())
    return rep


async def daily_report(session: AsyncSession, day: date, courier_id: int | None = None) -> DailyReport:
    return build_report(day, await list_sales(session, day, courier_id=courier_id))


def vat_label(rates: set[Decimal], lang: str | None = None) -> str:
    if len(rates) == 1:
        (r,) = rates
        return t(lang, "vat.rate", rate=format(r.normalize(), "f"))
    return t(lang, "vat")


def render_report(rep: DailyReport, lang: str | None = None) -> str:
    lines = [t(lang, "report.title", date=fmt_date(rep.day), n=rep.sale_count), ""]
    if not rep.sale_count:
        lines.append(t(lang, "report.none"))
        return "\n".join(lines)
    lines += [f"• {name}: {fmt_money(a.ex)}" for name, a in rep.by_client]
    lines += [
        "",
        t(lang, "report.total_ex", v=fmt_money(rep.totals.ex)),
        f"{vat_label(rep.vat_rates, lang)}: {fmt_money(rep.totals.vat)}",
        t(lang, "report.total", v=fmt_money(rep.totals.total)),
    ]
    return "\n".join(lines)


def render_courier_report(rep: DailyReport, lang: str | None = None) -> str:
    """Courier sees only own deliveries for today, no company-wide numbers."""
    lines = [t(lang, "courier_report.title", date=fmt_date(rep.day), n=rep.sale_count), ""]
    if not rep.sale_count:
        lines.append(t(lang, "courier_report.none"))
        return "\n".join(lines)
    for s in rep.sales:
        lines.append(f"№{s.id} · {s.client.name}: {fmt_money(sale_totals(s).total)}")
    lines += ["", t(lang, "report.total", v=fmt_money(rep.totals.total))]
    return "\n".join(lines)


def render_sales_list(sales: list[Sale], day: date, lang: str | None = None) -> str:
    if not sales:
        return t(lang, "sales_list.none", date=fmt_date(day))
    lines = [t(lang, "sales_list.title", date=fmt_date(day)), ""]
    for s in sales:
        tot = sale_totals(s)
        time = s.created_at.astimezone(local_tz()).strftime("%H:%M") if s.created_at else ""
        lines.append(f"№{s.id} {time} · {s.client.name} · {s.courier.name} · {fmt_money(tot.total)}")
    return "\n".join(lines)
