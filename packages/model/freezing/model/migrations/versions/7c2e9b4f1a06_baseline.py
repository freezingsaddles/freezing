"""Baseline: production's schema when the earlier migrations were squashed.

Revision ID: 7c2e9b4f1a06
Revises:
Create Date: 2026-11-19

Production was already at this revision, so it runs only on new databases.
"""

import sqlalchemy as sa
from alembic import op

from freezing.model.migrationsutil import baseline_statements

revision = "7c2e9b4f1a06"
down_revision = None


def upgrade():
    for _, _, statement in baseline_statements():
        op.execute(sa.text(statement))


def downgrade():
    for kind, name, _ in reversed(baseline_statements()):
        op.execute(sa.text(f"DROP {kind} `{name}`"))
