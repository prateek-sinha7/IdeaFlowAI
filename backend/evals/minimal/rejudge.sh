#!/usr/bin/env bash
# rejudge.sh — score ONE already-dispatched run with a chosen judge provider.
# Spends judge tokens only; nothing is re-dispatched, so the artifacts under
# test are byte-identical to the run they were cloned from.
#
# You normally invoke one of the wrappers (aws-judge-1.sh, mistral-judge-2.sh,
# …) rather than this directly. Direct form:
#
#   ./rejudge.sh <RUN_ID> <PROVIDER> [extra cli args…]
#   DRY_RUN=1 ./rejudge.sh <RUN_ID> bedrock      # print the command, run nothing
#
# LOCATION-INDEPENDENT: `python3.11 -m evals.minimal.cli` resolves `evals` as a
# package, which only works with cwd = backend/. Running it from this folder
# fails with `ModuleNotFoundError: No module named 'evals'` — the one error
# that looks like a broken install and is really a wrong directory. So this
# script finds backend/ from its own path and cds there itself.
set -euo pipefail

export PYTHONUNBUFFERED=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "$HERE/../.." && pwd)"
cd "$BACKEND_ROOT"

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <RUN_ID> <PROVIDER: mistral|bedrock> [extra cli args…]" >&2
  exit 1
fi

RUN_ID="$1"
PROVIDER="$2"
shift 2

if [[ ! -d "evals/minimal/.runs/$RUN_ID" ]]; then
  echo "no such run: evals/minimal/.runs/$RUN_ID" >&2
  echo "list them with: ls evals/minimal/.runs" >&2
  exit 1
fi

# The judge is Mistral-hosted for BOTH providers' runs unless overridden — a
# missing key gives a 401 on every stage, which reads like a quota problem and
# is really an unexported env var. Fail with that named up front instead.
if [[ "$PROVIDER" == "mistral" && -z "${MISTRAL_API_KEY:-}" ]]; then
  echo "MISTRAL_API_KEY is not exported in this shell — run: source ~/.zshrc" >&2
  exit 1
fi

echo "==> rejudge: $RUN_ID via $PROVIDER (judge tokens only — no dispatch)" >&2

CMD=(python3.11 -m evals.minimal.cli score "$RUN_ID"
     --judge-provider "$PROVIDER" --advise "$@")

if [[ -n "${DRY_RUN:-}" ]]; then
  echo "DRY_RUN: (cd $BACKEND_ROOT && ${CMD[*]})"
  exit 0
fi

"${CMD[@]}"

# Rebuilt here rather than once at the end, so the report is never stale if you
# open it between scripts — same reason eval.sh rebuilds per stage.
echo "==> report: rebuilding report.html" >&2
python3.11 -m evals.minimal.cli report
