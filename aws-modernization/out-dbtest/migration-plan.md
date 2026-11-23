# Database Migration Plan
**Source:** unknown  
**Target:** azure-postgresql  
**Generated:** 2026-11-20T10:49:36.392025+00:00  
**Tables:** 26  

## Migration Phases

### Phase 1: Schema Preparation
Review generated DDL, resolve HIGH/CRITICAL risk columns, add missing PKs.

- **Tool:** Manual review + db_migration_model.py validate
- **Risk:** low

**Steps:**
- Run: python migration_plan.py engagement.json --target azure-postgresql
- Review schema.sql for HIGH/CRITICAL risk columns
- Add surrogate PKs to tables flagged with no primary key
- Confirm NUMERIC precision with business stakeholders for packed decimal fields

### Phase 2: Target Schema Deployment
Deploy schema.sql to the azure-postgresql instance.

- **Tool:** psql or Flyway
- **Risk:** low

**Steps:**
- Create target database on azure-postgresql
- Run: psql -h <host> -U <user> -d <db> -f schema.sql
- Verify all tables created: SELECT tablename FROM pg_tables WHERE schemaname='public'

### Phase 3: Data Migration
Migrate data from unknown to azure-postgresql using the recommended tool.

- **Tool:** Flyway or Liquibase for schema + custom ETL for data
- **Risk:** high

**Steps:**
- Configure Flyway or Liquibase for schema + custom ETL for data
- Run initial full-load migration
- Validate row counts per table
- Run parity checks on HIGH-risk columns (packed decimal, date fields)

### Phase 4: ORM & Application Cutover
Update application ORM configuration to point to the new database.

- **Tool:** orm-config/ generated files
- **Risk:** medium

**Steps:**
- Replace existing ORM provider with generated orm-config/ files
- Update connection string in appsettings.json / application.yml / database.py
- Run application integration tests against the new database
- Enable CDC dual-write for shared kernel tables

### Phase 5: Cutover & Validation
Switch production traffic to the new database. Validate parity.

- **Tool:** Bidirectional CDC Guardrail skill + differential-golden-run-comparator skill
- **Risk:** critical

**Steps:**
- Enable bidirectional CDC for zero-downtime cutover
- Run differential-golden-run-comparator skill for parity validation
- Shift 10% traffic canary to new database
- Monitor for 24h, then shift 100%
- Decommission source database after 30-day observation period

## Tables

### `IMS.ENTITIES.CLAIM`
Source: `IMS.ENTITIES.CLAIM`  
Capability: `claim`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.CLAIMSTATUS`
Source: `IMS.ENTITIES.CLAIMSTATUS`  
Capability: `claim`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.CLAIMATTACHMENT`
Source: `IMS.ENTITIES.CLAIMATTACHMENT`  
Capability: `claim`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.CLIENT`
Source: `IMS.ENTITIES.CLIENT`  
Capability: `client`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.OFFER`
Source: `IMS.ENTITIES.OFFER`  
Capability: `client`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.OFFERSTATUS`
Source: `IMS.ENTITIES.OFFERSTATUS`  
Capability: `client`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.DIRECTORY`
Source: `IMS.ENTITIES.DIRECTORY`  
Capability: `directory`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.FORM`
Source: `IMS.ENTITIES.FORM`  
Capability: `form`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.DOCUMENTTYPE`
Source: `IMS.ENTITIES.DOCUMENTTYPE`  
Capability: `form`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.INVOICE`
Source: `IMS.ENTITIES.INVOICE`  
Capability: `invoice`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.INVOICESTATUS`
Source: `IMS.ENTITIES.INVOICESTATUS`  
Capability: `invoice`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.PARTICULAR`
Source: `IMS.ENTITIES.PARTICULAR`  
Capability: `invoice`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.PARTICULARTYPE`
Source: `IMS.ENTITIES.PARTICULARTYPE`  
Capability: `invoice`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.ACTIVITYLOG`
Source: `IMS.ENTITIES.ACTIVITYLOG`  
Capability: `activitylog`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.POLICY`
Source: `IMS.ENTITIES.POLICY`  
Capability: `policy`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.INSURANCEPROVIDER`
Source: `IMS.ENTITIES.INSURANCEPROVIDER`  
Capability: `insuranceprovider`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.POLICYTYPE`
Source: `IMS.ENTITIES.POLICYTYPE`  
Capability: `policytype`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.AGENT`
Source: `IMS.ENTITIES.AGENT`  
Capability: `agent`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.POLICYSTATUS`
Source: `IMS.ENTITIES.POLICYSTATUS`  
Capability: `policy`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.POLICYATTACHMENT`
Source: `IMS.ENTITIES.POLICYATTACHMENT`  
Capability: `policy`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.RISK`
Source: `IMS.ENTITIES.RISK`  
Capability: `policy`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.ENDORSEMENT`
Source: `IMS.ENTITIES.ENDORSEMENT`  
Capability: `policy`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.DEFAULTREBATE`
Source: `IMS.ENTITIES.DEFAULTREBATE`  
Capability: `defaultrebate`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.SOA`
Source: `IMS.ENTITIES.SOA`  
Capability: `soa`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.ENTITIES.SOASTATUS`
Source: `IMS.ENTITIES.SOASTATUS`  
Capability: `soa`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

### `IMS.WEBMVC.MODELS.APPLICATIONUSER`
Source: `IMS.WEBMVC.MODELS.APPLICATIONUSER`  
Capability: `identity`  

| Column | Source Type | Target Type | PK | Nullable | Risk | Note |
|--------|-------------|-------------|-----|----------|------|------|
| `ID` | `UNKNOWN` | `TEXT` | ✓ |  | high | Unknown source type; defaulted to TEXT — review manually |

## Risks

### [HIGH] High-risk type conversion: IMS.ENTITIES.CLAIM.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.CLAIMSTATUS.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.CLAIMATTACHMENT.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.CLIENT.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.OFFER.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.OFFERSTATUS.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.DIRECTORY.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.FORM.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.DOCUMENTTYPE.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.INVOICE.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.INVOICESTATUS.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.PARTICULAR.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.PARTICULARTYPE.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.ACTIVITYLOG.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.POLICY.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.INSURANCEPROVIDER.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.POLICYTYPE.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.AGENT.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.POLICYSTATUS.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.POLICYATTACHMENT.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.RISK.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.ENDORSEMENT.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.DEFAULTREBATE.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.SOA.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.ENTITIES.SOASTATUS.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.

### [HIGH] High-risk type conversion: IMS.WEBMVC.MODELS.APPLICATIONUSER.ID
UNKNOWN -> TEXT: Unknown source type; defaulted to TEXT — review manually
**Remediation:** Validate data values before migration. Run parity checks post-migration.
