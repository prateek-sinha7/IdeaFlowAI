#!/usr/bin/env bash
# Audit the installed frontend graph and block on any High/Critical finding.
#
# There is no MAX_HIGH baseline. `npm audit` exits non-zero when it finds
# anything, so its exit code is captured but not used as the verdict; the
# verdict is `ci_gate scan-gate`'s, which fails on a resolved High or Critical
# finding whether or not a non-breaking fix exists.
#
# KNOWN RESIDUALS: two image-size advisories (GHSA-w3rx-r6r6-pgpr and
# GHSA-5p2g-fcmc-qvqq) are accepted, with per-advisory justifications, in
# backend/tools/ci/npm_audit_accepts.py. They are unfixable upstream — every
# image-size release through 2.0.2, the latest, is affected and the project has
# issues disabled — and they reach us only through the pinned pptxgenjs. npm
# audit has no `--ignore` flag, so unlike ci-pip-audit.sh (which passes
# pip-audit `--ignore-vuln PYSEC-2026-1325`) the accept is applied to the report
# between production and the gate. The gate itself keeps no escape hatch: an
# accept that stops matching FAILS instead of quietly expiring, and an entry is
# dropped only when every advisory behind it is accepted.
#
# Usage: ci-npm-audit.sh <report-path>
set -euo pipefail

report="${1:?usage: ci-npm-audit.sh <report-path>}"
mkdir -p "$(dirname "${report}")"
report_abs="$(cd "$(dirname "${report}")" && pwd)/$(basename "${report}")"
gated_abs="${report_abs%.json}-gated.json"

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

# Apply the reviewed accepts. NOT `|| true`: a stale accept, an unreadable
# report, or a report whose shape changed all exit non-zero here, and that has
# to fail the job rather than fall through to a gate reading a stale file. Both
# the raw and the gated report are uploaded as evidence, so the accepts stay
# auditable after the fact.
uv run --frozen python -m tools.ci.npm_audit_accepts \
  --report "${report_abs}" \
  --out "${gated_abs}"

uv run --frozen python -m tools.ci.ci_gate scan-gate \
  --scanner npm \
  --report "${gated_abs}" \
  --producer 'security[frontend-deps]' \
  --out "${report_abs%.json}-verdict.json"
