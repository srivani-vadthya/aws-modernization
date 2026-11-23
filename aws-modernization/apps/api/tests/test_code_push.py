from __future__ import annotations

import pytest

from app import code_push

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
