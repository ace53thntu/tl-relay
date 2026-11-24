# Shared assertions. Sourced, never executed.
PASS=0
FAIL=0

ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }

# Always closes stdin. A hook that drains stdin must not block on a terminal.
_run() { printf '%s' "$2" | sh "$1" 2>/dev/null; }

_decision() { printf '%s' "$1" | jq -r '.hookSpecificOutput.permissionDecision // ""' 2>/dev/null; }
_reason()   { printf '%s' "$1" | jq -r '.hookSpecificOutput.permissionDecisionReason // ""' 2>/dev/null; }

assert_deny() {
  out=$(_run "$1" "$2")
  d=$(_decision "$out"); r=$(_reason "$out")
  if [ "$d" = "deny" ] && printf '%s' "$r" | grep -qF "$3"; then
    ok "deny: $3"
  else
    bad "expected deny containing '$3', got decision='$d' reason='$r'"
  fi
}

assert_allow() {
  out=$(_run "$1" "$2")
  d=$(_decision "$out")
  if [ "$d" = "deny" ]; then
    bad "expected allow, got deny: $(_reason "$out")"
  else
    ok "allow"
  fi
}

report() {
  printf '%s: %d passed, %d failed\n' "$(basename "$0")" "$PASS" "$FAIL"
  [ "$FAIL" -eq 0 ]
}
