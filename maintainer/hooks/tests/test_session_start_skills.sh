#!/bin/sh
. "$(dirname "$0")/lib.sh"
H="$(cd "$(dirname "$0")/../../../hooks" && pwd)/session-start-skills.sh"

TMP=$(mktemp -d)
trap 'chmod 644 "$TMP/skill.md" 2>/dev/null; rm -rf "$TMP"' EXIT
printf 'say "hi" \\ then\nsecond line\n' > "$TMP/skill.md"

run() { env TL_RELAY_BOOTSTRAP_SKILL="$TMP/skill.md" "$@" /bin/sh "$H" </dev/null 2>/dev/null; }

o=$(run)
want=$(/bin/cat "$TMP/skill.md")
got=$(printf '%s' "$o" | /usr/bin/jq -er .hookSpecificOutput.additionalContext 2>/dev/null)
[ "$got" = "$want" ] && ok "additionalContext equals the skill text" || bad "additionalContext differs: '$got'"

n=$(printf '%s' "$o" | /usr/bin/jq -r .hookSpecificOutput.hookEventName 2>/dev/null)
[ "$n" = "SessionStart" ] && ok "hookEventName is SessionStart" || bad "hookEventName was '$n'"

o=$(env -u TL_RELAY_BOOTSTRAP_SKILL -u CLAUDE_PLUGIN_ROOT /bin/sh "$H" </dev/null 2>/dev/null)
real=$(/bin/cat "${H%/*}/../skills/using-tl-relay/SKILL.md")
got=$(printf '%s' "$o" | /usr/bin/jq -er .hookSpecificOutput.additionalContext 2>/dev/null)
[ -n "$real" ] && [ "$got" = "$real" ] && ok "default path carries the using-tl-relay skill text" || bad "default payload differs from using-tl-relay/SKILL.md"

n=$(printf '%s' "$o" | /usr/bin/jq -r .hookSpecificOutput.hookEventName 2>/dev/null)
[ "$n" = "SessionStart" ] && ok "default path hookEventName is SessionStart" || bad "default path hookEventName was '$n'"

o=$(env TL_RELAY_BOOTSTRAP_SKILL="$TMP/missing.md" /bin/sh "$H" </dev/null 2>/dev/null)
rc=$?
[ -z "$o" ] && [ $rc -eq 0 ] && ok "silent with exit 0 when the skill file is missing" || bad "missing file: rc=$rc out='$o'"

chmod 000 "$TMP/skill.md"
o=$(run)
rc=$?
[ $rc -eq 0 ] && ok "exits 0 when the skill file is unreadable" || bad "unreadable file: rc=$rc"
chmod 644 "$TMP/skill.md"

o=$(env TL_RELAY_BOOTSTRAP_SKILL="$TMP/skill.md" PATH=/nonexistent /bin/sh "$H" </dev/null 2>/dev/null)
got=$(printf '%s' "$o" | /usr/bin/jq -er .hookSpecificOutput.additionalContext 2>/dev/null)
[ "$got" = "$want" ] && ok "prints the payload with an empty PATH" || bad "no payload with PATH=/nonexistent"

report
