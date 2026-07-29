#!/usr/bin/env bash
# eval.sh — the CLI for the hybrid eval suite (evals/hybrid).
#
# Standalone: this script owns this package and nothing else. It shares no entry
# point with evals/grading/grade.sh (agent-output GRADING, always live) or with
# evals/model_graded/model-graded.sh (the frozen previous grading branch).
#
# LOCATION-INDEPENDENT by design: it resolves its own directory and walks up to
# find the backend root, so moving this folder does not break it.
#
# This suite answers "did the machinery do what it promised?" — the pipeline ran
# in the right order, the manifest matches the registry, the prompt surface is
# intact, and a revision actually fulfilled the instruction it was given. The
# verdict is always CODE, never a judge model: binary, free, reproducible.
#
# OFFLINE BY DEFAULT — scripted models, 0 LLM tokens. `--live` is a UNIVERSAL
# FLAG, never a command name and never implicit: add it wherever it is accepted
# below and that is the only way this script spends tokens.
#
# Usage:
#   ./eval.sh                          # the whole suite, offline           (free)
#   ./eval.sh --live                   # the whole suite, INCLUDING live    [LIVE]
#
#   ./eval.sh hello                    # Phase-0 harness gate only          (free)
#   ./eval.sh layers                   # engine + revision layer tests      (free)
#   ./eval.sh prompts                  # dump composed prompts to disk      (free)
#
#   ./eval.sh phase <path>             # one phase folder, e.g. prototype/revision
#   ./eval.sh phase <path> --live      # that phase, including its live tests
#
#   ./eval.sh <scenario-id>            # 0-token check that a scenario+checker
#                                      #   is sane (validate_scenario)      (free)
#   ./eval.sh <scenario-id> --live     # ONE real-model run of that scenario [LIVE]
#   ./eval.sh benchmark [<id>|cheap|all] [N]
#                                      # REPEATED live sampling — reports a pass
#                                      #   RATE, not one pass/fail. Inherently
#                                      #   live, so it takes no --live.      [LIVE]
#
#   ./eval.sh scenarios                # list every discovered scenario     (free)
#   ./eval.sh phases                   # list every phase folder            (free)
#   ./eval.sh check                    # validate every scenario+checker    (free)
#   ./eval.sh <any pytest args...>     # passthrough, e.g. ./eval.sh -k s3 -v
#
# Scenario ids are globally unique across every workflow/*/*/scenarios/*.yaml, so
# one id always means one scenario no matter how many pipelines accumulate.
#
# Exit codes: pytest's own (0 ok · 1 tests failed) · 2 usage
set -euo pipefail

EVAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Walk up to the backend root (the dir holding pyproject.toml) so both the pytest
# paths and the package import path work no matter where this folder is moved to.
BACKEND="$EVAL_DIR"
while [[ "$BACKEND" != "/" && ! -f "$BACKEND/pyproject.toml" ]]; do
  BACKEND="$(dirname "$BACKEND")"
done
if [[ ! -f "$BACKEND/pyproject.toml" ]]; then
  echo "eval.sh: cannot find the backend root (no pyproject.toml above $EVAL_DIR)" >&2
  exit 2
fi

# Both derived from the location on disk, not hardcoded — a move of this folder
# needs no edit here. REL is for pytest paths, PKG for `python -m`.
REL="$(python3 -c "import os;print(os.path.relpath('$EVAL_DIR', '$BACKEND'))")"
PKG="${REL//\//.}"

PY="${PYTHON:-python3.11}"

cd "$BACKEND"

BASE=(-m pytest "$REL")
OFFLINE='eval and not requires_api_key'

# Strips a literal --live from "$@"; sets _live=true if found. One implementation
# so --live means exactly the same thing in every command that accepts it.
_strip_live() {
  _live=false
  _rest=()
  for a in "$@"; do
    if [[ "$a" == "--live" ]]; then _live=true; else _rest+=("$a"); fi
  done
}

_warn_live() {
  echo ">>> LIVE — sends real prompts to a real model and spends tokens." >&2
}

_scenario_files() { find "$EVAL_DIR"/workflow/*/*/scenarios -name '*.yaml' ! -name '_*' 2>/dev/null | sort; }

case "${1:-all}" in
  help|-h|--help)
    sed -n '2,46p' "$EVAL_DIR/eval.sh" | sed 's/^# \{0,1\}//'
    exit 0
    ;;

  all)
    shift || true
    _strip_live "$@"
    if $_live; then
      _warn_live
      exec "$PY" "${BASE[@]}" -m eval ${_rest[@]+"${_rest[@]}"}
    fi
    exec "$PY" "${BASE[@]}" -m "$OFFLINE" ${_rest[@]+"${_rest[@]}"}
    ;;

  --live)
    # Bare `--live` with no other args — same as `all --live`, handled here
    # because the case would otherwise fall through to the passthrough arm.
    shift
    _warn_live
    exec "$PY" "${BASE[@]}" -m eval "$@"
    ;;

  hello)
    shift
    exec "$PY" -m pytest "$REL/test_hello_world.py" -m eval "$@"
    ;;

  layers)
    # The layered tests along the issue surface: pipeline-agnostic engine seams
    # first, then the prototype/revision-specific layers.
    shift
    exec "$PY" -m pytest \
      "$REL/engine/test_api_entry_seam.py" \
      "$REL/engine/test_previous_run_context_seed.py" \
      "$REL/workflow/prototype/revision/test_prototype_revision_manifest_shape.py" \
      "$REL/workflow/prototype/revision/test_revision_validation_post_step_dispatches_fix_loop.py" \
      "$REL/workflow/prototype/revision/test_issue_selection_ignores_instruction.py" \
      "$REL/workflow/prototype/revision/test_fix_loop_prompt_assembly_before_model_call.py" \
      -m eval "$@"
    ;;

  prompts)
    shift
    exec "$PY" -m "$PKG.dump_prompts" "$@"
    ;;

  phase)
    shift
    if [[ -z "${1:-}" ]]; then
      echo "usage: ./eval.sh phase <path> [--live]   e.g. ./eval.sh phase prototype/revision" >&2
      echo "available:" >&2
      find "$EVAL_DIR/workflow" -mindepth 2 -maxdepth 2 -type d ! -name '__pycache__' 2>/dev/null \
        | sed "s|$EVAL_DIR/workflow/|  |" | sort >&2
      exit 2
    fi
    phase_path="$1"; shift
    if [[ ! -d "$EVAL_DIR/workflow/$phase_path" ]]; then
      echo "eval.sh: no such phase '$phase_path'. Try: ./eval.sh phases" >&2
      exit 2
    fi
    _strip_live "$@"
    if $_live; then
      _warn_live
      exec "$PY" -m pytest "$REL/workflow/$phase_path" -m eval ${_rest[@]+"${_rest[@]}"}
    fi
    exec "$PY" -m pytest "$REL/workflow/$phase_path" -m "$OFFLINE" ${_rest[@]+"${_rest[@]}"}
    ;;

  benchmark)
    # ./eval.sh benchmark [<scenario-id>|cheap|all] [N] — both args optional, in
    # order. Anything that is not a bare number or a --flag is the scenario id;
    # live_benchmark's argparse rejects an unknown one. Inherently live.
    shift
    scenario="cheap"
    n="10"
    if [[ -n "${1:-}" && ! "${1:-}" =~ ^[0-9]+$ && "${1:-}" != --* ]]; then
      scenario="${1%.yaml}"   # a bare id or its <id>.yaml filename, interchangeably
      shift
    fi
    if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
      n="$1"; shift
    fi
    _warn_live
    exec "$PY" -m "$PKG.live_benchmark" --scenario "$scenario" --n "$n" "$@"
    ;;

  scenarios)
    found=0
    while IFS= read -r f; do
      [[ -n "$f" ]] || continue
      found=1
      phase="$(basename "$(dirname "$(dirname "$f")")")"
      domain="$(basename "$(dirname "$(dirname "$(dirname "$f")")")")"
      printf "  %-38s %s\n" "$(basename "${f%.yaml}")" "$domain/$phase"
    done < <(_scenario_files)
    [[ $found -eq 0 ]] && echo "  (no scenarios yet)"
    exit 0
    ;;

  phases)
    find "$EVAL_DIR/workflow" -mindepth 2 -maxdepth 2 -type d ! -name '__pycache__' 2>/dev/null \
      | sed "s|$EVAL_DIR/workflow/|  |" | sort
    exit 0
    ;;

  check)
    # Every scenario's fixture+checker, validated locally. Confirms each checker
    # correctly flags its RAW fixture as unmet — a broken fixture or an
    # always-true checker is caught here, before any live run pays for it.
    rc=0
    while IFS= read -r f; do
      [[ -n "$f" ]] || continue
      id="$(basename "${f%.yaml}")"
      if out=$("$PY" -m "$PKG.validate_scenario" "$id" 2>&1); then
        printf "  %-38s ok\n" "$id"
      else
        printf "  %-38s FAILED\n" "$id"
        echo "$out" | sed 's/^/      /'
        rc=1
      fi
    done < <(_scenario_files)
    exit $rc
    ;;

  *)
    # `./eval.sh <scenario-id>` or `<scenario-id>.yaml` — any scenario in any
    # workflow/*/*/scenarios/*.yaml.
    #
    # SAFE BY DEFAULT: bare, this is a 0-token LOCAL check (validate_scenario) —
    # no model call. `--live` is REQUIRED to spend tokens, so a bare scenario
    # name can never accidentally reach a real model.
    _maybe_scenario="${1%.yaml}"
    _matches=("$EVAL_DIR"/workflow/*/*/scenarios/"${_maybe_scenario}".yaml)
    if [[ -n "${_maybe_scenario:-}" && -f "${_matches[0]:-}" ]]; then
      scenario="$_maybe_scenario"
      shift
      _strip_live "$@"
      if $_live; then
        echo ">>> LIVE single run against the real model ($scenario) — spends tokens." >&2
        exec "$PY" -m "$PKG.live_benchmark" --scenario "$scenario" --n 1 ${_rest[@]+"${_rest[@]}"}
      fi
      exec "$PY" -m "$PKG.validate_scenario" "$scenario"
    fi
    # Passthrough: every argument is extra pytest args on the full offline suite.
    exec "$PY" "${BASE[@]}" -m "$OFFLINE" "$@"
    ;;
esac
