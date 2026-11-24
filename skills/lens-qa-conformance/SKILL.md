---
name: lens-qa-conformance
description: Use when a subagent maps each design rule in a breakdown row's rule set to code and a test in the diff.
---

# QA conformance lens

## Overview

You map each rule of one breakdown row to the code and the test that carry it. You return one row per rule.

## Rules

- The rule set is the row's page plus every LLD and Overview anchor it links to, one hop deep. A shared page counts only at the linked anchors.
- A rule is any of the following. Scenarios are test material, not rules.
  - One H3 entry under a `## Rules` heading. Without H3 entries, each bullet or prose paragraph there. Never count both.
  - One bullet under a `**Rules:**` label.
  - One rule bullet under a bold label that names a case, as `write-lld` § Rules, not narrative defines it. A body label, a telemetry label and `**Out of scope**` are not case labels.
  - One `<PREFIX>-INV-n` invariant.
  - One stated fact in the Schema changes page (`schema-changes.md`) sections `## Data model` and `## Config changes`. Also count each `## DDL` fact the Data model does not state.
- Read the rule set, `git diff <base>..HEAD`, and the repo at the base commit.
- Read the base commit with `git show <base>:<path>`, `git grep <pattern> <base>` and `git ls-tree -r <base>`. Never check out another commit. Grep and Glob read the working tree, so read HEAD with `git grep <pattern> HEAD`.
- Give `code` as one or more `file:line` entries at HEAD, joined by `, `, or `none`. For `baseline`, each `file:line` is at the base commit.
- Give `test` as `<test file>::<test name>`, or `none`. List several tests the same way, joined by `, `.
- Give a `reason` for `out-of-scope`, `overridden` and `env-only`; leave it empty otherwise. For `env-only`, the `reason` names the environment check. It also names where the rule lives when it is outside the repo.

## Checks

- When more than one verdict fits, take the first in this order: `overridden`, `out-of-scope`, `env-only`, `baseline`, `covered`, `code-only`, `missing`.
- `covered`: the diff carries the code, and a test at HEAD asserts the rule.
- `code-only`: the diff carries the code, and no test at HEAD asserts the rule. This verdict is blocking.
- `missing`: HEAD carries no code for the rule, including base code the diff deleted or broke. This verdict is blocking.
- `baseline`: the base commit carries the rule, and the diff leaves that code unchanged at HEAD.
- `env-only`: HEAD carries the code, or the rule lives outside the repo, and only a deployed environment can show it. An example is a toggle checked on QA. These rows go to Known gaps.
- `out-of-scope`: another breakdown row owns the rule. The `reason` names that row.
- `overridden`: the operator confirmed the signed page is wrong for this rule. The `reason` names the decision.
- A new test with no code in the diff or at the base is `missing`.
- Code split between the base and the diff counts as diff code.

## Never does

- Edits code or pages.
- Reports style or general bugs.

## Output

Return an object `{"rows": [...]}`. Each row has `anchor`, `rule`, `code`, `test`, `verdict` and `reason`.
