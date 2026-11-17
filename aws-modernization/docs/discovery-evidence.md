# Source-backed discovery

Discovery has six views: Overview, Modules, Dependencies, Integrations, Findings,
and AIOps Telemetry. It does not consume the historical demo discovery or token
totals. No AWS Transform connection is claimed.

## Running it

Start the existing API and web app. Open an engagement's Discovery step. The
view inspects local source and automatically reviews a new source snapshot with
Bedrock. There is no separate model button. **Refresh discovery** rescans the local
checkout (it does not pull Git commits), includes saved comments and reuses the
review if source and saved comments are unchanged. A failed model request leaves measured
source data visible; Refresh discovery permits an explicit retry.

**Clone & Discover** performs inventory internally and opens Discovery directly.
There is no separate Intake & Inventory screen or human intake approval. Internal
intake completion is recorded as completed, not as human approval. Previously saved
intake engagements open Discovery too; later approvals and selected scope remain.
The duplicate section-comment editor and unmeasured coverage card are removed.
Use the existing governance comment field when approving or rejecting Discovery.
Previously saved section comments remain available in report exports.

The API reads its existing `.env`; secrets are never returned in reports.
Discovery uses `DISCOVERY_BEDROCK_MODEL` if supplied, otherwise
`BEDROCK_MODEL_REASONING` (default `amazon.nova-pro-v1:0`). Authentication uses
`BEDROCK_API_KEY` or `AWS_BEARER_TOKEN_BEDROCK`. Requests explicitly use Bedrock,
regardless of the legacy `LLM_PROVIDER` setting. Other pipeline stages retain
their existing provider configuration. There is no silent provider/model fallback.

The configured Nova Lite and Nova Pro models returned HTTP 200 in live smoke
checks. The configured Claude 3.5 Sonnet model returned HTTP 404; discovery does
not use it. Availability can change; the UI reports subsequent failures.

## Evidence and limitations

- Project frameworks, manifest dependencies, paths, counts and physical LOC are
  read from source. Versions are declarations, not verified deployed versions.
- Languages are inferred from extensions. LOC includes comments and blank lines
  in recognized text formats. Headline metrics count provisional application code.
  An expandable breakdown retains every scanned file/line across application,
  vendor, generated, support and unclassified categories. Vendor identity requires
  a library/license banner; generated code requires a marker or source-map link.
  Filename-only library hints remain unclassified. Per-file reasons are exported.
- Node dependencies, NuGet packages directories, build outputs, Git metadata,
  symlinks and files above 2 MB are excluded. Files that cannot be read or parsed
  are listed. Unknown/binary formats have no LOC measurement.
- XML project references are direct declarations. Source integration and type/
  AngularJS matches are **lexical leads**, not a compiler AST, symbol resolution,
  complete call graph or runtime proof. Comment handling is limited; review leads.
- Existing capability IDs are retained as **inferred groupings** for continuity.
  Unassigned source, including frontend files, is grouped by owning project or
  top-level folder. Proposed business modules and technical groups are separate.
  Discovery refresh does not alter scope membership or approval state.
- Repeated integrations are grouped by API family and project, not assumed to be
  distinct external systems. Raw reference counts and every evidence link remain.
- Coverage, complexity, license, security, lifecycle and external-system ownership
  remain unmeasured/unverified. No invented pass rates or integration owners.
- Bedrock reviews up to 160 evidence records balanced across evidence kinds.
  Configuration values and raw source contents are not sent. Model output must
  reference supplied evidence IDs; invalid references and placeholder findings
  are discarded. Valid references do not prove an interpretation correct: AI
  findings remain labelled as requiring review.
- AIOps records review attempts, provider/model, actual returned token counts,
  and locally measured elapsed time. Cost is null, not an invented estimate.
- Source fingerprint changes invalidate previous AI interpretations. Model
  failures retain source findings and are reported without raw response bodies.

## Storage and compatibility

Reports and comments are stored beside the engagement in `discovery-report.json`
and `discovery-comments.json`, with current report/evidence/graph copies under
`artifacts/`. Refresh does not rewrite engagement.json or approval state.
Explicit discovery approval snapshots `artifacts/discovery-approved.json` and
projects source-backed capabilities, file paths and labelled graph edges into
the seed consumed by Scope and AKG. Existing selected scope is preserved. Later
requirement extraction uses exact selected paths when available. Demo semantic
IR is cleared on adoption: lexical declarations are never presented as an AST.
Reports are per-engagement and written atomically. In-process locking prevents
overlapping reviews; automatic duplicate requests reuse pending/saved results.

Final ZIP downloads include discovery.json, discovery-approved.json (when an
approval exists), discovery-evidence.json, discovery-comments.json,
discovery-declarations.json, discovery-graph.json and discovery-provenance.json.
The conventional graph.json follows the approved snapshot when present. Provenance
records whether the latest scanned source matches the approved snapshot.

Endpoints:

- `GET /api/engagements/{id}/discovery-report`: inspect source, reuse same-source AI.
- `POST /api/engagements/{id}/discovery-report`: refresh; `useBedrock` controls AI,
  `onlyIfNeeded` deduplicates reviews by schema version, source and saved comments.
- `POST /api/engagements/{id}/discovery-comments`: save section review comments.

This change improves the Discovery screen. It does not certify or replace the
unrelated legacy demonstration outputs in later modernization phases. It does
not claim that all languages have equal analysis depth: arbitrary repositories
receive an inventory, supported manifests receive dependency inspection, and
unsupported language-specific analysis is explicitly listed.

## Verification

From `apps/api`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_discovery_report.py -v
```

From `apps/web`:

```powershell
npm.cmd run build
```

Offline regressions cover source references, frontend inclusion, invalid AI
evidence, provider failures, source changes, report/comment persistence, missing
source handling, classification accounting, grouping, automatic-review caching,
multi-language coverage, ZIP content and Discovery -> Scope -> Requirements gates.
