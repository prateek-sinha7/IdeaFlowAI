#!/usr/bin/env bash
# tools/api/runs/composed-workflow-signoff/run-http.sh
#
# Same pattern as ../run-http.sh, scoped to this folder's composed-workflow
# signoff files. Runs any run.<name>.http file end-to-end and captures the
# full SSE/HTTP transcript -> tools/api/runs/composed-workflow-signoff/logs/<name>/<timestamp>.log
#
# Usage:
#   ./run-http.sh <name>
#   e.g. ./run-http.sh compose_build_and_run
#        ./run-http.sh compose_revision
#        ./run-http.sh compose_stop_resume
#
# Requires: backend running at http://localhost:8000 (../run.sh),
# httpyac installed globally (npm install -g httpyac).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NAME="${1:-}"
if [[ -z "$NAME" ]]; then
	echo "Usage: ./run-http.sh <name>" >&2
	echo "Available: $(ls run.*.http | sed -E 's/^run\.(.+)\.http$/\1/' | paste -sd ' ' -)" >&2
	exit 1
fi

HTTP_FILE="run.${NAME}.http"
if [[ ! -f "$HTTP_FILE" ]]; then
	echo "ERROR: no such file $HTTP_FILE" >&2
	echo "Available: $(ls run.*.http | sed -E 's/^run\.(.+)\.http$/\1/' | paste -sd ' ' -)" >&2
	exit 1
fi

if ! curl -s -o /dev/null --max-time 3 http://localhost:8000/health; then
	echo "ERROR: backend not reachable at http://localhost:8000. Start it first: ../run.sh" >&2
	exit 1
fi

if ! command -v httpyac >/dev/null 2>&1; then
	echo "ERROR: httpyac not found. Install it: npm install -g httpyac" >&2
	exit 1
fi

[[ -t 1 ]] && printf '\033[2J\033[3J\033[H' || true

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
export RUN_TIMESTAMP="$TIMESTAMP"

LOG_DIR="logs/${NAME}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${TIMESTAMP}.log"

clear && printf '\e[3J'

echo "==> Running ${HTTP_FILE} (this can take several minutes -- real LLM generation)"
echo "==> Full transcript: tools/api/runs/composed-workflow-signoff/${LOG_FILE}"
echo

httpyac send "$HTTP_FILE" --all -e local --output none 2>&1 | tee "$LOG_FILE"

echo
echo "==> Done."
echo "    Full log: tools/api/runs/composed-workflow-signoff/${LOG_FILE}"
