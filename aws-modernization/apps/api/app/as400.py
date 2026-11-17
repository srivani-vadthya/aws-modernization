"""Small, conservative IBM i relationship extractor.

This is intentionally a lexical analyser, not a compiler. Every fact retains
the source file and only well-known RPG/CL/SQL forms are emitted so the UI can
show useful leads without presenting guesses as a complete call graph.
"""

from __future__ import annotations

import re
from pathlib import Path


PROGRAM_SUFFIXES = {
    ".rpgle", ".sqlrpgle", ".clle", ".cblle", ".cbl", ".cob",
    ".pli", ".pl1", ".cs", ".vb", ".jcl", ".proc"
}
DATA_SUFFIXES = {".pf", ".lf", ".dspf", ".sql", ".ddl", ".cpy", ".copy"}


def _normalise(value: str) -> str:
    return value.strip().upper()


def extract_relationships(path: Path, text: str) -> list[dict[str, any]]:
    """Extract CALLS, READS, WRITES, and MAPS_TO facts with AST line numbers
    across AS/400 RPGLE, CLLE, COBOL, PL/I, JCL, and C# / .NET.
    """
    suffix = path.suffix.lower()
    if suffix not in PROGRAM_SUFFIXES | DATA_SUFFIXES:
        return []
    source = path.stem.upper()
    facts: list[dict[str, any]] = []
    seen: set[tuple[str, str, str, int]] = set()

    lines = text.splitlines()

    for idx, line in enumerate(lines, start=1):
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("*") or line_clean.startswith("//"):
            continue

        def add(target: str, kind: str) -> None:
            target_norm = _normalise(target)
            if target_norm and target_norm != source:
                key = (source, target_norm, kind, idx)
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "source": source,
                        "target": target_norm,
                        "kind": kind,
                        "line": idx,
                        "snippet": line_clean[:140],
                        "evidence": f"{path.name}#L{idx}",
                        "ast_node": f"AST:{source}:L{idx}:{kind}",
                    })

        # 1. AS/400 RPGLE & SQLRPGLE
        if suffix in {".rpgle", ".sqlrpgle"}:
            for target in re.findall(r"\b(?:CALLP?|EXTPGM)\s*(?:\(|\s+)\s*'?([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(target, "CALLS")
            for target in re.findall(r"\b(?:DCL-F|F)\s*([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(target, "READS")
            for target in re.findall(r"\b(?:CHAIN|SETLL|SETGT|READE?)\s*(?:\([^)]*\)\s*)?([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(target, "READS")
            for target in re.findall(r"\b(?:WRITE|UPDATE|DELETE)\s+([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(target, "WRITES")

        # 2. AS/400 CLLE (Control Language)
        elif suffix == ".clle":
            for target in re.findall(r"\bCALL\s+(?:PGM\s*\(\s*)?([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(target, "CALLS")
            for target in re.findall(r"\bSBMJOB\s+.*CMD\s*\(\s*CALL\s+PGM\s*\(\s*([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(target, "CALLS")
            for target in re.findall(r"\bOVRDBF\s+FILE\s*\(\s*([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(target, "READS")

        # 3. Mainframe COBOL & JCL
        elif suffix in {".cblle", ".cbl", ".cob"}:
            for target in re.findall(r"\bCALL\s+['\"]?([A-Za-z0-9_#$@-]+)", line, re.IGNORECASE):
                add(target, "CALLS")
            for target in re.findall(r"\bCOPY\s+['\"]?([A-Za-z0-9_#$@-]+)", line, re.IGNORECASE):
                add(target, "READS")
        elif suffix in {".jcl", ".proc"}:
            for target in re.findall(r"\bEXEC\s+PGM=([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(target, "CALLS")
            for target in re.findall(r"\bDSN=([A-Za-z0-9_#$@.]+)", line, re.IGNORECASE):
                add(target.split(".")[-1], "READS")

        # 4. PL/I (Programming Language One)
        elif suffix in {".pli", ".pl1"}:
            for target in re.findall(r"\bCALL\s+([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(target, "CALLS")
            for target in re.findall(r"%INCLUDE\s+([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(target, "READS")

        # 5. C# / .NET Legacy (EF6 / ADO.NET)
        elif suffix in {".cs", ".vb"}:
            for target in re.findall(r"\b(?:new|await)\s+([A-Za-z0-9_]+Client|[A-Za-z0-9_]+Service)\b", line, re.IGNORECASE):
                add(target, "CALLS")
            for target in re.findall(r"\bDbSet<([A-Za-z0-9_]+)>\b", line, re.IGNORECASE):
                add(target, "READS")
            for target in re.findall(r"\b(?:FromSqlRaw|SqlQuery)\s*\(\s*['\"].*?(?:FROM|JOIN)\s+([A-Za-z0-9_]+)", line, re.IGNORECASE):
                add(target, "READS")

        # 6. Screen files (DSPF)
        elif suffix == ".dspf":
            for record in re.findall(r"^\s*A\s+R\s+([A-Za-z0-9_#$@]+)", line, re.IGNORECASE):
                add(record, "MAPS_TO")

        # Embedded SQL across any language
        for target in re.findall(r"\bFROM\s+([A-Za-z0-9_#$@.]+)", line, re.IGNORECASE):
            add(target.split(".")[-1], "READS")
        for target in re.findall(r"\b(?:UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+([A-Za-z0-9_#$@.]+)", line, re.IGNORECASE):
            add(target.split(".")[-1], "WRITES")

    return sorted(facts, key=lambda f: (f["source"], f["line"], f["target"]))
