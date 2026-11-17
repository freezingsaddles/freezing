"""Strava keeps sending events while riders stay authorised, season or not."""

from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from freezing.model.msg.mq import ActivityUpdateSchema
from freezing.model.orm import Athlete
from freezing.sync.config import config
from freezing.sync.subscribe import ActivityUpdateSubscriber, too_late_to_matter

DEADLINE = config.END_DATE + config.UPLOAD_GRACE_PERIOD


def message(operation, when):
    return ActivityUpdateSchema().load(
        {
            "operation": operation,
            "athlete_id": 1,
            "activity_id": 2,
            "event_time": when.isoformat(),
            "updates": {},
        }
    )


@pytest.fixture
def subscriber():
    sub = ActivityUpdateSubscriber(
        beanstalk_client=MagicMock(), shutdown_event=MagicMock()
    )
    sub.activity_sync = MagicMock()
    sub.streams_sync = MagicMock()
    sub.photos_sync = MagicMock()
    return sub


@contextmanager
def a_session():
    @contextmanager
    def transaction_context(*args, **kwargs):
        yield MagicMock(
            **{"get.return_value": Athlete(id=1, name="A Rider", team_id=None)}
        )

    with patch("freezing.sync.subscribe.meta") as meta:
        meta.transaction_context = transaction_context
        yield


@pytest.mark.parametrize("operation", ["create", "update"])
def test_a_ride_uploaded_out_of_season_is_not_fetched(subscriber, operation):
    """A live Strava call and a cache file, to decide it is not our ride."""
    with a_session():
        subscriber.handle_message(message(operation, DEADLINE + timedelta(days=180)))
    assert not subscriber.activity_sync.fetch_and_store_activity_detail.called
    assert not subscriber.streams_sync.fetch_and_store_activity_streams.called
    assert not subscriber.photos_sync.sync_photos.called


def test_a_deletion_is_honoured_whenever_it_comes(subscriber):
    """It costs no Strava call, and we should not keep what a rider removed."""
    with a_session():
        subscriber.handle_message(message("delete", DEADLINE + timedelta(days=180)))
    assert subscriber.activity_sync.delete_activity.called


def test_a_ride_from_the_season_is_fetched(subscriber):
    with a_session():
        subscriber.handle_message(message("create", DEADLINE - timedelta(days=30)))
    assert subscriber.activity_sync.fetch_and_store_activity_detail.called


def test_the_grace_period_is_inclusive():
    assert not too_late_to_matter(message("create", DEADLINE))
    assert too_late_to_matter(message("create", DEADLINE + timedelta(seconds=1)))


def test_an_event_with_no_time_is_not_assumed_stale():
    m = ActivityUpdateSchema().load(
        {"operation": "create", "athlete_id": 1, "activity_id": 2, "updates": {}}
    )
    assert not too_late_to_matter(m)
