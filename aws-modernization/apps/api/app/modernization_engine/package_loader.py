from __future__ import annotations

from ..module_context.repository import ContextError, read_manifest, verify

SUPPORTED_SCHEMA = {"2.0.0"}


def load(eid: str, package_id: str, module_id: str) -> tuple[dict, dict]:
    manifest = read_manifest(eid, package_id)
    if manifest.get("moduleId") != module_id:
        raise ContextError("Package module does not match the requested module", 422)
    if manifest.get("schemaVersion") not in SUPPORTED_SCHEMA:
        raise ContextError("Package schema is unsupported by the Modernization Engine", 422)
    try:
        integrity = verify(eid, package_id)
    except ContextError as exc:
        raise ContextError("Package integrity is invalid: " + str(exc), 422) from exc
    return manifest, integrity
