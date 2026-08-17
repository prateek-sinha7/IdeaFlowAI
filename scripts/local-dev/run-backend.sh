#!/usr/bin/env bash
# scripts/local-dev/run-backend.sh
#
# Starts the FastAPI backend dev server (assumes setup-backend.sh has
# already been run at least once).
#
# app/main.py does `from app.api... import ...` (absolute imports rooted at
# the `app` package), so this must run with cwd = backend/ as `app.main:app`
# — NOT from the repo root as `backend.app.main:app` (that import path
# resolves `app` to nothing and fails with ModuleNotFoundError).
#
# Usage:
#   scripts/local-dev/run-backend.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ ! -d "$REPO_ROOT/venv" ]]; then
  echo "ERROR: venv not found. Run scripts/local-dev/setup-backend.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$REPO_ROOT/venv/bin/activate"

cd "$REPO_ROOT/backend"
exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
