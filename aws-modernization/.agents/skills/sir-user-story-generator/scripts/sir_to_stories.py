#!/usr/bin/env python3
"""Build the Epic > Feature > User Story scaffold from Semantic IR (SIR) contracts.

The scaffold is mechanical on purpose: the business rules of one legacy method become one story (each rule an
acceptance scenario), so nothing is dropped and a branch is never sized as a story of its own; every story
carries a `trace` (all its `ruleIds`) back to the legacy lines. The wording is template text (`narrativeSource: "template"`)
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
import estimation as est_mod  # noqa: E402


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


# --------------------------------------------------------------------------- stories = pieces of behaviour
# A branch is a decision point inside a behaviour, and a rule is a requirement of a behaviour: neither is a story.
# A story is the behaviour of one legacy method (its rules become acceptance scenarios), sized by estimation.py
# on Complexity, Amount of Work and Risk & Uncertainty relative to a reference story.

OPS_PER_STORY = 6   # + 1 validation scenario + 1 parity scenario keeps a story at <= 8 acceptance scenarios
AI_CAPABILITY = est_mod.AI_CAPABILITY
DEFAULT_CAPABILITY = est_mod.DEFAULT_CAPABILITY
MAX_EPIC_EFFICIENCY = est_mod.MAX_EPIC_EFFICIENCY
rollup = est_mod.rollup


def _behaviour_key(rule: dict) -> str:
    """The legacy method a rule lives in: rules of one method are one piece of behaviour to build and test."""
    node = str(rule.get("astNode") or "")
    if node.count(":") >= 2:
        return node.rsplit(":", 2)[0]
    lines = str(rule.get("legacyLines") or "")
    return lines.split("#", 1)[0] or str(rule.get("ruleId"))


def _behaviour_name(key: str) -> str:
    return key.split(":", 1)[-1].rsplit("/", 1)[-1] or key


def group_rules(rules: list[dict]) -> list[tuple[str, list[dict]]]:
    """Rules grouped by legacy method (first-seen order). Branch/guard rules stay with the first part; the
    operations are split into parts of OPS_PER_STORY so each story keeps <= 8 acceptance scenarios."""
    groups: dict[str, list[dict]] = {}
    for r in rules:
        groups.setdefault(_behaviour_key(r), []).append(r)
    out = []
    for key, members in groups.items():
        guards = [r for r in members if est_mod.is_branch(r)]
        ops = [r for r in members if not est_mod.is_branch(r)]
        chunks = [ops[i:i + OPS_PER_STORY] for i in range(0, len(ops), OPS_PER_STORY)] or [[]]
        chunks[0] = guards + chunks[0]
        for i, chunk in enumerate(chunks, 1):
            out.append((_behaviour_name(key) + (f" (part {i} of {len(chunks)})" if len(chunks) > 1 else ""), chunk))
    return out


def _behaviour_story(sir: dict, name: str, rules: list[dict], n: int, persona: str) -> dict:
    """One story per piece of legacy behaviour; its guard conditions are one scenario, each operation another."""
    guards = [r for r in rules if est_mod.is_branch(r)]
    ops = [r for r in rules if not est_mod.is_branch(r)]
    core = [r for r in rules if _is_core(r)]
    first = (core or ops or rules)[0]
    legacy = ", ".join(dict.fromkeys(str(r.get("legacyLines", "")) for r in rules if r.get("legacyLines")))
    ac = []
    if guards:
        conds = [c for g in guards for c in est_mod.conditions(g)]
        ac.append(f"Scenario: The request is validated before {name} runs\n"
                  f"  Given the legacy validation rule(s) {', '.join(str(g.get('ruleId')) for g in guards)} apply\n"
                  f"  When the modernized service receives the request\n"
                  f"  Then it enforces the same conditions: " + "; ".join(conds))
    ac += [(f"Scenario: {_title(r.get('statement', ''), 70)}\n"
            f"  Given the legacy rule {r.get('ruleId')} applies\n"
            f"  When the modernized service handles the request\n"
            f"  Then the service applies: {str(r.get('statement', '')).strip().rstrip('.')}") for r in ops]
    ac.append(f"Scenario: Parity with legacy behaviour of {name}\n"
              f"  Given the same input is replayed against the legacy code and the modernized service\n"
              f"  When both complete\n"
              f"  Then the observable outcome is identical")
    classes = list(dict.fromkeys(str(r.get("classification") or "business rule") for r in rules))
    what = "; ".join(f"{r.get('ruleId')} {str(r.get('statement', '')).strip().rstrip('.')}" for r in rules)
    return {
        "id": f"US-{sir['id']}-{n:02d}",
        "type": "functional",
        "title": (f"Preserve the behaviour of {name}" if len(ops) != 1 or guards
                  else _title(ops[0].get("statement", ""))),
        "narrative": {"asA": persona,
                      "iWant": f"the modernized service to behave like the legacy {name}",
                      "soThat": "the legacy behaviour is preserved exactly in the modernized service"},
        "description": f"Legacy behaviour {name} ({', '.join(classes)}): {what}. Legacy lines: {legacy}.",
        "acceptanceCriteria": ac,
        "storyPoints": 1,   # set by _estimate_feature
        "priority": "Must" if core else "Should",
        "labels": ["legacy-parity"] if core else [],
        "narrativeSource": "template",
        "trustBoundary": first.get("trustBoundary", ""),
        "classification": ", ".join(classes),
        "trace": {"sirId": sir["id"], "ruleId": first.get("ruleId"), "ruleIds": [r.get("ruleId") for r in rules],
                  "legacyLines": legacy, "snippet": "\n".join(str(r.get("snippet", "")) for r in rules)[:2000],
                  "astNode": first.get("astNode", "")},
    }


def _estimate_feature(sir: dict, stories: list[dict], rules_by_story: dict[str, list[dict]],
                      team: dict | None, level: str) -> None:
    a = sir.get("legacyAssessment")
    for s in stories:
        if s["type"] == "functional":
            e = est_mod.score_behaviour(rules_by_story[s["id"]], a, team)
        elif s["type"] == "flow":
            e = est_mod.score_flow(sir, a, team)
        else:
            e = est_mod.score_enabler(rules_by_story[s["id"]], a, team)
        e["legacyFactors"] = [{k: f[k] for k in ("category", "finding", "evidence", "points")}
                              for f in sorted((f for f in (a or {}).get("factors", []) if f.get("points")),
                                              key=lambda f: -f["points"])[:4]] if s["type"] != "enabler" else []
        est_mod.ai_assist(e, level)
        s["estimation"] = e
        s["storyPoints"] = e["aiPoints"]
        if e["risk"]["level"] >= 3 and s["type"] != "enabler":
            s["labels"] = sorted(set(s.get("labels", [])) | {"legacy-risk"})


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
    a = sir.get("legacyAssessment") or {}
    if a.get("regressionScope"):
        ac.append("Scenario: Adjacent workflows are not regressed\n"
                  f"  Given the workflows {', '.join(a['regressionScope'][:4])} share this data\n"
                  "  When the modernized flow is deployed\n"
                  "  Then their behaviour is unchanged")
    return {
        "id": f"US-{sir['id']}-FLOW",
        "type": "flow",
        "title": f"Run {sir['name']} end to end",
        "narrative": {"asA": persona, "iWant": f"{_first_lower(sir['name'])} to run through every step in order",
                      "soThat": "each step completes and its side effects are applied"},
        "description": sir.get("summary", ""),
        "acceptanceCriteria": ac,
        "definitionOfDone": list(a.get("definitionOfDone", [])),
        "storyPoints": 1, "priority": "Must", "labels": ["flow"], "narrativeSource": "template",
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
        "storyPoints": 1, "priority": "Could", "labels": ["enabler"], "narrativeSource": "template",
        "trustBoundary": first.get("trustBoundary", ""), "classification": "Legacy plumbing",
        "trace": {"sirId": sir["id"], "ruleId": first.get("ruleId"), "ruleIds": [r.get("ruleId") for r in plumbing],
                  "legacyLines": first.get("legacyLines", ""), "snippet": first.get("snippet", ""),
                  "astNode": first.get("astNode", "")},
    }


def build_feature(sir: dict, persona: str, *, team: dict | None = None, level: str = DEFAULT_CAPABILITY) -> dict:
    rules = sir.get("rules", [])
    plumbing = [r for r in rules if _is_plumbing(r)]
    business = [r for r in rules if not _is_plumbing(r)]
    stories, rules_by_story = [], {}
    for i, (name, chunk) in enumerate(group_rules(business), 1):
        story = _behaviour_story(sir, name, chunk, i, persona)
        stories.append(story)
        rules_by_story[story["id"]] = chunk
    stories.append(_flow_story(sir, rules, persona))
    if plumbing:
        stories.append(_enabler_story(sir, plumbing))
        rules_by_story[stories[-1]["id"]] = plumbing
    a = sir.get("legacyAssessment")
    _estimate_feature(sir, stories, rules_by_story, team, level)
    return {
        "id": f"FT-{sir['id']}", "title": sir.get("name", sir["id"]), "description": sir.get("summary", ""),
        "sirId": sir["id"], "stateMachine": sir.get("stateMachine", ""), "sideEffects": list(sir.get("sideEffects", [])),
        "inputs": list(sir.get("inputs", [])), "labels": [], "narrativeSource": "template",
        "legacyAssessment": a, "definitionOfDone": list((a or {}).get("definitionOfDone", [])),
        "stories": stories,
    }


def planning_questions(backlog: dict) -> list[dict]:
    """Things the code cannot answer (DB triggers, shared schemas, test environments, patch vs refactor...)."""
    out, seen = [], set()
    for _, feature in bm.iter_features(backlog):
        flow_id = next((s["id"] for s in feature["stories"] if s["type"] == "flow"), None)
        for f in (feature.get("legacyAssessment") or {}).get("factors", []):
            q = f.get("question")
            if q and q not in seen:
                seen.add(q)
                out.append({"id": f"Q-PLAN-{len(out) + 1:02d}", "storyId": flow_id, "question": q})
    return out


def build_backlog(sirs: list[dict], *, epic: str | None = None, persona: str | None = None,
                  only: list[str] | None = None, module_names: dict[str, str] | None = None,
                  source: dict | None = None, ai_capability: str | None = None,
                  team: dict | None = None) -> dict:
    level = str(ai_capability or "").upper()
    assumed = level not in AI_CAPABILITY
    if assumed:
        level = DEFAULT_CAPABILITY
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
            "approach": ("Parity-first migration: a minimal surgical port of the traced behaviour. Refactoring "
                         "(interfaces, breaking up classes, removing static state) is done only where an enabler "
                         "story or a Definition-of-Done item calls for it."),
            "definitionOfDone": ["Acceptance scenarios pass against the modernized service",
                                 "Parity with the legacy behaviour is demonstrated on the same inputs",
                                 "Open planning questions for the feature are answered or accepted as risks"],
            "features": [build_feature(s, default_persona, team=team, level=level) for s in members],
        })
    for e in epics:
        if AI_CAPABILITY[level]:
            est_mod.enforce_epic_cap([s for f in e["features"] for s in f["stories"]])
        for f in e["features"]:
            rollup(f, f["stories"])
        rollup(e, [s for f in e["features"] for s in f["stories"]])
    backlog = {"schemaVersion": bm.SCHEMA_VERSION, "generatedAt": datetime.now(timezone.utc).isoformat(),
               "source": {"sirIds": [s["id"] for s in selected], **(source or {})},
               "estimationModel": {
                   "method": "Complexity + Amount of Work + Risk & Uncertainty (each 1-5), relative to a reference "
                             "story, on Fibonacci 1, 2, 3, 5, 8, 13, 21",
                   "scale": [{"factorSum": f"<= {lim}" if lim < 99 else "> 13.5", "points": p}
                             for lim, p in est_mod.SUM_TO_POINTS],
                   "reference": dict(est_mod.REFERENCE),
                   "capability": level, "multiplier": AI_CAPABILITY[level], "assumed": assumed,
                   "team": dict(team or {}),
                   "storyPointsMean": "AI-assisted points (estimation.aiPoints); estimation.humanPoints is the "
                                      "manual baseline"},
               "epics": epics, "openQuestions": []}
    backlog["openQuestions"] = planning_questions(backlog)
    all_stories = [s for _, _, s in bm.iter_stories(backlog)]
    ref = est_mod.pick_reference(all_stories)
    if ref:
        ref["labels"] = sorted(set(ref.get("labels", [])) | {"reference-story"})
        backlog["estimationModel"]["reference"]["storyId"] = ref["id"]
        backlog["openQuestions"].append({
            "id": "Q-EST-02", "storyId": ref["id"],
            "question": (f"Agree the reference story for relative sizing: {ref['id']} '{ref['title']}' is the closest "
                         f"to the {est_mod.REFERENCE['points']}-point anchor ({est_mod.REFERENCE['description']}). "
                         "Replace it with a story the team has already delivered if one is a better anchor.")})
    if not team or any(team.get(k) is None for k in ("legacyStackFamiliar", "targetStackFamiliar", "builtSimilarBefore")):
        backlog["openQuestions"].append({
            "id": "Q-EST-03", "storyId": None,
            "question": "Team context for the risk factor: does the team know the legacy stack, the target stack, "
                        "and has it built something similar before? (Unknown answers add no risk; confirm them.)"})
    if assumed:
        backlog["openQuestions"].append({
            "id": "Q-EST-01", "storyId": None,
            "question": f"Confirm the team's AI capability level (assumed {level}: AI agent with SIR/AST context). "
                        "L0 no AI tools, L1 autocomplete/chat only, L3 adds an automated parity harness."})
    return backlog


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--out", default="backlog.json")
    ap.add_argument("--markdown")
    ap.add_argument("--epic", help="put every contract under one epic with this name")
    ap.add_argument("--persona")
    ap.add_argument("--only", nargs="*", help="only these SIR ids")
    ap.add_argument("--ai-capability", choices=sorted(AI_CAPABILITY),
                    help="team AI capability level for AI-assisted points (default L2, recorded as assumed)")
    ap.add_argument("--team-knows-legacy", choices=("yes", "no"))
    ap.add_argument("--team-knows-target", choices=("yes", "no"))
    ap.add_argument("--team-built-similar", choices=("yes", "no"))
    args = ap.parse_args(argv)
    yn = {"yes": True, "no": False, None: None}
    team = {"legacyStackFamiliar": yn[args.team_knows_legacy], "targetStackFamiliar": yn[args.team_knows_target],
            "builtSimilarBefore": yn[args.team_built_similar]}
    with open(args.input, encoding="utf-8") as fh:
        sirs = load_sirs(json.load(fh))
    backlog = build_backlog(sirs, epic=args.epic, persona=args.persona, only=args.only,
                            ai_capability=args.ai_capability, team=team)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(backlog, fh, indent=2, ensure_ascii=False)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as fh:
            fh.write(bm.backlog_markdown(backlog))
    c = bm.counts(backlog)
    print(f"{c['epics']} epic(s), {c['features']} feature(s), {c['stories']} stories "
          f"({c['storyPoints']} AI-assisted points, {c['humanPoints']} manual baseline, "
          f"{round(c['aiEfficiency'] * 100)}% AI efficiency) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
