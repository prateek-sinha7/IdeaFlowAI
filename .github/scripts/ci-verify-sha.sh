#!/usr/bin/env bash
# Verify the checkout is the exact revision this evaluation claims to judge, and
# export it for later steps.
#
# Every producer records its verdict against this value. If a job silently
# checked out a merge commit or a newer head, its evidence would be attributed
# to the wrong revision and a stale result could satisfy a current required
# status. Failing here is the cheapest place to catch that.
#
# Inputs (environment):
#   EXPECTED_SHA - the revision the workflow intends to evaluate.
# Outputs:
#   $GITHUB_ENV : EVALUATION_SHA
#   $GITHUB_OUTPUT : evaluation_sha
set -euo pipefail

if [[ -z "${EXPECTED_SHA:-}" ]]; then
  echo "::error::EXPECTED_SHA is not set; cannot verify the evaluated revision."
  exit 1
fi

if [[ ! "${EXPECTED_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "::error::EXPECTED_SHA '${EXPECTED_SHA}' is not a full 40-character SHA."
  exit 1
fi

actual_sha="$(git rev-parse HEAD)"
if [[ "${actual_sha}" != "${EXPECTED_SHA}" ]]; then
  echo "::error::Checked out ${actual_sha} but this evaluation is for ${EXPECTED_SHA}."
  exit 1
fi

echo "EVALUATION_SHA=${actual_sha}" >>"${GITHUB_ENV}"
echo "evaluation_sha=${actual_sha}" >>"${GITHUB_OUTPUT}"
echo "Evaluating exact revision ${actual_sha}"
