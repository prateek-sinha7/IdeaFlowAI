#!/usr/bin/env bash
# scripts/local-dev/setup-backend.sh
#
# Prepares the native backend development environment without making database
# or Cognito changes. The backend uses PostgreSQL and Cognito; this script
# intentionally never substitutes SQLite, seeds local-password users, or
# creates users in a shared Cognito pool.
#
# Usage:
#   scripts/local-dev/setup-backend.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
BACKEND_ENV="$BACKEND_DIR/.env"
TEMPLATE="$BACKEND_DIR/.env.example"

log() { echo "==> $*"; }

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required. Install it, then rerun this script." >&2
  exit 1
fi

if [[ ! -f "$BACKEND_ENV" ]]; then
  log "Creating backend/.env from backend/.env.example..."
  cp "$TEMPLATE" "$BACKEND_ENV"
  echo "Configure DATABASE_URL and Cognito values in backend/.env, then rerun this script." >&2
  exit 1
fi

log "Installing locked backend dependencies with uv..."
(cd "$BACKEND_DIR" && uv sync)

log "Preparing the native run sandbox root..."
mkdir -p "$BACKEND_DIR/runs"

if grep -q '<postgres-' "$BACKEND_ENV"; then
  echo "ERROR: DATABASE_URL still contains the template placeholder. Configure PostgreSQL in backend/.env." >&2
  exit 1
fi

log "Checking whether existing users block migration 0038..."
(cd "$BACKEND_DIR" && uv run python scripts/migrate_local_users_to_cognito.py --report)

cat <<'EOF'

Backend setup is ready.

Before applying migrations, resolve every row reported above with the Cognito
cutover runbook. Then run from backend/:
  uv run alembic upgrade head

The setup script does not seed users. Cognito is the only authentication
provider, so create or invite development accounts through the approved pool.
EOF
