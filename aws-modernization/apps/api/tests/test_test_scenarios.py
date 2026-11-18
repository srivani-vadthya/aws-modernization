"""Test Scenarios step: criteria -> scenarios / cases / Playwright project / coverage, plus the run and the gate."""
from app import phases, store, test_scenarios as ts

CRITERIA = [
    'Given the invoice has more than one line item, when the clerk submits it, then the invoice is saved with the status "Pending" (R1, R2)',
    'Given an invoice with the same invoice number already exists, when the clerk submits it, then the request is refused with the error "InvoiceNumber" (R3)',
    'Given the entered details are not valid, when the clerk submits the invoice, then the message "Check the details" is shown (R4)',
    "Given anything goes wrong while saving, when the clerk submits it, then an error is shown (R5)",
    "Given the invoice total is at least 100, when it is submitted, then approval is requested (R6)",
]


def _eng(criteria=CRITERIA):
    story = {"id": "US-1", "title": "As a clerk, I want to submit an invoice", "priority": "Must",
             "narrative": {"asA": "accounts clerk", "iWant": "to submit a new invoice", "soThat": "it is paid"},
             "acceptanceCriteria": list(criteria)}
    return {"id": "t1", "name": "Demo", "scope": {"name": "Invoices", "capabilityId": "inv"},
            "userStories": {"backlog": {"epics": [{"id": "EP-1", "title": "Invoicing", "features": [
                {"id": "FT-1", "title": "Submit invoice", "stories": [story]}]}]}}}


def test_step_sits_before_tests_and_parity():
    ids = phases.PHASE_IDS
    assert ids.index("test-scenarios") == ids.index("tests") - 1


def test_parse_and_classify():
    p = ts.parse_criterion(CRITERIA[0])
    assert p["refs"] == ["R1", "R2"] and p["then"].startswith("the invoice is saved")
    cats = [ts.classify(ts.parse_criterion(c)) for c in CRITERIA]
    assert cats == ["positive", "negative", "validation", "exception", "edge"]


def test_every_criterion_is_covered_and_literals_kept():
    m = ts.build(_eng())
    assert [s["criterionIndex"] for s in m["scenarios"] if s["origin"] == "criterion"] == [0, 1, 2, 3, 4]
    assert all(c["scenarioIds"] for s in m["coverage"] for c in s["criteria"]) and m["coverage"][0]["covered"]
    refused = next(c for c in m["cases"] if c["category"] == "negative")
    assert any('"InvoiceNumber"' in e for e in refused["expected"])
    assert all(c["preconditions"] and len(c["steps"]) >= 3 and c["expected"] for c in m["cases"])


def test_only_what_the_criteria_say(monkeypatch):
    monkeypatch.setattr(store, "save", lambda e: e)
    m = ts.build(_eng([CRITERIA[0]]))   # one criterion: exactly one scenario, no canned negative / boundary extras
    assert len(m["scenarios"]) == len(m["cases"]) == 1 and m["scenarios"][0]["category"] == "positive"


def test_sync_follows_the_stories_and_runs_the_checks(monkeypatch):
    monkeypatch.setattr(store, "save", lambda e: e)
    eng = _eng()
    ts.sync(eng)
    t = eng["testScenarios"]
    assert t["counts"]["cases"] == len(CRITERIA) and t["runs"][0]["summary"]["failed"] == 0
    eng["userStories"]["backlog"]["epics"][0]["features"][0]["stories"][0]["acceptanceCriteria"].pop()
    ts.sync(eng)                                                   # an edit rebuilds and re-checks
    assert eng["testScenarios"]["counts"]["cases"] == len(CRITERIA) - 1 and not ts.is_stale(eng)
    eng["userStories"]["backlog"]["epics"] = []
    ts.sync(eng)                                                   # no stories, no tests
    assert "testScenarios" not in eng


def test_playwright_project_and_run(monkeypatch):
    monkeypatch.setattr(store, "save", lambda e: e)
    eng = _eng()
    m = ts.build(eng)
    files = ts.playwright_files(eng, m)
    spec = files["specs/submit-invoice.spec.ts"]
    assert "playwright.config.ts" in files and "pages/AppPage.ts" in files
    assert '[TC-002]' in spec and 'app.expectText("InvoiceNumber")' in spec
    eng["testScenarios"] = {"generatedAt": "now", "sourceDigest": ts.source_digest(eng), **m, "files": files,
                            "counts": ts.counts(m), "runs": []}
    rec = ts.run(eng)
    assert rec["mode"] == "checks" and rec["summary"]["failed"] == 0 and rec["total"] == len(m["cases"])
    eng["testScenarios"]["files"]["specs/submit-invoice.spec.ts"] = "// emptied"
    assert ts.run(eng)["summary"]["failed"] == len(m["cases"])           # a missing script is reported, not hidden
    live = ts.run(eng, "http://localhost:9")                             # never simulated: reports what is missing
    assert live["liveStatus"] in {"setup-required", "unavailable", "failed", "completed"}
    assert not ts.is_stale(eng)
    eng["userStories"]["backlog"]["epics"][0]["features"][0]["stories"][0]["acceptanceCriteria"].append(CRITERIA[0])
    assert ts.is_stale(eng)
    assert b"PK" == ts.export_zip(eng)[:2] and "## Coverage matrix" in ts.export_markdown(eng)


def test_routes_and_gate(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main as api_main
    monkeypatch.setattr(store, "ENG_DIR", tmp_path)
    eng = _eng()
    eng["gates"] = {p: {"status": "pending", "decision": None, "comment": None, "actor": None, "at": None}
                    for p in phases.PHASE_IDS}
    eng["gates"]["modernize"].update(decision="approved", status="approved")
    store.save(eng)
    c = TestClient(api_main.app)
    gate = lambda: c.post("/api/engagements/t1/gates/test-scenarios", json={"decision": "approved"})
    assert gate().status_code == 400                                   # nothing generated yet
    assert c.post("/api/engagements/t1/test-scenarios/run").status_code == 400
    r = c.post("/api/engagements/t1/test-scenarios/generate")
    assert r.status_code == 200 and r.json()["stale"] is False and r.json()["testScenarios"]["counts"]["cases"] == 5
    assert r.json()["testScenarios"]["runs"][0]["mode"] == "checks"        # results are there on first open
    run = c.post("/api/engagements/t1/test-scenarios/run", json={}).json()["testScenarios"]["runs"][0]
    assert run["summary"]["failed"] == 0
    assert c.post("/api/engagements/t1/test-scenarios/run", json={"baseUrl": "not a url"}).status_code == 422
    assert c.get("/api/engagements/t1/test-scenarios/export?format=zip").content[:2] == b"PK"
    assert c.get("/api/engagements/t1/test-scenarios/export?format=md").text.startswith("# Test scenarios")
    r = gate()
    assert r.status_code == 200 and r.json()["currentPhase"] == "tests"  # next step is Tests & Parity
    assert (tmp_path / "t1" / "artifacts" / "tests" / "test-scenarios" / "playwright.config.ts").is_file()
