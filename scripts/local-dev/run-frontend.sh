#!/usr/bin/env bash
# scripts/local-dev/run-frontend.sh
#
# Starts the Next.js frontend dev server (assumes setup-frontend.sh has
# already been run at least once).
#
# Usage:
#   scripts/local-dev/run-frontend.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "ERROR: frontend/node_modules not found. Run scripts/local-dev/setup-frontend.sh first." >&2
  exit 1
fi

cd "$FRONTEND_DIR"
exec npm run dev
