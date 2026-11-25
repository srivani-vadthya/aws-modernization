from __future__ import annotations

import hashlib
import json
import re
from .collector import Collection
from .models import Readiness


def assess(c: Collection) -> Readiness:
    eng, seed = c.engagement, c.engagement.get("seed") or {}
    module = c.scope["capabilityId"]
    for phase in ("discovery", "scope", "semantic-ir", "user-stories"):
        if (eng.get("gates", {}).get(phase) or {}).get("decision") != "approved":
            c.finding("APPROVAL_MISSING", f"{phase} approval is not recorded.", phase, "blocker",
                      action="Use the existing workflow to review and approve this stage.")
        elif phase != "discovery":
            c.finding("APPROVAL_VERSION_UNBOUND", f"{phase} approval is phase-level, not bound to this content hash.",
                      phase, action="Review this exact package before future execution.")
    c.finding("AST_NOT_PERSISTED", "The current pipeline does not persist a complete AST snapshot.", "analysis-context")
    c.finding("DEPENDENCY_COVERAGE_UNPROVEN", "Dependency context is limited to existing analysis; completeness is not established.",
              "module-graph")
    c.finding("REQUIREMENTS_ASSOCIATION_UNKNOWN", "Separate requirements do not establish module-specific approved requirements.",
              "requirements")
    if eng.get("sourceType") == "sample":
        c.finding("DEMO_SOURCE", "This engagement uses sample/demo source.", severity="blocker",
                  action="Use a reviewed real engagement before production modernization.")
    if not any(a.kind == "source" and a.role == "selected" for a in c.artifacts):
        c.finding("SELECTED_SOURCE_MISSING", "No selected-module source files were collected.", severity="blocker")
    if c.dependencies["unresolvedNodeIds"]:
        c.finding("UNRESOLVED_DEPENDENCIES", "Some referenced graph nodes are absent.", "module-graph", "blocker",
                  c.dependencies["unresolvedNodeIds"])
    if c.dependencies["externalDependencies"]:
        c.finding("EXTERNAL_CONTRACT_REVIEW", "External integration compatibility has not been verified.",
                  "module-graph", evidence=[n["id"] for n in c.dependencies["externalDependencies"]])
    contracts = [s for s in seed.get("semantic_ir", []) if s.get("module") == module]
    if not contracts:
        c.finding("SIR_MISSING", "Selected-module SIR contracts are absent.", "sir", "blocker")
    flows = c.scope.get("useCases", [])
    entries = {s.get("trace", {}).get("entryPoint") for s in contracts}
    omitted = [f.get("id", "") for f in flows if f.get("entryPoint") and f["entryPoint"] not in entries]
    if omitted:
        c.finding("SIR_USE_CASE_GAPS", "Selected use cases have no corresponding SIR trace.", "sir", "blocker", omitted)
    if len(contracts) >= 12:
        c.finding("SIR_LIMIT_REVIEW", "The generator's 12-contract limit is reached; inspect coverage, not just count.", "sir")
    rules = {r.get("ruleId") for s in contracts for r in s.get("rules", [])}
    ids = {s["id"] for s in contracts}
    covered = set()
    stories = c.engagement.get("userStories") or {}
    count = 0
    for ep in (stories.get("backlog") or {}).get("epics", []):
        for f in ep.get("features", []):
            for s in f.get("stories", []):
                count += 1
                tr = s.get("trace") or {}
                refs = set(tr.get("ruleIds", []))
                covered.update(refs)
                if tr.get("sirId") not in ids or refs - rules:
                    c.finding("STORY_TRACE_INVALID", "Story refers to missing selected-module contracts/rules.",
                              "stories", "blocker", [s["id"]])
                if not s.get("acceptanceCriteria"):
                    c.finding("CRITERIA_MISSING", "Story has no acceptance criteria.", "stories", "blocker", [s["id"]])
    if not count:
        c.finding("STORIES_MISSING", "No user stories were collected.", "stories", "blocker")
    if rules - covered:
        c.finding("RULE_COVERAGE_GAPS", "Some SIR rules are not referenced by stories.", "stories",
                  evidence=sorted(str(r) for r in rules - covered if r))
    for item in stories.get("validation", []):
        c.finding("STORY_VALIDATION_RECORDED", "Existing backlog validation has findings; inspect the snapshot.", "stories")
        break
    ts = eng.get("testScenarios") or {}
    if not ts:
        c.finding("TEST_SCENARIOS_MISSING", "No test-scenario snapshot exists.", "tests")
    else:
        rows = [s for e in (stories.get("backlog") or {}).get("epics", []) for f in e.get("features", []) for s in f.get("stories", [])]
        payload = [[s["id"], s.get("title"), list(s.get("acceptanceCriteria", []))] for s in rows]
        expected = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        if ts.get("sourceDigest") != expected:
            c.finding("TESTS_STALE", "Test scenarios do not match current story/criteria content.", "tests", "blocker")
    live = [r for r in ts.get("runs", []) if r.get("mode") == "live"]
    c.finding("BASELINE_NOT_VERIFIED",
              "Live-run records exist but are not proven against this source snapshot." if live
              else "No source-bound live baseline was established; checks-only passes are not behavioral verification.",
              "tests")
    target = c.target
    if not target.get("approved") or target.get("approvalStatus") != "APPROVED":
        c.finding("TARGET_NOT_APPROVED", "Explicit target approval is missing.", "target", "blocker")
    if not target.get("language") or not target.get("framework"):
        c.finding("TARGET_INCOMPLETE", "Target language/framework must be explicit.", "target", "blocker")
    from .templates import recommendations
    selected = {t["id"] for t in c.template_rows}
    missing = set(recommendations(target)) - selected
    if not selected or missing:
        c.finding("TEMPLATES_NOT_SELECTED", "No modernization-ready template selection for all configured targets.",
                  "target", "blocker", sorted(missing))
    for template in c.template_rows:
        for issue in template["compatibility"]["issues"]:
            c.finding(issue["code"], issue["message"], template["id"], issue["severity"],
                      action="Resolve the recorded compatibility decision before modernization; preserve original skills.")
    status = "blocked" if any(f.severity == "blocker" for f in c.findings) else "review-required" if c.findings else "available"
    return Readiness(modernizationPrerequisites=status, findings=c.findings)
