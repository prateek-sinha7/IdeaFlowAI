#!/usr/bin/env bash
# run-eval.sh — run the issue-scoped eval suite (tests/evals).
#
# Part of .investigations/revision-pipeline-thinking-issue (design.md D-03/D-04).
# Default run is fully OFFLINE: scripted models only, 0 LLM tokens.
#
# Usage:
#   ./run-eval.sh              # full eval suite, offline (default)
#   ./run-eval.sh layers       # Phase-1 layer tests only (L1–L6)
#   ./run-eval.sh scenarios    # Phase-2 scenario evals only (S1/S2/S3)
#   ./run-eval.sh hello        # Phase-0 harness gate only
#   ./run-eval.sh defect       # show the defect: run S1/S2 WITHOUT the xfail
#                              #   markers (--runxfail) so their real failures print
#   ./run-eval.sh prompts      # dump the composed system prompts + dispatch message
#                              #   to .investigations/.../prompt-dumps/ (0 tokens)
#   ./run-eval.sh live-s1      # REAL Haiku S1 run: does the model wire the Save
#                              #   button? prints diagnostics — consumes tokens
#   ./run-eval.sh live         # ALSO include live-LLM tests (requires_api_key;
#                              #   needs credentials — consumes tokens, Haiku only)
#   ./run-eval.sh <any pytest args...>   # passthrough, e.g. ./run-eval.sh -k s3 -v
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3.11}"
BASE=(-m pytest tests/evals)

case "${1:-all}" in
  all)
    shift || true
    exec "$PY" "${BASE[@]}" -m "eval and not requires_api_key" "$@"
    ;;
  hello)
    shift
    exec "$PY" -m pytest tests/evals/test_hello_world.py -m eval "$@"
    ;;
  layers)
    shift
    exec "$PY" -m pytest \
      tests/evals/revision_fulfillment/test_l1_api_entry.py \
      tests/evals/revision_fulfillment/test_l2_compile.py \
      tests/evals/revision_fulfillment/test_l3_context_seed.py \
      tests/evals/revision_fulfillment/test_l4_post_step.py \
      tests/evals/revision_fulfillment/test_l5_selection_gap.py \
      tests/evals/revision_fulfillment/test_l6_llm_boundary.py \
      -m eval "$@"
    ;;
  scenarios)
    shift
    exec "$PY" -m pytest tests/evals/revision_fulfillment/test_scenarios.py -m eval "$@"
    ;;
  defect)
    shift
    echo ">>> Running S1/S2 with --runxfail: expected output is TWO failures at"
    echo ">>> the fulfillment assertions (this IS the bug, reproduced)."
    exec "$PY" -m pytest tests/evals/revision_fulfillment/test_scenarios.py \
      -m eval --runxfail -k "s1_noop_edit or s2_partial_fix" "$@"
    ;;
  prompts)
    shift
    exec "$PY" -m tests.evals.dump_prompts "$@"
    ;;
  live-s1)
    shift
    echo ">>> LIVE run against the real model — this consumes LLM tokens." >&2
    exec "$PY" -m pytest tests/evals/revision_fulfillment/test_live_s1.py \
      -m "eval and requires_api_key" -s -v "$@"
    ;;
  live)
    shift
    echo ">>> Including requires_api_key tests — this consumes LLM tokens." >&2
    exec "$PY" "${BASE[@]}" -m eval "$@"
    ;;
  *)
    # Passthrough: treat every argument as extra pytest args on the full suite.
    exec "$PY" "${BASE[@]}" -m "eval and not requires_api_key" "$@"
    ;;
esac
