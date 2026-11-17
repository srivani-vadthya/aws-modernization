---
name: batch-modernization-engine
description: >-
  Extracts and transforms legacy JCL job streams, SORT steps, and batch COBOL programs into cloud-native
  Spring Batch chunk-oriented pipelines (ItemReader -> ItemProcessor -> ItemWriter) and Azure Data Factory / AWS Step Functions.
---

# Batch Modernization Engine (Nightly Batch & ETL)

## Purpose
In enterprise banking and insurance mainframes, over 65% of MIPS consumption occurs during the overnight batch window running thousands of JCL jobs. Transforming online CICS transactions to REST APIs without modernizing nocturnal batch processing leaves the mainframe running indefinitely.

The **Batch Modernization Engine** parses JCL steps (`EXEC PGM=...`, `SORT FIELDS=...`, `IEBGENER`), file disposals (`DISP=(OLD,DELETE)`), and sequential file updates, generating production-grade **Spring Batch 5 / Azure Data Factory** chunk-oriented workflows.

## Invocation & CLI Usage
```bash
python -c "
import sys; sys.path.insert(0, 'apps/api')
from app.bedrock_skills import modernize_batch_job
jcl_sample = '''
//DAILYPOL JOB (ACCT),'DAILY RENEWAL',CLASS=A,MSGCLASS=X
//STEP10   EXEC PGM=SORT
//SORTIN   DD DSN=PROD.POL.MASTER,DISP=SHR
//SORTOUT  DD DSN=&&TEMP1,DISP=(NEW,PASS)
//SYSIN    DD *
  SORT FIELDS=(1,10,CH,A)
/*
//STEP20   EXEC PGM=POLRNW01
//INPUT    DD DSN=&&TEMP1,DISP=(OLD,DELETE)
//OUTPUT   DD DSN=PROD.POL.RENEWED,DISP=(NEW,CATLG)
'''
result = modernize_batch_job(jcl_sample)
print(result)
"
```

## Generated Artifacts
1. **Spring Batch Step Configuration**:
   - `ItemReader<PolicyRecord>`: Streaming reader with configurable chunk size (e.g. 1,000 items/chunk).
   - `ItemProcessor<PolicyRecord, RenewedPolicy>`: Core rating calculation and status updates.
   - `ItemWriter<RenewedPolicy>`: Bulk batch insert to PostgreSQL with multi-threaded partitions.
2. **Cloud Orchestrator Pipeline**:
   - Azure Data Factory pipeline or AWS Step Functions state machine mapping job step dependencies.
