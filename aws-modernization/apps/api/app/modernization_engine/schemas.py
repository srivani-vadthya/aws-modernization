from pydantic import Field
from .models import AgentDefinition, ExecutionRecord, Model, ModernizationPlan, ModernizationRun, OrchestrationRecord, ReadinessPreview


class CreateRunRequest(Model):
    moduleId: str = Field(min_length=1, max_length=300)
    packageId: str = Field(pattern=r"^[a-f0-9]{32}$")


class PrepareRequest(Model):
    moduleId: str = Field(min_length=1, max_length=300)


class RunResponse(Model):
    run: ModernizationRun


class RunListResponse(Model):
    runs: list[ModernizationRun]


class PreviewResponse(Model):
    preview: ReadinessPreview


class PlanResponse(Model):
    plan: ModernizationPlan


class PlanListResponse(Model):
    plans: list[ModernizationPlan]


class OrchestrationRequest(Model):
    planId: str = Field(pattern=r"^[a-f0-9]{32}$")


class AgentListResponse(Model):
    agents: list[AgentDefinition]


class OrchestrationResponse(Model):
    orchestration: OrchestrationRecord


class OrchestrationListResponse(Model):
    orchestrations: list[OrchestrationRecord]


class ExecutionRequest(Model):
    orchestrationId: str = Field(pattern=r"^[a-f0-9]{32}$")


class StartModernizationRequest(Model):
    planId: str = Field(pattern=r"^[a-f0-9]{32}$")


class ExecutionActionRequest(Model):
    action: str = Field(pattern=r"^(queue|pause|resume|cancel|checkpoint|retry)$")
    taskId: str | None = Field(default=None, max_length=300)


class ExecutionResponse(Model):
    execution: ExecutionRecord


class ExecutionListResponse(Model):
    executions: list[ExecutionRecord]
