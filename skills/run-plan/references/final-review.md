Read this when a run-plan plan has every task complete.

## Whole-branch review

In the design-doc lane there is no final review. Go straight to Finish.

1. **Range.** Compute the branch's merge base, for example `git -C <worktree> merge-base HEAD "$(git -C <worktree> symbolic-ref --short refs/remotes/origin/HEAD)"`. If origin/HEAD is unset, run `git -C <worktree> remote set-head origin --auto` once, then rerun.
2. The merge base serves twice: as the range base, and as round 1's base in every final-review round.
3. **Package.** Run `bash scripts/review-package -C <worktree> PLAN_FILE MERGE_BASE HEAD` by absolute path.
4. **Review.** Give `review-change` the printed path as the diff. Also give it the ledger's deferred-minor lines; it decides which need fixing before merge.
5. **Pre-existing.** Log each `pre-existing` finding as `Final: pre-existing: <one-liner>`. That holds for this round and for the fix-wave review. These stay out of the fix wave.
6. **Fix wave.** If any finding not flagged `pre-existing` remains, dispatch ONE fix subagent. It gets the complete findings list. With none, skip to Finish.
7. **Re-review.** After a fix wave, run exactly one more `review-change` round over the fix range.
8. For that round, run `bash scripts/review-package -C <worktree> PLAN_FILE FIX_BASE HEAD` by absolute path. `FIX_BASE` is the head the previous round saw.
9. Round 1's base stays the merge base.
10. **Residuals.** Adjudicate what the round reports, and log each decision.

| After the re-review | Do |
|---|---|
| Nothing open except `pre-existing` | Go to Finish |
| Findings still open, `pre-existing` aside | The plan stops under the fix-loop cap in references/fix-loop.md. Report them and every `pre-existing:` ledger line to the operator, then wait. |

- Dispatch one fixer for the whole list. In one observed run, a fixer per finding cost more than every task in the plan combined, because each fixer rebuilt context and re-ran suites.
- A second fix wave never runs.

## Finish

1. **Rulings.** Collect every ledger line containing `Ruling:`, before you delete anything. Preflight rulings and adjudications count alike.
2. List them in the final message under "Rulings I made". Keep the order you made them in, each with its cost if wrong. A ruling keeps its `[<key_class>]` tag.
3. **Pre-existing.** Collect every `pre-existing:` ledger line under "Pre-existing findings". Each keeps its severity; the operator decides when to fix it.
4. **Cleanup.** Run `rm -rf <workspace>` once two things hold. The final review is clean apart from `pre-existing` findings, or the design-doc lane skipped it. Its fixes are merged. When the ledger header holds `Keep workspace`, skip the delete. The caller reads the ledger there and removes the workspace.
5. After the delete, git history holds the record. With `Keep workspace`, the kept ledger holds it until the caller removes it.
6. **Push.** Push and open a PR only on the operator's word.
7. Follow any push or identity rule in the project `CLAUDE.md`; otherwise push to its own `origin`, unchanged.

- Every ruling in the ledger reaches "Rulings I made", with no exceptions.
- The operator learns of decisions made in their name through that list and nowhere else. Delete the workspace first, and those rulings become secret.
- Delete only this plan's workspace, and leave every neighbouring directory under `.tl-relay/sdd/` untouched: each one is another plan's.

## Ledger lines

Whole-branch review step 5 writes this format:

```
Final: pre-existing: <one-liner>
```
