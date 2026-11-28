#!/usr/bin/env python3
"""Build a story register from a worksheet: register JSON Lines plus a Markdown register page."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registerio import bad_char, write_jsonl  # noqa: E402
from xlsx2md import cell_md, read_sheet  # noqa: E402

IMPACT_RANK = {"low": 0, "medium": 1, "high": 2}


def check_mint(mint):
    if not mint:
        raise SystemExit("gen_register: --mint must not be empty")
    if mint != mint.strip():
        raise SystemExit(f"gen_register: --mint {mint!r} must not carry surrounding whitespace")
    if ch := bad_char(mint):
        raise SystemExit(f"gen_register: --mint holds U+{ord(ch):04X}")


def unbold(cell):
    return cell[2:-2] if len(cell) >= 4 and cell.startswith("**") and cell.endswith("**") else cell


def id_cell(cell):
    value = unbold(cell.strip()).strip()
    return value if value.replace("*", "").strip() else ""


def mint_number(cell, n):
    value = unbold(cell)
    if ch := bad_char(value):
        raise SystemExit(f"gen_register: No. at sheet row {n} holds U+{ord(ch):04X}")
    if not (value.isascii() and value.isdigit() and value.lstrip("0") != ""):
        raise SystemExit(f"gen_register: No. {cell!r} at sheet row {n} is not a whole number of 1 or more")
    return value


def build(rows, cols, mint=None, id_col=None, story_col=None):
    if mint is not None:
        check_mint(mint)
    if bool(mint) == bool(id_col):
        raise SystemExit("gen_register: pass exactly one of --mint or --id-col")
    header = rows[0]

    def idx(name):
        if name not in header:
            raise SystemExit(f"gen_register: no column {name!r}; the header is {header}")
        return header.index(name)

    c = {k: idx(v) for k, v in cols.items()}
    ci = idx(id_col) if id_col else None
    si = idx(story_col) if id_col else None
    blocks, order, criteria, skipped = {}, [], [], []
    minted, seen_ids = {}, {}
    for n, r in enumerate(rows[1:], start=2):
        number = r[c["number"]].strip()
        key = number if mint else id_cell(r[si])
        if not key:
            skipped.append(n)
            continue
        if mint:
            key = number = mint_number(key, n)
        if id_col and (ch := bad_char(key)):
            raise SystemExit(f"gen_register: story at sheet row {n} holds U+{ord(ch):04X}")
        if key not in blocks:
            story = f"{mint}-{number.lstrip('0').zfill(2)}" if mint else key
            if mint:
                if story in minted:
                    first_number, first_row = minted[story]
                    raise SystemExit(f"gen_register: No. {number!r} at sheet row {n} and {first_number!r} "
                                     f"at sheet row {first_row} both mint story {story}")
                minted[story] = (number, n)
            blocks[key] = {"story": story, "title": r[c["title"]], "impacts": [], "rows": []}
            order.append(key)
        b = blocks[key]
        cid = f"{b['story']}-AC{len(b['rows']) + 1}" if mint else id_cell(r[ci])
        if not cid:
            b["impacts"].append(r[c["impact"]].strip())
            skipped.append(n)
            continue
        if ch := bad_char(cid):
            raise SystemExit(f"gen_register: id at sheet row {n} holds U+{ord(ch):04X}")
        if cid in seen_ids:
            raise SystemExit(f"gen_register: id {cid!r} at sheet row {n} repeats sheet row {seen_ids[cid]}")
        seen_ids[cid] = n
        item = {"id": cid, "story": b["story"], "number": number, "title": b["title"],
                "impact": r[c["impact"]].strip(), "scenario": r[c["scenario"]], "rule": r[c["rule"]], "sheet_row": n}
        b["rows"].append(item)
        b["impacts"].append(item["impact"])
        criteria.append(item)
    return [blocks[k] for k in order], criteria, skipped


def render_page(blocks):
    out = []
    for b in blocks:
        impacts = [i for i in b["impacts"] if i]
        top = max(impacts, key=lambda v: IMPACT_RANK.get(v.lower(), -1)) if impacts else "—"
        out.append(f'<a id="{b["story"].lower()}"></a>\n\n## {b["story"]} — {cell_md(b["title"])}\n\n'
                   f"Change impact: **{top}**\n")
        if not b["rows"]:
            out.append("This story carries no acceptance criteria in this revision.\n")
            continue
        out.append("| Criterion | Impact | Scenario | Rule and message |\n| --- | --- | --- | --- |")
        for r in b["rows"]:
            rule = cell_md(r["rule"]) if r["rule"].strip() else "—"
            out.append(f'| `{r["id"]}` | {r["impact"]} | {cell_md(r["scenario"])} | {rule} |')
        out.append("")
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("xlsx")
    p.add_argument("--sheet")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--mint")
    group.add_argument("--id-col")
    p.add_argument("--story-col")
    for key, default in (("number", "No."), ("title", "Title"), ("impact", "Change impact"),
                         ("scenario", "Scenario"), ("rule", "Rule and message")):
        p.add_argument(f"--{key}-col", default=default)
    p.add_argument("--jsonl", required=True)
    p.add_argument("--page")
    p.add_argument("--page-title")
    p.add_argument("--page-description")
    p.add_argument("--source-rel")
    p.add_argument("--generated-at")
    a = p.parse_args(argv)
    if a.mint is not None:
        check_mint(a.mint)
    name, rows = read_sheet(a.xlsx, a.sheet)
    cols = {"number": a.number_col, "title": a.title_col, "impact": a.impact_col,
            "scenario": a.scenario_col, "rule": a.rule_col}
    blocks, criteria, skipped = build(rows, cols, mint=a.mint, id_col=a.id_col, story_col=a.story_col)
    write_jsonl(a.jsonl, criteria)
    if a.page:
        missing = [f for f in ("page_title", "page_description", "source_rel", "generated_at") if not getattr(a, f)]
        if missing:
            raise SystemExit("gen_register: --page also needs " + ", ".join("--" + m.replace("_", "-") for m in missing))
        dq = lambda s: json.dumps(s, ensure_ascii=False)  # noqa: E731
        front = ("---\ntype: Design Spec\n"
                 f"title: {dq(a.page_title)}\ndescription: {dq(a.page_description)}\nstatus: draft\n"
                 f"generated:\n  by: script/ingest-sources/gen_register.py\n  at: {a.generated_at}\n"
                 f"sources:\n  - resource: {dq(a.source_rel)}\n    title: {dq('sheet ' + name)}\n---\n\n")
        with open(a.page, "w", encoding="utf-8") as fh:
            fh.write(front + f"# {a.page_title}\n\n" + render_page(blocks))
    print(json.dumps({"sheet": name, "stories": len(blocks), "criteria": len(criteria), "skipped_rows": skipped}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
