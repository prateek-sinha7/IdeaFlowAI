#!/usr/bin/env bash
# Blocking ShellCheck analysis over every tracked shell script.
#
# Warning severity is BLOCKING. The previous pipeline ran this with `|| true`
# and `continue-on-error: true`, which made the signal decorative. If a finding
# is genuinely not applicable, silence it at the line with a justified
# `# shellcheck disable=SCxxxx` comment so the exception is reviewable, rather
# than disabling the whole command.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

mapfile -d '' -t scripts < <(git ls-files -z '*.sh')

if ((${#scripts[@]} == 0)); then
  echo "::error::no tracked shell scripts found; the scope is wrong"
  exit 1
fi

echo "Analysing ${#scripts[@]} shell script(s) at warning severity."
shellcheck --severity=warning --shell=bash --external-sources "${scripts[@]}"
echo "ShellCheck found no problems at warning severity or above."
