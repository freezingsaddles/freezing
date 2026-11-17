"""Athlete seasons.

Revision ID: 7c2e9b4f1a06
Revises: 5d1f7a3c8e20
Create Date: 2026-11-08 12:00:00.000000

Each athlete's results from a finished season, kept through the yearly wipe.

"""

# revision identifiers, used by Alembic.
revision = "7c2e9b4f1a06"
down_revision = "5d1f7a3c8e20"

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.create_table(
        "athlete_seasons",
        sa.Column("year", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("athlete_id", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("athlete_name", sa.String(255), nullable=False),
        sa.Column("team_id", sa.BigInteger),
        sa.Column("team_name", sa.String(1000)),
        sa.Column("points", sa.Double, nullable=False),
        sa.Column("distance", sa.Double, nullable=False),
        sa.Column("moving_time", sa.Integer, nullable=False),
        sa.Column("rides", sa.Integer, nullable=False),
        sa.Column("days", sa.Integer, nullable=False),
        sa.Column("rank", sa.Integer),
        sa.Column("team_rank", sa.Integer),
    )


def downgrade():
    op.drop_table("athlete_seasons")
