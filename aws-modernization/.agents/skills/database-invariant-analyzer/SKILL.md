---
name: database-invariant-analyzer
description: >-
  Extracts and transforms legacy Db2 triggers, check constraints, stored procedures, and table invariants
  into cloud-native Spring Data JPA Entity Listeners, Bean Validation constraints, and Java 21 services.
---

# Database Invariant & Trigger Analyzer (Phase 1 / Copybook & DDL)

## Purpose
Legacy relational mainframe databases (Db2 on z/OS) frequently store critical business rules within triggers, check constraints, referential cascades, and stored procedures rather than in application COBOL code. The **Database Invariant Analyzer** extracts these hidden invariants and maps them into modern Spring Boot / JPA structures.

## Invocation & CLI Usage
Run the analyzer against legacy SQL DDL or Db2 catalog export files:
```bash
python -c "
import sys; sys.path.insert(0, 'apps/api')
from app.bedrock_skills import analyze_database_invariants
artifacts = '''
CREATE TRIGGER TRIG_POLICY_PREMIUM_AUDIT
AFTER UPDATE OF PREMIUM_AMOUNT ON POLICY_MASTER
REFERENCING OLD AS O NEW AS N FOR EACH ROW
BEGIN ATOMIC
  INSERT INTO POLICY_AUDIT_LOG (POLICY_ID, OLD_VAL, NEW_VAL, CHANGED_TS)
  VALUES (N.POLICY_ID, O.PREMIUM_AMOUNT, N.PREMIUM_AMOUNT, CURRENT TIMESTAMP);
END;

ALTER TABLE MOTOR_POLICY ADD CONSTRAINT CHK_VEHICLE_AGE CHECK (VEHICLE_AGE >= 0 AND VEHICLE_AGE <= 35);
'''
result = analyze_database_invariants(artifacts)
print(result)
"
```

## Supported Invariant Conversions
1. **Db2 Triggers (`CREATE TRIGGER ...`)**:
   - `BEFORE INSERT/UPDATE`: Converted to `@PrePersist` / `@PreUpdate` Spring JPA Entity Lifecycle Callbacks or Hibernate Event Listeners.
   - `AFTER INSERT/UPDATE`: Converted to Spring Data Domain Events (`@DomainEvents`) or transactional event publishers (`ApplicationEventPublisher`).
2. **Table Check Constraints (`ADD CONSTRAINT ... CHECK (...)`)**:
   - Converted to Jakarta Bean Validation annotations (e.g., `@Min`, `@Max`, `@Pattern`, or custom `@MotorVehicleAgeValid`).
3. **Stored Procedures (`CREATE PROCEDURE ...`)**:
   - Converted to stateless Java 21 Spring Service methods leveraging Spring Data Repositories or jOOQ type-safe queries.

## Output Schema
```json
{
  "total_invariants_detected": 2,
  "invariants": [
    {
      "name": "TRIG_POLICY_PREMIUM_AUDIT",
      "type": "TRIGGER",
      "legacy_ddl": "CREATE TRIGGER ...",
      "modern_equivalent": "@PostUpdate public void onPremiumChange(PolicyEntity entity) { ... }",
      "target_framework": "Spring Data JPA Entity Listener",
      "risk_level": "LOW"
    }
  ]
}
```
