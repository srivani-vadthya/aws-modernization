"""Story-point estimation from business complexity, sized relative to a reference story on the Fibonacci scale.

One story is one business use case (one SIR contract). Technical details (classes, frameworks, coupling, stored
procedures, test tooling, the team's stack skills or AI tooling, and internal calls between pieces of code) are
deliberately NOT considered. A story is sized on what the business asks for, scored 1 (very low) to 5 (very high)
on three factors from what the SIR shows:

* Business rules - business checks to honour, exact calculations that must not change, how many distinct business
  outcomes the use case has, and whether the checks involve money, eligibility or compliance.
* Process scope - distinct business outcomes to verify (records saved, notifications sent, information shown),
  checks that each need a test case, business entities involved, adjacent business workflows affected.
* Business uncertainty - outside parties the process depends on, business intent the legacy system does not
  document, and money/compliance checks that change records (errors have direct business impact).

The sum (3..15) is compared with the reference story (B1 + S2 + U1 = 2 points) and mapped onto Fibonacci
1, 2, 3, 5, 8, 13, 21. 13 is a warning to split, 21 must be split. Standard library only.
"""
from __future__ import annotations

import re

LEVEL_LABEL = {1: "very low", 2: "low", 3: "medium", 4: "high", 5: "very high"}
FACTORS = (("rules", "Business rules"), ("scope", "Process scope"), ("uncertainty", "Business uncertainty"))
# factor sum (3..15) -> Fibonacci points; the reference story (B1 + S2 + U1 = 4) is 2 points
SUM_TO_POINTS = ((3.5, 1), (5.5, 2), (7.5, 3), (9.5, 5), (11.5, 8), (13.5, 13), (99.0, 21))
REFERENCE = {"title": "Look up one business record",
             "description": "Show one existing record, no business conditions, nothing changed, no outside parties.",
             "rules": 1, "scope": 2, "uncertainty": 1, "points": 2}

# business-critical vocabulary, matched on words (identifiers are split first): money, eligibility, compliance
_CRITICAL = re.compile(r"\b(amount|balance|charge|commission|discount|due|fee|interest|payment|paid|unpaid|penalt\w*|"
                       r"premium|price|pricing|rate|rebate|refund|tax\w*|vat|total|audit|complian\w*|consent|"
                       r"eligib\w*|regulat\w*|approv\w*|limit|threshold)\b", re.I)
_ENTITY = re.compile(r"^(?:Reads|Persists changes to|Calls external dependency|Delegates to|Calls)\s+([\w.<>]+)")
_LOOKUP = ("Status", "Type")   # reference data looked up along the way, not a business record of its own


def is_branch(rule: dict) -> bool:
    """A guard / decision line (old SIRs made each one a rule). It is a check inside a use case, not a rule."""
    return (str(rule.get("astNode", "")).endswith(":BRANCH")
            or str(rule.get("statement", "")).startswith(("Branches on", "Validates the request")))


def conditions(rule: dict) -> list[str]:
    if rule.get("conditions"):
        return [str(c) for c in rule["conditions"]]
    return [str(rule.get("statement", "")).removeprefix("Branches on: ").strip()]


def checks(rules: list[dict]) -> list[str]:
    """The distinct business checks of a use case ('return ...' / 'throw ...' lines are what a check does when it
    fails, not checks of their own)."""
    out = [c.strip() for r in rules if rule_kind(r) == "check" for c in conditions(r)]
    return list(dict.fromkeys(c for c in out if c and not c.startswith(("return", "throw"))))


def is_core(rule: dict) -> bool:
    return str(rule.get("trustBoundary", "")).startswith("Deterministic")


def rule_kind(rule: dict) -> str:
    """logic | check | write | external | read | internal | rule. 'logic' = a business decision with its outcome
    (from the C# syntax tree); 'internal' = one piece of code calling another."""
    node, cls = str(rule.get("astNode", "")), str(rule.get("classification", ""))
    stmt = str(rule.get("statement", ""))
    if rule.get("logic") or node.endswith(":DECIDES"):
        return "logic"
    if is_branch(rule):
        return "check"
    if node.endswith(":WRITES") or cls == "State Mutation":
        return "write"
    if node.endswith(":INVOKES_EXTERNAL") or cls == "External Integration":
        return "external"
    if node.endswith(":READS") or cls == "Data Retrieval":
        return "read"
    if cls == "Orchestration" or node.endswith(":CALLS") or stmt.startswith(("Delegates to", "Calls ")):
        return "internal"
    return "rule"


def entity(rule: dict) -> str | None:
    m = _ENTITY.match(str(rule.get("statement", "")))
    return m.group(1).split(".")[0] if m else None


def json_text(actions: list[dict]) -> str:
    """The words of a rule's actions (targets, values, errors), for spotting money / compliance vocabulary."""
    return " ".join(words(str(v)) for a in actions for k, v in a.items() if k != "type" and isinstance(v, str))


def words(identifier: str) -> str:
    """'premiumFromParticular' -> 'premium from particular'."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|_", " ", str(identifier)).strip().lower()


def to_points(total: float) -> int:
    return next(p for limit, p in SUM_TO_POINTS if total <= limit)


def _level(value: float) -> int:
    return max(1, min(5, int(round(value))))


def _bucket(value: float, edges: tuple) -> int:
    """1 + number of edges the value is above, e.g. edges (1, 3, 6, 10) -> 1..5."""
    return 1 + sum(1 for e in edges if value > e)


def _undocumented_intent(assessment: dict | None) -> list[str]:
    """Only the business side of the legacy assessment: intent the legacy system leaves unexplained."""
    return [f["finding"] for f in (assessment or {}).get("factors", [])
            if f.get("category") == "unknowns" and f.get("points")]


def _factor(level: int, evidence: list[str]) -> dict:
    return {"level": level, "label": LEVEL_LABEL[level], "evidence": evidence}


# --------------------------------------------------------------------------- one use case = one story

def score_use_case(rules: list[dict], assessment: dict | None = None) -> dict:
    """Score one business use case from its rules (plumbing already removed). Internal calls are ignored."""
    by_kind: dict[str, list[dict]] = {}
    for r in rules:
        by_kind.setdefault(rule_kind(r), []).append(r)
    decisions = checks(rules)
    writes, externals = by_kind.get("write", []), by_kind.get("external", [])
    reads, other = by_kind.get("read", []), by_kind.get("rule", [])
    logic = by_kind.get("logic", [])
    outcomes = list(dict.fromkeys(str(r.get("statement", "")) for r in writes + externals + other))
    shows_only = not outcomes and bool(reads) and not logic
    entities = {e for r in writes + reads if (e := entity(r)) and not e.endswith(_LOOKUP)}
    calcs = [r for r in other if is_core(r)]
    logic_text = " ".join(words(str(p.get("code", ""))) + " " + json_text(r["logic"]["then"])
                          for r in logic for p in r["logic"].get("when", []) or [{}])
    critical = bool(_CRITICAL.search(" ".join(words(c) for c in decisions) + " " + logic_text
                                     + " " + " ".join(str(r.get("statement", "")) for r in other)))
    # only a use case that changes records can break the workflows that share them
    changes = bool(writes) or any(a.get("type") in ("data", "set") for r in logic for a in r["logic"]["then"])
    adjacent = ((assessment or {}).get("regressionScope") or []) if changes else []

    b, b_ev = 1, []
    if logic:       # business decisions read from the code: size on how many distinct rules there are
        if len(logic) >= 4:
            b += 1 if len(logic) < 8 else 2
        b_ev.append(f"{len(logic)} business rule(s), each a decision with its own outcome")
    elif len(decisions) >= 3:
        b += 1 if len(decisions) < 6 else 2
        b_ev.append(f"{len(decisions)} business checks to honour")
    if calcs:
        b += 1
        b_ev.append(f"{len(calcs)} exact calculation(s) or policy rule(s) that must not change")
    if len(outcomes) >= 4:
        b += 1
        b_ev.append(f"{len(outcomes)} distinct business outcomes")
    if critical:
        b += 1
        b_ev.append("checks or rules on money, eligibility or compliance")
    if not b_ev:
        b_ev = [f"{len(decisions)} simple business check(s)" if decisions else "no business checks"]

    n_out = len(outcomes) or (1 if shows_only else 0)
    if logic:       # each business rule is one acceptance case; records changed are already in `writes`
        units = (len(logic) * 0.5 + (1 if changes else 0) + (1 if len(entities) >= 3 else 0)
                 + min(2, (len(adjacent) + 1) // 2) + len({entity(r) for r in externals}))
        s_ev = [f"{len(logic)} business rule(s), each an acceptance case to verify"]
    else:
        units = (n_out + len(decisions) * 0.5 + (1 if writes else 0) + (1 if len(entities) >= 3 else 0)
                 + min(2, (len(adjacent) + 1) // 2))
        s_ev = ["shows information only" if shows_only else f"{n_out} business outcome(s) to verify"]
        if decisions:
            s_ev.append(f"{len(decisions)} check(s), each needing a test case")
    s = _bucket(units, (1, 3, 6, 10))
    if writes:
        s_ev.append("changes business records")
    if len(entities) >= 3:
        s_ev.append(f"involves {len(entities)} business entities ({', '.join(sorted(entities))})")
    if adjacent:
        s_ev.append(f"{len(adjacent)} adjacent business workflow(s) must keep working")

    u, u_ev = 1, []
    if externals:
        u += 1
        parties = {entity(r) or str(r.get("statement")) for r in externals}
        u_ev.append(f"depends on {len(parties)} outside part{'y' if len(parties) == 1 else 'ies'}")
    unknown = _undocumented_intent(assessment)
    if unknown:
        u += 1
        u_ev.append(f"business intent not documented in the legacy system ({unknown[0]})")
    if critical and changes:
        u += 1
        u_ev.append("money or compliance checks change records: errors have direct business impact")
    if not u_ev:
        u_ev = ["business behaviour is fully known; no outside parties"]
    return _result(_level(b), b_ev, _level(s), s_ev, _level(u), u_ev)


def _result(b, b_ev, s, s_ev, u, u_ev) -> dict:
    total = b + s + u
    return {"rules": _factor(b, b_ev), "scope": _factor(s, s_ev), "uncertainty": _factor(u, u_ev),
            "factorSum": total, "points": to_points(total),
            "reference": (f"Relative to the reference story '{REFERENCE['title']}' "
                          f"(B{REFERENCE['rules']} + S{REFERENCE['scope']} + U{REFERENCE['uncertainty']} = "
                          f"{REFERENCE['points']} points)"),
            "notes": []}


def pick_reference(stories: list[dict]) -> dict | None:
    """The story closest to the reference profile (B1 S2 U1): the team's anchor for relative sizing."""
    target = (REFERENCE["rules"], REFERENCE["scope"], REFERENCE["uncertainty"])
    scored = [(sum(abs(s["estimation"][k]["level"] - t) for (k, _), t in zip(FACTORS, target)), s["id"], s)
              for s in stories if s.get("estimation")]
    return min(scored)[2] if scored else None


def rollup(node: dict, stories: list[dict]) -> dict:
    node["estimation"] = {"points": sum(s["storyPoints"] for s in stories)}
    return node["estimation"]
