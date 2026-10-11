#!/usr/bin/env bash
# Scan frontend/package-lock.json with Trivy and require zero High/Critical
# findings after the reviewed exceptions in backend/tools/ci/scan_accepts.py.
#
# WHY A LOCKFILE SCAN AS WELL AS THE IMAGE SCAN
# The frontend image is a Next.js `output: "standalone"` build. Next compiles
# dependencies into .next/server and .next/static chunks, and only a handful of
# packages (next, react, sharp, ...) survive as node_modules/*/package.json.
# Image scanners identify packages from that installed metadata, so most of the
# frontend's production graph, including everything that runs in users'
# browsers, is invisible to `trivy image` and `grype`. The lockfile is the only
# place that still names those packages. This replaced `npm audit`, so every
# vulnerability verdict now comes from Trivy or Grype.
#
# Trivy excludes devDependencies of package-lock.json by default, which is what
# ships; build tooling that never reaches the image or the browser is not gated.
#
# Inputs (environment):
#   SCAN_GATE_MODE   block (default) | warn. In warn mode findings, expired/stale
#                    exceptions and unusable reports only warn.
#
# TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
# In future this must be changed back to BLOCKING, and the outstanding High/Critical
# vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
# Usage: ci-lockfile-scan.sh <evidence-dir>
set -euo pipefail

evidence_dir="${1:?usage: ci-lockfile-scan.sh <evidence-dir>}"
lockfile="${GITHUB_WORKSPACE:-.}/frontend/package-lock.json"
scan_gate_mode="${SCAN_GATE_MODE:-block}"

case "${scan_gate_mode}" in
  block | warn) ;;
  *)
    echo "::error::SCAN_GATE_MODE must be block or warn, got '${scan_gate_mode}'"
    exit 2
    ;;
esac

# A missing lockfile is a repository-integrity failure, not a vulnerability
# verdict, so it stays blocking even in warn mode.
if [[ ! -s "${lockfile}" ]]; then
  echo "::error::${lockfile} is missing or empty; nothing to scan is a failure."
  exit 1
fi

mkdir -p "${evidence_dir}"
evidence_abs="$(cd "${evidence_dir}" && pwd)"
report="${evidence_abs}/trivy-frontend-lockfile-report.json"

# Report production only; the gate below is the verdict.
trivy fs --scanners vuln --format json --output "${report}" "${lockfile}" || true

overall=0
cd "${GITHUB_WORKSPACE:-.}/backend"

echo "::group::reviewed exceptions for frontend-lockfile"
if ! uv run --frozen python -m tools.ci.scan_accepts \
    --scope frontend-lockfile \
    --trivy "${report}" \
    --out "${evidence_abs}/scan-accepts-frontend-lockfile.json"; then
  # TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
  # In future this must be changed back to BLOCKING, and the outstanding High/Critical
  # vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
  if [[ "${scan_gate_mode}" == "warn" ]]; then
    echo "::warning title=Scan exceptions (advisory, TEMPORARY)::frontend-lockfile: tools.ci.scan_accepts reported a problem (expired/stale exception or unreadable report). Not blocking: SCAN_GATE_MODE=warn."
  else
    overall=1
  fi
fi
echo "::endgroup::"

echo "::group::trivy verdict for frontend-lockfile"
if ! uv run --frozen python -m tools.ci.ci_gate scan-gate \
    --scanner trivy-fs \
    --report "${report%.json}-gated.json" \
    --producer 'container-scan[frontend]/trivy-lockfile' \
    --mode "${scan_gate_mode}" \
    --out "${report%.json}-verdict.json"; then
  overall=1
fi
echo "::endgroup::"

if ((overall == 0)) && [[ "${scan_gate_mode}" == "warn" ]]; then
  echo "::notice::frontend-lockfile scan ran in advisory mode (TEMPORARY); findings, if any, are in the warnings, the step summary and *-verdict.json."
fi

exit "${overall}"
