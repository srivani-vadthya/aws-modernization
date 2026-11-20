"""SQLAlchemy ORM models for the Nexus Modernize platform.

Tables:
  - engagements       — mirrors the engagement JSON (id, name, status, full JSON blob)
  - migration_plans   — stores generated DB migration plans per engagement
  - migration_runs_pg — stores migration run records (supplements file-based store)
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Engagements
# ---------------------------------------------------------------------------

class Engagement(Base):
    __tablename__ = "engagements"

    id          = Column(String(32),  primary_key=True)
    name        = Column(String(255), nullable=False)
    source_type = Column(String(50),  nullable=False, default="unknown")
    status      = Column(String(50),  nullable=False, default="intake")
    current_phase = Column(String(50), nullable=False, default="intake")
    domain      = Column(String(100), nullable=True)
    git_url     = Column(Text,        nullable=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at  = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    payload     = Column(JSONB,       nullable=False, default=dict)

    migration_plans = relationship("MigrationPlan", back_populates="engagement",
                                   cascade="all, delete-orphan")
    migration_runs  = relationship("MigrationRunPg", back_populates="engagement",
                                   cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Engagement id={self.id} name={self.name!r} status={self.status}>"


# ---------------------------------------------------------------------------
# Migration Plans
# ---------------------------------------------------------------------------

class MigrationPlan(Base):
    __tablename__ = "migration_plans"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    engagement_id   = Column(String(32), ForeignKey("engagements.id", ondelete="CASCADE"),
                             nullable=False, index=True)
    source_engine   = Column(String(50),  nullable=False)
    target_engine   = Column(String(50),  nullable=False)
    table_count     = Column(Integer,     nullable=False, default=0)
    risk_count      = Column(Integer,     nullable=False, default=0)
    critical_count  = Column(Integer,     nullable=False, default=0)
    ddl_sql         = Column(Text,        nullable=True)
    plan_json       = Column(JSONB,       nullable=False, default=dict)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)

    engagement = relationship("Engagement", back_populates="migration_plans")

    __table_args__ = (
        UniqueConstraint("engagement_id", "source_engine", "target_engine",
                         name="uq_migration_plan_eng_src_tgt"),
    )

    def __repr__(self) -> str:
        return (f"<MigrationPlan id={self.id} "
                f"{self.source_engine}->{self.target_engine} "
                f"tables={self.table_count}>")


# ---------------------------------------------------------------------------
# Migration Runs
# ---------------------------------------------------------------------------

class MigrationRunPg(Base):
    __tablename__ = "migration_runs_pg"

    id            = Column(String(32),  primary_key=True)
    engagement_id = Column(String(32),  ForeignKey("engagements.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    scope_id      = Column(String(100), nullable=True)
    status        = Column(String(50),  nullable=False, default="pending")
    target_engine = Column(String(50),  nullable=True)
    note          = Column(Text,        nullable=True)
    started_at    = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at  = Column(DateTime(timezone=True), nullable=True)
    run_json      = Column(JSONB,       nullable=False, default=dict)

    engagement = relationship("Engagement", back_populates="migration_runs")

    def __repr__(self) -> str:
        return f"<MigrationRunPg id={self.id} status={self.status}>"
