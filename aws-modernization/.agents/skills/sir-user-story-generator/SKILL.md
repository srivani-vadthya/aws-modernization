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
| **Story** `US-<SIR>-NN` (functional) | one business rule (`ruleId`, `statement`, `snippet`, `legacyLines`) | 1 per rule |
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
`acceptanceCriteria`, `storyPoints` (Fibonacci) and `priority` (Must/Should/Could/Won't). You may add
labels and `epic.businessOutcome`. Set `narrativeSource` to `"refined"` once you have rewritten a story.

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
- **Follow INVEST.** If a story would be more than 8 points, split it into sibling stories (`US-…-03a`,
  `US-…-03b`) and copy the same `trace` onto each.

**You must not:**
- Delete a story, or change `id` or any `trace` field (`sirId`, `ruleId`, `legacyLines`, `snippet`,
  `astNode`).
- Change the meaning of a rule labelled `deterministic-core`, or whose `trustBoundary` says "must not be
  altered". Keep its numbers, rounding, literals and conditions exactly as written.
- Invent behaviour. If the SIR is ambiguous, garbled or truncated, add an entry to `openQuestions`
  instead of guessing. Examples: a field named `NOT`, a snippet that stops at `USING`, or a state called
  `COMM_STUB_CALED`.

### Estimating legacy work
If a SIR contract carries `legacyAssessment` (the app attaches it from the AST/AKG: framework paradigm, coupling,
data layer, testability, integrations, security, unknowns), the script adds its `uplift` to story points
(`estimation` records base, uplift and the evidence), labels risky stories `legacy-risk`, adds a regression
scenario for adjacent workflows and a Definition of Done to the flow story, and turns anything the code cannot
answer into `Q-PLAN-nn` open questions. When rewriting stories, never lower `storyPoints` below `estimation.points`,
and keep the epic's `approach` (parity-first surgical port vs. refactoring) explicit.

### 4. Validate and review with the user
```bash
python .agents/skills/sir-user-story-generator/scripts/push_backlog.py validate backlog.json
```
Fix every `ERROR`. Regenerate the markdown and show the user a summary: the counts, any open questions,
and anything you split or re-prioritised. To regenerate the markdown:
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
- `scripts/sir_to_stories.py`: builds the SIR → backlog scaffold.
- `scripts/backlog_model.py`: the backlog schema, validation, and renderers (Markdown, HTML, Jira ADF,
  Jira wiki).
- `scripts/push_backlog.py`: `validate` and `push` for Jira, Azure DevOps, Bitbucket and GitHub. Uses
  only the Python standard library.
- `tracker-config.example.json`: template for the non-secret tracker settings.
- `examples/claims.sir.json`: the CLAIMCI0 / IMSCLAIM SIRs, used as sample input.
