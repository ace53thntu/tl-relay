#!/usr/bin/python3
from __future__ import annotations

import argparse
import sys

import fr_check
import fr_git
import fr_inputs
import fr_score


def main(argv) -> int:
    parser = argparse.ArgumentParser(prog="final_run.py")
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    fp = sub.add_parser("fingerprint")
    fp.add_argument("commit")
    sc = sub.add_parser("score")
    sc.add_argument("--heldout")
    tn = sub.add_parser("tune")
    tn.add_argument("skill")
    tn.add_argument("--runs", type=int, default=5)
    ck = sub.add_parser("check")
    ck.add_argument("remote", nargs="?")
    ck.add_argument("url", nargs="?")
    args = parser.parse_args(argv)
    if args.command == "score":
        return fr_score.score(args.repo, args.heldout)
    if args.command == "tune":
        return fr_score.tune(args.repo, args.skill, args.runs)
    if args.command == "check":
        return fr_check.check(args.repo, sys.stdin)
    try:
        if args.command == "fingerprint":
            print(fr_inputs.fingerprint(args.repo, args.commit))
    except (fr_git.GitError, fr_inputs.InputError) as exc:
        sys.stderr.write("final_run: %s\n" % exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
