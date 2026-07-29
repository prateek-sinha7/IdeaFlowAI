#!/usr/bin/env bash
# model-graded.sh — the CLI for the FROZEN model-graded branch.
#
# ┌─ FROZEN ─────────────────────────────────────────────────────────────────┐
# │ This package is superseded by evals/grading/ (use ./evals/grading/       │
# │ grade.sh). It is kept only to read back runs already recorded under      │
# │ logs/. Its scores were not reproducible — see evals/grading/docs/        │
# │ SUMMARY.md — so do not start new work here and do not calibrate          │
# │ against its numbers.                                                     │
# └──────────────────────────────────────────────────────────────────────────┘
#
# Standalone: this script owns this package and nothing else. It shares no entry
# point with evals/hybrid/eval.sh (the hybrid suite) or evals/grading/grade.sh.
#
# Deliberately NOT named grade.sh or graded.sh: a one-character difference
# between two token-spending commands is a footgun.
#
# LOCATION-INDEPENDENT by design: it resolves its own directory and walks up to
# find the backend root, so moving this folder does not break it.
#
# Usage:
#   ./model-graded.sh report [--last N] [--worst N] [--by system_prompt_hash]
#                                      # summarize recorded runs by scanning
#                                      #   logs/<run_id>/{run,grade}.json  (free)
#
#   ./model-graded.sh graded <scenario-id> [--judge] [--samples N]
#                                      # one scenario. Bare = free driver+precheck
#                                      #   sanity run; --judge adds a real judge
#                                      #   call and a report entry.          [LIVE]
#   ./model-graded.sh dataset <agent-id> [dataset-name] [--judge]
#                                      # every scenario in scenarios/<name>.json
#                                      #   for one agent, as ONE run.        [LIVE]
#
#   ./model-graded.sh runs             # list recorded run folders           (free)
#   ./model-graded.sh agents           # list agents + their datasets        (free)
#
# --provider/--model move the AGENT UNDER TEST; --judge-provider/--judge-model
# move the JUDGE. They are separate axes — conflating them grades one model's
# output with a rubric calibrated for another.
#
# Exit codes: the CLI's own (0 ok · non-zero on failure) · 2 usage
set -euo pipefail

MG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Walk up to the backend root (the dir holding pyproject.toml) so the package
# import path works no matter where this folder is moved to.
BACKEND="$MG_DIR"
while [[ "$BACKEND" != "/" && ! -f "$BACKEND/pyproject.toml" ]]; do
  BACKEND="$(dirname "$BACKEND")"
done
if [[ ! -f "$BACKEND/pyproject.toml" ]]; then
  echo "model-graded.sh: cannot find the backend root (no pyproject.toml above $MG_DIR)" >&2
  exit 2
fi

# Derived from the location on disk, not hardcoded — a move needs no edit here.
PKG="$(python3 -c "
import os
print(os.path.relpath('$MG_DIR', '$BACKEND').replace(os.sep, '.'))
")"

PY="${PYTHON:-python3.11}"

cd "$BACKEND"

_cli() { exec "$PY" -m "$PKG.cli" "$@"; }

_frozen_notice() {
  echo ">>> FROZEN package — superseded by ./evals/grading/grade.sh." >&2
  echo ">>> Its scores were not reproducible; do not calibrate against them." >&2
}

case "${1:-help}" in
  help|-h|--help)
    sed -n '2,40p' "$MG_DIR/model-graded.sh" | sed 's/^# \{0,1\}//'
    exit 0
    ;;

  report)
    # Pure local file read over logs/ — no model call, no tokens.
    shift
    _cli report "$@"
    ;;

  graded)
    shift
    [[ -z "${1:-}" ]] && { echo "usage: ./model-graded.sh graded <scenario-id> [--judge]" >&2; exit 2; }
    _frozen_notice
    case " $* " in
      *" --judge "*) echo ">>> LIVE: --judge dispatches a real judge model and spends tokens." >&2 ;;
    esac
    _cli graded "$@"
    ;;

  dataset)
    shift
    [[ -z "${1:-}" ]] && { echo "usage: ./model-graded.sh dataset <agent-id> [dataset-name] [--judge]" >&2; exit 2; }
    _frozen_notice
    echo ">>> LIVE: dispatches the agent under test for EVERY row in the dataset." >&2
    _cli dataset "$@"
    ;;

  runs)
    found=0
    while IFS= read -r d; do
      [[ -n "$d" ]] || continue
      found=1
      printf "  %s\n" "$(basename "$d")"
    done < <(find "$MG_DIR/logs" -mindepth 1 -maxdepth 1 -type d ! -name '.*' 2>/dev/null | sort -r)
    [[ $found -eq 0 ]] && echo "  (no recorded runs)"
    exit 0
    ;;

  agents)
    for d in "$MG_DIR"/agents/*/; do
      [[ -d "$d" ]] || continue
      [[ "$(basename "$d")" == __pycache__ ]] && continue
      # `|| true`: under `set -e` + `pipefail` a failing element of this
      # pipeline (e.g. xargs on an agent with no scenarios/) would abort the
      # whole listing mid-loop instead of just yielding an empty string.
      datasets=$(find "$d/scenarios" -name '*.json' 2>/dev/null \
        | xargs -n1 basename 2>/dev/null | sed 's/\.json$//' | sort | tr '\n' ' ' || true)
      printf "  %-24s %s\n" "$(basename "$d")" "${datasets:-(no datasets)}"
    done
    exit 0
    ;;

  *)
    # Passthrough keeps the underlying CLI reachable.
    _frozen_notice
    _cli "$@"
    ;;
esac
