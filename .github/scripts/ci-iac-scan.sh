#!/usr/bin/env bash
# Run the Checkov and Trivy-config policy gates over the Terraform tree.
#
# Both scanners always run and both verdicts are computed; the script exits
# non-zero afterwards if either is red. Documented architectural exceptions live
# in ci/checkov.yaml (checkov) and ci/trivyignore (trivy) and are reviewed
# there. Those exceptions may never contain a CVE or GHSA identifier: an IaC
# policy decision is not a software vulnerability waiver.
#
# Usage: ci-iac-scan.sh <evidence-dir>
set -euo pipefail

evidence_dir="${1:?usage: ci-iac-scan.sh <evidence-dir>}"
mkdir -p "${evidence_dir}"
evidence_abs="$(cd "${evidence_dir}" && pwd)"

checkov_report="${evidence_abs}/checkov-report.json"
trivy_config_report="${evidence_abs}/trivy-config-report.json"

# Refuse to run if a software-vulnerability ID has been smuggled into either IaC
# exception file. ci/trivyignore is checked too now that it is actually passed to
# trivy below: an unread file needed no guard, a read one does.
for exception_file in ci/checkov.yaml ci/trivyignore; do
  if grep -Eiq '(CVE-[0-9]{4}-[0-9]+|GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4})' \
     "${exception_file}" 2>/dev/null; then
    echo "::error::${exception_file} contains a CVE/GHSA identifier. IaC policy"
    echo "::error::exceptions must not be used to waive software vulnerabilities."
    exit 1
  fi
done

# checkov's version comes from the single pin authority, so there is no second
# copy in this script or in the workflow to drift. It runs in an ISOLATED
# environment because checkov 3.2.x pins boto3==1.34.25, which conflicts with the
# backend's boto3 and would make backend/uv.lock unresolvable.
checkov_version="$(
  cd backend && uv run --frozen python -c \
    'from tools.ci.pin_authority import get_authority; print(get_authority().checkov_version)'
)"
echo "Using checkov==${checkov_version} (from tools/ci/pin_authority.py)"

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

# The ignorefile and the two --skip-dirs are NOT optional decoration; without
# them this gate reported 19 HIGH/CRITICAL findings, none of which was an
# unreviewed risk:
#   * ci/trivyignore carries the reviewed architectural accepts (documented and
#     mirrored in ci/checkov.yaml). Passing no --ignorefile meant trivy loaded
#     no ignore config at all, so the accepts were dead text.
#   * "**/examples/**" — every module ships an illustrative examples/basic root.
#     Trivy walks each one as its own root module and re-reports the module's
#     findings against it, so a single real finding was counted once per
#     example. Examples are never applied to an account.
#   * "**/localstack/**" — the local emulator root deliberately weakens settings
#     that make no sense against LocalStack (ECR image_tag_mutability =
#     "MUTABLE", open egress). It is not deployable infrastructure, and skipping
#     it is what keeps the live AWS-0031 check meaningful for shared/ instead of
#     forcing a blanket ignore of mutable ECR tags.
# Verified against the failing run's own evidence
# (ci-results/trivy-config-report.json): the surviving real findings are exactly
# the accepted IDs in ci/trivyignore, from foundation/ and app/. The
# velocityai-alb root (and modules/alb_internal) were removed, which also
# retired the AWS-0132 accept that only ever matched the ALB access-log bucket.
trivy config \
  --ignorefile ci/trivyignore \
  --skip-dirs "**/examples/**" \
  --skip-dirs "**/localstack/**" \
  --format json --output "${trivy_config_report}" infra/terraform || true

overall=0
cd "${GITHUB_WORKSPACE:-.}/backend"

echo "::group::Checkov verdict"
if ! uv run --frozen python -m tools.ci.ci_gate scan-gate \
    --scanner checkov \
    --report "${checkov_report}" \
    --producer 'security[iac]/checkov' \
    --out "${checkov_report%.json}-verdict.json"; then
  overall=1
fi
echo "::endgroup::"

echo "::group::Trivy config verdict"
if ! uv run --frozen python -m tools.ci.ci_gate scan-gate \
    --scanner trivy-config \
    --report "${trivy_config_report}" \
    --producer 'security[iac]/trivy-config' \
    --out "${trivy_config_report%.json}-verdict.json"; then
  overall=1
fi
echo "::endgroup::"

exit "${overall}"
