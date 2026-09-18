import sqlalchemy as sa
from alembic import op

"""add athlete registered

Revision ID: da4b6a7ba6d6
Revises: 3f29d873f8aa
Create Date: 2026-09-18 16:20:44.981112

Set when an athlete reaches the end of the /register walkthrough. Nullable, so
everyone who registered before it existed reads as null rather than false.

"""

# revision identifiers, used by Alembic.
revision = "da4b6a7ba6d6"
down_revision = "3f29d873f8aa"


def upgrade():
    op.add_column("athletes", sa.Column("registered", sa.Boolean, nullable=True))


def downgrade():
    op.drop_column("athletes", "registered")
