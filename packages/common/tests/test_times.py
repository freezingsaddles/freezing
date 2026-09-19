from datetime import UTC, datetime, timedelta, timezone

import pytest

from freezing.common.times import parse_instant


def test_an_offset_is_kept():
    assert parse_instant("2019-01-01T00:00:00-05:00") == datetime(
        2019, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=-5))
    )


def test_z_is_utc():
    assert parse_instant("2026-01-15T14:30:00Z") == datetime(
        2026, 1, 15, 14, 30, tzinfo=UTC
    )


def test_no_offset_is_read_as_utc():
    assert parse_instant("2026-01-15T14:30:00") == datetime(
        2026, 1, 15, 14, 30, tzinfo=UTC
    )


def test_a_bare_date_is_midnight_utc():
    assert parse_instant("2026-01-15") == datetime(2026, 1, 15, 0, 0, tzinfo=UTC)


def test_the_same_instant_written_two_ways():
    assert parse_instant("2019-01-01T00:00:00-05:00") == parse_instant(
        "2019-01-01T05:00:00Z"
    )


def test_nonsense_is_refused():
    with pytest.raises(ValueError):
        parse_instant("not a date")
