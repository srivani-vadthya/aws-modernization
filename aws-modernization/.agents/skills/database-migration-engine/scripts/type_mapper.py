"""Map source database types to target database types.

Config-driven: adding a new source or target is just adding rows to TYPE_MAP.
Lossless mappings are preferred; lossy mappings are flagged with a risk level.

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_migration_model import SUPPORTED_SOURCES, SUPPORTED_TARGETS


# ---------------------------------------------------------------------------
# Type mapping table
# (source_engine, source_type_pattern) -> (target_type, risk, conversion_note)
# Patterns are matched case-insensitively against the normalised source type.
# First match wins — order from most specific to least specific.
# ---------------------------------------------------------------------------

_TYPE_MAP: list[tuple[str, str, str, str, str]] = [
    # (source_engine, source_pattern, target_type, risk, note)

    # ---- DB2 for i (AS/400) ------------------------------------------------
    ("db2i", r"PACKED\((\d+),(\d+)\)",  "NUMERIC({0},{1})",  "medium", "COMP-3 packed decimal -> NUMERIC; verify rounding mode"),
    ("db2i", r"CHAR\((\d+)\)",          "VARCHAR({0})",      "low",    "Fixed CHAR -> VARCHAR"),
    ("db2i", r"DATE",                   "DATE",              "low",    ""),
    ("db2i", r"TIME",                   "TIME",              "low",    ""),
    ("db2i", r"TIMESTAMP",              "TIMESTAMPTZ",       "low",    "Add timezone awareness"),
    ("db2i", r"BINARY\((\d+)\)",        "BYTEA",             "medium", "Binary field -> BYTEA"),
    ("db2i", r"FLOAT\((\d+)\)",         "DOUBLE PRECISION",  "medium", "Verify float precision requirements"),

    # ---- DB2 z/OS -----------------------------------------------------------
    ("db2zos", r"CHAR\((\d+)\)",        "VARCHAR({0})",      "low",    "Fixed CHAR -> VARCHAR"),
    ("db2zos", r"VARCHAR\((\d+)\)",     "VARCHAR({0})",      "low",    ""),
    ("db2zos", r"DECIMAL\((\d+),(\d+)\)","NUMERIC({0},{1})", "low",    ""),
    ("db2zos", r"INTEGER",              "INTEGER",           "low",    ""),
    ("db2zos", r"SMALLINT",             "SMALLINT",          "low",    ""),
    ("db2zos", r"BIGINT",               "BIGINT",            "low",    ""),
    ("db2zos", r"FLOAT",                "DOUBLE PRECISION",  "medium", "Verify float precision"),
    ("db2zos", r"DATE",                 "DATE",              "low",    ""),
    ("db2zos", r"TIME",                 "TIME",              "low",    ""),
    ("db2zos", r"TIMESTAMP",            "TIMESTAMPTZ",       "low",    "Add timezone awareness"),
    ("db2zos", r"CLOB",                 "TEXT",              "low",    ""),
    ("db2zos", r"BLOB",                 "BYTEA",             "medium", "Binary large object -> BYTEA"),
    ("db2zos", r"GRAPHIC\((\d+)\)",     "VARCHAR({0})",      "medium", "DBCS graphic -> VARCHAR; verify encoding"),

    # ---- SQL Server ---------------------------------------------------------
    ("sqlserver", r"NVARCHAR\(MAX\)",   "TEXT",              "low",    ""),
    ("sqlserver", r"NVARCHAR\((\d+)\)", "VARCHAR({0})",      "low",    "Unicode -> UTF-8 VARCHAR"),
    ("sqlserver", r"VARCHAR\(MAX\)",    "TEXT",              "low",    ""),
    ("sqlserver", r"VARCHAR\((\d+)\)",  "VARCHAR({0})",      "low",    ""),
    ("sqlserver", r"NCHAR\((\d+)\)",    "CHAR({0})",         "low",    ""),
    ("sqlserver", r"CHAR\((\d+)\)",     "CHAR({0})",         "low",    ""),
    ("sqlserver", r"NTEXT",             "TEXT",              "low",    "Deprecated type -> TEXT"),
    ("sqlserver", r"TEXT",              "TEXT",              "low",    ""),
    ("sqlserver", r"UNIQUEIDENTIFIER",  "UUID",              "low",    "Use gen_random_uuid() as default"),
    ("sqlserver", r"BIT",               "BOOLEAN",           "low",    ""),
    ("sqlserver", r"TINYINT",           "SMALLINT",          "low",    "No TINYINT in PostgreSQL"),
    ("sqlserver", r"SMALLINT",          "SMALLINT",          "low",    ""),
    ("sqlserver", r"INT",               "INTEGER",           "low",    ""),
    ("sqlserver", r"BIGINT",            "BIGINT",            "low",    ""),
    ("sqlserver", r"DECIMAL\((\d+),(\d+)\)", "NUMERIC({0},{1})", "low", ""),
    ("sqlserver", r"NUMERIC\((\d+),(\d+)\)", "NUMERIC({0},{1})", "low", ""),
    ("sqlserver", r"MONEY",             "NUMERIC(19,4)",     "low",    ""),
    ("sqlserver", r"SMALLMONEY",        "NUMERIC(10,4)",     "low",    ""),
    ("sqlserver", r"FLOAT",             "DOUBLE PRECISION",  "medium", "Verify float precision"),
    ("sqlserver", r"REAL",              "REAL",              "low",    ""),
    ("sqlserver", r"DATETIME2",         "TIMESTAMPTZ",       "low",    ""),
    ("sqlserver", r"DATETIME",          "TIMESTAMPTZ",       "low",    "No timezone in DATETIME; add UTC assumption"),
    ("sqlserver", r"SMALLDATETIME",     "TIMESTAMP",         "low",    ""),
    ("sqlserver", r"DATE",              "DATE",              "low",    ""),
    ("sqlserver", r"TIME",              "TIME",              "low",    ""),
    ("sqlserver", r"DATETIMEOFFSET",    "TIMESTAMPTZ",       "low",    ""),
    ("sqlserver", r"VARBINARY\(MAX\)",  "BYTEA",             "medium", ""),
    ("sqlserver", r"VARBINARY\((\d+)\)","BYTEA",             "medium", ""),
    ("sqlserver", r"IMAGE",             "BYTEA",             "medium", "Deprecated type -> BYTEA"),
    ("sqlserver", r"XML",               "XML",               "low",    ""),
    ("sqlserver", r"ROWVERSION",        "BYTEA",             "medium", "No rowversion in PostgreSQL; use xmin or trigger"),
    ("sqlserver", r"HIERARCHYID",       "TEXT",              "high",   "No native equivalent; store as ltree or TEXT"),

    # ---- Oracle -------------------------------------------------------------
    ("oracle", r"VARCHAR2\((\d+)\)",    "VARCHAR({0})",      "low",    ""),
    ("oracle", r"NVARCHAR2\((\d+)\)",   "VARCHAR({0})",      "low",    ""),
    ("oracle", r"CHAR\((\d+)\)",        "CHAR({0})",         "low",    ""),
    ("oracle", r"NUMBER\((\d+),(\d+)\)","NUMERIC({0},{1})",  "low",    ""),
    ("oracle", r"NUMBER\((\d+)\)",      "NUMERIC({0})",      "low",    ""),
    ("oracle", r"NUMBER",               "NUMERIC",           "medium", "Unqualified NUMBER; verify precision"),
    ("oracle", r"INTEGER",              "INTEGER",           "low",    ""),
    ("oracle", r"FLOAT\((\d+)\)",       "DOUBLE PRECISION",  "medium", "Verify float precision"),
    ("oracle", r"DATE",                 "TIMESTAMPTZ",       "medium", "Oracle DATE includes time; use TIMESTAMPTZ"),
    ("oracle", r"TIMESTAMP\((\d+)\) WITH TIME ZONE", "TIMESTAMPTZ", "low", ""),
    ("oracle", r"TIMESTAMP",            "TIMESTAMP",         "low",    ""),
    ("oracle", r"CLOB",                 "TEXT",              "low",    ""),
    ("oracle", r"NCLOB",                "TEXT",              "low",    ""),
    ("oracle", r"BLOB",                 "BYTEA",             "medium", ""),
    ("oracle", r"RAW\((\d+)\)",         "BYTEA",             "medium", ""),
    ("oracle", r"LONG RAW",             "BYTEA",             "high",   "Deprecated; migrate to BYTEA"),
    ("oracle", r"XMLTYPE",              "XML",               "medium", "Verify XML functions used"),

    # ---- MySQL --------------------------------------------------------------
    ("mysql", r"TINYINT\(1\)",          "BOOLEAN",           "low",    "MySQL boolean convention"),
    ("mysql", r"TINYINT",               "SMALLINT",          "low",    ""),
    ("mysql", r"SMALLINT",              "SMALLINT",          "low",    ""),
    ("mysql", r"MEDIUMINT",             "INTEGER",           "low",    "No MEDIUMINT in PostgreSQL"),
    ("mysql", r"INT",                   "INTEGER",           "low",    ""),
    ("mysql", r"BIGINT",                "BIGINT",            "low",    ""),
    ("mysql", r"DECIMAL\((\d+),(\d+)\)","NUMERIC({0},{1})",  "low",    ""),
    ("mysql", r"FLOAT",                 "REAL",              "low",    ""),
    ("mysql", r"DOUBLE",                "DOUBLE PRECISION",  "low",    ""),
    ("mysql", r"VARCHAR\((\d+)\)",      "VARCHAR({0})",      "low",    ""),
    ("mysql", r"CHAR\((\d+)\)",         "CHAR({0})",         "low",    ""),
    ("mysql", r"TEXT",                  "TEXT",              "low",    ""),
    ("mysql", r"MEDIUMTEXT",            "TEXT",              "low",    ""),
    ("mysql", r"LONGTEXT",              "TEXT",              "low",    ""),
    ("mysql", r"BLOB",                  "BYTEA",             "medium", ""),
    ("mysql", r"MEDIUMBLOB",            "BYTEA",             "medium", ""),
    ("mysql", r"LONGBLOB",              "BYTEA",             "medium", ""),
    ("mysql", r"DATETIME",              "TIMESTAMPTZ",       "low",    "Add UTC assumption"),
    ("mysql", r"TIMESTAMP",             "TIMESTAMPTZ",       "low",    ""),
    ("mysql", r"DATE",                  "DATE",              "low",    ""),
    ("mysql", r"TIME",                  "TIME",              "low",    ""),
    ("mysql", r"YEAR",                  "SMALLINT",          "low",    ""),
    ("mysql", r"ENUM\(([^)]+)\)",       "TEXT",              "medium", "ENUM -> TEXT + CHECK constraint"),
    ("mysql", r"SET\(([^)]+)\)",        "TEXT[]",            "medium", "SET -> TEXT array"),
    ("mysql", r"JSON",                  "JSONB",             "low",    "Use JSONB for indexing"),

    # ---- SQLite -------------------------------------------------------------
    ("sqlite", r"INTEGER",              "INTEGER",           "low",    ""),
    ("sqlite", r"REAL",                 "DOUBLE PRECISION",  "low",    ""),
    ("sqlite", r"TEXT",                 "TEXT",              "low",    ""),
    ("sqlite", r"BLOB",                 "BYTEA",             "medium", ""),
    ("sqlite", r"NUMERIC",              "NUMERIC",           "low",    ""),

    # ---- Fallback (unknown source) ------------------------------------------
    ("unknown", r".*",                  "TEXT",              "high",   "Unknown source type; defaulted to TEXT — review manually"),
]


def _resolve_placeholders(template: str, match: re.Match) -> str:
    """Replace {0}, {1} in template with capture groups from the regex match."""
    result = template
    for i, group in enumerate(match.groups()):
        result = result.replace(f"{{{i}}}", group or "")
    return result


def map_type(source_engine: str, source_type: str) -> tuple[str, str, str]:
    """Return (target_type, risk, conversion_note) for a given source type."""
    src = source_type.strip().upper()
    engines_to_try = [source_engine, "unknown"]

    for engine in engines_to_try:
        for rule_engine, pattern, target_template, risk, note in _TYPE_MAP:
            if rule_engine != engine:
                continue
            m = re.fullmatch(pattern, src, re.IGNORECASE)
            if m:
                target = _resolve_placeholders(target_template, m)
                return target, risk, note

    return "TEXT", "high", f"No mapping found for {source_engine}:{source_type}; defaulted to TEXT"


def map_table(table: dict, source_engine: str) -> dict:
    """Apply type mapping to every column in a table dict."""
    mapped = dict(table)
    mapped_columns = []
    for col in table.get("columns", []):
        target_type, risk, note = map_type(source_engine, col.get("sourceType", "UNKNOWN"))
        mapped_col = dict(col)
        mapped_col["targetType"] = target_type
        mapped_col["risk"] = risk
        mapped_col["conversionNote"] = note
        mapped_columns.append(mapped_col)
    mapped["columns"] = mapped_columns
    return mapped


def map_schema(raw: dict, source_engine: str) -> dict:
    """Map all tables in a schema-raw.json dict."""
    tables = [map_table(t, source_engine) for t in raw.get("tables", [])]
    return {
        "sourceEngine": source_engine,
        "tableCount": len(tables),
        "tables": tables,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("schema", help="Path to schema-raw.json (output of schema_extractor.py)")
    ap.add_argument("--source", required=True,
                    help=f"Source engine: {', '.join(sorted(SUPPORTED_SOURCES))}")
    ap.add_argument("--target", default="azure-postgresql",
                    help=f"Target engine: {', '.join(sorted(SUPPORTED_TARGETS))} (default: azure-postgresql)")
    ap.add_argument("--out", default="schema-mapped.json")
    args = ap.parse_args(argv)

    with open(args.schema, encoding="utf-8") as fh:
        raw = json.load(fh)

    result = map_schema(raw, args.source)
    result["targetEngine"] = args.target

    output = json.dumps(result, indent=2)
    Path(args.out).write_text(output, encoding="utf-8")
    print(f"{result['tableCount']} table(s) mapped ({args.source} -> {args.target}) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
