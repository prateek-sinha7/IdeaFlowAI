#!/bin/bash
# =============================================================================
# remote-cognito-reconcile.sh — on-host half of .github/workflows/cognito-reconcile.yml
# =============================================================================
# Runs as root on the EC2 box via SSM RunCommand. Executes
# app/scripts/reconcile_cognito_users.py INSIDE the running backend container,
# so it uses the same DATABASE_URL, the same app.env and the same Cognito
# config the live application does — no second, divergent connection path.
#
# The script has to live under backend/app/ rather than backend/scripts/ for
# this to be possible at all: backend/Dockerfile COPYs only app/, agents/,
# alembic/ and one named thumbnail generator into the runtime image, so nothing
# else under backend/scripts/ exists on a deployed box. See that module's own
# docstring.
#
# WHY THIS EXISTS
# ---------------
# Nobody holds EC2/SSH or direct database access to any environment: the only
# principal that can reach the box is the per-environment GitHub OIDC deploy
# role, and its only channel is SSM RunCommand. Drift between the Cognito pool
# and the local users table is therefore not something an operator can go and
# look at — this is the channel.
#
# NO SECRETS ARE HANDLED HERE. Unlike remote-deploy.sh's config push, this
# script fetches nothing from SSM and pipes nothing to stdin: the reconciler
# reads the pool with the EC2 instance role's own Cognito grants and the
# database with the container's existing config. Nothing in its output is
# sensitive — it prints user ids, emails and a per-class drift summary, all of
# which already appear in the admin UI. (remote-admin-recovery.sh, which this
# comment used to contrast against, was deleted in Phase 4 of the Cognito-only
# auth migration -- it recovered a local break-glass admin that no longer
# exists.)
#
# INJECTED BY THE WORKFLOW (as shell assignments prepended to this file):
#   REGION, MODE
# =============================================================================

set -euo pipefail

: "${REGION:?REGION was not injected by cognito-reconcile.yml}"
: "${MODE:?MODE was not injected by cognito-reconcile.yml}"

case "$MODE" in
    report|fix-disabled) ;;
    *)
        echo "[reconcile] FATAL: unknown MODE '${MODE}' (expected report|fix-disabled)" >&2
        exit 1
        ;;
esac

APP_DIR=/opt/velocityai
ETC_DIR=/etc/velocityai
APP_ENV="${ETC_DIR}/app.env"

if [ ! -d "$APP_DIR" ]; then
    echo "[reconcile] FATAL: ${APP_DIR} does not exist — is this the right box?" >&2
    exit 1
fi
cd "$APP_DIR"

# docker-compose.prod.yml interpolates these for the awslogs driver with
# awslogs-create-group=false (fail-closed on an empty group), and the on-host
# secrets loader deliberately drops them from app.env. `docker compose` parses
# BOTH files even for a plain `exec`, so without these the command dies on an
# unset-variable interpolation rather than doing anything useful. Re-derived
# here the same way remote-deploy.sh does, not invented.
if [ -f "$APP_ENV" ]; then
    # Only the four compose-interpolated names — deliberately NOT a blanket
    # `source` of app.env, which would pull every application secret into this
    # shell's environment (and every child process) for no reason.
    for _name in BACKEND_IMAGE FRONTEND_IMAGE VELOCITYAI_ENVIRONMENT VELOCITYAI_CW_LOG_GROUP; do
        _line="$(grep -E "^${_name}=" "$APP_ENV" | tail -n1 || true)"
        if [ -n "$_line" ]; then
            export "${_name}=${_line#*=}"
        fi
    done
fi
export AWS_REGION="$REGION"

compose_stack() {
    docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"
}

if ! compose_stack ps --status running --services 2>/dev/null | grep -qx backend; then
    echo "[reconcile] FATAL: the backend container is not running. Deploy first." >&2
    compose_stack ps >&2 || true
    exit 1
fi

# Report FIRST in every mode, including fix-disabled — the reconciler prints its
# findings before applying anything, so a single run leaves a record of what the
# state was as well as what changed. Costs one extra read-only pass.
echo "[reconcile] === drift report (read-only) ==="
REPORT_OUTPUT=$(compose_stack exec -T backend python -m app.scripts.reconcile_cognito_users --report)
echo "$REPORT_OUTPUT"

# Check for DRIFT in report output (used by scheduled runs to fail on drift)
if echo "$REPORT_OUTPUT" | grep -q "^DRIFT$"; then
    DRIFT_FOUND=1
else
    DRIFT_FOUND=0
fi

if [ "$MODE" = "report" ]; then
    echo "[reconcile] report-only mode — nothing was changed."
    # For scheduled runs: fail the job if drift was found in report mode
    if [ "$DRIFT_FOUND" -eq 1 ]; then
        echo "[reconcile] DRIFT detected — check the report above"
        exit 1
    fi
    exit 0
fi

echo "[reconcile] === applying --fix-disabled ==="
echo "[reconcile] this DISABLES local rows Cognito confirms are absent or disabled."
echo "[reconcile] it never re-enables, never deletes, and never creates a row."
compose_stack exec -T backend python -m app.scripts.reconcile_cognito_users --fix-disabled

echo "[reconcile] === state after fix ==="
compose_stack exec -T backend python -m app.scripts.reconcile_cognito_users --report

echo "[reconcile] SUCCESS"
