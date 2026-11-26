#!/bin/sh
# Proves the Vale gate: every expected rule fires on dirty.md, none fires on clean.md.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INI="$DIR/.vale.ini"
fail=0

command -v vale >/dev/null || { echo "FAIL vale is not on PATH. See https://docs.vale.sh/topics/installation"; exit 1; }

out=$(vale --no-exit --output=JSON --config "$INI" "$DIR/fixtures/dirty.md") || { echo "FAIL vale could not run on dirty.md"; exit 1; }
while IFS= read -r rule; do
  [ -n "$rule" ] || continue
  printf '%s' "$out" | grep -q "\"Check\": \"$rule\"" || { echo "FAIL $rule did not fire on dirty.md"; fail=1; }
done < "$DIR/fixtures/expected-rules.txt"

for f in "$DIR"/styles/TlRelay/*.yml; do
  [ -e "$f" ] || continue
  rule="TlRelay.$(basename "$f" .yml)"
  [ "$rule" = "TlRelay.SemicolonsTable" ] && continue
  grep -qx "$rule" "$DIR/fixtures/expected-rules.txt" || { echo "FAIL $rule has no line in expected-rules.txt"; fail=1; }
done

clean=$(vale --no-exit --output=JSON --config "$INI" "$DIR/fixtures/clean.md") || { echo "FAIL vale could not run on clean.md"; exit 1; }
if printf '%s' "$clean" | grep -q '"Check"'; then
  echo "FAIL clean.md raised alerts:"
  printf '%s\n' "$clean" | grep -E '"(Check|Line|Match)"'
  fail=1
fi

table=$(vale --output=JSON --config "$INI" "$DIR/fixtures/table.md") || { echo "FAIL a semicolon in a table cell raised an error"; fail=1; }
printf '%s' "$table" | grep -q '"Check": "TlRelay.SemicolonsTable"' || { echo "FAIL TlRelay.SemicolonsTable did not fire on table.md"; fail=1; }

( cd / && vale --config "$INI" "$DIR/fixtures/clean.md" >/dev/null ) || { echo "FAIL vale did not exit 0 on clean.md when run from /"; fail=1; }

HOMETMP=$(mktemp -d); trap 'rm -rf "$HOMETMP"' EXIT
plain=$(vale --no-exit --config "$INI" "$DIR/fixtures/dirty.md")
nohome=$(TL_RELAY_VALE_VOCAB="$HOMETMP/missing.txt" sh "$DIR/run.sh" --no-exit "$DIR/fixtures/dirty.md")
[ "$plain" = "$nohome" ] || { echo "FAIL run.sh differs from plain vale when the vocabulary file is missing"; fail=1; }
unset_=$(env -u TL_RELAY_VALE_VOCAB sh "$DIR/run.sh" --no-exit "$DIR/fixtures/dirty.md")
[ "$plain" = "$unset_" ] || { echo "FAIL run.sh differs from plain vale when TL_RELAY_VALE_VOCAB is unset"; fail=1; }
empty=$(TL_RELAY_VALE_VOCAB="" sh "$DIR/run.sh" --no-exit "$DIR/fixtures/dirty.md")
[ "$plain" = "$empty" ] || { echo "FAIL run.sh differs from plain vale when TL_RELAY_VALE_VOCAB is empty"; fail=1; }
printf 'leverages\n' > "$HOMETMP/vocab.txt"
withhome=$(TL_RELAY_VALE_VOCAB="$HOMETMP/vocab.txt" sh "$DIR/run.sh" --no-exit "$DIR/fixtures/dirty.md")
printf '%s' "$plain" | grep -q "'leverages'" || { echo "FAIL dirty.md does not flag leverage without the extra vocabulary"; fail=1; }
printf '%s' "$withhome" | grep -q "'leverages'" && { echo "FAIL run.sh still flags a word in the extra vocabulary"; fail=1; }
homejson=$(TL_RELAY_VALE_VOCAB="$HOMETMP/vocab.txt" sh "$DIR/run.sh" --no-exit --output=JSON "$DIR/fixtures/dirty.md")
while IFS= read -r rule; do
  [ -n "$rule" ] && [ "$rule" != "TlRelay.ContextWords" ] || continue
  printf '%s' "$homejson" | grep -q "\"Check\": \"$rule\"" || { echo "FAIL $rule did not fire through run.sh with an extra vocabulary"; fail=1; }
done < "$DIR/fixtures/expected-rules.txt"
TL_RELAY_VALE_VOCAB="$HOMETMP/vocab.txt" sh "$DIR/run.sh" "$DIR/fixtures/dirty.md" >/dev/null 2>&1 && { echo "FAIL run.sh exited 0 on dirty.md with an extra vocabulary"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS"
exit "$fail"
