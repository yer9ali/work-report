"""Report periods in local time, and timestamps from session files."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo


def period_bounds(start: date, end: date, tz: tzinfo) -> tuple[datetime, datetime]:
    """`[start 00:00, end+1 00:00)` in `tz` — whole local days, end inclusive."""
    return (
        datetime.combine(start, time.min, tz),
        datetime.combine(end + timedelta(days=1), time.min, tz),
    )


def parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def week_bounds(today: date) -> tuple[date, date]:
    """Monday–Friday of this week; on a weekend, of the week that just ended."""
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=4)
