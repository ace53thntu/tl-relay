Read this when a run-plan task review opens the fix loop. Open it again before every round.

| The loop opens on | Notes |
|---|---|
| A `scope` finding | Any severity |
| A Critical or Important finding | Unless flagged `pre-existing` |
| A "Cannot verify from diff" item | Once you confirm it as a real gap |

## Cap

A task gets at most 3 review rounds: review round 1, then up to 2 fix rounds, each closed by a `review-change` round.
`review-change` sets the same limit.

| Round | Fixer |
|---|---|
| Fix round 1 | The original Sonnet implementer, resumed with its context intact. It gets the open findings verbatim. |
| Fix round 2, default | The same implementer, resumed again |
| Fix round 2, escalated | A fresh implementer on `model: opus`, overriding the template's model. This applies when the review after fix round 1 marks any finding from fix round 1's fix message NOT ADDRESSED. |
| Any round, no way to message the live subagent | A fresh implementer with the brief path, the report-file path and the findings. The report file serves as its persistent memory. |

The escalation follows the escalation rule in `route-subagents`: Sonnet has failed the same task twice, so the task moves up.

## Procedure

1. **Adjudicate.** Weigh every finding, every round. Push back on a wrong one with your reasoning, and log the decision.
2. **Divert.** Three kinds of finding skip the loop entirely:
   - **Minor, unless it is `scope`.** Log it on discovery as `Task <N>: minor (deferred): <one-liner>`. Later, the final whole-branch review triages that list before merge. Nobody reads an un-triaged roll-up, which makes it a silent discard.
   - **`plan-mandated`, or in conflict with the plan text.** You rule; the spec outranks the plan text. The ruling enters the ledger before any action.
   - **`pre-existing`.** It keeps its severity and never blocks, Minor or not. Record it once, per SKILL.md step 5, in the round that first reports it. It gets no `minor (deferred)` line and appears in no fix message.
3. **Send the fix message.** Everything left goes in it, plus the instance rule: fix every instance of the same pattern within the files the task touches. Outside those files, the fixer lists instances in its report and leaves them unfixed.
4. **Name tests.** The message names each covering test file. For a one-line fix those files are enough.
5. **For an escalated fixer, add three things:** the brief path, the report-file path and the open findings.
6. **Frame the hand-off.** Tell the escalated fixer the task is its own now, after two failed attempts. Point it at the report file for what the earlier implementer tried.
7. **Collect the fix.** Expect the fix report in the same report file, appended once the covering tests have run again. Its reply follows the short contract.
8. **Check evidence.** The fix report must show the covering tests, the command and its output. Review waits until it does.
9. **Package.** Run `bash scripts/review-package -C <worktree> PLAN_FILE FIX_BASE HEAD` by absolute path. `FIX_BASE` is the head the previous round saw.
10. **Review.** Call `review-change` with the inputs from its Inputs section. Pass `FIX_BASE` as range base; round 1's base stays the task-start `BASE`.
11. **Sort the round's output.**

    | Reported | Goes to |
    |---|---|
    | New Critical or Important breakage in the fix diff | The open list |
    | A new `scope` finding, at any severity | The open list |
    | An observation outside the task's scope | The ledger, as a deferred minor |
    | A `pre-existing` finding | The pre-existing route in step 2 |

    None of these lengthen the loop.
12. **Log the round.** X counts the earlier findings, `pre-existing` aside, that `review-change` marks ADDRESSED. Y counts the findings from step 3's fix message that it marks NOT ADDRESSED, plus the findings step 11 sends to the open list. The one-liners name each of them, with `(new)` on those first raised this round.

## Rules

- A plan mandate never justifies dismissing a finding.
- A fix that contradicts the plan waits for its recorded ruling.
- Your session fixes nothing itself. Its context serves coordination, and your own fix would bypass review.
- The cap: the review after fix round 2 still shows an open Critical, Important or `scope` finding, `pre-existing` aside.
- At the cap you stop the whole plan. You park nothing and start no next task.
- After the cap line, report the open findings and the task's `pre-existing:` lines to the operator. Then wait.

## Ledger lines

```
Task <N>: minor (deferred): <one-liner>
# after each fix round R:
Task <N>: fix round <R>/2 (<X> addressed, <Y> open — <finding one-liners>; commits <a7>..<b7>)
# when the cap is reached:
Task <N>: stopped at the cap — <finding one-liners>
```
