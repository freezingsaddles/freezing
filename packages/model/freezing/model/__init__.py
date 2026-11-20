import warnings

import sqlalchemy as sa
from alembic import command
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from freezing.model import meta, migrationsutil
from freezing.model.autolog import log
from freezing.model.config import config
from freezing.model.monkeypatch import collections


def init_db():
    init_model(config.SQLALCHEMY_URL)


def init_model(sqlalchemy_url: str, check_version: bool = True):
    """
    Initialize the tables and classes of the model using configured engine.

    :param sqlalchemy_url: The database URI.
    :param check_version: Whether to ensure that the database version is up-to-date.
    """
    # Monkeypatch Collections to get old alembic version to work
    collections()
    engine = create_engine(
        sqlalchemy_url, pool_recycle=3600
    )  # pool_recycle is for mysql

    sm = sessionmaker(autoflush=True, autocommit=False, bind=engine)
    meta.engine = engine
    meta.scoped_session = scoped_session(sm)

    alembic_cfg = migrationsutil.create_config(sqlalchemy_url=sqlalchemy_url)

    alembic_script = ScriptDirectory.from_config(alembic_cfg)

    # The apps and their workers all start at once, and MySQL cannot roll DDL
    # back, so they migrate one at a time; the rest find it done.
    with engine.connect() as lock:
        lock.execute(sa.text("SELECT GET_LOCK('freezing-migrations', -1)"))
        try:
            _migrate(engine, alembic_cfg, alembic_script, check_version)
        finally:
            lock.execute(sa.text("SELECT RELEASE_LOCK('freezing-migrations')"))


def _migrate(engine, alembic_cfg, alembic_script, check_version):
    if not sa.inspect(engine).get_table_names():
        log.info("Database is empty, creating it")
        command.upgrade(alembic_cfg, "head")
    elif check_version:
        latest = alembic_script.get_current_head()
        installed = migrationsutil.get_database_version()
        try:
            alembic_script.get_revisions(installed)
        except CommandError:
            warnings.warn(
                "Unknown db revision {} installed, ignoring db upgrade.".format(
                    installed
                ),
                stacklevel=2,
            )
        else:
            if latest != installed:
                log.info(
                    "Installed database ({}) does not match latest available ({}). (UPGRADING)".format(
                        installed, latest
                    ),
                    UserWarning,
                )
                command.upgrade(alembic_cfg, "head")
    else:
        log.info("Skipping database upgrade.")
