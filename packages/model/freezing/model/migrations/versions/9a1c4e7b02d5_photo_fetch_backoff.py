"""Photo fetch backoff.

Revision ID: 9a1c4e7b02d5
Revises: 536a0f435c79
Create Date: 2026-09-19 14:10:00.000000

"""

# revision identifiers, used by Alembic.
revision = "9a1c4e7b02d5"
down_revision = "536a0f435c79"

import sqlalchemy as sa
from alembic import op

# Keep in step with freezing.sync.data.photos.MAX_FETCHES.
MAX_FETCHES = 14


def upgrade():
    op.alter_column(
        "rides",
        "photos_fetched",
        existing_type=sa.Boolean,
        type_=sa.Integer,
        existing_nullable=True,
    )
    op.add_column("rides", sa.Column("photos_resync_date", sa.DateTime, nullable=True))
    op.create_index("ix_rides_photos_resync_date", "rides", ["photos_resync_date"])
    # The count records a budget spent, not fetches made: a ride already done
    # goes straight to the cap so that nothing looks at it again.
    op.execute(
        f"update rides set photos_fetched = {MAX_FETCHES} where photos_fetched = 1"
    )
    # A ride still waiting has been waiting since its own season, and its
    # captions are long settled, so it gets the last look of the backoff rather
    # than the first: the backlog drains once and then stops. Any past timestamp
    # makes it due; the epoch avoids guessing at the server's timezone.
    op.execute(
        f"update rides set photos_fetched = {MAX_FETCHES - 1},"
        " photos_resync_date = '1970-01-01' where photos_fetched = 0"
    )


def downgrade():
    op.drop_index("ix_rides_photos_resync_date", "rides")
    op.drop_column("rides", "photos_resync_date")
    op.execute("update rides set photos_fetched = 1 where photos_fetched > 0")
    op.alter_column(
        "rides",
        "photos_fetched",
        existing_type=sa.Integer,
        type_=sa.Boolean,
        existing_nullable=True,
    )
