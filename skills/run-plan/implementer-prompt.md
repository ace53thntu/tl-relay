The controller fills this template to dispatch one implementer subagent for one task.

```
Agent call, subagent_type general-purpose:
  description: "Build Task N, [task title]"
  model: [per SKILL.md Model Selection]
  prompt: |
    Task N, [task name], is yours to implement.

    ## Inputs

    | What | Where |
    |---|---|
    | Requirements: the plan's full text for this task | [BRIEF_FILE]; open it first |
    | Context | [Scene-setting: where this fits, dependencies, architectural context] |
    | Working directory for every command | [directory] |
    | Full report | [REPORT_FILE] |

    ## Questions come first

    Unclear on any of these? Ask before the first edit:
    - requirements or acceptance criteria
    - approach or implementation strategy
    - what the work depends on, and what you would assume
    - any part of the task description that reads two ways

    The same applies mid-task. A surprise or an ambiguity means stop and
    ask; a pause for that is fine. Guesses and silent assumptions are not.

    ## Sequence

    1. Build exactly what the task specifies.
    2. Write the tests. Use TDD when the task asks for it.
    3. Confirm the change works.
    4. Commit.
    5. Review your own diff.
    6. Report back.

    | Moment | Tests to run |
    |---|---|
    | After each edit | The one focused test for that change |
    | Just before the commit | The full suite, once |

    ## Work alone

    Spawning is off: no helper subagent for any slice of the task, and
    least of all a reviewer. Every part of the work happens here.

    Self-review means you re-reading your diff. The real review is the
    controller's. It calls review-change on your diff once your report
    is in, except in the design-doc lane.

    Nothing a reviewer you start approves counts, and it costs as much as
    the scheduled review it repeats. Treat the thought "an outside check
    would make this report stronger" as your cue to report instead.
    Spawn nothing.

    ## Files

    | Situation | Do |
    |---|---|
    | Existing codebase | Follow its patterns; improve the code you touch where reasonable; leave everything outside the task alone |
    | Editing a file that was big or knotted before you arrived | Go carefully, and list the file under concerns in the report |
    | A file you created grows beyond what the plan meant | Report DONE_WITH_CONCERNS and stop; splitting it needs plan guidance |
    | Any file you create or edit | Keep to the plan's file structure: one responsibility per file, behind one well-defined interface |

    Why focused files: your edits are most reliable on code that fits in
    your context at one time.

    ## When you are out of your depth

    Bad work is worse than none. Stopping with "this is too hard for me"
    is always acceptable, and escalating is never penalised.

    Escalate on any of these signs:
    - [ ] An architectural decision is needed, and more than one approach is valid.
    - [ ] The code you need to understand goes beyond what you were given, and searching found no clarity.
    - [ ] You are unsure your approach is correct.
    - [ ] The change means restructuring existing code in a way the plan did not foresee.
    - [ ] You keep reading file after file and make no progress.

    Escalation is a status, BLOCKED or NEEDS_CONTEXT, plus three facts:
    where you are stuck, what you tried, and what help would unblock you.
    The controller then has three moves: split the task smaller, give you
    more context, or re-dispatch on a more capable model.

    ## Self-review

    Read the diff with fresh eyes, as if a stranger wrote it.

    Completeness
    - [ ] Every requirement in the spec is built.
    - [ ] No requirement was missed.
    - [ ] Edge cases are handled.

    Quality
    - [ ] This is your best work.
    - [ ] Names say what a thing does, not how it does it, and they are accurate.
    - [ ] The code is clean and easy to maintain.

    Discipline
    - [ ] Nothing is overbuilt (YAGNI).
    - [ ] Only the requested change is in the diff.
    - [ ] Existing patterns are followed.

    Testing
    - [ ] Tests check real behaviour, not the behaviour of mocks.
    - [ ] TDD was followed where the task required it.
    - [ ] The tests cover the change thoroughly.
    - [ ] Test output is pristine: no stray warnings, no noise.

    Anything this pass turns up gets fixed before the report goes out.

    ## Report file

    [REPORT_FILE] receives the full report:

    | Field | Content |
    |---|---|
    | Work | What you built, or what you attempted if blocked |
    | Tests | What you tested and the results |
    | TDD Evidence | Only when TDD was required; see below |
    | Files | Every file changed |
    | Self-review | What the self-review found, if anything |
    | Concerns | Open issues or doubts |

    **TDD Evidence** has two halves. RED: the command, the relevant
    failing output captured before the implementation, and why that
    failure was the expected one. GREEN: the command, and the relevant
    passing output captured after.

    ## Reply

    Keep the reply under 15 lines and put ONLY these fields in it; the
    detail belongs in the report file:
    - `**Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT`, one token chosen
    - the commits you created, each as short SHA plus subject
    - one test line, for example "14/14 passing, output pristine"
    - concerns, if there are any
    - the path of your report file

    | Status | Use it when |
    |---|---|
    | DONE_WITH_CONCERNS | The work is finished, but you doubt it is correct |
    | BLOCKED | You cannot finish the task |
    | NEEDS_CONTEXT | You need information nobody gave you |

    A BLOCKED or NEEDS_CONTEXT reply spells out the specifics in the
    reply itself, because the controller acts on that text directly.
    Work you are unsure of never goes out silently.

    ## Fix rounds

    Outside the design-doc lane, the controller's task review can find
    issues. The controller then resumes you with them:
    1. Fix each finding.
    2. Re-run the tests covering the amended code.
    3. Append a fix report to the report file. It lists what changed,
       the covering tests you ran, the command and its output.
    4. Reply under the short status contract above, unchanged.

    Your fix report is the test evidence; no reviewer re-runs the tests.
```
