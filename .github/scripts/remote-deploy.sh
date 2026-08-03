#!/bin/bash
# =============================================================================
# On-host redeploy — executed ON THE EC2 INSTANCE by SSM RunCommand.
# =============================================================================
# Invoked by .github/workflows/deploy.yml, which builds the payload it sends as:
#
#     #!/bin/bash
#     REGISTRY='<account>.dkr.ecr.<region>.amazonaws.com'
#     REGION='eu-central-1'
#     IMAGE_TAG='v1.2.3'                 # label only — NOT what is deployed
#     BACKEND_DIGEST='sha256:...'        # what is actually deployed
#     FRONTEND_DIGEST='sha256:...'       #  "
#     ...one literal assignment per input...
#     <the entire contents of this file>
#
# Keeping the logic in a committed file rather than a heredoc inside the
# workflow YAML is deliberate: it can be shellcheck'd and `bash -n`'d in CI,
# it diffs cleanly in review, and it removes the nested-quoting hazard of
# runner-side vs. box-side `$` expansion that a heredoc forces you to get right
# one backslash at a time.
#
# WHAT THIS REPLACES
# ------------------
# This is a faithful port of the `post_build` phase of the retired
# infra/buildspec.yml (AWS CodeBuild), with the two Terraform couplings removed
# because Terraform no longer runs in CI/CD:
#
#   buildspec (CodeBuild)                     -> here (GitHub Actions)
#   terraform output -raw instance_id         -> vars.EC2_INSTANCE_ID
#   terraform output -raw config_bucket       -> (not needed)
#   aws s3 cp config/docker-compose.yml       -> injected base64 from the checkout
#   aws s3 cp config/docker-compose.prod.yml  -> injected base64 from the checkout
#   aws s3 cp config/reconcile-host-config.sh -> injected base64 from the checkout
#   aws s3 cp config/deploy.env  (image pins) -> REGISTRY + injected DIGESTS
#
# Everything else — the first-boot wait, the host-config reconcile and its
# 0/1/2 exit contract, the uid-10001 bind-mount ownership, the ECR login and
# the two-file `docker compose` invocation — is preserved, because each one
# exists in response to a specific production incident documented in the
# buildspec's own comments.
#
# THREE THINGS ARE DELIBERATELY STRICTER THAN THE BUILDSPEC WAS
#   1. §2  A host/deploy environment mismatch ABORTS. It used to warn and
#          continue, which allowed one environment's images to land on another
#          environment's box while the backup decision followed the CI-side
#          value — a silent cross-environment deploy with no restore point.
#   2. §7  Images are pinned BY DIGEST (repo@sha256:...), never by tag, so the
#          bytes CI built and scanned are provably the bytes that run here.
#   3. §11 The health gate covers backend, frontend AND the nginx ingress, and
#          a failure ROLLS BACK to the previously pinned digests instead of
#          leaving a broken stack serving traffic.
#
# WHY `docker compose` DIRECTLY AND NOT `systemctl restart velocityai-app`
# -----------------------------------------------------------------------
# velocityai-app.service runs `docker compose -f docker-compose.yml -f
# docker-compose.prod.yml`, and the prod override interpolates
# ${VELOCITYAI_CW_LOG_GROUP} for the awslogs driver with
# `awslogs-create-group: "false"` (i.e. fail-closed on an empty group). That
# variable is written into /etc/velocityai/app.env by bootstrap-ec2.sh §11 but
# is NOT in velocityai-load-secrets' preserve list — the loader keeps only
# ^(BACKEND_IMAGE|FRONTEND_IMAGE|ENV)= — so it is stripped on every loader run,
# including the ExecStartPre inside a `systemctl restart`. Restarting the unit
# would therefore hand compose an empty log group. Running compose here lets us
# export the four interpolation inputs explicitly and deterministically.
# The unit itself is left untouched (bootstrap already `enable`d it, and both
# services carry `restart: unless-stopped`, so reboot recovery is unaffected).
# =============================================================================

# SSM's AWS-RunShellScript invokes the payload with /bin/sh (dash on Ubuntu) —
# the interpreter is chosen by the agent, so the shebang above is NOT honoured
# and `set -o pipefail` would abort with "Illegal option -o pipefail". Re-exec
# under bash on the first executable line. Must stay POSIX-compatible.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi

set -euo pipefail

# ── Inputs (injected as literal assignments above this file) ─────────────────
# The three *_GZ values are gzip-then-base64 of the corresponding repo file.
# Plain base64 put the whole payload at ~85 KB, close enough to SendCommand's
# request-size ceiling that a future edit to reconcile-host-config.sh (37 KB of
# it) could push a deploy over. gzip -9 brings the same content in at roughly a
# quarter of that, so there is real headroom.
: "${REGISTRY:?REGISTRY was not injected by deploy.yml}"
: "${REGION:?REGION was not injected by deploy.yml}"
: "${IMAGE_TAG:?IMAGE_TAG was not injected by deploy.yml}"
: "${DEPLOY_ENV:?DEPLOY_ENV was not injected by deploy.yml}"
: "${BACKEND_DIGEST:?BACKEND_DIGEST was not injected by deploy.yml}"
: "${FRONTEND_DIGEST:?FRONTEND_DIGEST was not injected by deploy.yml}"
: "${COMPOSE_GZ:?COMPOSE_GZ was not injected by deploy.yml}"
: "${COMPOSE_PROD_GZ:?COMPOSE_PROD_GZ was not injected by deploy.yml}"
: "${RECONCILE_GZ:?RECONCILE_GZ was not injected by deploy.yml}"

APP_DIR=/opt/velocityai
ETC_DIR=/etc/velocityai
APP_ENV="${ETC_DIR}/app.env"
BOOTSTRAP_ENV="${ETC_DIR}/bootstrap.env"

# ── Images are addressed BY DIGEST, not by tag ───────────────────────────────
# `repo:tag` is a mutable pointer: between the build resolving it and this host
# pulling it, a tag can be re-pointed at other content (and on a shared
# registry, by a job for another environment). `repo@sha256:...` IS the
# content, so what CI built and scanned is exactly what runs here — the pull
# either gets those bytes or fails. IMAGE_TAG still travels, but only as a
# human-readable label for logs and the deploy record.
#
# Defence in depth: deploy.yml validates these before building the payload,
# but the payload is literal shell, so validate again here rather than let a
# malformed reference reach `docker compose pull` as a confusing manifest error.
for _digest in "$BACKEND_DIGEST" "$FRONTEND_DIGEST"; do
    case "$_digest" in
        sha256:????????????????????????????????????????????????????????????????) ;;
        *)
            echo "[deploy] FATAL: malformed image digest '${_digest}'" >&2
            exit 1
            ;;
    esac
done

BACKEND_IMAGE_REF="${REGISTRY}/velocityai/backend@${BACKEND_DIGEST}"
FRONTEND_IMAGE_REF="${REGISTRY}/velocityai/frontend@${FRONTEND_DIGEST}"

echo "[deploy] start $(date -u --iso-8601=seconds) env=${DEPLOY_ENV} tag=${IMAGE_TAG}"

# ── 1. Wait out first-boot self-provisioning ────────────────────────────────
# On a freshly created instance the host install (Docker, Postgres, nginx, the
# systemd units, the first app start) runs asynchronously from user-data via
# velocityai-firstboot.service. If Docker is not on the box yet, wait for that
# to write its completion sentinel rather than racing it. On an already
# provisioned host Docker is present and this whole block is skipped, so
# steady-state deploys pay nothing for it.
if ! command -v docker >/dev/null 2>&1; then
    echo "[deploy] docker not present — waiting for velocityai-firstboot bootstrap to finish"
    for i in $(seq 1 90); do
        if [ -f /var/lib/velocityai/.bootstrap-done ]; then
            echo "[deploy] first-boot bootstrap complete"
            break
        fi
        if [ "$i" = "90" ]; then
            echo "[deploy] FATAL: timed out after 15 minutes waiting for first-boot bootstrap" >&2
            echo "[deploy]        check: journalctl -u velocityai-firstboot.service" >&2
            exit 1
        fi
        sleep 10
    done
fi

# ── 2. Preconditions ────────────────────────────────────────────────────────
# bootstrap.env is written by Terraform's compute module user_data and is the
# only place the host's own identity (region, env tag, FQDN, param prefix)
# lives. Its absence means this box was never provisioned, so there is nothing
# a container redeploy can usefully do.
if [ ! -f "$BOOTSTRAP_ENV" ]; then
    echo "[deploy] FATAL: ${BOOTSTRAP_ENV} is missing — this instance is not bootstrapped." >&2
    echo "[deploy]        Apply the Terraform app layer and let velocityai-firstboot.service run." >&2
    exit 1
fi
# shellcheck source=/dev/null
. "$BOOTSTRAP_ENV"

# ── Environment identity must MATCH — this is a hard gate ───────────────────
# bootstrap.env's VELOCITYAI_ENVIRONMENT is the box's own identity, written by
# Terraform's compute module user_data. If it disagrees with the environment CI
# resolved, the deploy is pointed at the wrong host and there is no safe way to
# continue.
#
# This used to WARN and proceed using the host value, which produced the worst
# possible outcome: the images and SSM config of one environment landed on
# another environment's box, while `$DEPLOY_ENV` still drove the §9 backup
# decision — so a dev-targeted deploy could mutate a prod host having skipped
# the pre-deploy pg_dump entirely. Nothing downstream can detect that, because
# each half is individually self-consistent.
#
# The per-environment IAM deploy roles (infra/terraform/bootstrap/github_oidc.tf)
# make this state nearly unreachable — ssm:SendCommand is denied unless the
# target instance carries this environment's own Environment tag. This check is
# the second, on-host layer: it also catches a mis-tagged instance or a
# hand-crafted SendCommand, neither of which IAM can see.
HOST_ENV="${VELOCITYAI_ENVIRONMENT:-}"
if [ -z "$HOST_ENV" ]; then
    echo "[deploy] FATAL: VELOCITYAI_ENVIRONMENT is not set in ${BOOTSTRAP_ENV}." >&2
    echo "[deploy]        Cannot confirm this host belongs to '${DEPLOY_ENV}' — refusing to deploy." >&2
    exit 1
fi
if [ "$HOST_ENV" != "$DEPLOY_ENV" ]; then
    echo "[deploy] FATAL: environment mismatch — this host is '${HOST_ENV}', the deploy targets '${DEPLOY_ENV}'." >&2
    echo "[deploy]        Refusing to deploy. Check the EC2_INSTANCE_ID variable on the" >&2
    echo "[deploy]        '${DEPLOY_ENV}' GitHub Environment and the instance's Environment tag." >&2
    exit 1
fi

# `mkdir -p`, NOT `install -d -m 0750`: these directories already exist on a
# bootstrapped host (bootstrap-ec2.sh creates /opt/velocityai at 0755), and
# `install -d -m` would silently re-permission them on every deploy. 0750
# root:root on /opt/velocityai would break velocityai-skills-backup.service,
# which runs as User=velocityai and has to traverse into data/skills.
mkdir -p "$APP_DIR" "$ETC_DIR"

# ── 3. Ship the repo's config onto the box ──────────────────────────────────
# These three files are byte-for-byte repo content. CodeBuild read them from
# s3://<backup-bucket>/config/ where the Terraform app layer had uploaded them;
# with Terraform out of the pipeline they travel inline instead, which also
# removes a whole failure mode (deploying a compose file from a stale apply).
#
# Written via a temp file + mv so a truncated decode can never leave a
# half-written compose file that the `docker compose` calls below would then
# read. `base64 -d | gunzip -c` under pipefail fails the deploy instead.
unpack() {
    local blob="$1" dest="$2" tmp
    tmp="$(mktemp "${dest}.XXXXXX")"
    printf '%s' "$blob" | base64 -d | gunzip -c > "$tmp"
    if [ ! -s "$tmp" ]; then
        echo "[deploy] FATAL: decoded payload for ${dest} is empty" >&2
        rm -f "$tmp"
        exit 1
    fi
    mv "$tmp" "$dest"
}

unpack "$COMPOSE_GZ" "${APP_DIR}/docker-compose.yml"
unpack "$COMPOSE_PROD_GZ" "${APP_DIR}/docker-compose.prod.yml"
chown velocityai:velocityai "${APP_DIR}/docker-compose.yml" "${APP_DIR}/docker-compose.prod.yml"
chmod 0644 "${APP_DIR}/docker-compose.yml" "${APP_DIR}/docker-compose.prod.yml"

unpack "$RECONCILE_GZ" "${APP_DIR}/reconcile-host-config.sh"
chmod 0755 "${APP_DIR}/reconcile-host-config.sh"

# ── 4. Bind-mount ownership ─────────────────────────────────────────────────
# Both containers run as the non-root numeric uid:gid 10001 and write into
# these two bind mounts (per-user skills, per-run agent sandboxes under
# RUNS_ROOT=/app/runs). bootstrap-ec2.sh sets this ownership on FIRST BOOT
# only, and steady-state deploys never re-run bootstrap — without re-asserting
# it here, pipeline runs fail with EACCES on '/app/runs/<user>'.
mkdir -p "${APP_DIR}/data/runs" "${APP_DIR}/data/skills"
chown -R 10001:10001 "${APP_DIR}/data/runs" "${APP_DIR}/data/skills"

# ── 5. Host-config reconcile (nginx + CloudWatch agent) ─────────────────────
# bootstrap-ec2.sh runs once per instance, but the nginx site and the agent
# config legitimately change with the application, so a repo edit would
# otherwise never reach a live box. The script is idempotent and defines a
# three-value exit contract that we honour exactly as the buildspec did:
#   0 — clean
#   1 — nginx failed; it already rolled the host back. A bad nginx config is a
#       live-traffic risk, so this ABORTS the deploy.
#   2 — CloudWatch agent degraded only (observability, not the request path).
#       Reported loudly, does NOT abort.
set +e
bash "${APP_DIR}/reconcile-host-config.sh"
RECONCILE_STATUS=$?
set -e
if [ "$RECONCILE_STATUS" -eq 1 ]; then
    echo "[deploy] FATAL: reconcile-host-config.sh failed on nginx (exit 1) — aborting deploy" >&2
    exit 1
elif [ "$RECONCILE_STATUS" -ne 0 ]; then
    echo "[deploy] WARNING: reconcile-host-config.sh exited ${RECONCILE_STATUS} (CloudWatch agent DEGRADED)" >&2
    echo "[deploy]          see /var/log/velocityai-reconcile.log — continuing with the app deploy." >&2
fi

# ── 6. Pull this deploy's config from SSM into app.env ──────────────────────
# deploy.yml has just written the GitHub-side variables/secrets to
# /velocityai/<env>/*, so run the host loader now to materialise them into
# app.env. This is what makes "GitHub is the single source of truth for
# environment config" true on every deploy rather than only on a reboot.
# Not present in the CodeBuild pipeline, which only ever picked up new SSM
# values when something else happened to restart the unit.
echo "[deploy] refreshing ${APP_ENV} from SSM"
/usr/local/bin/velocityai-load-secrets

# ── 7. Re-assert the managed lines (AFTER the loader) ───────────────────────
# velocityai-load-secrets rewrites app.env from scratch and preserves only
# ^(BACKEND_IMAGE|FRONTEND_IMAGE|ENV)=, so anything else in bootstrap-ec2.sh
# §11's managed block is dropped. We rewrite exactly that block, in the same
# shape and order §11 wrote it, and nothing else:
#   BACKEND_IMAGE / FRONTEND_IMAGE  the DIGEST-pinned reference for the image
#       this deploy resolved (repo@sha256:...). Written here rather than by
#       `sed -i 's|^KEY=.*|...|'` because sed exits 0 having changed nothing
#       when the pattern is absent — a silent no-op that restarts the box on
#       the PREVIOUS image while reporting success.
#   VELOCITYAI_ENVIRONMENT / VELOCITYAI_CW_LOG_GROUP  required by
#       docker-compose.prod.yml's awslogs driver (see the header note). The
#       loader drops these, so a deploy that did not restore them would ship
#       containers with an empty log group and `awslogs-create-group: "false"`.
#
# This is also where the ROLLBACK TARGET is captured, before the pins are
# overwritten: whatever images are currently pinned are, by definition, the
# last set that passed this script's health gate. Recorded now because after
# the rewrite below the old values are gone from the only place they existed.
# Empty on a first-ever deploy (§11 handles that case explicitly).
PREV_BACKEND_IMAGE=""
PREV_FRONTEND_IMAGE=""
if [ -f "$APP_ENV" ]; then
    PREV_BACKEND_IMAGE="$(sed -n 's/^BACKEND_IMAGE=//p' "$APP_ENV" | tail -n 1)"
    PREV_FRONTEND_IMAGE="$(sed -n 's/^FRONTEND_IMAGE=//p' "$APP_ENV" | tail -n 1)"
fi

TMP_ENV="$(mktemp "${ETC_DIR}/app.env.XXXXXX")"
chmod 0640 "$TMP_ENV"
chown root:velocityai "$TMP_ENV" 2>/dev/null || true
if [ -f "$APP_ENV" ]; then
    grep -vE '^(BACKEND_IMAGE|FRONTEND_IMAGE|VELOCITYAI_ENVIRONMENT|VELOCITYAI_CW_LOG_GROUP)=' \
        "$APP_ENV" >> "$TMP_ENV" || true
fi
{
    echo "BACKEND_IMAGE=${BACKEND_IMAGE_REF}"
    echo "FRONTEND_IMAGE=${FRONTEND_IMAGE_REF}"
    echo "VELOCITYAI_ENVIRONMENT=${HOST_ENV}"
    echo "VELOCITYAI_CW_LOG_GROUP=/velocityai/${HOST_ENV}/app"
} >> "$TMP_ENV"
mv "$TMP_ENV" "$APP_ENV"
chmod 0640 "$APP_ENV"
chown root:velocityai "$APP_ENV" 2>/dev/null || true

# Post-condition. `grep -qxF` is whole-line + fixed-string, so the '/' and ':'
# in an ECR URI cannot be misread as regex.
if ! grep -qxF "BACKEND_IMAGE=${BACKEND_IMAGE_REF}" "$APP_ENV"; then
    echo "[deploy] FATAL: BACKEND_IMAGE pin did not apply (expected ${BACKEND_IMAGE_REF})." >&2
    exit 1
fi
if ! grep -qxF "FRONTEND_IMAGE=${FRONTEND_IMAGE_REF}" "$APP_ENV"; then
    echo "[deploy] FATAL: FRONTEND_IMAGE pin did not apply (expected ${FRONTEND_IMAGE_REF})." >&2
    exit 1
fi
echo "[deploy] image pins verified (tag ${IMAGE_TAG}):"
echo "[deploy]   backend  ${BACKEND_DIGEST}"
echo "[deploy]   frontend ${FRONTEND_DIGEST}"

# ── 8. ECR login ────────────────────────────────────────────────────────────
# velocityai-ecr-login.timer refreshes this every 6 hours, but a deploy must
# not depend on where it happens to fall in that window — an expired token
# surfaces as a confusing `docker compose pull` denial.
aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "$REGISTRY"

# ── 9. Pre-deploy pg_dump (stage/prod only) ────────────────────────────────
# A restore point from seconds before the new image runs `alembic upgrade head`
# (migrations run in-container from backend/docker-entrypoint.sh, not as a
# separate step). Uses the existing systemd oneshot so bucket/KMS config comes
# from its EnvironmentFile. A failed backup BLOCKS the deploy — proceeding
# without a restore point defeats the purpose. Skipped on dev for speed.
case "$DEPLOY_ENV" in
    stage | prod)
        echo "[deploy] pre-deploy pg_dump (${DEPLOY_ENV} safety net)..."
        if ! systemctl start velocityai-pg-dump.service; then
            echo "[deploy] FATAL: pre-deploy pg_dump FAILED — refusing to deploy without a restore point." >&2
            journalctl -u velocityai-pg-dump.service -n 40 --no-pager >&2 || true
            exit 1
        fi
        echo "[deploy] pre-deploy pg_dump complete"
        ;;
    *)
        echo "[deploy] skipping pre-deploy pg_dump (env=${DEPLOY_ENV})"
        ;;
esac

# ── 10. Recreate the stack ──────────────────────────────────────────────────
# Export exactly the variables the two compose files interpolate, rather than
# `set -a; . app.env; set +a` as the buildspec did. Sourcing app.env re-parses
# every SSM-sourced value through the shell, which strips the quotes out of
# JSON-shaped values (CORS_ORIGINS) and aborts the whole deploy under `set -e`
# on any value the shell finds unbalanced. Container environment is unaffected
# either way — docker-compose.yml feeds it via `env_file:`, which compose
# parses itself. NEXT_PUBLIC_* are not exported: they are `build.args` only
# (we never build on the box) and already carry `:-` defaults, so compose does
# not warn about them.
export BACKEND_IMAGE="$BACKEND_IMAGE_REF"
export FRONTEND_IMAGE="$FRONTEND_IMAGE_REF"
export VELOCITYAI_CW_LOG_GROUP="/velocityai/${HOST_ENV}/app"
export AWS_REGION="$REGION"

cd "$APP_DIR"
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# ── 11. Health gate (all three tiers) + automatic rollback on failure ──────
# WHAT IS CHECKED, AND WHY EACH TIER EARNS ITS PLACE
#   backend  loopback :8000/health — the app itself. Was the only check, and it
#            passing told us nothing about whether a user could load the site.
#   frontend loopback :3000/       — Next.js standalone. A frontend that crashes
#            on boot (bad build, missing runtime env) left the previous gate
#            perfectly green while every page returned 502.
#   ingress  https://127.0.0.1/health and / through NGINX, with the real Host
#            header — proves TLS terminates, the upstreams resolve, and the
#            proxy is actually wired to these containers. `-k` because the cert
#            is issued for the FQDN and we deliberately connect to loopback:
#            this validates the request path, not certificate trust (cert expiry
#            is a separate CloudWatch alarm, not this script's job).
# All three over loopback, so the gate never depends on public DNS or on the
# security group — an internal fault is distinguishable from an exposure issue.
#
# ON FAILURE: ROLL BACK, don't just report. Previously this exited 1 with the
# broken stack still serving, so a red pipeline and an outage arrived together
# and recovery was a manual SSH/SSM race. Restoring the previous digests is
# safe precisely because they are digests: the exact bytes that were healthy
# moments ago, still present in the local Docker cache, no registry round-trip
# and no tag re-resolution.
#
# NOT ROLLED BACK: database migrations. `alembic upgrade head` runs in-container
# on start (backend/docker-entrypoint.sh) and this script cannot know whether a
# migration was destructive. That is what §9's pre-deploy pg_dump is for on
# stage/prod: the restore point exists, and restoring it is a deliberate human
# decision. The rollback below returns the CODE to the last healthy version and
# says so explicitly in the log.
FQDN="${VELOCITYAI_FQDN:-localhost}"

# Whether to include the nginx/TLS tier. Mirrors the SAME condition
# reconcile-host-config.sh §nginx uses to decide whether it can validate the
# config at all: with no /etc/letsencrypt/live/<domain>, the 443 server block
# references cert files that do not exist, so nginx is legitimately not serving
# HTTPS yet and probing it would fail a deploy for a state that is expected
# mid-provisioning. On a fully provisioned host reconcile REFUSES to continue
# when the cert directory is missing (it exits 1 and this script has already
# aborted at §5), so reaching here with certs present is the normal case and the
# ingress tier is then mandatory.
if [ -d "/etc/letsencrypt/live/${FQDN}" ]; then
    INGRESS_CHECK=1
else
    INGRESS_CHECK=0
    echo "[deploy] NOTE: /etc/letsencrypt/live/${FQDN} absent — skipping the nginx/TLS health tier" >&2
    echo "[deploy]       (host still provisioning; backend+frontend are still checked)." >&2
fi

compose_stack() {
    docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"
}

# One full pass over every tier. Returns 0 only when all applicable tiers answer.
check_health() {
    curl -fsS --max-time 10 http://127.0.0.1:8000/health >/dev/null 2>&1 || return 1
    curl -fsS --max-time 10 -o /dev/null http://127.0.0.1:3000/ >/dev/null 2>&1 || return 2
    if [ "$INGRESS_CHECK" -eq 1 ]; then
        curl -fsS --max-time 10 -k -o /dev/null -H "Host: ${FQDN}" \
            https://127.0.0.1/health >/dev/null 2>&1 || return 3
        curl -fsS --max-time 10 -k -o /dev/null -H "Host: ${FQDN}" \
            https://127.0.0.1/ >/dev/null 2>&1 || return 4
    fi
    return 0
}

describe_health_failure() {
    case "$1" in
        1) echo "backend (127.0.0.1:8000/health)" ;;
        2) echo "frontend (127.0.0.1:3000/)" ;;
        3) echo "nginx ingress -> backend (https://${FQDN}/health)" ;;
        4) echo "nginx ingress -> frontend (https://${FQDN}/)" ;;
        *) echo "unknown tier" ;;
    esac
}

if [ "$INGRESS_CHECK" -eq 1 ]; then
    echo "[deploy] waiting for health: backend + frontend + nginx ingress (up to 5 minutes)..."
else
    echo "[deploy] waiting for health: backend + frontend (up to 5 minutes)..."
fi
HEALTHY=0
LAST_RC=0
for i in $(seq 1 30); do
    set +e
    check_health
    LAST_RC=$?
    set -e
    if [ "$LAST_RC" -eq 0 ]; then
        HEALTHY=1
        break
    fi
    echo "[deploy]   attempt ${i}/30 — waiting on $(describe_health_failure "$LAST_RC")"
    sleep 10
done

if [ "$HEALTHY" -eq 1 ]; then
    if [ "$INGRESS_CHECK" -eq 1 ]; then
        echo "[deploy] healthy: backend + frontend + nginx ingress"
    else
        echo "[deploy] healthy: backend + frontend (ingress tier skipped)"
    fi
    echo "[deploy] complete $(date -u --iso-8601=seconds) tag=${IMAGE_TAG}"
    echo "[deploy]   backend  ${BACKEND_IMAGE_REF}"
    echo "[deploy]   frontend ${FRONTEND_IMAGE_REF}"
    exit 0
fi

echo "[deploy] FATAL: health gate failed after 5 minutes on $(describe_health_failure "$LAST_RC")" >&2
echo "[deploy] --- container state ---" >&2
compose_stack ps >&2 || true
echo "[deploy] --- backend logs (tail 80) ---" >&2
compose_stack logs --tail=80 backend >&2 || true
echo "[deploy] --- frontend logs (tail 40) ---" >&2
compose_stack logs --tail=40 frontend >&2 || true

# No previous pins (first deploy on a fresh box) means there is nothing healthy
# to return to. Leave the stack as-is for diagnosis and fail.
if [ -z "$PREV_BACKEND_IMAGE" ] || [ -z "$PREV_FRONTEND_IMAGE" ]; then
    echo "[deploy] NO ROLLBACK TARGET: no previous image pins were recorded (first deploy on this host)." >&2
    echo "[deploy]        Leaving the current stack up for diagnosis." >&2
    exit 1
fi

if [ "$PREV_BACKEND_IMAGE" = "$BACKEND_IMAGE_REF" ] && [ "$PREV_FRONTEND_IMAGE" = "$FRONTEND_IMAGE_REF" ]; then
    echo "[deploy] NO ROLLBACK: the previous pins are identical to this deploy's — the currently" >&2
    echo "[deploy]        pinned version is itself the one failing. Leaving the stack up for diagnosis." >&2
    exit 1
fi

echo "[deploy] ROLLING BACK to the previously healthy images:" >&2
echo "[deploy]   backend  ${PREV_BACKEND_IMAGE}" >&2
echo "[deploy]   frontend ${PREV_FRONTEND_IMAGE}" >&2

# Re-pin app.env so a later reboot / `systemctl restart velocityai-app` comes
# back on the rolled-back version too. Without this, the containers would be
# rolled back but the box's declared state would still name the broken images.
ROLLBACK_ENV="$(mktemp "${ETC_DIR}/app.env.XXXXXX")"
chmod 0640 "$ROLLBACK_ENV"
chown root:velocityai "$ROLLBACK_ENV" 2>/dev/null || true
grep -vE '^(BACKEND_IMAGE|FRONTEND_IMAGE)=' "$APP_ENV" >> "$ROLLBACK_ENV" || true
{
    echo "BACKEND_IMAGE=${PREV_BACKEND_IMAGE}"
    echo "FRONTEND_IMAGE=${PREV_FRONTEND_IMAGE}"
} >> "$ROLLBACK_ENV"
mv "$ROLLBACK_ENV" "$APP_ENV"
chmod 0640 "$APP_ENV"
chown root:velocityai "$APP_ENV" 2>/dev/null || true

export BACKEND_IMAGE="$PREV_BACKEND_IMAGE"
export FRONTEND_IMAGE="$PREV_FRONTEND_IMAGE"

set +e
compose_stack up -d --remove-orphans
ROLLBACK_UP_RC=$?
set -e
if [ "$ROLLBACK_UP_RC" -ne 0 ]; then
    echo "[deploy] CRITICAL: the rollback 'docker compose up' itself failed (exit ${ROLLBACK_UP_RC})." >&2
    echo "[deploy]          The host needs manual attention NOW." >&2
    exit 1
fi

# Confirm the rollback actually restored service, and say so plainly either way.
# "Rolled back" without verification is not a state anyone should trust.
echo "[deploy] verifying rollback health (up to 2 minutes)..." >&2
for i in $(seq 1 12); do
    set +e
    check_health
    LAST_RC=$?
    set -e
    if [ "$LAST_RC" -eq 0 ]; then
        echo "[deploy] ROLLBACK SUCCEEDED — service restored on the previous images." >&2
        echo "[deploy]        Deploy of ${IMAGE_TAG} FAILED and was reverted." >&2
        if [ "$DEPLOY_ENV" = "stage" ] || [ "$DEPLOY_ENV" = "prod" ]; then
            echo "[deploy]        NOTE: database migrations are NOT reverted. If ${IMAGE_TAG} applied a" >&2
            echo "[deploy]        destructive migration, restore the pre-deploy pg_dump from §9." >&2
        fi
        exit 1
    fi
    echo "[deploy]   rollback attempt ${i}/12 — waiting on $(describe_health_failure "$LAST_RC")" >&2
    sleep 10
done

echo "[deploy] CRITICAL: ROLLBACK DID NOT RESTORE HEALTH (last failure: $(describe_health_failure "$LAST_RC"))." >&2
echo "[deploy]          The host is serving a degraded stack and needs manual attention NOW." >&2
compose_stack ps >&2 || true
exit 1
