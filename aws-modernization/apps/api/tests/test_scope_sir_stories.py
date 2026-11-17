"""Scope modules -> SIR -> user stories -> tracker push, end to end on a small synthetic AKG/AST."""
from __future__ import annotations

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import scope_modules, sir_generator, store, user_stories
from app import main as api_main

CONTROLLER = """using System;
namespace App.Controllers
{
    public class OrderController
    {
        public ActionResult Create(OrderModel model, int? retries = null)
        {
            if (model.Total > 500)
            {
                throw new Exception("Order total exceeds limit 500");
            }
            var customer = Uow.Customers.GetAll().First();
            Uow.Orders.Add(model);
            Uow.SaveChanges();
            return View();
        }
    }
}
"""


def _seed() -> dict:
    nodes = [
        {"id": "CAP-orders", "label": "Orders", "type": "capability", "capability": "orders"},
        {"id": "CAP-billing", "label": "Billing", "type": "capability", "capability": "billing"},
        {"id": "App.Controllers.OrderController", "label": "OrderController", "type": "program", "role": "controller",
         "file": "App/Controllers/OrderController.cs", "line": 4, "loc": 14, "capability": "orders"},
        {"id": "App.Models.Order", "label": "Order", "type": "entity", "file": "App/Models/Order.cs", "line": 3,
         "loc": 8, "capability": "orders"},
        {"id": "App.Models.Customer", "label": "Customer", "type": "entity", "file": "App/Models/Customer.cs",
         "line": 3, "loc": 8, "capability": "billing"},
        {"id": "App.Billing.InvoiceService", "label": "InvoiceService", "type": "program",
         "file": "App/Billing/InvoiceService.cs", "line": 1, "loc": 30, "capability": "billing"},
    ]
    edges = [{"id": "ref1", "source": "App.Models.Order", "target": "App.Models.Customer", "kind": "REFERENCES",
              "file": "App/Models/Order.cs", "line": 5}]
    workflow = {
        "id": "WF:App.Controllers.OrderController.Create", "entryPoint": "App.Controllers.OrderController.Create",
        "entryKind": "controller-action", "trigger": None, "reads": ["App.Models.Customer"],
        "writes": ["App.Models.Order"], "externals": [], "events": [], "depth": 1, "fullyTraced": True,
        "file": "App/Controllers/OrderController.cs", "line": 6,
        "steps": [
            {"from": "App.Controllers.OrderController.Create", "kind": "ACCESSES_DATA", "to": "App.Models.Customer",
             "file": "App/Controllers/OrderController.cs", "line": 11, "depth": 1, "operation": "read"},
            {"from": "App.Controllers.OrderController.Create", "kind": "ACCESSES_DATA", "to": "App.Models.Order",
             "file": "App/Controllers/OrderController.cs", "line": 12, "depth": 1, "operation": "write"},
            {"from": "App.Controllers.OrderController.Create", "kind": "CALLS", "to": "App.Data.Uow.SaveChanges",
             "file": "App/Controllers/OrderController.cs", "line": 13, "depth": 1},
        ]}
    caps = [{"id": "orders", "name": "Orders", "summary": "2 types", "programs": 1, "tables": 1, "screens": 0,
             "risk": "low", "coupling": "1 outgoing"},
            {"id": "billing", "name": "Billing", "summary": "2 types", "programs": 1, "tables": 1, "screens": 0,
             "risk": "low", "coupling": "0"}]
    return {"graph": {"nodes": nodes, "edges": edges, "evidenceRequired": True},
            "dotnet_akg": {"codeWorkflows": [workflow], "sharedKernels": [], "dataLineage": []},
            "capabilities": caps, "programs": [], "tables": [], "semantic_ir": [], "requirements": [],
            "backlog": [], "tests": []}


@pytest.fixture()
def eng(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ENG_DIR", tmp_path / "engagements")
    monkeypatch.setattr(store, "ROOT", tmp_path)
    e = {"id": "eng1", "name": "demo", "sourceType": "git", "currentPhase": "scope", "status": "scope",
         "gates": {}, "inventory": {"assets": []}, "seed": _seed(), "scope": None}
    src = store.engagement_dir("eng1") / "source" / "App" / "Controllers"
    src.mkdir(parents=True)
    (src / "OrderController.cs").write_text(CONTROLLER, encoding="utf-8")
    seed = e["seed"]
    seed["programs"] = [{"id": n["id"], "name": n["label"], "capability": n["capability"], "loc": n.get("loc", 0),
                         "path": n.get("file")} for n in seed["graph"]["nodes"] if n["type"] == "program"]
    seed["tables"] = [{"id": n["id"], "name": n["label"], "capability": n["capability"], "path": n.get("file")}
                      for n in seed["graph"]["nodes"] if n["type"] == "entity"]
    return api_main._ensure_gates(e)


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Tests never reach a model unless they install a stub."""
    for mod in (scope_modules, sir_generator, user_stories):
        monkeypatch.setattr(mod, "ask_json", lambda *a, **k: (None, None))


# ------------------------------------------------------------------ scope modules

def test_scope_modules_are_derived_from_graph_with_files_and_use_cases(eng):
    result = scope_modules.build_scope_modules(eng, use_llm=False)
    mods = {m["id"]: m for m in result["modules"]}
    assert set(mods) == {"orders", "billing"}
    orders = mods["orders"]
    assert orders["metrics"]["useCases"] == 1
    assert orders["useCases"][0]["writes"] == ["Order"] and orders["useCases"][0]["reads"] == ["Customer"]
    assert {f["path"] for f in orders["files"]} == {"App/Controllers/OrderController.cs", "App/Models/Order.cs"}
    assert orders["dependsOn"] == ["Billing"]
    assert result["enrichment"]["status"] == "deterministic"


def test_scope_modules_llm_wording_is_cached_and_cannot_add_files(eng, monkeypatch):
    calls = []

    def fake(system, user, **kw):
        calls.append(1)
        return ([{"id": "orders", "displayName": "Order Capture", "businessSummary": "Takes customer orders.",
                  "useCases": [{"ref": 0, "name": "Place an order", "description": "Order is stored."}],
                  "files": ["/etc/passwd"]}], "model-x")

    monkeypatch.setattr(scope_modules, "ask_json", fake)
    first = scope_modules.build_scope_modules(eng)
    orders = next(m for m in first["modules"] if m["id"] == "orders")
    assert orders["displayName"] == "Order Capture" and orders["useCases"][0]["name"] == "Place an order"
    assert all(f["path"] != "/etc/passwd" for f in orders["files"])
    again = scope_modules.build_scope_modules(eng)
    assert len(calls) == 1, "a successful LLM pass must be cached until the graph changes"
    assert next(m for m in again["modules"] if m["id"] == "orders")["displayName"] == "Order Capture"


def test_module_summary_prompt_includes_key_ast_conditions(eng, monkeypatch):
    seen = []
    monkeypatch.setattr(scope_modules, "ask_json", lambda system, user, **kw: (seen.append(user), (None, None))[1])
    scope_modules.build_scope_modules(eng)
    facts = json.loads(seen[0].split("FACTS:" + chr(10), 1)[1])
    orders = next(m for m in facts if m["id"] == "orders")
    assert any("model.Total > 500" in c for c in orders["useCases"][0]["keyConditions"])


# ------------------------------------------------------------------ SIR

def test_sir_scaffold_is_ast_anchored(eng):
    contracts, meta = sir_generator.build_contracts(eng, "orders", use_llm=False)
    assert meta["llm"]["status"] == "skipped" and len(contracts) == 1
    c = contracts[0]
    assert c["id"] == "SIR-001" and c["module"] == "orders" and c["origin"] == "deterministic"
    assert c["inputs"][0] == {"name": "model", "type": "OrderModel", "required": True}
    assert c["inputs"][1]["required"] is False
    write = next(r for r in c["rules"] if r["astNode"].endswith(":WRITES"))
    assert write["legacyLines"] == "App/Controllers/OrderController.cs#L12"
    assert "Uow.Orders.Add(model)" in write["snippet"]
    assert write["trustBoundary"].startswith("Deterministic")
    guard = next(r for r in c["rules"] if r["astNode"].endswith(":BRANCH"))
    assert "model.Total > 500" in guard["statement"]
    plumbing = next(r for r in c["rules"] if "SaveChanges" in r["statement"])
    assert plumbing["kind"] == "legacy_plumbing_pruned"
    assert c["stateMachine"].startswith("RECEIVE_REQUEST -> ") and c["stateMachine"].endswith("COMPLETE")
    assert "Persists changes to Order" in c["sideEffects"]


def test_llm_lifting_changes_wording_only(eng, monkeypatch):
    def fake(system, user, **kw):
        payload = json.loads(user.split("CONTRACTS:\n", 1)[1])
        c = payload[0]
        return ([{"id": c["id"], "name": "Place Order", "summary": "Accept and store a customer order.",
                  "stateMachine": "not a valid machine!!", "sideEffects": ["Order is stored"],
                  "rules": [{"ref": r["ref"], "statement": f"Meaning of {r['ref']}", "classification": "Validation",
                             "kind": "legacy_plumbing_pruned",
                             "legacyLines": "HACKED#L1", "snippet": "HACKED"} for r in c["rules"]]}], "model-x")

    monkeypatch.setattr(sir_generator, "ask_json", fake)
    before, _ = sir_generator.build_contracts(eng, "orders", use_llm=False)
    after, meta = sir_generator.build_contracts(eng, "orders", use_llm=True)
    assert meta["llm"]["status"] == "ok" and after[0]["origin"] == "llm" and after[0]["name"] == "Place Order"
    assert after[0]["stateMachine"] == before[0]["stateMachine"], "invalid LLM state machine must be ignored"
    for b, a in zip(before[0]["rules"], after[0]["rules"]):
        assert (b["legacyLines"], b["snippet"], b["astNode"]) == (a["legacyLines"], a["snippet"], a["astNode"])
        assert a["statement"].startswith("Meaning of") and a["source"] == "llm"
    write = next(r for r in after[0]["rules"] if r["astNode"].endswith(":WRITES"))
    assert write["kind"] == "deterministic_business_rule", "LLM may not demote a data write to plumbing"


def test_generate_persists_and_regeneration_keeps_other_modules(eng):
    eng["scope"] = {"capabilityId": "orders", "name": "Orders"}
    eng["seed"]["semantic_ir"] = [{"id": "SIR-001", "module": "billing", "name": "x", "rules": []}]
    out = sir_generator.generate(eng, use_llm=False)
    mods = sorted(s["module"] for s in out["seed"]["semantic_ir"])
    assert mods == ["billing", "orders"]
    assert next(s for s in out["seed"]["semantic_ir"] if s["module"] == "orders")["id"] == "SIR-002"
    again = sir_generator.generate(out, use_llm=False)  # no force: unchanged
    assert again["sirMeta"]["generatedAt"] == out["sirMeta"]["generatedAt"]


# ------------------------------------------------------------------ user stories

def _with_sir(eng):
    eng["scope"] = {"capabilityId": "orders", "name": "Orders"}
    return sir_generator.generate(eng, use_llm=False)


def test_backlog_scaffold_covers_every_rule_and_validates(eng):
    eng = _with_sir(eng)
    out = user_stories.generate(eng, refine=False)
    us = out["userStories"]
    backlog, sir = us["backlog"], eng["seed"]["semantic_ir"][0]
    stories = [s for _, _, s in user_stories.bm.iter_stories(backlog)]
    functional = [s for s in stories if s["type"] == "functional"]
    business = [r for r in sir["rules"] if r["kind"] != "legacy_plumbing_pruned"]
    assert len(functional) == len(business)
    assert {s["type"] for s in stories} == {"functional", "flow", "enabler"}
    assert not [i for i in us["validation"] if i["level"] == "ERROR"]
    assert all(s["narrativeSource"] == "template" for s in stories)
    for f in ("backlog.json", "backlog.md", "sir.json", "scripts/push_backlog.py"):
        assert (store.engagement_dir("eng1") / "artifacts" / "user-stories" / f).is_file()


def test_llm_refinement_keeps_trace_and_rejects_dropped_literals(eng, monkeypatch):
    eng = _with_sir(eng)
    guard_story = {}

    def fake(system, user, **kw):
        if "EPIC" in system:
            return ({"title": "Order Management", "description": "Orders are captured.",
                     "businessOutcome": "Faster order intake.", "persona": "sales clerk"}, "m")
        view = json.loads(user.split("INPUT:\n", 1)[1])
        stories = []
        for s in view["stories"]:
            rule = s["rule"]
            ac = ["Scenario: Order within the limit\n  Given an order totalling 100\n  When it is submitted\n  Then it is stored"]
            if rule.get("statement", "").startswith("Persists changes"):   # deterministic core, no literal to keep
                ac = ["Scenario: Order stored\n  Given a valid order\n  When it is submitted\n  Then it is persisted"]
            stories.append({"id": s["id"], "title": "Refined " + s["id"], "narrative": {
                "asA": "sales clerk", "iWant": "to submit orders", "soThat": "customers are served"},
                "description": "d", "acceptanceCriteria": ac, "storyPoints": 13, "priority": "Must",
                "labels": ["ok-label", "bad label!"], "trace": {"ruleId": "HACKED"}})
            if "Branches on" in (rule.get("statement") or ""):
                guard_story["id"] = s["id"]
        return ({"feature": {"title": "Place order", "description": "Order placement."}, "stories": stories,
                 "openQuestions": [{"storyId": None, "question": "Is 500 inclusive?"}]}, "m")

    monkeypatch.setattr(user_stories, "ask_json", fake)
    out = user_stories.generate(eng, refine=True)
    us = out["userStories"]
    backlog = us["backlog"]
    assert backlog["epics"][0]["title"] == "Order Management"
    assert backlog["epics"][0]["businessOutcome"] == "Faster order intake."
    stories = {s["id"]: s for _, _, s in user_stories.bm.iter_stories(backlog)}
    sir = eng["seed"]["semantic_ir"][0]
    assert stories["US-SIR-001-02"]["trace"]["ruleId"] == sir["rules"][1]["ruleId"]
    assert max(s["storyPoints"] for s in stories.values()) <= 8
    assert all("bad label!" not in s["labels"] for s in stories.values())
    refined = [s for s in stories.values() if s["narrativeSource"] == "refined"]
    assert refined and us["refinement"]["status"] in ("llm", "partial")
    assert any("Is 500 inclusive?" == q["question"] for q in backlog["openQuestions"])


def test_literal_guard_rejects_rewrite_that_drops_a_number():
    story = {"title": "t", "narrative": {"asA": "a", "iWant": "i", "soThat": "s"}, "description": "d",
             "acceptanceCriteria": ["Scenario: x"], "storyPoints": 3, "priority": "Must", "labels": [],
             "narrativeSource": "template"}
    rule = {"statement": "Reject orders over 500", "snippet": "", "trustBoundary": "Deterministic Core (x)"}
    upd = {"title": "T", "narrative": {"asA": "a", "iWant": "i", "soThat": "s"}, "description": "d",
           "acceptanceCriteria": ["Scenario: large orders\n  Then they are rejected"], "storyPoints": 3}
    assert "500" in user_stories._apply_story(dict(story), upd, rule)
    assert story["narrativeSource"] == "template"
    upd["acceptanceCriteria"] = ["Scenario: large orders\n  Then orders over 500 are rejected"]
    s2 = dict(story)
    assert user_stories._apply_story(s2, upd, rule) is None and s2["narrativeSource"] == "refined"


# ------------------------------------------------------------------ tracker push

def _calls_http(log, fail_on=None):
    counter = {"n": 100}

    def http(method, url, headers, body):
        log.append((method, url, headers, body))
        if fail_on and fail_on in json.dumps(body):
            return 400, {"errorMessages": ["boom"]}
        counter["n"] += 1
        n = counter["n"]
        if "atlassian" in url:
            return 201, {"id": str(n), "key": f"MOD-{n}"}
        if "dev.azure.com" in url:
            return 200, {"id": n, "url": f"https://dev.azure.com/o/_apis/wit/workItems/{n}"}
        if "bitbucket" in url:
            return 201, {"id": n, "links": {"html": {"href": f"https://bitbucket.org/w/r/issues/{n}"}}}
        if url.endswith("/sub_issues"):
            return 201, {}
        return 201, {"id": n * 10, "number": n, "html_url": f"https://github.com/o/r/issues/{n}"}
    return http


@pytest.fixture()
def backlog(eng):
    eng = _with_sir(eng)
    b = user_stories.generate(eng, refine=False)["userStories"]["backlog"]
    for _, _, s in user_stories.bm.iter_stories(b):
        s["narrativeSource"] = "refined"
    return b


ENVS = {
    "jira": {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_PROJECT_KEY": "MOD", "JIRA_EMAIL": "a@b.c",
             "JIRA_API_TOKEN": "tok"},
    "ado": {"ADO_ORG": "o", "ADO_PROJECT": "p", "ADO_PAT": "pat"},
    "bitbucket": {"BITBUCKET_WORKSPACE": "w", "BITBUCKET_REPO": "r", "BITBUCKET_TOKEN": "t"},
    "github": {"GITHUB_REPO": "o/r", "GITHUB_TOKEN": "t"},
}


def test_provider_status_never_leaks_secrets():
    st = {p["id"]: p for p in user_stories.pb.provider_status({}, dict(ENVS["jira"]))}
    assert st["jira"]["configured"] and not st["ado"]["configured"]
    assert "tok" not in json.dumps(st) and st["jira"]["secrets"] == {"JIRA_API_TOKEN": True}
    assert "ADO_PAT" in st["ado"]["missing"]


def test_dry_run_sends_nothing_and_apply_requires_configuration(backlog):
    pb = user_stories.pb
    log: list = []
    rep = pb.push(backlog, "jira", {}, {}, http=_calls_http(log))
    assert not log and not rep["ready"] and rep["summary"]["create"] > 0
    with pytest.raises(pb.PushError, match="not configured"):
        pb.push(backlog, "jira", {}, {}, apply=True, http=_calls_http(log))


def test_jira_label_mode_links_stories_to_epic(backlog):
    pb, log = user_stories.pb, []
    rep = pb.push(backlog, "jira", {}, ENVS["jira"], apply=True, http=_calls_http(log))
    assert rep["summary"].get("folded") == 1 and "failed" not in rep["summary"]
    epic_key = next(r["key"] for r in rep["rows"] if r["level"] == "epic")
    story_calls = [c for c in log if c[3]["fields"]["issuetype"]["name"] == "Story"]
    assert story_calls and all(c[3]["fields"]["parent"] == {"key": epic_key} for c in story_calls)
    assert all(any(lbl.startswith("feature-FT-") for lbl in c[3]["fields"]["labels"]) for c in story_calls)
    assert log[0][2]["Authorization"].startswith("Basic ")


def test_ado_hierarchy_and_idempotent_rerun(backlog):
    pb, log, state = user_stories.pb, [], {}
    rep = pb.push(backlog, "ado", {}, ENVS["ado"], apply=True, http=_calls_http(log), state=state)
    types = [c[1].split("workitems/$")[1].split("?")[0] for c in log]
    assert types[0] == "Epic" and types[1] == "Feature" and set(types[2:]) == {"User%20Story"}
    rel = log[2][3][-1]["value"]
    assert rel["rel"] == "System.LinkTypes.Hierarchy-Reverse" and "workItems/" in rel["url"]
    created = len(log)
    rep2 = pb.push(backlog, "ado", {}, ENVS["ado"], apply=True, http=_calls_http(log), state=state)
    assert len(log) == created and rep2["summary"] == {"exists": created}


def test_failed_parent_skips_children_and_template_stories_are_blocked(backlog):
    pb, log = user_stories.pb, []
    rep = pb.push(backlog, "github", {}, ENVS["github"], apply=True, http=_calls_http(log, fail_on='"labels": ["epic"'))
    assert rep["summary"]["failed"] == 1 and rep["summary"]["skipped"] == len(rep["rows"]) - 1
    next(s for _, _, s in user_stories.bm.iter_stories(backlog))["narrativeSource"] = "template"
    rep = pb.push(backlog, "bitbucket", {}, ENVS["bitbucket"], http=_calls_http([]))
    assert rep["summary"]["blocked"] == 1


def test_github_sub_issue_link_and_only_selection(backlog):
    pb, log = user_stories.pb, []
    story_id = next(s["id"] for _, _, s in user_stories.bm.iter_stories(backlog))
    rep = pb.push(backlog, "github", {}, ENVS["github"], apply=True, only=[story_id], http=_calls_http(log))
    assert [r["level"] for r in rep["rows"]] == ["epic", "feature", "story"]
    assert sum(1 for c in log if c[1].endswith("/sub_issues")) == 2
    with pytest.raises(pb.PushError, match="unknown item"):
        pb.push(backlog, "github", {}, ENVS["github"], only=["nope"])


def test_credentials_are_only_sent_over_https(backlog):
    pb = user_stories.pb
    with pytest.raises(pb.PushError, match="non-https"):
        pb.http_request("POST", "http://evil.example.com/x", {"Authorization": "x"}, {})


def test_real_http_path_against_local_server(backlog):
    pb = user_stories.pb
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, self.headers["Authorization"], body))
            out = json.dumps({"id": len(seen), "key": f"MOD-{len(seen)}"}).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        env = {**ENVS["jira"], "JIRA_BASE_URL": f"http://127.0.0.1:{srv.server_port}"}
        rep = pb.push(backlog, "jira", {}, env, apply=True)
    finally:
        srv.shutdown()
    assert "failed" not in rep["summary"] and seen[0][0] == "/rest/api/3/issue"


# ------------------------------------------------------------------ API + gates

def test_gate_flow_scope_to_user_stories(eng, monkeypatch):
    monkeypatch.setattr(api_main.bedrock_skills, "extract_dynamic_requirements", lambda *a, **k: None)
    monkeypatch.setattr(api_main.playwright_gen, "generate_playwright_suite", lambda *a, **k: {})
    store.save(eng)
    client = TestClient(api_main.app)
    eid = eng["id"]
    mods = client.get(f"/api/engagements/{eid}/scope-modules?llm=false").json()
    assert {m["id"] for m in mods["modules"]} == {"orders", "billing"}

    assert client.post(f"/api/engagements/{eid}/scope", json={"capabilityId": "orders"}).status_code == 200
    scoped = client.get(f"/api/engagements/{eid}").json()["scope"]
    assert scoped["sharedServices"] == [], "no fabricated shared services"
    assert {f["path"] for f in scoped["files"]} >= {"App/Models/Order.cs"}

    client.post(f"/api/engagements/{eid}/gates/discovery", json={"decision": "approved"})  # may be 4xx; irrelevant
    e = store.load(eid)
    e["gates"]["discovery"].update(decision="approved", status="approved")
    store.save(e)
    r = client.post(f"/api/engagements/{eid}/gates/scope", json={"decision": "approved"})
    assert r.status_code == 200 and r.json()["currentPhase"] == "semantic-ir"
    assert r.json()["gates"]["semantic-ir"]["decision"] is None, "SIR must be reviewed, not auto-approved"

    assert client.post(f"/api/engagements/{eid}/gates/semantic-ir", json={"decision": "approved"}).status_code == 400
    sir = client.post(f"/api/engagements/{eid}/semantic-ir/generate", json={"llm": False})
    assert sir.status_code == 200 and sir.json()["seed"]["semantic_ir"][0]["module"] == "orders"
    r = client.post(f"/api/engagements/{eid}/gates/semantic-ir", json={"decision": "approved"})
    assert r.status_code == 200 and r.json()["currentPhase"] == "user-stories"

    assert client.post(f"/api/engagements/{eid}/gates/user-stories", json={"decision": "approved"}).status_code == 400
    assert client.post(f"/api/engagements/{eid}/gates/requirements", json={"decision": "approved"}).status_code == 400
    gen = client.post(f"/api/engagements/{eid}/user-stories/generate", json={"refine": False})
    assert gen.status_code == 200 and gen.json()["userStories"]["counts"]["stories"] > 0
    r = client.post(f"/api/engagements/{eid}/gates/user-stories", json={"decision": "approved"})
    assert r.status_code == 200 and r.json()["currentPhase"] == "requirements"

    dry = client.post(f"/api/engagements/{eid}/user-stories/push",
                      json={"provider": "github", "allowTemplate": True})
    assert dry.status_code == 200 and dry.json()["apply"] is False and dry.json()["rows"][0]["payload"]
    assert client.post(f"/api/engagements/{eid}/user-stories/push",
                       json={"provider": "github", "apply": True}).status_code == 400  # needs confirm
    assert client.get("/api/integrations").status_code == 200
    assert client.get(f"/api/engagements/{eid}/user-stories/export?format=md").text.startswith("# Backlog")

    # picking a different scope invalidates the downstream artifacts and sign-offs
    client.post(f"/api/engagements/{eid}/scope", json={"capabilityId": "billing"})
    after = client.get(f"/api/engagements/{eid}").json()
    assert after.get("userStories") is None and after["gates"]["semantic-ir"]["decision"] is None


def test_legacy_engagement_without_user_story_gate_is_backfilled(eng):
    legacy = copy.deepcopy(eng)
    legacy["gates"].pop("user-stories")
    store.save(legacy)
    got = TestClient(api_main.app).get(f"/api/engagements/{legacy['id']}").json()
    assert got["gates"]["user-stories"]["status"] == "pending"
