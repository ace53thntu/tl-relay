#!/usr/bin/env python3
"""Merge reader slice tables and prove every criterion was ruled on exactly once."""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registerio import load_jsonl  # noqa: E402

VERDICTS = ("changed", "identical", "new", "reworded", "withdrawn")
ROW = re.compile(r"^\|\s*`?([^|`]*?)`?\s*\|\s*`?([^|`]*?)`?\s*\|\s*(\w+)\s*\|")
EMPTY = {"", "—", "-"}


def read_slices(paths):
    rows = []
    for path in sorted(paths):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = ROW.match(line)
                if not m or m.group(3) not in VERDICTS:
                    continue
                new, old = m.group(1).strip(), m.group(2).strip()
                rows.append({"slice": os.path.basename(path), "new": "" if new in EMPTY else new,
                             "old": "" if old in EMPTY else old, "verdict": m.group(3)})
    return rows


def check(rows, new_ids, old_ids):
    errors, seen_new, seen_old = [], {}, {}
    for r in rows:
        v, where = r["verdict"], f"{r['slice']}: {r['new'] or '—'} / {r['old'] or '—'}"
        if v == "new" and (not r["new"] or r["old"]):
            errors.append(f"{where}: a new verdict must name only a new criterion")
        if v == "withdrawn" and (r["new"] or not r["old"]):
            errors.append(f"{where}: a withdrawn verdict must name only an old criterion")
        if v in ("identical", "reworded", "changed") and not (r["new"] and r["old"]):
            errors.append(f"{where}: a {v} verdict must name both criteria")
        if r["new"]:
            seen_new[r["new"]] = seen_new.get(r["new"], 0) + 1
        if r["old"]:
            seen_old[r["old"]] = seen_old.get(r["old"], 0) + 1
    errors += [f"new {i} ruled {seen_new.get(i, 0)} times" for i in new_ids if seen_new.get(i, 0) != 1]
    errors += [f"old {i} ruled {seen_old.get(i, 0)} times" for i in old_ids if seen_old.get(i, 0) != 1]
    errors += [f"unknown new id {i}" for i in sorted(set(seen_new) - set(new_ids))]
    errors += [f"unknown old id {i}" for i in sorted(set(seen_old) - set(old_ids))]
    counts = {v: sum(r["verdict"] == v for r in rows) for v in VERDICTS}
    continued = counts["identical"] + counts["reworded"] + counts["changed"]
    if continued + counts["withdrawn"] != len(old_ids):
        errors.append(f"old total {continued + counts['withdrawn']} is not {len(old_ids)}")
    if continued + counts["new"] != len(new_ids):
        errors.append(f"new total {continued + counts['new']} is not {len(new_ids)}")
    return counts, errors


def ids_to_scan(rows, old_story):
    ids = {r["old"] for r in rows if r["verdict"] in ("changed", "withdrawn")}
    withdrawn = {r["old"] for r in rows if r["verdict"] == "withdrawn"}
    members = {}
    for oid, story in old_story.items():
        members.setdefault(story, set()).add(oid)
    ids |= {story for story, m in members.items() if m <= withdrawn}
    return sorted(ids)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ws", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--ids-out", required=True)
    a = p.parse_args(argv)
    old = load_jsonl(os.path.join(a.ws, "old.jsonl"))
    new = load_jsonl(os.path.join(a.ws, "new.jsonl"))
    rows = read_slices(glob.glob(os.path.join(a.ws, "slice-*.md")))
    counts, errors = check(rows, [n["id"] for n in new], [o["id"] for o in old])
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    ids = ids_to_scan(rows, {o["id"]: o["story"] for o in old})
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"counts": counts, "old": len(old), "new": len(new), "rows": rows}, fh, indent=2, ensure_ascii=False)
    with open(a.ids_out, "w", encoding="utf-8") as fh:
        fh.write("".join(i + "\n" for i in ids))
    print(json.dumps({"counts": counts, "old": len(old), "new": len(new), "ids_to_scan": len(ids)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
