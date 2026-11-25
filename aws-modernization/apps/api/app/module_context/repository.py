from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any

from .. import store


class ContextError(Exception):
    def __init__(self, message: str, status: int = 409):
        self.status = status
        super().__init__(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def io_path(path: Path) -> Path:
    """Use Windows extended paths for deeply nested portable package contents."""
    value = str(path.resolve())
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return Path(value)


def safe_child(root: Path, relative: str) -> Path:
    # Repository metadata may use Windows separators. Normalize only relative paths;
    # retain strict rejection of drive-qualified, absolute, traversal, and linked paths.
    normalized = str(relative).replace("\\", "/")
    rel = Path(normalized)
    if not normalized or rel.is_absolute() or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ":" in normalized or ".." in rel.parts:
        raise ContextError("Unsafe artifact path", 422)
    root = root.resolve()
    p = root / rel
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ContextError("Linked artifact paths are not allowed", 422)
    if not p.resolve().is_relative_to(root):
        raise ContextError("Artifact escapes its root", 422)
    return io_path(p)


def engagement_root(eid: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", eid):
        raise ContextError("Engagement not found", 404)
    root = safe_child(store.ENG_DIR, eid)
    if not (root / "engagement.json").is_file():
        raise ContextError("Engagement not found", 404)
    return root


def storage_root(eid: str) -> Path:
    return safe_child(engagement_root(eid), "artifacts/module-context")


def package_root(eid: str, package_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", package_id):
        raise ContextError("Package not found", 404)
    return safe_child(storage_root(eid), package_id)


def read_manifest(eid: str, package_id: str) -> dict:
    root = package_root(eid, package_id)
    path = safe_child(root, "manifest.json")
    if not path.is_file():
        raise ContextError("Package not found", 404)
    try:
        from .models import Manifest, ManifestV1
        m = json.loads(path.read_bytes())
        model = {"1.0.0": ManifestV1, "2.0.0": Manifest}.get(m.get("schemaVersion"))
        if model is None:
            raise ValueError("Unsupported package schema version")
        model.model_validate(m)  # Never reserialize defaults into historical snapshots.
        if m["packageId"] != package_id or m["engagementId"] != eid:
            raise ValueError("identity")
        expected = m["packageDigest"]
        if digest(canonical({**m, "packageDigest": ""})) != expected:
            raise ValueError("manifest digest")
        return m
    except (ValueError, OSError) as exc:
        raise ContextError("Package manifest is invalid", 409) from exc


def list_manifests(eid: str, module_id: str | None = None) -> list[dict]:
    root = storage_root(eid)
    if not root.exists():
        return []
    rows = []
    for p in root.iterdir():
        if re.fullmatch(r"[a-f0-9]{32}", p.name) and p.is_dir():
            m = read_manifest(eid, p.name)
            if module_id is None or m["moduleId"] == module_id:
                rows.append(m)
    return sorted(rows, key=lambda m: m["createdAt"], reverse=True)


def verify(eid: str, package_id: str) -> dict:
    from .validation import validate_snapshot
    m = read_manifest(eid, package_id)
    root = package_root(eid, package_id)
    files = {}
    for artifact in m["artifacts"]:
        p = safe_child(root, artifact["path"])
        if not p.is_file():
            raise ContextError("Package artifact is missing")
        files[artifact["path"]] = p.read_bytes()
    return validate_snapshot(m, files)


def download(eid: str, package_id: str) -> bytes:
    from .validation import validate_snapshot
    m = read_manifest(eid, package_id)
    root = package_root(eid, package_id)
    files = {}
    for a in m['artifacts']:
        p = safe_child(root, a['path'])
        if not p.is_file():raise ContextError('Package artifact is missing')
        files[a['path']] = p.read_bytes()
    validate_snapshot(m, files)
    files['manifest.json'] = safe_child(root,'manifest.json').read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path,data in sorted(files.items()):
            info=zipfile.ZipInfo(path, date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100444 << 16
            archive.writestr(info,data)
    result=buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        if set(archive.namelist())!=set(files) or len(archive.namelist())!=len(files) or archive.testzip():
            raise ContextError('ZIP entry consistency failure')
        if any(archive.read(p)!=data for p,data in files.items()):raise ContextError('ZIP byte mismatch')
    return result
