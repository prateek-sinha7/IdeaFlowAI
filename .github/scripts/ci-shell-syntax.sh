#!/usr/bin/env bash
# Parse-check every tracked shell script.
#
# Scope comes from `git ls-files`, not a hand-written directory list, so a script
# added in a new location is covered automatically instead of silently escaping
# the check.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

failed=()
count=0

while IFS= read -r -d '' script; do
  count=$((count + 1))
  if ! bash -n "${script}"; then
    failed+=("${script}")
  fi
done < <(git ls-files -z '*.sh')

echo "Parse-checked ${count} shell script(s)."

if ((${#failed[@]} > 0)); then
  echo "::error::bash -n failed for: ${failed[*]}"
  exit 1
fi
