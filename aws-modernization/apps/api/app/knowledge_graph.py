"""Applied Knowledge Graph — enriches raw AST edges with application-specific
semantics, data relationships, and workflow context.

Produces:
  - Semantic node annotations  (domain role, trust boundary, SIR rule refs)
  - Typed edge semantics       (CALLS, READS, WRITES, MAPS_TO, TRIGGERED_BY,
                                OWNS_DATA, EMITS_EVENT, IN_SCOPE_OF, CONTAINS)
  - Data-relationship layer    (field-level lineage from copybook_schemas)
  - Workflow context layer     (SIR → requirement → backlog → test trace chains)
  - Cross-capability coupling  (bidirectional shared-kernel detection)
"""

from __future__ import annotations

from collections import defaultdict


# ---------------------------------------------------------------------------
# Semantic role inference
# Role priority: event-publisher > batch-entry-point > screen-boundary >
#                data-access-gateway > orchestrator > business-logic
# A node that both CALLS and READS/WRITES is an orchestrator, not a gateway.
# ---------------------------------------------------------------------------

def _infer_role(outgoing_kinds: set[str], node_type: str = "") -> str:
    if node_type == "entity":
        return "data-entity"
    if node_type == "external":
        return "external-system"
    if "EMITS_EVENT" in outgoing_kinds:
        return "event-publisher"
    if "TRIGGERED_BY" in outgoing_kinds:
        return "batch-entry-point"
    if "HTTP_CALLS" in outgoing_kinds or node_type in {"frontend", "view"}:
        return "screen-boundary"
    if "MAPS_TO" in outgoing_kinds:
        return "screen-boundary"
    if "INVOKES_EXTERNAL" in outgoing_kinds:
        return "integration-adapter"
    if "CALLS" in outgoing_kinds:
        # If it also touches data it is still an orchestrator — it delegates
        return "orchestrator"
    if outgoing_kinds & {"READS", "WRITES"}:
        return "data-access-gateway"
    return "business-logic"


def _normalized_kinds(edge: dict) -> set[str]:
    """ACCESSES_DATA carries its read/write operations; expose them as READS/WRITES too."""
    kind = edge.get("kind", "")
    if kind == "ACCESSES_DATA":
        ops = set(edge.get("operations") or ["read"])
        return {kind} | ({"WRITES"} if "write" in ops else set()) | ({"READS"} if "read" in ops else set())
    return {kind}


# ---------------------------------------------------------------------------
# Trust boundary inference — exact prefix/suffix matching, not substring
# ---------------------------------------------------------------------------

_TRUST_PREFIXES: list[tuple[str, str]] = [
    ("LGACDB", "Deterministic Core — customer DB gateway"),
    ("LGAPDB", "Deterministic Core — policy DB gateway"),
    ("LGIPDB", "Deterministic Core — policy inquiry DB gateway"),
    ("CUST",   "Deterministic Core — customer master"),
    ("POL",    "Deterministic Core — policy invariant"),
    ("CLM",    "Deterministic Core — claims invariant"),
    ("MOTOR",  "Deterministic Core — motor vehicle data"),
    ("HOUSE",  "Deterministic Core — property data"),
]

_TRUST_SUFFIXES: list[tuple[str, str]] = [
    ("DB01", "Deterministic Core — DB2 gateway"),
    ("DB",   "Deterministic Core — data persistence"),
]

_TRUST_TYPE_MAP: dict[str, str] = {
    "screen": "UI Boundary — replaced by cloud SPA",
    "frontend": "UI Boundary — replaced by cloud SPA",
    "view": "UI Boundary — replaced by cloud SPA",
    "job":    "Batch Boundary — replaced by Step Functions",
    "event":  "Event Bus — observed publisher",
    "table":  "Deterministic Core — data persistence",
    "entity": "Deterministic Core — data persistence",
    "external": "External Integration — outside the solution",
    "config": "Configuration — externalise to Parameter Store / Secrets Manager",
}


def _infer_trust_boundary(node_id: str, node_type: str) -> str:
    if node_type in _TRUST_TYPE_MAP:
        return _TRUST_TYPE_MAP[node_type]
    uid = node_id.upper().split(":")[-1]   # strip capability prefix if present
    for prefix, boundary in _TRUST_PREFIXES:
        if uid.startswith(prefix):
            return boundary
    for suffix, boundary in _TRUST_SUFFIXES:
        if uid.endswith(suffix):
            return boundary
    return "Application Logic"


# ---------------------------------------------------------------------------
# Edge semantic metadata
# ---------------------------------------------------------------------------

_EDGE_SEMANTIC: dict[str, dict[str, str]] = {
    "CALLS": {
        "semanticType": "synchronous-invocation",
        "modernEquivalent": "REST/gRPC internal call or Spring @Service injection",
        "migrationRisk": "low",
    },
    "READS": {
        "semanticType": "data-query",
        "modernEquivalent": "JPA/EF Core SELECT via repository",
        "migrationRisk": "medium",
    },
    "WRITES": {
        "semanticType": "data-mutation",
        "modernEquivalent": "JPA/EF Core INSERT/UPDATE/DELETE via repository",
        "migrationRisk": "high",
    },
    "MAPS_TO": {
        "semanticType": "ui-screen-binding",
        "modernEquivalent": "React component route / REST endpoint",
        "migrationRisk": "low",
    },
    "TRIGGERED_BY": {
        "semanticType": "batch-schedule-dependency",
        "modernEquivalent": "AWS Step Functions scheduled trigger / EventBridge rule",
        "migrationRisk": "medium",
    },
    "IN_SCOPE_OF": {
        "semanticType": "bounded-context-membership",
        "modernEquivalent": "DDD aggregate root ownership",
        "migrationRisk": "low",
    },
    "CONTAINS": {
        "semanticType": "module-membership",
        "modernEquivalent": "Maven/Gradle module or .NET project reference",
        "migrationRisk": "low",
    },
    "EMITS_EVENT": {
        "semanticType": "domain-event-publication",
        "modernEquivalent": "Amazon EventBridge PutEvents / Transactional Outbox",
        "migrationRisk": "medium",
    },
    "OWNS_DATA": {
        "semanticType": "data-ownership",
        "modernEquivalent": "Aurora PostgreSQL table owned by bounded context",
        "migrationRisk": "high",
    },
    "ACCESSES_DATA": {
        "semanticType": "data-access",
        "modernEquivalent": "EF Core repository / DbContext owned by the bounded context",
        "migrationRisk": "medium",
    },
    "HTTP_CALLS": {
        "semanticType": "http-request",
        "modernEquivalent": "Typed API client against the service's OpenAPI contract",
        "migrationRisk": "medium",
    },
    "INVOKES_EXTERNAL": {
        "semanticType": "external-integration",
        "modernEquivalent": "Adapter behind a port (SES, S3, HTTP client via IHttpClientFactory)",
        "migrationRisk": "high",
    },
    "INHERITS": {"semanticType": "type-inheritance", "modernEquivalent": "Composition or base class", "migrationRisk": "low"},
    "IMPLEMENTS": {"semanticType": "interface-implementation", "modernEquivalent": "Port/adapter interface", "migrationRisk": "low"},
    "REFERENCES": {"semanticType": "entity-relationship", "modernEquivalent": "Foreign key / aggregate reference by id", "migrationRisk": "medium"},
}


# ---------------------------------------------------------------------------
# Data-relationship layer (field-level lineage from copybook schemas)
# ---------------------------------------------------------------------------

def _build_data_lineage(copybook_schemas: list[dict]) -> list[dict]:
    lineage: list[dict] = []
    for schema in copybook_schemas:
        src = schema.get("sourceDataset") or schema.get("id", "UNKNOWN")
        tgt = schema.get("targetTable", "unknown_table")
        for field in schema.get("fields", []):
            usage = field.get("usage", "DISPLAY")
            lineage.append({
                "id": f"LINEAGE:{src}.{field['name']}->{tgt}.{field['sqlColumn']}",
                "source": src,
                "target": tgt,
                "kind": "FIELD_LINEAGE",
                "sourceField": field["name"],
                "targetColumn": field["sqlColumn"],
                "sourceType": usage,
                "targetType": field.get("sqlType", "VARCHAR"),
                "conversionNote": field.get("notes", ""),
                "semanticType": "data-migration-lineage",
                "migrationRisk": "high" if "COMP-3" in usage else "low",
            })
    return lineage


# ---------------------------------------------------------------------------
# Workflow context layer (SIR → requirement → backlog → test trace chains)
# ---------------------------------------------------------------------------

def _build_workflow_chains(
    semantic_ir: list[dict],
    requirements: list[dict],
    backlog: list[dict],
    tests: list[dict],
) -> list[dict]:
    # Pre-index for O(1) lookups
    reqs_by_sir: dict[str, list[dict]] = defaultdict(list)
    for req in requirements:
        for rule_id in req.get("sirRules", []):
            reqs_by_sir[rule_id].append(req)

    stories_by_req: dict[str, list[dict]] = defaultdict(list)
    for story in backlog:
        for req_id in story.get("requirementIds", []):
            stories_by_req[req_id].append(story)

    tests_by_req: dict[str, list[dict]] = defaultdict(list)
    for test in tests:
        tests_by_req[test.get("req", "")].append(test)

    chains: list[dict] = []
    seen_chain_ids: set[str] = set()

    for sir in semantic_ir:
        for rule in sir.get("rules", []):
            rule_id = rule["ruleId"]
            for req in reqs_by_sir.get(rule_id, []):
                for story in stories_by_req.get(req["id"], []):
                    chain_id = f"CHAIN:{rule_id}->{req['id']}->{story['id']}"
                    if chain_id in seen_chain_ids:
                        continue
                    seen_chain_ids.add(chain_id)
                    linked_tests = tests_by_req.get(req["id"], [])
                    chains.append({
                        "id": chain_id,
                        "sirRule": rule_id,
                        "sirStatement": rule.get("statement", ""),
                        "astNode": rule.get("astNode", ""),
                        "legacyEvidence": rule.get("legacyLines", ""),
                        "requirement": req["id"],
                        "requirementStatement": req.get("statement", ""),
                        "backlogItem": story["id"],
                        "backlogTitle": story.get("title", ""),
                        "wave": story.get("wave", 1),
                        "testCases": [t["id"] for t in linked_tests],
                        "trustBoundary": rule.get("trustBoundary", "Application Logic"),
                        "traceComplete": bool(linked_tests),
                    })
    return chains


# ---------------------------------------------------------------------------
# Bidirectional shared-kernel detection
# A node is a shared kernel if it is accessed (as source OR target) by
# programs belonging to more than one capability.
# ---------------------------------------------------------------------------

def _detect_shared_kernels(
    edges: list[dict],
    programs: list[dict],
    tables: list[dict],
) -> list[dict]:
    prog_cap: dict[str, str] = {p["id"]: p.get("capability", "") for p in programs}
    table_ids: set[str] = {t["id"] for t in tables}

    # Resolve a node id to its capability — strip path prefix if present
    def resolve_cap(node_id: str) -> str | None:
        cap = prog_cap.get(node_id)
        if cap:
            return cap
        short = node_id.split(":")[-1]
        return prog_cap.get(short)

    # For each node, collect all capabilities that touch it (either direction)
    node_caps: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        kind = edge.get("kind", "")
        if kind in {"CONTAINS", "IN_SCOPE_OF", "OWNS_DATA"}:
            continue
        src, tgt = edge.get("source", ""), edge.get("target", "")
        src_cap = resolve_cap(src)
        tgt_cap = resolve_cap(tgt)
        if src_cap:
            node_caps[tgt].add(src_cap)
        if tgt_cap:
            node_caps[src].add(tgt_cap)

    shared: list[dict] = []
    for node_id, caps in node_caps.items():
        if len(caps) < 2:
            continue
        node_type = "table" if node_id in table_ids else "program"
        coupling = len(caps)
        shared.append({
            "id": f"SK:{node_id}",
            "nodeId": node_id,
            "nodeType": node_type,
            "consumingCapabilities": sorted(caps),
            "couplingDegree": coupling,
            "recommendation": (
                "Extract as Shared Kernel microservice with Anti-Corruption Layer facade"
                if node_type == "program"
                else "Implement dual-write CDC pattern; assign clear data ownership"
            ),
            "migrationRisk": "critical" if coupling >= 3 else "high",
        })
    return sorted(shared, key=lambda s: -s["couplingDegree"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _group_by(items: list[dict], key: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for item in items:
        val = item.get(key)
        if val:
            result[val].append(item.get("id", ""))
    return dict(result)


# ---------------------------------------------------------------------------
# Step 1 — Trace Entry Points to Data Sinks (End-to-End Business Use Cases)
# ---------------------------------------------------------------------------

_ENTRY_TYPES = {"screen", "job", "event"}
_SINK_KINDS  = {"READS", "WRITES"}


def _trace_use_case_flows(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Walk from every entry-point node through CALLS chains to READS/WRITES sinks.

    Each distinct (entry, frozenset-of-tables) pair becomes a candidate use case.
    """
    node_map  = {n["id"]: n for n in nodes}
    # adjacency: source → [(target, kind)]
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in edges:
        adj[e["source"]].append((e["target"], e["kind"]))

    entry_nodes = [n for n in nodes if n.get("type") in _ENTRY_TYPES]

    flows: list[dict] = []
    seen_keys: set[tuple] = set()

    for entry in entry_nodes:
        # BFS / DFS — collect all reachable nodes and the tables touched
        visited: set[str] = set()
        stack = [entry["id"]]
        call_chain: list[str] = []
        tables_read: list[str] = []
        tables_written: list[str] = []

        while stack:
            nid = stack.pop()
            if nid in visited:
                continue
            visited.add(nid)
            n = node_map.get(nid)
            if n and n.get("type") == "program":
                call_chain.append(nid)
            for tgt, kind in adj.get(nid, []):
                if kind == "CALLS":
                    stack.append(tgt)
                elif kind == "READS":
                    tables_read.append(tgt)
                elif kind == "WRITES":
                    tables_written.append(tgt)

        all_tables = sorted(set(tables_read + tables_written))
        if not all_tables:
            continue

        key = (entry["id"], tuple(all_tables))
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # Derive a human-readable label from the entry node
        entry_label = entry.get("label", entry["id"]).split("\n")[0]
        mutation = bool(tables_written)
        flows.append({
            "id": f"UC:{entry['id']}",
            "entryPoint": entry["id"],
            "entryLabel": entry_label,
            "entryType": entry.get("type", "unknown"),
            "callChain": call_chain,
            "tablesRead": sorted(set(tables_read)),
            "tablesWritten": sorted(set(tables_written)),
            "transactionBoundary": all_tables,
            "isMutation": mutation,
            "candidateUseCaseName": _infer_use_case_name(entry_label, tables_written, tables_read),
        })

    return flows


def _flows_from_code_workflows(code_workflows: list[dict], nodes: list[dict]) -> list[dict]:
    """Use-case flows from traced code workflows (entry action -> calls -> data/external)."""
    label = {n["id"]: n.get("label", n["id"]) for n in nodes}
    flows: list[dict] = []
    seen: set[tuple] = set()
    for wf in code_workflows:
        if wf.get("entryKind") == "controller-action" and any(
                f["entryPoint"] == wf["entryPoint"] for f in flows):
            continue
        tables_read, tables_written = wf.get("reads", []), wf.get("writes", [])
        all_tables = sorted(set(tables_read) | set(tables_written))
        if not all_tables:
            continue
        key = (wf["entryPoint"], tuple(all_tables))
        if key in seen:
            continue
        seen.add(key)
        entry_type, _, member = wf["entryPoint"].rpartition(".")
        trig = wf.get("trigger") or {}
        entry_label = f"{label.get(entry_type, entry_type)}.{member}"
        if trig:
            entry_label = f"{trig.get('verb')} {trig.get('url')} → {entry_label}"
        chain = []
        for s in wf.get("steps", []):
            if s["kind"] == "CALLS":
                owner = s["to"].rpartition(".")[0]
                if owner and owner not in chain and owner != entry_type:
                    chain.append(owner)
        flows.append({
            "id": f"UC:{wf['id']}",
            "entryPoint": wf["entryPoint"],
            "entryLabel": entry_label,
            "entryType": wf.get("entryKind", "unknown"),
            "callChain": chain,
            "tablesRead": sorted(set(tables_read)),
            "tablesWritten": sorted(set(tables_written)),
            "transactionBoundary": all_tables,
            "externals": wf.get("externals", []),
            "isMutation": bool(tables_written),
            "fullyTraced": wf.get("fullyTraced", False),
            "evidence": {"file": wf.get("file"), "line": wf.get("line")},
            "candidateUseCaseName": _infer_use_case_name(
                entry_label, [label.get(t, t) for t in sorted(set(tables_written))],
                [label.get(t, t) for t in sorted(set(tables_read))]),
        })
    return flows


def _infer_use_case_name(entry_label: str, written: list[str], read: list[str]) -> str:
    label = entry_label.strip().title()
    if written:
        return f"{label} → Mutates {', '.join(written[:2])}"
    if read:
        return f"{label} → Reads {', '.join(read[:2])}"
    return label


# ---------------------------------------------------------------------------
# Step 2 — Graph Clustering for Logical Domain Modules
# ---------------------------------------------------------------------------

_HUB_LABELS = {
    "logging", "auth", "authentication", "error", "date", "util", "shared",
    "common", "helper", "format", "config", "ssmap", "bms",
}


def _cluster_logical_modules(
    nodes: list[dict],
    edges: list[dict],
    shared_kernels: list[dict],
) -> list[dict]:
    """Group nodes into logical modules using capability membership + shared-kernel
    coupling analysis (lightweight community detection without external deps).

    Hub nodes (logging, auth, etc.) are filtered out so they don't merge distinct
    business modules.
    """
    # Identify hub node ids to exclude from clustering
    hub_ids: set[str] = set()
    for n in nodes:
        label_lower = n.get("label", "").lower()
        if any(h in label_lower for h in _HUB_LABELS):
            hub_ids.add(n["id"])

    # Group non-hub program/table nodes by capability
    cap_members: dict[str, list[dict]] = defaultdict(list)
    for n in nodes:
        if n.get("type") in {"program", "table", "entity"} and n["id"] not in hub_ids:
            cap = n.get("capability", "shared")
            cap_members[cap].append(n)
    write_edges = [e for e in edges if "WRITES" in _normalized_kinds(e)]
    cap_names = {n.get("capability"): n.get("label") for n in nodes if n.get("type") == "capability"}

    # Build intra-capability edge density
    cap_edge_counts: dict[str, int] = defaultdict(int)
    cap_cross_counts: dict[str, int] = defaultdict(int)
    node_cap = {n["id"]: n.get("capability", "shared") for n in nodes}
    for e in edges:
        sc = node_cap.get(e["source"], "")
        tc = node_cap.get(e["target"], "")
        if sc and tc:
            if sc == tc:
                cap_edge_counts[sc] += 1
            else:
                cap_cross_counts[sc] += 1
                cap_cross_counts[tc] += 1

    # Shared kernel ids per capability
    sk_by_cap: dict[str, list[str]] = defaultdict(list)
    for sk in shared_kernels:
        nid = sk["nodeId"]
        cap = node_cap.get(nid, "")
        if cap:
            sk_by_cap[cap].append(nid)

    modules: list[dict] = []
    for cap_id, members in cap_members.items():
        programs = [m for m in members if m.get("type") == "program"]
        tables   = [m for m in members if m.get("type") in {"table", "entity"}]
        intra    = cap_edge_counts.get(cap_id, 0)
        cross    = cap_cross_counts.get(cap_id, 0)
        cohesion = round(intra / max(intra + cross, 1), 2)
        sk_ids   = sk_by_cap.get(cap_id, [])

        # Data ownership: tables exclusively written by this capability
        owned_tables = [
            t["id"] for t in tables
            if any(node_cap.get(e["source"], "") == cap_id and e["target"] == t["id"] for e in write_edges)
            and not any(node_cap.get(e["source"], "") != cap_id and e["target"] == t["id"] for e in write_edges)
        ]

        ids = {m["id"] for m in members}
        touching = [e for e in edges if e["kind"] != "CONTAINS" and (e["source"] in ids or e["target"] in ids)]
        modules.append({
            "moduleId": cap_id,
            "moduleName": cap_names.get(cap_id, cap_id),
            "evidenceEdgeCount": len(touching),
            "evidenceKinds": sorted({e["kind"] for e in touching}),
            "programs": [p["id"] for p in programs],
            "tables": [t["id"] for t in tables],
            "ownedTables": owned_tables,
            "intraEdges": intra,
            "crossEdges": cross,
            "cohesionScore": cohesion,
            "sharedKernels": sk_ids,
            "isHighlyCoupled": cross > intra,
            "recommendedBoundary": (
                "Shared Kernel — extract as ACL facade"
                if sk_ids else
                "Bounded Context — candidate microservice"
                if cohesion >= 0.6 else
                "Loosely Coupled — consider merging with adjacent module"
            ),
        })

    return sorted(modules, key=lambda m: -m["cohesionScore"])


# ---------------------------------------------------------------------------
# Step 3 — Extract Business Rules and Domain Vocabulary from AST + AKG
# ---------------------------------------------------------------------------

_RULE_KINDS = {"deterministic_business_rule", "rule"}


def _extract_business_rules(semantic_ir: list[dict], nodes: list[dict]) -> list[dict]:
    """Mine conditional/validation rules from SIR entries and annotate with
    domain vocabulary extracted from node labels and table names.
    """
    node_vocab: set[str] = set()
    for n in nodes:
        for word in n.get("label", "").replace("\n", " ").split():
            if len(word) >= 4:
                node_vocab.add(word.title())

    rules: list[dict] = []
    for sir in semantic_ir:
        module = sir.get("module", "shared")
        for rule in sir.get("rules", []):
            if rule.get("kind") == "legacy_plumbing_pruned":
                continue
            rules.append({
                "ruleId": rule["ruleId"],
                "module": module,
                "statement": rule.get("statement", ""),
                "classification": rule.get("classification", ""),
                "astNode": rule.get("astNode", ""),
                "legacyEvidence": rule.get("legacyLines", ""),
                "snippet": rule.get("snippet", ""),
                "trustBoundary": rule.get("trustBoundary", "Application Logic"),
                "domainVocabulary": sorted(
                    w for w in node_vocab
                    if w.lower() in rule.get("statement", "").lower()
                )[:6],
            })

    return rules


# ---------------------------------------------------------------------------
# Public: identify_scope — combines all three steps
# ---------------------------------------------------------------------------

def identify_scope(seed: dict) -> dict:
    """Run the three-step AKG+AST scope identification pipeline and return a
    structured scope-identification report.

    Steps:
      1. Trace entry points → data sinks  (business use-case flows)
      2. Graph clustering                  (logical domain modules)
      3. Business rule & vocabulary mining (domain semantics)
    """
    applied: dict = seed.get("applied_graph") or build_applied_graph(seed)
    nodes: list[dict] = applied.get("nodes", [])
    edges: list[dict] = applied.get("edges", [])
    shared_kernels: list[dict] = applied.get("sharedKernels", [])
    semantic_ir: list[dict] = seed.get("semantic_ir", [])

    code_workflows: list[dict] = applied.get("codeWorkflows") or []
    use_case_flows   = (_flows_from_code_workflows(code_workflows, nodes) if code_workflows
                        else _trace_use_case_flows(nodes, edges))
    logical_modules  = _cluster_logical_modules(nodes, edges, shared_kernels)
    business_rules   = _extract_business_rules(semantic_ir, nodes)

    # Summarise domain vocabulary across all modules
    all_vocab: set[str] = set()
    for rule in business_rules:
        all_vocab.update(rule.get("domainVocabulary", []))

    return {
        "useCaseFlows": use_case_flows,
        "logicalModules": logical_modules,
        "businessRules": business_rules,
        "domainVocabulary": sorted(all_vocab),
        "summary": {
            "totalUseCaseFlows": len(use_case_flows),
            "mutatingFlows": sum(1 for f in use_case_flows if f["isMutation"]),
            "readOnlyFlows": sum(1 for f in use_case_flows if not f["isMutation"]),
            "logicalModuleCount": len(logical_modules),
            "businessRuleCount": len(business_rules),
            "sharedKernelCount": len(shared_kernels),
        },
        "basis": (
            "AKG+AST Scope Identification: entry-point tracing, "
            "graph clustering, and business rule extraction."
        ),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_applied_graph(seed: dict) -> dict:
    """Enrich the raw AST graph stored in *seed* and return the applied graph.

    The caller stores the result as ``seed["applied_graph"]``.
    """
    raw_graph: dict = seed.get("graph") or {"nodes": [], "edges": []}
    nodes: list[dict] = [dict(n) for n in raw_graph.get("nodes", [])]
    edges: list[dict] = [dict(e) for e in raw_graph.get("edges", [])]
    akg_layers: dict = seed.get("dotnet_akg") or {}

    # Evidence-backed graphs: an edge without a source location does not go in the graph.
    dropped_without_location = 0
    if raw_graph.get("evidenceRequired"):
        kept = [e for e in edges if e.get("file") and e.get("line")]
        dropped_without_location = len(edges) - len(kept)
        edges = kept

    programs: list[dict] = seed.get("programs", [])
    tables: list[dict] = seed.get("tables", [])
    semantic_ir: list[dict] = seed.get("semantic_ir", [])
    requirements: list[dict] = seed.get("requirements", [])
    backlog: list[dict] = seed.get("backlog", [])
    tests: list[dict] = seed.get("tests", [])
    copybook_schemas: list[dict] = seed.get("copybook_schemas", [])

    # Build outgoing-edge index before any mutations
    outgoing_kinds: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        outgoing_kinds[edge.get("source", "")].update(_normalized_kinds(edge))

    # Build SIR rule → node index for annotation
    sir_node_index: dict[str, list[str]] = defaultdict(list)
    for sir in semantic_ir:
        for rule in sir.get("rules", []):
            ast_node = rule.get("astNode", "")
            if ast_node:
                sir_node_index[ast_node].append(rule["ruleId"])

    # 1. Annotate nodes
    for node in nodes:
        nid = node["id"]
        ntype = node.get("type", "program")
        node["semanticRole"] = _infer_role(outgoing_kinds.get(nid, set()), ntype)
        node["trustBoundary"] = _infer_trust_boundary(nid, ntype)
        # Attach SIR rules whose astNode references this node id
        node["sirRules"] = [
            rule_id
            for ast_key, rule_ids in sir_node_index.items()
            if nid in ast_key
            for rule_id in rule_ids
        ]

    # 2. Enrich existing edges with semantic metadata (never overwrite what the extractor recorded)
    for edge in edges:
        for k, v in _EDGE_SEMANTIC.get(edge.get("kind", ""), {}).items():
            edge.setdefault(k, v)

    # 3. Synthesise OWNS_DATA edges (capability → table) for legacy graphs only. Evidence-backed
    #    graphs already carry capability membership as located CONTAINS edges.
    edge_id_set: set[str] = {e["id"] for e in edges}
    if not raw_graph.get("evidenceRequired"):
        for table in tables:
            cap_id = f"CAP-{table.get('capability', '')}"
            eid = f"{cap_id}->OWNS:{table['id']}"
            if eid not in edge_id_set:
                edges.append({
                    "id": eid,
                    "source": cap_id,
                    "target": table["id"],
                    "kind": "OWNS_DATA",
                    **_EDGE_SEMANTIC["OWNS_DATA"],
                })
                edge_id_set.add(eid)

    # 4. EMITS_EVENT is no longer synthesised from SIR side-effect prose: an event exists only
    #    when the extractor saw a real publisher call (MediatR/ServiceBus/EventBridge/SNS ...).

    # 5. Data lineage — from the source's own model, never from placeholders
    if akg_layers:
        data_lineage = [dict(r) for r in akg_layers.get("dataLineage", [])]
    else:
        data_lineage = _build_data_lineage(copybook_schemas)

    # 6. Workflow trace chains (SIR -> requirement -> backlog -> test) and code workflows
    workflow_chains = _build_workflow_chains(semantic_ir, requirements, backlog, tests)
    code_workflows: list[dict] = akg_layers.get("codeWorkflows", [])

    # 7. Shared kernel detection (bidirectional)
    if akg_layers:
        shared_kernels = [dict(k) for k in akg_layers.get("sharedKernels", [])]
    else:
        shared_kernels = _detect_shared_kernels(edges, programs, tables)

    # 8. Statistics
    kind_counts: dict[str, int] = defaultdict(int)
    for edge in edges:
        kind_counts[edge.get("kind", "UNKNOWN")] += 1

    total_chains = len(workflow_chains)
    traced_chains = sum(1 for c in workflow_chains if c["traceComplete"])

    return {
        "nodes": nodes,
        "edges": edges,
        "dataLineage": data_lineage,
        "workflowChains": workflow_chains,
        "codeWorkflows": code_workflows,
        "sharedKernels": shared_kernels,
        "diagnostics": akg_layers.get("diagnostics", {}),
        "engine": akg_layers.get("engine") or raw_graph.get("engine") or "inventory",
        "statistics": {
            "totalNodes": len(nodes),
            "capabilityNodes": sum(1 for n in nodes if n.get("type") == "capability"),
            "programNodes": sum(1 for n in nodes if n.get("type") == "program"),
            "tableNodes": sum(1 for n in nodes if n.get("type") in {"table", "entity"}),
            "eventNodes": sum(1 for n in nodes if n.get("type") == "event"),
            "externalNodes": sum(1 for n in nodes if n.get("type") == "external"),
            "totalEdges": len(edges),
            "edgesByKind": dict(kind_counts),
            "dataLineageFields": len(data_lineage),
            "totalWorkflowChains": total_chains,
            "tracedWorkflowChains": traced_chains,
            "codeWorkflows": len(code_workflows),
            "fullyTracedCodeWorkflows": sum(1 for w in code_workflows if w.get("fullyTraced")),
            "sharedKernelCount": len(shared_kernels),
            "edgesWithLocation": sum(1 for e in edges if e.get("file") and e.get("line")),
            "edgesDroppedWithoutLocation": dropped_without_location,
        },
        "semanticIndex": {
            "nodesByRole": _group_by(nodes, "semanticRole"),
            "nodesByTrustBoundary": _group_by(nodes, "trustBoundary"),
            "edgesBySemanticType": _group_by(edges, "semanticType"),
        },
        "basis": (
            "Applied Knowledge Graph: AST edges enriched with domain semantics, "
            "data lineage, workflow trace chains, and bidirectional shared-kernel coupling analysis."
        ),
    }
