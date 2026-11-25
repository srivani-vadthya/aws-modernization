"""Explicit, isolated validation of generated output; never runs during provider generation."""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .models import ExecutionRecord, ValidationResult


def _run(stage: str, command: list[str], cwd: Path) -> ValidationResult:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=900, check=False)
        message = (result.stdout if result.returncode == 0 else result.stderr or result.stdout)[-1200:].strip()
        return ValidationResult(stage=stage, status="passed" if result.returncode == 0 else "failed", message=message or f"Exit code {result.returncode}", at=datetime.now(timezone.utc))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ValidationResult(stage=stage, status="failed", message=f"Validation command could not complete: {type(exc).__name__}", at=datetime.now(timezone.utc))


def validate(record: ExecutionRecord, output: Path) -> ExecutionRecord:
    results: list[ValidationResult] = []
    frontend = output / "frontend"
    if (frontend / "package.json").is_file() and shutil.which("npm"):
        install = _run("frontend-build", ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"], frontend)
        if install.status == "passed":
            results.append(_run("frontend-build", ["npm", "run", "build"], frontend))
        else:
            results.append(install)
    else:
        results.append(ValidationResult(stage="frontend-build", status="not-applicable", message="No generated frontend package or npm executable is available.", at=datetime.now(timezone.utc)))
    project = next(iter(output.glob("backend/**/*.csproj")), None)
    if project and shutil.which("dotnet"):
        results.append(_run("backend-build", ["dotnet", "build", str(project), "--nologo"], project.parent))
        results.append(_run("backend-tests", ["dotnet", "test", str(project), "--no-build", "--nologo"], project.parent))
    else:
        results.extend([ValidationResult(stage="backend-build", status="not-applicable", message="No generated .NET project or dotnet executable is available.", at=datetime.now(timezone.utc)), ValidationResult(stage="backend-tests", status="not-applicable", message="No generated .NET test project is available.", at=datetime.now(timezone.utc))])
    results.extend([ValidationResult(stage="data-validation", status="not-run", message="A target-specific migration validator is not yet configured.", at=datetime.now(timezone.utc)), ValidationResult(stage="runtime-startup", status="not-run", message="Runtime startup requires an explicit target-specific launch profile.", at=datetime.now(timezone.utc)), ValidationResult(stage="behavior-parity", status="not-run", message="No source-bound legacy behavior baseline is available.", at=datetime.now(timezone.utc))])
    return record.model_copy(update={"validation": results, "updatedAt": datetime.now(timezone.utc)})
