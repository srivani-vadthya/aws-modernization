---
name: differential-golden-run-comparator
description: >-
  Ingests production mainframe transaction logs (COMMAREA hex dumps, VSAM/Db2 before-and-after snapshots),
  applies automated PII masking, replays transactions through the modernized cloud service, and calculates
  a bitwise Parity Equivalence Score (down to the penny and byte) with automated root-cause diffing.
---

# Differential Golden Parity Runner (Phase 6 / Shadow Validation)

## Purpose
In financial services, insurance, and healthcare, no modernization project passes approval based on unit tests alone. The **Differential Golden Parity Runner** provides undeniable mathematical proof of equivalence by replaying thousands of real-world legacy production transaction vectors side-by-side against the modernized cloud microservice.

## Invocation & CLI Usage
```bash
python -c "
import sys; sys.path.insert(0, 'apps/api')
from app.bedrock_skills import run_differential_golden_parity
result = run_differential_golden_parity('eng-motor-policy', sample_size=1000)
print(result)
"
```

## Core Engine Capabilities
1. **Automated PII Tokenization & Masking**:
   - Strips SSNs, credit card numbers, policyholder names, and addresses while preserving fixed-length byte field boundaries.
2. **Side-by-Side Dual Execution Replay**:
   - Replays input vectors through legacy emulator / stored dumps and modern target REST/gRPC endpoints.
3. **Deep Field-by-Field Comparator**:
   - Compares:
     - Numerical balances & premiums (exact to 2 decimal places using `BigDecimal`).
     - Alphanumeric status flags & state transitions.
     - Timestamp formats and timezone offsets.
4. **Automated Divergence Root-Cause Analyzer (LLM Reasoning)**:
   - When a discrepancy is detected (e.g. $0.01 divergence due to rounding or collation order difference), the agent analyzes the AST code path and flags the exact line of code responsible.

## Output Schema
```json
{
  "totalVectorsReplayed": 1000,
  "identicalMatches": 998,
  "parityConfidenceScore": 99.80,
  "maxVarianceTolerancePercent": 0.05,
  "status": "CERTIFIED_FOR_PRODUCTION_CUTOVER",
  "discrepancies": [
    {
      "vectorId": "VEC-4882-CICS",
      "field": "ANNUAL_PREMIUM",
      "legacyValue": "1420.50",
      "modernValue": "1420.51",
      "delta": "0.01",
      "rootCause": "COBOL ROUNDED (Bankers Rounding) vs IEEE 754 float drift",
      "remediation": "Switch Java Double to BigDecimal.setScale(2, RoundingMode.HALF_EVEN)"
    }
  ]
}
```
