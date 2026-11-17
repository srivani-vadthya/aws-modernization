---
name: shared-kernel-decoupler-and-acl-generator
description: >-
  Identifies cross-scope shared tables and programs across modernizing domains,
  generating Anti-Corruption Layer (ACL) OpenAPI specs, circuit-breaker facades, and dual-write strategies.
---

# Shared Kernel Decoupler & Anti-Corruption Layer (ACL) Generator (Phase 2 / Scope)

## Purpose
In enterprise monolithic architectures, separate business capabilities (e.g. Motor Policy vs. Claims vs. Customer 360) are tightly coupled via shared database tables (e.g. `CUSTOMER`, `POLICY_MASTER`) or common utility programs (e.g. `LGACDB01`). Modernizing Scope 1 without addressing external consumers from Scopes 2, 3, or 4 causes database deadlocks, broken foreign keys, and deployment failure.

The **Shared Kernel Decoupler** identifies every cross-boundary resource, calculates blast radius, and synthesizes an Anti-Corruption Layer (ACL) with circuit breakers and event-driven decoupling.

## Invocation & CLI Usage
```bash
python -c "
import sys; sys.path.insert(0, 'apps/api')
from app.bedrock_skills import decouple_shared_kernels
mock_scope = {
    'capabilityId': 'motor',
    'name': 'Motor Policy Services',
    'sharedServices': [
        {
            'resourceId': 'CUSTOMER',
            'kind': 'table',
            'resourceName': 'CUSTOMER Master Table',
            'consumers': ['Scope 2: Customer Onboarding', 'Scope 3: Billing']
        }
    ]
}
result = decouple_shared_kernels(mock_scope)
print(result)
"
```

## Supported Patterns Generated
1. **OpenAPI / REST Facade**: Exposes the shared kernel behind a decoupled REST contract so other scopes interact via API rather than direct SQL joins.
2. **Circuit Breaker & Retry**: Resilience4j or Polly circuit breakers to prevent cascade failures.
3. **Dual-Write CDC Strategy**: AWS DMS / Debezium CDC sync rules to keep legacy master data synchronized with the new microservice data store.

## Output Schema
```json
{
  "decoupledKernelsCount": 1,
  "artifacts": [
    {
      "resourceId": "CUSTOMER",
      "strategy": "OpenAPI Facade + Event-Driven CDC",
      "aclSpec": "openapi: 3.0.0...",
      "blastRadiusMitigation": "Isolates 2 external scopes from database locking."
    }
  ]
}
```
