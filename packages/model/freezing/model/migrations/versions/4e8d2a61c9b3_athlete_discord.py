"""Athlete discord.

Revision ID: 4e8d2a61c9b3
Revises: c3f81be5d7a0
Create Date: 2026-09-23 12:00:00.000000

The Discord account an athlete linked through the site. The username is a copy
for people reading the table; the id is what identifies the account.

"""

# revision identifiers, used by Alembic.
revision = "4e8d2a61c9b3"
down_revision = "c3f81be5d7a0"

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.add_column("athletes", sa.Column("discord_user_id", sa.BigInteger))
    op.add_column("athletes", sa.Column("discord_username", sa.String(255)))
    op.create_unique_constraint(
        "athletes_discord_user_id", "athletes", ["discord_user_id"]
    )


def downgrade():
    op.drop_constraint("athletes_discord_user_id", "athletes", type_="unique")
    op.drop_column("athletes", "discord_username")
    op.drop_column("athletes", "discord_user_id")
