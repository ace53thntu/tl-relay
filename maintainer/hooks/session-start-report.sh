#!/bin/sh
# SessionStart. Prints the guardrail comparison where the model will read it.
#
# This hook cannot block. Exit 2 here shows stderr to the user and the session
# continues, and stderr never reaches the model. Plain stdout on exit 0 is the
# one channel SessionStart injects into context, so everything goes there.
set -u

cat >/dev/null 2>&1 || :

. "$(dirname "$0")/lib-guardrails.sh"

problems=$(guardrail_problems "${AI_SDLC_ROOT:-}")
if [ $? -eq 0 ]; then
  printf 'ai-sdlc guardrail check: ok.\n'
else
  printf 'ai-sdlc guardrail check: FAILED. Tool use is denied until this is fixed.\n%s\n' "$problems"
  printf 'Read and Edit are never denied. Restore the registration with them.\n'
fi

# A config directory created after the list was written is unguarded, and the
# enforcer cannot know it exists.
for conf in "${HOME:-/nonexistent}"/.claude*/settings.json; do
  [ -f "$conf" ] || continue
  case ":${AI_SDLC_USER_SETTINGS:-}:" in
    (*":$conf:"*) ;;
    (*) printf 'ai-sdlc: %s is a user settings file the enforcer does not compare. Add its directory to install.claude_config_dirs and rerun sdlc.py install.\n' "$conf" ;;
  esac
done

MEMORY=${AI_SDLC_MEMORY:-${HOME:-/nonexistent}/.claude/projects/$(printf %s "${AI_SDLC_ROOT:-}" | tr -c 'A-Za-z0-9' -)/memory/MEMORY.md}
if [ -f "$MEMORY" ]; then
  over=$(sh "$(dirname "$0")/check-memory-index.sh" "$MEMORY" 2>&1) ||
    printf 'ai-sdlc: MEMORY.md is past its load limit and is being truncated. %s\n' "$over"
fi

# Skipped inside the suite itself. run.sh exports AI_SDLC_IN_TESTS, and a test of
# this script would otherwise re-enter run.sh without bound.
TESTS=${AI_SDLC_TESTS:-$(dirname "$0")/tests/run.sh}
if [ -z "${AI_SDLC_IN_TESTS:-}" ] && [ -f "$TESTS" ]; then
  if ! sh "$TESTS" >/dev/null 2>&1; then
    printf 'ai-sdlc: the hook test suite is failing. Run: sh %s\n' "$TESTS"
  fi
fi

exit 0
