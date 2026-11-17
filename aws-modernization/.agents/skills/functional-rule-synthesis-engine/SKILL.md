---
name: functional-rule-synthesis-engine
description: >-
  Extracts business calculations, validation constraints, and policy underwriting logic from legacy code,
  synthesizing executable Gherkin feature files (Given-When-Then) and IEEE 830 functional requirements with line-level AST traceability.
---

# Functional Rule & Gherkin Synthesis Engine (Phase 3 / Requirements)

## Purpose
Reverse-engineering legacy systems requires converting dense procedural logic (COBOL `PERFORM ... VARYING`, nested `IF/ELSE`, and database flags) into clear, business-readable specifications that developers and business analysts can verify together.

The **Functional Rule Synthesis Engine** extracts core domain formulas and generates executable **Gherkin feature files (`.feature`)** ready for Cucumber/SpecFlow verification alongside formal IEEE 830 functional requirements.

## Invocation & CLI Usage
```bash
python -c "
import sys; sys.path.insert(0, 'apps/api')
from app.bedrock_skills import synthesize_functional_rules
mock_scope = {
    'capabilityId': 'motor',
    'name': 'Motor Insurance Underwriting'
}
result = synthesize_functional_rules(mock_scope)
print(result)
"
```

## Generated Artifacts
1. **Executable Gherkin Scenarios**:
   - Explicit `Given-When-Then` test fixtures covering happy paths, edge cases (e.g. driver age under 21), and calculation boundaries.
2. **IEEE 830 Functional Specifications**:
   - Structured requirement IDs with statement, risk severity, and AST code paragraph trace links.
3. **Domain Calculation Formulas**:
   - Clean pseudocode equations explaining rating factors, discounts, and penalties.

## Output Schema
```json
{
  "totalRulesSynthesized": 4,
  "gherkinFeatures": [
    {
      "featureName": "Motor Policy Premium Rating",
      "scenarios": [
        {
          "scenario": "Young driver premium surcharge",
          "gherkin": "Scenario: Driver under 21 gets 25% surcharge\n  Given a driver with age 19\n  When policy quote is calculated\n  Then young driver surcharge of 25% is added"
        }
      ]
    }
  ]
}
```
