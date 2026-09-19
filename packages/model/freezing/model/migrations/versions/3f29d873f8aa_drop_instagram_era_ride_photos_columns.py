import sqlalchemy as sa
from alembic import op

"""drop instagram-era ride_photos columns

Revision ID: 3f29d873f8aa
Revises: d1119fc76e42
Create Date: 2026-09-18 13:04:31.788219

Strava stopped syndicating Instagram photos years ago. `source` told the two
apart (1 native, 2 Instagram) and `ref` held the Instagram permalink; stravalib
no longer sees `ref` come back at all. Nothing reads either column.

"""

# revision identifiers, used by Alembic.
revision = "3f29d873f8aa"
down_revision = "d1119fc76e42"


def upgrade():
    op.drop_column("ride_photos", "source")
    op.drop_column("ride_photos", "ref")


def downgrade():
    op.add_column(
        "ride_photos",
        sa.Column("source", sa.Integer, nullable=False, server_default="1"),
    )
    op.add_column("ride_photos", sa.Column("ref", sa.String(255), nullable=True))
