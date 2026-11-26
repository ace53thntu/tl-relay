---
name: write-task-breakdown
description: Use when a design set's design stage is signed and its task breakdown needs generating or checking. Generates the task tables in task-breakdown.md from the schema, route, element and use case pages, and checks that every task carries a man-day figure.
---

# write-task-breakdown

## Configuration

Paths follow [config.md](../using-tl-relay/config.md): `<design root>` holds `designs/`, by default `<state_dir>/<workspace>/`. `knowledge_dir` has no default.
`<skill dir>` is this skill's base directory as the session reports it.

## Overview

`task-breakdown.md` lists the tasks of a design set. It holds one `SCHEMA` task, one task per route, one task per section 4 element page, and one task per use case page with `## Screens`. `generate_breakdown.py` writes the tables. The writer proposes the figures, the tech lead confirms each, and the `tl-design` session writes them. `check_breakdown.py` fails until every task has one.

The `breakdown` stage starts after the tech lead signs `G-design`. Seven existing sets have no breakdown, and their stage is `n/a`.

## Task rules

`task-breakdown.md` holds frontmatter, an H1, free text the tech lead writes, and the task tables. The generator writes the tables between `<!-- breakdown:begin -->` and `<!-- breakdown:end -->`. It never touches text outside them. A new page takes its H1 from the Overview H1, else the Overview frontmatter `title`, else the handle. Nobody edits inside the markers by hand.

| Source element | Task id | Task name | Scope |
| --- | --- | --- | --- |
| `schema-changes.md` | `SCHEMA` | Create schema and config changes | The `## Data model` group labels and the name of each `## Config changes` entry: its bold or code lead, else its text up to the first period |
| Route page `lld/<module>/api/4-N-*.md` | `<module_code>-4.N` | The route page H1 (or frontmatter `title`), after ` - ` | `METHOD /path` |
| Element page `lld/<module>/<slug>.md` | `<module_code>-4.N` | The element page H1 (or frontmatter `title`), after ` - ` | `<Kind> <name>` |
| Use case page with `## Screens` | `UC-n`, or `<MODULE>-UC-n` in a multi-module set | The use case name | The app labels under `## Screens` |

- The generator does not parse SQL.
- An element page is a `.md` file directly in `lld/<module>/`, outside `api/`, as `write-design` sets. Its H1 reads `# <Kind> 4.N: <name> - <summary>`, such as `Workflow 4.N:`. `<Kind>` is one capitalised word other than `API`. An H1 with no ` - <summary>` gives the task the name `<Kind> <name>`.
- A page in `lld/<module>/` whose H1 does not match, such as `scenarios.md`, produces no task and no problem.
- Route and element tasks of a module sort together by N. When a route and an element page claim one id, the route keeps it and the check reports the element page.
- `module_code` comes from the `module_code:` frontmatter of `lld/<module>.md`.
- The name and scope come from the page H1, or from the frontmatter `title` when the page has no H1.
- A route H1 reads `# API 4.N: <METHOD path> - <summary>`. An H1 with no ` - <summary>` gives the task the name `METHOD path`.
- In a single-module set, a use case id is `UC-n`. In a multi-module set, the id takes the prefix from the use case file name, so `bk-uc-1-book.md` becomes `BK-UC-1`.
- Adding a second module renames every use case id. The old rows land under `Tasks without a source`. The tech lead moves their figures to the new rows and deletes the old rows.

The table columns are `ID | Task | Scope | Ticket | Design | Depends on | MD`. `Design` links the source page.

`Depends on` holds task ids and `DEP-n` links. A `DEP-n` renders as `[DEP-n](dependencies.md)`, with no fragment:

- A route or element task depends on `SCHEMA` in either of two cases:
  - a `**<its own module_code> · <name>**` label exists under `## Data model`, or
  - any `**Existing tables**` or `**Shared tables**` label exists.
- A UI task depends on each route task whose `METHOD /path` string appears in the use case page body.
- Any task depends on each `DEP-n` in `dependencies.md` whose `Blocked tasks` cell lists it.

## Commands

Run these from the set directory `<design root>/designs/<handle>`. Set `SK` and `CK` first.

```bash
SK=<skill dir>/scripts
CK=<skill dir>/../write-contract/scripts
```

Step 1 needs the sibling skill `write-contract`. If `$CK/render_lld.py` is missing, stop and name `write-contract` with
`npx skills add ace53thntu/tl-relay --skill write-contract`.

1. Retitle the route pages for each module with routes, so each H1 equals the OpenAPI `summary`:

   ```bash
   python3 "$CK/render_lld.py" --contract contracts/<module>.openapi.yaml --lld lld/<module>-api.md --module <module> --common lld/<module>-api.md --retitle
   ```

   Skip a module with no routes.

2. Generate the tables:

   ```bash
   python3 "$SK/generate_breakdown.py" --set .
   ```

   It creates `task-breakdown.md` when none exists. It stops with an error when an existing `task-breakdown.md` has no markers.

3. Check:

   ```bash
   python3 "$SK/check_breakdown.py" --set .
   ```

   It prints one problem per line, each starting with a task id, a page path or `set`. Exit 0 means no problem, 1 means at least one, and 2 means `--set` is not a directory.

| Message | Fix |
| --- | --- |
| `set: no tasks found` | Add route, element, use case or schema pages, or fix the page that hides them |
| `lld/<module>.md: no module_code` | Add `module_code:` to the frontmatter of the module page |
| `<path>: duplicate task id <id>` | Renumber the element page, or the route page that holds the id |
| `<path>: not a route page` | Move an element page out of `api/`, or fix the route H1 |
| `<id>: no man-day figure` | Fill `md` in the estimates file |
| `<id>: no source element` | Delete the row, or restore the page it came from |
| `<id>: man-day figure '<v>' is not in whole hours above 0` | Replace the figure with a man-day figure in whole hours, such as 0.5 |

## Estimates file

`task-breakdown.estimates.tsv` belongs to the tech lead. It has three tab-separated columns, `id`, `md` and `ticket`, with one row for each task id.

- The tech lead confirms every man-day figure. The writer proposes it, and the `tl-design` session writes it. The generator never writes `md`.
- A new task appends a row with an empty `md` and `ticket`.
- The generator never changes an existing row.
- A removed source element keeps its row. The page lists it under `Tasks without a source`, and the check fails until the tech lead deletes it.
- A figure passes when it is a man-day figure in whole hours above 0, such as 0.5, after the whitespace is stripped.

## Gate G-breakdown

`G-breakdown` passes when `check_breakdown.py` exits 0, and the tech lead has signed the gate.

The tech lead confirms each figure and the `tl-design` session writes it. The session then reruns the generator, runs the check, and the tech lead signs. The published page carries the MD and Ticket values.

## Rules

- Never edit between `breakdown:begin` and `breakdown:end`. The next generate overwrites the edit.
- Rerun the generator after any change to a route page, a use case page, `schema-changes.md`, `dependencies.md` or the estimates file. Two runs on unchanged input write identical files.
- Skills write no frontmatter that the publish command owns, such as a page id block, and run no push.
- **REQUIRED SUB-SKILL:** `technical-writing` for all prose, then the Vale gate in `technical-writing`. Zero errors.
