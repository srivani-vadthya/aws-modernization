"""Language-analysis plugin registry used by the source classifier.

The core pipeline only consumes normalized relationship facts. New language or
vendor analyzers can be registered here without changing intake, gates, packs,
or the UI contract.
"""

from __future__ import annotations

from pathlib import Path

from .as400 import DATA_SUFFIXES, PROGRAM_SUFFIXES, extract_relationships


ANALYZERS = {
    "ibm-i": {
        "suffixes": PROGRAM_SUFFIXES | DATA_SUFFIXES,
        "extract": extract_relationships,
    },
}


def analyze_file(path: Path, text: str) -> tuple[list[dict[str, str]], set[str]]:
    facts: list[dict[str, str]] = []
    active: set[str] = set()
    for name, analyzer in ANALYZERS.items():
        if path.suffix.lower() not in analyzer["suffixes"]:
            continue
        active.add(name)
        facts.extend(analyzer["extract"](path, text))
    return facts, active
