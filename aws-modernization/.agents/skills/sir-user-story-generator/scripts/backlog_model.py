"""Backlog schema, validation and renderers for the SIR -> user story generator.

Shape (nested; every id is stable and every story keeps a `trace` back to the legacy code):

    {"schemaVersion": "1.0", "generatedAt": ..., "source": {...},
     "epics": [{"id": "EP-CLAIM", "title", "module", "description", "businessOutcome", "labels", "narrativeSource",
                "features": [{"id": "FT-SIR-001", "title", "description", "sirId", "stateMachine",
                              "sideEffects", "inputs", "labels", "narrativeSource",
                              "stories": [{"id": "US-SIR-001-01", "type": "functional|flow|enabler", "title",
                                           "narrative": {"asA", "iWant", "soThat"}, "description",
                                           "acceptanceCriteria": ["Scenario: ..."], "storyPoints", "priority",
                                           "labels", "narrativeSource": "template|refined",
                                           "trustBoundary", "classification",
                                           "trace": {"sirId", "ruleId", "ruleIds", "legacyLines", "snippet",
                                                     "astNode"}}]}]}],
     "openQuestions": [{"id", "storyId", "question"}]}

Standard library only.
"""
from __future__ import annotations

import html
import re
from typing import Iterator

SCHEMA_VERSION = "1.0"
FIBONACCI = (1, 2, 3, 5, 8, 13, 21)
MAX_POINTS = 8
PRIORITIES = ("Must", "Should", "Could", "Won't")
STORY_TYPES = ("functional", "flow", "enabler")
NARRATIVE_SOURCES = ("template", "refined")
TRACE_FIELDS = ("sirId", "ruleId", "ruleIds", "legacyLines", "snippet", "astNode")


def iter_features(backlog: dict) -> Iterator[tuple[dict, dict]]:
    for epic in backlog.get("epics", []):
        for feature in epic.get("features", []):
            yield epic, feature


def iter_stories(backlog: dict) -> Iterator[tuple[dict, dict, dict]]:
    for epic, feature in iter_features(backlog):
        for story in feature.get("stories", []):
            yield epic, feature, story


def counts(backlog: dict) -> dict:
    stories = [s for _, _, s in iter_stories(backlog)]
    return {
        "epics": len(backlog.get("epics", [])),
        "features": sum(1 for _ in iter_features(backlog)),
        "stories": len(stories),
        "storyPoints": sum(s.get("storyPoints") or 0 for s in stories),
        "refined": sum(1 for s in stories if s.get("narrativeSource") == "refined"),
        "template": sum(1 for s in stories if s.get("narrativeSource") != "refined"),
        "openQuestions": len(backlog.get("openQuestions", [])),
    }


def snap_points(value) -> int:
    """Nearest Fibonacci story size, capped at MAX_POINTS (bigger work must be split)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 3
    return min((f for f in FIBONACCI if f <= MAX_POINTS), key=lambda f: (abs(f - v), f))


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-").upper() or "GENERAL"


# --------------------------------------------------------------------------- validation

def validate(backlog: dict) -> list[tuple[str, str]]:
    """Returns [(level, message)] where level is ERROR or WARN. An empty list means clean."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def dup(kind: str, ident: str):
        if not ident:
            out.append(("ERROR", f"{kind} without an id"))
        elif ident in seen:
            out.append(("ERROR", f"duplicate id {ident}"))
        seen.add(ident)

    if not backlog.get("epics"):
        out.append(("ERROR", "backlog has no epics"))
    for epic in backlog.get("epics", []):
        dup("epic", epic.get("id", ""))
        if not epic.get("title"):
            out.append(("ERROR", f"{epic.get('id')}: epic has no title"))
        if not epic.get("features"):
            out.append(("ERROR", f"{epic.get('id')}: epic has no features"))
        for feature in epic.get("features", []):
            dup("feature", feature.get("id", ""))
            if not feature.get("title"):
                out.append(("ERROR", f"{feature.get('id')}: feature has no title"))
            if not feature.get("stories"):
                out.append(("ERROR", f"{feature.get('id')}: feature has no stories"))
            for story in feature.get("stories", []):
                sid = story.get("id", "")
                dup("story", sid)
                if story.get("type") not in STORY_TYPES:
                    out.append(("ERROR", f"{sid}: type must be one of {STORY_TYPES}"))
                if not story.get("title"):
                    out.append(("ERROR", f"{sid}: story has no title"))
                nar = story.get("narrative") or {}
                for part in ("asA", "iWant", "soThat"):
                    if not str(nar.get(part, "")).strip():
                        out.append(("ERROR", f"{sid}: narrative.{part} is empty"))
                ac = story.get("acceptanceCriteria") or []
                if not ac:
                    out.append(("ERROR", f"{sid}: no acceptance criteria"))
                for i, a in enumerate(ac, 1):
                    if not str(a).lstrip().startswith(("Scenario:", "Scenario Outline:")):
                        out.append(("ERROR", f"{sid}: acceptance criterion {i} must start with 'Scenario:'"))
                pts = story.get("storyPoints")
                if pts not in FIBONACCI:
                    out.append(("ERROR", f"{sid}: storyPoints {pts!r} is not a Fibonacci size"))
                elif pts > MAX_POINTS:
                    out.append(("ERROR", f"{sid}: {pts} points is over {MAX_POINTS}; split into sibling stories"))
                if story.get("priority") not in PRIORITIES:
                    out.append(("ERROR", f"{sid}: priority must be one of {PRIORITIES}"))
                if story.get("narrativeSource") not in NARRATIVE_SOURCES:
                    out.append(("ERROR", f"{sid}: narrativeSource must be one of {NARRATIVE_SOURCES}"))
                trace = story.get("trace") or {}
                if not trace.get("sirId"):
                    out.append(("ERROR", f"{sid}: trace.sirId missing"))
                if story.get("type") == "functional" and not trace.get("ruleId"):
                    out.append(("ERROR", f"{sid}: functional story needs trace.ruleId"))
                if story.get("narrativeSource") == "template":
                    out.append(("WARN", f"{sid}: still template wording (not refined)"))
    for q in backlog.get("openQuestions", []):
        if not q.get("question"):
            out.append(("ERROR", f"open question {q.get('id')} is empty"))
    return out


# --------------------------------------------------------------------------- renderers

def _narrative(story: dict) -> str:
    n = story.get("narrative") or {}
    return f"As a {n.get('asA', '')}, I want {n.get('iWant', '')}, so that {n.get('soThat', '')}."


def backlog_markdown(backlog: dict) -> str:
    c = counts(backlog)
    lines = [f"# Backlog: {', '.join(e['title'] for e in backlog.get('epics', [])) or 'empty'}", "",
             f"{c['epics']} epic(s) · {c['features']} feature(s) · {c['stories']} stories · "
             f"{c['storyPoints']} points · {c['refined']} refined / {c['template']} template", ""]
    for epic in backlog.get("epics", []):
        lines += [f"## Epic {epic['id']}: {epic['title']}", ""]
        if epic.get("businessOutcome"):
            lines += [f"**Business outcome:** {epic['businessOutcome']}", ""]
        if epic.get("description"):
            lines += [epic["description"], ""]
        for feature in epic.get("features", []):
            lines += [f"### Feature {feature['id']}: {feature['title']}", ""]
            if feature.get("description"):
                lines += [feature["description"], ""]
            for s in feature.get("stories", []):
                lines += [f"#### {s['id']}: {s['title']}",
                          f"*{s.get('type')} · {s.get('storyPoints')} pts · {s.get('priority')} · "
                          f"{s.get('narrativeSource')}*", "", _narrative(s), ""]
                if s.get("description"):
                    lines += [s["description"], ""]
                lines += ["**Acceptance criteria**", "", "```gherkin"]
                for a in s.get("acceptanceCriteria", []):
                    lines += [a, ""]
                lines[-1:] = ["```"]
                t = s.get("trace") or {}
                lines += ["", f"Trace: `{t.get('sirId')}` rule `{t.get('ruleId')}` · legacy `{t.get('legacyLines')}`"
                              f" · `{t.get('astNode')}`", ""]
    if backlog.get("openQuestions"):
        lines += ["## Open questions", ""]
        lines += [f"- **{q.get('storyId') or 'general'}**: {q['question']}" for q in backlog["openQuestions"]]
    return "\n".join(lines).rstrip() + "\n"


def story_html(story: dict) -> str:
    """HTML body used by Azure DevOps (description field)."""
    t = story.get("trace") or {}
    e = html.escape
    parts = [f"<p>{e(_narrative(story))}</p>"]
    if story.get("description"):
        parts.append(f"<p>{e(story['description'])}</p>")
    parts.append("<p><b>Legacy trace</b><br/>" + e(f"{t.get('sirId')} / {t.get('ruleId')} / {t.get('legacyLines')} / "
                                                   f"{t.get('astNode')}") + "</p>")
    if t.get("snippet"):
        parts.append(f"<pre>{e(t['snippet'])}</pre>")
    return "".join(parts)


def acceptance_html(story: dict) -> str:
    return "".join(f"<pre>{html.escape(a)}</pre>" for a in story.get("acceptanceCriteria", []))


def item_markdown(item: dict) -> str:
    """Markdown body for GitHub / Bitbucket issues."""
    lines: list[str] = []
    if item["level"] == "story":
        s = item["story"]
        t = s.get("trace") or {}
        lines += [_narrative(s), ""]
        if s.get("description"):
            lines += [s["description"], ""]
        lines += ["### Acceptance criteria", "", "```gherkin"]
        for a in s.get("acceptanceCriteria", []):
            lines += [a, ""]
        lines[-1:] = ["```", "", "### Legacy trace",
                      f"- SIR `{t.get('sirId')}` · rule `{t.get('ruleId')}`",
                      f"- Legacy lines: `{t.get('legacyLines')}` · AST node `{t.get('astNode')}`"]
        if t.get("snippet"):
            lines += ["", "```", t["snippet"], "```"]
        lines += ["", f"_{s.get('storyPoints')} story points · {s.get('priority')}_"]
    else:
        src = item["epic"] if item["level"] == "epic" else item["feature"]
        lines += [src.get("description") or src.get("title", "")]
        if src.get("businessOutcome"):
            lines += ["", f"**Business outcome:** {src['businessOutcome']}"]
        if item["level"] == "feature":
            f = item["feature"]
            if f.get("stateMachine"):
                lines += ["", f"State flow: `{f['stateMachine']}`"]
            for fx in f.get("sideEffects", []):
                lines += [f"- {fx}"]
    lines += ["", f"<!-- backlog-id: {item['id']} -->"]
    return "\n".join(lines)


# Atlassian Document Format (Jira Cloud REST v3) ---------------------------------------------------

def _adt(text: str) -> dict:
    return {"type": "text", "text": text}


def _adf_p(text: str) -> dict:
    return {"type": "paragraph", "content": [_adt(text)] if text else []}


def _adf_code(text: str, lang: str | None = None) -> dict:
    node = {"type": "codeBlock", "content": [_adt(text)]}
    if lang:
        node["attrs"] = {"language": lang}
    return node


def _adf_h(text: str, level: int = 3) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": [_adt(text)]}


def adf(item: dict) -> dict:
    """Jira Cloud description (ADF) for an epic / feature / story item."""
    doc: list[dict] = []
    if item["level"] == "story":
        s = item["story"]
        t = s.get("trace") or {}
        doc += [_adf_p(_narrative(s))]
        if s.get("description"):
            doc.append(_adf_p(s["description"]))
        doc.append(_adf_h("Acceptance criteria"))
        doc += [_adf_code(a, "gherkin") for a in s.get("acceptanceCriteria", [])]
        doc += [_adf_h("Legacy trace"),
                _adf_p(f"SIR {t.get('sirId')} · rule {t.get('ruleId')} · {t.get('legacyLines')} · {t.get('astNode')}")]
        if t.get("snippet"):
            doc.append(_adf_code(t["snippet"]))
    else:
        src = item["epic"] if item["level"] == "epic" else item["feature"]
        doc.append(_adf_p(src.get("description") or src.get("title", "")))
        if src.get("businessOutcome"):
            doc.append(_adf_p(f"Business outcome: {src['businessOutcome']}"))
        if item["level"] == "feature":
            f = item["feature"]
            if f.get("stateMachine"):
                doc.append(_adf_code(f["stateMachine"]))
            for fx in f.get("sideEffects", []):
                doc.append(_adf_p(f"• {fx}"))
    doc.append(_adf_p(f"backlog-id: {item['id']}"))
    return {"type": "doc", "version": 1, "content": doc}


def jira_wiki(item: dict) -> str:
    """Jira Server/DC wiki-markup description."""
    if item["level"] != "story":
        src = item["epic"] if item["level"] == "epic" else item["feature"]
        return f"{src.get('description') or src.get('title', '')}\n\nbacklog-id: {item['id']}"
    s = item["story"]
    t = s.get("trace") or {}
    body = [_narrative(s), "", "h3. Acceptance criteria"]
    body += [f"{{code}}\n{a}\n{{code}}" for a in s.get("acceptanceCriteria", [])]
    body += ["h3. Legacy trace", f"{t.get('sirId')} / {t.get('ruleId')} / {t.get('legacyLines')}",
             f"\nbacklog-id: {item['id']}"]
    return "\n".join(body)


# --------------------------------------------------------------------------- flattening for pushes

def flatten(backlog: dict) -> list[dict]:
    """Ordered work items: every epic, then its features, then their stories, each with its parent id."""
    items: list[dict] = []
    for epic in backlog.get("epics", []):
        items.append({"id": epic["id"], "level": "epic", "parent": None, "title": epic["title"],
                      "labels": list(epic.get("labels", [])), "epic": epic})
        for feature in epic.get("features", []):
            items.append({"id": feature["id"], "level": "feature", "parent": epic["id"], "title": feature["title"],
                          "labels": list(feature.get("labels", [])), "feature": feature, "epic": epic})
            for story in feature.get("stories", []):
                items.append({"id": story["id"], "level": "story", "parent": feature["id"], "title": story["title"],
                              "labels": list(story.get("labels", [])), "story": story, "feature": feature,
                              "epic": epic})
    return items
