"""Registers the hooks: renders the fragment templates and merges them into the Claude Code settings files."""
import difflib
import errno
import json
import os
import pathlib
import re
import shlex
import signal
import stat
import subprocess
import threading

from runtime import config

FRAGMENTS = ("settings-fragment.json", "user-fragment.json")
SCRIPT = re.compile(r"'([^']+)'$")
RETIRED = ("block-test-edit.sh", "warn-out-of-scope.sh", "validate-evidence.sh")
HOOK_MARKER = "# ai-sdlc pre-push hook"
HOOK_TEMPLATE = "git-pre-push"


class InstallError(Exception):
    pass


class InstallInterrupted(InstallError):
    pass


def _require_utf8(path, label):
    try:
        str(path).encode("utf-8")
    except UnicodeEncodeError:
        raise InstallError("%s: %s is not valid UTF-8" % (label, json.dumps(str(path))))


def _expand(value, label, resolve=True):
    try:
        path = pathlib.Path(value).expanduser()
        if "\0" in str(path):
            raise ValueError("embedded null byte")
        _require_utf8(path, label)
        if resolve:
            path = path.resolve()
            _require_utf8(path, label)
        return path
    except (RuntimeError, TypeError, ValueError) as exc:
        raise InstallError("%s: %s is not a usable path (%s)" % (label, json.dumps(value, default=str), exc))


def _escape(value):
    return json.dumps(str(value).replace("'", "'\\''"), ensure_ascii=False)[1:-1]


def render(text, repo, home):
    values = {"home": _escape(home), "repo": _escape(repo)}
    return re.sub(r"\{(home|repo)\}", lambda m: values[m.group(1)], text)


def _script(command):
    found = SCRIPT.search(command or "")
    return os.path.basename(found.group(1)) if found else None


def _retired(command):
    found = SCRIPT.search(command or "")
    return bool(found) and any(found.group(1).endswith("/hooks/" + name) for name in RETIRED)


def merge_settings(live, fragment):
    merged = json.loads(json.dumps(live))
    events = merged.setdefault("hooks", {})
    for event, groups in list(events.items()):
        dropped = False
        kept_groups = []
        for group in groups:
            hooks = group.get("hooks", [])
            live_hooks = [h for h in hooks if not _retired(h.get("command"))]
            if len(live_hooks) == len(hooks):
                kept_groups.append(group)
                continue
            dropped = True
            if live_hooks:
                group["hooks"] = live_hooks
                kept_groups.append(group)
        if dropped:
            if kept_groups:
                events[event] = kept_groups
            else:
                del events[event]
    for event, groups in (fragment.get("hooks") or {}).items():
        live_groups = events.setdefault(event, [])
        for group in groups:
            matcher = group.get("matcher", "*")
            for hook in group.get("hooks", []):
                name = _script(hook.get("command"))
                kept = False
                for live_group in live_groups:
                    if live_group.get("matcher", "*") != matcher:
                        continue
                    stale = []
                    for old in live_group.get("hooks", []):
                        if old.get("command") == hook.get("command") and not kept:
                            kept = True
                            stale.append(old)
                        elif name and _script(old.get("command")) == name and (SCRIPT.search(old["command"]).group(1)).endswith("/hooks/" + name):
                            continue
                        else:
                            stale.append(old)
                    live_group["hooks"] = stale
                live_groups[:] = [g for g in live_groups if g.get("hooks")]
                if not kept:
                    live_groups.append({"matcher": matcher, "hooks": [hook]})
    return merged


def _block(cfg, name):
    value = cfg.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InstallError("%s must be a mapping in the home ai-sdlc.yaml" % name)
    return value


def _root(cfg):
    root = _block(cfg, "project").get("root")
    if not root:
        raise InstallError("set project.root in the home ai-sdlc.yaml")
    path = _expand(root, "project.root")
    if re.search(r"[\r\n]", str(path)):
        raise InstallError("project.root: %s must not contain a newline" % json.dumps(str(path)))
    return path


def _config_dirs(cfg):
    dirs = _block(cfg, "install").get("claude_config_dirs")
    if dirs is None:
        dirs = []
    if not isinstance(dirs, list) or not all(isinstance(d, str) for d in dirs):
        raise InstallError("install.claude_config_dirs must be a list of paths")
    out = []
    for d in dirs or ["~/.claude"]:
        path = _expand(d, "install.claude_config_dirs", resolve=False)
        if not d or not path.is_absolute():
            raise InstallError("install.claude_config_dirs: %s must be an absolute path" % json.dumps(d))
        if ":" in str(path) or re.search(r"[\r\n]", str(path)):
            raise InstallError('install.claude_config_dirs: %s must not contain ":" or a newline' % json.dumps(d))
        out.append(path)
    return out


def _quote(value):
    return "'%s'" % str(value).replace("'", "'\\''")


def env_text(cfg, repo, home):
    root = _root(cfg)
    home = pathlib.Path(home)
    values = (
        ("AI_SDLC_ROOT", root),
        ("AI_SDLC_USER_FRAGMENT", home / "hooks" / "user-fragment.json"),
        ("AI_SDLC_FRAGMENT", home / "hooks" / "settings-fragment.json"),
        ("AI_SDLC_USER_SETTINGS", ":".join(str(d / "settings.json") for d in _config_dirs(cfg))),
        ("AI_SDLC_SETTINGS", root / ".claude" / "settings.json"),
    )
    return "".join("export %s=%s\n" % (name, _quote(value)) for name, value in values)


def _is_file(path):
    try:
        return path.is_file()
    except OSError as exc:
        raise InstallError("%s: %s" % (path, exc))


def _read(path):
    info = _stat(path)
    if info is None:
        return ""
    if not stat.S_ISREG(info.st_mode):
        raise InstallError("%s: not a regular file" % path)
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise InstallError("%s: %s" % (path, exc))


def _dump(doc):
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def with_home_env(live, path, home, home_given=False):
    env = live.get("env")
    if env is None:
        env = {}
    if not isinstance(env, dict):
        raise InstallError("%s: expected an object under env" % path)
    if "AI_SDLC_HOME" in env and not home_given:
        value = env["AI_SDLC_HOME"]
        if not isinstance(value, str) or not value:
            raise InstallError("%s: env.AI_SDLC_HOME is %s; pass --home to replace it" % (path, json.dumps(value)))
        try:
            differs = pathlib.Path(value).expanduser().resolve() != home
        except (RuntimeError, ValueError):
            raise InstallError("%s: env.AI_SDLC_HOME is %s, not a usable path; pass --home to replace it" % (path, json.dumps(value)))
        if differs:
            raise InstallError("%s: env.AI_SDLC_HOME is %s; pass --home to replace it" % (path, value))
    return dict(live, env=dict(env, AI_SDLC_HOME=str(home)))


def _names_other_home(value, home):
    if not isinstance(value, str) or not value:
        return True
    try:
        return pathlib.Path(value).expanduser().resolve() != home
    except (RuntimeError, ValueError):
        return True


def without_stale_home(live, path, home, home_given):
    env = live.get("env")
    if env is None:
        return live
    if not isinstance(env, dict):
        raise InstallError("%s: expected an object under env" % path)
    if "AI_SDLC_HOME" not in env or not _names_other_home(env["AI_SDLC_HOME"], home):
        return live
    if not home_given:
        raise InstallError("%s: env.AI_SDLC_HOME is %s; pass --home to remove it" % (path, json.dumps(env["AI_SDLC_HOME"])))
    kept = {k: v for k, v in env.items() if k != "AI_SDLC_HOME"}
    out = {k: v for k, v in live.items() if k != "env"}
    if kept:
        out["env"] = kept
    return out


def check_local_home(path, home):
    text = _read(path)
    if not text.strip():
        return
    try:
        live = json.loads(text)
    except ValueError as exc:
        raise InstallError("%s: %s" % (path, exc))
    if not isinstance(live, dict):
        raise InstallError("%s: expected a JSON object" % path)
    env = live.get("env")
    if env is None:
        return
    if not isinstance(env, dict):
        raise InstallError("%s: expected an object under env" % path)
    if "AI_SDLC_HOME" in env and _names_other_home(env["AI_SDLC_HOME"], home):
        raise InstallError("%s: env.AI_SDLC_HOME is %s; delete the key, install does not edit this file" % (path, json.dumps(env["AI_SDLC_HOME"])))


def _merged(path, fragment, home=None, home_given=False, project=False):
    old = _read(path)
    try:
        live = json.loads(old) if old.strip() else {}
    except ValueError as exc:
        raise InstallError("%s: %s" % (path, exc))
    if not isinstance(live, dict) or not isinstance(live.get("hooks", {}), dict):
        raise InstallError("%s: expected an object with an object under hooks" % path)
    for event, groups in live.get("hooks", {}).items():
        ok = isinstance(groups, list) and all(
            isinstance(g, dict) and isinstance(g.get("hooks", []), list) and all(isinstance(h, dict) for h in g.get("hooks", []))
            for g in groups)
        if not ok:
            raise InstallError("%s: expected a list of hook groups under hooks.%s" % (path, event))
    merged = merge_settings(live, fragment)
    if home is not None:
        merged = (without_stale_home if project else with_home_env)(merged, path, home, home_given)
    return old, _dump(merged)


def _template(path):
    if not _is_file(path):
        raise InstallError("missing hook template %s" % path)
    return _read(path)


def _stat(path):
    try:
        return os.stat(path)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return None
        raise InstallError("%s: %s" % (path, exc))


def _same_settings(a, b):
    stats = [_stat(a), _stat(b)]
    resolved = []
    for path in (a, b):
        try:
            resolved.append(path.resolve())
        except (RuntimeError, OSError) as exc:
            raise InstallError("%s: %s" % (path, exc))
    if resolved[0] == resolved[1]:
        return True
    if stats[0] and stats[1] and os.path.samestat(*stats):
        return True
    parents = [_stat(a.parent), _stat(b.parent)]
    return bool(parents[0] and parents[1] and os.path.samestat(*parents))


def plan(repo, home, home_given=False):
    repo, home = _expand(repo, "repo"), _expand(home, "home")
    for label, value in (("repo", repo), ("home", home)):
        if re.search(r"[\r\n]", str(value)):
            raise InstallError("%s: %s must not contain a newline" % (label, json.dumps(str(value))))
    if "'" in str(repo):
        raise InstallError("repo: %s contains a single quote; the guardrail check cannot read a hook path with one" % json.dumps(str(repo)))
    if not _is_file(home / "ai-sdlc.yaml"):
        raise InstallError("copy ai-sdlc.example.yaml to %s and set project.root" % (home / "ai-sdlc.yaml"))
    if repo == home:
        raise InstallError("the home and the repo are both %s; installing would overwrite the fragment templates" % home)
    cfg = config.load(repo, home)
    root = _root(cfg)
    check_local_home(root / ".claude" / "settings.local.json", home)
    rendered = {name: render(_template(repo / "maintainer" / "hooks" / name), repo, home) for name in FRAGMENTS}
    out = [(home / "hooks" / name, _read(home / "hooks" / name), text) for name, text in rendered.items()]
    out.append((home / "env.sh", _read(home / "env.sh"), env_text(cfg, repo, home)))
    fragments = {}
    for name, text in rendered.items():
        try:
            fragments[name] = json.loads(text)
        except ValueError as exc:
            raise InstallError("%s: %s" % (repo / "maintainer" / "hooks" / name, exc))
    user = fragments["user-fragment.json"]
    project = root / ".claude" / "settings.json"
    shared = False
    for d in _config_dirs(cfg):
        fragment = user
        if _same_settings(d / "settings.json", project):
            fragment = merge_settings(user, fragments["settings-fragment.json"])
            shared = True
        out.append((d / "settings.json",) + _merged(d / "settings.json", fragment, home, home_given))
    if not shared:
        out.append((project,) + _merged(project, fragments["settings-fragment.json"], home, home_given, project=True))
    for path, _, new in out:
        try:
            new.encode("utf-8")
        except UnicodeError as exc:
            raise InstallError("%s: %s" % (path, exc))
    return out


def _git(repo, *args):
    env = dict(os.environ)
    try:
        names = subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True, env=env).stdout.split()
        for name in names:
            env.pop(name, None)
        env["LC_ALL"] = "C"
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)
    except OSError as exc:
        raise InstallError("cannot run git: %s" % exc)
    except UnicodeError as exc:
        raise InstallError("git %s printed output that is not UTF-8: %s" % (" ".join(args), exc))


class HooksPathSet(InstallError):
    pass


def _git_ok(repo, *args):
    done = _git(repo, *args)
    if done.returncode != 0:
        raise InstallError("git %s failed: %s" % (" ".join(args), done.stderr.strip()))
    return done.stdout.rstrip("\n")


def _hook_target(repo):
    top = _git(repo, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        if "not a git repository" in top.stderr:
            return None
        raise InstallError("git rev-parse --show-toplevel failed: %s" % top.stderr.strip())
    try:
        if not os.path.samefile(top.stdout.rstrip("\n"), repo):
            return None
    except OSError as exc:
        raise InstallError("%s: %s" % (repo, exc))
    common = (repo / _git_ok(repo, "rev-parse", "--git-common-dir")).resolve()
    configured = _git(repo, "config", "--get", "core.hooksPath")
    if configured.returncode not in (0, 1):
        raise InstallError("git config core.hooksPath failed: %s" % configured.stderr.strip())
    if configured.returncode == 0:
        raise HooksPathSet("core.hooksPath is set to %s; git does not run %s there" % (configured.stdout.rstrip("\n"), common / "hooks" / "pre-push"))
    return common / "hooks" / "pre-push", common.parent


def _hook_text(path):
    try:
        regular = stat.S_ISREG(os.lstat(path).st_mode)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return None
        raise InstallError("%s: %s" % (path, exc))
    if not regular:
        raise InstallError("%s: a pre-push hook that is not a regular file is already there; move it aside first" % path)
    text = _read(path)
    if HOOK_MARKER not in text:
        raise InstallError("%s: a pre-push hook not written by ai-sdlc is already there; move it aside first" % path)
    return text


def _require_main(main):
    for needed in ("maintainer/skills/write-skill/scripts/final_run.py", "maintainer/sdlc.py"):
        if not _is_file(main / needed):
            raise InstallError("%s: the main checkout lacks %s; check out a branch that has it there, then rerun install --git-hook" % (main, needed))


def git_hook_change(repo, home):
    repo, home = _expand(repo, "repo"), _expand(home, "home")
    target = _hook_target(repo)
    if target is None:
        return None
    path, main = target
    old = _hook_text(path) or ""
    _require_main(main)
    values = {"home": shlex.quote(str(home)), "main": shlex.quote(str(main))}
    new = re.sub(r"\{(home|main)\}", lambda m: values[m.group(1)], _template(repo / "maintainer" / "hooks" / HOOK_TEMPLATE))
    return path, old, new


def _differs(named, expected):
    if not isinstance(named, str) or not named:
        return True
    try:
        return not os.path.samefile(named, expected)
    except OSError:
        return _names_other_home(named, expected)


def _hook_value(text, key):
    for line in text.splitlines():
        if line.startswith(key):
            try:
                tokens = shlex.split(line)
            except ValueError:
                return None
            return tokens[0][len(key):] if tokens else None
    return None


def _hook_home(text):
    return _hook_value(text, "AI_SDLC_HOME=")


def hook_notice(repo, home):
    repo, home = _expand(repo, "repo"), _expand(home, "home")
    try:
        target = _hook_target(repo)
        if target is None:
            return None
        path = target[0]
        _require_main(target[1])
        text = _hook_text(path)
    except HooksPathSet as exc:
        return "pre-push hook: %s" % exc
    except InstallError as exc:
        return "pre-push hook: %s" % " ".join(str(exc).split())
    if text is None:
        return "pre-push hook not installed in %s; run install --git-hook to add it" % path.parent
    if not os.access(str(path), os.X_OK):
        return "pre-push hook %s is not executable; run install --git-hook to restore it" % path
    named_main = _hook_value(text, "main=")
    if _differs(named_main, target[1]):
        return "pre-push hook %s names checkout %s, not %s; run install --git-hook to update it" % (path, named_main, target[1])
    named = _hook_home(text)
    if _differs(named, home):
        return "pre-push hook %s names home %s, not %s; run install --git-hook to update it" % (path, named, home)
    return None


def _undo(written, made):
    failed = []
    for path, saved in reversed(written):
        try:
            if saved is not None:
                try:
                    if path.read_bytes() == saved:
                        continue
                except OSError:
                    pass
                with path.open("wb") as handle:
                    handle.write(saved)
            else:
                real = pathlib.Path(os.path.realpath(path))
                if real.exists():
                    real.unlink()
        except OSError:
            failed.append(path)
    for directory in reversed(made):
        try:
            directory.rmdir()
        except OSError:
            failed.append(directory)
    return failed


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt


def _undo_uninterrupted(written, made, main_thread):
    old_int = None
    if main_thread:
        old_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        return _undo(written, made)
    finally:
        if main_thread and old_int is not None:
            signal.signal(signal.SIGINT, old_int)


def apply(changes):
    main_thread = threading.current_thread() is threading.main_thread()
    previous = signal.getsignal(signal.SIGTERM) if main_thread else None
    if main_thread:
        signal.signal(signal.SIGTERM, _raise_interrupt)
    try:
        _apply(changes, main_thread)
    finally:
        if main_thread and previous is not None:
            signal.signal(signal.SIGTERM, previous)


def _apply(changes, main_thread):
    written, made = [], []
    path = None
    try:
        for path, old, new in changes:
            if old == new:
                if path.name == "pre-push" and path.exists():
                    path.chmod(0o755)
                continue
            data = new.encode("utf-8")
            saved = path.read_bytes() if path.exists() else None
            written.append((path, saved))
            missing = []
            parent = path.parent
            while not os.path.lexists(parent):
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                made.append(directory)
            path.write_bytes(data)
            if path.name == "pre-push":
                path.chmod(0o755)
    except (OSError, UnicodeError) as exc:
        message = "%s: %s" % (path, exc)
        failed = _undo_uninterrupted(written, made, main_thread)
        if failed:
            message += "; not restored: " + ", ".join(str(f) for f in failed)
        raise InstallError(message)
    except KeyboardInterrupt:
        failed = _undo_uninterrupted(written, made, main_thread)
        raise InstallInterrupted("not restored: " + ", ".join(str(f) for f in failed) if failed else "every file restored")


def diff(path, old, new):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "%s (current)" % path, "%s (new)" % path))
