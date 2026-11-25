#!/usr/bin/env python3
"""Installs the hooks and skills, and checks the repo for neutrality. Exit 0 done, 1 refused or found, 2 error, 130 interrupted."""
import argparse
import io
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from runtime import config, install, neutral  # noqa: E402


def home():
    return config.default_home()


def cmd_install(args):
    if args.home == "":
        raise install.InstallError("--home needs a path")
    try:
        repo, target_home = config.default_repo(), args.home or home()
        changes = install.plan(repo, target_home, home_given=args.home is not None)
        notice = None
        if args.git_hook:
            change = install.git_hook_change(repo, target_home)
            if change is None:
                notice = "no git directory in %s; pre-push hook skipped" % repo
            else:
                changes.append(change)
        else:
            notice = install.hook_notice(repo, target_home)
        if sys.stdout is None:
            raise install.InstallError("output closed before install wrote anything; nothing changed")
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            for path, old, new in changes:
                if old != new:
                    text = install.diff(path, old, new)
                    sys.stdout.write(text.encode(encoding, "backslashreplace").decode(encoding))
            sys.stdout.flush()
        except BrokenPipeError:
            try:
                devnull = os.open(os.devnull, os.O_WRONLY)
                try:
                    os.dup2(devnull, sys.stdout.fileno())
                finally:
                    os.close(devnull)
            except (AttributeError, OSError, io.UnsupportedOperation):
                pass
            raise install.InstallError("output closed before install wrote anything; nothing changed")
    except KeyboardInterrupt:
        raise install.InstallInterrupted("nothing changed")
    if not args.dry_run:
        install.apply(changes)
    if notice:
        print(notice, file=sys.stderr)
    return 0


def cmd_check_neutral(args):
    cfg = config._read(config.home_file(home()))
    section = cfg.get("neutrality")
    if section is not None and not isinstance(section, dict):
        raise neutral.NeutralError("neutrality must be a mapping")
    patterns = (section or {}).get("patterns")
    if patterns is None:
        patterns = []
    if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
        raise neutral.NeutralError("neutrality.patterns must be a list of strings")
    if any(not p.strip() for p in patterns):
        raise neutral.NeutralError("neutrality.patterns must not hold an empty pattern")
    allow = (section or {}).get("identity_allow", [])
    if not isinstance(allow, list) or not all(isinstance(a, str) and a.strip() for a in allow):
        raise neutral.NeutralError("neutrality.identity_allow must be a list of non-empty email addresses")
    if not patterns:
        print("neutrality.patterns is empty in %s" % config.home_file(home()), file=sys.stderr)
        return 2
    if args.tag_object is not None:
        found = neutral.tag_hits(args.repo, patterns, args.tag_object, allow)
    elif args.range is not None:
        found = neutral.range_hits(args.repo, patterns, args.range, allow)
    else:
        found = neutral.hits(args.repo, patterns)
    for line in found:
        print(line)
    return 1 if found else 0


def parser():
    top = argparse.ArgumentParser(prog="sdlc.py")
    sub = top.add_subparsers(dest="action", required=True)
    install_cmd = sub.add_parser("install")
    install_cmd.add_argument("--dry-run", action="store_true")
    install_cmd.add_argument("--home")
    install_cmd.add_argument("--git-hook", action="store_true")
    neutral_cmd = sub.add_parser("check-neutral")
    neutral_cmd.add_argument("--repo", default=str(config.default_repo()))
    neutral_scope = neutral_cmd.add_mutually_exclusive_group()
    neutral_scope.add_argument("--range")
    neutral_scope.add_argument("--tag-object")
    return top


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = parser().parse_args(argv)
    if args.action == "install":
        try:
            return cmd_install(args)
        except install.InstallInterrupted as exc:
            print("interrupted: %s" % exc, file=sys.stderr)
            return 130
        except (install.InstallError, config.ConfigError) as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 1
    try:
        return cmd_check_neutral(args)
    except (neutral.NeutralError, config.ConfigError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
