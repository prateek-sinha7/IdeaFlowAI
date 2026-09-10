#!/usr/bin/env bash
# Scan one locally built image with BOTH Trivy and Grype and require zero
# High/Critical findings from each.
#
# Both engines always run, even when the first already found something: two
# scanners disagree often enough that only having the first engine's answer is
# an incomplete picture. Their exit codes are collected and the script fails
# afterwards if either verdict is red. That is evidence collection past a
# failure, not a waiver.
#
# Deliberately absent: --ignore-unfixed, --only-fixed, --ignorefile. Fix
# availability is a remediation detail, not a risk classification.
#
# Inputs (environment): IMAGE_REF, COMPONENT
# Usage: ci-image-scan.sh <evidence-dir>
set -euo pipefail

evidence_dir="${1:?usage: ci-image-scan.sh <evidence-dir>}"
: "${IMAGE_REF:?IMAGE_REF must be set}"
: "${COMPONENT:?COMPONENT must be set}"

mkdir -p "${evidence_dir}"
evidence_abs="$(cd "${evidence_dir}" && pwd)"

trivy_report="${evidence_abs}/trivy-${COMPONENT}-report.json"
grype_report="${evidence_abs}/grype-${COMPONENT}-report.json"

# Resolve the tag to an immutable digest so both engines provably scanned the
# same bytes.
image_id="$(docker image inspect --format '{{.Id}}' "${IMAGE_REF}")"
echo "Scanning ${IMAGE_REF} (${image_id})"
echo "${image_id}" >"${evidence_abs}/image-${COMPONENT}-id.txt"

# Report production only; neither exit code is the verdict.
trivy image --format json --output "${trivy_report}" "${IMAGE_REF}" || true
grype "${IMAGE_REF}" --output json --file "${grype_report}" || true

overall=0

cd "${GITHUB_WORKSPACE:-.}/backend"

for engine in trivy grype; do
  case "${engine}" in
    trivy) scanner_flag="trivy-image"; report="${trivy_report}" ;;
    grype) scanner_flag="grype";       report="${grype_report}" ;;
  esac

  echo "::group::${engine} verdict for ${COMPONENT}"
  if ! uv run --frozen python -m tools.ci.ci_gate scan-gate \
      --scanner "${scanner_flag}" \
      --report "${report}" \
      --producer "container-scan[${COMPONENT}]/${engine}" \
      --out "${report%.json}-verdict.json"; then
    overall=1
  fi
  echo "::endgroup::"
done

if ((overall != 0)); then
  echo "::error::container-scan[${COMPONENT}] failed: at least one engine"
  echo "::error::reported a High/Critical finding."
fi
exit "${overall}"
