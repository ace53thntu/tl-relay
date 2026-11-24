Read this when a run-plan implementer reports DONE_WITH_CONCERNS, NEEDS_CONTEXT or BLOCKED.

1. Find the status in the reply.
2. NEEDS_CONTEXT: give the implementer the missing context and re-dispatch.
3. DONE_WITH_CONCERNS: read every concern before anything else, then sort each one.

   | Concern | Do |
   |---|---|
   | Correctness or scope | Settle it first, in every lane: resume the implementer, or rule on it in the ledger. Then continue as for an observation. |
   | Observation only, such as "this file is getting large" | Note it. Then send the task to review, or to completion in the design-doc lane. |

4. BLOCKED: diagnose the blocker and match it to one row.

   | Blocker | Response |
   |---|---|
   | 1. Missing context | Add context; re-dispatch on the same model |
   | 2. Needs more reasoning | Re-dispatch on a more capable model |
   | 3. Task too large | Split it into smaller pieces |
   | 4. The plan is wrong | Rule on the correction, write the ruling to the ledger, re-dispatch carrying it |

- An escalation always gets an answer.
- A stuck implementer needs a changed input. An unchanged retry on the same model is not allowed.
