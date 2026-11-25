"""Deterministic, evidence-only planning. This module never calls a provider or writes source."""
from __future__ import annotations

from .models import (EvidenceReference, ModernizationPlan, PlanRisk, PlanStatus,
                     PlanTask, PlanWorkstream, StrategyRecommendation)
from .providers import allocate_provider, provider_readiness

PLANNING_ENGINE_VERSION = "3.5.0"


def _ref(value: dict, entity_id: str | None = None) -> EvidenceReference:
    return EvidenceReference(artifactId=value["artifactId"], pointer=value.get("pointer", ""), entityId=entity_id)


def _artifact_refs(manifest: dict, roles: set[str] | None = None) -> list[EvidenceReference]:
    return [_ref({"artifactId": a["id"]}) for a in manifest["artifacts"]
            if roles is None or a.get("role") in roles]


def _entity_refs(contract: dict, kind: str) -> list[EvidenceReference]:
    return [_ref(e["reference"], e["id"]) for e in contract["traceability"]["entities"] if e["kind"] == kind]


def _provider(category: str, target: dict, readiness: dict) -> tuple[str, str, dict, bool, str | None]:
    return allocate_provider(category, target, bool(target.get("templateIds")), readiness)


def _strategy(manifest: dict) -> StrategyRecommendation:
    contract, target = manifest["contract"], manifest["contract"]["target"]
    evidence = [_ref(target["snapshot"])] if target.get("snapshot") else []
    if target.get("language") and target.get("framework") and contract["templates"]:
        return StrategyRecommendation(category="refactor", confidence="medium", evidence=evidence,
            rationale="A target configuration and template bundle are packaged, so staged refactoring can be reviewed.",
            risks=["Target compatibility and execution readiness remain governed by package findings."],
            unresolvedQuestions=["Confirm target architecture and provider capability before execution."])
    return StrategyRecommendation(category="retain", confidence="low", evidence=evidence,
        rationale="The package lacks complete target evidence for an executable transformation commitment.",
        risks=["Missing target or template evidence prevents a modernization commitment."],
        unresolvedQuestions=["Complete and approve target configuration and template selection."])


def _workstreams(manifest: dict) -> list[tuple[str, str, str, list[EvidenceReference]]]:
    contract, target = manifest["contract"], manifest["contract"]["target"]
    paths = [a["path"].lower() for a in manifest["artifacts"] if a["kind"] == "source"]
    deps = contract["dependencies"]["items"]
    result = []
    if target.get("language") or any(p.endswith((".cs", ".java", ".py", ".go")) for p in paths):
        result.append(("backend", "Backend modernization", "Backend target or source evidence is packaged.", _artifact_refs(manifest, {"selected", "dependency", "shared"})))
    if target.get("frontendFramework") or any(p.endswith((".tsx", ".jsx", ".vue", ".html", ".css")) for p in paths):
        result.append(("frontend", "Frontend modernization", "Frontend target or source evidence is packaged.", _artifact_refs(manifest, {"selected", "dependency", "shared"})))
    for ident, name, categories in [("database", "Database modernization", {"database"}), ("api", "API modernization", {"api"}), ("integration", "Integration modernization", {"external-service", "messaging"}), ("configuration", "Configuration modernization", {"configuration"}), ("build", "Build and deployment modernization", {"build", "deployment"})]:
        evidence = [_ref(d["evidence"]) for d in deps if d["category"] in categories]
        if evidence:
            result.append((ident, name, "Packaged dependency evidence is applicable.", evidence))
    tests = _entity_refs(contract, "scenario") + _entity_refs(contract, "test-case") + _artifact_refs(manifest, {"test-baseline"})
    if tests:
        result.append(("testing", "Testing and behavioral validation", "Packaged test evidence is available.", tests))
    return result


def _batches(manifest: dict, suffixes: tuple[str, ...], excluded: tuple[str, ...] = (), size: int = 8) -> list[list[EvidenceReference]]:
    refs = [_ref({"artifactId": item["id"]}) for item in manifest["artifacts"]
            if item.get("kind") == "source" and item["path"].lower().endswith(suffixes)
            and not any(part in item["path"].lower() for part in excluded)]
    return [refs[index:index + size] for index in range(0, len(refs), size)]


def _transform_refs(manifest: dict) -> list[EvidenceReference]:
    """Return a bounded .NET project closure for repository-level Transform.

    Dependency inference can legitimately be broad, particularly for legacy web
    applications containing checked-in JavaScript libraries. Passing every
    inferred dependency to a .NET transformation turns a selected module into a
    whole-repository job. Transform instead receives the selected files, build
    files, and compilable/configuration files in the selected files' projects.
    """
    source = [item for item in manifest["artifacts"] if item.get("kind") == "source"]
    selected = [item for item in source if item.get("role") == "selected"]
    project_roots = {
        item["path"].split("/", 2)[1]
        for item in selected
        if item.get("path", "").startswith("source/") and len(item["path"].split("/")) > 2
    }
    allowed_suffixes = (".cs", ".cshtml", ".config", ".json", ".csproj", ".sln")
    chosen: list[dict] = []
    for item in source:
        path = item.get("path", "")
        relative = path.removeprefix("source/")
        root = relative.split("/", 1)[0]
        is_build = item.get("role") == "build-support"
        is_project_context = (root in project_roots and
                              (relative.lower().endswith(allowed_suffixes) or relative.lower().endswith("packages.config")))
        # Shared artifacts may live in a separate project/root but are explicit
        # scope evidence, so preserve them in the closure as well.
        if item.get("role") in {"selected", "shared"} or is_build or is_project_context:
            chosen.append(item)
    return [_ref({"artifactId": item["id"]}) for item in chosen]


def _task(task_id: str, ws_id: str, name: str, evidence: list[EvidenceReference], manifest: dict, blocked: bool, readiness: dict) -> PlanTask:
    contract, target = manifest["contract"], manifest["contract"]["target"]
    provider, rationale, capability, fallback, fallback_provider = _provider(ws_id, target, readiness)
    templates = [_ref(f["reference"]) for t in contract["templates"] for f in t["files"]]
    required = [str(x) for x in (target.get("language"), target.get("framework"), target.get("frameworkVersion")) if x]
    return PlanTask(taskId=task_id, name=name, description="Analyze packaged evidence for this workstream; this plan performs no source change.", category=ws_id, workstreamId=ws_id, sourceArtifacts=evidence,
        businessRules=_entity_refs(contract, "rule"), requirements=_entity_refs(contract, "requirement"), stories=_entity_refs(contract, "story"), acceptanceCriteria=_entity_refs(contract, "criterion"),
        requiredTargetTechnologies=required, templates=templates, suggestedProvider=provider, providerRationale=rationale,
        capabilityVerification=capability, expectedOutputFolders=[{"backend": "backend", "frontend": "frontend", "database": "data", "api": "backend", "configuration": "docs", "build": "docs", "testing": "tests", "integration": "docs"}.get(ws_id, "docs")],
        fallbackEligible=fallback, fallbackProvider=fallback_provider,
        expectedOutput="A reviewed implementation proposal and traceable validation evidence for the workstream.",
        acceptanceConditions=["Preserve all referenced behavior.", "Resolve packaged blockers before execution."], validationApproach="Use packaged requirements, stories, acceptance criteria and test evidence; live parity is not asserted.",
        risks=["Package evidence may be incomplete or unverified."], unresolvedDependencies=[], estimatedComplexity="unknown" if not evidence else "medium", priority="high" if ws_id in {"backend", "database", "api"} else "medium", planningStatus="blocked" if blocked else "proposed")


def build(manifest: dict, readiness, plan_id: str, created_at) -> ModernizationPlan:
    contract = manifest["contract"]
    blockers = [PlanRisk(code=f.code, severity=f.severity, message=f.message, evidence=[EvidenceReference(artifactId=e) for e in f.evidence]) for f in readiness.findings if f.severity == "blocker"]
    risks = [PlanRisk(code=f.code, severity=f.severity, message=f.message, evidence=[EvidenceReference(artifactId=e) for e in f.evidence]) for f in readiness.findings if f.severity != "blocker"]
    unresolved = [d for d in contract["dependencies"]["items"] if d["status"] in {"unresolved", "external-incomplete", "implementation-unavailable"}]
    risks.extend(PlanRisk(code="UNRESOLVED_PACKAGE_DEPENDENCY", severity="warning", message=f"Dependency '{d['name']}' is {d['status']}.", evidence=[_ref(d["evidence"])]) for d in unresolved)
    internal_edges = [d["name"].split(" -> ", 1) for d in contract["dependencies"]["items"] if d["category"] == "internal" and " -> " in d["name"]]
    graph = {}
    for left, right in internal_edges:
        graph.setdefault(left, set()).add(right)
    def cyclic(node: str, visiting: set[str], visited: set[str]) -> bool:
        if node in visiting: return True
        if node in visited: return False
        visiting.add(node)
        result = any(cyclic(next_node, visiting, visited) for next_node in graph.get(node, set()))
        visiting.remove(node); visited.add(node)
        return result
    if any(cyclic(node, set(), set()) for node in graph):
        risks.append(PlanRisk(code="CIRCULAR_SOURCE_DEPENDENCY", severity="warning", message="A cycle was detected in packaged internal dependency evidence; no task ordering edge was fabricated.", evidence=[]))
    definitions = _workstreams(manifest)
    provider_snapshot = provider_readiness()
    tasks = [_task(f"task-{ident}", ident, name, refs, manifest, bool(blockers), provider_snapshot) for ident, name, _, refs in definitions]
    expanded = []
    for task in tasks:
        # AWS Transform receives the complete staged .NET module once.  Running
        # the repository-level transformation once per arbitrary file batch
        # would repeatedly transform the same staged repository and corrupt the
        # result. Bedrock remains batched because its input/output is a file map.
        if task.suggestedProvider == "aws-transform":
            expanded.append(task.model_copy(update={"sourceArtifacts": _transform_refs(manifest),
                "description": "Modernize the selected module's .NET project closure and required build files; checked-in client libraries and unrelated repository files are excluded."}))
            continue
        suffixes = (".cs",) if task.category == "backend" else (".cshtml", ".html", ".js", ".ts", ".tsx") if task.category == "frontend" else ()
        batches = _batches(manifest, suffixes, ("/scripts/libs/", ".min.js", ".map")) if suffixes else []
        if not batches:
            expanded.append(task)
            continue
        for index, refs in enumerate(batches, 1):
            expanded.append(task.model_copy(update={"taskId": task.taskId if index == 1 else f"{task.taskId}-{index}",
                "name": f"{task.name} batch {index}/{len(batches)}", "sourceArtifacts": refs,
                "description": f"Modernize only this explicit batch of {len(refs)} source artifacts into the target scaffold."}))
    tasks = expanded
    previous_backend = None
    ordered = []
    for task in tasks:
        if task.category in {"backend", "api"}:
            task = task.model_copy(update={"dependencies": [previous_backend] if previous_backend else []})
            previous_backend = task.taskId
        ordered.append(task)
    tasks = ordered
    # Frontend and configuration generation consume the generated backend/API
    # contract; do not run them from an unrelated legacy-only prompt.
    backend_ids = [task.taskId for task in tasks if task.category in {"backend", "api"}]
    if backend_ids:
        tasks = [task.model_copy(update={"dependencies": backend_ids})
                 if task.category in {"frontend", "configuration"} else task
                 for task in tasks]
    workstreams = [PlanWorkstream(id=ident, name=name, rationale=rationale, evidence=refs, taskIds=[f"task-{ident}"]) for ident, name, rationale, refs in definitions]
    # A task ID is created exactly once, so ownership cannot be duplicated across providers.
    assert len({task.taskId for task in tasks}) == len(tasks)
    return ModernizationPlan(planId=plan_id, engagementId=manifest["engagementId"], moduleId=manifest["moduleId"], packageId=manifest["packageId"], packageSchemaVersion=manifest["schemaVersion"], packageDigest=manifest["packageDigest"], targetConfigurationRevision=contract["target"]["configurationDigest"], targetDecision=contract["target"], templateBundleRevisions={t["id"]: t["revision"] for t in contract["templates"]}, providerReadiness=provider_snapshot, planningEngineVersion=PLANNING_ENGINE_VERSION, status=PlanStatus.BLOCKED_PLAN if blockers else PlanStatus.READY_FOR_REVIEW, createdAt=created_at, strategy=_strategy(manifest), workstreams=workstreams, tasks=tasks, dependencyOrder=[[t.taskId] for t in tasks], risks=risks, blockers=blockers)
