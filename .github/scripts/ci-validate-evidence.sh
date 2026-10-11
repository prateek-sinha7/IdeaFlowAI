#!/usr/bin/env bash
# Validate the evaluator's aggregate manifest before `ci-required` is published.
#
# The point is that nothing downstream can upgrade a red evaluation. The previous
# finalizer parsed this manifest, checked that `outcome` was one of "success" or
# "failure", and then proceeded either way — while also hardcoding
# `ci_evidence_outcome=success` with a "for now" comment. So a failed evaluator
# still reached the publisher, and the publisher's verdict depended only on
# whether its own later steps happened to succeed, not on the evaluation.
#
# This script is the whole gate now: the manifest must exist, the evaluator run
# must have concluded success, and the manifest must pass
# backend/tools/ci/manifest_validation.py — schema-valid, for the attested SHA,
# a strict `success` with no advisory downgrade, only `success` verdicts, and
# every required signal accounted for exactly once (as a verdict in
# `signal_states`, or path-filtered on a pull request in `policy_filtered`,
# F-15). Anything else exits non-zero and the status goes red.
#
# The manifest rules used to be a python heredoc here. They moved into a
# stdlib-only, unit-tested module (tests/unit/tools/ci/test_manifest_validation.py)
# that this script runs with the runner's system python3 from the same trusted
# default-branch checkout as this file.
#
# Inputs (environment):
#   EXPECTED_SHA          - the attested revision
#   EVALUATOR_CONCLUSION  - github.event.workflow_run.conclusion
# Usage: ci-validate-evidence.sh <attestation-dir>
set -euo pipefail

dir="${1:?usage: ci-validate-evidence.sh <attestation-dir>}"
: "${EXPECTED_SHA:?EXPECTED_SHA must be set}"
: "${EVALUATOR_CONCLUSION:?EVALUATOR_CONCLUSION must be set}"

manifest="${dir}/ci-evidence-manifest.json"

if [[ ! -s "${manifest}" ]]; then
  echo "::error::the evaluator produced no aggregate manifest at ${manifest}."
  echo "::error::An absent manifest is a failed evaluation, not a pass."
  exit 1
fi

# The source workflow's own conclusion must be success. A cancelled or failed
# evaluator run has no complete evidence to finalize.
if [[ "${EVALUATOR_CONCLUSION}" != "success" ]]; then
  echo "::error::the evaluator run concluded '${EVALUATOR_CONCLUSION}'."
  echo "::error::A non-successful evaluation cannot be finalized as green."
  exit 1
fi

python3 "$(git rev-parse --show-toplevel)/backend/tools/ci/manifest_validation.py" "${manifest}" "${EXPECTED_SHA}"
