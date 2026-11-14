from decimal import Decimal as D

import pytest

from app.bot.parsers import parse_positive
from app.services.formatting import fmt_money, fmt_price, fmt_qty
from app.services.vat import NO_VAT, WITH_VAT, line_amounts, price_ex_from_input, q2

RATE = D("12")


# ---------- VAT ----------


def test_acceptance_11200_with_vat_is_10000_ex_vat():
    assert price_ex_from_input(D("11200"), WITH_VAT, RATE) == D("10000")


def test_no_vat_price_kept_as_entered():
    assert price_ex_from_input(D("8500"), NO_VAT, RATE) == D("8500")


def test_line_amounts_simple():
    a = line_amounts(D("25"), D("10000"), RATE)
    assert (a.ex, a.vat, a.total) == (D("250000.00"), D("30000.00"), D("280000.00"))


def test_with_vat_line_total_equals_qty_times_entered_price():
    price_ex = price_ex_from_input(D("10000"), WITH_VAT, RATE)
    assert price_ex == D("8928.571429")
    a = line_amounts(D("25"), price_ex, RATE, D("10000"))
    assert a.total == D("250000.00")
    assert a.ex + a.vat == a.total


@pytest.mark.parametrize("qty", ["1", "2.5", "12.345", "37", "99.9", "250", "1000"])
@pytest.mark.parametrize("entered", ["1", "999", "8500", "10000", "12345.67", "33333", "77777.77"])
def test_with_vat_invariant_over_many_values(qty, entered):
    qty, entered = D(qty), D(entered)
    a = line_amounts(qty, price_ex_from_input(entered, WITH_VAT, RATE), RATE, entered)
    assert a.ex + a.vat == a.total
    assert a.total == q2(qty * entered)


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        price_ex_from_input(D("1"), "bogus", RATE)


# ---------- parsers (TZ §5.1) ----------


@pytest.mark.parametrize(
    "text,expected",
    [("25", "25"), ("12,5", "12.5"), ("12.5", "12.5"), ("8 500", "8500"), ("8500", "8500"),
     ("8 500", "8500"), (" 1 000 000 ", "1000000")],
)  # fmt: skip
def test_parse_accepts(text, expected):
    assert parse_positive(text) == D(expected)


@pytest.mark.parametrize("text", ["0", "0,0", "-5", "abc", "12a", "", None, "1e5", "Infinity", "NaN", "1.2.3", "1,5,6"])
def test_parse_rejects(text):
    assert parse_positive(text) is None


# ---------- formatting (TZ §5.2) ----------


def test_fmt_money():
    assert fmt_money(D("276750")) == "276 750"
    assert fmt_money(D("444359.5")) == "444 360"
    assert fmt_money(D("0")) == "0"


def test_fmt_price():
    assert fmt_price(D("8928.571429")) == "8 928,57"
    assert fmt_price(D("10000")) == "10 000"
    assert fmt_price(D("5.05")) == "5,05"


def test_fmt_qty():
    assert fmt_qty(D("25.500")) == "25.5"
    assert fmt_qty(D("100.000")) == "100"
    assert fmt_qty(D("0.125")) == "0.125"
