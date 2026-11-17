"""Codebase walker — discovers and dispatches every legacy .NET + TS file."""
from __future__ import annotations
import os
from pathlib import Path
from .models import AstFile
from .parsers import parse_csharp, parse_vb, parse_typescript, parse_config

SKIP_DIRS = {".git", "node_modules", "bin", "obj", ".github", "Migrations", "migrations"}

# Maps file suffix (lowercased) → parser function.
# Order matters for compound suffixes: check longest match first.
_SUFFIX_MAP: dict[str, object] = {
    # C# variants — all route through parse_csharp (lang is derived inside)
    ".aspx.cs":  parse_csharp,
    ".ascx.cs":  parse_csharp,
    ".asmx.cs":  parse_csharp,
    ".svc.cs":   parse_csharp,
    ".asax.cs":  parse_csharp,
    ".cs":       parse_csharp,
    # VB.NET variants
    ".aspx.vb":  parse_vb,
    ".ascx.vb":  parse_vb,
    ".vb":       parse_vb,
    # TypeScript / TSX
    ".tsx":      parse_typescript,
    ".ts":       parse_typescript,
    # XML config
    "web.config":  parse_config,
    "app.config":  parse_config,
}


def _parser_for(path: Path):
    name_lower = path.name.lower()
    # Exact filename match (web.config, app.config)
    if name_lower in _SUFFIX_MAP:
        return _SUFFIX_MAP[name_lower]
    # Compound suffix match (.aspx.cs, .svc.cs, …)
    for suffix, parser in _SUFFIX_MAP.items():
        if suffix.startswith(".") and "." in suffix[1:] and name_lower.endswith(suffix):
            return parser
    # Simple suffix match
    ext = path.suffix.lower()
    return _SUFFIX_MAP.get(ext)


def walk_codebase(root: Path) -> list[AstFile]:
    results: list[AstFile] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            fpath  = Path(dirpath) / fname
            parser = _parser_for(fpath)
            if parser is None:
                continue
            rel = str(fpath.relative_to(root)).replace("\\", "/")
            try:
                results.append(parser(fpath, rel))
            except Exception as exc:
                print(f"  [WARN] {rel}: {exc}")
    return results
