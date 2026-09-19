import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from freezing.common.athletes import full_name, register_athlete
from freezing.model.orm import Athlete

TOKENS = {"access_token": "at", "refresh_token": "rt", "expires_at": 1800000000}


def strava(firstname="Ann", lastname="Rider", athlete_id=5, profile="pic"):
    return SimpleNamespace(
        id=athlete_id, firstname=firstname, lastname=lastname, profile=profile
    )


@pytest.fixture
def session():
    """Return a session with no existing athlete and no display name collisions."""
    session = MagicMock()
    session.get.return_value = None
    session.query.return_value.filter.return_value.filter.return_value.count.return_value = (
        0
    )
    with patch("freezing.common.athletes.meta.scoped_session", return_value=session):
        yield session


def collides(session, times=1):
    """Make the next `times` display-name lookups report a conflict."""
    counter = session.query.return_value.filter.return_value.filter.return_value.count
    counter.side_effect = [1] * times + [0] * 10


def test_new_athlete_is_added(session):
    athlete = register_athlete(strava(), **TOKENS)
    assert (athlete.id, athlete.name) == (5, "Ann Rider")
    assert athlete.profile_photo == "pic"
    assert (athlete.access_token, athlete.refresh_token) == ("at", "rt")
    assert athlete.expires_at == 1800000000
    session.add.assert_called_once_with(athlete)


def test_display_name_abbreviates_the_surname(session):
    assert register_athlete(strava(), **TOKENS).display_name == "Ann R"


def test_display_name_falls_back_when_it_collides(session):
    collides(session)
    assert register_athlete(strava(), **TOKENS).display_name == "Ann Rider"


def test_missing_surname(session):
    for lastname in (None, "", "  "):
        athlete = register_athlete(strava(lastname=lastname), **TOKENS)
        assert athlete.name == "Ann"
        assert athlete.display_name == "Ann"


def test_existing_row_is_updated(session):
    existing = Athlete(id=5, name="Ann Rider", display_name="Handpicked")
    session.get.return_value = existing
    athlete = register_athlete(strava(profile="new"), **TOKENS)
    assert athlete is existing
    assert athlete.profile_photo == "new"


def test_a_set_display_name_survives(session):
    session.get.return_value = Athlete(id=5, name="Ann Rider", display_name="Annie")
    assert register_athlete(strava(), **TOKENS).display_name == "Annie"


def test_a_missing_display_name_is_filled_in(session):
    session.get.return_value = Athlete(id=5, name="Ann Rider", display_name=None)
    assert register_athlete(strava(), **TOKENS).display_name == "Ann R"


def test_rename_recomputes_the_display_name(session):
    session.get.return_value = Athlete(id=5, name="Ann Rider", display_name="Ann R")
    athlete = register_athlete(strava(lastname="Cyclist"), **TOKENS)
    assert (athlete.name, athlete.display_name) == ("Ann Cyclist", "Ann C")


def test_rename_is_logged(session, caplog):
    session.get.return_value = Athlete(id=5, name="Ann Rider", display_name="Ann R")
    with caplog.at_level(logging.INFO, logger="freezing.common.athletes"):
        register_athlete(strava(lastname="Cyclist"), **TOKENS)
    assert "'Ann Rider' was renamed 'Ann Cyclist'" in caplog.text


def test_a_new_athlete_is_not_reported_as_renamed(session, caplog):
    with caplog.at_level(logging.INFO, logger="freezing.common.athletes"):
        register_athlete(strava(), **TOKENS)
    assert "renamed" not in caplog.text


def test_disambiguation_failure_falls_back_to_the_full_name(session, caplog):
    session.query.side_effect = RuntimeError("database gone")
    with caplog.at_level(logging.ERROR, logger="freezing.common.athletes"):
        athlete = register_athlete(strava(), **TOKENS)
    assert athlete.display_name == "Ann Rider"
    assert "disambiguation error" in caplog.text


def test_tokens_left_alone_when_not_given(session):
    session.get.return_value = Athlete(
        id=5, name="Ann Rider", access_token="old", refresh_token="keep", expires_at=42
    )
    athlete = register_athlete(strava(), access_token="fresh")
    assert athlete.access_token == "fresh"
    assert (athlete.refresh_token, athlete.expires_at) == ("keep", 42)


def test_full_name_trims():
    assert full_name(strava(firstname=" Ann ", lastname=" Rider ")) == "Ann Rider"
    assert full_name(strava(firstname="Ann", lastname=None)) == "Ann"
    assert full_name(strava(firstname=None, lastname="Rider")) == "Rider"
