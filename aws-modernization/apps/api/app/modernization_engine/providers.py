from __future__ import annotations

import shutil
import subprocess
import os
import json
import re
import queue
import threading
import time
from pathlib import Path
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


def _configured(name: str) -> bool:
    """Report configuration presence without reading or exposing a secret value."""
    return bool(os.getenv(name))


PROVIDER_CAPABILITIES = {
    # Installed adapter evidence: provider_execution currently invokes the custom
    # definition only for an approved .NET 8 backend/API target.  Do not claim
    # generic frontend support merely because a CLI is present.
    "aws-transform": {"available": False, "workstreams": {"backend", "api"}},
    "amazon-bedrock": {"available": True, "workstreams": {"backend", "frontend", "api", "configuration"}},
    "custom": {"available": False, "workstreams": set()},
    "manual-engineering-review": {"available": True, "workstreams": {"backend", "frontend", "database", "api", "integration", "configuration", "build", "testing"}},
}

TRANSFORM_DOTNET_DEFINITION = "AWS/dotnet-modernization"
DEFAULT_TRANSFORM_EXECUTION_ARGUMENTS = [
    "custom", "def", "exec", "--code-repository-path", "{working_directory}",
    "--transformation-name", TRANSFORM_DOTNET_DEFINITION, "--non-interactive", "--classic",
    "--do-not-learn", "--trust-all-tools", "--configuration",
    "additionalPlanContext=Target .NET 8. Read modernization-scope.json and modernization-template-contract.json in the repository root. Apply the immutable selected golden-template snapshots in .modernization-templates. Modernize only the declared selected scope and its declared dependency/project closure; do not expand into unrelated legacy areas. Continue best-effort migration for available source. Record unavailable legacy files as gaps and generate placeholders where configuration values are unavailable.",
]
TRANSFORM_NO_PROGRESS_TIMEOUT_SECONDS = 300
# Complex selected-scope closures can span linked MVC, data, and entity
# projects. Keep a bounded ceiling, but allow Transform enough time to finish
# its code-writing and review phases.
TRANSFORM_TOTAL_TIMEOUT_SECONDS = 7200


def _safe_cli_diagnostic(value: str) -> str:
    """Keep the actionable CLI reason while never persisting credential-like text."""
    value = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(aws_secret_access_key|aws_access_key_id|token|api[_-]?key)\s*[=:]\s*[^\s]+", r"\1=[REDACTED]", value)
    return value.strip()[-2000:]


def _cli_path(value: str) -> str:
    """Convert Python's Windows extended path into a form cmd-based CLIs accept."""
    # pathlib resolves paths under this service with the \\?\ prefix. Python
    # accepts it, but atx.cmd delegates to CMD.EXE, which treats it as a UNC cwd.
    if os.name == "nt" and value.startswith("\\\\?\\"):
        return value[4:]
    return value


def transform_host_sdk_ready() -> bool:
    """AWS Transform's .NET modernization worker currently requires SDK 10+."""
    try:
        result = subprocess.run(["dotnet", "--list-sdks"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    for line in result.stdout.splitlines():
        match = re.match(r"\s*(\d+)\.", line)
        if match and int(match.group(1)) >= 10:
            return True
    return False


def _stop_process_tree(process: subprocess.Popen) -> None:
    """Stop the CLI and its Node child when a bounded execution is abandoned."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, check=False, timeout=15)
        else:
            process.kill()
    except (OSError, subprocess.TimeoutExpired):
        process.kill()


def _conversation_events(working_directory: str) -> list[str]:
    """Read non-secret progress metadata that AWS Transform writes locally."""
    root = Path.home() / ".aws" / "atx" / "custom"
    if not root.is_dir():
        return []
    target = _cli_path(working_directory).lower()
    matches = []
    for folder in root.iterdir():
        metadata = folder / "metadata.json"
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _cli_path(str(data.get("workingDirectory", ""))).lower() == target:
            matches.append(folder)
    if not matches:
        return []
    conversation = max(matches, key=lambda item: item.stat().st_mtime)
    events = [f"AWS Transform conversation: {conversation.name}"]
    artifacts = conversation / "artifacts"
    if artifacts.is_dir():
        events.extend(f"AWS Transform artifact created: {item.name}" for item in artifacts.iterdir() if item.is_file())
    agents = conversation / "subagents"
    if agents.is_dir():
        for item in agents.glob("*.json"):
            try:
                data = json.loads(item.read_text(encoding="utf-8"))
                events.append(f"AWS Transform worker {data.get('agentType', 'unknown')}: {data.get('status', 'unknown')}")
            except (OSError, ValueError):
                continue
    return events


def aws_transform_executable() -> str | None:
    """Resolve the CLI without requiring its installer directory to be on PATH."""
    configured = os.getenv("AWS_TRANSFORM_CLI_PATH")
    candidates = [configured] if configured else []
    local = os.getenv("LOCALAPPDATA")
    if local:
        candidates.append(str(Path(local) / "atx" / "bin" / "atx.cmd"))
    candidates.append(shutil.which("atx"))
    return next((item for item in candidates if item and Path(item).is_file()), None)


def aws_transform_execution_configured() -> bool:
    """Return whether the supported .NET Transform CLI invocation is runnable.

    An operator may override the arguments for a newer CLI release, but the
    installed AWS/dotnet-modernization definition has a documented default.
    """
    try: value = json.loads(os.getenv("AWS_TRANSFORM_EXEC_ARGUMENTS", ""))
    except json.JSONDecodeError: value = DEFAULT_TRANSFORM_EXECUTION_ARGUMENTS
    if not value: value = DEFAULT_TRANSFORM_EXECUTION_ARGUMENTS
    return aws_transform_executable() is not None and isinstance(value, list) and all(isinstance(item, str) for item in value)


def provider_readiness() -> dict[str, dict[str, Any]]:
    """Non-invoking configuration snapshot used by planning and the UI.

    It intentionally does not call Transform or Bedrock.  CLI definition discovery
    and Bedrock model access require authenticated external calls, which belong to
    an explicit provider-verification operation rather than package preparation.
    """
    from ..llm_gateway import LLMGateway
    gateway = LLMGateway()
    executable = aws_transform_executable()
    transform_execution = aws_transform_execution_configured()
    transform_issues = []
    if not executable:
        transform_issues.append("AWS Transform CLI (atx) is not installed or not configured.")
    if executable and not transform_execution:
        transform_issues.append("AWS Transform execution arguments are not configured.")
    if transform_execution and not transform_host_sdk_ready():
        transform_issues.append("AWS Transform .NET worker requires a local .NET SDK 10 or later; install it before execution.")
    transform_issues.append("Installed Transform definitions have not been verified by a read-only CLI discovery operation.")
    bedrock_api_key = _configured("BEDROCK_API_KEY")
    bedrock_iam = _configured("AWS_ACCESS_KEY_ID") or _configured("AWS_PROFILE")
    bedrock_issues = []
    if not (bedrock_api_key or bedrock_iam):
        bedrock_issues.append("Neither Bedrock API-key authentication nor an AWS credential/profile configuration is present.")
    bedrock_issues.append("Model access is not verified until an explicitly authorized provider connectivity check or inference request.")
    code_model = gateway.get_model_for_task("code")
    return {
        "aws-transform": {
            "status": "CONFIGURED" if transform_execution and transform_host_sdk_ready() else "NOT_CONFIGURED",
            "cliAvailable": bool(executable), "executionArgumentsConfigured": transform_execution,
            "profileConfigured": _configured("AWS_TRANSFORM_PROFILE") or _configured("AWS_PROFILE"),
            "regionConfigured": _configured("AWS_REGION"), "verifiedDefinitions": [TRANSFORM_DOTNET_DEFINITION] if transform_execution else [],
            "supportedTaskCategories": [], "issues": transform_issues,
            "verification": "local-configuration-only",
        },
        "amazon-bedrock": {
            "status": "CONFIGURED" if (bedrock_api_key or bedrock_iam) else "NOT_CONFIGURED",
            "apiKeyConfigured": bedrock_api_key, "iamOrProfileConfigured": bedrock_iam,
            "region": gateway.region, "codeModelId": code_model,
            "requestFormat": "nova-messages-v1" if "nova" in code_model.lower() else "anthropic-messages",
            "structuredOutputContract": "JSON object with a files mapping rooted at backend, frontend, data, docs, or tests.",
            "maxPromptSourceCharacters": 48000, "maxGenerationTokens": 2000,
            "modelAccessVerified": False, "issues": bedrock_issues,
            "verification": "local-configuration-only",
        },
    }


def allocate_provider(workstream: str, target: dict, template_compatible: bool,
                      readiness: dict[str, dict[str, Any]] | None = None) -> tuple[str, str, dict[str, Any], bool, str | None]:
    """Allocate one task once, based on verified—not assumed—provider capability."""
    snapshot = readiness or provider_readiness()
    transform = snapshot["aws-transform"]
    bedrock = snapshot["amazon-bedrock"]
    transform_target = is_dotnet8_target(target)
    transform_capable = (transform_target and template_compatible and
                         workstream in PROVIDER_CAPABILITIES["aws-transform"]["workstreams"] and
                         TRANSFORM_DOTNET_DEFINITION in transform.get("verifiedDefinitions", []))
    if transform_capable:
        return "aws-transform", "Transform-first: verified installed definition supports this task.", {"provider": "aws-transform", "verified": True, "definition": "AWS/dotnet-modernization"}, True, "amazon-bedrock"
    if workstream in {"database", "integration", "testing", "build"}:
        return "manual-engineering-review", "No verified automated provider implementation supports this workstream.", {"provider": "manual-engineering-review", "verified": True, "reason": "manual-review-required"}, False, None
    if bedrock.get("status") == "CONFIGURED" and workstream in PROVIDER_CAPABILITIES["amazon-bedrock"]["workstreams"]:
        reason = "AWS Transform is not verified for this task; routed to configured Bedrock fallback."
        return "amazon-bedrock", reason, {"provider": "amazon-bedrock", "verified": False, "reason": "configuration-present-model-access-unverified", "transformReason": "no verified compatible Transform definition"}, False, None
    return "manual-engineering-review", "No verified or configured automated provider can own this task.", {"provider": "manual-engineering-review", "verified": True, "reason": "provider-unavailable"}, False, None


def is_dotnet8_target(target: dict[str, Any]) -> bool:
    """Accept normalized and display-form .NET 8 target values."""
    language = str(target.get("language", "")).lower().replace(" ", "")
    framework = str(target.get("frameworkVersion", "")).lower().replace(" ", "")
    return language in {"c#", "csharp", "c-sharp", "c#(.net8)", "c#(.net8.0)"} and framework in {"8", "8.0", "net8.0", ".net8", ".net8.0"}


def recommend_provider(workstream: str, target: dict, template_compatible: bool) -> tuple[str, str]:
    """Return a non-executing recommendation from declared local capability metadata."""
    provider, reason, _, _, _ = allocate_provider(workstream, target, template_compatible)
    return provider, reason


@dataclass(frozen=True)
class ProviderPlan:
    provider: str
    supported: bool
    message: str
    tasks: list[dict[str, Any]]


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    ok: bool
    output: str | None
    message: str


class TransformationProvider(ABC):
    """Future-only boundary. Implementations must not be invoked by Phase 2.1."""
    provider_id: str

    @abstractmethod
    def plan(self, package: dict[str, Any]) -> ProviderPlan: ...


class AwsTransformProvider(TransformationProvider):
    provider_id = "aws-transform"
    def plan(self, package: dict[str, Any]) -> ProviderPlan:
        return ProviderPlan(self.provider_id, self.cli_available(), "AWS Transform custom CLI is required for capability discovery and approved execution." if self.cli_available() else "AWS Transform custom CLI (atx) is unavailable.", [])
    def cli_available(self) -> bool:
        return aws_transform_executable() is not None
    def list_definitions(self, timeout: int = 20) -> ProviderResult:
        if not self.cli_available(): return ProviderResult(self.provider_id, False, None, "AWS Transform custom CLI (atx) is unavailable.")
        command = [aws_transform_executable(), "custom", "def", "list"]
        environment = dict(os.environ)
        # Transform is deliberately isolated from a possibly unrelated default
        # AWS profile.  An explicit Transform profile wins; otherwise retain an
        # explicitly configured AWS profile before using the local demo profile.
        environment["AWS_PROFILE"] = (os.getenv("AWS_TRANSFORM_PROFILE")
                                      or os.getenv("AWS_PROFILE")
                                      or "modernization")
        try: result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False, env=environment)
        except (OSError, subprocess.TimeoutExpired): return ProviderResult(self.provider_id, False, None, "AWS Transform capability discovery failed or timed out.")
        return ProviderResult(self.provider_id, result.returncode == 0, result.stdout if result.returncode == 0 else None, "AWS Transform definitions listed." if result.returncode == 0 else "AWS Transform capability discovery was rejected; verify CLI authentication and permissions.")

    def execute(self, definition: str, working_directory: str, output_directory: str,
                timeout: int = TRANSFORM_TOTAL_TIMEOUT_SECONDS,
                on_progress: Callable[[str], None] | None = None) -> ProviderResult:
        """Execute Transform with bounded, observable CLI progress."""
        if not aws_transform_execution_configured():
            return ProviderResult(self.provider_id, False, None, "AWS Transform execution arguments are not configured.")
        if not transform_host_sdk_ready():
            return ProviderResult(self.provider_id, False, None, "AWS Transform preflight failed: local .NET SDK 10 or later is required by the AWS Transform worker.")
        try: args = json.loads(os.getenv("AWS_TRANSFORM_EXEC_ARGUMENTS", ""))
        except json.JSONDecodeError: args = DEFAULT_TRANSFORM_EXECUTION_ARGUMENTS
        if not args: args = DEFAULT_TRANSFORM_EXECUTION_ARGUMENTS
        values = {"definition": definition, "working_directory": _cli_path(working_directory),
                  "output_directory": _cli_path(output_directory)}
        command = [aws_transform_executable(), *[arg.format(**values) for arg in args]]
        environment = dict(os.environ)
        environment["AWS_PROFILE"] = (os.getenv("AWS_TRANSFORM_PROFILE")
                                      or os.getenv("AWS_PROFILE")
                                      or "modernization")
        try:
            process = subprocess.Popen(command, cwd=_cli_path(working_directory), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=environment)
        except OSError:
            return ProviderResult(self.provider_id, False, None, "AWS Transform process could not start.")
        lines: list[str] = []
        updates: queue.Queue[str | None] = queue.Queue()
        def read_output() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                updates.put(line)
            updates.put(None)
        threading.Thread(target=read_output, daemon=True).start()
        started = last_progress = time.monotonic()
        known_events: set[str] = set()
        next_conversation_probe = started
        while process.poll() is None:
            try:
                line = updates.get(timeout=1)
            except queue.Empty:
                line = ""
            if line:
                safe_line = _safe_cli_diagnostic(line)
                lines.append(safe_line)
                last_progress = time.monotonic()
                if on_progress and safe_line:
                    on_progress(safe_line)
            if time.monotonic() >= next_conversation_probe:
                for event in _conversation_events(working_directory):
                    if event not in known_events:
                        known_events.add(event)
                        last_progress = time.monotonic()
                        if on_progress:
                            on_progress(event)
                next_conversation_probe = time.monotonic() + 10
            elapsed = time.monotonic() - started
            idle = time.monotonic() - last_progress
            if elapsed > timeout or idle > TRANSFORM_NO_PROGRESS_TIMEOUT_SECONDS:
                _stop_process_tree(process)
                reason = (f"AWS Transform stopped after {int(idle)} seconds without CLI progress."
                          if idle > TRANSFORM_NO_PROGRESS_TIMEOUT_SECONDS else
                          f"AWS Transform stopped after reaching its {timeout}-second execution limit.")
                return ProviderResult(self.provider_id, False, None, reason)
        while not updates.empty():
            line = updates.get()
            if line:
                safe_line = _safe_cli_diagnostic(line)
                lines.append(safe_line)
                if on_progress and safe_line:
                    on_progress(safe_line)
        output = "\n".join(lines)
        if process.returncode == 0:
            return ProviderResult(self.provider_id, True, output[-8000:], "AWS Transform execution completed.")
        diagnostic = _safe_cli_diagnostic(output or "AWS Transform returned a non-zero exit code.")
        return ProviderResult(self.provider_id, False, None,
                              "AWS Transform execution failed: " + diagnostic)


class BedrockProvider(TransformationProvider):
    provider_id = "amazon-bedrock"
    def __init__(self, gateway=None): self._gateway = gateway
    def plan(self, package: dict[str, Any]) -> ProviderPlan:
        return ProviderPlan(self.provider_id, True, "Uses the existing LLMGateway; runtime credentials and model access are checked at invocation.", [])
    def invoke(self, task_type: str, system_prompt: str, user_prompt: str, *, max_tokens: int = 2000) -> ProviderResult:
        if task_type not in {"fast", "reasoning", "code", "vision"}: return ProviderResult(self.provider_id, False, None, "Unsupported Bedrock task profile.")
        try:
            if self._gateway is None:
                from ..llm_gateway import LLMGateway
                self._gateway = LLMGateway()
            output = self._gateway.invoke(system_prompt, user_prompt, task_type=task_type,
                                          provider="bedrock", max_tokens=max_tokens)
        except Exception: return ProviderResult(self.provider_id, False, None, "Bedrock provider invocation failed without exposing provider details.")
        return ProviderResult(self.provider_id, bool(output), output, "Bedrock response received." if output else "Bedrock returned no usable response.")


class CustomTransformationProvider(TransformationProvider):
    provider_id = "custom"
    def plan(self, package: dict[str, Any]) -> ProviderPlan:
        return ProviderPlan(self.provider_id, False, "No custom transformation provider is configured.", [])
