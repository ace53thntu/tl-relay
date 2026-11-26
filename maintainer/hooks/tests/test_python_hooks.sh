#!/bin/sh
. "$(dirname "$0")/lib.sh"
W="$(dirname "$0")/../wrap-bash-exit-code.py"
R="$(dirname "$0")/../redact-secrets-output.py"

py() { printf '%s' "$2" | /usr/bin/python3 "$1" 2>/dev/null; }

o=$(py "$W" '{"tool_name":"Bash","permission_mode":"bypassPermissions","tool_input":{"command":"ls /nonexistent-tl-relay"}}')
c=$(printf '%s' "$o" | jq -r '.hookSpecificOutput.updatedInput.command // ""' 2>/dev/null)
{ printf '%s' "$c" | grep -qF 'ls /nonexistent-tl-relay' && printf '%s' "$c" | grep -qF "trap '__cc_rc="; } \
  && ok "wraps a command in the exit trap" || bad "no wrapped command in updatedInput"

out=$(/bin/sh -c "$c" 2>/dev/null); rc=$?
{ [ -n "$c" ] && [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -qF '[exit code '; } \
  && ok "a failing wrapped command exits 0 and prints its code" || bad "wrapped command rc=$rc out='$out'"

o=$(py "$W" "$(jq -n --arg c "${c:-x}" '{tool_name:"Bash",permission_mode:"bypassPermissions",tool_input:{command:$c}}')")
{ [ -n "$c" ] && [ -z "$o" ]; } && ok "leaves an already wrapped command alone" || bad "wrapped twice"

for m in default acceptEdits auto dontAsk plan; do
  o=$(py "$W" "$(jq -n --arg m "$m" '{tool_name:"Bash",permission_mode:$m,tool_input:{command:"git log -1"}}')")
  { [ -f "$W" ] && [ -z "$o" ]; } && ok "leaves a command alone in $m mode" || bad "wrapped in $m mode"
done

# Built at run time: a literal token in this file would be masked by the redact
# hook whenever an agent reads the file.
tok=$(printf 'gh%s_%s' p AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA)
o=$(py "$R" "$(jq -n --arg t "$tok" '{tool_name:"Bash",tool_response:{stdout:("x " + $t + " y")}}')")
s=$(printf '%s' "$o" | jq -r '.hookSpecificOutput.updatedToolOutput.stdout // ""' 2>/dev/null)
[ "$s" = "x [REDACTED] y" ] && ok "masks a token by its prefix" || bad "got '$s'"

kv=$(printf 'MY_%s=%s' TOKEN abcdef123456)
want=$(printf 'MY_%s=[REDACTED]' TOKEN)
o=$(py "$R" "$(jq -n --arg t "$kv" '{tool_name:"Bash",tool_response:{stdout:$t}}')")
s=$(printf '%s' "$o" | jq -r '.hookSpecificOutput.updatedToolOutput.stdout // ""' 2>/dev/null)
[ "$s" = "$want" ] && ok "masks a NAME=value credential" || bad "got '$s'"

o=$(py "$R" '{"tool_name":"Bash","tool_response":{"stdout":"nothing to hide"}}')
{ [ -f "$R" ] && [ -z "$o" ]; } && ok "prints nothing when the output is clean" || bad "rewrote clean output"

report
