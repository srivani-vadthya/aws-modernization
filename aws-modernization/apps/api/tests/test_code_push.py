from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app import code_push, main

ENG = {"scope": {"name": "Claims Processing"}}


class FakeGitHub:
    """Fake GitHub. `existing` = files already on the base branch; `branches` = branch -> commit sha."""

    def __init__(self, branch_exists=False, empty=False, existing=(), branches=("main",)):
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[tuple[str, str, object]] = []
        self.branch_exists, self.empty = branch_exists, empty
        self.existing = list(existing)
        self.branches = set(branches)
        self.initialised = False

    def __call__(self, method, path, token, body=None):
        self.calls.append((method, path))
        self.bodies.append((method, path, body))
        if path == "/repos/o/r":
            return 200, {"default_branch": "main", "permissions": {"push": True}}
        if path.endswith("/git/ref/heads/modernized-code"):
            return (200, {}) if self.branch_exists else (404, {})
        if "/git/ref/heads/" in path:
            name = path.rsplit("/git/ref/heads/", 1)[1]
            if self.empty and not self.initialised:
                return 409, {}
            return (200, {"object": {"sha": "base"}}) if name in self.branches else (404, {})
        if method == "PUT":
            self.initialised = True
            self.existing.append("README.md")
            return 201, {}
        if "/git/commits/base" in path:
            return 200, {"tree": {"sha": "t0"}}
        if "/git/trees/t0" in path:
            return 200, {"truncated": False, "tree": [{"path": p, "type": "blob"} for p in self.existing]}
        if path.endswith("/git/blobs"):
            return 201, {"sha": "b"}
        if path.endswith("/git/trees"):
            return 201, {"sha": "t1"}
        if path.endswith("/git/commits"):
            return 201, {"sha": "c1"}
        if path.endswith("/git/refs"):
            return 201, {}
        raise AssertionError(path)

    def pushed_paths(self):
        for method, path, body in self.bodies:
            if method == "POST" and path.endswith("/git/trees"):
                return [t["path"] for t in body["tree"]]
        return None


def _push(fake, monkeypatch, **kw):
    monkeypatch.setattr(code_push, "_call", fake)
    args = dict(branch="modernized-code", message="msg", apply=False)
    args.update(kw)
    return code_push.push(ENG, "o/r", "tok", **args)


def test_dummy_code_only_contains_code_files():
    files = code_push.dummy_files(ENG)
    assert "Program.cs" in files and any(p.endswith("Controller.cs") for p in files)
    assert not any(p.endswith((".ts", ".py")) for p in files)


def test_code_push_files_endpoint_returns_existing_project_listing(monkeypatch):
    monkeypatch.setattr(main.store, "load", lambda _eid: ENG)

    response = TestClient(main.app).get("/api/engagements/demo/code-push/files")

    assert response.status_code == 200
    data = response.json()
    assert data["demo"] is True
    assert data["project"] == "ClaimsProcessing"
    assert data["module1Branches"] == {}
    assert {item["path"] for item in data["files"]} == set(code_push.dummy_files(ENG))
    assert all({"path", "language", "content"} <= item.keys() for item in data["files"])


def test_module2_endpoint_uses_existing_code_push_module(monkeypatch):
    monkeypatch.setattr(main.store, "load", lambda _eid: ENG)
    calls = []

    def fake_push_module2(**kwargs):
        calls.append(kwargs)
        return {"created": False, "parentBranch": kwargs["parent_branch"]}

    monkeypatch.setattr(code_push, "push_module2", fake_push_module2)
    response = TestClient(main.app).post(
        "/api/engagements/demo/code-push/module2",
        json={
            "repo": "owner/repo",
            "parentBranch": "modernization/module-1",
            "newBranch": "modernization/module-2",
            "token": "request-token",
            "apply": True,
            "confirm": False,
        },
    )

    assert response.status_code == 200
    assert calls[0]["parent_branch"] == "modernization/module-1"
    assert calls[0]["new_branch"] == "modernization/module-2"
    assert calls[0]["apply"] is False


def test_code_push_records_latest_successful_module1_branch(monkeypatch):
    engagement = {"id": "demo"}
    monkeypatch.setattr(main.store, "load", lambda _eid: engagement)
    monkeypatch.setattr(main.store, "save", lambda value: value)
    monkeypatch.setattr(
        code_push,
        "push",
        lambda *_args, **_kwargs: {
            "repo": "owner/repo",
            "branch": "modernization/module-1",
            "baseBranch": "main",
            "commitSha": "module-1-sha",
        },
    )

    response = TestClient(main.app).post(
        "/api/engagements/demo/code-push",
        json={
            "repo": "owner/repo",
            "branch": "modernization/module-1",
            "apply": True,
            "confirm": True,
        },
    )

    assert response.status_code == 200
    saved = engagement["codePushModule1Branches"]["owner/repo"]
    assert saved["branch"] == "modernization/module-1"
    assert saved["commitSha"] == "module-1-sha"
    assert saved["baseBranch"] == "main"
    assert saved["updatedAt"]


def test_module2_endpoint_uses_latest_saved_module1_branch(monkeypatch):
    engagement = {
        "id": "demo",
        "codePushModule1Branches": {
            "owner/repo": {
                "branch": "modernization/module-1-latest",
                "commitSha": "module-1-sha",
            }
        },
    }
    monkeypatch.setattr(main.store, "load", lambda _eid: engagement)
    calls = []

    def fake_push_module2(**kwargs):
        calls.append(kwargs)
        return {"created": False, "parentBranch": kwargs["parent_branch"]}

    monkeypatch.setattr(code_push, "push_module2", fake_push_module2)
    response = TestClient(main.app).post(
        "/api/engagements/demo/code-push/module2",
        json={
            "repo": "owner/repo",
            "newBranch": "modernization/module-2",
            "token": "request-token",
        },
    )

    assert response.status_code == 200
    assert calls[0]["parent_branch"] == "modernization/module-1-latest"


def test_module2_publishes_new_branch_from_module1_and_preserves_parent_tree(monkeypatch):
    module1_paths = {
        "InsuranceProvider.Api.csproj",
        "Program.cs",
        "Models/InsuranceProvider.cs",
        "Services/IInsuranceProviderService.cs",
        "Services/InsuranceProviderService.cs",
        "Controllers/InsuranceProviderController.cs",
        "README.md",
    }
    blob_shas = {path: f"blob-{index}" for index, path in enumerate(sorted(module1_paths))}
    recorded = []

    def fake_call(method, path, token, body=None):
        recorded.append((method, path, body))
        if path == "/repos/owner/repo":
            return 200, {"default_branch": "main", "permissions": {"push": True}}
        if path.endswith("/git/ref/heads/modernization/module-2"):
            return 404, {}
        if path.endswith("/git/ref/heads/modernization/module-1"):
            return 200, {"object": {"sha": "module-1-commit"}}
        if path.endswith("/git/commits/module-1-commit"):
            return 200, {"tree": {"sha": "module-1-tree"}}
        if path.endswith("/git/trees/module-1-tree?recursive=1"):
            return 200, {
                "truncated": False,
                "tree": [
                    {"path": item_path, "type": "blob", "sha": blob_sha}
                    for item_path, blob_sha in blob_shas.items()
                ],
            }
        if "/git/blobs/" in path and method == "GET":
            file_path = next(file_path for file_path, sha in blob_shas.items() if path.endswith(sha))
            return 200, {
                "encoding": "base64",
                "content": base64.b64encode(f"// {file_path}".encode()).decode(),
            }
        if path.endswith("/git/blobs") and method == "POST":
            return 201, {"sha": "module2-blob"}
        if path.endswith("/git/trees") and method == "POST":
            return 201, {"sha": "module2-tree"}
        if path.endswith("/git/commits") and method == "POST":
            return 201, {"sha": "module2-commit"}
        if path.endswith("/git/refs") and method == "POST":
            return 201, {"ref": body["ref"]}
        raise AssertionError((method, path))

    monkeypatch.setattr(code_push, "_call", fake_call)
    monkeypatch.setattr(
        code_push,
        "generate_module2_files",
        lambda context: {"InsuranceClaims.Api/Program.cs": f"// based on {len(context)} Module 1 files"},
    )

    dry_run = code_push.push_module2(
        repo="owner/repo",
        parent_branch="modernization/module-1",
        new_branch="modernization/module-2",
        token="request-token",
        apply=False,
    )
    assert dry_run["previewFiles"] == [
        {
            "path": "InsuranceClaims.Api/Program.cs",
            "language": "csharp",
            "content": f"// based on {len(module1_paths) - 1} Module 1 files",
        }
    ]
    recorded.clear()

    result = code_push.push_module2(
        repo="owner/repo",
        parent_branch="modernization/module-1",
        new_branch="modernization/module-2",
        token="request-token",
        apply=True,
    )

    assert result["created"] is True
    assert result["parentCommitSha"] == "module-1-commit"
    assert result["inheritedFileCount"] == len(module1_paths)
    tree_call = next(call for call in recorded if call[0] == "POST" and call[1].endswith("/git/trees"))
    assert tree_call[2]["base_tree"] == "module-1-tree"
    commit_call = next(call for call in recorded if call[0] == "POST" and call[1].endswith("/git/commits"))
    assert commit_call[2]["parents"] == ["module-1-commit"]
    ref_call = next(call for call in recorded if call[0] == "POST" and call[1].endswith("/git/refs"))
    assert ref_call[2]["ref"] == "refs/heads/modernization/module-2"
    assert not any(
        method in {"PATCH", "PUT", "DELETE"} or path.endswith("/git/refs/main")
        for method, path, _body in recorded
    )


def test_module2_refuses_to_target_repository_default_branch(monkeypatch):
    calls = []

    def fake_call(method, path, _token, body=None):
        calls.append((method, path, body))
        if path == "/repos/owner/repo":
            return 200, {"default_branch": "main", "permissions": {"push": True}}
        raise AssertionError(f"Unexpected GitHub request: {method} {path}")

    monkeypatch.setattr(code_push, "_call", fake_call)

    with pytest.raises(code_push.PushError, match="default branch"):
        code_push.push_module2(
            repo="owner/repo",
            parent_branch="modernization/module-1",
            new_branch="main",
            token="request-token",
            apply=True,
        )

    assert calls == [("GET", "/repos/owner/repo", None)]


def test_dry_run_writes_nothing_and_shows_plan(monkeypatch):
    fake = FakeGitHub(existing=["Program.cs", "keep-me.txt"])
    res = _push(fake, monkeypatch)
    assert res["dryRun"] and res["baseBranch"] == "main"
    actions = {p["path"]: p["action"] for p in res["plan"]}
    assert actions["Program.cs"] == "skip" and actions["README.md"] == "new"
    assert res["counts"]["skip"] == 1 and "Program.cs" not in res["files"]
    assert not [c for c in fake.calls if c[0] in ("POST", "PUT")]


def test_existing_files_are_kept_by_default(monkeypatch):
    fake = FakeGitHub(existing=["Program.cs"])
    res = _push(fake, monkeypatch, apply=True)
    assert "Program.cs" not in fake.pushed_paths()
    assert res["commitUrl"].endswith("/commit/c1")
    assert ("POST", "/repos/o/r/git/refs") in fake.calls
    assert not [c for c in fake.calls if c[0] in ("PATCH", "DELETE")]  # never moves or force-updates a ref


def test_overwrite_replaces_existing_files(monkeypatch):
    fake = FakeGitHub(existing=["Program.cs"])
    res = _push(fake, monkeypatch, apply=True, overwrite=True)
    assert "Program.cs" in fake.pushed_paths()
    assert {p["path"]: p["action"] for p in res["plan"]}["Program.cs"] == "replace"


def test_custom_base_branch(monkeypatch):
    fake = FakeGitHub(branches=("main", "develop"))
    res = _push(fake, monkeypatch, base="develop")
    assert res["baseBranch"] == "develop"
    with pytest.raises(code_push.PushError, match="Base branch 'nope' was not found"):
        _push(FakeGitHub(), monkeypatch, base="nope")


def test_nothing_to_push_is_an_error(monkeypatch):
    fake = FakeGitHub(existing=list(code_push.dummy_files(ENG)))
    with pytest.raises(code_push.PushError, match="Nothing to push"):
        _push(fake, monkeypatch, apply=True)


def test_existing_branch_is_refused(monkeypatch):
    with pytest.raises(code_push.PushError, match="already exists"):
        _push(FakeGitHub(branch_exists=True), monkeypatch, apply=True)


def test_empty_repo_is_initialised(monkeypatch):
    fake = FakeGitHub(empty=True)
    dry = _push(fake, monkeypatch)
    assert dry["counts"]["new"] == len(code_push.dummy_files(ENG))
    res = _push(fake, monkeypatch, apply=True)
    assert res["initialisedEmptyRepo"] and res["commitUrl"]
    assert "README.md" not in fake.pushed_paths()  # already added as the first commit


def test_bad_input_and_token_not_leaked(monkeypatch):
    with pytest.raises(code_push.PushError):
        code_push.push(ENG, "not a repo", "tok", "b", "", False)
    monkeypatch.setattr(code_push, "_call", lambda *a, **k: (500, {"message": "boom SECRETTOKEN"}))
    with pytest.raises(code_push.PushError) as ei:
        code_push.push(ENG, "o/r", "SECRETTOKEN", "b", "", False)
    assert "SECRETTOKEN" not in str(ei.value)
