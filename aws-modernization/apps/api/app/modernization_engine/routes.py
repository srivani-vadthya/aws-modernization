from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from . import repository, service
from .schemas import (AgentListResponse, CreateRunRequest, OrchestrationListResponse,
                      OrchestrationRequest, OrchestrationResponse, ExecutionActionRequest,
                      ExecutionListResponse, ExecutionRequest, ExecutionResponse, PlanListResponse,
                      PlanResponse, PreviewResponse, RunListResponse, RunResponse, PrepareRequest,
                      StartModernizationRequest)
from ..module_context.repository import ContextError
from .execution_auth import Principal, SESSION_COOKIE, authenticate, issue_session, require

router = APIRouter(tags=["Modernization Engine"])


@router.post("/api/modernization-engine/session")
def create_execution_session(response: Response, principal: Principal = Depends(authenticate)):
    response.set_cookie(SESSION_COOKIE, issue_session(principal), httponly=True, samesite="strict", max_age=900)
    return {"authorized": True}


def call(fn, *args):
    try:
        return fn(*args)
    except ContextError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/engagements/{eid}/modernization-engine/packages/{packageId}/readiness", response_model=PreviewResponse)
def package_readiness(eid: str, packageId: str, moduleId: str):
    return {"preview": call(service.readiness_preview, eid, moduleId, packageId)}


@router.post("/api/engagements/{eid}/modernization-engine/runs", response_model=RunResponse)
def create_run(eid: str, body: CreateRunRequest):
    return {"run": call(service.create_run, eid, body.moduleId, body.packageId)}


@router.post("/api/engagements/{eid}/modernization-engine/prepare")
def prepare_modernization(eid: str, body: PrepareRequest):
    return call(service.prepare, eid, body.moduleId)


@router.get("/api/engagements/{eid}/modernization-engine/runs", response_model=RunListResponse)
def list_runs(eid: str, moduleId: str | None = None):
    return {"runs": call(repository.list_runs, eid, moduleId)}


@router.get("/api/engagements/{eid}/modernization-engine/runs/{runId}", response_model=RunResponse)
def get_run(eid: str, runId: str):
    return {"run": call(repository.load, eid, runId)}


@router.get("/api/engagements/{eid}/modernization-engine/runs/{runId}/status", response_model=RunResponse)
def get_run_status(eid: str, runId: str):
    return {"run": call(repository.load, eid, runId)}


@router.get("/api/engagements/{eid}/modernization-engine/packages/{packageId}/planning-preview", response_model=PlanResponse)
def package_planning_preview(eid: str, packageId: str, moduleId: str):
    return {"plan": call(service.planning_preview, eid, moduleId, packageId)}


@router.post("/api/engagements/{eid}/modernization-engine/plans", response_model=PlanResponse)
def create_plan(eid: str, body: CreateRunRequest):
    return {"plan": call(service.create_plan, eid, body.moduleId, body.packageId)}


@router.get("/api/engagements/{eid}/modernization-engine/plans", response_model=PlanListResponse)
def list_plans(eid: str, moduleId: str | None = None):
    return {"plans": call(service.list_plans, eid, moduleId)}


@router.get("/api/engagements/{eid}/modernization-engine/plans/{planId}", response_model=PlanResponse)
def get_plan(eid: str, planId: str):
    return {"plan": call(service.get_plan, eid, planId)}

@router.post("/api/engagements/{eid}/modernization-engine/plans/{planId}/approve", response_model=PlanResponse)
def approve_plan(eid: str, planId: str, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:control")
    return {"plan": call(service.approve_plan, eid, planId)}


@router.get("/api/engagements/{eid}/modernization-engine/plans/{planId}/tasks/{taskId}")
def get_plan_task(eid: str, planId: str, taskId: str):
    plan = call(service.get_plan, eid, planId)
    for task in plan.tasks:
        if task.taskId == taskId:
            return {"task": task, "planStatus": plan.status, "stale": plan.stale}
    raise HTTPException(404, "Modernization task not found")


@router.get("/api/engagements/{eid}/modernization-engine/plans/{planId}/dependency-order")
def plan_dependency_order(eid: str, planId: str):
    plan = call(service.get_plan, eid, planId)
    return {"dependencyOrder": plan.dependencyOrder, "risks": plan.risks, "blockers": plan.blockers}


@router.get("/api/engagements/{eid}/modernization-engine/plans/{planId}/risks")
def plan_risks(eid: str, planId: str):
    plan = call(service.get_plan, eid, planId)
    return {"risks": plan.risks, "blockers": plan.blockers, "status": plan.status}


@router.get("/api/modernization-engine/agents", response_model=AgentListResponse)
def list_agents():
    return {"agents": service.agents()}


@router.get("/api/engagements/{eid}/modernization-engine/plans/{planId}/orchestration-preview", response_model=OrchestrationResponse)
def orchestration_preview(eid: str, planId: str):
    return {"orchestration": call(service.orchestration_preview, eid, planId)}


@router.post("/api/engagements/{eid}/modernization-engine/orchestrations", response_model=OrchestrationResponse)
def create_orchestration(eid: str, body: OrchestrationRequest):
    return {"orchestration": call(service.create_orchestration, eid, body.planId)}


@router.get("/api/engagements/{eid}/modernization-engine/orchestrations", response_model=OrchestrationListResponse)
def list_orchestrations(eid: str, moduleId: str | None = None):
    return {"orchestrations": call(service.list_orchestrations, eid, moduleId)}


@router.get("/api/engagements/{eid}/modernization-engine/orchestrations/{orchestrationId}", response_model=OrchestrationResponse)
def get_orchestration(eid: str, orchestrationId: str):
    return {"orchestration": call(service.get_orchestration, eid, orchestrationId)}

@router.post("/api/engagements/{eid}/modernization-engine/orchestrations/{orchestrationId}/approve", response_model=OrchestrationResponse)
def approve_orchestration(eid: str, orchestrationId: str, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:control")
    return {"orchestration": call(service.approve_orchestration, eid, orchestrationId)}


@router.get("/api/engagements/{eid}/modernization-engine/orchestrations/{orchestrationId}/execution-preview", response_model=ExecutionResponse)
def execution_preview(eid: str, orchestrationId: str, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:read")
    return {"execution": call(service.execution_preview, eid, orchestrationId)}


@router.post("/api/engagements/{eid}/modernization-engine/executions", response_model=ExecutionResponse)
def create_execution(eid: str, body: ExecutionRequest, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:control")
    return {"execution": call(service.create_authorized_execution, eid, body.orchestrationId)}


@router.post("/api/engagements/{eid}/modernization-engine/start", response_model=ExecutionResponse)
def start_modernization(eid: str, body: StartModernizationRequest, background: BackgroundTasks,
                        principal: Principal = Depends(authenticate)):
    """The sole normal-user authorization action for prepared modernization work."""
    require(principal, eid, "execution:control")
    record = call(service.authorize_start, eid, body.planId)
    background.add_task(service.run_queued_execution, eid, record.executionId)
    return {"execution": record}


@router.get("/api/engagements/{eid}/modernization-engine/executions", response_model=ExecutionListResponse)
def list_executions(eid: str, moduleId: str | None = None, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:read")
    return {"executions": call(service.list_executions, eid, moduleId)}


@router.get("/api/engagements/{eid}/modernization-engine/executions/{executionId}", response_model=ExecutionResponse)
def get_execution(eid: str, executionId: str, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:read")
    return {"execution": call(service.get_execution, eid, executionId)}


@router.get("/api/engagements/{eid}/modernization-engine/executions/{executionId}/artifacts")
def execution_artifacts(eid: str, executionId: str, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:read")
    return {"artifacts": call(service.get_execution, eid, executionId).artifacts}


@router.get("/api/engagements/{eid}/modernization-engine/executions/{executionId}/logs")
def execution_logs(eid: str, executionId: str, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:read")
    return {"logs": call(service.get_execution, eid, executionId).logs}


@router.get("/api/engagements/{eid}/modernization-engine/executions/{executionId}/checkpoints")
def execution_checkpoints(eid: str, executionId: str, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:read")
    return {"checkpoints": call(service.get_execution, eid, executionId).checkpoints}


@router.get("/api/engagements/{eid}/modernization-engine/executions/{executionId}/tasks/{taskId}")
def execution_task(eid: str, executionId: str, taskId: str, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:read")
    record = call(service.get_execution, eid, executionId)
    for task in record.tasks:
        if task.taskId == taskId: return {"task": task}
    raise HTTPException(404, "Execution task not found")


@router.post("/api/engagements/{eid}/modernization-engine/executions/{executionId}/actions", response_model=ExecutionResponse)
def execution_action(eid: str, executionId: str, body: ExecutionActionRequest, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:control")
    return {"execution": call(service.execution_action, eid, executionId, body.action, body.taskId)}


@router.post("/api/engagements/{eid}/modernization-engine/executions/{executionId}/start", response_model=ExecutionResponse)
def start_execution(eid: str, executionId: str, background: BackgroundTasks, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:control")
    record = call(service.execution_action, eid, executionId, "queue")
    background.add_task(service.run_queued_execution, eid, executionId)
    return {"execution": record}


@router.post("/api/engagements/{eid}/modernization-engine/executions/{executionId}/validate", response_model=ExecutionResponse)
def validate_generated_output(eid: str, executionId: str, principal: Principal = Depends(authenticate)):
    require(principal, eid, "execution:control")
    return {"execution": call(service.validate_execution, eid, executionId)}
