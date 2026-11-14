"""Business time. "Today" is always the local date in Asia/Tashkent, even if the server runs in UTC."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def local_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().TIMEZONE)


def now_utc() -> datetime:
    return datetime.now(UTC)


def today_local() -> date:
    return datetime.now(local_tz()).date()


def parse_date(text: str | None) -> date | None:
    """Parse YYYY-MM-DD; None/empty -> today; invalid -> None."""
    if not text or not text.strip():
        return today_local()
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None
