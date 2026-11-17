"""Keep each athlete's season results through the yearly wipe.

Run it against production before year-start.sql empties the tables, or against
an old backup restored somewhere else with ``--sql`` to write statements that
production can load. Points come from the database's own ``daily_scores``
view, because the scoring has changed over the years. The source is opened
with a bare engine rather than ``init_model``, which would migrate a restored
backup and replace that view with today's.

The queries keep to what MySQL 5.7 and the oldest schemas have: no common
table expressions, no window functions, no ``rides.competition_date``.
"""

import argparse
import logging
import sys
from collections.abc import Iterable
from typing import Any, TextIO

from sqlalchemy import create_engine, delete, insert, text
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Connection

from freezing.model.config import config
from freezing.model.orm import AthleteSeason

log = logging.getLogger(__name__)

_SEASON = text("""
    select
      D.athlete_id,
      coalesce(A.display_name, A.name) as athlete_name,
      A.team_id,
      T.name as team_name,
      coalesce(not T.leaderboard_exclude, false) as on_leaderboard,
      D.points,
      D.distance,
      D.days,
      coalesce(R.rides, 0) as rides,
      coalesce(R.moving_time, 0) as moving_time
    from (
      select athlete_id, sum(points) as points, sum(distance) as distance,
        count(*) as days
      from daily_scores
      group by athlete_id
    ) D
    join athletes A on A.id = D.athlete_id
    left join teams T on T.id = A.team_id
    left join (
      select athlete_id, count(*) as rides, sum(moving_time) as moving_time
      from rides
      group by athlete_id
    ) R on R.athlete_id = D.athlete_id
""")


def competition_ranks[K](scores: dict[K, float]) -> dict[K, int]:
    """Rank highest first, ties sharing a place and the next place skipped."""
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    ranks: dict[K, int] = {}
    previous = None
    for place, (key, score) in enumerate(ordered, start=1):
        if score != previous:
            rank, previous = place, score
        ranks[key] = rank
    return ranks


def season_rows(year: int, results: Iterable[Any]) -> list[dict]:
    """Turn the per-athlete query results into athlete_seasons rows."""
    results = list(results)
    ranked = [r for r in results if r.on_leaderboard]
    rank = competition_ranks({r.athlete_id: float(r.points) for r in ranked})
    team_points: dict[int, float] = {}
    for r in ranked:
        team_points[r.team_id] = team_points.get(r.team_id, 0.0) + float(r.points)
    team_rank = competition_ranks(team_points)
    return [
        {
            "year": year,
            "athlete_id": r.athlete_id,
            "athlete_name": r.athlete_name,
            "team_id": r.team_id,
            "team_name": r.team_name,
            "points": float(r.points),
            "distance": float(r.distance),
            "moving_time": int(r.moving_time),
            "rides": int(r.rides),
            "days": int(r.days),
            "rank": rank.get(r.athlete_id),
            "team_rank": team_rank.get(r.team_id) if r.on_leaderboard else None,
        }
        for r in sorted(results, key=lambda r: r.athlete_id)
    ]


def season_year(conn: Connection) -> int:
    undated, latest = conn.execute(
        text("select sum(ride_date is null), max(ride_date) from daily_scores")
    ).one()
    # CONVERT_TZ gives null for a zone the server has no tables for.
    if undated:
        raise SystemExit(
            f"daily_scores has {undated} days with no date: load the server's "
            "time zone tables"
        )
    if latest is None:
        raise SystemExit("daily_scores is empty: there is no season here to archive")
    return latest.year


def write_sql(year: int, rows: list[dict], out: TextIO):
    table = AthleteSeason.__table__
    dialect = mysql.dialect()

    def literal(statement) -> str:
        return str(
            statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
        )

    out.write("begin;\n")
    out.write(literal(delete(table).where(table.c.year == year)) + ";\n")
    if rows:
        out.write(literal(insert(table).values(rows)) + ";\n")
    out.write("commit;\n")


def write_database(conn: Connection, year: int, rows: list[dict]):
    table = AthleteSeason.__table__
    conn.execute(delete(table).where(table.c.year == year))
    if rows:
        conn.execute(insert(table), rows)


def main(argv: list[str] | None = None, out: TextIO = sys.stdout):
    parser = argparse.ArgumentParser(
        description="Archive each athlete's season results into athlete_seasons."
    )
    parser.add_argument(
        "--source",
        default=config.SQLALCHEMY_URL,
        help="Database holding the season (default SQLALCHEMY_URL).",
        metavar="URL",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Season to file the results under (default: the year of the last ride).",
    )
    parser.add_argument(
        "--sql",
        action="store_true",
        help="Print SQL to load elsewhere instead of writing to the source.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    if not args.source:
        parser.error("no database: set SQLALCHEMY_URL or pass --source")

    engine = create_engine(args.source)
    with engine.begin() as conn:
        year = args.year or season_year(conn)
        rows = season_rows(year, conn.execute(_SEASON))
        log.info(
            "%d athletes in %d, %d of them ranked",
            len(rows),
            year,
            sum(r["rank"] is not None for r in rows),
        )
        if args.sql:
            write_sql(year, rows, out)
        else:
            write_database(conn, year, rows)


if __name__ == "__main__":
    main()
