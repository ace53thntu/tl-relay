#!/bin/sh
# SessionStart. Injects using-tl-relay into the session.
set -u

/bin/cat >/dev/null 2>&1 || :

skill="${TL_RELAY_BOOTSTRAP_SKILL:-${CLAUDE_PLUGIN_ROOT:-${0%/*}/..}/skills/using-tl-relay/SKILL.md}"
[ -r "$skill" ] || exit 0

jq=/usr/bin/jq
[ -x "$jq" ] || jq=$(command -v jq) || exit 0
"$jq" -Rs '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:.}}' "$skill" 2>/dev/null || :
exit 0
