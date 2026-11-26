---
name: write-design
description: Use when writing or changing a page of a design set under `<runtime>/designs/<handle>/`, such as the Overview, a use case page, the Schema changes page, a module LLD or the Dependencies page. Also use to check where a design-set page sits, or which rule governs it.
---

# Write a design set

## Configuration

Paths follow [config.md](../using-tl-relay/config.md): `<design root>` holds `designs/`, by default `<state_dir>/<workspace>/`. `knowledge_dir` has no default.
`<skill dir>` is this skill's base directory as the session reports it. `doc_budget.py` comes from the sibling skill `tl-design`. If `<skill dir>/../tl-design/scripts/doc_budget.py` is missing, stop and name `tl-design` with `npx skills add ace53thntu/tl-relay --skill tl-design`.

## Overview

A design set is one page tree under `<design root>/designs/<handle>/`. This skill owns that tree: the pages, their paths, and the rules that span them.

- `write-hla` sets the five-section skeleton of the Overview and the use case page form.
- `write-lld` sets the seven-section skeleton of a module LLD and its child page rules.
- `write-task-breakdown` owns `task-breakdown.md`.

This skill cites those skills and states only where a set differs from them.

## Page tree

```text
<Set title>                      overview.md
├── <Set title>: Use cases       use-cases/index.md
│   └── UC-n <name>              use-cases/uc-<n>-<slug>.md
├── <Set title>: Schema changes  schema-changes.md
├── <Set title>: LLDs            lld/index.md
│   ├── <Module> LLD             lld/<module>.md, with its child pages
│   └── Shared logic             lld/shared-execution-logic.md, several modules only
├── <Set title>: Task breakdown  task-breakdown.md
└── <Set title>: Dependencies    dependencies.md
```

- All paths are relative to `<design root>/designs/<handle>/`.
- The Overview has five children, in this order: Use cases, Schema changes, LLDs, Task breakdown and Dependencies.
- A set has no decisions page. [Decisions](#decisions) states where a decision goes.
- These files hold workflow state, not design content: `index.md` with the state block, `open-points.md`, `open-points-full.md`, `task-breakdown.estimates.tsv`, `sources/`, `specs/`, `audits/` and `contracts/`.

## Overview page

`overview.md` follows `write-hla`: its skeleton, `## Terms`, deep dives, failure modes, panels and budgets.

The Overview is an HLA with no module HLAs. The L1 HLA and module HLA rules of `write-hla` do not apply.

These rules differ:

- The five sections keep their fixed order: 1. Requirements and scope, 2. Core entities and API, 3. High-level design, 4. Deep dives, 5. Failure modes and self-healing.
- Section 1 takes the `write-hla` form: the numbered Core requirements list with linked use case ranges, then the `**NFR-n**` bullets.
- Each use case id in a range links `use-cases/uc-<n>-<slug>.md`, or `use-cases/<code>-uc-<n>-<slug>.md` in a multi-module set.
- A criterion id from the set's register, such as `S-nn` or `US-004`, stays plain text.
- Section 2 shows the trimmed `## Data model` of the Schema changes page, as `write-hla` section 2 sets for a schema page.
- Section 3 has no `3.1 Use cases` index.
- A set with several modules prefixes each use case id with the module code, such as `PL-UC-1`.
- The frontmatter carries `type: HLD`, as the HLA pages of the existing sets do.
- A set adds no entry to the HLA index `hlds/index.md`, neither for `overview.md` nor for `use-cases/index.md`.
- Every other page links a term to `overview.md#terms` on its first use.
- `doc_budget.py` types `overview.md` as an HLA page.

## Use case pages

- The container is `use-cases/index.md`, titled `<Set title>: Use cases`.
- Each use case has one page, `use-cases/uc-<n>-<slug>.md`.
- In a set with several modules, the file name opens with the lowercase `module_code`: `use-cases/<code>-uc-<n>-<slug>.md`. The id reads `<CODE>-UC-n`.
- The container and each page keep the `write-hla` shape (Use case pages). The first source of each page is the Overview.
- **Source.** cites a criterion id from the set's register.
- Only a use case with app screens carries `## Screens`. The section's only bullets are the app labels, such as `- **Admin Portal**`.
- A use case with no app screen has no `## Screens` heading. `generate_breakdown.py` makes a UI task for each page that has one.

## Schema changes page

`schema-changes.md`, titled `<Set title>: Schema changes`, holds three sections in this order:

1. `## Data model` keeps the `write-lld` Schema page shape: database names, one `erDiagram` per group, column notes, line kinds and each module's index table.
   - Each group sits under a bold label alone on its line, with no colon: `**<module_code> · <name>**`, `**Existing tables**` or `**Shared tables**`. An example is `**PL · Planning**`.
   - `generate_breakdown.py` reads these labels. A route or element task depends on `SCHEMA` when its own module's label exists, or when an Existing or Shared tables label exists.
2. `## DDL` holds the DDL in migration order, in `sql` fences. A `<details><summary>DDL in migration order</summary>` wrapper may hold the fences. The `write-lld` rule against DDL on the Schema page does not apply here.
3. `## Config changes` lists each environment variable, feature flag and per-country policy record the set adds or changes. The UI task and the API tasks never carry config.

- A set has one Schema changes page. Each module page's section 3 holds the `Schema:` line alone, linking its group.
- Behaviour the old section 3 prose carried goes to section 5.
- `doc_budget.py` types the page `schema-changes`: 600 words, with `## DDL` and `sql` fences allowed.

## LLDs

- The container is `lld/index.md`, titled `<Set title>: LLDs`. It lists one page per module.
- A module page is `lld/<module>.md`, titled `<Module> LLD`, with `type: LLD` and a `module_code` key, such as `module_code: PL`.
- Each module page gets an entry in the set's `index.md` whose description equals the page's.
- `module_code` sits only in the frontmatter of the module page. Never put it on `lld/<module>-api.md` or on any other `lld/*.md`.
- `generate_breakdown.py` counts modules by scanning `lld/*.md` for `module_code`. A stray key turns a single-module set into a multi-module set and renames every use case id.
- A module page keeps the seven sections and the child page rules of `write-lld`. A section with no content states "none".
- A small set has one module page and no optional child pages.
- The stack comes from the Overview, not from a repo.
- Section 1's `Input condition` column cites the `S-nn-ACm` and `T-nn` ids the scenario comes from.
- An LLD past `G-design` deletes nothing. An element with no reason goes into the writer's report with the reason. The tech lead rules on each one. A deletion there changes the contract and the task breakdown.
- In a set with no code, a claim cites a decision anchor, a criterion id or a screen instead of a file.

### Scenarios page

In a set with several modules, every module page moves its Scenarios block onto a child page, however long it is:

- Path `lld/<module>/scenarios.md`, beside the route pages' `api/` directory.
- Title `<LLD title without "LLD"> scenarios`, such as `Example Planning scenarios`.
- Body: one sentence, "This page holds the scenario table of section 1 of the [<LLD title>](../<module>.md#1-component-use-cases-and-technical-scenarios).", then the table. Relative links in the table gain one `../`.
- The parent's section 1 keeps its scope sentence and **Out of scope** list, then the `Scenarios:` line with the child page's link and a short gloss.
- Each child page gets an entry in the set's `index.md`.

### API page and route pages

- A module with routes always has an API page `lld/<module>-api.md` and an OpenAPI contract, as `write-contract` sets.
- The module page's section 4 is one sentence that links the API page.
- The API page holds the route table under the heading `## 4. Interface contracts and API specifications`. `check_contract.py` reads the table only under that heading.
- The API page's route table is the module's route list. `check_contract.py` runs once per module with `--api lld/<module>-api.md`.
- A route page is `lld/<module>/api/4-<N>-<method>-<slug>.md`, with the H1 `# API 4.N: <METHOD> <path> - <summary>`.
- A route page H1 in a set always carries `<METHOD> <path>`. `generate_breakdown.py` reads the first two words after `API 4.N:` as the method and the path.
- An element with no HTTP path gets a `<Kind> 4.N:` element page, such as `Workflow 4.N:`, not a route page.
- A non-route element page is a direct child of the module LLD, at `lld/<module>/<slug>.md`. It never sits under `lld/<module>/api/`. It gets a breakdown task, as `write-task-breakdown` sets.
- The API page and each route page get an entry in the set's `index.md` whose description equals the page's.
- A legacy set, written before the API page rule, may have no API page. A set with no API page keeps `lld/<module>/interface-contracts.md`. Section 4 links it, then holds the `write-lld` route table, and that page holds the `common-errors` block.

### Shared logic page

In a set with several modules, an operation that two or more modules run sits once on `lld/shared-execution-logic.md`, in the LLDs container.

- Each operation is one bullet: its name, inputs and result in one sentence, then **Used by.** with a link to each module and route that calls it.
- The page has no `text` block.
- Each module page's section 5 carries a `Shared logic:` line with the link, or the Execution logic page carries it when there is one. The module calls the operation by name.
- A module that calls no shared operation carries no line.
- A module whose operation differs keeps its own and states the difference in one sentence.

### Implementation notes

- When a rewrite takes an implementation-plan item off a page, the item moves to the set's `implementation-notes.md`. It is never deleted.
- An invariant, its id and a race outcome never move to `implementation-notes.md`. They stay on a design page, as `write-lld` section 5 sets.

## Decisions

- A set has no decisions page and no `Dn` id.
- A high-level decision is a section 4 deep dive on the Overview, in the form `write-hla` sets.
- A smaller ruling is an LLD module rule, in the form `write-hla` (Module rules) sets.
- A module rule sits under `## Rules` on the module's execution logic page. A module with no execution logic page keeps its rules at the end of section 5.
- A dependency Warning panel on a deep dive becomes one line that links `dependencies.md` and names its `DEP-n`.

### Merging a decisions page

A set written to an earlier version of these skills has a decisions page, `<top slug>/decisions.md`, with `Dn` ids. It keeps that page until the tech lead asks for the merge. Until then, its LLDs cite the `Dn` ids. The merge runs in one pass:

1. Sort each decision. A decision that meets the `write-hla` deep dive test becomes a deep dive, or folds into the deep dive that already shows its options. A sub-ruling or a ruling with no rejected option is dropped when the LLD already states it, and otherwise moves to the LLD as a module rule.
2. Write each deep dive in the `write-hla` deep dive form. Carry over the assumption line. A Waits on panel becomes one line that links `dependencies.md` and names its `DEP-n`. The merge adds that `dependencies.md` row when none exists. Leave out **Rules.**, **Details:** and **Consequences.**
3. Rewrite every link to the decisions page, and its label. A kept decision becomes `HLA 4.N`. A dropped one links the section that holds its rule, by that section's title. Replace the plain `Dn` ids in tables and frontmatter the same way. Dated audits keep the old ids.
4. Cut each use case Solutions section that a deep dive owns to the one linking sentence under `## Decision`. Move any fact its panels hold that the deep dive lacks into the deep dive first.
5. Move the decisions page's local file under `_archived/`.

## Dependencies

`dependencies.md`, titled `<Set title>: Dependencies`, holds one intro sentence and one table:

| ID | Team | Delivers | Blocked tasks | Until it lands | Status |
| --- | --- | --- | --- | --- | --- |

- Ids run `DEP-1` upward. A deleted number is never reused.
- **Blocked tasks** holds comma-separated task ids, or `none`.
- **Status** holds `{status:Not started}`, `{status:In progress}` or `{status:Done}`, which the publish tool renders as a status lozenge.
- The task ids come from the same `module_code` keys the generator reads, so a blocked task always names a generated task.
- Another page states a dependency in one sentence that links `dependencies.md` and names the `DEP-n` id. It does not restate the team, the delivery or the fallback.
- An existing set without `dependencies.md` keeps each dependency statement where it stands. The `DEP-n` link rule applies only after the tech lead asks for a Dependencies page.
- That sentence replaces the `**Waits on:**` panel of `write-hla` and the external dependency panel and statement of `write-lld`.
- `doc_budget.py` types the page `dependencies`: 150 words outside the table.

## Task breakdown

`task-breakdown.md` belongs to `write-task-breakdown`. Follow that skill for the page and its estimates file. Its generator reads the labels, H1s, file names and `## Screens` bullets this skill sets, so keep their form exact.

## Rules for every page of a set

- Skills write no `confluence` frontmatter and run no push.
- A published page carries no local reference: no audit path and no Confluence page id.
- A page states each decision as a fact. Never write "the tech lead decided".
- A design page carries no pseudo-code.
- A child page does not repeat a fact its parent states.
- No page carries an inline open point:
  - Write no `Open point (...)` line, no open-points section, no owner question table and no link to the open points pages.
  - Return each question the sources cannot answer in your report. The controller adds it to the set's open points pages, as `tl-design` says.
  - An answer becomes an Overview deep dive, a module rule, or an `Assumption:` line, and the controller deletes the entry.
  - `Assumption: … Confirms:` lines stay inline.
- Run `python3 <skill dir>/../tl-design/scripts/doc_budget.py <path>...` on every page written, with the budgets `write-hla` and `write-lld` set.
- **REQUIRED SUB-SKILL:** `technical-writing` for prose, then `unslop`, then the Vale gate in `technical-writing`. Zero errors.

## Common mistakes

- A decisions page, a `Dn` id, or a Waits on panel where one linked `DEP-n` line belongs.
- `module_code` on an API page or on any `lld/*.md` other than a module page.
- A group label with a colon or in another form, such as `**Planning:**`.
- A `## Screens` heading on a use case with no app screen.
- A module LLD of a multi-module design set with its scenario table inline instead of on a child page.
- An implementation-plan item deleted in a rewrite instead of moved to `implementation-notes.md`.
- An invariant, its id or a race outcome moved to `implementation-notes.md` instead of staying on a design page.
