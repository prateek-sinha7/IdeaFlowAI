#!/usr/bin/env bash
# Validate every workflow file with actionlint.
#
# Invoked from backend/ by run_checks.py, so it resolves the repository root
# itself rather than relying on the caller's working directory.
#
# `-shellcheck=` and `-pyflakes=` disable actionlint's bundled linters: the
# shell in workflows is checked by the dedicated shellcheck signal, and keeping
# them separate means a shell finding is attributed to the shell verdict rather
# than to the workflow-schema verdict.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

shopt -s nullglob
workflows=(.github/workflows/*.yml .github/workflows/*.yaml)
shopt -u nullglob

if ((${#workflows[@]} == 0)); then
  echo "::error::no workflow files found under .github/workflows"
  exit 1
fi

echo "Validating ${#workflows[@]} workflow file(s)."
actionlint -color -shellcheck= -pyflakes= "${workflows[@]}"
echo "actionlint found no problems."
