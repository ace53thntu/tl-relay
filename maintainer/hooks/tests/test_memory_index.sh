#!/bin/sh
. "$(dirname "$0")/lib.sh"
H="$(dirname "$0")/../check-memory-index.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

printf '# Index\n- [a](a.md) short hook\n' > "$TMP/good.md"
{ head -c 30000 /dev/zero | tr '\0' 'x'; printf '\n'; } > "$TMP/big.md"
i=0; while [ $i -lt 250 ]; do printf 'x\n'; i=$((i+1)); done > "$TMP/tall.md"

sh "$H" "$TMP/good.md" >/dev/null 2>&1
[ $? -eq 0 ] && ok "accepts a compact index" || bad "should accept good.md"

out=$(sh "$H" "$TMP/big.md" 2>&1); rc=$?
{ [ $rc -eq 1 ] && printf '%s' "$out" | grep -qF 'bytes against'; } && ok "rejects a file over the byte budget" || bad "expected rc=1 naming bytes, got $rc"

out=$(sh "$H" "$TMP/tall.md" 2>&1); rc=$?
{ [ $rc -eq 1 ] && printf '%s' "$out" | grep -qF '250 lines'; } && ok "rejects a file over the line limit" || bad "expected rc=1 naming 250 lines, got $rc"

sh "$H" "$TMP/absent.md" >/dev/null 2>&1
[ $? -eq 1 ] && ok "a missing file is an error, not a pass" || bad "must fail closed on a missing file"

report
