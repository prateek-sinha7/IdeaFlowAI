#!/usr/bin/env bash
# scripts/local-dev/run-backend.sh
#
# Starts the FastAPI backend with the supported uv-managed environment.
# Run setup-backend.sh first to create and validate backend/.env.
#
# Usage:
#   scripts/local-dev/run-backend.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required. Install it, then rerun this script." >&2
  exit 1
fi

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  echo "ERROR: backend/.env is missing. Copy backend/.env.example and configure PostgreSQL/Cognito first." >&2
  exit 1
fi

cd "$BACKEND_DIR"
exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
