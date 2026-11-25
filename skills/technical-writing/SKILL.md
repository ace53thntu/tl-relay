---
name: technical-writing
description: Use when writing or reviewing any prose deliverable (wiki pages, LLDs, specs, plans, ADRs, RFCs, readmes, PR descriptions, commit messages, status reports). Also use when a doc tries to teach and reference at the same time, when sentences run long, or when a page has drifted into a mix of tutorial and API dump.
---

# Technical writing

## Overview

Four layers, narrowest last: pick the document's **mode**, write **Google-style** sentences, obey **STE** instruction rules, keep the syntax **globally readable**.

Three rules override everything below:

1. Cut every word that does no work.
2. Use the short everyday word.
3. **Never let a rule make a sentence worse.** If applying one degrades the sentence, the rule is wrong for that sentence. Fix it another way.

**Companion skill:** run `unslop` over anything this skill touches. This skill sets structure, and `unslop` removes the AI fingerprint.

## Layer 1: Diátaxis, one mode per document

| Mode | Serves | Reader is |
|---|---|---|
| Tutorial | Learning + doing | Following along, does not know what they need |
| How-to | Working + doing | Has a goal, needs the steps |
| Reference | Working + understanding | Looking one thing up |
| Explanation | Learning + understanding | Wants the why |

**Never mix modes in one document.** This is a common defect in internal wikis. A page opens as explanation, turns into a how-to halfway down, then ends as an API dump. Every reader is served badly. Split it.

Quick test: if you cannot say which single mode a page is in, that is the finding.

**Design documents are Reference, not Explanation.** A reviewer looks up one fact in an HLD, HLA, LLD, spec, contract page, ADR or
decision page. Nobody reads it front to back. An audit,
postmortem or spike is Explanation, and even there the reader wants the finding first. Neither is a
story.

## Layer 2: Google style

- Address the reader as **you**
- **Active voice**, named actor: "the scheduler retries" not "retries are performed"
- Instructions are commands, not hedged statements: "Set the flag" not "the flag should be set"
- **Condition before the instruction.** Write "If the build fails, clear the cache" and not the reverse. The reader must know whether the step applies before reading it.
- Common case first, edge cases after
- Sentence-case headings that carry the point ("Why bookings double-fire" beats "Overview"). In a
  design document the heading is a technical label instead. See "Technical wording" under House rules.
- No "click here" links. The link text says what it links to.
- Numbered lists only for real sequences

## Layer 3: STE instruction rules

- One instruction per sentence
- **20–25 word ceiling.** Over that, split.
- Warnings go **before** the step they guard, never after
- Keep articles. Write "the flag" and not "flag"
- One word per action, reused: do not alternate delete/remove/drop for the same operation
- Avoid `-ing` forms where a plain verb works

## Layer 4: Global English

Most readers of these docs are not writing in their first language. Ambiguity costs them more than it costs you.

- Keep **only** and **not** next to what they modify
- Break long noun strings: "booking notification service name resolution failure" → say it as a clause
- Every pronoun has one obvious referent. When in doubt, repeat the noun.
- Do not drop verbs in parallel clauses
- No slashes for and/or
- Periods, not semicolons or em dashes
- **One name per concept** across the whole doc set. Not booking/appointment/service order for the same thing.

## House rules

House rules, from explicit user feedback. These override the generic layers where they conflict.

**Everywhere:**

- **Diagrams are Mermaid** (`stateDiagram-v2`, `sequenceDiagram`, `flowchart`), in a fenced block. Never ASCII art, because it does not render in their viewers. Mermaid is the source. A rendered image is a derivative, never the record.
- **No line numbers** in file references. Write `src/foo/bar.ts`, not the same path with `:42-90` after it. They rot within a week.
- **No open-questions or follow-ups section** unless asked. Resolve it, or state the decision and its assumption.
- **No print-typography cross-refs.** `§4.2` and `see section 4.2` are dead text in Markdown. Use a GitHub anchor link with descriptive text: `[Eligibility rules](#42-eligibility-rules)`. The slug is the lowercased heading, with punctuation stripped and spaces turned into dashes. In Obsidian, `[[file#heading|alias]]`. Descriptive text survives renumbering, and a bare number does not.
- **Dense paragraphs, not nested bullet trees.** For invariants, notes, and decision callouts: one tight paragraph per item, rule plus enforcement plus key edge in one breath. Do not use the `*Intent:* … *Enforcement:* … *Edge:*` scaffold. It triples the length without adding clarity. If the chat explanation read fine as bullets, the doc version should be tighter than that, not twice as long. A set of parallel rules or cases is the exception: write a flat list, one bullet per rule, each opening with a bold label and holding one or two sentences. Never nest the list.
- **A rule set, not a story.** A paragraph that narrates events (`X asks, and Y does Z instead. Until …, … If …, or it can end …`) states rules in disguise. Rewrite it as one bullet per rule: the actor, the condition, the result.
- **No storytelling.** Cut any sentence that sets up the next one instead of carrying a fact:
  `Two facts the boxes cannot show.`, `What Kenya needs is narrower than it looks.`, `One guard is
  weaker than it looks.` Cut the reveal. State the finding, then its evidence, never evidence then
  twist. Cut process narration: `the rubric asks`, `this review found`, `we then checked`. The reader
  wants the conclusion, not your path to it. Cut the dramatic one-line paragraph. Test: delete the
  sentence. If no fact is lost, it was scaffolding, not content.
- **Technical wording, not narrative, in design documents.** A heading is a technical label that
  names the change or the component: `API changes`, `Schema changes`, `Kenya order approval`,
  `Decision 9: approval wait stored as a row, not a workflow execution`. It is never a narrative
  sentence, such as `Routes this design adds`, `A reviewer approves, and only then does the ERP see the
  order` or `What the next country costs`. In the body, replace a colloquial phrase with the technical
  term. `for as long as it takes` becomes `no time bound`, `waits for a human` becomes `waits for
  review`, and `a query this design owes a home` becomes `the query has no owner`. A use case body is
  three bullets: input, system action, result. The one-line use case in an HLA requirements list is
  not a body. A renamed heading changes its anchor. Grep the doc set for
  the old anchor and fix every link in the same pass.
- **Names use the operation and the code's own terms.** This covers titles, headings, use case names, solution
  titles, task names and table row labels.
  - An action name starts with the technical verb the system runs: Get, List, Create, Update, Delete, Upload,
    Approve, Decline, Retry, Sync or Block. `Stage order documents` becomes `Upload and delete order attachments`, and
    `Inspect order documents` becomes `Get order attachments`.
  - A state or entity takes the name the code gives it, such as a status value, a table or a column. Do not invent a
    business term for it. A row the code marks `UPLOAD_REQUESTED` with no order is an `unlinked attachment`, not a
    `staged document`.
  - A heading names the component, not the event around it. `The type change` becomes `ICountry dos field`,
    `Left off the policy` becomes `Settings outside the country policy`, and `Known limits` becomes `Limitations`.
- **`unslop`'s "Add voice" section does not apply to a design document.** Run the three Scan sections
  of `unslop`. Stop before the "Add voice" section. Opinion, varied rhythm and deliberate mess suit
  chat and a PR description. In an HLD they put the narrative back.
- **No time-markers.** Present tense already means now. Cut `today`, `currently`, `at present`, `right
  now`, `at the moment`, `so far`. Where a sentence genuinely contrasts before against after, name the
  condition that ends it, not the date. `a no-op while one builder is registered` beats `a no-op today`.
  A doc read six months later is wrong about `today` and still right about the condition.
- **Real paths, symbols, and counts only.** A number that came from a command keeps that command in
  the audit or plan that measured it, so it can be regenerated. A published design page states the
  count as a plain fact. That covers an HLA, LLD, contract, open points page or task breakdown. It
  carries no `grep`, `jq`, `wc` or `git` command, and no "run at the repository root" narration.
- **PR descriptions and commit messages are documents too.** They follow the repo's Conventional Commits limit of one line under 72 characters.
- **Output targets** for specs, plans, LLDs, audits, ADRs, and glossary terms live in the "Skill output targets" section of the workspace `CLAUDE.md`. Without that section, audits go to `<runtime>/audits/`, ADRs to `<knowledge_dir>/wiki/decisions/` and glossary terms to `<knowledge_dir>/wiki/glossary.md`; with `knowledge_dir` unset, skip the ADR and glossary writes and say so in one line. Specs, plans and LLDs keep their writer skills' default paths. `<runtime>` and `knowledge_dir` follow [config.md](../using-tl-relay/config.md). Do not invent a location.

**LLD-specific:**

- **Endpoint summary tables.** With an OpenAPI contract, LLD section 4 is the route table `# | Route | Caller · tenancy | Page | Replay`, and each Route cell links the route page. Without a contract, the table is `# | Method · Path | Caller | Purpose`. **No `Auth` column** when every row would hold the same value. State it once in the section intro.
- **Per-endpoint `### Request` sections use JSON, not TypeScript interfaces.** Show a JSON object with example values under a `**<Kind> · <name>:**` label. For GET, the JSON is the parsed query and path params (csv enums as `"<uuid>,<uuid>"`). JSON is framework-agnostic, example values read better than type annotations for reviewers, and it composes with the response JSON block below it.

**HLA and LLD content:**

- **State it, or state that it is absent.** For schema, indexes, contracts, locking,
  idempotency, timeouts, retries, metrics, rate limits, circuit breakers, and dead-letter
  queues: write what the code has. Where the code has none, write "none" and whether the
  design adds it. Never supply a placeholder value (a TTL, a backoff multiplier, a metric
  name) the design did not decide. A check of eighteen hub pages against code found an error on
  every one, several of them facts that exist nowhere in the source. A
  mandatory section with nothing real to fill it is where those come from.
- **Every decision names its cost.** A Decision or ADR without the rejected options and the
  drawbacks of the chosen one is unfinished. An HLA's section 4 deep dive gives each decision its
  problem sentences, then `**Decision.**`, `**Rejected.**` and `**Cost.**`, with no status, as `write-hla` section 4 sets out. An ADR under `<knowledge_dir>/wiki/decisions/` keeps its own shape (Decision,
  Context, Options considered, Consequences, Code references). Do not import another layout. A ruling with no rejected option is a module rule in the LLD.
- **Three execution paths, by name:** happy path, duplicate or replayed request, downstream
  timeout or degraded. If one cannot occur, say why in a sentence rather than omit it.
- **Every use case names the actor, the trigger, and the business outcome.** An HLA use case
  missing one of the three is a feature list, not a use case.
- **Every index names the query it serves.** No index row without the query pattern that
  justified it.
- **Pick the diagram by what it shows:** service topology → `flowchart`, a cross-service
  call → `sequenceDiagram`, an entity lifecycle → `stateDiagram-v2`.

## Vale gate

Vale checks the rules that a pattern can express. Run it on every document you write or edit, after `unslop`. The `vale.vocab` key in `.tl-relay/config.yaml` names an extra vocabulary file, unset by default. Pass its path as the `TL_RELAY_VALE_VOCAB` prefix shown below, because each Bash call starts a fresh shell. Resolve a relative `vale.vocab` path against the workspace root, and pass the absolute path. The wrapper then accepts the words in that file, and ignores it when it is unset or missing. That vocabulary also silences error-level rules, so never add a word there to pass the gate:

```sh
TL_RELAY_VALE_VOCAB=<vale.vocab path> sh <skill dir>/vale/run.sh <file>
```

- **Error:** fix every one. Vale exits non-zero while one remains.
- **`E201`:** Vale could not parse the frontmatter and checked nothing. Quote the frontmatter value that holds a colon, then run again.
- **Warning:** read each one. Fix it, or keep the sentence when the fix makes it worse. Rule 3 applies to warnings and never to errors. A semicolon in a table cell is a warning. A semicolon in prose is an error.
- **Do not edit a rule, the configuration or the vocabulary to pass.** A rule that is wrong for the document goes in your report.
- **Controller check.** When you dispatched the writer, run the same command on the returned file. Return the Vale output to the writer while an error remains.
- **Scope.** The gate covers the files you write or edit. It does not cover chat, commit subjects, PR descriptions or pages you did not touch.
- **Headings and frontmatter count.** Vale reads both. A heading fix changes its anchor, so correct every link to it in the same pass. Put a frontmatter value in double quotes when the fix adds a colon to it, or the YAML breaks.
- **After a rule change,** run `sh <skill dir>/vale/test.sh`. It must print `PASS`.

Vale does not judge whether a number has a source or whether a paragraph carries a fact. The House rules do.

## Review checklist

Reviewing a doc, in this order:

1. What mode is this? If unanswerable, split it.
2. Any sentence over 25 words? Split it.
3. Any passive voice hiding who acts? Name the actor.
4. Any warning after its step? Move it up.
5. Same concept under two names? Pick one.
6. Any line numbers, open questions, or rendered-image-as-source? Remove.
7. Run `unslop`, then the Vale gate. Zero errors.

## Common mistakes

- **Applying the rules into worse prose.** Rule 3 is not decorative. A 24-word sentence that reads well beats two clipped ones that do not.
- **Treating a reference page as explanation.** Reference gets looked up, not read. It needs no narrative arc.
- **Rewriting a human's voice.** These rules govern structure and clarity, not personality. Leave someone's voice alone.
