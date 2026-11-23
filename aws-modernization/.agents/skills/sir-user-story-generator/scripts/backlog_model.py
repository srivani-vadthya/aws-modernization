"""Backlog schema, validation and renderers for the SIR -> user story generator.

Shape (nested; every id is stable and every story keeps a `trace` back to the legacy code). Epic = module,
Feature = business area, Story = one business use case (one SIR contract):

    {"schemaVersion": "1.0", "generatedAt": ..., "source": {...},
     "epics": [{"id": "EP-INVOICE", "title", "module", "description", "businessOutcome", "labels", "narrativeSource",
                "features": [{"id": "FT-INVOICE-SOA", "title", "description", "sirIds", "labels", "narrativeSource",
                              "stories": [{"id": "US-SIR-002", "type": "functional", "title",
                                           "narrative": {"asA", "iWant", "soThat"}, "description",
                                           "acceptanceCriteria": ["Given ..., when ..., then ... (R1, R2)"],
                                           "storyPoints", "priority", "labels", "narrativeSource": "template|refined",
                                           "behaviour", "estimation", "trustBoundary", "classification",
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
MAX_POINTS = 13          # 13 is allowed but should be split; 21 must be split
SPLIT_ADVISED = 8
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
        "storyPoints": sum(s.get("storyPoints") or 0 for s in stories),   # sized on business complexity
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


def is_criterion(text) -> bool:
    """One acceptance criterion: a single 'Given ..., when ..., then ...' line (Gherkin 'Scenario:' also accepted)."""
    t = str(text).strip().lower()
    return t.startswith(("scenario:", "scenario outline:")) or (t.startswith("given ") and " then " in t)


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
                elif len(ac) > SPLIT_ADVISED:
                    out.append(("WARN", f"{sid}: {len(ac)} acceptance criteria; consider splitting into smaller stories"))
                for i, a in enumerate(ac, 1):
                    if not is_criterion(a):
                        out.append(("ERROR", f"{sid}: acceptance criterion {i} must read 'Given ..., when ..., "
                                             "then ...'"))
                pts = story.get("storyPoints")
                if pts not in FIBONACCI:
                    out.append(("ERROR", f"{sid}: storyPoints {pts!r} is not a Fibonacci size"))
                elif pts > MAX_POINTS:
                    out.append(("ERROR", f"{sid}: {pts} points is over {MAX_POINTS}; split into sibling stories"))
                elif pts > SPLIT_ADVISED:
                    out.append(("WARN", f"{sid}: {pts} points; consider splitting into smaller stories"))
                est = story.get("estimation") or {}
                if isinstance(pts, int) and est.get("points") and pts < est["points"] and "manualPoints" not in est:
                    out.append(("ERROR", f"{sid}: storyPoints {pts} is below its business-complexity estimate "
                                         f"{est['points']}"))
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
# A story is rendered as the user story only: its title ("As a ..., I want ... so that ..."), description,
# acceptance criteria (one 'Given ..., when ..., then ...' line each), labels, story points and the epic /
# feature it belongs to. Legacy trace and the estimation breakdown stay in backlog.json but are not rendered.

def _belongs_to(epic: dict | None, feature: dict | None) -> str:
    return " › ".join(x["title"] for x in (epic, feature) if x)


def _story_lines(s: dict, epic: dict | None, feature: dict | None, heading: str) -> list[str]:
    lines = []
    if s.get("description"):
        lines += [s["description"], ""]
    lines += [f"**Story points:** {s.get('storyPoints')}  ", f"**Epic / Feature:** {_belongs_to(epic, feature)}"]
    if s.get("labels"):
        lines[-1] += "  "
        lines.append(f"**Labels:** {', '.join(s['labels'])}")
    lines += ["", heading.format("Acceptance criteria"), ""] + [f"- {a}" for a in s.get("acceptanceCriteria", [])]
    return lines


def backlog_markdown(backlog: dict) -> str:
    c = counts(backlog)
    lines = [f"# Backlog: {', '.join(e['title'] for e in backlog.get('epics', [])) or 'empty'}", "",
             f"{c['epics']} epic(s) · {c['features']} feature(s) · {c['stories']} stories · "
             f"{c['storyPoints']} story points", "",
             "*Story points are sized on business complexity (business rules, process scope, business "
             "uncertainty), not on technical details.*", ""]
    for epic in backlog.get("epics", []):
        lines += [f"## Epic: {epic['title']}", ""]
        for feature in epic.get("features", []):
            lines += [f"### Feature: {feature['title']}", ""]
            for s in feature.get("stories", []):
                lines += [f"#### {s['id']}: {s['title']}", ""] + _story_lines(s, epic, feature, "**{}**") + [""]
    if backlog.get("openQuestions"):
        titles = {s["id"]: s["title"] for _, _, s in iter_stories(backlog)}
        lines += ["## Open questions", ""]
        lines += [f"- **{titles.get(q.get('storyId')) or 'General'}**: {q['question']}" for q in backlog["openQuestions"]]
    return "\n".join(lines).rstrip() + "\n"


def story_html(story: dict, epic: dict | None = None, feature: dict | None = None) -> str:
    """HTML body used by Azure DevOps (description field). Story points, labels and AC have their own fields."""
    e = html.escape
    parts = [f"<p>{e(story['description'])}</p>"] if story.get("description") else []
    if epic or feature:
        parts.append(f"<p><b>Epic / Feature:</b> {e(_belongs_to(epic, feature))}</p>")
    return "".join(parts)


def acceptance_html(story: dict) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(a)}</li>" for a in story.get("acceptanceCriteria", [])) + "</ul>"


def item_markdown(item: dict) -> str:
    """Markdown body for GitHub / Bitbucket issues."""
    lines: list[str] = []
    if item["level"] == "story":
        lines += _story_lines(item["story"], item.get("epic"), item.get("feature"), "### {}")
    else:
        src = item["epic"] if item["level"] == "epic" else item["feature"]
        lines += [src.get("title", "")]
        if item["level"] == "feature":
            lines += ["", f"**Epic:** {item['epic']['title']}"]
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
        if s.get("description"):
            doc.append(_adf_p(s["description"]))
        doc += [_adf_p(f"Story points: {s.get('storyPoints')}"),
                _adf_p(f"Epic / Feature: {_belongs_to(item.get('epic'), item.get('feature'))}"),
                _adf_h("Acceptance criteria"),
                {"type": "bulletList", "content": [{"type": "listItem", "content": [_adf_p(a)]}
                                                   for a in s.get("acceptanceCriteria", [])]}]
    else:
        src = item["epic"] if item["level"] == "epic" else item["feature"]
        doc.append(_adf_p(src.get("title", "")))
        if item["level"] == "feature":
            doc.append(_adf_p(f"Epic: {item['epic']['title']}"))
    doc.append(_adf_p(f"backlog-id: {item['id']}"))
    return {"type": "doc", "version": 1, "content": doc}


def jira_wiki(item: dict) -> str:
    """Jira Server/DC wiki-markup description."""
    if item["level"] != "story":
        src = item["epic"] if item["level"] == "epic" else item["feature"]
        return f"{src.get('title', '')}\n\nbacklog-id: {item['id']}"
    s = item["story"]
    body = ([s["description"], ""] if s.get("description") else []) + [
        f"*Story points:* {s.get('storyPoints')}",
        f"*Epic / Feature:* {_belongs_to(item.get('epic'), item.get('feature'))}", "", "h3. Acceptance criteria"]
    body += [f"* {a}" for a in s.get("acceptanceCriteria", [])]
    body += [f"\nbacklog-id: {item['id']}"]
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
