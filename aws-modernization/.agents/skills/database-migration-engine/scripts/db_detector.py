"""Detect the source database engine from an engagement JSON.

Reads engagement.inventory (assets, languages, relationships) and
engagement.seed (tables, target) to identify:
  - Source DB engine (db2i, db2zos, sqlserver, oracle, mysql, sqlite, postgresql)
  - Detection evidence (file + line)
  - Target DB engine from target_contract.data

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Detection rules — ordered by specificity (most specific first)
# ---------------------------------------------------------------------------

_SOURCE_RULES: list[tuple[str, str, str]] = [
    # (engine_id, pattern, description)
    # DB2 for i / AS400
    ("db2i",       r"\.pf$",                                    "AS/400 physical file (.pf)"),
    ("db2i",       r"\.lf$",                                    "AS/400 logical file (.lf)"),
    ("db2i",       r"\.sqlrpgle$",                              "SQLRPGLE embedded SQL"),
    ("db2i",       r"DB2\s+for\s+i",                            "DB2 for i reference in source"),
    ("db2i",       r"EXEC\s+SQL.*FROM\s+\w+",                   "Embedded SQL in RPG/COBOL"),
    # DB2 z/OS
    ("db2zos",     r"EXEC\s+SQL",                               "Embedded SQL (COBOL/PL1)"),
    ("db2zos",     r"DSN=\w[\w.]+",                             "JCL DSN dataset reference"),
    ("db2zos",     r"DSNHDECP|DSNHADDR",                        "DB2 z/OS system module"),
    # SQL Server
    ("sqlserver",  r"SqlConnection|SqlCommand",                 "ADO.NET SQL Server client"),
    ("sqlserver",  r"UseSqlServer\s*\(",                        "EF Core UseSqlServer"),
    ("sqlserver",  r"database\.windows\.net",                   "Azure SQL connection string"),
    ("sqlserver",  r"Server=tcp:",                              "SQL Server TCP connection string"),
    ("sqlserver",  r"Initial\s+Catalog=",                       "SQL Server connection string"),
    ("sqlserver",  r"Microsoft\.EntityFrameworkCore\.SqlServer", "EF Core SqlServer package"),
    # Oracle
    ("oracle",     r"Oracle\.ManagedDataAccess",                "Oracle managed driver"),
    ("oracle",     r"UseOracle\s*\(",                           "EF Core UseOracle"),
    ("oracle",     r"jdbc:oracle:",                             "Oracle JDBC connection string"),
    ("oracle",     r"VARCHAR2|NUMBER\s*\(",                     "Oracle DDL types"),
    # MySQL
    ("mysql",      r"UseMySql\s*\(",                            "EF Core UseMySQL"),
    ("mysql",      r"jdbc:mysql:",                              "MySQL JDBC connection string"),
    ("mysql",      r"AUTO_INCREMENT",                           "MySQL DDL AUTO_INCREMENT"),
    ("mysql",      r"MySqlConnection",                          "MySQL .NET connector"),
    # SQLite
    ("sqlite",     r"UseSqlite\s*\(",                           "EF Core UseSqlite"),
    ("sqlite",     r"Data\s+Source=.*\.db",                     "SQLite file connection string"),
    ("sqlite",     r"sqlite3|import sqlite3",                   "Python sqlite3 module"),
    # PostgreSQL (already on PostgreSQL)
    ("postgresql", r"UseNpgsql\s*\(",                           "EF Core Npgsql"),
    ("postgresql", r"Npgsql\.EntityFrameworkCore",              "Npgsql EF Core package"),
    ("postgresql", r"Host=.*postgres",                          "PostgreSQL connection string"),
    ("postgresql", r"jdbc:postgresql:",                         "PostgreSQL JDBC connection string"),
]

# Content rules — matched against file CONTENTS when a source directory is available.
# (engine_id, regex, description). One vote per (file, engine).
_CONTENT_RULES: list[tuple[str, str, str]] = [
    ("db2zos",     r"EXEC\s+SQL|EXEC\s+CICS",                  "Embedded SQL / CICS in COBOL"),
    ("db2zos",     r"DSNTIAD|DSNTEP2|DSN\s+SYSTEM\(|DB2SSID",   "DB2 z/OS batch utility in JCL"),
    ("db2zos",     r"CCSID\s+EBCDIC",                          "DB2 z/OS DDL (CCSID EBCDIC)"),
    ("db2i",       r"CRTPF|CRTLF|RUNSQLSTM|QSYS",               "IBM i / AS400 object or command"),
    ("sqlserver",  r"System\.Data\.SqlClient|Microsoft\.Data\.SqlClient", "SQL Server ADO.NET provider"),
    ("sqlserver",  r"UseSqlServer\s*\(|SqlConnection|SqlCommand", "SQL Server client API"),
    ("sqlserver",  r"Initial\s+Catalog=|Integrated\s+Security=|database\.windows\.net|Server=tcp:", "SQL Server connection string"),
    ("sqlserver",  r"EntityFramework\.SqlServer|Microsoft\.EntityFrameworkCore\.SqlServer", "EF SqlServer provider"),
    ("sqlserver",  r"\[dbo\]\.|IDENTITY\s*\(\d+\s*,\s*\d+\)|NVARCHAR\s*\(", "T-SQL DDL"),
    ("oracle",     r"Oracle\.ManagedDataAccess|UseOracle\s*\(|jdbc:oracle:|VARCHAR2", "Oracle client / DDL"),
    ("mysql",      r"UseMySql\s*\(|jdbc:mysql:|AUTO_INCREMENT|MySqlConnection", "MySQL client / DDL"),
    ("sqlite",     r"UseSqlite\s*\(|Data\s+Source=[^;\"]*\.(?:db|sqlite)", "SQLite"),
    ("postgresql", r"UseNpgsql\s*\(|Npgsql|jdbc:postgresql:|Host=[^;\"]*postgres", "PostgreSQL client"),
]

_SCAN_SUFFIXES = {
    ".cs", ".config", ".json", ".csproj", ".xml", ".sql", ".ddl", ".jcl", ".cbl", ".cob",
    ".cpy", ".pf", ".lf", ".rpgle", ".sqlrpgle", ".properties", ".yml", ".yaml", ".java",
    ".py", ".txt",
}
_SKIP_DIRS = {".git", "node_modules", "bin", "obj", "packages", "__pycache__"}
_MAX_FILE_BYTES = 300_000
_MAX_FILES = 3000


def _scan_source_dir(source_dir: str) -> dict[str, list[dict]]:
    """Scan file contents under source_dir; one vote per (file, engine)."""
    votes: dict[str, list[dict]] = {}
    root = Path(source_dir)
    if not root.is_dir():
        return votes
    compiled = [(e, re.compile(p, re.IGNORECASE), d) for e, p, d in _CONTENT_RULES]
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            if fp.suffix.lower() not in _SCAN_SUFFIXES:
                continue
            try:
                if fp.stat().st_size > _MAX_FILE_BYTES:
                    continue
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            seen += 1
            if seen > _MAX_FILES:
                return votes
            rel = fp.relative_to(root).as_posix()
            hit: set[str] = set()
            for engine, rx, desc in compiled:
                if engine in hit:
                    continue
                if rx.search(text):
                    hit.add(engine)
                    votes.setdefault(engine, []).append(
                        {"evidence": rel, "rule": desc, "source": "file-content"}
                    )
    return votes


_TARGET_ALIASES: dict[str, str] = {
    "azure-postgresql":  "azure-postgresql",
    "azure_postgresql":  "azure-postgresql",
    "azurepostgresql":   "azure-postgresql",
    "aurora-postgresql": "aurora-postgresql",
    "aurora_postgresql": "aurora-postgresql",
    "aurorapostgresql":  "aurora-postgresql",
    "alloydb":           "alloydb",
    "supabase":          "supabase",
    "postgresql":        "postgresql",
    "postgres":          "postgresql",
}


def _load_engagement(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def detect_source(engagement: dict, source_dir: str | None = None) -> dict:
    """Detect source DB engine from engagement inventory + seed."""
    inventory = engagement.get("inventory") or {}
    seed = engagement.get("seed") or {}
    assets = inventory.get("assets", [])
    relationships = inventory.get("relationships", [])

    votes: dict[str, list[dict]] = {}

    # 1. Asset path matching
    for asset in assets:
        path = asset.get("path", "")
        for engine, pattern, desc in _SOURCE_RULES:
            if re.search(pattern, path, re.IGNORECASE):
                votes.setdefault(engine, []).append({
                    "evidence": path,
                    "rule": desc,
                    "source": "asset-path",
                })

    # 2. Relationship snippet matching
    for rel in relationships:
        snippet = rel.get("snippet", "")
        path = rel.get("path", "")
        for engine, pattern, desc in _SOURCE_RULES:
            if re.search(pattern, snippet, re.IGNORECASE):
                votes.setdefault(engine, []).append({
                    "evidence": f"{path}: {snippet[:80]}",
                    "rule": desc,
                    "source": "code-snippet",
                })

    # 3. Connection string in seed target
    target_data = (seed.get("target") or {}).get("data", "")
    if target_data:
        for engine, pattern, desc in _SOURCE_RULES:
            if re.search(pattern, target_data, re.IGNORECASE):
                votes.setdefault(engine, []).append({
                    "evidence": f"target.data={target_data}",
                    "rule": desc,
                    "source": "target-contract",
                })

    # 4. File contents (needs the engagement source folder)
    if source_dir:
        for engine, items in _scan_source_dir(source_dir).items():
            votes.setdefault(engine, []).extend(items)

    # 5. Platform table inventory hints (store: db2 / relational)
    stores = {str(t.get("store", "")).lower() for t in seed.get("tables", []) if isinstance(t, dict)}
    if "db2" in stores:
        engine = "db2i" if "db2i" in votes and "db2zos" not in votes else "db2zos"
        votes.setdefault(engine, []).append(
            {"evidence": "seed.tables store=db2", "rule": "Platform table inventory says DB2", "source": "seed-tables"}
        )

    if not votes:
        detected, evidence = "unknown", []
    else:
        winner = max(votes, key=lambda e: len(votes[e]))
        detected = winner
        evidence = votes[winner][:5]

    return {
        "sourceEngine": detected,
        "confidence": "high" if len(evidence) >= 3 else "medium" if evidence else "low",
        "evidenceCount": sum(len(v) for v in votes.values()),
        "evidence": evidence,
        "allVotes": {k: len(v) for k, v in votes.items()},
    }


def detect_target(engagement: dict) -> str:
    """Read target DB from engagement.seed.target.data."""
    raw = ((engagement.get("seed") or {}).get("target") or {}).get("data", "") or ""
    return _TARGET_ALIASES.get(raw.lower().strip(), "azure-postgresql")


def detect(engagement: dict, source_dir: str | None = None) -> dict:
    source = detect_source(engagement, source_dir)
    target = detect_target(engagement)
    return {
        "sourceEngine": source["sourceEngine"],
        "sourceConfidence": source["confidence"],
        "sourceEvidence": source["evidence"],
        "targetEngine": target,
        "allSourceVotes": source.get("allVotes", {}),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("engagement", help="Path to engagement.json")
    ap.add_argument("--source-dir", help="Engagement source folder (enables file-content detection)")
    ap.add_argument("--out", help="Write JSON result to this file")
    args = ap.parse_args(argv)

    eng = _load_engagement(args.engagement)
    result = detect(eng, args.source_dir)

    output = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
