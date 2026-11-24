#!/bin/sh
# Runs every test file. Exit 1 if any fails.
#
# AI_SDLC_IN_TESTS tells session-start-report.sh not to run this suite, which it
# would otherwise do from inside a test of itself, without bound.
set -u
AI_SDLC_IN_TESTS=1
export AI_SDLC_IN_TESTS

dir=$(dirname "$0")
rc=0
for t in "$dir"/test_*.sh; do
  [ -f "$t" ] || continue
  printf '%s\n' "$(basename "$t")"
  sh "$t" </dev/null || rc=1
done
exit $rc
