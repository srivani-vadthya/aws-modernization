from __future__ import annotations

import json
import re
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from ..module_context.repository import ContextError, engagement_root, safe_child
from .models import ExecutionLog, ExecutionRecord, ModernizationPlan, ModernizationRun, OrchestrationRecord


def now() -> datetime:
    return datetime.now(timezone.utc)


def runs_root(eid: str) -> Path:
    return safe_child(engagement_root(eid), "artifacts/modernization-engine-runs")


def run_root(eid: str, run_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ContextError("Modernization run not found", 404)
    return safe_child(runs_root(eid), run_id)


def load(eid: str, run_id: str) -> ModernizationRun:
    path = safe_child(run_root(eid, run_id), "run.json")
    if not path.is_file():
        raise ContextError("Modernization run not found", 404)
    try:
        return ModernizationRun.model_validate_json(path.read_bytes())
    except (ValueError, OSError) as exc:
        raise ContextError("Modernization run is malformed", 409) from exc


def list_runs(eid: str, module_id: str | None = None) -> list[ModernizationRun]:
    root = runs_root(eid)
    if not root.exists():
        return []
    items = []
    for child in root.iterdir():
        if re.fullmatch(r"[a-f0-9]{32}", child.name) and child.is_dir():
            item = load(eid, child.name)
            if module_id is None or item.moduleId == module_id:
                items.append(item)
    return sorted(items, key=lambda item: item.createdAt, reverse=True)


def create(run: ModernizationRun) -> ModernizationRun:
    root = runs_root(run.engagementId)
    root.mkdir(parents=True, exist_ok=True)
    target = run_root(run.engagementId, run.runId)
    if target.exists():
        raise ContextError("Modernization run already exists", 409)
    staging = safe_child(root, ".staging-" + run.runId)
    staging.mkdir()
    try:
        safe_child(staging, "run.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
        staging.rename(target)
    except BaseException:
        if staging.exists() and staging.resolve().parent == root.resolve():
            import shutil
            shutil.rmtree(staging)
        raise
    return load(run.engagementId, run.runId)


def plans_root(eid: str) -> Path:
    return safe_child(engagement_root(eid), "artifacts/modernization-plans")


def plan_root(eid: str, plan_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", plan_id):
        raise ContextError("Modernization plan not found", 404)
    return safe_child(plans_root(eid), plan_id)


def load_plan(eid: str, plan_id: str) -> ModernizationPlan:
    path = safe_child(plan_root(eid, plan_id), "plan.json")
    if not path.is_file():
        raise ContextError("Modernization plan not found", 404)
    try:
        return ModernizationPlan.model_validate_json(path.read_bytes())
    except (ValueError, OSError) as exc:
        raise ContextError("Modernization plan is malformed", 409) from exc


def list_plans(eid: str, module_id: str | None = None) -> list[ModernizationPlan]:
    root = plans_root(eid)
    if not root.exists():
        return []
    result = [load_plan(eid, p.name) for p in root.iterdir()
              if re.fullmatch(r"[a-f0-9]{32}", p.name) and p.is_dir()]
    return sorted((p for p in result if module_id is None or p.moduleId == module_id), key=lambda p: p.createdAt, reverse=True)


def create_plan(plan: ModernizationPlan) -> ModernizationPlan:
    root = plans_root(plan.engagementId)
    root.mkdir(parents=True, exist_ok=True)
    target = plan_root(plan.engagementId, plan.planId)
    if target.exists():
        raise ContextError("Modernization plan already exists", 409)
    staging = safe_child(root, ".staging-" + plan.planId)
    staging.mkdir()
    try:
        safe_child(staging, "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        staging.rename(target)
    except BaseException:
        if staging.exists() and staging.resolve().parent == root.resolve():
            import shutil
            shutil.rmtree(staging)
        raise
    return load_plan(plan.engagementId, plan.planId)


def update_plan(plan: ModernizationPlan) -> ModernizationPlan:
    path = safe_child(plan_root(plan.engagementId, plan.planId), "plan.json")
    if not path.is_file(): raise ContextError("Modernization plan not found", 404)
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return load_plan(plan.engagementId, plan.planId)


def orchestrations_root(eid: str) -> Path:
    return safe_child(engagement_root(eid), "artifacts/modernization-orchestrations")


def orchestration_root(eid: str, orchestration_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", orchestration_id):
        raise ContextError("Orchestration record not found", 404)
    return safe_child(orchestrations_root(eid), orchestration_id)


def load_orchestration(eid: str, orchestration_id: str) -> OrchestrationRecord:
    path = safe_child(orchestration_root(eid, orchestration_id), "orchestration.json")
    if not path.is_file():
        raise ContextError("Orchestration record not found", 404)
    try:
        return OrchestrationRecord.model_validate_json(path.read_bytes())
    except (ValueError, OSError) as exc:
        raise ContextError("Orchestration record is malformed", 409) from exc


def list_orchestrations(eid: str, module_id: str | None = None) -> list[OrchestrationRecord]:
    root = orchestrations_root(eid)
    if not root.exists():
        return []
    result = [load_orchestration(eid, p.name) for p in root.iterdir()
              if re.fullmatch(r"[a-f0-9]{32}", p.name) and p.is_dir()]
    return sorted((o for o in result if module_id is None or o.moduleId == module_id), key=lambda o: o.createdAt, reverse=True)


def create_orchestration(record: OrchestrationRecord) -> OrchestrationRecord:
    root = orchestrations_root(record.engagementId)
    root.mkdir(parents=True, exist_ok=True)
    target = orchestration_root(record.engagementId, record.orchestrationId)
    if target.exists():
        raise ContextError("Orchestration record already exists", 409)
    staging = safe_child(root, ".staging-" + record.orchestrationId)
    staging.mkdir()
    try:
        safe_child(staging, "orchestration.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")
        staging.rename(target)
    except BaseException:
        if staging.exists() and staging.resolve().parent == root.resolve():
            import shutil
            shutil.rmtree(staging)
        raise
    return load_orchestration(record.engagementId, record.orchestrationId)


def update_orchestration(record: OrchestrationRecord) -> OrchestrationRecord:
    path = safe_child(orchestration_root(record.engagementId, record.orchestrationId), "orchestration.json")
    if not path.is_file(): raise ContextError("Orchestration record not found", 404)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return load_orchestration(record.engagementId, record.orchestrationId)


def executions_root(eid: str) -> Path:
    return safe_child(engagement_root(eid), "artifacts/modernization-executions")


def execution_root(eid: str, execution_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", execution_id):
        raise ContextError("Execution record not found", 404)
    return safe_child(executions_root(eid), execution_id)


def load_execution(eid: str, execution_id: str) -> ExecutionRecord:
    path = safe_child(execution_root(eid, execution_id), "execution.json")
    if not path.is_file(): raise ContextError("Execution record not found", 404)
    try: return ExecutionRecord.model_validate_json(path.read_bytes())
    except (ValueError, OSError) as exc: raise ContextError("Execution record is malformed", 409) from exc


def list_executions(eid: str, module_id: str | None = None) -> list[ExecutionRecord]:
    root = executions_root(eid)
    if not root.exists(): return []
    result = [load_execution(eid, child.name) for child in root.iterdir() if re.fullmatch(r"[a-f0-9]{32}", child.name) and child.is_dir()]
    return sorted((item for item in result if module_id is None or item.moduleId == module_id), key=lambda item: item.createdAt, reverse=True)


def create_execution(record: ExecutionRecord) -> ExecutionRecord:
    root = executions_root(record.engagementId); root.mkdir(parents=True, exist_ok=True)
    target = execution_root(record.engagementId, record.executionId)
    if target.exists(): raise ContextError("Execution record already exists", 409)
    staging = safe_child(root, ".staging-" + record.executionId); staging.mkdir()
    try:
        safe_child(staging, "execution.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")
        staging.rename(target)
    except BaseException:
        if staging.exists() and staging.resolve().parent == root.resolve():
            import shutil; shutil.rmtree(staging)
        raise
    return load_execution(record.engagementId, record.executionId)


def update_execution(record: ExecutionRecord) -> ExecutionRecord:
    path = safe_child(execution_root(record.engagementId, record.executionId), "execution.json")
    if not path.is_file(): raise ContextError("Execution record not found", 404)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return load_execution(record.engagementId, record.executionId)


def append_execution_log(eid: str, execution_id: str, log: ExecutionLog) -> ExecutionRecord:
    """Persist provider progress immediately so browser polling sees live events."""
    record = load_execution(eid, execution_id)
    return update_execution(record.model_copy(update={"logs": [*record.logs, log], "updatedAt": now()}))


def _lock_path(eid: str, execution_id: str, task_id: str) -> Path:
    name = hashlib.sha256(task_id.encode("utf-8")).hexdigest() + ".lock"
    return safe_child(execution_root(eid, execution_id), "locks/" + name)


def acquire_task_lock(eid: str, execution_id: str, task_id: str, owner: str, now: datetime) -> bool:
    """Atomic only on this local filesystem: O_EXCL prevents concurrent local processes."""
    path = _lock_path(eid, execution_id, task_id); path.parent.mkdir(exist_ok=True)
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle: handle.write(json.dumps({"owner": owner, "at": now.isoformat()}))
        return True
    except FileExistsError: return False


def release_task_lock(eid: str, execution_id: str, task_id: str, owner: str) -> bool:
    path = _lock_path(eid, execution_id, task_id)
    if not path.exists(): return False
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return False
    if data.get("owner") != owner: return False
    path.unlink(); return True
