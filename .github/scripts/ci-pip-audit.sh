#!/usr/bin/env bash
# Audit the installed frozen backend graph and block on any High/Critical finding.
#
# pip-audit's own exit code is deliberately NOT the verdict: it exits non-zero
# for a vulnerability and also for a network problem, and it reports no severity
# at all. The verdict comes from `ci_gate scan-gate`, which parses the report,
# classifies conservatively, and fails on any blocking finding regardless of
# whether a fix has been published. There is no ignore list.
#
# Usage: ci-pip-audit.sh <report-path>
set -euo pipefail

report="${1:?usage: ci-pip-audit.sh <report-path>}"
mkdir -p "$(dirname "${report}")"
report_abs="$(cd "$(dirname "${report}")" && pwd)/$(basename "${report}")"

# `|| true` here guards ONLY the report-producing step. pip-audit exits 1 when
# it finds something, and we still need the JSON it wrote. The gate below is
# what decides pass or fail, and it has no escape hatch.
(
  cd backend
  uv run --frozen pip-audit --desc --format json --output "${report_abs}" || true
)

cd backend
uv run --frozen python -m agents.ci.ci_gate scan-gate \
  --scanner pip-audit \
  --report "${report_abs}" \
  --producer 'security[backend-deps]' \
  --out "${report_abs%.json}-verdict.json"
