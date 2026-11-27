---
name: tl-design
description: Use when starting or continuing the design of a new project or feature from its PRD, story register or prototype. Also use when asked where a design stands, what comes next, or to sign a design gate. Covers the tech lead workflow from raw sources through the Overview and LLDs to OpenAPI contracts and the task breakdown.
---

# tl-design

## Overview

A design set holds one project or feature. The main session runs this skill as the tech lead: `tl-design <handle>`.
It drives 14 steps across persona subagents, the `design-persona-review` Workflow, check scripts and the operator's
decisions. The operator signs every gate.

## Configuration

`.tl-relay/config.yaml` at the workspace root sets this skill's options. A missing file or key means the default. Paths follow [config.md](../using-tl-relay/config.md).

| Key | Default | Use here |
| --- | --- | --- |
| `knowledge_dir` | unset | The hub `K`: its `lint.sh` at step 10 |
| `state_dir` | `~/.tl-relay` | The root of `<runtime>`: the design set by default, and the publish dir |
| `operator_language` | `en` | The language of every operator question |
| `publish.command` | unset | The command step 12 runs, with `{dir}` and `{target}` |
| `publish.confirm_flag` | unset | The flag that makes `publish.command` push |

`<skill dir>` is this skill's base directory as the session reports it.

## Sibling skills

Before step 1, look up each of `ingest-sources`, `write-design`, `write-hla`, `write-lld`, `write-contract`,
`write-task-breakdown`, `technical-writing` and every `lens-*` skill in the session's skill list. A name counts with or
without the `tl-relay:` prefix. The list is the whole check: run no command and read no file for it. A name absent from
the list stops the run. Name it and give `npx skills add ace53thntu/tl-relay --skill <name>`.

## Readers and boundary

A design page has four readers: developers, QA, Solution Architecture and the EM. Each reads for a decision, not for code.

| Design page holds | Implementation plan holds |
| --- | --- |
| Scope | Pseudo-code |
| Entities and their relations | Full guard order (a route sequence shows only the checks a caller observes) |
| Routes and callers | DDL |
| State machines | DB migration order |
| High-level decisions with the rejected options | Per-field notes |
| Failure behaviour | Per-country config blocks |
| The values a decision fixed | File layout and test cases |
| Race and concurrency outcomes | |
| Invariants and their ids | |
| Business rules a caller or QA can observe, even when the source states them as guards | |
| Cross-team release dependencies | |

The implementation plan (`write-plan`) after G-design carries the right column. A page written to an earlier
skill version keeps its shape, and the budget check runs only on the pages a stage wrote or rewrote.

A rewrite moves each implementation-plan item it takes off a page to `$D/implementation-notes.md`.
That page is local and unpublished, and `doc_budget.py` types it `unknown`. The plan after G-design reads it. The rewrite's
audit lists each item as moved, not dropped.
`implementation-notes.md` holds only right-column items. An invariant, its id and a race outcome stay on a design page.

## State

`K` is the absolute path of `knowledge_dir`, unset when the key is unset. `DROOT` is the absolute `<design root>`. `D` is `$DROOT/designs/<handle>`. Each state file has one writer.

| File | Holds | Writer |
| --- | --- | --- |
| `D/index.md`, JSON block between `<!-- tl-design:state -->` markers | Sources, baselines, impact lines, stage status | `state.py` and `ingest-sources/scripts/snapshot.py` only |
| `D/workflow-state.md` | Step, stage, round, signed gates, open decisions, Workflow run ids, revise log | The session only, created from `templates/workflow-state.md` |

```bash
python3 "<skill dir>/scripts/state.py" --knowledge-root "$DROOT" --handle <handle> show
```

Write `<skill dir>` and each value in place in the Bash call. Set no shell variable in a command, because Claude Code asks
before every command that sets one.

| `state.py` command | Does |
| --- | --- |
| `init`, `show`, `next` | Create the set and its state block; print the state; print the next stage and its gate |
| `set-baseline --kind --sha256` | Moves a baseline after G-ingest and prints the stages it marked stale |
| `set-stage --stage --status [--signed]` | Sets a status. `signed-off` needs the date and no pending impact. A `design` status other than `signed-off` marks a signed `breakdown` stale |
| `set-reads --stage --kinds`, `add-impact --stage --reason --from-tsv`, `clear-impact --page --section` | Record a stage's source kinds; record the sections a drift record says must change; remove one section after its rewrite |

| Gate | Step | The session records the sign-off in |
| --- | --- | --- |
| `G-ingest` | 1 | `signed:`, then `set-stage --stage ingest --status signed-off --signed <date>` |
| `G-hla` | 7 | `signed:` only. `state.py` has no HLA stage |
| `G-design` | 10 | `signed:`, then `set-stage --stage design --status signed-off --signed <date>` |
| `G-breakdown` | 11 | `signed:`, then `set-stage --stage breakdown --status signed-off --signed <date>` |

- Sign a gate only after the operator says, in this conversation, that it passes. Pass the date the operator gives.
- Reopening `G-hla` removes `G-hla`, `G-design` and `G-breakdown` from `signed:`. Reopening `G-design` removes `G-design` and `G-breakdown`.
  Either reopen runs `set-stage --stage design --status draft`, which marks a signed `breakdown` stale.
- After G-ingest, run `set-baseline`, then `add-impact` with the drift record's impact file, when one exists. Report every stage it marked stale.
  Then rerun `set-stage --stage ingest --status signed-off` with the gate date.

## Start and resume

1. No `D/index.md`: ask the operator for the handle if none was given, then run `init`.
2. No `D/workflow-state.md`: create it from the template with `step: 1`, and start at step 1.
3. Otherwise resume at `step`, `stage` and `round`. Resume an unfinished Workflow run by its id in `workflow_runs`.
   The session records each Workflow it launches itself, at steps 1, 5, 8 and 9.
   It records the run id from the launch result, with the stage `round` where one exists.
4. Tell the operator the step, the round and the next human action in one sentence.

At step 1, a source already recorded with `baseline: true` counts as ingested unless it is the only recorded source of its kind and `ingest_sha256` holds its file `sha256`. Skip its snapshot.
A source with no baseline of its kind takes one `design-writer` dispatch for `ingest-sources` steps 1 to 3. The session then presents `G-ingest`.
After the gate rules for a first snapshot, clear `ingest_sha256`.
When the operator rejects a first snapshot at `G-ingest`, clear `ingest_sha256`.
When `ingest_sha256` holds the only recorded source of its kind, a resume with `G-ingest` unsigned repeats that dispatch, with the snapshot skipped.
A resume that finds `G-ingest` signed and `ingest_sha256` set, with no `ingest_ws`, finishes the gate rules, then clears `ingest_sha256` and every step 1 entry in `workflow_runs`.
Another file, a new revision included, waits while `ingest_sha256` holds the only recorded source of its kind.
Before step 1 compares a new file with `ingest_sha256`, run `python3 <skill dir>/../ingest-sources/scripts/snapshot.py --check --knowledge-root "$DROOT" --handle <handle>` on it.
Pass the kind, label and date its snapshot would take. A nonzero exit goes to the operator as a question.
While `G-ingest` is unsigned and `duplicate_of` names the source in `ingest_sha256`, the session repeats that source's dispatch, with the snapshot skipped.
Otherwise, when `duplicate_of` is not null, tell the operator the file is not a new revision. In that case, change no state and resume from the state as it is.
A new revision enters step 1 fresh when `ingest_sha256` does not hold its file `sha256`.
A source with no baseline of its kind enters step 1 fresh when `ingest_sha256` is empty.
When `ingest_sha256` holds its file `sha256`, the session repeats its dispatch.
Otherwise the file waits while `ingest_ws` is set or `ingest_sha256` names a recorded source, and enters step 1 fresh when neither holds.
On a fresh entry, remove `G-ingest` from `signed:`, and run `set-stage --stage ingest --status draft`.
Also clear `ingest_ws` and every step 1 entry in `workflow_runs`.
Then record the file's `sha256` as `ingest_sha256` in `workflow-state.md`.
A dispatch skips the snapshot when the revision in `ingest_sha256` is already recorded.
A new revision of another kind takes one dispatch for steps 1 and 2. The session then presents `G-ingest`.
After the gate rules, it clears `ingest_sha256`.
A new revision of a `stories` source runs in four parts:

1. Reuse `ingest_ws` when it is set. Otherwise create `$WS` under `<runtime>/designs/<handle>/runs/`.
   Name it `ingest-<date>-<first 8 characters of ingest_sha256>`.
   Resolve `state_dir` to an absolute path, and record `$WS` as `ingest_ws` in `workflow-state.md`.
   When `<runtime>` sits inside the workspace, add `<runtime>/designs/*/runs/` to the workspace `.gitignore` if absent.
   Write that line relative to the workspace root.
   Dispatch `design-writer` for `ingest-sources` steps 1 to 4.3 on `$WS`. It stops once `$WS/slices.json` exists.
   It writes both converted source paths to `$WS/writer.json`, with the step 3 command that wrote `$WS/new.jsonl`, every path absolute.
   If it returns without `slices.json` or `writer.json`, report its reason and stop.
2. Write the drift args, `digest` included, to `$WS/drift-args.json`, and rewrite them before each relaunch.
   Run `ingest-sources` step 4.4 in the session, with the reader tiers it defines. Then run step 4.5.
   Part 2 is done once `$WS/adjudication.json` carries the `inputs_sha256` that `assemble.py --pending` prints.
   A resume whose `--pending` list is empty reruns only step 4.5.
3. Dispatch `design-writer` again for `ingest-sources` steps 4.6 and 4.7 on the same `$WS`.
   If `$WS/ids-to-scan.txt` is not empty and `$WS/impact.tsv` is missing, report its reason and stop.
   Part 3 is done once the drift record's `audits/<date>-stories-adjudication.json` carries that `inputs_sha256`.
4. Present `G-ingest`. After it, follow the gate rules, with `ingest_sha256` as the `set-baseline` digest.
   Then rerun the `gen_register.py` command in `$WS/writer.json` with the `--page` flags of `ingest-sources` step 3.
   A nonzero exit from that rerun goes to the operator as a question.
   After each answer, rerun that `gen_register.py` command.
   Nothing is cleared until a rerun exits 0.
   Last, clear `ingest_ws`, `ingest_sha256` and every step 1 entry in `workflow_runs`.

A resume at step 1 reads `ingest_ws`. It resumes an unfinished recorded drift run with the args in `$WS/drift-args.json`.
With no such run, it continues from the first part that is not done.
With `G-ingest` signed, it finishes part 4.

Every `design-writer` dispatch for `ingest-sources`, the first snapshot's included, adds one rule to its prompt.
A sentence of `ingest-sources` that sends an error to the operator outranks the Ask rule: stop there and return that error as a question.
When such a dispatch returns that question, ask it through `AskUserQuestion` before any other step, not as a plain report.
Never add it to the open points, and present no `G-ingest` until the operator answers.

## Steps

Advance `step` only when the step's output exists and its human action is done.

| # | Step | Persona → skill/tool | Output | Operator |
| --- | --- | --- | --- | --- |
| 1 | Ingest | `design-writer` → `ingest-sources`. For a `stories` revision: 1 to 4.3, then 4.6 and 4.7. The session runs 4.4 and 4.5 | `sources/`, drift record | Accepts the drift, signs `G-ingest` |
| 2 | Interview | tech lead → `AskUserQuestion` | `decisions.md`, Interview section | Answers the gaps |
| 3 | Plan | tech lead | `plan.md`: pages to write, key decisions expected | Approves the outline |
| 4 | Draft HLA | `design-writer` → `write-hla`, `write-design` | Overview, use case, Schema changes and Dependencies pages | None |
| 5 | Persona review | `design-persona-review.js` → SA, SE, QA, Security, stage `hla` | `rounds/hla-r<n>/findings.json` | None |
| 6 | Decision loop | see [Decision loop](#decision-loop) | Updated pages, `decisions.md` | Key decisions |
| 7 | Sign HLA | tech lead → check scripts, head | `head.md` | Signs `G-hla` |
| 8 | LLD + contracts | `design-set-write.js`: `write`, `review`, `fix`, `rereview` | `lld/`, `contracts/` | None |
| 9 | Persona review + loop | steps 5–6 at stage `design`: `design-persona-review.js` → SA, SE, QA, Security, plus Temporal when it applies | `rounds/design-r<n>/findings.json` | Key decisions |
| 10 | Sign LLD | tech lead → check scripts, head | `head.md` | Signs `G-design` |
| 11 | Breakdown + estimates | `design-writer` → `write-task-breakdown`; `check_breakdown.py` | Task tables, proposed man-days | Confirms estimates (`timeline`), signs `G-breakdown` |
| 12 | Publish | `stage_publish.py`, then `publish.command` on the staged tree: a dry run without `publish.confirm_flag`, then the confirm run after approval; once when `publish.confirm_flag` is unset | Published pages, or a reported skip | Approves the target and the dry run; a rejected dry run means fix and restage, or record a skip |
| 13 | File tasks | The workspace's ticket-create command, dry run, then its confirm flag; with no such command, report a skip and go to step 14 | Ticket keys in the `ticket` column of the estimates TSV, or a reported skip | Approves the filing |
| 14 | Retro | tech lead | `retro.md`, proposed edits | Approves the edits |

The session dispatches `design-writer` with `Agent`, by the [agents rule](#running-without-agents-or-workflows). Its bound skills are the writer skills, such as `write-hla`. The writer tags every new or changed deep dive and module rule
in the Agent decisions section of `decisions.md`, with its `key_class`, reason and rejected option.
Every `design-writer` dispatch prompt, in `plugin`, `bare` and `none` mode, quotes the [Ask rule](#ask-rule) `key_class` table, with the `none` row, and its never-ask sentence.

Questions to the operator go through `AskUserQuestion` in the language `operator_language` names, `en` when it is unset, at most 4 per round, by the [Ask rule](#ask-rule). Ids and
code terms stay unchanged.

## Decision loop

Steps 6 and 9 run this loop. `round` starts at 1 for each stage.

1. The writer fixes every `blocking` finding, or disputes it in the Disputes section of `decisions.md`. It decides a key-class
   finding itself unless the [Ask rule](#ask-rule) sends it to the operator.
2. Items the Ask rule sends, and open disputes, go to the operator in one `AskUserQuestion` round, at most 4
   questions. Each gets an id `DR-n` in the Key decisions section and in `open_decisions`.
3. The writer applies the answers. The session records each answer and its page#anchor, then drops the id from `open_decisions`. Steps 5–6 repeat with `round` + 1.
4. The loop exits when a review returns no `blocking` finding and `open_decisions` is empty.
5. After round 3 the session stops, lists what is still open, and waits for the operator.

`minor` findings become `## Known gaps` in the head. Every answered key decision lands on a page as an Overview deep
dive (`HLA 4.N`) or a module rule. No page carries a `DR-n` id.

## Ask rule

The writer decides every item it can recommend, records it in the Agent decisions section with its `key_class`, reason and
rejected option, and the head lists it for the operator's veto. It asks the operator only when the item:

1. Changes what another team builds or sees: a contract, event or shared schema another team consumes, or a dependency row.
2. Changes the release timeline or a man-day figure.
3. Reverses an operator answer, an Interview row or a `DR-n`, or a fact on a signed page.
4. Has no clear recommendation, because the options trade off with no winner.

It never asks about a choice that matches the code at the baseline, follows from an earlier answer, or carries out an
answered decision. `key_class` classifies the item for the head and the ledger.

| `key_class` | Covers |
| --- | --- |
| `contract` | Contracts between teams or services: API, events, shared schema |
| `data_model` | Shared data model changes |
| `architecture` | Architecture options with a real trade-off |
| `security_release` | Security, sensitive data or release dependencies |
| `timeline` | Anything that affects the release timeline, including man-day estimates |
| `none` | No such choice is open |

**Open points.** A finding only an outside owner can answer, such as the PO or another team, stays `minor`. The session
adds it to `open-points.md` and `open-points-full.md` by the Rules below, and to Known gaps. It never blocks loop exit.

## Persona review call

Steps 5 and 9 call the `Workflow` tool with `scriptPath` `<skill dir>/workflows/design-persona-review.js`, where
`<skill dir>` is the base directory of this skill.

| Arg | Holds |
| --- | --- |
| `handle`, `knowledge` | The set's handle and `DROOT` |
| `stage` | `hla` at step 5, `design` at step 9 |
| `round` | The current `round` |
| `pages` | Absolute paths of the pages the stage wrote or changed |
| `temporal` | `true` only at stage `design`, only when a page names a Temporal workflow, schedule or worker, and only when the `temporal-workflow-design-critic` skill is available. Otherwise note the skipped persona in `workflow-state.md` |
| `ledger` | Absolute path of `D/decisions.md` |
| `agents` | `plugin` when the session lists `tl-relay:solution-architect`, `bare` when it lists `solution-architect`, else `none` |
| `workspace` | The absolute workspace root; required when `temporal` is `true` |

When the launch result gives the run id, append `{step, run, round}` to `workflow_runs` before the run returns.
An interrupted run then resumes by that id. The script returns `{stage, round, findings, missing, out}` and writes
`findings.json` at `out`.

- `missing` empty: read `findings`.
- `missing` names personas only: relaunch with the same `scriptPath`, the same args and `resumeFromRunId`. Resume reuses
  only the unchanged prefix of `agent()` calls, so personas after the first missing one may rerun with it and the merge.
- `missing` contains `merge`: `findings` and `out` are null. Relaunch the same way to rerun the merge.

Reviewers read only the pages, never `decisions.md` or sources. The merge marks a key-class finding `key_decision_unasked` only when its anchor matches a heading on its page. It also needs the Agent decisions section to have no row for that page and anchor. A key-class finding with an empty or off-page anchor stays `missing_detail` and is `blocking`.

## Draft head

At steps 7 and 10 the session writes `D/head.md` from `findings.json`, `decisions.md` and the check-script exits.

Line 1 is `READY|FAIL|BLOCKED <stage> r<n>`: `FAIL` when a check exits non-zero, `BLOCKED` when a decision is open.
Then a summary of at most 5 bullets, changed anchors, Agent decisions, Key decisions and Known gaps. The operator
reads the head and opens only the anchors it names.

`## Decided for veto` lists every Agent decisions row of the stage, from `decisions.md`, with a `key_class` other than `none`, one line
each: page#anchor, the choice, the rejected option. A veto at the gate becomes a `## Revise log` row and a `DR-n`.

## Check scripts

Before any sign-off, run these in order. Each script that runs must exit 0 before the session presents the gate, not after.

| Script | Runs on |
| --- | --- |
| `python3 <skill dir>/scripts/doc_budget.py <path>... [--waive <path>]... [--baseline <json>]` | Every page the stage wrote or rewrote |
| `python3 <skill dir>/../write-contract/scripts/check_contract.py --contract --lld --api [--module] [--common]` | Every module with routes, at G-design |
| `python3 <skill dir>/../write-task-breakdown/scripts/check_breakdown.py --set <set dir>` | The set, at G-breakdown |
| `sh "$K/scripts/lint.sh"`, only when `knowledge_dir` is set and `$K/scripts/lint.sh` exists | The hub |

- When `knowledge_dir` is unset or `$K/scripts/lint.sh` does not exist, the head reports the lint skip and the gate does not wait on it.
- Pass `--waive <path>` only for a page the operator named in this conversation, and record it in the head. A page edited in place runs against its pre-stage `doc_budget.py --json` report, passed as `--baseline`.
- On exit 1, move a fact to its named home, merge or link, and rerun. Never delete a design fact. When a page cannot
  meet its budget without dropping one, ask the operator, naming the page and the fact.

## Publish

Step 12 never pushes the set directory: its `index.md` holds the state block, and the local pages must stay unpublished.

```bash
python3 <skill dir>/scripts/stage_publish.py "$D" <publish dir> [--keep <key>]...
```

- `<publish dir>` is `<runtime>/designs/<handle>/publish/`, with `state_dir` resolved against the workspace root to an absolute path, because subagents work inside the repo worktree. It sits outside the hub and stays between pushes. Pass one `--keep <key>` for each entry in `publish.keep`. A restage keeps each page's frontmatter block under that key, such as the page id block a publish command writes back, so the next push updates the same pages. With `publish.keep` unset, a restage keeps no block.
- The script copies every page except the set `index.md`, `Note`, `Notes` and `Audit` pages, and the `audits/`, `rounds/`, `sources/` and `specs/` directories.
- The Overview becomes the root `index.md`. A module LLD `lld/<module>.md` becomes `lld/<module>/index.md`, and its API page `lld/<module>-api.md` becomes `lld/<module>/api/index.md`. Links follow the moved pages.
- The staged tree sits at `<publish dir>/_knowledge`, because some publish tools resolve links within the nearest knowledge directory.
- Every step 12 run checks the workspace `.gitignore` when `<runtime>` sits inside the workspace. It adds the line `<runtime>/designs/*/publish/` to the workspace `.gitignore` if absent, written relative to the workspace root. Staged pages hold page ids and must not be committed. A `state_dir` outside the workspace needs no line.
- When `publish.command` is unset, step 12 reports the skip and the run goes on to step 13.
- Otherwise ask the operator for the target. Fill `{dir}` with `<publish dir>/_knowledge` and `{target}` with the target.
  Run the command once without `publish.confirm_flag` and show the output. Then stop and wait for the operator to approve that output.
  Only then run it with the flag. When `publish.confirm_flag` is unset, run the command once, only after the operator approves the target.
  When the operator rejects the dry run output, fix the pages and restage, or record a skip in `workflow-state.md`. Run no confirm run.
- Record the push in a `## Publish` table in `workflow-state.md`: date, target, root page, page count, publish dir.

## Operator records

| Event | The session writes |
| --- | --- |
| The operator asks for a revise | One row in `## Revise log`: ts, stage, round, page#anchor, error_class, note in the operator's words. Then the writer revises |
| The operator confirms a man-day figure | The figure into the `md` column of `task-breakdown.estimates.tsv` |
| The ticket-create command returns keys | Each key into the `ticket` column of `task-breakdown.estimates.tsv` |

`error_class` is one of `missing_detail`, `voice_structure`, `length_focus`, `key_decision_unasked`, `other`.

## Retro

Step 14 runs after every set, and after any step where the operator revised a page.

1. Ask the operator what went wrong, and read `## Revise log`.
2. Write `D/retro.md`: each problem, the persona or skill at fault, and its error class.
3. Write each proposed edit into `retro.md` as text. Apply an edit only when its target file sits in a git checkout of `tl-relay` and the operator approves.
4. A problem that repeats across two retros becomes a check-script rule, not more prompt text.

## Working files

`workflow-state.md`, `decisions.md`, `plan.md`, `head.md` and `retro.md` sit in `D`. They are local and never
published. Each carries the frontmatter keys of `open-points-full.md`: `title`, `description`, `type: Note`,
`generated`, `stale_after`. The session lists each in `D/index.md` the way `open-points-full.md` is listed.
`decisions.md` starts from `templates/decisions.md` and is the `ledger` arg of both Workflows.

## Page tree

`write-design` (Page tree) owns the page tree, the page paths and the workflow-state files. Read it before the `design` stage starts.

The Overview has five children: Use cases, Schema changes, LLDs, Task breakdown and Dependencies.

## Running design-set-write

The `design` stage runs `<skill dir>/workflows/design-set-write.js` by `scriptPath`, one Workflow run per phase: `write`, `review`, `fix`, `rereview`. The script writes under `$D/`.

Write the Overview, use case pages, Schema changes and Dependencies pages first, with `write-design`. The `write` run comes after, because it reads those pages as inputs.

| Arg | Phases | Holds |
| --- | --- | --- |
| `phase` | all | `write`, `review`, `fix` or `rereview` |
| `handle` | all | The set's handle |
| `knowledge` | all | `DROOT` |
| `modules` | all | The modules that have routes, as the `lld/<module>.md` file names spell them |
| `skills` | all | `<skill dir>/..`, the directory that holds `write-contract` and `tl-design` |
| `ledger` | all | The absolute path of the ruling ledger |
| `findings` | `fix`, `rereview` | The findings the `review` run returned |
| `scratch` | `rereview` | The directory that holds the copy of the set made before the `fix` run |
| `baseline` | optional | The pre-stage `doc_budget.py --json` report, when the stage edits existing pages |

The design root has no git. Before each `fix` run, copy `$D` to a directory in the session scratchpad and pass that directory as `scratch` to the `rereview` run. The re-reviewer reads `diff -ru` between the copy and the set. The controller runs `doc_budget.py` itself on the pages of a module with no routes.

A set whose design runs a Temporal workflow, schedule or worker gets the `temporal-reviewer` persona at step 9, through `temporal: true` in the persona review call. It verifies each claim against the code. The writer fixes each finding or returns it as a question. A finding whose fix falls in a key class follows the Ask rule.

## Running without agents or Workflows

The `agents` value sets how a persona or writer is dispatched.

- `plugin`: dispatch `tl-relay:<name>`. `bare`: dispatch `<name>`.
- `none`, with a subagent tool: dispatch a general subagent on the agent's model. Its prompt names the bound skill to load,
  such as the lens skill for a persona or the writer skill for the current step, and carries the role text.
  The persona roles and models come from the `ROLES` and `MODELS` constants in `<skill dir>/workflows/design-persona-review.js`.
  `design-writer` runs on `opus` with this role: write and fix the pages of a design set through the bound writer skills. Tag each new or
  changed deep dive and module rule in the Agent decisions section of `decisions.md` with its `key_class`, reason and rejected option. Decide every
  key-class item you can recommend. Return an item as a question, with options and your recommendation, only when it changes what
  another team builds or sees, changes the timeline or a man-day figure, reverses an operator answer or a signed fact, or has no clear recommendation.
  The writer skills define no `key_class`, so the prompt also quotes the [Ask rule](#ask-rule) `key_class` table and its never-ask sentence:
  It never asks about a choice that matches the code at the baseline, follows from an earlier answer, or carries out an answered decision.
- No subagent tool: the session plays each role itself, loading the bound skill.
- No Workflow tool: run a persona or design-set script's phases in sequence, one persona lens at a time. Write the same `findings.json`. The step 1 drift run follows the reader tiers of `ingest-sources` instead.

## Rules

- Only this skill writes the Stages block. Stage skills write their own pages.
- Clear an impact line only after its section is rewritten, never before.
- A rewrite of a signed Overview into the current skeleton keeps `G-design` only when its audit lists no changed and no dropped fact. A changed fact reopens `G-design`.
  A fact moved to its named home, such as `implementation-notes.md`, is not a dropped fact.
- Open points live on two local pages per design set. They are the list the operator questions the
  Product Owner and other owners from. No design page carries an inline open point.
  - `$D/open-points-full.md` is the full list: every entry, each under its owner with its status.
  - `$D/open-points.md` holds only the entries with status Open, word for word as in the full list.
  - Neither page has a page id block from the publish command.
  - No design page links either page.
  - If the set has no full list yet, create it first as a copy of `open-points.md`.
- Stage skills and workflow agents return their questions. Add each one at the end of its owner's section, numbered
  one above the highest number in the full list. A deleted number is never reused.
  - An entry with status Open goes into both files, with the same text and number.
  - An entry with status Proposed or Accepted, such as another team's proposal, goes into the full list only.
  - An entry that changes status moves with it: it leaves `open-points.md` when it stops being Open, and joins it
    when it becomes Open.
- When an owner answers, record the answer as an Overview deep dive, a module rule or an `Assumption:` line, then
  delete the entry from both files. `Assumption: … Confirms:` lines stay inline on the design pages,
  as a plain paragraph with bold labels (**Assumption:** … **Confirms:** …), never wrapped in backticks. In a deep dive, the assumption line follows the Great panel.
- A design choice is final once the operator signs its gate. No stage waits on Solution Architecture or another reviewer
  to ratify a choice. A stage page carries no `Proposed` marker and no ratification sentence, and no ratification wait
  becomes an open point. Only work another team must build is an external dependency, stated once on the Dependencies page.
  An existing set without `dependencies.md` keeps each dependency statement where it stands, until the operator asks for that page.
- A design set has no decisions page and no `Dn` ids. A high-level decision picks between recorded
  alternatives at a component boundary. It is a deep dive `### 4.N` among the Overview deep dives, as `write-hla`
  sets. Pages cite it as `HLA 4.N`. A ruling that picks no alternative at a component boundary is a module rule under
  `## Rules` on the module's execution logic page, or nothing when the LLD already states it. A deep dive carries no
  status. A deep dive that waits on an owner links `dependencies.md` and names its `DEP-n` in one line.
- A set that still has a decisions page keeps it until the operator asks for the merge. `write-design` (Merging a decisions
  page) holds the steps. The merge changes no fact, so it keeps `G-design`.
- Stage skills own the page shape. Decisions live in Overview section 4, and module rules on the execution logic pages. A deep dive and a use case's own choice take
  the Bad, Good and Great solution panels `write-hla` sets. An LLD option set keeps the `**Decision.**` form `write-lld` sets, with no option panels.
- `write-design` sets where an LLD's blocks sit. In a set with several modules, Scenarios moves to a child page. A module with routes keeps section 4 on its API page. No gate restores a block to the parent.
  A route page's title is `API 4.N: <METHOD path> - <summary>`. Any other section 4 element page is titled `<Kind> 4.N: <name> - <summary>`, such as
  `Workflow 4.1: pickupBookingThWorkflow - Run one booking attempt`. Neither title carries the module name.
- **REQUIRED SUB-SKILL:** `technical-writing` for prose, then `unslop` when the session lists it (see `technical-writing`), then the Vale gate in `technical-writing`. Zero errors.
- **Technical wording, not narrative.** Headings are technical labels (`API changes`, not `Routes this
  design adds`). Body text uses technical terms, not colloquial phrases. Names use the operation and the code's own terms. See `technical-writing`, House rules.

## Common mistakes

- Treating a reviewer's "merge-ready" as the gate. The gate is the operator's words.
- Editing the JSON block by hand, which leaves baselines inconsistent.
- Adding an open point that asks Solution Architecture to ratify a choice. Record the choice as a decision instead.
