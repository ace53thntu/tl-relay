#!/bin/sh
# Enforces the two load limits on the memory index. Past either one the loader
# truncates the file and a session starts on part of it.
set -u

FILE=${1:?usage: check-memory-index.sh <file>}
BUDGET=${AI_SDLC_MEMORY_BUDGET:-24400}
MAXLINES=${AI_SDLC_MEMORY_MAXLINES:-200}

[ -f "$FILE" ] || { printf '%s does not exist\n' "$FILE" >&2; exit 1; }

rc=0

size=$(wc -c < "$FILE" | tr -d ' ')
if [ "$size" -gt "$BUDGET" ]; then
  printf '%s is %s bytes against a %s budget\n' "$FILE" "$size" "$BUDGET" >&2
  rc=1
fi

lines=$(wc -l < "$FILE" | tr -d ' ')
if [ "$lines" -gt "$MAXLINES" ]; then
  printf '%s is %s lines against a %s limit\n' "$FILE" "$lines" "$MAXLINES" >&2
  rc=1
fi

exit $rc
