#!/usr/bin/env bash
# Conventional-commit gate (pre-commit commit-msg stage). Adopted from
# gridwork-core claude/hooks (lean slice — just the commit-lint).
set -euo pipefail
first="$(head -1 "$1")"
# Allow merge/revert/fixup machinery through untouched.
case "$first" in
  Merge*|Revert*|"fixup! "*|"squash! "*) exit 0 ;;
esac
if echo "$first" | grep -qE '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore)(\([a-z0-9 ._/-]+\))?!?: .+'; then
  exit 0
fi
echo "commit-lint: first line must be a Conventional Commit (feat|fix|docs|style|refactor|perf|test|build|ci|chore). Got:" >&2
echo "  $first" >&2
exit 1
