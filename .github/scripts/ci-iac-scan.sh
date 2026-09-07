#!/usr/bin/env bash
# Run the Checkov and Trivy-config policy gates over the Terraform tree.
#
# Both scanners always run and both verdicts are computed; the script exits
# non-zero afterwards if either is red. Documented architectural exceptions live
# in ci/checkov.yaml and are reviewed there. Those exceptions may never contain
# a CVE or GHSA identifier: an IaC policy decision is not a software
# vulnerability waiver.
#
# Usage: ci-iac-scan.sh <evidence-dir>
set -euo pipefail

evidence_dir="${1:?usage: ci-iac-scan.sh <evidence-dir>}"
mkdir -p "${evidence_dir}"
evidence_abs="$(cd "${evidence_dir}" && pwd)"

checkov_report="${evidence_abs}/checkov-report.json"
trivy_config_report="${evidence_abs}/trivy-config-report.json"

# Refuse to run if a software-vulnerability ID has been smuggled into the IaC
# exception file.
if grep -Eiq '(CVE-[0-9]{4}-[0-9]+|GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4})' \
   ci/checkov.yaml 2>/dev/null; then
  echo "::error::ci/checkov.yaml contains a CVE/GHSA identifier. IaC policy"
  echo "::error::exceptions must not be used to waive software vulnerabilities."
  exit 1
fi

# checkov's version comes from the single pin authority, so there is no second
# copy in this script or in the workflow to drift. It runs in an ISOLATED
# environment because checkov 3.2.x pins boto3==1.34.25, which conflicts with the
# backend's boto3 and would make backend/uv.lock unresolvable.
checkov_version="$(
  cd backend && uv run --frozen python -c \
    'from agents.ci.pin_authority import get_authority; print(get_authority().checkov_version)'
)"
echo "Using checkov==${checkov_version} (from agents/ci/pin_authority.py)"

# Report production only; the gates below are the verdicts.
uv tool run --from "checkov==${checkov_version}" checkov \
  --framework terraform \
  --directory infra/terraform \
  --config-file ci/checkov.yaml \
  --output json \
  --output-file-path "${evidence_abs}" || true
# Checkov writes results_json.json into the directory it is given.
if [[ -f "${evidence_abs}/results_json.json" ]]; then
  mv "${evidence_abs}/results_json.json" "${checkov_report}"
fi

trivy config --format json --output "${trivy_config_report}" infra/terraform || true

overall=0
cd "${GITHUB_WORKSPACE:-.}/backend"

echo "::group::Checkov verdict"
if ! uv run --frozen python -m agents.ci.ci_gate scan-gate \
    --scanner checkov \
    --report "${checkov_report}" \
    --producer 'security[iac]/checkov' \
    --out "${checkov_report%.json}-verdict.json"; then
  overall=1
fi
echo "::endgroup::"

echo "::group::Trivy config verdict"
if ! uv run --frozen python -m agents.ci.ci_gate scan-gate \
    --scanner trivy-config \
    --report "${trivy_config_report}" \
    --producer 'security[iac]/trivy-config' \
    --out "${trivy_config_report%.json}-verdict.json"; then
  overall=1
fi
echo "::endgroup::"

exit "${overall}"
