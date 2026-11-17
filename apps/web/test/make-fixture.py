#!/usr/bin/env python3
r"""Build the anonymised database the spider runs against.

Run by hand against a copy of a real season, with an empty database of the
current schema alongside to say which columns still exist:

    python apps/web/test/make-fixture.py \\
        mysql://root@127.0.0.1/freezing \\
        mysql://root:test@127.0.0.1:13318/freezing \\
        apps/web/test/fixture.sql

Nothing identifying survives: names are invented, tokens are dropped, and a
GPS track is cut to its first few points, which is enough for the map to draw
something and not enough to say where anyone lives. Hashtags in ride names are
the one thing kept verbatim, because whole leaderboards are built on them.

Dates are left as they are. load-fixture.sh moves them, so that the fixture
does not go stale sitting in the repository.
"""

import datetime
import hashlib
import pathlib
import re
import sys
from urllib.parse import urlparse

import pymysql

#: How much of a season to keep.
WINDOW_DAYS = 60

#: Points kept from each GPS track, and readings from each stream beside it.
TRACK_POINTS = 10

#: Efforts are only worth keeping for segments a leaderboard asks about.
SEGMENT_SOURCE = "apps/web/leaderboards"


def connect(dsn):
    url = urlparse(dsn)
    return pymysql.connect(
        host=url.hostname or "127.0.0.1",
        port=url.port or 3306,
        user=url.username or "root",
        password=url.password or "",
        database=url.path.lstrip("/"),
    )


def rows(db, sql, *args):
    with db.cursor() as cur:
        cur.execute(sql, args or None)
        return [d[0] for d in cur.description], cur.fetchall()


def invented(seed, kind):
    """Invent a name: stable, meaningless, and plainly not a person."""
    n = int(hashlib.sha256(f"{kind}{seed}".encode()).hexdigest()[:8], 16)
    first = [
        "Ash",
        "Bay",
        "Cove",
        "Dell",
        "Elm",
        "Fen",
        "Glen",
        "Holt",
        "Ivy",
        "Kiln",
        "Larch",
        "Marsh",
    ][n % 12]
    last = ["Archer", "Barrow", "Chase", "Downs", "Ember", "Frost", "Gale", "Harrow"][
        (n // 12) % 8
    ]
    return f"{first} {last}"


def retitled(seed, original, kind):
    tags = " ".join(re.findall(r"#\w+", original or ""))
    n = int(hashlib.sha256(f"{kind}{seed}".encode()).hexdigest()[:4], 16)
    base = ["Morning ride", "Lunch ride", "Commute", "Evening spin", "Afternoon ride"][
        n % 5
    ]
    return f"{base} {tags}".strip()


def literal(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return "'" + str(v) + "'"
    if isinstance(v, (bytes, bytearray)):
        return "0x" + v.hex()
    if isinstance(v, str) and v.startswith("ST_GeomFromText("):
        return v  # already SQL, not a value
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def head(wkt, points=TRACK_POINTS):
    """Return the first few points of a LINESTRING, as SQL that rebuilds it."""
    if not wkt:
        return None
    inner = wkt[wkt.index("(") + 1 : wkt.rindex(")")]
    kept = [p.strip() for p in inner.split(",")][:points]
    if len(kept) < 2:  # MySQL will not hold a one-point line
        return None
    return "ST_GeomFromText('LINESTRING(" + ", ".join(kept) + ")')"


def clipped(stream, points=TRACK_POINTS):
    """Return the first few readings of an elevation or time stream."""
    if not stream:
        return stream
    parts = stream.strip().lstrip("[").rstrip("]").split(",")
    return "[" + ", ".join(p.strip() for p in parts[:points]) + "]"


def segments():
    """Segment ids a leaderboard asks about, and nothing else numeric."""
    ids = set()
    for path in sorted(pathlib.Path(SEGMENT_SOURCE).glob("*.yml")):
        for match in re.finditer(r"segment_id[^0-9\n]{0,20}(\d{5,})", path.read_text()):
            ids.add(int(match.group(1)))
        for match in re.finditer(r"segment/(\d{5,})", path.read_text()):
            ids.add(int(match.group(1)))
    return sorted(ids)


def main(source_dsn, target_dsn, out_path):  # noqa: C901
    src, target = connect(source_dsn), connect(target_dsn)
    with open(out_path, "w") as out:

        # A long-lived database keeps columns the model has dropped, and a
        # generated column cannot be written to at all.
        _, target_columns = rows(
            target,
            "select table_name, column_name from information_schema.columns"
            " where table_schema = database()"
            "   and coalesce(extra, '') not like '%GENERATED%'",
        )
        writable = {}
        for table, column in target_columns:
            writable.setdefault(table, set()).add(column)

        def dump(table, cols, values):
            allowed = writable.get(table, set(cols))
            keep = [i for i, c in enumerate(cols) if c in allowed]
            names = ",".join(f"`{cols[i]}`" for i in keep)
            kept = [tuple(r[i] for i in keep) for r in values]
            print(f"  {table:<14} {len(kept)}", file=sys.stderr)
            if not kept:
                return
            out.write(f"-- {table}\n")
            for i in range(0, len(kept), 500):
                batch = kept[i : i + 500]
                body = ",".join(
                    "(" + ",".join(literal(v) for v in r) + ")" for r in batch
                )
                out.write(f"insert into `{table}` ({names}) values {body};\n")

        # The busiest stretch of the season, not the last: a tail is nearly empty
        # and a fixture with no rides in it exercises nothing.
        _, [(busiest,)] = rows(
            src,
            "select competition_date from rides group by competition_date"
            " order by count(*) desc limit 1",
        )
        _, [(newest,)] = rows(
            src,
            "select max(start_date) from rides where competition_date <= %s",
            busiest + datetime.timedelta(days=WINDOW_DAYS // 2),
        )
        oldest = newest - datetime.timedelta(days=WINDOW_DAYS)
        print(f"{oldest:%Y-%m-%d} to {newest:%Y-%m-%d}", file=sys.stderr)

        out.write("set foreign_key_checks = 0;\n")

        cols, teams = rows(src, "select * from teams")
        dump(
            "teams",
            cols,
            [
                tuple(
                    (
                        invented(r[cols.index("id")], "team") + " Team"
                        if c == "name"
                        else v
                    )
                    for c, v in zip(cols, r)
                )
                for r in teams
            ],
        )

        cols, found = rows(
            src,
            "select * from rides where start_date between %s and %s and not private",
            oldest,
            newest,
        )
        ride_ids = tuple(r[cols.index("id")] for r in found)
        athlete_ids = tuple({r[cols.index("athlete_id")] for r in found})
        dump(
            "rides",
            cols,
            [
                tuple(
                    (
                        retitled(r[cols.index("id")], v, "ride")
                        if c == "name"
                        else None if c == "description" else v
                    )
                    for c, v in zip(cols, r)
                )
                for r in found
            ],
        )

        cols, athletes = rows(src, "select * from athletes where id in %s", athlete_ids)
        dump(
            "athletes",
            cols,
            [
                tuple(
                    (
                        None
                        if c in ("access_token", "refresh_token", "profile_photo")
                        else (
                            invented(r[cols.index("id")], "athlete")
                            if c in ("name", "display_name")
                            else v
                        )
                    )
                    for c, v in zip(cols, r)
                )
                for r in athletes
            ],
        )

        cols, geo = rows(
            src,
            "select ride_id, ST_AsText(start_geo), ST_AsText(end_geo)"
            " from ride_geo where ride_id in %s",
            ride_ids,
        )
        dump(
            "ride_geo",
            ["ride_id", "start_geo", "end_geo"],
            [
                (r[0], f"ST_GeomFromText('{r[1]}')", f"ST_GeomFromText('{r[2]}')")
                for r in geo
                if r[1] and r[2]
            ],
        )

        cols, tracks = rows(
            src,
            "select ride_id, ST_AsText(gps_track), elevation_stream, time_stream"
            " from ride_tracks where ride_id in %s",
            ride_ids,
        )
        trimmed = []
        for ride_id, wkt, elevation, times in tracks:
            line = head(wkt)
            if line is None:
                continue
            trimmed.append((ride_id, line, clipped(elevation), clipped(times)))
        dump(
            "ride_tracks",
            ["ride_id", "gps_track", "elevation_stream", "time_stream"],
            trimmed,
        )

        cols, photos = rows(
            src, "select * from ride_photos where ride_id in %s", ride_ids
        )
        dump(
            "ride_photos",
            cols,
            [
                tuple(
                    retitled(r[cols.index("id")], v, "caption") if c == "caption" else v
                    for c, v in zip(cols, r)
                )
                for r in photos
            ],
        )

        cols, weather = rows(
            src, "select * from ride_weather where ride_id in %s", ride_ids
        )
        dump("ride_weather", cols, weather)

        wanted = segments()
        cols, efforts = rows(
            src,
            "select * from ride_efforts where ride_id in %s and segment_id in %s",
            ride_ids,
            tuple(wanted),
        )
        print(f"  ({len(wanted)} segments named by leaderboards)", file=sys.stderr)
        dump("ride_efforts", cols, efforts)

        out.write("set foreign_key_checks = 1;\n")
        out.close()


if __name__ == "__main__":
    main(*sys.argv[1:4])
