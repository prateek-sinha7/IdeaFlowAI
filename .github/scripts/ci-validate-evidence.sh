#!/usr/bin/env bash
# Validate the evaluator's aggregate manifest before Sonar is allowed to run.
#
# The point is that Sonar cannot upgrade a red evaluation. The previous finalizer
# parsed this manifest, checked that `outcome` was one of "success" or "failure",
# and then proceeded either way — while also hardcoding
# `ci_evidence_outcome=success` with a "for now" comment. So a failed evaluator
# still reached the publisher, and the publisher's verdict depended only on
# Sonar.
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
  echo "::error::Sonar cannot upgrade a non-successful evaluation."
  exit 1
fi

python3 - "${manifest}" "${EXPECTED_SHA}" <<'PY'
import json
import sys

manifest_path, expected_sha = sys.argv[1], sys.argv[2]

with open(manifest_path, encoding="utf-8") as handle:
    manifest = json.load(handle)

problems = []

for field in ("schema_version", "producer", "evaluation_sha", "outcome"):
    if field not in manifest:
        problems.append(f"missing required field '{field}'")

if manifest.get("schema_version") != 1:
    problems.append(f"unsupported schema_version {manifest.get('schema_version')!r}")

if manifest.get("producer") != "ci-evidence":
    problems.append(f"unexpected producer {manifest.get('producer')!r}")

if manifest.get("evaluation_sha") != expected_sha:
    problems.append(
        f"manifest is for {manifest.get('evaluation_sha')!r}, "
        f"expected {expected_sha!r} (stale evidence)"
    )

# This is the check whose absence let Sonar decide everything on its own.
if manifest.get("outcome") != "success":
    problems.append(
        f"evaluator aggregate outcome is {manifest.get('outcome')!r}; "
        "a failed evaluation cannot be finalized as green"
    )

states = manifest.get("signal_states") or {}
non_success = sorted(
    name for name, state in states.items() if state != "success"
)
for name in non_success:
    problems.append(f"signal {name} is {states[name]}")

if problems:
    for problem in problems:
        print(f"::error::{problem}")
    raise SystemExit(1)

print(
    f"Evaluator evidence accepted: {len(states)} signal(s) succeeded for "
    f"{expected_sha}."
)
PY
