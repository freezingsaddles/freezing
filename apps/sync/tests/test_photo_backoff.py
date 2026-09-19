"""The photo fetch backoff: Strava never tells us a caption was written."""

from datetime import datetime, timedelta

import pytest

from freezing.model.orm import Ride
from freezing.sync.data.photos import (
    FIRST_INTERVAL,
    MAX_FETCHES,
    POLL_INTERVAL,
    _schedule_next_fetch,
    schedule_fetch,
    schedule_one_more_fetch,
)


@pytest.fixture
def ride():
    return Ride(1)


def test_a_ride_with_no_photos_is_left_alone(ride):
    assert ride.photos_fetched is None
    schedule_one_more_fetch(ride)
    assert ride.photos_resync_date is None


def test_scheduling_a_fetch_makes_it_due_now(ride):
    schedule_fetch(ride)
    assert ride.photos_fetched == 0
    assert ride.photos_resync_date <= datetime.now()


def test_the_interval_doubles(ride):
    schedule_fetch(ride)
    intervals = []
    for _ in range(MAX_FETCHES - 1):
        before = datetime.now()
        _schedule_next_fetch(ride)
        intervals.append(round((ride.photos_resync_date - before).total_seconds() / 60))
    assert intervals == [2 * 2**n for n in range(MAX_FETCHES - 1)]


def test_it_gives_up_after_the_last_fetch(ride):
    schedule_fetch(ride)
    for _ in range(MAX_FETCHES):
        _schedule_next_fetch(ride)
    assert ride.photos_fetched == MAX_FETCHES
    assert ride.photos_resync_date is None


def test_it_covers_the_same_ground_as_the_effort_resync_it_replaces(ride):
    total = sum(
        (timedelta(minutes=2 * 2**n) for n in range(MAX_FETCHES - 1)), timedelta()
    )
    assert timedelta(days=10) < total < timedelta(days=12)


def test_an_update_restarts_the_backoff(ride):
    schedule_fetch(ride)
    for _ in range(MAX_FETCHES):
        _schedule_next_fetch(ride)
    assert ride.photos_resync_date is None

    schedule_fetch(ride)
    assert ride.photos_fetched == 0
    assert ride.photos_resync_date <= datetime.now()


def test_one_more_look_does_not_restart_the_backoff(ride):
    schedule_fetch(ride)
    for _ in range(MAX_FETCHES):
        _schedule_next_fetch(ride)

    schedule_one_more_fetch(ride)
    assert ride.photos_fetched == MAX_FETCHES
    assert ride.photos_resync_date <= datetime.now()

    # That one look is all it buys.
    _schedule_next_fetch(ride)
    assert ride.photos_resync_date is None


def test_we_look_often_enough_for_the_first_step_to_mean_anything():
    """A ride waits for the tick after it falls due, so the tick bounds it."""
    assert POLL_INTERVAL <= FIRST_INTERVAL
