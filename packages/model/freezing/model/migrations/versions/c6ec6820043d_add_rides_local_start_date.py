import sqlalchemy as sa
from alembic import op

"""add rides local_start_date

Revision ID: c6ec6820043d
Revises: da4b6a7ba6d6
Create Date: 2026-09-19 09:12:03.556821

start_date still holds the rider's wall clock. This copies it into a column of
its own so that the questions that really do want local time -- the daylight
view, the weather lookup -- can say so, before start_date becomes the instant.

"""

# revision identifiers, used by Alembic.
revision = "c6ec6820043d"
down_revision = "da4b6a7ba6d6"


def upgrade():
    op.add_column("rides", sa.Column("local_start_date", sa.DateTime, nullable=True))
    op.create_index("ix_rides_local_start_date", "rides", ["local_start_date"])
    op.execute("update rides set local_start_date = start_date")


def downgrade():
    op.drop_index("ix_rides_local_start_date", table_name="rides")
    op.drop_column("rides", "local_start_date")
