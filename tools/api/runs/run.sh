#!/usr/bin/env bash
# tools/api/runs/run.sh
#
# Convenience wrapper so you don't have to remember scripts/local-dev/*.sh —
# starts the backend these .run.http files talk to (http://localhost:8000).
# Runs one-time setup (venv, DB migrations, seeded QA users) automatically
# if it hasn't been done yet, then starts the dev server in the foreground.
#
# Usage:
#   ./run.sh            # setup (if needed) + start the backend
#   ./run.sh --setup    # force-run setup again (safe to re-run)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

if [[ ! -d "$REPO_ROOT/venv" || "${1:-}" == "--setup" ]]; then
	echo "==> Running first-time backend setup (venv, migrations, seeded QA users)..."
	"$REPO_ROOT/scripts/local-dev/setup-backend.sh"
fi

echo "==> Starting backend at http://localhost:8000 (Ctrl+C to stop)..."
exec "$REPO_ROOT/scripts/local-dev/run-backend.sh"
