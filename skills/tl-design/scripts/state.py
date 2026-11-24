#!/usr/bin/env python3
"""Read and write the tl-design state block in designs/<handle>/index.md."""
import argparse
import csv
import json
import os
import re
import sys

STAGES = ["ingest", "review", "design", "breakdown"]
GATES = {s: "G-" + s for s in STAGES}
STATUSES = {"todo", "draft", "signed-off", "stale", "n/a"}
KINDS = {"prd", "stories", "prototype", "figma", "other"}
PAGE_DIRS = ["use-cases", "lld", "sources", "audits", "contracts", "specs"]
ORDER = {"todo": 0, "draft": 1, "stale": 2, "signed-off": 3}
BLOCK = re.compile(r"(<!-- tl-design:state -->\n```json\n)(.*?)(\n```\n<!-- /tl-design:state -->)", re.S)
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
HANDLE = re.compile(r"^[a-z][a-z0-9-]*\Z")
UNPRINTABLE_CLASS = "\x7f-\x84\x86-\x9f\ufffe\uffff"
UNPRINTABLE = re.compile("[%s]" % UNPRINTABLE_CLASS)
SEGMENT = r"(?!\.\.?(?:/|\Z))[^/\n" + UNPRINTABLE_CLASS + "]+"
ARCHIVE = re.compile(r"^raw/projects/%s/[0-9]{4}-[0-9]{2}-[0-9]{2}/%s/%s\Z" % (SEGMENT, SEGMENT, SEGMENT))


class StateError(Exception):
    pass


def index_path(knowledge_root, handle):
    if not HANDLE.match(handle):
        raise StateError(f"handle must be a lowercase letter followed by lowercase letters, digits or hyphens, got {handle!r}")
    return os.path.join(knowledge_root, "designs", handle, "index.md")


def blank_stage(sid, status="todo"):
    return {"id": sid, "status": status, "signed": None, "baselines": {}, "reads": []}


def merge_design(hla, lld):
    parts = [p for p in (hla, lld) if p is not None]
    if len(parts) == 1:
        merged = dict(parts[0])
    elif hla["status"] == "n/a" or lld["status"] == "n/a":
        merged = dict(lld if hla["status"] == "n/a" else hla)
    else:
        status = min(hla["status"], lld["status"], key=ORDER.__getitem__)
        signed = [p for p in (hla, lld) if p.get("signed")]
        source = max(signed, key=lambda p: p["signed"]) if signed else lld
        merged = dict(source)
        merged["status"] = status
    merged["id"] = "design"
    return merged


def migrate(state):
    state.pop("target", None)
    state.pop("tier", None)
    by_id = {s["id"]: s for s in state["stages"]}
    if "hla" in by_id or "contract-lld" in by_id:
        by_id["design"] = merge_design(by_id.get("hla"), by_id.get("contract-lld"))
    by_id.setdefault("breakdown", blank_stage("breakdown", "n/a"))
    state["stages"] = [by_id.get(sid) or blank_stage(sid) for sid in STAGES]
    for p in state["pending_impact"]:
        if p["stage"] in ("hla", "contract-lld"):
            p["stage"] = "design"
    state["pending_impact"] = [p for p in state["pending_impact"] if p["stage"] in STAGES]
    return state


def new_state(handle):
    return {
        "handle": handle,
        "sources": [],
        "stages": [blank_stage(s) for s in STAGES],
        "pending_impact": [],
    }


def render(state):
    return json.dumps(state, indent=2, ensure_ascii=False)


def init(knowledge_root, handle):
    path = index_path(knowledge_root, handle)
    if os.path.exists(path):
        raise StateError(f"{path} already exists")
    state = new_state(handle)
    base = os.path.dirname(path)
    for d in PAGE_DIRS:
        os.makedirs(os.path.join(base, d), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# {handle} design set\n\n<!-- tl-design:state -->\n```json\n{render(state)}\n```\n"
                 "<!-- /tl-design:state -->\n\n## Pages\n\n")
    return path


def load(path):
    with open(path, encoding="utf-8") as fh:
        m = BLOCK.search(fh.read())
    if not m:
        raise StateError(f"{path} has no tl-design state block")
    return migrate(json.loads(m.group(2)))


def save(path, state):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not BLOCK.search(text):
        raise StateError(f"{path} has no tl-design state block")
    text = BLOCK.sub(lambda m: m.group(1) + render(state) + m.group(3), text, count=1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def stage(state, sid):
    for s in state["stages"]:
        if s["id"] == sid:
            return s
    raise StateError(f"unknown stage {sid}")


def add_source(state, kind, label, received, sha256, path, content_sha256=None):
    if not ARCHIVE.match(path):
        raise StateError(
            f"{path} is not an archived snapshot. Run ingest-sources/scripts/snapshot.py, "
            "which copies the file to raw/projects/<handle>/<received>/<kind>/ and records it")
    if kind not in KINDS:
        raise StateError(f"kind must be one of {sorted(KINDS)}, got {kind}")
    if not DATE.match(received):
        raise StateError(f"received must be YYYY-MM-DD, got {received!r}")
    if "\n" in label or UNPRINTABLE.search(label):
        raise StateError(f"label must be one line with no DEL, C1 control other than U+0085, U+FFFE or U+FFFF, got {label!r}")
    if any(s["sha256"] == sha256 for s in state["sources"]):
        raise StateError(f"sha256 {sha256[:12]} is already recorded")
    is_baseline = not any(s["kind"] == kind for s in state["sources"])
    entry = {"kind": kind, "label": label, "received": received, "sha256": sha256,
             "path": path, "baseline": is_baseline}
    if content_sha256 and content_sha256 != sha256:
        entry["content_sha256"] = content_sha256
    state["sources"].append(entry)
    return is_baseline


def baseline(state, kind):
    return next((s for s in state["sources"] if s["kind"] == kind and s["baseline"]), None)


def set_baseline(state, kind, sha256):
    chosen = next((s for s in state["sources"] if s["kind"] == kind and s["sha256"] == sha256), None)
    if chosen is None:
        raise StateError(f"no {kind} source with sha256 {sha256[:12]}")
    old = baseline(state, kind)
    for s in state["sources"]:
        if s["kind"] == kind:
            s["baseline"] = s is chosen
    stale = []
    if old is not None and old is not chosen:
        for st in state["stages"]:
            if st["status"] == "signed-off" and st["baselines"].get(kind) == old["sha256"]:
                st["status"] = "stale"
                stale.append(st["id"])
    return stale


def set_stage(state, sid, status, signed=None):
    if status not in STATUSES:
        raise StateError(f"status must be one of {sorted(STATUSES)}, got {status}")
    st = stage(state, sid)
    if status == "signed-off":
        if not signed:
            raise StateError("signed-off needs the date the gate was passed")
        pending = [p for p in state["pending_impact"] if p["stage"] == sid]
        if pending:
            raise StateError(f"{len(pending)} pending impact lines block {sid}")
        st["baselines"] = {s["kind"]: s["sha256"] for s in state["sources"] if s["baseline"]}
        st["signed"] = signed
    st["status"] = status
    if sid == "design" and status != "signed-off":
        downstream = stage(state, "breakdown")
        if downstream["status"] == "signed-off":
            downstream["status"] = "stale"


def set_reads(state, sid, kinds):
    bad = sorted(k for k in kinds if k not in KINDS)
    if bad:
        raise StateError(f"kind must be one of {sorted(KINDS)}, got {', '.join(bad)}")
    st = stage(state, sid)
    st["reads"] = sorted(set(kinds))
    return st["reads"]


def add_impact(state, sid, rows, reason):
    stage(state, sid)
    known = {(p["stage"], p["page"], p["section"]) for p in state["pending_impact"]}
    added = 0
    for page, section, ids in rows:
        if (sid, page, section) in known:
            continue
        state["pending_impact"].append({"stage": sid, "page": page, "section": section, "ids": ids, "reason": reason})
        known.add((sid, page, section))
        added += 1
    return added


def clear_impact(state, page, section):
    before = len(state["pending_impact"])
    state["pending_impact"] = [p for p in state["pending_impact"] if not (p["page"] == page and p["section"] == section)]
    return before - len(state["pending_impact"])


def next_step(state):
    for st in state["stages"]:
        if st["status"] == "stale":
            return {"stage": st["id"], "status": "stale", "gate": GATES[st["id"]], "reads": st.get("reads", [])}
    for st in state["stages"]:
        if st["status"] not in ("signed-off", "n/a"):
            return {"stage": st["id"], "status": st["status"], "gate": GATES[st["id"]], "reads": st.get("reads", [])}
    return {"stage": None, "status": "done", "gate": None, "reads": []}


def read_impact_tsv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))
    return [tuple(r[:3]) for r in rows[1:] if len(r) >= 3]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--knowledge-root", required=True)
    p.add_argument("--handle", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("show")
    sub.add_parser("next")
    a = sub.add_parser("add-source")
    for f in ("kind", "label", "received", "sha256", "path"):
        a.add_argument("--" + f, required=True)
    b = sub.add_parser("set-baseline")
    b.add_argument("--kind", required=True)
    b.add_argument("--sha256", required=True)
    s = sub.add_parser("set-stage")
    s.add_argument("--stage", required=True, choices=STAGES)
    s.add_argument("--status", required=True, choices=sorted(STATUSES))
    s.add_argument("--signed")
    r = sub.add_parser("set-reads")
    r.add_argument("--stage", required=True, choices=STAGES)
    r.add_argument("--kinds", required=True)
    m = sub.add_parser("add-impact")
    m.add_argument("--stage", required=True, choices=STAGES)
    m.add_argument("--reason", required=True)
    m.add_argument("--from-tsv", required=True)
    c = sub.add_parser("clear-impact")
    c.add_argument("--page", required=True)
    c.add_argument("--section", required=True)
    args = p.parse_args(argv)
    try:
        path = index_path(args.knowledge_root, args.handle)
        if args.cmd == "init":
            print(json.dumps({"path": init(args.knowledge_root, args.handle)}))
            return 0
        state = load(path)
        if args.cmd == "show":
            print(render(state))
            return 0
        if args.cmd == "next":
            print(json.dumps(next_step(state)))
            return 0
        if args.cmd == "add-source":
            out = {"baseline": add_source(state, args.kind, args.label, args.received, args.sha256, args.path)}
        elif args.cmd == "set-baseline":
            out = {"stale": set_baseline(state, args.kind, args.sha256)}
        elif args.cmd == "set-stage":
            set_stage(state, args.stage, args.status, args.signed)
            out = {"stage": args.stage, "status": args.status}
        elif args.cmd == "set-reads":
            out = {"stage": args.stage, "reads": set_reads(state, args.stage, [k for k in args.kinds.split(",") if k])}
        elif args.cmd == "add-impact":
            out = {"added": add_impact(state, args.stage, read_impact_tsv(args.from_tsv), args.reason)}
        else:
            out = {"removed": clear_impact(state, args.page, args.section)}
        save(path, state)
        print(json.dumps(out))
        return 0
    except StateError as e:
        print(f"state: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
