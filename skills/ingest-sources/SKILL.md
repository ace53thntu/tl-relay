---
name: ingest-sources
description: Use when a PRD, story register workbook, prototype or other design input arrives for a project or feature. Also use when a new revision replaces an earlier one, or when someone asks what changed between two revisions. Snapshots inputs by content digest, converts them to Markdown, generates the story register and runs an adjudicated drift record.
---

# ingest-sources

## Overview

A raw input is immutable and identified by its content digest, never by the version label printed on it.
An Office package stamps its save moment into `docProps/core.xml`. The digest of the file's bytes
therefore changes each time someone decrypts and saves the same arriving file again. `snapshot.py` records both:
`sha256` over the bytes, and `content_sha256` over the package's other parts.
It reports a duplicate when either digest matches an entry already recorded. An entry recorded
before this skill computed `content_sha256` carries only `sha256`. Such an entry dedupes by bytes
alone and does not recognise a re-save of its own file.

A new revision of a kind that already has a baseline gets a drift record. The baseline moves only after
the operator accepts that record at G-ingest.

In this phase the drift record covers `stories` workbooks only. PRD and prototype drift are not built yet.

## Paths

`<skill dir>` is this skill's base directory as the session reports it.
Paths follow [config.md](../using-tl-relay/config.md): `<design root>` holds `designs/`, by default `<state_dir>/<workspace>/`. `knowledge_dir` has no default.

`PY` is `<skill dir>/.venv/bin/python` when it exists, else `python3`.

Before step 1, only when the input is a PDF, import each package that `<skill dir>/requirements.txt` lists with `PY`.
If an import fails, stop and give the operator
`python3 -m venv <skill dir>/.venv && <skill dir>/.venv/bin/python -m pip install -r <skill dir>/requirements.txt`.

`snapshot.py` imports `state.py` from the sibling skill `tl-design`. If `<skill dir>/../tl-design/scripts/state.py` is missing,
stop and name `tl-design` with `npx skills add ace53thntu/tl-relay --skill tl-design`.

```bash
K=<absolute path of the design root>
H=<handle>
SK=<skill dir>/scripts
PY=<the Python defined above>
WS=<the directory the caller names, else a fresh directory in the session scratchpad>
```

## 1. Snapshot

```bash
python3 "$SK/snapshot.py" --knowledge-root "$K" --handle "$H" --kind stories \
  --label "8 September revision" --received 2026-09-12 "<file>"
```

If `duplicate_of` is not null, report that the file is not a new revision and stop.

## 2. Convert

```bash
python3 "$SK/xlsx2md.py" "$K/<path>" --list
python3 "$SK/xlsx2md.py" "$K/<path>" --sheet "<sheet>" --out "$K/<path>.md"
"$PY" "$SK/pdf2md.py" "$K/<path>" --out "$K/<path>.md"
```

The converted Markdown sits beside the original. A PDF needs `$PY` with the `requirements.txt` packages installed, because pypdf is not in the standard library.

## 3. Generate the register

Agree the minting rule with the operator before the first run for a project. Mint identifiers for a revision that has
none. Read them from the columns of a revision that carries them.

```bash
python3 "$SK/gen_register.py" "$K/<path>" --sheet "<sheet>" --mint S --jsonl "$WS/new.jsonl"
python3 "$SK/gen_register.py" "$K/<path>" --sheet "<sheet>" --id-col Criterion --story-col "Old ID" --jsonl "$WS/old.jsonl"
```

For a first snapshot, also pass `--page "$K/designs/$H/specs/user-stories.md"` with `--page-title`,
`--page-description`, `--source-rel` and `--generated-at`. Then add the index entry with the same description.
For a revision, the caller writes the page after G-ingest, as step 4.8 says.

## 4. Drift record for a revision

1. Generate `old.jsonl` from the baseline and `new.jsonl` from the revision, as in step 3.
2. Pair them. The counts are hints: for S6 a text match said 42 withdrawn and the readers found 31.

   ```bash
   python3 "$SK/pair.py" --old "$WS/old.jsonl" --new "$WS/new.jsonl" --out "$WS/pairs.tsv" --unclaimed "$WS/unclaimed.txt"
   ```

3. Slice. Use one slice per 30 new criteria, at most 8.

   ```bash
   python3 "$SK/slices.py" --new "$WS/new.jsonl" --old "$WS/old.jsonl" --pairs "$WS/pairs.tsv" \
     --unclaimed "$WS/unclaimed.txt" --count <n> --out "$WS/slices.json"
   ```

4. Run the readers. First run `python3 "$SK/assemble.py" --ws "$WS" --pending`. It prints `slices_sha256`, the digest of
   `slices.json`, and `pending`, the slices that lack a slice file or a findings file stamped with that digest.
   Call the workflow below, where `slices` holds the pending entries of `slices.json` and `digest` is `slices_sha256`.

   ```js
   Workflow({scriptPath: "<skill dir>/workflows/drift-adjudicate.js", args: {kind, ws, oldSource, newSource, slices, digest}})
   ```

   Then run `--pending` again. If it lists a slice, run the workflow again with only the slices it lists.

   With no Workflow tool and a subagent tool, dispatch one subagent per pending slice, all at once where the tool allows.
   Each subagent's prompt is the text that `prompt(a, s)` builds in `<skill dir>/workflows/drift-adjudicate.js`, copied verbatim.
   Fill `a` from the args above and `s` from that slice in `slices.json`.
   Dispatch on `opus` where the tool takes a model, else on the tool's default.
   Wait until every subagent finishes, a failed one included. Then run `--pending` again.
   Next, redispatch only the slices it lists, and repeat the wait and the check.
   Step 5 starts only after `--pending` lists no slice.

   With no subagent tool, the session adjudicates the pending slices one at a time, following the reader instructions in `<skill dir>/workflows/drift-adjudicate.js`.
   Each slice writes `$WS/slice-<name>.md` and `$WS/findings-<name>.md`, each opening with the stamp those instructions give.
   Step 5 starts only after `--pending` lists no slice.

5. Assemble. A stamp error goes back to step 4 for the slice it names, never to the operator. Put every other
   error to the operator as a question. Write the ruling into the named slice file and note it in
   that slice's findings. Rerun until the exit code is 0.

   ```bash
   python3 "$SK/assemble.py" --ws "$WS" --out "$WS/adjudication.json" --ids-out "$WS/ids-to-scan.txt"
   ```

6. Scan the impact. The root is `$K/designs/$H`.

   ```bash
   python3 "$SK/impact.py" --root "$K/designs/$H" --ids-file "$WS/ids-to-scan.txt" --out "$WS/impact.tsv"
   ```

7. Write `$K/designs/$H/audits/<date>-stories-drift.md` with `type: Audit`. Read the findings only from the files
   that `$WS/adjudication.json` lists under `findings`. Carry the counts and every story that vanished while design
   rests on it. Also carry the values that changed, contradictions inside the revision, stale references and the
   readers' open questions. Each item names the file to change and who decides. The workspace may be gone after this
   run, so the record must hold everything the readers found. Copy `$WS/adjudication.json` to
   `$K/designs/$H/audits/<date>-stories-adjudication.json`, which keeps the old-to-new mapping. Add the index entry.
8. Stop at G-ingest. After the operator accepts, the caller runs `set-baseline` and `add-impact` with `$WS/impact.tsv`,
   then regenerates `$K/designs/$H/specs/user-stories.md` from the revision. Run alone, this skill presents G-ingest and
   then stops: it moves no baseline and leaves the register as it is.

## Rules

- Never retype criterion text. Generate it.
- `content_sha256` decides identity. `sha256` records the exact bytes that arrived.
- Never move a baseline or rewrite the register before G-ingest.
- A claim that a story vanished cites the search that found no carrier.
- **REQUIRED SUB-SKILL:** `technical-writing` for the drift record, then `unslop`, then the Vale gate in `technical-writing`. Zero errors.

## Common mistakes

- Grouping the 8 September workbook by number and title. Block 21 spells its title two ways, so group by number.
- Grouping the 31 August workbook by `No.`. That column is not the story there, so group by `Old ID`.
- Running `pdf2md.py` with a Python that lacks `requirements.txt`.
- Reporting pair counts as the drift result.
