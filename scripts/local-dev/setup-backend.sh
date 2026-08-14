#!/usr/bin/env bash
# scripts/local-dev/setup-backend.sh
#
# Sets up the Python backend for local development:
#   - creates ./venv if missing
#   - installs backend/requirements.txt
#   - creates backend/.env if missing
#   - runs alembic migrations
#   - seeds QA login users (self-registration is permanently disabled)
#
# Does NOT start the server — see scripts/local-dev/run-backend.sh.
#
# Usage:
#   scripts/local-dev/setup-backend.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

log() { echo "==> $*"; }

PYTHON_BIN="$(command -v python3.12 || command -v python3)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: python3 not found. Run scripts/local-dev/install-prereqs.sh first." >&2
  exit 1
fi

if [[ ! -d "$REPO_ROOT/venv" ]]; then
  log "Creating virtualenv at ./venv..."
  "$PYTHON_BIN" -m venv venv
else
  log "Virtualenv already exists at ./venv."
fi

# shellcheck disable=SC1091
source "$REPO_ROOT/venv/bin/activate"

log "Upgrading pip..."
pip install --upgrade pip

log "Installing backend dependencies..."
pip install -r "$REPO_ROOT/backend/requirements.txt"

# NOTE: backend/app/core/config.py resolves its env file as
# <backend/>.env (BACKEND_DIR/.env), NOT a repo-root .env. The venv/npm
# local-dev path also doesn't use the docker-compose Postgres setup that
# app.env.example targets, so we write a minimal SQLite-backed dev env
# here instead of copying app.env.example.
BACKEND_ENV="$REPO_ROOT/backend/.env"
if [[ ! -f "$BACKEND_ENV" ]]; then
  log "Creating backend/.env (edit it to add AWS/Bedrock creds or ANTHROPIC_API_KEY for real LLM calls)."
  SECRET_KEY="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  cat > "$BACKEND_ENV" <<EOF
ENV=development
SECRET_KEY=$SECRET_KEY
DATABASE_URL=sqlite:///./dev.db
CORS_ORIGINS=["http://localhost:3000"]

# RUNS_ROOT defaults to /app/runs (a prod-only mount) which doesn't exist
# locally; override to a writable dir.
RUNS_ROOT=./runs

# Bedrock (default LLM provider) — requires AWS credentials via the boto3
# default chain (~/.aws/credentials, AWS_PROFILE, or env vars).
AWS_REGION=eu-central-1
BEDROCK_MODEL_ID=anthropic.claude-haiku-4-5-20251001-v1:0
BEDROCK_INFERENCE_PROFILE_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0

# Alternative to Bedrock for local dev: set this and the backend uses
# ChatAnthropic directly instead of AWS.
ANTHROPIC_API_KEY=
EOF
else
  log "backend/.env already exists, leaving it untouched."
fi

log "Running database migrations (alembic upgrade head)..."
(cd "$REPO_ROOT/backend" && alembic upgrade head)

# Self-registration is permanently disabled (POST /api/auth/register always
# returns 403 — see app/api/auth.py). Account creation is admin/script-only,
# so seed the QA users to get a working login for local dev.
log "Seeding local dev login users (scripts/seed_test_users.py)..."
(cd "$REPO_ROOT/backend" && python scripts/seed_test_users.py)

log "Backend setup complete."
log "Log in with: qa-admin@flowinqa.com / flowin-e2e-pass"
