"""A ride whose photos have no primary must not call the detail sync for ever.

Only the ride's details name the primary photo, so photo sync asks for them
again when it cannot find one. The detail fetch schedules a photo fetch in
return, which is a cycle if the asking is unconditional.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from freezing.model.orm import Ride, RidePhoto
from freezing.sync.data.photos import (
    MAX_FETCHES,
    PhotoSync,
    _schedule_next_fetch,
    schedule_one_more_fetch,
)


def photo(unique_id, caption=""):
    return SimpleNamespace(
        unique_id=unique_id, caption=caption, urls={"1000": f"http://x/{unique_id}"}
    )


@pytest.fixture
def ride():
    r = Ride(1)
    r.detail_fetched = True
    r.photos_fetched = 3
    return r


@pytest.fixture
def sync():
    return PhotoSync()


def write(sync, ride, photos, stored):
    """Run a photo pass with `stored` already in the database."""
    session = MagicMock()
    session.query.return_value.filter_by.return_value = stored
    with patch("freezing.sync.data.photos.meta") as meta:
        meta.scoped_session.return_value = session
        sync.write_ride_photos_nonprimary(photos, ride, 1000)


def test_a_new_photo_without_a_primary_asks_for_the_details(sync, ride):
    write(sync, ride, [photo("a")], stored=[])
    assert ride.detail_fetched is False


def test_the_same_photos_again_do_not(sync, ride):
    """The loop: this is the pass that used to ask a second, hundredth time."""
    stored = [RidePhoto(id="a", ride_id=1, primary=False)]
    write(sync, ride, [photo("a")], stored=stored)
    assert ride.detail_fetched is True


def test_a_deleted_photo_still_asks(sync, ride):
    """The primary may have been the one removed, so the answer has changed."""
    stored = [
        RidePhoto(id="a", ride_id=1, primary=False),
        RidePhoto(id="b", ride_id=1, primary=False),
    ]
    write(sync, ride, [photo("a")], stored=stored)
    assert ride.detail_fetched is False


def test_a_known_primary_never_asks(sync, ride):
    stored = [RidePhoto(id="a", ride_id=1, primary=True)]
    write(sync, ride, [photo("a"), photo("b")], stored=stored)
    assert ride.detail_fetched is True


def test_the_cycle_settles(sync, ride):
    """Drive both halves against each other and watch it stop."""
    # Where ride 17399521117 was found: past its budget, details re-armed.
    ride.photos_fetched = MAX_FETCHES
    ride.photos_resync_date = None
    ride.detail_fetched = False
    stored = [RidePhoto(id="a", ride_id=1, primary=False)]

    passes = 0
    while ride.detail_fetched is False or ride.photos_resync_date is not None:
        passes += 1
        assert passes < 10, "the photo and detail syncs are still calling each other"
        if ride.detail_fetched is False:
            # What the detail sync does on its way past.
            ride.detail_fetched = True
            schedule_one_more_fetch(ride)
        if ride.photos_resync_date is not None:
            write(sync, ride, [photo("a")], stored=stored)
            _schedule_next_fetch(ride)

    assert ride.detail_fetched is True
    assert ride.photos_resync_date is None


def test_the_count_stops_where_the_backoff_does(ride):
    """photos_fetched = 18 in production, on a cap of 14."""
    ride.photos_fetched = MAX_FETCHES
    for _ in range(5):
        _schedule_next_fetch(ride)
    assert ride.photos_fetched == MAX_FETCHES
