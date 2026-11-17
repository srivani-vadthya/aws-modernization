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
    "You are a business analyst and agile delivery lead turning Semantic IR contracts extracted from legacy code into "
    "user stories. Rules:\n"
    "- Say what the business gets, not what the code does. Only state a purpose the rule statement, summary or side "
    "effects support.\n- Use a real persona (e.g. 'claims adjuster'); 'platform engineer' for technical enablers.\n"
    "- Acceptance criteria: one Gherkin Scenario per string, starting with 'Scenario:', with real values, literals "
    "and error texts copied from the rule or snippet. Any other test data must be a placeholder in angle brackets, "
    "e.g. <organization name> or <claim id>: never invent names, ids or amounts. Keep a parity scenario.\n"
    "- Stories are INVEST sized (Fibonacci 1,2,3,5,8; never more than 8).\n"
    "- NEVER change the meaning of a rule whose trustBoundary starts with 'Deterministic': keep its numbers, rounding, "
    "literals and conditions exactly as written.\n"
    "- NEVER invent behaviour. If a rule is ambiguous, garbled or truncated, add an openQuestion instead of guessing.\n"
    "Reply with JSON only."
)


def _feature_view(epic: dict, feature: dict, sirs: dict[str, dict], subset: list[dict] | None = None) -> dict:
    sir = sirs.get(feature["sirId"], {})
    rules = {r["ruleId"]: r for r in sir.get("rules", [])}
    stories = []
    for s in subset if subset is not None else feature["stories"]:
        t = s["trace"]
        rule = rules.get(t.get("ruleId")) or {}
        stories.append({
            "id": s["id"], "type": s["type"], "title": s["title"], "narrative": s["narrative"],
            "description": s["description"], "acceptanceCriteria": s["acceptanceCriteria"],
            "storyPoints": s["storyPoints"], "priority": s["priority"],
            "rule": {"ruleId": rule.get("ruleId"), "statement": rule.get("statement"),
                     "classification": rule.get("classification"), "trustBoundary": rule.get("trustBoundary"),
                     "legacyLines": rule.get("legacyLines"), "snippet": (rule.get("snippet") or "")[:500]}
            if rule else {"ruleIds": t.get("ruleIds")}})
    return {"epic": {"title": epic["title"], "businessOutcome": epic.get("businessOutcome")},
            "defaultPersona": feature["stories"][0]["narrative"]["asA"] if feature["stories"] else "",
            "feature": {"id": feature["id"], "title": feature["title"], "summary": feature["description"],
                        "stateMachine": feature["stateMachine"], "sideEffects": feature["sideEffects"],
                        "inputs": feature["inputs"]},
            "stories": stories}


_REFINE_USER = (
    "Rewrite this feature and its stories. Return one JSON object:\n"
    '{"feature": {"title": ..., "description": ...},\n'
    ' "stories": [{"id": <unchanged id>, "title": ..., "narrative": {"asA": ..., "iWant": ..., "soThat": ...}, '
    '"description": ..., "acceptanceCriteria": ["Scenario: ...\\n  Given ...\\n  When ...\\n  Then ..."], '
    '"storyPoints": <1|2|3|5|8>, "priority": "Must"|"Should"|"Could"|"Won\'t", "labels": [...]}],\n'
    ' "openQuestions": [{"storyId": <id or null>, "question": ...}]}\n\nINPUT:\n'
)


def _literals(rule: dict) -> list[str]:
    """Numbers in the statement and quoted strings in statement/snippet: facts a rewrite must keep."""
    stmt, snip = rule.get("statement") or "", rule.get("snippet") or ""
    nums = re.findall(r"(?<![\w.])\d+(?:\.\d+)?%?(?![\w])", stmt)
    quoted = re.findall(r"\"([^\"\n]{2,60})\"|'([^'\n]{2,60})'", stmt + "\n" + snip)
    return sorted({x for x in nums + [a or b for a, b in quoted] if x})


def _story_text(s: dict) -> str:
    n = s["narrative"]
    return "\n".join([s["title"], n["asA"], n["iWant"], n["soThat"], s["description"], *s["acceptanceCriteria"]])


def _apply_story(story: dict, upd: dict, rule: dict | None) -> str | None:
    """Apply an LLM rewrite to one story. Returns None on success, or the reason it was rejected."""
    nar = upd.get("narrative") or {}
    if not isinstance(nar, dict) or not all(isinstance(nar.get(k), str) and nar[k].strip()
                                            for k in ("asA", "iWant", "soThat")):
        return "incomplete narrative"
    ac = upd.get("acceptanceCriteria")
    if not (isinstance(ac, list) and 1 <= len(ac) <= 8 and all(isinstance(a, str) for a in ac)
            and all(a.lstrip().startswith("Scenario") for a in ac)):
        return "acceptance criteria must be 1-8 Gherkin scenarios starting with 'Scenario:'"
    title = upd.get("title")
    if not (isinstance(title, str) and title.strip()):
        return "missing title"
    candidate = dict(story, title=title.strip()[:140],
                     narrative={k: nar[k].strip() for k in ("asA", "iWant", "soThat")},
                     description=str(upd.get("description") or story["description"]).strip()[:800],
                     acceptanceCriteria=[a.strip() for a in ac])
    if rule and str(rule.get("trustBoundary", "")).startswith("Deterministic"):
        text = _story_text(candidate).lower()
        lost = [lit for lit in _literals(rule) if lit.lower() not in text]
        if lost:
            return f"deterministic-core rule: rewrite dropped literal(s) {lost}"
    story.update({k: candidate[k] for k in ("title", "narrative", "description", "acceptanceCriteria")})
    story["storyPoints"] = bm.snap_points(upd.get("storyPoints", story["storyPoints"]))
    if upd.get("priority") in bm.PRIORITIES:
        story["priority"] = upd["priority"]
    labels = [x for x in (upd.get("labels") or []) if isinstance(x, str) and SAFE_LABEL.match(x)]
    story["labels"] = sorted(set(story.get("labels", [])) | set(labels))[:8]
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
        rules = {r["ruleId"]: r for r in by_sir.get(feature["sirId"], {}).get("rules", [])}
        updates = {u.get("id"): u for u in parsed.get("stories") or [] if isinstance(u, dict)}
        ids = {s["id"] for s in subset}
        for story in subset:
            upd = updates.get(story["id"])
            if not upd:
                continue
            why = _apply_story(story, upd, rules.get(story["trace"].get("ruleId")))
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
    issues = [{"level": lvl, "message": msg} for lvl, msg in bm.validate(backlog)]
    out = artifacts_dir(eng["id"])
    (out / "sir.json").write_text(json.dumps({"semantic_ir": sirs}, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "backlog.json").write_text(json.dumps(backlog, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "backlog.md").write_text(bm.backlog_markdown(backlog), encoding="utf-8")
    scripts_out = out / "scripts"
    scripts_out.mkdir(exist_ok=True)
    for f in ("sir_to_stories.py", "backlog_model.py", "push_backlog.py"):
        shutil.copy2(SCRIPTS_DIR / f, scripts_out / f)
    shutil.copy2(SKILL_DIR / "tracker-config.example.json", out / "tracker-config.example.json")
    eng["userStories"] = {
        "generatedAt": _now(), "scope": cap_id, "sirIds": [s["id"] for s in sirs], "backlog": backlog,
        "counts": bm.counts(backlog), "validation": issues, "refinement": refinement,
        "epicDetermination": {"status": "llm" if determined else "deterministic", "model": epic_model},
        "files": ["sir.json", "backlog.json", "backlog.md", "scripts/sir_to_stories.py", "scripts/backlog_model.py",
                  "scripts/push_backlog.py", "tracker-config.example.json"],
        "commands": [
            "python scripts/sir_to_stories.py sir.json --out backlog.json --markdown backlog.md",
            "python scripts/push_backlog.py validate backlog.json",
            "python scripts/push_backlog.py push backlog.json --provider jira --config tracker-config.json",
        ],
        "lastPush": None,
    }
    return store.save(eng)


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
