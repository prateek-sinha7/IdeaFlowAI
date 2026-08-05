#!/usr/bin/env bash
# judge.sh — check + score + report a run that is ALREADY on disk, by folder
# name. Spends judge tokens only; nothing is re-dispatched, so the artifacts
# under test are exactly the bytes that were produced.
#
#   ./judge.sh <RUN_ID> [--stage NAME] [--advise] [--concurrency N]
#              [--judge-provider P] [--judge-model M]
#
#   ./judge.sh 260804-154746-prototype_smoke --advise
#   ./judge.sh 260804-154746-prototype_smoke --stage build       # just one stage
#   ./judge.sh .runs/260804-154746-prototype_smoke               # a path works too
#
# The run id is the last line ./eval.sh prints, and the folder name under
# evals/minimal/.runs/. Any stage already dispatched can be judged, including
# stages from a chain that stopped early — judge what you have, dispatch the
# rest later.
#
# BEFORE IT SPENDS, it verifies the judge will actually receive the evidence
# each rubric declares in `upstream:` — present, non-empty, and byte-matching
# the stage that produced it. If that fails it prints why, spends nothing, and
# stops: a judge with no evidence does not error, it scores the missing
# artifact as the artifact's fault and returns a plausible number.
#
# SECOND OPINION on the same bytes — clone first, so the two verdicts sit in
# separate folders over identical artifacts:
#   NEW=$(python3.11 -m evals.minimal.cli clone <RUN_ID> --label awsjudge)
#   ./judge.sh "$NEW" --judge-provider bedrock --advise
#
# Run one at a time: parallel terminals share one Mistral account, and that is
# what produces 429s — the dispatch provider is irrelevant, since the judge is
# Mistral-hosted either way unless overridden.
set -euo pipefail
export PYTHONUNBUFFERED=1

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <RUN_ID> [--stage NAME] [--advise] [--concurrency N]" >&2
  echo "       run ids are the folder names under evals/minimal/.runs/" >&2
  exit 1
fi

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ -z "${MISTRAL_API_KEY:-}" ]]; then
  # A missing key gives a 401 on every stage, which reads like a quota problem
  # and is really an unexported env var. Fail with that named up front.
  echo "MISTRAL_API_KEY is not exported in this shell — run: source ~/.zshrc" >&2
  exit 1
fi

exec python3.11 -m evals.minimal.cli judge "$@"
