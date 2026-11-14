"""User number input (TZ §5.1): accepts 25, 12,5, 12.5, 8 500, 8500. Rejects 0, negatives, letters."""

import re
from decimal import Decimal, InvalidOperation

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
MAX_VALUE = Decimal("1000000000000")  # sanity cap: fits Numeric(18, x)


def parse_positive(text: str | None) -> Decimal | None:
    if not text:
        return None
    t = re.sub(r"\s", "", text).replace(",", ".")  # \s also covers NBSP / thin spaces
    if not _NUM_RE.fullmatch(t):
        return None
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None
    if v <= 0 or v >= MAX_VALUE:
        return None
    return v
