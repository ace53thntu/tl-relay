from __future__ import annotations

import hashlib
import json
import re

import fr_git

BOOTSTRAP = "skills/using-tl-relay/SKILL.md"
HOOK = "hooks/session-start-skills.sh"
RUNNER_FILES = ("skills/tests/run-triggers.sh", "skills/tests/triggers.py")
RUNNER_WORKSPACE = "skills/tests/fixtures/trigger-workspace/"
_SKILL = re.compile(r"(?:maintainer/)?skills/([^/]+)/SKILL\.md")
_PROMPT = re.compile(r"skills/tests/prompts/([^/.][^/]*\.txt)")
_INPUT_OR_PARENT = re.compile(
    r"(maintainer/)?skills(/[^/]+(/SKILL\.md)?)?|skills/tests/prompts(/[^/]+\.txt)?|hooks(/session-start-skills\.sh)?"
    r"|skills/tests/(run-triggers\.sh|triggers\.py)|skills/tests/fixtures(/trigger-workspace(/[^/]+)*)?"
)
_LINK_MODES = ("120000", "160000")
_BARE_CR = "bare CR in the frontmatter"
_KEY = re.compile(r"^([A-Za-z0-9_-]+):[ \t]*(.*)$")
TRIGGER_KEYS = ("name", "description", "when_to_use", "disable-model-invocation")
_KEYS = "|".join(TRIGGER_KEYS)
_ALTERNATE = re.compile(
    r"""\?[ \t]+(?P<a>["']?)(?:%s)(?P=a)[ \t]*(?::.*)?$|(?P<b>["']?)(?:%s)(?P=b)[ \t]*:""" % (_KEYS, _KEYS)
)


class InputError(Exception):
    pass


def frontmatter(text: str) -> dict:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].partition("\r")[0].rstrip() != "---":
        raise InputError("no frontmatter")
    if "\r" in lines[0]:
        raise InputError(_BARE_CR)
    fields = {}
    key = None
    for line in lines[1:]:
        if "\r" in line:
            raise InputError(_BARE_CR)
        if line.rstrip() == "---":
            break
        match = _KEY.match(line)
        if match and not line[0].isspace():
            key = match.group(1)
            fields[key] = match.group(2)
        elif _ALTERNATE.match(line):
            raise InputError("write the frontmatter key as a plain key: %r" % line)
        elif key is not None:
            fields[key] += "\n" + line
    else:
        raise InputError("unterminated frontmatter")
    return {k: v for k, v in fields.items() if k in TRIGGER_KEYS}


def identity(fields: dict) -> tuple:
    return tuple(fields.get(k) for k in TRIGGER_KEYS)


def _resolve(repo, rev) -> str:
    out = fr_git.run(repo, "rev-parse", "--verify", "--end-of-options", rev + "^{commit}").stdout
    return out.decode().strip()


def _entries(repo, sha) -> dict:
    out = fr_git.run(repo, "ls-tree", "-r", "-z", "--full-tree", sha, "--", "skills", "maintainer/skills", "hooks").stdout
    entries = {}
    for item in out.split(b"\0"):
        if not item:
            continue
        meta, _, path = item.partition(b"\t")
        mode, _, oid = meta.decode().split(" ")
        name = path.decode("utf-8", "surrogateescape")
        if mode in _LINK_MODES and _INPUT_OR_PARENT.fullmatch(name):
            raise InputError("%s is a link (mode %s)" % (name, mode))
        entries[name] = (mode, oid)
    return entries


def _blob(repo, entries, path) -> bytes:
    return fr_git.run(repo, "cat-file", "blob", entries[path][1]).stdout


def skills_at(repo, rev) -> dict:
    entries = _entries(repo, _resolve(repo, rev))
    found = {}
    for path in entries:
        match = _SKILL.fullmatch(path)
        if not match:
            continue
        fields = frontmatter(_blob(repo, entries, path).decode("utf-8", "replace"))
        for key in ("name", "description"):
            if key not in fields:
                raise InputError("%s has no %s" % (path, key))
        found[match.group(1)] = identity(fields)
    if not found:
        raise InputError("no skills found at %s" % rev)
    return found


def prompts_at(repo, rev) -> dict:
    entries = _entries(repo, _resolve(repo, rev))
    return {
        match.group(1): _blob(repo, entries, path)
        for path in entries
        for match in [_PROMPT.fullmatch(path)]
        if match
    }


def _is_runner(path) -> bool:
    return path in RUNNER_FILES or path.startswith(RUNNER_WORKSPACE)


def fingerprint(repo, rev) -> str:
    sha = _resolve(repo, rev)
    entries = _entries(repo, sha)
    doc = {
        "version": 3,
        "skills": {k: list(v) for k, v in skills_at(repo, sha).items()},
        "prompts": {k: v.hex() for k, v in prompts_at(repo, sha).items()},
        "bootstrap": _blob(repo, entries, BOOTSTRAP).hex() if BOOTSTRAP in entries else None,
        "hook": _blob(repo, entries, HOOK).hex() if HOOK in entries else None,
        "runner": {path: _blob(repo, entries, path).hex() for path in sorted(entries) if _is_runner(path)},
    }
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
