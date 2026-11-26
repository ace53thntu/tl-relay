#!/bin/sh
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HOME_VOCAB="${TL_RELAY_VALE_VOCAB:-}"

command -v vale >/dev/null || { echo "vale is not on PATH. See https://docs.vale.sh/topics/installation" >&2; exit 127; }

if [ -z "$HOME_VOCAB" ] || [ ! -f "$HOME_VOCAB" ]; then
  exec vale --config "$DIR/.vale.ini" "$@"
fi

TMP=$(mktemp -d) || exit 1
trap 'rm -rf "$TMP"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
{
  mkdir -p "$TMP/styles/config/vocabularies/Home" &&
  ln -s "$DIR/styles/Google" "$TMP/styles/Google" &&
  ln -s "$DIR/styles/TlRelay" "$TMP/styles/TlRelay" &&
  ln -s "$DIR/styles/config/vocabularies/TlRelay" "$TMP/styles/config/vocabularies/TlRelay" &&
  cp "$HOME_VOCAB" "$TMP/styles/config/vocabularies/Home/accept.txt" &&
  sed -e "s|^StylesPath = .*|StylesPath = $TMP/styles|" -e 's|^Vocab = .*|Vocab = TlRelay, Home|' "$DIR/.vale.ini" > "$TMP/.vale.ini"
} || exit 1
vale --config "$TMP/.vale.ini" "$@"
