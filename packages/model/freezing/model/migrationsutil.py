"""Various utility functions."""

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
