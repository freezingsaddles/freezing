"""Strava's athlete webhook: the one notice we get that a rider disconnected."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from freezing.model.msg.mq import AthleteUpdate, AthleteUpdateSchema, DefinedTubes
from freezing.model.msg.strava import AspectType
from freezing.model.orm import Athlete
from freezing.sync.subscribe import ActivityUpdateSubscriber

DEAUTHORIZED = {
    "operation": "update",
    "athlete_id": 222,
    "updates": {"authorized": "false"},
}


@pytest.fixture
def athlete():
    return Athlete(
        id=222, name="A Rider", access_token="at", refresh_token="rt", expires_at=99
    )


@pytest.fixture
def subscriber():
    return ActivityUpdateSubscriber(
        beanstalk_client=MagicMock(), shutdown_event=MagicMock()
    )


@contextmanager
def session_holding(athlete):
    session = MagicMock()
    session.get.return_value = athlete

    @contextmanager
    def transaction_context(*args, **kwargs):
        yield session

    with (
        patch("freezing.sync.subscribe.meta") as subscribe_meta,
        patch("freezing.sync.data.meta") as data_meta,
    ):
        subscribe_meta.transaction_context = transaction_context
        data_meta.scoped_session.return_value = MagicMock()
        yield session


def test_the_message_reads_its_own_intent():
    message = AthleteUpdateSchema().load(DEAUTHORIZED)
    assert message.deauthorized
    assert message.athlete_id == 222
    assert message.operation is AspectType.update


@pytest.mark.parametrize("updates", [{}, None, {"authorized": "true"}, {"other": "x"}])
def test_an_athlete_update_that_is_not_a_disconnection_changes_nothing(updates):
    message = AthleteUpdate()
    message.updates = updates
    assert not message.deauthorized


def test_a_disconnection_forgets_the_tokens(subscriber, athlete):
    message = AthleteUpdateSchema().load(DEAUTHORIZED)
    with session_holding(athlete):
        subscriber.handle_athlete_message(message)

    assert athlete.access_token is None
    assert athlete.refresh_token is None
    assert athlete.expires_at == 0


def test_the_rider_keeps_their_rides(subscriber, athlete):
    """Scoring is on what was ridden, not on who is still connected."""
    message = AthleteUpdateSchema().load(DEAUTHORIZED)
    with session_holding(athlete) as session:
        subscriber.handle_athlete_message(message)

    assert not session.delete.called


def test_an_athlete_update_we_have_no_use_for_is_left_alone(subscriber, athlete):
    message = AthleteUpdateSchema().load(
        {"operation": "update", "athlete_id": 222, "updates": {"authorized": "true"}}
    )
    with session_holding(athlete):
        subscriber.handle_athlete_message(message)

    assert athlete.access_token == "at"
    assert athlete.refresh_token == "rt"


def test_an_athlete_we_do_not_know_is_not_an_error(subscriber):
    message = AthleteUpdateSchema().load(DEAUTHORIZED)
    with session_holding(None):
        subscriber.handle_athlete_message(message)


def test_the_two_tubes_are_distinct():
    assert DefinedTubes.activity_update.value != DefinedTubes.athlete_update.value
