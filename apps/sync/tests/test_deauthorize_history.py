"""Handing back authorisations from seasons whose database is gone."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from stravalib.exc import AccessUnauthorized, Fault

from freezing.sync.cli.deauthorize_history import DeauthorizeHistoryScript

DDL = """CREATE TABLE `athletes` (
  `id` int NOT NULL,
  `name` varchar(1024) NOT NULL,
  `expires_at` int NOT NULL,
  `refresh_token` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
"""


def backup(tmp_path, name, rows):
    body = ",".join(f"({i},'A{i}',{exp},{t})" for i, exp, t in rows)
    path = tmp_path / name
    path.write_text(DDL + f"INSERT INTO `athletes` VALUES {body};\n")
    return path


@pytest.fixture
def script():
    s = DeauthorizeHistoryScript()
    s.logger = logging.getLogger("test")
    return s


def test_it_does_not_need_the_competition_database():
    """The seasons this is for have had theirs wiped."""
    assert DeauthorizeHistoryScript.needs_database is False


def test_the_newest_token_is_tried_first(script, tmp_path):
    """Ordered by the expiry Strava issued, not by the name of the file."""
    old = backup(tmp_path, "b-old.sql", [(1, 100, "'old'")])
    new = backup(tmp_path, "a-new.sql", [(1, 900, "'new'")])
    # Given oldest-last, so filename order would get this wrong.
    assert script.tokens_by_athlete([new, old])[1] == ["new", "old"]


def test_an_athlete_in_one_season_only_has_one_token(script, tmp_path):
    a = backup(tmp_path, "a.sql", [(1, 100, "'x'"), (2, 100, "'y'")])
    b = backup(tmp_path, "b.sql", [(1, 200, "'z'")])
    tokens = script.tokens_by_athlete([a, b])
    assert tokens[1] == ["z", "x"]
    assert tokens[2] == ["y"]


def test_an_athlete_without_a_token_is_skipped(script, tmp_path):
    a = backup(tmp_path, "a.sql", [(1, 100, "NULL"), (2, 100, "'y'")])
    assert set(script.tokens_by_athlete([a])) == {2}


def test_a_missing_backup_is_an_error(script, tmp_path):
    from freezing.sync.exc import CommandError

    with pytest.raises(CommandError):
        script.tokens_by_athlete([tmp_path / "absent.sql"])


def fault(status, payload):
    return Fault(
        "boom", response=SimpleNamespace(status_code=status, json=lambda: payload)
    )


REVOKED = {"errors": [{"field": "refresh_token", "code": "invalid"}]}


def run_deauthorize(script, tokens, refresh=None, on_deauthorize=None):
    client = MagicMock()
    client.refresh_access_token.side_effect = refresh
    client.deauthorize.side_effect = on_deauthorize
    with (
        patch("freezing.sync.cli.deauthorize_history.Client", return_value=client),
        patch("freezing.sync.cli.deauthorize_history.time.sleep"),
    ):
        return script.deauthorize(tokens), client


def test_a_live_token_is_handed_back(script):
    outcome, client = run_deauthorize(script, ["new"], refresh=[{"access_token": "at"}])
    assert outcome == "deauthorized"
    assert client.deauthorize.called


def test_a_spent_token_falls_through_to_an_older_one(script):
    outcome, client = run_deauthorize(
        script,
        ["new", "old"],
        refresh=[fault(400, REVOKED), {"access_token": "at"}],
    )
    assert outcome == "deauthorized"
    assert client.refresh_access_token.call_count == 2


def test_an_athlete_who_already_left_is_settled(script):
    outcome, _ = run_deauthorize(
        script, ["a", "b"], refresh=[fault(400, REVOKED), fault(400, REVOKED)]
    )
    assert outcome == "already-gone"


def test_a_token_that_works_but_is_already_revoked_is_settled(script):
    outcome, _ = run_deauthorize(
        script,
        ["a"],
        refresh=[{"access_token": "at"}],
        on_deauthorize=AccessUnauthorized("gone"),
    )
    assert outcome == "already-gone"


def test_our_own_credentials_being_refused_is_not_the_athlete_s_fault(script):
    """A 500, or a bad client_id, must not be recorded as the rider leaving."""
    with pytest.raises(Fault):
        run_deauthorize(script, ["a"], refresh=[fault(500, REVOKED)])


def test_the_ledger_settles_an_athlete(script, tmp_path):
    ledger = tmp_path / "l.jsonl"
    script.record(ledger, 1, "deauthorized")
    script.record(ledger, 2, "failed")
    assert script.read_ledger(ledger) == {1: "deauthorized", 2: "failed"}


def test_a_failure_is_left_for_the_next_run(script, tmp_path):
    from freezing.sync.cli.deauthorize_history import SETTLED

    assert "failed" not in SETTLED
    assert SETTLED == {"deauthorized", "already-gone"}


def test_the_ledger_holds_no_tokens(script, tmp_path):
    ledger = tmp_path / "l.jsonl"
    script.record(ledger, 1, "deauthorized")
    entry = json.loads(ledger.read_text())
    assert set(entry) == {"athlete_id", "outcome", "at"}


def test_a_dry_run_asks_strava_nothing(script, tmp_path):
    a = backup(tmp_path, "a.sql", [(1, 100, "'x'")])
    args = SimpleNamespace(
        backups=[a], ledger=tmp_path / "l.jsonl", yes=False, limit=None
    )
    with patch("freezing.sync.cli.deauthorize_history.Client") as client:
        script.execute(args)
    assert not client.called
    assert not (tmp_path / "l.jsonl").exists()
