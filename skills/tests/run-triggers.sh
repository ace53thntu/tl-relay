#!/bin/bash
set -u
set -m

here=$(dirname "${BASH_SOURCE[0]}")
skills=$(CDPATH= cd -- "$here/.." && pwd -P)
root=$(dirname "$skills")
agent=${TL_RELAY_TRIGGER_AGENT:-claude}
prompts=${TL_RELAY_TRIGGER_PROMPTS:-$here/prompts}
limit=${TL_RELAY_TRIGGER_TIMEOUT:-120}

tmp=
agent_pid=
dog_pid=
watch_pid=

stop_agent() {
  [ -n "$dog_pid" ] && kill -TERM -- "-$dog_pid" 2>/dev/null
  [ -n "$watch_pid" ] && kill -TERM "$watch_pid" 2>/dev/null
  [ -n "$agent_pid" ] || return 0
  kill -TERM -- "-$agent_pid" 2>/dev/null
  local i
  for i in $(seq 50); do
    kill -0 -- "-$agent_pid" 2>/dev/null || break
    sleep 0.1 & wait "$!"
  done
  kill -KILL -- "-$agent_pid" 2>/dev/null
  wait 2>/dev/null
  [ -z "${TL_RELAY_TRIGGER_PGID_FILE:-}" ] || : >"$TL_RELAY_TRIGGER_PGID_FILE"
  agent_pid=
  dog_pid=
  watch_pid=
}

cleanup() { [ -n "$tmp" ] && rm -rf "$tmp"; tmp=; }

abort() {
  stop_agent
  cleanup
  exit "$1"
}

trap 'abort 130' INT
trap 'abort 143' TERM
trap 'abort 129' HUP
trap 'abort 141' PIPE
trap cleanup EXIT

build_workspace() {
  mkdir -p "$tmp/ws/.claude/skills" || return 1
  cp -R "$here/fixtures/trigger-workspace/." "$tmp/ws/" || return 1
  [ -f "$root/hooks/session-start-skills.sh" ] || return 1
  local f linked=0
  for f in "$skills"/*/SKILL.md "$root"/maintainer/skills/*/SKILL.md; do
    [ -e "$f" ] || continue
    linked=$((linked + 1))
    ln -s "$(dirname "$f")" "$tmp/ws/.claude/skills/$(basename "$(dirname "$f")")" || return 1
  done
  [ "$linked" -gt 0 ] || return 1
  python3 -c 'import json, shlex, sys
hook = "/bin/sh " + shlex.quote(sys.argv[2] + "/hooks/session-start-skills.sh")
json.dump({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": hook}]}]}}, open(sys.argv[1], "w"))' \
    "$tmp/ws/.claude/settings.json" "$root"
}

passed=0
failed=0
errored=0
total=0
for file in "$prompts"/*.txt; do
  [ -e "$file" ] || continue
  name=$(basename "$file" .txt)
  expect=$(head -n 1 "$file" | sed 's/^expect:[[:space:]]*//')
  prompt=$(tail -n +2 "$file")
  total=$((total + 1))

  tmp=$(mktemp -d "${TMPDIR:-/tmp}/trigger.XXXXXX")
  mkfifo "$tmp/stream"
  if ! build_workspace; then
    printf 'ERROR %s: could not build the trigger workspace\n' "$name"
    errored=$((errored + 1))
    cleanup
    continue
  fi
  (
    cd "$tmp/ws" || exit 1
    exec "$agent" -p "$prompt" --output-format stream-json --verbose \
      --max-budget-usd 1 --strict-mcp-config --disallowedTools Bash Edit Write NotebookEdit \
      --setting-sources project --model opus
  ) >"$tmp/stream" 2>>"$tmp/err" &
  agent_pid=$!
  (sleep "$limit"; touch "$tmp/timeout"; kill -TERM -- "-$agent_pid" 2>/dev/null; sleep 5; kill -KILL -- "-$agent_pid" 2>/dev/null) &
  dog_pid=$!

  TL_RELAY_TRIGGER_SEEN="$tmp/seen.jsonl" python3 "$here/triggers.py" watch "$expect" "$tmp/timeout" <"$tmp/stream" >"$tmp/verdict" 2>>"$tmp/err" &
  watch_pid=$!
  [ -z "${TL_RELAY_TRIGGER_PGID_FILE:-}" ] || printf '%s\n' "$agent_pid" >"$TL_RELAY_TRIGGER_PGID_FILE"
  wait "$watch_pid"
  status=$?
  watch_pid=
  stop_agent

  if [ "$status" -eq 0 ]; then
    line="PASS $name"
    passed=$((passed + 1))
  else
    if grep -q '^FAIL: ' "$tmp/verdict" 2>/dev/null; then
      kind=FAIL
      failed=$((failed + 1))
    else
      kind=ERROR
      errored=$((errored + 1))
    fi
    reason=$(sed 's/^[A-Z]*: //' "$tmp/verdict")
    [ -n "$reason" ] || reason="no verdict from the trigger watcher (exit $status)"
    [ "$kind" = ERROR ] && [ -e "$tmp/timeout" ] && reason="timeout after ${limit}s, $reason"
    line="$kind $name: $reason"
    if [ -s "$tmp/err" ]; then
      line="$line"$'\n'"$(tail -n 3 "$tmp/err" | sed 's/^/  stderr: /')"
    fi
    if [ "$kind" = FAIL ] && [ -n "${TL_RELAY_TRIGGER_KEEP:-}" ]; then
      keep_err=$(mkdir -p "$TL_RELAY_TRIGGER_KEEP" 2>&1 \
        && cp "$tmp/seen.jsonl" "$TL_RELAY_TRIGGER_KEEP/$name.$(date +%s).$$.jsonl" 2>&1) \
        || line="$line"$'\n'"  keep: $keep_err"
    fi
  fi
  cleanup
  echo "$line"
done

echo "$passed/$total"
[ "$total" -gt 0 ] || exit 1
[ "$failed" -eq 0 ] || exit 1
[ "$errored" -eq 0 ] || exit 3
exit 0
