"""Strava returns a ride's efforts late, so every ride is read again on a backoff."""

from datetime import datetime
from unittest.mock import patch

import pytest

from freezing.model.orm import Ride
from freezing.sync.data.activity import MAX_EFFORT_RESYNCS, schedule_effort_resync

# Cumulative hours from the first detail fetch, per the comment on the backoff.
EXPECTED = [1, 7, 43, 259]


@pytest.fixture
def ride():
    r = Ride(1)
    r.efforts_fetched = False
    r.resync_count = 0
    return r


START = datetime(2026, 1, 1)


class Clock:
    """A ride is read again at its due time, so the clock has to follow it."""

    def __init__(self):
        self.now_ = START

    def now(self):
        return self.now_


def replay(ride):
    """Follow the ride until it is left alone, collecting when it was read."""
    clock = Clock()
    seen = []
    with patch("freezing.sync.data.activity.datetime", clock):
        while not ride.efforts_fetched:
            before = ride.resync_date
            schedule_effort_resync(ride)
            if ride.resync_date != before:
                clock.now_ = ride.resync_date
                seen.append(round((ride.resync_date - START).total_seconds() / 3600))
    return seen


def test_the_backoff_is_the_one_the_comment_claims(ride):
    assert replay(ride) == EXPECTED


def test_it_gives_up_rather_than_reading_for_ever(ride):
    replay(ride)
    assert ride.efforts_fetched
    assert ride.resync_count == MAX_EFFORT_RESYNCS


def test_the_constant_counts_the_resyncs_it_names(ride):
    """It read `> _MAX_EFFORT_RESYNCS` once, and quietly did one more."""
    assert len(replay(ride)) == MAX_EFFORT_RESYNCS


def test_a_ride_that_has_had_its_share_is_not_read_again(ride):
    ride.resync_count = MAX_EFFORT_RESYNCS
    schedule_effort_resync(ride)
    assert ride.efforts_fetched
    assert ride.resync_date is None


def test_a_ride_that_has_never_been_counted_starts_at_the_beginning(ride):
    ride.resync_count = None
    schedule_effort_resync(ride)
    assert ride.resync_count == 1


def test_the_last_read_is_about_eleven_days_out(ride):
    assert 10 < replay(ride)[-1] / 24 < 12
