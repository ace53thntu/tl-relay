---
name: tl-implement
description: Use when a signed design's breakdown row must be built, as in implement row DC-4.2 of a design handle. Also use to resume a run or to ask where a run stands. Covers the tech lead workflow from one breakdown row through plan, build, conformance and a gate to a pull request.
---

# tl-implement

## Overview

One run builds one breakdown row of a signed design set: `tl-implement <handle> <row>`. The main session runs this
skill as the tech lead. It drives 10 steps across persona subagents, `write-plan`, `run-plan` and the operator's
gate. The operator reads one document, the head, and approves or vetoes items.

| Persona | Model | Does | Never does |
| --- | --- | --- | --- |
| `tech-lead` | Main session | Orchestrates, rules on non-key items, renders the head, asks the operator | Writes product code |
| plan gate | Opus, high effort | Reads the plan against the row's page; finds contradictions, missing steps, unbuilt dependencies | Edits the plan |
| implementer | Sonnet | One plan task per subagent, test first | Decides a key-class item |
| code reviewer | Opus, high effort | `/code-review` per `review-change` | Fixes code |
| `qa-conformance` | `opus` | One row per rule: code location, test name, verdict | Reviews style or finds general bugs |
| `temporal-code-reviewer` | `opus` | Reviews Temporal code in the diff against the rule set | Runs when the diff has no Temporal code, or when `temporal:temporal-developer` is unavailable |

## Configuration

`.tl-relay/config.yaml` at the workspace root sets this skill's options. A missing file or key means the default. Paths follow [config.md](../using-tl-relay/config.md).

| Key | Default | Use here |
| --- | --- | --- |
| `state_dir` | `~/.tl-relay` | The root of `<runtime>`, which holds the run dir and, by default, the design set |
| `worktree_dir` | unset | The worktree root after `$WORKTREE_ROOT` |
| `operator_language` | `en` | The language of every operator question |
| `tracker.comment` | unset | The command step 9 runs to post the ticket comment, with `{target}` and `{body_file}` |
| `tracker.confirm_flag` | unset | The flag that makes `tracker.comment` post |

## Sibling skills

Before step 1, look up each of `tl-design`, `write-plan`, `run-plan`, `test-first`, `review-change` and `lens-qa-conformance` in the
session's skill list. A name counts with or without the `tl-relay:` prefix. The list is the whole check: run no command
and read no file for it. A name absent from the list stops the run. Name it and give
`npx skills add ace53thntu/tl-relay --skill <name>`.

## Inputs of a run

The skill reads, from `<design root>/designs/<handle>/`:

- The row in `task-breakdown.md`: Task, Scope, Design link, Depends on, MD.
- The ticket key from the `ticket` column of `task-breakdown.estimates.tsv`.
- The repo from the breakdown's `affects` frontmatter.
- The page the Design link names: an LLD page, or the set's `schema-changes.md` for a schema and config row.
- The rule set: that page plus every LLD and Overview anchor it links to, one hop deep. A shared page counts only at the anchors the row's page links to.
- The Ask-rule triggers and the set's `decisions.md` § Agent decisions, so the run does not reopen settled items.

A rule is what `lens-qa-conformance` § Rules counts as a rule. Scenarios are test material, not rules.

## Run state

Run state is runtime data. It lives under `<runtime>`, outside the hub and the repo:
`<runtime>/designs/<handle>/runs/<row>/` (the run dir). It holds:

- `run-state.md`, created from `templates/run-state.md`.
- `plan-gate.md`, `fixes.md`, `head.md`, `conformance-r<n>.json`, `temporal-r<n>.json` and `retro.md`.

When `<runtime>` sits inside the workspace, the step that creates the run dir checks the workspace `.gitignore`. It adds the line `<runtime>/designs/*/runs/` if absent, written relative to the workspace root. A `<runtime>` outside the workspace needs no line.

`state_dir` is resolved against the workspace root to an absolute path, because subagents work inside the repo worktree.

The main session is the only writer. A run resumes at its recorded `step`. Tell the operator the step, the round and
the next human action in one sentence.

## Workspace conventions

The branch name, commit identity, push remote and `gh` identity follow the workspace `CLAUDE.md` when it names them. Without them the run uses
git's own config for the commit identity, remote `origin`, the active `gh` account, and the branch name `<ticket>-<row slug>`.

## Steps

Advance `step` only when the step's output exists and its human action is done.

| # | Step | Persona → skill/tool | Output | Operator |
| --- | --- | --- | --- | --- |
| 1 | Start | tech-lead | Run state, worktree and branch | — |
| 2 | Plan | tech-lead → `write-plan`, spec = the row's page | Plan file | — |
| 3 | Plan gate | Opus plan gate | Findings; plan revised, at most 2 rounds | Ask-rule questions only |
| 4 | Build | `run-plan`: Sonnet implementers, `test-first`, per-task and final `review-change` | Commits on the branch, ledger | — |
| 5 | Conformance | `qa-conformance`, plus `temporal-code-reviewer` when it applies | Conformance table, Temporal findings | Answers a signed-page-is-wrong question; answers the Temporal review question once per run |
| 6 | Fix loop | implementer fixes, step 5 reruns, at most 3 rounds per pass | Commits | Ask-rule questions only |
| 7 | Knowledge refresh | tech-lead | Corrected pages in the repo's own `_knowledge/` bundle and `**Refresh**` log lines, on the same branch | — |
| 8 | Gate | tech-lead renders the head | `head.md` | Approves, or vetoes items |
| 9 | Publish | push, open PR, ticket comment | PR URL, comment id | Approves the comment output |
| 10 | Retro | tech-lead | `retro.md`, proposed edits | Approves the edits |

### Step 1, start

The checks run in this order, each before any worktree, branch or run directory exists:

1. A row with no ticket key refuses to start and points at `tl-design` step 13.
2. A breakdown with more than one repo refuses to start.
3. Each Depends on row needs a PR merged into the repo's default branch.
   The skill looks in three sources. They are the row's run state `pr:`, the repo's PRs by the row's ticket key, and a PR the operator names at start.
   It looks up each PR's merged state, because `pr:` is recorded when the PR opens.
   The check passes when any PR found in these sources is merged into the default branch.
   The run state's `depends:` field records the PR. An unconfirmed PR refuses the run and names the unmerged row.

Then the skill creates the run dir and the run state. It fetches `<remote>` first, then creates the worktree and a branch with `--no-track`
from `<remote>/<default branch>`. The worktree sits under the workspace's worktree root, which is the `CLAUDE.md` section "Worktree location", else `$WORKTREE_ROOT`, else `worktree_dir`, else `<state_dir>/worktrees`, and the branch name follows the
workspace `CLAUDE.md` convention with the ticket key when present, else `<ticket>-<row slug>`. The run state records `base:`, the `<remote>/<default branch>` commit. `<remote>` is the push remote the workspace `CLAUDE.md` names. Without one, it is remote `origin`.

### Step 2, plan

Invoke `write-plan` with the row's page (an LLD page or `schema-changes.md`) as its spec, and state that the caller gates the plan itself. The plan's
`affects` names the repo. Take back the saved plan path and record it in `plan:`.

### Step 3, plan gate

A fresh Opus subagent at high effort reads the plan and the rule set. With no subagent tool, the main session runs the gate. It reports contradictions with the pages,
missing steps and steps that depend on something the plan never builds. The tech lead adjudicates.

- At most 2 rounds. A failed round sends the plan back through `write-plan` with the findings, again stating that the caller gates the plan itself.
- After round 2, remaining items become Ask-rule questions or agent decisions.
- Write `<run dir>/plan-gate.md` at the end of step 3 on both exits: a pass, or round 2 exhausted.
- It lists the adjudication and any remaining items as Ask-rule questions or agent decisions.
- `plan-gate.md` records either exit, and run-plan skips its own gate on both.

### Step 4, build

Invoke `run-plan` on the plan, in the run's worktree. Pass the ledger header notes `Plan gate passed by caller: <run dir>/plan-gate.md` and
`Keep workspace`. The skill writes no ledger itself. At run-plan's Finish, decline its push and PR. Step 9 publishes.

- `run-plan` asks the operator nothing. A decision with a key class becomes `Ruling: [<key_class>] <what you decided> — <why> — <what it costs if wrong>`.
- Tell `run-plan` that each such `<why>` names the rejected option.
- Its stop conditions still stop the run.
- After step 4, read the ledger at the workspace path `sdd-workspace` prints, and record that path in the run state.
- Remove the workspace after step 10, or when the operator ends the run.

### Step 5, conformance

Dispatch `qa-conformance` with `Agent`, by the [agents rule](#running-without-agents-or-workflows). Dispatch `temporal-code-reviewer` too when the diff touches Temporal code
and the external skill `temporal:temporal-developer` is available. When the diff touches Temporal code and the skill is not available, the run
asks the operator before the gate whether to proceed without the Temporal review or stop. It asks once per run and records the answer in `run-state.md` field `temporal_review:`, one of `proceed` or `stop`; blank means not asked.
Later step 5 rounds read `temporal_review:` and do not ask again. A `stop` answer ends the run with a `BLOCKED` head that names `temporal_review` as the reason. A diff with no Temporal code needs no note.
Temporal code is a file that imports a Temporal SDK package, or a module a worker registers as activities.
The diff counts when it adds, changes or deletes such code, at `base:` or at HEAD.

Each dispatch prompt carries the worktree path, the rule set, the run's `base:` commit, and the operator's overrides
with their reasons. The `qa-conformance` prompt also carries the breakdown, so `out-of-scope` can name the owning row.

- `qa-conformance` returns `{"rows": [...]}`: one row per rule with `anchor`, `rule`, `code`, `test`, `verdict` and `reason`. Save it as `conformance-r<n>.json`.
- `code-only` and `missing` block. `env-only` rows go to Known gaps.
- The other verdicts are `covered`, `baseline`, `out-of-scope` and `overridden`.
- `temporal-code-reviewer` returns `{"findings": [...]}` with `side`, `file`, `line`, `rule`, `defect`, `fix` and `severity`. Save it as `temporal-r<n>.json`. `blocking` findings block, and `minor` findings go to Known gaps.
- When adjudicating, drop each finding on a rule the operator overrode.

**Signed page is wrong.** The code at `base:` can contradict a signed page. That reverses a signed fact, so Ask-rule
trigger 3 sends it to the operator. When the operator confirms the page is wrong:

- The run builds what the operator decided and marks the rule `overridden`.
- The head and the PR body name the deviation.
- Write one row into the set's `decisions.md` § Agent decisions, flagged for the next `tl-design` revision of the page.
- Never edit the signed page. `G-design` stays signed.

### Step 6, fix loop

An implementer fixes each blocking item, test first. Step 5 reruns on `base:`..HEAD, never
on a fix-only range.

- Blocking items are blocking rows, blocking Temporal findings, each failing command, and each vetoed decision.
- A failing command stays a blocking item when a `BLOCKED` head hides the `FAIL`.
- Implementers commit under the workspace `CLAUDE.md` identity and branch when present, else git's own config and `<ticket>-<row slug>`.
- A pass opens on the first entry to step 6, after a veto, or after an answer that needs a code change.
- Opening a pass sets `pass_start:` to the round about to run. Each pass has at most 3 rounds, counted from `pass_start:`.
- `round:` starts at 1 with the first step 5 run. The first pass opens with `pass_start:` at 2.
- A round is one set of fix commits plus a rerun of step 5 and every command that failed. `round:` increments when that rerun starts.
- `round:` keeps counting across passes, so `conformance-r<n>.json` and `temporal-r<n>.json` never collide.
- Each fix decision with a key class goes into `<run dir>/fixes.md` as a `Decision: [<key_class>] …` line.
- When the pass's rounds are spent with open blocking items, the run stops before the gate. It lists what is open and waits for the operator.

### Step 7, knowledge refresh

Apply the workspace `CLAUDE.md` rule "Finishing a plan means refreshing the repos it touched" when present; without it, skip this step and note that in `run-state.md` field `skips:`. Correct the pages the change moved in the repo's own `_knowledge/` bundle inside the worktree, append a `**Refresh**` line per page to its `log.md`, and run the lint that rule names on that bundle. The
edits go on the same branch, so the pull request carries them.

### Step 8, gate

Write `head.md` from `templates/head.md`. Line 1 is `READY|FAIL|BLOCKED <row> r<n>`. `FAIL` means a test or check
exits non-zero. `BLOCKED` means a question is open. When a head is both `FAIL` and `BLOCKED`, it reads `BLOCKED`; the answer comes first.

- `## Summary` holds at most 5 bullets.
- `## Conformance` lists blocking rows first.
- `## Decided for veto` lists every agent decision of the run with a key class.
  Each takes one line that names the choice and the rejected option.
  The sources are `plan-gate.md`, `fixes.md` and the `Ruling: [<key_class>]` lines of the ledger.
  A `plan-gate.md` or `fixes.md` decision line reads `Decision: [<key_class>] <choice> — rejected: <option> — <why>`.
  For a ledger `Ruling: [<key_class>]` line, the head takes the rejected option from its `<why>`.
- `## Known gaps` lists `env-only` rows and `minor` Temporal findings. It also lists the skip notes and the Temporal review answer; it reads them from the `run-state.md` fields `skips:` and `temporal_review:`. It lists the ledger's `minor (deferred)` and `pre-existing:` lines.
- `## Test evidence` lists each command run after the last commit and its result line.
- A step 4 ruling that meets an Ask-rule trigger blocks the gate until the operator answers it. The head reads `BLOCKED`.
- When the operator answers, an answer that needs a code change becomes a blocking item, and the run returns to step 6.
  Any other answer is recorded, and the skill renders the head again.
- A `FAIL` head returns the run to step 6, with each failing command as a blocking item. It continues the current pass.
- The operator approves, or vetoes items. A veto becomes a fix, and the run returns to step 6.

### Step 9, publish

Publish runs only on an approved `READY` head. A `FAIL` or `BLOCKED` head never publishes.
The approval of the `READY` head covers the push and the PR. The ticket comment needs its own approval of the shown output. The acts run in order:

1. Push the branch with `git push -u <remote> <branch>`, with `<remote>` from the workspace `CLAUDE.md` when present, else `origin`.
2. Open the pull request with the title and body from the head.
3. Post the ticket comment with the `tracker.comment` command, `{target}` set to the ticket key and `{body_file}` to the head's `## Ticket comment` text in a file, as follows. Run the command once without `tracker.confirm_flag` and show the output. Then stop and wait for the operator to approve that output. Only then run it with the flag.
   When `tracker.confirm_flag` is unset, first show the `{body_file}` text and the full command, then run it once after the operator approves. When `tracker.comment` is unset, report the skip; the run still pushes and opens the PR.

On resume, skip opening the PR when `pr:` is set, and skip the comment when `comment:` is set.
The skill never changes the ticket status. Record the PR URL in `pr:` and the comment id in `comment:`. Later runs read
`pr:` to find the PR, then look up its merged state for the Depends on check.

### Step 10, retro

As in `tl-design` step 14: ask the operator what went wrong and write `<run dir>/retro.md`.
Write each proposed edit into `retro.md` as text. Apply an edit only when its target file sits in a git checkout of `tl-relay` and the operator approves.

## Ask rule

The run uses the `tl-design` Ask rule unchanged, at steps 3, 5, 6 and 8. Step 5 asks the signed-page-is-wrong question, and the Temporal review question once per run.
Step 4 asks nothing and records rulings instead.
In this phase the triggers most often fire when the code at `base:` contradicts a signed page.
Such a contradiction reverses a signed fact, so trigger 3 applies. Questions go through `AskUserQuestion` in the language
`operator_language` names, `en` when it is unset. Ids and code terms
stay unchanged. Questions go out at most 4 per round.

## Running without agents or Workflows

The `agents` value sets how `qa-conformance` and `temporal-code-reviewer` are dispatched. The session picks it: `plugin` when it lists `tl-relay:qa-conformance`, `bare` when it lists `qa-conformance`, else `none`.

- `plugin`: dispatch `tl-relay:<name>`. `bare`: dispatch `<name>`.
- `none`, with a subagent tool: dispatch a general subagent on the agent's model. Its prompt names the bound skill to load and carries the role text.
  Carry each agent's role text in the prompt, verbatim.
  `qa-conformance` runs on `opus` and binds `lens-qa-conformance`. Its role text:

  > You check the build against the row's rule set, using the bound lens. You return one row per rule with its code, its test and its verdict.
  >
  > Never edit code or pages.

  `temporal-code-reviewer` runs on `opus` and binds `temporal:temporal-developer`. Its role text:

  > You review the Temporal code in the diff against the rule set the prompt names, using the bound skill. The rules cover determinism, activity options, retries, idempotency and versioning. Read the changed files and the code they call. Read the base commit the prompt names with `git show <base>:<path>` or `git diff <base>..HEAD`. Never check out another commit.
  >
  > Return an object `{"findings": [...]}`. Each finding has `side`, `file`, `line`, `rule`, `defect`, `fix` and `severity`. The `side` is `head`, or `base` when the code that carried the rule no longer exists at HEAD. The `file` is the path inside the reviewed repository on that side. The `line` is the line number on that side. The `rule` is the rule the code breaks. The `defect` is what the code does wrong. The `fix` is the change that resolves it. The `severity` is `blocking` or `minor`. Mark a finding `blocking` when the code breaks a rule and the run can fail, replay wrongly or repeat a side effect. Mark every other finding `minor`.
  >
  > Never install tools, start servers or run workflows.
  >
  > Never edit code or pages.
- No subagent tool: the session plays each role itself, loading the bound skill.
