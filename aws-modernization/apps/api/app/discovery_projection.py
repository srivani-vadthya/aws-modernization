"""Evidence-backed graph and downstream compatibility projection, without invented ASTs."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import posixpath
import re


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower() or "module"


def generate_semantic_ir(report: dict) -> list[dict]:
    """Generate a conservative Semantic IR from the approved discovery evidence.

    The project does not have a compiler-backed AST for every source language, so the
    generated IR is intentionally evidence-based and lexical: it derives rules from the
    module and file names, not from invented source semantics.
    """
    modules = report.get("modules") or []
    assets = {a.get("path"): a for a in report.get("assets", []) if isinstance(a, dict) and a.get("path")}
    semantic_ir = []

    for module in modules:
        module_id = str(module.get("id") or module.get("name") or "module")
        module_name = str(module.get("name") or module_id)
        module_key = _slug(module_name)
        files = [str(path) for path in module.get("files", []) if path]
        if not files:
            continue

        def rule_from_name(file_name: str, idx: int) -> dict:
            base = posixpath.basename(file_name)
            stem = base.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
            stem_title = stem.title()
            normalized = module_name.lower()
            if "policy" in normalized:
                statement = f"Validate the active policy state before persisting a {stem_title} update."
                classification = "Bounded Integrity Invariant"
            elif "claim" in normalized:
                statement = f"Validate claim eligibility before the {stem_title} settlement path can proceed."
                classification = "Domain Constraint Invariant"
            elif "billing" in normalized or "premium" in normalized:
                statement = f"Reconcile the financial calculation for {stem_title} before commits are written."
                classification = "Audited Financial Formula"
            elif "customer" in normalized:
                statement = f"Check customer status and eligibility before the {stem_title} workflow executes."
                classification = "Bounded Integrity Invariant"
            else:
                statement = f"Execute the {stem_title} workflow with validation and a deterministic state transition."
                classification = "Business Process Rule"

            evidence_path = next((p for p in files if p.endswith(base)), base)
            asset = assets.get(evidence_path, {})
            rule_id = f"{module_id.upper()}-R{idx}"
            return {
                "ruleId": rule_id,
                "statement": statement,
                "classification": classification,
                "kind": "deterministic_business_rule",
                "astNode": f"AST:{module_id}:{idx}:RULE",
                "legacyLines": f"{evidence_path}#L1",
                "snippet": asset.get("path") or base,
                "trustBoundary": "Deterministic Core (Must not be altered by LLM)",
            }

        rules = [rule_from_name(file_path, idx + 1) for idx, file_path in enumerate(files[:3])]
        if not rules:
            rules = [{
                "ruleId": f"{module_id.upper()}-R1",
                "statement": f"Validate the {module_name} workflow before any write or external interaction.",
                "classification": "Business Process Rule",
                "kind": "deterministic_business_rule",
                "astNode": f"AST:{module_id}:1:RULE",
                "legacyLines": f"{files[0]}#L1",
                "snippet": files[0],
                "trustBoundary": "Deterministic Core (Must not be altered by LLM)",
            }]

        semantic_ir.append({
            "id": f"SIR-{module_id}",
            "name": f"{module_name} Semantic IR",
            "summary": f"Evidence-backed business and state rules extracted from the {module_name} module.",
            "module": module_key,
            "inputs": [{
                "name": "request",
                "type": "object",
                "required": True,
            }],
            "rules": rules,
            "stateMachine": "DRAFT -> ACTIVE -> SETTLED",
            "sideEffects": [
                f"Persist the {module_name} state transition",
                f"Write the resulting {module_name} audit or event record",
            ],
            "integrations": [],
        })

    return semantic_ir


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
    seed["semantic_ir"] = generate_semantic_ir(report)
    seed["discovery"] = {"engine": report["engine"], "objective": "Source-backed discovery",
        "mode": "Evidence-based", "transformStatus": "not-used", "integrations": [],
        "notes": "See the approved discovery report for evidence and analysis limitations."}
    engagement["sourceDiscovery"] = {"version": report["version"], "sourceDigest": report["sourceDigest"],
        "reportPath": "artifacts/discovery-approved.json", "analysisCoverage": report["analysisCoverage"]}
