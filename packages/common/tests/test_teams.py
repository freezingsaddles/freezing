from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from freezing.common.teams import (
    MultipleTeamsError,
    NoTeamsError,
    register_athlete_team,
)
from freezing.model.orm import Athlete, Team

MAIN, RED, BLUE, OBSERVERS = 1, 10, 11, 99
TEAMS = {"competition_teams": [RED, BLUE, OBSERVERS], "observer_teams": [OBSERVERS]}


def club(club_id, name="Club"):
    return SimpleNamespace(
        id=club_id, name=name, cover_photo=f"cover-{club_id}", profile=f"pic-{club_id}"
    )


def athlete(*clubs):
    return SimpleNamespace(id=5, firstname="Ann", lastname="Rider", clubs=list(clubs))


@pytest.fixture
def session():
    session = MagicMock()
    session.get.return_value = None
    with patch("freezing.common.teams.meta.scoped_session", return_value=session):
        yield session


def test_single_team_creates_row(session):
    model = Athlete()
    team = register_athlete_team(athlete(club(RED, "Red")), model, **TEAMS)
    assert isinstance(team, Team)
    assert (team.id, team.name) == (RED, "Red")
    assert (team.cover_photo, team.profile_photo) == ("cover-10", "pic-10")
    assert team.leaderboard_exclude is False
    assert model.team is team
    session.add.assert_called_once_with(team)


def test_existing_row_is_updated(session):
    existing = Team(id=RED, name="Old name")
    session.get.return_value = existing
    team = register_athlete_team(athlete(club(RED, "Red")), Athlete(), **TEAMS)
    assert team is existing
    assert team.name == "Red"


def test_observer_membership_does_not_conflict(session):
    team = register_athlete_team(
        athlete(club(RED), club(OBSERVERS)), Athlete(), **TEAMS
    )
    assert team.id == RED


def test_observer_only_is_excluded_from_leaderboard(session):
    team = register_athlete_team(athlete(club(OBSERVERS)), Athlete(), **TEAMS)
    assert team.id == OBSERVERS
    assert team.leaderboard_exclude is True


def test_two_real_teams_is_an_error(session):
    with pytest.raises(MultipleTeamsError) as info:
        register_athlete_team(athlete(club(RED), club(BLUE)), Athlete(), **TEAMS)
    assert [c.id for c in info.value.teams] == [RED, BLUE]


def test_falls_back_to_main_team(session):
    team = register_athlete_team(
        athlete(club(MAIN), club(12345)), Athlete(), main_team=MAIN, **TEAMS
    )
    assert team.id == MAIN


def test_no_matching_team(session):
    with pytest.raises(NoTeamsError):
        register_athlete_team(athlete(club(12345)), Athlete(), main_team=MAIN, **TEAMS)


def test_no_clubs_means_reauthorize(session):
    strava_athlete = athlete()
    strava_athlete.clubs = None
    with pytest.raises(NoTeamsError, match="re-authorize"):
        register_athlete_team(strava_athlete, Athlete(), **TEAMS)
