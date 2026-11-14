"""VAT (НДС) math. Money is ALWAYS Decimal, never float.

Rounding rule (to be confirmed with the accountant, see README "Открытые вопросы"):
rounding is done PER LINE to 0.01, invoice/report totals are sums of rounded lines.
Within a line:
    ex    = round(qty * price_ex)
    total = round(qty * price_ex * (1 + rate/100))      price entered without VAT
    total = round(qty * entered_price)                  price entered WITH VAT
    vat   = total - ex
so that ex + vat == total holds exactly in every row of the invoice, and when the
price was entered with VAT the line total equals qty * entered price (TZ §5.3) even in
half-kopeck edge cases (price_ex is stored with 6 decimals only).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

WITH_VAT = "with_vat"
NO_VAT = "no_vat"
MODES = (WITH_VAT, NO_VAT)

D2 = Decimal("0.01")
PRICE_Q = Decimal("0.000001")  # price_ex_vat precision stored in DB (Numeric(18, 6))
QTY_Q = Decimal("0.001")  # qty precision stored in DB (Numeric(18, 3))
ZERO = Decimal("0")


def q2(x: Decimal) -> Decimal:
    return x.quantize(D2, rounding=ROUND_HALF_UP)


def price_ex_from_input(entered: Decimal, mode: str, rate: Decimal) -> Decimal:
    """Convert the price typed by the courier to the price without VAT (6 decimals)."""
    if mode not in MODES:
        raise ValueError(f"unknown price mode: {mode}")
    if mode == WITH_VAT:
        return (entered / (1 + rate / 100)).quantize(PRICE_Q, rounding=ROUND_HALF_UP)
    return entered.quantize(PRICE_Q, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Amounts:
    ex: Decimal = ZERO
    vat: Decimal = ZERO
    total: Decimal = ZERO

    def __add__(self, other: "Amounts") -> "Amounts":
        return Amounts(self.ex + other.ex, self.vat + other.vat, self.total + other.total)


def line_amounts(qty: Decimal, price_ex: Decimal, rate: Decimal, entered_with_vat: Decimal | None = None) -> Amounts:
    raw_ex = qty * price_ex
    ex = q2(raw_ex)
    total = q2(qty * entered_with_vat) if entered_with_vat is not None else q2(raw_ex * (1 + rate / 100))
    return Amounts(ex=ex, vat=total - ex, total=total)


def sum_amounts(lines) -> Amounts:
    acc = Amounts()
    for a in lines:
        acc = acc + a
    return acc
