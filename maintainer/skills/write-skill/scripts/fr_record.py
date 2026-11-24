from __future__ import annotations

import json
import os
import pathlib

import fr_git


class RecordError(Exception):
    pass


def path(repo) -> pathlib.Path:
    return fr_git.common_dir(repo) / "ai-sdlc" / "final-run.jsonl"


_FIELDS = {
    "run": ("fingerprint", "commit", "prompt", "tier"),
    "verdict": ("fingerprint", "commit"),
}
_OUTCOME = {"run": "result", "verdict": "verdict"}


def _check(row) -> None:
    kind = row.get("type")
    if not isinstance(kind, str) or kind not in _FIELDS:
        raise ValueError("unknown type")
    for name in _FIELDS[kind]:
        if not isinstance(row.get(name), str):
            raise ValueError("%s is not a string" % name)
    if row.get(_OUTCOME[kind]) not in ("PASS", "FAIL"):
        raise ValueError("%s is not PASS or FAIL" % _OUTCOME[kind])
    if "heldout" not in row:
        raise ValueError("heldout is missing")
    heldout = row["heldout"]
    if heldout is not None and not isinstance(heldout, str):
        raise ValueError("heldout is not a string or null")


def load(repo) -> list:
    target = path(repo)
    try:
        data = target.read_bytes()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise RecordError("cannot read %s: %s" % (target, exc))
    if data and not data.endswith(b"\n"):
        raise RecordError("%s ends in a truncated line" % target)
    rows = []
    for number, raw in enumerate(data.split(b"\n")[:-1], 1):
        try:
            row = json.loads(raw.decode("utf-8"))
            if not isinstance(row, dict):
                raise ValueError("not an object")
            _check(row)
        except (ValueError, RecursionError) as exc:
            raise RecordError("%s line %d is invalid: %s" % (target, number, exc))
        rows.append(row)
    return rows


def _append(repo, row) -> None:
    try:
        _check(row)
    except ValueError as exc:
        raise RecordError("refusing to record an invalid row: %s" % exc)
    target = path(repo)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        view = memoryview((json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
        fd = os.open(str(target), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise RecordError("cannot finish writing %s" % target)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise RecordError("cannot write %s: %s" % (target, exc))


def append_run(repo, fingerprint, commit, heldout, prompt, tier, result) -> None:
    _append(repo, {
        "type": "run", "fingerprint": fingerprint, "commit": commit,
        "heldout": heldout, "prompt": prompt, "tier": tier, "result": result,
    })


def append_verdict(repo, fingerprint, commit, heldout, verdict) -> None:
    _append(repo, {
        "type": "verdict", "fingerprint": fingerprint, "commit": commit,
        "heldout": heldout, "verdict": verdict,
    })


def verdict_for(rows, fingerprint):
    found = [
        r.get("verdict") for r in rows
        if r.get("type") == "verdict" and r.get("fingerprint") == fingerprint
    ]
    if not found:
        return None
    return "FAIL" if "FAIL" in found else found[-1]


def results_for(rows, fingerprint) -> dict:
    out: dict = {}
    for r in rows:
        if r.get("type") == "run" and r.get("fingerprint") == fingerprint:
            out.setdefault(r.get("prompt"), []).append(r.get("result"))
    return out


def heldout_failed(rows, digest, *, current) -> bool:
    counts: dict = {}
    for r in rows:
        if r.get("heldout") != digest:
            continue
        if r["type"] == "verdict":
            if r["verdict"] == "FAIL":
                return True
        elif r["prompt"].startswith("heldout/") and r["fingerprint"] != current:
            tally = counts.setdefault((r["fingerprint"], r["prompt"]), {"PASS": 0, "FAIL": 0})
            tally[r["result"]] += 1
    return any(
        tally["FAIL"] >= 2 or (tally["FAIL"] == 1 and tally["PASS"] < 4)
        for tally in counts.values()
    )


def heldouts_for(rows, fingerprint) -> set:
    return {
        r.get("heldout") for r in rows
        if r.get("type") == "run" and r.get("fingerprint") == fingerprint
    }


def heldout_matches(rows, fingerprint, digest) -> bool:
    return heldouts_for(rows, fingerprint) - {None} <= {digest}
