from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1] / "data"
ENG_DIR = ROOT / "engagements"
lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    ENG_DIR.mkdir(parents=True, exist_ok=True)


def engagement_dir(eid: str) -> Path:
    p = ENG_DIR / eid
    p.mkdir(parents=True, exist_ok=True)
    (p / "source").mkdir(exist_ok=True)
    (p / "artifacts").mkdir(exist_ok=True)
    return p


def path_for(eid: str) -> Path:
    return engagement_dir(eid) / "engagement.json"


def save(eng: dict[str, Any]) -> dict[str, Any]:
    ensure_dirs()
    eng["updatedAt"] = _now()
    with lock:
        path_for(eng["id"]).write_text(json.dumps(eng, indent=2), encoding="utf-8")
    return eng


def load(eid: str) -> dict[str, Any] | None:
    p = path_for(eid)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def list_all() -> list[dict[str, Any]]:
    ensure_dirs()
    items = []
    for d in ENG_DIR.iterdir():
        f = d / "engagement.json"
        if f.exists():
            items.append(json.loads(f.read_text(encoding="utf-8")))
    items.sort(key=lambda e: e.get("updatedAt", ""), reverse=True)
    return items
