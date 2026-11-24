---
name: debug-issue
description: Use when a bug, a failing test, or behaviour you did not expect turns up, and before you suggest any fix for it
---

# Debugging by root cause

Before any code changes, you establish why the defect happens. A patch that hides the symptom is a failed fix, not a partial win.

**Root cause first: no fix, and no fix proposal, until stage 1 is complete.**

Skipping any single step counts as skipping the process, even when the shortcut seems to honour its purpose.

## Scope

Load the skill for any behaviour that surprises you. That covers broken builds, failing tests, faults between integrated components, slow paths and production incidents.

It matters most when the last fix failed, when several fixes are already in, or when a one-line fix looks "obvious". It matters just as much when you only half understand the problem, or when someone is waiting on you.

| Tempting reason to skip | Why it does not hold |
|-------------------------|----------------------|
| A manager wants it fixed right now. | Guess-and-check takes longer than the stages, so the manager waits longer. |
| You are short of time. | A rushed fix gets redone, and the redo costs more than the investigation. |
| The bug looks simple. | It still has a cause, and on a simple bug the stages take minutes. |

## Stages

Run the stages in order. Finish each one before you start the next.

| Stage | You do | Leave the stage when |
|-------|--------|----------------------|
| 1. Investigate the cause | Read the errors, reproduce the failure, check recent changes, collect evidence | You can say WHAT fails and WHY |
| 2. Compare with working code | Find working examples, compare them with the broken code | You have listed the differences |
| 3. Test one hypothesis | State one theory, test it with the smallest change | The theory holds, or you have formed a new one |
| 4. Fix and confirm | Write a failing test, apply one fix, verify | The bug is gone and the tests pass |

### Stage 1: Investigate the cause

Before any fix attempt, tick every box. A box that names a condition applies only when that condition holds.

**Collect**

- [ ] Full error output saved: the whole stack trace and every warning, with error code, file path and line number for each frame that matters. Read the warnings too; the fix often sits in text you scrolled past.
- [ ] Trigger pinned down: you know whether it fails on every run, the exact steps are written down, and you can set it off on demand. Without that, collect more evidence; do not pick a cause by guessing.
- [ ] Change list written: environment differences between a passing and a failing setup, configuration edits, new or bumped dependencies, plus `git diff` and the recent `git log`.

**Locate**

- [ ] Hand-off log captured, when the failure crosses components (API → service → database, or CI → build → signing). Before any fix, instrument each hand-off. Record the layer's state, whether each env or config value arrived, and the data going out and coming in. Run once with all of it on; the output names the hand-off that breaks. Dig into that one component only after you have read the output.

  ```bash
  # 1. CI job: is the secret set?
  [ -n "${REGISTRY_TOKEN:-}" ] && echo "CI: REGISTRY_TOKEN SET" || echo "CI: REGISTRY_TOKEN UNSET"

  # 2. build script: did the secret arrive?
  [ -n "${REGISTRY_TOKEN:-}" ] && echo "build: REGISTRY_TOKEN SET" || echo "build: REGISTRY_TOKEN UNSET"

  # 3. publish script: which registries hold stored credentials?
  jq -r '.auths // {} | keys[]' ~/.docker/config.json   # registry names only, never the credentials

  # 4. the push: what does the registry answer?
  docker --debug push "$IMAGE_TAG"
  ```

  The output names the broken link: `secrets → CI job ✓`, `CI job → build script ✗`. Print whether a secret is present. Never print its value.

- [ ] Origin of the bad value found, when the error is deep in the call stack: a list of frames with file:line, from the throwing frame up to the frame that first produced the value. That first frame is the fix site, not the frame that threw. [`root-cause-tracing.md`](root-cause-tracing.md) holds the full method.

### Stage 2: Compare with working code

No fix until the pattern is clear.

**What to compare against**

- [ ] Working counterpart named: a file:line in this codebase where similar code does a similar job and works.
- [ ] Reference understood, when you apply a known pattern: you can walk a colleague through every line of its reference implementation. Only then apply it.

**What to write down**

- [ ] Difference list: every way the working and broken code differ, including the ones that look harmless. A difference stays on the list until evidence removes it.
- [ ] Dependency list: the assumptions the code makes, the configuration, settings and environment it reads, and the other components it calls.

### Stage 3: Test one hypothesis

Run this stage as an experiment, with one variable per run.

- [ ] Gaps declared: wherever you do not understand something, the notes say "I don't understand X". Ask for help or research further; never bluff.
- [ ] Hypothesis on paper: one sentence that names a specific cause and the evidence for it, e.g. "The cause is X; evidence Y points there."
- [ ] Experiment designed: the smallest change that could prove the hypothesis wrong, changing one thing only. Two fixes in one run hide which one mattered.
- [ ] Outcome recorded: confirmed, so move to stage 4; refuted, so revert and write a new hypothesis. Never layer a second fix over the first.

### Stage 4: Fix and confirm

The fix targets the root cause, never the symptom.

- [ ] Failing test in place before the fix, written with the `test-first` skill: the smallest reproduction, as an automated test where a framework exists, otherwise as a throwaway script.
- [ ] Diff holds one change, aimed at the root cause: no side improvements, no refactoring folded in.
- [ ] Success shown: the original symptom is gone, the new test passes and the rest of the suite is still green. Before you tell anyone it is fixed, run the `verify-done` skill.
- [ ] Fix did not hold: count the failed fixes so far and use the table below.

| Failed fixes so far | Next move |
|---------------------|-----------|
| 1 or 2 | Return to stage 1, carrying what the failed fix revealed. |
| 3 or more | Stop fixing and run the [architecture review](#architecture-review-after-three-failed-fixes). Fix number four waits until that discussion has happened. |

## Architecture review after three failed fixes

At three failed fixes, suspect the design rather than your hypotheses.

The design is the problem when:

- the change you need keeps growing towards a "massive refactoring";
- patching one place makes symptoms appear somewhere else;
- every fix surfaces more coupling or more shared state.

Questions for the review:

- Do we keep this pattern because it works, or only because it is already in place?
- Is the pattern sound in the first place?
- Which costs less from here: restructuring the architecture, or more symptom patches?

Take these questions to your human partner, and agree on an answer before writing another fix. Record the situation as a design fault, not as a wrong hypothesis.

## When no root cause exists

- **Allowed only when** the stage 1 evidence places the cause outside your code: an external service, a timing dependency, or the environment.
- **Then you** record what you checked. Add logging or monitoring so the next occurrence leaves a trace. Add handling that fits the cause: an error message, a timeout or a retry. With that done, the process is complete.

Check this verdict twice. Incomplete investigation explains 95% of "no root cause" verdicts.

## Companion techniques

Three pages in this directory carry parts of the method.

| File | Open it when |
|------|--------------|
| [`root-cause-tracing.md`](root-cause-tracing.md) | The error fires many frames below the place where the bad value entered. |
| [`defense-in-depth.md`](defense-in-depth.md) | The root cause is fixed, and each layer the data passes should now reject it. |
| [`condition-based-waiting.md`](condition-based-waiting.md) | A test sleeps for a guessed time instead of waiting for the state it needs. |

## Warning signs

Catch yourself thinking any of these, and you go back to stage 1.

| If you think | Do instead |
|--------------|------------|
| "Ship the patch; the cause can wait for the post-mortem." | Open the stage 1 checklist before writing any code. |
| "Let me tweak X and watch." | Write the hypothesis sentence, then design a one-variable test. |
| "Batch the edits; one test run at the end." | Revert to one edit per run. |
| "A manual click-through is proof enough." | Write the failing test with `test-first`. |
| "My money is on X, so I'm patching X." | Collect the evidence that names X before you touch it. |
| "No idea why, yet this could do it." | Write "I don't understand ..." and keep investigating. |
| "Our case differs from the reference, so I'll bend it." | Read the reference end to end, then apply it as written. |
| "Top issues: A, B, C, with fixes below." (no investigation yet) | Delete the fix list and start the stage 1 checklist. |
| "Here's the fix." (data flow untraced) | Trace the bad value to its origin first. |
| **"Just one more attempt."** (2 or more already failed) | Count the failed fixes and use the decision table. |
| **"Fixed that; now something else broke."** | Go back to stage 1. When every fix does this, raise it in the architecture review. |

Three or more failed fixes lead to the [architecture review](#architecture-review-after-three-failed-fixes), not back to coding.

## Signals from your human partner

These remarks from your human partner send you back to stage 1.

| Your partner says | It means |
|-------------------|----------|
| "Is that not happening?" | A claim you made was never checked against the system. |
| "Will it show us...?" | They want evidence you have not collected. |
| "Stop guessing." | Your fixes are running ahead of your understanding. |
| "Ultra-think this." | Step back from the symptoms to the fundamentals. |
| "We're stuck?" (frustrated) | The current approach is not working; change it. |

## Excuses

| Excuse | Fact |
|--------|------|
| "Too trivial to need a process." | On a simple bug the stages take minutes, and there is still a cause to find. |
| "No time; this is an emergency." | Guess-and-check burns more incident minutes than a systematic search. |
| "Quick try now, a proper look afterwards." | The first fix becomes the template for the next ones, so a bad start compounds. |
| "Tests can come once it works." | A fix without a test regresses unnoticed. Only a test that failed first proves this fix. |
| "Doing three fixes together is faster." | Two changes in one run: a pass cannot tell you which one fixed it, and the other may add a bug. |
| "The reference is huge; I'll take the gist." | Skimmed patterns ship with the skipped parts broken. |
| "I already see what's wrong." | What you see is the symptom. The cause stays unconfirmed until evidence shows it. |
| "One more try." (after 2 or more failures) | A third failure is evidence against the design. The next move is the architecture review, not fix four. |
