import json
import os
import re
from pathlib import Path
from typing import FrozenSet, List, Optional, Tuple

BUILTINS = frozenset([
    "clear", "compact", "model", "config", "resume", "login", "logout", "exit",
    "cost", "status", "help", "fast", "context", "memory", "permissions", "doctor",
])

INTERACTIVE_ENTRYPOINTS = ("cli", "claude-desktop")
IGNORED_PREFIXES = ("Base directory for this skill", "This session is being continued", "[Request interrupted")
COMMAND_RE = re.compile(
    r"<command-message>.*?</command-message>\s*<command-name>/?([^<\s]+)</command-name>"
    r"(?:\s*<command-args>(.*?)</command-args>)?",
    re.DOTALL,
)


def config_dir(arg: Optional[str]) -> Path:
    raw = arg or os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"
    return Path(raw).expanduser().resolve()


def list_transcripts(config_dir: Path) -> List[Path]:
    found = {path.resolve() for path in (config_dir / "projects").glob("*/*.jsonl")}
    return sorted(found)


def read_new(path: Path, offset: int) -> Tuple[List[dict], int]:
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() < offset:
            offset = 0
        handle.seek(offset)
        data = handle.read()
    end = data.rfind(b"\n") + 1
    entries = []
    for line in data[:end].splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries, offset + end


def _text_of(content) -> Optional[str]:
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content:
        parts = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                return None
            parts.append(block.get("text") or "")
        return "\n".join(parts)
    return None


def operator_text(entry: dict) -> Optional[str]:
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return None
    message = entry.get("message")
    text = _text_of(message.get("content")) if isinstance(message, dict) else None
    if text is None:
        return None
    text = text.strip()
    if "<local-command-caveat>" in text or "<local-command-stdout>" in text:
        return None
    command = COMMAND_RE.search(text)
    if command:
        name = command.group(1)
        if name in BUILTINS:
            return None
        return ("/%s %s" % (name, command.group(2) or "")).strip()
    if text.startswith("<") or text.startswith(IGNORED_PREFIXES):
        return None
    return text or None


def skip_reason(entries: List[dict]) -> Optional[str]:
    for entry in entries:
        if "entrypoint" in entry:
            if entry["entrypoint"] not in INTERACTIVE_ENTRYPOINTS:
                return "headless"
            break
    for entry in entries:
        text = operator_text(entry)
        if text is not None:
            if text == "/retro" or text.startswith("/retro "):
                return "retro"
            return ""
    return None
