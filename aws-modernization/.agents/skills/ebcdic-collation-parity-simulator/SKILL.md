---
name: ebcdic-collation-parity-simulator
description: >-
  Simulates binary character collation sorting (EBCDIC IBM-037 vs UTF-8) and COMP-3 packed decimal
  arithmetic edge-cases to prevent silent business logic divergence during shadow parity runs.
---

# EBCDIC Collation & Math Parity Simulator (Phase 6 / Dual-Run Testing)

## Purpose
Mainframe architectures run on EBCDIC (e.g. IBM-037 or IBM-1140), where numbers sort **after** uppercase letters (`'A' < '1'`). Cloud and modern microservices run on ASCII / UTF-8, where numbers sort **before** letters (`'1' < 'A'`). In batch processing and sequential record reconciliation, this subtle sorting difference causes pagination bugs, key mismatch errors, and regulatory reporting inversions.

Additionally, COBOL `COMP-3` (packed decimal) arithmetic truncates and rounds differently than IEEE 754 floating point or standard double precision.

The **EBCDIC Collation Parity Simulator** catches these edge cases during shadow dual-run validation before cutover.

## Invocation & CLI Usage
Execute test vectors through the parity simulator:
```bash
python -c "
import sys; sys.path.insert(0, 'apps/api')
from app.bedrock_skills import simulate_ebcdic_collation_parity
vectors = ['POL-100-A', 'pol-100-a', '999-SPECIAL', 'POL 100']
result = simulate_ebcdic_collation_parity(vectors)
print(result)
"
```

## Analyzed Edge-Case Dimensions
1. **Binary Collation Inversion**:
   - Compares sorting under IBM-037 byte order against UTF-8 byte order.
   - Detects when alphabetical identifiers interleave differently with numeric identifiers.
2. **Space vs Punctuation Ordering**:
   - Mainframe space `0x40` vs ASCII space `0x20` relative to hyphens and underscores.
3. **COMP-3 Packed Decimal vs `BigDecimal`**:
   - Asserts that fixed-point financial rounding in Java `BigDecimal(roundingMode = HALF_EVEN)` matches COBOL `ROUNDED` clause behaviors without decimal drift.

## Agent Instructions & Output Format
When discrepancies are flagged, output:
- Raw EBCDIC order vs Raw UTF-8 order.
- Inversion index points.
- Recommended SQL `ORDER BY` collation clause (e.g., PostgreSQL `COLLATE "C"` or custom collation mapping) to maintain 100% binary backward compatibility.
