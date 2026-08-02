import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
import mithra_api.models  # noqa: F401 - registers tables on Base.metadata
from mithra_api.db import Base

# The database comes from the environment, like it does for every other process
# in the system. The URL in alembic.ini is a fallback for a bare `alembic`
# invocation on a developer's machine; hardcoding it there meant migrations
# only ever ran against one laptop's Postgres, and in a container they aimed at
# a host that does not exist.
_url = os.environ.get("DATABASE_URL")
if _url:
    config.set_main_option("sqlalchemy.url", _url)

target_metadata = Base.metadata

# PostGIS installs its own tables (spatial_ref_sys, the tiger geocoder set,
# topology). Autogenerate sees them as tables missing from our metadata and
# proposes dropping them, which would break the extension. Only ever consider
# tables we actually declare.
_OUR_TABLES = set(Base.metadata.tables)
_POSTGIS_SCHEMAS = {"tiger", "tiger_data", "topology"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        if getattr(obj, "schema", None) in _POSTGIS_SCHEMAS:
            return False
        return name in _OUR_TABLES
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
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
