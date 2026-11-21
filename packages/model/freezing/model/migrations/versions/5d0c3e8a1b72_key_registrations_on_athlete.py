"""Key registrations on the athlete.

Revision ID: 5d0c3e8a1b72
Revises: 7c1e2a9d4b3f
Create Date: 2026-11-21

One row per athlete, their latest submission; WordPress keeps the history. The
receiver has never written to the table, so it is rebuilt rather than converted.
"""

import sqlalchemy as sa
from alembic import op

revision = "5d0c3e8a1b72"
down_revision = "7c1e2a9d4b3f"


def require_empty():
    rows = op.get_bind().execute(sa.text("select count(*) from registrations")).scalar()
    if rows:
        raise RuntimeError(f"registrations has {rows} rows; convert them by hand")


def upgrade():
    require_empty()
    op.drop_table("registrations")
    op.create_table(
        "registrations",
        sa.Column(
            "athlete_id",
            sa.BigInteger(),
            sa.ForeignKey("athletes.id", ondelete="CASCADE"),
            primary_key=True,
            autoincrement=False,
        ),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.Column("first_name", sa.String(255), nullable=False),
        sa.Column("last_name", sa.String(255), nullable=False),
        sa.Column("zip_code", sa.String(32), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column(
            "team_captain", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_registrations_email", "registrations", ["email"])


def downgrade():
    require_empty()
    op.drop_table("registrations")
    op.create_table(
        "registrations",
        sa.Column("message_id", sa.String(255), primary_key=True),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.Column("first_name", sa.String(255), nullable=False),
        sa.Column("last_name", sa.String(255), nullable=False),
        sa.Column("zip_code", sa.String(32), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("strava_id", sa.String(64), nullable=True),
        sa.Column(
            "athlete_id",
            sa.BigInteger(),
            sa.ForeignKey("athletes.id", ondelete="set null"),
            nullable=True,
        ),
        sa.Column(
            "team_captain", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_registrations_email", "registrations", ["email"])
