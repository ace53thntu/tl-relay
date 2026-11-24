Read this when run-plan setup is done and Task 1 is not yet dispatched. It runs once.

1. Make one pass over the plan. Log each check in writing as you make it.
2. Hunt for two conflict types:
   - tasks contradicting each other or the plan's Global Constraints
   - a plan mandate the review rubric would call a defect, e.g. a test asserting nothing
3. A block of logic duplicated verbatim also counts under the second type.
4. Fill the conflict table, using the row types below. Your output is this table; a verdict alone does not count.
5. Copy the table into the ledger.
6. Before execution starts, put a ruling in the ledger beside each row with a finding. Base it on the plan passage that requires the flagged behaviour.
7. Dispatch Task 1.

| Row type | One row per | Columns |
|---|---|---|
| Pair | Two tasks sharing a file or an interface | Task A · Task B · A's output vs B's input · Finding |
| Self-consistency | Single task | Its tests vs its code · Files it creates vs files it later touches · Finding |

- No rows behind a "scan is clean" claim means no scan took place.
- A clean scan needs no comment. Proceed.
- In conflict rulings the spec binds; the plan only argues from it.
- Outside the design-doc lane, you leave conflicts that only implementation reveals to the review loop.
