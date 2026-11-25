---
name: write-lld
description: Use when a story, feature slice, or endpoint change needs a Low-Level Design before implementation, when a ticket is `ready for LLD`, or when someone asks for the schema, contracts, concurrency model, or telemetry of a specific module in writing.
---

# Write an LLD

## Configuration

Paths follow [config.md](../using-tl-relay/config.md): `<design root>` holds `designs/`, by default `<state_dir>/<workspace>/`. `knowledge_dir` has no default.
`<skill dir>` is this skill's base directory as the session reports it. `doc_budget.py` comes from the sibling skill `tl-design`. If `<skill dir>/../tl-design/scripts/doc_budget.py` is missing, stop and name `tl-design` with `npx skills add ace53thntu/tl-relay --skill tl-design`.

## Overview

Seven sections in fixed order. The LLD fixes the module's contracts, state, concurrency model and failure handling. Pseudo-code, DDL, field mappings, per-country config blocks and the code changes belong to the implementation plan that follows (`write-plan`), as do tests and rollout: the file layout, the change order, the wiring, migration file names, versioning markers and replay test files.

A module LLD of a design set under `<design root>/designs/<handle>/` follows `write-design`, which cites this skill.

## Inputs to collect before writing

- Module: the component, service, or feature slice
- Stack: language, database engine, framework, cache layer, as found in the repo
- Requirements: functional scope, idempotency rules, performance SLAs, ticket keys

Missing an input? Ask. Do not open the document with a gap in this list.

## Skeleton

### 1. Component use cases and technical scenarios
- Scope: one sentence on the part of the HLA the module serves, then an **Out of scope** bullet list. No requirement list.
- Scenario table: `Scenario ID | Scenario name | Input condition | Expected system state or outcome`, at most 15 rows.
- Three rows are mandatory, by name: happy path, duplicate or replayed request, downstream timeout or degraded. If one cannot occur, keep the row and say why.
- Each element names the reason it exists, in a fixed slot. The reason is an HLA deep dive `4.N`, a module rule, a use case `UC-n`, an `NFR-n`, or a criterion id from the set's register. Delete an element with no reason. The elements and their slots are:
  - a table: the `NEW table` note in its `erDiagram`
  - a column: its `erDiagram` note
  - an index: its `Target query and justification` cell
  - a check constraint: the `erDiagram` note of the column it checks
  - a key-only table: the reason of its parent table
  - a route of section 4: the `Use cases:` line on its route page
  - an in-process interface of section 5: the deep dive, rule or use case its entry links
  - a metric or event of section 7: a reason clause on its bullet
- Exempt from the reason rule: log tags and log fields, trace spans, operator diagnostic queries, workflow patch markers, and replay fixtures and test files. They serve operation and testing, not a requirement. A metric is not exempt.
- Write an LLD only against an HLA in the five-section skeleton. An HLA without `UC-n` ids is rewritten first. An L1 HLA over module HLAs holds no `UC-n`: the LLD cites the use cases of its module HLA.

### 2. Execution and state diagrams
- Component flow: Mermaid `sequenceDiagram` through the layers the repo actually has (controller, service, repository, cache, database transaction).
- Entity lifecycle: Mermaid `stateDiagram-v2` with every state and transition, using the status vocabulary the code uses.

### 3. Data schema and indexing strategy
- Data model: an `erDiagram` with types, keys and a note on each new table and column. For MongoDB services, the document schema with field types. Match the engine the repo runs.
- Index table: `Index name | Columns | Target query and justification`. No index row without the query it serves.

### 4. Interface contracts and API specifications
- Without an OpenAPI contract: per endpoint, a JSON request and response with example values, each body under a `**<Kind> · <route>:**` label, then `**Rules:**` for what the JSON cannot express. JSON, not TypeScript interfaces. Protobuf only where the service already speaks gRPC.
- With an OpenAPI contract: section 4 is one sentence that links the API page `<module>-api.md`. The API page holds the route table `# | Route | Caller · tenancy | Page | Replay`, one row per route in number order. The Route cell links the route page `<module>/api/4-N-<method>-<slug>.md`.
  - Caller · tenancy: who may call the route, and how tenancy scopes the row. A 401 or 403 behaviour that differs from the common errors goes here.
  - Page: `none`, or the page parameters of a list route.
  - Replay: whether the route takes `Idempotency-Key`, and what a replay does without one.
- `write-contract`'s `render_lld.py` creates the route pages and renders the block between `<!-- contract:begin METHOD /path -->` and `<!-- contract:end -->` on each, and the `common-errors` block on the API page. Never edit inside a block. Write `**Rules:**` under the block on each route page. Section 4 has no per-route headings, no rendered JSON and no error table.
  - A route page holds, in order:
    1. The H1.
    2. The seed sentence `contract.py` writes.
    3. A `Use cases:` line linking each use case page that calls the route. It is the route's reason slot.
    4. `**Sequence:**`, when the route qualifies.
    5. The contract block.
    6. `**Rules:**`.
    7. Any `**Assumption:** … **Confirms:** …` lines.
    8. The Options form, only for a choice this route alone makes.
  - A field's meaning goes in its OpenAPI `description`, and a response's remediation in that response's `description`. Neither goes on the page.
  - A behavioural rule a caller, QA or operations can observe never lives only in a `description`. Examples are precedence between two values, a log level operations relies on, and an action operations must take. It also gets a `**Rules:**` bullet, or a link to the page that states it.
  - `**Rules:**` holds at most 5 bullets for any rule OpenAPI cannot express, such as what triggers a status, a cross-field rule or an emitted message. A body the contract does not render, such as a message, is a `json` block under `**Message · <topic>:**`.
  - A route rule beyond five goes under `## Rules` on the module's execution logic page, and the route page links it.
  - `**Sequence:**` appears only when the route has a branch beyond the common errors. It is one Mermaid `sequenceDiagram`, under the `Use cases:` line and above the contract block.
    - Participants are the caller, each hop that forwards the call, the service that owns the route, and each store or service the page names. They take the names the page uses.
    - Messages show each check a caller can observe, with its response. A check that runs under a lock follows the lock message, so a race stays visible. The full guard order stays in the implementation plan.
    - A check with its own response is an `alt` or `else` branch that ends in the status and application code, such as `MP-->>BFF: 403 7070`.
    - The shared 401 and 500 of the common errors stay out.
    - The diagram restates the block, the rules and the LLD. It adds no participant, call, check or code they lack.
    - A page section that already holds the route's sequence counts. A record or child page's sequence does not.
    - A route number inside the diagram is plain text, because Mermaid renders no links.
- Without a contract, each route or message has an error table: `HTTP code | Application error code | Remediation message`.
- Without a contract, four lines for each route, each stated or stated absent. With a contract, they are the route table columns:
  - Who may call it, and how tenancy scopes the row.
  - For a list, the page parameters and the page shape.
  - Whether it takes `Idempotency-Key`, and if not, what a replay does.
  - Which failure returns 401 and which returns 403.

### 5. Concurrency control and execution logic
- With an Execution logic page, section 5 is one sentence that links it, and the rules below apply on that page.
- Locking model in the code after the change: optimistic with version column, Redis lock with lease TTL, or row-level lock. Name which, or write "none" when there is no lock.
- Commit conditions of writers that compete for one row: a Mermaid `stateDiagram-v2` of the row's states, not one bullet per writer.
  - Each state names its stored values, such as `INIT, erpOrderStatus FAILURE`.
  - Each transition is a writer.
  - Each refusal code sits in a note on the state that refuses.
  - One sentence above the diagram names the lock every transition runs under.
  - At most three labelled bullets under it hold what the diagram cannot draw: refusals outside the drawn states, a state's extra admission, a freshness window.
- Idempotency: key generation rule, deduplication store, window and TTL.
- Invariants: rule bullets, one per rule, naming the actor or the route, the condition and the result. A refusal cites the contract's error code or the section 1 scenario id it covers. Guard order and pseudo-code belong to the implementation plan.
  - An invariant or race outcome keeps its id and stays on a design page. It goes on the route page `**Rules:**`, or in the execution logic `## Rules` with a link when the cap is full.
  - A writer never cuts an invariant or race outcome. When both caps are full, it keeps the invariant and returns a question naming the page and the invariant.

### 6. Edge cases, timeouts, and retries
- Downstream client timeouts: connect, read. Cite the config file that holds them.
- Retry policy: maximum count, backoff multiplier, jitter range. Cite where they are set.

### 7. Telemetry and observability
- Metrics the design adds: `Metric name | Type (counter, gauge, histogram) | Labels`.
- Structured log fields added or required.

Exactly these seven top-level sections. A citation goes inline where the claim is. There is no Code references section.

### Child pages

A long LLD may move these blocks onto child pages of the LLD. The parent keeps all seven section headings. An LLD has no traceability page and no code changes page.

A long LLD may move section 5 to `lld/<module>/execution-logic.md`, titled `<LLD title without "LLD"> execution logic`. When the module name already ends in "execution", the title keeps one, such as `Example Visit execution logic`. Body: one sentence linking `../<module>.md#5-concurrency-control-and-execution-logic`, then the section's blocks in order. Relative links gain one `../`. The page ends with `## Rules`, which holds the module rules in the form `write-hla` (Module rules) sets. A module with no Execution logic page keeps its rules at the end of section 5.

| Child page | Holds | The parent keeps |
| --- | --- | --- |
| Scenarios | The section 1 scenario table | A `Scenarios:` line with the link |
| API | Section 4 in full: token checks, route table, error codes, shared route rules, then `## Common errors`. It replaces `interface-contracts.md`, and the route pages are its children | One sentence under section 4 that links it |
| Schema | The `erDiagram` per group and the index tables | Only the `Schema:` line with the link |
| Execution logic | Section 5 in full: the locking model and commit conditions, idempotency, stored rows, the Shared logic line (`write-design`), invariants, assumptions, key expiry and in-process interfaces | One sentence under section 5 that links it |

- The route pages are direct children of the API page, in route number order. No group page sits between them. A route page's own children stay under it.
- The use case pages name the routes each use case calls. The API page carries no use case grouping.
- Number the routes `4.1` to `4.N` in call order when they are first published. A later change keeps the published numbers.
- **Module name.** Every page of a module names the module with one phrase, in sentence case: the first word capitalised, the rest as written, such as `Example Visit execution` or `Example Planning`. The phrase opens the titles of the HLA, its Use cases page, the LLD, its scenarios and execution logic pages and the API page. A route page's title carries no module name.
  - To rename a module, replace the whole phrase on every page of the set: titles, H1s, link texts, `index.md`, `sources` titles and the contract descriptions. Then run `render_lld.py --retitle --check` for the module, which must report up to date.
- A route page's title is `API 4.N: <METHOD path> - <purpose>`, for example `API 4.5: POST /admin/purchases/{orderId}/decision - Approve or decline an order`. The purpose is a short verb phrase of at most eight words. A route with no HTTP path, such as a message consumer, carries the purpose alone.
- A section 4 element may move onto a direct child page of the LLD when it is not an API route. Temporal workflows, updates and activity modules are such elements.
  - Its title is `<Kind> 4.N: <name> - <summary>`, for example `Workflow 4.1: pickupBookingThWorkflow - Run one booking attempt`.
  - `<Kind>` names the element type, such as Workflow, Update, Activity, Notification or Helper. `<name>` is the code's own name for the element.
  - The summary follows the purpose rule for route pages. The title carries no module name.
- `render_lld.py` builds the title from the operation's OpenAPI `summary` when it creates the page. Write each `summary` as the purpose before the first render. After a `summary` changes, render with `--retitle`, as `write-contract` states.
- Every reason and scenario rule above still applies on the child page.
- Moving a block changes its anchors. Retarget every inbound link in the set.

**The API page** holds what two or more route pages share, and nothing a single route page already states:

- A route number appears only as a link to its route page: `[4.2](<module>-api-delete.md)`, every time. That covers repeat mentions in one sentence, and numbers in prose, table cells, panels and `Assumption:` lines. A range links both ends. A route with no page goes by its method and path, never a number.
- The error table lists a code only when two or more route pages answer it, or when its route has no page. Every other code sits in its route page's error table. One sentence after the table says so.
- One table per mapping. Two tables keyed by the same routes merge into one, and rows whose cells are equal merge into one row.
- A paragraph that another page already holds becomes one sentence that links that page.
- **A link replaces a fact only when the target page states that fact.** Before cutting a fact down to a link, open the target and find the fact there. When it is not there, keep the fact, or move it to the target first.

- No table inside a list item on any design page: Confluence renders it as legacy content with a scroll bar. A short list of names goes inline in one sentence.

**The Schema page** holds the data model diagrams and the index tables. It has one section, `## Data model`, and no table of changes, no purpose tables, no DDL and no migration order section:

- Every name is the database name: the table, the column, the enum type as Postgres knows it. Never an ORM model or enum name, and never a code symbol.
- `## Data model` holds one `erDiagram` per group, each under a bold label:
  - **Existing tables**: every existing table the design changes, with only the changed and referenced columns, then `existing columns "unchanged, not shown"`.
  - **Shared tables**: every new table whose rows another module's columns name, with all its columns.
  - One diagram per module, with the tables only that module uses. A shared or existing table its tables reference appears by its key alone, noted `shared table` or `existing table`.
- Each entity lists its columns as `type name KEY "note"`, keys `PK`, `FK`, `UK`. A note carries the reason the column exists, the enum values, the check, or the constraint behind a `UK`. `NEW table` on the primary key of a new table, with the reason the table exists. `NEW column` or `NEW value` on each change to an existing table or enum.
- A solid line is a foreign key. A dashed line is a column that names another table's row with no foreign key, labelled `<table>.<column>, no FK`. Any other label states what the rows are to each other, plus `CASCADE` where the foreign key cascades.
- Render each diagram and look at it. Reorder the entities and relationship lines until no line crosses a line or a box.
- Under each module group's diagram, the index table `Index name | Columns | Target query and justification` with every index the module's queries use. An index of a shared or existing table goes under the module that owns its query.
- The HLA section 2 shows a trimmed copy of the `## Data model` body, without the index tables, as `write-hla` section 2 states.

### Options

A lock model, a retry policy and a route shape are choices an LLD owns. When the LLD weighs options for such a choice, it uses this form: one or two problem sentences, `**Decision.**`, `**Rejected.**` and `**Cost.**`.

- `**Decision.**` ends with the choice's source as its last sentence: `Decision: [HLA 4.N](…)` when an HLA deep dive records the choice, or `Rule: [<rule name>](…)` when a module rule does, adding `, with [HLA 4.M](…)` for each further deep dive. A choice this LLD makes alone ends with `Source: [PROJ-40001](https://example.atlassian.net/browse/PROJ-40001)`, a Jira key always as a link, or a link to the analysis the LLD records.
- The reason a source gives for the choice goes into `**Decision.**`, at most 75 words.
- `**Rejected.**` holds one bullet per recorded option, at most 3: its name and the source's rejection reason in one sentence, with no mechanism the source does not state.
- `**Cost.**` holds one bullet per cost the source records, at most 30 words each. Never merge two costs with different scopes. A single cost may be one unbulleted paragraph of at most 30 words. A cost another section holds is one clause with its link.
- A cost bullet keeps every scope qualifier its source states: the path, toggle, country, caller or state it applies to. It stays true when read alone.
- A diagram for the choice goes after `**Cost.**`.
- The options appear only under `**Rejected.**`. No list, table or paragraph outside it repeats an option.
- An option comes only from a source: an HLA deep dive's rejected option, a ticket, or an analysis this LLD records with its evidence.
- A choice the HLA owns is not argued again. The LLD links the HLA deep dive.
- A choice with one recorded option has `**Decision.**` and `**Cost.**` only.

### Status of a choice

An LLD records the design as decided. It carries no `Proposed` marker, no ratification wait and no `ships before it is ratified` sentence. A source note that a choice waits on Solution Architecture or another reviewer to ratify it is dropped, and the choice reads as decided. Only a choice another team builds is an external dependency. The LLD states it once, names the team, and states what this module does until it lands.

There is no Assumptions section. An unverified premise is written inline in the section that depends on it, prefixed `Assumption:`, with what would confirm it.
Write it as a plain paragraph with bold labels: **Assumption:** the premise. **Confirms:** who or what settles it.
Never wrap the line in backticks. A code span publishes to Confluence as code.

## Output

- Path: `<runtime>/plans/lld/YYYY-MM-DD-<slug>.md`.
- Frontmatter from `<knowledge_dir>/_templates/plan.md` when `knowledge_dir` is set and the file exists, else written inline: `type: LLD` and `affects`. `affects` lists every repo the change touches code in. That list drives the knowledge refresh after the work ships.
- Add an entry to `plans/lld/index.md` beside the page, only when the page sits under `knowledge_dir`. Its description string equals the page's `description` exactly. `lint.sh` compares them.

With a contract, the route pages sit in `lld/<module>/api/`, children of the API page `lld/<module>-api.md`.

## Panels

The publish tool renders a GitHub alert as a Confluence panel. The marker stands alone on its line.

| Panel | Marker | Holds |
| --- | --- | --- |
| Info | `> [!NOTE]` | The scenario or the risk a section answers, stated once at its top |
| Warning, red | `> [!CAUTION]` | A failure with no bound, such as no expiry, no alert or no retry |
| Note, yellow | `> [!WARNING]` | A fail-closed adapter, an external dependency not yet in place, or a `**Waits on:**` line |

- Every panel holds one or two sentences, with links outside the count.
- A panel restates a fact the page holds and adds none. A cost stays in **Cost.**, not in a panel.
- At most one panel of each kind per section. An `Assumption:` line stays a plain paragraph, not a panel.

## Budgets

`doc_budget.py` counts prose words. It skips frontmatter, fenced blocks, HTML comments, image lines and text between `contract:begin` and `contract:end`. Table text and text inside `<details>` count.

| Page | Budget |
| --- | --- |
| LLD parent page | 1,200 words |
| API page | 800 words |
| Execution logic page | 1,000 words, plus 800 for `## Rules` |
| Element page (workflow, activities, notifications, reconciliation) | 600 words |
| Route page | 300 words |
| Schema page | 600 words |
| Scenarios page | 15 rows per table |
| `**Decision.**` | 75 words |
| `**Cost.**` bullet | 30 words |

Run `python3 <skill dir>/../tl-design/scripts/doc_budget.py <path>...` on every page written. It lists each violation and exits 1.

## Rules that apply to every section

- **REQUIRED SUB-SKILL:** `technical-writing` for prose and its House rules, then `unslop`, then the Vale gate in `technical-writing`. Zero errors.
- **Technical wording, not narrative.** Headings are technical labels (`API changes`, not `Routes this
  design adds`). Body text uses technical terms, not colloquial phrases. Names use the operation and the code's own terms. See `technical-writing`, House rules.
- **State it, or state that it is absent.** Write what the code has. Where it has none, write "none" and whether this document adds it. Never fill a slot with a placeholder value the design did not decide.
- **Every claim about behaviour cites a file, a commit, or a ticket.** Read code through codegraph before writing, not from memory.
- **On the API page, a request, response or message body is a `json` code block** under a bold label, `**<Kind> · <writer or route>:**`, with example values from the contract or the code. A route page's contract block is rendered, and a message body there takes the same label. A table cell that needs a body links the block.
- **Bullets, not tables, outside the mandated tables.** This skill fixes the scenario, route, error and index tables. Every other table on an LLD page becomes bullets:
  - Each bullet opens with a bold label that names its row key: the writer, the span kind, the country, the case. The rest is one or two sentences that hold the condition and the result, such as an error code.
  - A mapping of three rows or fewer becomes one sentence.
  - Rows whose cells are equal merge into one bullet, such as `**Thailand and Malaysia.**`.
  - A citation column (`Where`, `Reference`, `Sample`) goes. A location the reader needs moves into the sentence. A `none` or `unchanged` cell goes.
  - A per-route or per-step table that serves one operation, such as a rollback, moves to the child page that holds the operation. The parent keeps one summary sentence and the link.
- **Rules, not narrative.** A paragraph that walks through events (`asks … instead`, `Until …`, `If … or it can end …`) becomes rule bullets under a bold label that names the case, such as `**Cancelling a Kenya order while the path is on**`. One rule per bullet: the actor or the route, the condition, the result. A sentence the paragraph held just above the label joins the list as its first bullet.
- After a table becomes bullets or moves, read each inbound link's sentence. A claim such as "the rollback table states" turns false, so retarget or rewrite it.
- **Link a term on its first use.** `## Terms` on the HLA defines each design-set term once. Every other page links the term to `<hla>.md#terms` on first use, such as `[Walk-in](../hlds/<slug>.md#terms)`, and adds no inline gloss.
- **A value the design leaves open is `<X> has no value yet`.** Never `No source sets <X>`, `The design does not fix <X>` or `<X>, not decided`. When a ticket holds a placeholder, quote it: `The vendor timeout has no value yet: PROJ-29798 AC 9 says "X minutes".` A number that exists but nobody measured stays `not measured`.
- **Write "not measured" for a number you cannot source**, never an estimate dressed as a measurement.

- **A restated bound keeps the kind its source gives it.** A wait bound (`waits up to 1 minute`) stays a wait bound. It never becomes a timeout, a race, a deadline or an SLA. A timeout never becomes a wait bound. The same holds for retries: `up to 3 attempts` is not `retries 3 times after the first`.

## Common mistakes

- A design-set term, such as Walk-in or book-again, glossed inline instead of linked to the HLA `#terms`.
- A fact replaced by a link to a page that does not state it.
- `No source sets <X>` or `The design does not fix <X>` for a value the design leaves open, instead of `<X> has no value yet`.
- A traceability page or a code changes page under an LLD. Code changes belong to the implementation plan.
- A TTL, a retry count, or a metric name that exists nowhere in the repo and was not decided in this document.
- Foreign keys drawn for a MongoDB collection.
- A state diagram whose states do not match the enum in the code.
- Section 1 with a happy path only.
- Group pages between the API page and its route pages.
- A module name written two ways across its pages, such as `visit execution` on the HLA and `Visit execution` on the API page.
- A wait bound or retry count restated as another kind, such as `waits up to 1 minute` written as `races against 1 minute`.
- Editing the JSON between `contract:begin` and `contract:end` instead of the contract.
- A route page titled by method and path alone, with no purpose.
- A section 4 element page whose title opens with the module name instead of `<Kind> 4.N:`.
- A table, route or metric that names no reason.
- A reason for a log field, span, patch marker or test fixture. They are exempt.
- A reason whose id exists in no source.
- A table this skill does not mandate, such as a country matrix, a writer and commit-condition table or a `Change | Where` table, instead of labelled bullets.
- A behavioural rule stated only in an OpenAPI `description`, which the rendered route page does not show.
- A paragraph that tells a sequence of events where a list of rules belongs.
- Competing writers' commit conditions as one bullet per writer instead of a state diagram of the row.
- An LLD that argues a choice the HLA already owns.
- A `Proposed` marker, a `ratifies` sentence or a `ships before it is ratified` line.
- A panel that adds a fact, repeats the paragraph next to it, or wraps an `Assumption:` line.
- Pseudo-code, a guard table, DDL, field notes, screens on a route page, or Bad, Good and Great panels on an LLD page.
