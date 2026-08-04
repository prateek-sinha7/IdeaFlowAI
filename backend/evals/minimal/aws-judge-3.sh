#!/usr/bin/env bash
# aws-judge-3.sh — rejudge run 3 (permits) with the bedrock judge.
#
#   ./aws-judge-3.sh
#
# Runs from anywhere; rejudge.sh cds to backend/ itself.
#
# Government staged review. Its build stage never got a Mistral verdict in the original run (429 rate limit from three parallel terminals), so this pass is what completes the Mistral column.
#
# Judge tokens only — the artifacts are a clone of
# 260803-155235-prototype_aws_3_permits
# and are NOT re-dispatched. Its twin is mistral-judge-3.sh,
# pointed at the same artifacts with the other judge.
#
# Run these ONE AT A TIME. Parallel terminals share one Mistral account and
# that is what produced the 429 last time — dispatch provider is irrelevant to
# it, since the judge is Mistral-hosted either way unless overridden.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rejudge.sh" \
  260803-155235-prototype_aws_3_permits-awsjudge \
  bedrock "$@"
