"""Deterministic target scaffolds written before any provider-generated code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import EvidenceReference, GeneratedArtifact


def _write(root: Path, relative: str, content: str) -> GeneratedArtifact:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return GeneratedArtifact(artifactId=hashlib.sha256(("scaffold:" + relative).encode()).hexdigest()[:24],
        path="output/" + relative, artifactType="target-scaffold", sourceTaskId="target-scaffold",
        sourceReferences=[], sha256=hashlib.sha256(content.encode()).hexdigest(), validationStatus="unverified")


def create(workspace: Path, target: dict, plan=None) -> list[GeneratedArtifact]:
    """Create self-contained .NET 8 and React/Vite foundations, idempotently."""
    files = {
        "backend/Modernized.Api/Modernized.Api.csproj": '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework><Nullable>enable</Nullable><ImplicitUsings>enable</ImplicitUsings></PropertyGroup>
</Project>\n''',
        "backend/Modernized.Api/Program.cs": '''var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
var app = builder.Build();
app.UseSwagger(); app.UseSwaggerUI();
app.MapControllers();
app.Run();
''',
        "backend/Modernized.Api/Controllers/HealthController.cs": '''using Microsoft.AspNetCore.Mvc;
namespace Modernized.Api.Controllers;
[ApiController, Route("api/health")]
public sealed class HealthController : ControllerBase { [HttpGet] public object Get() => new { status = "ok" }; }
''',
        "backend/Modernized.Api/appsettings.json": json.dumps({"ConnectionStrings": {"DefaultConnection": "__CONFIGURE_DATABASE_CONNECTION__"}}, indent=2) + "\n",
        "frontend/package.json": json.dumps({"name":"modernized-frontend","private":True,"version":"0.1.0","type":"module","scripts":{"build":"tsc -b && vite build"},"dependencies":{"react":"latest","react-dom":"latest"},"devDependencies":{"vite":"latest","typescript":"latest","@types/react":"latest","@types/react-dom":"latest"}}, indent=2) + "\n",
        "frontend/index.html": '<div id="root"></div><script type="module" src="/src/main.tsx"></script>\n',
        "frontend/tsconfig.json": json.dumps({"compilerOptions":{"target":"ES2020","jsx":"react-jsx","module":"ESNext","moduleResolution":"Bundler","strict":True,"skipLibCheck":True},"include":["src"]}, indent=2) + "\n",
        "frontend/src/main.tsx": "import { createRoot } from 'react-dom/client';\nimport App from './App';\ncreateRoot(document.getElementById('root')!).render(<App />);\n",
        "frontend/src/App.tsx": "export default function App() { return <main><h1>Modernized application</h1></main>; }\n",
    }
    if plan is not None:
        files["docs/generation-coverage.json"] = json.dumps({"status": "planned", "tasks": [
            {"taskId": task.taskId, "category": task.category,
             "sourceArtifactIds": [ref.artifactId for ref in task.sourceArtifacts],
             "requiredOutputRoot": task.expectedOutputFolders[0] if task.expectedOutputFolders else "docs"}
            for task in plan.tasks
        ]}, indent=2) + "\n"
    artifacts = []
    for relative, content in files.items():
        if not (workspace / relative).exists():
            artifacts.append(_write(workspace, relative, content))
    return artifacts
