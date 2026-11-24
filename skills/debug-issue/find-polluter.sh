#!/usr/bin/env bash
# Runs test files one at a time and stops at the first one that leaves the
# given file or directory behind.
#
# Usage: ./find-polluter.sh <file_or_dir_to_check> <test_pattern>
#   e.g. ./find-polluter.sh 'packages/engine/.git' 'src/**/*.test.ts'
# Exit: 0 no polluter, 1 polluter found or usage error, 2 target exists before the run.
set -e

print_usage() {
  printf 'Usage: %s <file_to_check> <test_pattern>\n' "$0"
  printf "Example: %s 'packages/engine/.git' 'src/**/*.test.ts'\n" "$0"
}

discover() {
  local TEST_PATTERN="$1"
  find . \( -path "./$TEST_PATTERN" -o -path "./${TEST_PATTERN//\*\*\//}" \) | sort -u
}

count_lines() {
  if [ -z "$1" ]; then
    echo 0
  else
    printf '%s\n' "$1" | wc -l | tr -d '[:space:]'
  fi
}

report_polluter() {
  local culprit="$1" artefact="$2"
  printf '\n🎯 FOUND POLLUTER!\n'
  printf '   Test: %s\n' "$culprit"
  printf '   Created: %s\n\n' "$artefact"
  printf 'Pollution details:\n'
  ls -la "$artefact"
  printf '\nTo investigate:\n'
  printf '  npm test %s    # Run just this test\n' "$culprit"
  printf '  cat %s         # Review test code\n' "$culprit"
}

report_clean() {
  printf '\n✅ No polluter found - all tests clean!\n'
}

if [ "$#" -ne 2 ]; then
  print_usage
  exit 1
fi

artefact="$1"
pattern="$2"

printf '🔍 Searching for test that creates: %s\n' "$artefact"
printf 'Test pattern: %s\n\n' "$pattern"

if [ -e "$artefact" ] || [ -L "$artefact" ]; then
  printf '⚠️  %s already exists before any test runs. Pick a target that is absent before the run.\n' "$artefact"
  exit 2
fi

pattern="${pattern#./}"
candidates="$(discover "$pattern")"
total="$(count_lines "$candidates")"
printf 'Found %s test files\n\n' "$total"

position=0
# The loop word-splits the list: a path with a space becomes several items.
for candidate in $candidates; do
  position=$((position + 1))

  printf '[%s/%s] Testing: %s\n' "$position" "$total" "$candidate"
  npm test "$candidate" >/dev/null 2>&1 || true

  if [ -e "$artefact" ] || [ -L "$artefact" ]; then
    report_polluter "$candidate" "$artefact"
    exit 1
  fi
done

report_clean
exit 0
