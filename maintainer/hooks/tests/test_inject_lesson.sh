#!/bin/sh
. "$(dirname "$0")/lib.sh"
H="$(cd "$(dirname "$0")/../../../hooks" && pwd)/inject-lesson.sh"

TMP=$(mktemp -d)
trap 'chmod 644 "$TMP/lessons/write-plan.md" 2>/dev/null; rm -rf "$TMP"' EXIT
mkdir -p "$TMP/lessons"
printf '%s\n' '- L-1 · rule one' > "$TMP/lessons/write-plan.md"
: > "$TMP/lessons/empty.md"

run() { env "$@" /bin/sh "$H" 2>/dev/null; }
send() { printf '%s' "$1" | run TL_RELAY_LESSONS="$TMP/lessons"; }
ctx() { printf '%s' "$1" | /usr/bin/jq -r '.hookSpecificOutput.additionalContext' 2>/dev/null; }
tool() { printf '{"hook_event_name":"PreToolUse","tool_name":"Skill","tool_input":{"skill":"%s"}}' "$1"; }
prompt() { printf '{"hook_event_name":"UserPromptSubmit","prompt":"%s"}' "$1"; }

has() { case "$(ctx "$1")" in *"$2"*) return 0 ;; esac; return 1; }

silent() {
  o=$(printf '%s' "$2" | run TL_RELAY_LESSONS="$TMP/lessons"); rc=$?
  [ -z "$o" ] && [ $rc -eq 0 ] && ok "$1" || bad "$1: rc=$rc out='$o'"
}

o=$(send "$(tool write-plan)"); rc=$?
e=$(printf '%s' "$o" | /usr/bin/jq -r .hookSpecificOutput.hookEventName 2>/dev/null)
c=$(ctx "$o")
want="Lessons for write-plan from $TMP/lessons/write-plan.md. A lesson replaces a default of that skill. An instruction from the operator in this session overrides a lesson."
l1=$(printf '%s\n' "$c" | /usr/bin/sed -n 1p)
l2=$(printf '%s\n' "$c" | /usr/bin/sed -n 2p)
l3=$(printf '%s\n' "$c" | /usr/bin/sed -n 3p)
[ $rc -eq 0 ] && [ "$e" = "PreToolUse" ] && [ "$l1" = "$want" ] && [ -z "$l2" ] && [ "$l3" = '- L-1 · rule one' ] && has "$o" '- L-1 · rule one' \
  && ok "tool call injects lesson" || bad "tool call: rc=$rc event='$e' ctx='$c'"

o=$(send "$(prompt '/write-plan spec.md')"); rc=$?
e=$(printf '%s' "$o" | /usr/bin/jq -r .hookSpecificOutput.hookEventName 2>/dev/null)
[ $rc -eq 0 ] && [ "$e" = "UserPromptSubmit" ] && has "$o" '- L-1 · rule one' \
  && ok "slash prompt injects lesson" || bad "slash prompt: rc=$rc event='$e'"

o=$(send "$(prompt '/write-plan')"); rc=$?
[ $rc -eq 0 ] && has "$o" '- L-1 · rule one' && ok "bare slash command resolves" || bad "bare slash: rc=$rc"

o=$(send "$(prompt '/write-plan\nfoo')"); rc=$?
[ $rc -eq 0 ] && has "$o" '- L-1 · rule one' && ok "name followed by newline resolves" || bad "newline prompt: rc=$rc"

o=$(send "$(tool tl-relay:write-plan)"); rc=$?
[ $rc -eq 0 ] && [ "$(ctx "$o" | /usr/bin/sed -n 1p)" = "$want" ] && ok "plugin-prefixed tool call injects lesson" || bad "plugin tool call: rc=$rc"

o=$(send "$(prompt '/tl-relay:write-plan spec.md')"); rc=$?
[ $rc -eq 0 ] && has "$o" '- L-1 · rule one' && ok "plugin-prefixed slash prompt injects lesson" || bad "plugin slash: rc=$rc"

silent "plain prompt gives no output" "$(prompt 'please run write-plan')"
silent "path-like prompt gives no output" "$(prompt '/Volumes/x/y.md please read')"
silent "missing lesson gives no output" "$(tool brainstorm)"
silent "empty lesson gives no output" "$(tool empty)"

chmod 000 "$TMP/lessons/write-plan.md"
silent "unreadable lesson gives no output" "$(tool write-plan)"
chmod 644 "$TMP/lessons/write-plan.md"

silent "leading space gives no output" "$(prompt ' /write-plan')"
silent "missing prompt gives no output" '{"hook_event_name":"UserPromptSubmit"}'
silent "null prompt gives no output" '{"hook_event_name":"UserPromptSubmit","prompt":null}'

for s in 'x:y' 'other:write-plan' 'tl-relay:' '../write-plan' 'Write-Plan' '-x' '' 'write-plan\nx' 'write-plan\n'; do
  silent "rejected name '$s' gives no output" "$(tool "$s")"
done

o=$(printf '%s' "$(tool write-plan)" | run -u TL_RELAY_LESSONS); rc=$?
[ -z "$o" ] && [ $rc -eq 0 ] && ok "unset TL_RELAY_LESSONS gives no output" || bad "unset var: rc=$rc out='$o'"

o=$(printf '%s' "$(tool write-plan)" | run TL_RELAY_LESSONS=); rc=$?
[ -z "$o" ] && [ $rc -eq 0 ] && ok "empty TL_RELAY_LESSONS gives no output" || bad "empty var: rc=$rc out='$o'"

o=$(printf '%s' "$(tool write-plan)" | run TL_RELAY_LESSONS="$TMP/lessons" PATH=/nonexistent); rc=$?
[ $rc -eq 0 ] && has "$o" '- L-1 · rule one' && ok "empty PATH still works" || bad "empty PATH: rc=$rc"

silent "malformed stdin gives no output and exit 0" 'not json'
silent "empty stdin gives no output and exit 0" ''

o=$(send "$(tool write-plan)")
d=$(printf '%s' "$o" | /usr/bin/jq -r '.hookSpecificOutput | has("permissionDecision")' 2>/dev/null)
[ "$d" = "false" ] && ok "no permission decision" || bad "permissionDecision present or no output: '$d'"

report
