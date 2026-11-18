"""Scope modules -> SIR -> user stories -> tracker push, end to end on a small synthetic AKG/AST."""
from __future__ import annotations

import copy
import json
import re
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
    # C#: each decision is a rule with its condition AND its outcome, anchored to the line of the outcome
    decisions = [r for r in c["rules"] if r["astNode"].endswith(":DECIDES")]
    assert [(d["logic"]["when"], d["logic"]["then"]) for d in decisions] == [
        ([{"code": "model.Total > 500", "negated": False}], [{"type": "throw", "message": "Order total exceeds limit 500"}]),
        ([{"code": "model.Total > 500", "negated": True}],      # after the guard clause: only when it passed
         [{"type": "data", "op": "add", "entity": "Orders", "args": ["model"]}])]
    assert decisions[0]["legacyLines"] == "App/Controllers/OrderController.cs#L10"
    assert 'throw new Exception("Order total exceeds limit 500")' in decisions[0]["snippet"]
    assert decisions[0]["trustBoundary"].startswith("Deterministic")
    assert not [r for r in c["rules"] if r["astNode"].endswith(":BRANCH")], "decisions replace the bare condition list"
    assert c["businessLogic"]["entry"] == "Create"
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
    business = [r["ruleId"] for r in sir["rules"] if r["kind"] != "legacy_plumbing_pruned"]
    assert [s["id"] for s in stories] == [f"US-{sir['id']}"], "one story per use case"
    story = stories[0]
    assert story["trace"]["ruleIds"] == business, "every business rule is traced, plumbing is not"
    assert user_stories.cited_rules(story["acceptanceCriteria"]) == {user_stories.sts.short_id(r) for r in business}
    assert len(story["acceptanceCriteria"]) <= user_stories.sts.MAX_CRITERIA
    assert [f["title"] for _, f in user_stories.bm.iter_features(backlog)] == ["Order"], "feature = business area"
    assert not [i for i in us["validation"] if i["level"] == "ERROR"]
    assert story["narrativeSource"] == "template"
    for f in ("backlog.json", "backlog.md", "sir.json", "scripts/push_backlog.py"):
        assert (store.engagement_dir("eng1") / "artifacts" / "user-stories" / f).is_file()


def test_llm_refinement_keeps_trace_and_rejects_dropped_literals(eng, monkeypatch):
    eng = _with_sir(eng)
    seen_views = []

    def fake(system, user, **kw):
        if "EPIC" in system:
            return ({"title": "Order Management", "description": "Orders are captured.",
                     "businessOutcome": "Faster order intake.", "persona": "sales clerk"}, "m")
        view = json.loads(user.split("INPUT:\n", 1)[1])
        seen_views.append(view)
        stories = [{"id": s["id"], "title": "ignored", "narrative": {
            "asA": "sales clerk", "iWant": "to place an order", "soThat": "the customer is served"},
            "description": "The clerk places an order.",
            "acceptanceCriteria": [
                'Given an order over 500, when it is placed, then it is refused with "Order total exceeds limit 500" (R1)',
                "Given a valid order, when it is placed, then it is stored (R2)",
                "Given the same order in the current and the new system, when both complete, then the result is "
                "identical (R1-R4)"],
            "storyPoints": 13, "priority": "Must", "labels": ["ordering", "bad label!"], "trace": {"ruleId": "HACKED"}}
            for s in view["stories"]]
        return ({"feature": {"title": "Ordering", "description": "Order placement."}, "stories": stories,
                 "openQuestions": [{"storyId": None, "question": "Is 500 inclusive?"}]}, "m")

    monkeypatch.setattr(user_stories, "ask_json", fake)
    out = user_stories.generate(eng, refine=True)
    us = out["userStories"]
    backlog = us["backlog"]
    assert backlog["epics"][0]["title"] == "Order Management"
    story = next(user_stories.bm.iter_stories(backlog))[2]
    sir = eng["seed"]["semantic_ir"][0]
    assert story["trace"]["ruleIds"] == [r["ruleId"] for r in sir["rules"] if r["kind"] != "legacy_plumbing_pruned"]
    assert story["title"] == "As a sales clerk, I want to place an order so that the customer is served"
    base = story["estimation"]["points"]
    assert story["storyPoints"] == next(f for f in user_stories.bm.FIBONACCI if f > base), "one step up at most"
    assert story["labels"] == ["ordering", "reference-story"] or story["labels"] == ["ordering"]
    assert story["narrativeSource"] == "refined" and us["refinement"]["status"] == "llm"
    assert any("Is 500 inclusive?" == q["question"] for q in backlog["openQuestions"])
    rules = seen_views[0]["stories"][0]["rules"]   # the model sees short ids, rule kinds and each decision's meaning
    assert [r["id"] for r in rules] == ["R1", "R2", "R3", "R4"]
    assert [r["kind"] for r in rules] == ["decision", "decision", "write", "read"]
    assert rules[0]["meaning"] == 'if the total is more than 500, the message "Order total exceeds limit 500" is shown'
    assert rules[1]["meaning"] == "if the total is at most 500, the order is added"


def test_literal_guard_rejects_rewrite_that_drops_a_number():
    story = {"title": "t", "narrative": {"asA": "a", "iWant": "i", "soThat": "s"}, "description": "d",
             "acceptanceCriteria": ["Given x, when y, then z (R1)"], "storyPoints": 3, "priority": "Must",
             "labels": [], "narrativeSource": "template"}
    rule = {"ruleId": "S.R1", "statement": "Reject orders over 500", "snippet": "",
            "trustBoundary": "Deterministic Core (x)"}
    upd = {"narrative": {"asA": "a", "iWant": "i", "soThat": "s"}, "description": "d",
           "acceptanceCriteria": ["Given a large order, when it is placed, then it is rejected (R1)"], "storyPoints": 3}
    assert "500" in user_stories._apply_story(dict(story), upd, rule)
    assert story["narrativeSource"] == "template"
    upd["acceptanceCriteria"] = ["Given an order over 500, when it is placed, then it is rejected (R1)"]
    s2 = dict(story)
    assert user_stories._apply_story(s2, upd, rule) is None and s2["narrativeSource"] == "refined"
    # a story groups several rules: the guard checks every core rule, not just the first one
    plain = {"ruleId": "S.R2", "statement": "Branches on x", "snippet": "", "trustBoundary": "Application Logic"}
    upd["acceptanceCriteria"] = ["Given a large order, when it is placed, then it is rejected (R1, R2)"]
    assert "500" in user_stories._apply_story(dict(story), upd, [plain, rule])


def test_rewrite_that_drops_a_rule_is_rejected():
    story = {"title": "t", "narrative": {"asA": "a", "iWant": "i", "soThat": "s"}, "description": "d",
             "acceptanceCriteria": ["Given x, when y, then z (R1-R4)"], "storyPoints": 3, "priority": "Must",
             "labels": [], "narrativeSource": "template"}
    rules = [{"ruleId": f"S.R{i}", "statement": "Persists changes to Order", "trustBoundary": "x"} for i in range(1, 5)]
    upd = {"narrative": {"asA": "a", "iWant": "i", "soThat": "s"}, "description": "d",
           "acceptanceCriteria": ["Given an order, when it is placed, then it is stored (R1, R2)"]}
    assert user_stories._apply_story(dict(story), upd, rules) == "acceptance criteria do not cover rule(s) R3, R4"
    upd["acceptanceCriteria"] = ["Given an order, when it is placed, then it is stored (R1, R2–R4)"]
    assert user_stories._apply_story(dict(story), upd, rules) is None, "ranges with an en dash count"
    upd["acceptanceCriteria"] = ["Given an order, when it is placed, then it is stored (R1-R4)"]
    assert user_stories._apply_story(dict(story), upd, rules) is None, "ranges with a hyphen count"


def _rule(n, cls, stmt, node, **extra):
    return {"ruleId": f"SIR-007.R{n}", "kind": "deterministic_business_rule", "classification": cls,
            "statement": stmt, "astNode": node, "trustBoundary": extra.pop("tb", "Application Logic"),
            "legacyLines": f"A.cs#L{n}", "snippet": "", **extra}


def _invoice_post():
    """Shaped like the real 'Invoice: Post' contract: checks, writes in helper methods, email, internal calls."""
    return {"id": "SIR-007", "module": "invoice", "name": "Invoice: Post", "summary": "x",
            "sideEffects": ["Persists changes to Invoice"], "inputs": [{"name": "model"}],
            "legacyAssessment": {"regressionScope": ["Invoice: Edit"], "factors": []},
            "rules": [
                _rule(1, "Validation / Control Flow", "Validates the request before processing: ...",
                      "AST:InvoiceApiController.Post:L50:BRANCH",
                      conditions=["if (model.Particulars.Count > 1)", 'if (model.Status == "pending")',
                                  "if (entity.Id == 0)"]),
                _rule(2, "State Mutation", "Persists changes to Invoice", "AST:InvoiceApiController.CreateNew:L9:WRITES",
                      tb="Deterministic Core (x)"),
                _rule(3, "State Mutation", "Persists changes to Particular", "AST:InvoiceApiController.Save:L9:WRITES",
                      tb="Deterministic Core (x)"),
                _rule(4, "External Integration", "Calls external dependency SmtpClient",
                      "AST:EmailService.Send:L24:INVOKES_EXTERNAL"),
                _rule(5, "Orchestration", "Delegates to InvoiceApiController.GetInvoiceStatusId",
                      "AST:InvoiceApiController.Post:L46:CALLS"),
                _rule(6, "Orchestration", "Delegates to InvoiceApiController.GetParticularTypeId",
                      "AST:InvoiceApiController.Post:L48:CALLS"),
                _rule(7, "Legacy Plumbing", "Infrastructure call ApplicationUnit.SaveChanges",
                      "AST:InvoiceApiController.Post:L60:CALLS", kind="legacy_plumbing_pruned")]}


def test_one_story_per_use_case_in_business_language():
    sts = user_stories.sts
    sir = _invoice_post()
    backlog = sts.build_backlog([sir], module_names={"invoice": "Invoice"})
    (_, feature, story), = list(user_stories.bm.iter_stories(backlog))
    assert feature["title"] == "Invoice" and story["behaviour"] == "Invoice: Post"
    assert story["title"] == ("As a business user, I want to create an invoice so that the invoice and particular "
                              "records are saved and the right people are notified by email")
    ac = story["acceptanceCriteria"]
    assert ac[:5] == [   # every business check is named, one criterion each
        "Given there is more than 1 particular, when the invoice is submitted, then the outcome is the same as today (R1)",
        'Given the status is "pending", when the invoice is submitted, then the outcome is the same as today (R1)',
        "Given the invoice has not been saved yet, when the invoice is submitted, then the outcome is the same as "
        "today (R1)",
        "Given a new invoice that passes every check, when the invoice is submitted, then the invoice and particular "
        "records are saved (R2–R3)",
        "Given a new invoice that passes every check, when the invoice is submitted, then an email notification is "
        "sent (R4)"]
    assert "Invoice: Edit" in ac[5] and ac[6].endswith("then the result is identical (R1–R6)") and len(ac) == 7
    assert ('Business checks, applied exactly as today: there is more than 1 particular; the status is "pending"; '
            "the invoice has not been saved yet.") in story["description"]
    text = " ".join([story["title"], story["description"], *ac])
    assert not re.search(r"\b\d+ business checks?\b", text), "checks are named, never just counted"
    for code in ("Delegates", "Controller", "GetInvoiceStatusId", "SmtpClient", "model.", "if (", "SIR-007"):
        assert code not in text, f"technical detail leaked: {code}"
    assert story["labels"][:3] == ["invoice", "create", "notification"]   # + "reference-story": the only story
    assert story["trace"]["ruleIds"] == [f"SIR-007.R{i}" for i in range(1, 7)], "plumbing (R7) is not traced"


def test_technical_only_use_cases_produce_no_story():
    sts = user_stories.sts
    wiring = {"id": "SIR-001", "module": "platform", "name": "ApplicationUnit", "rules": [
        _rule(i, "Orchestration", f"Calls {name}", f"AST:ApplicationUnit:L{i}:CALLS")
        for i, name in enumerate(["DataContext", "ClaimRepository", "ClientRepository"], 1)]}
    with pytest.raises(ValueError, match="only technical code"):
        sts.build_backlog([wiring])
    backlog = sts.build_backlog([wiring, _invoice_post()])
    assert [s["id"] for _, _, s in user_stories.bm.iter_stories(backlog)] == ["US-SIR-007"]


def test_same_action_twice_raises_a_question_and_reads_are_shown():
    sts = user_stories.sts
    api, page = _invoice_post(), _invoice_post()
    page.update(id="SIR-008", name="Invoice: Create")
    view = {"id": "SIR-009", "module": "invoice", "name": "Soa: Details", "rules": [
        _rule(1, "Validation / Control Flow", "Validates ...", "AST:SoaController.Details:L1:BRANCH",
              conditions=["if (vm == null)", "return HttpNotFound();"]),
        _rule(2, "Data Retrieval", "Reads Soa", "AST:SoaController.Details:L2:READS"),
        _rule(3, "Data Retrieval", "Reads SoaStatus", "AST:SoaController.Details:L3:READS")]}
    backlog = sts.build_backlog([api, page, view], module_names={"invoice": "Invoice"})
    dup = [q for q in backlog["openQuestions"] if q["id"].startswith("Q-DUP")]
    assert len(dup) == 1 and dup[0]["storyId"] == "US-SIR-008"
    assert '"Invoice: Post" and "Invoice: Create" both let the user create an invoice' in dup[0]["question"]
    assert [f["title"] for _, f in user_stories.bm.iter_features(backlog)] == ["Invoice", "SOA"]
    soa = next(s for _, _, s in user_stories.bm.iter_stories(backlog) if s["id"] == "US-SIR-009")
    assert soa["title"] == ("As a business user, I want to view the details of an SOA so that I can review the SOA "
                            "information"), "lookups such as SoaStatus are not business information"
    assert soa["acceptanceCriteria"] == [   # the check and what it does when it fails, read from the code
        'Given the SOA is not found, when the user opens the SOA, then a "not found" page is shown (R1)',
        "Given an existing SOA, when the user opens the SOA, then the SOA information is shown (R2–R3)",
        "Given the same request is made in the current and the new system, when both complete, then the result is "
        "identical (R1–R3)"]
    assert "read-only" in soa["labels"]


def test_many_checks_are_listed_on_one_line_when_they_do_not_fit():
    sir = _invoice_post()
    sir["rules"][0]["conditions"] = [f"if (model.Amount{i} > {i})" for i in range(1, 17)]   # more than fit
    story = next(user_stories.bm.iter_stories(user_stories.sts.build_backlog([sir])))[2]
    first = story["acceptanceCriteria"][0]
    assert first.startswith("Given a new invoice, when the invoice is submitted, then these checks are applied "
                            "exactly as today: the amount 1 is more than 1; the amount 2 is more than 2;")
    assert first.endswith("the amount 16 is more than 16 (R1)")
    assert len(story["acceptanceCriteria"]) <= user_stories.sts.MAX_CRITERIA


# every distinct check found in the real engagements, and its wording
REAL_CHECKS = [
    ("invoice", "if (model.Particulars.Count > 1)", "there is more than 1 particular"),
    ("invoice", "if (particularVAT.ParticularTypeId == 0)", "the particular type of the particular VAT is not set"),
    ("invoice", "if (entity.Id == 0)", "the invoice has not been saved yet"),
    ("invoice", "if (CreateNewInvoice(entity) == false)", "creating the new invoice fails"),
    ("invoice", "if (SaveModifications(entity) == false)", "saving the modifications fails"),
    ("SOA", 'if (model.StatusName.ToLower() == "unpaid")', 'the status is "unpaid"'),
    ("invoice", "switch (model.InvoiceAction)", "the invoice action decides what happens"),
    ("invoice", "if (model.InvoiceAction == InvoiceActionEnum.Paid)", 'the invoice action is "Paid"'),
    ("invoice", "if (ModelState.IsValid == false)", "the entered details are not valid"),
    ("invoice", "if (list == null || list.Count <= 0)", "the list is empty"),
    ("invoice", "if (list[0].IsApprove)", 'the first item is marked "approve"'),
    ("invoice", "if (item.IsSelected)", 'the item is marked "selected"'),
    ("invoice", "if (entity != null)", "the invoice is found"),
    ("invoice", "if (id.HasValue == false)", "no record is chosen"),
    ("invoice", "if (vm.IsOrganization)", 'the invoice is marked "organization"'),
    ("invoice", "if (id != null) //Edit", "a record is chosen"),
    ("invoice", "if(vm.DueDate.Year < 1980)", "the due date is before 1980"),
    ("invoice", 'if(!(vm.StatusName.ToLower() == "pending" || vm.StatusName.ToLower() == "rejected"))',
     'the status is neither "pending" nor "rejected"'),
    ("invoice", "if (premiumFromParticular != null)", "the premium from particular is available"),
    ("invoice", "if (policy != null && policy.Endorsements != null && policy.Endorsements.Count > 0)",
     "the policy has at least one endorsement"),
    ("invoice", "if(policyId != null)", "a policy is chosen"),
    ("SOA", "if (vm == null)", "the SOA is not found"),
    ("directory", "if(id == null)", "no record is chosen"),
    ("directory", "if (model == null)", "no directory details are given"),
    ("order", "if (model.Total > 500)", "the total is more than 500"),
]


@pytest.mark.parametrize("noun,code,text", REAL_CHECKS)
def test_real_checks_read_as_plain_english(noun, code, text):
    (check,) = user_stories.sts.ct.checks([code], noun)
    assert check["text"] == text
    assert not re.search(r"[(){}=!&|]|\.\w|\bmodel\b|\bvm\b|\bentity\b", check["text"]), "no code left"


def test_what_a_failed_check_does_becomes_its_outcome():
    ct = user_stories.sts.ct
    got = ct.checks(["if (model.Total > 500)", 'throw new Exception("Order total exceeds limit 500")',
                     "if (vm == null)", "return HttpNotFound();", "if (vm == null)", "if (x.IsOrganization)"], "order")
    assert [(c["text"], c["outcome"]) for c in got] == [
        ("the total is more than 500", 'the message "Order total exceeds limit 500" is shown'),
        ("the order is not found", 'a "not found" page is shown'),
        ('the x is marked "organization"', None)], "repeated checks appear once"
    assert ct.outcome("return new HttpStatusCodeResult(HttpStatusCode.BadRequest);") == "the request is refused"


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


def test_push_to_ado_button_request(eng, monkeypatch):
    """The 'Push to ADO' button: all stories (template wording included), ADO settings from the environment."""
    eng = user_stories.generate(_with_sir(eng), refine=False)
    store.save(eng)
    log = []
    monkeypatch.setattr(user_stories.pb, "http_request", _calls_http(log))
    for name, value in ENVS["ado"].items():
        monkeypatch.setenv(name, value)
    client = TestClient(api_main.app)
    body = {"provider": "ado", "apply": True, "confirm": True, "allowTemplate": True}
    rep = client.post("/api/engagements/eng1/user-stories/push", json=body).json()
    items = len(user_stories.bm.flatten(eng["userStories"]["backlog"]))
    assert rep["summary"] == {"created": items}, "epic, features and every story, template wording included"
    assert all("dev.azure.com/o/p/" in call[1] for call in log), "organisation and project come from ADO_ORG / ADO_PROJECT"
    again = client.post("/api/engagements/eng1/user-stories/push", json=body).json()
    assert again["summary"] == {"exists": items} and len(log) == items, "pushing twice creates nothing new"
    assert store.load("eng1")["userStories"]["lastPush"]["provider"] == "ado"

    monkeypatch.delenv("ADO_PAT")
    r = client.post("/api/engagements/eng1/user-stories/push", json=body)
    assert r.status_code == 400 and "ADO_PAT" in r.json()["detail"], "a clear error when ADO is not configured"


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


# ------------------------------------------------------------------ legacy complexity -> estimates

class _FakeSrc:
    def __init__(self, files): self.files = files
    def lines(self, rel): return self.files.get(rel, [])


def _assess(files, **flow_over):
    from app import legacy_assessment as la
    flow = {"id": "UC:W", "entryPoint": "A.B.Ctl.Run", "tablesRead": [], "tablesWritten": ["A.Order"],
            "externals": [], **flow_over}
    wf = {"steps": [{"from": "A.B.Ctl.Run", "kind": "CALLS", "to": "A.Svc.Do", "file": "c.cs", "line": 3, "depth": 1}],
          "fullyTraced": True}
    return la.assess(flow, wf, _FakeSrc(files), module_flows=[flow], kernel_nodes={"A.Order": 3}, node_cap={},
                     cap_id="m", node_loc={}, externals={})


def test_assessment_finds_evidence_and_ignores_modern_authorize():
    code = ["public class Ctl {", "var u = HttpContext.Current.User;", "var s = new OrderService();",
            "var cmd = new SqlCommand(sql, conn);", "[Authorize]", "// TODO fix"]
    a = _assess({"c.cs": code})
    cats = {f["category"] for f in a["factors"]}
    assert {"testability", "data", "unknowns"} <= cats
    assert "security" not in cats, "[Authorize] alone is not a legacy security risk"
    sql = next(f for f in a["factors"] if "ADO.NET" in f["finding"])
    assert sql["evidence"] == "c.cs#L4" and sql.get("question")
    assert 0 < a["uplift"] <= 3
    assert any("DBA" in d for d in a["definitionOfDone"])


def test_estimates_use_business_complexity_only(eng):
    eng = _with_sir(eng)
    sir = eng["seed"]["semantic_ir"][0]
    sir["legacyAssessment"] = {"paradigm": "MVC", "uplift": 3, "regressionScope": ["Orders: Edit"],
                               "definitionOfDone": ["dod"], "factors": [
                                   {"category": "data", "finding": "Raw SQL", "evidence": "c.cs#L1", "points": 2,
                                    "question": "Which stored procedures does this use?"},
                                   {"category": "framework", "finding": "Web Forms", "evidence": "c.cs#L2", "points": 2},
                                   {"category": "unknowns", "finding": "TODO in code", "evidence": "c.cs#L9",
                                    "points": 1}]}
    backlog = user_stories.sts.build_backlog([sir])
    story = next(user_stories.bm.iter_stories(backlog))[2]
    est = story["estimation"]
    for key in ("rules", "scope", "uncertainty"):   # every factor is a 1-5 level backed by evidence
        assert 1 <= est[key]["level"] <= 5 and est[key]["evidence"]
    evidence = " ".join(e for k in ("rules", "scope", "uncertainty") for e in est[k]["evidence"])
    assert "Raw SQL" not in evidence and "Web Forms" not in evidence, "technical findings are not sized"
    assert "TODO in code" in evidence, "undocumented business intent is business uncertainty"
    assert est["factorSum"] == sum(est[k]["level"] for k in ("rules", "scope", "uncertainty"))
    assert est["points"] == story["storyPoints"] == user_stories.sts.est_mod.to_points(est["factorSum"])
    assert any("Orders: Edit workflow use the same records" in a for a in story["acceptanceCriteria"])
    questions = [q["question"] for q in backlog["openQuestions"]]
    assert "Which stored procedures does this use?" not in questions, "technical planning questions are dropped"
    assert [q["id"] for q in backlog["openQuestions"]] == ["Q-EST-02"]
    assert backlog["estimationModel"]["reference"]["storyId"] == story["id"]
    assert not [i for i in user_stories.bm.validate(backlog) if i[0] == "ERROR"]


def test_refinement_can_raise_points_one_step_never_lower(eng):
    sir = _with_sir(eng)["seed"]["semantic_ir"][0]
    story = next(user_stories.bm.iter_stories(user_stories.sts.build_backlog([sir])))[2]
    rules = [r for r in sir["rules"] if r["kind"] != "legacy_plumbing_pruned"]
    base = story["storyPoints"]
    upd = {"narrative": {"asA": "a", "iWant": "i", "soThat": "s"}, "description": "d",
           "acceptanceCriteria": ['Given x, when y, then "Order total exceeds limit 500" is shown (R1-R4)'],
           "storyPoints": 1}
    assert user_stories._apply_story(story, upd, rules) is None and story["storyPoints"] == base, "never lower"
    upd["storyPoints"] = 21
    assert user_stories._apply_story(story, upd, rules) is None
    assert story["storyPoints"] == next(f for f in user_stories.bm.FIBONACCI if f > base), "at most one step up"


def test_points_follow_business_rules_not_technology():
    est = user_stories.sts.est_mod
    simple = [{"ruleId": "R1", "statement": "Reads Invoice", "classification": "Data Retrieval",
               "trustBoundary": "Application Logic", "astNode": "AST:InvoiceApi.Get:L5:READS"}]
    heavy = [{"ruleId": "G", "statement": "Validates the request before processing",
              "conditions": ["if (a)", "if (b)", "if (c)", "if (d)", "if (e)", "if (premium > limit)"],
              "classification": "Validation / Control Flow",
              "trustBoundary": "Application Logic", "astNode": "AST:Inv.Save:L1:BRANCH"}] + [
        {"ruleId": f"W{i}", "statement": f"Persists changes to T{i}", "classification": "State Mutation",
         "trustBoundary": "Deterministic Core (x)", "astNode": f"AST:Inv.Save:L{i}:WRITES"} for i in range(2, 6)]
    internal = [{"ruleId": f"C{i}", "statement": f"Delegates to Inv.Step{i}", "classification": "Orchestration",
                 "trustBoundary": "Application Logic", "astNode": f"AST:Inv.Get:L{i}:CALLS"} for i in range(10)]
    technical = {"factors": [{"category": "security", "finding": "MD5 hashing", "points": 1},
                             {"category": "data", "finding": "stored procedures", "points": 2},
                             {"category": "coupling", "finding": "static state", "points": 2}]}
    unknown = {"factors": [{"category": "unknowns", "finding": "undocumented discount rule", "points": 1}]}
    a = est.score_use_case(simple)
    b = est.score_use_case(heavy)
    assert a["points"] <= 2, "a single look-up is at the reference-story size"
    assert b["rules"]["level"] > a["rules"]["level"] and b["scope"]["level"] > a["scope"]["level"]
    assert b["uncertainty"]["level"] > a["uncertainty"]["level"], "money checks that change records carry impact"
    assert b["points"] >= 8
    assert est.score_use_case(simple + internal) == a, "internal calls between code do not change the size"
    assert est.score_use_case(simple, technical) == a, "technical legacy findings do not change the size"
    assert est.score_use_case(simple, unknown)["uncertainty"]["level"] > a["uncertainty"]["level"]
    dashboard = [{"ruleId": "G", "statement": "Validates", "conditions": ["if (x.IsOrganization)"] * 3,
                  "classification": "Validation / Control Flow", "astNode": "AST:D.Index:L1:BRANCH"}]
    assert est.checks(dashboard) == ["if (x.IsOrganization)"], "the same check repeated is one check"
    thrown = [{"ruleId": "G", "statement": "Validates", "astNode": "AST:D.Index:L1:BRANCH",
               "conditions": ["if (total > 500)", 'throw new Exception("Too big")', "return HttpNotFound();"]}]
    assert est.checks(thrown) == ["if (total > 500)"], "what a failed check does is not another check"


def test_story_is_the_user_story_card(eng):
    sir = _with_sir(eng)["seed"]["semantic_ir"][0]
    backlog = user_stories.sts.build_backlog([sir])
    for _, _, s in user_stories.bm.iter_stories(backlog):
        n = s["narrative"]
        assert s["title"] == f"As a {n['asA']}, I want {n['iWant']} so that {n['soThat']}"
        for a in s["acceptanceCriteria"]:   # one line each: Given ..., when ..., then ... (short rule ids)
            assert "\n" not in a and a.startswith("Given ") and ", when " in a and ", then " in a
            assert "SIR-" not in a
        assert s["behaviour"] == sir["name"]
    assert user_stories.sts.cite(["S.R1", "S.R2", "S.R3", "S.R5", "S.R7", "S.R8"]) == " (R1–R3, R5, R7–R8)"
    assert user_stories.sts.cite([]) == ""
    assert user_stories.sts.story_title({"asA": "accounts clerk", "iWant": "to x", "soThat": "y"}).startswith("As an")


def test_renderers_show_the_story_card(eng):
    sir = _with_sir(eng)["seed"]["semantic_ir"][0]
    backlog = user_stories.sts.build_backlog([sir])
    md = user_stories.bm.backlog_markdown(backlog)
    epic, feature, story = next(user_stories.bm.iter_stories(backlog))
    assert story["title"] in md and f"{epic['title']} › {feature['title']}" in md
    assert f"- {story['acceptanceCriteria'][0]}" in md and story["description"] in md
    for hidden in ("Trace:", "Legacy lines", "AST:", "Complexity", "AI-assisted", "```"):
        assert hidden not in md, hidden
    item = next(i for i in user_stories.bm.flatten(backlog) if i["level"] == "story")
    ac0 = story["acceptanceCriteria"][0]
    for body, expected in ((user_stories.bm.item_markdown(item), ac0), (user_stories.bm.jira_wiki(item), ac0),
                           (json.dumps(user_stories.bm.adf(item), ensure_ascii=False), json.dumps(ac0)[1:-1])):
        assert "Story points" in body and feature["title"] in body and expected in body
        assert "trace" not in body.lower()
    assert "<li>" in user_stories.bm.acceptance_html(story)


def test_story_card_edits_and_removal_persist(eng):
    eng = user_stories.generate(_with_sir(eng), refine=False)
    stories = [s for _, _, s in user_stories.bm.iter_stories(eng["userStories"]["backlog"])]
    sid, trace = stories[0]["id"], dict(stories[0]["trace"])
    out = user_stories.update_story(eng, sid, {
        "title": "As a clerk, I want to see the owner so that I know who is responsible",
        "description": "Shows the owner.", "acceptanceCriteria": ["Given x, when y, then z (R-001)", "  ", ""],
        "labels": ["read view", "bad label!", "assignee"], "storyPoints": 1, "trace": {"sirId": "HACKED"}})
    s = next(x for _, _, x in user_stories.bm.iter_stories(out["userStories"]["backlog"]) if x["id"] == sid)
    assert s["title"].startswith("As a clerk") and s["acceptanceCriteria"] == ["Given x, when y, then z (R-001)"]
    assert s["labels"] == ["read-view", "assignee"] and s["storyPoints"] == 1 and s["trace"] == trace
    assert s["narrativeSource"] == "refined" and s["edited"]
    assert not [v for v in out["userStories"]["validation"] if v["level"] == "ERROR"], "a person may lower points"
    md = (store.engagement_dir("eng1") / "artifacts" / "user-stories" / "backlog.md").read_text(encoding="utf-8")
    assert "As a clerk" in md, "backlog.md is rewritten on save"
    with pytest.raises(ValueError):
        user_stories.update_story(out, sid, {"storyPoints": 4})
    with pytest.raises(ValueError):
        user_stories.update_story(out, sid, {"acceptanceCriteria": [" "]})
    out = user_stories.remove_story(out, sid)
    remaining = [x["id"] for _, _, x in user_stories.bm.iter_stories(out["userStories"]["backlog"])]
    assert sid not in remaining and out["userStories"]["counts"]["stories"] == len(stories) - 1
    with pytest.raises(KeyError):
        user_stories.remove_story(out, sid)


def test_story_edit_endpoints(eng, monkeypatch):
    eng = user_stories.generate(_with_sir(eng), refine=False)
    store.save(eng)
    sid = next(user_stories.bm.iter_stories(eng["userStories"]["backlog"]))[2]["id"]
    client = TestClient(api_main.app)
    r = client.patch(f"/api/engagements/eng1/user-stories/stories/{sid}", json={"description": "New text"})
    assert r.status_code == 200
    assert next(s for _, _, s in user_stories.bm.iter_stories(r.json()["userStories"]["backlog"])
                if s["id"] == sid)["description"] == "New text"
    assert client.patch("/api/engagements/eng1/user-stories/stories/US-NOPE", json={"title": "x"}).status_code == 404
    assert client.patch(f"/api/engagements/eng1/user-stories/stories/{sid}", json={"title": " "}).status_code == 400
    assert client.delete(f"/api/engagements/eng1/user-stories/stories/{sid}").status_code == 200
    assert client.delete(f"/api/engagements/eng1/user-stories/stories/{sid}").status_code == 404


def test_modules_are_ordered_most_used_first():
    def mod(i, name, deps=(), shared=False):
        return {"id": i, "name": name, "shared": shared, "dependsOn": list(deps), "sharedKernels": [],
                "riskScore": None, "metrics": {"loc": 100, "useCases": 1}}
    mods = [mod("a", "App", deps=["Core", "Mid", "Platform"]),
            mod("m", "Mid", deps=["Core", "Platform"]),
            mod("c", "Core", deps=["Platform"]),
            mod("p", "Platform", shared=True)]
    out = scope_modules._rank_for_modernization(mods, {m["name"]: m["id"] for m in mods})
    assert [m["name"] for m in out] == ["Platform", "Core", "Mid", "App"]
    assert [m["modernization"]["rank"] for m in out] == [1, 2, 3, 4]
    assert out[0]["modernization"]["reason"].startswith("used by 3 other modules")
    assert out[-1]["modernization"]["reason"].startswith("not used by any other module")
