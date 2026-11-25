from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    BLOCKED = "BLOCKED"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    APPROVED = "APPROVED"
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.DRAFT: {RunStatus.VALIDATING, RunStatus.CANCELLED},
    RunStatus.VALIDATING: {RunStatus.BLOCKED, RunStatus.READY_FOR_APPROVAL, RunStatus.FAILED},
    RunStatus.BLOCKED: {RunStatus.VALIDATING, RunStatus.CANCELLED},
    RunStatus.READY_FOR_APPROVAL: {RunStatus.APPROVED, RunStatus.CANCELLED},
    RunStatus.APPROVED: {RunStatus.PLANNED, RunStatus.CANCELLED},
    RunStatus.PLANNED: {RunStatus.QUEUED, RunStatus.CANCELLED},
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(), RunStatus.FAILED: set(), RunStatus.CANCELLED: set(),
}


class ValidationFinding(Model):
    code: str
    severity: Literal["blocker", "warning", "info"]
    message: str
    evidence: list[str] = Field(default_factory=list)
    source: str


class ReadinessPreview(Model):
    engagementId: str
    moduleId: str
    packageId: str
    packageSchemaVersion: str | None = None
    packageIntegrity: Literal["valid", "invalid", "not-checked"]
    overallStatus: Literal["NOT_READY", "READY_WITH_WARNINGS", "READY"]
    executable: bool = False
    policyVersion: str = "1.0"
    target: dict = Field(default_factory=dict)
    templates: list[dict] = Field(default_factory=list)
    findings: list[ValidationFinding] = Field(default_factory=list)


class StatusEvent(Model):
    at: datetime
    fromStatus: RunStatus | None = None
    toStatus: RunStatus
    reason: str


class ModernizationRun(Model):
    runId: str
    engagementId: str
    moduleId: str
    packageId: str
    packageSchemaVersion: str
    packageDigest: str
    target: dict
    templates: list[dict]
    status: RunStatus
    createdAt: datetime
    updatedAt: datetime
    statusHistory: list[StatusEvent]
    validation: ReadinessPreview
    provider: str | None = None
    planner: dict = Field(default_factory=lambda: {"status": "NOT_PLANNED"})
    execution: dict = Field(default_factory=lambda: {"status": "NOT_IMPLEMENTED"})


class PlanStatus(StrEnum):
    DRAFT_PLAN = "DRAFT_PLAN"
    BLOCKED_PLAN = "BLOCKED_PLAN"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED_PLAN = "APPROVED_PLAN"


class EvidenceReference(Model):
    artifactId: str
    pointer: str = ""
    entityId: str | None = None


class StrategyRecommendation(Model):
    category: Literal["rehost", "replatform", "refactor", "rearchitect", "replace", "retain"]
    rationale: str
    evidence: list[EvidenceReference] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unresolvedQuestions: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]
    approved: Literal[False] = False


class PlanWorkstream(Model):
    id: str
    name: str
    rationale: str
    evidence: list[EvidenceReference] = Field(default_factory=list)
    taskIds: list[str] = Field(default_factory=list)


class PlanTask(Model):
    taskId: str
    name: str
    description: str
    category: str
    workstreamId: str
    sourceArtifacts: list[EvidenceReference] = Field(default_factory=list)
    businessRules: list[EvidenceReference] = Field(default_factory=list)
    requirements: list[EvidenceReference] = Field(default_factory=list)
    stories: list[EvidenceReference] = Field(default_factory=list)
    acceptanceCriteria: list[EvidenceReference] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    requiredTargetTechnologies: list[str] = Field(default_factory=list)
    templates: list[EvidenceReference] = Field(default_factory=list)
    suggestedProvider: Literal["aws-transform", "amazon-bedrock", "custom", "manual-engineering-review"]
    providerRationale: str
    capabilityVerification: dict = Field(default_factory=dict)
    expectedOutputFolders: list[str] = Field(default_factory=list)
    fallbackEligible: bool = False
    fallbackProvider: Literal["amazon-bedrock", "manual-engineering-review"] | None = None
    expectedOutput: str
    acceptanceConditions: list[str] = Field(default_factory=list)
    validationApproach: str
    risks: list[str] = Field(default_factory=list)
    unresolvedDependencies: list[str] = Field(default_factory=list)
    estimatedComplexity: Literal["low", "medium", "high", "unknown"]
    priority: Literal["low", "medium", "high"]
    planningStatus: Literal["proposed", "blocked"]


class PlanRisk(Model):
    code: str
    severity: Literal["blocker", "warning", "info"]
    message: str
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ModernizationPlan(Model):
    planId: str
    engagementId: str
    moduleId: str
    packageId: str
    packageSchemaVersion: str
    packageDigest: str
    targetConfigurationRevision: str
    targetDecision: dict = Field(default_factory=dict)
    templateBundleRevisions: dict[str, str] = Field(default_factory=dict)
    providerReadiness: dict = Field(default_factory=dict)
    planningEngineVersion: str
    status: PlanStatus
    createdAt: datetime
    strategy: StrategyRecommendation
    workstreams: list[PlanWorkstream] = Field(default_factory=list)
    tasks: list[PlanTask] = Field(default_factory=list)
    dependencyOrder: list[list[str]] = Field(default_factory=list)
    risks: list[PlanRisk] = Field(default_factory=list)
    blockers: list[PlanRisk] = Field(default_factory=list)
    stale: bool = False
    executionAuthorized: Literal[False] = False


class AgentAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class AgentDefinition(Model):
    agentId: str
    name: str
    description: str
    taskCategories: list[str]
    sourceTechnologies: list[str] = Field(default_factory=list)
    targetTechnologies: list[str] = Field(default_factory=list)
    requiredInputArtifacts: list[str]
    expectedOutputTypes: list[str]
    requiredSkillsOrTemplates: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    capabilityMetadata: dict = Field(default_factory=dict)
    availability: AgentAvailability


class TaskContext(Model):
    packageId: str
    packageDigest: str
    planId: str
    planRevision: str
    taskId: str
    sourceReferences: list[EvidenceReference] = Field(default_factory=list)
    businessRules: list[EvidenceReference] = Field(default_factory=list)
    requirements: list[EvidenceReference] = Field(default_factory=list)
    acceptanceCriteria: list[EvidenceReference] = Field(default_factory=list)
    targetTechnologies: list[str] = Field(default_factory=list)
    templateReferences: list[EvidenceReference] = Field(default_factory=list)
    dependencyResults: list[str] = Field(default_factory=list)
    expectedOutputContract: str


class AgentOutputMetadata(Model):
    taskId: str
    agentId: str
    outputType: str
    artifactReferences: list[EvidenceReference] = Field(default_factory=list)
    validationStatus: Literal["not-produced", "unverified", "validated"] = "not-produced"
    executionStatus: Literal["not-started", "in-progress", "completed", "failed"] = "not-started"
    findings: list[str] = Field(default_factory=list)
    errorDetails: str | None = None


class AssignmentStatus(StrEnum):
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    WAITING_FOR_DEPENDENCY = "WAITING_FOR_DEPENDENCY"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskAssignment(Model):
    taskId: str
    agentId: str
    assignmentRationale: str
    inputContext: TaskContext
    expectedOutputs: list[str]
    prerequisiteTasks: list[str] = Field(default_factory=list)
    status: AssignmentStatus
    blockedReasons: list[str] = Field(default_factory=list)
    output: AgentOutputMetadata


class OrchestrationRecord(Model):
    orchestrationId: str
    engagementId: str
    moduleId: str
    packageId: str
    packageDigest: str
    planId: str
    planRevision: str
    createdAt: datetime
    status: Literal["PREVIEW", "BLOCKED", "READY_FOR_REVIEW", "APPROVED"]
    assignments: list[TaskAssignment] = Field(default_factory=list)
    readyTaskIds: list[str] = Field(default_factory=list)
    blockedTaskIds: list[str] = Field(default_factory=list)
    independentTaskIds: list[str] = Field(default_factory=list)
    findings: list[PlanRisk] = Field(default_factory=list)
    stale: bool = False
    executionAuthorized: Literal[False] = False


class ExecutionStatus(StrEnum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    BLOCKED = "BLOCKED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    INTERRUPTED = "INTERRUPTED"
    PAUSED = "PAUSED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


EXECUTION_TRANSITIONS: dict[ExecutionStatus, set[ExecutionStatus]] = {
    ExecutionStatus.CREATED: {ExecutionStatus.VALIDATING, ExecutionStatus.CANCELLED},
    ExecutionStatus.VALIDATING: {ExecutionStatus.BLOCKED, ExecutionStatus.QUEUED, ExecutionStatus.FAILED},
    ExecutionStatus.BLOCKED: {ExecutionStatus.VALIDATING, ExecutionStatus.CANCELLED},
    ExecutionStatus.QUEUED: {ExecutionStatus.RUNNING, ExecutionStatus.INTERRUPTED, ExecutionStatus.CANCELLING, ExecutionStatus.CANCELLED},
    ExecutionStatus.RUNNING: {ExecutionStatus.PAUSED, ExecutionStatus.INTERRUPTED, ExecutionStatus.CANCELLING, ExecutionStatus.COMPLETED, ExecutionStatus.FAILED},
    ExecutionStatus.INTERRUPTED: {ExecutionStatus.QUEUED, ExecutionStatus.CANCELLED},
    ExecutionStatus.PAUSED: {ExecutionStatus.QUEUED, ExecutionStatus.CANCELLING, ExecutionStatus.CANCELLED},
    ExecutionStatus.CANCELLING: {ExecutionStatus.CANCELLED},
    ExecutionStatus.CANCELLED: set(), ExecutionStatus.COMPLETED: set(), ExecutionStatus.FAILED: {ExecutionStatus.QUEUED, ExecutionStatus.CANCELLED},
}


class ExecutionEvent(Model):
    at: datetime
    fromStatus: ExecutionStatus | None = None
    toStatus: ExecutionStatus
    reason: str
    sequence: int = 0
    previousHash: str = ""
    eventHash: str = ""


class FailureRecord(Model):
    classification: Literal["validation", "authorization", "worker", "transient", "unknown"]
    message: str
    retryable: bool
    manualInterventionRequired: bool = False


class TaskAttempt(Model):
    attempt: int
    at: datetime
    status: Literal["not-started", "failed", "completed"]
    failure: FailureRecord | None = None


class ExecutionTask(Model):
    taskId: str
    agentId: str
    status: ExecutionStatus
    priority: Literal["low", "medium", "high"]
    prerequisites: list[str] = Field(default_factory=list)
    attempts: list[TaskAttempt] = Field(default_factory=list)
    locked: bool = False
    lockOwner: str | None = None
    lockedAt: datetime | None = None


class Checkpoint(Model):
    checkpointId: str
    executionId: str
    taskId: str
    state: ExecutionStatus
    completedPrerequisites: list[str] = Field(default_factory=list)
    lastSuccessfulStep: str | None = None
    artifactReferences: list[EvidenceReference] = Field(default_factory=list)
    at: datetime
    stale: bool = False
    packageDigest: str = ""
    planRevision: str = ""
    orchestrationRevision: str = ""
    integrityHash: str = ""


class ExecutionLog(Model):
    at: datetime
    executionId: str
    taskId: str | None = None
    agentId: str | None = None
    provider: str | None = None
    eventType: str
    status: ExecutionStatus
    message: str
    artifactReferences: list[EvidenceReference] = Field(default_factory=list)


class GeneratedArtifact(Model):
    artifactId: str
    path: str
    artifactType: str
    sourceTaskId: str
    sourceReferences: list[EvidenceReference] = Field(default_factory=list)
    sha256: str | None = None
    templateRevisions: dict[str, str] = Field(default_factory=dict)
    validationStatus: Literal["not-produced", "unverified", "validated"] = "not-produced"


class ValidationResult(Model):
    stage: Literal["frontend-build", "backend-build", "backend-tests", "data-validation", "runtime-startup", "behavior-parity"]
    status: Literal["passed", "failed", "not-applicable", "not-run"]
    message: str
    at: datetime


class ExecutionRecord(Model):
    executionId: str
    engagementId: str
    moduleId: str
    packageId: str
    packageDigest: str
    planId: str
    planRevision: str
    orchestrationId: str
    orchestrationRevision: str
    targetConfiguration: dict = Field(default_factory=dict)
    templateRevisions: dict[str, str] = Field(default_factory=dict)
    createdAt: datetime
    updatedAt: datetime
    status: ExecutionStatus
    statusHistory: list[ExecutionEvent] = Field(default_factory=list)
    tasks: list[ExecutionTask] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)
    logs: list[ExecutionLog] = Field(default_factory=list)
    artifacts: list[GeneratedArtifact] = Field(default_factory=list)
    validation: list[ValidationResult] = Field(default_factory=list)
    maxAttempts: int = 1
    concurrencyLimit: int = 1
    stale: bool = False
    executionAuthorized: Literal[False] = False
    eventChainValid: bool = True
