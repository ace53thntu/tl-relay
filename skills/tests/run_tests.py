import argparse
import os
import pathlib
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

HEAVY = ("test_final_run", "test_triggers")
HEAVY_PREFIXES = ("maintainer/skills/write-skill/scripts/", "maintainer/runtime/", "maintainer/hooks/", "hooks/",
                  "skills/tests/", "skills/using-tl-relay/")
GIT_ENV_DROP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")


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
            for name in sorted({type(t).__name__ for t in tests}):
                units.append("%s.%s" % (module, name))
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


def run(tests_dir, skip, jobs, out) -> int:
    units = collect_units(tests_dir, skip)

    def run_unit(unit):
        return subprocess.run([sys.executable, "-m", "unittest", "-q", unit], cwd=str(tests_dir),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    with ThreadPoolExecutor(max(1, jobs)) as pool:
        results = list(pool.map(run_unit, units))
    failed = 0
    for unit, proc in zip(units, results):
        if proc.returncode != 0 or b"\nOK" not in proc.stderr:
            failed += 1
            out.write("FAIL %s\n%s\n" % (unit, proc.stderr.decode(errors="replace")))
    if failed:
        out.write("FAILED (%d of %d units)\n" % (failed, len(units)))
        return 1
    out.write("OK (%d units)\n" % len(units))
    return 0


def main(argv, repo=None, tests_dir=None, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parsed = parser.parse_args(list(argv))
    jobs = parsed.jobs
    run_all = parsed.all
    tests_dir = pathlib.Path(tests_dir) if tests_dir else pathlib.Path(__file__).resolve().parent
    repo = pathlib.Path(repo) if repo else pathlib.Path(__file__).resolve().parents[2]
    skip = set()
    if not run_all:
        paths = changed_paths(repo)
        if paths is not None and not needs_heavy(paths):
            skip = set(HEAVY)
            out.write("skipped: test_final_run, test_triggers (diff touches no write-skill scripts, skills/tests, runtime, hooks, sdlc.py or using-tl-relay)\n")
    return run(tests_dir, skip, jobs, out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
