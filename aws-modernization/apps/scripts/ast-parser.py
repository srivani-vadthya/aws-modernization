"""
IMS AST Parser — CLI entry point.

Usage:
    python scripts/ast-parser.py --root . --output artifacts/ast-output.json

All parsing logic lives in scripts/ims_ast/.
Import the package directly for programmatic use:

    from ims_ast import walk_codebase, build_summary
"""
import sys
import json
import argparse
from pathlib import Path
from dataclasses import asdict

# Allow `python scripts/ast-parser.py` from the repo root
sys.path.insert(0, str(Path(__file__).parent))

from ims_ast import walk_codebase, build_summary


def main() -> None:
    ap = argparse.ArgumentParser(description="IMS AST Parser")
    ap.add_argument("--root",   default=".", help="Workspace root (default: current dir)")
    ap.add_argument("--output", default="artifacts/ast-output.json", help="Output JSON path")
    args = ap.parse_args()

    root   = Path(args.root).resolve()
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Scanning: {root}")
    files   = walk_codebase(root)
    summary = build_summary(files)

    result = {
        "meta": {
            "engine":       "IMS AST Parser v2.0",
            "root":         str(root),
            "languages":    ["csharp", "webforms", "wcf", "asmx", "vb", "typescript", "config"],
            "capabilities": list(summary["by_capability"].keys()),
        },
        "summary": summary,
        "files":   [asdict(af) for af in files],
    }

    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nOutput: {output}")

    print(f"\n{'Capability':<42} {'Files':>6} {'LOC':>7} {'Symbols':>8} {'Debt':>6}")
    print("-" * 72)
    for cap, data in summary["by_capability"].items():
        print(f"{cap:<42} {data['files']:>6} {data['loc']:>7} {data['symbols']:>8} {data['tech_debt']:>6}")
    print("-" * 72)
    print(f"{'TOTAL':<42} {summary['total_files']:>6} {summary['total_loc']:>7} "
          f"{summary['total_symbols']:>8} {summary['total_tech_debt_flags']:>6}")

    if summary["arch_flag_totals"]:
        print("\nLegacy architecture markers detected:")
        for flag, count in sorted(summary["arch_flag_totals"].items(), key=lambda x: -x[1]):
            print(f"  {count:>4}x  {flag}")


if __name__ == "__main__":
    main()
