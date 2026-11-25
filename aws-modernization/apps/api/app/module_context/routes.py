from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .models import Manifest, ManifestV1, PackageRequest
from .repository import ContextError, download, list_manifests, read_manifest, verify
from .service import freshness, generate
from .templates import catalog

router = APIRouter(tags=["Module context packages"])


def call(fn, *args):
    try:
        return fn(*args)
    except ContextError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(409, "Context input is unreadable or malformed; no existing artifact was modified.") from exc


@router.get("/api/module-context-templates")
def get_templates(eid: str | None = None):
    if eid is None:
        return {"templates": catalog()}
    from .repository import engagement_root, safe_child
    import json
    def read_catalog():
        eng = json.loads(safe_child(engagement_root(eid), "engagement.json").read_bytes())
        target = (eng.get("seed") or {}).get("target") or {}
        from .templates import recommendations
        return {"templates": catalog(target), "recommendedIds": recommendations(target)}
    return call(read_catalog)


@router.get("/api/module-context-schema")
def get_schema(version: str = "2.0.0"):
    model = {"1.0.0": ManifestV1, "2.0.0": Manifest}.get(version)
    if model is None:
        raise HTTPException(422, "Unsupported schema version")
    return model.model_json_schema()


@router.post("/api/engagements/{eid}/module-context-packages")
def create_package(eid: str, body: PackageRequest):
    return call(generate, eid, body)


@router.get("/api/engagements/{eid}/module-context-packages")
def list_packages(eid: str, moduleId: str | None = None):
    return {"packages": call(list_manifests, eid, moduleId)}


@router.get("/api/engagements/{eid}/module-context-packages/{packageId}")
def get_package(eid: str, packageId: str):
    return call(read_manifest, eid, packageId)


@router.get("/api/engagements/{eid}/module-context-packages/{packageId}/freshness")
def get_freshness(eid: str, packageId: str):
    return call(freshness, eid, packageId)


@router.get("/api/engagements/{eid}/module-context-packages/{packageId}/download")
def get_download(eid: str, packageId: str):
    data = call(download, eid, packageId)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="module-context-{packageId}.zip"'})


@router.get("/api/engagements/{eid}/module-context-packages/{packageId}/integrity")
def get_integrity(eid: str, packageId: str):
    return call(verify, eid, packageId)
