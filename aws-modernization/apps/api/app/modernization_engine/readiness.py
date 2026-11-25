from __future__ import annotations

from .models import ReadinessPreview, ValidationFinding

READINESS_POLICY_VERSION = "2.0"

# A first modernization pass from an unknown legacy repository must be useful
# without pretending that discovery evidence is complete.  Only conditions that
# make provider input unsafe or technically unusable stop execution.  All other
# findings remain in the package and execution report as quality risks.
HARD_PACKAGE_BLOCKERS = {
    "SOURCE_MISSING",
    "SOURCE_EXCLUDED",
    "PACKAGE_INTEGRITY_INVALID",
    "PACKAGE_SCHEMA_UNSUPPORTED",
    "TARGET_NOT_APPROVED",
    "TARGET_NOT_CONFIGURED",
    "TEMPLATES_NOT_SELECTED",
    "TEMPLATE_MISSING",
}


def _finding(code: str, severity: str, message: str, evidence: list[str], source: str) -> ValidationFinding:
    return ValidationFinding(code=code, severity=severity, message=message, evidence=evidence, source=source)


def _package_finding(item: dict) -> ValidationFinding:
    """Keep package evidence intact while applying the execution admission policy."""
    code = item["code"]
    severity = "blocker" if code in HARD_PACKAGE_BLOCKERS else ("warning" if item["severity"] == "blocker" else item["severity"])
    message = item["message"]
    if code == "SENSITIVE_CONTENT_EXCLUDED":
        message = "Potentially sensitive content was excluded from provider input; reproduce its configuration manually from approved secrets."
    return _finding(code, severity, message, item.get("evidence", []), "module-context-package")


def preview(eid: str, module_id: str, manifest: dict, integrity: dict) -> ReadinessPreview:
    findings: list[ValidationFinding] = []
    contract = manifest["contract"]
    for item in manifest["readiness"]["findings"]:
        findings.append(_package_finding(item))
    if not integrity.get("valid"):
        findings.append(_finding("PACKAGE_INTEGRITY_INVALID", "blocker", "Package integrity validation failed.", [], "engine"))
    if manifest["schemaVersion"] != "2.0.0":
        findings.append(_finding("PACKAGE_SCHEMA_UNSUPPORTED", "blocker", "Engine requires schema 2.0.0.", [manifest["schemaVersion"]], "engine"))
    selected = {row["id"] for row in manifest.get("templates", [])}
    expected = set(contract["target"].get("templateIds", []))
    if not selected or expected - selected:
        findings.append(_finding("ENGINE_TEMPLATE_SELECTION_MISSING", "blocker", "Required target template snapshots are absent.", sorted(expected - selected), "engine"))
    for template in manifest.get("templates", []):
        if not template.get("available", False):
            findings.append(_finding("ENGINE_TEMPLATE_UNAVAILABLE", "blocker", "A selected template bundle is unavailable.", [template["id"]], "engine"))
        if template.get("compatibility", {}).get("status") == "blocked":
            findings.append(_finding("ENGINE_TEMPLATE_COMPATIBILITY_REVIEW", "warning", "Selected template has compatibility decisions that must be recorded in the modernization report.", [template["id"]], "engine"))
    # Existing workflow approvals are phase-level records.  A later explicit
    # plan approval is bound to this package digest, so phase-only approvals are
    # evidence quality warnings rather than a circular precondition.
    records = {row["gateId"]: row for row in contract["approvals"]["records"]}
    for gate, record in records.items():
        if record.get("decision") != "approved":
            findings.append(_finding("ENGINE_APPROVAL_MISSING", "warning", "Existing phase approval is not recorded; review the packaged evidence before approving the plan.", [gate], "engine"))
        elif record.get("binding") != "exact-artifact-hash":
            findings.append(_finding("ENGINE_APPROVAL_REVISION_UNBOUND", "warning", "Existing phase approval is not bound to this package digest; plan approval will bind the execution to this revision.", [gate], "engine"))
    target = contract["target"]
    if target.get("missingFields"):
        findings.append(_finding("ENGINE_TARGET_INCOMPLETE", "blocker", "Target configuration has unavailable required fields.", target["missingFields"], "engine"))
    blockers = sum(item.severity == "blocker" for item in findings)
    warnings = sum(item.severity == "warning" for item in findings)
    status = "NOT_READY" if blockers else "READY_WITH_WARNINGS" if warnings else "READY"
    return ReadinessPreview(engagementId=eid, moduleId=module_id, packageId=manifest["packageId"],
        packageSchemaVersion=manifest["schemaVersion"], packageIntegrity="valid" if integrity.get("valid") else "invalid",
        overallStatus=status, executable=not blockers, target=target, templates=manifest.get("templates", []), findings=findings,
        policyVersion=READINESS_POLICY_VERSION)
