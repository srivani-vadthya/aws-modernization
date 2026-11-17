from __future__ import annotations

import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import store
from .classifier import classify_tree
from .generated import write_generated
from .phases import PHASE_IDS
from .seed import genapp_seed, generic_seed

GENAPP_URL = "https://github.com/cicsdev/cics-genapp.git"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gates() -> dict:
    return {
        pid: {"status": "pending", "decision": None, "comment": None, "actor": None, "at": None}
        for pid in PHASE_IDS
    }


def _new(name: str, source_type: str, git_url: str | None = None, branch: str | None = None) -> dict:
    eid = uuid.uuid4().hex[:12]
    store.engagement_dir(eid)
    return {
        "id": eid,
        "name": name,
        "sourceType": source_type,
        "gitUrl": git_url,
        "gitBranch": branch or "main",
        "region": "us-east-1",
        "status": "intake",
        "currentPhase": "intake",
        "createdAt": _now(),
        "gates": _gates(),
        "inventory": None,
        "seed": None,
        "scope": None,
        "adoExport": None,
        "github": None,
        "awsIntake": None,
    }


def _finalize(eng: dict, source: Path, overlay_seed: bool) -> dict:
    inventory = classify_tree(source)
    eng["inventory"] = inventory
    if overlay_seed:
        eng["seed"] = genapp_seed(inventory, eng["id"])
        eng["name"] = eng.get("name") or "GenApp insurance"
        eng["domain"] = "insurance"
    else:
        eng["seed"] = generic_seed(inventory, eng["id"], eng["name"])
        eng["domain"] = "unclassified"
    # Modernized target service artifacts are written into the artifacts folder
    target_info = (eng.get("seed") or {}).get("target") or {}
    lang = (target_info.get("language") or "").lower()
    stack = (target_info.get("stack") or "").lower()
    if any("c#" in s or ".net" in s for s in (lang, stack)):
        from .generated_dotnet import write_dotnet_generated
        gen_dir = store.engagement_dir(eng["id"]) / "artifacts" / "ims-modernized-service"
        write_dotnet_generated(gen_dir)
    elif overlay_seed:
        gen_dir = store.engagement_dir(eng["id"]) / "artifacts" / "motor-policy-service"
        write_generated(gen_dir)
    # Intake is an internal processing step; Discovery is the first human gate.
    eng["gates"]["intake"].update(status="completed", decision=None,
        actor="source-ingestion", at=_now(),
        comment="Source inventory completed automatically; review and approve Discovery.")
    eng["gates"]["discovery"]["status"] = "ready"
    eng["currentPhase"] = "discovery"
    eng["status"] = "discovery"
    return store.save(eng)


def from_git(url: str, branch: str = "main", name: str | None = None, sample: bool = False) -> dict:
    eng = _new(name or url.rsplit("/", 1)[-1].removesuffix(".git"), "git" if not sample else "sample", url, branch)
    dest = store.engagement_dir(eng["id"]) / "source"
    if dest.exists():
        shutil.rmtree(dest)
    cmd = ["git", "clone", "--depth", "1", "--branch", branch, url, str(dest)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
    except subprocess.CalledProcessError:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        retry = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if retry.returncode != 0:
            raise RuntimeError(retry.stderr.strip() or retry.stdout.strip() or "git clone failed")
    except FileNotFoundError as exc:
        raise RuntimeError("git is not installed on this machine") from exc
    return _finalize(eng, dest, overlay_seed=sample)


def from_sample() -> dict:
    return from_git(GENAPP_URL, "main", "GenApp insurance", sample=True)


def from_zip(upload_path: Path, filename: str) -> dict:
    eng = _new(filename.removesuffix(".zip"), "zip")
    dest = store.engagement_dir(eng["id"]) / "source"
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(upload_path, "r") as zf:
        zf.extractall(dest)
    return _finalize(eng, dest, overlay_seed=False)


def from_folder(folder_path: Path, name: str | None = None) -> dict:
    if not folder_path.exists() or not folder_path.is_dir():
        raise ValueError(f"Folder does not exist or is not a directory: {folder_path}")
    eng_name = name or folder_path.name
    eng = _new(eng_name, "folder")
    dest = store.engagement_dir(eng["id"]) / "source"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        folder_path,
        dest,
        ignore=shutil.ignore_patterns(".git", "node_modules", "bin", "obj", ".vs", "packages", "dist", "Scripts", "scripts", "Content", "content", "fonts", "Images", "images")
    )
    return _finalize(eng, dest, overlay_seed=False)
