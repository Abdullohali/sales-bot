"""Number/date output formats from TZ §5.2."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.services.vat import D2


def _group(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def fmt_money(x: Decimal) -> str:
    """Money: integer with space as thousands separator: 276 750."""
    return _group(int(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def fmt_price(x: Decimal) -> str:
    """Unit price: integer, or two decimals after a comma if there are kopecks: 8 928,57."""
    v = x.quantize(D2, rounding=ROUND_HALF_UP)
    whole = int(v)
    frac = abs(v - whole)
    if frac == 0:
        return _group(whole)
    return f"{_group(whole)},{int(frac * 100):02d}"


def fmt_qty(x: Decimal) -> str:
    """Quantity without trailing zeros: 25.5, 100."""
    s = format(x.normalize(), "f")
    return s


def fmt_date(d: date) -> str:
    return d.isoformat()
