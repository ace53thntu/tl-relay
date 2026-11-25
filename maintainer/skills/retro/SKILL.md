---
name: retro
description: Use when the nightly 22:00 job fires, when the operator asks to look back at the day's transcripts for choices they had to make by hand, or to listen to other sessions while they work. Also use when lesson files in the home lessons folder or retro feedback memories need adding, merging or pruning.
---

# Retro

`<home>` is `$TL_RELAY_HOME`, else `$AI_SDLC_HOME`, else `~/.ai-sdlc` when only `~/.ai-sdlc` exists, else `~/.tl-relay`. An empty `TL_RELAY_HOME` counts as unset. Pass it as an absolute path. Run scripts as `/usr/bin/python3 <this folder>/scripts/<script>.py … --home <home>`.

## Cycle

`/retro` runs these steps once, and `/retro listen` every 10 minutes through `Monitor`. Before the first cycle, run `ledger.py new-owner --kind sweep` for `/retro` or `--kind listen` for `/retro listen`. Use the printed owner for every lock and unlock of that run.

1. `ledger.py lock --owner <owner>`. On exit 4, stop and write nothing. If a later step fails, unlock before you stop.
2. `ledger.py sync-vetoes`, then `ledger.py vetoed`.
3. `digest.py run`, with `--config-dir` only when the operator names one. Read `<home>/retro/digest.next.jsonl` in pages.
4. Classify and write per [Classes](#classes).
5. `digest.py commit`.
6. `ledger.py count --date <local date> --important N --routine N --avoidable N --corrections N --repeats N --lessons N`, once per local date of the records in `<home>/retro/digest.jsonl`. `--lessons` counts the lessons written, never memories, on the local date of the record that led to each one.
7. Write the [report](#report), then `ledger.py unlock --owner <owner>`.

## Classes

A decision is **important** when it:

1. changes what another team builds or sees, such as a cross-team contract, event, shared schema or dependency row.
2. changes a release timeline or a man-day figure.
3. reverses an earlier operator answer or a fact on a signed page.
4. has no clear recommendation.

Count it. Never write a lesson that removes the question.

Any other decision is **routine**, and **avoidable** when the operator picked the recommended option or the answer follows from earlier answers or the code. With `recommended` null, use the pick the excerpt states.

| Record | Write |
|---|---|
| Routine and avoidable | `ledger.py sight --key <owner>:<slug> --source <record id>`. Reuse a key from `<home>/retro/candidates.jsonl` that names the same situation. Write a lesson only when it prints 2 or more. |
| Correction or stated rule | A lesson at once |
| `repeat` | A lesson for the skill it names, else a memory |
| Text matching a `vetoed` line | Nothing |

**Owner:** judge it from `skills` and the excerpt. The latest skill is only a candidate. No tl-relay owner means a memory, with `memory` as the `sight` key prefix.

A `repeat` whose text the operator did not type, such as a harness notice, writes nothing. A finding that contradicts `CLAUDE.md` or an existing memory writes nothing and becomes an open question.

## Lessons

Write each lesson by [lessons.md](lessons.md).

## Memories

Write each memory by [memories.md](memories.md).

## Report

Add to `<home>/retro/reports/YYYY-MM-DD.md`, never replace it, in `operator_language`. Read it from the home file, which is `<home>/tl-relay.yaml`, or `<home>/ai-sdlc.yaml` when it is the only one. Default to English. List each lesson and memory written, drop, skipped veto, open question and the counts.

## Limits

- Write only under `<home>/lessons/`, `<home>/retro/` and the memory folders.
- Put every temporary file under `<home>/retro/scratch/<owner>/`. `ledger.py unlock` deletes that folder.
- Never edit a `SKILL.md`, commit or push, even when asked.
- Never copy a secret into any file.
- Ask nothing in a headless run. Open questions go in the report.
