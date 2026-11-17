"""Evidence-backed graph and downstream compatibility projection, without invented ASTs."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import posixpath


def enrich(report: dict) -> dict:
    assets = report["assets"]
    breakdown = {}
    for category in ("application", "vendor", "generated", "support", "unclassified"):
        rows = [a for a in assets if a["category"] == category]
        breakdown[category] = {"files": len(rows), "loc": sum(a["loc"] or 0 for a in rows)}
    report["summary"].update(applicationFiles=breakdown["application"]["files"],
        applicationLoc=breakdown["application"]["loc"], breakdown=breakdown,
        proposedModules=sum(m["type"] == "Inferred grouping" for m in report["modules"]),
        technicalGroups=sum(m["type"] == "Technical folder" for m in report["modules"]))
    report["applicationLanguages"] = dict(Counter(a["language"] for a in assets if a["category"] == "application"))
    groups = {}
    for row in report["integrations"]:
        # Group by mechanism and project, never pretend one API family is one external system.
        owners = [posixpath.dirname(p["path"]) for p in report["projects"]
                  if row["path"].startswith(posixpath.dirname(p["path"]) + "/")]
        owner = max(owners, key=len) if owners else row["path"].split("/")[0]
        key = (owner, row["name"])
        group = groups.setdefault(key, {"id": "integration:" + hashlib.sha256(repr(key).encode()).hexdigest()[:12],
            "name": row["name"], "project": owner, "paths": [], "referenceCount": 0,
            "status": "Grouped lexical leads", "direction": "Not resolved", "implementation": "Not verified",
            "groupingBasis": "Same API family in the same project; not a resolved external-system identity", "evidenceIds": []})
        group["referenceCount"] += 1
        group["paths"] = sorted(set(group["paths"] + [row["path"]]))
        group["evidenceIds"].extend(row["evidenceIds"])
    report["integrationGroups"] = list(groups.values())
    report["summary"]["integrationGroups"] = len(groups)
    report["summary"]["integrationReferences"] = len(report["integrations"])
    report["analysisCoverage"] = {
        "inventory": "Recognized file extensions plus other assets across repositories",
        "projectManifests": ".NET MSBuild projects; NuGet, npm and Bower package manifests",
        "declarations": "C# type and AngularJS registration lexical patterns",
        "ast": "Not generated; lexical declarations are not syntax trees",
        "unsupportedLanguages": sorted({a["language"] for a in assets if a["category"] == "application"
                                         and a["language"] not in {"C#", "JavaScript", "TypeScript", "HTML", "Razor", "ASPX", "CSS", "SCSS", "SQL"}}),
    }
    report["limits"][-1] = "File classification records its basis. Application ownership is provisional; uncertain library paths remain unclassified."
    nodes, edges = [], []
    file_nodes = {}
    for index, module in enumerate(report["modules"]):
        mid = module["id"]
        nodes.append({"id": "CAP-" + mid, "type": "capability", "label": module["name"], "capability": mid,
            "position": {"x": index * 320, "y": 0}, "evidenceIds": module["evidenceIds"], "basis": module["type"]})
        for n, path in enumerate(module["files"]):
            fid = mid + ":" + path
            file_nodes[path] = fid
            refs = [e["id"] for e in report["evidence"] if e["path"] == path and e["kind"] in {"module file membership", "folder membership"}]
            nodes.append({"id": fid, "type": "program", "label": posixpath.basename(path), "path": path,
                "capability": mid, "position": {"x": index * 320, "y": 80 + n * 60}, "evidenceIds": refs})
            edges.append({"id": "contains:" + fid, "source": "CAP-" + mid, "target": fid,
                          "kind": "CONTAINS", "basis": module["type"], "evidenceIds": refs})
    project_paths = {p["path"] for p in report["projects"]}
    for i, p in enumerate(report["projects"]):
        nodes.append({"id": "project:" + p["path"], "type": "project", "label": p["path"], "capability": "projects",
                      "position": {"x": -400, "y": i * 100}, "evidenceIds": p["evidenceIds"]})
    for i, r in enumerate(report["references"]):
        target = posixpath.normpath(posixpath.join(posixpath.dirname(r["source"]), r["target"]))
        if target in project_paths:
            edges.append({"id": f"project-ref:{i}", "source": "project:" + r["source"], "target": "project:" + target,
                          "kind": "REFERENCES_PROJECT", "basis": "Declared", "evidenceIds": r["evidenceIds"]})
    for i, group in enumerate(report["integrationGroups"]):
        nodes.append({"id": group["id"], "type": "integration", "label": group["name"], "capability": "references",
                      "position": {"x": -800, "y": i * 120}, "evidenceIds": group["evidenceIds"]})
        for path in group["paths"]:
            if path in file_nodes:
                refs = [r for r in group["evidenceIds"] if any(e["id"] == r and e["path"] == path for e in report["evidence"])]
                edges.append({"id": file_nodes[path] + "->" + group["id"], "source": file_nodes[path], "target": group["id"],
                              "kind": "OBSERVED_REFERENCE", "basis": "Lexical lead", "evidenceIds": refs})
    report["graph"] = {"nodes": nodes, "edges": edges, "sourceDigest": report["sourceDigest"],
                       "basis": "File membership, declared project references and labelled lexical leads; not a call graph"}
    return report


def adopt(engagement: dict, report: dict) -> None:
    """Called only at explicit discovery approval. Existing selected scope is preserved."""
    seed = engagement.setdefault("seed", {})
    assets = {a["path"]: a for a in report["assets"]}
    caps, programs = [], []
    for module in report["modules"]:
        caps.append({"id": module["id"], "name": module["name"], "summary": module["description"],
            "programs": len(module["files"]), "tables": 0, "jobs": 0, "screens": 0,
            "coupling": "Not measured", "risk": "Not assessed", "complexity": "Not measured",
            "loc": module["loc"], "components": [], "dependsOn": [], "integrations": [],
            "evidenceIds": module["evidenceIds"], "basis": module["type"]})
        for path in module["files"]:
            programs.append({"id": module["id"] + ":" + path, "path": path, "name": posixpath.basename(path),
                             "capability": module["id"], "loc": assets[path]["loc"] or 0, "online": False})
    seed["capabilities"], seed["programs"], seed["tables"] = caps, programs, []
    seed["graph"] = copy.deepcopy(report["graph"])
    # Legacy consumers must not mistake generated demo AST/semantic rules for source evidence.
    seed["semantic_ir"] = []
    seed["discovery"] = {"engine": report["engine"], "objective": "Source-backed discovery",
        "mode": "Evidence-based", "transformStatus": "not-used", "integrations": [],
        "notes": "See the approved discovery report for evidence and analysis limitations."}
    engagement["sourceDiscovery"] = {"version": report["version"], "sourceDigest": report["sourceDigest"],
        "reportPath": "artifacts/discovery-approved.json", "analysisCoverage": report["analysisCoverage"]}
