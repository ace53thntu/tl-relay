# Baseline, failure classes and with-skill pass

## Contents

- Baseline
- Passing baseline
- Failure classes
- Sampling the wording
- With-skill pass
- Grading an artifact
- Changing an existing skill

## Baseline

The agent writes no skill text before the baseline shows the failure. The agent deletes any text written ahead of its baseline and never adapts it later.

1. List the specifics the requester wants encoded: the steps, their order, the names and the checks. Generic good behaviour is no specific.
2. Write 2 or 3 pressure scenarios. Each exercises at least one listed specific and tempts the exact failure the guidance targets. For a discipline skill, stack pressures: a deadline, sunk effort, an authority's nudge.
3. For an original skill, give each scenario to one fresh subagent with no skill text.
   For an edit, the agent copies the current skill directory to a fresh `<snapshot-dir>` outside the checkout, once per run:
   `mkdir -p <snapshot-dir>/skills/<name>`, `cp -R <worktree>/skills/<name>/. <snapshot-dir>/skills/<name>/` (for a skill under `maintainer/skills/<name>`, copy from there), `ln -sfn <worktree>/maintainer/sdlc.py <snapshot-dir>/sdlc.py`.
   A sharpen rerun reuses that copy. Each fresh subagent gets its scenario plus "Read `<snapshot-dir>/skills/<name>/SKILL.md` and follow it."
4. Log each subagent's choice and its excuses verbatim in the run ledger. These outputs are the before side of every pair.
5. Subagents inherit the session's global instructions, so a pass may come from them. Note that risk in the ledger.
6. If the baseline fails, continue to "Failure classes". If it passes, follow "Passing baseline" below.

Run comparisons as subagents following this procedure. Do not script them.
Every subagent this file launches gets one ban: never invoke an installed copy of `<name>`.

## Passing baseline

The agent never declines alone. It reports to the operator what each scenario tested and what each subagent did. The report carries the Baseline step 5 note on inherited instructions.

The agent offers two choices and waits for the answer:

- Sharpen: the operator supplies the specifics. Add them to the Baseline step 1 list and rerun Baseline steps 2 to 6.
  The earlier passing runs leave the before side. The ledger keeps them, marked superseded.
- Drop: the agent writes no skill.

No operator can answer, as in a dispatched subagent or `claude -p`? Report to the caller and stop.

## Failure classes

Name one class per scenario in the ledger, with the guidance form chosen for it.

| Failure observed | Guidance form |
|------------------|---------------|
| The agent breaks a rule when pressed | A prohibition plus an excuse table that counters each logged excuse |
| The output takes the wrong form | A recipe that lists the output's parts |
| The output omits an element | A required slot the output must fill |
| Behaviour hinges on a state | A conditional on a fact the agent can observe |

- Never soften a rule with a qualifier. Turn a real exception into a separate condition that names a fact the agent can observe.
- Never lean on a carve-out sentence to protect some output. Restructure until the rule cannot touch it.
- Never answer a wrong-form failure with a prohibition list.

## Sampling the wording

Do this for every skill, before the draft.

1. Write each candidate wording as a variant.
2. Run five or more single-shot fresh subagents per variant.
3. Run a control that lacks the wording.
4. Read every flagged hit by hand.

The sample passes when the control shows the failure and the variant runs converge on the compliant choice.
If the control does not fail, or the variants do not converge, sharpen the scenarios and rerun the sample.

## With-skill pass

With-skill runs read the skill by path. No before or with-skill run touches `~/.claude/skills`.

1. Take the before side of each pair from the baseline outputs in the ledger. For an edit, that is the snapshot run.
2. Give each scenario to a fresh subagent with "Read `<worktree>/skills/<name>/SKILL.md` and follow it."
   Compare its output with the before side.
3. Check that each with-skill subagent picks the compliant option and cites the skill as its reason. When the skill produces an artifact, grade it as "Grading an artifact" below describes.
4. When a rerun shows a new excuse, add a targeted counter to the rebuttal table. Rerun that scenario.
5. Repeat step 4 until a rerun shows no excuse the table lacks.
6. Test the skill on every model tier expected to run it.
7. Run a fresh agent on a real task, with the same path instruction. Check that it reaches the right section and reads linked files whole.

## Grading an artifact

A skill produces an artifact when its scenario's deliverable is a file, code, a document or message text. The agent grades every pair of such a skill in four parts:

1. Assertions. Before grading, the agent writes assertions from the Baseline step 1 specifics. Each states one checkable fact about the artifact, such as "the down file drops `items_quantity_idx`".
2. Scripts. The agent writes and runs a script for each assertion a script can check, such as a schema validation or a regex.
3. Grader. A fresh grader subagent gets the assertions, the script results and both outputs of every pair. It returns pass or fail with evidence per assertion. The runner never grades its own output.
4. Record. The ledger holds each assertion, each grade with its evidence and the pass count per side. The PR pair carries both counts.

A with-skill run that fails an assertion fails step 3, whatever it cites.

## Changing an existing skill

1. Take the snapshot and run its baseline before you touch the rule.
2. Change only that rule.
3. Rerun the skill's own prompts with the `tune` command in [trigger-prompts.md](trigger-prompts.md). `tune` refuses a skill with no prompt files, so the blind author writes them first. Pair one scenario for the changed rule: the snapshot run before, the changed skill after.
4. Rerun the neighbours' prompts with the `tune` command when the description changed. Skip a neighbour with no prompt files and report it to the operator or caller.
