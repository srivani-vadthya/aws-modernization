from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(item: dict[str, Any]) -> str:
    payload = json.dumps(item, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def detect_human_actions(engagement: dict[str, Any], run_id: str | None = None) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seed = engagement.get("seed") or {}
    scope = engagement.get("scope") or {}
    target = seed.get("target") or {}
    if not target.get("approved"):
        actions.append({
            "id": "HA-001",
            "runId": run_id,
            "engagementId": engagement.get("id"),
            "category": "source-gap",
            "title": "Target technology must be explicitly approved",
            "description": "No validated user-approved target contract is available for migration execution.",
            "affectedComponent": "target.contract",
            "phase": "modernize",
            "reasonHumanActionRequired": "The target stack must be selected and approved by the user before a migration run can start.",
            "requiredAction": "Capture the canonical target contract and approval evidence in the engagement.",
            "priority": "CRITICAL",
            "dependencyIds": ["target.contract"],
            "suggestedOwnerRole": "Solution Architect",
            "status": "OPEN",
            "evidence": [{"source": "engagement.seed.target", "detail": "target approval missing"}],
            "observedCheck": "target validation",
            "firstSeenAt": _now(),
            "lastSeenAt": _now(),
            "resolutionNote": "",
        })
    if not scope:
        actions.append({
            "id": "HA-002",
            "runId": run_id,
            "engagementId": engagement.get("id"),
            "category": "dependency",
            "title": "Scoped module is not selected",
            "description": "Migration cannot proceed without a verified business scope.",
            "affectedComponent": "scope",
            "phase": "scope",
            "reasonHumanActionRequired": "No scope has been approved for this engagement.",
            "requiredAction": "Select and approve the migration scope in the engagement UI or API.",
            "priority": "CRITICAL",
            "dependencyIds": ["scope"],
            "suggestedOwnerRole": "Business Analyst",
            "status": "OPEN",
            "evidence": [{"source": "engagement.scope", "detail": "scope missing"}],
            "observedCheck": "scope validation",
            "firstSeenAt": _now(),
            "lastSeenAt": _now(),
            "resolutionNote": "",
        })
    if engagement.get("sourceType") == "sample" and not scope.get("capabilityId"):
        actions.append({
            "id": "HA-003",
            "runId": run_id,
            "engagementId": engagement.get("id"),
            "category": "source-gap",
            "title": "Sample engagement is not a production-validated migration target",
            "description": "The sample fixture is a local demo and not evidence of a production system.",
            "affectedComponent": "source.sample",
            "phase": "validation",
            "reasonHumanActionRequired": "Demo fixtures must be labelled as simulated and cannot certify production readiness.",
            "requiredAction": "Replace or review the sample with a real legacy source before release certification.",
            "priority": "MEDIUM",
            "dependencyIds": ["sample"],
            "suggestedOwnerRole": "Product Owner",
            "status": "OPEN",
            "evidence": [{"source": "engagement.sourceType", "detail": "sample"}],
            "observedCheck": "sample fixture review",
            "firstSeenAt": _now(),
            "lastSeenAt": _now(),
            "resolutionNote": "",
        })

    deduped: dict[str, dict[str, Any]] = {}
    for action in actions:
        fp = _fingerprint({"title": action["title"], "category": action["category"], "engagementId": action["engagementId"]})
        deduped.setdefault(fp, action)
    return list(deduped.values())


def render_human_actions_markdown(actions: list[dict[str, Any]], *, engagement: dict[str, Any] | None = None, run_id: str | None = None) -> str:
    total = len(actions)
    open_count = sum(1 for a in actions if a.get("status") == "OPEN")
    critical_count = sum(1 for a in actions if a.get("priority") == "CRITICAL")
    lines = [
        "# Human Action Required",
        "",
        f"- Run ID: {run_id or 'n/a'}",
        f"- Engagement ID: {engagement.get('id') if engagement else 'n/a'}",
        f"- Source type: {engagement.get('sourceType') if engagement else 'n/a'}",
        f"- Target: {((engagement or {}).get('seed') or {}).get('target') if engagement else 'n/a'}",
        "",
        f"- Total records: {total}",
        f"- Open: {open_count}",
        f"- Critical: {critical_count}",
        ""
    ]
    if not actions:
        lines.append("No verified human actions found in checks executed.")
        lines.append("Unperformed checks: build/test validation, external integration validation, and production credential review.")
        return "\n".join(lines) + "\n"
    lines.append("| Priority | Status | Title | Affected component | Owner |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in actions:
        lines.append(f"| {item.get('priority', 'MEDIUM')} | {item.get('status', 'OPEN')} | {item.get('title', 'Untitled')} | {item.get('affectedComponent', 'n/a')} | {item.get('suggestedOwnerRole', 'n/a')} |")
    lines.append("")
    for item in actions:
        lines.append(f"## {item.get('title')}")
        lines.append(f"- Category: {item.get('category')}")
        lines.append(f"- Reason: {item.get('reasonHumanActionRequired')}")
        lines.append(f"- Required action: {item.get('requiredAction')}")
        lines.append(f"- Evidence: {json.dumps(item.get('evidence', []), default=str)}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_human_action_artifacts(base_dir: str | Path, actions: list[dict[str, Any]], *, engagement: dict[str, Any] | None = None, run_id: str | None = None) -> dict[str, str]:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    json_path = base / "human-actions.json"
    md_path = base / "HUMAN_ACTION_REQUIRED.md"
    json_path.write_text(json.dumps(actions, indent=2), encoding="utf-8")
    md_path.write_text(render_human_actions_markdown(actions, engagement=engagement, run_id=run_id), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
