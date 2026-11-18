"""User Story Generation: SIR -> Epic / Feature / User Story backlog, following the
`sir-user-story-generator` skill (.agents/skills/sir-user-story-generator).

Division of labour, exactly as the skill describes it:
  * the skill's own scripts (sir_to_stories.py / backlog_model.py / push_backlog.py) build the scaffold, validate
    it and push it, so no rule is ever dropped and every story keeps its legacy trace;
  * the LLM does the "agent" part: it determines the epic (name, outcome, persona), rewrites each feature and
    story in business language with Gherkin acceptance criteria, and raises open questions. It may change only
    the fields the skill allows; ids and trace fields are never touched, and rewrites that lose the literals of
    a deterministic-core rule are rejected.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import scope_modules, store
from .llm_json import ask_json

logger = logging.getLogger(__name__)

SKILL_DIR = Path(__file__).resolve().parents[3] / ".agents" / "skills" / "sir-user-story-generator"
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import backlog_model as bm  # noqa: E402  (the skill's own modules)
import push_backlog as pb  # noqa: E402
import sir_to_stories as sts  # noqa: E402

REFINE_WORKERS = 3
# the skill's scripts copied next to each backlog so it can be rebuilt and pushed outside the app
SCRIPT_FILES = ("sir_to_stories.py", "checks_text.py", "estimation.py", "backlog_model.py", "push_backlog.py")
SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,38}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def module_sirs(eng: dict) -> list[dict]:
    seed = eng.get("seed") or {}
    cap = (eng.get("scope") or {}).get("capabilityId")
    return [s for s in seed.get("semantic_ir", []) if not cap or s.get("module") == cap]


def artifacts_dir(eid: str) -> Path:
    d = store.engagement_dir(eid) / "artifacts" / "user-stories"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- LLM: epic determination

_EPIC_SYSTEM = (
    "You are an agile delivery lead. From the facts of one legacy module and its Semantic IR contracts, decide the "
    "EPIC that a modernization backlog should use. Use only the supplied facts. Reply with JSON only."
)


def _determine_epic(eng: dict, sirs: list[dict], module: dict | None) -> tuple[dict, str | None]:
    facts = {"module": (module or {}).get("name") or (eng.get("scope") or {}).get("name"),
             "businessSummary": (module or {}).get("businessSummary") or (module or {}).get("summary"),
             "useCases": [u["name"] for u in (module or {}).get("useCases", [])[:10]],
             "contracts": [{"id": s["id"], "name": s["name"], "summary": s.get("summary"),
                            "sideEffects": s.get("sideEffects", [])[:4]} for s in sirs]}
    parsed, model = ask_json(_EPIC_SYSTEM, (
        'Return {"title": <2-5 word business capability name for the epic>, "description": <2 sentences>, '
        '"businessOutcome": <one sentence: what the business gets once this is modernized>, '
        '"persona": <the most representative real user role, e.g. "claims adjuster">}\n\nFACTS:\n'
        + json.dumps(facts, indent=1)), max_tokens=600)
    if not isinstance(parsed, dict):
        return {}, None
    clean = {k: str(parsed[k]).strip() for k in ("title", "description", "businessOutcome", "persona")
             if isinstance(parsed.get(k), str) and parsed[k].strip()}
    return clean, model


# --------------------------------------------------------------------------- LLM: story refinement

_REFINE_SYSTEM = (
    "You are a business analyst writing user stories for business people, from Semantic IR contracts extracted from "
    "legacy code. One story is one business use case. Rules:\n"
    "- Say what the business gets, not what the code does. Only state a purpose the rules, use-case summary or side "
    "effects support.\n"
    "- asA is a real business role (e.g. 'accounts clerk', 'claims adjuster'), never 'user', 'system' or a module "
    "name. Use `defaultPersona` when it is a real role.\n"
    "- narrative asA / iWant / soThat become the title 'As a <asA>, I want <iWant> so that <soThat>'. iWant starts "
    "with 'to' (e.g. 'to submit a new invoice for approval'); soThat is the business benefit.\n"
    "- description: 2-4 plain sentences on what the user does and gets, in business language.\n"
    "- No technical words anywhere: never name classes, methods, files, line numbers, tables, database ids, "
    "frameworks, APIs, HTTP verbs or services. Translate code conditions into business conditions "
    "(e.g. `if (model.Particulars.Count > 1)` -> 'the invoice has more than one line item').\n"
    "- Acceptance criteria: one single line per string, 'Given <context>, when <action>, then <outcome> "
    "(<rule ids>)', ending with the short ids of the rules it covers, e.g. (R2, R4) or (R3-R6). Use real values, "
    "literals and error texts copied from the rules or snippets. Any other test data is a placeholder in angle "
    "brackets, e.g. <client name>: never invent names, ids or amounts.\n"
    "- Write every criterion in plain, simple English that a non-technical business user understands at first read: "
    "short sentences (aim for under 30 words), everyday words, active voice, one idea per line. Say 'the invoice is "
    "saved' not 'the record is persisted'; 'the request is refused' not 'the API returns an error'; 'is empty' not "
    "'is null'. No jargon, code terms, status codes or field/table names. Keep the business intent, every condition, "
    "number, quoted value and error text exactly as in the source: simplify the wording, never the meaning.\n"
    "- Every rule id of the story appears in at least one criterion. Rules of kind 'internal' are one piece of code "
    "calling another: they get no criterion of their own; cite them only in the last criterion, which states that "
    "the result is identical to the current system. At most 16 criteria. Never drop a rule.\n"
    "- Rules of kind 'decision' come with `meaning`: the decision already worded from the code (its conditions and "
    "exactly what happens). Keep every condition and outcome of it, including quoted values and error texts; you may "
    "make the wording more natural, never less complete.\n"
    "- When `adjacentWorkflows` is not empty, keep one criterion saying those workflows keep working unchanged.\n"
    "- labels: 2-5 short lowercase business tags, hyphenated (e.g. 'invoice', 'approval').\n"
    "- NEVER change the meaning of a rule whose trustBoundary starts with 'Deterministic': keep its numbers, "
    "rounding, literals and conditions exactly as written.\n"
    "- Story points measure BUSINESS complexity only: keep storyPoints at estimation.points; raise them by at most "
    "one Fibonacci step, and only if the business rule is harder than the evidence shows. Never lower them.\n"
    "- NEVER invent behaviour. If what a rule means for the business is unclear, word the criterion neutrally "
    "('the same check as today') and add an openQuestion instead of guessing.\n"
    "Reply with JSON only."
)


def _story_rules(story: dict, sirs: dict[str, dict]) -> list[dict]:
    rules = {r["ruleId"]: r for r in sirs.get(story["trace"].get("sirId"), {}).get("rules", [])}
    return [rules[r] for r in (story["trace"].get("ruleIds") or []) if r in rules]


def _feature_view(epic: dict, feature: dict, sirs: dict[str, dict], subset: list[dict] | None = None) -> dict:
    stories = []
    for s in subset if subset is not None else feature["stories"]:
        sir = sirs.get(s["trace"].get("sirId"), {})
        own = _story_rules(s, sirs)
        area = sts.area_and_action(sir, "record")[0] if sir else "record"
        meanings = {x["id"]: f"if {x['given']}, {x['then']}" if x["given"] else x["then"]
                    for x in sts._logic_lines([r for r in own if r.get("logic")], sir, sts._human(area), set())}
        view_rules = [{"id": sts.short_id(r.get("ruleId")),
                       "kind": "decision" if r.get("logic") else sts.est_mod.rule_kind(r),
                       "statement": r.get("statement"), "conditions": r.get("conditions"),
                       **({"meaning": meanings[r["ruleId"]]} if r.get("ruleId") in meanings else {}),
                       "trustBoundary": r.get("trustBoundary"), "snippet": (r.get("snippet") or "")[:300]}
                      for r in own]
        stories.append({
            "id": s["id"],
            "useCase": {"name": sir.get("name"), "summary": sir.get("summary"),
                        "sideEffects": sir.get("sideEffects", []), "inputs": sir.get("inputs", [])},
            "narrative": s["narrative"], "description": s["description"],
            "acceptanceCriteria": s["acceptanceCriteria"], "storyPoints": s["storyPoints"], "priority": s["priority"],
            "estimation": {k: (s.get("estimation") or {}).get(k) for k in ("rules", "scope", "uncertainty", "points")},
            "adjacentWorkflows": sts.adjacent_workflows(sir) if any(r["kind"] == "write" for r in view_rules) else [],
            "rules": view_rules})
    return {"epic": {"title": epic["title"], "businessOutcome": epic.get("businessOutcome")},
            "defaultPersona": feature["stories"][0]["narrative"]["asA"] if feature["stories"] else "",
            "feature": {"id": feature["id"], "title": feature["title"], "summary": feature["description"]},
            "stories": stories}


_REFINE_USER = (
    "Rewrite this feature and its stories. Return one JSON object:\n"
    '{"feature": {"title": ..., "description": ...},\n'
    ' "stories": [{"id": <unchanged id>, "narrative": {"asA": ..., "iWant": ..., "soThat": ...}, '
    '"description": ..., "acceptanceCriteria": ["Given ..., when ..., then ... (R1, R2)"], '
    '"storyPoints": <1|2|3|5|8|13>, "priority": "Must"|"Should"|"Could"|"Won\'t", "labels": [...]}],\n'
    ' "openQuestions": [{"storyId": <id or null>, "question": ...}]}\n\nINPUT:\n'
)


def _literals(rule: dict) -> list[str]:
    """Numbers in the statement and quoted strings in statement/snippet: facts a rewrite must keep."""
    stmt, snip = rule.get("statement") or "", rule.get("snippet") or ""
    nums = re.findall(r"(?<![\w.])\d+(?:\.\d+)?%?(?![\w])", stmt)
    quoted = re.findall(r"\"([^\"\n]{2,60})\"|'([^'\n]{2,60})'", stmt + "\n" + snip)
    return sorted({x for x in nums + [a or b for a, b in quoted] if x})


_CITED = re.compile(r"\bR(\d+)(?:\s*[–-]\s*R?(\d+))?")


def cited_rules(criteria: list[str]) -> set[str]:
    """Short rule ids cited in the criteria, ranges expanded: 'R3-R6' -> R3, R4, R5, R6."""
    out: set[str] = set()
    for a in criteria:
        for lo, hi in _CITED.findall(a):
            out.update(f"R{n}" for n in range(int(lo), int(hi or lo) + 1))
    return out


def _story_text(s: dict) -> str:
    n = s["narrative"]
    return "\n".join([s["title"], n["asA"], n["iWant"], n["soThat"], s["description"], *s["acceptanceCriteria"]])


def _apply_story(story: dict, upd: dict, rule: dict | list[dict] | None) -> str | None:
    """Apply an LLM rewrite to one story. Returns None on success, or the reason it was rejected."""
    nar = upd.get("narrative") or {}
    if not isinstance(nar, dict) or not all(isinstance(nar.get(k), str) and nar[k].strip()
                                            for k in ("asA", "iWant", "soThat")):
        return "incomplete narrative"
    ac = upd.get("acceptanceCriteria")
    if not (isinstance(ac, list) and 1 <= len(ac) <= sts.MAX_CRITERIA
            and all(isinstance(a, str) and bm.is_criterion(a) for a in ac)):
        return f"acceptance criteria must be 1-{sts.MAX_CRITERIA} lines reading 'Given ..., when ..., then ...'"
    narrative = {k: nar[k].strip() for k in ("asA", "iWant", "soThat")}
    candidate = dict(story, title=sts.story_title(narrative)[:240], narrative=narrative,
                     description=str(upd.get("description") or story["description"]).strip()[:800],
                     acceptanceCriteria=[a.strip() for a in ac])
    rules = rule if isinstance(rule, list) else [rule] if rule else []
    wanted = {sts.short_id(r.get("ruleId")) for r in rules if r.get("ruleId")}
    missing = sorted(wanted - cited_rules(ac), key=lambda x: (len(x), x))
    if missing:   # the skill: never drop a rule
        return f"acceptance criteria do not cover rule(s) {', '.join(missing)}"
    text = _story_text(candidate).lower()
    for r in rules:
        if str(r.get("trustBoundary", "")).startswith("Deterministic"):
            lost = [lit for lit in _literals(r) if lit.lower() not in text]
            if lost:
                return f"deterministic-core rule {r.get('ruleId')}: rewrite dropped literal(s) {lost}"
    story.update({k: candidate[k] for k in ("title", "narrative", "description", "acceptanceCriteria")})
    est = story.get("estimation") or {}
    floor = est.get("points") or story["storyPoints"]   # the business-complexity estimate: never lowered...
    ceiling = next((f for f in bm.FIBONACCI if f > floor), floor)   # ...and raised by at most one Fibonacci step
    story["storyPoints"] = min(max(bm.snap_points(upd.get("storyPoints", story["storyPoints"])), floor), ceiling)
    if story["storyPoints"] != floor:
        est.setdefault("notes", []).append(f"raised from {floor} by refinement: business rule harder than the evidence")
    if upd.get("priority") in bm.PRIORITIES:
        story["priority"] = upd["priority"]
    labels = [x for x in (upd.get("labels") or []) if isinstance(x, str) and SAFE_LABEL.match(x)]
    keep = [x for x in story.get("labels", []) if x == "reference-story"]
    story["labels"] = list(dict.fromkeys(labels + keep))[:8] or story.get("labels", [])
    story["narrativeSource"] = "refined"
    return None


STORIES_PER_CALL = 4   # keeps each reply short enough to finish inside the gateway's request timeout


def _refine_chunk(args: tuple) -> tuple[dict, dict, list[dict], bool, dict | None, str | None]:
    epic, feature, subset, first, sirs = args
    view = _feature_view(epic, feature, sirs, subset)
    prompt = _REFINE_USER + json.dumps(view, indent=1)
    for _ in range(2):  # one retry: the model endpoint throttles and times out under parallel load
        parsed, model = ask_json(_REFINE_SYSTEM, prompt, max_tokens=3200)
        if isinstance(parsed, dict):
            return epic, feature, subset, first, parsed, model
    return epic, feature, subset, first, None, None


def _refine(backlog: dict, sirs: list[dict]) -> dict:
    by_sir = {s["id"]: s for s in sirs}
    jobs = []
    for epic, feature in bm.iter_features(backlog):
        stories = feature["stories"]
        for i in range(0, len(stories), STORIES_PER_CALL):
            jobs.append((epic, feature, stories[i:i + STORIES_PER_CALL], i == 0, by_sir))
    with ThreadPoolExecutor(max_workers=REFINE_WORKERS) as pool:
        results = list(pool.map(_refine_chunk, jobs))
    models: set[str] = set()
    rejected: list[dict] = []
    questions = backlog.setdefault("openQuestions", [])
    for epic, feature, subset, first, parsed, model in results:
        if not parsed:
            continue
        models.add(model or "")
        feat = parsed.get("feature") or {}
        if first:
            if isinstance(feat.get("title"), str) and feat["title"].strip():
                feature["title"] = feat["title"].strip()[:140]
            if isinstance(feat.get("description"), str) and feat["description"].strip():
                feature["description"] = feat["description"].strip()[:600]
            feature["narrativeSource"] = "refined"
        updates = {u.get("id"): u for u in parsed.get("stories") or [] if isinstance(u, dict)}
        ids = {s["id"] for s in subset}
        for story in subset:
            upd = updates.get(story["id"])
            if not upd:
                continue
            why = _apply_story(story, upd, _story_rules(story, by_sir))
            if why:
                rejected.append({"storyId": story["id"], "reason": why})
        for q in parsed.get("openQuestions") or []:
            if (isinstance(q, dict) and isinstance(q.get("question"), str) and len(q["question"].strip()) > 8
                    and q["question"].strip().lower() not in {"none", "n/a", "null", "no questions", "none."}):
                sid = q.get("storyId") if q.get("storyId") in ids else None
                questions.append({"id": f"Q-{len(questions) + 1:02d}", "storyId": sid,
                                  "question": q["question"].strip()[:400]})
    for r in rejected:  # the skill: ambiguous or unsafe rewrites become open questions, not guesses
        questions.append({"id": f"Q-{len(questions) + 1:02d}", "storyId": r["storyId"],
                          "question": f"AI rewrite rejected ({r['reason']}). Review this story's wording manually."})
    c = bm.counts(backlog)
    status = "unavailable" if not models else "llm" if c["template"] == 0 else "partial"
    return {"status": status, "model": ", ".join(sorted(m for m in models if m)) or None,
            "refined": c["refined"], "total": c["stories"], "rejected": rejected}


# --------------------------------------------------------------------------- public API

def generate(eng: dict, *, refine: bool = True, epic: str | None = None, persona: str | None = None) -> dict:
    sirs = module_sirs(eng)
    if not sirs:
        raise ValueError("No Semantic IR contracts for the selected scope. Generate and approve the Semantic IR first.")
    scope = eng.get("scope") or {}
    cap_id = scope.get("capabilityId")
    module = scope_modules.find_module(eng, cap_id) if cap_id and eng.get("seed") else None
    determined: dict = {}
    epic_model = None
    if refine:
        determined, epic_model = _determine_epic(eng, sirs, module)
    title = epic or determined.get("title") or (module or {}).get("displayName") or scope.get("name")
    backlog = sts.build_backlog(
        sirs, epic=None, persona=persona or determined.get("persona"),
        module_names={cap_id: title} if cap_id and title else None,
        source={"engagementId": eng["id"], "engagement": eng.get("name"), "scope": scope.get("name")})
    for e in backlog["epics"]:
        if determined.get("description"):
            e["description"] = determined["description"]
        if determined.get("businessOutcome"):
            e["businessOutcome"] = determined["businessOutcome"]
        if determined:
            e["narrativeSource"] = "refined"
    refinement = {"status": "skipped", "model": None, "refined": 0, "total": bm.counts(backlog)["stories"],
                  "rejected": []}
    if refine:
        refinement = _refine(backlog, sirs)
        if epic_model and not refinement["model"]:
            refinement["model"] = epic_model
        for e in backlog["epics"]:   # the LLM may raise story points: refresh the rollups
            for f in e["features"]:
                sts.rollup(f, f["stories"])
            sts.rollup(e, [s for f in e["features"] for s in f["stories"]])
    issues = [{"level": lvl, "message": msg} for lvl, msg in bm.validate(backlog)]
    out = artifacts_dir(eng["id"])
    (out / "sir.json").write_text(json.dumps({"semantic_ir": sirs}, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "backlog.json").write_text(json.dumps(backlog, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "backlog.md").write_text(bm.backlog_markdown(backlog), encoding="utf-8")
    scripts_out = out / "scripts"
    scripts_out.mkdir(exist_ok=True)
    for f in SCRIPT_FILES:
        shutil.copy2(SCRIPTS_DIR / f, scripts_out / f)
    shutil.copy2(SKILL_DIR / "tracker-config.example.json", out / "tracker-config.example.json")
    eng["userStories"] = {
        "generatedAt": _now(), "scope": cap_id, "sirIds": [s["id"] for s in sirs], "backlog": backlog,
        "counts": bm.counts(backlog), "validation": issues, "refinement": refinement,
        "epicDetermination": {"status": "llm" if determined else "deterministic", "model": epic_model},
        "files": ["sir.json", "backlog.json", "backlog.md", *(f"scripts/{f}" for f in SCRIPT_FILES),
                  "tracker-config.example.json"],
        "commands": [
            "python scripts/sir_to_stories.py sir.json --out backlog.json --markdown backlog.md",
            "python scripts/push_backlog.py validate backlog.json",
            "python scripts/push_backlog.py push backlog.json --provider jira --config tracker-config.json",
        ],
        "lastPush": None,
    }
    return store.save(eng)


# --------------------------------------------------------------------------- manual edits

EDITABLE = ("title", "description", "acceptanceCriteria", "labels", "storyPoints")


def _find_story(backlog: dict, sid: str) -> tuple[dict, dict, dict]:
    for epic, feature, story in bm.iter_stories(backlog):
        if story["id"] == sid:
            return epic, feature, story
    raise KeyError(sid)


def _label(text: str) -> str | None:
    t = re.sub(r"\s+", "-", str(text).strip())
    return t if SAFE_LABEL.match(t) else None


def _persist(eng: dict) -> dict:
    """Recompute rollups, counts and validation, rewrite backlog.json / backlog.md, save the engagement."""
    us = eng["userStories"]
    backlog = us["backlog"]
    for e in backlog["epics"]:
        for f in e["features"]:
            sts.rollup(f, f["stories"])
        sts.rollup(e, [s for f in e["features"] for s in f["stories"]])
    us["counts"] = bm.counts(backlog)
    us["validation"] = [{"level": lvl, "message": msg} for lvl, msg in bm.validate(backlog)]
    out = artifacts_dir(eng["id"])
    (out / "backlog.json").write_text(json.dumps(backlog, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "backlog.md").write_text(bm.backlog_markdown(backlog), encoding="utf-8")
    return store.save(eng)


def update_story(eng: dict, sid: str, changes: dict) -> dict:
    """A person's edit of one story. Only the fields of the story card change; id and trace never do."""
    us = eng.get("userStories")
    if not us:
        raise ValueError("Generate the user stories first")
    _, _, story = _find_story(us["backlog"], sid)
    upd = {k: v for k, v in changes.items() if k in EDITABLE and v is not None}
    if "title" in upd:
        title = str(upd["title"]).strip()
        if not title:
            raise ValueError("Title cannot be empty")
        story["title"] = title[:300]
    if "description" in upd:
        story["description"] = str(upd["description"]).strip()[:2000]
    if "acceptanceCriteria" in upd:
        ac = [str(a).strip() for a in upd["acceptanceCriteria"] if str(a).strip()]
        if not ac:
            raise ValueError("Add at least one acceptance criterion")
        story["acceptanceCriteria"] = ac[:20]
    if "labels" in upd:
        story["labels"] = list(dict.fromkeys(x for x in map(_label, upd["labels"]) if x))[:12]
    if "storyPoints" in upd:
        pts = upd["storyPoints"]
        if pts not in bm.FIBONACCI or pts > bm.MAX_POINTS:
            raise ValueError(f"Story points must be one of {[f for f in bm.FIBONACCI if f <= bm.MAX_POINTS]}")
        story["storyPoints"] = pts
        story.setdefault("estimation", {})["manualPoints"] = pts   # a person's call overrides the estimate
    story["narrativeSource"] = "refined"   # reviewed by a person
    story["edited"] = True
    return _persist(eng)


def remove_story(eng: dict, sid: str) -> dict:
    """Remove one story; a feature or epic left without stories is removed with it."""
    us = eng.get("userStories")
    if not us:
        raise ValueError("Generate the user stories first")
    backlog = us["backlog"]
    _, feature, _ = _find_story(backlog, sid)
    feature["stories"] = [s for s in feature["stories"] if s["id"] != sid]
    for e in backlog["epics"]:
        e["features"] = [f for f in e["features"] if f["stories"]]
    backlog["epics"] = [e for e in backlog["epics"] if e["features"]]
    backlog["openQuestions"] = [q for q in backlog.get("openQuestions", []) if q.get("storyId") != sid]
    ref = (backlog.get("estimationModel") or {}).get("reference") or {}
    if ref.get("storyId") == sid:
        ref.pop("storyId")
    return _persist(eng)


def integrations(config: dict | None = None) -> list[dict]:
    return pb.provider_status(config, dict(os.environ))


_ALLOWED_CRED = {n for names in pb.SECRET_ENV.values() for n in names} | {
    n for m in pb.SETTINGS_ENV.values() for n in m.values()}


def push(eng: dict, provider: str, *, apply: bool, confirm: bool, only: list[str] | None, allow_template: bool,
         config: dict | None, credentials: dict | None) -> dict:
    us = eng.get("userStories")
    if not us:
        raise ValueError("Generate the user stories before pushing them to a tracker")
    if apply and not confirm:
        raise pb.PushError("Pushing creates work items in the external tracker; confirm explicitly")
    env = dict(os.environ)
    # Session-only credentials from the UI: merged in memory, never persisted or echoed back.
    env.update({k: v for k, v in (credentials or {}).items() if k in _ALLOWED_CRED and isinstance(v, str) and v})
    state_path = artifacts_dir(eng["id"]) / "backlog.push-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    def save_state(s: dict) -> None:
        state_path.write_text(json.dumps(s, indent=2), encoding="utf-8")

    rep = pb.push(us["backlog"], provider, {provider: config or {}}, env, apply=apply, only=only,
                  allow_template=allow_template, state=state, show_payload=not apply, on_state=save_state)
    if apply:
        save_state(rep["state"])
        us["lastPush"] = {"provider": provider, "label": rep["label"], "target": rep["target"], "at": _now(),
                          "summary": rep["summary"],
                          "items": [{k: r.get(k) for k in ("id", "level", "action", "key", "url")} for r in rep["rows"]]}
        store.save(eng)
    rep.pop("state", None)
    return rep
