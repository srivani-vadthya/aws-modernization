from __future__ import annotations

import hashlib
import json
from typing import Any

LANGUAGE_ALIASES = {
    "c#": "csharp",
    "csharp": "csharp",
    "cs": "csharp",
    ".net": "csharp",
    "dotnet": "csharp",
    "c# (.net 10)": "csharp",
    "c# (.net 9)": "csharp",
    "java": "java",
    "python": "python",
    "python-fastapi": "python",
    "node": "node",
    "javascript": "node",
    "typescript": "node",
}

FRAMEWORK_ALIASES = {
    "aspnetcore": "aspnetcore",
    "asp.net core": "aspnetcore",
    "dotnet": "aspnetcore",
    "dotnet 10": "aspnetcore",
    "dotnet10": "aspnetcore",
    "dotnet 9": "aspnetcore",
    "dotnet9": "aspnetcore",
    "spring": "spring-boot",
    "spring-boot": "spring-boot",
    "spring boot": "spring-boot",
    "fastapi": "fastapi",
    "django": "django",
    "react": "react",
    "next": "next",
    "node-express": "node-express",
}

ARCHITECTURE_ALIASES = {
    "clean": "clean-architecture",
    "clean architecture": "clean-architecture",
    "ddd": "ddd",
    "domain-driven-design": "ddd",
    "hexagonal": "hexagonal",
    "layered": "layered",
    "modular": "modular",
    "microservice": "microservice",
    "event-driven": "event-driven",
}

VALID_LANGUAGE_FRAMEWORKS = {
    "csharp": {"aspnetcore", "dotnet"},
    "java": {"spring-boot"},
    "python": {"fastapi", "django"},
    "node": {"react", "next", "node-express"},
}


def normalize_string(value: Any, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def normalize_target_contract(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    language = normalize_string(raw.get("language") or raw.get("languageName") or raw.get("stack"), default="")
    framework = normalize_string(raw.get("framework") or raw.get("frameworkName") or raw.get("frameworkType"), default="")
    architecture = normalize_string(raw.get("architecture") or raw.get("architectureStyle") or raw.get("pattern"), default="")
    language_lower = language.lower()
    framework_lower = framework.lower()
    runtime = normalize_string(raw.get("runtime"), default="")
    data = normalize_string(raw.get("data") or raw.get("dataEngine") or raw.get("database"), default="")
    language_version = normalize_string(raw.get("languageVersion") or raw.get("version"), default="")
    framework_version = normalize_string(raw.get("frameworkVersion") or raw.get("framework_version"), default="")
    runtime_version = normalize_string(raw.get("runtimeVersion") or raw.get("runtime_version"), default="")

    lang = LANGUAGE_ALIASES.get(language_lower, language_lower or "")
    if not lang and ("c#" in language_lower or ".net" in language_lower or "dotnet" in language_lower):
        lang = "csharp"
    if not lang and "python" in language_lower:
        lang = "python"
    if not lang and "java" in language_lower:
        lang = "java"

    fw = FRAMEWORK_ALIASES.get(framework_lower, framework_lower)
    if "aspnet" in framework_lower or "dotnet" in framework_lower or ".net" in framework_lower:
        fw = "aspnetcore"
    if "spring" in framework_lower or "spring-boot" in framework_lower:
        fw = "spring-boot"
    if "fastapi" in framework_lower:
        fw = "fastapi"
    if not fw:
        if lang == "csharp":
            fw = "aspnetcore"
        elif lang == "java":
            fw = "spring-boot"
        elif lang == "python":
            fw = "fastapi"
        elif lang == "node":
            fw = "node-express"
    arch = ARCHITECTURE_ALIASES.get(architecture.lower(), architecture.lower())
    runtime_norm = (runtime or "").lower()
    if not runtime_norm and lang == "csharp":
        runtime_norm = "dotnet"
    if not runtime_norm and lang == "java":
        runtime_norm = "jvm"
    if not runtime_norm and lang == "python":
        runtime_norm = "python"

    if not language_version and lang == "csharp" and ("10" in (framework or "") or "net10" in (framework or "") or "dotnet 10" in (framework or "")):
        language_version = "10"
    if not framework_version and lang == "csharp" and ("10" in (framework or "") or "net10" in (framework or "") or "dotnet 10" in (framework or "")):
        framework_version = "10"
    if not framework_version and lang == "java" and "21" in (framework or ""):
        framework_version = "21"

    approved = bool(raw.get("approved") or raw.get("isApproved") or raw.get("approvalStatus") == "approved")
    approved_by = normalize_string(raw.get("approvedBy") or raw.get("approved_by"))
    approved_at = normalize_string(raw.get("approvedAt") or raw.get("approved_at"))
    status = "APPROVED" if approved else "DRAFT"

    if not any([lang, fw, arch, data]):
        status = "NEEDS_USER_INPUT"

    normalized = {
        "language": lang or "unknown",
        "framework": fw or framework.lower() or "unknown",
        "architecture": arch or architecture.lower() or "unknown",
        "runtime": runtime_norm or "unknown",
        "data": (data or raw.get("dataEngine") or "unknown").lower() or "unknown",
        "languageVersion": language_version,
        "frameworkVersion": framework_version,
        "runtimeVersion": runtime_version,
        "deploymentCloud": normalize_string(raw.get("deploymentCloud") or raw.get("cloud"), default=""),
        "deploymentRegion": normalize_string(raw.get("deploymentRegion") or raw.get("region"), default=""),
        "deploymentEnvironment": normalize_string(raw.get("deploymentEnvironment") or raw.get("environment"), default=""),
        "frontendRequirement": normalize_string(raw.get("frontendRequirement") or raw.get("frontend"), default=""),
        "serviceDecomposition": normalize_string(raw.get("serviceDecomposition") or raw.get("serviceDecompositionStyle"), default=""),
        "approved": approved,
        "approvedBy": approved_by,
        "approvedAt": approved_at,
        "approvalStatus": status,
        "targetVersion": normalize_string(raw.get("targetVersion"), default="1.0"),
        "configurationDigest": "",
    }
    normalized["configurationDigest"] = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode("utf-8")).hexdigest()

    _validate_mappings(normalized)
    return normalized


def _validate_mappings(target: dict[str, Any]) -> None:
    lang = target["language"]
    framework = target["framework"]
    if lang == "csharp" and framework not in VALID_LANGUAGE_FRAMEWORKS["csharp"]:
        raise ValueError(f"Unsupported C# target framework '{framework}'. Use aspnetcore or dotnet.")
    if lang == "java" and framework not in VALID_LANGUAGE_FRAMEWORKS["java"]:
        raise ValueError(f"Unsupported Java target framework '{framework}'. Use spring-boot.")
    if lang == "python" and framework not in VALID_LANGUAGE_FRAMEWORKS["python"]:
        raise ValueError(f"Unsupported Python target framework '{framework}'. Use fastapi or django.")
    if lang == "node" and framework not in VALID_LANGUAGE_FRAMEWORKS["node"]:
        raise ValueError(f"Unsupported Node target framework '{framework}'. Use node-express, react, or next.")
    if lang == "csharp" and "java" in framework:
        raise ValueError("Contradictory target: C# cannot target Java/Spring Boot.")
    if lang == "java" and "c#" in framework:
        raise ValueError("Contradictory target: Java cannot target C#/.NET.")
    if target["approved"] and not target.get("approvedBy"):
        target["approvedBy"] = "user"


def target_is_active(target: dict[str, Any] | None) -> bool:
    if not target:
        return False
    return bool(target.get("approved")) and target.get("approvalStatus") == "APPROVED"


def validate_target_contract(payload: dict[str, Any] | None, *, require_approval: bool = False) -> dict[str, Any]:
    target = normalize_target_contract(payload)
    if require_approval and not target_is_active(target):
        raise ValueError("Target must be explicitly approved by the user before migration can start.")
    if target.get("approvalStatus") == "NEEDS_USER_INPUT":
        if require_approval:
            raise ValueError("Target is incomplete and cannot start migration.")
    return target
