from __future__ import annotations

import os
import pathlib
import subprocess


MAIN = "refs/remotes/origin/main"


class GitError(Exception):
    pass


def _clean_env() -> dict:
    env = dict(os.environ)
    try:
        probe = subprocess.run(
            ["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True, env=env
        )
    except OSError as exc:
        raise GitError("cannot run git: %s" % exc)
    for name in probe.stdout.split():
        env.pop(name, None)
    return env


def run(repo, *args, check=True) -> "subprocess.CompletedProcess[bytes]":
    env = _clean_env()
    try:
        result = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args], capture_output=True, env=env)
    except OSError as exc:
        raise GitError("cannot run git: %s" % exc)
    if check and result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise GitError("git %s failed: %s" % (" ".join(args), detail))
    return result


def _path(repo, *args) -> pathlib.Path:
    out = run(repo, *args).stdout.decode("utf-8", "surrogateescape").strip()
    return pathlib.Path(out)


def common_dir(repo) -> pathlib.Path:
    path = _path(repo, "rev-parse", "--git-common-dir")
    if not path.is_absolute():
        path = pathlib.Path(repo) / path
    return path.resolve()


def toplevel(repo) -> pathlib.Path:
    return _path(repo, "rev-parse", "--show-toplevel")


def merge_base(repo, rev="HEAD") -> str:
    out = run(repo, "merge-base", rev, MAIN).stdout
    return out.decode().strip()
