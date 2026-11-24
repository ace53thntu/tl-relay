import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from records import redact

TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
LOCK_TTL = timedelta(hours=2)
LOCKED = 4
COUNT_FIELDS = ("important", "routine", "avoidable", "corrections", "repeats", "lessons_written")


def _clean(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


def _write(path: Path, text: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def _load_lines(path: Path) -> List[dict]:
    lines = []
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                try:
                    item = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    lines.append(item)
    except OSError:
        pass
    return lines


def _jsonl(items: List[dict]) -> str:
    return "".join(json.dumps(_clean(item), ensure_ascii=False) + "\n" for item in items)


def _append(path: Path, item: dict):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(_jsonl([item]))


def _retro(args) -> Path:
    retro = Path(args.home).expanduser().resolve() / "retro"
    retro.mkdir(parents=True, exist_ok=True)
    return retro


def _now(value: Optional[str] = None) -> datetime:
    if value:
        return datetime.strptime(value, TS_FORMAT).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _target(value: str) -> str:
    return str(Path(value).expanduser().resolve())


def _ts(moment: datetime) -> str:
    return moment.strftime(TS_FORMAT)


def _new_owner(args) -> int:
    print("%s-%s-%s" % (args.kind, _now(args.now).astimezone().strftime("%Y-%m-%d"), secrets.token_hex(3)))
    return 0


def _lock(args) -> int:
    path = _retro(args) / "lock"
    now = _now(args.now)
    body = json.dumps({"owner": args.owner, "ts": _ts(now)})
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held = _load_json(path, {})
            if not isinstance(held, dict):
                held = {}
            if held.get("owner") == args.owner:
                return 0
            try:
                stamp = _now(held["ts"])
            except (KeyError, TypeError, ValueError):
                try:
                    stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                except OSError:
                    continue
            age = now - stamp
            if age < timedelta(0):
                age = LOCK_TTL
            if age < LOCK_TTL:
                return LOCKED
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
        return 0
    return LOCKED


def _unlock(args) -> int:
    path = _retro(args) / "lock"
    held = _load_json(path, {})
    owner = held.get("owner") if isinstance(held, dict) else None
    if path.exists() and owner is not None and owner != args.owner:
        return LOCKED
    if Path(args.owner).name == args.owner and args.owner not in (".", ".."):
        shutil.rmtree(_retro(args) / "scratch" / args.owner, ignore_errors=True)
        try:
            os.rmdir(_retro(args) / "scratch")
        except OSError:
            pass
    try:
        os.remove(path)
    except OSError:
        pass
    return 0


def _sight(args) -> int:
    path = _retro(args) / "candidates.jsonl"
    rows = _load_lines(path)
    if not any(r.get("key") == args.key and r.get("source") == args.source for r in rows):
        item = {"key": args.key, "source": args.source, "ts": _ts(_now())}
        _append(path, item)
        rows.append(item)
    print(len({r.get("source") for r in rows if r.get("key") == args.key}))
    return 0


def _highest(prefix: str, texts: List[str]) -> int:
    pattern = re.compile(r"\b%s-(\d+)\b" % prefix)
    return max([int(m) for text in texts for m in pattern.findall(text)] or [0])


def _next_id(args) -> int:
    args.target = _target(args.target)
    written = _load_lines(_retro(args) / "written.jsonl")
    if args.kind == "lesson":
        ids = [r["id"] for r in written if r.get("kind") == "lesson" and r.get("target") == args.target]
        try:
            lines = Path(args.target).read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        ids += [line for line in lines if line.startswith("- L-")]
        print("L-%d" % (_highest("L", ids) + 1))
    else:
        ids = [r["id"] for r in written if r.get("kind") == "memory"]
        print("M-%d" % (_highest("M", ids) + 1))
    return 0


def _notify(target: str, text: str):
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    title = "retro: %s" % Path(target).name
    script = 'display notification "%s" with title "%s"' % (escaped, title)
    try:
        subprocess.run(["osascript", "-e", script], check=False)
    except OSError:
        pass


def _record(args) -> int:
    args.target = _target(args.target)
    item = {"id": args.id, "kind": args.kind, "target": args.target, "text": args.text, "ts": _ts(_now())}
    _append(_retro(args) / "written.jsonl", item)
    if os.environ.get("RETRO_NO_NOTIFY") != "1":
        _notify(args.target, redact(args.text))
    return 0


def _drop(args) -> int:
    args.target = _target(args.target)
    path = _retro(args) / "written.jsonl"
    rows = _load_lines(path)
    hit = False
    for row in rows:
        if row.get("id") == args.id and row.get("target") == args.target:
            row["dropped"] = True
            hit = True
    if not hit:
        return 2
    _write(path, _jsonl(rows))
    return 0


def _holds(row: dict) -> bool:
    try:
        text = Path(row["target"]).read_text(encoding="utf-8")
    except OSError:
        return False
    ident = re.escape(row["id"])
    pattern = r"^- %s ·" % ident if row.get("kind") == "lesson" else r"^\s*retro_id: %s\s*$" % ident
    return re.search(pattern, text, re.MULTILINE) is not None


def _sync_vetoes(args) -> int:
    retro = _retro(args)
    vetoed = _load_lines(retro / "vetoed.jsonl")
    seen = {(v.get("id"), v.get("target")) for v in vetoed}
    for row in _load_lines(retro / "written.jsonl"):
        key = (row.get("id"), row.get("target"))
        if row.get("dropped") or key in seen or _holds(row):
            continue
        _append(retro / "vetoed.jsonl", {"id": row["id"], "target": row["target"], "text": row.get("text"),
                                         "ts": _ts(_now())})
        seen.add(key)
        print(redact(row["id"]))
    return 0


def _vetoed(args) -> int:
    for row in _load_lines(_retro(args) / "vetoed.jsonl"):
        print(json.dumps(_clean(row), ensure_ascii=False))
    return 0


def _count(args) -> int:
    retro = _retro(args)
    days = _load_json(retro / "days.json", {})
    day = days.setdefault(args.date, {f: 0 for f in COUNT_FIELDS})
    for field, value in zip(COUNT_FIELDS, (args.important, args.routine, args.avoidable, args.corrections,
                                           args.repeats, args.lessons)):
        day[field] = int(day.get(field, 0)) + value
    _write(retro / "days.json", json.dumps(days))
    rows = [dict(date=d, **{f: int(days[d].get(f, 0)) for f in COUNT_FIELDS}) for d in sorted(days)]
    _write(retro / "decisions.jsonl", _jsonl(rows))
    return 0


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="ledger.py")
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name, *flags, **extra):
        p = sub.add_parser(name)
        p.add_argument("--home", required=True)
        for flag in flags:
            p.add_argument(flag, required=True, **extra.get(flag, {}))
        return p

    command("new-owner", "--kind", **{"--kind": {"choices": ["listen", "sweep"]}}).add_argument("--now")
    command("lock", "--owner").add_argument("--now")
    command("unlock", "--owner")
    command("sight", "--key", "--source")
    command("next-id", "--kind", "--target", **{"--kind": {"choices": ["lesson", "memory"]}})
    command("record", "--id", "--kind", "--target", "--text", **{"--kind": {"choices": ["lesson", "memory"]}})
    command("drop", "--id", "--target")
    command("sync-vetoes")
    command("vetoed")
    command("count", "--date", "--important", "--routine", "--avoidable", "--corrections", "--repeats",
            "--lessons", **{f: {"type": int} for f in ("--important", "--routine", "--avoidable", "--corrections",
                                                        "--repeats", "--lessons")})
    args = parser.parse_args(argv)
    handlers = {"new-owner": _new_owner, "lock": _lock, "unlock": _unlock, "sight": _sight, "next-id": _next_id, "record": _record,
                "drop": _drop, "sync-vetoes": _sync_vetoes, "vetoed": _vetoed, "count": _count}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
