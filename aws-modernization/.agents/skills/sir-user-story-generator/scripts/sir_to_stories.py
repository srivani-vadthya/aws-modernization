#!/usr/bin/env python3
"""Build the Epic > Feature > User Story scaffold from Semantic IR (SIR) contracts.

The scaffold is mechanical on purpose: every business rule becomes a story, so nothing is dropped, and every
story carries a `trace` back to the legacy lines. The wording is template text (`narrativeSource: "template"`)
that the agent (or the app's LLM pass) then rewrites in business language, without touching the trace.

Usage:
    python sir_to_stories.py <input.json> --out backlog.json --markdown backlog.md \
        [--epic "Claims"] [--persona "claims adjuster"] [--only SIR-002]

<input.json> may be an engagement.json (reads seed.semantic_ir), {"semantic_ir": [...]}, a list of SIRs, or a
single SIR object. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backlog_model as bm  # noqa: E402


def load_sirs(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("semantic_ir"), list):
            return data["semantic_ir"]
        seed = data.get("seed")
        if isinstance(seed, dict) and isinstance(seed.get("semantic_ir"), list):
            return seed["semantic_ir"]
        if "rules" in data and "id" in data:
            return [data]
    raise ValueError("input has no Semantic IR: expected a list, {'semantic_ir': [...]}, an engagement, or one SIR")


def _is_plumbing(rule: dict) -> bool:
    return rule.get("kind") == "legacy_plumbing_pruned" or "plumbing" in str(rule.get("classification", "")).lower()


def _is_core(rule: dict) -> bool:
    return str(rule.get("trustBoundary", "")).startswith("Deterministic")


def _first_upper(text: str) -> str:
    text = str(text).strip()
    return text[:1].upper() + text[1:]


def _first_lower(text: str) -> str:
    text = str(text).strip().rstrip(".")
    return text[:1].lower() + text[1:]


def _title(statement: str, limit: int = 90) -> str:
    t = _first_upper(str(statement).strip().rstrip("."))
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def module_title(module: str) -> str:
    return str(module).replace("_", " ").replace("-", " ").title()


def _rule_story(sir: dict, rule: dict, n: int, persona: str) -> dict:
    core = _is_core(rule)
    statement = str(rule.get("statement", "")).strip()
    legacy = rule.get("legacyLines", "")
    return {
        "id": f"US-{sir['id']}-{n:02d}",
        "type": "functional",
        "title": _title(statement),
        "narrative": {"asA": persona, "iWant": f"the modernized service to honour this legacy rule: {statement.rstrip('.')}",
                      "soThat": "the legacy behaviour is preserved exactly in the modernized service"},
        "description": (f"Legacy rule {rule.get('ruleId')} ({rule.get('classification') or 'business rule'}) "
                        f"at {legacy}."),
        "acceptanceCriteria": [
            (f"Scenario: {_title(statement, 70)}\n"
             f"  Given the legacy rule {rule.get('ruleId')} applies\n"
             f"  When the modernized service handles the request\n"
             f"  Then the service applies: {statement.rstrip('.')}"),
            (f"Scenario: Parity with legacy behaviour at {legacy}\n"
             f"  Given the same input is replayed against the legacy code and the modernized service\n"
             f"  When both complete\n"
             f"  Then the observable outcome is identical"),
        ],
        "storyPoints": 5 if core else 3,
        "priority": "Must" if core else "Should",
        "labels": ["legacy-parity"] if core else [],
        "narrativeSource": "template",
        "trustBoundary": rule.get("trustBoundary", ""),
        "classification": rule.get("classification", ""),
        "trace": {"sirId": sir["id"], "ruleId": rule.get("ruleId"), "ruleIds": [rule.get("ruleId")],
                  "legacyLines": legacy, "snippet": rule.get("snippet", ""), "astNode": rule.get("astNode", "")},
    }


def _flow_story(sir: dict, rules: list[dict], persona: str) -> dict:
    states = [s.strip() for s in str(sir.get("stateMachine", "")).split("->") if s.strip()]
    required = [i["name"] for i in sir.get("inputs", []) if i.get("required")]
    effects = sir.get("sideEffects") or []
    ac = [(f"Scenario: {sir['name']} completes its state flow\n"
           f"  Given the request supplies {', '.join(required) or 'its inputs'}\n"
           f"  When the process runs\n"
           f"  Then it moves through {' → '.join(states) or 'its states in order'}")]
    if effects:
        ac.append("Scenario: Side effects are applied once the flow completes\n"
                  "  Given the process has completed successfully\n"
                  "  When the results are inspected\n"
                  "  Then " + "; ".join(str(e).rstrip(".") for e in effects))
    first = rules[0] if rules else {}
    return {
        "id": f"US-{sir['id']}-FLOW",
        "type": "flow",
        "title": f"Run {sir['name']} end to end",
        "narrative": {"asA": persona, "iWant": f"{_first_lower(sir['name'])} to run through every step in order",
                      "soThat": "each step completes and its side effects are applied"},
        "description": sir.get("summary", ""),
        "acceptanceCriteria": ac,
        "storyPoints": 5, "priority": "Must", "labels": ["flow"], "narrativeSource": "template",
        "trustBoundary": "", "classification": "State flow",
        "trace": {"sirId": sir["id"], "ruleId": None, "ruleIds": [r.get("ruleId") for r in rules],
                  "legacyLines": first.get("legacyLines", ""), "snippet": "", "astNode": first.get("astNode", "")},
    }


def _enabler_story(sir: dict, plumbing: list[dict]) -> dict:
    first = plumbing[0]
    return {
        "id": f"US-{sir['id']}-ENB",
        "type": "enabler",
        "title": f"Replace legacy plumbing in {sir['name']}",
        "narrative": {"asA": "platform engineer",
                      "iWant": f"the {len(plumbing)} legacy infrastructure call(s) replaced by cloud-framework equivalents",
                      "soThat": "the business logic runs without the legacy runtime"},
        "description": "Pruned plumbing: " + "; ".join(f"{r.get('ruleId')} {r.get('statement')}" for r in plumbing),
        "acceptanceCriteria": [
            "Scenario: Legacy plumbing is no longer required\n"
            "  Given the modernized service is deployed\n"
            "  When the flow runs\n"
            "  Then none of the pruned legacy calls are executed and behaviour is unchanged"],
        "storyPoints": 3, "priority": "Could", "labels": ["enabler"], "narrativeSource": "template",
        "trustBoundary": first.get("trustBoundary", ""), "classification": "Legacy plumbing",
        "trace": {"sirId": sir["id"], "ruleId": first.get("ruleId"), "ruleIds": [r.get("ruleId") for r in plumbing],
                  "legacyLines": first.get("legacyLines", ""), "snippet": first.get("snippet", ""),
                  "astNode": first.get("astNode", "")},
    }


def build_feature(sir: dict, persona: str) -> dict:
    rules = sir.get("rules", [])
    plumbing = [r for r in rules if _is_plumbing(r)]
    business = [r for r in rules if not _is_plumbing(r)]
    stories = [_rule_story(sir, r, i, persona) for i, r in enumerate(business, 1)]
    stories.append(_flow_story(sir, rules, persona))
    if plumbing:
        stories.append(_enabler_story(sir, plumbing))
    return {
        "id": f"FT-{sir['id']}", "title": sir.get("name", sir["id"]), "description": sir.get("summary", ""),
        "sirId": sir["id"], "stateMachine": sir.get("stateMachine", ""), "sideEffects": list(sir.get("sideEffects", [])),
        "inputs": list(sir.get("inputs", [])), "labels": [], "narrativeSource": "template", "stories": stories,
    }


def build_backlog(sirs: list[dict], *, epic: str | None = None, persona: str | None = None,
                  only: list[str] | None = None, module_names: dict[str, str] | None = None,
                  source: dict | None = None) -> dict:
    wanted = set(only or [])
    selected = [s for s in sirs if not wanted or s.get("id") in wanted]
    if not selected:
        raise ValueError("no SIR contracts selected")
    module_names = module_names or {}
    groups: dict[str, list[dict]] = {}
    for sir in selected:
        groups.setdefault(epic or sir.get("module") or "general", []).append(sir)
    epics = []
    for key, members in groups.items():
        title = epic or module_names.get(key) or module_title(key)
        default_persona = persona or f"{title.lower()} user"
        epics.append({
            "id": f"EP-{bm.slug(key)}", "title": title, "module": key,
            "description": f"Modernized behaviour of the {title} capability, traced to {len(members)} SIR contract(s).",
            "businessOutcome": "", "labels": [bm.slug(key).lower()], "narrativeSource": "template",
            "features": [build_feature(s, default_persona) for s in members],
        })
    return {"schemaVersion": bm.SCHEMA_VERSION, "generatedAt": datetime.now(timezone.utc).isoformat(),
            "source": {"sirIds": [s["id"] for s in selected], **(source or {})},
            "epics": epics, "openQuestions": []}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--out", default="backlog.json")
    ap.add_argument("--markdown")
    ap.add_argument("--epic", help="put every contract under one epic with this name")
    ap.add_argument("--persona")
    ap.add_argument("--only", nargs="*", help="only these SIR ids")
    args = ap.parse_args(argv)
    with open(args.input, encoding="utf-8") as fh:
        sirs = load_sirs(json.load(fh))
    backlog = build_backlog(sirs, epic=args.epic, persona=args.persona, only=args.only)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(backlog, fh, indent=2, ensure_ascii=False)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as fh:
            fh.write(bm.backlog_markdown(backlog))
    c = bm.counts(backlog)
    print(f"{c['epics']} epic(s), {c['features']} feature(s), {c['stories']} stories "
          f"({c['storyPoints']} points) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
