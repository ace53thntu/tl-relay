---
name: verify-done
description: Use when you are about to claim work is complete, fixed or passing, and before a commit or pull request. Run the verification commands and confirm the output supports the claim first; evidence comes before the claim.
---

# Verify before you call it done

You run the check and read the result before you say anything positive about the work. Evidence comes first, every time.

Skipping the letter of this rule breaks its spirit. A claim worded differently still needs the evidence.

## The rule

```
NO CLAIM OF DONE WITHOUT VERIFICATION OUTPUT FROM THIS MESSAGE
```

A passing result counts only when the verification command ran in the current message. Output from an earlier message does not support the claim.

Name the success criteria before the work starts, as the "Verifiable success criteria" section of the project `CLAUDE.md` requires where it exists. Then check the work against each criterion, one by one. A general feeling of done does not count.

## When it applies

Run the gate before each of these:

- Any success or completion claim, in any wording. That covers exact phrases, paraphrases and synonyms.
- Any implication of success, and any message that suggests the work is complete or correct.
- Any expression of satisfaction.
- Any positive statement about the state of the work.
- A commit, a pull request, or marking a task complete.
- Moving to the next task.
- Delegating to an agent.

## Gate

Run these steps before any status claim or any expression of satisfaction:

1. IDENTIFY the command that proves the claim.
2. RUN the full command, fresh and complete.
3. READ the whole output. Check the exit code. Count the failures.
4. VERIFY that the output confirms the claim.
   - If it does not, report the actual status with the evidence.
   - If it does, state the claim together with the evidence.
5. Only then make the claim.

A claim made after you skipped a gate step is a lie. It is not verification.

## What each claim needs

| Claim | Evidence required | Not enough |
|---|---|---|
| Tests pass | Test command output showing 0 failures | An earlier run, or "should pass" |
| Linter clean | Linter output showing 0 errors | A partial check, or extrapolation |
| Build succeeds | Build command exits 0 | A passing linter, or logs that look fine |
| Bug fixed | The original symptom tested and passing | Changed code and an assumed fix |
| Regression test works | A verified red-green cycle | One passing run |
| Agent completed | A VCS diff showing the changes | The agent's own "success" report |
| Requirements met | A line-by-line checklist | Passing tests |

## Patterns

Tests:

- ✅ Run the test command, see the pass count (for example 34/34), then say all tests pass.
- ❌ "Should pass now." "Looks correct."

Regression tests (red-green):

- ✅ Write the test and run it: it passes. Revert the fix and run it: it must fail. Restore the fix and run it: it passes.
- ❌ "I wrote a regression test", with no red-green check.

Build:

- ✅ Run the build, see exit 0, then say the build passes.
- ❌ "The linter passed." A linter does not check compilation.

Requirements:

- ✅ Re-read the plan, build a checklist, verify each item, then report the gaps or the completion.
- ❌ "Tests pass, phase complete."

Agent delegation:

- ✅ When an agent reports success, check the VCS diff, verify the changes, and report the actual state.
- ❌ Trusting the agent's report.

## Stop signals

Stop and run the gate when any of these happens:

- You write "should", "probably" or "seems to".
- You express satisfaction before verifying: "Great!", "Perfect!", "Done!" and similar.
- You are about to commit, push or open a pull request without verification.
- You trust an agent's success report.
- You rely on a partial check.
- You think "just this once".
- You are tired and want the work over.
- Your wording implies success and no verification has run. This is the catch-all.

## Excuses and answers

| Excuse | Answer |
|---|---|
| "Should work now" | Run the verification command. |
| "I'm confident" | Feeling sure does not replace the evidence the claim needs. Collect that evidence. |
| "Just this once" | The rule has no exceptions. |
| "The linter passed" | A linter does not check compilation. Run the check that proves the claim. |
| "The agent said success" | Check the result yourself. |
| "I'm tired" | Tiredness does not excuse skipping the check. Run it before you claim anything. |
| "A partial check is enough" | A partial check gives you no proof about the claim. |
| "My words differ, so the rule does not apply" | The rule targets the intent behind a claim, whatever its wording. |

## Definition of Done for a task

[core.md](core.md) is the Definition of Done for every task. The session runs each check itself.
