"""Version 2 engine-facing contracts. Native upstream payloads remain unchanged."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict

class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")

Hash = str

class Reference(Model):
    artifactId: str
    pointer: str = ""

class InventoryEntry(Model):
    path: str
    sha256: str | None = None
    artifactId: str | None = None
    status: Literal["included", "excluded", "unavailable", "not-selected", "unsupported", "unresolved"]
    reason: str

class Entity(Model):
    id: str
    kind: str
    originalId: str | None = None
    reference: Reference

class Relationship(Model):
    kind: str
    fromId: str
    toId: str | None
    status: Literal["resolved", "missing", "unresolved"]
    originalReference: str | None = None
    evidence: Reference
    explanation: str

class TraceSummary(Model):
    totalArtifacts: int = 0
    resolvedRelationships: int
    missingRelationships: int
    unresolvedReferences: int
    uncoveredBusinessRules: int
    requirementsWithoutStoryCoverage: int
    storiesWithoutAcceptanceCriteria: int
    acceptanceCriteriaWithoutTestCoverage: int | None
    criterionCoverageAssessment: Literal["assessed-explicit-links", "unavailable"]

class Traceability(Model):
    version: Literal["1.0.0"] = "1.0.0"
    entities: list[Entity]
    relationships: list[Relationship]
    summary: TraceSummary

class Approval(Model):
    gateId: str
    gateType: str | None
    status: str | None
    decision: str | None
    comment: str | None
    actor: str | None
    timestamp: str | None
    artifactIds: list[str]
    recordedRevision: str | None
    snapshotHashes: dict[str, str]
    binding: Literal["exact-artifact-hash", "mismatch", "unavailable"]
    evidence: Reference
    unavailableFields: list[str]

class Approvals(Model):
    version: Literal["1.0.0"] = "1.0.0"
    records: list[Approval]

class Dependency(Model):
    id: str
    category: Literal["internal", "module", "library", "framework", "database", "api", "external-service", "messaging", "configuration", "build", "deployment"]
    status: Literal["confirmed", "potential", "unresolved", "external-incomplete", "implementation-unavailable"]
    name: str
    version: str | None = None
    implementationArtifactId: str | None = None
    evidence: Reference
    explanation: str

class Dependencies(Model):
    version: Literal["1.0.0"] = "1.0.0"
    completeness: Literal["not-proven"] = "not-proven"
    items: list[Dependency]
    counts: dict[str, int]

class TargetContract(Model):
    version: Literal["1.0.0"] = "1.0.0"
    snapshot: Reference | None
    configurationDigest: str
    language: str | None
    framework: str | None
    frameworkVersion: str | None
    runtime: str | None
    runtimeVersion: str | None
    architecture: str | None
    frontendFramework: str | None
    database: str | None
    apiApproach: str | None
    missingFields: list[str]
    templateIds: list[str]

class TemplateFile(Model):
    name: str
    reference: Reference
    sourcePath: str
    sha256: str

class TemplateContract(Model):
    id: str
    revision: str
    aggregateDigest: str
    sourceIdentity: str
    files: list[TemplateFile]
    missingFiles: list[str]
    compatibilityStatus: str

class ReadinessContract(Model):
    overallStatus: Literal["NOT_READY", "READY_WITH_WARNINGS", "READY"]
    executionAuthorized: Literal[False] = False
    counts: dict[str, int]
    categories: dict[str, list[int]]
    baseline: Literal["not-source-bound"] = "not-source-bound"

class EngineContract(Model):
    version: Literal["1.0.0"] = "1.0.0"
    inventory: list[InventoryEntry]
    traceability: Traceability
    approvals: Approvals
    dependencies: Dependencies
    target: TargetContract
    templates: list[TemplateContract]
    readiness: ReadinessContract
    artifactCount: int = 0
