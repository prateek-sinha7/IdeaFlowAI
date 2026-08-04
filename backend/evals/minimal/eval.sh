#!/usr/bin/env bash
# eval.sh — one command: dispatch, then checks + score (+ advise) + rebuild
# the report for whatever stage(s) that run just touched. Wraps
# evals.minimal.cli; every individual command it calls is still available
# directly (see cli.py).
#
# Usage:
#   ./eval.sh <config> [--stage NAME] [--into RUN_ID] [--repeats N] [--advise] [--concurrency N]
#
# Examples:
#   ./eval.sh configs/small.yaml --advise                  # whole chain, 1 row
#   ./eval.sh configs/small.yaml --stage specify --advise   # one stage; prints RUN_ID
#   ./eval.sh configs/small.yaml --stage plan --into RUN_ID --advise
#   ./eval.sh configs/ten.yaml --advise --concurrency 4     # 10 rows, 4 judges at once
#   ./eval.sh configs/ten_aws.yaml --advise --concurrency 4 # same 10 rows, on AWS Bedrock
#
# PROVIDER: a config may pin its own (`provider: bedrock` in ten_aws.yaml);
# an explicit --provider on the command line still overrides it.
#
# LOCATION-INDEPENDENT: resolves its own directory and runs from `backend/`
# (the CLI is invoked as `python3.11 -m evals.minimal.cli`, which requires cwd
# = backend/) regardless of where you call this script from.
set -euo pipefail

# Unbuffered stdout/stderr from Python — without this, output can sit in a
# block buffer and never reach the terminal until the process exits, which is
# what made a multi-minute run look hung. run.py's own progress lines go to
# stderr already (see run.py::_report), so they show up live either way, but
# this keeps the plain print()s (cli.py, checks.py, judge.py) live too.
export PYTHONUNBUFFERED=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "$HERE/../.." && pwd)"
cd "$BACKEND_ROOT"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <config> [--stage NAME] [--into RUN_ID] [--repeats N] [--advise] [--concurrency N]" >&2
  exit 1
fi

CONFIG="$1"
shift
STAGE=""
ADVISE=""
CONCURRENCY=""

# Pull --stage/--advise/--concurrency out of the passthrough args, so this
# script knows which stage(s) to score/check afterward and what to forward to
# `score`, without re-parsing the CLI's own argparse. --advise and
# --concurrency are stripped from RUN_ARGS below: `cli run` accepts neither,
# only `cli score` does.
ARGS=("$@")
RUN_ARGS=()
SKIP_NEXT=0
for ((i = 0; i < ${#ARGS[@]}; i++)); do
  if [[ $SKIP_NEXT -eq 1 ]]; then SKIP_NEXT=0; continue; fi
  case "${ARGS[$i]}" in
    --stage)
      STAGE="${ARGS[$((i + 1))]}"
      RUN_ARGS+=("${ARGS[$i]}")
      ;;
    --advise)
      ADVISE="--advise"
      ;;
    --concurrency)
      CONCURRENCY="--concurrency ${ARGS[$((i + 1))]}"
      SKIP_NEXT=1
      ;;
    *)
      RUN_ARGS+=("${ARGS[$i]}")
      ;;
  esac
done

echo "==> run: dispatching '$CONFIG'${STAGE:+ (--stage $STAGE)}${RUN_ARGS[*]:+ ${RUN_ARGS[*]}}${ADVISE:+ (+advise per stage)}" >&2
# NOT captured into a variable — that would buffer every line until the whole
# (potentially multi-minute) dispatch finished before showing anything. Instead
# it streams straight to the terminal, and the run id (its only stdout line
# besides the per-stage summary) is read back from a temp file.
RUN_OUT="$(mktemp)"
trap 'rm -f "$RUN_OUT"' EXIT
python3.11 -m evals.minimal.cli run "$CONFIG" ${RUN_ARGS[@]+"${RUN_ARGS[@]}"} | tee "$RUN_OUT"
RUN_ID="$(head -n1 "$RUN_OUT")"
echo "==> run id: $RUN_ID" >&2

# No explicit --stage means the whole configured chain ran; pull the stage
# list back out of the run's own config snapshot rather than re-deriving it.
if [[ -z "$STAGE" ]]; then
  STAGES="$(python3.11 -c "
import json
config = json.load(open('evals/minimal/.runs/${RUN_ID}/config.json'))
print(' '.join(config['order']))
")"
else
  STAGES="$STAGE"
fi

# report.html is rebuilt after run (below) and after EACH stage's checks and
# score — not once at the end — so it's never stale if you open it mid-run:
# whatever's been checked/scored so far is already on disk and visible.
echo "==> report: rebuilding report.html" >&2
python3.11 -m evals.minimal.cli report

STAGE_COUNT="$(wc -w <<< "$STAGES" | tr -d ' ')"
I=0
for s in $STAGES; do
  I=$((I + 1))
  echo "==> checks ($I/$STAGE_COUNT): $s — deterministic, free" >&2
  python3.11 -m evals.minimal.cli checks "$RUN_ID" --stage "$s"
  python3.11 -m evals.minimal.cli report
  echo "==> score ($I/$STAGE_COUNT): $s — judging via Mistral${ADVISE:+ + advising}" >&2
  python3.11 -m evals.minimal.cli score "$RUN_ID" --stage "$s" $ADVISE $CONCURRENCY
  python3.11 -m evals.minimal.cli report
done

# A run whose dispatches all errored used to exit 0 and print "done": the
# per-stage lines said `completed 0/1`, but nothing acted on it, so an
# unattended run (or a loop of them) looked successful while producing
# nothing. Seen when every stage returned 401 (run 260731-135513).
FAILED="$(python3.11 - "$RUN_ID" <<'PY'
import json, sys, pathlib
run = sys.argv[1]
path = pathlib.Path("evals/minimal/.runs")/run/"run.json"
data = json.loads(path.read_text()) if path.exists() else {}
bad = [(stage, r.get("error_reason") or "errored")
       for stage, rows in data.items() for r in rows if r.get("errored")]
for stage, reason in bad:
    print(f"{stage}: {reason}")
PY
)"
if [[ -n "$FAILED" ]]; then
  echo "==> FAILED: $RUN_ID — dispatches errored:" >&2
  echo "$FAILED" | sed 's/^/    /' >&2
  echo "$RUN_ID"
  exit 1
fi

echo "==> done: $RUN_ID" >&2
echo "$RUN_ID"
