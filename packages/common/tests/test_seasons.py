"""The seasons, against instants published by the US Naval Observatory."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from freezing.common.seasons import (
    DECEMBER_SOLSTICE,
    JUNE_SOLSTICE,
    MARCH_EQUINOX,
    SEPTEMBER_EQUINOX,
    end_of_winter,
    last_full_day_of_winter,
    season,
)

DC = ZoneInfo("America/New_York")

# https://aa.usno.navy.mil/data/Earth_Seasons, in UTC.
PUBLISHED = [
    (2024, MARCH_EQUINOX, "2024-03-20 03:06"),
    (2024, JUNE_SOLSTICE, "2024-06-20 20:51"),
    (2024, SEPTEMBER_EQUINOX, "2024-09-22 12:44"),
    (2024, DECEMBER_SOLSTICE, "2024-12-21 09:20"),
    (2025, MARCH_EQUINOX, "2025-03-20 09:01"),
    (2025, JUNE_SOLSTICE, "2025-06-21 02:42"),
    (2025, SEPTEMBER_EQUINOX, "2025-09-22 18:19"),
    (2025, DECEMBER_SOLSTICE, "2025-12-21 15:03"),
    (2026, MARCH_EQUINOX, "2026-03-20 14:46"),
    (2026, JUNE_SOLSTICE, "2026-06-21 08:24"),
    (2026, SEPTEMBER_EQUINOX, "2026-09-23 00:05"),
    (2026, DECEMBER_SOLSTICE, "2026-12-21 20:50"),
]


@pytest.mark.parametrize("year,which,published", PUBLISHED)
def test_within_a_couple_of_minutes_of_the_observatory(year, which, published):
    expected = datetime.strptime(published, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    off_by = abs((season(year, which) - expected).total_seconds())
    # Without the correction from dynamical time these run about 100s late,
    # so this is tight enough to notice if that is ever dropped.
    assert off_by < 90, f"{year} {which} is {off_by:.0f}s out"


@pytest.mark.parametrize(
    "year,expected",
    [
        (2024, "2024-03-18"),
        (2025, "2025-03-19"),
        (2026, "2026-03-19"),
        (2027, "2027-03-19"),
        (2028, "2028-03-18"),
    ],
)
def test_the_last_whole_day_of_winter(year, expected):
    assert str(last_full_day_of_winter(year, DC)) == expected


def test_a_day_the_equinox_falls_in_is_not_a_whole_day_of_winter():
    """2024's equinox is just after 11pm on the 19th in Washington."""
    equinox = season(2024, MARCH_EQUINOX).astimezone(DC)
    assert equinox.date().isoformat() == "2024-03-19"
    assert equinox.hour == 23
    assert str(last_full_day_of_winter(2024, DC)) == "2024-03-18"


def test_the_end_of_winter_is_the_end_of_that_day():
    end = end_of_winter(2026, DC)
    assert end.strftime("%Y-%m-%d %H:%M:%S %Z") == "2026-03-19 23:59:59 EDT"
    assert end.tzinfo is DC


def test_the_seasons_of_a_year_come_in_order():
    turns = [
        season(2026, which)
        for which in (
            MARCH_EQUINOX,
            JUNE_SOLSTICE,
            SEPTEMBER_EQUINOX,
            DECEMBER_SOLSTICE,
        )
    ]
    assert turns == sorted(turns)
