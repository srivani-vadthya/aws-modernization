"""Lifecycle and scheduling primitives. They do not invoke workers in this phase."""
from __future__ import annotations

import uuid
import hashlib
from ..module_context.repository import canonical
from .models import (Checkpoint, ExecutionEvent, ExecutionLog, ExecutionRecord, ExecutionStatus,
                     ExecutionTask, EXECUTION_TRANSITIONS, FailureRecord, TaskAttempt)


def _event(record: ExecutionRecord, to_status: ExecutionStatus, reason: str, now) -> ExecutionEvent:
    previous = record.statusHistory[-1].eventHash if record.statusHistory else ""
    sequence = len(record.statusHistory) + 1
    payload = {"sequence": sequence, "previousHash": previous, "fromStatus": record.status.value, "toStatus": to_status.value, "reason": reason, "at": now.isoformat()}
    return ExecutionEvent(at=now, fromStatus=record.status, toStatus=to_status, reason=reason, sequence=sequence, previousHash=previous, eventHash=hashlib.sha256(canonical(payload)).hexdigest())


def verify_events(record: ExecutionRecord) -> bool:
    if record.statusHistory and all(not event.eventHash for event in record.statusHistory):
        return True  # Backward-compatible historical Phase 2.4 records.
    previous = ""
    for index, event in enumerate(record.statusHistory, 1):
        if event.sequence != index or event.previousHash != previous: return False
        payload = {"sequence": index, "previousHash": previous, "fromStatus": event.fromStatus.value if event.fromStatus else None, "toStatus": event.toStatus.value, "reason": event.reason, "at": event.at.isoformat()}
        if event.eventHash != hashlib.sha256(canonical(payload)).hexdigest(): return False
        previous = event.eventHash
    return True


def transition(record: ExecutionRecord, to_status: ExecutionStatus, reason: str, now) -> ExecutionRecord:
    if to_status not in EXECUTION_TRANSITIONS[record.status]:
        raise ValueError(f"Invalid execution transition: {record.status} -> {to_status}")
    event = _event(record, to_status, reason, now)
    log = ExecutionLog(at=now, executionId=record.executionId, eventType="state-change", status=to_status, message=reason)
    return record.model_copy(update={"status": to_status, "updatedAt": now, "statusHistory": [*record.statusHistory, event], "logs": [*record.logs, log], "eventChainValid": True})


def ready_tasks(record: ExecutionRecord) -> list[str]:
    done = {task.taskId for task in record.tasks if task.status is ExecutionStatus.COMPLETED}
    active = sum(task.status is ExecutionStatus.RUNNING for task in record.tasks)
    slots = max(0, record.concurrencyLimit - active)
    candidates = [task for task in record.tasks if task.status is ExecutionStatus.QUEUED and not task.locked and set(task.prerequisites) <= done]
    rank = {"high": 0, "medium": 1, "low": 2}
    return [task.taskId for task in sorted(candidates, key=lambda item: rank[item.priority])[:slots]]


def checkpoint(record: ExecutionRecord, task_id: str, now, step: str | None = None) -> ExecutionRecord:
    task = next((item for item in record.tasks if item.taskId == task_id), None)
    if task is None: raise ValueError("Execution task not found")
    done = [item.taskId for item in record.tasks if item.taskId in task.prerequisites and item.status is ExecutionStatus.COMPLETED]
    body = {"executionId": record.executionId, "taskId": task_id, "state": task.status.value, "completedPrerequisites": done, "lastSuccessfulStep": step, "packageDigest": record.packageDigest, "planRevision": record.planRevision, "orchestrationRevision": record.orchestrationRevision}
    point = Checkpoint(checkpointId=uuid.uuid4().hex, executionId=record.executionId, taskId=task_id, state=task.status,
        completedPrerequisites=done, lastSuccessfulStep=step, at=now, packageDigest=record.packageDigest, planRevision=record.planRevision,
        orchestrationRevision=record.orchestrationRevision, integrityHash=hashlib.sha256(canonical(body)).hexdigest())
    return record.model_copy(update={"checkpoints": [*record.checkpoints, point], "updatedAt": now})


def validate_checkpoint(record: ExecutionRecord, point: Checkpoint) -> str | None:
    task = next((item for item in record.tasks if item.taskId == point.taskId), None)
    if not task: return "Checkpoint task is unavailable"
    if task.status is ExecutionStatus.COMPLETED: return "Completed tasks cannot be resumed"
    body = {"executionId": record.executionId, "taskId": point.taskId, "state": point.state.value, "completedPrerequisites": point.completedPrerequisites, "lastSuccessfulStep": point.lastSuccessfulStep, "packageDigest": point.packageDigest, "planRevision": point.planRevision, "orchestrationRevision": point.orchestrationRevision}
    if point.integrityHash != hashlib.sha256(canonical(body)).hexdigest(): return "Checkpoint integrity hash is invalid"
    if (point.packageDigest, point.planRevision, point.orchestrationRevision) != (record.packageDigest, record.planRevision, record.orchestrationRevision): return "Checkpoint revision binding is stale"
    if any(next((item for item in record.tasks if item.taskId == p), None).status is not ExecutionStatus.COMPLETED for p in point.completedPrerequisites): return "Checkpoint prerequisite state is invalid"
    return None


def fail_task(record: ExecutionRecord, task_id: str, failure: FailureRecord, now) -> ExecutionRecord:
    tasks = []
    for task in record.tasks:
        if task.taskId == task_id:
            attempt = TaskAttempt(attempt=len(task.attempts) + 1, at=now, status="failed", failure=failure)
            tasks.append(task.model_copy(update={"status": ExecutionStatus.FAILED, "locked": False, "attempts": [*task.attempts, attempt]}))
        else: tasks.append(task)
    return record.model_copy(update={"tasks": tasks, "updatedAt": now})


def retry_task(record: ExecutionRecord, task_id: str, now) -> ExecutionRecord:
    tasks = []
    for task in record.tasks:
        if task.taskId != task_id: tasks.append(task); continue
        if task.status is not ExecutionStatus.FAILED or not task.attempts: raise ValueError("Task is not eligible for retry")
        failure = task.attempts[-1].failure
        if not failure or not failure.retryable or failure.classification in {"validation", "authorization"} or len(task.attempts) >= record.maxAttempts:
            raise ValueError("Task failure is not eligible for automatic retry")
        tasks.append(task.model_copy(update={"status": ExecutionStatus.QUEUED, "locked": False}))
    return record.model_copy(update={"tasks": tasks, "updatedAt": now})
