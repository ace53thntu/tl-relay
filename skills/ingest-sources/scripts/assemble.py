#!/usr/bin/env python3
"""Merge reader slice tables and prove every criterion was ruled on exactly once."""
import argparse
import csv
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registerio import load_jsonl  # noqa: E402

VERDICTS = ("changed", "identical", "new", "reworded", "withdrawn")
ROW = re.compile(r"^\|\s*`?([^|`]*?)`?\s*\|\s*`?([^|`]*?)`?\s*\|\s*(\w+)\s*\|")
EMPTY = {"", "—", "-"}
STAMP = "<!-- drift inputs sha256 {} -->"
INPUTS = ("slices.json", "new.jsonl", "old.jsonl")


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


def inputs_digest(ws):
    h = hashlib.sha256()
    for name in INPUTS:
        with open(os.path.join(ws, name), "rb") as fh:
            data = fh.read()
        h.update(name.encode() + b"\n" + str(len(data)).encode() + b"\n" + data)
    return h.hexdigest()


def slice_names(ws):
    with open(os.path.join(ws, "slices.json"), encoding="utf-8") as fh:
        return [s["name"] for s in json.load(fh)]


def register_errors(ws, want_new, want_old, new_ids, old_ids):
    errors = []
    for name, want, have in (("new.jsonl", want_new, new_ids), ("old.jsonl", want_old, old_ids)):
        path = os.path.join(ws, name)
        errors += [f"{path}: id {i} missing" for i in sorted(want - set(have))]
        errors += [f"{path}: unexpected id {i}" for i in sorted(set(have) - want)]
    return errors


def stamped(path, digest):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.readline().lstrip("\ufeff").strip() == STAMP.format(digest)
    except (OSError, UnicodeDecodeError):
        return False


def stale_files(ws, digest, name):
    paths = [os.path.join(ws, f"{kind}-{name}.md") for kind in ("slice", "findings")]
    return [p for p in paths if not stamped(p, digest)]


def pending(ws):
    digest = inputs_digest(ws)
    return {"inputs_sha256": digest, "pending": [n for n in slice_names(ws) if stale_files(ws, digest, n)]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ws", required=True)
    p.add_argument("--out")
    p.add_argument("--ids-out")
    p.add_argument("--pending", action="store_true")
    a = p.parse_args(argv)
    if a.pending and (a.out or a.ids_out):
        p.error("--pending cannot be combined with --out or --ids-out")
    if not a.pending and not (a.out and a.ids_out):
        p.error("--out and --ids-out are required without --pending")
    failed = "slices.json"
    errors = []
    try:
        digest = inputs_digest(a.ws)
        names = slice_names(a.ws)
        failed = "old.jsonl"
        old = load_jsonl(os.path.join(a.ws, failed))
        old_ids = [o["id"] for o in old]
        old_story = {o["id"]: o["story"] for o in old}
        failed = "new.jsonl"
        new = load_jsonl(os.path.join(a.ws, failed))
        new_ids = [n["id"] for n in new]
        if a.pending:
            failed = "slices.json"
            with open(os.path.join(a.ws, failed), encoding="utf-8") as fh:
                slicing = json.load(fh)
            want_new = {i for s in slicing for i in s["new_ids"]}
            want_old = {i for s in slicing for i in s["rule_on"]}
            failed = "pairs.tsv"
            with open(os.path.join(a.ws, failed), encoding="utf-8", newline="") as fh:
                want_old |= {r["old_id"] for r in csv.DictReader(fh, delimiter="\t") if r.get("old_id")}
            errors = register_errors(a.ws, want_new, want_old, new_ids, old_ids)
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as e:
        path = e.filename if isinstance(e, OSError) and e.filename else os.path.join(a.ws, failed)
        print(f"assemble: cannot read {path}: {e}", file=sys.stderr)
        return 1
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if a.pending:
        print(json.dumps(pending(a.ws)))
        return 0
    stale = [f"{path}: no stamp for drift inputs sha256 {digest[:12]}; rerun reader {name}"
             for name in names for path in stale_files(a.ws, digest, name)]
    if stale:
        print("\n".join(stale), file=sys.stderr)
        return 1
    rows = read_slices([os.path.join(a.ws, f"slice-{n}.md") for n in names])
    counts, errors = check(rows, new_ids, old_ids)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    ids = ids_to_scan(rows, old_story)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"inputs_sha256": digest, "counts": counts, "old": len(old), "new": len(new), "rows": rows,
                   "findings": [os.path.join(a.ws, f"findings-{n}.md") for n in names]}, fh, indent=2, ensure_ascii=False)
    with open(a.ids_out, "w", encoding="utf-8") as fh:
        fh.write("".join(i + "\n" for i in ids))
    print(json.dumps({"counts": counts, "old": len(old), "new": len(new), "ids_to_scan": len(ids)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
