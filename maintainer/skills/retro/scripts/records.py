import importlib.util
import json
import re
from pathlib import Path
from typing import FrozenSet, List, Optional

from transcripts import operator_text

REPO = Path(__file__).resolve().parents[4]
EXCERPT_MAX = 600

_spec = importlib.util.spec_from_file_location("redact_secrets_output", REPO / "maintainer" / "hooks" / "redact-secrets-output.py")
_hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hook)

OPTION_RE = re.compile(r"^\s*[-*]?\s*\**\s*([A-D1-4])[.)]")
BASE_WORDS = {
    "recommended": ["recommended"],
    "correction_prefix": ["no", "wrong", "don't", "stop", "wait"],
    "correction_rule": ["from now on"],
}
REJECTED_MARK = "user doesn't want to proceed"


def redact(text: str) -> str:
    return _hook.redact(text)


def compile_patterns(extra: Optional[dict] = None) -> dict:
    extra = extra or {}
    if not isinstance(extra, dict) or set(extra) - set(BASE_WORDS):
        raise ValueError("patterns take only the keys: %s" % ", ".join(BASE_WORDS))
    alt = {}
    for key, base in BASE_WORDS.items():
        more = extra.get(key, [])
        if not isinstance(more, list) or not all(isinstance(w, str) and w.strip() for w in more):
            raise ValueError("%s must be a list of non-empty strings" % key)
        alt[key] = "|".join(re.escape(w) for w in sorted(set(base + more), key=len, reverse=True))
    return {
        "recommended": re.compile(alt["recommended"], re.IGNORECASE),
        "correction_prefix": re.compile(r"^(%s)\b" % alt["correction_prefix"], re.IGNORECASE),
        "correction_rule": re.compile(alt["correction_rule"], re.IGNORECASE),
    }


def load_patterns(path: Path) -> dict:
    if not path.exists():
        return compile_patterns()
    return compile_patterns(json.loads(path.read_text(encoding="utf-8")))


def repo_skills(repo: Path) -> FrozenSet[str]:
    roots = (repo / "skills", repo / "maintainer" / "skills")
    return frozenset(p.parent.name for root in roots for p in root.glob("*/SKILL.md"))


def _clean(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _interrupt(entry: dict) -> bool:
    if entry.get("type") != "user":
        return False
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = "".join(b.get("text") or "" for b in content if isinstance(b, dict))
    return isinstance(content, str) and content.lstrip().startswith("[Request interrupted")


def _text_question(text: str, recommended_re):
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or not lines[-1].rstrip().endswith("?"):
        return None
    labels = []
    recommended = None
    for line in lines:
        match = OPTION_RE.match(line)
        if match:
            labels.append(match.group(1))
            if recommended is None and recommended_re.search(line):
                recommended = match.group(1)
    if len(labels) < 2:
        return None
    return lines[-1].strip(), labels, recommended


class _Run:
    def __init__(self, ctx: dict, skills: FrozenSet[str], project: str, patterns: dict):
        ctx.setdefault("skills", [])
        ctx.setdefault("pending", None)
        ctx.setdefault("last_ts", None)
        ctx.setdefault("prev_assistant", False)
        ctx.setdefault("ask_ids", [])
        self.ctx = ctx
        self.known = skills
        self.project = project
        self.patterns = patterns
        self.out = []
        self.counts = {}
        self.emit = True

    def add(self, entry: dict, kind: str, excerpt: str, uuid: Optional[str] = None, ts: Optional[str] = None, **fields):
        uuid = uuid or entry.get("uuid")
        key = (uuid, kind)
        n = self.counts.get(key, 0)
        self.counts[key] = n + 1
        if not self.emit:
            return
        session = entry.get("sessionId")
        record = {
            "id": "%s:%s:%s:%d" % (session, uuid, kind, n),
            "kind": kind,
            "session": session,
            "project": self.project,
            "ts": ts or entry.get("timestamp"),
            "skills": list(self.ctx["skills"]),
            "excerpt": excerpt,
        }
        record.update(fields)
        cleaned = {k: _clean(v) for k, v in record.items()}
        cleaned["excerpt"] = cleaned["excerpt"][:EXCERPT_MAX]
        self.out.append(cleaned)

    def use_skill(self, entry: dict, name: str):
        if name not in self.known:
            return
        skills = self.ctx["skills"]
        if name in skills:
            skills.remove(name)
        skills.insert(0, name)
        self.add(entry, "skill_run", name, skill=name)

    def assistant(self, entry: dict):
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "AskUserQuestion":
                ids = self.ctx["ask_ids"]
                ids.append(block.get("id"))
                del ids[:-20]
            elif block.get("type") == "tool_use" and block.get("name") == "Skill":
                name = (block.get("input") or {}).get("skill")
                if isinstance(name, str):
                    self.use_skill(entry, name)
            elif block.get("type") == "text":
                text = block.get("text") or ""
                found = _text_question(text, self.patterns["recommended"])
                if found:
                    question, options, recommended = found
                    self.ctx["pending"] = {
                        "uuid": entry.get("uuid"), "ts": entry.get("timestamp"), "question": redact(question),
                        "options": [redact(o) for o in options], "recommended": recommended,
                        "skills": list(self.ctx["skills"]),
                        "excerpt": redact(text)[:EXCERPT_MAX],
                    }

    def tool_result(self, entry: dict):
        result = entry.get("toolUseResult")
        if isinstance(result, dict) and result.get("questions") and isinstance(result.get("answers"), dict):
            for question in result["questions"]:
                if not isinstance(question, dict):
                    continue
                text = question.get("question") or ""
                labels = [o.get("label") for o in question.get("options") or [] if isinstance(o, dict)]
                recommended = next((l for l in labels if l and "(Recommended)" in l), None)
                self.add(entry, "decision", text, via="ask", question=text, options=labels,
                         recommended=recommended, answer=result["answers"].get(text))
        elif isinstance(result, str) and REJECTED_MARK in result and self._answers_ask(entry):
            self.add(entry, "correction", result, marker="rejected")

    def _answers_ask(self, entry: dict) -> bool:
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            return False
        return any(isinstance(b, dict) and b.get("type") == "tool_result"
                   and b.get("tool_use_id") in self.ctx["ask_ids"] for b in content)

    def operator(self, entry: dict, text: str, after_assistant: bool):
        match = re.match(r"/([^\s]+)", text)
        if match:
            self.use_skill(entry, match.group(1))
        prefix = self.patterns["correction_prefix"].match(text)
        pending = self.ctx["pending"]
        if pending:
            self.ctx["pending"] = None
            self.add(entry, "decision", pending.get("excerpt") or pending["question"],
                     uuid=pending["uuid"], ts=entry.get("timestamp"), via="text",
                     question=pending["question"], options=pending["options"],
                     recommended=pending["recommended"], answer=text)
            rule = None
        else:
            rule = self.patterns["correction_rule"].search(text)
        marker = prefix or rule
        if after_assistant and marker:
            self.add(entry, "correction", text, marker=marker.group(0).lower())


def extract(entries: List[dict], ctx: dict, skills: FrozenSet[str], project: str,
            patterns: Optional[dict] = None) -> List[dict]:
    run = _Run(ctx, skills, project, patterns or compile_patterns())
    start = ctx["last_ts"]
    for entry in entries:
        ts = entry.get("timestamp")
        run.emit = start is None or (ts is not None and ts > start)
        kind = entry.get("type")
        if kind == "assistant":
            run.assistant(entry)
        elif kind == "user":
            run.tool_result(entry)
            text = operator_text(entry)
            if text is not None:
                run.operator(entry, text, ctx["prev_assistant"])
        if kind in ("user", "assistant"):
            if not _interrupt(entry):
                ctx["prev_assistant"] = kind == "assistant"
            if ts is not None and (ctx["last_ts"] is None or ts > ctx["last_ts"]):
                ctx["last_ts"] = ts
    return run.out
