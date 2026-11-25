from __future__ import annotations


def collect_dependencies(scope: dict, graph: dict, applied: dict) -> dict:
    module = scope["capabilityId"]
    nodes = {n["id"]: n for n in graph.get("nodes", []) if n.get("id")}
    for n in applied.get("nodes", []):
        if n.get("id"):
            nodes.setdefault(n["id"], n)
    edges = []
    seen = set()
    for e in [*graph.get("edges", []), *applied.get("edges", [])]:
        key = (e.get("source"), e.get("target"), e.get("kind"), e.get("file"), e.get("line"))
        if key not in seen:
            seen.add(key)
            edges.append(e)
    selected = {key for key, n in nodes.items() if n.get("capability") == module}
    reached = set(selected)
    reasons: dict[str, list[dict]] = {}
    # Follow actual outgoing relationships, never capability-container membership.
    changed = True
    while changed:
        changed = False
        for e in edges:
            if e.get("kind") == "CONTAINS" or e.get("source") not in reached:
                continue
            target = e.get("target")
            if target:
                reasons.setdefault(target, [])
                if e not in reasons[target]:
                    reasons[target].append(e)
                if target not in reached:
                    reached.add(target)
                    changed = True
    relevant = [e for e in edges if e.get("source") in reached or e.get("target") in selected]
    consumers = [e for e in relevant if e.get("target") in selected and e.get("source") not in selected
                 and e.get("kind") != "CONTAINS"]
    missing = sorted(reached - nodes.keys())
    external = [n for key, n in nodes.items() if key in reached and n.get("type") in {"external", "integration", "event"}]
    return {"selectedNodeIds": sorted(selected), "contextNodeIds": sorted(reached),
            "nodes": [nodes[k] for k in sorted(reached) if k in nodes], "edges": relevant,
            "incomingConsumers": consumers,
            "consumerNodes": [nodes[k] for k in sorted({e["source"] for e in consumers}) if k in nodes],
            "externalDependencies": external,
            "unresolvedNodeIds": missing, "inclusionEvidence": reasons,
            "sharedKernels": applied.get("sharedKernels", []),
            "completeness": "limited-to-existing-analysis"}
