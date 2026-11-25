"""Approval-gated provider execution in an isolated modernization workspace."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Callable

from .models import (ExecutionLog, ExecutionRecord, ExecutionStatus, FailureRecord, GeneratedArtifact,
                     TaskAttempt)
from .providers import AwsTransformProvider, BedrockProvider, is_dotnet8_target
from ..module_context.repository import safe_child

_OUTPUT_ROOTS = {"frontend", "backend", "data", "docs", "tests"}


def _template_revisions(manifest: dict) -> dict[str, str]:
    return {item["id"]: item["revision"] for item in manifest.get("templates", [])}


def _template_context(manifest: dict, package_root, category: str) -> str:
    """Load immutable package snapshots, never mutable original skill files."""
    wanted = "dotnet8-guidance" if category in {"backend", "api"} else "react-guidance" if category == "frontend" else None
    sections, total = [], 0
    for artifact in manifest.get("artifacts", []):
        if artifact.get("kind") != "template" or (wanted and not artifact.get("path", "").startswith(f"templates/{wanted}/")):
            continue
        try:
            content = safe_child(package_root, artifact["path"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        remaining = 24_000 - total
        if remaining <= 0: break
        sections.append(f"TEMPLATE {artifact['path']}:\n{content[:remaining]}")
        total += min(len(content), remaining)
    return "\n\n".join(sections) or "No applicable immutable template snapshot is available."


def _safe_output_path(value: str) -> str | None:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] not in _OUTPUT_ROOTS:
        return None
    return path.as_posix()


def _source_context(manifest: dict, package_root, artifact_ids: set[str] | None = None) -> str:
    excerpts: list[str] = []
    total = 0
    for artifact in manifest.get("artifacts", []):
        if artifact.get("kind") != "source" or artifact.get("role") not in {"selected", "dependency", "shared"}:
            continue
        if artifact_ids is not None and artifact.get("id") not in artifact_ids:
            continue
        path = artifact.get("path", "")
        if not path.startswith("source/"):
            continue
        try:
            text = safe_child(package_root, path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        remaining = 48_000 - total
        if remaining <= 0:
            break
        excerpt = text[:remaining]
        excerpts.append(f"FILE: {path.removeprefix('source/')}\n{excerpt}")
        total += len(excerpt)
    return "\n\n".join(excerpts)


def _generated_context(workspace) -> str:
    """Expose bounded generated API context to later dependent tasks."""
    excerpts, total = [], 0
    for path in sorted(workspace.rglob("*")) if workspace.exists() else []:
        if not path.is_file() or path.suffix.lower() not in {".cs", ".json", ".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        remaining = 16_000 - total
        if remaining <= 0:
            break
        excerpts.append(f"GENERATED: {path.relative_to(workspace).as_posix()}\n{text[:remaining]}")
        total += min(len(text), remaining)
    return "\n\n".join(excerpts) or "No generated files yet."


def _files_from_response(output: str, allowed_roots: set[str] | None = None) -> dict[str, str]:
    """Accept JSON wrapped in prose/fences, but never accept non-file output."""
    # Capture the complete fenced body, not the first balanced-looking object.
    # The earlier expression stopped at the first `}` inside `files`, so a
    # perfectly valid multi-file JSON response was incorrectly rejected.
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", output, re.S | re.I)
    candidate = match.group(1) if match else output.strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        start = output.find("{")
        if start < 0:
            raise
        payload, _ = decoder.raw_decode(output[start:])
    # A few models wrap the contract in a tool/result envelope. Accept that
    # documented shape while still applying the exact same path/content checks.
    if isinstance(payload, dict) and not isinstance(payload.get("files"), dict):
        for key in ("result", "output", "generated"):
            nested = payload.get(key)
            if isinstance(nested, dict) and isinstance(nested.get("files"), dict):
                payload = nested
                break
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("Provider response did not contain a files object")
    result = {}
    for name, content in files.items():
        safe = _safe_output_path(str(name))
        if safe is None or not isinstance(content, str) or (allowed_roots and safe.split("/", 1)[0] not in allowed_roots):
            raise ValueError("Provider response contains an unsafe or invalid output path")
        result[safe] = content
    if not result:
        raise ValueError("Provider response did not contain generated files")
    return result


def execute_bedrock_task(record: ExecutionRecord, task_id: str, plan_task, manifest: dict, package_root, workspace) -> ExecutionRecord:
    task = next(item for item in record.tasks if item.taskId == task_id)
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    running_task = task.model_copy(update={"status": ExecutionStatus.RUNNING, "locked": True, "lockOwner": "bedrock-provider", "lockedAt": now})
    tasks = [running_task if item.taskId == task_id else item for item in record.tasks]
    record = record.model_copy(update={"tasks": tasks, "updatedAt": now})
    target = record.targetConfiguration
    root = {"backend": "backend", "frontend": "frontend", "configuration": "docs", "api": "backend"}.get(plan_task.category, "docs")
    system = f"Return exactly one JSON object and no prose: {{\"files\":{{\"{root}/relative-file\":\"full file content\"}}}}. Every path must start with {root}/. Do not use markdown fences."
    source_ids = {ref.artifactId for ref in plan_task.sourceArtifacts}
    prompt = "Target configuration:\n" + json.dumps(target, sort_keys=True) + "\n\nGolden-template snapshots (must be followed):\n" + _template_context(manifest, package_root, plan_task.category) + "\n\nTask:\n" + plan_task.description + "\n\nExisting generated output:\n" + _generated_context(workspace) + "\n\nLegacy evidence:\n" + _source_context(manifest, package_root, source_ids)
    # 2,000 tokens commonly truncates even one ordinary source file. The plan
    # is batched, and this bounded response budget is large enough for useful
    # file mappings without asking the model to generate an entire application
    # in one call.
    result = BedrockProvider().invoke("code", system, prompt, max_tokens=8000)
    if not result.ok or not result.output:
        return _failed(record, task_id, "Bedrock did not return a usable implementation response.", "amazon-bedrock")
    try:
        files = _files_from_response(result.output, {root})
    except (ValueError, json.JSONDecodeError):
        correction = BedrockProvider().invoke("code", system,
            prompt + "\n\nYour previous response was rejected. Return ONLY one valid JSON object with a non-empty files mapping under " + root + "/.", max_tokens=8000)
        if not correction.ok or not correction.output:
            return _failed(record, task_id, "Bedrock response was not a safe generated-file mapping after one correction retry.", "amazon-bedrock")
        try:
            files = _files_from_response(correction.output, {root})
        except (ValueError, json.JSONDecodeError):
            return _failed(record, task_id, "Bedrock response was not a safe generated-file mapping after one correction retry.", "amazon-bedrock")
        record = record.model_copy(update={"logs": [*record.logs, ExecutionLog(at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc), executionId=record.executionId, taskId=task_id, agentId=task.agentId, provider="amazon-bedrock", eventType="provider-format-retry", status=ExecutionStatus.RUNNING, message="One correction retry produced a valid file mapping.")]})
    artifacts = list(record.artifacts)
    for relative, content in files.items():
        path = safe_child(workspace, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        artifacts.append(GeneratedArtifact(artifactId=hashlib.sha256((task_id + relative).encode()).hexdigest()[:24], path="output/" + relative, artifactType="generated-source", sourceTaskId=task_id, sourceReferences=plan_task.sourceArtifacts, sha256=hashlib.sha256(content.encode()).hexdigest(), templateRevisions=_template_revisions(manifest), validationStatus="unverified"))
    completed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    completed = running_task.model_copy(update={"status": ExecutionStatus.COMPLETED, "locked": False, "lockOwner": None, "lockedAt": None, "attempts": [*running_task.attempts, TaskAttempt(attempt=len(running_task.attempts) + 1, at=completed_at, status="completed")]})
    return record.model_copy(update={"tasks": [completed if item.taskId == task_id else item for item in record.tasks], "artifacts": artifacts, "updatedAt": completed_at, "logs": [*record.logs, ExecutionLog(at=completed_at, executionId=record.executionId, taskId=task_id, agentId=task.agentId, provider="amazon-bedrock", eventType="provider-complete", status=ExecutionStatus.RUNNING, message="Bedrock generated files were written to the isolated execution workspace; validation is pending.")]})


def _failed(record: ExecutionRecord, task_id: str, message: str, provider: str | None = None) -> ExecutionRecord:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    task = next(item for item in record.tasks if item.taskId == task_id)
    attempt = TaskAttempt(attempt=len(task.attempts) + 1, at=now, status="failed",
                          failure=FailureRecord(classification="worker", message=message, retryable=True))
    failed = task.model_copy(update={"status": ExecutionStatus.FAILED, "locked": False, "lockOwner": None, "lockedAt": None, "attempts": [*task.attempts, attempt]})
    return record.model_copy(update={"tasks": [failed if item.taskId == task_id else item for item in record.tasks], "updatedAt": now, "logs": [*record.logs, ExecutionLog(at=now, executionId=record.executionId, taskId=task_id, agentId=task.agentId, provider=provider, eventType="provider-failed", status=ExecutionStatus.RUNNING, message=message)]})


def _stage_transform_input(manifest: dict, package_root, workspace, plan_task) -> tuple[Path, int]:
    """Copy only plan-approved source evidence into Transform's isolated input."""
    source = workspace.parent / "legacy-source"
    source.mkdir(parents=True, exist_ok=True)
    allowed = {reference.artifactId for reference in plan_task.sourceArtifacts}
    selected_paths = [artifact.get("path", "").removeprefix("source/") for artifact in manifest.get("artifacts", [])
                      if artifact.get("kind") == "source" and artifact.get("role") == "selected"]
    included_paths: list[str] = []
    staged = 0
    for artifact in manifest.get("artifacts", []):
        if artifact.get("id") not in allowed or artifact.get("kind") != "source":
            continue
        package_path = artifact.get("path", "")
        if not package_path.startswith("source/"):
            continue
        try:
            input_path = safe_child(package_root, package_path)
            output_path = safe_child(source, package_path.removeprefix("source/"))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, output_path)
            staged += 1
            included_paths.append(package_path.removeprefix("source/"))
        except OSError:
            continue
    # This is generated execution metadata, never legacy source. It gives the
    # Transform definition an immutable, auditable boundary for the selected
    # module and the exact project/dependency closure we staged.
    scope_manifest = {
        "schemaVersion": "1.0",
        "mode": "selected-scope-with-dependency-closure",
        "selectedSourcePaths": sorted(selected_paths),
        "includedDependencyAndBuildPaths": sorted(path for path in included_paths if path not in selected_paths),
        "excludedRule": "Do not modernize files outside this manifest unless required solely to preserve a declared project reference.",
        "missingInputPolicy": "Continue best-effort with placeholders and report unavailable legacy inputs as gaps.",
    }
    safe_child(source, "modernization-scope.json").write_text(json.dumps(scope_manifest, indent=2), encoding="utf-8")
    template_contract = {"schemaVersion": "1.0", "bundles": manifest.get("templates", []),
                         "instruction": "Use only these immutable package snapshots as golden-template guidance."}
    safe_child(source, "modernization-template-contract.json").write_text(json.dumps(template_contract, indent=2), encoding="utf-8")
    for artifact in manifest.get("artifacts", []):
        if artifact.get("kind") != "template" or not artifact.get("path", "").startswith("templates/"):
            continue
        try:
            destination = safe_child(source, ".modernization-templates/" + artifact["path"].removeprefix("templates/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe_child(package_root, artifact["path"]), destination)
        except OSError:
            continue
    return source, staged


def execute_transform_task(record: ExecutionRecord, task_id: str, plan_task, manifest: dict, package_root, workspace,
                           on_progress: Callable[[str], None] | None = None) -> ExecutionRecord:
    # Keep copied legacy input outside the generated-output root so the explorer
    # and validation never mistake it for generated application code.
    source, staged_count = _stage_transform_input(manifest, package_root, workspace, plan_task)
    if on_progress:
        on_progress(f"AWS Transform staging prepared: {staged_count} selected-module/project files.")
    # Transform works in its own staged source tree. Capture the exact input
    # hashes before invocation, then collect only files that it created or
    # changed. Original package content is never treated as generated output.
    before = {path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in source.rglob("*") if path.is_file()}
    if staged_count == 0 or not any(path.suffix.lower() == ".csproj" for path in source.rglob("*")):
        return _failed(record, task_id,
                       "AWS Transform preflight failed: the selected-module staging area has no source files or .NET project file.",
                       "aws-transform")
    target = record.targetConfiguration
    if not is_dotnet8_target(target):
        return _failed(record, task_id, "AWS/dotnet-modernization is incompatible with the approved target.", "aws-transform")
    result = AwsTransformProvider().execute("AWS/dotnet-modernization", str(source), str(workspace), on_progress=on_progress)
    if not result.ok:
        return _failed(record, task_id, f"{result.message} Transform staged {staged_count} selected-module/project files.", "aws-transform")
    changed = [path for path in source.rglob("*") if path.is_file()
               and before.get(path.relative_to(source).as_posix()) != hashlib.sha256(path.read_bytes()).hexdigest()]
    if not changed:
        return _failed(record, task_id, f"AWS Transform completed but did not create or change files in its isolated staging workspace. Transform staged {staged_count} selected-module/project files.", "aws-transform")
    output = workspace / "backend" / "transform"
    generated: list[Path] = []
    for source_path in changed:
        relative = source_path.relative_to(source)
        destination = safe_child(output, relative.as_posix())
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        generated.append(destination)
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    task = next(item for item in record.tasks if item.taskId == task_id)
    completed = task.model_copy(update={"status": ExecutionStatus.COMPLETED, "locked": False, "lockOwner": None, "lockedAt": None, "attempts": [*task.attempts, TaskAttempt(attempt=len(task.attempts) + 1, at=now, status="completed")]})
    artifacts = [*record.artifacts, *[GeneratedArtifact(artifactId=hashlib.sha256((task_id + str(p)).encode()).hexdigest()[:24], path="output/" + p.relative_to(workspace).as_posix(), artifactType="generated-source", sourceTaskId=task_id, sourceReferences=plan_task.sourceArtifacts, sha256=hashlib.sha256(p.read_bytes()).hexdigest(), templateRevisions=_template_revisions(manifest), validationStatus="unverified") for p in generated]]
    return record.model_copy(update={"tasks": [completed if item.taskId == task_id else item for item in record.tasks], "artifacts": artifacts, "updatedAt": now, "logs": [*record.logs, ExecutionLog(at=now, executionId=record.executionId, taskId=task_id, agentId=task.agentId, provider="aws-transform", eventType="provider-complete", status=ExecutionStatus.RUNNING, message=f"AWS Transform output was collected from {staged_count} selected-module/project files into the isolated execution workspace; validation is pending.")]})
