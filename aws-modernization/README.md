# Nexus Modernize

Customer-demo portal for an AWS-centered modernization offering. AWS Transform is the conversion engine; this product is the control plane: intake, discovery, knowledge graph, business-module scope, requirements, backlog (Azure DevOps), cloud-native reimagine, tests, failure analysis, and a hand-off pack.

Default demo domain: **insurance** (IBM CICS GenApp). Region: `us-east-1`. No login in v1.

## Run locally

Terminal 1 — API:

```powershell
cd C:\Surya\aws-modernization\apps\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Terminal 2 — UI:

```powershell
cd C:\Surya\aws-modernization\apps\web
npm install
npm run dev
```

Open http://localhost:5173

## Demo path

1. **Load sample: GenApp insurance** (clones https://github.com/cicsdev/cics-genapp) for the curated demo, or paste a Git URL / upload a zip for reusable source-derived analysis.
2. Approve each phase gate (inventory → discovery → graph → Motor policy scope → SRS → backlog → architecture/code → tests → residuals).
3. Export wave-1 stories to Azure DevOps (configured PAT) or download the JSON payload.
4. Download the artifact pack. The curated GenApp demo also includes a generated Spring Boot skeleton.

## Reusable analysis

Git and ZIP engagements are no longer labelled as GenApp insurance. The pipeline inventories their assets, groups likely modules from their source-tree paths and file types, and generates a traceable baseline graph, requirements, backlog, test plan, and residual risks. These outputs are explicitly heuristic: validate module boundaries, dependencies, and business rules with source-language analysis and an SME before implementation.

The core pipeline is platform-neutral. Language analyzers are optional plugins that emit a shared relationship contract; the existing IBM i plugin handles RPGLE/SQLRPGLE, CLLE, DDS display/physical files, and COBOL members. It extracts conservative `CALLS`, `READS`, `WRITES`, and `MAPS_TO` leads; it is not a replacement for a compiler-backed dependency analysis. Additional analyzers can be registered without changing intake, gates, artifact packs, or the UI contract.

## Optional AWS S3 intake

To stage a sanitized source ZIP from an engagement, configure the API with an IAM role, AWS profile, or the normal AWS SDK credential chain, plus:

```dotenv
AWS_REGION=us-east-1
AWS_S3_INTAKE_BUCKET=your-private-intake-bucket
AWS_S3_INTAKE_PREFIX=nexus-modernize/intake
# Optional: AWS_PROFILE=your-named-profile
# Optional: AWS_S3_SSE=aws:kms
# Optional with aws:kms: AWS_S3_KMS_KEY_ID=alias/your-key
```

The identity needs `s3:PutObject` for the configured prefix, and `kms:Encrypt` when using a customer-managed KMS key. Staging is generic: an environment-specific Transform or other analysis connector is selected after intake, rather than being hard-coded to one source platform.

The **Load sample** path intentionally retains its curated GenApp discovery package and generated motor-policy skeleton for customer demonstrations.

## Optional integrations

Set in `apps/api/.env` (never commit secrets):

- `ADO_ORG`, `ADO_PROJECT`, `ADO_PAT` — create work items on export
- `GITHUB_TOKEN` — push generated code (later)
- `AWS_REGION=us-east-1` — Transform/Bedrock wiring (later)
