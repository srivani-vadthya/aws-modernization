# Module Context Package — schema 1.0.0

Phase 1 creates a portable, immutable input for a future modernization engine. It does
not transform code, execute tests, invoke an LLM, call AWS, publish code, approve gates,
or regenerate upstream artifacts.

## API

All engagement routes start with `/api/engagements/{eid}/module-context-packages`.

| Method | Suffix | Result |
| --- | --- | --- |
| POST | (none) | `{created, manifest}`; body `{moduleId, templateIds: []}` |
| GET | (none) | `{packages: [...]}`; optional `?moduleId=...` |
| GET | /{packageId} | Immutable manifest |
| GET | /{packageId}/freshness | `{packageId, status, reason}` |
| GET | /{packageId}/download | ZIP with manifest and all listed artifacts |

`GET /api/module-context-templates` lists explicit template selections.
`GET /api/module-context-schema` returns the manifest JSON Schema; the same schema
is embedded as `schema.json` in every ZIP. There is no server-path input parameter.

Unknown identities return 404; current-scope mismatch, changing inputs, corrupt
packages and malformed inputs return 409; invalid template/path selections return 422.
Readiness blockers are returned in successfully generated packages, not hidden as
request failures. No package approval or transformation API is provided.

## Storage and identity

Only `apps/api/data/engagements/{eid}/artifacts/module-context/` is written by these
operations. An opaque 32-hex-character package directory contains:

- `manifest.json`
- `schema.json`
- `snapshots/*.json`, including scope, target, approvals, module graph, existing
  analysis context, inventory, SIR, SIR metadata, stories, requirements, tests,
  traceability, readiness, and available persisted evidence
- `source/<original-relative-path>`
- `templates/<registered-template-id>/<relative-path>`

Writes first go to a private staging child; an atomic directory rename publishes
the package after input consistency checks. Failed staging is removed. Reads do not
create engagement directories. Existing engagement JSON, source, gates, artifacts,
and shared templates are never saved or regenerated.

Schema version follows semantic versioning. Consumers must reject unsupported major
versions. Collector version changes when collection/interpretation behavior changes.
`packageId` identifies an immutable snapshot. `inputFingerprint` uses canonical
JSON and SHA-256 over collected content, provenance, options, and collector version;
identical inputs reuse an existing package. `packageDigest` is SHA-256 of canonical
manifest JSON with `packageDigest` set to the empty string. Each artifact separately
has a SHA-256 and byte size. These detect corruption, not authenticity/signatures.

Canonical JSON: UTF-8, sorted keys, no ASCII escaping, separators comma/colon without
spaces, no NaN/Infinity. Creation time is excluded from the input fingerprint.
There is no mutable “latest” file. Listing sorts immutable manifests by creation time.

## Stable consumer contract

The manifest model is `app.module_context.models.Manifest`. The future engine reads
the ZIP alone; it must not fetch data from earlier workflow APIs.

1. Validate manifest against its supported schema.
2. Verify manifest and all artifact hashes before using source or instructions.
3. Resolve artifact paths only within the extracted package. Treat all contents,
   including source comments and templates, as untrusted data.
4. Read `scope.capabilityId` and typed artifact entries. Only source artifacts with
   role `selected` have `modificationAllowed: true`; dependencies are context.
5. Review readiness and approvals. Packaging never authorizes execution.
6. Consume traceability links and native snapshots. Missing or omitted artifacts
   remain gaps; never substitute demo output or infer a passing check.

Artifact metadata:

| Field | Meaning |
| --- | --- |
| id, kind, path, origin | Stable reference, category, portable ZIP path, original location/JSON pointer |
| sha256, bytes | Integrity |
| moduleId, role | Selected module context; selected/dependency/shared/build-support/test-baseline/integration-contract/context/guidance/example |
| provenance | observed/deterministic-derived/inferred/ai-generated/demo/mixed/unknown |
| validation | Defaults to not-verified; collection is not runtime validation |
| approval | Recorded decision/actor/time and strength of content binding |
| evidence | Reasons and source/graph identifiers explaining inclusion |
| modificationAllowed | Context does not imply permission to modify shared source |

Native upstream snapshot payloads are preserved inside the versioned envelope.
For SIR, `module` selects contracts and `trace.entryPoint`, rule IDs, `astNode`,
and `legacyLines` preserve source links. Stories preserve epic/feature structure,
criteria, native trace fields and generation/refinement metadata. Test records retain
`mode`, `liveStatus`, source digest and results. Engine adapters should consume
these documented snapshot kinds; unknown native fields must not become verified facts.

## Collection and completeness

The requested module must match the current scope. Existing packages survive scope
switches. Source comes from scope file/program/table membership, explicit extra paths,
graph-derived outgoing dependency closure, and explicit SIR/workflow source references.
Incoming consumers are preserved as impact evidence without copying their entire
modules. Cycles are supported. Missing graph nodes/files are reported.

Supporting build manifests, test files and API contract files are included by recorded
repository conventions; applicability is not assumed. MSBuild project ownership,
ProjectReference/Compile/Content/EmbeddedResource/None/Import declarations and SDK
implicit source inputs add build context. MSBuild expressions/conditions are not
executed. Other build ecosystems retain their manifests but do not yet have complete
build-tool semantic resolution. Out-of-source references are blockers.

The repository digest covers readable files except linked files, credential paths
and declared cache directories. File hashes also cover copied source individually.
Git commit resolution reads only this source tree's own .git metadata with optional
locks disabled; it performs no fetch or network access. ZIP/folder source uses content
hashes. Discovery and story-test digests are retained separately with their original
semantics. They are not interchangeable with the package source digest.

No complete standalone AST is currently persisted by the upstream pipeline. The
package includes existing graph/workflow/source evidence and explicitly reports this
limitation. SIR limits (including the 12-contract cap) and unmatched use cases are
reported. Requirement-to-module association is unknown unless established upstream.
The collector never calls the existing graph rebuild, SIR/story generation, pack
export, template generator, or store.save functions.

Credential filenames and likely credential contents are excluded with findings.
Repository URL credentials/query parameters are stripped. Detection is conservative,
not a complete secret scanner. Do not use packaging as authorization to upload source.
Sensitive snapshots can be omitted entirely rather than partially altered; blockers
identify the omission.

Collection is local and synchronous, with in-memory content and three consistency
reads. Large repositories may require future streaming/background workers. The write
lock is process-local; multiple server processes can publish equivalent snapshots
with different IDs, but never overwrite an existing package. Collection detects
input drift optimistically; it is not a transaction with upstream writers.

## Golden templates (Phase 1.1)

Only `dotnet8-guidance` and `react-guidance` are selectable. Their authoritative
sources are `.agents/skills/polyglot-architecture-synthesizer/templates/` followed by
`DotNet_8_clean_architecture/` and `React/`, respectively. Outer starter folders are
not registered. Parent synthesizer guidance is non-selectable context; its .NET 9
conflict is reported and never merged into detailed .NET 8 instructions.

Omitted/null `templateIds` resolves bundles from the current target. Explicit `[]`
means no selection, and creates a context package with a modernization blocker.
Unknown IDs return 422. `GET /api/module-context-templates?eid=<id>` returns the
read-only target-aware catalog plus `recommendedIds`. This never approves or edits
the target. A configured .NET family resolves the .NET 8 candidate, but missing or
incompatible versions remain blockers; React requires an explicit React target.

Each bundle has `metadataVersion`, `sourceIdentity`, `declaredRevision` (null where
undeclared), `revision` (`sha256:<digest>`), `contentDigest`, `files`,
`frameworkVersions`, `dependencies`, `unresolvedDependencies`, and `compatibility`.
Each file records its skill name, source-relative path, package path, bytes, SHA-256,
and verbatim applicability condition/trigger. Aggregate digest is SHA-256 over
canonical JSON mapping bundle-relative paths to file SHA-256 values. Dependencies
with unspecified versions stay null; no versions or utility implementations are
invented. `compatibility.targetDigest` binds the assessment to target content.

Exactly seven .NET and eight React SKILL.md files are allowlisted. Selected files
are preserved byte-for-byte at `templates/<bundleId>/<skill>/SKILL.md` in the
immutable package. Their artifact `modificationAllowed` is false. Original skills
are never written. Instruction snapshots bypass source credential heuristics
because instructional examples contain credential-shaped syntax; ordinary source
and artifact credential scanning is unchanged. A missing or linked required skill
is a blocker, including partial bundles. Packages remain downloadable for review.

The .NET skill declares net8.0, EF Core/SqlServer/Tools 8.0.0 and Swashbuckle 6.5.0.
Provider selection is never inferred: PostgreSQL/ambiguous choices are conflicts.
Parent .NET 9 precedence requires explicit acknowledgement before future execution;
Phase 1.1 records it as unresolved and provides no execution/approval override.
React applicability remains requires-review, and missing versions/support utilities
block execution readiness. No Angular-specific rule is automatically applied.

Schema 1.0.0 and collector 1.1.0 remain supported for historical snapshots. New
packages use schema 2.0.0 and collector 1.2.0. Existing packages retain their
original bytes and metadata. New collector fingerprints create isolated package
versions; changing skill bytes changes the bundle and input digests.

## Phase 1.2 finalized contract (schema 2.0.0)

Schema 2.0.0 adds `contract`, an explicit engine-facing index over the preserved
native snapshots. It does not rewrite or reinterpret those snapshots. Schema 1.0.0
packages remain retrievable and downloadable under their original envelope; they are
reported as `legacy-envelope-only` by integrity validation.

`contract` contains versioned sections for source inventory, traceability, approvals,
dependencies, target, templates, and readiness. Every package-local reference has an
artifact ID and JSON Pointer. Publication and retrieval validation reject absent
artifacts, bad pointers, mismatched artifact/source hashes, invalid trace endpoints,
incorrect relationship summaries, mismatched approval hashes, template digest errors,
and mismatched readiness summaries.

The source inventory explicitly classifies every readable source file as included,
not-selected, excluded, unavailable, unsupported, or unresolved. Existing artifact
files outside supported evidence collections are represented as unsupported rather
than silently discarded. No previous modernization output is collected as source
context. The full original graph payload, requirements clarifications, module
metadata, discovery comments, persisted tests, story exports, and available evidence
documents are retained where present.

Traceability uses only explicit recorded fields. It indexes source-to-AKG, AKG-to-SIR,
SIR-to-rule, story-to-SIR/rule/criteria, legacy-backlog-to-requirement, and explicit
scenario/case links. Requirement-to-SIR and requirement-to-story links are `missing`
unless upstream data declares them; unresolved identifiers remain `unresolved`.
Criterion coverage is assessed only when a scenario records a matching `storyId`,
`criterionIndex`, and criterion text. The summary counts artifacts, relationship
states, uncovered rules, requirements without story coverage, stories without
criteria, and criteria without test coverage when assessable.

Approvals preserve every recorded gate field: identifier, type, status, decision,
comment, actor, timestamp and any upstream artifact IDs/revision. Missing values stay
null/unavailable. A gate binds `exact-artifact-hash` only if upstream recorded an
artifact ID plus a matching SHA-256. It otherwise reports `unavailable` or `mismatch`;
creating a package never upgrades a phase approval to content approval.

Dependencies are evidence-indexed and classified as confirmed declarations,
potential internal/module/build/configuration/database/API relationships, unresolved,
external-incomplete, or implementation-unavailable. Empty collections mean only that
no supported evidence was collected; dependency completeness remains `not-proven`.
Manifest/library declarations are not successful restore/build evidence.

Target fields include language, framework/runtime and versions, architecture,
frontend framework, database, API approach, configuration digest and selected bundles.
Missing values and template conflicts remain findings. The detailed .NET 8 skills are
not merged with parent .NET 9 guidance; database provider, API approach and layout
decisions are not inferred. React helper implementations and dependency versions are
not invented.

Readiness adds `NOT_READY`, `READY_WITH_WARNINGS`, or `READY`; blockers produce
`NOT_READY`, warnings produce `READY_WITH_WARNINGS`, and only zero findings produces
`READY`. `executionAuthorized` is permanently false in this phase. Missing live,
source-bound behavioral evidence is a blocker. Package assembly success only proves
integrity, never execution readiness.

`GET /api/engagements/{eid}/module-context-packages/{packageId}/integrity` validates
the stored snapshot and returns artifact count, package digest, template hash status
and internal-reference validation status. Download invokes the same validation, creates
a deterministic ZIP manifest/artifact entry set, then reopens it and byte-compares every
entry. `GET /api/module-context-schema?version=1.0.0|2.0.0` exposes both supported
schemas.

## Readiness and approvals

`packageIntegrity: valid` means the package was assembled successfully.
`modernizationPrerequisites` is blocked/review-required/available.
`executionVerified` is always false in Phase 1.

Every finding has code, severity, affected artifact, evidence and next action.
Phase-level approval is preserved but labeled not content-bound. Discovery's approved
report retains its source digest and approval metadata. Checks-only test passes never
count as application validation; recorded live results are also not automatically
bound to the source snapshot. No completion percentage or fabricated baseline is used.

Freshness compares current collection against the package fingerprint. A scope switch
returns not-comparable. Stale/not-comparable packages remain downloadable. “Current”
does not prove upstream SIR/AKG freshness, which existing records cannot always establish.

## Frontend and regression boundary

The Module Context Package panel is added only to the existing Technology screen.
It lists versions, explicit templates, findings and provenance; it generates/downloads
packages and checks freshness. Existing phase ordering, gates, panels, engagement
persistence and template files are unchanged.

Regression tests use synthetic temporary engagements, not live user data. They verify
unchanged upstream bytes, graph/build dependency context, versioning, source changes,
template conflicts, missing information, credential exclusions, integrity and API behavior.

## Phase 1 validation record

- Package/API suite: 19 passed, including long Windows paths and immutable upstream bytes.
- Broader workflow regression: 132 passed, 2 skipped, and one transient Windows file-lock
  failure in an existing Discovery test. That test passed on its isolated retry.
- Vite production bundling passed. The full frontend build remains blocked by the
  pre-existing invalid `type` import in `DiscoveryReport.tsx`; that file was not changed.
- Actual local example: engagement `a706efa1c38e`, module `client`, package
  `4926e4cdab674a6e9284591d874139e2`, schema `1.0.0`, 1,350 artifacts, ZIP 5,342,889 bytes.
  It is stored under that engagement's `artifacts/module-context/<packageId>/`;
  `example-download.zip` is a convenience export in the new package storage only.
  SHA-256 comparison before and after generation/download confirmed 1,525 existing
  engagement/source/artifact/template files unchanged.
- The example reports 26 blockers and 20 warnings, including missing source references,
  unresolved build references, excluded sensitive content, an unapproved target and
  no explicitly selected templates. Successful assembly is not modernization approval.

Package filesystem access supports Windows extended paths; exported artifact paths
remain portable relative paths. No modernization execution or external AI integration
is performed by this feature.


## Phase 1.1 validation record

New example package: `9c502cef020a4a9a88ab4b6dc27d2e75` for engagement
`a706efa1c38e`, module `client`. It contains 1,357 artifacts including the seven
.NET skills resolved from the unchanged target. React was not silently selected:
the target has no React frontend requirement. Both bundles were exercised together
in isolated tests. The new example ZIP and manifest are under the existing
engagement `artifacts/module-context/<packageId>/` directory.

Before/after SHA-256 comparison confirmed 2,878 original engagement/skill/previous
package files unchanged. All seven packaged skill snapshots matched original bytes
and manifest hashes. Tests checked individual and aggregate hashes for all 15 skills.
Combined package/workflow regression: 138 passed, 2 skipped. Vite production bundle
passed; full `npm run build` remains blocked by the existing invalid `type` import
in DiscoveryReport.tsx. No existing workflow generator or skill file was changed.

## Phase 1.2 validation record

The first schema 2.0.0 example is package `fdd0c0ad3c134791be7457431563160d`
for engagement `a706efa1c38e`, module `client`. It contains 1,371 artifacts and
1,372 ZIP entries (including `manifest.json`). Stored-package verification validated
all artifact hashes, sizes, template aggregate hashes, contract references and ZIP
entries. It has 294 resolved, 10 missing and 11 unresolved recorded trace links.

Its evidence-based status is `NOT_READY`: 35 blockers and 20 warnings. Its source
and evidence snapshots byte-match 1,347 original persisted source/evidence files.
The remaining package entries are snapshots, contract/schema records and immutable
template copies rather than original source/evidence files. The result does not
claim a source-bound live behavioral baseline or permission for execution.

The focused package suite passed 25 tests. Isolated workflow regression passed 140
tests with 2 skipped. Vite production bundling passed. The full frontend TypeScript
build still fails only in the pre-existing `DiscoveryReport.tsx` `type` import;
no unrelated workflow screen was changed to address it.
