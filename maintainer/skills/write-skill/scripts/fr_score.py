from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import traceback

import fr_git
import fr_inputs
import fr_lock
import fr_record
import fr_tiers

PASS, FAIL, ERROR = "PASS", "FAIL", "ERROR"
_SUMMARY = re.compile(r"(\d+)/(\d+)")
_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
_GRACE_SECONDS = 15
EXPORT_PREFIX = "final-run-export."


class Refused(Exception):
    pass


class Interrupted(Exception):
    pass


def _write(stream, text: str) -> None:
    if stream is None:
        return
    try:
        stream.write(text)
    except (OSError, ValueError):
        pass


def _say(text: str) -> None:
    _write(sys.stderr, "final_run: %s\n" % text)


def _say_traceback() -> None:
    if sys.stderr is None:
        return
    try:
        traceback.print_exc()
    except (OSError, ValueError):
        pass


def _settle_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.flush()
        except (OSError, ValueError):
            try:
                null = os.open(os.devnull, os.O_WRONLY)
                os.dup2(null, stream.fileno())
                os.close(null)
            except (OSError, ValueError):
                pass


def read_heldout(directory, repo):
    path = pathlib.Path(directory).resolve()
    if not path.is_dir():
        raise Refused("%s is not a directory" % directory)
    top = pathlib.Path(fr_git.toplevel(repo)).resolve()
    if path == top or top in path.parents:
        raise Refused("the held-out directory must sit outside the checkout %s" % top)
    files = {p.name: p.read_bytes() for p in sorted(path.iterdir()) if p.suffix == ".txt" and not p.name.startswith(".") and p.is_file()}
    if not files:
        raise Refused("%s holds no .txt prompt" % directory)
    doc = [[name, data.hex()] for name, data in sorted(files.items())]
    return hashlib.sha256(json.dumps(doc, separators=(",", ":")).encode("utf-8")).hexdigest(), files


def _check_heldout(files, skills) -> None:
    known = (set(skills) | {fields[0] for fields in skills.values()}) - {fr_inputs.BOOTSTRAP.split("/")[1]}
    for name, data in sorted(files.items()):
        head, sep, prompt = data.partition(b"\n")
        skill = head[len(b"expect: "):].decode("utf-8", "replace")
        if not (head.startswith(b"expect: ") and sep and skill in known and prompt.strip()):
            raise Refused(
                "held-out prompt %s must start with an LF-terminated 'expect: <skill>' line "
                "naming a non-bootstrap skill at HEAD, followed by a prompt" % name
            )


def _require_clean(repo) -> None:
    out = fr_git.run(repo, "status", "--porcelain", "--untracked-files=all").stdout
    if out.strip():
        raise Refused("the worktree has staged, unstaged or untracked changes")
    if fr_git.run(repo, "rev-parse", "--verify", "--quiet", fr_git.MAIN + "^{commit}", check=False).returncode != 0:
        raise Refused("%s does not resolve locally" % fr_git.MAIN)


def _check_hook_home(repo) -> None:
    hook = fr_git.common_dir(repo) / "hooks" / "pre-push"
    try:
        text = hook.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return
    except OSError as exc:
        raise Refused("cannot read %s: %s" % (hook, exc))
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
    from runtime import install
    if not install.is_own_hook(text):
        return
    named = install._hook_home(text)
    home = os.environ["TL_RELAY_HOME"]
    if install._differs(named, home):
        raise Refused("the pre-push hook %s names home %s, not %s" % (hook, named, home))


def _check_heldout_identity(repo, rows, digest, fp, skills) -> None:
    current = {k: v[:2] for k, v in skills.items()}
    for commit in sorted({r["commit"] for r in rows if r.get("heldout") == digest and r["fingerprint"] != fp}):
        try:
            recorded = {k: v[:2] for k, v in fr_inputs.skills_at(repo, commit).items()}
        except (fr_git.GitError, fr_inputs.InputError):
            recorded = None
        if recorded != current:
            raise Refused("this held-out set was scored on another skill name or description, write a fresh one")


def _recorded(rows, fingerprint):
    verdict = fr_record.verdict_for(rows, fingerprint)
    if verdict is None:
        return None
    _write(sys.stdout, "%s %s (recorded)\n" % (verdict, fingerprint[:12]))
    return 0 if verdict == PASS else 1


def _export(repo, sha) -> pathlib.Path:
    out = pathlib.Path(tempfile.mkdtemp(prefix=EXPORT_PREFIX)).resolve()
    try:
        data = fr_git.run(repo, "archive", "--format=tar", sha).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(str(out))
    except BaseException:
        shutil.rmtree(str(out), ignore_errors=True)
        raise
    return out


def _ignore_signals() -> None:
    mask = None
    while True:
        try:
            if mask is None:
                mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
            signal.pthread_sigmask(signal.SIG_BLOCK, _SIGNALS)
            break
        except BaseException:
            continue
    for sig in _SIGNALS:
        signal.signal(sig, signal.SIG_IGN)
    signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def _agent_group(pgid_file):
    try:
        pgid = int(pathlib.Path(pgid_file).read_text())
    except (OSError, ValueError):
        return None
    return pgid if pgid > 1 else None


def _kill_group(pgid, sig) -> None:
    if pgid is None:
        return
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _stop_group(proc, pgid_file) -> None:
    _kill_group(proc.pid, signal.SIGTERM)
    _kill_group(_agent_group(pgid_file), signal.SIGTERM)
    try:
        proc.wait(timeout=_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid, signal.SIGKILL)
        proc.wait()
    _kill_group(_agent_group(pgid_file), signal.SIGKILL)


def _default_signals() -> None:
    for sig in _SIGNALS:
        signal.signal(sig, signal.SIG_DFL)


def _run_prompt(export, key, data, env) -> str:
    with tempfile.TemporaryDirectory(prefix="final-run-prompt.") as prompts:
        pathlib.Path(prompts, key.split("/", 1)[1]).write_bytes(data)
        pgid_file = os.path.join(prompts, "agent.pgid")
        env = dict(env, TL_RELAY_TRIGGER_PROMPTS=prompts, TL_RELAY_TRIGGER_PGID_FILE=pgid_file)
        proc = subprocess.Popen(
            ["/bin/bash", str(export / "skills" / "tests" / "run-triggers.sh")],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL if sys.stderr is None else None,
            start_new_session=True, preexec_fn=_default_signals,
        )
        try:
            out, _ = proc.communicate()
        except BaseException:
            _stop_group(proc, pgid_file)
            raise
    text = out.decode("utf-8", "replace")
    lines = [line for line in text.splitlines() if line.strip()]
    _write(sys.stderr, "".join("  %s\n" % line for line in lines if not _SUMMARY.fullmatch(line)))
    summary = _SUMMARY.fullmatch(lines[-1]) if lines else None
    if summary is None or summary.group(2) != "1":
        return ERROR
    if proc.returncode == 0 and summary.group(1) == "1":
        return PASS
    if proc.returncode == 1 and summary.group(1) == "0":
        return FAIL
    return ERROR


def _handle(signum, frame):
    for sig in _SIGNALS:
        signal.signal(sig, signal.SIG_IGN)
    raise Interrupted("interrupted by signal %d" % signum)


def _run_all(repo, sha, fp, digest, files, change, skills, export, env) -> int:
    committed = fr_inputs.prompts_at(repo, sha)
    prompts = {"committed/" + k: v for k, v in committed.items()}
    prompts.update({"heldout/" + k: v for k, v in files.items()})
    if not prompts:
        raise Refused("no trigger prompts at HEAD")
    tiers = {k: fr_tiers.tier_of(k, change, skills) for k in prompts}
    order = sorted(prompts, key=lambda k: (tiers[k] != "strict", k))
    done = fr_record.results_for(fr_record.load(repo), fp)
    for key in order:
        tier, results = tiers[key], list(done.get(key, []))
        while True:
            verdict = fr_tiers.judge(tier, results)
            if verdict != "more":
                break
            result = _run_prompt(export, key, prompts[key], env)
            if result == ERROR:
                _say("ERROR on %s, nothing recorded for it" % key)
                return 3
            fr_record.append_run(repo, fp, sha, digest, key, tier, result)
            results.append(result)
        if verdict == "fail":
            fr_record.append_verdict(repo, fp, sha, digest, FAIL)
            _write(sys.stdout, "FAIL %s at %s\n" % (fp[:12], key))
            return 1
    fr_record.append_verdict(repo, fp, sha, digest, PASS)
    _write(sys.stdout, "PASS %s\n" % fp[:12])
    return 0


def _score(repo, heldout) -> int:
    fr_lock.lock_path()
    _check_hook_home(repo)
    _require_clean(repo)
    sha = fr_inputs._resolve(repo, "HEAD")
    fp = fr_inputs.fingerprint(repo, sha)
    existing = _recorded(fr_record.load(repo), fp)
    if existing is not None:
        return existing
    change = fr_tiers.changes(repo, fr_git.merge_base(repo, sha), sha)
    if change.session_hook_changed:
        raise Refused("the branch changes hooks/session-start-skills.sh, which score cannot run")
    if change.identity_changed and heldout is None:
        raise Refused("a skill name or description changed, pass --heldout <dir>")
    digest, files = read_heldout(heldout, repo) if heldout is not None else (None, {})
    skills = fr_inputs.skills_at(repo, sha)
    _check_heldout(files, skills)
    with fr_lock.machine_lock():
        rows = fr_record.load(repo)
        existing = _recorded(rows, fp)
        if existing is not None:
            return existing
        if digest is not None and fr_record.heldout_failed(rows, digest, current=fp):
            raise Refused("this held-out set already failed, write a new one")
        if digest is not None:
            _check_heldout_identity(repo, rows, digest, fp, skills)
        if not fr_record.heldout_matches(rows, fp, digest):
            raise Refused("this fingerprint has runs recorded with a different held-out set")
        export = _export(repo, sha)
        try:
            env = dict(os.environ, TL_RELAY_BOOTSTRAP_SKILL=str(export / "skills" / "using-tl-relay" / "SKILL.md"),
                       TL_RELAY_TRIGGER_KEEP=str(fr_record.path(repo).parent / "final-run-streams"))
            result = _run_all(repo, sha, fp, digest, files, change, skills, export, env)
        finally:
            try:
                while True:
                    try:
                        _ignore_signals()
                        break
                    except Interrupted:
                        continue
            finally:
                shutil.rmtree(str(export), ignore_errors=True)
        return result


def _tune_skills(top, skill) -> dict:
    found = {}
    for path in sorted(list((top / "skills").glob("*/SKILL.md")) + list((top / "maintainer" / "skills").glob("*/SKILL.md"))):
        try:
            fields = fr_inputs.frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, fr_inputs.InputError) as exc:
            raise Refused("cannot read %s: %s" % (path, exc))
        if "name" not in fields or "description" not in fields:
            raise Refused("%s needs a name and a description" % path)
        found[path.parent.name] = fr_inputs.identity(fields)
    if skill not in found:
        raise Refused("no skill named %s in %s" % (skill, top / "skills"))
    return found


def _tune_prompts(top, skill, names) -> dict:
    prompts_root = top / "skills" / "tests" / "prompts"
    found = {}
    if prompts_root.is_dir():
        for path in sorted(prompts_root.iterdir()):
            if path.suffix == ".txt" and not path.name.startswith(".") and path.is_file():
                if fr_tiers.owner(path.name, names) == skill:
                    found[path.name] = path.read_bytes()
    if not found:
        raise Refused("no trigger prompt belongs to %s" % skill)
    return found


def _tune(repo, skill, runs) -> int:
    if os.environ.get("TL_RELAY_TRIGGER_PROMPTS"):
        raise Refused("tune refuses TL_RELAY_TRIGGER_PROMPTS, unset it")
    if runs < 1:
        raise Refused("--runs must be at least 1")
    fr_lock.lock_path()
    top = pathlib.Path(fr_git.toplevel(repo)).resolve()
    skills = _tune_skills(top, skill)
    prompts = _tune_prompts(top, skill, sorted(skills))
    env = dict(os.environ, TL_RELAY_BOOTSTRAP_SKILL=str(top / "skills" / "using-tl-relay" / "SKILL.md"),
               TL_RELAY_TRIGGER_KEEP=str(fr_record.path(top).parent / "final-run-streams"))
    failed = False
    for name, data in prompts.items():
        results = []
        for _ in range(runs):
            result = _run_prompt(top, "tune/" + name, data, env)
            if result == ERROR:
                _say("ERROR on %s" % name)
                return 3
            results.append(result)
        passes = results.count(PASS)
        failed = failed or passes < runs
        _write(sys.stdout, "%s %d/%d\n" % (name, passes, runs))
    return 1 if failed else 0


def _code_of(run) -> int:
    try:
        return run()
    except fr_lock.LockHeld as exc:
        _say(str(exc))
        return 4
    except Interrupted as exc:
        _say(str(exc))
        return 3
    except (Refused, fr_lock.LockError, fr_record.RecordError, fr_git.GitError, fr_inputs.InputError) as exc:
        _say(str(exc))
        return 2
    except Exception:
        _say_traceback()
        return 3


def _exit_code(repo, heldout) -> int:
    return _code_of(lambda: _score(repo, heldout))


def _guarded(run) -> int:
    old = {sig: signal.getsignal(sig) for sig in _SIGNALS}
    code = 3
    try:
        try:
            for sig, handler in old.items():
                if handler != signal.SIG_IGN:
                    signal.signal(sig, _handle)
            code = run()
        finally:
            _ignore_signals()
    except Interrupted as exc:
        _say(str(exc))
    except Exception:
        _say_traceback()
    _settle_streams()
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, _SIGNALS)
    for sig, handler in old.items():
        signal.signal(sig, handler)
    try:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
    except BaseException:
        pass
    return code


def score(repo, heldout) -> int:
    return _guarded(lambda: _exit_code(repo, heldout))


def tune(repo, skill: str, runs: int = 5) -> int:
    return _guarded(lambda: _code_of(lambda: _tune(repo, skill, runs)))
