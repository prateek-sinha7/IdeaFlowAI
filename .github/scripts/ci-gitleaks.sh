#!/usr/bin/env bash
# Scan the full git history for secrets and block on any non-allowlisted finding.
#
# Usage: ci-gitleaks.sh <report-path>
set -euo pipefail

report="${1:?usage: ci-gitleaks.sh <report-path>}"
mkdir -p "$(dirname "${report}")"

# --redact keeps the secret value out of the log and the artifact. The curated
# false-positive allowlist lives in ci/gitleaks.toml and is reviewed there, not
# inline here. Report production only; the gate below is the verdict.
gitleaks detect \
  --redact \
  --no-banner \
  --config ci/gitleaks.toml \
  --gitleaks-ignore-path ci/gitleaksignore \
  --source . \
  --report-format json \
  --report-path "${report}" || true

if [[ ! -f "${report}" ]]; then
  echo "::error::gitleaks produced no report. An absent report is a failed"
  echo "::error::signal, not evidence of zero leaked secrets."
  exit 1
fi

cd backend
uv run --frozen python -m tools.ci.ci_gate scan-gate \
  --scanner gitleaks \
  --report "${GITHUB_WORKSPACE:-..}/${report}" \
  --producer 'security[secrets]' \
  --out "${GITHUB_WORKSPACE:-..}/${report%.json}-verdict.json"
