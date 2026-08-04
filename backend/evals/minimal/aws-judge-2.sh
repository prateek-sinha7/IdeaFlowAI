#!/usr/bin/env bash
# aws-judge-2.sh — rejudge run 2 (reservations) with the bedrock judge.
#
#   ./aws-judge-2.sh
#
# Runs from anywhere; rejudge.sh cds to backend/ itself.
#
# Hospitality time grid. Clean run — checks 100/100 at build and validate, so judge disagreement here is about quality, not about a missed defect.
#
# Judge tokens only — the artifacts are a clone of
# 260803-155235-prototype_aws_2_reservations
# and are NOT re-dispatched. Its twin is mistral-judge-2.sh,
# pointed at the same artifacts with the other judge.
#
# Run these ONE AT A TIME. Parallel terminals share one Mistral account and
# that is what produced the 429 last time — dispatch provider is irrelevant to
# it, since the judge is Mistral-hosted either way unless overridden.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rejudge.sh" \
  260803-155235-prototype_aws_2_reservations-awsjudge \
  bedrock "$@"
