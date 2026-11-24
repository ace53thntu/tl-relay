#!/bin/bash
here=$(dirname "$0")
marker=${AI_SDLC_STUB_MARKER:-unset}
sleepers='(exec -a "$0" sleep 300) & exec -a "$0" sleep 300'
case "${AI_SDLC_STUB_MODE:-}" in
  linger)
    cat "$here/read-then-skill.jsonl"
    exec bash -c "$sleepers" "$marker"
    ;;
  ignore-term)
    trap '' TERM
    cat "$here/read-then-skill.jsonl"
    bash -c "$sleepers" "$marker"
    exit
    ;;
  clean-linger)
    cat "$here/no-skill.jsonl"
    exec bash -c "$sleepers" "$marker"
    ;;
  clean-on-term)
    trap 'echo "{\"type\":\"result\",\"is_error\":false}"; exit 0' TERM
    (exec -a "$marker" sleep 300) &
    wait
    ;;
  silent)
    exec bash -c "$sleepers" "$marker"
    ;;
  silent-ignore-term)
    trap '' TERM
    bash -c "$sleepers" "$marker"
    exit
    ;;
  orphan-holds-pipe)
    trap '' TERM
    bash -c '(exec -a "$0" sleep 300) &' "$marker"
    exit 0
    ;;
esac
case "$2" in
  *stub:wrong*) cat "$here/wrong-skill.jsonl" ;;
  *stub:clean*) cat "$here/no-skill.jsonl" ;;
  *stub:error*) cat "$here/error-result.jsonl" ;;
  *stub:no-result*) cat "$here/no-result.jsonl" ;;
  *stub:stderr*) cat "$here/no-result.jsonl"; sleep 1; echo agent-stderr-line >&2 ;;
  *stub:dump*)
    python3 - "$@" <<'PY'
import json, os, subprocess, sys
found = subprocess.run(["find", ".", "-mindepth", "1"], capture_output=True, text=True).stdout.split("\n")
files = sorted(f[2:] for f in found if f)
links = {n: os.path.realpath(".claude/skills/" + n) for n in os.listdir(".claude/skills")}
settings = json.load(open(".claude/settings.json"))
dump = {"cwd": os.path.realpath("."), "args": sys.argv[1:], "files": files, "settings": settings, "links": links}
json.dump(dump, open(os.environ["AI_SDLC_STUB_DUMP"], "w"))
PY
    cat "$here/read-then-skill.jsonl" ;;
  *stub:bad-utf8*) printf '\377\376\n' ;;
  *) cat "$here/read-then-skill.jsonl" ;;
esac
