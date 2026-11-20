"""PostgreSQL-backed persistence layer for engagements and migration plans.

Works alongside the existing file-based store (store.py) — both are kept in
sync so the platform degrades gracefully if the DB is unavailable.

Pattern:
  - write: file store first (source of truth), then DB (async-safe upsert)
  - read:  file store first; fall back to DB if file is missing
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import db_session, health_check as db_health_check
from .models import Engagement, MigrationPlan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engagement persistence
# ---------------------------------------------------------------------------

def upsert_engagement(eng: dict[str, Any]) -> None:
    """Write or update an engagement record in PostgreSQL. Non-fatal on error."""
    try:
        with db_session() as db:
            stmt = pg_insert(Engagement).values(
                id=eng["id"],
                name=eng.get("name", ""),
                source_type=eng.get("sourceType", "unknown"),
                status=eng.get("status", "intake"),
                current_phase=eng.get("currentPhase", "intake"),
                domain=eng.get("domain"),
                git_url=eng.get("gitUrl"),
                created_at=_parse_dt(eng.get("createdAt")),
                updated_at=_parse_dt(eng.get("updatedAt")) or datetime.now(timezone.utc),
                payload=eng,
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name":          pg_insert(Engagement).excluded.name,
                    "source_type":   pg_insert(Engagement).excluded.source_type,
                    "status":        pg_insert(Engagement).excluded.status,
                    "current_phase": pg_insert(Engagement).excluded.current_phase,
                    "domain":        pg_insert(Engagement).excluded.domain,
                    "updated_at":    pg_insert(Engagement).excluded.updated_at,
                    "payload":       pg_insert(Engagement).excluded.payload,
                },
            )
            db.execute(stmt)
    except Exception as exc:
        logger.warning("upsert_engagement failed (non-fatal): %s", exc)


def load_engagement_from_db(eid: str) -> dict[str, Any] | None:
    """Load an engagement from PostgreSQL by id. Returns None if not found."""
    try:
        with db_session() as db:
            row = db.execute(
                select(Engagement).where(Engagement.id == eid)
            ).scalar_one_or_none()
            return row.payload if row else None
    except Exception as exc:
        logger.warning("load_engagement_from_db failed: %s", exc)
        return None


def list_engagements_from_db() -> list[dict[str, Any]]:
    """List all engagements from PostgreSQL ordered by updated_at desc."""
    try:
        with db_session() as db:
            rows = db.execute(
                select(Engagement).order_by(Engagement.updated_at.desc())
            ).scalars().all()
            return [
                {
                    "id":           r.id,
                    "name":         r.name,
                    "sourceType":   r.source_type,
                    "status":       r.status,
                    "currentPhase": r.current_phase,
                    "domain":       r.domain,
                    "updatedAt":    r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("list_engagements_from_db failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Migration plan persistence
# ---------------------------------------------------------------------------

def upsert_migration_plan(engagement_id: str, plan: dict[str, Any], ddl_sql: str = "") -> None:
    """Store a generated migration plan in PostgreSQL. Non-fatal on error."""
    try:
        risks = plan.get("risks", [])
        with db_session() as db:
            stmt = pg_insert(MigrationPlan).values(
                engagement_id=engagement_id,
                source_engine=plan.get("sourceEngine", "unknown"),
                target_engine=plan.get("targetEngine", "unknown"),
                table_count=plan.get("tableCount", 0),
                risk_count=len(risks),
                critical_count=sum(1 for r in risks if r.get("severity") == "critical"),
                ddl_sql=ddl_sql,
                plan_json=plan,
            ).on_conflict_do_update(
                constraint="uq_migration_plan_eng_src_tgt",
                set_={
                    "table_count":    pg_insert(MigrationPlan).excluded.table_count,
                    "risk_count":     pg_insert(MigrationPlan).excluded.risk_count,
                    "critical_count": pg_insert(MigrationPlan).excluded.critical_count,
                    "ddl_sql":        pg_insert(MigrationPlan).excluded.ddl_sql,
                    "plan_json":      pg_insert(MigrationPlan).excluded.plan_json,
                },
            )
            db.execute(stmt)
    except Exception as exc:
        logger.warning("upsert_migration_plan failed (non-fatal): %s", exc)


def load_migration_plan_from_db(engagement_id: str) -> dict[str, Any] | None:
    """Load the latest migration plan for an engagement from PostgreSQL."""
    try:
        with db_session() as db:
            row = db.execute(
                select(MigrationPlan)
                .where(MigrationPlan.engagement_id == engagement_id)
                .order_by(MigrationPlan.created_at.desc())
            ).scalar_one_or_none()
            return row.plan_json if row else None
    except Exception as exc:
        logger.warning("load_migration_plan_from_db failed: %s", exc)
        return None


def load_migration_plan_ddl(engagement_id: str) -> str | None:
    """Load the DDL SQL for the latest migration plan."""
    try:
        with db_session() as db:
            row = db.execute(
                select(MigrationPlan)
                .where(MigrationPlan.engagement_id == engagement_id)
                .order_by(MigrationPlan.created_at.desc())
            ).scalar_one_or_none()
            return row.ddl_sql if row else None
    except Exception as exc:
        logger.warning("load_migration_plan_ddl failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def db_status() -> dict:
    """Expose DB health for the /api/db/health endpoint."""
    return db_health_check()
