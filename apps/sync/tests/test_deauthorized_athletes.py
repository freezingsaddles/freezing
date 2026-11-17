"""Strava never says a rider disconnected; a dead refresh token is how we learn."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from stravalib.exc import Fault

from freezing.model.orm import Athlete
from freezing.sync.data import (
    StravaClientForAthlete,
    _refresh_token_rejected,
    has_strava_authorization,
)
from freezing.sync.exc import AthleteDeauthorized


def fault(status_code, payload):
    return Fault(
        "boom", response=SimpleNamespace(status_code=status_code, json=lambda: payload)
    )


REVOKED = {
    "message": "Bad Request",
    "errors": [
        {"resource": "RefreshToken", "field": "refresh_token", "code": "invalid"}
    ],
}


def test_a_revoked_refresh_token_is_recognised():
    assert _refresh_token_rejected(fault(400, REVOKED))


@pytest.mark.parametrize(
    "example",
    [
        fault(500, REVOKED),
        fault(400, {"errors": [{"field": "client_id", "code": "invalid"}]}),
        fault(400, {"errors": []}),
        fault(400, {}),
        Fault("no response at all"),
    ],
)
def test_other_faults_are_left_alone(example):
    """Our own credentials being wrong must not look like a rider disconnecting."""
    assert not _refresh_token_rejected(example)


def test_a_malformed_body_is_not_a_revocation():
    def explode():
        raise ValueError("not json")

    assert not _refresh_token_rejected(
        Fault("boom", response=SimpleNamespace(status_code=400, json=explode))
    )


@pytest.fixture
def athlete():
    return Athlete(
        id=1, name="A Rider", access_token="stale", refresh_token="dead", expires_at=0
    )


def test_a_disconnected_athlete_is_forgotten(athlete):
    with (
        patch("freezing.sync.data.meta") as meta,
        patch(
            "stravalib.client.Client.refresh_access_token",
            side_effect=fault(400, REVOKED),
        ),
    ):
        meta.scoped_session.return_value = MagicMock()
        with pytest.raises(AthleteDeauthorized):
            StravaClientForAthlete(athlete)

    assert athlete.access_token is None
    assert athlete.refresh_token is None
    assert athlete.expires_at == 0


def test_an_athlete_with_no_tokens_is_not_an_error_worth_a_traceback(athlete):
    athlete.access_token = None
    athlete.refresh_token = None
    with pytest.raises(AthleteDeauthorized):
        StravaClientForAthlete(athlete)


def test_a_fault_that_is_not_a_revocation_still_surfaces(athlete):
    with (
        patch(
            "stravalib.client.Client.refresh_access_token",
            side_effect=fault(500, REVOKED),
        ),
        pytest.raises(Fault),
    ):
        StravaClientForAthlete(athlete)
    # Their tokens are none of our business if the failure was at our end.
    assert athlete.refresh_token == "dead"


def test_the_filter_keeps_athletes_we_hold_either_token_for():
    sql = str(
        has_strava_authorization().compile(compile_kwargs={"literal_binds": True})
    )
    assert "refresh_token IS NOT NULL" in sql
    assert "access_token IS NOT NULL" in sql
