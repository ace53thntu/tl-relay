---
name: route-subagents
description: Use before dispatching any subagent, and whenever someone asks which model tier or effort delegated work should get. Also use when deciding whether a design document skips code review, whether a task is concrete enough for an implementer, whether a failing task moves to a stronger model, or what to do after two fix attempts made no progress.
---

# Route subagents

The main session plans and adjudicates. Subagents type, and every dispatch names its model.

## Roles in the code lane

| Role | Dispatch | Does |
|---|---|---|
| Scout | per `explore-codebase` | Sweeps files the code index does not hold |
| Planner and controller | the main session | Reads the code, finds the mismatch, writes the plan and each task prompt |
| Plan gate | `model: opus`, `effort: high` | Reads the plan before the first implementer |
| Implementer | `model: sonnet`, `effort: medium` | Writes the code, one task per subagent |
| Code reviewer | `model: opus`, `effort: high`, per `review-change` | Reviews the diff; `review-change` owns rounds and findings |

## Model parameter

- `model:` takes `opus`, `sonnet`, `haiku` or `fable`. Name the tier, never a version.
- Use `fable` only when the user names it in the request.
- Set `effort` only where a row above sets it.

## Design-doc lane

It applies when the deliverable is an HLD, HLA, LLD, spec, spike, tech-debt proposal, postmortem or load-test plan.

- The writer runs on `model: opus`, one task per subagent under `run-plan`.
- No code review runs.
- The plan gate still runs.

## Plan gate

Before the first implementer, a fresh subagent reads the plan. It reports contradictions, missing steps, and steps that depend on something the plan never builds. The main session adjudicates each finding.

## Implementer readiness and escalation

- A task is ready only when it names the files to touch, the change in each, and the command that proves it. A task short of that goes back to the planner.
- Escalate one task to `model: opus` when its change turns on business logic across repositories, or when Sonnet has failed it twice.
- Escalate that task, never the whole plan.

## Stuck debugging

A debugging thread that loops twice without progress stops iterating in its own context. The planner gets the failing output, both sides of the suspected mismatch, and what was ruled out.

## Excuses and answers

| Excuse | Answer |
|---|---|
| "Docs are cheap, so Sonnet can write them." | No test catches a design-doc defect. The writer is Opus. |
| "Run code review on each page to be safe." | The design-doc lane runs no code review. The plan gate still runs. |
| "The plan is short, so skip the gate." | The gate runs before the first implementer on every plan. |
| "Sonnet is struggling, so move everything to Opus." | Escalate the task that failed twice. The rest stay on Sonnet. |
| "Pin a model version for consistency." | The parameter takes a tier only. |
| "Keep it moving, dispatch the vague task." | A task without files, change and command goes back to the planner. |
| "One more fix in this context will work." | Two loops end the thread. Hand the planner the whole picture. |
