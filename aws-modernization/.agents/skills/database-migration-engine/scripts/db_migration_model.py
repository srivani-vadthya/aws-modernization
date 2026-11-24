"""Shared schema, validators, and output renderers for the database-migration-engine.

Standard library only.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Iterator

SCHEMA_VERSION = "1.0"

SUPPORTED_SOURCES = {
    "db2i", "db2zos", "sqlserver", "oracle", "mysql", "sqlite", "postgresql", "unknown"
}
SUPPORTED_TARGETS = {
    "azure-postgresql", "aurora-postgresql", "alloydb", "supabase", "postgresql"
}
RISK_LEVELS = ("low", "medium", "high", "critical")
COLUMN_REQUIRED = ("name", "sourceType", "targetType", "nullable")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(text)).strip("_").lower() or "unknown"


# ---------------------------------------------------------------------------
# Schema shapes
# ---------------------------------------------------------------------------

def make_column(
    name: str,
    source_type: str,
    target_type: str,
    nullable: bool = True,
    primary_key: bool = False,
    unique: bool = False,
    default: str | None = None,
    conversion_note: str = "",
    risk: str = "low",
) -> dict:
    return {
        "name": name,
        "sourceType": source_type,
        "targetType": target_type,
        "nullable": nullable,
        "primaryKey": primary_key,
        "unique": unique,
        "default": default,
        "conversionNote": conversion_note,
        "risk": risk,
    }


def make_table(
    name: str,
    source_name: str,
    columns: list[dict],
    indexes: list[dict] | None = None,
    foreign_keys: list[dict] | None = None,
    capability: str = "",
    shared_kernel: bool = False,
    evidence: str = "",
) -> dict:
    return {
        "name": name,
        "sourceName": source_name,
        "columns": columns,
        "indexes": indexes or [],
        "foreignKeys": foreign_keys or [],
        "capability": capability,
        "sharedKernel": shared_kernel,
        "evidence": evidence,
    }


def make_plan(
    source_engine: str,
    target_engine: str,
    tables: list[dict],
    risks: list[dict],
    migration_tool: str,
    phases: list[dict],
) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now(),
        "sourceEngine": source_engine,
        "targetEngine": target_engine,
        "tableCount": len(tables),
        "tables": tables,
        "risks": risks,
        "migrationTool": migration_tool,
        "phases": phases,
    }


# ---------------------------------------------------------------------------
# Iterators
# ---------------------------------------------------------------------------

def iter_columns(plan: dict) -> Iterator[tuple[dict, dict]]:
    for table in plan.get("tables", []):
        for col in table.get("columns", []):
            yield table, col


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(plan: dict) -> list[tuple[str, str]]:
    """Returns [(level, message)]. Empty list = clean."""
    out: list[tuple[str, str]] = []

    if plan.get("sourceEngine") not in SUPPORTED_SOURCES:
        out.append(("ERROR", f"sourceEngine '{plan.get('sourceEngine')}' not in {SUPPORTED_SOURCES}"))
    if plan.get("targetEngine") not in SUPPORTED_TARGETS:
        out.append(("ERROR", f"targetEngine '{plan.get('targetEngine')}' not in {SUPPORTED_TARGETS}"))
    if not plan.get("tables"):
        out.append(("WARN", "No tables found in migration plan"))

    seen_tables: set[str] = set()
    for table in plan.get("tables", []):
        tname = table.get("name", "")
        if not tname:
            out.append(("ERROR", "Table with no name"))
            continue
        if tname in seen_tables:
            out.append(("ERROR", f"Duplicate table name: {tname}"))
        seen_tables.add(tname)
        if not table.get("columns"):
            out.append(("WARN", f"Table '{tname}' has no columns"))
        pk_cols = [c for c in table.get("columns", []) if c.get("primaryKey")]
        if not pk_cols:
            out.append(("WARN", f"Table '{tname}' has no primary key column"))
        for col in table.get("columns", []):
            for req in COLUMN_REQUIRED:
                if req not in col:
                    out.append(("ERROR", f"Table '{tname}' column missing field '{req}'"))
            if col.get("risk") not in RISK_LEVELS:
                out.append(("WARN", f"Table '{tname}'.{col.get('name')}: unknown risk '{col.get('risk')}'"))

    for risk in plan.get("risks", []):
        if not risk.get("description"):
            out.append(("WARN", "Risk entry with no description"))

    return out


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def plan_markdown(plan: dict) -> str:
    lines = [
        "# Database Migration Plan",
        f"**Source:** {plan.get('sourceEngine')}  ",
        f"**Target:** {plan.get('targetEngine')}  ",
        f"**Generated:** {plan.get('generatedAt')}  ",
        f"**Tables:** {plan.get('tableCount')}  ",
        "",
        "## Migration Phases",
        "",
    ]
    for phase in plan.get("phases", []):
        lines += [
            f"### Phase {phase.get('phase')}: {phase.get('name')}",
            f"{phase.get('description', '')}",
            "",
            f"- **Tool:** {phase.get('tool', 'N/A')}",
            f"- **Risk:** {phase.get('risk', 'N/A')}",
            "",
        ]
        if phase.get("steps"):
            lines.append("**Steps:**")
            for step in phase["steps"]:
                lines.append(f"- {step}")
            lines.append("")

    lines += ["## Tables", ""]
    for table in plan.get("tables", []):
        shared = " ⚠️ shared kernel" if table.get("sharedKernel") else ""
        lines += [
            f"### `{table.get('name')}`{shared}",
            f"Source: `{table.get('sourceName')}`  ",
            f"Capability: `{table.get('capability') or 'unassigned'}`  ",
            "",
            "| Column | Source Type | Target Type | PK | Nullable | Risk | Note |",
            "|--------|-------------|-------------|-----|----------|------|------|",
        ]
        for col in table.get("columns", []):
            pk = "✓" if col.get("primaryKey") else ""
            nullable = "✓" if col.get("nullable") else ""
            lines.append(
                f"| `{col.get('name')}` | `{col.get('sourceType')}` | `{col.get('targetType')}` "
                f"| {pk} | {nullable} | {col.get('risk')} | {col.get('conversionNote', '')} |"
            )
        lines.append("")

    if plan.get("risks"):
        lines += ["## Risks", ""]
        for risk in plan.get("risks", []):
            lines += [
                f"### [{risk.get('severity', 'medium').upper()}] {risk.get('title', '')}",
                risk.get("description", ""),
                f"**Remediation:** {risk.get('remediation', 'N/A')}",
                "",
            ]

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# CLI — validate a plan file
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Validate a migration-plan.json file")
    ap.add_argument("plan", help="Path to migration-plan.json")
    args = ap.parse_args()

    with open(args.plan, encoding="utf-8") as fh:
        data = json.load(fh)

    issues = validate(data)
    if not issues:
        print("Migration plan is valid")
        sys.exit(0)

    errors = [m for lvl, m in issues if lvl == "ERROR"]
    warns  = [m for lvl, m in issues if lvl == "WARN"]
    for m in errors:
        print(f"ERROR  {m}")
    for m in warns:
        print(f"WARN   {m}")
    print(f"\n{len(errors)} error(s), {len(warns)} warning(s)")
    sys.exit(1 if errors else 0)
