import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from records import EXCERPT_MAX, repo_skills, extract, load_patterns, redact
from transcripts import config_dir, list_transcripts, operator_text, read_new, skip_reason

REPO = Path(__file__).resolve().parents[4]
WINDOW_DAYS = 7
KEY_MAX = 120
MIN_WORDS = 4
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
X = "<x>"

BACKTICK_RE = re.compile(r"`[^`]*`")
URL_RE = re.compile(r"\S+://\S+")
SLASH_RE = re.compile(r"\S*/\S*")
HASH_RE = re.compile(r"#\d+")
TICKET_RE = re.compile(r"\b[a-z]+-\d+\b")
HEX_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
HYPHEN_RE = re.compile(r"\S*-\S*")
DIGITS_RE = re.compile(r"\d+")


def normalise(text: str) -> str:
    text = redact(text).lower()
    for pattern in (BACKTICK_RE, URL_RE, SLASH_RE, HASH_RE, TICKET_RE, HEX_RE, HYPHEN_RE, DIGITS_RE):
        text = pattern.sub(X, text)
    return " ".join(text.split())[:KEY_MAX]


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


def _new_file_state() -> dict:
    return {"offset": 0, "skip": None, "skills": [], "pending": None, "last_ts": None,
            "prev_assistant": False, "ask_ids": []}


def _candidates(entries: List[dict], start: Optional[str], cutoff: str, answers: set) -> List[tuple]:
    found = []
    for entry in entries:
        ts = entry.get("timestamp")
        if start is not None and not (ts is not None and ts > start):
            continue
        if ts is not None and ts < cutoff:
            continue
        text = operator_text(entry)
        if text is None or text.startswith("/") or len(text.split()) < MIN_WORDS:
            continue
        if redact(text) in answers:
            continue
        found.append((entry, text))
    return found


def _is_retro(entries: List[dict]) -> bool:
    for entry in entries:
        text = operator_text(entry)
        if text is not None and (text == "/retro" or text.startswith("/retro ")):
            return True
        message = entry.get("message")
        content = message.get("content") if entry.get("type") == "assistant" and isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if (isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill"
                    and (block.get("input") or {}).get("skill") == "retro"):
                return True
    return False


def _run(args) -> int:
    retro = Path(args.home).expanduser().resolve() / "retro"
    retro.mkdir(parents=True, exist_ok=True)
    try:
        patterns = load_patterns(retro / "patterns.json")
    except ValueError as error:
        print("patterns.json: %s" % error, file=sys.stderr)
        return 2
    now = args.now or datetime.utcnow().strftime(TS_FORMAT)
    cutoff = (datetime.strptime(now, TS_FORMAT) - timedelta(days=WINDOW_DAYS)).strftime(TS_FORMAT)
    state = _load_json(retro / "state.json", {})
    files = dict(state.get("files") or {})
    history = [h for h in _load_lines(retro / "instructions.jsonl") if (h.get("ts") or "") >= cutoff]
    skills = repo_skills(REPO)
    out = []
    for path in list_transcripts(config_dir(args.config_dir)):
        ctx = _new_file_state()
        ctx.update(files.get(str(path)) or {})
        files[str(path)] = ctx
        if ctx["skip"]:
            continue
        entries, ctx["offset"] = read_new(path, ctx["offset"])
        if ctx["skip"] is None:
            ctx["skip"] = skip_reason(entries)
        if not ctx["skip"] and _is_retro(entries):
            ctx["skip"] = "retro"
        if ctx["skip"]:
            continue
        start = ctx["last_ts"]
        recs = extract(entries, ctx, skills, path.parent.name, patterns)
        out.extend(recs)
        answers = {r["answer"] for r in recs if r["kind"] == "decision" and r.get("via") == "text"}
        for entry, text in _candidates(entries, start, cutoff, answers):
            key = normalise(text)
            seen = sum(1 for h in history if h.get("key") == key)
            ts = entry.get("timestamp")
            session = entry.get("sessionId")
            if seen >= 2:
                out.append({
                    "id": "%s:%s:repeat:0" % (session, entry.get("uuid")), "kind": "repeat",
                    "session": session, "project": path.parent.name, "ts": ts,
                    "skills": list(ctx["skills"]), "excerpt": redact(text)[:EXCERPT_MAX],
                    "key": key, "count": seen + 1,
                })
            history.append({"key": key, "ts": ts, "session": session})
    _write(retro / "digest.next.jsonl", _jsonl(out))
    _write(retro / "instructions.next.jsonl", _jsonl(history))
    _write(retro / "state.next.json", json.dumps(_clean({"files": files, "last_run": now}), ensure_ascii=False))
    print(redact("records: %d file: %s" % (len(out), retro / "digest.next.jsonl")))
    return 0


def _commit(args) -> int:
    retro = Path(args.home).expanduser().resolve() / "retro"
    if not (retro / "state.next.json").exists():
        return 2
    os.replace(retro / "state.next.json", retro / "state.json")
    os.replace(retro / "instructions.next.jsonl", retro / "instructions.jsonl")
    if (retro / "digest.next.jsonl").exists():
        os.replace(retro / "digest.next.jsonl", retro / "digest.jsonl")
    return 0


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="digest.py")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--config-dir")
    run.add_argument("--home", required=True)
    run.add_argument("--now")
    commit = sub.add_parser("commit")
    commit.add_argument("--home", required=True)
    args = parser.parse_args(argv)
    return _run(args) if args.command == "run" else _commit(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
