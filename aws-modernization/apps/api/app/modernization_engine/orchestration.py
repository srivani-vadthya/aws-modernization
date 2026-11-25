"""Non-executing orchestration preview and record construction."""
from __future__ import annotations

from .agent_registry import candidates
from .models import (AgentOutputMetadata, AssignmentStatus, EvidenceReference,
                     ModernizationPlan, OrchestrationRecord, PlanRisk, TaskAssignment, TaskContext)


def _manual_agent_id() -> str:
    return "manual-engineering-review"


def build(plan: ModernizationPlan, plan_revision: str, orchestration_id: str, created_at, preview: bool) -> OrchestrationRecord:
    plan_blocked = plan.status != "APPROVED_PLAN" or plan.stale or bool(plan.blockers)
    findings = list(plan.blockers)
    if plan.status != "APPROVED_PLAN":
        findings.append(PlanRisk(code="PLAN_NOT_APPROVED", severity="blocker", message="Plan is not approved for execution; assignments are proposals only.", evidence=[]))
    if plan.stale:
        findings.append(PlanRisk(code="PLAN_STALE", severity="blocker", message="Plan no longer matches its source package revision.", evidence=[]))
    task_ids = {task.taskId for task in plan.tasks}
    graph = {task.taskId: [item for item in task.dependencies if item in task_ids] for task in plan.tasks}
    def cyclic(node: str, active: set[str], seen: set[str]) -> bool:
        if node in active: return True
        if node in seen: return False
        active.add(node)
        result = any(cyclic(next_node, active, seen) for next_node in graph[node])
        active.remove(node); seen.add(node)
        return result
    if any(cyclic(node, set(), set()) for node in graph):
        findings.append(PlanRisk(code="CIRCULAR_TASK_DEPENDENCY", severity="blocker", message="Plan task dependencies contain a cycle; no assignment may proceed.", evidence=[]))
        plan_blocked = True
    assignments = []
    for task in plan.tasks:
        agents = candidates(task.category, [], task.requiredTargetTechnologies, bool(task.templates))
        if agents:
            agent = agents[0]
            rationale = f"Agent supports the '{task.category}' category and is locally available for proposal-only work."
            outputs = agent.expectedOutputTypes
        else:
            agent_id, rationale, outputs = _manual_agent_id(), "No compatible available registered agent; manual engineering review is required.", ["manual-review-decision"]
            agent = None
        prerequisites = list(task.dependencies)
        status = AssignmentStatus.BLOCKED if plan_blocked else AssignmentStatus.WAITING_FOR_DEPENDENCY if prerequisites else AssignmentStatus.READY
        reasons = [f"{blocker.code}: {blocker.message}" for blocker in findings if blocker.severity == "blocker"]
        if prerequisites and not plan_blocked:
            reasons.append("Prerequisite task results are not available in this non-executing phase.")
        context = TaskContext(packageId=plan.packageId, packageDigest=plan.packageDigest, planId=plan.planId, planRevision=plan_revision,
            taskId=task.taskId, sourceReferences=task.sourceArtifacts, businessRules=task.businessRules, requirements=task.requirements,
            acceptanceCriteria=task.acceptanceCriteria, targetTechnologies=task.requiredTargetTechnologies, templateReferences=task.templates,
            dependencyResults=[], expectedOutputContract=task.expectedOutput)
        assignments.append(TaskAssignment(taskId=task.taskId, agentId=agent.agentId if agent else agent_id, assignmentRationale=rationale,
            inputContext=context, expectedOutputs=outputs, prerequisiteTasks=prerequisites, status=status, blockedReasons=reasons,
            output=AgentOutputMetadata(taskId=task.taskId, agentId=agent.agentId if agent else agent_id, outputType=outputs[0])))
    ready = [a.taskId for a in assignments if a.status is AssignmentStatus.READY]
    blocked = [a.taskId for a in assignments if a.status is AssignmentStatus.BLOCKED]
    independent = [a.taskId for a in assignments if not a.prerequisiteTasks]
    return OrchestrationRecord(orchestrationId=orchestration_id, engagementId=plan.engagementId, moduleId=plan.moduleId,
        packageId=plan.packageId, packageDigest=plan.packageDigest, planId=plan.planId, planRevision=plan_revision, createdAt=created_at,
        status="PREVIEW" if preview else "BLOCKED" if blocked else "READY_FOR_REVIEW", assignments=assignments, readyTaskIds=ready,
        blockedTaskIds=blocked, independentTaskIds=independent, findings=findings)
