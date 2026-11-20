"""Generate target DDL SQL from a mapped schema (output of type_mapper.py).

Produces PostgreSQL-compatible CREATE TABLE statements, primary key constraints,
unique indexes, and foreign key stubs. Works for all supported target engines
(azure-postgresql, aurora-postgresql, alloydb, supabase, postgresql).

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_migration_model import now


_HEADER = """\
-- =============================================================================
-- Database Migration Engine — Generated DDL
-- Source  : {source_engine}
-- Target  : {target_engine}
-- Generated: {generated_at}
-- Tables  : {table_count}
--
-- Review all HIGH / CRITICAL risk columns before executing.
-- Run inside a transaction and test on a non-production instance first.
-- =============================================================================

"""

_TABLE_HEADER = "-- Table: {name}{shared}\n"
_TABLE_FOOTER = "\n"


def _ident(name: str) -> str:
    """Normalise a table/column name into a safe lower-case PostgreSQL identifier."""
    return name.lower().replace(".", "_").replace("-", "_").replace(" ", "_")


def _col_ddl(col: dict) -> tuple[str, str]:
    """Return (sql, comment). The comment is appended AFTER the separating comma."""
    parts = [f'    "{_ident(col["name"])}"', col["targetType"]]
    if col.get("primaryKey"):
        parts.append("NOT NULL")
    elif not col.get("nullable", True):
        parts.append("NOT NULL")
    if col.get("default") is not None:
        parts.append(f"DEFAULT {col['default']}")
    if col.get("unique") and not col.get("primaryKey"):
        parts.append("UNIQUE")
    notes = []
    if col.get("conversionNote"):
        notes.append(" ".join(str(col["conversionNote"]).split()))
    if col.get("risk") in ("high", "critical"):
        notes.append(f"WARNING {col['risk'].upper()} RISK")
    return " ".join(parts), " | ".join(notes)


def _table_ddl(table: dict) -> str:
    name = _ident(table["name"])
    shared_note = "  -- WARNING shared kernel: dual-write CDC required" if table.get("sharedKernel") else ""
    lines = [_TABLE_HEADER.format(name=name, shared=shared_note)]
    lines.append(f'CREATE TABLE IF NOT EXISTS "{name}" (')

    items: list[tuple[str, str]] = [_col_ddl(col) for col in table.get("columns", [])]

    pk_cols = [f'"{_ident(c["name"])}"' for c in table.get("columns", []) if c.get("primaryKey")]
    if pk_cols:
        items.append((f"    PRIMARY KEY ({', '.join(pk_cols)})", ""))

    for fk in table.get("foreignKeys", []):
        ref_table = _ident(fk.get("referencedTable", ""))
        ref_col = _ident(fk.get("referencedColumn", "id"))
        src_col = _ident(fk.get("column", ""))
        if ref_table and src_col:
            items.append(
                (f'    FOREIGN KEY ("{src_col}") REFERENCES "{ref_table}" ("{ref_col}")', "")
            )

    # Commas go before any trailing comment so the SQL stays valid.
    body = []
    for i, (sql, note) in enumerate(items):
        line = sql + ("," if i < len(items) - 1 else "")
        if note:
            line += f"  -- {note}"
        body.append(line)
    lines.append("\n".join(body))
    lines.append(");")

    for idx in table.get("indexes", []):
        col_name = _ident(idx.get("column", "col"))
        idx_name = f"idx_{name}_{col_name}"
        unique = "UNIQUE " if idx.get("unique") else ""
        lines.append(f'CREATE {unique}INDEX IF NOT EXISTS "{idx_name}" ON "{name}" ("{col_name}");')

    lines.append(_TABLE_FOOTER)
    return "\n".join(lines)


def generate(mapped: dict) -> str:
    source_engine = mapped.get("sourceEngine", "unknown")
    target_engine = mapped.get("targetEngine", "postgresql")
    tables = mapped.get("tables", [])

    sql = _HEADER.format(
        source_engine=source_engine,
        target_engine=target_engine,
        generated_at=now(),
        table_count=len(tables),
    )

    for table in tables:
        sql += _table_ddl(table)

    return sql


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("schema", help="Path to schema-mapped.json (output of type_mapper.py)")
    ap.add_argument("--target", default="azure-postgresql", help="Target engine label for header comment")
    ap.add_argument("--out", default="schema.sql")
    args = ap.parse_args(argv)

    with open(args.schema, encoding="utf-8") as fh:
        mapped = json.load(fh)

    mapped.setdefault("targetEngine", args.target)
    sql = generate(mapped)
    Path(args.out).write_text(sql, encoding="utf-8")
    print(f"{len(mapped.get('tables', []))} table(s) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
