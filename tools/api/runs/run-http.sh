#!/usr/bin/env bash
# tools/api/runs/run-http.sh
#
# Runs any run.<pipeline>.http file end-to-end and captures everything:
#   - the generated deliverable(s) -> tools/api/runs/artifacts/<pipeline>/...
#   - the full SSE/HTTP transcript  -> tools/api/runs/logs/<pipeline>/<timestamp>.log
#
# Usage:
#   ./run-http.sh <pipeline>
#   e.g. ./run-http.sh ppt
#        ./run-http.sh user_stories
#        ./run-http.sh prototype
#        ./run-http.sh app_builder
#        ./run-http.sh dotnet_to_azure
#        ./run-http.sh mulesoft_to_springboot
#        ./run-http.sh custom
#        ./run-http.sh sample_conditional_branch_new
#        ./run-http.sh sample_conditional_previous_step
#        ./run-http.sh sample_conditional_human_input
#        ./run-http.sh sample_conditional_launch_new
#        ./run-http.sh sample_conditional_target
#
# Requires: backend running at http://localhost:8000 (see ./run.sh),
# httpyac installed globally (npm install -g httpyac).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PIPELINE="${1:-}"
if [[ -z "$PIPELINE" ]]; then
	echo "Usage: ./run-http.sh <pipeline>" >&2
	echo "Available: $(ls run.*.http | sed -E 's/^run\.(.+)\.http$/\1/' | paste -sd ' ' -)" >&2
	exit 1
fi

HTTP_FILE="run.${PIPELINE}.http"
if [[ ! -f "$HTTP_FILE" ]]; then
	echo "ERROR: no such file $HTTP_FILE" >&2
	echo "Available: $(ls run.*.http | sed -E 's/^run\.(.+)\.http$/\1/' | paste -sd ' ' -)" >&2
	exit 1
fi

if ! curl -s -o /dev/null --max-time 3 http://localhost:8000/health; then
	echo "ERROR: backend not reachable at http://localhost:8000. Start it first: ./run.sh" >&2
	exit 1
fi

if ! command -v httpyac >/dev/null 2>&1; then
	echo "ERROR: httpyac not found. Install it: npm install -g httpyac" >&2
	exit 1
fi

# Fresh screen for a fresh run: a run's trace is long, and leftover scrollback
# from the previous one is easy to misread as part of this one. 2J clears the
# screen, 3J the scrollback buffer, H homes the cursor. Only when stdout is a
# terminal -- the transcript below is `tee`d to a log file that must stay clean.
# Runs after every precondition check so their error messages survive.
[[ -t 1 ]] && printf '\033[2J\033[3J\033[H' || true

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
export RUN_TIMESTAMP="$TIMESTAMP"

LOG_DIR="logs/${PIPELINE}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${TIMESTAMP}.log"

clear && printf '\e[3J'

echo "==> Running ${HTTP_FILE} (this can take several minutes -- real LLM generation)"
echo "==> Full transcript: tools/api/runs/${LOG_FILE}"
echo

httpyac send "$HTTP_FILE" --all -e local --output none 2>&1 | tee "$LOG_FILE"

echo
echo "==> Done."
echo "    Artifacts: tools/api/runs/artifacts/${PIPELINE}/"
echo "    Full log:  tools/api/runs/${LOG_FILE}"
