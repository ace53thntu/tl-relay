---
name: review-change
description: Use after finishing a task or a major feature, and before a merge, to check the work against its requirements
---

# Review change

This skill wraps the built-in `/code-review`. It reviews no code itself. A fresh Opus subagent runs `/code-review` on one commit range, and the main loop adjudicates what comes back.

When `/code-review` is unavailable, as in Cursor or Codex, the reviewer subagent reads the diff file and reviews the range itself against the same finding rules and return contract. With no subagent tool, the main session does that review.

This skill is the authority for review rounds and findings. `route-subagents` assigns the reviewer its model and effort.

Review early and often.

## When to run

Work in the design-doc lane of `route-subagents` skips code review. There, the required rows below do not apply.

| Moment | Required? | Why |
|--------|-----------|-----|
| Before a refactor | Optional | It sets a baseline. |
| After a complex bug fix | Optional | A second look catches what the fix disturbed. |
| When you are stuck | Optional | A fresh view breaks the loop. |
| After each `run-plan` task | Required | The reviewer checks each task before the next builds on it. |
| After a major feature | Required | The reviewer checks the whole feature against its requirements. |
| Before a merge to main | Required | Nothing reaches main unreviewed. |

## Inputs

Build the reviewer's context from these inputs only. Never pass the session history. Never pass the implementer's transcript.

| Input | Value | Source |
|-------|-------|--------|
| Worktree path | The checkout under review. The reviewer names it in every git command. | The session. |
| Range | A base SHA and a head SHA. | Round 1: round 1 base. Later rounds: the previous round's HEAD. Head: this round's HEAD. |
| Round 1 base | `git -C <worktree path> merge-base HEAD "$(git -C <worktree path> symbolic-ref --short refs/remotes/origin/HEAD)"`. If origin/HEAD is unset, run `git -C <worktree path> remote set-head origin --auto` once, then rerun. Under `run-plan`, per task: the commit the task started from. | Git. |
| Later rounds | Base is the previous round's HEAD. Round 1's base travels along every round. | The round record. |
| Diff file | The diff of the range, for example the output of `scripts/review-package` from `run-plan`. | `run-plan`, or a diff you write. |
| Task brief | The task text, plus its report file when one exists. | The plan. |
| Success criteria | What "done" is checked against. | The plan or spec. |
| Binding constraints | The plan's Global Constraints or the spec requirements, copied verbatim. | The plan or spec. |
| Findings already reported | Round 1: none. Round N: every finding from rounds 1 to N-1. | The round record. |

The reviewer judges `pre-existing` against round 1's base. A defect added in an earlier round is therefore never `pre-existing`.

## Procedure

1. Record the head SHA this round reviews. It becomes the next round's range base.
2. Dispatch a fresh `Agent` with `model: opus` and `effort: high`. Its prompt holds:
   - every input from the table above;
   - an instruction to report a change the task did not ask for as a finding in category `scope`;
   - an instruction to report a task requirement with no matching change as a finding in category `scope`;
   - the full text of [core.md](core.md) as the finding rules, followed by the severity map below.
3. The subagent invokes the Skill tool with skill `code-review` and args `high <worktree path> range <base>..<head>`. It also reads the diff file.
   - When `/code-review` is unavailable, the subagent skips the invocation and reviews the diff file itself against [core.md](core.md) and the return contract. With no subagent tool, the main session does this.
   - If `/code-review` has not yet notified completion, the subagent waits. The review runs as a forked background task.
   - If the review returned its finding cap, the subagent adds "findings may be capped" to Cannot verify.
   - The subagent never edits the worktree.
4. The subagent returns the contract below.
5. The main loop adjudicates every round.
6. The review runs at most three rounds.

Severity map: Critical and Important are blocking. Minor is minor. A finding may also be pre-existing; a pre-existing one keeps that severity and does not block. [core.md](core.md) defines blocking, minor and `pre-existing`.

## Return contract

| Field | Required content |
|-------|------------------|
| Verdict | APPROVED or CHANGES REQUESTED. Findings that are only `pre-existing` never yield CHANGES REQUESTED. |
| New findings | New ones only, grouped by category (`scope` included). Each names a severity (Critical, Important or Minor) and a `file:line`. |
| Flags | `plan-mandated` when the plan text requires the flagged behavior. `pre-existing` per [core.md](core.md), judged against round 1's base. |
| Cannot verify from diff | Requirements that sit in unchanged code or span several tasks. |
| Earlier findings | Each one marked ADDRESSED or NOT ADDRESSED, with evidence. |

## Adjudication and cap

| Finding | Main loop does |
|---------|----------------|
| Critical or Important, not `pre-existing` | Gets it fixed before proceeding. |
| Minor | Notes it. |
| `pre-existing` | Lists it in the report to the operator. |
| Wrong | Answers with the code or test that disproves it, then the technical reason. Asks the reviewer to clarify where the finding is unclear. |
| Any fix | Covers every instance of the same pattern in the files the change touches. |
| Same pattern outside those files | Reports it. Does not fix it. |
| Open findings after round 3 | Stops, reports them to the operator, and waits. |

## Rationalizations

| Excuse | Fact |
|--------|------|
| "Why not read the diff inline?" | Coordination needs your context, and an inline review spends it on diff. Dispatch the reviewer; take back findings only. |
| "Why not give the reviewer my session history?" | History anchors the reviewer on your reasoning, not on the work product. Hand over the diff, task, criteria and findings. |
| "Why not run one more round to converge?" | Round 3 ends the review with findings still open. Report them to the operator. |

## Never

| Don't | Do instead |
|-------|------------|
| Treat a small-looking change as exempt. | Run the review anyway. |
| Skip review outside the design-doc lane of `route-subagents`. | Review every task, feature and merge outside that lane. |
| Ignore a Critical finding. | Get it fixed, unless it is `pre-existing`; then list it. |
| An Important finding, not `pre-existing`, is still open as you move on. | Get it fixed first. |
| Argue against valid technical feedback. | Accept it, then act on it by its row in the findings table. |
| Let the reviewer edit the worktree. | Keep the reviewer read-only. |
