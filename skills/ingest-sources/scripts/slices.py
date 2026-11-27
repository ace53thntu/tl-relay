#!/usr/bin/env python3
"""Split a new register into reader slices by story, and give each unpaired old criterion to one slice."""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registerio import load_jsonl, register_field, require_columns, unique_ids  # noqa: E402

NAMES = "ABCDEFGH"


def make_slices(new, pairs, old, unclaimed, count):
    if not 1 <= count <= len(NAMES):
        raise SystemExit(f"slices: --count must be 1 to {len(NAMES)}")
    stories = []
    for n in new:
        if not stories or stories[-1]["story"] != n["story"]:
            stories.append({"story": n["story"], "ids": []})
        stories[-1]["ids"].append(n["id"])
    groups, current, size, closed = [], [], 0, 0
    for s in stories:
        target = (len(new) - closed) / (count - len(groups))
        if current and size + len(s["ids"]) > target * 1.25 and len(groups) < count - 1:
            groups.append(current)
            closed += size
            current, size = [], 0
        current.append(s)
        size += len(s["ids"])
    groups.append(current)
    out = [{"name": NAMES[i], "stories": [s["story"] for s in g], "new_ids": [x for s in g for x in s["ids"]],
            "rule_on": []} for i, g in enumerate(groups)]
    where = {nid: i for i, s in enumerate(out) for nid in s["new_ids"]}
    old_story = {o["id"]: o["story"] for o in old}
    for oid in unclaimed:
        votes = {}
        for p in pairs:
            if p["old_id"] and old_story.get(p["old_id"]) == old_story[oid]:
                i = where[p["new_id"]]
                votes[i] = votes.get(i, 0) + 1
        if votes:
            i = min(votes, key=lambda k: (-votes[k], k))
        else:
            i = min(range(len(out)), key=lambda k: (len(out[k]["new_ids"]), k))
        out[i]["rule_on"].append(oid)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new", required=True)
    p.add_argument("--old", required=True)
    p.add_argument("--pairs", required=True)
    p.add_argument("--unclaimed", required=True)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    path = a.pairs
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
            require_columns(reader.fieldnames, ("new_id", "old_id"))
            k = len(reader.fieldnames)
            numbered = []
            for row in reader:
                m = k - sum(1 for f in reader.fieldnames if row[f] is None) + len(row.get(None, []))
                if m != k:
                    raise ValueError(f"line {reader.line_num}: has {m} fields, header has {k}")
                numbered.append((reader.line_num, row))
        pairs = [row for _, row in numbered]
        path = a.unclaimed
        with open(path, encoding="utf-8") as fh:
            unclaimed = [line.strip() for line in fh if line.strip()]
        registers = []
        for path in (a.new, a.old):
            rows = load_jsonl(path)
            for n, row in enumerate(rows, 1):
                register_field(row, n, "id")
                register_field(row, n, "story")
            unique_ids([row["id"] for row in rows])
            registers.append(rows)
        path = a.pairs
        new_ids = {row["id"] for row in registers[0]}
        for n, row in numbered:
            if row.get("old_id") and row.get("new_id") not in new_ids:
                raise ValueError(f"line {n}: new_id '{row.get('new_id')}' is not in new.jsonl")
        path = a.unclaimed
        old_ids = {row["id"] for row in registers[1]}
        for n, oid in enumerate(unclaimed, 1):
            if oid not in old_ids:
                raise ValueError(f"row {n}: id '{oid}' is not in old.jsonl")
    except (OSError, ValueError, csv.Error) as e:
        print(f"slices: cannot read {path}: {e}", file=sys.stderr)
        return 1
    result = make_slices(registers[0], pairs, registers[1], unclaimed, a.count)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    print(json.dumps([{"name": s["name"], "new": len(s["new_ids"]), "rule_on": len(s["rule_on"])} for s in result]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
