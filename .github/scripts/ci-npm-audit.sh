#!/usr/bin/env bash
# Audit the installed frontend graph and block on any High/Critical finding.
#
# There is no MAX_HIGH baseline. `npm audit` exits non-zero when it finds
# anything, so its exit code is captured but not used as the verdict; the
# verdict is `ci_gate scan-gate`'s, which fails on a resolved High or Critical
# finding whether or not a non-breaking fix exists.
#
# Usage: ci-npm-audit.sh <report-path>
set -euo pipefail

report="${1:?usage: ci-npm-audit.sh <report-path>}"
mkdir -p "$(dirname "${report}")"
report_abs="$(cd "$(dirname "${report}")" && pwd)/$(basename "${report}")"

# `|| true` guards only report production; see the note in ci-pip-audit.sh.
(
  cd frontend
  npm audit --json >"${report_abs}" || true
)

if [[ ! -s "${report_abs}" ]]; then
  echo "::error::npm audit produced no report. An absent report is a failed"
  echo "::error::signal, not evidence of zero findings."
  exit 1
fi

cd backend
uv run --frozen python -m agents.ci.ci_gate scan-gate \
  --scanner npm \
  --report "${report_abs}" \
  --producer 'security[frontend-deps]' \
  --out "${report_abs%.json}-verdict.json"
