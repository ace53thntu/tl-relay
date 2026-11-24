Read this when run-plan setup finds a ledger at `<workspace>/progress.md`.

1. Check ownership on the first line. If it names another plan file, the ledger belongs to that plan. Leave it and start your own fresh.
3. If the first line names your plan file, find each task's latest status line. Skip the finding records listed below.
   On resume, add each caller note the ledger header lacks, inserting it in the header and never at the end. Add the gate note only when the ledger records no plan gate of its own. That means the header lacks `Own plan gate: ran`. A note already present keeps its value, except `Keep workspace`. Set `Keep workspace` as the current invocation passes it: add it when passed, remove it when not.
4. Act on that line per task:

   | Task's latest status line | Meaning | Do |
   |---|---|---|
   | `Task <N>: complete …` | DONE | Never dispatch it again |
   | `Task <N>: fix round <R>/2 …` | Inside the fix loop; the review closing round <R> has run | Y above 0 after round 1: start fix round 2. Y above 0 after round 2: write the cap line, report to the operator and wait. Y at 0: write the completion line |
   | `Task <N>: stopped at the cap …` | Waiting on the operator's word | Never re-dispatch it; resume nothing |
   | None, though the task has other lines | Review round 1 done at most | Resume at that review |

5. With no task waiting at the cap, pick up at the first task that lacks a `Task <N>: complete` line.

- These are finding records. They never change a task's position:

  ```
  Task <N>: pre-existing: …
  Final: pre-existing: …
  minor (deferred)
  Ruling:
  ```

- Any `Final: pre-existing:` line proves the final review ran. A second fix wave never starts.
- The Finish report needs every `pre-existing:` line, so keep them all.
- One line per finding: skip writing one when that task or the final review already lists it.
