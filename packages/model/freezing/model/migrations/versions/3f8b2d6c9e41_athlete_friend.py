"""Athlete friend.

Revision ID: 3f8b2d6c9e41
Revises: a454b1c73435
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op

revision = "3f8b2d6c9e41"
down_revision = "a454b1c73435"


def upgrade():
    op.add_column("athletes", sa.Column("friend", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("athletes", "friend")
