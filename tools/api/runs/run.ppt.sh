#!/usr/bin/env bash
# tools/api/runs/run.ppt.sh
#
# Runs the ppt (od_ppt) pipeline end-to-end via run.ppt.http and captures
# everything:
#   - the generated deck  -> tools/api/runs/artifacts/ppt/<timestamp>.html
#   - the full WS/HTTP log -> tools/api/runs/logs/ppt/<timestamp>.log
#
# Usage:
#   ./run.ppt.sh
#
# Requires: backend running at http://localhost:8000 (see ./run.sh),
# httpyac installed globally (npm install -g httpyac).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! curl -s -o /dev/null --max-time 3 http://localhost:8000/health; then
	echo "ERROR: backend not reachable at http://localhost:8000. Start it first: ./run.sh" >&2
	exit 1
fi

if ! command -v httpyac >/dev/null 2>&1; then
	echo "ERROR: httpyac not found. Install it: npm install -g httpyac" >&2
	exit 1
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
export RUN_TIMESTAMP="$TIMESTAMP"

LOG_DIR="logs/ppt"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${TIMESTAMP}.log"

echo "==> Running run.ppt.http (this can take several minutes -- real LLM generation)"
echo "==> Full transcript: tools/api/runs/logs/ppt/${TIMESTAMP}.log"
echo

httpyac send run.ppt.http --all -e local 2>&1 | tee "$LOG_FILE"

echo
echo "==> Done."
echo "    Deck:      tools/api/runs/artifacts/ppt/${TIMESTAMP}.html  (or .txt if the run didn't complete)"
echo "    Full log:  tools/api/runs/logs/ppt/${TIMESTAMP}.log"
