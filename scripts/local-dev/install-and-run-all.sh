#!/usr/bin/env bash
# scripts/local-dev/install-and-run-all.sh
#
# One-shot local dev bootstrap: installs prerequisites, sets up the backend
# venv and frontend node_modules, then runs both dev servers concurrently.
#
# Backend:  http://localhost:8000
# Frontend: http://localhost:3000
#
# Press Ctrl+C to stop both servers.
#
# Skip prereq installation (e.g. already have Python/Node/git) with:
#   SKIP_PREREQS=1 scripts/local-dev/install-and-run-all.sh
#
# Usage:
#   scripts/local-dev/install-and-run-all.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "==> $*"; }

if [[ "${SKIP_PREREQS:-0}" != "1" ]]; then
  log "Installing prerequisites..."
  "$SCRIPT_DIR/install-prereqs.sh"
else
  log "Skipping prerequisite installation (SKIP_PREREQS=1)."
fi

log "Setting up backend..."
"$SCRIPT_DIR/setup-backend.sh"

log "Setting up frontend..."
"$SCRIPT_DIR/setup-frontend.sh"

log "Reminder: edit backend/.env with real AWS/Bedrock creds (or set"
log "ANTHROPIC_API_KEY) before the backend can serve real LLM calls."

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  log "Shutting down..."
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

log "Starting backend (http://localhost:8000)..."
"$SCRIPT_DIR/run-backend.sh" &
BACKEND_PID=$!

log "Starting frontend (http://localhost:3000)..."
"$SCRIPT_DIR/run-frontend.sh" &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
