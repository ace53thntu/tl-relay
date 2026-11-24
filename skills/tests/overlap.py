import hashlib
import pathlib
import re
import sys
from typing import Iterator, NamedTuple, Tuple

from test_skills import SKILLS, skill_files

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
UPSTREAM = FIXTURES / "upstream-lines.sha256"
FIXED = FIXTURES / "overlap-fixed-lines.txt"

MAINTAINER_SKILLS = SKILLS.parent / "maintainer" / "skills"

MIN_LENGTH = 20
MAX_SHARE = 0.10
MAX_RUN = 3
MAX_EXEMPTED = 5


class Verdict(NamedTuple):
    counted: int
    matched: int
    longest_run: int
    passes: bool
    exempted: int


def normalise(line):
    text = re.sub(r"\s+", " ", line.strip()).lower()
    return text if len(text) >= MIN_LENGTH else None


def line_hash(normalised):
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def file_verdict(text, upstream, fixed):
    counted = matched = longest = run = exempted = 0
    for line in text.splitlines():
        normalised = normalise(line)
        if normalised is None:
            continue
        digest = line_hash(normalised)
        if digest in fixed:
            exempted += 1
            continue
        counted += 1
        if digest in upstream:
            matched += 1
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    passes = (
        matched <= MAX_SHARE * counted and longest < MAX_RUN and exempted <= MAX_EXEMPTED
    )
    return Verdict(counted, matched, longest, passes, exempted)


def _data_lines(path):
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def load_upstream():
    return set(_data_lines(UPSTREAM))


def load_fixed():
    fixed = {}
    for line in FIXED.read_text(encoding="utf-8").splitlines():
        if line.strip():
            path, digest, _reason = line.split("\t")
            fixed.setdefault(path, set()).add(digest)
    return fixed


def overlap_files() -> Iterator[Tuple[pathlib.Path, str]]:
    for path in skill_files():
        yield path, str(path.relative_to(SKILLS))
    for directory in sorted(MAINTAINER_SKILLS.iterdir()):
        if not (directory / "SKILL.md").is_file():
            continue
        for path in sorted(directory.rglob("*")):
            rel = path.relative_to(MAINTAINER_SKILLS)
            if any(p == "__pycache__" or p.startswith(".venv") for p in rel.parts):
                continue
            if path.is_file():
                yield path, str(rel)


def report():
    upstream, fixed = load_upstream(), load_fixed()
    for path, rel in overlap_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        v = file_verdict(text, upstream, fixed.get(rel, set()))
        share = 100 * v.matched / v.counted if v.counted else 0
        status = "PASS" if v.passes else "FAIL"
        print(f"{status} {share:.0f}% {v.matched}/{v.counted} run={v.longest_run} {rel}")


if __name__ == "__main__":
    if sys.argv[1:] == ["report"]:
        report()
    else:
        sys.exit("usage: overlap.py report")
