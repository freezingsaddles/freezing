"""A ride the forecaster has nothing for must not be asked about for ever."""

from unittest.mock import MagicMock, patch

import pytest

from freezing.model.orm import Ride
from freezing.sync.data.weather import MAX_WEATHER_ATTEMPTS, WeatherSync


@pytest.fixture
def weather_sync():
    return WeatherSync()


def run(weather_sync, ride, *, fails, **kwargs):
    """One pass of sync_weather over a single ride."""
    session = MagicMock()
    session.get.return_value = ride
    session.execute.return_value.fetchall.return_value = [
        MagicMock(_mapping={"id": ride.id, "start_geo": "POINT(-77.0 38.9)"})
    ]
    vc = MagicMock()
    if fails:
        vc.return_value.histo_forecast.side_effect = RuntimeError("no observations")
    with (
        patch("freezing.sync.data.weather.meta") as meta,
        patch("freezing.sync.data.weather.HistoVisualCrossing", vc),
    ):
        meta.scoped_session.return_value = session
        weather_sync.sync_weather(**kwargs)
    return session


@pytest.fixture
def ride():
    r = Ride(1)
    r.weather_attempts = 0
    r.timezone = "America/New_York"
    r.elapsed_time = 3600
    r.moving_time = 3600
    return r


def test_a_failure_is_counted(weather_sync, ride):
    run(weather_sync, ride, fails=True)
    assert ride.weather_attempts == 1


def test_the_count_is_committed_not_rolled_back(weather_sync, ride):
    """The rollback that discards the half-written weather must not discard it."""
    session = run(weather_sync, ride, fails=True)
    assert session.commit.called


def test_a_ride_is_given_up_on(weather_sync, ride):
    ride.weather_attempts = MAX_WEATHER_ATTEMPTS - 1
    run(weather_sync, ride, fails=True)
    assert ride.weather_attempts == MAX_WEATHER_ATTEMPTS


def test_the_query_stops_selecting_it():
    """The bound has to be in the SQL, or counting it changes nothing."""
    import inspect

    source = inspect.getsource(WeatherSync.sync_weather)
    assert "R.weather_attempts < :max_attempts" in source
    assert "max_attempts=MAX_WEATHER_ATTEMPTS" in source


def test_half_a_day_of_asking():
    """The job runs hourly; fewer attempts than that is a short outage."""
    assert MAX_WEATHER_ATTEMPTS == 12


def test_retry_failed_asks_again(weather_sync, ride):
    session = run(weather_sync, ride, fails=True, retry_failed=True)
    updated = session.query.return_value.filter.return_value.update
    assert updated.called
    assert updated.call_args[0][0] == {Ride.weather_attempts: 0}


def test_nothing_is_reset_without_asking(weather_sync, ride):
    session = run(weather_sync, ride, fails=True)
    assert not session.query.return_value.filter.return_value.update.called
