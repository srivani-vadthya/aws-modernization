---
name: bidirectional-cdc-guardrail
description: >-
  Monitors and verifies dual-run active-active state synchronization, CDC replication lag, conflict resolution,
  and instant rollback certification metrics during Strangler Fig phased cutover.
---

# Bidirectional CDC Guardrail (Phase 7 / Cutover & Dual-Run)

## Purpose
During phased Strangler Fig modernization, microservices and legacy mainframes run concurrently for weeks or months. Writes occurring on either system must replicate bidirectionally without creating infinite ping-pong write loops or lost updates.

The **Bidirectional CDC Guardrail** validates active-active CDC topology health, tracks replication lag against RPO (Recovery Point Objective) targets, and certifies rollback safety before DNS/traffic cutover.

## Invocation & CLI Usage
Query CDC stream status for an engagement scope:
```bash
python -c "
import sys; sys.path.insert(0, 'apps/api')
from app.bedrock_skills import get_bidirectional_cdc_status
status = get_bidirectional_cdc_status('eng-auto-motor-core')
print(status)
"
```

## Key Metrics Monitored
1. **Replication Latency (RPO Guarantee)**:
   - Forward Replication (Mainframe Db2 -> Kafka -> Aurora PostgreSQL): Target < 1.5s
   - Reverse Replication (Aurora PostgreSQL -> Kafka -> Mainframe Db2): Target < 1.5s
2. **Conflict Resolution Strategy**:
   - `SOURCE_OF_TRUTH_WINS`: Mainframe canonical until 100% traffic shifted.
   - `LAST_WRITE_WINS_TIMESTAMP`: High-precision microsecond timestamp ordering.
3. **Loop Detection & Suppression**:
   - CDC marker origin tags (e.g., `origin_id = 'CLOUD_MICROSERVICE'`) to prevent feedback loops.
4. **Rollback Certification**:
   - Automatic green light / red light based on unsynced transaction buffer count (< 50 transactions).

## Agent Instructions & Output Schema
The skill delivers a structured cutover health report:
```json
{
  "topology": "BIDIRECTIONAL_ACTIVE_ACTIVE",
  "forward_stream": { "source": "Db2_zOS", "target": "Aurora_Postgres", "lag_seconds": 0.8 },
  "reverse_stream": { "source": "Aurora_Postgres", "target": "Db2_zOS", "lag_seconds": 1.2 },
  "unsynced_tx_buffer": 14,
  "rollback_safety_certified": true,
  "recommended_action": "Safe to proceed with 20% shadow traffic shift."
}
```
