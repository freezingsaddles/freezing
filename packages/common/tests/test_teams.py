from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from freezing.common.teams import (
    MultipleTeamsError,
    NoTeamsError,
    fill_clubs,
    looks_blank,
    register_athlete_team,
)
from freezing.model.orm import Athlete, Team

MAIN, RED, BLUE, OBSERVERS = 1, 10, 11, 99
TEAMS = {"competition_teams": [RED, BLUE], "observer_teams": [OBSERVERS]}


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


def test_every_configured_club_is_recorded(session):
    model = Athlete()
    team = register_athlete_team(
        athlete(club(RED), club(OBSERVERS), club(12345)), model, **TEAMS
    )
    assert team.id == RED
    assert sorted(t.id for t in model.clubs) == [RED, OBSERVERS]
    assert {t.id: t.leaderboard_exclude for t in model.clubs} == {
        RED: False,
        OBSERVERS: True,
    }


def test_observer_also_listed_in_teams_still_works(session):
    model = Athlete()
    team = register_athlete_team(
        athlete(club(OBSERVERS)),
        model,
        competition_teams=[RED, BLUE, OBSERVERS],
        observer_teams=[OBSERVERS],
    )
    assert team.id == OBSERVERS
    assert team.leaderboard_exclude is True
    assert [t.id for t in model.clubs] == [OBSERVERS]


def test_main_team_fallback_is_a_club_too(session):
    model = Athlete()
    team = register_athlete_team(
        athlete(club(MAIN), club(OBSERVERS)), model, main_team=MAIN, **TEAMS
    )
    assert team.id == OBSERVERS
    model = Athlete()
    team = register_athlete_team(athlete(club(MAIN)), model, main_team=MAIN, **TEAMS)
    assert team.id == MAIN
    assert [t.id for t in model.clubs] == [MAIN]


def test_clubs_are_recorded_when_no_team_can_be_chosen(session):
    model = Athlete()
    with pytest.raises(MultipleTeamsError):
        register_athlete_team(
            athlete(club(RED), club(BLUE), club(OBSERVERS)), model, **TEAMS
        )
    assert sorted(t.id for t in model.clubs) == [RED, BLUE, OBSERVERS]


def test_clubs_left_are_dropped(session):
    model = Athlete()
    register_athlete_team(athlete(club(RED), club(OBSERVERS)), model, **TEAMS)
    register_athlete_team(athlete(club(RED)), model, **TEAMS)
    assert [t.id for t in model.clubs] == [RED]


class _Client:
    def __init__(self, clubs):
        self.clubs = clubs
        self.calls = 0

    def get_athlete_clubs(self):
        self.calls += 1
        return iter(self.clubs)


def test_fill_clubs_asks_for_the_list_when_the_record_has_none():
    client = _Client([club(RED)])
    strava_athlete = fill_clubs(client, athlete())
    assert [c.id for c in strava_athlete.clubs] == [RED]


def test_fill_clubs_leaves_listed_clubs_alone():
    client = _Client([club(BLUE)])
    strava_athlete = fill_clubs(client, athlete(club(RED)))
    assert [c.id for c in strava_athlete.clubs] == [RED]
    assert client.calls == 0


def test_looks_blank():
    assert looks_blank(athlete())
    assert not looks_blank(athlete(club(RED)))
    geared = athlete()
    geared.bikes = [SimpleNamespace(id="b1")]
    assert not looks_blank(geared)


@pytest.mark.parametrize(
    "followers, friends, blank",
    [(1, 0, True), (5, 5, True), (6, 0, False), (0, 6, False), (None, None, True)],
)
def test_looks_blank_allows_a_few_followers(followers, friends, blank):
    a = athlete()
    a.follower_count = followers
    a.friend_count = friends
    assert looks_blank(a) is blank
