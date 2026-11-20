"""Athlete clubs.

Revision ID: 75d6da077a30
Revises: 3f8b2d6c9e41
Create Date: 2026-11-20

The athlete sync fills it in for everyone already registered.
"""

import sqlalchemy as sa
from alembic import op

revision = "75d6da077a30"
down_revision = "3f8b2d6c9e41"


def upgrade():
    op.create_table(
        "athlete_clubs",
        sa.Column(
            "athlete_id",
            sa.BigInteger(),
            sa.ForeignKey("athletes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_athlete_clubs_team_id", "athlete_clubs", ["team_id"])


def downgrade():
    op.drop_table("athlete_clubs")
