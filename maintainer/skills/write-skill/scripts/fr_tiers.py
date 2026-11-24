from __future__ import annotations

import difflib
import re
from typing import Iterable, NamedTuple, Optional, Set

import fr_git
import fr_inputs

STRICT_PASS = 4
STRICT_FAIL = 2
NEIGHBOUR_RETRY = 4
_SEPARATOR = re.compile(r"\|[\s|:-]*-[\s|:-]*")
_DELIMITER_CELL = re.compile(r":?-+:?")
_NEW_ROW_NAME = re.compile(r"`([a-z0-9][a-z0-9-]*)`")
_LISTED_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")


class Changes(NamedTuple):
    skills: Set[str]
    removed: Set[str]
    identity_changed: bool
    all_strict: bool
    session_hook_changed: bool


def judge(tier: str, results: list) -> str:
    if tier == "strict":
        if results.count("FAIL") >= STRICT_FAIL:
            return "fail"
        return "pass" if results.count("PASS") >= STRICT_PASS else "more"
    if tier != "neighbour":
        raise ValueError("unknown tier %r" % tier)
    if "FAIL" not in results:
        return "pass" if results else "more"
    later = results[results.index("FAIL") + 1:]
    if "FAIL" in later:
        return "fail"
    return "pass" if later.count("PASS") >= NEIGHBOUR_RETRY else "more"


def owner(prompt: str, skills: Iterable[str]) -> Optional[str]:
    matches = [name for name in skills if prompt.startswith(name + "-")]
    return max(matches, key=len) if matches else None


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip()[1:-1].split("|")]


def _listed_names(line: str) -> set:
    return set(_LISTED_NAME.findall(_cells(line)[0].lower()))


def _table_rows(lines: list) -> range:
    headings = [i for i, line in enumerate(lines) if line.rstrip() == "## Skills"]
    if len(headings) != 1:
        return range(0)
    head = headings[0] + 1
    while head < len(lines) and not lines[head].strip():
        head += 1
    if head + 1 >= len(lines):
        return range(0)
    delimiter = lines[head + 1]
    if not lines[head].startswith("|") or not delimiter.startswith("|") or not delimiter.rstrip().endswith("|"):
        return range(0)
    cells = _cells(delimiter)
    if len(_cells(lines[head])) != len(cells) or not all(_DELIMITER_CELL.fullmatch(c) for c in cells):
        return range(0)
    end = head + 2
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return range(head + 2, end)


def rows_only(old: str, new: str, added: Iterable[str]) -> bool:
    old_lines, new_lines = old.split("\n"), new.split("\n")
    rows = _table_rows(new_lines)
    if not rows:
        return old == new
    header = len(_cells(new_lines[rows.start - 2]))
    opcodes = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes()
    inserted = {j for tag, _, _, j1, j2 in opcodes if tag == "insert" for j in range(j1, j2)}
    seen = set()
    for j in rows:
        if j not in inserted:
            seen |= _listed_names(new_lines[j])
    allowed = set(added)
    for tag, _, _, j1, j2 in opcodes:
        if tag == "equal":
            continue
        if tag != "insert":
            return False
        for j in range(j1, j2):
            line = new_lines[j]
            if j not in rows or not line.rstrip().endswith("|") or _SEPARATOR.fullmatch(line.strip()):
                return False
            if len(_cells(line)) != header:
                return False
            match = _NEW_ROW_NAME.fullmatch(_cells(line)[0])
            if not match or match.group(1) not in allowed or match.group(1) in seen:
                return False
            seen.add(match.group(1))
    return True


def _show(repo, rev, path) -> Optional[bytes]:
    result = fr_git.run(repo, "show", "%s:%s" % (rev, path), check=False)
    return result.stdout if result.returncode == 0 else None


def changes(repo, base, head) -> Changes:
    old, new = fr_inputs.skills_at(repo, base), fr_inputs.skills_at(repo, head)
    old_prompts, new_prompts = fr_inputs.prompts_at(repo, base), fr_inputs.prompts_at(repo, head)
    removed = set(old) - set(new)
    changed = removed | {k for k in new if old.get(k) != new[k]}
    identity = bool(changed)
    names = set(old) | set(new)
    for key in set(old_prompts) | set(new_prompts):
        if old_prompts.get(key) != new_prompts.get(key):
            found = owner(key, names)
            if found:
                changed.add(found)
    old_boot = _show(repo, base, fr_inputs.BOOTSTRAP)
    new_boot = _show(repo, head, fr_inputs.BOOTSTRAP)
    all_strict = old_boot != new_boot and not (
        old_boot is not None
        and new_boot is not None
        and rows_only(
            old_boot.decode("utf-8", "replace"),
            new_boot.decode("utf-8", "replace"),
            {k for k in set(new) - set(old) if new[k][0].strip() == k},
        )
    )
    return Changes(
        changed,
        removed,
        identity,
        all_strict,
        _show(repo, base, fr_inputs.HOOK) != _show(repo, head, fr_inputs.HOOK),
    )


def tier_of(prompt: str, change: Changes, skills: Iterable[str]) -> str:
    if prompt.startswith("heldout/"):
        return "strict"
    name = prompt[len("committed/"):] if prompt.startswith("committed/") else prompt
    if change.all_strict or owner(name, set(skills) | change.removed) in change.skills:
        return "strict"
    return "neighbour"
