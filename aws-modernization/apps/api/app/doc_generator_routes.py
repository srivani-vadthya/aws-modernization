"""Doc generator routes — loosely coupled, registered in main.py with one line."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from . import store
from .doc_generator_service import generate_docs

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/engagements/{eid}/generate-docs/docx")
def download_docx(eid: str):
    if not store.load(eid):
        raise HTTPException(404, "Engagement not found")
    try:
        docx_bytes, _ = generate_docs(eid)
    except Exception as exc:
        logger.exception("Doc generation failed for %s", eid)
        raise HTTPException(500, f"Documentation generation failed: {exc}") from exc
    eng = store.load(eid)
    name = (eng.get("name") or eid).replace(" ", "_")
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{name}_docs.docx"'},
    )


@router.post("/api/engagements/{eid}/generate-docs/html")
def download_html(eid: str):
    if not store.load(eid):
        raise HTTPException(404, "Engagement not found")
    try:
        _, html_str = generate_docs(eid)
    except Exception as exc:
        logger.exception("Doc generation failed for %s", eid)
        raise HTTPException(500, f"Documentation generation failed: {exc}") from exc
    eng = store.load(eid)
    name = (eng.get("name") or eid).replace(" ", "_")
    return Response(
        content=html_str.encode("utf-8"),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{name}_docs.html"'},
    )
