"""Score an AKG against a hand-checked reference graph, per edge type.

Reference format (JSON):

    {
      "closedSources": ["IMS.WebMvc.Controllers.InvoiceApiController"],   # optional
      "edges": [
        {"kind": "ACCESSES_DATA", "source": "...InvoiceApiController", "target": "IMS.Entities.Invoice"},
        ...
      ]
    }

Recall is measured over every reference edge. Precision needs to know which produced
edges the reference *could* have listed: by default that is every produced edge whose
(kind, source) appears in the reference; `closedSources` declares sources whose edges the
reference lists exhaustively for every kind it covers.

CLI:  python -m app.dotnet_akg.evaluate --root <solution dir> --reference ref.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def score(graph: dict, reference: dict) -> dict:
    produced = {(e["kind"], e["source"], e["target"]) for e in graph["edges"]}
    expected = {(e["kind"], e["source"], e["target"]) for e in reference["edges"]}
    closed = set(reference.get("closedSources", []))
    ref_kinds = {k for k, _, _ in expected}
    ref_scope = {(k, s) for k, s, _ in expected} | {(k, s) for k in ref_kinds for s in closed}

    per_kind: dict[str, dict] = {}
    for kind in sorted(ref_kinds):
        exp = {x for x in expected if x[0] == kind}
        got_in_scope = {x for x in produced if x[0] == kind and (x[0], x[1]) in ref_scope}
        tp = exp & got_in_scope
        per_kind[kind] = {
            "expected": len(exp),
            "found": len(tp),
            "produced_in_scope": len(got_in_scope),
            "precision": round(len(tp) / len(got_in_scope), 3) if got_in_scope else (1.0 if not exp else 0.0),
            "recall": round(len(tp) / len(exp), 3) if exp else 1.0,
            "missing": sorted("{} -> {}".format(s, t) for _, s, t in exp - got_in_scope),
            "unexpected": sorted("{} -> {}".format(s, t) for _, s, t in got_in_scope - exp),
        }
    return per_kind


def regression_checks(graph: dict) -> list[str]:
    """Invariants that must hold for any codebase. Returns a list of violations."""
    problems: list[str] = []
    internal = {n["id"] for n in graph["nodes"] if n["type"] in {"program", "entity"}}
    for e in graph["edges"]:
        if not e.get("file") or not e.get("line") or not e.get("rule_id"):
            problems.append(f"edge without location/rule: {e['id']}")
    for n in graph["nodes"]:
        if n["type"] == "external" and n["id"].split(":", 1)[1] in internal:
            problems.append(f"external node for a type defined in the solution: {n['id']}")
        if n["id"].startswith("external:") and n["type"] != "external":
            problems.append(f"node labelled external but typed {n['type']}: {n['id']}")
        if n["type"] == "event" and not any(e["kind"] == "EMITS_EVENT" and e["target"] == n["id"]
                                            for e in graph["edges"]):
            problems.append(f"event node without a publisher call: {n['id']}")
    for row in graph.get("dataLineage", []):
        if not row.get("file") or not row.get("line"):
            problems.append(f"lineage row without source location: {row['id']}")
        if row.get("source") not in internal:
            problems.append(f"lineage row whose source type is not in the solution: {row['id']}")
    for e in graph["edges"]:
        if e["kind"] == "CALLS" and e["source"] == e["target"]:
            problems.append(f"self-call edge: {e['id']}")
    return problems


def format_report(per_kind: dict) -> str:
    lines = [f"{'edge kind':<20} {'expected':>8} {'found':>6} {'precision':>9} {'recall':>7}"]
    for kind, r in per_kind.items():
        lines.append(f"{kind:<20} {r['expected']:>8} {r['found']:>6} {r['precision']:>9.3f} {r['recall']:>7.3f}")
        for m in r["missing"][:10]:
            lines.append(f"    missing    {m}")
        for u in r["unexpected"][:10]:
            lines.append(f"    unexpected {u}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from . import build_dotnet_akg
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--min-recall", type=float, default=0.0)
    ap.add_argument("--min-precision", type=float, default=0.0)
    args = ap.parse_args(argv)
    graph = build_dotnet_akg(Path(args.root))
    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    per_kind = score(graph, reference)
    print(format_report(per_kind))
    problems = regression_checks(graph)
    for p in problems:
        print("REGRESSION:", p)
    failed = problems or any(r["recall"] < args.min_recall or r["precision"] < args.min_precision
                             for r in per_kind.values())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
