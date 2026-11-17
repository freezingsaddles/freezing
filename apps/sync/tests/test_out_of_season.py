"""Out of season there is nothing to sync, which is news only if you asked."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from freezing.model.orm import Athlete
from freezing.sync.data import has_strava_authorization
from freezing.sync.data.activity import ActivitySync
from freezing.sync.exc import CommandError, CompetitionOver


@contextmanager
def a_session():
    @contextmanager
    def transaction_context(*args, **kwargs):
        yield MagicMock()

    with patch("freezing.sync.data.activity.meta") as meta:
        meta.transaction_context = transaction_context
        yield


@pytest.fixture
def activity_sync():
    return ActivitySync()


def test_the_cli_still_reports_it():
    """BaseCommand.run turns a CommandError into a usage error; keep that."""
    assert issubclass(CompetitionOver, CommandError)


def test_after_the_grace_period_there_is_nothing_to_sync(activity_sync):
    over = datetime.now(UTC) - timedelta(days=30)
    with a_session(), pytest.raises(CompetitionOver) as raised:
        activity_sync.sync_rides(start_date=over - timedelta(days=90), end_date=over)
    assert "no rides to sync" in str(raised.value)


def test_force_syncs_anyway(activity_sync):
    over = datetime.now(UTC) - timedelta(days=30)
    with a_session():
        # It gets past the guard; the empty athlete query ends it harmlessly.
        activity_sync.sync_rides(
            start_date=over - timedelta(days=90), end_date=over, force=True
        )


def test_in_season_it_syncs(activity_sync):
    now = datetime.now(UTC)
    with a_session():
        activity_sync.sync_rides(
            start_date=now - timedelta(days=30), end_date=now + timedelta(days=30)
        )


def test_before_the_season_it_just_returns(activity_sync):
    """The far end of the same window, and it has always been quiet."""
    ahead = datetime.now(UTC) + timedelta(days=30)
    with a_session():
        activity_sync.sync_rides(start_date=ahead, end_date=ahead + timedelta(days=90))


def test_the_athlete_filters_are_sql_and_not_python():
    """`Athlete.team_id is not None` is True, and filters nothing."""
    for clause in (has_strava_authorization(), Athlete.team_id.isnot(None)):
        assert not isinstance(clause, bool)
        assert "IS NOT NULL" in str(clause.compile())
