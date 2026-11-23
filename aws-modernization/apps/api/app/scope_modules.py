"""Scope step: business modules / use cases derived from the AKG + AST, with their source files.

Everything structural here is computed from the engagement's own graph (AKG) and parsed inventory (AST):
modules, use cases, file lists, coupling. The LLM is only asked to *describe* what the graph says in
business language (module summary, use-case names); it never adds files, edges or modules.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from . import knowledge_graph
from .llm_json import ask_json

logger = logging.getLogger(__name__)

_FILE_NODE_TYPES = {"program": "code", "entity": "data model", "table": "data model",
                    "view": "view", "frontend": "frontend", "config": "config"}
_LANG_BY_EXT = {".cs": "C#", ".ts": "TypeScript", ".js": "JavaScript", ".cshtml": "Razor", ".aspx": "ASPX",
                ".cbl": "COBOL", ".cblle": "COBOL", ".cob": "COBOL", ".cpy": "Copybook", ".rpgle": "RPG",
                ".sqlrpgle": "RPG", ".clle": "CL", ".pf": "DDS", ".dspf": "DDS", ".sql": "SQL",
                ".java": "Java", ".py": "Python", ".config": "Config", ".json": "JSON", ".html": "HTML"}
_ENRICH_CHUNK = 5          # modules per LLM call
_USE_CASES_SENT = 8        # use cases per module shown to the LLM


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lang(path: str) -> str:
    return _LANG_BY_EXT.get(PurePosixPath(path).suffix.lower(), PurePosixPath(path).suffix.lstrip(".").upper() or "file")


def ensure_analysis(seed: dict) -> dict:
    """Make sure applied_graph + scope_analysis exist in the seed; returns scope_analysis."""
    if not seed.get("applied_graph"):
        seed["applied_graph"] = knowledge_graph.build_applied_graph(seed)
    if not seed.get("scope_analysis"):
        seed["scope_analysis"] = knowledge_graph.identify_scope(seed)
    return seed["scope_analysis"]


def _node_path(node: dict) -> str | None:
    return node.get("file") or node.get("path")


def _inventory_index(eng: dict) -> dict[str, str]:
    """stem (upper-case) -> path, so legacy programs without a path can still be tied to a file."""
    index: dict[str, str] = {}
    for a in (eng.get("inventory") or {}).get("assets", []):
        index.setdefault(PurePosixPath(a["path"]).stem.upper(), a["path"])
    return index


def _words(identifier: str) -> str:
    """CamelCase / snake_case identifier -> 'Camel Case' words."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|[_\-]+", " ", identifier)
    return " ".join(spaced.split())


def use_case_name(flow: dict) -> str:
    """Neutral, graph-derived name: '<Owner>: <Action>' (the LLM may later reword it)."""
    owner, _, member = str(flow["entryPoint"]).rpartition(".")
    owner = owner.rpartition(".")[2] or owner
    for suffix in ("ApiController", "Controller", "Api"):
        if owner.endswith(suffix) and len(owner) > len(suffix):
            owner = owner[: -len(suffix)]
            break
    return f"{_words(owner)}: {_words(member)}" if owner else _words(member)


def _flow_capability(flow: dict, node_cap: dict[str, str]) -> str | None:
    """A use case belongs to the capability that owns the data it writes (else reads, else its entry point)."""
    for key in ("tablesWritten", "tablesRead"):
        owners = Counter(node_cap[t] for t in flow.get(key, []) if node_cap.get(t))
        if owners:
            return owners.most_common(1)[0][0]
    return node_cap.get(flow.get("entryPoint", ""))


def flows_by_module(seed: dict) -> dict[str, list[dict]]:
    analysis = ensure_analysis(seed)
    nodes = (seed.get("applied_graph") or {}).get("nodes") or (seed.get("graph") or {}).get("nodes", [])
    node_cap = {n["id"]: n.get("capability") for n in nodes}
    out: dict[str, list[dict]] = defaultdict(list)
    for flow in analysis.get("useCaseFlows", []):
        cap = _flow_capability(flow, node_cap)
        if cap:
            out[cap].append(flow)
    for flows in out.values():
        flows.sort(key=lambda f: (not f["isMutation"], f["candidateUseCaseName"]))
    return out


def _module_files(cap_id: str, nodes: list[dict], seed: dict, inv: dict[str, str],
                  kernel_nodes: set[str], flow_nodes: set[str]) -> list[dict]:
    programs = {p["id"]: p for p in seed.get("programs", [])}
    files: dict[str, dict] = {}
    for n in nodes:
        if n.get("capability") != cap_id or n.get("type") not in _FILE_NODE_TYPES:
            continue
        path = _node_path(n) or (programs.get(n["id"]) or {}).get("path") or inv.get(str(n["id"]).upper())
        if not path:
            continue
        label = str(n.get("label", n["id"])).split("\n")[0]
        row = files.setdefault(path, {"path": path, "kind": _FILE_NODE_TYPES[n["type"]], "language": _lang(path),
                                      "loc": 0, "symbols": [], "shared": False, "inUseCase": False})
        row["loc"] += int(n.get("loc") or 0)
        row["symbols"].append(label)
        row["shared"] = row["shared"] or n["id"] in kernel_nodes
        row["inUseCase"] = row["inUseCase"] or n["id"] in flow_nodes
        if n.get("role") and n.get("type") == "program":
            row.setdefault("roles", [])
            if n["role"] not in row["roles"]:
                row["roles"].append(n["role"])
    rows = sorted(files.values(), key=lambda r: (r["kind"], r["path"]))
    for r in rows:
        r["symbols"] = sorted(set(r["symbols"]))
    return rows


def _structural_modules(eng: dict) -> list[dict]:
    seed = eng.get("seed") or {}
    ensure_analysis(seed)
    applied = seed["applied_graph"]
    nodes = applied.get("nodes", [])
    edges = applied.get("edges", [])
    caps = {c["id"]: c for c in seed.get("capabilities", [])}
    logical = {m["moduleId"]: m for m in seed["scope_analysis"].get("logicalModules", [])}
    kernel_nodes = {k["nodeId"] for k in applied.get("sharedKernels", [])}
    cap_name = {c["id"]: c["name"] for c in caps.values()}
    node_cap = {n["id"]: n.get("capability") for n in nodes}
    inv = _inventory_index(eng)
    flows = flows_by_module(seed)

    modules: list[dict] = []
    for cap_id, cap in caps.items():
        lm = logical.get(cap_id)
        mod_flows = flows.get(cap_id, [])
        flow_nodes = {t for f in mod_flows for t in (f["tablesRead"] + f["tablesWritten"] + f.get("callChain", [])
                                                     + [f["entryPoint"]])}
        files = _module_files(cap_id, nodes, seed, inv, kernel_nodes, flow_nodes)
        member_ids = {n["id"] for n in nodes if n.get("capability") == cap_id}
        touching = [e for e in edges if e.get("kind") != "CONTAINS"
                    and (e["source"] in member_ids or e["target"] in member_ids)]
        cross = {node_cap.get(e["target"]) for e in touching if e["source"] in member_ids} - {cap_id, None}
        if not files and not mod_flows and not touching:
            continue  # nothing in the graph backs this capability
        modules.append({
            "id": cap_id,
            "name": cap["name"],
            "displayName": None,
            "summary": cap.get("summary", ""),
            "businessSummary": None,
            "shared": bool(cap.get("shared")),
            "metrics": {"programs": cap.get("programs", 0), "tables": cap.get("tables", 0),
                        "screens": cap.get("screens", 0), "files": len(files), "useCases": len(mod_flows),
                        "loc": cap.get("loc") or sum(f["loc"] for f in files),
                        "evidenceEdges": len(touching)},
            "risk": cap.get("risk", "unknown"), "riskScore": cap.get("riskScore"),
            "coupling": cap.get("coupling", ""),
            "cohesion": (lm or {}).get("cohesionScore"),
            "boundary": (lm or {}).get("recommendedBoundary"),
            "ownedTables": [t.split(".")[-1] for t in (lm or {}).get("ownedTables", [])],
            "sharedKernels": [k.split(".")[-1] for k in (lm or {}).get("sharedKernels", [])],
            "dependsOn": [cap_name.get(c, c) for c in sorted(cross)],
            "evidenceKinds": sorted({e["kind"] for e in touching}),
            "useCases": [{
                "id": f["id"], "name": use_case_name(f), "entry": f["entryLabel"],
                "entryPoint": f["entryPoint"], "mutates": f["isMutation"],
                "reads": [t.split(".")[-1] for t in f["tablesRead"]],
                "writes": [t.split(".")[-1] for t in f["tablesWritten"]],
                "externals": [x.split(".")[-1] for x in f.get("externals", [])],
                "description": None,
            } for f in mod_flows],
            "files": files,
        })
    return _rank_for_modernization(modules, {m["name"]: m["id"] for m in modules})


def _rank_for_modernization(modules: list[dict], id_by_name: dict[str, str]) -> list[dict]:
    """Order modules by which should be modernized first: the most widely used (shared) modules come first.

    Modules that many other modules depend on are foundations; modernizing them first lets their consumers be
    migrated against the new version. Sort key: incoming dependencies (descending), then fewer outgoing
    dependencies (more self-contained first), then use-case count, then name. Dependencies come from AKG edges.
    Adds `modernization = {rank, score, reason}` to each module (`score` = incoming dependency count).
    """
    inbound: dict[str, int] = {m["id"]: 0 for m in modules}
    for m in modules:
        for dep in m["dependsOn"]:
            if id_by_name.get(dep) in inbound:
                inbound[id_by_name[dep]] += 1
    for m in modules:
        inn, out = inbound[m["id"]], len(m["dependsOn"])
        reason = (f"used by {inn} other module{'s' if inn != 1 else ''}" if inn else "not used by any other module")
        reason += f"; depends on {out} other module{'s' if out != 1 else ''}" if out else "; depends on no other modules"
        m["modernization"] = {"rank": 0, "score": inn, "reason": reason}
    modules.sort(key=lambda m: (-inbound[m["id"]], len(m["dependsOn"]), -m["metrics"]["useCases"], m["name"]))
    for i, m in enumerate(modules, 1):
        m["modernization"]["rank"] = i
    return modules


def _digest(modules: list[dict]) -> str:
    slim = [{"id": m["id"], "name": m["name"], "m": m["metrics"], "uc": [u["id"] for u in m["useCases"]],
             "f": [f["path"] for f in m["files"]]} for m in modules]
    return hashlib.sha256(json.dumps(slim, sort_keys=True).encode()).hexdigest()[:16]


_SYSTEM = (
    "You are a business analyst describing parts of a legacy application for a modernization team. "
    "You receive, per module, FACTS extracted from the application's AST and knowledge graph: entities, "
    "entry points, data read/written, key conditions from the code, coupling. Describe what the module does for the business in plain "
    "language. Where a use case has keyConditions (validation or branching found in its code), reflect them in the "
    "description as business rules. Use ONLY the supplied facts: never invent entities, screens, rules or numbers. If the facts are "
    "too thin to say something, say so briefly instead of guessing. Reply with JSON only."
)


_LOGIC_PER_USE_CASE = 2    # key branch/validation conditions shown to the LLM per use case


def _key_logic(eng: dict, modules: list[dict]) -> dict[str, dict[int, list[str]]]:
    """module id -> {use-case ref -> key AST conditions (if/throw/validation lines of the entry method)}."""
    from . import sir_generator, store  # local import: sir_generator imports this module
    seed = eng.get("seed") or {}
    wf_by_id = {w["id"]: w for w in (seed.get("dotnet_akg") or {}).get("codeWorkflows", [])}
    if not wf_by_id:
        return {}
    src = sir_generator._Source(store.engagement_dir(eng["id"]) / "source")
    flows = flows_by_module(seed)
    out: dict[str, dict[int, list[str]]] = {}
    for m in modules:
        for ref, flow in enumerate(flows.get(m["id"], [])[:_USE_CASES_SENT]):
            wf = wf_by_id.get(flow["id"].removeprefix("UC:"))
            try:
                rules, _ = sir_generator._branch_rules("", 0, flow, wf, src)
            except Exception:  # unreadable/odd source must never block the module cards
                continue
            conds = [r["statement"].removeprefix("Branches on: ") for r in rules[:_LOGIC_PER_USE_CASE]]
            if conds:
                out.setdefault(m["id"], {})[ref] = conds
    return out


def _enrich_chunk(chunk: list[dict], logic: dict[str, dict[int, list[str]]] | None = None) -> tuple[dict[str, dict], str | None]:
    logic = logic or {}
    facts = [{"id": m["id"], "name": m["name"], "entities": m["ownedTables"], "tables": m["metrics"]["tables"],
              "codeAssets": m["metrics"]["programs"], "screens": m["metrics"]["screens"],
              "dependsOn": m["dependsOn"], "sharedAssets": m["sharedKernels"],
              "useCases": [{"ref": i, "entry": u["entry"], "mutates": u["mutates"], "reads": u["reads"],
                            "writes": u["writes"], "externals": u["externals"],
                            "keyConditions": logic.get(m["id"], {}).get(i, [])}
                           for i, u in enumerate(m["useCases"][:_USE_CASES_SENT])]} for m in chunk]
    user = (
        "For every module return an object in a JSON array:\n"
        '{"id": <module id>, "displayName": <2-4 word business name>, '
        '"businessSummary": <1-2 sentences on what the business does here>, '
        '"useCases": [{"ref": <ref>, "name": <short business use-case name>, '
        '"description": <one sentence on the outcome>}]}\n\nFACTS:\n' + json.dumps(facts, indent=1))
    parsed, model = ask_json(_SYSTEM, user, max_tokens=3500)
    out: dict[str, dict] = {}
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and item.get("id"):
                out[str(item["id"])] = item
    return out, model


def _apply_enrichment(modules: list[dict], enriched: dict[str, dict]) -> int:
    touched = 0
    for m in modules:
        e = enriched.get(m["id"])
        if not e:
            continue
        if isinstance(e.get("displayName"), str) and e["displayName"].strip():
            m["displayName"] = e["displayName"].strip()[:60]
        if isinstance(e.get("businessSummary"), str) and e["businessSummary"].strip():
            m["businessSummary"] = e["businessSummary"].strip()[:400]
        for uc in e.get("useCases") or []:
            if isinstance(uc, dict) and isinstance(uc.get("ref"), int) and 0 <= uc["ref"] < len(m["useCases"]):
                tgt = m["useCases"][uc["ref"]]
                if isinstance(uc.get("name"), str) and uc["name"].strip():
                    tgt["name"] = uc["name"].strip()[:100]
                if isinstance(uc.get("description"), str):
                    tgt["description"] = uc["description"].strip()[:240]
        touched += 1
    return touched


def build_scope_modules(eng: dict, *, use_llm: bool = True, refresh: bool = False) -> dict:
    """Module cards + use cases + file lists for the Scope screen. Caches LLM wording in the seed."""
    seed = eng.setdefault("seed", {})
    modules = _structural_modules(eng)
    digest = _digest(modules)
    cached = seed.get("scope_modules") or {}
    if cached.get("digest") == digest and not refresh and cached.get("enrichment", {}).get("status") == "llm":
        for m in modules:
            c = (cached.get("wording") or {}).get(m["id"])
            if c:
                _apply_enrichment([m], {m["id"]: c})
        return {"modules": modules, "enrichment": cached["enrichment"], "digest": digest, **_summary(modules)}

    enrichment: dict[str, Any] = {"status": "deterministic", "model": None, "generatedAt": _now(),
                                  "note": "Module facts come from the AKG/AST; no LLM wording was applied."}
    wording: dict[str, dict] = {}
    if use_llm and modules:
        models, failed = set(), 0
        logic = _key_logic(eng, modules)
        for i in range(0, len(modules), _ENRICH_CHUNK):
            chunk = modules[i:i + _ENRICH_CHUNK]
            got, model = _enrich_chunk(chunk, logic)
            if got:
                wording.update(got)
                _apply_enrichment(chunk, got)
                models.add(model)
            else:
                failed += 1
        if wording:
            enrichment.update(status="llm", model=", ".join(sorted(m for m in models if m)),
                              note=("Business wording generated by the LLM from AKG/AST facts."
                                    + (f" {failed} batch(es) fell back to graph-derived text." if failed else "")))
        else:
            enrichment.update(status="unavailable",
                              note="LLM unavailable; showing graph-derived descriptions only.")
    # Only a successful LLM pass is cached; otherwise the next visit retries the LLM.
    if enrichment["status"] == "llm":
        seed["scope_modules"] = {"digest": digest, "wording": wording, "enrichment": enrichment}
    return {"modules": modules, "enrichment": enrichment, "digest": digest, **_summary(modules)}


def _summary(modules: list[dict]) -> dict:
    return {
        "summary": {"modules": len(modules), "useCases": sum(m["metrics"]["useCases"] for m in modules),
                    "files": sum(m["metrics"]["files"] for m in modules)},
        "basis": "Modules, use cases and files are derived from the Applied Knowledge Graph and AST "
                 "(entry points traced to the data they read/write); no demo scopes are substituted.",
    }


def find_module(eng: dict, cap_id: str) -> dict | None:
    result = build_scope_modules(eng, use_llm=False)
    return next((m for m in result["modules"] if m["id"] == cap_id), None)
