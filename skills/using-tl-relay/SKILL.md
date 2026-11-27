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

| Skill | When |
|-------|------|
| `brainstorm` | Creative work lies ahead: a feature, a component, a behavior change, anything new. |
| `write-plan` | No code exists yet, and a spec or approved requirements for a change with several steps are available. The plan may start by reading the code. |
| `run-plan` | A plan is ready and its independent tasks go to subagents. |
| `route-subagents` | A subagent is about to be dispatched, or someone asks which model or effort delegated work gets. |
| `debug-issue` | The next fix for a bug, failing test or unexpected behavior is not proposed yet. |
| `explore-codebase` | Existing code must be found or read: callers, call paths, where a value is set, config sweeps across repositories. |
| `test-first` | A feature or bugfix lacks its test; no implementation goes first. |
| `review-change` | A merge is next, or a task or major feature is complete. |
| `tl-design` | Someone asks to start or continue a feature's design from its sources, asks where a design stands, or asks to sign a design gate. |
| `tl-implement` | Building or resuming a signed design's breakdown row as a pull request. |
| `verify-done` | A claim of complete, fixed or passing lacks a check you ran and read in this message, after the last change. |
| `unslop` | A draft for a human reader reads as machine-written, or a writer skill reaches its prose pass. |

## Workflow

1. Check the skills, then invoke each relevant one and any the user named.
2. When `TL_RELAY_LESSONS` is set, read `$TL_RELAY_LESSONS/<skill>.md` if it exists. A lesson replaces a default of that skill; the operator's word this session overrides it.
3. Announce the skill ("Using [skill] to [purpose]"), then follow the skill exactly.

A reply, a clarifying question, a code search, a file read: each is an action. Check the skills before every action, on every turn.

- One todo per checklist item; drop a skill that clearly does not fit.
- Before plan mode, invoke `brainstorm` unless the work was brainstormed.

When two or more skills apply, invoke the `using-tl-relay` skill and read its `reference.md` for their order.

## Red flags

Each thought below means STOP.

- "It is only a simple question." "This is not a real task." "A skill is overkill here." "I will do one thing first." "Moving fast feels productive.": Check the skills BEFORE any action.
- "I need context first." "I will collect some facts." "One quick git or file check.": Run the skill check BEFORE asking or gathering.
- "I will look through the codebase.": Invoke `explore-codebase`, then open files. To plan an approved change, invoke `write-plan` first, then `explore-codebase` for the reads.
- "No formal skill is needed." "I know the concept." "I remember that skill.": Invoke the skill that covers the work; read its current version.

## Precedence of instructions

1. Your user's instructions rank highest: your instruction files (user and project `CLAUDE.md`, `AGENTS.md`) when present, and direct requests.
2. Skills rank next.
3. Default behavior ranks last.
4. A skill's workflow and instructions stand until your human partner explicitly tells you to set them aside. Nothing else lifts them.
