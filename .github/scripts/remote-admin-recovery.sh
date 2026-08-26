#!/bin/bash
# =============================================================================
# remote-admin-recovery.sh — on-host half of .github/workflows/admin-recovery.yml
# =============================================================================
# Runs as root on the EC2 box via SSM RunCommand. Executes
# backend/app/scripts/recover_admin.py INSIDE the running backend container
# (same package as bootstrap_admin.py, invoked the same way: `python -m
# app.scripts.recover_admin`), so it uses the same DATABASE_URL, the same
# app.env, and the same Cognito config the live application does — no second,
# divergent connection path. It lives under app/scripts/, not the top-level
# scripts/, because only app/ is COPYed into the runtime image (see
# backend/Dockerfile) — anything under backend/scripts/ never ships.
#
# WHY THIS EXISTS
# ---------------
# Nobody holds EC2/SSH access to this environment: the only principal that can
# reach the box is the CI/CD OIDC deploy role, and the only channel it has is
# SSM RunCommand. So an operator locked out of the app has no shell to run a
# recovery command from. This script is that shell, driven by a
# workflow_dispatch.
#
# THE PASSWORD PATH
# -----------------
# SSM SecureString -> pipe -> container stdin. Never a shell variable (readable
# in /proc, inherited by subprocesses, prone to landing in an error message),
# never an argv element (visible in `ps`), never a file. Mirrors
# remote-deploy.sh §12 exactly, including the deliberate absence of any `echo`
# of the pipeline and of `set -x` anywhere in this script.
#
# `pipefail` is what makes the pipe safe: if get-parameter fails, the pipeline is
# non-zero even though the container command may exit 0 on its own — and the
# command would in any case reject the empty stdin. Fail-closed either way.
#
# INJECTED BY THE WORKFLOW (as shell assignments prepended to this file):
#   REGION, PARAM_PREFIX, ADMIN_EMAIL, MODE, DEMOTE_OTHERS
# =============================================================================

set -euo pipefail

: "${REGION:?REGION was not injected by admin-recovery.yml}"
: "${PARAM_PREFIX:?PARAM_PREFIX was not injected by admin-recovery.yml}"
: "${MODE:?MODE was not injected by admin-recovery.yml}"

APP_DIR=/opt/velocityai
ETC_DIR=/etc/velocityai
APP_ENV="${ETC_DIR}/app.env"

if [ ! -d "$APP_DIR" ]; then
    echo "[recover] FATAL: ${APP_DIR} does not exist — is this the right box?" >&2
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
    # shell's environment (and into every child process) for no reason.
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
    echo "[recover] FATAL: the backend container is not running. Deploy first." >&2
    compose_stack ps >&2 || true
    exit 1
fi

# ── report mode: read-only, no secret fetched ────────────────────────────────
# Runs first in EVERY mode. It is the only way to see this environment's real
# auth state (AUTH_PROVIDER, the user inventory, the local-admin count) given
# nobody can read the SSM parameters or query the database directly — and it
# costs one read-only command.
echo "[recover] === current auth state (read-only) ==="
compose_stack exec -T backend python -m app.scripts.recover_admin --report

if [ "$MODE" = "report" ]; then
    echo "[recover] report-only mode — nothing was changed."
    exit 0
fi

# ── reset mode ───────────────────────────────────────────────────────────────
: "${ADMIN_EMAIL:?ADMIN_EMAIL is required when MODE=reset}"

ADMIN_PASSWORD_PARAM="${PARAM_PREFIX}/bootstrap/admin-password"

RECOVER_ARGS="--email ${ADMIN_EMAIL} --password-stdin"
if [ "${DEMOTE_OTHERS:-0}" = "1" ]; then
    RECOVER_ARGS="${RECOVER_ARGS} --demote-other-local-admins"
fi

echo "[recover] === resetting administrator: ${ADMIN_EMAIL} ==="
echo "[recover] streaming the password from ${ADMIN_PASSWORD_PARAM} (never logged)..."

# shellcheck disable=SC2086  # RECOVER_ARGS is a deliberate word-split of flags
aws ssm get-parameter \
    --name "$ADMIN_PASSWORD_PARAM" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text \
    --region "$REGION" \
    | compose_stack exec -T backend python -m app.scripts.recover_admin $RECOVER_ARGS

echo "[recover] === auth state after recovery ==="
compose_stack exec -T backend python -m app.scripts.recover_admin --report

echo "[recover] SUCCESS"
