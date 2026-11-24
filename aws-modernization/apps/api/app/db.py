"""PostgreSQL database connection — Azure Database for PostgreSQL Flexible Server.

Reads all connection config from environment variables (never hardcoded).
Provides:
  - SQLAlchemy engine with connection pooling
  - Session factory for dependency injection
  - Base for ORM models
  - health_check() for the /api/db/health endpoint
  - run_migrations() to apply Alembic migrations on startup
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — all values from environment, never hardcoded
# ---------------------------------------------------------------------------

def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(f"Required environment variable '{key}' is not set. Check your .env file.")
    return val


def _build_url() -> str:
    host     = _require("PGHOST")
    user     = _require("PGUSER")
    password = _require("PGPASSWORD")
    database = _require("PGDATABASE")
    port     = os.getenv("PGPORT", "5432")
    sslmode  = os.getenv("PG_SSLMODE", "require")
    return (
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
        f"?sslmode={sslmode}"
    )


# ---------------------------------------------------------------------------
# Engine — created once at import time
# ---------------------------------------------------------------------------

def _build_engine():
    url = _build_url()
    return create_engine(
        url,
        poolclass=QueuePool,
        pool_size=int(os.getenv("PG_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("PG_MAX_OVERFLOW", "20")),
        pool_timeout=int(os.getenv("PG_POOL_TIMEOUT", "30")),
        pool_pre_ping=True,          # drop stale connections automatically
        pool_recycle=1800,           # recycle connections every 30 min
        echo=os.getenv("PG_ECHO", "false").lower() == "true",
        connect_args={
            "connect_timeout": 10,
            "application_name": "nexus-modernize",
        },
    )


try:
    engine = _build_engine()
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    logger.info("PostgreSQL engine initialised: %s:%s/%s",
                os.getenv("PGHOST"), os.getenv("PGPORT"), os.getenv("PGDATABASE"))
except Exception as exc:
    engine = None          # type: ignore[assignment]
    SessionLocal = None    # type: ignore[assignment]
    logger.warning("PostgreSQL engine could not be initialised: %s", exc)


# ---------------------------------------------------------------------------
# ORM Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a session and closes it after the request."""
    if SessionLocal is None:
        raise RuntimeError("Database is not configured. Set PGHOST, PGUSER, PGPASSWORD, PGDATABASE.")
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context manager for use outside FastAPI (scripts, skills)."""
    if SessionLocal is None:
        raise RuntimeError("Database is not configured.")
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def health_check() -> dict:
    """Returns a health dict — safe to expose on /api/db/health."""
    if engine is None:
        return {
            "status": "unavailable",
            "error": "Engine not initialised — check PGHOST, PGUSER, PGPASSWORD, PGDATABASE in .env",
        }
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT version(), current_database(), current_user, "
                "pg_postmaster_start_time()::text AS started_at"
            )).mappings().one()
            pool = engine.pool
            return {
                "status": "healthy",
                "host": os.getenv("PGHOST"),
                "port": os.getenv("PGPORT", "5432"),
                "database": row["current_database"],
                "user": row["current_user"],
                "serverVersion": row["version"],
                "serverStartedAt": row["started_at"],
                "pool": {
                    "size": pool.size(),
                    "checkedIn": pool.checkedin(),
                    "checkedOut": pool.checkedout(),
                    "overflow": pool.overflow(),
                },
            }
    except Exception as exc:
        logger.error("DB health check failed: %s", exc)
        return {"status": "unhealthy", "error": str(exc)}


# ---------------------------------------------------------------------------
# Migrations — run Alembic programmatically on startup
# ---------------------------------------------------------------------------

def run_migrations() -> None:
    """Apply any pending Alembic migrations. Called once on app startup."""
    try:
        from alembic import command
        from alembic.config import Config
        from pathlib import Path

        alembic_cfg_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        if not alembic_cfg_path.exists():
            logger.info("No alembic.ini found — skipping migrations")
            return

        cfg = Config(str(alembic_cfg_path))
        cfg.set_main_option("sqlalchemy.url", _build_url())
        command.upgrade(cfg, "head")
        logger.info("Alembic migrations applied successfully")
    except Exception as exc:
        logger.warning("Alembic migration failed (non-fatal): %s", exc)
