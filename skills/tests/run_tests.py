import argparse
import os
import pathlib
import subprocess
import sys
import unittest
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

HEAVY = ("test_final_run", "test_triggers")
HEAVY_PREFIXES = ("maintainer/skills/write-skill/scripts/", "maintainer/runtime/", "maintainer/hooks/", "hooks/",
                  "skills/tests/", "skills/using-tl-relay/")
GIT_ENV_DROP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")
HEAVY_SUITE = "skills/tests"

Suite = namedtuple("Suite", "path kind skip_unless")
Unit = namedtuple("Unit", "suite kind cwd argv")

SUITES: Tuple[Suite, ...] = (
    Suite("skills/tests", "py", None),
    Suite("maintainer/runtime/tests", "py", None),
    Suite("skills/ingest-sources/scripts", "py", None),
    Suite("skills/tl-design/scripts", "py", None),
    Suite("skills/write-contract/scripts", "py", None),
    Suite("skills/write-task-breakdown/scripts", "py", None),
    Suite("maintainer/skills/retro/scripts", "py", None),
    Suite("maintainer/hooks/tests/run.sh", "sh", None),
    Suite("skills/technical-writing/vale/test.sh", "sh", None),
)


def needs_heavy(paths) -> bool:
    for path in paths:
        if path == "maintainer/sdlc.py":
            return True
        if path.startswith("skills/tests/prompts/"):
            continue
        if path.startswith(HEAVY_PREFIXES):
            return True
    return False


def git_output(repo, *args) -> Optional[bytes]:
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_DROP}
    try:
        proc = subprocess.run(["git", "-C", str(repo)] + list(args), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def changed_paths(repo) -> Optional[List[str]]:
    base = git_output(repo, "merge-base", "refs/remotes/origin/main", "HEAD")
    if base is None:
        return None
    base_sha = base.decode("utf-8", "surrogateescape").strip()
    diff = git_output(repo, "diff", "--no-renames", "-z", "--name-only", base_sha)
    untracked = git_output(repo, "ls-files", "-z", "--others", "--exclude-standard")
    if diff is None or untracked is None:
        return None
    names = (diff.decode("utf-8", "surrogateescape").split("\0")
             + untracked.decode("utf-8", "surrogateescape").split("\0"))
    return sorted({name for name in names if name})


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def _inside(path, root) -> bool:
    if not path:
        return False
    try:
        pathlib.Path(path).resolve().relative_to(root)
    except ValueError:
        return False
    return True


def collect_units(tests_dir, skip) -> List[str]:
    saved = dict(sys.modules)
    root = pathlib.Path(tests_dir).resolve()
    sys.path.insert(0, str(tests_dir))
    units = []
    try:
        for path in sorted(pathlib.Path(tests_dir).glob("test_*.py")):
            module = path.stem
            if module in skip:
                continue
            cached = sys.modules.get(module)
            if cached is not None and not _inside(getattr(cached, "__file__", None), root):
                sys.modules.pop(module, None)
            try:
                tests = list(flatten(unittest.defaultTestLoader.loadTestsFromName(module)))
            except (Exception, SystemExit):
                units.append(module)
                continue
            if any(type(t).__name__ == "_FailedTest" for t in tests):
                units.append(module)
                continue
            units.extend(sorted({"%s.%s.%s" % (module, type(t).__name__, t._testMethodName) for t in tests}))
    finally:
        sys.path.remove(str(tests_dir))
        for name in list(sys.modules):
            if name in saved and sys.modules[name] is saved[name]:
                continue
            if _inside(getattr(sys.modules[name], "__file__", None), root):
                sys.modules.pop(name, None)
        for name, module in saved.items():
            if sys.modules.get(name) is not module:
                sys.modules[name] = module
    return units


def suite_units(repo, suite, skip) -> List[Unit]:
    if suite.kind == "sh":
        return [Unit(suite.path, "sh", repo, ["sh", str(repo / suite.path)])]
    tests_dir = repo / suite.path
    return [Unit(suite.path, "py", tests_dir, [sys.executable, "-m", "unittest", "-q", name])
            for name in collect_units(tests_dir, skip)]


def order(units) -> List[Unit]:
    return sorted(units, key=lambda unit: not unit.argv[-1].startswith("test_final_run"))


def run(units, jobs, out) -> int:
    units = order(units)

    def run_unit(unit):
        return subprocess.run(unit.argv, cwd=str(unit.cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    with ThreadPoolExecutor(max(1, jobs)) as pool:
        results = list(pool.map(run_unit, units))
    failed = 0
    for unit, proc in zip(units, results):
        if unit.kind == "py":
            passed = proc.returncode == 0 and b"\nOK" in proc.stderr
            detail = proc.stderr
            name = unit.argv[-1]
        else:
            passed = proc.returncode == 0
            detail = proc.stdout + proc.stderr
            name = unit.suite
        if not passed:
            failed += 1
            out.write("FAIL %s %s\n%s\n" % (unit.suite, name, detail.decode(errors="replace")))
    if failed:
        out.write("FAILED (%d of %d units)\n" % (failed, len(units)))
        return 1
    out.write("OK (%d units)\n" % len(units))
    return 0


def main(argv, repo=None, suites=None, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parsed = parser.parse_args(list(argv))
    suites = SUITES if suites is None else suites
    repo = pathlib.Path(repo) if repo else pathlib.Path(__file__).resolve().parents[2]
    heavy_skip = set()
    if not parsed.all and any(suite.path == HEAVY_SUITE for suite in suites):
        paths = changed_paths(repo)
        if paths is not None and not needs_heavy(paths):
            heavy_skip = set(HEAVY)
            out.write("skipped: test_final_run, test_triggers (diff touches no write-skill scripts, skills/tests, runtime, hooks, sdlc.py or using-tl-relay)\n")
    units = []
    for suite in suites:
        units.extend(suite_units(repo, suite, heavy_skip if suite.path == HEAVY_SUITE else set()))
    return run(units, parsed.jobs, out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
