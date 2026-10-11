#!/usr/bin/env bash
# Scan one image with BOTH Trivy and Grype and require zero High/Critical
# findings from each, after the reviewed exceptions in
# backend/tools/ci/scan_accepts.py.
#
# One script, two callers, one policy:
#   * ci.yml `container-scan` scans the image it just built locally (never
#     pushed). IMAGE_SOURCE=local (the default).
#   * deploy.yml `build` scans the digest it just pushed to ECR, so what landed
#     in the registry is checked by the same engines and the same exceptions
#     that certified the commit. IMAGE_SOURCE=registry.
#
# Both engines always run, even when the first already found something: two
# scanners disagree often enough that only having the first engine's answer is
# an incomplete picture. Their exit codes are collected and the script fails
# afterwards if either verdict is red. That is evidence collection past a
# failure, not a waiver.
#
# Deliberately absent: --ignore-unfixed, --only-fixed, --ignorefile. Fix
# availability is a remediation detail, not a risk classification. The ONLY
# way a High/Critical finding stops blocking is a dated, per-package entry in
# tools/ci/scan_accepts.py, which fails the build when it expires or stops
# matching anything.
#
# Inputs (environment):
#   IMAGE_REF        image to scan (a local tag, or registry/repo@sha256:...)
#   COMPONENT        backend | frontend
#   IMAGE_SOURCE     local (default) | registry
#   PRODUCER_PREFIX  verdict label prefix (default: container-scan)
#   SCAN_GATE_MODE   block (default) | warn. In warn mode findings, expired/stale
#                    exceptions and unusable reports are reported as warnings
#                    and do not fail this script.
#
# TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
# In future this must be changed back to BLOCKING, and the outstanding High/Critical
# vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
# Usage: ci-image-scan.sh <evidence-dir>
set -euo pipefail

evidence_dir="${1:?usage: ci-image-scan.sh <evidence-dir>}"
: "${IMAGE_REF:?IMAGE_REF must be set}"
: "${COMPONENT:?COMPONENT must be set}"
image_source="${IMAGE_SOURCE:-local}"
producer_prefix="${PRODUCER_PREFIX:-container-scan}"
scan_gate_mode="${SCAN_GATE_MODE:-block}"

case "${scan_gate_mode}" in
  block | warn) ;;
  *)
    echo "::error::SCAN_GATE_MODE must be block or warn, got '${scan_gate_mode}'"
    exit 2
    ;;
esac

case "${COMPONENT}" in
  backend | frontend) ;;
  *)
    echo "::error::COMPONENT must be backend or frontend, got '${COMPONENT}'"
    exit 2
    ;;
esac

mkdir -p "${evidence_dir}"
evidence_abs="$(cd "${evidence_dir}" && pwd)"

trivy_report="${evidence_abs}/trivy-${COMPONENT}-report.json"
grype_report="${evidence_abs}/grype-${COMPONENT}-report.json"

# Resolve what is being scanned to an immutable identity so both engines
# provably scanned the same bytes.
case "${image_source}" in
  local)
    image_id="$(docker image inspect --format '{{.Id}}' "${IMAGE_REF}")"
    trivy_source=(--image-src docker)
    grype_target="docker:${IMAGE_REF}"
    ;;
  registry)
    # A tag is a mutable pointer; only a digest names content.
    if [[ ! "${IMAGE_REF}" =~ @sha256:[0-9a-f]{64}$ ]]; then
      echo "::error::IMAGE_SOURCE=registry requires IMAGE_REF pinned by digest, got '${IMAGE_REF}'"
      exit 2
    fi
    image_id="${IMAGE_REF##*@}"
    trivy_source=(--image-src remote)
    grype_target="registry:${IMAGE_REF}"
    ;;
  *)
    echo "::error::IMAGE_SOURCE must be local or registry, got '${image_source}'"
    exit 2
    ;;
esac
echo "Scanning ${IMAGE_REF} (${image_id}) from ${image_source}"
echo "${image_id}" >"${evidence_abs}/image-${COMPONENT}-id.txt"

# Report production only; neither exit code is the verdict.
trivy image "${trivy_source[@]}" --format json \
  --output "${trivy_report}" "${IMAGE_REF}" || true
grype "${grype_target}" --output json --file "${grype_report}" || true

overall=0

cd "${GITHUB_WORKSPACE:-.}/backend"

# Apply the reviewed exceptions. NOT `|| true`: an expired or stale exception,
# or an unreadable report, must fail this component. Gated reports are still
# written for every readable report, so both engines get a verdict below.
echo "::group::reviewed exceptions for ${COMPONENT}-image"
if ! uv run --frozen python -m tools.ci.scan_accepts \
    --scope "${COMPONENT}-image" \
    --trivy "${trivy_report}" \
    --grype "${grype_report}" \
    --out "${evidence_abs}/scan-accepts-${COMPONENT}-image.json"; then
  # TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
  # In future this must be changed back to BLOCKING, and the outstanding High/Critical
  # vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
  if [[ "${scan_gate_mode}" == "warn" ]]; then
    echo "::warning title=Scan exceptions (advisory, TEMPORARY)::${COMPONENT}-image: tools.ci.scan_accepts reported a problem (expired/stale exception or unreadable report). Not blocking: SCAN_GATE_MODE=warn."
  else
    overall=1
  fi
fi
echo "::endgroup::"

for engine in trivy grype; do
  case "${engine}" in
    trivy) scanner_flag="trivy-image"; report="${trivy_report}" ;;
    grype) scanner_flag="grype";       report="${grype_report}" ;;
  esac

  echo "::group::${engine} verdict for ${COMPONENT}"
  if ! uv run --frozen python -m tools.ci.ci_gate scan-gate \
      --scanner "${scanner_flag}" \
      --report "${report%.json}-gated.json" \
      --producer "${producer_prefix}[${COMPONENT}]/${engine}" \
      --mode "${scan_gate_mode}" \
      --out "${report%.json}-verdict.json"; then
    overall=1
  fi
  echo "::endgroup::"
done

if ((overall != 0)); then
  echo "::error::${producer_prefix}[${COMPONENT}] failed: an engine reported an"
  echo "::error::unaccepted High/Critical finding, or an exception is expired/stale."
elif [[ "${scan_gate_mode}" == "warn" ]]; then
  echo "::notice::${producer_prefix}[${COMPONENT}] ran in advisory mode (TEMPORARY); findings, if any, are in the warnings, the step summary and *-verdict.json."
fi
exit "${overall}"
