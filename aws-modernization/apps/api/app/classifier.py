from __future__ import annotations

from collections import Counter
from pathlib import Path

from .analyzers import analyze_file

KIND_BY_SUFFIX = {
    ".cbl": ("cobol", "program"),
    ".cob": ("cobol", "program"),
    ".cobol": ("cobol", "program"),
    ".cpy": ("cobol", "copybook"),
    ".copy": ("cobol", "copybook"),
    ".pli": ("pli", "program"),
    ".pl1": ("pli", "program"),
    ".jcl": ("jcl", "job"),
    ".proc": ("jcl", "proc"),
    ".bms": ("bms", "screen"),
    ".csd": ("cics", "definition"),
    ".sql": ("sql", "ddl"),
    ".ddl": ("sql", "ddl"),
    ".java": ("java", "source"),
    ".rpgle": ("rpgle", "program"),
    ".sqlrpgle": ("rpgle", "program"),
    ".clle": ("cl", "job"),
    ".dspf": ("dds", "screen"),
    ".pf": ("dds", "ddl"),
    ".lf": ("dds", "ddl"),
    ".cblle": ("cobol", "program"),
    ".xml": ("xml", "config"),
    ".cs": ("csharp", "source"),
    ".vb": ("vbnet", "source"),
    ".csproj": ("csharp", "project"),
    ".sln": ("csharp", "solution"),
    ".md": ("docs", "doc"),
    ".txt": ("docs", "doc"),
    ".json": ("config", "json"),
    ".yml": ("config", "yaml"),
    ".yaml": ("config", "yaml"),
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "dist", "target", "bin", "obj", ".vs", "packages",
    "Scripts", "scripts", "Content", "content", "fonts", "Images", "images", "assets", "bower_components"
}


def classify_tree(root: Path) -> dict:
    assets: list[dict] = []
    counts: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    missing_hints: list[str] = []
    relationships: list[dict[str, str]] = []
    active_analyzers: set[str] = set()

    if not root.exists():
        return {"assets": [], "counts": {}, "languages": {}, "warnings": ["Source tree is empty"]}

    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        language, kind = KIND_BY_SUFFIX.get(suffix, ("other", "file"))
        file_size = 0
        try:
            file_size = path.stat().st_size
            if file_size < 2_000_000 and suffix not in {".png", ".gif", ".jar", ".class"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                loc = text.count("\n") + 1 if text else 0
                facts, analyzers = analyze_file(path, text)
                active_analyzers.update(analyzers)
                for fact in facts:
                    relationships.append({**fact, "path": rel})
        except OSError:
            loc = 0
        assets.append(
            {
                "path": rel,
                "kind": kind,
                "language": language,
                "loc": loc,
                "bytes": file_size,
            }
        )
        counts[kind] += 1
        languages[language] += 1

    if languages.get("cobol") and not languages.get("copybook") and counts.get("copybook", 0) == 0:
        missing_hints.append("COBOL present but no copybooks detected — Transform may fail on COPY statements.")
    if languages.get("cobol") and counts.get("job", 0) == 0:
        missing_hints.append("No JCL detected. Batch blast-radius will be incomplete.")

    return {
        "assets": sorted(assets, key=lambda a: a["path"])[:4000],
        "assetCount": len(assets),
        "counts": dict(counts),
        "languages": dict(languages),
        "warnings": missing_hints,
        "relationships": relationships,
        "analyzers": sorted(active_analyzers),
    }
