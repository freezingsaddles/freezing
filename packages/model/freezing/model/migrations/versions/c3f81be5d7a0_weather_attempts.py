"""Weather attempts.

Revision ID: c3f81be5d7a0
Revises: b7e2c04d1a93
Create Date: 2026-09-19 20:30:00.000000

"""

# revision identifiers, used by Alembic.
revision = "c3f81be5d7a0"
down_revision = "b7e2c04d1a93"

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.add_column(
        "rides",
        sa.Column("weather_attempts", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("rides", "weather_attempts")
