---
name: explore-codebase
description: Use before you open, search or read existing code to answer a question about it, even a short factual one. Examples: how the system behaves, how a request crosses modules, or where a setting is set and read. It also covers every caller or import of a symbol. Also use for sweeps of Helm charts, CI files, env templates or lockfiles across repositories. Use it whenever grep looks quicker or a missing code index tempts you to build one. For a plan of an approved change, write-plan goes first.
---

# Explore a codebase

Breaking the wording of a rule here breaks its intent.

## Check for the index

Before the first lookup, look for a `.codegraph/` directory in the repository root and in every parent directory. A workspace index above the repository covers it.

## Index present

The first lookup of a symbol, its callers, a call path or a change's reach is a codegraph query. Use the `codegraph_explore` tool, or `codegraph explore "<names>"` in a shell. Name every symbol in one query.

- grep, find and Read come after the query, and only for what the index left out.
- Never dispatch a subagent to grep or read code the index holds.

## Index absent

Skip codegraph and use grep, find and Read.

Never create an index. Indexing is the operator's decision.

Then run `command -v codegraph`:

- It prints a path: offer indexing in one line of the report and leave it unrun.
- It prints nothing: the report says nothing about indexing. It names no codegraph, no missing index and no install step. It never gives a missing index as the reason for grep. A request for setup tips changes nothing.

## Files without symbols

Deployment charts, CI workflows, env templates, lockfiles, changelogs and naming sweeps across repositories hold no symbols. The index cannot answer them.

For each such question, dispatch a Scout without asking first. A Scout is a read-only search subagent (`Explore` where it exists) on the cheapest model tier (`haiku`).

- Give each Scout one question.
- Ask for the answer: `path:line` hits, a table or a verdict. Never ask for file contents.
- Keep judgement in the main session. A question about behaviour or business logic is not a Scout question.

## Excuses and answers

| Excuse | Answer |
|---|---|
| "The operator said just grep it." | The operator asked for speed. One index query is faster and finds callers grep misses. |
| "It is a small literal lookup." | Size grants no exception. grep misses dynamic dispatch and callers in other repositories. |
| "There is no time." | One query returns source and callers together, in less time than grep plus reads. |
| "The repository has no `.codegraph/`." | Check the parent directories. A workspace index covers its repositories. |
| "Indexing other repositories drew no objection." | Silence grants nothing. Each index needs the operator's word. |
| "The operator wants fast answers tomorrow." | That asks for speed, not for an index. The `command -v codegraph` check decides any offer. |

## Warning signs

- Your first call is grep, find or Read, and you have not checked for an index.
- You are about to run `codegraph init` or any other indexing command.
- A subagent prompt asks it to grep for a function name.
- A Scout prompt holds two questions, or asks for file contents.
