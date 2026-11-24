#!/bin/sh
# PreToolUse (Skill) and UserPromptSubmit. Injects the skill's lesson file.
set -u

[ -n "${TL_RELAY_LESSONS:-}" ] || { /bin/cat >/dev/null 2>&1; exit 0; }

jq=/usr/bin/jq
[ -x "$jq" ] || jq=$(command -v jq) || exit 0

input=$(/bin/cat 2>/dev/null) || input=

event=$(printf '%s' "$input" | "$jq" -j '.hook_event_name | strings' 2>/dev/null) || :
case "$event" in
  PreToolUse) q='(.tool_input.skill | strings) // empty' ;;
  UserPromptSubmit) q='(.prompt | strings | capture("^/(?<n>[^\\s]*)") | .n) // empty' ;;
  *) exit 0 ;;
esac

name=$(printf '%s' "$input" | "$jq" -j "($q) + \".\"" 2>/dev/null) || exit 0
name=${name%.}
name=${name#tl-relay:}

export LC_ALL=C
case "$name" in
  ''|-*|*[!a-z0-9-]*) exit 0 ;;
esac

file="$TL_RELAY_LESSONS/$name.md"
[ -s "$file" ] && [ -r "$file" ] || exit 0

"$jq" -n --rawfile c "$file" --arg e "$event" --arg n "$name" --arg p "$file" \
  '{hookSpecificOutput:{hookEventName:$e,additionalContext:("Lessons for \($n) from \($p). A lesson replaces a default of that skill. An instruction from the operator in this session overrides a lesson.\n\n" + $c)}}' 2>/dev/null || :
exit 0
