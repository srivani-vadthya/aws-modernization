from __future__ import annotations

import uuid
from threading import Lock
from . import agent_registry, execution, orchestration, package_loader, planner, repository, scaffolding
from .readiness import READINESS_POLICY_VERSION
from .provider_execution import execute_bedrock_task, execute_transform_task
from .validation import validate
from .models import (ALLOWED_TRANSITIONS, ExecutionEvent, ExecutionLog, ExecutionRecord, ExecutionStatus,
                     ExecutionTask, ModernizationPlan, ModernizationRun, OrchestrationRecord, PlanStatus, RunStatus, StatusEvent)
from ..module_context.repository import canonical, digest, package_root
from ..module_context.models import PackageRequest
from ..module_context.service import generate as generate_package
from .readiness import preview


_prepare_locks: dict[tuple[str, str], Lock] = {}
_prepare_locks_guard = Lock()


def _prepare_lock(eid: str, module_id: str) -> Lock:
    """Serialize duplicate browser preparation requests for one module."""
    with _prepare_locks_guard:
        return _prepare_locks.setdefault((eid, module_id), Lock())


def readiness_preview(eid: str, module_id: str, package_id: str):
    manifest, integrity = package_loader.load(eid, package_id, module_id)
    return preview(eid, module_id, manifest, integrity)


def create_run(eid: str, module_id: str, package_id: str) -> ModernizationRun:
    manifest, integrity = package_loader.load(eid, package_id, module_id)
    result = preview(eid, module_id, manifest, integrity)
    now = repository.now()
    final = RunStatus.BLOCKED if result.overallStatus == "NOT_READY" else RunStatus.READY_FOR_APPROVAL
    history = [
        StatusEvent(at=now, toStatus=RunStatus.DRAFT, reason="Modernization run created from immutable package snapshot."),
        StatusEvent(at=now, fromStatus=RunStatus.DRAFT, toStatus=RunStatus.VALIDATING, reason="Package integrity and execution readiness evaluated."),
        StatusEvent(at=now, fromStatus=RunStatus.VALIDATING, toStatus=final,
                    reason="Execution is blocked by package findings." if final is RunStatus.BLOCKED else "Ready for a future explicit approval action."),
    ]
    return repository.create(ModernizationRun(
        runId=uuid.uuid4().hex, engagementId=eid, moduleId=module_id, packageId=package_id,
        packageSchemaVersion=manifest["schemaVersion"], packageDigest=manifest["packageDigest"],
        target=manifest["target"], templates=manifest["templates"], status=final,
        createdAt=now, updatedAt=now, statusHistory=history, validation=result,
    ))


def planning_preview(eid: str, module_id: str, package_id: str) -> ModernizationPlan:
    manifest, integrity = package_loader.load(eid, package_id, module_id)
    return planner.build(manifest, preview(eid, module_id, manifest, integrity), uuid.uuid4().hex, repository.now())


def create_plan(eid: str, module_id: str, package_id: str) -> ModernizationPlan:
    """Persist only the new plan record; package and engagement evidence stay immutable."""
    return repository.create_plan(planning_preview(eid, module_id, package_id))


def prepare(eid: str, module_id: str) -> dict:
    """Idempotently assemble a package, readiness result, run, and reviewable plan."""
    with _prepare_lock(eid, module_id):
        package = generate_package(eid, PackageRequest(moduleId=module_id, templateIds=None))["manifest"]
        readiness = readiness_preview(eid, module_id, package["packageId"])
        run = next((item for item in repository.list_runs(eid, module_id)
                    if item.packageId == package["packageId"] and item.validation.policyVersion == READINESS_POLICY_VERSION), None)
        if run is None:
            run = create_run(eid, module_id, package["packageId"])
        plan = next((item for item in list_plans(eid, module_id)
                     if item.packageId == package["packageId"] and not item.stale
                     and item.planningEngineVersion == planner.PLANNING_ENGINE_VERSION), None)
        if plan is None:
            plan = create_plan(eid, module_id, package["packageId"])
        orchestration_record = next((item for item in list_orchestrations(eid, module_id)
                                     if item.planId == plan.planId and not item.stale), None)
        if orchestration_record is None:
            orchestration_record = create_orchestration(eid, plan.planId)
        return {"package": package, "readiness": readiness, "run": run,
                "plan": plan, "orchestration": orchestration_record}


def get_plan(eid: str, plan_id: str) -> ModernizationPlan:
    plan = repository.load_plan(eid, plan_id)
    # A plan can be read after its package has been superseded or removed. It is stale if the
    # referenced package can no longer be loaded or its immutable digest no longer agrees.
    try:
        manifest, _ = package_loader.load(eid, plan.packageId, plan.moduleId)
        stale = manifest["packageDigest"] != plan.packageDigest
    except Exception:
        stale = True
    return plan.model_copy(update={"stale": stale})


def list_plans(eid: str, module_id: str | None = None) -> list[ModernizationPlan]:
    return [get_plan(eid, item.planId) for item in repository.list_plans(eid, module_id)]


def approve_plan(eid: str, plan_id: str) -> ModernizationPlan:
    plan = get_plan(eid, plan_id)
    if plan.stale or plan.blockers: raise ValueError("A stale or blocked modernization plan cannot be approved")
    if plan.status != "READY_FOR_REVIEW": raise ValueError("Modernization plan is not ready for approval")
    approved = repository.update_plan(plan.model_copy(update={"status": "APPROVED_PLAN"}))
    if not any(item.planId == approved.planId and not item.stale for item in list_orchestrations(eid, approved.moduleId)):
        create_orchestration(eid, approved.planId)
    return approved


def agents():
    return agent_registry.list_agents()


def orchestration_preview(eid: str, plan_id: str) -> OrchestrationRecord:
    plan = get_plan(eid, plan_id)
    revision = digest(canonical(plan.model_dump(mode="json", exclude={"stale"})))
    return orchestration.build(plan, revision, uuid.uuid4().hex, repository.now(), preview=True)


def create_orchestration(eid: str, plan_id: str) -> OrchestrationRecord:
    preview = orchestration_preview(eid, plan_id)
    return repository.create_orchestration(preview.model_copy(update={"status": "BLOCKED" if preview.blockedTaskIds else "READY_FOR_REVIEW"}))


def get_orchestration(eid: str, orchestration_id: str) -> OrchestrationRecord:
    record = repository.load_orchestration(eid, orchestration_id)
    try:
        plan = get_plan(eid, record.planId)
        revision = digest(canonical(plan.model_dump(mode="json", exclude={"stale"})))
        stale = plan.stale or revision != record.planRevision or plan.packageDigest != record.packageDigest
    except Exception:
        stale = True
    return record.model_copy(update={"stale": stale})


def list_orchestrations(eid: str, module_id: str | None = None) -> list[OrchestrationRecord]:
    return [get_orchestration(eid, record.orchestrationId) for record in repository.list_orchestrations(eid, module_id)]


def approve_orchestration(eid: str, orchestration_id: str) -> OrchestrationRecord:
    record = get_orchestration(eid, orchestration_id)
    if record.stale or record.blockedTaskIds: raise ValueError("A stale or blocked orchestration cannot be approved")
    if record.status != "READY_FOR_REVIEW": raise ValueError("Orchestration is not ready for approval")
    return repository.update_orchestration(record.model_copy(update={"status": "APPROVED"}))


def execution_preview(eid: str, orchestration_id: str) -> ExecutionRecord:
    record = get_orchestration(eid, orchestration_id)
    plan = get_plan(eid, record.planId)
    readiness = readiness_preview(eid, record.moduleId, record.packageId)
    blockers = [f"{f.code}: {f.message}" for f in readiness.findings if f.severity == "blocker"]
    if plan.status != "APPROVED_PLAN": blockers.append("PLAN_NOT_APPROVED: Plan approval is required before queueing.")
    if record.status != "APPROVED": blockers.append("ORCHESTRATION_NOT_APPROVED: Orchestration approval is required before queueing.")
    if record.stale: blockers.append("ORCHESTRATION_STALE: Revision binding no longer matches.")
    now = repository.now()
    status = ExecutionStatus.BLOCKED if blockers else ExecutionStatus.CREATED
    automated = {task.taskId for task in plan.tasks if task.suggestedProvider in {"amazon-bedrock", "aws-transform"}}
    deferred = [item.taskId for item in record.assignments if item.taskId not in automated]
    if not automated:
        blockers.append("NO_AUTOMATED_PROVIDER_TASKS: No planned task has an executable provider allocation.")
        status = ExecutionStatus.BLOCKED
    tasks = [ExecutionTask(taskId=item.taskId, agentId=item.agentId, status=ExecutionStatus.BLOCKED if blockers else ExecutionStatus.CREATED,
             priority=next((task.priority for task in plan.tasks if task.taskId == item.taskId), "medium"), prerequisites=item.prerequisiteTasks)
             for item in record.assignments if item.taskId in automated]
    reason = "Execution preview is blocked: " + " | ".join(blockers) if blockers else "Execution preview created; no worker started."
    event = ExecutionEvent(at=now, toStatus=status, reason=reason)
    log = ExecutionLog(at=now, executionId="preview", eventType="execution-preview", status=status, message=reason)
    logs = [log]
    if deferred:
        logs.append(ExecutionLog(at=now, executionId="preview", eventType="manual-workstream-deferred", status=status,
                                 message="Manual-review workstreams were not queued for provider execution: " + ", ".join(deferred) + "."))
    return ExecutionRecord(executionId=uuid.uuid4().hex, engagementId=eid, moduleId=record.moduleId, packageId=record.packageId,
        packageDigest=record.packageDigest, planId=plan.planId, planRevision=record.planRevision, orchestrationId=record.orchestrationId,
        orchestrationRevision=digest(canonical(record.model_dump(mode="json", exclude={"stale"}))), targetConfiguration=plan.targetDecision,
        templateRevisions=plan.templateBundleRevisions, createdAt=now, updatedAt=now, status=status, statusHistory=[event], tasks=tasks, logs=logs)


def create_authorized_execution(eid: str, orchestration_id: str) -> ExecutionRecord:
    preview = execution_preview(eid, orchestration_id)
    if preview.status is ExecutionStatus.BLOCKED:
        raise ValueError(preview.statusHistory[-1].reason)
    return repository.create_execution(preview)


def authorize_start(eid: str, plan_id: str) -> ExecutionRecord:
    """Record the one explicit start authorization against exact current revisions."""
    plan = get_plan(eid, plan_id)
    with _prepare_lock(eid, plan.moduleId):
        plan = get_plan(eid, plan_id)
        readiness = readiness_preview(eid, plan.moduleId, plan.packageId)
        if plan.stale or plan.blockers or readiness.overallStatus == "NOT_READY":
            raise ValueError("Modernization cannot start until all readiness blockers are resolved")
        if plan.status not in {"READY_FOR_REVIEW", "APPROVED_PLAN"}:
            raise ValueError("Modernization plan is not available for start authorization")
        if plan.status != "APPROVED_PLAN":
            plan = repository.update_plan(plan.model_copy(update={"status": PlanStatus.APPROVED_PLAN}))
        prepared = orchestration_preview(eid, plan.planId)
        if prepared.blockedTaskIds:
            raise ValueError("Modernization orchestration has blocked tasks")
        authorized = repository.create_orchestration(prepared.model_copy(update={"status": "APPROVED"}))
        record = create_authorized_execution(eid, authorized.orchestrationId)
        return execution_action(eid, record.executionId, "queue")


def get_execution(eid: str, execution_id: str) -> ExecutionRecord:
    record = repository.load_execution(eid, execution_id)
    try:
        manifest, _ = package_loader.load(eid, record.packageId, record.moduleId)
        plan = get_plan(eid, record.planId)
        orchestration_record = get_orchestration(eid, record.orchestrationId)
        current_plan_revision = digest(canonical(plan.model_dump(mode="json", exclude={"stale"})))
        current_orchestration_revision = digest(canonical(orchestration_record.model_dump(mode="json", exclude={"stale"})))
        stale = (manifest["packageDigest"] != record.packageDigest or plan.stale or orchestration_record.stale
                 or current_plan_revision != record.planRevision or current_orchestration_revision != record.orchestrationRevision)
    except Exception:
        stale = True
    checkpoints = [item.model_copy(update={"stale": stale}) for item in record.checkpoints]
    return record.model_copy(update={"stale": stale, "checkpoints": checkpoints})


def list_executions(eid: str, module_id: str | None = None) -> list[ExecutionRecord]:
    return [get_execution(eid, item.executionId) for item in repository.list_executions(eid, module_id)]


def interrupt_orphaned_executions(eid: str) -> int:
    """A process-local worker cannot survive an API restart; record that fact safely."""
    updated = 0
    for record in repository.list_executions(eid):
        if record.status in {ExecutionStatus.QUEUED, ExecutionStatus.RUNNING}:
            interrupted = execution.transition(record, ExecutionStatus.INTERRUPTED,
                                                "Backend restarted before the local provider worker completed.", repository.now())
            repository.update_execution(interrupted)
            updated += 1
    return updated


def execution_action(eid: str, execution_id: str, action: str, task_id: str | None = None) -> ExecutionRecord:
    record = get_execution(eid, execution_id); now = repository.now()
    if record.stale:
        raise ValueError("Execution revision bindings are stale; state-changing actions are rejected")
    readiness = readiness_preview(eid, record.moduleId, record.packageId)
    if readiness.overallStatus == "NOT_READY":
        raise ValueError("Execution package is not ready; state-changing actions are rejected")
    plan = get_plan(eid, record.planId)
    orchestration_record = get_orchestration(eid, record.orchestrationId)
    if plan.status != "APPROVED_PLAN" or orchestration_record.status != "APPROVED":
        raise ValueError("Execution plan and orchestration must remain approved")
    if action == "queue":
        updated = record
        if updated.status is ExecutionStatus.CREATED:
            updated = execution.transition(updated, ExecutionStatus.VALIDATING, "Execution authorization and revision bindings revalidated.", now)
        updated = execution.transition(updated, ExecutionStatus.QUEUED, "Queued by explicit request.", now)
        updated = updated.model_copy(update={"tasks": [item.model_copy(update={"status": ExecutionStatus.QUEUED}) if item.status is ExecutionStatus.CREATED else item for item in updated.tasks]})
    elif action == "pause": updated = execution.transition(record, ExecutionStatus.PAUSED, "Paused by explicit request.", now)
    elif action == "resume": updated = execution.transition(record, ExecutionStatus.QUEUED, "Resumed by explicit request.", now)
    elif action == "cancel":
        target = ExecutionStatus.CANCELLED if record.status in {ExecutionStatus.CREATED, ExecutionStatus.BLOCKED, ExecutionStatus.QUEUED, ExecutionStatus.PAUSED, ExecutionStatus.CANCELLING} else ExecutionStatus.CANCELLING
        updated = execution.transition(record, target, "Cancellation confirmed." if target is ExecutionStatus.CANCELLED else "Cancellation requested; awaiting worker confirmation.", now)
    elif action == "checkpoint":
        if not task_id: raise ValueError("taskId is required for checkpoint")
        updated = execution.checkpoint(record, task_id, now)
    elif action == "retry":
        if not task_id: raise ValueError("taskId is required for retry")
        updated = execution.retry_task(record, task_id, now)
    else: raise ValueError("Unsupported execution action")
    return repository.update_execution(updated)


def run_queued_execution(eid: str, execution_id: str) -> None:
    """Run only explicitly queued, authorized work; called by the API background task."""
    record = get_execution(eid, execution_id)
    if record.status is not ExecutionStatus.QUEUED or record.stale:
        return
    record = execution.transition(record, ExecutionStatus.RUNNING, "Approved provider execution started.", repository.now())
    repository.update_execution(record)
    plan = get_plan(eid, record.planId)
    manifest, _ = package_loader.load(eid, record.packageId, record.moduleId)
    snapshot_root = package_root(eid, record.packageId)
    workspace = repository.execution_root(eid, execution_id) / "output"
    workspace.mkdir(parents=True, exist_ok=True)
    scaffold_artifacts = scaffolding.create(workspace, record.targetConfiguration, plan)
    if scaffold_artifacts:
        record = record.model_copy(update={"artifacts": [*record.artifacts, *scaffold_artifacts], "updatedAt": repository.now(),
            "logs": [*record.logs, ExecutionLog(at=repository.now(), executionId=record.executionId,
                eventType="target-scaffold-created", status=ExecutionStatus.RUNNING,
                message="Deterministic .NET 8 and React target scaffolds were created before provider generation.")]})
        repository.update_execution(record)
    while ready := execution.ready_tasks(record):
        ready = [task_id for task_id in ready if next((item.suggestedProvider for item in plan.tasks if item.taskId == task_id), None) in {"amazon-bedrock", "aws-transform"}]
        if not ready:
            break
        for task_id in ready:
            plan_task = next((item for item in plan.tasks if item.taskId == task_id), None)
            if plan_task is None:
                continue
            task = next(item for item in record.tasks if item.taskId == task_id)
            provider = plan_task.suggestedProvider
            started_at = repository.now()
            record = record.model_copy(update={
                "tasks": [item.model_copy(update={"status": ExecutionStatus.RUNNING, "locked": True,
                    "lockOwner": provider, "lockedAt": started_at}) if item.taskId == task_id else item for item in record.tasks],
                "logs": [*record.logs, ExecutionLog(at=started_at, executionId=record.executionId,
                    taskId=task_id, agentId=task.agentId, provider=provider,
                    eventType="provider-start", status=ExecutionStatus.RUNNING,
                    message=f"{provider} modernization task started.")],
                "updatedAt": started_at,
            })
            repository.update_execution(record)
            if plan_task.suggestedProvider == "aws-transform":
                def transform_progress(message: str) -> None:
                    repository.append_execution_log(eid, execution_id, ExecutionLog(
                        at=repository.now(), executionId=execution_id, taskId=task_id,
                        agentId=task.agentId, provider="aws-transform", eventType="provider-progress",
                        status=ExecutionStatus.RUNNING, message=message))
                record = execute_transform_task(record, task_id, plan_task, manifest, snapshot_root, workspace, transform_progress)
                # Progress is persisted while the CLI runs. Merge it before the
                # final task update so it is never overwritten by this worker.
                persisted = repository.load_execution(eid, execution_id)
                known = {item.model_dump_json() for item in persisted.logs}
                record = record.model_copy(update={"logs": [*persisted.logs, *[item for item in record.logs if item.model_dump_json() not in known]]})
            elif plan_task.suggestedProvider == "amazon-bedrock":
                record = execute_bedrock_task(record, task_id, plan_task, manifest, snapshot_root, workspace)
            else:
                continue
            repository.update_execution(record)
    if any(task.status is ExecutionStatus.FAILED for task in record.tasks):
        record = execution.transition(record, ExecutionStatus.FAILED, "One or more provider tasks failed; generated output remains unvalidated.", repository.now())
    elif all(task.status is ExecutionStatus.COMPLETED for task in record.tasks):
        deferred = [task.taskId for task in plan.tasks if task.suggestedProvider not in {"amazon-bedrock", "aws-transform"}]
        suffix = (" Manual-review workstreams remain: " + ", ".join(deferred) + ".") if deferred else ""
        record = execution.transition(record, ExecutionStatus.COMPLETED, "Automated provider tasks completed; build, tests, and behavior parity remain separate validation requirements." + suffix, repository.now())
    else:
        record = execution.transition(record, ExecutionStatus.FAILED, "No runnable provider worker was available for one or more assigned tasks.", repository.now())
    repository.update_execution(record)


def validate_execution(eid: str, execution_id: str) -> ExecutionRecord:
    record = get_execution(eid, execution_id)
    if record.status is not ExecutionStatus.COMPLETED:
        raise ValueError("Generated output can be validated only after provider tasks complete")
    output = repository.execution_root(eid, execution_id) / "output"
    return repository.update_execution(validate(record, output))


def transition(run: ModernizationRun, to_status: RunStatus, reason: str) -> ModernizationRun:
    """Lifecycle guard for future commands. No public transition route exists in Phase 2.1."""
    if to_status not in ALLOWED_TRANSITIONS[run.status]:
        raise ValueError(f"Invalid modernization run transition: {run.status} -> {to_status}")
    return run.model_copy(update={"status": to_status, "updatedAt": repository.now(),
        "statusHistory": [*run.statusHistory, StatusEvent(at=repository.now(), fromStatus=run.status, toStatus=to_status, reason=reason)]})
