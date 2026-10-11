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
#   4. §13 (new, not in the buildspec) A successful deploy prunes every local
#          Docker image not referenced by any container. Every deploy pulls a
#          new backend/frontend image and never removed the one it replaced,
#          so pulled images accumulated on the box's disk indefinitely.
#
# WHY `docker compose` DIRECTLY AND NOT `systemctl restart velocityai-app`
# -----------------------------------------------------------------------
# velocityai-app.service runs `docker compose -f docker-compose.yml -f
# docker-compose.prod.yml`, and the prod override interpolates
# ${VELOCITYAI_CW_LOG_GROUP} for the awslogs driver with
# `awslogs-create-group: "false"` (i.e. fail-closed on an empty group).
#
# CORRECTION: this paragraph used to claim the loader keeps only
# ^(BACKEND_IMAGE|FRONTEND_IMAGE|ENV)= and therefore strips
# VELOCITYAI_CW_LOG_GROUP on every run, so that `systemctl restart` would hand
# compose an empty log group. That is wrong — the loader's preserve pattern is
# five keys and has always included VELOCITYAI_ENVIRONMENT and
# VELOCITYAI_CW_LOG_GROUP (infra/scripts/velocityai-load-secrets.sh). The stated
# reason for running compose directly did not hold.
#
# The REAL reasons to invoke compose here, which do hold:
#   * This script must control the ORDER of pull -> pre-migration gate -> up ->
#     health gate -> rollback. `systemctl restart` collapses all of that into one
#     unit start with the pull in ExecStartPre, leaving nowhere to run the gate
#     between pulling and starting, and nothing to roll back to.
#   * A failed `systemctl restart` gives this script a unit exit code, not the
#     compose output it needs to attribute a failure to a specific service.
#   * velocityai-app.service declares Restart=on-failure/RestartSec=30s, so a
#     failing start becomes a crash loop that masks the failure instead of
#     surfacing it once, promptly, to the deploy.
# Compose is therefore invoked directly, with the interpolation inputs exported
# explicitly so the environment does not depend on loader timing either way.
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
# The four *_GZ values are gzip-then-base64 encoded repository files.
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
: "${SECRETS_LOADER_GZ:?SECRETS_LOADER_GZ was not injected by deploy.yml}"

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

# ── 1. Precondition: this box must have been provisioned at all ─────────────
# CHECKED FIRST, BEFORE THE FIRST-BOOT WAIT BELOW — the order matters.
#
# bootstrap.env is written by Terraform's compute module user_data (or by
# .github/scripts/remote-bootstrap.sh on a hand-created box) and is the only
# place the host's own identity (region, env tag, FQDN, param prefix) lives. Its
# absence means this box was never provisioned, so there is nothing a container
# redeploy can usefully do.
#
# This check used to sit AFTER the 15-minute first-boot wait. On a box that was
# never provisioned, Docker is also absent, so the wait ran to its full timeout
# polling for a sentinel that nothing was going to write — 15 minutes of SSM
# execution budget spent before reaching the test that could have answered in
# milliseconds. Worse, the timeout reported "timed out waiting for first-boot
# bootstrap" and pointed at velocityai-firstboot.service, which on such a box is
# not even installed; the actual problem was never diagnosed.
#
# Reordered: fail fast on the cheap, unambiguous condition, and only then wait
# for work that is genuinely in flight.
if [ ! -f "$BOOTSTRAP_ENV" ]; then
    echo "[deploy] FATAL: ${BOOTSTRAP_ENV} is missing — this instance is not bootstrapped." >&2
    echo "[deploy]        A container redeploy cannot provision a host. Run the 'Provision'" >&2
    echo "[deploy]        workflow for this environment (or, on a Terraform-managed box, apply" >&2
    echo "[deploy]        the app layer and let velocityai-firstboot.service run), then deploy." >&2
    exit 1
fi

# ── 2. Wait out first-boot self-provisioning ────────────────────────────────
# bootstrap.env exists, so this box HAS been provisioned or is being provisioned
# right now. On a freshly created instance the host install (Docker, Postgres,
# nginx, the systemd units, the first app start) runs asynchronously from
# user-data via velocityai-firstboot.service. If Docker is not on the box yet,
# wait for that to write its completion sentinel rather than racing it — and
# because §1 already confirmed bootstrap.env, the unit really is expected to be
# running, so waiting is the right thing rather than a guess.
# On an already provisioned host Docker is present and this whole block is
# skipped, so steady-state deploys pay nothing for it.
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

# ── 2a. Host identity ───────────────────────────────────────────────────────
# Sourced after the wait, not before it: on a box mid-provision, bootstrap.env is
# present but the rest of the host is not yet, and sourcing early would only make
# the mismatch gate below race the very bootstrap that writes the file.
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
# These four files are byte-for-byte repo content. CodeBuild read them from
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

# The loader is host code, not mutable bootstrap state. Refresh it atomically
# from this deploy before it materializes SSM values, so supported parameters
# can never be dropped merely because the instance predates an allowlist change.
unpack "$SECRETS_LOADER_GZ" "${APP_DIR}/velocityai-load-secrets.sh"
LOADER_TMP="$(mktemp /usr/local/bin/velocityai-load-secrets.XXXXXX)"
install -o root -g root -m 0755 "${APP_DIR}/velocityai-load-secrets.sh" "$LOADER_TMP"
mv "$LOADER_TMP" /usr/local/bin/velocityai-load-secrets

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
    # FIX-CWA-02: a degraded CloudWatch agent used to ALWAYS be report-and-
    # continue, regardless of environment — so a deploy could report full
    # success ("Deploy succeeded.") on stage/prod while observability was
    # silently blind. Monitoring gaps on stage/prod are a release-blocking
    # condition; on dev they remain a warning so day-to-day iteration isn't
    # gated on the agent's health. Set VELOCITYAI_ALLOW_DEGRADED_MONITORING=1
    # in bootstrap.env as an explicit, auditable break-glass override for a
    # stage/prod deploy that must proceed despite the degradation.
    ALLOW_DEGRADED="${VELOCITYAI_ALLOW_DEGRADED_MONITORING:-0}"
    if { [ "$DEPLOY_ENV" = "stage" ] || [ "$DEPLOY_ENV" = "prod" ]; } && [ "$ALLOW_DEGRADED" != "1" ]; then
        echo "[deploy] FATAL: reconcile-host-config.sh exited ${RECONCILE_STATUS} (CloudWatch agent DEGRADED) on '${DEPLOY_ENV}'." >&2
        echo "[deploy]        Observability is a release gate on stage/prod — refusing to report success while monitoring is blind." >&2
        echo "[deploy]        See /var/log/velocityai-reconcile.log on the host for the specific failure." >&2
        echo "[deploy]        Break-glass: set VELOCITYAI_ALLOW_DEGRADED_MONITORING=1 in /etc/velocityai/bootstrap.env to override." >&2
        exit 1
    fi
    echo "[deploy] WARNING: reconcile-host-config.sh exited ${RECONCILE_STATUS} (CloudWatch agent DEGRADED)" >&2
    echo "[deploy]          see /var/log/velocityai-reconcile.log — continuing with the app deploy (env=${DEPLOY_ENV})." >&2
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

# ── 7. Re-assert the image pins (AFTER the loader) ──────────────────────────
# Only the two *_IMAGE lines. This step used to also rewrite
# VELOCITYAI_ENVIRONMENT and VELOCITYAI_CW_LOG_GROUP, on the stated grounds that
# "velocityai-load-secrets preserves only ^(BACKEND_IMAGE|FRONTEND_IMAGE|ENV)=".
# That is not what the loader does. Its actual preserve pattern
# (infra/scripts/velocityai-load-secrets.sh) is
#   ^(BACKEND_IMAGE|FRONTEND_IMAGE|ENV|VELOCITYAI_ENVIRONMENT|VELOCITYAI_CW_LOG_GROUP)=
# — FIVE keys, and it has been five in both the canonical loader and the copy
# bootstrap installs. So the two VELOCITYAI_* lines were already surviving the
# loader, and re-writing them here achieved nothing except to make this script a
# second author of values §11 owns. Worse, it wrote them from $HOST_ENV, so the
# two sites could disagree about the log group after an environment retag.
#
#   BACKEND_IMAGE / FRONTEND_IMAGE  the DIGEST-pinned reference for the image
#       this deploy resolved (repo@sha256:...). These genuinely must be written
#       here — they are the one thing this deploy knows that §11 does not.
#       Written by rewriting the file rather than by `sed -i 's|^KEY=.*|...|'`
#       because sed exits 0 having changed nothing when the pattern is absent —
#       a silent no-op that restarts the box on the PREVIOUS image while
#       reporting success.
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
    # Strip ONLY the two keys this step re-writes. Everything else — including
    # VELOCITYAI_ENVIRONMENT and VELOCITYAI_CW_LOG_GROUP, which §11 owns and the
    # loader preserves — is carried through untouched.
    grep -vE '^(BACKEND_IMAGE|FRONTEND_IMAGE)=' "$APP_ENV" >> "$TMP_ENV" || true
fi
{
    echo "BACKEND_IMAGE=${BACKEND_IMAGE_REF}"
    echo "FRONTEND_IMAGE=${FRONTEND_IMAGE_REF}"
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

# ── 10a. Pre-migration gate: users must be cleanly Cognito-linked ───────────
# Migrations do NOT run as a deploy step — backend/docker-entrypoint.sh runs
# `alembic upgrade head` under `set -eu` before `exec uvicorn`. So a migration
# that refuses to apply never reports a failed step: the container exits,
# `restart: unless-stopped` loops it, :8000 is never bound, and the §11 health
# gate burns its full five minutes before rolling the images back. The operator
# sees "health gate failed", not the actual cause.
#
# Migration 0038 (Cognito-only users) has exactly that shape: it aborts when any
# `users` row is not cleanly Cognito-linked (NULL/duplicate `cognito_sub`, or a
# residual non-'cognito' `auth_provider`), because dropping `password_hash`
# would otherwise leave an account with no way to authenticate at all. The
# cutover runbook says to check for this first, but that was a MANUAL step with
# nothing enforcing it.
#
# So assert it here, before anything mutates: fail fast, name the rows, and
# leave the currently-healthy stack untouched and serving.
#
# Three details matter:
#   --entrypoint python  bypasses docker-entrypoint.sh. Without it this very
#                        command would run `alembic upgrade head` — the thing
#                        being gated.
#   --no-deps            does not drag the frontend up as a dependency.
#   run (not exec)       a one-off container against the NEW image; `exec`
#                        would need a running container and would use the OLD
#                        one, whose migration requirements may differ.
# `run` does not publish ports (that needs --service-ports), so this cannot
# collide with the live backend on :8000. The script is read-only, and reads
# DATABASE_URL from the same env_file the service uses.
echo "[deploy] pre-migration gate: checking users are cleanly Cognito-linked..."
if ! docker compose -f docker-compose.yml -f docker-compose.prod.yml \
        run --rm --no-deps --entrypoint python backend \
        scripts/migrate_local_users_to_cognito.py --report --fail-on-unlinked; then
    echo "[deploy] FATAL: pre-migration gate FAILED — one or more users rows are not" >&2
    echo "[deploy]        cleanly Cognito-linked, so 'alembic upgrade head' would abort" >&2
    echo "[deploy]        inside the backend container and crash-loop it." >&2
    echo "[deploy]        Resolve the rows listed above, then re-run this deploy:" >&2
    echo "[deploy]          scripts/migrate_local_users_to_cognito.py --link --apply" >&2
    echo "[deploy]          scripts/migrate_local_users_to_cognito.py --invite --apply" >&2
    echo "[deploy]        See docs/runbooks/cognito-cutover.md step 1." >&2
    echo "[deploy]        NOTE: nothing was changed — the previous stack is still running." >&2
    exit 1
fi
echo "[deploy] pre-migration gate passed"

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
# moments ago, still present in the local Docker cache (within THIS run only —
# §12 prunes the superseded image after a healthy deploy, so a later manual
# rollback needs a digest-exact ECR pull), no registry round-trip
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

    # Bootstrap-admin step removed: Cognito-only. See docs/architecture/authentication-and-authorization.md.

    # ── 12. Prune unused Docker images ───────────────────────────────────────
    # Every deploy pulls a NEW backend/frontend image by digest (§7-§10) but
    # never removed the one it replaced, so pulled images accumulate on the
    # box's local disk (the root/data EBS volume) without bound across enough
    # deploys.
    #
    # `docker image prune -af` deletes every LOCAL image not referenced by any
    # container, running OR stopped. That "referenced by any container" check
    # is Docker's own prune logic, not this script's — it is structurally
    # impossible for this command to remove an image backing a container that
    # still exists, so the backend/frontend images the health gate just
    # confirmed healthy above can never be touched by it. `-a` additionally
    # removes untagged/dangling images (leftover intermediate layers from
    # earlier `docker compose pull`s); `-f` skips prune's interactive
    # confirmation, which SSM RunCommand has no terminal to answer.
    #
    # Placement matters: run ONLY here, in the HEALTHY branch, AFTER the
    # health gate and the compose `up -d` that started this deploy's
    # containers — never before them, or the prune could race the very
    # containers being created.
    #
    # Does not weaken this script's own rollback: the FAILURE branch further
    # below (restoring PREV_BACKEND_IMAGE/PREV_FRONTEND_IMAGE from local Docker
    # cache with no registry round-trip) is mutually exclusive with this
    # HEALTHY branch — a deploy that reaches this line has already passed the
    # gate and will never take that path in the same run. A LATER, separate
    # deploy that then fails still rolls back correctly onto the image it is
    # itself replacing (this deploy's, which is still running and therefore
    # still protected by prune's own container-reference check). Rolling back
    # further than that one previous release already required a fresh —
    # digest-exact, so still byte-identical — ECR pull before this step
    # existed too, since app.env's BACKEND_IMAGE/FRONTEND_IMAGE (§7) only ever
    # remembers ONE previous pin. Non-fatal: a prune failure (e.g. the Docker
    # daemon busy with another operation) must not turn an already-verified-
    # healthy deploy into a reported failure.
    echo "[deploy] pruning local Docker images not referenced by any container..."
    set +e
    docker image prune -af
    PRUNE_RC=$?
    set -e
    if [ "$PRUNE_RC" -ne 0 ]; then
        echo "[deploy] WARNING: docker image prune exited ${PRUNE_RC} (non-fatal — deploy already succeeded)" >&2
    fi
    docker system df >&2 || true

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
