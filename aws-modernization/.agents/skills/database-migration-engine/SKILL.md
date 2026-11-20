---
name: database-migration-engine
description: >-
  Generic database migration skill. Detects the source database from any ingested
  repository, extracts its full schema, maps types to the target database engine,
  and generates target DDL, ORM configuration, and a phased migration plan.
  Supports any source (DB2 for i, DB2 z/OS, SQL Server, Oracle, MySQL, SQLite)
  and any target (Azure PostgreSQL, Aurora PostgreSQL, AlloyDB, Supabase).
---

# Database Migration Engine

## Purpose
When any repository is ingested by the platform, this skill reads the engagement
JSON already produced and performs the full database migration pipeline:

1. **Detect** — identify the source database engine from code evidence
2. **Extract** — pull every table, column, type, constraint, and index
3. **Map** — convert source types to target types (configurable, lossless-first)
4. **Generate DDL** — produce target-ready `CREATE TABLE` / index SQL
5. **Generate ORM** — emit the ORM wiring for the target language/framework
6. **Plan** — produce a phased migration plan with risk ratings

No changes are made to `apps/api/app/`. The skill reads from the engagement JSON
and writes only to its own output files.

## Invocation & CLI Usage

### Full pipeline (recommended)
```bash
python .agents/skills/database-migration-engine/scripts/migration_plan.py \
  apps/api/data/engagements/<id>/engagement.json \
  --target azure-postgresql \
  --out migration-plan.json \
  --ddl schema.sql \
  --orm orm-config/
```

### Individual steps
```bash
# Step 1 — detect source DB
python .agents/skills/database-migration-engine/scripts/db_detector.py \
  engagement.json

# Step 2 — extract schema
python .agents/skills/database-migration-engine/scripts/schema_extractor.py \
  engagement.json --out schema-raw.json

# Step 3 — map types
python .agents/skills/database-migration-engine/scripts/type_mapper.py \
  schema-raw.json --source db2i --target azure-postgresql --out schema-mapped.json

# Step 4 — generate DDL
python .agents/skills/database-migration-engine/scripts/ddl_generator.py \
  schema-mapped.json --target azure-postgresql --out schema.sql

# Step 5 — generate ORM config
python .agents/skills/database-migration-engine/scripts/orm_adapter.py \
  schema-mapped.json --language csharp --framework aspnetcore \
  --target azure-postgresql --out orm-config/

# Step 6 — validate output
python .agents/skills/database-migration-engine/scripts/db_migration_model.py \
  migration-plan.json
```

## Supported Source Databases
| Source Engine       | Detected From                                           |
|---------------------|---------------------------------------------------------|
| DB2 for i (AS/400)  | `.pf`, `.lf` DDS files, SQLRPGLE embedded SQL           |
| DB2 z/OS            | `.sql` DDL, COBOL EXEC SQL, JCL DSN references          |
| SQL Server          | `appsettings.json` connection string, EF Core SqlServer |
| Oracle              | `NUMBER`, `VARCHAR2` DDL, JDBC Oracle driver            |
| MySQL               | `TINYINT(1)`, `AUTO_INCREMENT` DDL patterns             |
| SQLite              | `.db` file reference, `Data Source=` connection string  |
| PostgreSQL          | `Npgsql` driver, `Host=` connection string              |

## Supported Target Databases
| Target                        | `--target` value     |
|-------------------------------|----------------------|
| Azure Database for PostgreSQL | `azure-postgresql`   |
| Amazon Aurora PostgreSQL      | `aurora-postgresql`  |
| Google AlloyDB                | `alloydb`            |
| Supabase                      | `supabase`           |
| Generic PostgreSQL            | `postgresql`         |

## Output Files
| File                  | Contents                                           |
|-----------------------|----------------------------------------------------|
| `migration-plan.json` | Full structured plan with risk ratings             |
| `schema.sql`          | Target DDL (`CREATE TABLE`, indexes, constraints)  |
| `orm-config/`         | ORM wiring files for the target language/framework |
| `migration-plan.md`   | Human-readable plan (optional `--markdown`)        |

## What It Reads From the Engagement
| Engagement Field                         | Used By               |
|------------------------------------------|-----------------------|
| `engagement.inventory`                   | `db_detector.py`      |
| `engagement.seed.tables`                 | `schema_extractor.py` |
| `engagement.seed.target`                 | `type_mapper.py`, `orm_adapter.py` |
| `engagement.applied_graph.sharedKernels` | `migration_plan.py`   |
| `engagement.seed.graph.edges`            | `migration_plan.py`   |

## Files
- `scripts/db_migration_model.py` — shared schema, validators, output renderers
- `scripts/db_detector.py`        — detects source DB engine from engagement inventory
- `scripts/schema_extractor.py`   — extracts tables, columns, types, constraints
- `scripts/type_mapper.py`        — maps source types to target types (config-driven)
- `scripts/ddl_generator.py`      — generates target DDL SQL
- `scripts/orm_adapter.py`        — generates ORM config for target language/framework
- `scripts/migration_plan.py`     — full pipeline + phased migration plan + risk report
