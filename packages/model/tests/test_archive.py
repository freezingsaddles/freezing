"""Ranking a season's results for athlete_seasons."""

import io
from types import SimpleNamespace

from freezing.model.archive import competition_ranks, season_rows, write_sql


def result(athlete_id, team_id, points, on_leaderboard=True, name="Rider"):
    return SimpleNamespace(
        athlete_id=athlete_id,
        athlete_name=name,
        team_id=team_id,
        team_name=f"Team {team_id}" if team_id else None,
        on_leaderboard=on_leaderboard,
        points=points,
        distance=points / 5,
        days=10,
        rides=12,
        moving_time=36000,
    )


def test_ties_share_a_place_and_skip_the_next():
    assert competition_ranks({"a": 30, "b": 50, "c": 30, "d": 10}) == {
        "b": 1,
        "a": 2,
        "c": 2,
        "d": 4,
    }


def test_observers_are_kept_but_not_ranked():
    rows = season_rows(
        2024,
        [
            result(1, 10, 100),
            result(2, 10, 300),
            result(3, 20, 350),
            result(4, 99, 900, on_leaderboard=False),
            result(5, None, 50, on_leaderboard=False),
        ],
    )
    by_id = {r["athlete_id"]: r for r in rows}
    assert [r["athlete_id"] for r in rows] == [1, 2, 3, 4, 5]
    assert {i: r["rank"] for i, r in by_id.items()} == {
        1: 3,
        2: 2,
        3: 1,
        4: None,
        5: None,
    }
    # Team 10 has 400 points to team 20's 350; the observers' 900 do not count.
    assert {i: r["team_rank"] for i, r in by_id.items()} == {
        1: 1,
        2: 1,
        3: 2,
        4: None,
        5: None,
    }
    assert all(r["year"] == 2024 for r in rows)


def test_sql_replaces_the_year_and_quotes_names():
    out = io.StringIO()
    write_sql(2024, season_rows(2024, [result(1, 10, 100, name="O'Brien \\ 🚲")]), out)
    sql = out.getvalue()
    assert "DELETE FROM athlete_seasons WHERE athlete_seasons.year = 2024;" in sql
    assert "'O''Brien \\\\ 🚲'" in sql
    assert sql.startswith("begin;\n") and sql.endswith("commit;\n")
