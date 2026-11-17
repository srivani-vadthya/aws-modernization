"""Project an AKG onto the engagement seed shapes the rest of the app consumes."""
from __future__ import annotations

from collections import Counter, defaultdict

from .analysis import PLATFORM

_LAYER_KEYS = ("engine", "solution", "projects", "capabilities", "dataLineage", "codeWorkflows",
               "sharedKernels", "efModel", "diagnostics", "statistics", "basis")


def apply_to_seed(seed: dict, akg: dict) -> dict:
    nodes, edges = akg["nodes"], akg["edges"]
    by_id = {n["id"]: n for n in nodes}
    cap_of = {n["id"]: n.get("capability") for n in nodes}

    seed["graph"] = {"nodes": nodes, "edges": edges, "evidenceRequired": True, "engine": akg["engine"],
                     "basis": akg["basis"]}
    seed["dotnet_akg"] = {k: akg[k] for k in _LAYER_KEYS if k in akg}
    # Remove placeholder layers that are not backed by this source tree.
    seed["copybook_schemas"] = []

    programs = [{"id": n["id"], "name": n["label"], "capability": n["capability"], "loc": n.get("loc", 0),
                 "online": True, "path": n.get("file"), "role": n.get("role")}
                for n in nodes if n["type"] == "program"]
    tables = [{"id": n["id"], "name": n["label"], "capability": n["capability"], "store": "relational",
               "table": n.get("table", n["label"]), "path": n.get("file")}
              for n in nodes if n["type"] == "entity"]

    out_caps: dict[str, Counter] = defaultdict(Counter)
    externals: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e["kind"] == "CONTAINS":
            continue
        a, b = cap_of.get(e["source"]), cap_of.get(e["target"])
        if a and b and a != b and b not in {PLATFORM, "projects"}:
            out_caps[a][b] += 1
        if e["kind"] == "INVOKES_EXTERNAL" and a:
            externals[a].add(e["target"])
    kernels_by_cap: Counter = Counter()
    for k in akg.get("sharedKernels", []):
        for c in k["consumingCapabilities"]:
            kernels_by_cap[c] += 1

    caps = []
    for c in akg["capabilities"]:
        cid = c["id"]
        progs = [p for p in programs if p["capability"] == cid]
        tbls = [t for t in tables if t["capability"] == cid]
        loc = sum(p["loc"] for p in progs)
        ext_pts = min(30, 10 * len(externals[cid]))
        cross_pts = min(35, 3 * sum(out_caps[cid].values()))
        kernel_pts = min(20, 5 * kernels_by_cap[cid])
        loc_pts = 15 if loc > 3000 else 8 if loc > 1000 else 3
        score = min(100, ext_pts + cross_pts + kernel_pts + loc_pts)
        caps.append({
            "id": cid,
            "name": c["name"],
            "summary": (f"{len(tbls)} entities, {len(progs)} types, {len(c['views'])} views, "
                        f"{len(c['frontend'])} TypeScript controllers"),
            "programs": len(progs), "tables": len(tbls), "jobs": 0,
            "screens": len(c["views"]) + len(c["frontend"]),
            "shared": cid == PLATFORM,
            "coupling": f"{sum(out_caps[cid].values())} outgoing cross-capability edges",
            "risk": "high" if score >= 70 else "medium" if score >= 40 else "low",
            "riskScore": score,
            "riskBreakdown": {
                "externalIntegrationPoints": ext_pts, "crossCapabilityPoints": cross_pts,
                "sharedKernelPoints": kernel_pts, "codeVolumePoints": loc_pts,
                "rationale": (f"{len(externals[cid])} external integrations, {sum(out_caps[cid].values())} "
                              f"cross-capability edges, {kernels_by_cap[cid]} shared kernels, {loc} LOC."),
            },
            "loc": loc,
            "complexity": "high" if len(progs) > 12 else "medium" if len(progs) > 4 else "low",
            "dependsOn": [d for d, _ in out_caps[cid].most_common(5)],
            "integrations": sorted(f"INT-{by_id[x]['label']}" for x in externals[cid] if x in by_id),
            "components": ([{"id": p["id"], "name": p["name"], "kind": "program", "loc": p["loc"],
                             "role": p.get("role")} for p in progs]
                           + [{"id": t["id"], "name": t["name"], "kind": "table", "store": t["store"],
                               "role": f"table {t['table']}"} for t in tbls]),
            "basis": "Assigned from entity writes/reads in the AKG (see node capabilityBasis)",
        })
    caps.sort(key=lambda c: (c["shared"], -(c["programs"] + c["tables"])))
    for i, c in enumerate(caps, 1):
        c["recommendedOrder"] = i
    seed["capabilities"] = caps
    seed["programs"] = programs
    seed["tables"] = tables

    integrations = []
    for n in nodes:
        if n["type"] != "external":
            continue
        users = sorted({cap_of[e["source"]] for e in edges if e["target"] == n["id"] and cap_of.get(e["source"])})
        integrations.append({
            "id": f"INT-{n['label']}", "name": n["qualifiedName"], "kind": n.get("role", "external"),
            "protocol": n.get("role", ""), "direction": "outbound", "inCodebase": False,
            "evidence": f"{n['file']}#L{n['line']}", "usedBy": users,
            "note": "Resolved from a framework type the solution does not define (INVOKES_EXTERNAL).",
        })
    discovery = seed.setdefault("discovery", {})
    discovery["integrations"] = integrations
    discovery["engine"] = akg["engine"]
    stats = akg["statistics"]
    discovery["notes"] = (f"Parsed {stats['files']['csharp']} C#, {stats['files']['typescript']} TypeScript and "
                          f"{stats['files']['razor']} Razor files from {akg.get('solution') or 'project files'}; "
                          f"{stats['totalEdges']} evidence-backed edges.")
    return seed
