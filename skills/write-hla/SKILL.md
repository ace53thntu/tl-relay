---
name: write-hla
description: Use when a new system, platform, or cross-service initiative needs a High-Level Architecture document, when a stakeholder asks for the "HLA" or "HLD" of something before build, or when an existing service set needs its topology, boundaries, and failure modes written down in one page.
---

# Write an HLA

## Configuration

Paths follow [config.md](../using-tl-relay/config.md): `<design root>` holds `designs/`, by default `<state_dir>/<workspace>/`. `knowledge_dir` has no default.
`<skill dir>` is this skill's base directory as the session reports it. `doc_budget.py` comes from the sibling skill `tl-design`. If `<skill dir>/../tl-design/scripts/doc_budget.py` is missing, stop and name `tl-design` with `npx skills add ace53thntu/tl-relay --skill tl-design`.

## Overview

One page, five sections in fixed order, with a use case tree: one page per use case under a use case container. An L1 HLA over module HLAs has no use case tree: its module HLAs hold the use cases. It records the system's boundaries, the decisions that shaped them, and how it fails. Reviewers read several of these, so the same thing sits in the same place every time.

An HLA written to an earlier version of this skill keeps its shape until someone rewrites it.

The Overview of a design set under `<design root>/designs/<handle>/` follows `write-design`, which cites this skill.

## Inputs to collect before writing

- System or service name
- Business context: every use case and its source, and the qualities the system must meet. A capacity figure is an input only when it changes a design choice.
- Constraints: infrastructure, stack, third-party boundaries

Missing an input? Ask. Do not open the document with a gap in this list.

## Skeleton

On the page, each numbered section is an H2 (`## 3. High-level design`) and each subsection an H3 (`### 3.1 …`).

The page opens with two or three sentences before section 1: what the system does or replaces, who uses it and when it ships, and the parts the page covers, such as its modules or its use case groups.

Then `## Terms`, before section 1: a bullet list `- **<term>**: <definition>`. It holds every design-set term that the HLA and its pages use. A design-set term is a word the HLA and its pages coin, or a common word they narrow to one meaning, used on at least two of those pages, such as Walk-in, book-again or reconciliation scan. A generic technical word, such as retry or webhook, is not one. A component name, such as callback route or polling activity, is not one either: pages link the component's own page or section. An entry names every role the HLA and its pages give the term: what it is, plus what it reads or writes when it matters. It copies no value another page owns, such as an id, an interval or a column list, and links that page instead. It is at most 30 words, term included. Other pages link a term to `<hla>.md#terms` on its first use, such as `[Walk-in](../hlds/<slug>.md#terms)`.

### 1. Requirements and scope
- `### Functional requirements` holds `**Core requirements**`, then a numbered list, one item per section 3 subsection except Final design, in the same order. Each item reads `<Actor> should be able to <job>.`, one to three sentences, in the words of its 3.N heading.
  - On an HLA with use cases, each item ends with its use case range, each id linking its use case page: `([UC-1](<slug>/use-cases/uc-1-….md) and [UC-2](…))`. A module HLA prefixes its ids with the module code, such as `PL-UC-1`. No two HLAs of a set share a UC id.
  - On an L1 HLA over module HLAs, one item per module, ending with the module's range linked to its section 1: `([PL-UC-1 to PL-UC-6](planning.md#1-requirements-and-scope))`. Every use case belongs to exactly one module HLA.
  - Section 1 holds no use case table. Each use case's name, actor, trigger and source live on its use case page.
- `### Non-functional requirements` holds `**Core requirements**`, then one bullet per NFR: `**NFR-n** <part> should <quality>, <bound> (<sources>)`. At most five, numbered `NFR-1` onward per HLA with no module prefix. The bound carries a number with its source, or `not measured`. An L1 HLA lists the NFRs its own deep dives cite, and each module HLA lists its own. Every citation of an NFR links the section 1 of the HLA that owns it, so `NFR-4` of two HLAs stay apart by link.
- Every ticket key in this section is a link, once per citation, followed by its criterion ids as plain text: `[PROJ-30108](https://tracker.example.com/PROJ-30108) N1, N6`.
- `### Out of scope`: two bullet lists. **Functional** names the features the design does not build. **Non-functional** names the qualities it does not target.
- Capacity: a figure appears only when it changes a design choice.

### 2. Core entities and API
- One line per core entity, with no columns in the line itself.
- With a schema page, the entity lines precede that page's `## Data model` body without its index tables: the labels and the `erDiagram` blocks. Each `erDiagram` keeps entity names, relationships, keys, and new and changed columns. It also keeps a new enum's values and the `existing columns "unchanged, not shown"` row, and no other column note. The column detail stays on the schema page.
- An optional `### <Entity> status` follows the data model for each entity whose lifecycle the design adds or changes. It holds one `stateDiagram-v2` with every status and transition. One sentence names who writes the status past its first state. One more names the stored time zone when the entity stores a date or time.
- Route table: `Method · Path | Caller | Purpose`.
- An L1 HLA over module HLAs: `### Core entities` is one bullet per module, `**<Module>:** <Entity>, <Entity>, …`. A table map follows: one Mermaid `flowchart TB` with one subgraph per module plus one for the existing tables it touches, each table a node by name only, a solid `---` line per foreign key and a dashed `-.-` line per column that names another table's row with no foreign key. One sentence under it states that legend, and one more links the schema page's `#data-model`. The L1 copies no `erDiagram` and no column. `### API` is one sentence linking each module HLA, which holds the routes.

### 3. High-level design
- One subsection per core requirement: `### 3.N <Actor> should be able to <job>`. A module HLA groups the use cases that share routes, at most five subsections. An L1 HLA takes one per module, in the order of its core requirements.
- An L1 3.N holds item 1 below only. One line then links the module HLA's section 3: `[Planning section 3](planning.md#3-high-level-design) holds the tables, the module steps and the request flows.` It has no diagram, request flow or note. Its 3.N Final design holds the one diagram.
- On a module HLA or an HLA with no module HLAs, each 3.N holds, in order:
  1. One or two sentences naming the main risk, with a link to the deep dive that owns it: `Two Portal tabs must not confirm over each other. … ([4.1](#41-…))`. An L1 HLA links the module HLA's deep dive. When no deep dive owns the step's risk, link the [failure-mode](#5-failure-modes-and-self-healing) question that does.
  2. A cumulative Mermaid diagram. Each later 3.N copies the previous diagram and adds to it. Start from this shape:

     ```mermaid
     ---
     config:
       flowchart:
         wrappingWidth: 400
     ---
     flowchart TB
       Client["Client<br/>Portal, App"] <--> BFF["<div style='text-align:left'><b>BFF entry</b><br/>- session<br/>- tenant<br/>- Cerbos check<br/>- routing</div>"]
       subgraph Mods["BFF modules"]
         direction LR
         PL["Planning"]
       end
       BFF <-->|"confirm(weekPlanId)<br/>move(stopId)"| PL
       Mods <-->|transaction| PG(("Postgres"))
       PG ~~~ Schema
       subgraph Schema[" "]
         direction LR
         T0["<div style='text-align:left'><b>week_plan</b><br/>- id<br/>- week_start<br/>- current_version</div>"]
       end
       classDef schema fill:none,stroke:none
       class T0 schema
       style Schema fill:none,stroke:none
     ```

     - The config block is YAML front matter, as above, not an `%%{init}%%` line.
     - Call labels name the module operation in function form. In-process calls between modules are edges inside `Mods`.
     - The `Schema` subgraph holds the tables the step writes or reads, each a free-text node. A table another module owns carries `(Module)` after its name.
     - An object store or third party appears in the step that moves data through it.
     - Default Mermaid style. No lane labels. Switch `Mods` to top-down when left-to-right passes about 2000 px.
  3. One request flow per actor whose flow differs, each of at most 7 steps. A flow reads `When <actor> <does X>:`, then numbered steps naming the endpoint from the contract or the route table, such as `The Portal sends POST /api/v1/week-plans/{weekPlanId}/confirmations with the version it read.` A step that does several things in one transaction reads `<Module>, in one transaction:`, with one sub-bullet per check or write.
  4. On an HLA with use cases, a `Use cases:` line linking each use case page the subsection covers.
  5. A step that depends on an unanswered question states only what the design holds. In a design set the question goes to the open points pages, as `tl-design` says, and an open value reads `<X> has no value yet`.
- The last subsection is `### 3.N Final design`: the topology as a Mermaid `flowchart TD` with every system boundary, ingress, worker, datastore and broker. A module HLA follows it with the service matrix `Service | Runtime and framework | Single responsibility | Inbound protocol | Outbound protocol | Storage engine`. One responsibility per row. Storage ownership is exclusive. A shared table is a finding, not a footnote. One closing sentence names what the deep dives cover.
- Each use case keeps its own page under the use case container. See [Use case pages](#use-case-pages). Section 3 links them. It holds no use case body and no use case index table.

### 4. Deep dives
- One subsection `### 4.N <question>` per decision, with no decision label in the heading. No section intro and no cap on the count. Order the deep dives from the outermost boundary inward: ownership and storage first, then the request flows.
- A decision picks between real alternatives at a component boundary: data ownership, the write owner across clients, the lifecycle engine, the concurrency or idempotency model, the offline protocol, the authorization model, or a storage model that is hard to reverse. It needs at least one rejected option the sources record.
- Every other ruling is a [module rule](#module-rules) in the LLD: a status list, a day cap, a notification path, a re-read rule, a timer, a read-model shape. A ruling the LLD already states gets no HLA text.
- Each deep dive holds, in order:
  1. One or two problem sentences. An NFR link may sit inside them: `Each person must resolve to one principal on both clients ([NFR-4](#1-requirements-and-scope)).`
  2. The dependency panel, only when the decision waits on an owner: `> [!WARNING]` opening `**Waits on:**`, naming the owner and what waits.
  3. The options as Bad, Good and Great solution panels, in this form:

     ```markdown
     ### 4.6 How does vendor status reach Marketplace?

     <one or two problem sentences>

     > [!CAUTION]
     > **Bad solution: <option name>**
     >
     > **Approach.** <what the option does>
     >
     > **Challenges.** <why it fails a requirement>

     > [!WARNING]
     > **Good solution: <option name>**
     >
     > **Approach.** <what the option does>
     >
     > **Challenges.** <the cost the Great solution avoids>

     > [!TIP]
     > **Great solution: <chosen option>**
     >
     > **Approach.** <the choice and the reason the source gives, at most 75 words>
     >
     > **Challenges.** <the costs of the choice, each keeping its scope qualifiers>
     ```

     - Exactly one Great panel: the chosen option. Its **Approach.** carries the choice and the reason the source gives for it, at most 75 words. Its **Challenges.** carries the costs the source records.
     - Bad and Good panels are the rejected options. Bad: the option fails a requirement. Good: it works but carries a cost the Great solution avoids. A deep dive holds at least one Bad or Good panel and at most four Bad and Good panels together. The Great panel is not counted.
     - An option comes only from a recorded alternative in the sources. Add no option the source does not hold. A decision whose sources record no rejected option is not a deep dive. It is a module rule.
     - Each panel's **Challenges.** is at most 50 words. Never merge two costs with different scopes. A cost another section holds is one clause with its link.
     - A **Challenges.** sentence keeps every scope qualifier its source states: the path, toggle, country, caller or state it applies to. It stays true when read alone.
     - Order: the problem sentences, the `**Waits on:**` panel when one applies, the Bad panels, the Good panels, then the Great panel.
  4. A diagram only when the source holds one, placed after the Great panel. Draw none otherwise.
  5. The assumption line, only when the decision rests on an unverified premise, after the Great panel: a plain paragraph `**Assumption:** … **Confirms:** <who settles it>.`
- A deep dive holds no **Rules.**, **Details:** or **Consequences.** block. The rules and the mechanism live in the LLD, which links the deep dive as its reason.
- A decision has no `Dn` id. Every page cites it by its deep dive: `[HLA 4.6](<hla>.md#46-…)` from another page, `[4.6](#46-…)` inside the HLA. A module HLA's deep dive is cited with its module name, such as `[Planning 4.2](planning.md#42-…)`. A decision that spans modules is a deep dive on the L1 HLA.
- Section 4 holds no `Other decisions` list and no decision summary table.
- A deep dive sits directly on the page, never inside an expand. Only section 5 answers use one.
- No function name, activity name or `path:line` citation in a deep dive. They belong to the LLD. An option a source names only by a function is described by its behaviour, with a link to the page that names it.
- A workflow id template, idempotency key, alert code or log reason that the decision fixes is a value, not a name. It stays.

### 5. Failure modes and self-healing
- One subsection per failure: `### 5.N What happens when <failure>?`, such as `What happens when Postgres is down?` or `What happens under a traffic spike?`.
- The heading stays outside any expand, so the Table of Contents and `#5n-…` links reach it. The whole answer sits in one expand titled `Behaviour and recovery`: one sentence of context, such as `Visit photos and signatures live only in S3.`, then **Behaviour** and **Recovery**:

  ```markdown
  ### 5.2 What happens when S3 is down?

  <details><summary>Behaviour and recovery</summary>

  Visit photos and signatures live only in S3.

  **Behaviour**

  - A completed visit waits in the outbox with its photos, and nothing reaches the BFF.

  **Recovery**

  - The outbox retries on its next drain.

  </details>
  ```
- Cover upstream spikes (rate limiting, load shedding), every downstream outage, and every single point of failure. Merge failures that share one cause or one recovery into one question. A section 5 holds at most 8 questions.
- Recovery names each pager alert or notification the operations team receives, by its name, in the 5.N answer itself. Alert names stay, and other detail moves to the overflow home. When the answer is still over its budget, the writer keeps the names and returns a question.
- Recovery states the bound or its absence: "no dead-letter queue", "no recovery SLA", "recovery not measured". State only the bound the source records. Where the source records none, write "not measured".
- Recovery states the automatic mechanism first: a retry, a fallback such as the Walk-in, a scan, or a timer. It states what the mechanism does, including any user notification it sends. Manual recovery and operations alerts follow. A Recovery with an automatic mechanism never opens with `None automatic` or an operations action.
- Every bound, status code and alert name the source records survives. A detail beyond the 5.N budget goes to the LLD section 6 or the execution logic page, and the answer links it.
- A failure every module meets, such as Postgres, the BFF or a traffic spike, is written once, on the L1 HLA. A module HLA keeps the question, and its context sentence links the L1 question. Behaviour and Recovery hold only the module's own bullets and any recovery bound the L1 question lacks. With none, the expand holds one paragraph instead: `The [overview page](yff-th.md#54-what-happens-when-postgres-is-down) holds this failure. <Module> adds no behaviour of its own.`

Never put the label "C4" in a heading.

## Output

- Path: `<runtime>/hlds/<slug>.md`. No date prefix. HLA pages are living and edited in place.
- Frontmatter as the existing HLD pages there: `type: HLD`, `title`, `description`, `tags`, `status`, `affects`, `generated`, `sources`. No `verified` key. Only a human adds one.
- Add an entry to `hlds/index.md` beside the page for the use case container, only when the page sits under `knowledge_dir`. An L1 HLA over module HLAs has no container entry.

### Use case pages

- An L1 HLA over module HLAs has no container and no use case page. Each module HLA has its own.
- The HLA title names the module in sentence case, such as `Example Visit execution`, the same phrase every page of the module uses. `write-lld` (Module name) states how to rename it.
- Container: `<slug>/use-cases/index.md`, titled `<HLA title>: Use cases`. Its body is one sentence linking the HLA's `#functional-requirements` and saying section 3 walks through the requests, then one link per use case page.
- Path: `<slug>/use-cases/uc-N-<use-case-slug>.md`, one page per `UC-n`.
- Frontmatter: `type: HLD`, `title`, `description`, `tags`, `status`, `generated`, `sources`. The first source is the HLA page.
- Title `UC-n <use case name>`, with the id and its module prefix if any. The name is a technical verb plus its object, such as `Get order attachments`, `List and view Kenya orders` or `Approve or decline a pending order`. The verb names the operation the system runs: Get, List, Create, Update, Delete, Upload, Approve, Decline, Retry, Sync or Block. A business verb such as Stage, Inspect, Resolve, Refuse or Record does not name the operation.
- Body: four bullets, **Input.**, **System action.**, **Result.** and **Source.** The input bullet names the actor and the route from the HLA route table. A use case with no route names the event or schedule that starts it. **Source.** cites a ticket or PRD, with every ticket key a link. A use case without a source does not belong in the HLA.
- Then a Mermaid `sequenceDiagram` with only the components that use case needs, and the state the use case changes: table, topic or workflow.
- A component needed for a quality, such as a cache or a queue, gets one line. The line links the deep dive on the HLA page that owns the component.
- `## Screens` sits directly before `## Decision`. Its screenshots come from the prototype site, one screen per image, never a design-tool export. It opens with "The prototype shows this use case on the screens below, numbered in flow order.", then each app label, the project's own app or portal name, such as `**Admin Portal**`, and its images from `use-cases/_screens/`: the phone frame only for an app, the portal window for a portal, saved at the capture's own size and never resampled, at most six per label. Leave out a screen that contradicts a decision, and say so in one note under the images. When the prototype shows no screen for the use case, the section holds one sentence that says so and why.
- The last section is `## Decision`. It holds only the choice no deep dive owns, so each decision has one home.
  - When a deep dive owns the use case's choice, the section is one sentence: `[HLA 4.8](../../<slug>.md#48-…) holds the decision and its rejected options.`
  - A use case may make its own choice, such as a cache or a start mechanism only it uses. The section then shows it in the deep dive panel form. It holds one or two problem sentences, then the Bad, Good and Great solution panels. It has no heading of its own.
  - When the use case uses a deep dive and also makes its own choice, one sentence links the deep dive first, then the panel form follows for its own choice.
  - A use case choice with no recorded alternative shows only the Great panel.
- The page repeats no requirement, entity list, route table or deep dive from the HLA. It links them.

### Module rules

- A module rule lives on its module's execution logic page, `lld/<module>/execution-logic.md`, under `## Rules` at the end of the page. One H3 per rule, named for what it governs, such as `### Stop event reasons` or `### Month lock`. A rule has no id.
- A rule states the behaviour and its consequences, in prose or bullets. No option panels, no **Context.** label. A fact the execution logic page already states is linked, not repeated.
- A rule may name the deep dive it follows from as its reason, such as `Reason: [HLA 4.3](…)`. A label in front of a link to a rule reads `Rule:`.

## Panels

A panel is a GitHub alert. The marker stands alone on its line.

| Panel | Marker | Holds |
| --- | --- | --- |
| Unbounded failure | `> [!CAUTION]` | A failure with no bound |
| Waits on | `> [!WARNING]` | A deep dive's `**Waits on:**` panel |
| Bad solution | `> [!CAUTION]` | A rejected option that fails a requirement |
| Good solution | `> [!WARNING]` | A rejected option that works but carries a cost the Great solution avoids |
| Great solution | `> [!TIP]` | The chosen option |

- A panel holds one or two sentences, with links outside the count. Solution panels hold the labelled paragraphs of the deep dive form instead.
- A panel, except a solution panel, restates a fact the page holds and adds none. The chosen option's costs stay in the Great panel's **Challenges.** A Bad or Good panel's **Challenges.** states why that option lost.
- At most one panel of each kind per section, except solution panels. A deep dive may also hold one `**Waits on:**` panel. A requirements panel carries no criterion citation.

## Budgets

`doc_budget.py` counts prose words. It skips frontmatter, fenced blocks, HTML comments, image lines and text between `contract:begin` and `contract:end`. Table text and text inside `<details>` count.

| Page | Budget |
| --- | --- |
| HLA page | 4,000 words |
| 3.N subsection, except 3.N Final design | 200 words |
| 4.N deep dive | 320 words |
| 5.N answer | 120 words, at most 8 questions |
| `## Terms` entry | 30 words |
| Great **Approach.** | 75 words |
| Panel **Challenges.** | 50 words |
| Use case page | 300 words |

Run `python3 <skill dir>/../tl-design/scripts/doc_budget.py <path>...` on every page written. It lists each violation and exits 1. `--json` prints the result as JSON.

The section budgets can add past 4,000. The page cap wins: merge deep dives that are module rules, and failures that share a recovery.

## Rules that apply to every section

- **REQUIRED SUB-SKILL:** `technical-writing` for prose and its House rules, then `unslop` when the session lists it (see `technical-writing`), then the Vale gate in `technical-writing`. Zero errors.
- **Technical wording, not narrative.** Headings are technical labels (`API changes`, not `Routes this
  design adds`). Body text uses technical terms, not colloquial phrases. Names use the operation and the code's own terms. See `technical-writing`, House rules.
- **State it, or state that it is absent.** Write what the code has. Where it has none, write "none" and whether this document adds it. Never fill a slot with a placeholder value the design did not decide.
- **Every claim about behaviour cites a file, a commit, or a ticket.** Read the code through `explore-codebase` before writing, not from memory.
- **Write "not measured" for a number you cannot source**, never an estimate dressed as a measurement.
- **A link replaces a fact only when the target page states that fact.** Before cutting a fact down to a link, open the target and find the fact there. When it is not there, keep the fact, or move it to the target first.
- **No table inside a list item**, on any page: a publish target can render it as a block with a scroll bar. A short list of names goes inline in one sentence.
- **Link a term on its first use.** `## Terms` on the HLA defines each design-set term once. Every other page links the term to `<hla>.md#terms` on first use and adds no inline gloss. The link text is the entry's term or its plural, such as `[book-again](…#terms)`, not an inflected verb.
- **A value the design leaves open is `<X> has no value yet`.** Never `No source sets <X>`, `The design does not fix <X>` or `<X>, not decided`. When a ticket holds a placeholder, quote it: `The vendor timeout has no value yet: PROJ-29798 AC 9 says "X minutes".` A number that exists but nobody measured stays `not measured`.
- **Challenges, Behaviour and Recovery say what happens, to what, and why.** Each sentence names the actor, the action and its effect. A bare noun phrase, such as `The reconciliation scan.` or `Idempotency by vendor event id.`, names a mechanism without saying what it does. A compressed clause, such as `The route has no commit to follow.`, leaves the consequence for the reader to infer.
  - A Recovery bullet names the mechanism, what it finds and what it does: `The reconciliation scan finds the active booking on the CANCELLED order and signals the cancel.`
  - A Behaviour bullet states the observable effect: `Example product shows a stale status until the polling activity reads the vendor.`, not `Status stays behind in Example product.`
  - A Challenges sentence states the cost and its cause: `The vendor call runs in the same request as the example-service submit, which already waits up to 1 minute.`, not `A second external call joins the 1-minute example-service wait.`
  - A sentence that restates itself (`Not measured, because capacity is not measured.`) names what is missing instead: `No load test has run the new routes at the NFR-1 peak.`

- **A restated bound keeps the kind its source gives it.** A wait bound (`waits up to 1 minute`) stays a wait bound. It never becomes a timeout, a race, a deadline or an SLA. A timeout never becomes a wait bound. The same holds for retries: `up to 3 attempts` is not `retries 3 times after the first`.

## Common mistakes

- `No source sets <X>` or `The design does not fix <X>` for a value the design leaves open, instead of `<X> has no value yet`.
- A topology diagram with every box and no boundary lines. The boundaries are the point.
- "Eventually consistent" with no stated window. Say how long, or say it is not bounded.
- Section 5 written as aspiration. It describes what exists, and it marks what the design adds.
- A `3.1 Use cases` index table.
- A cumulative diagram that drops the previous step's parts.
- An L1 3.N that repeats a module HLA's diagram, tables or request flow.
- A module failure question that restates the L1 HLA's Behaviour or Recovery.
- A section 5 written as a table or as Upstream / Downstream / SPOF lists instead of one question per failure.
- A section 5 answer outside its `Behaviour and recovery` expand, or a heading inside one.
- A 5.N Recovery that says `alerts operations` without the alert's name.
- A 5.N Recovery that omits or buries an automatic mechanism, such as a fallback, behind the manual or operations recovery.
- A wait bound or retry count restated as another kind, such as `waits up to 1 minute` written as `races against 1 minute`.
- A Challenges, Behaviour or Recovery line that is a bare noun phrase or a clause whose consequence the reader must infer.
- A new decisions page, a `Dn` id, or a link labelled `D7` or `Decision 7`. A decision is cited as `HLA 4.N`.
- A module rule written as a deep dive, such as a status list, a day cap or a lock date. It goes under `## Rules` on the execution logic page.
- A panel, except a solution panel, that adds a fact or repeats the paragraph next to it.
- A deep dive in the `**Decision.**` / `**Rejected.**` / `**Cost.**` form instead of solution panels.
- A Great panel whose **Approach.** drops the source's reason for the choice.
- A `## Terms` entry that names only one of a term's roles.
- A design-set term used on a page with no `## Terms` entry. `doc_budget.py` reports it as `term-missing`.
- A `## Terms` entry for a component name, or one that copies an id, interval or column list. `doc_budget.py` reports the second as `terms-value`.
- A fact replaced by a link to a page that does not state it.
- A Challenges sentence that drops the path, toggle, country, caller or state its source scopes it to.
- A rewrite that changes a heading and leaves links into its old anchor. Resolve every `<hla>.md#slug` link in the set against the new headings and summaries.
- A use case page that retells another. Each draws only its own path.
- A use case id that differs between section 1, section 3 and the page title.
- A use case named with a business verb, such as `Stage order documents` or `Inspect order documents`, instead of the operation, such as `Upload and delete order attachments` or `Get order attachments`.
- A use case table or an NFR table under [Requirements and scope](#1-requirements-and-scope). It holds Core requirements lists, and the use case pages hold the use case details.
- An HLA with no opening sentences before section 1.
- A ticket key in the requirements section with no link.
- Use case pages placed directly under the HLA instead of under the container.
- A use case on an L1 HLA that has module HLAs.
- An apposition for a term `## Terms` holds, or a component list in 3.N.
