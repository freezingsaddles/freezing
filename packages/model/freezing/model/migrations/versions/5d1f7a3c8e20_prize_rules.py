"""Prize rules.

Revision ID: 5d1f7a3c8e20
Revises: 4e8d2a61c9b3
Create Date: 2026-11-06 12:00:00.000000

The rules of a sponsored pointless prize, written by its sponsor or the cabal.

"""

# revision identifiers, used by Alembic.
revision = "5d1f7a3c8e20"
down_revision = "4e8d2a61c9b3"

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.create_table(
        "prize_rules",
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("name", sa.String(191), primary_key=True),
        sa.Column("rules", sa.Text, nullable=False),
        sa.Column("updated_by", sa.BigInteger),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("prize_rules")
