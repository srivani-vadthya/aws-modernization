import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import store
from app.main import app


def test_approved_modernize_gate_enters_code_modernization(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ENG_DIR", tmp_path / "engagements")
    eid = "facefeed1234"
    root = store.ENG_DIR / eid
    root.mkdir(parents=True)
    gates = {phase: {"status": "approved", "decision": "approved", "comment": None, "actor": "reviewer", "at": None}
             for phase in ("intake", "discovery", "graph", "scope", "semantic-ir", "user-stories", "modernize")}
    (root / "engagement.json").write_text(json.dumps({"id": eid, "name": "test", "gates": gates,
        "currentPhase": "modernize", "status": "modernize", "seed": {}}), encoding="utf-8")
    with TestClient(app) as client:
        response = client.post(f"/api/engagements/{eid}/gates/modernize", json={"decision": "approved", "actor": "reviewer"})
    assert response.status_code == 200
    assert response.json()["currentPhase"] == "code modernization"
