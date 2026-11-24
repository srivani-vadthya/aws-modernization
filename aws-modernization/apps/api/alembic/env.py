"""Alembic environment configuration.

Reads the database URL from environment variables via app.db so credentials
are never hardcoded. Supports both offline (SQL script) and online (live DB) modes.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Make app package importable from alembic/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Import all models so Alembic can detect them
from app.models import Base  # noqa: F401 — registers all ORM models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# The database is shared with other schemas that have their own Alembic history,
# so use a dedicated version table and only manage tables defined in our models.
VERSION_TABLE = "alembic_version_nexus"


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and reflected and name not in target_metadata.tables:
        return False
    return True


def _db_url() -> str:
    host     = os.environ["PGHOST"]
    user     = os.environ["PGUSER"]
    password = os.environ["PGPASSWORD"]
    database = os.environ["PGDATABASE"]
    port     = os.getenv("PGPORT", "5432")
    sslmode  = os.getenv("PG_SSLMODE", "require")
    return (
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
        f"?sslmode={sslmode}"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        version_table=VERSION_TABLE,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _db_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
