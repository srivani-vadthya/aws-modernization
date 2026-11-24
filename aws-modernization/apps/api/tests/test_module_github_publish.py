from __future__ import annotations

import base64
import json

import httpx
import pytest

from app import bedrock_skills, github_deployer, main


class InMemoryGitHub:
    def __init__(self):
        self.blobs = {}
        self.trees = {}
        self.commits = {"base-commit": "base-tree"}
        self.refs = {"main": "base-commit"}
        self.base_paths = {}
        for index in range(20):
            path = f"legacy/file-{index}.txt"
            sha = f"base-blob-{index}"
            self.blobs[sha] = f"legacy content {index}"
            self.base_paths[path] = sha
        self.blobs["shared-blob"] = "public class SharedService {}"
        self.base_paths["modules/shared/SharedService.cs"] = "shared-blob"
        self.trees["base-tree"] = dict(self.base_paths)
        self.requests = []
        self.next_blob = 0
        self.next_tree = 0
        self.next_commit = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        path = request.url.path
        self.requests.append((request.method, path, body))

        if path == "/user":
            return httpx.Response(200, json={"login": "owner"})
        if path == "/repos/owner/repo":
            return httpx.Response(
                200,
                json={
                    "default_branch": "main",
                    "html_url": "https://github.com/owner/repo",
                    "permissions": {"push": True},
                },
            )
        if path.endswith("/git/ref/heads/main") and request.method == "GET":
            return httpx.Response(200, json={"object": {"sha": self.refs["main"]}})
        if "/git/ref/heads/" in path and request.method == "GET":
            branch = path.split("/git/ref/heads/", 1)[1]
            if branch in self.refs:
                return httpx.Response(200, json={"object": {"sha": self.refs[branch]}})
            return httpx.Response(404, json={"message": "Not found"})
        if "/git/commits/" in path and request.method == "GET":
            sha = path.rsplit("/", 1)[1]
            if sha in self.commits:
                return httpx.Response(200, json={"tree": {"sha": self.commits[sha]}})
            return httpx.Response(404, json={"message": "Not found"})
        if "/git/trees/" in path and request.method == "GET":
            sha = path.rsplit("/", 1)[1]
            entries = [
                {"path": item_path, "type": "blob", "sha": blob_sha}
                for item_path, blob_sha in self.trees[sha].items()
            ]
            return httpx.Response(200, json={"truncated": False, "tree": entries})
        if "/git/blobs/" in path and request.method == "GET":
            sha = path.rsplit("/", 1)[1]
            return httpx.Response(
                200,
                json={
                    "encoding": "base64",
                    "content": base64.b64encode(self.blobs[sha].encode()).decode(),
                },
            )
        if path.endswith("/git/blobs") and request.method == "POST":
            self.next_blob += 1
            sha = f"module-blob-{self.next_blob}"
            self.blobs[sha] = body["content"]
            return httpx.Response(201, json={"sha": sha})
        if path.endswith("/git/trees") and request.method == "POST":
            self.next_tree += 1
            sha = f"module-tree-{self.next_tree}"
            new_paths = dict(self.trees[body["base_tree"]])
            for entry in body["tree"]:
                new_paths[entry["path"]] = entry["sha"]
            self.trees[sha] = new_paths
            return httpx.Response(201, json={"sha": sha})
        if path.endswith("/git/commits") and request.method == "POST":
            self.next_commit += 1
            sha = f"module-commit-{self.next_commit}"
            self.commits[sha] = body["tree"]
            return httpx.Response(201, json={"sha": sha})
        if path.endswith("/git/refs") and request.method == "POST":
            ref = body["ref"].removeprefix("refs/heads/")
            if ref in self.refs:
                return httpx.Response(422, json={"message": "Reference already exists"})
            self.refs[ref] = body["sha"]
            return httpx.Response(201, json={"ref": body["ref"]})
        return httpx.Response(404, json={"message": f"Unexpected request: {request.method} {path}"})

    def branch_files(self, branch: str) -> dict[str, str]:
        commit = self.refs[branch]
        tree = self.commits[commit]
        return {path: self.blobs[sha] for path, sha in self.trees[tree].items()}


def _mock_github(monkeypatch, github: InMemoryGitHub):
    real_client = httpx.Client
    transport = httpx.MockTransport(github)
    monkeypatch.setattr(
        github_deployer.httpx,
        "Client",
        lambda *args, **kwargs: real_client(transport=transport, *args, **kwargs),
    )


def test_module_pushes_chain_from_latest_branch_and_preserve_prior_modules(monkeypatch):
    fake = InMemoryGitHub()
    _mock_github(monkeypatch, fake)
    states = {}
    contexts = []
    results = []

    for module_id in ("orders", "billing", "claims"):
        def generate(parent_files, current_module=module_id):
            contexts.append(dict(parent_files))
            return {f"modules/{current_module}/{current_module.title()}.cs": f"class {current_module.title()} {{}}"}

        result = github_deployer.publish_module_branch(
            repo_name="owner/repo",
            module_id=module_id,
            generate_files=generate,
            token="test-token",
            pipeline_states=states,
        )
        results.append(result)
        states[result["repository"]] = result.pop("pipelineState")

    pushes = results
    assert [push["parentBranch"] for push in pushes] == ["main", pushes[0]["branch"], pushes[1]["branch"]]
    assert [push["parentCommitSha"] for push in pushes] == ["base-commit", pushes[0]["commitSha"], pushes[1]["commitSha"]]
    assert len({push["branch"] for push in pushes}) == 3
    assert contexts[0]["modules/shared/SharedService.cs"] == "public class SharedService {}"
    assert "modules/orders/Orders.cs" in contexts[1]
    assert "modules/billing/Billing.cs" in contexts[2]

    first_branch_files = fake.branch_files(pushes[0]["branch"])
    second_branch_files = fake.branch_files(pushes[1]["branch"])
    third_branch_files = fake.branch_files(pushes[2]["branch"])
    assert len([path for path in first_branch_files if path.startswith("legacy/")]) == 20
    assert "modules/orders/Orders.cs" in first_branch_files
    assert "modules/orders/Orders.cs" in second_branch_files
    assert "modules/billing/Billing.cs" in second_branch_files
    assert {"modules/orders/Orders.cs", "modules/billing/Billing.cs", "modules/claims/Claims.cs"} <= third_branch_files.keys()
    assert fake.refs["main"] == "base-commit"
    assert states["owner/repo"]["pushCount"] == 3
    assert fake.branch_files("main") == {
        **{f"legacy/file-{index}.txt": f"legacy content {index}" for index in range(20)},
        "modules/shared/SharedService.cs": "public class SharedService {}",
    }
    assert not any(method in {"PATCH", "PUT", "DELETE"} for method, _path, _body in fake.requests)


def test_module_generation_uses_parent_code_and_rejects_paths_outside_module(monkeypatch):
    captured = {}

    def generate(system, prompt, **kwargs):
        captured["system"] = system
        captured["request"] = json.loads(prompt)
        captured["kwargs"] = kwargs
        return {"files": {"modules/orders/Orders.cs": "class Orders {}"}}, "test-model"

    monkeypatch.setattr(bedrock_skills, "ask_json", generate)
    files = bedrock_skills.synthesize_module_codebase(
        {"id": "orders", "name": "Orders", "dependsOn": ["Shared"]},
        {"language": "csharp", "framework": "dotnet-9"},
        {"modules/shared/SharedService.cs": "class SharedService {}"},
    )
    assert list(files) == ["modules/orders/Orders.cs"]
    assert captured["request"]["parentBranchFiles"]["modules/shared/SharedService.cs"] == "class SharedService {}"
    assert captured["request"]["module"]["dependsOn"] == ["Shared"]
    assert captured["kwargs"]["task_type"] == "code"

    monkeypatch.setattr(
        bedrock_skills,
        "ask_json",
        lambda *_args, **_kwargs: ({"files": {"README.md": "overwrite"}}, "test-model"),
    )
    with pytest.raises(RuntimeError, match="outside"):
        bedrock_skills.synthesize_module_codebase(
            {"id": "orders"},
            {"language": "csharp"},
            {"modules/shared/SharedService.cs": "class SharedService {}"},
        )


def test_module_publish_route_persists_latest_branch_and_sha(monkeypatch):
    engagement = {"id": "eng-1", "seed": {"target": {}}, "githubModulePipelines": {}}
    published_states = []
    results = []

    monkeypatch.setattr(main.store, "load", lambda _eid: engagement)
    monkeypatch.setattr(main.store, "save", lambda value: value)
    monkeypatch.setattr(
        main.target_contract,
        "validate_target_contract",
        lambda *_args, **_kwargs: {"language": "csharp", "framework": "dotnet-9"},
    )
    monkeypatch.setattr(
        main.scope_modules,
        "build_scope_modules",
        lambda *_args, **_kwargs: {"modules": [{"id": "orders", "name": "Orders"}]},
    )
    monkeypatch.setattr(
        bedrock_skills,
        "synthesize_module_codebase",
        lambda _module, _target, _context: {"modules/orders/Orders.cs": "class Orders {}"},
    )

    def publish(**kwargs):
        published_states.append(dict(kwargs["pipeline_states"]))
        kwargs["generate_files"]({"modules/shared/Shared.cs": "class Shared {}"})
        index = len(results) + 1
        result = {
            "repository": "owner/repo",
            "branch": f"modernization/orders-{index}",
            "commitSha": f"commit-{index}",
            "parentBranch": "main" if index == 1 else f"modernization/orders-{index - 1}",
            "parentCommitSha": "base" if index == 1 else f"commit-{index - 1}",
            "filesCommitted": 1,
            "branchUrl": "https://github.com/owner/repo/tree/branch",
            "pipelineState": {
                "repository": "owner/repo",
                "defaultBranch": "main",
                "latestBranch": f"modernization/orders-{index}",
                "latestCommitSha": f"commit-{index}",
            },
        }
        results.append(result)
        return dict(result)

    monkeypatch.setattr(github_deployer, "publish_module_branch", publish)
    body = main.GitHubModulePublishIn(repoName="owner/repo", token="request-token")
    first = main.post_github_module_publish("eng-1", "orders", body)
    second = main.post_github_module_publish("eng-1", "orders", body)

    assert first["parentBranch"] == "main"
    assert second["parentBranch"] == first["branch"]
    assert published_states[1]["owner/repo"]["latestCommitSha"] == first["commitSha"]
    assert engagement["githubModulePipelines"]["owner/repo"]["latestCommitSha"] == second["commitSha"]
