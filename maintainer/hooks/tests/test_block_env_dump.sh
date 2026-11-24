#!/bin/sh
. "$(dirname "$0")/lib.sh"
H="$(dirname "$0")/../block-env-dump.sh"

assert_deny "$H" '{"tool_input":{"command":"export"},"cwd":"/tmp"}' "TOAN BO bien moi truong"
assert_deny "$H" '{"tool_input":{"command":"printenv"},"cwd":"/tmp"}' "TOAN BO bien moi truong"
assert_deny "$H" '{"tool_input":{"command":"export $(grep -v ^# .env | xargs)"},"cwd":"/tmp"}' "phan thay the rong"
assert_deny "$H" '{"tool_input":{"command":"cd apps/mobile && cat config.json"},"cwd":"/tmp"}' "khong theo doi cd"
assert_allow "$H" '{"tool_input":{"command":"echo hello"},"cwd":"/tmp"}'
assert_allow "$H" '{"tool_input":{"command":"grep -rn foo /absolute/path"},"cwd":"/tmp"}'

home_read() { printf '{"tool_input":{"command":"%s"},"cwd":"/tmp"}' "$1" | HOME=/Users/someone sh "$H" 2>/dev/null; }
o=$(home_read 'cat /Users/someone/.zshrc')
[ "$(_decision "$o")" = "deny" ] && ok "denies an absolute home path to a shell rc file" || bad "absolute home path was allowed"
o=$(home_read 'cat /Users/other/.zshrc')
[ "$(_decision "$o")" != "deny" ] && ok "allows a path outside HOME" || bad "denied a path outside HOME"
o=$(home_read 'cat ~/.zshrc')
[ "$(_decision "$o")" = "deny" ] && ok "still denies the ~ form" || bad "~ form allowed"
o=$(home_read 'cat $HOME/.zshrc')
[ "$(_decision "$o")" = "deny" ] && ok "still denies the HOME variable form" || bad "HOME form allowed"
o=$(home_read 'cat ${HOME}/.zshrc')
[ "$(_decision "$o")" = "deny" ] && ok "denies the braced HOME form" || bad "braced HOME form allowed"
o=$(printf '{"tool_input":{"command":"cat /Users/someone/.zshrc"},"cwd":"/tmp"}' | HOME=/Users/someone/ sh "$H" 2>/dev/null)
[ "$(_decision "$o")" = "deny" ] && ok "denies the absolute form when HOME has a trailing slash" || bad "trailing-slash HOME allowed the absolute form"
o=$(printf '{"tool_input":{"command":"cat ~/.zshrc"},"cwd":"/tmp"}' | HOME=/ sh "$H" 2>/dev/null)
[ "$(_decision "$o")" = "deny" ] && ok "denies the ~ form when HOME is /" || bad "HOME=/ allowed the ~ form"

report
