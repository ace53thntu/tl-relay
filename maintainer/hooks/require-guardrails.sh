#!/bin/sh
# PreToolUse, registered user-global. Denies while the registered hooks do not
# match the fragments.
#
# The EXIT trap is the point. Exit 1 and exit 127 both mean "continue" to Claude
# Code, so an unbound variable or a missing library would silently disable this
# hook. Every unplanned exit becomes a block instead, and the allow paths clear
# the trap explicitly.
trap 'printf "ai-sdlc: require-guardrails.sh stopped before reaching a decision. Run it by hand with the payload to see why.\n" >&2; exit 2' EXIT
set -u

# Without jq the deny below prints nothing, and empty output means "continue".
# This check comes before the allowlist: with no jq nothing can be decided, and
# the repair is made from a terminal.
command -v jq >/dev/null 2>&1 || {
  printf 'ai-sdlc: jq not found, cannot verify guardrails.\n' >&2
  trap - EXIT
  exit 2
}

payload=$(cat)

. "$(dirname "$0")/lib-guardrails.sh"

# Read, Edit, Write, Glob and Grep are never denied. Restoring a registration
# needs exactly those, and a guardrail that cannot be repaired from inside the
# session it stops is a trap. Bash is denied, which is what block-env-dump.sh
# guards anyway.
tool=$(printf '%s' "$payload" | jq -r '.tool_name // ""' 2>/dev/null)
case "$tool" in
  Read|Edit|Write|Glob|Grep) trap - EXIT; exit 0 ;;
esac

# The payload's cwd follows a `cd` in the Bash tool. The project directory is
# where the session loaded its project settings from, and it does not move.
project=${CLAUDE_PROJECT_DIR:-$(printf '%s' "$payload" | jq -r '.cwd // ""' 2>/dev/null)}
# A trailing slash or a symlinked spelling must not skip the project pair.
project=$(cd "$project" 2>/dev/null && pwd -P || printf '%s' "$project")

problems=$(guardrail_problems "$project")
if [ $? -eq 0 ]; then
  trap - EXIT
  exit 0
fi

jq -n --arg p "$(printf '%s' "$problems" | tr '\n' ';')" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",
    permissionDecisionReason:("ai-sdlc: guardrails are not in place. " + $p +
      " Read, Edit and Write are never denied: restore the registration with them, then retry.")}}' || exit 2
trap - EXIT
exit 0
