#!/usr/bin/env bash
# Record a digest of every characterization golden before the test run (INV-3).
#
# Usage: ci-golden-digest.sh <output-file>
set -euo pipefail

out="${1:?usage: ci-golden-digest.sh <output-file>}"
golden_dir="backend/tests/agents/characterization/golden"

mkdir -p "$(dirname "${out}")"

if [[ ! -d "${golden_dir}" ]]; then
  echo "::error::characterization golden directory is missing: ${golden_dir}"
  exit 1
fi

# NUL-delimited so a path containing whitespace cannot split a record.
find "${golden_dir}" -type f -print0 \
  | sort -z \
  | xargs -0 --no-run-if-empty sha256sum \
  >"${out}"

echo "Recorded $(wc -l <"${out}") golden file digest(s)."
