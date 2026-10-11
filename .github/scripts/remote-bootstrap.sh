#!/bin/bash
# =============================================================================
# On-host PROVISIONING wrapper — executed ON THE EC2 INSTANCE by SSM RunCommand.
# =============================================================================
# Invoked by .github/workflows/provision.yml, which builds the payload it sends
# as (same shape as .github/scripts/remote-deploy.sh's payload):
#
#     #!/bin/bash
#     DEPLOY_ENV='dev'
#     REGION='eu-central-1'
#     PARAM_PREFIX='/velocityai/dev'
#     BACKUP_BUCKET='velocityai-dev-pg-dumps-<account>'
#     KMS_KEY_ID='arn:aws:kms:...'
#     FQDN='dev.velocityai.example.com'
#     ECR_REGISTRY='<account>.dkr.ecr.eu-central-1.amazonaws.com'
#     ACME_EMAIL='platform@example.com'
#     DATA_DEVICE='/dev/nvme1n1'
#     BOOTSTRAP_SHA256='<sha256 of the bootstrap-ec2.sh CI just uploaded>'
#     FORCE='0'
#     DRY_RUN='0'
#     SKIP_DB_PASSWORD_CHECK='0'
#     ...the entire contents of this file...
#
# WHAT THIS REPLACES
# ------------------
# On a Terraform-provisioned box, `infra/terraform/modules/compute/user_data.sh.tpl`
# does three things at first boot: (1) writes /etc/velocityai/bootstrap.env from
# rendered `${...}` template variables, (2) installs a minimal AWS CLI, and
# (3) installs + starts `velocityai-firstboot.service`, a detached systemd unit
# that fetches `bootstrap-ec2.sh` from S3 and runs it — because user-data IS
# cloud-init's final stage, and bootstrap-ec2.sh's own `cloud-init status --wait`
# would deadlock if called synchronously from here.
#
# A hand-created EC2 instance never runs user_data.sh.tpl (nothing rendered it,
# nothing installed the unit) and never gets `bootstrap-ec2.sh` onto its disk
# (nothing uploaded it to S3 — that upload is `aws_s3_object.bootstrap_script`
# in `infra/terraform/app/main.tf`, an apply this box never had). This script
# is the CI/CD replacement for BOTH gaps at once: `.github/workflows/provision.yml`
# uploads the six config objects (S3, from the runner) BEFORE sending this
# payload, and this script fills in the rest of user_data.sh.tpl's job, then
# runs `bootstrap-ec2.sh` itself (synchronously — no first-boot deadlock here,
# because this is not cloud-init).
#
# WHY IT ALSO INSTALLS velocityai-firstboot.service
# --------------------------------------------------
# Not just Terraform parity for its own sake: without it, a REPLACED or
# rebuilt instance (new EBS root, same data volume re-attached) would need a
# human to re-run this workflow by hand before the box could self-provision.
# Installing the same sentinel-guarded unit here means a reboot or a fresh
# instance recovers by itself, exactly like the Terraform path — the unit
# only NEEDS `/etc/velocityai/bootstrap.env` to already exist on disk, which
# this script writes unconditionally on every run (see §2 below).
#
# THE THREE GATES, IN ORDER
# --------------------------
#   A. Sentinel present + FORCE!=1  -> exit 0 immediately. No side effects at
#      all — not even the bootstrap.env rewrite in §2 — so a routine re-run of
#      this workflow against an already-provisioned box is a safe no-op.
#   B. bootstrap.env already exists and its VELOCITYAI_ENVIRONMENT disagrees
#      with the injected DEPLOY_ENV -> abort. Mirrors remote-deploy.sh's own
#      host/deploy environment-mismatch gate; the failure mode it prevents
#      (this environment's job silently reconfiguring another environment's
#      box) is identical here.
#   C. SSM prefix's DATABASE_PASSWORD parameter must exist (checked by NAME
#      only — `--query 'Parameter.Name'`, no `--with-decryption`, so the value
#      never reaches this log) -> fresh-provision path fails in seconds
#      instead of ~4 minutes into bootstrap-ec2.sh §6. Skippable via
#      SKIP_DB_PASSWORD_CHECK=1 for a box whose Postgres data dir already
#      exists (recovery mode never reads this parameter).
#
#      Gate C cannot always run where it is written: on a bare box the aws CLI
#      does not exist until §2 installs it, so the check is DEFERRED to §2a.
#      That deferral interacts with DRY_RUN, which exits before §2a — so a dry
#      run on a box without the CLI cannot complete Gate C and FAILS rather than
#      reporting "all gates passed". It previously reported success, which is the
#      one outcome a dry run must never get wrong: its entire purpose is to tell
#      an operator whether the real run will work.
#
# THREE-WAY OUTCOME on the bootstrap-ec2.sh run itself (its own §20 writes the
# completion sentinel BEFORE exiting non-zero on a degraded subsystem, so exit
# code alone cannot distinguish "failed" from "provisioned but degraded"):
#   rc=0                          -> SUCCESS
#   rc!=0, sentinel present       -> DEGRADED (host usable, exits non-zero so
#                                     CI still reports it loudly)
#   rc!=0, sentinel absent        -> FAILED (host not usable)
# =============================================================================

# SSM's AWS-RunShellScript invokes the payload with /bin/sh (dash on Ubuntu) —
# the interpreter is chosen by the agent, so the shebang above is NOT honoured
# and `set -o pipefail` would abort with "Illegal option -o pipefail". Re-exec
# under bash on the first executable line, same as remote-deploy.sh. Must stay
# POSIX-compatible so dash can parse this line before bash takes over.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi

set -euo pipefail
exec > >(tee -a /var/log/velocityai-provision.log) 2>&1

echo "[provision] start $(date -u --iso-8601=seconds)"

if [ "$(id -u)" -ne 0 ]; then
    echo "[provision] FATAL: must run as root (or via sudo)" >&2
    exit 1
fi

# ── Inputs (injected as literal assignments above this file) ────────────────
: "${DEPLOY_ENV:?DEPLOY_ENV was not injected by provision.yml}"
: "${REGION:?REGION was not injected by provision.yml}"
: "${BACKUP_BUCKET:?BACKUP_BUCKET was not injected by provision.yml}"
: "${KMS_KEY_ID:?KMS_KEY_ID was not injected by provision.yml}"
: "${FQDN:?FQDN was not injected by provision.yml}"
: "${ECR_REGISTRY:?ECR_REGISTRY was not injected by provision.yml}"
: "${ACME_EMAIL:?ACME_EMAIL was not injected by provision.yml}"
: "${BOOTSTRAP_SHA256:?BOOTSTRAP_SHA256 was not injected by provision.yml}"

PARAM_PREFIX="${PARAM_PREFIX:-/velocityai/${DEPLOY_ENV}}"
DATA_DEVICE="${DATA_DEVICE:-/dev/nvme1n1}"
FORCE="${FORCE:-0}"
DRY_RUN="${DRY_RUN:-0}"
SKIP_DB_PASSWORD_CHECK="${SKIP_DB_PASSWORD_CHECK:-0}"

ETC_DIR=/etc/velocityai
BOOTSTRAP_ENV="${ETC_DIR}/bootstrap.env"
SENTINEL=/var/lib/velocityai/.bootstrap-done

echo "[provision] env=${DEPLOY_ENV} region=${REGION} prefix=${PARAM_PREFIX} bucket=${BACKUP_BUCKET} fqdn=${FQDN} force=${FORCE} dry_run=${DRY_RUN}"

# ── Gate A: already provisioned ──────────────────────────────────────────────
if [ -f "$SENTINEL" ]; then
    if [ "$FORCE" != "1" ]; then
        echo "[provision] host already bootstrapped at $(cat "$SENTINEL") — nothing to do."
        echo "[provision]        Re-run this workflow with force=true to provision again (this restarts the app stack)."
        exit 0
    fi
    echo "[provision] sentinel present but force=1 — re-running bootstrap-ec2.sh (idempotent; the app stack WILL restart)."
fi

# ── Gate B: environment identity must not already disagree ──────────────────
if [ -f "$BOOTSTRAP_ENV" ]; then
    # shellcheck source=/dev/null
    . "$BOOTSTRAP_ENV"
    HOST_ENV="${VELOCITYAI_ENVIRONMENT:-}"
    if [ -n "$HOST_ENV" ] && [ "$HOST_ENV" != "$DEPLOY_ENV" ]; then
        echo "[provision] FATAL: environment mismatch — this host is already configured as '${HOST_ENV}', this run targets '${DEPLOY_ENV}'." >&2
        echo "[provision]        Refusing to overwrite. Check EC2_INSTANCE_ID on the '${DEPLOY_ENV}' GitHub Environment and this instance's Environment tag." >&2
        exit 1
    fi
fi

# ── Gate C: fresh-provision prerequisite ─────────────────────────────────────
# Name-only lookup — no --with-decryption — so the password value never
# reaches this command's output or this log.
# This check cannot run unconditionally HERE: on a fresh box the aws CLI is
# not installed until §2 below. The previous form swallowed stderr and judged
# only the exit code, so a missing `aws` binary — or any API error — was
# reported as "parameter does not exist", which sent diagnosis chasing a
# phantom missing secret for a parameter that was present all along. So:
# surface what aws actually said, and when the CLI is absent DEFER the check
# to §2a rather than guessing.
check_db_password_param() {
    err="$(aws ssm get-parameter \
             --name "${PARAM_PREFIX}/DATABASE_PASSWORD" \
             --region "$REGION" \
             --query 'Parameter.Name' --output text 2>&1 >/dev/null)" && rc=0 || rc=$?
    if [ "$rc" -eq 0 ]; then
        echo "[provision] OK: ${PARAM_PREFIX}/DATABASE_PASSWORD exists (value not read)."
        return 0
    fi
    echo "[provision] FATAL: could not verify ${PARAM_PREFIX}/DATABASE_PASSWORD." >&2
    echo "[provision]        aws reported: ${err}" >&2
    echo "[provision]        bootstrap-ec2.sh needs it to create the postgres role on a fresh box." >&2
    echo "[provision]        If it is genuinely absent, create it (SecureString):" >&2
    echo "[provision]          aws ssm put-parameter --name ${PARAM_PREFIX}/DATABASE_PASSWORD --type SecureString --value '<random>' --region ${REGION}" >&2
    echo "[provision]        If this box's Postgres data dir already exists (recovery mode), re-run with SKIP_DB_PASSWORD_CHECK=1." >&2
    return 1
}

DB_PASSWORD_CHECK_DEFERRED=0
if [ "$SKIP_DB_PASSWORD_CHECK" != "1" ]; then
    if command -v aws >/dev/null 2>&1; then
        check_db_password_param || exit 1
    else
        DB_PASSWORD_CHECK_DEFERRED=1
        echo "[provision] aws CLI not present yet — deferring the ${PARAM_PREFIX}/DATABASE_PASSWORD check until §2 installs it."
    fi
else
    echo "[provision] SKIP_DB_PASSWORD_CHECK=1 — not checking for ${PARAM_PREFIX}/DATABASE_PASSWORD."
fi

if [ "$DRY_RUN" = "1" ]; then
    # A dry run must not claim "all gates passed" when one of them never ran.
    # Gate C is deferred to §2a when the aws CLI is absent, but §2a is past the
    # dry-run exit — so on a bare box (exactly the box a dry run is most useful
    # for) the script previously printed "all gates passed" having never verified
    # DATABASE_PASSWORD. An operator would then start a real provision believing
    # the prerequisite was confirmed, and hit the failure ~4 minutes into
    # bootstrap-ec2.sh §6 instead.
    #
    # Installing the CLI to resolve it is not an option: that is a write, and a
    # dry run promises none. So this is a hard failure with the one instruction
    # that fixes it.
    if [ "$DB_PASSWORD_CHECK_DEFERRED" = "1" ]; then
        echo "[provision] FATAL: DRY_RUN cannot verify ${PARAM_PREFIX}/DATABASE_PASSWORD on this host." >&2
        echo "[provision]        The aws CLI is not installed yet, and installing it would be a write — which DRY_RUN must not perform." >&2
        echo "[provision]        Gate C therefore did NOT run, so this is not a clean dry run." >&2
        echo "[provision]        Options:" >&2
        echo "[provision]          - verify the parameter yourself from anywhere with credentials:" >&2
        echo "[provision]              aws ssm get-parameter --name ${PARAM_PREFIX}/DATABASE_PASSWORD --query 'Parameter.Name' --region ${REGION}" >&2
        echo "[provision]          - or re-run with SKIP_DB_PASSWORD_CHECK=1 if this box's Postgres data dir already exists (recovery mode never reads it)" >&2
        echo "[provision]          - or run the real provision (dry_run=false), where §2a runs the check after installing the CLI" >&2
        exit 1
    fi
    echo "[provision] DRY_RUN=1 — all gates passed; stopping before any write."
    exit 0
fi

# ── 1. Write /etc/velocityai/bootstrap.env ───────────────────────────────────
# Same content Terraform's user_data.sh.tpl renders from `${...}` template
# variables, written here as a plain heredoc instead. Written unconditionally
# on every non-dry-run pass (even a FORCE re-run) so a config change (rotated
# FQDN, new bucket, etc.) on the GitHub Environment reaches the box on the next
# provision, the same way bootstrap-ec2.sh itself is safe to re-run.
mkdir -p "$ETC_DIR"
TMP_ENV="$(mktemp "${ETC_DIR}/bootstrap.env.XXXXXX")"
cat > "$TMP_ENV" <<EOF
VELOCITYAI_ENVIRONMENT=${DEPLOY_ENV}
VELOCITYAI_REGION=${REGION}
VELOCITYAI_PARAM_PREFIX=${PARAM_PREFIX}
VELOCITYAI_DATA_DEVICE=${DATA_DEVICE}
VELOCITYAI_BACKUP_BUCKET=${BACKUP_BUCKET}
VELOCITYAI_KMS_KEY_ID=${KMS_KEY_ID}
VELOCITYAI_FQDN=${FQDN}
VELOCITYAI_ECR_REGISTRY=${ECR_REGISTRY}
VELOCITYAI_ACME_EMAIL=${ACME_EMAIL}
EOF
chmod 0644 "$TMP_ENV"
mv "$TMP_ENV" "$BOOTSTRAP_ENV"
echo "[provision] wrote ${BOOTSTRAP_ENV}"

# ── 2. AWS CLI v2 assurance (mirrors bootstrap-ec2.sh §2b / user_data.sh.tpl) ─
#
# apt_force_https, apt_wait_lock and install_awscli_v2 come from
# infra/scripts/lib/host-common.sh, which provision.yml INLINES into this payload
# immediately above this script (see "Build SSM provision payload"). It cannot be
# fetched from disk here: this script is the first thing to run on a hand-created
# box and no file exists on it yet, which is the whole reason the payload is
# assembled rather than referenced.
#
# The three helpers, and the AWSCLI_VERSION pin, previously existed as a second
# verbatim copy in this file. R-05/R-06 removed the duplication; the rationale for
# each (443-only egress, the unmatched-glob abort, the bounded lock wait) now lives
# once, in the library.
if ! command -v apt_force_https >/dev/null 2>&1; then
    echo "[provision] FATAL: host-common.sh was not inlined into this payload." >&2
    echo "[provision]        provision.yml must cat infra/scripts/lib/host-common.sh" >&2
    echo "[provision]        after the prelude and before this script." >&2
    exit 1
fi

# SC2034 disabled with cause: this variable is READ, just not anywhere ShellCheck
# can see. `infra/scripts/lib/host-common.sh` defaults it
# (`: "${HOST_COMMON_LOG_PREFIX:=[host]}"`) and both `_hc_log` and `_hc_err` echo
# it on every line they emit. provision.yml INLINES that library into this
# payload (see the note at the top of this block), so there is no source
# directive for ShellCheck to follow and it concludes the assignment is dead.
# Exporting instead would also silence SC2034 but would leak the value into every
# child process for no reason. Do not delete the assignment: the library would
# fall back to "[host]" and provisioning output would stop being attributable.
# shellcheck disable=SC2034
HOST_COMMON_LOG_PREFIX="[provision]"

apt_force_https
apt_wait_lock

# `apt-get update` exits 0 even when every index fetch fails (it warns and
# reuses stale lists), so a failure here would otherwise surface as an opaque
# `exit status 100` from the install below. Assert reachability explicitly.
apt-get update -y
if ! apt-get install -y --no-install-recommends curl unzip ca-certificates jq; then
    echo "[provision] FATAL: apt could not install the provisioning prerequisites." >&2
    echo "[provision]        Sources are HTTPS, so this is not the port-80 egress issue." >&2
    echo "[provision]        Check the security group's outbound 443 and the Transit Gateway path." >&2
    exit 1
fi

install_awscli_v2

# ── 2a. Deferred Gate C ───────────────────────────────────────────────────────
# Runs only when Gate C above could not: the aws CLI did not exist yet. Still
# ahead of bootstrap-ec2.sh, so a genuinely absent parameter fails before any
# Postgres role is created.
if [ "$DB_PASSWORD_CHECK_DEFERRED" = "1" ]; then
    echo "[provision] running the deferred ${PARAM_PREFIX}/DATABASE_PASSWORD check now that the aws CLI is available."
    check_db_password_param || exit 1
fi

# ── 3. Install the first-boot self-heal unit (Terraform user_data.sh.tpl parity) ─
# Guarded by the same ConditionPathExists as the Terraform path, so installing
# it here is safe even when bootstrap-ec2.sh below is about to run and write
# the sentinel itself — the unit simply never fires because the condition is
# already false by the time anything would start it after this point.
install -d -m 0755 /opt/velocityai

cat >/opt/velocityai/run-firstboot-bootstrap.sh <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
exec > >(tee -a /var/log/velocityai-firstboot.log) 2>&1
echo "[firstboot] $(date -u +%FT%TZ) fetching bootstrap-ec2.sh from S3"
# shellcheck source=/dev/null
. /etc/velocityai/bootstrap.env
: "${VELOCITYAI_BACKUP_BUCKET:?VELOCITYAI_BACKUP_BUCKET missing}"
REGION="${VELOCITYAI_REGION:-eu-central-1}"
for i in $(seq 1 30); do
    if aws s3 cp "s3://${VELOCITYAI_BACKUP_BUCKET}/config/bootstrap-ec2.sh" \
         /opt/velocityai/bootstrap-ec2.sh --region "${REGION}"; then
        break
    fi
    # Last failed attempt is fatal: without it the loop falls through and runs
    # whatever stale bootstrap-ec2.sh an earlier run left on disk (REL-21).
    # POSIX test only: this wrapper is written from a quoted heredoc.
    [ "$i" -lt 30 ] || { echo "[firstboot] FATAL: could not fetch bootstrap-ec2.sh after 30 attempts" >&2; exit 1; }
    echo "[firstboot] bootstrap-ec2.sh not available yet (attempt $i) — retrying"
    sleep 10
done
chmod 0755 /opt/velocityai/bootstrap-ec2.sh
echo "[firstboot] running bootstrap-ec2.sh"
bash /opt/velocityai/bootstrap-ec2.sh
WRAP
chmod 0755 /opt/velocityai/run-firstboot-bootstrap.sh

cat >/etc/systemd/system/velocityai-firstboot.service <<'UNIT'
[Unit]
Description=VelocityAI first-boot full host bootstrap (Postgres, nginx, Docker, app)
After=cloud-init.target network-online.target
Wants=network-online.target
ConditionPathExists=!/var/lib/velocityai/.bootstrap-done

[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=1800
ExecStart=/opt/velocityai/run-firstboot-bootstrap.sh

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable velocityai-firstboot.service
echo "[provision] velocityai-firstboot.service installed + enabled — a future reboot or rebuilt instance self-heals without a CI run."

# ── 4. Fetch + checksum-verify + run bootstrap-ec2.sh, synchronously ────────
# Unlike the Terraform first-boot path, this call is NOT inside cloud-init, so
# there is no deadlock risk in running it directly and waiting on it.
for i in $(seq 1 30); do
    if aws s3 cp "s3://${BACKUP_BUCKET}/config/bootstrap-ec2.sh" \
         /opt/velocityai/bootstrap-ec2.sh --region "$REGION"; then
        break
    fi
    echo "[provision] config/bootstrap-ec2.sh not available in S3 yet (attempt $i) — retrying"
    if [ "$i" = "30" ]; then
        echo "[provision] FATAL: could not fetch config/bootstrap-ec2.sh from S3 after 30 attempts." >&2
        echo "[provision]        Confirm provision.yml's upload step succeeded and BACKUP_BUCKET is correct." >&2
        exit 1
    fi
    sleep 10
done

# Integrity gate: this is what replaces "Terraform's own apply put it there" —
# the object CI just uploaded is verified byte-for-byte against the checksum
# computed on the runner BEFORE this script ever executes it as root.
ACTUAL_SHA256="$(sha256sum /opt/velocityai/bootstrap-ec2.sh | awk '{print $1}')"
if [ "$ACTUAL_SHA256" != "$BOOTSTRAP_SHA256" ]; then
    echo "[provision] FATAL: bootstrap-ec2.sh checksum mismatch." >&2
    echo "[provision]        expected ${BOOTSTRAP_SHA256}" >&2
    echo "[provision]        got      ${ACTUAL_SHA256}" >&2
    echo "[provision]        The uploaded object may be stale, corrupted, or tampered with — refusing to execute it." >&2
    exit 1
fi
echo "[provision] OK: bootstrap-ec2.sh checksum verified (${ACTUAL_SHA256})"
chmod 0755 /opt/velocityai/bootstrap-ec2.sh

echo "[provision] running bootstrap-ec2.sh (idempotent, ~6 minutes)..."
set +e
bash /opt/velocityai/bootstrap-ec2.sh
BOOTSTRAP_RC=$?
set -e

# ── 5. Three-way outcome ──────────────────────────────────────────────────────
# bootstrap-ec2.sh §20 writes the sentinel BEFORE exiting non-zero on a
# degraded subsystem (its own comment: "the sentinel is STATE, the non-zero
# exit is the SIGNAL"), so the sentinel's presence — not the exit code alone —
# is what distinguishes a usable-but-degraded host from a genuine failure.
if [ "$BOOTSTRAP_RC" -eq 0 ]; then
    echo "[provision] SUCCESS: bootstrap-ec2.sh completed cleanly."
    exit 0
fi

if [ -f "$SENTINEL" ]; then
    echo "[provision] DEGRADED: bootstrap-ec2.sh exited ${BOOTSTRAP_RC} but the host IS provisioned (sentinel present at $(cat "$SENTINEL"))." >&2
    echo "[provision]           See the '[bootstrap] DEGRADED:' line in /var/log/velocityai-bootstrap.log for which subsystem." >&2
    exit "$BOOTSTRAP_RC"
fi

echo "[provision] FAILED: bootstrap-ec2.sh exited ${BOOTSTRAP_RC} and no sentinel was written — the host is NOT fully provisioned." >&2
echo "[provision]         check: /var/log/velocityai-bootstrap.log" >&2
echo "[provision]         check: journalctl -u velocityai-firstboot.service" >&2
exit "$BOOTSTRAP_RC"
