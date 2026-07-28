#!/usr/bin/env bash
# run-eval.sh — run the issue-scoped eval suite (tests/evals).
#
# Part of .investigations/revision-pipeline-thinking-issue (design.md D-03/D-04).
# Default run is fully OFFLINE: scripted models only, 0 LLM tokens.
#
# tests/evals/ is organized as workflow/<domain>/<variant>/ (mirroring
# agents/workflows/<pipeline_type>/) plus common/ (shared framework code)
# and engine/ (pipeline-agnostic tests) — see tests/evals/PLAN.md.
#
# `--live` is a UNIVERSAL FLAG, not a separate command name: everything here
# is offline by default; adding --live wherever it's accepted below is the
# one consistent way to spend real tokens. It is never implicit.
#
# Usage:
#   ./run-eval.sh                       # full eval suite, offline (default)
#   ./run-eval.sh --live                # full eval suite, INCLUDING live/real-model tests
#   ./run-eval.sh phase <path>          # one phase folder, offline, e.g.
#                              #   ./run-eval.sh phase prototype/revision
#   ./run-eval.sh phase <path> --live   # that phase, including its live tests
#   ./run-eval.sh <scenario-id>         # LOCAL, 0-token check of any scenario in
#   ./run-eval.sh <scenario-id>.yaml    #   any workflow/*/*/scenarios/*.yaml
#                              #   (validate_scenario.py: confirms the checker
#                              #   correctly flags the raw fixture as unmet — catches
#                              #   a broken fixture/checker without spending tokens).
#   ./run-eval.sh <scenario-id> --live  # single real-model run of that one scenario (N=1)
#   ./run-eval.sh benchmark [<scenario-id>|cheap|all] [N]
#                              # REPEATED live sampling (default: cheap = every
#                              #   discovered scenario NOT marked expensive, N=10)
#                              #   — reports a pass RATE, not just one pass/fail.
#                              #   Scenario ids are read from EVERY
#                              #   tests/evals/workflow/*/*/scenarios/*.yaml — globally
#                              #   unique, so a scenario is always referred to by the
#                              #   same id everywhere no matter how many pipelines
#                              #   accumulate scenarios. "all" runs every one of them,
#                              #   capped at each scenario's YAML default_n if it's
#                              #   marked expensive — pass --skip-expensive to drop
#                              #   those from "all", or --n-override <id>=N to run
#                              #   one's full requested count on purpose. Extra flags
#                              #   pass through, e.g.:
#                              #     ./run-eval.sh benchmark all 10 --skip-expensive
#                              #   (benchmark is inherently live — no --live needed)
#   ./run-eval.sh layers       # engine-level + prototype/revision layer tests (L2/L4-L6
#                              #   are prototype_revision-specific; the pipeline-agnostic
#                              #   ones live in tests/evals/engine/)
#   ./run-eval.sh hello        # Phase-0 harness gate only
#   ./run-eval.sh prompts      # dump the composed system prompts + dispatch message
#                              #   to .investigations/.../prompt-dumps/ (0 tokens)
#   ./run-eval.sh <any pytest args...>   # passthrough, e.g. ./run-eval.sh -k s3 -v
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3.11}"
BASE=(-m pytest tests/evals)

# Strips a literal --live from "$@" (however it prints($1..)); sets
# _live=true if found. Used by both the default/all case and `phase` so
# --live means the same thing in both places instead of two implementations.
_strip_live() {
  _live=false
  _rest=()
  for a in "$@"; do
    if [[ "$a" == "--live" ]]; then _live=true; else _rest+=("$a"); fi
  done
}

case "${1:-all}" in
  all)
    shift || true
    _strip_live "$@"
    if $_live; then
      echo ">>> Including requires_api_key tests — this consumes LLM tokens." >&2
      exec "$PY" "${BASE[@]}" -m eval ${_rest[@]+"${_rest[@]}"}
    fi
    exec "$PY" "${BASE[@]}" -m "eval and not requires_api_key" ${_rest[@]+"${_rest[@]}"}
    ;;
  --live)
    # Bare `--live` with no other args, e.g. `./run-eval.sh --live` — same as
    # `all --live`, handled here since case falls to `*` otherwise.
    shift
    echo ">>> Including requires_api_key tests — this consumes LLM tokens." >&2
    exec "$PY" "${BASE[@]}" -m eval "$@"
    ;;
  hello)
    shift
    exec "$PY" -m pytest tests/evals/test_hello_world.py -m eval "$@"
    ;;
  layers)
    shift
    exec "$PY" -m pytest \
      tests/evals/engine/test_api_entry_seam.py \
      tests/evals/engine/test_previous_run_context_seed.py \
      tests/evals/workflow/prototype/revision/test_prototype_revision_manifest_shape.py \
      tests/evals/workflow/prototype/revision/test_revision_validation_post_step_dispatches_fix_loop.py \
      tests/evals/workflow/prototype/revision/test_issue_selection_ignores_instruction.py \
      tests/evals/workflow/prototype/revision/test_fix_loop_prompt_assembly_before_model_call.py \
      -m eval "$@"
    ;;
  prompts)
    shift
    exec "$PY" -m tests.evals.dump_prompts "$@"
    ;;
  phase)
    shift
    if [[ -z "${1:-}" ]]; then
      echo "usage: ./run-eval.sh phase <path> [--live]   e.g. ./run-eval.sh phase prototype/revision" >&2
      exit 2
    fi
    phase_path="$1"
    shift
    _strip_live "$@"
    if $_live; then
      echo ">>> Including requires_api_key tests in phase '$phase_path' — this consumes LLM tokens." >&2
      exec "$PY" -m pytest "tests/evals/workflow/${phase_path}" -m eval ${_rest[@]+"${_rest[@]}"}
    fi
    exec "$PY" -m pytest "tests/evals/workflow/${phase_path}" -m "eval and not requires_api_key" ${_rest[@]+"${_rest[@]}"}
    ;;
  benchmark)
    # ./run-eval.sh benchmark [<scenario-id>|cheap|all] [N] — args optional,
    # in order. Scenario ids come from workflow/*/*/scenarios/*.yaml, so this
    # stays generic rather than hardcoding the known ids — anything that
    # isn't a bare number or a --flag is treated as the scenario name; the
    # Python side (live_benchmark.py's argparse choices) rejects an unknown one.
    # No --live needed here — "benchmark" is inherently a live command.
    shift
    scenario="cheap"
    n="10"
    if [[ -n "${1:-}" && ! "${1:-}" =~ ^[0-9]+$ && "${1:-}" != --* ]]; then
      scenario="${1%.yaml}"   # accept a bare id or its <id>.yaml filename interchangeably
      shift
    fi
    if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
      n="$1"
      shift
    fi
    exec "$PY" -m tests.evals.live_benchmark --scenario "$scenario" --n "$n" "$@"
    ;;
  *)
    # `./run-eval.sh <scenario-id>` or `./run-eval.sh <scenario-id>.yaml` —
    # any scenario in any workflow/*/*/scenarios/*.yaml.
    #
    # SAFE BY DEFAULT: this alone runs a 0-token LOCAL check (validate_scenario.py)
    # — no model call. `--live` is REQUIRED to actually spend tokens, so a
    # bare scenario name never accidentally reaches a real model.
    _maybe_scenario="${1%.yaml}"
    _matches=(tests/evals/workflow/*/*/scenarios/"${_maybe_scenario}".yaml)
    if [[ -n "${_maybe_scenario:-}" && -f "${_matches[0]:-}" ]]; then
      scenario="$_maybe_scenario"
      shift
      _strip_live "$@"
      if $_live; then
        echo ">>> LIVE single run against the real model ($scenario) — this consumes LLM tokens." >&2
        exec "$PY" -m tests.evals.live_benchmark --scenario "$scenario" --n 1 ${_rest[@]+"${_rest[@]}"}
      else
        exec "$PY" -m tests.evals.validate_scenario "$scenario"
      fi
    fi
    # Passthrough: treat every argument as extra pytest args on the full suite.
    exec "$PY" "${BASE[@]}" -m "eval and not requires_api_key" "$@"
    ;;
esac
