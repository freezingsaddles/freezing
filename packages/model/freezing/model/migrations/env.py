from logging.config import fileConfig
from os import environ

from alembic import context
from sqlalchemy import create_engine, engine_from_config, pool

from freezing.model import meta, orm

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = orm.Base.metadata

# Tables in the database that other applications own.
FOREIGN_TABLES = {"freezebot_posts"}


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and name in FOREIGN_TABLES)


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        url = config.SQLALCHEMY_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    if meta.engine:
        # init_model's engine, when it brings the database up to date.
        connectable = meta.engine
    elif environ.get("SQLALCHEMY_URL"):
        connectable = create_engine(environ["SQLALCHEMY_URL"], poolclass=pool.NullPool)
    else:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
