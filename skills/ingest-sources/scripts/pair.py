#!/usr/bin/env python3
"""Pair the criteria of a new register revision with the old one. The counts are hints for readers."""
import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registerio import load_jsonl, register_field, register_text  # noqa: E402

LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def norm(text):
    text = LINK.sub(r"\1", text.replace("<br>", " "))
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def pair(old, new, threshold=0.55):
    claimed, found = set(), {}
    by_scenario = {}
    for o in old:
        by_scenario.setdefault(norm(o["scenario"]), []).append(o)
    for n in new:
        for o in by_scenario.get(norm(n["scenario"]), []):
            if o["id"] not in claimed:
                claimed.add(o["id"])
                found[n["id"]] = (o, "scenario", 1.0)
                break
    for n in new:
        if n["id"] in found:
            continue
        key = norm(n["scenario"] + " " + n["rule"])
        best, best_ratio = None, 0.0
        for o in old:
            if o["id"] in claimed:
                continue
            sm = difflib.SequenceMatcher(None, key, norm(o["scenario"] + " " + o["rule"]), autojunk=False)
            if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
                continue
            ratio = sm.ratio()
            if ratio >= threshold and (best is None or ratio > best_ratio):
                best, best_ratio = o, ratio
        if best is not None:
            claimed.add(best["id"])
            found[n["id"]] = (best, "similar", round(best_ratio, 3))
    rows = []
    for n in new:
        o, kind, ratio = found.get(n["id"], (None, "", 0.0))
        rule_changed = "" if o is None else ("no" if norm(o["rule"]) == norm(n["rule"]) else "yes")
        rows.append({"new_id": n["id"], "old_id": o["id"] if o else "", "kind": kind,
                     "rule_changed": rule_changed, "ratio": ratio})
    return rows, [o["id"] for o in old if o["id"] not in claimed]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--unclaimed", required=True)
    a = p.parse_args(argv)
    path = a.old
    try:
        registers = []
        for path in (a.old, a.new):
            rows = load_jsonl(path)
            for n, row in enumerate(rows, 1):
                register_field(row, n, "id")
                register_text(row, n, "scenario")
                register_text(row, n, "rule")
            registers.append(rows)
    except (OSError, ValueError) as e:
        print(f"pair: cannot read {path}: {e}", file=sys.stderr)
        return 1
    rows, unclaimed = pair(*registers)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write("new_id\told_id\tkind\trule_changed\tratio\n")
        for r in rows:
            fh.write(f"{r['new_id']}\t{r['old_id']}\t{r['kind']}\t{r['rule_changed']}\t{r['ratio']}\n")
    with open(a.unclaimed, "w", encoding="utf-8") as fh:
        fh.write("".join(i + "\n" for i in unclaimed))
    print(json.dumps({
        "paired_scenario": sum(r["kind"] == "scenario" for r in rows),
        "paired_similar": sum(r["kind"] == "similar" for r in rows),
        "unpaired_new": sum(r["kind"] == "" for r in rows),
        "unclaimed_old": len(unclaimed),
        "rule_unchanged": sum(r["rule_changed"] == "no" for r in rows),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
