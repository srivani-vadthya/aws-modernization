from __future__ import annotations

import re
from pathlib import Path
from .repository import ContextError, canonical, digest, safe_child

APP_ROOT = Path(__file__).resolve().parents[4]
BASE = ".agents/skills/polyglot-architecture-synthesizer"
DOTNET = ["dotnet-file-structure", "dotnet-model", "dotnet-dto", "dotnet-dbcontext", "dotnet-repository", "dotnet-service", "dotnet-controller"]
REACT = ["file-structure", "api-connector", "json-config-driven-form", "page-with-form", "form-input-component", "button-component", "modal-component", "table-component"]


def registry() -> list[dict]:
    return [
        {"id": "dotnet8-guidance", "root": APP_ROOT / BASE / "templates/DotNet_8_clean_architecture",
         "sourcePath": BASE + "/templates/DotNet_8_clean_architecture", "skills": DOTNET,
         "kind": "guidance", "language": "csharp", "framework": "aspnetcore", "major": "8",
         "limitations": ["Detailed .NET 8 instructions are authoritative; parent .NET 9 guidance is not combined."]},
        {"id": "react-guidance", "root": APP_ROOT / BASE / "templates/React",
         "sourcePath": BASE + "/templates/React", "skills": REACT,
         "kind": "guidance", "language": "typescript", "framework": "react", "major": None,
         "limitations": ["Evaluate each skill's applicability; Angular-specific conditions are not universal."]},
    ]


def recommendations(target: dict) -> list[str]:
    language = str(target.get("language", "")).lower()
    framework = str(target.get("framework", "")).lower()
    ids = []
    if any(x in language for x in ("c#", "csharp", ".net", "dotnet")) or framework in {"aspnetcore", "dotnet", ".net"}:
        ids.append("dotnet8-guidance")
    if framework == "react" or re.search(r"\breact\b", str(target.get("frontendRequirement", "")).lower()):
        ids.append("react-guidance")
    return ids


def select(ids: list[str] | None, target: dict | None = None) -> list[dict]:
    ids = recommendations(target or {}) if ids is None else ids
    rows = {r["id"]: r for r in registry()}
    if len(ids) != len(set(ids)) or any(i not in rows for i in ids):
        raise ContextError("Select unique authoritative golden bundle IDs", 422)
    return [rows[i] for i in sorted(ids)]


def inspect_bundle(row: dict, target: dict | None = None) -> tuple[dict, dict[str, bytes]]:
    target = target or {}
    files, contents, missing = [], {}, []
    # An exact allowlist, not an arbitrary recursive template directory.
    expected = [s + "/SKILL.md" for s in row.get("skills", [])] or ["SKILL.md"]
    for rel in expected:
        try:
            path = safe_child(row["root"], rel)
            data = path.read_bytes()
        except (OSError, ContextError):
            missing.append(rel)
            continue
        text = data.decode("utf-8")
        name = re.search(r"(?m)^name:\s*(.+)$", text)
        trigger = re.search(r"(?m)^trigger:\s*(.+)$", text)
        condition = re.search(r"## When to Apply\s*([\s\S]*?)(?=\n## |\Z)", text)
        files.append({"path": rel, "sourcePath": row.get("sourcePath", "") + "/" + rel,
                      "name": name.group(1).strip() if name else rel.split("/")[0],
                      "sha256": digest(data), "bytes": len(data),
                      "applicability": {"trigger": trigger.group(1).strip() if trigger else "not-declared",
                          "condition": condition.group(1).strip() if condition else "See complete skill instructions.",
                          "evaluation": "requires-review"},
                      "packagePath": "templates/" + row["id"] + "/" + rel})
        contents[rel] = data
    combined = "\n".join(b.decode("utf-8") for b in contents.values())
    dependencies = [{"name": n, "version": v, "basis": "declared-in-skill"} for n, v in
                    re.findall(r'PackageReference Include="([^"]+)" Version="([^"]+)"', combined)]
    versions = sorted(set(re.findall(r"<TargetFramework>([^<]+)</TargetFramework>", combined)))
    unresolved = []
    if row["id"] == "react-guidance":
        dependencies += [{"name": n, "version": None, "basis": "referenced-in-skill-version-undeclared"}
                         for n in ["react", "typescript", "react-router-dom", "axios", "node"]]
        unresolved = ["Dependency versions", "deepClone", "validateFormFields", "Card", "CardContent",
                      "Typography", "Select", "MainLayout", "CSS variable tokens", "build configuration"]
    issues = []
    def issue(code, message, severity="blocker"):
        issues.append({"code": code, "message": message, "severity": severity, "resolution": "unresolved"})
    if missing:
        issue("TEMPLATE_MISSING", "Required skill files are unavailable: " + ", ".join(missing))
    if row["id"] not in recommendations(target):
        issue("TEMPLATE_TARGET_CONFLICT", "Bundle does not match an explicit configured target.")
    parent = None
    if row["id"] == "dotnet8-guidance":
        version = str(target.get("frameworkVersion") or target.get("runtimeVersion") or "")
        if not version:
            issue("TEMPLATE_VERSION_UNRESOLVED", "Explicit .NET framework/runtime version is missing.")
        elif not re.match(r"^(?:net)?8(?:[.]|$)", version):
            issue("TEMPLATE_VERSION_CONFLICT", "Detailed skills require .NET 8.")
        for field in ("frameworkVersion", "runtimeVersion"):
            supplied = str(target.get(field) or "")
            if supplied and not re.match(r"^(?:net)?8(?:[.]|$)", supplied):
                issue("TEMPLATE_" + field.upper() + "_CONFLICT", field + " conflicts with .NET 8.")
        if str(target.get("framework", "")).lower() not in {"aspnetcore", "asp.net core", "dotnet", ".net"}:
            issue("TEMPLATE_FRAMEWORK_CONFLICT", "Detailed skills require ASP.NET Core.")
        architecture = str(target.get("architecture") or "").lower()
        if not architecture:
            issue("TARGET_ARCHITECTURE_MISSING", "Backend architecture is not configured.")
        elif any(word in architecture for word in ("hexagonal", "vertical slice", "cqrs")):
            issue("TARGET_ARCHITECTURE_CONFLICT", "Configured architecture differs from detailed controller/service/repository layout.")
        api = str(target.get("apiApproach") or "").lower()
        if not api:
            issue("TARGET_API_APPROACH_MISSING", "API approach is not explicitly configured.")
        elif api not in {"controllers", "controller", "rest controllers", "asp.net core controllers"}:
            issue("TARGET_API_APPROACH_CONFLICT", "Detailed skills require controller-based HTTP APIs.")
        database = str(target.get("data", "")).lower()
        if "postgres" in database:
            issue("TEMPLATE_DATABASE_CONFLICT", "SQL Server skill instructions conflict with the PostgreSQL target or unresolved provider choice.")
        elif not ("sql server" in database or "sqlserver" in database):
            issue("TEMPLATE_DATABASE_UNRESOLVED", "SQL Server skill instructions require an explicit provider decision.")
        parent_path = APP_ROOT / BASE / "SKILL.md"
        parent = {"sourcePath": BASE + "/SKILL.md", "selectable": False, "authority": "context-only",
                  "sha256": digest(parent_path.read_bytes()) if parent_path.is_file() else None,
                  "applied": False}
        issue("TEMPLATE_GUIDANCE_CONFLICT", "Parent .NET 9/hexagonal guidance conflicts with detailed .NET 8 layout. Detailed .NET 8 skills govern this bundle; record explicit conflict acknowledgement before execution.")
    else:
        issue("REACT_APPLICABILITY_REVIEW", "Evaluate Angular-specific conditions per skill before applying instructions.", "warning")
        issue("TEMPLATE_DEPENDENCIES_UNRESOLVED", "React dependency versions and referenced supporting implementations are not supplied by this bundle.")
    hashes = {f["path"]: f["sha256"] for f in files}
    bundle_digest = digest(canonical(hashes))
    result = {**{k: v for k, v in row.items() if k not in {"root", "skills"}},
              "metadataVersion": "1.0.0", "authority": "existing-skill-instructions",
              "sourceIdentity": row.get("sourcePath", "fixture-template"), "declaredRevision": None,
              "revision": "sha256:" + bundle_digest, "contentDigest": bundle_digest,
              "digestPolicy": "sha256 of canonical JSON mapping bundle-relative paths to file SHA-256",
              "fileCount": len(files), "available": not missing, "missingFiles": missing,
              "files": files, "frameworkVersions": versions, "dependencies": dependencies,
              "unresolvedDependencies": unresolved, "parentGuidance": parent,
              "compatibility": {"targetDigest": digest(canonical(target)), "issues": issues,
                                "status": "blocked" if any(i["severity"] == "blocker" for i in issues) else "review-required"}}
    return result, contents


def catalog(target: dict | None = None) -> list[dict]:
    return [inspect_bundle(row, target)[0] for row in registry()]
