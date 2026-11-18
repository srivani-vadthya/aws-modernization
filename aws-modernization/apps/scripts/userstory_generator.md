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
| **Feature** `FT-<MODULE>-<AREA>` | the business area: the part of the use-case name before `:` (`Invoice` in "Invoice: Post") | 1 per area |
| **Story** `US-<SIR id>` | one business use case = one SIR contract. Internal calls between pieces of code get no criterion of their own; plumbing is left out; a contract with only internal calls (e.g. a class that wires up repositories) produces no story | 1 per SIR with business behaviour |

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
[3a](#3a-estimating-story-points-business-complexity-only)) and `priority`
(Must/Should/Could/Won't). You may add labels and `epic.businessOutcome`. Set `narrativeSource` to
`"refined"` once you have rewritten a story.

Guidance for the rewrite:
- **Say what the business gets, not what the code does.** For example,
  `CALL 'CBLTDLI' USING DLI-GET-UNIQUE` means "retrieve the existing claim before deciding to insert or
  update it, so duplicates are never created". Only state a purpose that the SIR statement, summary or
  side effects support.
- **Use real personas.** "As a claims adjuster" is better than "As a system".
- **Write the story as the user story.** The title is `As a <role>, I want <goal> so that <benefit>`,
  built from `narrative.asA / iWant / soThat`. Add a 2-4 sentence business `description` and 2-5 short
  lowercase `labels`.
- **Make acceptance criteria concrete.** One line per criterion: `Given <context>, when <action>, then
  <outcome> (<rule ids>)`, ending with the ids of the rules it covers, with real values, literals and
  error texts copied from the SIR, for example `... then the response reads "ERROR: CLAIM RECORD FOR
  UPDATE NOT FOUND" (R-004)`. Keep the criterion showing the outcome matches the current system.
- **Write criteria in plain English.** A non-technical reader must understand each line at first read:
  short sentences (under about 30 words), everyday words, active voice, one idea per line. Say "the
  invoice is saved", not "the record is persisted"; "is empty", not "is null". No jargon, code terms,
  status codes or field/table names. Simplify the wording only: keep the business intent and every
  condition, number, quoted value and error text unchanged.
- **A story is a use case, not a branch or a method.** Every rule id of the story must appear in at least one criterion, e.g. `(R2–R6)`; never drop a rule from `trace.ruleIds`.
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

### 3a. Estimating story points (business complexity only)

**Technical details are not considered.** Story points measure how complex the *business* ask is, not how
hard the code is to change. Classes, frameworks, coupling, stored procedures, test tooling, the team's
stack familiarity and AI tooling do not raise or lower a story's size.

**What not to do.** Do not turn every branch into a rule, and do not turn every rule into a story. Do not
give a story a fixed 3 or 5 points.

**How a story is formed**
- **A branch is a condition, not a rule.** The SIR step merges a method's `if`, `throw` and `BadRequest`
  lines into one *"Validates the request before processing"* rule, with the lines listed in `conditions`.
- **One story is one business use case** (one SIR contract), never one per code method. Its acceptance
  criteria are: one line for its business checks (quoting the status values and messages they use), one
  for the records it saves, one for each notification or outside system, one for the information it shows
  (read-only use cases), one for adjacent workflows (only when it changes records), and one showing the
  result is identical to the current system, which also cites the internal calls. Max 8.
- **Business decisions (C#).** The SIR step reads each use case with the C# syntax tree (`apps/api/app/business_logic.py`): every `if` / `else` / `switch` / `foreach` / `catch` path of the entry
  method and the helper methods it calls, with what happens on it (values set, refusals and errors, records
  added / updated / deleted, emails sent). Each becomes a rule (`astNode` ending `:DECIDES`, with a `logic`
  field) and one acceptance criterion, worded by `scripts/checks_text.py`, e.g. "Given the invoice has not been
  saved yet and an invoice with the same invoice number and the same insurance provider already exists, ...
  then the request is refused with the error "InvoiceNumber"". Up to 16 criteria; more than 8 is flagged
  for splitting.
- **The template never guesses.** It states only what the SIR proves. Translating a code condition such as
  `entity.Id == 0` into business words is the AI refinement's (or a person's) job; a rewrite that drops a
  rule id is rejected and the template is kept.
- **Same action twice** (e.g. a screen and an API that both create an invoice) raises a `Q-DUP-nn` question.
- **Legacy plumbing is not a story.** Rules classified as plumbing are technical and are left out.
- Every story still keeps its `trace` in `backlog.json`, but it is not shown or pushed.

**How a story is sized: three business factors, each scored 1 (very low) to 5 (very high)**
Each level is backed by evidence in `estimation.<factor>.evidence`. `scripts/estimation.py` computes them.

| Factor | What raises it |
|---|---|
| **Business rules** (`rules`) | 3–5 business conditions: +1; 6 or more: +2. Exact calculations or policies that must not change: +1. 4 or more rules in one behaviour: +1. Rules on money, eligibility or compliance: +1. Flow story: number of process steps, hand-offs to outside parties. |
| **Process scope** (`scope`) | Business outcomes to verify, plus 0.5 per condition (each an acceptance scenario), plus 1 when business records change, plus 1 when 3 or more business entities are involved; mapped to 1–5 at 1 / 3 / 6 / 10. Flow story: steps end to end, outcomes to verify, adjacent business workflows that must keep working. |
| **Business uncertainty** (`uncertainty`) | Depends on an outside party or system: +1. Business intent not documented in the legacy system: +1. Money/compliance rules that must not change (errors have direct business impact): +1. Flow story: open business questions: +1. |

**Scale and reference story.** The three levels are added up (3–15) and compared with the reference
story, *"Look up one business record"*: B1 + S2 + U1 = 4, which is **2 points**.

| Factor sum | ≤3 | 4–5 | 6–7 | 8–9 | 10–11 | 12–13 | 14–15 |
|---|---|---|---|---|---|---|---|
| Points | 1 | 2 | 3 | 5 | 8 | 13 (split if you can) | 21 (must split) |

The script labels the story closest to the reference profile `reference-story` and adds `Q-EST-02` so the
team can confirm it or replace it with a story they have already delivered.

**Your job during refinement**
- Check the evidence for each factor. If the business rule is harder than the evidence shows (for example a
  regulatory or financial nuance), raise `storyPoints` by at most one Fibonacci step and record why in
  `estimation.notes`. Never lower `storyPoints` below `estimation.points`.

**What is shown.** Each story is shown as a card: ID, the rules it covers and the legacy behaviour,
story points, **Title** (the user story), **Description**, **Acceptance criteria** (one per line) and
**Labels**. In the app every field is editable and saved on blur (`PATCH /api/engagements/{id}/
user-stories/stories/{storyId}`); **Remove** deletes a story (`DELETE` on the same path); ticked
cards limit a tracker push to those stories.

### 4. Validate and review with the user
```bash
python .agents/skills/sir-user-story-generator/scripts/push_backlog.py validate backlog.json
```
Fix every `ERROR`. Regenerate the markdown and show the user a summary: the counts, **story points per epic**, any open
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
- `apps/api/app/business_logic.py` (app side): reads the business decisions of a C# use case from its syntax tree for the SIR.
- `scripts/checks_text.py`: turns each business check (a code condition) into plain English, e.g.
  `if (model.Particulars.Count > 1)` -> "there is more than 1 particular"; never guesses a meaning.
- `scripts/estimation.py`: story points from business complexity (Business rules, Process scope,
  Business uncertainty), relative to a reference story. Technical details are not considered.
- `scripts/backlog_model.py`: the backlog schema, validation, and renderers (Markdown, HTML, Jira ADF,
  Jira wiki).
- `scripts/push_backlog.py`: `validate` and `push` for Jira, Azure DevOps, Bitbucket and GitHub. Uses
  only the Python standard library.
- `tracker-config.example.json`: template for the non-secret tracker settings.
- `examples/claims.sir.json`: the CLAIMCI0 / IMSCLAIM SIRs, used as sample input.
