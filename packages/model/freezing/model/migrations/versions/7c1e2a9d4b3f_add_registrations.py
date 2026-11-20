"""Add registrations.

Revision ID: 7c1e2a9d4b3f
Revises: 75d6da077a30
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from alembic import op

revision = "7c1e2a9d4b3f"
down_revision = "75d6da077a30"


def upgrade():
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
        sa.Column("previous_mileage", sa.String(255), nullable=True),
        sa.Column(
            "team_captain", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_registrations_email", "registrations", ["email"])


def downgrade():
    op.drop_index("ix_registrations_email", table_name="registrations")
    op.drop_table("registrations")
