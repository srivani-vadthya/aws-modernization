---
name: sir-user-story-generator
description: >-
  Turns Semantic IR (SIR) contracts extracted from legacy code (COBOL/IMS/CICS/RPG) into a traceable
  Epic > Feature > User Story backlog with Gherkin acceptance criteria, then pushes it to Jira,
  Azure DevOps, Bitbucket or GitHub. Use when asked to generate user stories, a backlog, epics or
  features from SIR / semantic information retrieval output, or to push/sync those stories to a tracker.
---

# SIR → User Story Generator (Epic / Feature / User Story)

## Purpose
SIR contracts (`SIR-xxx`) describe what a legacy program does: business rules with code traces,
a state flow and side effects. This skill turns them into a backlog that a delivery team can plan with.
Every story traces back to the exact legacy lines it came from, and the backlog can be pushed to the
team's tracker.

A script builds the scaffold, so no rule is ever dropped. **You** (the agent) then rewrite the wording in
business language, without changing any of the traced facts.

## Hierarchy mapping

| Backlog level | Comes from | Count |
|---|---|---|
| **Epic** `EP-<MODULE>` | SIR `module` (business capability), or `--epic` override | 1 per module |
| **Feature** `FT-<SIR id>` | one SIR contract (`name`, `summary`, `stateMachine`, `sideEffects`, `inputs`) | 1 per SIR |
| **Story** `US-<SIR>-NN` (functional) | one piece of business behaviour: the rules of one legacy method (grouped by `astNode`): one validation scenario for its conditions, one scenario per operation, all rules in `trace.ruleIds` | 1 per legacy method (split into parts of max 6 operations) |
| **Story** `US-<SIR>-FLOW` (flow) | `stateMachine` transitions + `sideEffects` + required `inputs` | 1 per SIR |
| **Story** `US-<SIR>-ENB` (enabler) | rules with `kind: legacy_plumbing_pruned` or classification containing "plumbing" | 0–1 per SIR |

## Workflow

### 1. Locate the SIR input
Any of these work as input:
- An engagement: `apps/api/data/engagements/<id>/engagement.json` (reads `seed.semantic_ir`).
- The API: `GET /api/engagements/<id>`. Save the response to a file first.
- A file holding a list of SIRs, `{"semantic_ir": [...]}`, or a single SIR object.
- SIR shown only as a screenshot or UI text: transcribe it into the `SemanticIR` shape
  (`apps/web/src/api.ts`). 
  Transcribe exactly, including typos. Do not fix anything while transcribing.

### 2. Generate the scaffold
```bash
python .agents/skills/sir-user-story-generator/scripts/sir_to_stories.py <input.json> \
  --out backlog.json --markdown backlog.md [--epic "Claims"] [--persona "claims adjuster"] [--only SIR-002]
```
Put the outputs where the user wants them, for example `apps/api/data/engagements/<id>/artifacts/`.

### 3. Refine the stories (your job)
Edit `backlog.json`. For each story:

**You may change** `title`, `narrative.asA/iWant/soThat`, `description` and the wording of
`acceptanceCriteria`, `storyPoints` (Fibonacci, set by the rules in
[3a](#3a-estimating-story-points-complexity-work-risk-and-human-vs-ai-capability)) and `priority`
(Must/Should/Could/Won't). You may add labels and `epic.businessOutcome`. Set `narrativeSource` to
`"refined"` once you have rewritten a story.

Guidance for the rewrite:
- **Say what the business gets, not what the code does.** For example,
  `CALL 'CBLTDLI' USING DLI-GET-UNIQUE` means "retrieve the existing claim before deciding to insert or
  update it, so duplicates are never created". Only state a purpose that the SIR statement, summary or
  side effects support.
- **Use real personas.** "As a claims adjuster" is better than "As a system". For technical enablers,
  use "platform engineer".
- **Make acceptance criteria concrete.** Use one Gherkin `Scenario` per string, with real values,
  literals and error texts copied from the SIR, for example
  `Then the response contains "ERROR: CLAIM RECORD FOR UPDATE NOT FOUND"`. Keep the parity scenario.
- **A story is a behaviour, not a branch.** Never create one story per `if`/branch. Keep every rule of the story as a scenario (closely related rules may share one), and never drop a rule from `trace.ruleIds`.
- **Follow INVEST.** If a story would be 13 or more points, split it into sibling stories (`US-…-03a`,
  `US-…-03b`) and copy the same `trace` onto each.

**You must not:**
- Delete a story, or change `id` or any `trace` field (`sirId`, `ruleId`, `legacyLines`, `snippet`,
  `astNode`).
- Change the meaning of a rule labelled `deterministic-core`, or whose `trustBoundary` says "must not be
  altered". Keep its numbers, rounding, literals and conditions exactly as written.
- Invent behaviour. If the SIR is ambiguous, garbled or truncated, add an entry to `openQuestions`
  instead of guessing. Examples: a field named `NOT`, a snippet that stops at `USING`, or a state called
  `COMM_STUB_CALED`.

### 3a. Estimating story points (Complexity, Work, Risk, and human vs AI capability)

**What not to do.** Do not turn every branch into a rule, and do not turn every rule into a story. Do not
give a story a fixed 3 or 5 points. Those three habits are why the Invoice module came out at **455 points
in 121 stories**.

**How a story is formed**
- **A branch is a condition, not a rule.** The SIR step merges a method's `if`, `throw` and `BadRequest`
  lines into one *"Validates the request before processing"* rule, with the lines listed in `conditions`
  and `conditionLines`. For older SIRs that have one rule per branch, the story step merges them the same
  way.
- **A rule is a requirement, not a story.** A functional story is one piece of business behaviour: the
  rules of one legacy method.
  - Its acceptance criteria are one validation scenario, one scenario per operation (read, write,
    delegate, external call), and one parity scenario.
  - A method with more than 6 operations is split into parts, so a story never has more than 8 scenarios.
  - Every rule stays in `trace.ruleIds`.

**How a story is sized: three factors, each scored 1 (very low) to 5 (very high)**
Each level is backed by evidence the team can check, recorded in `estimation.<factor>.evidence`.
`scripts/estimation.py` computes them.

| Factor | What raises it (evidence the script reads) |
|---|---|
| **Complexity** (technical and domain difficulty) | 3–5 decision points: +1. 6 or more: +2. Deterministic-core rules (formulas, writes, external calls) that must be reproduced exactly: +1. Touching 4 or more components: +1. Legacy coupling or framework paradigm (Web Forms, WCF, deep call chain): +1. Flow story: number of steps, external integrations. |
| **Amount of work** (volume and extent) | Operations to rebuild and test, plus 0.5 per condition (each needs a test case), plus 1 for data writes. This maps to 1–5 at the thresholds 1 / 3 / 6 / 10. Code that needs refactoring before it can be tested: +1. Flow story: steps to wire, side effects to verify, adjacent workflows to regression-test. |
| **Risk and uncertainty** (knowns vs unknowns) | External system dependency: +1. Relevant unknowns from the legacy assessment: +1 each, up to +2 (data such as stored procedures or shared tables; integration; security; untraced calls or undocumented intent). Flow story: up to +3. **Team context:** no one knows the legacy stack: +1. New to the target stack: +1. Has built something similar before: −1. |

**Scale and reference story.** The three levels are added up (3–15) and compared with the reference
story, *"Read one record and return it"*. That story scores C1 + W2 + R1 = 4, which is **2 points**.

| Factor sum | ≤3 | 4–5 | 6–7 | 8–9 | 10–11 | 12–13 | 14–15 |
|---|---|---|---|---|---|---|---|
| Points | 1 | 2 | 3 | 5 | 8 | 13 (split if you can) | 21 (must split) |

The script labels the backlog story closest to the reference profile `reference-story`, and adds
`Q-EST-02` so the team can confirm it or replace it with a story they have already delivered.
`estimation.confidence` is `high`, `medium` or `low`, following the risk level.
`estimation.inputsNeeded` lists what the cross-functional team must bring to size or finish the story:
- Design: a wireframe, for screen controllers.
- QA: edge cases, when there are 3 or more conditions.
- DBA: stored procedures and shared tables.
- Integration: a sandbox and contract for external dependencies.

**Team context.** Pass it as `engagement.teamContext = {legacyStackFamiliar, targetStackFamiliar,
builtSimilarBefore}`, or on the command line as `--team-knows-legacy / --team-knows-target /
--team-built-similar yes|no`. An unknown answer adds no risk and raises `Q-EST-03`.

**Human vs AI capability.** Every story gets two estimates. The team plans with the AI-assisted one
(`storyPoints = estimation.aiPoints`). `estimation.humanPoints` is the manual baseline.
AI re-scores the same three factors:
- It removes **55% of the Amount of work** (65% at L3, where an automated parity harness takes over
  regression testing).
- It removes **25% of the Complexity**, because it reads and explains the legacy code.
- It removes **5% of the Risk**, because answers still come from people, vendors and DBAs.

| Level | Team working style | Multiplier |
|---|---|---|
| L0 | No AI tools | 0 (AI-assisted = manual) |
| L1 | IDE autocomplete or chat only | 0.5 |
| L2 (default) | AI agent with the SIR, AST and this backlog as context | 1.0 |
| L3 | L2 plus an automated legacy-replay parity harness in CI | 1.2 |

Set the level with `--ai-capability` or `engagement.aiCapability`. If it is not set, L2 is assumed and
`Q-EST-01` is raised.

**Limits**
- A story never claims more than 70% saving, and an epic never more than 60%.
- `estimation.humanOnly` is effort only people can do (2 points when risk is 4 or more, or when a flow
  story has open questions). `aiPoints` never goes below it.

**Invoice module, 104 SIR rules**

| | Before | Now |
|---|---|---|
| Stories | 121 | **45** |
| Manual baseline | 455 points | **204 points** |
| AI-assisted at L2 | — | **100 points** |
| AI-assisted at L1 / L3 | — | 140 / 96 points |

**Your job during refinement**
- Check the evidence for each factor, not the arithmetic. If the evidence is wrong or incomplete (for
  example, the domain rule is harder than the code shows, or a vendor dependency is missing), change the
  factor level.
- Record the reason in `estimation.notes`.
- Keep `storyPoints` between `estimation.points` and `estimation.humanPoints`. Never lower `humanPoints`.

### 4. Validate and review with the user
```bash
python .agents/skills/sir-user-story-generator/scripts/push_backlog.py validate backlog.json
```
Fix every `ERROR`. Regenerate the markdown and show the user a summary: the counts, **human-baseline
vs AI-assisted points per epic with the AI efficiency %, and the capability level assumed**, any open
questions, and anything you split, bundled or re-prioritised. To regenerate the markdown:
`python -c "import sys,json; sys.path.insert(0,'.agents/skills/sir-user-story-generator/scripts'); from backlog_model import backlog_markdown; open('backlog.md','w',encoding='utf-8').write(backlog_markdown(json.load(open('backlog.json',encoding='utf-8'))))"`

### 5. Push to a tracker
1. Ask which tracker to use if the user has not said: `jira`, `ado`, `bitbucket` or `github`.
2. Copy [tracker-config.example.json](tracker-config.example.json) to `tracker-config.json` and fill in
   the non-secret settings.
3. Check that the secrets are set as environment variables (or kept in a git-ignored `.env` file and
   passed with `--env-file`). Never write tokens into config, backlog or skill files, and never echo them.
4. **Dry run first.** It sends nothing:
   ```bash
   python .agents/skills/sir-user-story-generator/scripts/push_backlog.py push backlog.json \
     --provider jira --config tracker-config.json [--show-payload]
   ```
5. Show the user the dry-run plan, then **get explicit confirmation**. Creating work items is visible to
   other people and hard to undo. Once confirmed, re-run the same command with `--apply`.
6. Report the created keys and URLs from the output.

How the push behaves:
- **Re-runs are safe.** `backlog.push-state.json` records what was pushed to each tracker and target.
  Re-running skips existing items and picks up after a partial failure. If a parent fails, its children
  are skipped.
- **Template stories are blocked.** `--apply` refuses stories with `narrativeSource: "template"` unless
  you pass `--allow-template`.
- **Partial pushes.** `--only US-SIR-002-01 …` pushes only the listed stories, plus their epic and
  feature if those don't exist yet.

## Tracker mapping (summary)

| Provider | Epic | Feature | Story | Hierarchy |
|---|---|---|---|---|
| `ado` (Agile) | Epic | Feature | User Story (Scrum: PBI) | native parent links; AC in the Acceptance Criteria field |
| `jira` `featureMode: label` | Epic | label `feature-FT-…` on its stories | Story | `parent` = Epic |
| `jira` `featureMode: epic` | `topIssueType` (e.g. Initiative) or label | Epic | Story | `parent` = feature Epic |
| `github` | issue + `epic` label | issue + `feature` label | issue + `user-story` label | native sub-issues |
| `bitbucket` | `[Epic]` issue | `[Feature]` issue | issue | `Parent: #N` link in body |


## Files
- `scripts/sir_to_stories.py`: builds the SIR → backlog scaffold (stories per legacy behaviour).
- `scripts/estimation.py`: story points from Complexity, Amount of Work and Risk & Uncertainty, relative
  to a reference story, plus the AI-assisted estimate.
- `scripts/backlog_model.py`: the backlog schema, validation, and renderers (Markdown, HTML, Jira ADF,
  Jira wiki).
- `scripts/push_backlog.py`: `validate` and `push` for Jira, Azure DevOps, Bitbucket and GitHub. Uses
  only the Python standard library.
- `tracker-config.example.json`: template for the non-secret tracker settings.
- `examples/claims.sir.json`: the CLAIMCI0 / IMSCLAIM SIRs, used as sample input.
