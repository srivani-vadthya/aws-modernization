"""Tests for the parser-based .NET AKG extractor.

Two deliberately different fixture solutions keep the rules honest: an EF6/Web API 2/
AngularJS solution with a generic repository behind a unit of work, and an SDK-style
ASP.NET Core API with DbContext injection, attribute routing and MediatR.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from app import knowledge_graph
from app.dotnet_akg import build_dotnet_akg
from app.dotnet_akg.evaluate import regression_checks, score
from app.dotnet_akg.seeding import apply_to_seed

FIXTURES = Path(__file__).parent / "fixtures"
SHOP = FIXTURES / "legacy_shop"
TICKETS = FIXTURES / "modern_tickets"


@pytest.fixture(scope="module")
def shop() -> dict:
    return build_dotnet_akg(SHOP, overrides={})


@pytest.fixture(scope="module")
def tickets() -> dict:
    return build_dotnet_akg(TICKETS, overrides={})


def _edge(g: dict, kind: str, src_suffix: str, tgt_suffix: str) -> dict | None:
    return next((e for e in g["edges"] if e["kind"] == kind and e["source"].endswith(src_suffix)
                 and e["target"].endswith(tgt_suffix)), None)


# ---------------------------------------------------------------------------
# Precision / recall per edge type against hand-checked references
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["legacy_shop", "modern_tickets"])
def test_precision_and_recall_per_edge_type(name: str):
    graph = build_dotnet_akg(FIXTURES / name, overrides={})
    reference = json.loads((FIXTURES / f"{name}.reference.json").read_text(encoding="utf-8"))
    report = score(graph, reference)
    failures = {k: r for k, r in report.items() if r["precision"] < 1.0 or r["recall"] < 1.0}
    assert not failures, json.dumps(failures, indent=2)


@pytest.mark.parametrize("name", ["legacy_shop", "modern_tickets"])
def test_regression_invariants(name: str):
    graph = build_dotnet_akg(FIXTURES / name, overrides={})
    assert regression_checks(graph) == []


# ---------------------------------------------------------------------------
# Edge semantics
# ---------------------------------------------------------------------------

def test_every_edge_has_file_line_and_rule(shop, tickets):
    for g in (shop, tickets):
        assert g["statistics"]["edgesWithoutLocation"] == 0
        for e in g["edges"]:
            assert e["file"] and e["line"] >= 1 and e["rule_id"], e
            assert e["evidence"], e


def test_repository_operations_are_classified_from_method_bodies(shop):
    order = _edge(shop, "ACCESSES_DATA", "OrdersApiController", "Entities.Order")
    assert order["operations"] == ["read", "write"]
    # Detach() neither reads nor writes; Delete(int) writes through Delete(T)
    assert "Detach" not in order["methods"]
    line = _edge(shop, "ACCESSES_DATA", "OrdersApiController", "Entities.OrderLine")
    assert line["operations"] == ["write"] and "Delete" in line["methods"]


def test_dbset_access_without_repository(tickets):
    t = _edge(tickets, "ACCESSES_DATA", "TicketService", "Domain.Ticket")
    assert t["operations"] == ["read", "write"]
    assert t["rule_id"] == "data.dbset-call"


def test_solution_types_are_never_external(shop, tickets):
    shop_external = [n["id"] for n in shop["nodes"] if n["type"] == "external"]
    assert shop_external == ["external:System.Net.Mail.SmtpClient"]
    # Logger is defined in the solution, so a call to it is internal
    assert _edge(shop, "CALLS", "OrdersApiController", "Services.Logger")
    # An internal class named like an AWS SDK client is an ordinary internal call
    assert _edge(tickets, "CALLS", "TicketService", "Services.EventBridgeClient")
    assert not any(n["id"].endswith("EventBridgeClient") for n in tickets["nodes"] if n["type"] == "external")


def test_events_only_from_real_publishers(shop, tickets):
    # legacy_shop has a comment about EventBridge but no publisher call
    assert not [e for e in shop["edges"] if e["kind"] == "EMITS_EVENT"]
    assert not [n for n in shop["nodes"] if n["type"] == "event"]
    events = [e for e in tickets["edges"] if e["kind"] == "EMITS_EVENT"]
    assert [e["target"] for e in events] == ["event:MediatR.IMediator.Publish"]


def test_http_calls_resolve_to_actions(shop, tickets):
    e = _edge(shop, "HTTP_CALLS", "ordersCtrl.ts", "OrdersApiController")
    assert set(e["actions"]) == {"Post", "Cancel"} and set(e["verbs"]) == {"POST", "PATCH"}
    unresolved = shop["diagnostics"]["unresolvedHttpCalls"]
    assert [u["url"] for u in unresolved] == ["/api/NoSuchApi"]
    t = _edge(tickets, "HTTP_CALLS", "web/src/api.ts", "TicketsController")
    assert set(t["actions"]) == {"Create", "Get", "Archive"}
    assert t["rule_id"] == "http.attribute-route"


def test_project_files_define_the_scan(shop):
    ids = {n["id"] for n in shop["nodes"]}
    assert "Shop.Entities.Obsolete" not in ids                     # on disk, not in the csproj
    assert shop["diagnostics"]["filesNotInAnyProject"] == ["Shop.Entities/Obsolete.cs"]
    assert "Shop.Web.Services.NotificationService" in ids           # Services/ folder is included
    assert any(i.startswith("ts:") for i in ids)                    # TypeScript is included
    assert not any("jquery" in i for i in ids)                      # vendor JS is not


# ---------------------------------------------------------------------------
# Derived layers
# ---------------------------------------------------------------------------

def test_lineage_uses_ef_model_columns_and_types(shop):
    rows = {r["sourceField"]: r for r in shop["dataLineage"]}
    total = rows["OrderModel.Total"]
    assert total["targetColumn"] == "Order.Total" and total["targetType"] == "decimal(18,2)"
    assert total["migrationRisk"] == "high"                         # double -> decimal(18,2)
    flattened = rows["OrderModel.CustomerName"]                     # ForMember(src => src.Customer.Name)
    assert flattened["entityProperty"] == "Customer.Name"
    assert flattened["targetColumn"] == "Customer.CustomerName"     # column renamed in the EF mapping
    assert flattened["rule_id"] == "lineage.automapper-formember"
    assert all(r["file"] and r["line"] for r in shop["dataLineage"])
    assert shop["efModel"]["source"]["file"].endswith("201901010000000_Initial.resx")


def test_no_lineage_without_a_model(tickets):
    assert tickets["dataLineage"] == []


def test_workflows_are_traced_to_writes_and_externals(shop, tickets):
    wf = {w["entryPoint"].rsplit(".", 1)[-1] + ":" + w["entryKind"]: w for w in shop["codeWorkflows"]}
    cancel = wf["Cancel:http-call"]
    assert cancel["fullyTraced"] and cancel["writes"] == ["Shop.Entities.Order"]
    assert cancel["externals"] == ["external:System.Net.Mail.SmtpClient"]
    assert cancel["trigger"]["verb"] == "PATCH"
    post = wf["Post:http-call"]                                     # Post -> private SaveNew -> writes
    assert set(post["writes"]) == {"Shop.Entities.Order", "Shop.Entities.OrderLine"}
    assert not wf["Index:controller-action"]["fullyTraced"]          # read-only
    create = next(w for w in tickets["codeWorkflows"] if w["entryPoint"].endswith("TicketsController.Create"))
    assert create["events"] == ["event:MediatR.IMediator.Publish"]
    assert create["externals"] == ["external:System.Net.Http.HttpClient"]


def test_capabilities_from_writes_not_names(tickets, shop):
    cap = {n["id"]: n["capability"] for n in tickets["nodes"]}
    assert cap["Tickets.Api.Domain.TicketNote"] == cap["Tickets.Api.Domain.Ticket"]   # written together
    assert cap["Tickets.Api.Services.TicketService"] == cap["Tickets.Api.Domain.Ticket"]
    assert cap["Tickets.Api.Controllers.AgentsController"] == cap["Tickets.Api.Domain.Agent"]
    assert cap["Tickets.Api.Data.AppDbContext"] == "platform"
    shop_cap = {n["id"]: n["capability"] for n in shop["nodes"]}
    assert shop_cap["Shop.Data.GenericRepository"] == "platform"
    for n in shop["nodes"] + tickets["nodes"]:
        if n["type"] in {"program", "entity"}:
            assert n["capabilityBasis"]["rule"].startswith("capability."), n


def test_overrides_beat_rules():
    g = build_dotnet_akg(TICKETS, overrides={
        "rename": {"ticket": "Service Desk"},
        "merge": {"agent": "ticket"},
        "assign": {"GeoClient": "platform"},
    })
    cap = {n["id"]: n for n in g["nodes"]}
    assert cap["Tickets.Api.Domain.Agent"]["capability"] == "ticket"
    assert cap["Tickets.Api.Services.GeoClient"]["capability"] == "platform"
    assert cap["Tickets.Api.Services.GeoClient"]["capabilityBasis"]["rule"] == "capability.override"
    assert {c["id"]: c["name"] for c in g["capabilities"]}["ticket"] == "Service Desk"


def test_overrides_file_in_source_root(tmp_path):
    import shutil
    src = tmp_path / "tickets"
    shutil.copytree(TICKETS, src)
    (src / "akg-overrides.json").write_text(json.dumps({"merge": {"agent": "ticket"}}), encoding="utf-8")
    g = build_dotnet_akg(src)
    assert {n["id"]: n["capability"] for n in g["nodes"]}["Tickets.Api.Domain.Agent"] == "ticket"


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------

def test_applied_graph_and_scope_from_dotnet_akg(shop):
    seed = {"semantic_ir": [{"id": "SIR-1", "module": "order", "rules": [],
                             "sideEffects": ["Publish OrderPlaced to Amazon EventBridge"]}]}
    apply_to_seed(seed, shop)
    applied = knowledge_graph.build_applied_graph(seed)
    kinds = applied["statistics"]["edgesByKind"]
    assert kinds.get("ACCESSES_DATA") == 4
    assert "EMITS_EVENT" not in kinds and applied["statistics"]["eventNodes"] == 0   # prose is not a publisher
    assert "OWNS_DATA" not in kinds                                                  # no location -> not added
    assert applied["statistics"]["edgesWithLocation"] == applied["statistics"]["totalEdges"]
    assert applied["dataLineage"] and all(r["file"] for r in applied["dataLineage"])
    assert applied["codeWorkflows"]
    roles = {n["id"]: n["semanticRole"] for n in applied["nodes"]}
    assert roles["Shop.Entities.Order"] == "data-entity"
    assert roles["Shop.Web.Services.NotificationService"] == "integration-adapter"
    seed["applied_graph"] = applied
    scope = knowledge_graph.identify_scope(seed)
    assert scope["summary"]["mutatingFlows"] >= 3
    order_mod = next(m for m in scope["logicalModules"] if m["moduleId"] == "order")
    assert "Shop.Entities.Order" in order_mod["ownedTables"]


def test_evidence_required_graph_drops_unlocated_edges(shop):
    seed: dict = {}
    apply_to_seed(seed, shop)
    seed["graph"]["edges"].append({"id": "x", "source": "a", "target": "b", "kind": "CALLS"})
    applied = knowledge_graph.build_applied_graph(seed)
    assert applied["statistics"]["edgesDroppedWithoutLocation"] == 1
    assert not any(e["id"] == "x" for e in applied["edges"])


def test_seed_projection_lists_real_integrations(shop):
    seed: dict = {}
    apply_to_seed(seed, shop)
    ints = seed["discovery"]["integrations"]
    assert [i["name"] for i in ints] == ["System.Net.Mail.SmtpClient"]
    assert ints[0]["evidence"].startswith("Shop.Web/Services/NotificationService.cs#L")
    assert seed["copybook_schemas"] == []
    assert {t["id"] for t in seed["tables"]} == {"Shop.Entities.Order", "Shop.Entities.OrderLine",
                                                "Shop.Entities.OrderStatus", "Shop.Entities.Customer"}


def test_generic_seed_has_no_placeholder_lineage_or_events():
    from app.seed import generic_seed
    inventory = {"assets": [{"path": "src/Orders/OrderService.cs", "kind": "source", "language": "csharp", "loc": 40}],
                 "languages": {"csharp": 1}, "relationships": []}
    seed = generic_seed(inventory, "e1", "demo")
    assert seed["copybook_schemas"] == []
    assert not any("EventBridge" in s for sir in seed["semantic_ir"] for s in sir.get("sideEffects", []))
    assert not any(i["id"] == "INT-DB2-REMOTE" for i in seed["discovery"]["integrations"])
    applied = knowledge_graph.build_applied_graph(seed)
    assert applied["dataLineage"] == []
    assert applied["statistics"]["eventNodes"] == 0


# ---------------------------------------------------------------------------
# IMS (runs only where the IMS source is available)
# ---------------------------------------------------------------------------

IMS_ROOT = Path(os.environ.get("IMS_ROOT", r"C:\Sai\git-legacy codes\ims"))


@pytest.mark.skipif(not (IMS_ROOT / "IMS.sln").is_file(), reason="IMS source not available (set IMS_ROOT)")
def test_ims_data_access_against_independent_oracle():
    """Recompute Uow.<Repo>.<Method>() data access with a separate method and compare."""
    graph = build_dotnet_akg(IMS_ROOT, overrides={})
    uow = (IMS_ROOT / "IMS.Data" / "ApplicationUnit.cs").read_text(encoding="utf-8-sig")
    prop_repo = dict((p, r) for r, p in re.findall(r"public\s+(\w+Repository)\s+(\w+)\s*$", uow, re.M))
    repos = (IMS_ROOT / "IMS.Data" / "Repositories" / "IMSRepository.cs").read_text(encoding="utf-8-sig")
    repo_entity = dict(re.findall(r"class\s+(\w+Repository)\s*:\s*GenericRepository<(\w+)>", repos))
    ops = {"GetAll": "read", "GetById": "read", "GetDBSet": "read", "Add": "write", "Update": "write", "Delete": "write"}
    expected: set[tuple[str, str]] = set()
    for p in (IMS_ROOT / "IMS.WebMvc").rglob("*.cs"):
        if "obj" in p.parts:
            continue
        text = p.read_text(encoding="utf-8-sig", errors="ignore")
        cls = re.search(r"public\s+class\s+(\w+)", text)
        # Controllers use the inherited `Uow` property; services hold it in `_uow` (from BaseService).
        for m in re.finditer(r"^(?!\s*//).*?\b_{0,2}[Uu]ow\.(\w+)\.(\w+)\s*\(", text, re.M):
            if m.group(2) in ops and cls:
                expected.add((cls.group(1), repo_entity[prop_repo[m.group(1)]]))
    # The oracle models the unit-of-work path only; direct DbSet writes (ProductionSeedData) are a separate rule.
    produced = {(e["source"].rsplit(".", 1)[-1], e["target"].rsplit(".", 1)[-1])
                for e in graph["edges"] if e["kind"] == "ACCESSES_DATA" and e["source"].startswith("IMS.WebMvc.")
                and any(ev["rule_id"] == "data.repository-call" for ev in e["evidence"])}
    assert expected - produced == set(), "missing"
    assert produced - expected == set(), "unexpected"
    assert len(expected) >= 48


@pytest.mark.skipif(not (IMS_ROOT / "IMS.sln").is_file(), reason="IMS source not available (set IMS_ROOT)")
def test_ims_known_gaps_are_closed():
    graph = build_dotnet_akg(IMS_ROOT, overrides={})
    assert regression_checks(graph) == []
    ids = {n["id"] for n in graph["nodes"]}
    assert "IMS.WebMvc.Services.LoggingService" in ids                       # internal, not external:
    assert "IMS.Entities.ActivityLog" in ids                                 # Logs.cs is scanned
    assert {n["id"] for n in graph["nodes"] if n["type"] == "external"} <= {
        "external:System.Net.Mail.SmtpClient", "external:Rotativa.ActionAsPdf",
        "external:System.IO.File", "external:System.IO.FileStream"}
    assert not graph["diagnostics"].get("unresolvedHttpCalls")
    assert graph["statistics"]["codeWorkflows"] > 0 and graph["statistics"]["sharedKernelCount"] > 0
    assert not [e for e in graph["edges"] if e["kind"] == "EMITS_EVENT"]
    assert not any("DB2" in (r.get("target") or "") for r in graph["dataLineage"])
    # IdentityConfig.cs declares several classes; they are nodes, not things the file "calls"
    assert not any(e["source"].endswith("IdentityConfig") for e in graph["edges"])
    cap = {n["id"]: n["capability"] for n in graph["nodes"]}
    assert cap["IMS.WebMvc.Controllers.AccountController"] == "identity"
    assert cap["IMS.Entities.Directory"] == "directory"
    assert cap["IMS.Entities.Particular"] == cap["IMS.Entities.Invoice"]
