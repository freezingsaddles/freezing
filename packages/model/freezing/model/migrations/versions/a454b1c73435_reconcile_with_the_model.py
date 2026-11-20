"""Reconcile production's schema with the model.

Revision ID: a454b1c73435
Revises: 7c2e9b4f1a06
Create Date: 2026-11-19

Strava's ids are 64-bit; every ride table cascades from rides as ride_tracks
already did; the views and the trainer column nothing reads go.
"""

import sqlalchemy as sa
from alembic import op

from freezing.model.migrationsutil import baseline_statements

revision = "a454b1c73435"
down_revision = "7c2e9b4f1a06"

UNUSED_VIEWS = {
    "daily_scores_elevation",
    "generator_16",
    "generator_256",
    "ride_start_end",
    "team_daily_scores",
    "v_athlete_dist_freq",
    "v_athlete_dist_minmax",
    "v_athlete_dist_totalfreq",
    "v_athlete_dist_totalfreq_filled",
    "v_athlete_enumber",
    "v_athlete_enumber_candidates",
    "v_daily_dist_totals",
}

# The foreign keys on the ids that widen, with how production had them:
# (name, table, column, referent, on delete, on update).
ID_KEYS = [
    ("athletes_ibfk_1", "athletes", "team_id", "teams", "SET NULL", "RESTRICT"),
    ("rides_ibfk_1", "rides", "athlete_id", "athletes", "CASCADE", "RESTRICT"),
    ("ride_errors_ibfk_1", "ride_errors", "athlete_id", "athletes", "CASCADE", None),
    ("tribes_ibfk_1", "tribes", "athlete_id", "athletes", "CASCADE", "RESTRICT"),
]

# The ids and the columns that refer to them: (table, column, nullable).
ID_COLUMNS = [
    ("teams", "id", False),
    ("athletes", "id", False),
    ("athletes", "team_id", True),
    ("rides", "athlete_id", False),
    ("ride_errors", "athlete_id", False),
    ("tribes", "athlete_id", False),
    ("athletes", "expires_at", False),
]

# Every ride table's foreign key on rides. Only ride_tracks had one, with
# ON UPDATE RESTRICT spelled out.
RIDE_KEYS = [
    ("ride_tracks_ibfk_1", "ride_tracks"),
    ("ride_efforts_ibfk_1", "ride_efforts"),
    ("ride_geo_ibfk_1", "ride_geo"),
    ("ride_photos_ibfk_1", "ride_photos"),
    ("ride_weather_ibfk_1", "ride_weather"),
]


def unused_views() -> list[tuple[str, str]]:
    """Return the unused views' names and definitions, each after the views it uses."""
    return [
        (name, statement)
        for kind, name, statement in baseline_statements()
        if kind == "VIEW" and name in UNUSED_VIEWS
    ]


def has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def has_key(table: str, name: str) -> bool:
    keys = sa.inspect(op.get_bind()).get_foreign_keys(table)
    return name in {k["name"] for k in keys}


# MySQL cannot roll DDL back, so a run that stops part way leaves its work
# done; each step checks for that, and running it again finishes the job.
def upgrade():
    for name, _ in reversed(unused_views()):
        op.execute(sa.text(f"DROP VIEW IF EXISTS `{name}`"))
    if has_column("rides", "trainer"):
        op.drop_column("rides", "trainer")

    for name, table, *_ in ID_KEYS:
        if has_key(table, name):
            op.drop_constraint(name, table, type_="foreignkey")
    for table, column, nullable in ID_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.BigInteger(),
            existing_type=sa.Integer(),
            existing_nullable=nullable,
        )
    for name, table, column, referent, ondelete, _ in ID_KEYS:
        op.create_foreign_key(
            name, table, referent, [column], ["id"], ondelete=ondelete
        )

    if has_key("ride_tracks", "ride_tracks_ibfk_1"):
        op.drop_constraint("ride_tracks_ibfk_1", "ride_tracks", type_="foreignkey")
    for name, table in RIDE_KEYS:
        if has_key(table, name):
            continue
        op.execute(sa.text(f"""
            DELETE t FROM `{table}` t LEFT JOIN rides r ON r.id = t.ride_id
            WHERE t.ride_id IS NOT NULL AND r.id IS NULL
        """))
        op.create_foreign_key(
            name, table, "rides", ["ride_id"], ["id"], ondelete="CASCADE"
        )


def downgrade():
    for name, table in RIDE_KEYS:
        op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(
        "ride_tracks_ibfk_1",
        "ride_tracks",
        "rides",
        ["ride_id"],
        ["id"],
        ondelete="CASCADE",
        onupdate="RESTRICT",
    )

    for name, table, *_ in ID_KEYS:
        op.drop_constraint(name, table, type_="foreignkey")
    for table, column, nullable in ID_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.Integer(),
            existing_type=sa.BigInteger(),
            existing_nullable=nullable,
        )
    for name, table, column, referent, ondelete, onupdate in ID_KEYS:
        op.create_foreign_key(
            name,
            table,
            referent,
            [column],
            ["id"],
            ondelete=ondelete,
            onupdate=onupdate,
        )

    op.add_column("rides", sa.Column("trainer", sa.Boolean(), nullable=True))
    for _, statement in unused_views():
        op.execute(sa.text(statement))
