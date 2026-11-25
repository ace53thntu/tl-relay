---
name: write-skill
description: Use when an agent receives skill-writing work for `tl-relay/skills`, whether authoring a fresh SKILL.md from a request that only describes its job or revising one that exists. Applies in place of brainstorm for this work. Also use when the result must clear the overlap test and the trigger suite.
---

# Write skill

First message to the user: "write-skill: working on the <name> skill."

This procedure covers `tl-relay/skills/` only. For a skill directory elsewhere, stop and tell the user.

Follow the wording of each step. Bending a step's wording breaks its intent too.

## Workflow

1. Check the need: reusable, not obvious, not enforceable by a script or validator. If the request looks unfit, never decline alone. Tell the operator why and wait: continue to step 2, sharpen the request, or drop. On drop, stop. With no operator, report the request, why it looks unfit and the choices to the caller, then stop.
2. Classify the skill: discipline, technique, mental model or reference. Only a discipline skill takes the steps marked for discipline.
3. Run the baseline: [baseline.md](baseline.md), and see "Excuses". Write no skill text before it shows the failure. An edit counts.
4. Name the failure class, pick the guidance form, and sample the wording: [baseline.md](baseline.md).
5. Have the blind author write the trigger and held-out prompts: [trigger-prompts.md](trigger-prompts.md).
6. Draft SKILL.md and its companion files: [body-rules.md](body-rules.md).
7. Run the with-skill pass by path: [baseline.md](baseline.md).
8. Tune the description with the `tune` command: [trigger-prompts.md](trigger-prompts.md). A tuning FAIL stops nothing.
9. Commit the work, then run the `score` command and gates 1, 3 and 4. Push only after `score` exits 0 and those gates pass: [gates.md](gates.md).
10. Record each before/after pair (see "Evidence").
11. After merge, update the main checkout with `git -C <main> pull --ff-only`. Then install with `ln -sfn <main>/skills/<name> ~/.claude/skills/<name>`, or `<main>/maintainer/skills/<name>` when the skill lives under `maintainer/`. `readlink` on the link must print that source path, and `test -e ~/.claude/skills/<name>` must exit zero. Then follow "Push gate install" in [gates.md](gates.md). Then run `bash <main>/skills/tests/run-triggers.sh`. Every prompt must pick its expected skill. Rerun a FAIL once, because one result is noisy. If it fails again, report it to the operator or caller. On `ERROR` or exit 3, rerun once, then report the output and exit code to the operator.

Finish and verify one skill before starting another.

## Evidence

- The run ledger holds each baseline choice, its verbatim excuses, the failure class, the guidance form and each with-skill result.
- The PR description carries every before/after pair. The ledger goes after merge, so the PR keeps the record.
- The PR description names no ledger path, local path or private source.

## Excuses

- "The baseline is a formality." An obvious rule still fails under pressure.
- "I can adapt my earlier draft." Delete text written before its baseline.
- "Tune on the held-out prompt too." A tuned-on prompt scores nothing.
- "This edit needs no before/after." Every changed rule gets a pair.
- "I can rerun the failed fingerprint." A FAIL on a fingerprint stands. Push nothing, report to the operator or caller, and stop.
- "The baseline passed, so I decline." Report the evidence. The operator decides.

Restart the step if you wrote skill text before a subagent ran, or read held-out prompts while tuning.
