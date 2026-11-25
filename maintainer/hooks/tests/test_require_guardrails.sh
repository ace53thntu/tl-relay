#!/bin/sh
. "$(dirname "$0")/lib.sh"
H="$(dirname "$0")/../require-guardrails.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
printf '#!/bin/sh\nexit 0\n' > "$TMP/a.sh"; printf '#!/bin/sh\nexit 0\n' > "$TMP/b.sh"
mkdir "$TMP/dir.sh"

frag() { printf '{"hooks":{"%s":[{"matcher":"%s","hooks":[{"type":"command","command":"/bin/sh %s%s%s"}]}]}}\n' "$1" "$2" "'" "$3" "'"; }
frag PreToolUse   '*'  "$TMP/a.sh"    > "$TMP/ufrag.json";  cp "$TMP/ufrag.json" "$TMP/usettings.json"
frag SessionStart '*'  "$TMP/b.sh"    > "$TMP/pfrag.json";  cp "$TMP/pfrag.json" "$TMP/psettings.json"
frag PostToolUse  '*'  "$TMP/a.sh"    > "$TMP/moved.json"
frag PreToolUse   Bash "$TMP/a.sh"    > "$TMP/narrow.json"
frag PreToolUse   '*'  "$TMP/gone.sh" > "$TMP/ghost.json"
frag PreToolUse   '*'  "$TMP/dir.sh"  > "$TMP/dir.json"
printf '{"hooks":{"PreToolUse":[{"matcher":"*","hooks":[{"type":"command","command":"/usr/bin/python3 %s"}]}]}}\n' "$TMP/a.sh" > "$TMP/bare.json"
jq '.hooks.Stop = [{"hooks":[{"type":"prompt","prompt":"check"}]}]' "$TMP/usettings.json" > "$TMP/withprompt.json"
jq '.hooks.Stop = [{"matcher":"Bash"}]' "$TMP/usettings.json" > "$TMP/nohooks.json"
printf '{"hooks":{}}\n' > "$TMP/empty.json"
printf 'not json\n'     > "$TMP/corrupt.json"

ROOT=$(cd "$TMP" && pwd -P)/root
mkdir "$ROOT"
# CLAUDE_PROJECT_DIR is cleared so the payload's cwd decides, as in a session
# that does not export it.
call() { # tool, cwd, user-settings-list, user-fragment, project-settings
  printf '{"tool_name":"%s","cwd":"%s","tool_input":{"command":"ls"}}' "$1" "$2" \
  | CLAUDE_PROJECT_DIR="${PROJECT_DIR:-}" \
    TL_RELAY_ROOT="$ROOT" TL_RELAY_COMPARE="$(dirname "$0")/../compare.jq" \
    TL_RELAY_USER_FRAGMENT="${4:-$TMP/ufrag.json}" TL_RELAY_FRAGMENT="$TMP/pfrag.json" \
    TL_RELAY_USER_SETTINGS="$3" TL_RELAY_SETTINGS="${5:-$TMP/psettings.json}" sh "$H" 2>/dev/null
  echo $? > "$TMP/rc"
}
allows() { [ "$(dec "$1")" != "deny" ] && [ "$(cat "$TMP/rc")" = 0 ]; }
dec() { printf '%s' "$1" | jq -r '.hookSpecificOutput.permissionDecision // ""' 2>/dev/null; }
rsn() { printf '%s' "$1" | jq -r '.hookSpecificOutput.permissionDecisionReason // ""' 2>/dev/null; }

o=$(call Bash "$ROOT" "$TMP/usettings.json")
allows "$o" && ok "allows Bash when everything is registered" || bad "denied: $(rsn "$o")"

o=$(call Bash "$ROOT" "$TMP/empty.json")
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "a.sh"; } && ok "denies and names the missing user hook" || bad "expected deny naming a.sh"

o=$(call Bash "$ROOT" "$TMP/moved.json")
[ "$(dec "$o")" = "deny" ] && ok "denies when a hook moved to another event" || bad "event drift must not pass"

o=$(call Bash "$ROOT" "$TMP/narrow.json")
[ "$(dec "$o")" = "deny" ] && ok "denies when a matcher was narrowed" || bad "matcher drift must not pass"

o=$(call Bash "$ROOT" "$TMP/ghost.json" "$TMP/ghost.json")
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "gone.sh"; } && ok "denies when a registered script does not exist" || bad "a registration pointing at nothing must fail closed"

o=$(call Bash "$ROOT" "$TMP/dir.json" "$TMP/dir.json")
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "dir.sh"; } && ok "denies when the script path is a directory" || bad "a directory is not a script"

o=$(call Bash "$ROOT" "$TMP/bare.json" "$TMP/bare.json")
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "no quoted script path"; } && ok "denies a fragment entry whose script path cannot be checked" || bad "an unquoted command skips the existence check"

o=$(call Bash "$ROOT" "$TMP/usettings.json" "$TMP/empty.json")
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "lists no hooks"; } && ok "denies on a fragment that requires nothing" || bad "an empty fragment must not switch the check off"

o=$(call Bash "$ROOT" "$TMP/usettings.json" "$TMP/corrupt.json")
[ "$(dec "$o")" = "deny" ] && ok "denies on a corrupt fragment" || bad "corrupt fragment must fail closed"

o=$(call Bash "$ROOT" "$TMP/usettings.json" "$TMP/nope.json")
[ "$(dec "$o")" = "deny" ] && ok "denies on an absent fragment" || bad "absent fragment must fail closed"

o=$(call Bash "$ROOT" "$TMP/withprompt.json")
allows "$o" && ok "allows when the live file also holds a prompt hook" || bad "denied: $(rsn "$o")"

o=$(call Bash "$ROOT" "$TMP/nohooks.json")
allows "$o" && ok "allows when a live matcher object has no hooks array" || bad "denied: $(rsn "$o")"

o=$(call Bash "$ROOT" "$TMP/usettings.json:$TMP/usettings.json")
allows "$o" && ok "allows when every config directory is registered" || bad "denied: $(rsn "$o")"

o=$(call Bash "$ROOT" "$TMP/usettings.json:$TMP/empty.json")
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "empty.json"; } && ok "denies and names the config directory that lost the hook" || bad "a second config directory must not go unguarded"

o=$(call Bash "$ROOT" "$TMP/usettings.json:$TMP/nope.json")
[ "$(dec "$o")" = "deny" ] && ok "denies when a listed settings file is absent" || bad "absent settings must fail closed"

o=$(call Bash "$ROOT" "$TMP/usettings.json" "" "$TMP/empty.json")
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "b.sh"; } && ok "denies and names the missing project hook at the root" || bad "expected deny naming b.sh"

o=$(call Bash "$TMP" "$TMP/usettings.json" "" "$TMP/empty.json")
allows "$o" && ok "ignores the project pair outside the root" || bad "must not require project hooks in a sub-repo session"

o=$(PROJECT_DIR="$ROOT" call Bash "$TMP" "$TMP/usettings.json" "" "$TMP/empty.json")
[ "$(dec "$o")" = "deny" ] && ok "keeps the project pair after a cd out of the root" || bad "a cd must not drop the project hooks"

o=$(PROJECT_DIR="$ROOT/" call Bash "$TMP" "$TMP/usettings.json" "" "$TMP/empty.json")
[ "$(dec "$o")" = "deny" ] && ok "keeps the project pair when the root is spelled with a trailing slash" || bad "a trailing slash must not skip the project hooks"

for t in Read Edit Write; do
  o=$(call "$t" "$ROOT" "$TMP/empty.json")
  allows "$o" && ok "always allows $t so the operator can repair" || bad "$t must never be denied"
done

o=$(call Bash "$ROOT" "$TMP/empty.json")
printf '%s' "$o" | jq -e . >/dev/null 2>&1 && ok "deny output is valid JSON" || bad "invalid JSON lets the tool proceed"

bare() {
  printf '{"tool_name":"Bash","cwd":"%s","tool_input":{"command":"ls"}}' "$ROOT" \
  | env -u AI_SDLC_HOME -u AI_SDLC_REPO -u AI_SDLC_ROOT -u AI_SDLC_USER_FRAGMENT -u AI_SDLC_FRAGMENT \
      -u AI_SDLC_USER_SETTINGS -u AI_SDLC_SETTINGS -u TL_RELAY_HOME -u TL_RELAY_ROOT -u TL_RELAY_USER_FRAGMENT -u TL_RELAY_FRAGMENT \
      -u TL_RELAY_USER_SETTINGS -u TL_RELAY_SETTINGS CLAUDE_PROJECT_DIR= \
      TL_RELAY_COMPARE="$(dirname "$0")/../compare.jq" "$@" sh "$H" 2>/dev/null
  echo $? > "$TMP/rc"
}
o=$(bare)
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "TL_RELAY_ROOT is unset" && printf '%s' "$(rsn "$o")" | grep -qF "sdlc.py install"; } && ok "names an unset variable and sdlc.py install" || bad "unset variables not reported: $(rsn "$o")"

mkdir "$TMP/ahome"
printf 'TL_RELAY_ROOT=%s\nTL_RELAY_USER_FRAGMENT=%s\nTL_RELAY_FRAGMENT=%s\nTL_RELAY_USER_SETTINGS=%s\nTL_RELAY_SETTINGS=%s\n' \
  "$ROOT" "$TMP/ufrag.json" "$TMP/pfrag.json" "$TMP/usettings.json" "$TMP/psettings.json" > "$TMP/ahome/env.sh"
o=$(bare TL_RELAY_HOME="$TMP/ahome")
allows "$o" && ok "reads the five variables from env.sh under the home" || bad "env.sh ignored: $(rsn "$o")"

o=$(bare TL_RELAY_HOME="$TMP/ahome" TL_RELAY_USER_SETTINGS="$TMP/empty.json")
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "empty.json"; } && ok "a variable set in the environment wins over env.sh" || bad "env.sh overrode the environment"

o=$(bare TL_RELAY_HOME="$TMP/ahome" TL_RELAY_USER_SETTINGS=)
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "TL_RELAY_USER_SETTINGS is unset"; } && ok "a variable exported empty is not replaced from env.sh" || bad "empty variable was overridden by env.sh"

mkdir "$TMP/lhome"
printf 'AI_SDLC_ROOT=%s\nAI_SDLC_USER_FRAGMENT=%s\nAI_SDLC_FRAGMENT=%s\nAI_SDLC_USER_SETTINGS=%s\nAI_SDLC_SETTINGS=%s\n' \
  "$ROOT" "$TMP/ufrag.json" "$TMP/pfrag.json" "$TMP/usettings.json" "$TMP/psettings.json" > "$TMP/lhome/env.sh"
o=$(bare AI_SDLC_HOME="$TMP/lhome")
allows "$o" && ok "legacy env allows: AI_SDLC_HOME with AI_SDLC_ names in env.sh" || bad "legacy env denied: $(rsn "$o")"

mkdir "$TMP/mhome" "$TMP/other"
printf 'TL_RELAY_ROOT=%s\nAI_SDLC_ROOT=%s\nTL_RELAY_USER_FRAGMENT=%s\nTL_RELAY_FRAGMENT=%s\nTL_RELAY_USER_SETTINGS=%s\nTL_RELAY_SETTINGS=%s\n' \
  "$ROOT" "$TMP/other" "$TMP/ufrag.json" "$TMP/pfrag.json" "$TMP/usettings.json" "$TMP/psettings.json" > "$TMP/mhome/env.sh"
o=$(bare TL_RELAY_HOME="$TMP/mhome" TL_RELAY_SETTINGS="$TMP/empty.json")
{ [ "$(dec "$o")" = "deny" ] && printf '%s' "$(rsn "$o")" | grep -qF "b.sh"; } && ok "new env.sh wins: TL_RELAY_ROOT is used over AI_SDLC_ROOT" || bad "AI_SDLC_ROOT won: $(rsn "$o")"

mkdir "$TMP/nohome"
o=$(bare TL_RELAY_HOME="$TMP/nohome" AI_SDLC_ROOT="$ROOT" AI_SDLC_USER_FRAGMENT="$TMP/ufrag.json" AI_SDLC_FRAGMENT="$TMP/pfrag.json" \
  AI_SDLC_USER_SETTINGS="$TMP/usettings.json" AI_SDLC_SETTINGS="$TMP/psettings.json")
allows "$o" && ok "legacy env names resolve when the home has no env.sh" || bad "env fallback denied: $(rsn "$o")"

# A PATH holding everything the hook needs except jq. An empty PATH would also
# remove cat, and the test would pass for the wrong reason.
mkdir "$TMP/bin"
for b in dirname cat tr; do ln -s "$(command -v "$b")" "$TMP/bin/$b"; done
err=$(printf '{"tool_name":"Bash","cwd":"%s","tool_input":{"command":"ls"}}' "$ROOT" \
  | CLAUDE_PROJECT_DIR= TL_RELAY_ROOT="$ROOT" TL_RELAY_COMPARE="$(dirname "$0")/../compare.jq" \
    TL_RELAY_USER_FRAGMENT="$TMP/ufrag.json" TL_RELAY_FRAGMENT="$TMP/pfrag.json" \
    TL_RELAY_USER_SETTINGS="$TMP/empty.json" TL_RELAY_SETTINGS="$TMP/psettings.json" \
    PATH="$TMP/bin" /bin/sh "$H" 2>&1 >/dev/null)
rc=$?
{ [ $rc -eq 2 ] && printf '%s' "$err" | grep -qF "jq not found"; } && ok "blocks with exit 2 and a reason when jq is unavailable" || bad "rc=$rc err='$err'"

report
