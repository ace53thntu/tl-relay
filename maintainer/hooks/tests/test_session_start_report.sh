#!/bin/sh
. "$(dirname "$0")/lib.sh"
H="$(dirname "$0")/../session-start-report.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
printf '#!/bin/sh\nexit 0\n' > "$TMP/a.sh"
mkdir -p "$TMP/home/.claude" "$TMP/home/.claude-other"

printf '{"hooks":{"PreToolUse":[{"matcher":"*","hooks":[{"type":"command","command":"/bin/sh %s%s%s"}]}]}}\n' "'" "$TMP/a.sh" "'" > "$TMP/ufrag.json"
LIVE="$TMP/home/.claude/settings.json"
cp "$TMP/ufrag.json" "$LIVE"
printf '{"hooks":{}}\n' > "$TMP/empty.json"

# HOME points at the fixture so the scan for config directories never reads the
# real ones.
run() { # user-settings [memory-file]
  env -u AI_SDLC_HOME -u AI_SDLC_REPO -u AI_SDLC_ROOT -u AI_SDLC_USER_FRAGMENT -u AI_SDLC_FRAGMENT -u AI_SDLC_USER_SETTINGS -u AI_SDLC_SETTINGS -u TL_RELAY_HOME -u TL_RELAY_MEMORY -u TL_RELAY_MEMORY_BUDGET -u TL_RELAY_MEMORY_MAXLINES HOME="$TMP/home" ${2:+TL_RELAY_MEMORY="$2"} TL_RELAY_ROOT="${TL_RELAY_ROOT:-$TMP/root}" TL_RELAY_COMPARE="$(dirname "$0")/../compare.jq" \
  TL_RELAY_USER_FRAGMENT="$TMP/ufrag.json" TL_RELAY_FRAGMENT="$TMP/ufrag.json" \
  TL_RELAY_USER_SETTINGS="$1" TL_RELAY_SETTINGS="$1" \
  TL_RELAY_IN_TESTS=1 sh "$H" </dev/null 2>/dev/null
}

o=$(run "$LIVE")
printf '%s' "$o" | grep -qxF 'tl-relay guardrail check: ok.' && ok "reports ok on stdout when registered" || bad "no ok on stdout"

o=$(run "$TMP/empty.json")
printf '%s' "$o" | grep -qF 'tl-relay guardrail check: FAILED.' && ok "reports FAILED on stdout when a hook is missing" || bad "no FAILED line"
printf '%s' "$o" | grep -qF 'a.sh' && ok "names the missing hook on stdout" || bad "did not name a.sh"

run "$TMP/empty.json" >/dev/null
[ $? -eq 0 ] && ok "always exits 0" || bad "SessionStart exit 2 does not block, so exit 0"

o=$(run "$LIVE")
printf '%s' "$o" | grep -qF 'does not compare' && bad "flagged a config directory that is listed" || ok "silent when every config directory is listed"

cp "$TMP/ufrag.json" "$TMP/home/.claude-other/settings.json"
o=$(run "$LIVE")
printf '%s' "$o" | grep -qF '.claude-other/settings.json' && ok "names a config directory the enforcer does not compare" || bad "an unlisted config directory went unreported"

printf 'short\n' > "$TMP/mem_ok.md"
head -c 30000 /dev/zero | tr '\0' 'x' > "$TMP/mem_big.md"
i=0; while [ $i -lt 250 ]; do printf 'x\n'; i=$((i+1)); done > "$TMP/mem_tall.md"

mem_run() { run "$LIVE" "$1"; }

o=$(mem_run "$TMP/mem_big.md")
printf '%s' "$o" | grep -qF 'MEMORY.md' && ok "warns when MEMORY.md is over its byte budget" || bad "no memory warning"

o=$(mem_run "$TMP/mem_tall.md")
printf '%s' "$o" | grep -qF 'MEMORY.md' && ok "warns when MEMORY.md is over its line limit" || bad "no memory warning"

o=$(mem_run "$TMP/mem_ok.md")
printf '%s' "$o" | grep -qF 'MEMORY.md' && bad "should be silent when memory is within limits" || ok "silent when memory is fine"
o=$(MEM="$TMP/mem_big.md" run "$LIVE")
printf '%s' "$o" | grep -qF 'MEMORY.md' && bad "an exported MEM leaks into the memory path" || ok "ignores an exported MEM"

STUB=$(mktemp -d)

suite_run() { # stub-exit-code
  printf '#!/bin/sh\nexit %s\n' "$1" > "$STUB/run.sh"
  env -u AI_SDLC_HOME -u AI_SDLC_REPO -u AI_SDLC_ROOT -u AI_SDLC_USER_FRAGMENT -u AI_SDLC_FRAGMENT -u AI_SDLC_USER_SETTINGS -u AI_SDLC_SETTINGS -u TL_RELAY_HOME -u TL_RELAY_MEMORY -u TL_RELAY_MEMORY_BUDGET -u TL_RELAY_MEMORY_MAXLINES HOME="$TMP/home" TL_RELAY_ROOT="$TMP/root" TL_RELAY_COMPARE="$(dirname "$0")/../compare.jq" \
  TL_RELAY_USER_FRAGMENT="$TMP/ufrag.json" TL_RELAY_FRAGMENT="$TMP/ufrag.json" \
  TL_RELAY_USER_SETTINGS="$LIVE" TL_RELAY_SETTINGS="$LIVE" \
  TL_RELAY_TESTS="$STUB/run.sh" TL_RELAY_IN_TESTS= sh "$H" </dev/null 2>/dev/null
}

o=$(suite_run 1)
printf '%s' "$o" | grep -qi 'test suite' && ok "mentions a failing suite" || bad "no mention of the suite"

o=$(suite_run 0)
printf '%s' "$o" | grep -qi 'test suite' && bad "should be silent when the suite passes" || ok "silent when the suite passes"

mkdir -p "$TMP/home/.claude/projects/-a-b-c/memory"
head -c 30000 /dev/zero | tr '\0' 'x' > "$TMP/home/.claude/projects/-a-b-c/memory/MEMORY.md"
o=$(TL_RELAY_ROOT=/a/b.c run "$LIVE")
printf '%s' "$o" | grep -qF 'MEMORY.md' && ok "derives the memory path from the root" || bad "memory path not derived from TL_RELAY_ROOT"

o=$(run "$LIVE")
printf '%s' "$o" | grep -qF 'install.claude_config_dirs' && ok "points unlisted config directories at the install config" || bad "message does not name install.claude_config_dirs"

o=$(env -u AI_SDLC_HOME -u AI_SDLC_REPO -u AI_SDLC_ROOT -u AI_SDLC_USER_FRAGMENT -u AI_SDLC_FRAGMENT -u AI_SDLC_USER_SETTINGS -u AI_SDLC_SETTINGS -u TL_RELAY_HOME -u TL_RELAY_ROOT -u TL_RELAY_USER_FRAGMENT -u TL_RELAY_FRAGMENT -u TL_RELAY_USER_SETTINGS -u TL_RELAY_SETTINGS \
  HOME="$TMP/home" TL_RELAY_COMPARE="$(dirname "$0")/../compare.jq" TL_RELAY_IN_TESTS=1 sh "$H" </dev/null 2>/dev/null)
rc=$?
{ [ $rc -eq 0 ] && printf '%s' "$o" | grep -qF 'sdlc.py install'; } && ok "exits 0 and names sdlc.py install with every variable unset" || bad "rc=$rc out='$o'"

rm -rf "$STUB"

report
