"""Private rides are never due a photo fetch.

Revision ID: b7e2c04d1a93
Revises: 9a1c4e7b02d5
Create Date: 2026-09-19 19:30:00.000000

"""

# revision identifiers, used by Alembic.
revision = "b7e2c04d1a93"
down_revision = "9a1c4e7b02d5"

import sqlalchemy as sa
from alembic import op


def upgrade():
    # A ride's photos were scheduled without asking whether the ride was
    # private, and sync_photos passes private rides over, so every private ride
    # with photos has been waiting since the day it was recorded. Unset rather
    # than spent, so that a ride made public later is scheduled properly.
    op.execute(
        sa.text(
            "update rides set photos_fetched = null, photos_resync_date = null"
            " where private = true"
        )
    )


def downgrade():
    # The schedule these rides carried was never acted on, so there is nothing
    # to put back.
    pass
