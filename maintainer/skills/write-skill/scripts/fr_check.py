from __future__ import annotations

import os
import pathlib
import shlex
import shutil
import subprocess
import sys

import fr_git
import fr_inputs
import fr_lock
import fr_record
import fr_score
import fr_tiers

_MAIN = fr_git.MAIN
_FINAL_RUN = pathlib.Path(__file__).resolve().with_name("final_run.py")
_TOUCHED = ("skills/", fr_inputs.HOOK)


class Blocked(Exception):
    def __init__(self, rule, reason, command, code=1, label="Run"):
        super().__init__(reason)
        self.rule, self.reason, self.command, self.code, self.label = rule, reason, command, code, label


def _one_line(text, limit=3) -> str:
    lines = text.strip().splitlines() or ["no output"]
    more = " (+%d more)" % (len(lines) - limit) if len(lines) > limit else ""
    return " | ".join(lines[:limit]) + more


def _home() -> pathlib.Path:
    return fr_lock._home()


def _command(*argv) -> str:
    return "AI_SDLC_HOME=%s %s" % (shlex.quote(str(_home())), shlex.join([str(a) for a in argv]))


def _final_run(repo, *args) -> str:
    return _command(sys.executable, _FINAL_RUN, "--repo", repo, *args)


def _commit(repo, rev) -> str:
    out = fr_git.run(repo, "rev-parse", "--verify", "--end-of-options", rev + "^{commit}").stdout
    return out.decode().strip()


def _touches(repo, base, sha) -> bool:
    out = fr_git.run(
        repo, "-c", "log.showSignature=false", "log", "--no-show-signature", "--diff-merges=separate",
        "--ignore-submodules=none",
        "--no-renames", "-z", "--format=", "--name-only", "%s..%s" % (base, sha)
    ).stdout
    for raw in out.split(b"\0"):
        path = raw.decode("utf-8", "surrogateescape")
        if path.startswith((_TOUCHED[0], "maintainer/skills/")) or path == _TOUCHED[1]:
            return True
    return False


def _trigger_check(repo, base, sha):
    fp = fr_inputs.fingerprint(repo, sha)
    if fp in (fr_inputs.fingerprint(repo, base), fr_inputs.fingerprint(repo, _MAIN)):
        return None
    score = _final_run(repo, "score", "--heldout") + " <dir>"
    if fr_tiers.changes(repo, base, sha).session_hook_changed:
        return Blocked(
            5, "the session hook changed and cannot get a PASS",
            "stop and ask the operator, who decides whether to push with --no-verify "
            "and measure after the merge",
            label="Next",
        )
    try:
        rows = fr_record.load(repo)
    except fr_record.RecordError as exc:
        raise Blocked(5, str(exc), score, code=2)
    verdict = fr_record.verdict_for(rows, fp)
    if verdict != "PASS":
        raise Blocked(5, "no PASS verdict for fingerprint %s (found %s)" % (fp[:12], verdict), score)
    return None


def _overlap(repo, sha) -> None:
    export = fr_score._export(repo, sha)
    try:
        done = subprocess.run(
            [sys.executable, str(export / "skills" / "tests" / "overlap.py"), "report"],
            cwd=str(export), env=fr_git._clean_env(), capture_output=True,
        )
    finally:
        shutil.rmtree(str(export), ignore_errors=True)
    out = done.stdout.decode("utf-8", "replace")
    failed = [line for line in out.splitlines() if line.startswith("FAIL")]
    if done.returncode != 0 or failed:
        detail = _one_line("\n".join(failed) or done.stderr.decode("utf-8", "replace") or "exit %d" % done.returncode)
        raise Blocked(6, "overlap report failed: %s" % detail, "python3 skills/tests/overlap.py report")


def _neutral(repo, base, sha) -> None:
    _run_neutral(repo, "--range=%s..%s" % (base, sha))


def _run_neutral(repo, scope) -> None:
    root = os.environ.get("AI_SDLC_REPO")
    if not root:
        raise Blocked(7, "AI_SDLC_REPO is not set", "export AI_SDLC_REPO=<ai-sdlc checkout>")
    top = fr_git.toplevel(repo)
    argv = [sys.executable, str(pathlib.Path(root) / "maintainer" / "sdlc.py"), "check-neutral",
            "--repo", str(top), scope]
    done = subprocess.run(argv, env=fr_git._clean_env(), capture_output=True)
    if done.returncode != 0:
        detail = _one_line((done.stdout + done.stderr).decode("utf-8", "replace"))
        raise Blocked(7, "check-neutral exited %d: %s" % (done.returncode, detail), _command(*argv))


def _require_home(rule) -> None:
    if not os.environ.get("AI_SDLC_HOME"):
        raise Blocked(rule, "AI_SDLC_HOME is not set", "export AI_SDLC_HOME=<ai-sdlc home>")
    fr_lock._home()


def _scan_tag_objects(repo, local_sha, remote_ref) -> None:
    kind = fr_git.run(repo, "cat-file", "-t", local_sha, check=False)
    if kind.returncode != 0:
        raise Blocked(7, "cannot read the object pushed to %s" % remote_ref, "stop and ask the operator", label="Next")
    if kind.stdout.strip() != b"tag":
        return
    _require_home(7)
    _run_neutral(repo, "--tag-object=%s" % local_sha)


def _scan_unmerged(repo, local_sha, remote_ref) -> None:
    try:
        main = _commit(repo, _MAIN)
    except fr_git.GitError:
        raise Blocked(2, "refs/remotes/origin/main is missing", "git fetch origin main")
    try:
        sha = _commit(repo, local_sha)
    except fr_git.GitError:
        raise Blocked(7, "%s does not peel to a commit, so check-neutral cannot scan it" % remote_ref,
                      "stop and ask the operator", label="Next")
    if not fr_git.run(repo, "rev-list", "--max-count=1", "%s..%s" % (main, sha)).stdout.strip():
        return
    _require_home(7)
    _neutral(repo, main, sha)


def _update(repo, line):
    parts = line.split()
    if len(parts) != 4:
        raise Blocked(1, "malformed ref update %r" % line, "git push")
    _, local_sha, remote_ref, _ = parts
    if set(local_sha) == {"0"}:
        return None
    _scan_tag_objects(repo, local_sha, remote_ref)
    if remote_ref.startswith(("refs/tags/", "refs/notes/")):
        _scan_unmerged(repo, local_sha, remote_ref)
        return None
    try:
        _commit(repo, _MAIN)
    except fr_git.GitError:
        raise Blocked(2, "refs/remotes/origin/main is missing", "git fetch origin main")
    sha = _commit(repo, local_sha)
    out = fr_git.run(repo, "merge-base", sha, _MAIN, check=False)
    base = out.stdout.decode().strip()
    if out.returncode != 0 or not base:
        raise Blocked(2, "%s shares no history with origin/main" % remote_ref, "git rebase origin/main")
    if not _touches(repo, base, sha):
        return None
    _require_home(5)
    pending = _trigger_check(repo, base, sha)
    _overlap(repo, sha)
    _neutral(repo, base, sha)
    return pending


def check(repo, stdin) -> int:
    try:
        try:
            lines = [ln for ln in stdin.read().splitlines() if ln.strip()]
            deferred = [_update(repo, line) for line in lines]
            for pending in deferred:
                if pending:
                    raise pending
        except Blocked as exc:
            fr_score._write(
                sys.stderr, "blocked by rule %d: %s. %s: %s\n" % (exc.rule, exc.reason, exc.label, exc.command)
            )
            return exc.code
        except fr_lock.HomeError as exc:
            fr_score._say("blocked: %s" % exc)
            return 2
        except (fr_git.GitError, fr_inputs.InputError, fr_lock.LockError, fr_record.RecordError,
                OSError, UnicodeError) as exc:
            fr_score._say("blocked: cannot decide: %s" % exc)
            return 1
        except Exception:
            fr_score._say_traceback()
            return 1
        return 0
    finally:
        fr_score._settle_streams()
