---
name: foundational-readiness-auditor
description: >-
  Audits legacy mainframe modernization readiness at Phase 0 gate before Intake or Discovery begins.
  Verifies compiler AST grammar, golden test vectors, CDC replication targets, and cross-scope ACL isolation.
---

# Foundational Readiness Auditor (Phase 0 Gate)

## Purpose
The **Foundational Readiness Auditor** enforces the prerequisite ground-truth check before generative modernization or reverse engineering is permitted. In real-world enterprise modernizations, attempting LLM code translation without a deterministic AST grammar or golden test suite leads to hallucinated business logic and untraceable regressions.

## Invocation & CLI Usage
This skill can be triggered whenever assessing a new legacy application repo, an intake scope, or an engagement.

To run programmatically using the modernization platform engine:
```bash
python -c "
import sys; sys.path.insert(0, 'apps/api')
from app.bedrock_skills import audit_foundational_readiness
result = audit_foundational_readiness({
    'grammar_defined': True,
    'golden_vectors_count': 120,
    'cdc_replication_target': 'arn:aws:kinesis:us-east-1:123456789012:stream/cdc',
    'cross_scope_acls_isolated': True
})
print(result)
"
```

## Mandatory Phase 0 Gates
An application or sub-scope must satisfy the following 4 criteria to pass Phase 0:

1. **Deterministic AST Grammar Defined**:
   - COBOL/PL/I grammar specification (e.g. ProLeap COBOL parser or ANTLR4 tree).
   - If missing, AST-backed structural extraction cannot be guaranteed.
2. **Golden Execution Vectors (>= 50 test cases)**:
   - High-fidelity mainframe transaction inputs & corresponding output dumps (e.g., EBCDIC copybook hex records, VSAM file snapshots).
3. **Change Data Capture (CDC) Target Provisioned**:
   - Target streaming infrastructure (AWS MSK / Kinesis / Azure Event Hubs) ready to mirror Db2/VSAM state changes with sub-second RPO.
4. **Cross-Scope ACL Isolation Verified**:
   - Tenant boundaries, IAM policies, and shared data service permissions isolated to prevent unintended cascade effects during incremental Strangler Fig cutover.

## Agent Instructions & Output Schema
When auditing readiness, report findings in the following format:
```markdown
### Foundational Readiness Assessment
- **Readiness Score**: <0-100>%
- **Phase Gate Status**: [PASSED | BLOCKED]
- **Unmet Prerequisites**:
  - [Prerequisite Name]: [Remediation Action Required]
- **AI Remediation Recommendations**:
  - Step-by-step guidance on creating the AST grammar or capturing golden test vectors.
```
