Read this when `review-change` returns "Cannot verify from diff" items for a run-plan task.

1. Read each item as a requirement the diff cannot show: it sits in unchanged code, or it spans tasks.
2. Check it yourself against the plan and the other tasks.
3. Confirmed gap: record it as a `scope` finding. The fix loop takes it with the other findings.
4. Mark the task complete only after you settle every item.

- The rest of the review proceeds; these items hold nothing else up.
- The reviewer saw only the diff. You hold the plan and the cross-task context, so the call is yours.
