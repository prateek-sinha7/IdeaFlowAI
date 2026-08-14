#!/usr/bin/env bash
# scripts/local-dev/setup-frontend.sh
#
# Sets up the Next.js frontend for local development:
#   - npm install in frontend/
#   - creates frontend/.env.local if missing
#
# Does NOT start the dev server — see scripts/local-dev/run-frontend.sh.
#
# Usage:
#   scripts/local-dev/setup-frontend.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"

log() { echo "==> $*"; }

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm not found. Run scripts/local-dev/install-prereqs.sh first." >&2
  exit 1
fi

log "Installing frontend dependencies..."
(cd "$FRONTEND_DIR" && npm install)

ENV_LOCAL="$FRONTEND_DIR/.env.local"
if [[ ! -f "$ENV_LOCAL" ]]; then
  log "Creating frontend/.env.local..."
  cat > "$ENV_LOCAL" <<'EOF'
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/chat
EOF
else
  log "frontend/.env.local already exists, leaving it untouched."
fi

log "Frontend setup complete."
