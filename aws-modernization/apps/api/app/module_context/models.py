from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "2.0.0"
COLLECTOR_VERSION = "1.2.0"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PackageRequest(Model):
    moduleId: str = Field(min_length=1, max_length=300)
    templateIds: list[str] | None = Field(default=None, max_length=10)


class Finding(Model):
    code: str
    severity: Literal["blocker", "warning", "info"]
    message: str
    artifactId: str | None = None
    evidence: list[str] = Field(default_factory=list)
    action: str


class Artifact(Model):
    id: str
    kind: str
    path: str
    origin: str
    sha256: str
    bytes: int
    moduleId: str | None = None
    role: str
    provenance: Literal["observed", "deterministic-derived", "inferred", "ai-generated", "demo", "mixed", "unknown"]
    validation: str = "not-verified"
    approval: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    modificationAllowed: bool = False


class Readiness(Model):
    packageIntegrity: Literal["valid"] = "valid"
    modernizationPrerequisites: Literal["blocked", "review-required", "available"]
    findings: list[Finding]
    executionVerified: bool = False


class ManifestV1(Model):
    schemaVersion: Literal["1.0.0"] = "1.0.0"
    collectorVersion: str = COLLECTOR_VERSION
    packageId: str
    engagementId: str
    moduleId: str
    createdAt: str
    inputFingerprint: str
    packageDigest: str
    source: dict[str, Any]
    scope: dict[str, Any]
    target: dict[str, Any]
    templates: list[dict[str, Any]]
    approvals: dict[str, Any]
    coverage: dict[str, Any]
    artifacts: list[Artifact]
    readiness: Readiness


# Imported after Model is defined to keep reusable section models independent.
from .contracts import EngineContract

class Manifest(ManifestV1):
    schemaVersion: Literal["2.0.0"] = SCHEMA_VERSION
    contract: EngineContract
