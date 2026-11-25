#!/bin/sh
# Runs every test file. Exit 1 if any fails.
#
# TL_RELAY_IN_TESTS tells session-start-report.sh not to run this suite, which it
# would otherwise do from inside a test of itself, without bound.
set -u
unset AI_SDLC_HOME AI_SDLC_REPO AI_SDLC_ROOT AI_SDLC_USER_FRAGMENT AI_SDLC_FRAGMENT AI_SDLC_USER_SETTINGS AI_SDLC_SETTINGS
unset TL_RELAY_HOME TL_RELAY_REPO TL_RELAY_ROOT TL_RELAY_USER_FRAGMENT TL_RELAY_FRAGMENT TL_RELAY_USER_SETTINGS TL_RELAY_SETTINGS TL_RELAY_MEMORY TL_RELAY_MEMORY_BUDGET TL_RELAY_MEMORY_MAXLINES
TL_RELAY_IN_TESTS=1
export TL_RELAY_IN_TESTS

dir=$(dirname "$0")
rc=0
for t in "$dir"/test_*.sh; do
  [ -f "$t" ] || continue
  printf '%s\n' "$(basename "$t")"
  sh "$t" </dev/null || rc=1
done
exit $rc
