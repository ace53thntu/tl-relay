---
name: write-plan
description: Use when approved requirements describe a multi-step change and the implementation plan must exist before anyone touches code. Also use when drafting the plan means reading the existing code first
---

# Write Plan

First message to the user: "write-plan: drafting the implementation plan for <topic>."

Task rules: [core.md](core.md). The plan rules in `core.md` bind every plan, including a plan `tl-implement` asks `write-plan` for, and every task in the plan follows them.

## Workflow

1. Scope. Ask: does this plan, alone, ship working, tested software? Every plan must. For a spec covering independent subsystems, offer one plan per subsystem. Brainstorming was the place to cut it into sub-project specs.
2. Write the file map (see "File map").
3. Write the header, then the tasks, from the templates under "Plan header" and "Task template".
4. Self-review the finished plan (see "Self-review"). Do it yourself. Dispatch no subagent.
5. Save the plan and hand it off (see "Save and hand-off").

## Reader

- **Knows:** the project language. From an exact interface and an exact test, writes idiomatic code.
- **Does not know:** the codebase or the spec.
- **Fills gaps by:** picking a sensible option wherever the plan leaves a choice.

So the plan supplies what this reader lacks:

- the files to touch
- names and signatures
- values the spec fixes
- the test that proves each task

Break the work into bite-sized tasks. Apply DRY, YAGNI, TDD and frequent commits.

## File map

The file map is a table: path | responsibility. It has one row per file the plan creates or changes, and one responsibility per row. It comes before any task. The table fixes the decomposition, and the tasks are cut from it.

| Rule | Reason |
|------|--------|
| Small files, each with one responsibility, a clear boundary and a defined interface, over large multi-purpose ones | The implementer holds a focused file in context and edits it more reliably |
| Files that change together sit together | They land in the same task |
| A feature's model, view and storage files sit together, grouped by the responsibility they share | The feature then lands in one task instead of one per layer |

Existing codebase: its patterns win. Restructuring a codebase of large files is not the plan's call. The plan may split an unwieldy file that the task already changes.

## Task sizing

| Keep apart when | Merge when |
|-----------------|------------|
| A reviewer could accept one task and reject the other | No reviewer could split the verdict between them, or one is setup, configuration, scaffolding or documentation for the other's deliverable |

Every task is self-contained and closes on a deliverable someone can test in isolation.

Shrink each task as far as it goes. Stop before a piece would lose its own red–green cycle or become too small to earn a fresh review.

## Step granularity

Steps follow the table: one action per row, each with its own check, in this order.

| Step | Action | You can check |
|------|--------|---------------|
| 1 | Red test | The new test exists and asserts the expected result |
| 2 | Red run | The run reports the test failing |
| 3 | Minimal code | The change adds only what the test needs |
| 4 | Green run | The run reports the tests passing |
| 5 | Commit | The commit holds the test and the code |

## Plan header

Copy the block below to the top of the plan file and keep its section order. Fill each placeholder as the table after it says.

````markdown
---
type: Implementation Plan
affects:
  - repo-name
---

# [Feature Title] Implementation Plan

> **For agentic workers:** Execute this plan task by task with the run-plan sub-skill (REQUIRED SUB-SKILL: Use run-plan). Track each step through its `- [ ]` checkbox.

**Goal:** [One sentence on what gets built]

**Architecture:** [Two or three sentences on the approach]

**Tech Stack:** [Key technologies and libraries]

**Spec:** [Path to the spec or design doc this plan implements]

## Global Constraints

- [One project-wide requirement per line, exact values from the spec]

## Review Focus

- [Input or condition, and the behaviour a reasonable person expects]

---
````

| Part | Rule |
|------|------|
| `affects:` | Every repo the plan changes, each as one `  - ` item |
| H1 | The feature's name replaces the placeholder |
| `**Spec:**` | Executors read this doc and the plan together, and the plan argues from the spec |
| `## Global Constraints` | Holds version floors, dependency limits, naming and copy rules, platform requirements. Copy exact values from the spec. Each task inherits these lines |
| `## Review Focus` | Up to five entries, most likely first. Each names an input class or failure mode and the behaviour a reasonable person expects |

A Review Focus entry qualifies when all three hold:

- the spec implies the input;
- no task's tests exercise it;
- it ranks among the five likeliest to hurt a user.

An input the spec never names must still not break the software. The spec lists required behaviour, not every input.

Each entry's pinning test lands in the task that owns it, in that task's step style. Draft the whole section in a single sitting, spec open.

## Task template

`task-brief` in run-plan extracts each `### Task N:` section. Keep the other labels and list prefixes exact as well, since they are the plan convention. Paths go in backticks. A `Modify:` path carries a `:<start>-<end>` line range.

`**Interfaces:**` holds two lines:

| Line | Lists | Because |
|------|-------|---------|
| `Consumes:` | Every symbol this task needs from earlier tasks (function, type, constant or property), each with its exact signature | The implementer reads only its own task |
| `Produces:` | Every symbol later tasks need from this task: exact name, parameter types, return type | Those implementers also read only their own task, so this block carries the neighbours' names and types |

Blocks inside a task run: heading, `**Files:**`, `**Interfaces:**`, steps. A four-backtick fence wraps the template so three-backtick code blocks fit inside.

````markdown
### Task N: [Task Title]

**Files:**
- Create: `src/slug.py`
- Modify: `src/__init__.py:2-2`
- Test: `tests/test_slugify.py`

**Interfaces:**
- Consumes: `normalize_whitespace(text: str) -> str` from Task 1
- Produces: `slugify(title: str) -> str`, lowercase words joined by hyphens

- [ ] **Step 1: Add a test that fails**

```python
import src


def test_slugify_joins_words_with_hyphens():
    assert src.slugify("Hello  World") == "hello-world"
```

- [ ] **Step 2: Run the test and see it fail**

Run: `python -m pytest tests/test_slugify.py::test_slugify_joins_words_with_hyphens -v`
Expected: FAIL with "AttributeError: module 'src' has no attribute 'slugify'"

- [ ] **Step 3: Implement `slugify(title: str) -> str` in `src/slug.py`**

Pass the title through `normalize_whitespace`, lowercase it, then replace each space with a hyphen. Re-export it on line 2 of `src/__init__.py`: `from src.slug import slugify`.

- [ ] **Step 4: Run the test and see it pass**

Run: `python -m pytest tests/test_slugify.py::test_slugify_joins_words_with_hyphens -v`
Expected: PASS

- [ ] **Step 5: Commit the change**

```bash
git add tests/test_slugify.py src/slug.py src/__init__.py
git commit -m "feat: add slugify"
```
````

## Step content

Judge a step by one question: can the implementer write exactly one reasonable thing from it? A step must be unambiguous, not complete. Include only what removes the ambiguity.

| Step type | Carries |
|-----------|---------|
| Verification | Shell command; the output that signals success |
| Test | Test name; assertions written as code; the spec's literal values |
| Code | Signature (name, parameters, return type); target file; values the spec pins. The implementer owns the body |

- **Code body:** Do the signature and its tests still allow more than one algorithm? Write the body. Does the spec dictate the exact text? Write it out. Otherwise leave the body to the implementer.
- **Approach hint:** at most one line, in place of a body. Add it only when a real choice remains, such as a library call or data structure.

Cross-task code: reference the owning task's Interfaces block instead of restating it.

A plan's content is the implementer's missing decisions. Two smells show a plan has drifted:

| Smell | Sign |
|-------|------|
| Transcript | The code already sits inside the plan: its text outgrows the code it stands for |
| Filler | A line decides nothing: "TBD", "handle edge cases", "add appropriate validation", "write tests for the above", or a type or function no task defines |

Self-review catches both.

## Self-review

- Spec requirement with no task → write the missing task.
- Any other problem → fix it in place.
- Fixes done → stop. Run no second review pass.
- Whole plan written → reopen the spec and run the checks below yourself, with no subagent.

1. **Spec coverage.** Every spec section and requirement points to a task. Write down any that do not.
2. **Step scan.** Ask of every step: does it yield exactly one reasonable implementation? Repair either failure. *Gap:* the step decides nothing. *Transcript:* the signature and tests already fix its body.
3. **Type consistency.** Later tasks reuse earlier types, method signatures and property names unchanged. Any drift between tasks is a bug. Example: Task 2 defines `fetch_invoice(id)` and Task 5 calls `get_invoice(id)`.
4. **Review Focus.** Find every input class or failure mode the spec implies without a task test. Enter the likeliest to hurt a user in `## Review Focus`, up to five. Add each one's test to its owning task. If you find none, leave the section empty. An empty section records that you checked.
5. **Proportion.** Trigger: the plan runs several times the spec's length, or code blocks fill most of it. That plan is a transcript. Remedy: shrink bodies to signatures, test names and assertions. Then recheck every step for ambiguity.

## Execution

`run-plan` implements the plan. Each task gets a fresh subagent. A fresh reviewer gates each task before the next one starts. A whole-branch review closes the run.

`route-subagents` assigns models to these roles. Name the roles in the plan. Never copy its table.

## Save and hand-off

Save path: `<runtime>/plans/YYYY-MM-DD-<slug>.md`, with `<runtime>` per [config.md](../using-tl-relay/config.md). The `CLAUDE.md` section "Skill output targets" overrides it. Where the user names another location, use theirs.

When the invoking skill states that the caller gates the plan itself, skip the review message and the REQUIRED line below. Instead, return the saved plan path to the caller. The caller decides when `run-plan` starts. You save and self-review a plan the caller revises.

Otherwise, hand off after saving and self-review: post the link to your human partner with this message: "Ready for your review: `<saved path>`. Does the plan capture what you want?" Implementation waits until they approve it.

Once the human approves: **REQUIRED SUB-SKILL:** `run-plan`.
