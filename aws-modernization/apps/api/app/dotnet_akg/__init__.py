"""Evidence-backed Applied Knowledge Graph for .NET solutions.

    from app.dotnet_akg import build_dotnet_akg
    akg = build_dotnet_akg(Path("C:/src/ims"))

Two rules hold for everything this package emits:
  * nodes and edges come from parsers that understand the language
    (tree-sitter C#/TypeScript grammars + a solution-wide symbol table), not text matching;
  * every edge carries {file, line, rule_id}; an edge without a location is rejected.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

try:
    import tree_sitter as ts
except Exception:  # pragma: no cover - optional parser dependency in bare dev environments
    ts = None

from . import analysis, csharp, web
from .efmodel import load_ef_model
from .extract import EdgeSink, Extractor, assign_roles, classify_repository_methods
from .solution import load_workspace

__all__ = ["build_dotnet_akg", "is_dotnet_tree", "OVERRIDES_FILE"]

OVERRIDES_FILE = "akg-overrides.json"
ENGINE = "dotnet-akg/tree-sitter v1"

_EDGE_SEMANTICS = {
    "CALLS": ("synchronous-invocation", "low"),
    "ACCESSES_DATA": ("data-access", "medium"),
    "INHERITS": ("type-inheritance", "low"),
    "IMPLEMENTS": ("interface-implementation", "low"),
    "REFERENCES": ("entity-relationship", "medium"),
    "MAPS_TO": ("object-mapping", "low"),
    "HTTP_CALLS": ("http-request", "medium"),
    "INVOKES_EXTERNAL": ("external-integration", "high"),
    "EMITS_EVENT": ("domain-event-publication", "medium"),
    "CONTAINS": ("capability-membership", "low"),
    "RENDERS": ("ui-view-rendering", "low"),
    "BINDS_MODEL": ("ui-model-binding", "low"),
    "INCLUDES": ("ui-partial-view", "low"),
    "HOSTS_SCRIPT": ("ui-script-host", "low"),
    "READS_CONFIG": ("configuration-read", "medium"),
    "REFERENCES_PROJECT": ("project-reference", "low"),
}


def is_dotnet_tree(root: Path) -> bool:
    return any(root.rglob("*.sln")) or any(root.rglob("*.csproj"))


def _load_overrides(root: Path, overrides: dict | None) -> dict:
    if overrides is not None:
        return overrides
    p = root / OVERRIDES_FILE
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def build_dotnet_akg(root: Path, overrides: dict | None = None) -> dict:
    if ts is None:
        return {
            "nodes": [],
            "edges": [],
            "diagnostics": {"missingDependency": "tree-sitter is not installed"},
            "status": "NOT_VALIDATED",
        }
    root = Path(root).resolve()
    ws = load_workspace(root)
    overrides = _load_overrides(root, overrides)
    diagnostics: dict[str, list] = defaultdict(list)

    # -- parse + symbols ------------------------------------------------------
    cs_parser = csharp.parser()
    files: list[csharp.SourceFile] = []
    for proj in ws.projects:
        for rel in proj.compile:
            try:
                sf = csharp.parse_file(root, rel, proj.name, cs_parser)
            except OSError as exc:
                diagnostics["unreadableFiles"].append({"file": rel, "error": str(exc)})
                continue
            if sf.tree.root_node.has_error:
                diagnostics["parseErrors"].append({"file": rel})
            files.append(sf)
    tab = csharp.SymbolTable(files)
    entities = assign_roles(tab)
    repo_ops = classify_repository_methods(tab)

    # -- C# edges -------------------------------------------------------------
    sink = EdgeSink()
    ex = Extractor(tab, entities, repo_ops, sink)
    ex.declarations()
    ex.bodies()

    # -- HTTP surface ---------------------------------------------------------
    routes = web.build_route_table(tab)
    ts_parser = ts.Parser(web.TS_LANGUAGE)
    tsx_parser = ts.Parser(web.TSX_LANGUAGE)
    ts_nodes: list[dict] = []
    ts_by_ctrl: dict[str, str] = {}
    entry_points: list[dict] = []
    ts_files = [(p.name, rel) for p in ws.projects for rel in p.typescript] + [("(frontend)", rel) for rel in ws.frontend]
    for proj_name, rel in ts_files:
        try:
            calls, registered = web.ts_http_calls(root, rel, tsx_parser if rel.endswith(".tsx") else ts_parser)
        except OSError:
            continue
        tid = f"ts:{rel}"
        label = registered[0] if registered else PurePosixPath(rel).stem
        ts_nodes.append({"id": tid, "label": label, "type": "frontend",
                         "role": "typescript-controller" if registered else "typescript-module",
                         "path": rel, "file": rel, "line": 1, "project": proj_name})
        for r in registered:
            ts_by_ctrl[r] = tid
        for call in calls:
            hit = web.match_route(routes, call.url, call.verb)
            if hit is None:
                diagnostics["unresolvedHttpCalls"].append(
                    {"file": call.file, "line": call.line, "url": call.url, "verb": call.verb})
                continue
            action, how = hit
            sink.add("HTTP_CALLS", tid, action.controller.fqn, call.file, call.line, f"http.{how}",
                     actions=[action.method], verbs=[call.verb], urls=[call.url], via=[call.client])
            entry_points.append({"id": f"{tid}:{call.line}", "type": action.controller.fqn,
                                 "member": action.method, "kind": "http-call", "file": call.file,
                                 "line": call.line, "trigger": {"source": tid, "verb": call.verb, "url": call.url}})
    views = [v for p in ws.projects for v in p.views]
    view_nodes = web.razor_views(tab, root, views, sink, ts_by_ctrl)

    triggered = {(ep["type"], ep["member"]) for ep in entry_points}
    for a in routes.actions:
        if (a.controller.fqn, a.method) in triggered:
            continue  # already traced from the front-end call that reaches it
        entry_points.append({"id": f"{a.controller.fqn}.{a.method}", "type": a.controller.fqn, "member": a.method,
                             "kind": "controller-action", "file": a.controller.file, "line": a.line})
    for sym in tab.by_fqn.values():
        if sym.role == "http-application":
            for m in sym.members.get("Application_Start", []):
                entry_points.append({"id": f"{sym.fqn}.Application_Start", "type": sym.fqn,
                                     "member": "Application_Start", "kind": "application-start",
                                     "file": sym.file, "line": m.line})

    # -- configuration --------------------------------------------------------
    configs = [c for p in ws.projects for c in p.configs]
    cfg_entries = web.config_entries(root, configs)
    cfg_nodes: dict[str, dict] = {}
    for c in cfg_entries:
        cfg_nodes.setdefault(f"config:{c['key']}", {
            "id": f"config:{c['key']}", "label": c["key"], "type": "config", "role": c["kind"],
            "file": c["file"], "line": c["line"], **({"provider": c["provider"]} if c.get("provider") else {})})
    for fqn, key, file, ln in ex.config_reads:
        cid = f"config:{key}"
        if cid not in cfg_nodes:
            diagnostics["configKeysNotInConfigFiles"].append({"key": key, "file": file, "line": ln})
            cfg_nodes[cid] = {"id": cid, "label": key, "type": "config", "role": "app-setting (not declared)",
                              "file": file, "line": ln}
        sink.add("READS_CONFIG", fqn, cid, file, ln, "config.configuration-manager")

    # -- projects -------------------------------------------------------------
    proj_nodes = []
    for p in ws.projects:
        proj_nodes.append({"id": f"project:{p.path}", "label": p.name, "type": "project", "role": "msbuild-project",
                           "file": p.path, "line": 1, "files": len(p.compile)})
        for target, ln in p.project_refs:
            sink.add("REFERENCES_PROJECT", f"project:{p.path}", f"project:{target}", p.path, ln, "msbuild.project-reference")
        if p.missing:
            diagnostics["filesListedButMissing"].extend(p.missing)
    if ws.unlisted:
        diagnostics["filesNotInAnyProject"].extend(ws.unlisted)

    ef = load_ef_model(root, [r for p in ws.projects for r in p.resources])

    # -- nodes ----------------------------------------------------------------
    type_nodes = []
    for sym in tab.by_fqn.values():
        type_nodes.append({
            "id": sym.fqn, "label": sym.name, "type": "entity" if sym.role == "entity" else "program",
            "role": sym.role, "kind": sym.kind, "namespace": sym.namespace, "project": sym.project,
            "file": sym.file, "line": sym.line, "loc": sym.node.end_point[0] - sym.node.start_point[0] + 1,
            **({"entity": sym.entity.fqn} if sym.entity is not None else {}),
            **({"table": ef["entities"][sym.fqn]["table"]} if sym.fqn in ef["entities"] else {}),
        })
    edges = sink.all()
    known = {n["id"] for n in type_nodes} | {n["id"] for n in ts_nodes} | {n["id"] for n in view_nodes} \
        | set(cfg_nodes) | {n["id"] for n in proj_nodes}
    synthetic: dict[str, dict] = {}
    for e in edges:
        for end in (e["source"], e["target"]):
            if end in known or end in synthetic:
                continue
            if end.startswith("external:"):
                synthetic[end] = {"id": end, "label": end.split(":", 1)[1].rsplit(".", 1)[-1], "type": "external",
                                  "role": e.get("category", "external"), "qualifiedName": end.split(":", 1)[1],
                                  "file": e["file"], "line": e["line"]}
            elif end.startswith("event:"):
                synthetic[end] = {"id": end, "label": end.split(":", 1)[1], "type": "event", "role": "event-channel",
                                  "file": e["file"], "line": e["line"]}

    # -- capabilities ---------------------------------------------------------
    extra = ts_nodes + view_nodes
    workflows = analysis.build_workflows(tab, ex.facts, entry_points)
    cap_of, cap_info = analysis.assign_capabilities(tab, entities, sink, ex.facts, extra, workflows, overrides)
    for n in list(synthetic.values()) + list(cfg_nodes.values()):
        users = Counter(cap_of.get(e["source"]) for e in edges if e["target"] == n["id"])
        users.pop(None, None)
        real = {c for c in users if c != analysis.PLATFORM}
        cap_of[n["id"]] = real.pop() if len(real) == 1 else analysis.PLATFORM
    all_nodes = type_nodes + ts_nodes + view_nodes + list(cfg_nodes.values()) + list(synthetic.values())
    for n in all_nodes:
        n["capability"] = cap_of.get(n["id"], analysis.PLATFORM)
        b = cap_info["basis"].get(n["id"])
        if b:
            n["capabilityBasis"] = b
    for p in proj_nodes:
        p["capability"] = "projects"
    caps_used = sorted({n["capability"] for n in all_nodes})
    cap_nodes = []
    for i, cid in enumerate(caps_used):
        meta = cap_info["capabilities"].get(cid, {"id": cid, "name": cid})
        cap_nodes.append({"id": f"CAP-{cid}", "label": meta["name"], "type": "capability", "capability": cid})
    for n in all_nodes:
        b = n.get("capabilityBasis", {})
        sink.add("CONTAINS", f"CAP-{n['capability']}", n["id"], n.get("file"), n.get("line"),
                 b.get("rule", "capability.assignment"), basis=b.get("detail"))
    edges = sink.all()

    # Positions: one column per capability, members stacked beneath it.
    col: dict[str, int] = {c: i for i, c in enumerate(caps_used)}
    depth: Counter = Counter()
    for cn in cap_nodes:
        cn["position"] = {"x": 60 + col[cn["capability"]] * 300, "y": 40}
    for n in all_nodes:
        c = n["capability"]
        depth[c] += 1
        n["position"] = {"x": 40 + col[c] * 300 + (depth[c] % 2) * 130, "y": 110 + (depth[c] // 2) * 60}
    for i, p in enumerate(proj_nodes):
        p["position"] = {"x": -320, "y": 60 + i * 90}
    nodes = cap_nodes + all_nodes + proj_nodes

    for e in edges:
        sem, risk = _EDGE_SEMANTICS.get(e["kind"], ("relationship", "low"))
        e.setdefault("semanticType", sem)
        if e["kind"] == "ACCESSES_DATA" and "write" in e.get("operations", []):
            risk = "high"
        e.setdefault("migrationRisk", risk)

    # -- derived layers -------------------------------------------------------
    lineage = analysis.build_lineage(tab, entities, ex.maps, ef)
    node_types = {n["id"]: n["type"] for n in nodes}
    kernels = analysis.shared_kernels(edges, cap_of, node_types)

    kind_counts = Counter(e["kind"] for e in edges)
    capabilities = []
    for cid in caps_used:
        members = [n for n in all_nodes if n["capability"] == cid]
        capabilities.append({
            "id": cid, "name": cap_info["capabilities"].get(cid, {}).get("name", cid),
            "entities": sorted(n["id"] for n in members if n["type"] == "entity"),
            "types": sorted(n["id"] for n in members if n["type"] == "program"),
            "views": sorted(n["id"] for n in members if n["type"] == "view"),
            "frontend": sorted(n["id"] for n in members if n["type"] == "frontend"),
        })
    return {
        "engine": ENGINE,
        "root": str(root),
        "solution": ws.solution,
        "projects": [{"name": p.name, "path": p.path, "compile": len(p.compile), "typescript": len(p.typescript),
                      "views": len(p.views), "sdkStyle": p.sdk_style} for p in ws.projects],
        "nodes": nodes,
        "edges": edges,
        "capabilities": capabilities,
        "dataLineage": lineage,
        "codeWorkflows": workflows,
        "sharedKernels": kernels,
        "efModel": {"source": ef["source"], "entities": len(ef["entities"])},
        "diagnostics": {k: v for k, v in diagnostics.items() if v} | (
            {"rejectedEdges": sink.rejected} if sink.rejected else {}),
        "statistics": {
            "files": {"csharp": len(files), "typescript": len(ts_nodes), "razor": len(view_nodes),
                      "config": len(configs)},
            "types": len(type_nodes),
            "entities": len(entities),
            "totalNodes": len(nodes),
            "totalEdges": len(edges),
            "edgesByKind": dict(sorted(kind_counts.items())),
            "dataLineageFields": len(lineage),
            "codeWorkflows": len(workflows),
            "fullyTracedWorkflows": sum(1 for w in workflows if w["fullyTraced"]),
            "sharedKernelCount": len(kernels),
            "edgesWithoutLocation": sum(1 for e in edges if not e.get("file") or not e.get("line")),
        },
        "basis": ("Parsed with tree-sitter C#/TypeScript grammars and resolved against a solution-wide symbol "
                  "table; every edge carries file, line and rule_id."),
    }
