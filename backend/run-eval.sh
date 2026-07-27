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
#   ./run-eval.sh live-s2      # REAL Haiku S2 run: does the model make Reports
#                              #   reachable from the sidebar? consumes tokens
#   ./run-eval.sh live-example1
#                              # REAL Haiku run on a REAL user-provided prototype
#                              #   (~124KB, fixtures/example1/) — materially more
#                              #   tokens than S1/S2's ~3KB fixture
#   ./run-eval.sh benchmark [s1|s2|example1|both|all] [N]
#                              # REPEATED live sampling (default: both=s1+s2, N=10)
#                              #   — reports a pass RATE, not just one pass/fail.
#                              #   "all" includes example1, but CAPPED at N=3
#                              #   regardless of N (a single example1 run has
#                              #   hit 8.1M tokens) — pass --skip-expensive to
#                              #   drop it from "all", or --n-example1 N to run
#                              #   its full requested count on purpose. Extra
#                              #   flags pass through, e.g.:
#                              #     ./run-eval.sh benchmark all 10 --skip-expensive
#                              #     ./run-eval.sh benchmark all 10 --n-example1 10
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
  live-s2)
    shift
    echo ">>> LIVE run against the real model — this consumes LLM tokens." >&2
    exec "$PY" -m pytest tests/evals/revision_fulfillment/test_live_s2.py \
      -m "eval and requires_api_key" -s -v "$@"
    ;;
  live-example1)
    shift
    echo ">>> LIVE run against the real model, REAL ~124KB fixture — this" >&2
    echo ">>> consumes materially more LLM tokens than live-s1/live-s2." >&2
    exec "$PY" -m pytest tests/evals/revision_fulfillment/test_live_example1.py \
      -m "eval and requires_api_key" -s -v "$@"
    ;;
  benchmark)
    # ./run-eval.sh benchmark [s1|s2|example1|both|all] [N] — args optional, in order.
    shift
    scenario="both"
    n="10"
    if [[ "${1:-}" == "s1" || "${1:-}" == "s2" || "${1:-}" == "example1" \
          || "${1:-}" == "both" || "${1:-}" == "all" ]]; then
      scenario="$1"
      shift
    fi
    if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
      n="$1"
      shift
    fi
    exec "$PY" -m tests.evals.live_benchmark --scenario "$scenario" --n "$n"
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
