"""GitHub automated repository creator and publisher for Nexus Modernize.

Allows users to export the modernized microservice, Playwright test suite,
Azure Terraform IaC, and GitHub Actions CI/CD workflows directly into a GitHub repo.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote

import httpx

logger = logging.getLogger("github_deployer")
module_publish_lock = threading.Lock()


class ModulePublishError(RuntimeError):
    pass


def get_github_token(custom_token: str | None = None) -> str | None:
    return (
        custom_token
        or os.getenv("GITHUB_TOKEN")
        or os.getenv("GITHUB_PAT")
        or os.getenv("GH_TOKEN")
        or os.getenv("GH_PAT")
    )


def _repo_from_url(repo_url: str | None) -> tuple[str | None, str | None]:
    if not repo_url:
        return None, None
    cleaned = repo_url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    match = re.search(r"github\.com[:/]+([^/]+)/([^/]+)$", cleaned, flags=re.IGNORECASE)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def build_feature_branch_name(reference_number: str | None = None) -> str:
    raw = (reference_number or os.getenv("USERSTORY_REFERENCE_NUMBER") or os.getenv("REFERENCE_NUMBER") or "Userstory").strip()
    sanitized = re.sub(r"[^A-Za-z0-9]+", "", raw)
    if not sanitized or sanitized.lower() in {"main", "master"}:
        sanitized = "Userstory"
    branch_name = f"feature/Userstory{sanitized}"
    if branch_name.lower() in {"main", "master", "feature/main", "feature/master"}:
        branch_name = "feature/Userstory"
    return branch_name


def publish_module_branch(
    repo_name: str,
    module_id: str,
    generate_files: Callable[[dict[str, str]], dict[str, str]],
    token: str | None = None,
    org: str | None = None,
    private: bool = True,
    pipeline_states: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate from the latest pipeline parent and publish the module on a new branch."""
    gh_token = get_github_token(token)
    if not gh_token:
        raise ModulePublishError("GitHub Personal Access Token (GITHUB_TOKEN) is not configured.")

    requested_repo = (repo_name or "").strip().strip("/")
    if "github.com" in requested_repo.lower():
        url_owner, url_repo = _repo_from_url(requested_repo)
        if url_owner and url_repo:
            requested_repo = f"{url_owner}/{url_repo}"
    if not requested_repo:
        raise ModulePublishError("A GitHub repository name is required.")
    if "/" in requested_repo:
        requested_owner, repo_slug = requested_repo.split("/", 1)
    else:
        requested_owner, repo_slug = None, requested_repo
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", repo_slug) or (
        requested_owner and not re.fullmatch(r"[A-Za-z0-9_.-]+", requested_owner)
    ):
        raise ModulePublishError("Repository must be a name or owner/repository.")

    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    def request(client: httpx.Client, method: str, url: str, **kwargs: Any) -> tuple[httpx.Response, dict[str, Any]]:
        try:
            response = client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ModulePublishError(f"GitHub request failed ({type(exc).__name__}).") from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        return response, data if isinstance(data, dict) else {}

    def require(response: httpx.Response, expected: tuple[int, ...], action: str, data: dict[str, Any]) -> None:
        if response.status_code not in expected:
            detail = str(data.get("message") or response.text or "unknown error")[:200]
            detail = detail.replace(gh_token, "***")
            raise ModulePublishError(f"{action} failed ({response.status_code}): {detail}")

    api = "https://api.github.com"
    with httpx.Client(timeout=30.0) as client:
        user_response, user = request(client, "GET", f"{api}/user")
        require(user_response, (200,), "GitHub authentication", user)
        owner = org or requested_owner or user.get("login")
        if not owner:
            raise ModulePublishError("Could not determine the GitHub repository owner.")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner):
            raise ModulePublishError("GitHub owner or organisation name is invalid.")
        repo_key = f"{owner}/{repo_slug}"
        repo_api = f"{api}/repos/{quote(owner, safe='')}/{quote(repo_slug, safe='')}"

        repo_response, repo_info = request(client, "GET", repo_api)
        if repo_response.status_code == 404:
            create_api = f"{api}/orgs/{quote(org, safe='')}/repos" if org else f"{api}/user/repos"
            create_response, repo_info = request(
                client,
                "POST",
                create_api,
                json={
                    "name": repo_slug,
                    "description": "Modernized modules generated by Nexus Modernize.",
                    "private": private,
                    "auto_init": True,
                },
            )
            require(create_response, (200, 201), f"Create repository '{repo_key}'", repo_info)
        else:
            require(repo_response, (200,), f"Access repository '{repo_key}'", repo_info)

        default_branch = repo_info.get("default_branch")
        if not default_branch:
            raise ModulePublishError(f"GitHub did not report a default branch for '{repo_key}'.")

        state = (pipeline_states or {}).get(repo_key) or {}
        if state:
            parent_branch = state.get("latestBranch")
            parent_sha = state.get("latestCommitSha")
            if not parent_branch or not parent_sha:
                raise ModulePublishError(f"Saved module-publish state for '{repo_key}' is incomplete.")
        else:
            parent_branch = default_branch
            ref_response, ref_data = request(
                client,
                "GET",
                f"{repo_api}/git/ref/heads/{quote(default_branch, safe='')}",
            )
            require(ref_response, (200,), f"Resolve default branch '{default_branch}'", ref_data)
            parent_sha = (ref_data.get("object") or {}).get("sha")
            if not parent_sha:
                raise ModulePublishError(f"Could not resolve the commit for default branch '{default_branch}'.")

        commit_response, parent_commit = request(client, "GET", f"{repo_api}/git/commits/{quote(parent_sha, safe='')}")
        require(commit_response, (200,), f"Read parent commit '{parent_sha}'", parent_commit)
        parent_tree = (parent_commit.get("tree") or {}).get("sha")
        if not parent_tree:
            raise ModulePublishError(f"Parent commit '{parent_sha}' has no tree.")

        tree_response, tree_data = request(
            client,
            "GET",
            f"{repo_api}/git/trees/{quote(parent_tree, safe='')}?recursive=1",
        )
        require(tree_response, (200,), "Read parent branch tree", tree_data)
        if tree_data.get("truncated"):
            raise ModulePublishError("Parent branch tree is too large to safely use as module context.")

        context_files: dict[str, str] = {}
        context_extensions = {
            ".cs", ".csproj", ".java", ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md",
            ".xml", ".yaml", ".yml", ".toml", ".txt", ".gradle", ".properties", ".sql", ".html",
            ".css", ".go", ".rs", ".php", ".rb", ".sh", ".config", ".sln",
        }
        context_names = {
            "Dockerfile", "Makefile", ".gitignore", "pom.xml", "build.gradle", "settings.gradle",
        }
        for item in tree_data.get("tree", []):
            path = item.get("path", "")
            if item.get("type") != "blob" or not path:
                continue
            if os.path.basename(path) not in context_names and os.path.splitext(path)[1].lower() not in context_extensions:
                continue
            blob_response, blob_data = request(
                client,
                "GET",
                f"{repo_api}/git/blobs/{quote(item['sha'], safe='')}",
            )
            require(blob_response, (200,), f"Read parent file '{path}'", blob_data)
            if blob_data.get("encoding") != "base64" or not isinstance(blob_data.get("content"), str):
                continue
            try:
                context_files[path] = base64.b64decode(blob_data["content"]).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                continue

        files = generate_files(context_files)
        if not isinstance(files, dict) or not files:
            raise ModulePublishError(f"Generation returned no files for module '{module_id}'.")

        tree_entries = []
        module_slug = re.sub(r"[^a-z0-9-]+", "-", module_id.lower()).strip("-") or "module"
        module_root = f"modules/{module_slug}/"
        for path, content in sorted(files.items()):
            normalized = path.replace("\\", "/") if isinstance(path, str) else ""
            if (
                not normalized
                or normalized.startswith("/")
                or any(part in {"", ".", ".."} for part in normalized.split("/"))
                or not normalized.startswith(module_root)
                or not isinstance(content, str)
            ):
                raise ModulePublishError(
                    f"Generation returned a file outside the isolated module path '{module_root}'."
                )
            blob_response, blob_data = request(
                client,
                "POST",
                f"{repo_api}/git/blobs",
                json={"content": content, "encoding": "utf-8"},
            )
            require(blob_response, (201,), f"Upload generated file '{normalized}'", blob_data)
            tree_entries.append(
                {"path": normalized, "mode": "100644", "type": "blob", "sha": blob_data.get("sha")}
            )
            if not blob_data.get("sha"):
                raise ModulePublishError(f"GitHub did not return a blob SHA for '{normalized}'.")

        new_tree_response, new_tree = request(
            client,
            "POST",
            f"{repo_api}/git/trees",
            json={"base_tree": parent_tree, "tree": tree_entries},
        )
        require(new_tree_response, (201,), "Create module tree", new_tree)
        new_tree_sha = new_tree.get("sha")
        if not new_tree_sha:
            raise ModulePublishError("GitHub did not return a SHA for the module tree.")

        branch_slug = module_slug
        branch = (
            f"modernization/{branch_slug[:40]}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        )
        commit_response, new_commit = request(
            client,
            "POST",
            f"{repo_api}/git/commits",
            json={
                "message": f"feat(modernization): add module {module_id}",
                "tree": new_tree_sha,
                "parents": [parent_sha],
            },
        )
        require(commit_response, (201,), "Create module commit", new_commit)
        commit_sha = new_commit.get("sha")
        if not commit_sha:
            raise ModulePublishError("GitHub did not return a commit SHA.")

        ref_response, ref_data = request(
            client,
            "POST",
            f"{repo_api}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": commit_sha},
        )
        require(ref_response, (201,), f"Create branch '{branch}'", ref_data)

        push_record = {
            "moduleId": module_id,
            "branch": branch,
            "commitSha": commit_sha,
            "parentBranch": parent_branch,
            "parentCommitSha": parent_sha,
        }
        pipeline_state = {
            "repository": repo_key,
            "defaultBranch": default_branch,
            "latestBranch": branch,
            "latestCommitSha": commit_sha,
            "lastModuleId": module_id,
            "pushCount": int(state.get("pushCount") or 0) + 1,
        }
        return {
            **push_record,
            "repository": repo_key,
            "repoUrl": repo_info.get("html_url") or f"https://github.com/{repo_key}",
            "branchUrl": f"https://github.com/{repo_key}/tree/{branch}",
            "filesCommitted": len(tree_entries),
            "pipelineState": pipeline_state,
        }


def create_or_update_repo(
    repo_name: str,
    files: dict[str, str],
    commit_message: str = "feat(modernize): initialize modernized cloud microservice and Azure IaC",
    token: str | None = None,
    org: str | None = None,
    private: bool = True,
    branch: str | None = None,
    repo_url: str | None = None,
    reference_number: str | None = None,
) -> dict[str, Any]:
    """Create a new GitHub repository (or use existing) and commit the generated codebase via GitHub REST API."""
    gh_token = get_github_token(token)
    if not gh_token:
        return {
            "ok": False,
            "error": "GitHub Personal Access Token (GITHUB_TOKEN) is not configured.",
            "instructions": "Provide a GitHub Personal Access Token with 'repo' scope to publish automatically.",
        }

    repo_target = repo_url or os.getenv("BACKEND_REPO")
    if repo_target:
        repo_owner, repo_slug = _repo_from_url(repo_target)
        if repo_owner and repo_slug:
            org = org or repo_owner
            repo_name = repo_slug

    if branch and branch.lower() in {"main", "master"}:
        branch = build_feature_branch_name(reference_number)
    elif not branch:
        branch = build_feature_branch_name(reference_number)

    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(timeout=30.0) as client:
        # 1. Determine Owner / User
        user_res = client.get("https://api.github.com/user", headers=headers)
        if user_res.status_code != 200:
            return {
                "ok": False,
                "error": f"Failed to authenticate with GitHub: {user_res.text[:200]}",
            }
        current_user = user_res.json().get("login")
        target_owner = org or current_user

        # 2. Check if repo exists or create it
        repo_url_api = f"https://api.github.com/repos/{target_owner}/{repo_name}"
        check_res = client.get(repo_url_api, headers=headers)

        if check_res.status_code == 404:
            create_endpoint = (
                f"https://api.github.com/orgs/{org}/repos" if org else "https://api.github.com/user/repos"
            )
            create_payload = {
                "name": repo_name,
                "description": "Modernized cloud-native microservice generated by Nexus Modernize with Azure WebApp & PostgreSQL IaC.",
                "private": private,
                "auto_init": True,
            }
            create_res = client.post(create_endpoint, headers=headers, json=create_payload)
            if create_res.status_code not in (200, 201):
                return {
                    "ok": False,
                    "error": f"Failed to create GitHub repository '{target_owner}/{repo_name}': {create_res.text[:200]}",
                }
            html_url = create_res.json().get("html_url")
        elif check_res.status_code == 200:
            html_url = check_res.json().get("html_url")
        else:
            return {
                "ok": False,
                "error": f"Error accessing repository '{target_owner}/{repo_name}': {check_res.text[:200]}",
            }

        default_branch = check_res.json().get("default_branch") if check_res.status_code == 200 else "main"
        branch_ref = f"refs/heads/{branch}"
        branch_ref_path = quote(branch_ref.replace("refs/heads/", ""), safe="")
        _branch_check = client.get(
            f"https://api.github.com/repos/{target_owner}/{repo_name}/git/ref/heads/{branch_ref_path}",
            headers=headers,
        )
        if _branch_check.status_code == 404:
            base_ref = client.get(f"https://api.github.com/repos/{target_owner}/{repo_name}/git/ref/heads/{quote(default_branch, safe='')}", headers=headers)
            if base_ref.status_code != 200:
                return {
                    "ok": False,
                    "error": f"Unable to resolve default branch '{default_branch}' for repository '{target_owner}/{repo_name}'.",
                }
            base_sha = base_ref.json()["object"]["sha"]
            create_branch_res = client.post(
                f"https://api.github.com/repos/{target_owner}/{repo_name}/git/refs",
                headers=headers,
                json={"ref": branch_ref, "sha": base_sha},
            )
            if create_branch_res.status_code not in (200, 201):
                return {
                    "ok": False,
                    "error": f"Failed to create branch '{branch}' in '{target_owner}/{repo_name}': {create_branch_res.text[:200]}",
                }

        # 3. Commit files using GitHub REST API contents endpoint
        committed_files = []
        for path_str, content in files.items():
            content_bytes = content.encode("utf-8") if isinstance(content, str) else content
            b64_content = base64.b64encode(content_bytes).decode("utf-8")
            file_url = f"https://api.github.com/repos/{target_owner}/{repo_name}/contents/{path_str}"
            branch_query = quote(branch, safe="")
            sha = None
            f_check = client.get(f"{file_url}?ref={branch_query}", headers=headers)
            if f_check.status_code == 200:
                sha = f_check.json().get("sha")

            put_body = {
                "message": f"feat: add {path_str}",
                "content": b64_content,
                "branch": branch,
            }
            if sha:
                put_body["sha"] = sha

            put_res = client.put(file_url, headers=headers, json=put_body)
            if put_res.status_code in (200, 201):
                committed_files.append(path_str)
            else:
                logger.warning(f"Failed to commit {path_str}: {put_res.text[:150]}")

        return {
            "ok": True,
            "repoUrl": html_url,
            "owner": target_owner,
            "repoName": repo_name,
            "branch": branch,
            "filesCommitted": len(committed_files),
            "workflowUrl": f"{html_url}/actions",
        }
