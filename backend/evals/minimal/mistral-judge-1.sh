#!/usr/bin/env bash
# mistral-judge-1.sh — rejudge run 1 (fraud_review) with the mistral judge.
#
#   ./mistral-judge-1.sh
#
# Runs from anywhere; rejudge.sh cds to backend/ itself.
#
# Banking review queue. THE ONE TO READ FIRST: its validate.html throws `Identifier 'priorTxns' has already been declared`, so the page renders blank — and the Mistral judge scored that stage 96.8, its highest. Whether a judge catches a file it cannot execute is the whole question here.
#
# Judge tokens only — the artifacts are a clone of
# 260803-160333-prototype_aws_1_fraud_review-mistraljudge
# and are NOT re-dispatched. Its twin is aws-judge-1.sh,
# pointed at the same artifacts with the other judge.
#
# Run these ONE AT A TIME. Parallel terminals share one Mistral account and
# that is what produced the 429 last time — dispatch provider is irrelevant to
# it, since the judge is Mistral-hosted either way unless overridden.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rejudge.sh" \
  260803-160333-prototype_aws_1_fraud_review-mistraljudge \
  mistral "$@"
