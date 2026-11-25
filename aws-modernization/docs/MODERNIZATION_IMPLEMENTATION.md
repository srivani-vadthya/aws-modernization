# Modernization implementation guide

This is the implementation reference for the VModernize Modernization Engine.
It documents the capability that exists today: its inputs, approvals, provider
paths, artifact storage, and limitations.

For local installation and configuration, see [LOCAL_SETUP.md](LOCAL_SETUP.md).

## Purpose

The engine turns an approved, versioned Module Context Package into a controlled
modernization execution. It does not overwrite the original cloned legacy
repository and it does not regenerate Discovery, AKG, Scope, SIR, Requirements,
or User Stories while execution is running.

It provides:

- module-scoped source and dependency context
- immutable target architecture and golden-template snapshots
- readiness, plans, orchestration, approvals, and execution records
- AWS Transform-first allocation for supported .NET 8 backend/API tasks
- Amazon Bedrock generation for compatible remaining tasks
- isolated provider workspaces and collected outputs
- persisted task events, provider attribution, and artifact hashes

## End-to-end flow

```text
Repository intake
  -> Discovery / AKG / Scope / SIR / Requirements / User Stories
  -> Target Architecture approval
  -> Module Context Package
  -> Readiness assessment
  -> Plan approval + orchestration approval
  -> Explicit browser authorization
  -> Provider execution
  -> Collected output + validation review
```

## Module Context Package

The immutable engine input is stored at:

```text
apps/api/data/engagements/<engagement-id>/artifacts/module-context/<package-id>/
```

It contains the source inventory, selected scope, dependency/build context,
upstream evidence snapshots, target configuration, approvals, traceability,
readiness findings, and selected template snapshots. The manifest and each listed
artifact have SHA-256 integrity metadata.

Plans, orchestrations, and executions bind to package ID and digest. A stale,
corrupt, mismatched, or unsupported package cannot execute. See
[module-context-package.md](module-context-package.md) for the detailed contract.

## Scope behavior

The selected module is the requested modification scope. The package also includes
the context required to modernize it safely:

- selected source files
- declared shared source and dependencies
- project/solution manifests and build-support files
- integration contracts and recorded traces where available

AWS Transform receives only plan-approved source references in an isolated
`legacy-source` workspace plus `modernization-scope.json`. The scope contract tells
Transform to work only within the selected module and its dependency/project closure.

### Practical limitation

Legacy .NET applications commonly keep controllers, views, configuration, and data
in one project. When a project build closure is needed, Transform can modify more
than the initially selected files within that project. It must not expand into
unrelated projects outside the staged closure. The execution artifacts make that
closure visible.

## Target architecture and golden templates

The approved target defines target language, framework/runtime, frontend, database,
architecture, API style, and selected template bundles.

Authoritative templates are only the skills below:

```text
.agents/skills/polyglot-architecture-synthesizer/templates/
  DotNet_8_clean_architecture/
  React/
```

Selected `dotnet8-guidance` and `react-guidance` files are copied byte-for-byte into
the Module Context Package with individual file hashes and aggregate bundle digests.
The original skills are never modified.

The outer `BackendTemplate/` and `FrontendTemplate/` folders are not authoritative
for this engine. They remain in the repository because older application code still
references them and require a separate refactor before removal.

### How templates reach providers

| Provider | Template delivery |
| --- | --- |
| Amazon Bedrock | Applicable immutable package snapshots are included in the task prompt. |
| AWS Transform | Snapshots are staged in `.modernization-templates/`; `modernization-template-contract.json` identifies the selected bundle revisions and requires those snapshots to be used as golden guidance. |

Collected artifacts record the selected template bundle revisions.

## Readiness, approval, and authorization

Preparation does not call a provider. It generates or reuses a package, verifies
integrity/module identity, calculates readiness, and creates or reuses a
version-bound plan and orchestration.

Plan and orchestration approval are required before execution. Execution also needs
explicit browser authorization. The UI exchanges an operator token for a short-lived
HttpOnly session cookie. The token is not stored in React source, local storage, or
engagement artifacts.

A `401` means browser authorization is missing or expired; it does not mean source
conversion failed. Re-authorize the session without restarting the API.

## Planning and provider allocation

Each plan task contains source references, target requirements, acceptance criteria,
provider rationale, and expected safe output roots. Dependencies are evidenced, not
invented.

| Workstream | Current allocation |
| --- | --- |
| Compatible .NET 8 backend/API | AWS Transform first |
| Compatible frontend/configuration/API not supported by Transform | Amazon Bedrock when configured |
| Database, build/deployment, testing, integration without verified automation | Manual engineering review |

AWS Transform is selected only for the installed `AWS/dotnet-modernization`
definition and a compatible .NET 8 target. Provider selection is capability-based,
not a fixed backend/frontend split.

## Provider execution

### AWS Transform

The integration invokes the local AWS Transform CLI (`atx`) and requires:

- an authenticated AWS Transform CLI/profile
- local .NET SDK 10 or later for the Transform worker
- an approved compatible .NET 8 backend/API task

The current limits are five minutes without provider progress and two hours total.
Restarting the API interrupts the local provider worker.

Transform writes only to the isolated staged source copy first. After a successful
task completion, the engine collects changed files into the output workspace. The
original legacy clone is never overwritten.

### Amazon Bedrock

Bedrock receives the approved target, applicable template snapshots, source context,
and previous generated context. It must return a JSON `files` mapping. The engine
accepts only safe paths under:

```text
backend/  frontend/  data/  docs/  tests/
```

Traversal paths, malformed mappings, and unsafe output are rejected. Configured
Bedrock status means local configuration exists; model access is proven only by an
authorized invocation.

## Execution storage and outputs

Each execution is isolated:

```text
apps/api/data/engagements/<engagement-id>/artifacts/
  modernization-executions/<execution-id>/
    execution.json
    legacy-source/
    output/
```

| Location | Meaning |
| --- | --- |
| `execution.json` | Lifecycle, task attempts, events, provider failures, and generated-artifact metadata. |
| `legacy-source/` | Temporary provider working copy. In-progress Transform changes appear here and are not final output. |
| `output/` | Collected provider output. Transform files are copied here after its task succeeds; accepted Bedrock files are written here. |

Initial .NET/React scaffolds are starter files only. They are not proof that a
provider completed business-code modernization.

## Lifecycle and UI

Key states are:

```text
CREATED -> VALIDATING -> QUEUED -> RUNNING -> COMPLETED
                                      -> FAILED / CANCELLED / INTERRUPTED
```

The Code Modernization UI shows readiness, selected templates, plan/provider
allocation, authorization, persisted provider events, and collected artifacts.
Service-layer checks reject invalid transitions, stale bindings, duplicate task
locks, missing approvals, and missing authorization.

Manual-review tasks are reported as manual work; they are never silently presented
as automated modernization completion.

## Validation expectations

Collected output starts as `unverified`. Provider success means output was safely
collected; it does not prove business-behavior parity.

Review each execution with:

1. task completion/failure events and provider logs
2. generated artifact/source/template provenance
3. target/template compatibility findings
4. build and automated tests of generated code
5. API, database, and integration contract checks
6. source-bound legacy-versus-modern behavioral validation
7. missing source, excluded sensitive content, unresolved dependencies, and manual
   review workstreams

Do not treat package-integrity or output-collection tests as legacy application
execution or business-behavior parity tests.

## Current limitations

- Provider work may be partial, fail validation, or exceed the execution timeout.
- A failed/interrupted provider task is not final modernization output.
- Build/test/behavioral parity require explicit validation and are not fabricated
  from static analysis.
- Missing legacy source, excluded credential-bearing configuration, unresolved build
  references, and incomplete traceability remain visible as gaps.
- AWS Transform currently supports the configured .NET backend/API definition; it
  is not generic automated frontend/database modernization.
- React template guidance is supplied to compatible Bedrock tasks. Missing dependency
  versions and applicability conflicts are reported rather than invented.

## Main implementation locations

| Responsibility | Location |
| --- | --- |
| Module package collection/integrity | `apps/api/app/module_context/` |
| Plans, orchestration, execution lifecycle | `apps/api/app/modernization_engine/` |
| Provider adapters | `apps/api/app/modernization_engine/providers.py` |
| Provider staging/output handling | `apps/api/app/modernization_engine/provider_execution.py` |
| Browser authorization | `apps/api/app/modernization_engine/execution_auth.py` |
| Code Modernization UI | `apps/web/src/components/ModernizationEnginePanel.tsx` |
| Frontend API client | `apps/web/src/api.ts` |
| Authoritative template source | `.agents/skills/polyglot-architecture-synthesizer/templates/` |
