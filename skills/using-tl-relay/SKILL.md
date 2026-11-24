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

| Skill | Reach for it when |
|-------|-------------------|
| `brainstorm` | Creative work lies ahead: a feature, a component, a behavior change, anything new. |
| `write-plan` | No code exists yet, and a spec or approved requirements for a change with several steps are available. |
| `run-plan` | A plan is ready, and its independent tasks go to subagents. |
| `route-subagents` | A subagent is about to be dispatched, or someone asks which model or effort delegated work gets. |
| `debug-issue` | The next fix for any bug, failing test or unexpected behavior is not proposed yet. |
| `explore-codebase` | Existing code must be found or read: callers, call paths, where a value is set, or a sweep of config files across repositories. |
| `test-first` | A feature or bugfix lacks the test for the code it needs; no implementation goes first. |
| `review-change` | A merge is next, or a task or major feature is complete. |
| `tl-design` | Someone asks to start or continue a feature's design from its sources, asks where a design stands, or asks to sign a design gate. |
| `tl-implement` | Someone asks to build a signed design's breakdown row into a pull request, or to resume such a run. |
| `verify-done` | You have not run and read, in this message and after the last change, the check behind a claim of complete, fixed or passing. The claim waits for it. |

## Workflow

1. Check the skills.
2. Invoke the relevant skill, or the one the user named.
3. When the environment sets `TL_RELAY_LESSONS`, read `$TL_RELAY_LESSONS/<skill>.md` if it exists. A lesson replaces a default of that skill. An instruction from the operator in this session overrides a lesson.
4. Announce it: "Using [skill] to [purpose]".
5. Follow the skill exactly.

A reply, a clarifying question, a code search, a file read: each is an action. Before any action, check the skills and invoke each relevant or requested one.

This holds on every turn, not only the first.

- Checklist in the skill: one todo each.
- Drop a skill once the situation shows it does not fit.
- About to enter plan mode: invoke `brainstorm` first, unless this work was already brainstormed.

## Order between skills

When several skills apply, sort them by kind.

| Kind | Runs | Examples |
|------|------|----------|
| Process | First; it sets the approach | `brainstorm`, `debug-issue`, any other process skill |
| Implementation | After; it carries the approach out | `frontend-design`, the domain skills |

| Request | First | Then |
|---------|-------|------|
| "Build X" | `brainstorm` | Implementation skills |
| "Fix this bug" | `debug-issue` | Domain skills |

## Red flags

Each thought below means STOP. You are rationalizing.

| Thought | Why it fails | Do |
|---------|--------------|----|
| "It is only a simple question." | You answer a task without its skill. | Check the skills, then answer. |
| "I need context first." | The clarifying question goes out unguided. | Run the skill check BEFORE asking. |
| "I will look through the codebase." | You explore without the method a skill gives. | Invoke `explore-codebase`, then open files. |
| "One quick git or file check." | The files cannot tell you what this conversation asked for. | Check the skills first. |
| "I will collect some facts." | You gather without the method a skill gives. | Check the skills for HOW to gather, then collect. |
| "No formal skill is needed." | When a skill covers the work, going without it is a bypass. | Use it. |
| "I remember that skill." | You act on a version that may have changed. | Read the current version. |
| "This is not a real task." | You act without the check every action needs. | Check the skills. |
| "A skill is overkill here." | The small job grows, and the skipped steps grow with it. | Use the skill. |
| "I will do one thing first." | That one thing would run unchecked. | Check BEFORE any action. |
| "Moving fast feels productive." | Rework later eats the time saved now. | Let a skill steer. |
| "I know the concept." | Knowing about a skill does nothing until you run it. | Invoke it. |

## Precedence of instructions

1. Your user's instructions rank highest: your instruction files (user and project `CLAUDE.md`, `AGENTS.md`) when present, and direct requests.
2. Skills rank next.
3. Default behavior ranks last.
4. A skill's workflow and instructions stand until your human partner explicitly tells you to set them aside. Nothing else lifts them.
