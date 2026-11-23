#!/usr/bin/env python3
"""Build the Epic > Feature > User Story scaffold from Semantic IR (SIR) contracts.

One story per business use case (one SIR contract), grouped into features by business area and into epics by
module. Every business rule of the use case is traced on the story (`trace.ruleIds`), so nothing is dropped. The
wording is template text (`narrativeSource: "template"`) that states only what the SIR proves; the agent (or the
app's LLM pass) then rewrites it in business language, without touching the trace.

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
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backlog_model as bm  # noqa: E402
import checks_text as ct  # noqa: E402
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


# --------------------------------------------------------------------------- one use case = one story
# Epic = module, Feature = business area (the part of the use-case name before ':', e.g. "Invoice" in
# "Invoice: Post"), Story = one use case (one SIR contract). Every business rule of the use case is traced on the
# story. Internal calls between pieces of code are technical: they get no acceptance criterion of their own and are
# only cited in the "same result as today" criterion. A use case with nothing but internal calls (e.g. a class
# that wires up repositories) is technical code, not a user story, and is left out. Legacy plumbing is left out too.
#
# The template states only what the SIR proves (records saved, notifications sent, information shown, quoted
# status values). It never guesses what a code condition means: the LLM refinement (or a person) words those.

rollup = est_mod.rollup
DEFAULT_PERSONA = "business user"
MAX_CRITERIA = 16       # a story with more than 8 is flagged for splitting by the validator
_EMAIL = re.compile(r"smtp|e-?mail|mail", re.I)
_SUFFIX = re.compile(r"(Client|Service|Api|Gateway|Proxy|Adapter)$")


def _article(phrase: str) -> str:
    """'an invoice', 'a policy', 'an SOA' (acronyms that start with a vowel sound take 'an')."""
    first = phrase.split(" ", 1)[0]
    vowel = first[:1].lower() in "aeiou" if not first.isupper() else first[:1] in "AEFHILMNORSX"
    return f"{'an' if vowel else 'a'} {phrase}"


def _plural(noun: str) -> str:
    if noun.isupper():
        return noun + "s"
    if noun.endswith("y") and noun[-2:-1] not in "aeiou":
        return noun[:-1] + "ies"
    return noun + ("es" if noun.endswith(("s", "x", "ch", "sh")) else "s")


def _human(identifier: str) -> str:
    """'ParticularType' -> 'particular type'; short names are acronyms: 'Soa' -> 'SOA'."""
    ident = str(identifier).strip()
    return ident.upper() if len(ident) <= 3 else est_mod.words(ident)


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def _first_upper(text: str) -> str:
    text = str(text).strip()
    return text[:1].upper() + text[1:]


def _first_lower(text: str) -> str:
    text = str(text).strip().rstrip(".")
    return text if text[:2].isupper() else text[:1].lower() + text[1:]


def module_title(module: str) -> str:
    return str(module).replace("_", " ").replace("-", " ").title()


def short_id(rule_id: str) -> str:
    """'SIR-001.R12' -> 'R12' (a story only ever cites rules of its own use case)."""
    return str(rule_id).rsplit(".", 1)[-1]


def cite(rule_ids: list) -> str:
    """' (R1, R3-R6)': short ids with consecutive runs collapsed; empty when there is nothing to cite."""
    ids = [short_id(r) for r in dict.fromkeys(rule_ids) if r]
    nums = [int(m.group(1)) for i in ids if (m := re.fullmatch(r"R(\d+)", i))]
    if len(nums) != len(ids):        # ids that are not R<n>: list them as they are
        return f" ({', '.join(ids)})" if ids else ""
    nums, parts, start = sorted(set(nums)), [], None
    for i, n in enumerate(nums):
        start = n if start is None else start
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            parts.append(f"R{start}" if start == n else f"R{start}–R{n}")
            start = None
    return f" ({', '.join(parts)})" if parts else ""


def story_title(narrative: dict) -> str:
    """The story title is the user story itself: 'As a <role>, I want <goal> so that <benefit>'."""
    return (f"As {_article(narrative['asA'].strip())}, I want {narrative['iWant'].strip().rstrip('.,')} "
            f"so that {narrative['soThat'].strip().rstrip('.')}")


def area_and_action(sir: dict, fallback_area: str) -> tuple[str, str]:
    """'Invoice: Change State' -> ('Invoice', 'Change State'); a name without ':' belongs to the module."""
    name = str(sir.get("name") or sir.get("id"))
    area, sep, action = name.partition(":")
    return (area.strip(), action.strip()) if sep and area.strip() and action.strip() else (fallback_area, name)


def _intent(action: str, noun: str, writes: bool) -> dict:
    """What the user wants to do, worded from the use-case action (never from code). `noun` is the business entity.
    Returns goal (after 'I want'), when (the trigger), context (what the criteria start from), mode
    (create | update | view) and label (a business tag, never an HTTP verb or method name)."""
    a = est_mod.words(action).replace("-", " ")
    one, many = _article(noun), _plural(noun)

    def it(goal, when, context, mode, label):
        return {"goal": goal, "when": when, "context": context, "mode": mode, "label": label}

    if a in ("create edit", "create or edit", "add edit", "edit create"):
        return it(f"to open {one} to create or edit it", "the user opens the form", one, "view", "form")
    if a in ("create", "post", "add", "new", "insert", "register"):
        if writes:
            return it(f"to create {one}", f"the {noun} is submitted", f"a new {noun}", "create", "create")
        return it(f"to start creating {one}", "the user opens the form", f"a new {noun}", "view", "form")
    if a in ("edit", "update", "patch", "put", "save", "modify"):
        if writes:
            return it(f"to update {one}", "the changes are saved", f"an existing {noun}", "update", "update")
        return it(f"to open {one} for editing", f"the user opens the {noun}", f"an existing {noun}", "view", "form")
    if a in ("delete", "remove", "cancel"):
        done = "cancellation" if a == "cancel" else "deletion"
        return it(f"to {a} {one}", f"the user confirms the {done}", f"an existing {noun}",
                  "update" if writes else "view", a)
    if a in ("details", "detail", "view", "get", "show", "display", "read"):
        return it(f"to view the details of {one}", f"the user opens the {noun}", f"an existing {noun}", "view", "view")
    if a in ("index", "list", "search", "browse", "all", "home"):
        if noun.lower() == "dashboard":
            return it("to see the dashboard", "the user opens the dashboard", "the dashboard", "view", "overview")
        return it(f"to see the list of {many}", "the user opens the list", f"the {many}", "view", "list")
    if a.startswith(("change state", "change status", "set status", "update status")) or a in ("state", "status"):
        return it(f"to change the status of {one}", f"the user changes the status of the {noun}", f"an existing {noun}",
                  "update" if writes else "view", "status-change")
    if "pdf" in a.split() or a.startswith(("print", "export", "download", "generate")):
        what = "a PDF" if "pdf" in a.split() else "a copy"
        return it(f"to produce {what} of {one}", f"the user asks for {what}", f"an existing {noun}", "view",
                  "pdf" if what == "a PDF" else "export")
    return it(f"to carry out the \"{_first_upper(a)}\" step for {one}", "the user carries out the step", one,
              "update" if writes else "view", bm.slug(a).lower())


def _outside(rules: list[dict]) -> tuple[bool, list[str]]:
    """(sends email?, other outside systems in business words)."""
    names = list(dict.fromkeys(est_mod.entity(r) or "" for r in rules))
    email = any(_EMAIL.search(n) for n in names)
    others = [_human(_SUFFIX.sub("", n) or n) for n in names if n and not _EMAIL.search(n)]
    return email, others


def _records(entities: list[str]) -> str:
    """'the invoice and particular records are' / 'the invoice record is'."""
    return f"the {_join(entities)} record{'s are' if len(entities) > 1 else ' is'}"


def adjacent_workflows(sir: dict) -> list[str]:
    return [str(w) for w in ((sir.get("legacyAssessment") or {}).get("regressionScope") or [])][:4]


def _new_and_existing(logic: list[dict]) -> bool:
    """True when the use case handles both a new record (x.Id == 0) and an existing one (the else branch)."""
    seen = {bool(p.get("negated")) for r in logic for p in r["logic"].get("when", [])
            if re.search(r"\.Id\s*==\s*0$", str(p.get("code", "")))}
    return seen == {True, False}


def _logic_lines(logic: list[dict], sir: dict, noun: str, acronyms: set[str]) -> list[dict]:
    """Each business decision in words: {'given': '...', 'then': '...', 'id': ruleId}."""
    info = sir.get("businessLogic") or {}
    ctx = ct.Ctx(noun, info.get("aliases"), info.get("helpers"), None, info.get("entry"), acronyms)
    out = []
    for r in logic:
        ctx.method = r["logic"].get("method")
        t = ct.logic_rule(r["logic"], ctx)
        if t["then"]:
            out.append({"given": " and ".join(t["given"]), "then": " and ".join(t["then"]), "id": r.get("ruleId")})
    return out


def build_story(sir: dict, area: str, action: str, persona: str, acronyms: set[str] | None = None) -> dict | None:
    """One use case -> one user story, or None when the use case has no business behaviour (only internal calls)."""
    business = [r for r in sir.get("rules", []) if not _is_plumbing(r)]
    by_kind: dict[str, list[dict]] = {}
    for r in business:
        by_kind.setdefault(est_mod.rule_kind(r), []).append(r)
    if not any(by_kind.get(k) for k in ("logic", "check", "write", "external", "read", "rule")):
        return None
    guards, writes = by_kind.get("check", []), by_kind.get("write", [])
    externals, reads, other = by_kind.get("external", []), by_kind.get("read", []), by_kind.get("rule", [])
    logic = by_kind.get("logic", [])
    acts = [a for r in logic for a in r["logic"].get("then", [])]
    logic_changes = any(a.get("type") in ("data", "set") for a in acts)

    noun = _human(area)
    it = _intent(action, noun, bool(writes) or logic_changes)
    if it["mode"] == "create" and _new_and_existing(logic):   # one action that creates OR updates the record
        it = {**it, "goal": f"to create or update {_article(noun)}", "context": _article(noun),
              "label": "create-update"}
    rules_in_words = _logic_lines(logic, sir, noun, acronyms or set()) if logic else []
    decisions = est_mod.checks(business)
    # every check spelled out in words, with what it does when the code says so ("the message ... is shown")
    named = ct.checks([c for g in guards for c in est_mod.conditions(g)], noun)
    guard_ids = cite([g.get("ruleId") for g in guards])
    written = list(dict.fromkeys(_human(e) for r in writes if (e := est_mod.entity(r))))
    shown = list(dict.fromkeys(_human(e) for r in reads if (e := est_mod.entity(r)) and not e.endswith(est_mod._LOOKUP)))
    email, systems = _outside(externals)
    changes = it["mode"] in ("create", "update") or bool(writes) or logic_changes
    adjacent = adjacent_workflows(sir) if writes or logic_changes else []   # only a use case that changes records can break others
    checked = f"{it['context']} that passes every check" if decisions and changes else it["context"]
    given_when = f"Given {checked}, when {it['when']}"

    # so that ...: the business benefit the SIR can prove
    if writes:
        benefit = f"{_records(written or [noun])} {'saved' if it['mode'] == 'create' else 'kept up to date'}"
    elif shown or reads:
        benefit = f"I can review the {_join(shown or [noun])} information"
    else:
        benefit = "the work is done the same way as today"
    if email:
        benefit += " and the right people are notified by email"
    if systems:
        benefit += f" and the {_join(systems)} system{'s are' if len(systems) > 1 else ' is'} kept informed"
    narrative = {"asA": persona, "iWant": it["goal"], "soThat": benefit}

    # acceptance criteria: one line each, 'Given ..., when ..., then ... (rule ids)'
    ac: list[str] = []
    data_in_logic = any(a.get("type") == "data" for a in acts)
    notify_in_logic = any(a.get("type") == "notify" for a in acts)
    if writes and not data_in_logic:     # the decision rules already say which records are added / updated
        ac.append(f"{given_when}, then {_records(written or [noun])} saved{cite([r.get('ruleId') for r in writes])}")
    if email and not notify_in_logic:
        ac.append(f"{given_when}, then an email notification is sent"
                  + cite([r.get("ruleId") for r in externals if _EMAIL.search(est_mod.entity(r) or "")]))
    for system in systems:
        ids = [r.get("ruleId") for r in externals if _human(_SUFFIX.sub("", est_mod.entity(r) or "") or "") == system]
        ac.append(f"{given_when}, then the {system} system is updated{cite(ids)}")
    rule_lines = [f"{given_when}, then {_first_lower(r.get('statement', ''))}{cite([r.get('ruleId')])}" for r in other]
    if not writes and (shown or reads):
        info = _join(shown or [noun])
        start = f"there is {info} information" if it["context"].startswith("the ") else it["context"]
        ac.append(f"Given {start}, when {it['when']}, then the {info} information is shown"
                  + cite([r.get("ruleId") for r in reads]))
    if adjacent:
        ac.append(f"Given the {_join(adjacent)} workflow{'s' if len(adjacent) > 1 else ''} use the same records, "
                  "when this change goes live, then they keep working unchanged")
    parity = ("Given the same request is made in the current and the new system, when both complete, then the "
              f"result is identical{cite([r.get('ruleId') for r in business])}")
    # one criterion per business check, naming it; if they do not all fit, one line that lists every check
    check_lines = [f"Given {c['text']}, when {it['when']}, then "
                   f"{c['outcome'] or 'the outcome is the same as today'}{guard_ids}" for c in named]
    room = MAX_CRITERIA - len(ac) - 1
    if len(rule_lines) > max(1, room - min(len(check_lines), 1)):
        rule_lines = [f"{given_when}, then these rules apply as today: "
                      + "; ".join(_first_lower(r.get("statement", "")) for r in other)
                      + cite([r.get("ruleId") for r in other])]
    room = MAX_CRITERIA - len(ac) - len(rule_lines) - 1
    if len(check_lines) > room:
        check_lines = [f"Given {it['context']}, when {it['when']}, then these checks are applied exactly as today: "
                       + "; ".join(c["text"] + (f" ({c['outcome']})" if c["outcome"] else "") for c in named)
                       + guard_ids]
    # one criterion per business decision read from the code: its conditions and exactly what happens
    decision_lines = [f"Given {x['given'] or it['context']}, when {it['when']}, then {x['then']}{cite([x['id']])}"
                      for x in rules_in_words]
    room = MAX_CRITERIA - len(ac) - len(rule_lines) - len(check_lines) - 1
    if len(decision_lines) > room:   # never dropped: the ones that do not fit share one line
        keep, rest = decision_lines[:max(room - 1, 0)], rules_in_words[max(room - 1, 0):]
        decision_lines = keep + [f"Given {_article(noun)}, when {it['when']}, then these rules also apply exactly as "
                                 "today: " + "; ".join(f"if {x['given']}, {x['then']}" if x["given"] else x["then"]
                                                       for x in rest) + cite([x["id"] for x in rest])]
    ac = check_lines + decision_lines + ac + rule_lines + [parity]

    # description: plain business sentences
    desc = [f"The user can {it['goal'][3:]}."]
    if rules_in_words:
        desc.append("Business rules, exactly as today: " + "; ".join(
            f"if {x['given']}, {x['then']}" if x["given"] else x["then"] for x in rules_in_words) + ".")
    if named:
        listed = "; ".join(c["text"] for c in named)
        desc.append(f"Business checks, applied exactly as today: {listed}." if changes else
                    f"What is shown depends on these checks, exactly as today: {listed}.")
    if rules_in_words:
        pass    # the rules above already say what is saved and who is notified
    elif writes:
        desc.append(f"{_first_upper(_records(written or [noun]))} saved"
                    + (" and an email notification is sent." if email else "."))
    elif email:
        desc.append("An email notification is sent.")
    elif shown or reads:
        desc.append(f"It shows the {_join(shown or [noun])} information.")
    if other:
        desc.append("These rules must work exactly as today: "
                    + "; ".join(_first_lower(r.get("statement", "")) for r in other) + ".")
    if adjacent:
        desc.append(f"Other workflows that use the same records ({_join(adjacent)}) must keep working.")

    labels = [bm.slug(area).lower(), it["label"]]
    labels += ["notification"] if email else []
    labels += ["read-only"] if not writes and not externals and not logic_changes else []
    first = (logic + writes + externals + other + guards + reads or business)[0]
    legacy = ", ".join(dict.fromkeys(str(r.get("legacyLines", "")) for r in business if r.get("legacyLines")))
    return {
        "id": f"US-{sir['id']}",
        "type": "functional",
        "title": story_title(narrative),
        "narrative": narrative,
        "description": " ".join(desc),
        "acceptanceCriteria": ac,
        "storyPoints": 1,   # set below from the business-complexity estimate
        "priority": "Must" if writes or externals or logic_changes else "Should",
        "labels": list(dict.fromkeys(labels)),
        "narrativeSource": "template",
        "behaviour": str(sir.get("name") or sir["id"]),
        "trustBoundary": first.get("trustBoundary", ""),
        "classification": ", ".join(dict.fromkeys(str(r.get("classification") or "business rule") for r in business)),
        "trace": {"sirId": sir["id"], "ruleId": first.get("ruleId"), "ruleIds": [r.get("ruleId") for r in business],
                  "legacyLines": legacy, "snippet": "\n".join(str(r.get("snippet", "")) for r in business)[:2000],
                  "astNode": first.get("astNode", "")},
        "estimation": None,
    }


def build_features(members: list[dict], module_key: str, module_label: str, persona: str) -> list[dict]:
    """Group the module's use cases into business-area features; one story per use case."""
    areas: dict[str, dict] = {}
    acronyms = {_human(area_and_action(s, module_label)[0]) for s in members}   # e.g. "SOA": keep its capitals
    for sir in members:
        area, action = area_and_action(sir, module_label)
        story = build_story(sir, area, action, persona, acronyms)
        if story is None:
            continue
        story["estimation"] = est_mod.score_use_case([r for r in sir.get("rules", []) if not _is_plumbing(r)],
                                                     sir.get("legacyAssessment"))
        story["storyPoints"] = story["estimation"]["points"]
        feat = areas.setdefault(area, {
            "id": f"FT-{bm.slug(module_key)}-{bm.slug(area)}", "title": _human(area) if len(area) <= 3 else area,
            "description": "", "sirIds": [], "labels": [bm.slug(area).lower()], "narrativeSource": "template",
            "stories": []})
        feat["sirIds"].append(sir["id"])
        feat["stories"].append(story)
    for feat in areas.values():
        goals = [s["narrative"]["iWant"][3:] for s in feat["stories"]]
        feat["description"] = f"What a user can do here: {_join(goals)}."
    return list(areas.values())


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
        features = build_features(members, key, title, persona or DEFAULT_PERSONA)
        if not features:
            continue
        n = sum(len(f["stories"]) for f in features)
        epics.append({
            "id": f"EP-{bm.slug(key)}", "title": title, "module": key,
            "description": f"The {title} business capability: {n} use case{'s' if n > 1 else ''} in "
                           f"{len(features)} feature{'s' if len(features) > 1 else ''}.",
            "businessOutcome": "", "labels": [bm.slug(key).lower()], "narrativeSource": "template",
            "features": features,
        })
    if not epics:
        raise ValueError("The selected contracts contain only technical code (internal calls and plumbing), so "
                         "there is no business behaviour to write user stories for. Select a business module.")
    for e in epics:
        for f in e["features"]:
            rollup(f, f["stories"])
        rollup(e, [s for f in e["features"] for s in f["stories"]])
    backlog = {"schemaVersion": bm.SCHEMA_VERSION, "generatedAt": datetime.now(timezone.utc).isoformat(),
               "source": {"sirIds": [s["id"] for s in selected], **(source or {})},
               "estimationModel": {
                   "method": "Business complexity only: Business rules + Process scope + Business uncertainty "
                             "(each 1-5), relative to a reference story, on Fibonacci 1, 2, 3, 5, 8, 13, 21. "
                             "Technical details are not considered.",
                   "scale": [{"factorSum": f"<= {lim}" if lim < 99 else "> 13.5", "points": p}
                             for lim, p in est_mod.SUM_TO_POINTS],
                   "reference": dict(est_mod.REFERENCE)},
               "epics": epics, "openQuestions": []}
    # the same business action reached two ways (e.g. a screen and an API) reads as two identical stories
    seen: dict[str, dict] = {}
    for _, _, story in bm.iter_stories(backlog):
        key = story["narrative"]["iWant"].lower()
        if key in seen:
            first = seen[key]
            backlog["openQuestions"].append({
                "id": f"Q-DUP-{len(backlog['openQuestions']) + 1:02d}", "storyId": story["id"],
                "question": (f"\"{first['behaviour']}\" and \"{story['behaviour']}\" both let the user "
                             f"{story['narrative']['iWant'][3:]}. Are they the same business action (one story), or do they differ for the "
                             "business? If they are the same, remove one of the two stories.")})
        else:
            seen[key] = story
    ref = est_mod.pick_reference([s for _, _, s in bm.iter_stories(backlog)])
    if ref:
        ref["labels"] = list(dict.fromkeys(ref.get("labels", []) + ["reference-story"]))
        backlog["estimationModel"]["reference"]["storyId"] = ref["id"]
        backlog["openQuestions"].append({
            "id": "Q-EST-02", "storyId": ref["id"],
            "question": (f"Agree the reference story for relative sizing: \"{ref['title']}\" is the closest to the "
                         f"{est_mod.REFERENCE['points']}-point anchor ({est_mod.REFERENCE['description']}). "
                         "Replace it with a story the team has already delivered if one is a better anchor.")})
    return backlog


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
    print(f"{c['epics']} epic(s), {c['features']} feature(s), {c['stories']} stories, "
          f"{c['storyPoints']} story points -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
