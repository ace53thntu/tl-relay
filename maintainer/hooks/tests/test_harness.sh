#!/bin/sh
# The harness must detect a deny and an allow, and must not hang on a script
# that reads stdin.
. "$(dirname "$0")/lib.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

printf '#!/bin/sh\ncat >/dev/null\njq -n %s\n' \
  "'{hookSpecificOutput:{hookEventName:\"PreToolUse\",permissionDecision:\"deny\",permissionDecisionReason:\"canary reason\"}}'" \
  > "$TMP/always_deny.sh"
printf '#!/bin/sh\ncat >/dev/null\nexit 0\n' > "$TMP/always_allow.sh"
chmod +x "$TMP/always_deny.sh" "$TMP/always_allow.sh"

assert_deny  "$TMP/always_deny.sh"  '{"tool_input":{"command":"anything"}}' "canary reason"
assert_allow "$TMP/always_allow.sh" '{"tool_input":{"command":"anything"}}'

report
