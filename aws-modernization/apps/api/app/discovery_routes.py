"""Additive discovery endpoints; never modify scope, gates or legacy seed artifacts."""
from __future__ import annotations

import json
import hashlib
import re
import threading
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import discovery_report, store

router = APIRouter()
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


class RunIn(BaseModel):
    useBedrock: bool = True
    onlyIfNeeded: bool = False


class CommentIn(BaseModel):
    section: str = Field(pattern="^(overview|modules|dependencies|integrations|findings|telemetry)$")
    text: str = Field(min_length=1, max_length=2000)


def context(eid: str):
    if not re.fullmatch(r"[a-f0-9]{12}", eid):
        raise HTTPException(404, "Engagement not found")
    eng = store.load(eid)
    if not eng:
        raise HTTPException(404, "Engagement not found")
    root = store.ENG_DIR / eid
    with _guard:
        lock = _locks.setdefault(eid, threading.Lock())
    return eng, root, lock


def read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    tmp.replace(path)


def persist(root, report):
    write(root / "discovery-report.json", report)
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    write(artifacts / "discovery.json", report)
    write(artifacts / "discovery-evidence.json", {"sourceDigest": report["sourceDigest"], "evidence": report["evidence"], "assets": report["assets"]})
    write(artifacts / "discovery-graph.json", report["graph"])
    write(artifacts / "discovery-comments.json", report.get("comments", []))


def build(eng, root, prior):
    try:
        report = discovery_report.scan(root / "source", eng)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if prior.get("version") == report["version"] and prior.get("sourceDigest") == report["sourceDigest"]:
        report["ai"] = prior.get("ai", report["ai"])
        report["telemetry"] = prior.get("telemetry", [])
        if prior.get("reviewKey"):
            report["reviewKey"] = prior["reviewKey"]
    else:
        report["telemetry"] = prior.get("telemetry", [])
    report["comments"] = read(root / "discovery-comments.json", [])
    return report


def review_key(report):
    return hashlib.sha256(json.dumps([report["version"], report["sourceDigest"], report.get("comments", [])], sort_keys=True).encode()).hexdigest()


@router.get("/api/engagements/{eid}/discovery-report")
def get_report(eid: str):
    eng, root, lock = context(eid)
    if not lock.acquire(blocking=False):
        prior = read(root / "discovery-report.json", {})
        if prior:
            return {**prior, "ai": {**prior.get("ai", {}), "status": "Running"}}
        raise HTTPException(409, "Discovery is running. Please retry shortly.")
    try:
        path = root / "discovery-report.json"
        report = build(eng, root, read(path, {}))
        persist(root, report)
        return report
    finally:
        lock.release()


@router.post("/api/engagements/{eid}/discovery-report")
def run_report(eid: str, body: RunIn):
    eng, root, lock = context(eid)
    if not lock.acquire(blocking=False):
        if body.onlyIfNeeded:
            prior = read(root / "discovery-report.json", {})
            if prior:
                return {**prior, "ai": {**prior.get("ai", {}), "status": "Running"}}
        raise HTTPException(409, "Discovery is already running. Please retry shortly.")
    try:
        path = root / "discovery-report.json"
        prior = read(path, {})
        report = build(eng, root, prior)
        key = review_key(report)
        if body.useBedrock and (not body.onlyIfNeeded or prior.get("reviewKey") != key):
            report["ai"] = {"status": "Running", "interpretations": []}
            write(path, report)
            discovery_report.interpret(report, report["comments"])
            report["reviewKey"] = key
        elif prior.get("reviewKey") == key:
            report["reviewKey"] = key
        persist(root, report)
        return report
    finally:
        lock.release()


@router.post("/api/engagements/{eid}/discovery-comments")
def add_comment(eid: str, body: CommentIn):
    _, root, lock = context(eid)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Enter a comment before saving.")
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "Discovery is running. Save your comment when it completes.")
    try:
        path = root / "discovery-comments.json"
        comments = read(path, [])
        comments.append({"id": uuid.uuid4().hex, "section": body.section, "text": text, "at": discovery_report.now()})
        write(path, comments)
        return comments
    finally:
        lock.release()
