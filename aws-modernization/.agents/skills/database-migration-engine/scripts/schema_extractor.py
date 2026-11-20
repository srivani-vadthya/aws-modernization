"""Extract tables, columns, types, and constraints from an engagement JSON.

Sources consulted (in priority order):
  1. engagement.seed.tables       — platform-built table inventory
  2. engagement.inventory.assets  — DDS .pf files (AS/400), .sql/.ddl files
  3. engagement.inventory.relationships — READS/WRITES edges with field hints

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
from db_migration_model import make_column, make_table, slug


# ---------------------------------------------------------------------------
# DDS Physical File parser (AS/400 .pf)
# ---------------------------------------------------------------------------

_DDS_FIELD = re.compile(
    r"^\s*A\s+(?P<name>[A-Za-z0-9_#$@]+)\s+(?P<len>\d+)(?P<type>[A-Za-z]?)\s*(?P<dec>\d*)",
    re.IGNORECASE,
)
_DDS_KEY = re.compile(r"^\s*A\s+K\s+(?P<name>[A-Za-z0-9_#$@]+)", re.IGNORECASE)


def _dds_source_type(length: str, type_char: str, dec: str) -> str:
    t = type_char.upper()
    if t == "A":  return f"CHAR({length})"
    if t in ("S", "P"):
        d = dec or "0"
        return f"PACKED({length},{d})"
    if t == "L":  return "DATE"
    if t == "T":  return "TIME"
    if t == "Z":  return "TIMESTAMP"
    if t == "B":  return f"BINARY({length})"
    if t == "F":  return f"FLOAT({length})"
    return f"CHAR({length})"


def _parse_dds_pf(text: str, filename: str) -> dict | None:
    columns: list[dict] = []
    pk_names: set[str] = set()
    table_name = Path(filename).stem.upper()

    for line in text.splitlines():
        km = _DDS_KEY.match(line)
        if km:
            pk_names.add(km.group("name").upper())
        fm = _DDS_FIELD.match(line)
        if fm:
            name = fm.group("name").upper()
            src_type = _dds_source_type(fm.group("len"), fm.group("type"), fm.group("dec"))
            columns.append({
                "name": name,
                "sourceType": src_type,
                "primaryKey": False,
                "nullable": True,
                "evidence": filename,
            })

    if not columns:
        return None

    for col in columns:
        if col["name"] in pk_names:
            col["primaryKey"] = True
            col["nullable"] = False

    return {"name": table_name, "sourceName": table_name, "columns": columns, "evidence": filename}


# ---------------------------------------------------------------------------
# SQL DDL parser (generic CREATE TABLE — also DB2 DDL embedded in JCL)
# ---------------------------------------------------------------------------

_CREATE_HEAD = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>[^\s(]+)\s*\(", re.IGNORECASE)
_CONSTRAINT_START = ("PRIMARY", "UNIQUE", "FOREIGN", "INDEX", "KEY", "CONSTRAINT", "CHECK")
_FK_RE = re.compile(
    r"FOREIGN\s+KEY\s*\((?P<cols>[^)]+)\)\s*REFERENCES\s+(?P<ref>[^\s(]+)\s*(?:\((?P<refcols>[^)]*)\))?",
    re.IGNORECASE,
)
_COL_RE = re.compile(
    r"^(?P<name>[\w$#@]+|\"[^\"]+\"|\[[^\]]+\])\s+"
    r"(?P<type>[A-Za-z_][A-Za-z_ ]*?(?:\s*\(\s*\d+\s*(?:,\s*\d+\s*)?\))?)"
    r"(?:\s+(?P<mods>.*))?$",
    re.IGNORECASE | re.DOTALL,
)
_MOD_WORDS = {"NOT", "NULL", "DEFAULT", "PRIMARY", "GENERATED", "UNIQUE", "REFERENCES", "WITH", "CHECK", "IDENTITY", "AUTO_INCREMENT"}


def _clean_ident(raw: str) -> str:
    """'<DB2DBID>.customer' / '[dbo].[Foo]' / '"S"."T"' -> 'CUSTOMER' / 'FOO' / 'T'."""
    last = raw.strip().rstrip(";").split(".")[-1]
    return re.sub(r"[<>\[\]\"`]", "", last).strip().upper()


def _split_top_level(body: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def _balanced_body(text: str, open_idx: int) -> str | None:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i]
    return None


def _normalise_type(raw_type: str) -> str:
    """'char (10)' -> 'CHAR(10)'; drop trailing modifier words the lazy regex may swallow."""
    words = re.sub(r"\s+", " ", raw_type).strip().upper().split(" ")
    kept: list[str] = []
    for w in words:
        if kept and w.split("(")[0] in _MOD_WORDS:
            break
        kept.append(w)
    t = " ".join(kept)
    return re.sub(r"\s*\(\s*", "(", t).replace(", ", ",").replace(" )", ")")


def _parse_sql_ddl(text: str, filename: str) -> list[dict]:
    text = re.sub(r"--[^\n]*", "", text)  # strip line comments
    tables: list[dict] = []
    for m in _CREATE_HEAD.finditer(text):
        body = _balanced_body(text, m.end() - 1)
        if body is None:
            continue
        table_name = _clean_ident(m.group("name"))
        columns: list[dict] = []
        pk_cols: set[str] = set()
        fks: list[dict] = []

        items = [re.sub(r"\s+", " ", i).strip() for i in _split_top_level(body)]
        for flat in items:
            up = flat.upper()
            pm = re.search(r"PRIMARY\s+KEY\s*\(([^)]+)\)", flat, re.IGNORECASE)
            if pm and (up.startswith("PRIMARY") or up.startswith("CONSTRAINT")):
                pk_cols |= {_clean_ident(c) for c in pm.group(1).split(",")}
            if up.startswith("FOREIGN") or (up.startswith("CONSTRAINT") and "FOREIGN KEY" in up):
                fm = _FK_RE.search(flat)
                if fm:
                    src = [_clean_ident(c) for c in fm.group("cols").split(",")]
                    ref_cols = [_clean_ident(c) for c in (fm.group("refcols") or "").split(",") if c.strip()]
                    for i, sc in enumerate(src):
                        fks.append({
                            "column": sc,
                            "referencedTable": _clean_ident(fm.group("ref")),
                            "referencedColumn": ref_cols[i] if i < len(ref_cols) else sc,
                        })

        for flat in items:
            if not flat or flat.upper().startswith(_CONSTRAINT_START):
                continue
            cm = _COL_RE.match(flat)
            if not cm:
                continue
            col_name = _clean_ident(cm.group("name"))
            col_type = _normalise_type(cm.group("type"))
            mods = (cm.group("mods") or "").upper()
            is_pk = col_name in pk_cols or "PRIMARY KEY" in mods
            not_null = "NOT NULL" in mods
            columns.append({
                "name": col_name,
                "sourceType": col_type,
                "primaryKey": is_pk,
                "nullable": not (not_null or is_pk),
                "evidence": filename,
            })

        if columns:
            tables.append({
                "name": table_name,
                "sourceName": table_name,
                "columns": columns,
                "foreignKeys": fks,
                "evidence": filename,
            })
    return tables


# ---------------------------------------------------------------------------
# C# / Entity Framework entity parser
# ---------------------------------------------------------------------------

_CS_PRIMITIVES = {
    "int": "INT", "int32": "INT", "long": "BIGINT", "int64": "BIGINT",
    "short": "SMALLINT", "int16": "SMALLINT", "byte": "TINYINT",
    "bool": "BIT", "boolean": "BIT",
    "string": "NVARCHAR(MAX)",
    "decimal": "DECIMAL(18,2)", "double": "FLOAT", "float": "REAL", "single": "REAL",
    "datetime": "DATETIME2", "datetimeoffset": "DATETIMEOFFSET", "timespan": "TIME",
    "guid": "UNIQUEIDENTIFIER", "byte[]": "VARBINARY(MAX)",
}
_CS_PROP = re.compile(
    r"public\s+(?P<virtual>virtual\s+)?(?P<type>[\w.<>\[\]?,\s]+?)\s+(?P<name>\w+)\s*\{\s*get\s*;\s*"
    r"(?:private\s+|protected\s+|internal\s+)?set\s*;\s*\}"
)


def _class_body(text: str, class_name: str) -> str | None:
    m = re.search(r"\bclass\s+" + re.escape(class_name) + r"\b[^{]*\{", text)
    if not m:
        return None
    depth = 0
    for i in range(m.end() - 1, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[m.end():i]
    return None


def _parse_cs_entity(text: str, class_name: str, entity_names: set[str], filename: str) -> dict | None:
    body = _class_body(text, class_name)
    if body is None:
        return None
    columns: list[dict] = []
    fks: list[dict] = []
    upper_entities = {e.upper(): e for e in entity_names}
    for pm in _CS_PROP.finditer(body):
        ctype = re.sub(r"\s+", "", pm.group("type"))
        pname = pm.group("name")
        nullable = ctype.endswith("?")
        base = ctype.rstrip("?")
        low = base.lower()
        # navigation properties / collections are relationships, not columns
        if pm.group("virtual") or re.match(r"(I?List|ICollection|IEnumerable|HashSet)<", base):
            continue
        if base in entity_names:
            continue
        if low in _CS_PRIMITIVES:
            src_type = _CS_PRIMITIVES[low]
            nullable = nullable or low == "string"
        else:
            src_type = "UNKNOWN"  # enum / custom type — flagged for manual review
            nullable = True
        is_pk = pname.lower() in ("id", class_name.lower() + "id")
        columns.append({
            "name": pname.upper(),
            "sourceType": src_type,
            "primaryKey": is_pk,
            "nullable": False if is_pk else nullable,
            "evidence": filename,
        })
        # FooId -> FK to Foo when Foo is a known entity
        if not is_pk and pname.lower().endswith("id") and len(pname) > 2:
            ref = upper_entities.get(pname[:-2].upper())
            if ref:
                fks.append({"column": pname.upper(), "referencedTable": ref.upper(), "referencedColumn": "ID"})
    if not columns:
        return None
    return {
        "name": class_name.upper(),
        "sourceName": class_name,
        "columns": columns,
        "foreignKeys": fks,
        "evidence": filename,
    }


# ---------------------------------------------------------------------------
# Seed tables extractor (platform-built inventory)
# ---------------------------------------------------------------------------

def _from_seed_tables(seed: dict) -> list[dict]:
    """Convert engagement.seed.tables into raw table dicts."""
    raw = []
    for t in seed.get("tables", []):
        tid = t.get("id", "")
        name = str(t.get("table") or t.get("name") or tid.split(":")[-1].split(".")[-1]).upper()
        if not name:
            continue
        # Seed tables rarely carry column-level detail — build a minimal record
        columns = []
        for field in t.get("fields", []):
            columns.append({
                "name": field.get("name", "").upper(),
                "sourceType": field.get("type", "UNKNOWN"),
                "primaryKey": field.get("primaryKey", False),
                "nullable": field.get("nullable", True),
                "evidence": f"seed.tables:{tid}",
            })
        if not columns:
            columns.append({
                "name": "ID",
                "sourceType": "UNKNOWN",
                "primaryKey": True,
                "nullable": False,
                "evidence": f"seed.tables:{tid}",
            })
        raw.append({
            "name": name,
            "sourceName": name,
            "columns": columns,
            "capability": t.get("capability", ""),
            "evidence": f"seed.tables:{tid}",
            "placeholder": not t.get("fields"),
            "path": t.get("path", ""),
        })
    return raw


_DDL_SUFFIXES = {".sql", ".ddl", ".jcl", ".db2", ".txt", ".pf"}
_SKIP_DIRS = {".git", "node_modules", "bin", "obj", "packages", "__pycache__"}


# ---------------------------------------------------------------------------
# Public extract function
# ---------------------------------------------------------------------------

def extract(engagement: dict, source_dir: str | None = None) -> list[dict]:
    """Return a list of raw table dicts from all available sources."""
    seed = engagement.get("seed") or {}
    inventory = engagement.get("inventory") or {}
    tables_by_name: dict[str, dict] = {}

    # Priority 1 — seed.tables (platform-built)
    for t in _from_seed_tables(seed):
        tables_by_name[t["name"]] = t

    # Priority 2 — parse real source files under source_dir
    if source_dir and Path(source_dir).is_dir():
        src = Path(source_dir)

        def _take(parsed: dict) -> None:
            existing = tables_by_name.get(parsed["name"])
            if existing is None or existing.get("placeholder"):
                parsed["capability"] = (existing or {}).get("capability", "")
                tables_by_name[parsed["name"]] = parsed

        # 2a. DDL / DDS anywhere in the tree (DB2 DDL often lives inside .jcl)
        for dirpath, dirnames, filenames in os.walk(src):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                fp = Path(dirpath) / fn
                suffix = fp.suffix.lower()
                if suffix not in _DDL_SUFFIXES:
                    continue
                try:
                    if fp.stat().st_size > 2_000_000:
                        continue
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                rel = fp.relative_to(src).as_posix()
                if suffix == ".pf":
                    parsed = _parse_dds_pf(text, rel)
                    if parsed:
                        _take(parsed)
                elif re.search(r"CREATE\s+TABLE", text, re.IGNORECASE):
                    for t in _parse_sql_ddl(text, rel):
                        _take(t)

        # 2b. C# entity classes referenced by seed.tables (Entity Framework projects)
        cs_tables = [t for t in tables_by_name.values() if t.get("placeholder") and str(t.get("path", "")).endswith(".cs")]
        if cs_tables:
            entity_names = {t.get("sourceName", t["name"]) for t in cs_tables}
            for t in cs_tables:
                full = src / t["path"]
                if not full.is_file():
                    continue
                try:
                    text = full.read_text(encoding="utf-8-sig", errors="ignore")
                except OSError:
                    continue
                cm = re.search(r"\bclass\s+(" + re.escape(t["name"]) + r")\b", text, re.IGNORECASE)
                if not cm:
                    continue
                known = set(re.findall(r"\bclass\s+(\w+)", text)) | entity_names
                parsed = _parse_cs_entity(text, cm.group(1), known, t["path"])
                if parsed:
                    parsed["name"] = t["name"]
                    parsed["capability"] = t.get("capability", "")
                    tables_by_name[t["name"]] = parsed

    # Priority 3 — infer table names from READS/WRITES relationships
    for rel in inventory.get("relationships", []):
        if rel.get("kind") in ("READS", "WRITES"):
            tname = rel.get("target", "").upper()
            if tname and tname not in tables_by_name:
                tables_by_name[tname] = {
                    "name": tname,
                    "sourceName": tname,
                    "columns": [{
                        "name": "ID",
                        "sourceType": "UNKNOWN",
                        "primaryKey": True,
                        "nullable": False,
                        "evidence": rel.get("path", "inferred"),
                    }],
                    "capability": "",
                    "evidence": f"inferred from {rel.get('kind')} in {rel.get('path', '')}",
                }

    out = list(tables_by_name.values())
    for t in out:
        t.pop("placeholder", None)
        t.pop("path", None)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("engagement", help="Path to engagement.json")
    ap.add_argument("--source-dir", help="Path to the engagement source folder (optional)")
    ap.add_argument("--out", default="schema-raw.json", help="Output file (default: schema-raw.json)")
    args = ap.parse_args(argv)

    with open(args.engagement, encoding="utf-8") as fh:
        eng = json.load(fh)

    tables = extract(eng, args.source_dir)
    output = json.dumps({"tables": tables, "tableCount": len(tables)}, indent=2)
    Path(args.out).write_text(output, encoding="utf-8")
    print(f"{len(tables)} table(s) extracted -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
