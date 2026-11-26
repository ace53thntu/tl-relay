---
name: using-tl-relay
description: Use at the start of every conversation. It sets out how to find and use skills, and requires invoking a matching skill before ANY reply, clarifying questions included
---

<SUBAGENT-STOP>
This skill serves the main session. A subagent working one dispatched task stops reading here.
</SUBAGENT-STOP>

<MUST-READ-FIRST>
The bar is 1%, with no exceptions. A 1% chance that a skill fits means you MUST invoke it.

INVOKE EVERY SKILL THAT APPLIES, EVERY TIME.

Talking yourself past the bar is the failure the red flags below describe.
</MUST-READ-FIRST>

## Skills

- `brainstorm`: Creative work lies ahead: a feature, a component, a behavior change, anything new.
- `write-plan`: No code exists yet, and a spec or approved requirements for a change with several steps are available. The plan may start by reading the code.
- `run-plan`: A plan is ready and its independent tasks go to subagents.
- `route-subagents`: A subagent is about to be dispatched, or its model or effort is asked.
- `debug-issue`: No fix is proposed yet for a bug, failing test or unexpected behavior.
- `explore-codebase`: Existing code must be found or read: callers, call paths, where a value is set, or a sweep of config files across repositories.
- `test-first`: A feature or bugfix lacks its test; no implementation goes first.
- `review-change`: A merge is next, or a task or major feature is complete.
- `tl-design`: Starting, continuing, checking or signing a feature's design.
- `tl-implement`: Building or resuming a signed design's breakdown row as a pull request.
- `verify-done`: A claim of complete, fixed or passing lacks a fresh check you ran and read.

## Workflow

1. Check the skills, then invoke each relevant one and any the user named.
2. If `$TL_RELAY_LESSONS/<skill>.md` exists, read it. A lesson replaces a skill default; the operator's instruction in this session overrides a lesson.
3. Announce it ("Using [skill] to [purpose]"), then follow it exactly.

A reply, a clarifying question, a code search, a file read: each is an action. Check the skills before every action, on every turn.

- A skill's checklist becomes one todo per item. Drop a skill once it clearly does not fit.
- Before plan mode, invoke `brainstorm` unless the work was brainstormed.

When two or more skills apply or instructions conflict, read [reference.md](reference.md).

## Red flags

Each thought below means STOP.

- "It is only a simple question." "This is not a real task." "A skill is overkill here." "I will do one thing first." "Moving fast feels productive.": Check the skills BEFORE any action.
- "I need context first." "I will collect some facts." "One quick git or file check.": Run the skill check BEFORE asking or gathering.
- "I will look through the codebase.": Invoke `explore-codebase`, then open files. To plan an approved change, invoke `write-plan` first, then `explore-codebase` for the reads.
- "No formal skill is needed." "I know the concept." "I remember that skill.": Invoke it; read its current version.
