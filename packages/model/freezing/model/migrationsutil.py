"""Various utility functions."""

import re
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext

from freezing.model import meta


def create_config(sqlalchemy_url: str) -> Config:
    """
    Create the Alembic Config object based on the application configuration.

    :rtype: :class:`alembic.config.Config`
    """
    alembic_repository = "freezing.model:migrations"

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", alembic_repository)
    alembic_cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)

    return alembic_cfg


def get_database_version() -> str | None:
    """Get the current database revision (partial GUID), None if unversioned."""
    if meta.engine is None:
        raise RuntimeError("The database engine is not initialised; call init_model()")
    context = MigrationContext.configure(meta.engine.connect())
    return context.get_current_revision()


BASELINE = Path(__file__).parent / "migrations" / "baseline.sql"


def baseline_statements() -> list[tuple[str, str, str]]:
    """
    Return the baseline's statements as (kind, name, statement); kind is TABLE or VIEW.

    They come in order, everything after what it uses.
    """
    out = []
    for statement in BASELINE.read_text().split(";\n\n"):
        if statement.strip():
            match = re.search(r"^CREATE (TABLE|VIEW) `(\w+)`", statement, re.MULTILINE)
            if not match:
                raise ValueError(f"Not a CREATE statement: {statement[:80]!r}")
            out.append(
                (match.group(1), match.group(2), statement.strip().removesuffix(";"))
            )
    return out
