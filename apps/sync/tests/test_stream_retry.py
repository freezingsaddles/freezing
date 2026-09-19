"""Strava serves streams late, so a ride can arrive without its GPS track."""

import pytest

from freezing.model.orm import Ride
from freezing.sync.data.streams import schedule_track_retry


@pytest.fixture
def ride():
    return Ride(1)


def test_a_ride_with_a_track_is_left_alone(ride):
    ride.track_fetched = True
    schedule_track_retry(ride)
    assert ride.track_fetched is True


def test_a_ride_whose_track_was_not_ready_is_asked_again(ride):
    # write_ride_streams writes None when there is no latlng stream, and the
    # sweep selects on `== False`, which in SQL never matches NULL.
    ride.track_fetched = None
    schedule_track_retry(ride)
    assert ride.track_fetched is False


def test_a_ride_still_waiting_stays_in_the_queue(ride):
    ride.track_fetched = False
    schedule_track_retry(ride)
    assert ride.track_fetched is False


def test_a_trimmed_ride_is_asked_again(ride):
    """_sync_rides clears the flag on a distance change; it stays cleared."""
    ride.track_fetched = True
    ride.track_fetched = False  # what the distance mismatch writes
    schedule_track_retry(ride)
    assert ride.track_fetched is False


def test_the_retries_are_bounded_by_the_effort_resync(ride):
    """Four visits, then update_ride_complete is not reached again."""
    from freezing.sync.data.activity import MAX_EFFORT_RESYNCS, schedule_effort_resync

    ride.track_fetched = None
    ride.efforts_fetched = False
    ride.resync_count = 0

    asks = 0
    while not ride.efforts_fetched:
        schedule_effort_resync(ride)
        if not ride.efforts_fetched:
            schedule_track_retry(ride)  # what a detail fetch does
            ride.track_fetched = None  # ... and the sweep finds nothing
            asks += 1
    assert asks == MAX_EFFORT_RESYNCS


def run_sweep(ride, *, streams=None, raises=False):
    """One pass of sync_streams over a single ride."""
    from unittest.mock import MagicMock, patch

    from freezing.sync.data.streams import StreamSync

    session = MagicMock()
    session.get.return_value = ride
    query = session.query.return_value
    for method in ("options", "filter"):
        setattr(query, method, MagicMock(return_value=query))
    query.__iter__ = lambda self: iter([ride])

    fetcher = MagicMock()
    if raises:
        fetcher.return_value.fetch.side_effect = RuntimeError("Strava said no")
    else:
        fetcher.return_value.fetch.return_value = streams

    with (
        patch("freezing.sync.data.streams.meta") as meta,
        patch("freezing.sync.data.streams.StravaClientForAthlete"),
        patch("freezing.sync.data.streams.CachingStreamFetcher", fetcher),
    ):
        meta.scoped_session.return_value = session
        StreamSync().sync_streams()
    return session


def test_a_ride_with_no_streams_leaves_the_queue(ride):
    """Otherwise it is read again every five minutes for the rest of the season."""
    ride.track_fetched = False
    run_sweep(ride, streams=[])
    assert ride.track_fetched is None


def test_a_ride_whose_fetch_raises_leaves_the_queue(ride):
    ride.track_fetched = False
    run_sweep(ride, raises=True)
    assert ride.track_fetched is None


def test_each_ride_is_committed_on_its_own(ride):
    """A restart mid-pass keeps the tracks already read."""
    ride.track_fetched = False
    session = run_sweep(ride, streams=[])
    assert session.commit.called
