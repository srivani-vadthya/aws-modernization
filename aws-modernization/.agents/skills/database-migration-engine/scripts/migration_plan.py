"""Full database migration pipeline — entry point for the database-migration-engine skill.

Runs all steps in sequence:
  1. db_detector      — detect source + target engine
  2. schema_extractor — extract tables from engagement
  3. type_mapper      — map source types to target types
  4. ddl_generator    — generate target DDL SQL
  5. orm_adapter      — generate ORM config files
  6. risk analysis    — flag shared kernels, lossy mappings, missing PKs

Reads from engagement.json. Writes migration-plan.json, schema.sql, orm-config/.

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_migration_model import make_plan, plan_markdown, validate, now
from db_detector import detect
from schema_extractor import extract
from type_mapper import map_schema
from ddl_generator import generate as generate_ddl
from orm_adapter import generate_orm


# ---------------------------------------------------------------------------
# Risk analyser
# ---------------------------------------------------------------------------

def _analyse_risks(tables: list[dict], shared_kernel_ids: set[str]) -> list[dict]:
    risks: list[dict] = []

    for table in tables:
        tname = table["name"]

        # Shared kernel risk
        if table.get("sharedKernel") or tname in shared_kernel_ids:
            table["sharedKernel"] = True
            risks.append({
                "title": f"Shared kernel table: {tname}",
                "severity": "critical",
                "description": (
                    f"Table '{tname}' is accessed by multiple capabilities. "
                    "A schema change will affect all consumers."
                ),
                "remediation": (
                    "Implement dual-write CDC pattern during cutover. "
                    "Assign a single owning service and expose read access via API."
                ),
                "table": tname,
            })

        # High-risk columns
        high_cols = [c for c in table.get("columns", []) if c.get("risk") in ("high", "critical")]
        for col in high_cols:
            risks.append({
                "title": f"High-risk type conversion: {tname}.{col['name']}",
                "severity": col["risk"],
                "description": (
                    f"{col['sourceType']} -> {col['targetType']}: {col.get('conversionNote', '')}"
                ),
                "remediation": "Validate data values before migration. Run parity checks post-migration.",
                "table": tname,
                "column": col["name"],
            })

        # Missing primary key
        pk_cols = [c for c in table.get("columns", []) if c.get("primaryKey")]
        if not pk_cols:
            risks.append({
                "title": f"No primary key: {tname}",
                "severity": "high",
                "description": f"Table '{tname}' has no primary key. PostgreSQL requires a PK for CDC replication.",
                "remediation": "Add a surrogate primary key (SERIAL or UUID) before migration.",
                "table": tname,
            })

    return risks


# ---------------------------------------------------------------------------
# Migration tool recommendation
# ---------------------------------------------------------------------------

def _recommend_tool(source_engine: str, target_engine: str) -> str:
    if source_engine in ("db2i", "db2zos"):
        return "AWS Database Migration Service (DMS) with CDC + Flyway for schema"
    if source_engine == "sqlserver" and "azure" in target_engine:
        return "Azure Database Migration Service (DMS) + EF Core migrations"
    if source_engine == "oracle":
        return "AWS DMS or ora2pg + Flyway"
    if source_engine == "mysql":
        return "pgloader or AWS DMS"
    if source_engine == "sqlite":
        return "pgloader (single command migration)"
    return "Flyway or Liquibase for schema + custom ETL for data"


# ---------------------------------------------------------------------------
# Phase builder
# ---------------------------------------------------------------------------

def _build_phases(source_engine: str, target_engine: str, table_count: int, risk_count: int) -> list[dict]:
    return [
        {
            "phase": 1,
            "name": "Schema Preparation",
            "description": "Review generated DDL, resolve HIGH/CRITICAL risk columns, add missing PKs.",
            "tool": "Manual review + db_migration_model.py validate",
            "risk": "low",
            "steps": [
                "Run: python migration_plan.py engagement.json --target " + target_engine,
                "Review schema.sql for HIGH/CRITICAL risk columns",
                "Add surrogate PKs to tables flagged with no primary key",
                "Confirm NUMERIC precision with business stakeholders for packed decimal fields",
            ],
        },
        {
            "phase": 2,
            "name": "Target Schema Deployment",
            "description": f"Deploy schema.sql to the {target_engine} instance.",
            "tool": "psql or Flyway",
            "risk": "low",
            "steps": [
                f"Create target database on {target_engine}",
                "Run: psql -h <host> -U <user> -d <db> -f schema.sql",
                "Verify all tables created: SELECT tablename FROM pg_tables WHERE schemaname='public'",
            ],
        },
        {
            "phase": 3,
            "name": "Data Migration",
            "description": f"Migrate data from {source_engine} to {target_engine} using the recommended tool.",
            "tool": _recommend_tool(source_engine, target_engine),
            "risk": "high" if risk_count > 3 else "medium",
            "steps": [
                f"Configure {_recommend_tool(source_engine, target_engine)}",
                "Run initial full-load migration",
                "Validate row counts per table",
                "Run parity checks on HIGH-risk columns (packed decimal, date fields)",
            ],
        },
        {
            "phase": 4,
            "name": "ORM & Application Cutover",
            "description": "Update application ORM configuration to point to the new database.",
            "tool": "orm-config/ generated files",
            "risk": "medium",
            "steps": [
                "Replace existing ORM provider with generated orm-config/ files",
                "Update connection string in appsettings.json / application.yml / database.py",
                "Run application integration tests against the new database",
                "Enable CDC dual-write for shared kernel tables",
            ],
        },
        {
            "phase": 5,
            "name": "Cutover & Validation",
            "description": "Switch production traffic to the new database. Validate parity.",
            "tool": "Bidirectional CDC Guardrail skill + differential-golden-run-comparator skill",
            "risk": "critical" if any(t for t in ["sharedKernel"] if risk_count > 0) else "high",
            "steps": [
                "Enable bidirectional CDC for zero-downtime cutover",
                "Run differential-golden-run-comparator skill for parity validation",
                "Shift 10% traffic canary to new database",
                "Monitor for 24h, then shift 100%",
                "Decommission source database after 30-day observation period",
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    engagement_path: str,
    target_engine: str,
    source_dir: str | None,
    language: str,
    framework: str,
    out_plan: str,
    out_ddl: str,
    out_orm: str,
    out_markdown: str | None,
) -> dict:
    with open(engagement_path, encoding="utf-8") as fh:
        engagement = json.load(fh)

    # Step 1 — detect
    detection = detect(engagement, source_dir)
    source_engine = detection["sourceEngine"]
    if target_engine == "auto":
        target_engine = detection["targetEngine"]

    print(f"[1/5] Detected source: {source_engine} (confidence: {detection['sourceConfidence']})")
    print(f"      Target: {target_engine}")

    # Step 2 — extract
    raw_tables = extract(engagement, source_dir)
    print(f"[2/5] Extracted {len(raw_tables)} table(s)")

    # Step 3 — map types
    mapped = map_schema({"tables": raw_tables}, source_engine)
    mapped["targetEngine"] = target_engine
    print(f"[3/5] Type mapping complete")

    # Step 4 — DDL
    ddl_sql = generate_ddl(mapped)
    Path(out_ddl).write_text(ddl_sql, encoding="utf-8")
    print(f"[4/5] DDL written -> {out_ddl}")

    # Step 5 — ORM
    orm_files = generate_orm(mapped, language, framework, target_engine)
    orm_dir = Path(out_orm)
    orm_dir.mkdir(parents=True, exist_ok=True)
    for fname, content in orm_files.items():
        (orm_dir / fname).write_text(content, encoding="utf-8")
    print(f"[5/5] ORM config written -> {out_orm}/ ({len(orm_files)} file(s))")

    # Risk analysis
    shared_kernel_ids: set[str] = {
        sk.get("nodeId", "").split(":")[-1].upper()
        for sk in (engagement.get("applied_graph") or {}).get("sharedKernels", [])
    }
    risks = _analyse_risks(mapped["tables"], shared_kernel_ids)

    # Build plan
    phases = _build_phases(source_engine, target_engine, len(mapped["tables"]), len(risks))
    plan = make_plan(
        source_engine=source_engine,
        target_engine=target_engine,
        tables=mapped["tables"],
        risks=risks,
        migration_tool=_recommend_tool(source_engine, target_engine),
        phases=phases,
    )
    plan["detection"] = detection
    plan["ormFiles"] = list(orm_files.keys())
    plan["ddlFile"] = out_ddl

    # Validate
    issues = validate(plan)
    errors = [m for lvl, m in issues if lvl == "ERROR"]
    warns  = [m for lvl, m in issues if lvl == "WARN"]
    plan["validation"] = {"errors": errors, "warnings": warns}

    # Write plan
    Path(out_plan).write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"\nMigration plan written -> {out_plan}")
    print(f"  Tables : {len(mapped['tables'])}")
    print(f"  Risks  : {len(risks)} ({sum(1 for r in risks if r['severity'] == 'critical')} critical)")
    print(f"  Errors : {len(errors)}")
    print(f"  Warnings: {len(warns)}")

    if out_markdown:
        md = plan_markdown(plan)
        Path(out_markdown).write_text(md, encoding="utf-8")
        print(f"  Markdown -> {out_markdown}")

    return plan


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("engagement", help="Path to engagement.json")
    ap.add_argument("--target", default="azure-postgresql",
                    help="Target DB engine (default: azure-postgresql). Use 'auto' to read from target_contract.")
    ap.add_argument("--source-dir", help="Path to engagement source folder (improves schema extraction)")
    ap.add_argument("--language", default="csharp", help="Target language for ORM: csharp, java, python")
    ap.add_argument("--framework", default="aspnetcore", help="Target framework: aspnetcore, spring-boot, fastapi")
    ap.add_argument("--out", default="migration-plan.json", help="Output plan file")
    ap.add_argument("--ddl", default="schema.sql", help="Output DDL file")
    ap.add_argument("--orm", default="orm-config", help="Output ORM directory")
    ap.add_argument("--markdown", help="Also write a human-readable markdown report")
    args = ap.parse_args(argv)

    try:
        run_pipeline(
            engagement_path=args.engagement,
            target_engine=args.target,
            source_dir=args.source_dir,
            language=args.language,
            framework=args.framework,
            out_plan=args.out,
            out_ddl=args.ddl,
            out_orm=args.orm,
            out_markdown=args.markdown,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
