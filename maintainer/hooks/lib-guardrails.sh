# Sourced, never executed. No `set -e`: callers decide what a problem means.
# `sdlc.py install` writes $TL_RELAY_HOME/env.sh. A variable already set in the
# environment wins, even when empty. env.sh is read once, in a subshell.
# TL_RELAY_USER_SETTINGS is colon-separated, one entry per Claude Code config directory.
_lg_vars="ROOT USER_FRAGMENT FRAGMENT USER_SETTINGS SETTINGS"
_lg_env=
if [ -n "${TL_RELAY_HOME:-}" ] && [ -f "$TL_RELAY_HOME/env.sh" ]; then
  _lg_env=$(. "$TL_RELAY_HOME/env.sh" >/dev/null 2>&1
    for _lg_v in $_lg_vars; do
      eval "printf 'N %s=%s\\n' \$_lg_v \"\${TL_RELAY_$_lg_v:-}\""
    done)
fi
for _lg_v in $_lg_vars; do
  eval "[ \"\${TL_RELAY_$_lg_v+x}\" = x ]" && continue
  _lg_new=$(printf '%s\n' "$_lg_env" | sed -n "s/^N $_lg_v=//p")
  if [ -n "$_lg_new" ]; then
    eval "TL_RELAY_$_lg_v=\$_lg_new"
  else
    eval "TL_RELAY_$_lg_v="
  fi
done
: "${TL_RELAY_COMPARE:=$(dirname "$0")/compare.jq}"

# fragment, live-settings -> problem lines on stdout. 0 clean, 1 otherwise.
_compare_pair() {
  _cp_raw=$(jq -n --slurpfile f "$1" --slurpfile l "$2" -r -f "$TL_RELAY_COMPARE" 2>/dev/null) || {
    printf 'cannot compare %s against %s\n' "$1" "$2"
    return 1
  }

  _cp_found=$(printf '%s\n' "$_cp_raw" | while IFS="$(printf '\t')" read -r _kind _rest; do
    case "$_kind" in
      (EMPTY)    printf 'fragment %s lists no hooks\n' "$1" ;;
      (MISSING)  printf 'not registered in %s: %s\n' "$2" "$_rest" ;;
      (SCRIPT)   [ -f "$_rest" ] || printf 'script missing: %s\n' "$_rest" ;;
      (NOSCRIPT) printf 'no quoted script path in %s: %s\n' "$1" "$_rest" ;;
    esac
  done)

  [ -z "$_cp_found" ] && return 0
  printf '%s\n' "$_cp_found"
  return 1
}

# project dir -> problem lines on stdout. 0 clean, 1 otherwise.
guardrail_problems() {
  _gp_cwd=${1:-}
  _gp_rc=0
  _gp_n=0

  for _gp_v in $_lg_vars; do
    if eval "[ -z \"\${TL_RELAY_$_gp_v:-}\" ]"; then
      printf 'TL_RELAY_%s is unset; run sdlc.py install\n' "$_gp_v"
      _gp_rc=1
    fi
  done
  [ "$_gp_rc" -eq 0 ] || return 1

  # The hook cannot tell which config directory its session loaded, so every
  # listed user settings file must carry the whole user fragment.
  _gp_ifs=$IFS
  IFS=:
  for _gp_f in $TL_RELAY_USER_SETTINGS; do
    IFS=$_gp_ifs
    _gp_n=$((_gp_n+1))
    _compare_pair "$TL_RELAY_USER_FRAGMENT" "$_gp_f" || _gp_rc=1
  done
  IFS=$_gp_ifs
  [ "$_gp_n" -gt 0 ] || { printf 'no user settings file to compare\n'; _gp_rc=1; }

  # Project hooks are only supposed to be registered at the root. Claude Code
  # reads project settings from the session's own working directory and does not
  # search upward, so requiring them in a sub-repository session would deny every
  # tool call in 65 repositories.
  if [ "$_gp_cwd" = "$TL_RELAY_ROOT" ]; then
    _compare_pair "$TL_RELAY_FRAGMENT" "$TL_RELAY_SETTINGS" || _gp_rc=1
  fi

  return $_gp_rc
}
