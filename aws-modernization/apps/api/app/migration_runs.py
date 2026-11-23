from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import store
from .human_actions import detect_human_actions, write_human_action_artifacts


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_root(eid: str, run_id: str) -> Path:
    return store.engagement_dir(eid) / "artifacts" / "migration-runs" / run_id


def create_migration_run(eid: str, engagement: dict[str, Any], *, target: dict[str, Any] | None = None, scope: dict[str, Any] | None = None, note: str | None = None) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    root = run_root(eid, run_id)
    root.mkdir(parents=True, exist_ok=True)
    target_contract = target or ((engagement.get("seed") or {}).get("target") or {})
    scope_payload = scope or (engagement.get("scope") or {})
    run = {
        "runId": run_id,
        "engagementId": eid,
        "target": target_contract,
        "scope": scope_payload,
        "status": "QUEUED",
        "stage": "QUEUED",
        "phase": "modernize",
        "createdAt": _now(),
        "updatedAt": _now(),
        "attempt": 1,
        "attempts": [
            {"stage": "QUEUED", "timestamp": _now(), "status": "QUEUED", "note": note or "Migration queued"}
        ],
        "artifacts": {"manifest": [], "generated": [], "log": ""},
        "metrics": {},
        "blockers": [],
        "errors": [],
        "sourceDigest": None,
        "targetDigest": target_contract.get("configurationDigest"),
        "validation": {"result": "NOT_VALIDATED", "checks": []},
    }
    (root / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")

    actions = detect_human_actions(engagement, run_id)
    write_human_action_artifacts(root, actions, engagement=engagement, run_id=run_id)
    run["humanActions"] = actions
    (root / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    return run


def load_migration_run(eid: str, run_id: str) -> dict[str, Any] | None:
    path = run_root(eid, run_id) / "run.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def update_migration_run(eid: str, run_id: str, *, status: str | None = None, stage: str | None = None, error: str | None = None, artifacts: list[str] | None = None, metrics: dict[str, Any] | None = None, blockers: list[str] | None = None) -> dict[str, Any]:
    run = load_migration_run(eid, run_id)
    if not run:
        raise FileNotFoundError(f"Migration run {run_id} not found")
    if status:
        run["status"] = status
    if stage:
        run["stage"] = stage
        run.setdefault("attempts", []).append({"stage": stage, "timestamp": _now(), "status": status or run["status"]})
    if error:
        run.setdefault("errors", []).append({"timestamp": _now(), "message": error})
    if artifacts is not None:
        run["artifacts"]["manifest"] = artifacts
    if metrics is not None:
        run["metrics"].update(metrics)
    if blockers is not None:
        run["blockers"] = blockers
    run["updatedAt"] = _now()
    (run_root(eid, run_id) / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    return run


def list_migration_runs(eid: str) -> list[dict[str, Any]]:
    root = store.engagement_dir(eid) / "artifacts" / "migration-runs"
    runs: list[dict[str, Any]] = []
    if not root.exists():
        return runs
    for child in sorted(root.iterdir()):
        run_file = child / "run.json"
        if run_file.exists():
            runs.append(json.loads(run_file.read_text(encoding="utf-8")))
    return runs
