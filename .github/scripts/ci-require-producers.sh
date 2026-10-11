#!/usr/bin/env bash
# Require every named producer job to have SUCCEEDED before evidence is merged.
#
# Usage:
#   ci-require-producers.sh <name>=<result> [<name>=<result> ...]
#
# Each <result> is a `needs.<job>.result` value: success | failure | cancelled |
# skipped. Only `success` is accepted.
#
# WHY THIS IS A SEPARATE GATE
# ---------------------------
# The evidence jobs run with `if: always()` so that a failed producer still
# yields an honest verdict rather than a skipped job. But `always()` also means
# they run when a producer produced NOTHING — and merging coverage from an
# incomplete producer set computes a percentage over a smaller denominator, which
# reads as a PASS. A missing partition must fail the gate, not quietly shrink it.
#
# `skipped` and `cancelled` are rejected for the same reason as `failure`: all
# three mean "this producer's evidence does not exist for this revision".
#
# Every producer is reported before exiting, not just the first bad one, so one
# run of the job tells you the whole story.
#
# R-02: this loop was duplicated verbatim in ci.yml's backend-evidence and
# frontend-evidence jobs. Two copies of a fail-closed gate is two places to get
# an `exit` wrong; the backend copy also carried a second error line the frontend
# copy lacked, so the two had already started to diverge.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "::error::ci-require-producers.sh needs at least one <name>=<result> argument." >&2
  echo "::error::Called with none — that would vacuously pass, so this is a failure." >&2
  exit 1
fi

fail=0

for pair in "$@"; do
  case "$pair" in
    *=*) ;;
    *)
      echo "::error::'${pair}' is not in <name>=<result> form." >&2
      exit 1
      ;;
  esac

  name="${pair%%=*}"
  result="${pair#*=}"

  if [ -z "$name" ]; then
    echo "::error::'${pair}' has an empty producer name." >&2
    exit 1
  fi
  if [ -z "$result" ]; then
    # An empty result means the caller interpolated `needs.<job>.result` for a
    # job that is not in its `needs:` list — the expression yields an empty
    # string. Treat it as a wiring bug rather than as a verdict.
    echo "::error::producer '${name}' has an empty result. Is it listed in this job's \`needs:\`?" >&2
    exit 1
  fi

  echo "  ${name}: ${result}"
  if [ "$result" != "success" ]; then
    echo "::error::mandatory producer '${name}' is '${result}'."
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "::error::Aggregate evidence cannot be computed from an incomplete producer set."
  exit 1
fi

echo "All $# producer(s) succeeded."
