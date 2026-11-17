---
name: saga-transaction-orchestrator
description: >-
  Detects cross-boundary distributed transactions across modernizing services and synthesizes SAGA Orchestrators
  with forward actions, event publications, and compensating rollback handlers to replace legacy Two-Phase Commits (2PC).
---

# SAGA Distributed Transaction Orchestrator

## Purpose
Monolithic mainframe programs frequently update multiple database tables (e.g. `CUSTOMER`, `POLICY`, `PAYMENT_LEDGER`) within a single CICS/Db2 Two-Phase Commit (`EXEC CICS SYNCPOINT`). When decoupled into independent microservices, distributed 2PC introduces deadlocks and tight coupling.

The **SAGA Transaction Orchestrator** detects multi-aggregate mutations and synthesizes an orchestrated **SAGA State Machine** with automated compensating transactions (e.g. if `PolicyCreation` fails, trigger `CancelPayment` and `ReleaseCustomerLock`).

## Invocation & CLI Usage
```bash
python -c "
import sys; sys.path.insert(0, 'apps/api')
from app.bedrock_skills import synthesize_saga_orchestrator
scope = {'name': 'Policy Issuance SAGA', 'capabilityId': 'policy-issuance'}
result = synthesize_saga_orchestrator(scope)
print(result)
"
```

## Generated Patterns
1. **SAGA Execution Coordinator (SEC)**:
   - State machine coordinating steps: `ValidateCustomer` $\rightarrow$ `AuthorizePayment` $\rightarrow$ `IssuePolicy` $\rightarrow$ `PublishPolicyIssuedEvent`.
2. **Compensating Transactions**:
   - `AuthorizePayment` failure $\rightarrow$ no compensation needed.
   - `IssuePolicy` failure $\rightarrow$ triggers `RefundPayment` compensating action.
