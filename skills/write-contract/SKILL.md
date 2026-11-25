---
name: write-contract
description: Use when a module or feature needs an OpenAPI contract before its LLD, or when a design set reaches the design stage. Also use to check that a contract, its section 4 route table and its route pages agree. Writes OpenAPI 3.1 from the HLA routes and consumer jobs, renders LLD examples and runs check-contract.
---

# write-contract

## Configuration

Paths follow [config.md](../using-tl-relay/config.md): `<design root>` holds `designs/`, by default `<state_dir>/<workspace>/`. `knowledge_dir` has no default.
`<skill dir>` is this skill's base directory as the session reports it.

## Overview

A module's contract is the one source of every request shape, response shape, enum and error response. The LLD
says what each route means. The API page lists the routes. `check_contract.py` proves the three agree, and the
design stage cannot pass G-design until it exits 0 for every module.

## Where the files go

| Mode | Contract | Shared components | LLD and route pages | Route list |
| --- | --- | --- | --- | --- |
| Root | `<design root>/designs/<handle>/contracts/<module>.openapi.yaml` | `<design root>/designs/<handle>/contracts/common.openapi.yaml` | `<design root>/designs/<handle>/lld/<module>.md`, with route pages in the directory of the same name | `<design root>/designs/<handle>/lld/<module>-api.md` |

A route list is any Markdown table with a cell that starts with a method and a path, optionally in backticks.

## Procedure

```bash
SK=<skill dir>/scripts
```

1. Read the Overview, the route list, the shared components and the Overview's section 4 deep dives. Then
   read the screens, the `S-nn-ACm` register and the `T-nn` page, for the jobs each route serves.
2. For each route, name the screen and the criteria that call it. A route that no consumer calls is a question for
   the operator, not a shape to design.
3. Write the contract under the rules below.
4. Render the route pages and the common errors:

   ```bash
   python3 "$SK/render_lld.py" --contract <contract> --lld <lld> [--module <module>] [--common <page>]
   ```

   It creates a page under `<lld dir>/<module>/api/` for each route that has none, renders every block on the route pages, and renders the `common-errors` block on the `--common` page, or on `<lld dir>/<module>/interface-contracts.md` without it. In a design set with an API page, pass `--lld` and `--common` as `<lld dir>/<module>-api.md` with `--module <module>`. It writes only between markers on the `--common` page and never writes the LLD file. A common response is a response component that two or more routes reference. It appears in the common errors and on no route page.

   A render sets a route page's title only when it creates the page. It never retitles an existing page. After a `summary` changes, run the same command with `--retitle`:

   - It sets each route page's `title:` and H1 to `API 4.N: <METHOD path> - <summary>`, with no module prefix. It keeps the page's number.
   - It rewrites the link text of each renamed page on the `--common` page. The JSON output lists each rename under `retitled`.
   - Pages elsewhere that quote an old title as link text, such as the set's `index.md`, need the same edit by hand.

   A section 4 element that is not an API route, such as a Temporal workflow, has no contract operation. `render_lld.py` never creates or retitles its page. Write its title by hand as `<Kind> 4.N: <name> - <summary>`, with no module prefix, as `write-lld` (Child pages) states.

5. Write the section 4 route table, and the `**Rules:**` list on each route page, with `write-lld`, including its option rule. Add an index entry for each page step 4 created.
   The hand-written parts outside the blocks have this shape:

   - **Rules on a route page:**
     - The page follows the order `write-lld` section 4 sets: the H1, the seed sentence, `Use cases:`, `**Sequence:**`, the block, `**Rules:**`, `**Assumption:**` lines, then any Options form.
     - `**Rules:**` holds at most 5 bullets for any rule OpenAPI cannot express. Each bullet names the status it triggers, such as the 409, or the cross-field rule or message it covers. The block above already shows its body.
     - A route rule beyond five goes under `## Rules` on the module's execution logic page, and the route page links it.
     - Each field's meaning goes in its OpenAPI `description`, not in a list on the page. A response's remediation goes in its OpenAPI response `description`.
     - A behavioural rule a caller, QA or operations can observe never lives only in a `description`. Examples are precedence between two values, a log level operations relies on, and an action operations must take. It also gets a `**Rules:**` bullet, or a link to the page that states it.
     - Each body the contract does not render, such as an emitted message or event, is a `json` code block under `**Message · <topic>:**`.
   - **Shared route rules on the API page, or on `interface-contracts.md` in a set with no API page:** each body the page states, such as the request validator's, is a `json` code block under `**<Kind> · <writer>:**`.
   - **Sequence on a route page:** one Mermaid `sequenceDiagram` under the `Use cases:` line, above the block, as `write-lld` section 4 says.
   - A route number in either part appears only as a link to its route page, every time, outside a Mermaid block: `[4.3](4-3-post-...-approve.md)`. That covers repeat mentions in one sentence, list items and table cells.

6. Check, and fix what it reports until it exits 0:

   ```bash
   python3 "$SK/check_contract.py" --contract <contract> --lld <lld> --api <route list> [--module <module>] [--common <page>]
   ```

   Exit 3 means the gate's self-test broke. Stop and report it, and do not work around it.

| Check | Passes when |
| --- | --- |
| check1 | `@redocly/cli@2.52.1` lints the contract with `redocly.yaml` and exits 0, and both bundles succeed |
| check2 | Five sources list the same routes. They are the contract, the section 4 route table on the `--lld` page, the route list, the route page markers and the linked route pages. Each route page holds one marker |
| check3 | Every route page block and the `common-errors` block equal what `render_lld.py` renders now |
| check4 | Every 4xx and 5xx response has an example carrying an application error code |

## Contract rules

- Use OpenAPI `3.1.0`. A path writes parameters as `{name}`, never `:name`, and the route list uses the same form.
- The paths equal the route list exactly, including any version prefix the route list writes.
- Every operation has an `operationId`, a `summary`, `tags` and a `description` that names the LLD file and heading.
- Field names are camelCase. Every object schema sets `additionalProperties: false`.
- Every request body and every response carries an example. An error response carries one named example for each
  application error code.
- An application error code is upper snake case. A module's own codes start with its resource noun, for example
  `IMPORT_FILE_UNREADABLE`.
- Every route that requires a session references the shared `Unauthenticated` response for 401. A route
  that authenticates with a bearer header references `Forbidden` for 403, whether it reads or changes state. A route
  that reads a session cookie either takes the shared `CsrfToken` header parameter, or relies on an origin allow-list
  plus `SameSite=Strict`. Both reference `ForbiddenOrCsrfRejected`. The second takes no `CsrfToken`.
  A 401 means no valid session. A 403 means the policy denies a valid session, or a cookie-authenticated
  state-changing request lacks a valid CSRF token or comes from a disallowed origin. A route that runs before any session exists, such as sign-in,
  lists only the errors it can return.
- A list route references the `Page` and `PageSize` parameters, and returns `items`, `page`, `pageSize` and `total`.
- The root `security` is `session`, and `components.securitySchemes.session` references the shared scheme.
- Where the register gives a message, the example copies it word for word.
- A value that no source decides stays out of the schema. The LLD states it as a bold-labelled **Assumption:** paragraph, never in backticks.
  Otherwise the writer returns the question to the controller. The controller adds it to the set's open points pages, as `tl-design` says. No design page carries an inline
  open point or a link to the open points pages.

- An operation `description` states what the route does. It carries no `Proposed` marker, no ratification wait and
  no rejected alternative. A shape a source says awaits ratification goes into the contract as decided. The writer drops the
  ratification note. It goes on no page, into no open point and into no report.
- The LLD route page argues a rejected route or shape alternative in the form `write-lld` (Options) sets:
  `**Decision.**` ending with its `Decision:` or `Source:` line, `**Rejected.**` and `**Cost.**`. The form sits last on the page, after the `**Assumption:**` lines.

## Existing routes

A route that already runs in production code keeps its wire behaviour in the contract. Four contract rules above
apply only to a new route: upper snake case error codes, the shared `Unauthenticated`, `Forbidden` and
`ForbiddenOrCsrfRejected` responses, and root `security` `session`. An existing route keeps its own error codes, such as
integer codes, its own error envelope and its own security schemes. A code the design adds to an existing route takes
the route's existing code form. The operation `description` names the code baseline the contract follows.

## After G-design

A shape change edits the contract first. Then rerun `render_lld.py`, with `--retitle` when a `summary` changed, then `check_contract.py`.

## Rules

- Never edit between `contract:begin` and `contract:end`. The next render overwrites the edit, and check3 fails first.
- Design from the screens and the criteria, not from the database schema.
- **REQUIRED SUB-SKILL:** `write-lld` for the LLD prose, `technical-writing` for all prose, then `unslop`, then the Vale gate in `technical-writing`. Zero errors.

## Common mistakes

- Running Redocly without `redocly.yaml`. A wrong example is then only a warning, and lint exits 0.
- A 4xx response whose examples carry no `error.code`.
- One application error code for both 401 and 403.
- Renaming a route in the contract and leaving the route list or the LLD heading as it was.
- Changing a `summary` and rendering without `--retitle`. The route page keeps its old title.
- A `description` that marks a route or shape `Proposed`, says it awaits ratification, or lists the alternatives it beat.
