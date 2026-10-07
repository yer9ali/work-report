from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from period import parse_ts, period_bounds, week_bounds

ALMATY = ZoneInfo("Asia/Almaty")


def test_period_covers_whole_local_days() -> None:
    start, end = period_bounds(date(2026, 10, 7), date(2026, 10, 7), ALMATY)

    assert start == datetime(2026, 10, 7, 0, 0, tzinfo=ALMATY)
    assert end == datetime(2026, 10, 8, 0, 0, tzinfo=ALMATY)


def test_parse_ts_reads_z_and_rejects_garbage() -> None:
    assert parse_ts("2026-10-06T12:44:19.414079Z") == datetime(
        2026, 10, 6, 12, 44, 19, 414079, tzinfo=timezone.utc
    )
    assert parse_ts(None) is None
    assert parse_ts("вчера") is None


def test_week_is_monday_to_friday_and_weekend_means_the_week_just_ended() -> None:
    assert week_bounds(date(2026, 10, 7)) == (date(2026, 10, 5), date(2026, 10, 9))
    assert week_bounds(date(2026, 10, 10)) == (date(2026, 10, 5), date(2026, 10, 9))
    assert week_bounds(date(2026, 10, 12)) == (date(2026, 10, 12), date(2026, 10, 16))
