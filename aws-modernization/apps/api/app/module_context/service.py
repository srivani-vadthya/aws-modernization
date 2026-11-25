from __future__ import annotations

import shutil
import threading
import time
import uuid
from datetime import datetime, timezone

from .collector import SECRET_TEXT, collect
from .models import Manifest, PackageRequest
from .readiness import assess
from .assembly import assemble
from .validation import validate_snapshot
from .repository import ContextError, canonical, digest, list_manifests, read_manifest, safe_child, storage_root

_write_lock = threading.Lock()


def generate(eid: str, request: PackageRequest) -> dict:
    c = collect(eid, request)
    readiness = assess(c)
    contract = assemble(c)
    readiness.findings = c.findings
    readiness.modernizationPrerequisites = "blocked" if any(f.severity == "blocker" for f in c.findings) else "review-required" if any(f.severity == "warning" for f in c.findings) else "available"
    if collect(eid, request).consistency != c.consistency:
        raise ContextError("Inputs changed during collection; retry generation")
    # Only new package storage is ever written. No store.save(), generator or provider calls.
    with _write_lock:
        for m in list_manifests(eid, request.moduleId):
            if m["inputFingerprint"] == c.fingerprint:
                return {"created": False, "manifest": m}
        package_id = uuid.uuid4().hex
        root = storage_root(eid)
        root.mkdir(parents=True, exist_ok=True)
        staging = safe_child(root, ".staging-" + package_id)
        staging.mkdir()
        try:
            target = c.target if not SECRET_TEXT.search(canonical(c.target).decode()) else {}
            manifest = Manifest(
                packageId=package_id, engagementId=eid, moduleId=request.moduleId,
                createdAt=datetime.now(timezone.utc).isoformat(), inputFingerprint=c.fingerprint,
                packageDigest="", source=c.source,
                scope={"capabilityId": request.moduleId, "snapshot": "snapshots/scope.json" if "snapshots/scope.json" in c.files else None},
                target=target, templates=c.template_rows,
                approvals={"snapshot": "snapshots/approvals.json" if "snapshots/approvals.json" in c.files else None,
                           "binding": "existing-evidence-only"},
                coverage=c.coverage, artifacts=c.artifacts, readiness=readiness, contract=contract)
            # Readiness and schema travel with the package and are covered by artifact hashes.
            c.snapshot("readiness", readiness.model_dump(), "module-context deterministic assessment", "deterministic-derived")
            c.add("schema", "schema", "schema.json", canonical(Manifest.model_json_schema()),
                  "module-context.models.Manifest", provenance="observed")
            manifest.artifacts = c.artifacts
            manifest.contract.artifactCount = len(c.artifacts)
            manifest.contract.traceability.summary.totalArtifacts = len(c.artifacts)
            m = manifest.model_dump()
            m["packageDigest"] = digest(canonical(m))
            validate_snapshot(m, c.files)
            for relative, data in c.files.items():
                p = safe_child(staging, relative)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            safe_child(staging, "manifest.json").write_bytes(canonical(m))
            if collect(eid, request).consistency != c.consistency:
                raise ContextError("Inputs changed before publishing; retry generation")
            destination = safe_child(root, package_id)
            # Windows indexers can briefly hold a newly written directory open.
            for attempt in range(5):
                try:
                    staging.rename(destination)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        except BaseException:
            # This resolved path is solely a newly created staging child of package storage.
            if staging.exists() and staging.resolve().parent == root.resolve():
                shutil.rmtree(staging)
            raise
        return {"created": True, "manifest": read_manifest(eid, package_id)}


def freshness(eid: str, package_id: str) -> dict:
    m = read_manifest(eid, package_id)
    request = PackageRequest(moduleId=m["moduleId"], templateIds=[t["id"] for t in m["templates"]])
    try:
        c = collect(eid, request)
    except ContextError as exc:
        return {"packageId": package_id, "status": "not-comparable", "reason": str(exc)}
    return {"packageId": package_id, "status": "current" if c.fingerprint == m["inputFingerprint"] else "stale",
            "reason": "Compared collected content; this does not attest upstream analysis freshness."}
