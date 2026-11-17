"""sync_photos passes private rides over, so nothing should schedule one."""

from datetime import datetime

import pytest

from freezing.model.orm import Ride
from freezing.sync.data.photos import (
    MAX_FETCHES,
    schedule_fetch,
    schedule_one_more_fetch,
)


@pytest.fixture
def ride():
    r = Ride(1)
    r.private = False
    return r


def test_a_public_ride_is_scheduled(ride):
    schedule_fetch(ride)
    assert ride.photos_fetched == 0
    assert ride.photos_resync_date <= datetime.now()


def test_a_private_ride_is_not(ride):
    ride.private = True
    schedule_fetch(ride)
    assert ride.photos_fetched is None
    assert ride.photos_resync_date is None


def test_a_private_ride_is_not_asked_for_one_more_look(ride):
    ride.private = True
    ride.photos_fetched = 3
    schedule_one_more_fetch(ride)
    assert ride.photos_resync_date is None


def test_going_private_clears_a_schedule_already_set(ride):
    """Every detail fetch passes through here, so this is where it is noticed."""
    schedule_fetch(ride)
    ride.private = True
    schedule_one_more_fetch(ride)
    assert ride.photos_fetched is None
    assert ride.photos_resync_date is None


def test_going_public_starts_the_backoff(ride):
    """update_ride_basic schedules on `photos_fetched is None`, so leave it so."""
    ride.private = True
    schedule_fetch(ride)
    assert ride.photos_fetched is None

    ride.private = False
    schedule_fetch(ride)
    assert ride.photos_fetched == 0
    assert ride.photos_resync_date <= datetime.now()


def test_a_private_ride_is_never_left_permanently_due(ride):
    """1250 rows sat at 13 with a 1970 date, due every minute, for ever."""
    ride.private = True
    for _ in range(MAX_FETCHES + 5):
        schedule_fetch(ride)
        schedule_one_more_fetch(ride)
    assert ride.photos_resync_date is None
