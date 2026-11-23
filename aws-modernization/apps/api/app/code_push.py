"""Demo "modernized code" project and a push of it to a GitHub repository.

The code is a small static .NET 8 Web API named after the engagement's scope. It is sample code, not the
output of a real conversion. The push uses the GitHub Git Data API (blobs, tree, commit, ref), so no local
git is needed. It always creates a NEW branch and never overwrites or force-pushes anything.

The token is used for the one request and is never stored or logged; it is scrubbed from error text.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

API = "https://api.github.com"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,98}$")
LANG = {".cs": "csharp", ".csproj": "xml", ".json": "json", ".md": "markdown", ".gitignore": "text"}


class PushError(Exception):
    pass


def _pascal(text: str, fallback: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    out = "".join(w[:1].upper() + w[1:] for w in words)
    if not out or not out[0].isalpha():
        out = fallback
    return out


def project_name(eng: dict) -> str:
    scope = eng.get("scope") or {}
    return _pascal(scope.get("name") or scope.get("capabilityId") or "", "Policy")


def _entity(project: str) -> str:
    return project[:-1] if project.endswith("s") and len(project) > 3 else project


def dummy_files(eng: dict) -> dict[str, str]:
    p = project_name(eng)
    e = _entity(p)
    ns = f"{p}.Api"
    files: dict[str, str] = {}
    files[f"{ns}.csproj"] = f"""<Project Sdk="Microsoft.NET.Sdk.Web">
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
    files["Program.cs"] = f"""using {ns}.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddSingleton<I{e}Service, {e}Service>();

var app = builder.Build();

app.UseSwagger();
app.UseSwaggerUI();
app.MapControllers();
app.Run();
"""
    files[f"Models/{e}.cs"] = f"""namespace {ns}.Models;

public class {e}
{{
    public int Id {{ get; set; }}
    public string Title {{ get; set; }} = string.Empty;
    public string Status {{ get; set; }} = "Open";
    public decimal Amount {{ get; set; }}
    public DateTime CreatedAt {{ get; set; }} = DateTime.UtcNow;
}}
"""
    files[f"Services/I{e}Service.cs"] = f"""using {ns}.Models;

namespace {ns}.Services;

public interface I{e}Service
{{
    IReadOnlyList<{e}> GetAll();
    {e}? GetById(int id);
    {e} Create({e} item);
    bool Close(int id);
}}
"""
    files[f"Services/{e}Service.cs"] = f"""using {ns}.Models;

namespace {ns}.Services;

public class {e}Service : I{e}Service
{{
    private readonly List<{e}> _items = new();
    private int _nextId = 1;

    public IReadOnlyList<{e}> GetAll() => _items;

    public {e}? GetById(int id) => _items.FirstOrDefault(i => i.Id == id);

    public {e} Create({e} item)
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
    files[f"Controllers/{p}Controller.cs"] = f"""using Microsoft.AspNetCore.Mvc;
using {ns}.Models;
using {ns}.Services;

namespace {ns}.Controllers;

[ApiController]
[Route("api/[controller]")]
public class {p}Controller : ControllerBase
{{
    private readonly I{e}Service _service;

    public {p}Controller(I{e}Service service) => _service = service;

    [HttpGet]
    public ActionResult<IEnumerable<{e}>> GetAll() => Ok(_service.GetAll());

    [HttpGet("{{id:int}}")]
    public ActionResult<{e}> Get(int id)
    {{
        var item = _service.GetById(id);
        return item is null ? NotFound() : Ok(item);
    }}

    [HttpPost]
    public ActionResult<{e}> Create({e} item)
    {{
        try
        {{
            var created = _service.Create(item);
            return CreatedAtAction(nameof(Get), new {{ id = created.Id }}, created);
        }}
        catch (ArgumentException ex)
        {{
            return BadRequest(ex.Message);
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
    files["README.md"] = f"""# {p} API (modernized)

Demo .NET 8 Web API generated by Nexus Modernize.

```
dotnet run
```

Swagger UI is served at `/swagger`.
"""
    return files


def listing(eng: dict) -> list[dict[str, str]]:
    out = []
    for path, content in dummy_files(eng).items():
        ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
        out.append({"path": path, "language": LANG.get(ext, "text"), "content": content})
    return out


# --------------------------------------------------------------------------- GitHub


def _call(method: str, path: str, token: str, body: Any = None) -> tuple[int, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "code-push", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed https host)
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"message": raw[:200]}
    except urllib.error.URLError as exc:
        raise PushError(f"Cannot reach GitHub: {exc.reason}") from exc


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


def push(eng: dict, repo: str, token: str | None, branch: str, message: str, apply: bool,
         base: str = "", overwrite: bool = False) -> dict:
    repo = (repo or "").strip()
    branch = (branch or "").strip() or "modernized-code"
    base = (base or "").strip()
    token = (token or "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
    message = (message or "").strip() or "Add modernized code"
    if not REPO_RE.match(repo):
        raise PushError("Repository must look like owner/repo.")
    for name in (branch, base):
        if name and (not BRANCH_RE.match(name) or ".." in name or name.endswith(("/", ".lock"))):
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
            empty = True  # empty repository (no commits yet)
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
            status, listing = _call("GET", f"/repos/{repo}/git/trees/{tree_sha}?recursive=1", token)
            if status != 200:
                raise PushError(f"Could not read the files on '{base_name}' ({status}): {_msg(listing)}")
            if listing.get("truncated"):
                raise PushError("The base branch has too many files to compare safely. Use a smaller repo.")
            existing = {t["path"] for t in listing.get("tree", []) if t.get("type") == "blob"}

        plan = _plan(files, existing, overwrite)
        result["plan"] = plan
        result["counts"] = {a: sum(1 for p in plan if p["action"] == a) for a in ("new", "replace", "skip")}
        result["files"] = [p["path"] for p in plan if p["action"] != "skip"]
        result["fileCount"] = len(result["files"])
        if not apply:
            return result
        if not result["files"]:
            raise PushError("Nothing to push: every file already exists on the base branch. "
                            "Tick 'Replace existing files' to overwrite them.")

        if empty:
            # The Git Data API needs a first commit, so the README starts the default branch.
            first = "README.md"
            status, data = _call("PUT", f"/repos/{repo}/contents/{first}", token, {
                "message": "Initial commit", "branch": default,
                "content": base64.b64encode(files[first].encode("utf-8")).decode("ascii")})
            if status in (403, 404):
                raise PushError(
                    f"GitHub refused the write ({status}). The token can see the repo but cannot write to it. "
                    "Fine-grained token: set this repository's 'Contents' permission to Read and write. "
                    "Classic token: tick the 'repo' scope. If the repo belongs to an organisation, the token may "
                    "also need to be authorised for it (SSO).")
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
            result["files"] = [p["path"] for p in plan if p["action"] != "skip"]
            result["fileCount"] = len(result["files"])

        tree = []
        for path in result["files"]:
            status, blob = _call("POST", f"/repos/{repo}/git/blobs", token,
                                 {"content": files[path], "encoding": "utf-8"})
            if status != 201:
                raise PushError(f"Could not upload {path} ({status}): {_msg(blob)}")
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        status, new_tree = _call("POST", f"/repos/{repo}/git/trees", token, {"base_tree": tree_sha, "tree": tree})
        if status != 201:
            raise PushError(f"Could not create the file tree ({status}): {_msg(new_tree)}")
        status, new_commit = _call("POST", f"/repos/{repo}/git/commits", token,
                                   {"message": message, "tree": new_tree["sha"], "parents": [base_commit]})
        if status != 201:
            raise PushError(f"Could not create the commit ({status}): {_msg(new_commit)}")
        status, made = _call("POST", f"/repos/{repo}/git/refs", token,
                             {"ref": f"refs/heads/{branch}", "sha": new_commit["sha"]})
        if status != 201:
            raise PushError(f"Could not create the branch ({status}): {_msg(made)}")
        result.update({"commitSha": new_commit["sha"],
                       "commitUrl": f"https://github.com/{repo}/commit/{new_commit['sha']}",
                       "branchUrl": f"https://github.com/{repo}/tree/{branch}"})
        return result
    except PushError as exc:
        raise PushError(str(exc).replace(token, "***")) from None
