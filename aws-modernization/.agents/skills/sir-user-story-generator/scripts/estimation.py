"""Story-point estimation from evidence: Complexity, Amount of Work, Risk & Uncertainty, sized relative to a
reference story on the Fibonacci scale.

A story is NOT sized from a fixed base (3 or 5) or from how many branches it has. Each story is scored on three
factors, 1 (very low) to 5 (very high), from what the SIR and the legacy assessment actually show:

* Complexity - decision points in the logic, deterministic-core rules (formulas, writes, external calls),
  how many components are touched, legacy coupling and framework paradigm.
* Amount of work - distinct operations to rebuild and test, decisions that each need a test case, data writes,
  refactoring needed to make the code testable.
* Risk & uncertainty - external dependencies, unknowns the code cannot answer (stored procedures, untraced
  calls, undocumented intent), security, and the team's own familiarity with the legacy and target stacks.

The sum (3..15) is compared with the reference story (C1 + W2 + R1 = 2 points) and mapped onto Fibonacci
1, 2, 3, 5, 8, 13, 21. 13 is a warning to split, 21 must be split.

The AI-assisted estimate re-scores the same factors for a team using AI with the SIR/AST as context: AI removes
most of the volume of work, some of the complexity (it reads and explains the legacy code) and almost none of
the risk (answers come from people, vendors and DBAs). Standard library only.
"""
from __future__ import annotations

import re

import backlog_model as bm

LEVEL_LABEL = {1: "very low", 2: "low", 3: "medium", 4: "high", 5: "very high"}
# factor sum (3..15) -> Fibonacci points; the reference story (C1 + W2 + R1 = 4) is 2 points
SUM_TO_POINTS = ((3.5, 1), (5.5, 2), (7.5, 3), (9.5, 5), (11.5, 8), (13.5, 13), (99.0, 21))
REFERENCE = {"title": "Read one record and return it",
             "description": "One data read, no decisions, no writes, no external calls, on a stack the team knows.",
             "complexity": 1, "work": 2, "risk": 1, "points": 2}

AI_CAPABILITY = {"L0": 0.0, "L1": 0.5, "L2": 1.0, "L3": 1.2}   # team working style -> multiplier
DEFAULT_CAPABILITY = "L2"
# share of each factor AI removes at multiplier 1.0
AI_REDUCTION = {"complexity": 0.25, "work": 0.55, "risk": 0.05}
L3_WORK_REDUCTION = 0.65          # an automated parity harness also takes most of the regression testing
MAX_STORY_EFFICIENCY = 0.70
MAX_EPIC_EFFICIENCY = 0.60

RISK_CATEGORIES = ("data", "integration", "security", "unknowns")
_TARGET = re.compile(r"^(?:Reads|Persists changes to|Calls external dependency|Delegates to|Calls)\s+([\w.<>]+)")


def is_branch(rule: dict) -> bool:
    """A guard / decision line (old SIRs made each one a rule). It is a condition of a behaviour, not a rule."""
    return (str(rule.get("astNode", "")).endswith(":BRANCH")
            or str(rule.get("statement", "")).startswith(("Branches on", "Validates the request")))


def conditions(rule: dict) -> list[str]:
    if rule.get("conditions"):
        return [str(c) for c in rule["conditions"]]
    return [str(rule.get("statement", "")).removeprefix("Branches on: ").strip()]


def is_core(rule: dict) -> bool:
    return str(rule.get("trustBoundary", "")).startswith("Deterministic")


def to_points(total: float) -> int:
    return next(p for limit, p in SUM_TO_POINTS if total <= limit)


def _snap_up(value: float) -> int:
    return next((f for f in bm.FIBONACCI if f >= value), bm.FIBONACCI[-1])


def _level(value: float) -> int:
    return max(1, min(5, int(round(value))))


def _bucket(value: float, edges: tuple) -> int:
    """1 + number of edges the value is above, e.g. edges (1, 3, 6, 10) -> 1..5."""
    return 1 + sum(1 for e in edges if value > e)


def _legacy(assessment: dict | None) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in (assessment or {}).get("factors", []):
        if f.get("points"):
            out.setdefault(f["category"], []).append(f)
    return out


def _team(team: dict | None) -> tuple[int, list[str]]:
    team = team or {}
    delta, why = 0, []
    if team.get("legacyStackFamiliar") is False:
        delta, why = delta + 1, why + ["nobody on the team knows the legacy stack well"]
    if team.get("targetStackFamiliar") is False:
        delta, why = delta + 1, why + ["the team is new to the target stack"]
    if team.get("builtSimilarBefore") is True:
        delta, why = delta - 1, why + ["the team has built something similar before"]
    return delta, why


def _factor(level: int, evidence: list[str]) -> dict:
    return {"level": level, "label": LEVEL_LABEL[level], "evidence": evidence}


# --------------------------------------------------------------------------- per story type

def score_behaviour(rules: list[dict], assessment: dict | None, team: dict | None) -> dict:
    """A functional story = the rules of one legacy method."""
    legacy = _legacy(assessment)
    decisions = sum(len(conditions(r)) for r in rules if is_branch(r))
    ops = [r for r in rules if not is_branch(r)]
    core = [r for r in ops if is_core(r)]
    writes = [r for r in ops if str(r.get("astNode", "")).endswith(":WRITES") or r.get("classification") == "State Mutation"]
    externals = [r for r in ops if str(r.get("astNode", "")).endswith(":INVOKES_EXTERNAL")
                 or r.get("classification") == "External Integration"]
    data_ops = [r for r in ops if str(r.get("astNode", "")).endswith((":READS", ":WRITES"))
                or r.get("classification") in ("Data Retrieval", "State Mutation")]
    components = set()
    for r in ops:
        m = _TARGET.match(str(r.get("statement", "")))
        if m:
            components.add(m.group(1).split(".")[0])

    c_ev, c = [], 1
    if decisions >= 3:
        c += 1 if decisions < 6 else 2
        c_ev.append(f"{decisions} decision points in the logic")
    if core:
        c += 1
        c_ev.append(f"{len(core)} deterministic-core rule(s) that must be reproduced exactly")
    if len(components) >= 4:
        c += 1
        c_ev.append(f"touches {len(components)} components ({', '.join(sorted(components)[:4])})")
    if legacy.get("coupling") or legacy.get("framework"):
        c += 1
        c_ev.append("; ".join(f["finding"] for f in (legacy.get("framework", []) + legacy.get("coupling", []))[:2]))
    c = _level(c)

    units = len(ops) + decisions * 0.5 + (1 if writes else 0)
    w = _bucket(units, (1, 3, 6, 10))
    w_ev = [f"{len(ops)} operation(s) to rebuild and test"]
    if decisions:
        w_ev.append(f"{decisions} condition(s), each needing a test case")
    if writes:
        w_ev.append(f"writes data ({len(writes)} write(s)): needs data setup and verification")
    if legacy.get("testability"):
        w += 1
        w_ev.append(legacy["testability"][0]["finding"])
    w = _level(w)

    r, r_ev = 1, []
    if externals:
        r += 1
        r_ev.append(f"depends on {len(externals)} external system(s)")
    relevant = [cat for cat in RISK_CATEGORIES if legacy.get(cat)
                and (cat in ("security", "unknowns") or (cat == "data" and data_ops) or (cat == "integration" and externals))]
    if relevant:
        r += min(2, len(relevant))
        r_ev += [legacy[cat][0]["finding"] for cat in relevant[:2]]
    delta, why = _team(team)
    r, r_ev = r + delta, r_ev + why
    r = _level(r)
    if not r_ev:
        r_ev = ["requirement is fully traced to legacy code; no external dependencies"]
    inputs = _inputs_needed(rules, decisions, legacy if data_ops else {k: v for k, v in legacy.items() if k != "data"},
                            externals)
    return _result(c, c_ev, w, w_ev, r, r_ev, inputs)


def score_flow(sir: dict, assessment: dict | None, team: dict | None) -> dict:
    """The end-to-end story: wiring the steps together, side effects, integration and regression testing."""
    legacy = _legacy(assessment)
    states = [s for s in str(sir.get("stateMachine", "")).split("->") if s.strip()]
    effects = [e for e in sir.get("sideEffects") or [] if not str(e).startswith("No persistent")]
    regression = (assessment or {}).get("regressionScope") or []
    externals = sir.get("integrations") or []

    c, c_ev = 1, [f"{len(states)} steps in the state flow"]
    if len(states) >= 5:
        c += 1 if len(states) < 8 else 2
    if externals:
        c += 1
        c_ev.append(f"{len(externals)} external integration(s) in the flow")
    if legacy.get("framework") or legacy.get("coupling"):
        c += 1
        c_ev.append("; ".join(f["finding"] for f in (legacy.get("framework", []) + legacy.get("coupling", []))[:2]))
    c = _level(c)

    units = len(states) / 2 + len(effects) + len(regression)
    w = _level(_bucket(units, (2, 4, 7, 11)))
    w_ev = [f"end-to-end wiring of {len(states)} steps", f"{len(effects)} side effect(s) to verify"]
    if regression:
        w_ev.append(f"regression of {len(regression)} adjacent workflow(s)")

    r, r_ev = 1, []
    cats = [cat for cat in RISK_CATEGORIES if legacy.get(cat)]
    if cats:
        r += min(3, len(cats))
        r_ev += [legacy[cat][0]["finding"] for cat in cats[:3]]
    questions = [f["question"] for fs in legacy.values() for f in fs if f.get("question")]
    if questions:
        r_ev.append(f"{len(questions)} open planning question(s) the code cannot answer")
    delta, why = _team(team)
    r, r_ev = _level(r + delta), r_ev + why
    if not r_ev:
        r_ev = ["flow fully traced; no external dependencies or unknowns"]
    inputs = ["QA: end-to-end test data for every step"] + (["DBA: confirm stored procedures, triggers and shared tables"]
                                                             if legacy.get("data") else [])
    if regression:
        inputs.append("QA: regression suite for the adjacent workflows")
    return _result(c, c_ev, w, w_ev, r, r_ev, inputs, open_questions=bool(questions))


def score_enabler(plumbing: list[dict], assessment: dict | None, team: dict | None) -> dict:
    legacy = _legacy(assessment)
    c, c_ev = 1, ["mechanical replacement of infrastructure calls"]
    if legacy.get("framework"):
        c += 1
        c_ev.append(legacy["framework"][0]["finding"])
    w = _level(_bucket(len(plumbing), (2, 5, 9)))
    w_ev = [f"{len(plumbing)} legacy infrastructure call(s) to replace"]
    delta, why = _team({k: v for k, v in (team or {}).items() if k == "targetStackFamiliar"})
    r = _level(1 + delta)
    return _result(_level(c), c_ev, w, w_ev, r, why or ["well-understood framework replacement"],
                   ["Platform: target framework equivalents agreed"])


def _inputs_needed(rules: list[dict], decisions: int, legacy: dict, externals: list[dict]) -> list[str]:
    out = []
    owners = {str(r.get("astNode", "")).split(":")[1].split(".")[0] for r in rules if str(r.get("astNode", "")).count(":") >= 2}
    if any(o.endswith("Controller") and "Api" not in o for o in owners):
        out.append("Design: wireframe / mockup of the screen this behaviour serves")
    if decisions >= 3:
        out.append(f"QA: edge cases for the {decisions} conditions")
    if legacy.get("data"):
        out.append("DBA: stored procedures, views or triggers behind this data access")
    if externals:
        out.append("Integration: sandbox and contract for the external dependency")
    return out


def _result(c, c_ev, w, w_ev, r, r_ev, inputs, *, open_questions: bool = False) -> dict:
    total = c + w + r
    return {"complexity": _factor(c, c_ev), "work": _factor(w, w_ev), "risk": _factor(r, r_ev),
            "factorSum": total, "humanPoints": to_points(total),
            "confidence": "high" if r <= 2 else "medium" if r == 3 else "low",
            "reference": (f"Relative to the reference story '{REFERENCE['title']}' "
                          f"(C{REFERENCE['complexity']} + W{REFERENCE['work']} + R{REFERENCE['risk']} = "
                          f"{REFERENCE['points']} points)"),
            "inputsNeeded": inputs, "humanOnly": 2 if (r >= 4 or open_questions) else 1, "notes": []}


# --------------------------------------------------------------------------- AI-assisted

def ai_assist(est: dict, level: str) -> dict:
    """Re-score the factors for a team using AI; returns est with aiPoints/aiEfficiency filled in."""
    mult = AI_CAPABILITY[level]
    human = est["humanPoints"]
    work_red = L3_WORK_REDUCTION if level == "L3" else AI_REDUCTION["work"]
    reduced = {
        "complexity": max(1.0, est["complexity"]["level"] * (1 - AI_REDUCTION["complexity"] * mult)),
        "work": max(1.0, est["work"]["level"] * (1 - work_red * (1.0 if level == "L3" else mult))),
        "risk": max(1.0, est["risk"]["level"] * (1 - AI_REDUCTION["risk"] * mult)),
    }
    if mult:
        ai = to_points(sum(reduced.values()))
        floor = max(est["humanOnly"], _snap_up(human * (1 - MAX_STORY_EFFICIENCY)))
        ai = min(max(ai, floor), human)
    else:
        ai = human
    est.update({"aiFactors": {k: round(v, 2) for k, v in reduced.items()}, "aiPoints": ai, "points": ai,
                "aiEfficiency": round(1 - ai / human, 2) if human else 0.0, "capability": level})
    return est


def enforce_epic_cap(stories: list[dict]) -> None:
    """Never claim more than MAX_EPIC_EFFICIENCY on an epic: give points back to the biggest savings first."""
    human = sum(s["estimation"]["humanPoints"] for s in stories)
    floor = human * (1 - MAX_EPIC_EFFICIENCY)
    for s in sorted(stories, key=lambda s: (-(s["estimation"]["humanPoints"] - s["storyPoints"]), s["id"])):
        if sum(x["storyPoints"] for x in stories) >= floor:
            break
        e = s["estimation"]
        bigger = next((f for f in bm.FIBONACCI if f > s["storyPoints"]), s["storyPoints"])
        if bigger <= e["humanPoints"]:
            e.update(aiPoints=bigger, points=bigger, aiEfficiency=round(1 - bigger / e["humanPoints"], 2))
            e["notes"].append(f"raised to keep the epic within the {round(MAX_EPIC_EFFICIENCY * 100)}% AI-efficiency cap")
            s["storyPoints"] = bigger


def pick_reference(stories: list[dict]) -> dict | None:
    """The story closest to the reference profile (C1 W2 R1): the team's anchor for relative sizing."""
    target = (REFERENCE["complexity"], REFERENCE["work"], REFERENCE["risk"])
    stories = [s for s in stories if s["type"] == "functional"] or stories   # the anchor is business behaviour
    scored = [(sum(abs(a - b) for a, b in zip((s["estimation"]["complexity"]["level"], s["estimation"]["work"]["level"],
                                                 s["estimation"]["risk"]["level"]), target)),
               s["type"] != "functional", s["id"], s) for s in stories if s.get("estimation")]
    return min(scored)[3] if scored else None


def rollup(node: dict, stories: list[dict]) -> dict:
    human = sum((s.get("estimation") or {}).get("humanPoints", s["storyPoints"]) for s in stories)
    ai = sum(s["storyPoints"] for s in stories)
    node["estimation"] = {"humanPoints": human, "aiPoints": ai,
                          "aiEfficiency": round(1 - ai / human, 2) if human else 0.0}
    return node["estimation"]
