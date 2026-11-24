"""GitHub code-push helpers and incremental InsuranceClaims Module 2 publishing.

The original demo project endpoints remain supported through ``project_name``,
``dummy_files``, ``listing``, and ``push``. ``push_module2`` reads Module 1
source from its branch and publishes a separate InsuranceClaims.Api project
on a new child branch.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API = "https://api.github.com"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,98}$")
MODULE2_ROOT = "InsuranceClaims.Api"
LANG = {
    ".cs": "csharp",
    ".csproj": "xml",
    ".json": "json",
    ".md": "markdown",
    ".gitignore": "text",
}


class PushError(Exception):
    """Raised when validation or a GitHub operation fails."""


def _pascal(text: str, fallback: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    out = "".join(word[:1].upper() + word[1:] for word in words)
    if not out or not out[0].isalpha():
        out = fallback
    return out


def project_name(eng: dict) -> str:
    scope = eng.get("scope") or {}
    return _pascal(scope.get("name") or scope.get("capabilityId") or "", "Policy")


def _entity(project: str) -> str:
    return project[:-1] if project.endswith("s") and len(project) > 3 else project


def dummy_files(eng: dict) -> dict[str, str]:
    project = project_name(eng)
    entity = _entity(project)
    namespace = f"{project}.Api"
    files: dict[str, str] = {}
    files[f"{namespace}.csproj"] = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Swashbuckle.AspNetCore" Version="6.5.0" />
  </ItemGroup>
</Project>
"""
    files["Program.cs"] = f"""using {namespace}.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddSingleton<I{entity}Service, {entity}Service>();

var app = builder.Build();

app.UseSwagger();
app.UseSwaggerUI();
app.MapControllers();
app.Run();
"""
    files[f"Models/{entity}.cs"] = f"""namespace {namespace}.Models;

public class {entity}
{{
    public int Id {{ get; set; }}
    public string Title {{ get; set; }} = string.Empty;
    public string Status {{ get; set; }} = "Open";
    public decimal Amount {{ get; set; }}
    public DateTime CreatedAt {{ get; set; }} = DateTime.UtcNow;
}}
"""
    files[f"Services/I{entity}Service.cs"] = f"""using {namespace}.Models;

namespace {namespace}.Services;

public interface I{entity}Service
{{
    IReadOnlyList<{entity}> GetAll();
    {entity}? GetById(int id);
    {entity} Create({entity} item);
    bool Close(int id);
}}
"""
    files[f"Services/{entity}Service.cs"] = f"""using {namespace}.Models;

namespace {namespace}.Services;

public class {entity}Service : I{entity}Service
{{
    private readonly List<{entity}> _items = new();
    private int _nextId = 1;

    public IReadOnlyList<{entity}> GetAll() => _items;

    public {entity}? GetById(int id) => _items.FirstOrDefault(item => item.Id == id);

    public {entity} Create({entity} item)
    {{
        if (string.IsNullOrWhiteSpace(item.Title))
            throw new ArgumentException("Title is required.");
        if (item.Amount < 0)
            throw new ArgumentException("Amount cannot be negative.");

        item.Id = _nextId++;
        item.Status = "Open";
        item.CreatedAt = DateTime.UtcNow;
        _items.Add(item);
        return item;
    }}

    public bool Close(int id)
    {{
        var item = GetById(id);
        if (item is null || item.Status == "Closed") return false;
        item.Status = "Closed";
        return true;
    }}
}}
"""
    files[f"Controllers/{project}Controller.cs"] = f"""using Microsoft.AspNetCore.Mvc;
using {namespace}.Models;
using {namespace}.Services;

namespace {namespace}.Controllers;

[ApiController]
[Route("api/[controller]")]
public class {project}Controller : ControllerBase
{{
    private readonly I{entity}Service _service;

    public {project}Controller(I{entity}Service service) => _service = service;

    [HttpGet]
    public ActionResult<IEnumerable<{entity}>> GetAll() => Ok(_service.GetAll());

    [HttpGet("{{id:int}}")]
    public ActionResult<{entity}> Get(int id)
    {{
        var item = _service.GetById(id);
        return item is null ? NotFound() : Ok(item);
    }}

    [HttpPost]
    public ActionResult<{entity}> Create({entity} item)
    {{
        try
        {{
            var created = _service.Create(item);
            return CreatedAtAction(nameof(Get), new {{ id = created.Id }}, created);
        }}
        catch (ArgumentException exception)
        {{
            return BadRequest(exception.Message);
        }}
    }}

    [HttpPost("{{id:int}}/close")]
    public IActionResult Close(int id) => _service.Close(id) ? NoContent() : NotFound();
}}
"""
    files["appsettings.json"] = """{
  "Logging": { "LogLevel": { "Default": "Information" } },
  "AllowedHosts": "*"
}
"""
    files[".gitignore"] = "bin/\nobj/\n.vs/\n*.user\n"
    files["README.md"] = f"""# {project} API (modernized)

Demo .NET 8 Web API generated by Nexus Modernize.

```
dotnet run
```

Swagger UI is served at `/swagger`.
"""
    return files


def listing(eng: dict) -> list[dict[str, str]]:
    return [
        {
            "path": path,
            "language": LANG.get("." + path.rsplit(".", 1)[-1] if "." in path else "", "text"),
            "content": content,
        }
        for path, content in dummy_files(eng).items()
    ]


def _call(
    method: str,
    path: str,
    token: str,
    body: Any = None,
) -> tuple[int, Any]:
    """Call the GitHub REST API and return (HTTP status, decoded response)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nexus-modernize-module-publisher",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"message": raw[:300]}
    except urllib.error.URLError as exc:
        raise PushError(f"Cannot reach GitHub: {exc.reason}") from exc


def _message(data: Any) -> str:
    if isinstance(data, dict):
        return str(data.get("message") or data)[:300]
    return str(data)[:300]


def _validate_branch_name(name: str) -> None:
    if (
        not name
        or not BRANCH_RE.fullmatch(name)
        or ".." in name
        or name.endswith("/")
        or name.endswith(".lock")
        or "//" in name
        or "@{" in name
    ):
        raise PushError(f"Invalid Git branch name: {name!r}")


def _github_path(path: str) -> str:
    """Encode a Git ref path while preserving slash separators."""
    return urllib.parse.quote(path, safe="/")


def _get_branch_commit(
    repo: str,
    branch: str,
    token: str,
) -> tuple[str, str]:
    """Return (commit SHA, tree SHA) for a branch."""
    status, ref = _call(
        "GET",
        f"/repos/{repo}/git/ref/heads/{_github_path(branch)}",
        token,
    )
    if status == 404:
        raise PushError(f"Branch '{branch}' was not found in {repo}.")
    if status != 200:
        raise PushError(
            f"Could not read branch '{branch}' ({status}): {_message(ref)}"
        )

    commit_sha = ref["object"]["sha"]
    status, commit = _call(
        "GET",
        f"/repos/{repo}/git/commits/{commit_sha}",
        token,
    )
    if status != 200:
        raise PushError(
            f"Could not read commit for '{branch}' ({status}): {_message(commit)}"
        )

    return commit_sha, commit["tree"]["sha"]


def _read_branch_tree(
    repo: str,
    tree_sha: str,
    token: str,
) -> dict[str, dict[str, Any]]:
    """Return all blob entries keyed by path."""
    status, response = _call(
        "GET",
        f"/repos/{repo}/git/trees/{tree_sha}?recursive=1",
        token,
    )
    if status != 200:
        raise PushError(
            f"Could not read repository tree ({status}): {_message(response)}"
        )
    if response.get("truncated"):
        raise PushError(
            "GitHub returned a truncated repository tree. "
            "Cannot safely preserve all existing files."
        )

    return {
        item["path"]: item
        for item in response.get("tree", [])
        if item.get("type") == "blob"
    }


def _read_blob_text(repo: str, blob_sha: str, token: str) -> str:
    """Read and decode a GitHub blob as UTF-8 text."""
    status, blob = _call(
        "GET",
        f"/repos/{repo}/git/blobs/{blob_sha}",
        token,
    )
    if status != 200:
        raise PushError(
            f"Could not read an existing source file ({status}): {_message(blob)}"
        )

    if blob.get("encoding") != "base64":
        raise PushError("GitHub returned an unsupported blob encoding.")

    try:
        return base64.b64decode(blob["content"]).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise PushError("Could not decode an existing source file.") from exc


def load_module1_context(
    repo: str,
    parent_branch: str,
    tree: dict[str, dict[str, Any]],
    token: str,
) -> dict[str, str]:
    """
    Retrieve Module 1 source files from the selected parent branch.

    This verifies that Module 2 is based on the expected InsuranceProvider
    project and makes the existing source available to the generation step.
    """
    expected = [
        "InsuranceProvider.Api.csproj",
        "Program.cs",
        "Models/InsuranceProvider.cs",
        "Services/IInsuranceProviderService.cs",
        "Services/InsuranceProviderService.cs",
        "Controllers/InsuranceProviderController.cs",
    ]

    context: dict[str, str] = {}
    missing: list[str] = []

    for path in expected:
        entry = tree.get(path)
        if not entry:
            missing.append(path)
            continue
        context[path] = _read_blob_text(repo, entry["sha"], token)

    if missing:
        raise PushError(
            f"Branch '{parent_branch}' does not contain the expected Module 1 "
            f"InsuranceProvider files. Missing: {', '.join(missing)}"
        )

    return context


def generate_module2_files(module1_context: dict[str, str]) -> dict[str, str]:
    """
    Generate the sample InsuranceClaims.Api project.

    Module 1 source is supplied to this function as generation context.
    The demo generator validates that context is present, then creates Module 2
    in its own folder so it cannot overwrite Module 1's root-level files.
    """
    required_context = {
        "InsuranceProvider.Api.csproj",
        "Program.cs",
        "Models/InsuranceProvider.cs",
    }
    if not required_context.issubset(module1_context):
        raise PushError(
            "Module 1 context is incomplete. Module 2 generation was stopped."
        )

    root = MODULE2_ROOT
    files: dict[str, str] = {}

    files[f"{root}/InsuranceClaims.Api.csproj"] = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Swashbuckle.AspNetCore" Version="6.5.0" />
  </ItemGroup>
</Project>
"""

    files[f"{root}/Program.cs"] = """using InsuranceClaims.Api.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddSingleton<IInsuranceClaimService, InsuranceClaimService>();

var app = builder.Build();

app.UseSwagger();
app.UseSwaggerUI();
app.MapControllers();
app.Run();
"""

    files[f"{root}/appsettings.json"] = """{
  "Logging": {
    "LogLevel": {
      "Default": "Information",
      "Microsoft.AspNetCore": "Warning"
    }
  },
  "AllowedHosts": "*"
}
"""

    files[f"{root}/.gitignore"] = """bin/
obj/
.vs/
*.user
"""

    files[f"{root}/Models/InsuranceClaim.cs"] = """namespace InsuranceClaims.Api.Models;

public class InsuranceClaim
{
    public int Id { get; set; }
    public string ClaimNumber { get; set; } = string.Empty;
    public string PolicyNumber { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
    public decimal ClaimAmount { get; set; }
    public string Status { get; set; } = "Submitted";
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
"""

    files[f"{root}/Services/IInsuranceClaimService.cs"] = """using InsuranceClaims.Api.Models;

namespace InsuranceClaims.Api.Services;

public interface IInsuranceClaimService
{
    IReadOnlyList<InsuranceClaim> GetAll();
    InsuranceClaim? GetById(int id);
    InsuranceClaim Create(InsuranceClaim claim);
    bool UpdateStatus(int id, string status);
}
"""

    files[f"{root}/Services/InsuranceClaimService.cs"] = """using InsuranceClaims.Api.Models;

namespace InsuranceClaims.Api.Services;

public class InsuranceClaimService : IInsuranceClaimService
{
    private readonly List<InsuranceClaim> _claims = new();
    private int _nextId = 1;

    public IReadOnlyList<InsuranceClaim> GetAll() => _claims;

    public InsuranceClaim? GetById(int id) =>
        _claims.FirstOrDefault(claim => claim.Id == id);

    public InsuranceClaim Create(InsuranceClaim claim)
    {
        if (string.IsNullOrWhiteSpace(claim.PolicyNumber))
            throw new ArgumentException("Policy number is required.");

        if (string.IsNullOrWhiteSpace(claim.Description))
            throw new ArgumentException("Claim description is required.");

        if (claim.ClaimAmount <= 0)
            throw new ArgumentException("Claim amount must be greater than zero.");

        claim.Id = _nextId++;
        claim.ClaimNumber = $"CLM-{DateTime.UtcNow:yyyyMMdd}-{claim.Id:D5}";
        claim.Status = "Submitted";
        claim.CreatedAt = DateTime.UtcNow;

        _claims.Add(claim);
        return claim;
    }

    public bool UpdateStatus(int id, string status)
    {
        var claim = GetById(id);
        if (claim is null)
            return false;

        var allowedStatuses = new[]
        {
            "Submitted",
            "UnderReview",
            "Approved",
            "Rejected",
            "Settled"
        };

        if (!allowedStatuses.Contains(status, StringComparer.OrdinalIgnoreCase))
            throw new ArgumentException("Unsupported claim status.");

        claim.Status = allowedStatuses.First(
            value => value.Equals(status, StringComparison.OrdinalIgnoreCase));

        return true;
    }
}
"""

    files[f"{root}/Controllers/InsuranceClaimsController.cs"] = """using InsuranceClaims.Api.Models;
using InsuranceClaims.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace InsuranceClaims.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class InsuranceClaimsController : ControllerBase
{
    private readonly IInsuranceClaimService _service;

    public InsuranceClaimsController(IInsuranceClaimService service)
    {
        _service = service;
    }

    [HttpGet]
    public ActionResult<IEnumerable<InsuranceClaim>> GetAll()
    {
        return Ok(_service.GetAll());
    }

    [HttpGet("{id:int}")]
    public ActionResult<InsuranceClaim> GetById(int id)
    {
        var claim = _service.GetById(id);
        return claim is null ? NotFound() : Ok(claim);
    }

    [HttpPost]
    public ActionResult<InsuranceClaim> Create(InsuranceClaim claim)
    {
        try
        {
            var created = _service.Create(claim);
            return CreatedAtAction(
                nameof(GetById),
                new { id = created.Id },
                created);
        }
        catch (ArgumentException exception)
        {
            return BadRequest(new { error = exception.Message });
        }
    }

    [HttpPatch("{id:int}/status")]
    public IActionResult UpdateStatus(int id, [FromBody] UpdateClaimStatusRequest request)
    {
        try
        {
            return _service.UpdateStatus(id, request.Status)
                ? NoContent()
                : NotFound();
        }
        catch (ArgumentException exception)
        {
            return BadRequest(new { error = exception.Message });
        }
    }
}

public class UpdateClaimStatusRequest
{
    public string Status { get; set; } = string.Empty;
}
"""

    files[f"{root}/README.md"] = """# InsuranceClaims API

Demo .NET 8 Web API for the Insurance Claims module.

## Run

```bash
cd InsuranceClaims.Api
dotnet run
```

Swagger UI is served at `/swagger`.

## Endpoints

- `GET /api/InsuranceClaims` - list claims
- `GET /api/InsuranceClaims/{id}` - get a claim
- `POST /api/InsuranceClaims` - create a claim
- `PATCH /api/InsuranceClaims/{id}/status` - update claim status

## Note

This is sample in-memory demo code. Data is not persisted between application restarts.
It is a separate project from the existing InsuranceProvider.Api module.
"""

    return files


def push_module2(
    repo: str,
    parent_branch: str,
    new_branch: str,
    token: str | None = None,
    message: str = "Add InsuranceClaims API module",
    apply: bool = False,
) -> dict[str, Any]:
    """
    Publish Module 2 as a new branch based on the latest Module 1 branch.

    apply=False performs validation and returns a plan without creating a branch.
    apply=True creates blobs/tree/commit and a new branch reference.
    """
    repo = (repo or "").strip()
    parent_branch = (parent_branch or "").strip()
    new_branch = (new_branch or "").strip()
    token = (token or "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
    message = (message or "").strip() or "Add InsuranceClaims API module"

    if not REPO_RE.fullmatch(repo):
        raise PushError("Repository must use the OWNER/REPOSITORY format.")
    if not token:
        raise PushError("Provide a GitHub PAT or set the GITHUB_TOKEN environment variable.")

    _validate_branch_name(parent_branch)
    _validate_branch_name(new_branch)

    if parent_branch == new_branch:
        raise PushError("The new branch must be different from the parent branch.")

    result: dict[str, Any] = {
        "repo": repo,
        "parentBranch": parent_branch,
        "newBranch": new_branch,
        "module": MODULE2_ROOT,
        "dryRun": not apply,
    }

    try:
        # 1. Confirm repository access and discover the actual default branch.
        status, repository = _call("GET", f"/repos/{repo}", token)
        if status == 401:
            raise PushError("GitHub rejected the token. Check its validity and expiry.")
        if status == 404:
            raise PushError("Repository not found, or the token cannot access it.")
        if status != 200:
            raise PushError(
                f"Could not inspect repository ({status}): {_message(repository)}"
            )

        permissions = repository.get("permissions") or {}
        if permissions.get("push") is False:
            raise PushError("The token/account has no push permission for this repository.")

        default_branch = repository.get("default_branch") or "main"
        result["defaultBranch"] = default_branch

        # 2. Fail closed if anyone accidentally selects the default branch as target.
        if new_branch == default_branch:
            raise PushError(
                "Safety stop: the target branch is the repository's default branch."
            )

        # 3. A new branch must not already exist.
        status, existing_ref = _call(
            "GET",
            f"/repos/{repo}/git/ref/heads/{_github_path(new_branch)}",
            token,
        )
        if status == 200:
            raise PushError(
                f"Target branch '{new_branch}' already exists. "
                "Choose a new unique branch name; nothing was changed."
            )
        if status != 404:
            raise PushError(
                f"Could not check target branch ({status}): {_message(existing_ref)}"
            )

        # 4. Read the latest parent branch commit and full tree.
        parent_commit_sha, parent_tree_sha = _get_branch_commit(
            repo, parent_branch, token
        )
        tree = _read_branch_tree(repo, parent_tree_sha, token)

        # 5. Retrieve Module 1 source BEFORE generating Module 2.
        module1_context = load_module1_context(
            repo, parent_branch, tree, token
        )
        result["contextBranch"] = parent_branch
        result["contextFilesRead"] = sorted(module1_context.keys())
        result["parentCommitSha"] = parent_commit_sha

        # 6. Generate Module 2 with Module 1 source supplied as context.
        generated_files = generate_module2_files(module1_context)

        # 7. Never overwrite an existing path in the parent branch.
        collisions = sorted(set(generated_files).intersection(tree))
        if collisions:
            raise PushError(
                "Module 2 would overwrite existing paths in the parent branch: "
                + ", ".join(collisions)
                + ". Resolve these path collisions before publishing."
            )

        result["generatedFiles"] = sorted(generated_files)
        result["fileCount"] = len(generated_files)
        result["inheritedFileCount"] = len(tree)
        result["totalExpectedFileCount"] = len(tree) + len(generated_files)

        if not apply:
            result["previewFiles"] = [
                {
                    "path": path,
                    "language": LANG.get(os.path.splitext(path)[1].lower(), "text"),
                    "content": content,
                }
                for path, content in sorted(generated_files.items())
            ]
            result["message"] = (
                "Dry run only. Module 1 was read and Module 2 files were generated. "
                "No GitHub branch or commit was created."
            )
            return result

        # 8. Upload each generated file as a Git blob.
        new_tree_entries: list[dict[str, str]] = []
        for path, content in sorted(generated_files.items()):
            status, blob = _call(
                "POST",
                f"/repos/{repo}/git/blobs",
                token,
                {
                    "content": content,
                    "encoding": "utf-8",
                },
            )
            if status != 201:
                raise PushError(
                    f"Could not upload '{path}' ({status}): {_message(blob)}"
                )

            new_tree_entries.append(
                {
                    "path": path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob["sha"],
                }
            )

        # 9. Create a tree based on the complete Module 1 tree.
        status, new_tree = _call(
            "POST",
            f"/repos/{repo}/git/trees",
            token,
            {
                "base_tree": parent_tree_sha,
                "tree": new_tree_entries,
            },
        )
        if status != 201:
            raise PushError(
                f"Could not create Module 2 tree ({status}): {_message(new_tree)}"
            )

        # 10. Commit Module 2 with Module 1's commit as its parent.
        status, commit = _call(
            "POST",
            f"/repos/{repo}/git/commits",
            token,
            {
                "message": message,
                "tree": new_tree["sha"],
                "parents": [parent_commit_sha],
            },
        )
        if status != 201:
            raise PushError(
                f"Could not create Module 2 commit ({status}): {_message(commit)}"
            )

        # 11. Create a NEW branch pointing at the new commit.
        status, created_ref = _call(
            "POST",
            f"/repos/{repo}/git/refs",
            token,
            {
                "ref": f"refs/heads/{new_branch}",
                "sha": commit["sha"],
            },
        )
        if status != 201:
            raise PushError(
                f"Could not create branch '{new_branch}' ({status}): "
                f"{_message(created_ref)}"
            )

        result.update(
            {
                "created": True,
                "commitSha": commit["sha"],
                "branchUrl": f"https://github.com/{repo}/tree/{_github_path(new_branch)}",
                "commitUrl": f"https://github.com/{repo}/commit/{commit['sha']}",
                "message": (
                    "Module 2 was pushed to a new branch based on the Module 1 branch. "
                    "All parent-branch files and history are retained."
                ),
            }
        )
        return result

    except PushError as exc:
        # Do not expose the PAT in error messages.
        raise PushError(str(exc).replace(token, "***")) from None


def _msg(data: Any) -> str:
    return str((data or {}).get("message") or data)[:200] if isinstance(data, dict) else str(data)[:200]


def _plan(files: dict[str, str], existing: set[str], overwrite: bool) -> list[dict[str, str]]:
    plan = []
    for path in sorted(files):
        if path not in existing:
            plan.append({"path": path, "action": "new"})
        elif overwrite:
            plan.append({"path": path, "action": "replace"})
        else:
            plan.append({"path": path, "action": "skip"})
    return plan


def push(
    eng: dict,
    repo: str,
    token: str | None,
    branch: str,
    message: str,
    apply: bool,
    base: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Push the existing demo project to a new GitHub branch."""
    repo = (repo or "").strip()
    branch = (branch or "").strip() or "modernized-code"
    base = (base or "").strip()
    token = (token or "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
    message = (message or "").strip() or "Add modernized code"
    if not REPO_RE.fullmatch(repo):
        raise PushError("Repository must look like owner/repo.")
    for name in (branch, base):
        if name and (not BRANCH_RE.fullmatch(name) or ".." in name or name.endswith(("/", ".lock"))):
            raise PushError(f"Branch name '{name}' is not valid.")
    if not token:
        raise PushError("Enter a GitHub token (a personal access token with repo access).")

    files = dummy_files(eng)
    result: dict[str, Any] = {"repo": repo, "branch": branch, "dryRun": not apply, "overwrite": overwrite}
    try:
        status, info = _call("GET", f"/repos/{repo}", token)
        if status == 401:
            raise PushError("GitHub rejected the token (401). Check that it is correct and has not expired.")
        if status == 404:
            raise PushError("Repository not found, or the token has no access to it.")
        if status != 200:
            raise PushError(f"GitHub error ({status}): {_msg(info)}")
        if not (info.get("permissions") or {}).get("push", True):
            raise PushError("The token can read this repository but cannot push to it.")
        default = info.get("default_branch") or "main"
        base_name = base or default
        result["defaultBranch"] = default
        result["baseBranch"] = base_name

        status, _ = _call("GET", f"/repos/{repo}/git/ref/heads/{branch}", token)
        if status == 200:
            raise PushError(f"Branch '{branch}' already exists. Pick a new branch name (nothing is overwritten).")

        status, ref = _call("GET", f"/repos/{repo}/git/ref/heads/{base_name}", token)
        empty = False
        existing: set[str] = set()
        base_commit = tree_sha = ""
        if status in (404, 409) and not base:
            empty = True
        elif status == 404:
            raise PushError(f"Base branch '{base_name}' was not found in {repo}.")
        elif status != 200:
            raise PushError(f"Could not read branch '{base_name}' ({status}): {_msg(ref)}")
        else:
            base_commit = ref["object"]["sha"]
            status, commit = _call("GET", f"/repos/{repo}/git/commits/{base_commit}", token)
            if status != 200:
                raise PushError(f"Could not read the base commit ({status}): {_msg(commit)}")
            tree_sha = commit["tree"]["sha"]
            status, listing_data = _call("GET", f"/repos/{repo}/git/trees/{tree_sha}?recursive=1", token)
            if status != 200:
                raise PushError(f"Could not read the files on '{base_name}' ({status}): {_msg(listing_data)}")
            if listing_data.get("truncated"):
                raise PushError("The base branch has too many files to compare safely. Use a smaller repo.")
            existing = {
                item["path"]
                for item in listing_data.get("tree", [])
                if item.get("type") == "blob"
            }

        plan = _plan(files, existing, overwrite)
        result["plan"] = plan
        result["counts"] = {
            action: sum(1 for item in plan if item["action"] == action)
            for action in ("new", "replace", "skip")
        }
        result["files"] = [item["path"] for item in plan if item["action"] != "skip"]
        result["fileCount"] = len(result["files"])
        if not apply:
            return result
        if not result["files"]:
            raise PushError(
                "Nothing to push: every file already exists on the base branch. "
                "Tick 'Replace existing files' to overwrite them."
            )

        if empty:
            first = "README.md"
            status, data = _call(
                "PUT",
                f"/repos/{repo}/contents/{first}",
                token,
                {
                    "message": "Initial commit",
                    "branch": default,
                    "content": base64.b64encode(files[first].encode("utf-8")).decode("ascii"),
                },
            )
            if status in (403, 404):
                raise PushError(
                    f"GitHub refused the write ({status}). The token can see the repo but cannot write to it. "
                    "Fine-grained token: set this repository's 'Contents' permission to Read and write. "
                    "Classic token: tick the 'repo' scope. If the repo belongs to an organisation, the token may "
                    "also need to be authorised for it (SSO)."
                )
            if status not in (200, 201):
                raise PushError(f"Could not initialise the empty repository ({status}): {_msg(data)}")
            result["initialisedEmptyRepo"] = True
            status, ref = _call("GET", f"/repos/{repo}/git/ref/heads/{default}", token)
            if status != 200:
                raise PushError(f"Could not read branch '{default}' ({status}): {_msg(ref)}")
            base_commit = ref["object"]["sha"]
            status, commit = _call("GET", f"/repos/{repo}/git/commits/{base_commit}", token)
            if status != 200:
                raise PushError(f"Could not read the base commit ({status}): {_msg(commit)}")
            tree_sha = commit["tree"]["sha"]
            plan = _plan(files, {first}, overwrite)
            result["plan"] = plan
            result["files"] = [item["path"] for item in plan if item["action"] != "skip"]
            result["fileCount"] = len(result["files"])

        tree = []
        for path in result["files"]:
            status, blob = _call(
                "POST",
                f"/repos/{repo}/git/blobs",
                token,
                {"content": files[path], "encoding": "utf-8"},
            )
            if status != 201:
                raise PushError(f"Could not upload {path} ({status}): {_msg(blob)}")
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        status, new_tree = _call(
            "POST",
            f"/repos/{repo}/git/trees",
            token,
            {"base_tree": tree_sha, "tree": tree},
        )
        if status != 201:
            raise PushError(f"Could not create the file tree ({status}): {_msg(new_tree)}")
        status, new_commit = _call(
            "POST",
            f"/repos/{repo}/git/commits",
            token,
            {"message": message, "tree": new_tree["sha"], "parents": [base_commit]},
        )
        if status != 201:
            raise PushError(f"Could not create the commit ({status}): {_msg(new_commit)}")
        status, made = _call(
            "POST",
            f"/repos/{repo}/git/refs",
            token,
            {"ref": f"refs/heads/{branch}", "sha": new_commit["sha"]},
        )
        if status != 201:
            raise PushError(f"Could not create the branch ({status}): {_msg(made)}")
        result.update(
            {
                "commitSha": new_commit["sha"],
                "commitUrl": f"https://github.com/{repo}/commit/{new_commit['sha']}",
                "branchUrl": f"https://github.com/{repo}/tree/{branch}",
            }
        )
        return result
    except PushError as exc:
        raise PushError(str(exc).replace(token, "***")) from None


if __name__ == "__main__":
    # Configure these values for your repository before running.
    # First run with APPLY=False to inspect the plan.
    REPOSITORY = "OWNER/REPOSITORY"
    MODULE1_BRANCH = "modernization/module-1"
    MODULE2_BRANCH = "modernization/module-2"
    APPLY = False

    try:
        output = push_module2(
            repo=REPOSITORY,
            parent_branch=MODULE1_BRANCH,
            new_branch=MODULE2_BRANCH,
            apply=APPLY,
        )
        print(json.dumps(output, indent=2))
    except PushError as error:
        print(f"Push failed: {error}")
