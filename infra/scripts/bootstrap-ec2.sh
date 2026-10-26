#!/usr/bin/env bash
# VelocityAI production EC2 bootstrap.
#
# Materialized form of docs/SIMPLE_AWS_DEPLOYMENT.md Appendix D — runnable,
# idempotent, ~6 minutes wall-clock on a clean box.
#
# Detects two modes at run:
#   - Fresh provision (data volume blank): formats + initdb, generates DB
#     password into SSM, installs all packages, fetches docker-compose.yml,
#     authenticates to ECR, brings up velocityai-app.service.
#   - Recovery from snapshot (data volume already has xfs + a Postgres
#     data dir): skips initdb, reuses existing DB password from SSM,
#     same Docker / ECR / image-pull path.
#
# Invocation: this is normally run from the EC2's first-boot phase via SSM
# RunCommand AFTER cloud-init has placed /etc/velocityai/bootstrap.env on disk
# (Terraform's module.compute writes that file from user_data.sh.tpl).
# To run manually after a Terraform apply:
#   aws ssm send-command \
#     --document-name AWS-RunShellScript \
#     --instance-ids <i-...> \
#     --parameters 'commands=["bash -s"]' \
#     --cli-input-json '...' < infra/scripts/bootstrap-ec2.sh
#
# Or copy the file to the box and run `sudo bash bootstrap-ec2.sh`.

set -euo pipefail
exec > >(tee -a /var/log/velocityai-bootstrap.log) 2>&1
echo "[bootstrap] start $(date -u --iso-8601=seconds)"

if [[ "$EUID" -ne 0 ]]; then
    echo "[bootstrap] ERROR: must run as root (or via sudo)" >&2
    exit 1
fi

# ── Degraded-completion accumulator ────────────────────────────────────
# Some checks must be LOUD but must NOT abort the run. Aborting mid-script
# strands every later section (see the rationale block above §14a), which is
# strictly worse than finishing with a reported defect. Such a check appends a
# short tag here; §20 writes the completion sentinel, prints the tags and exits
# non-zero — the box ends up fully provisioned AND the invoking SSM command /
# CI step reports failure.
BOOTSTRAP_DEGRADED=()

# ── 0. Wait for cloud-init to finish ───────────────────────────────────
# Must come BEFORE sourcing /etc/velocityai/bootstrap.env: that file is written
# by user_data which runs as cloud-init's final stage. `aws ec2 wait
# instance-status-ok` only confirms system reachability; on a fast SSM dispatch
# the box can report status-ok before cloud-init's final stage has written
# bootstrap.env, and we'd die at the file-existence check below.
#
# This used to be `while ! cloud-init status --wait; do sleep 2; done`, which
# never terminates when cloud-init has settled into the `error` state: --wait
# returns non-zero immediately and forever, so the loop span until the SSM
# execution timeout killed it 30 minutes later with no diagnosis in the log.
# Bounded and state-aware instead:
#   done    -> proceed normally
#   error   -> WARN and proceed. cloud-init reports `error` for any failed
#              module, including ones this script does not depend on, and §1
#              below already fails hard if bootstrap.env is genuinely absent.
#              Refusing to continue here would turn a cosmetic module failure
#              into an unprovisionable host.
#   timeout -> abort. Ten minutes without cloud-init reaching a terminal state
#              means the box is not in a state worth provisioning, and failing
#              now leaves a legible error instead of a mystery hang.
echo "[bootstrap] waiting for cloud-init final stage..."
timeout 600 cloud-init status --wait > /dev/null 2>&1 || true
CLOUD_INIT_STATUS="$(cloud-init status 2>/dev/null | awk -F': *' '/^status:/ {print $2}')"
case "$CLOUD_INIT_STATUS" in
    done)
        echo "[bootstrap] cloud-init finished (status: done)"
        ;;
    error)
        echo "[bootstrap] WARNING: cloud-init reports status 'error'. Continuing — §1 below verifies /etc/velocityai/bootstrap.env directly." >&2
        echo "[bootstrap]          investigate: cloud-init status --long; journalctl -u cloud-final" >&2
        ;;
    *)
        echo "[bootstrap] ERROR: cloud-init did not reach a terminal state within 600s (status: '${CLOUD_INIT_STATUS:-unknown}')." >&2
        echo "[bootstrap]        investigate: cloud-init status --long; journalctl -u cloud-final" >&2
        exit 1
        ;;
esac

# ── 1. Source operator-controlled values written by user_data ──────────
#
# /etc/velocityai/bootstrap.env is created by Terraform's compute module user_data
# (see infra/modules/compute/user_data.sh.tpl). It carries:
#   VELOCITYAI_REGION         — AWS region (e.g. eu-central-1)
#   VELOCITYAI_PARAM_PREFIX   — SSM Parameter Store prefix, e.g. /velocityai/prod
#   VELOCITYAI_ENVIRONMENT    — short env tag (prod / staging / …)
#   VELOCITYAI_FQDN           — public hostname (nip.io or Route 53)
#   VELOCITYAI_KMS_KEY_ID     — project CMK ARN/alias for backup encryption
#   VELOCITYAI_BACKUP_BUCKET  — S3 bucket for pg_dump + skills tarballs
#   VELOCITYAI_ECR_REGISTRY   — <ACCOUNT>.dkr.ecr.<region>.amazonaws.com
#   VELOCITYAI_ACME_EMAIL     — email for Let's Encrypt registration
#   VELOCITYAI_DATA_DEVICE    — (optional) block device for the Postgres data
#                               volume; defaults to /dev/nvme1n1
#
# This script takes NO image tag from its caller. Which images the host runs is
# resolved in §10b from the SSM ${PARAM_PREFIX}/deploy/* parameters that
# .github/workflows/deploy.yml records after a successful health gate, falling
# back to S3 config/deploy.env for the pre-first-deploy state. There used to be a
# VELOCITYAI_IMAGE_TAG input defaulting to "latest"; see §10b for why that
# default could never resolve against an IMMUTABLE ECR repository.
#
# docker-compose.yml is downloaded from s3://$VELOCITYAI_BACKUP_BUCKET/config/,
# uploaded by Terraform's aws_s3_object.compose_yaml on a Terraform-managed box,
# by .github/workflows/provision.yml on a hand-created one, and refreshed on
# every deploy by deploy.yml's "Refresh host config artifacts in S3" step.
# The EC2 needs no git auth.
if [[ ! -f /etc/velocityai/bootstrap.env ]]; then
    echo "[bootstrap] ERROR: /etc/velocityai/bootstrap.env missing — terraform apply hasn't completed?" >&2
    exit 1
fi
# shellcheck source=/dev/null
. /etc/velocityai/bootstrap.env

REGION="${VELOCITYAI_REGION:-eu-central-1}"
DOMAIN="${VELOCITYAI_FQDN:?VELOCITYAI_FQDN missing in /etc/velocityai/bootstrap.env}"
PARAM_PREFIX="${VELOCITYAI_PARAM_PREFIX:-/velocityai/prod}"
ENVIRONMENT="${VELOCITYAI_ENVIRONMENT:-prod}"
# NOTE: the title-cased environment for the CloudWatch namespace
# ("prod" -> "VelocityAI/Prod", matching the monitoring module's
# `cw_metric_namespace`) is derived in reconcile-host-config.sh, which is the
# script that actually writes the agent config. An unused ENV_TITLE assignment
# lived here as a leftover from before that move (SC2034).
ACME_EMAIL="${VELOCITYAI_ACME_EMAIL:-security@example.com}"
BACKUP_BUCKET="${VELOCITYAI_BACKUP_BUCKET:?VELOCITYAI_BACKUP_BUCKET missing in /etc/velocityai/bootstrap.env}"
# VELOCITYAI_DATA_DEVICE lets a hand-provisioned box (attached data volume on
# a device other than nvme1n1 — e.g. /dev/xvdf on some instance families, or a
# second nvme index when more than one extra volume is attached) point this
# script at the right block device. Terraform-provisioned boxes are
# unaffected: modules/compute passes data_volume_device_name (default
# /dev/nvme1n1) into user_data as this same variable, so the default below
# only ever fires when the variable is genuinely unset.
DATA_DEV="${VELOCITYAI_DATA_DEVICE:-/dev/nvme1n1}"
DATA_MOUNT=/var/lib/postgresql
APP_USER=velocityai

# Fail fast, before §5 touches mkfs/fstab: a typo'd or absent device is a
# configuration error, not something mkfs.xfs or `blkid` should discover by
# formatting the wrong thing or hanging on a path that doesn't exist.
if [[ ! -b "$DATA_DEV" ]]; then
    echo "[bootstrap] ERROR: DATA_DEV '${DATA_DEV}' is not a block device. Set VELOCITYAI_DATA_DEVICE in /etc/velocityai/bootstrap.env to the actual attached data volume (check: lsblk)." >&2
    exit 1
fi

# ── 1b. Shared host helpers ────────────────────────────────────────────────
# infra/scripts/lib/host-common.sh, delivered to s3://$BACKUP_BUCKET/config/ by
# provision.yml and by deploy.yml's config refresh, and fetched here. Provides
# apt_force_https, apt_wait_lock, install_awscli_v2 (with the single AWSCLI_VERSION
# pin) and cw_namespace — each of which previously existed as a second copy in
# .github/scripts/remote-bootstrap.sh or reconcile-host-config.sh.
#
# Fetched BEFORE §2 because §2 is the first thing that needs apt_force_https, and
# with the same 30 x 10s retry loop as the other config objects: on a fresh
# instance this can run before the app layer has finished uploading. Absent after
# all attempts is fatal — the functions below are not optional.
#
# `aws` is available here: on a Terraform box user_data installs a minimal CLI, and
# on a hand-created box remote-bootstrap.sh §2 installed it before invoking this
# script. §2b below then asserts the pinned version.
mkdir -p /opt/velocityai/lib
for i in $(seq 1 30); do
    if aws s3 cp "s3://${BACKUP_BUCKET}/config/host-common.sh" \
         /opt/velocityai/lib/host-common.sh --region "$REGION"; then
        break
    fi
    # Fail on the LAST failed attempt. A post-loop `[[ -s file ]]` check cannot
    # tell a fresh download from a stale file left by an earlier run, so a fetch
    # that failed every time would continue with old bytes (REL-21).
    if [[ "$i" -eq 30 ]]; then
        echo "[bootstrap] FATAL: config/host-common.sh missing in s3://${BACKUP_BUCKET}/config/. Seed it by running the 'Provision' workflow for this environment with dry_run=true (the S3 upload runs before any host change), then retry." >&2
        echo "[bootstrap]        apt-over-HTTPS, the AWS CLI pin and the CloudWatch namespace map all live there — aborting" >&2
        exit 1
    fi
    echo "[bootstrap] host-common.sh not available yet (attempt $i) — retrying"
    sleep 10
done
chmod 0644 /opt/velocityai/lib/host-common.sh
# SC2034 disabled with cause: read by `_hc_log`/`_hc_err` in host-common.sh,
# which is sourced on the next lines from an absolute runtime path under
# /opt/velocityai. That source carries `# shellcheck source=/dev/null`, so
# ShellCheck cannot see the consumer and reports the assignment as unused.
# Deleting it would silently downgrade every log line to the "[host]" default.
# shellcheck disable=SC2034
HOST_COMMON_LOG_PREFIX="[bootstrap]"
# shellcheck source=/dev/null
. /opt/velocityai/lib/host-common.sh

# ── 2. Patch & baseline tools ──────────────────────────────────────────
export DEBIAN_FRONTEND=noninteractive

# ── 2a. Force apt over HTTPS ───────────────────────────────────────────
# See apt_force_https in infra/scripts/lib/host-common.sh (sourced in §1b) for the
# full rationale: this host egresses on 443 only, Ubuntu ships http:// sources, and
# the resulting failure looks unrelated to networking.
apt_force_https

# Fail fast, and diagnosably, if the archive is still unreachable.
# `apt-get update` returns 0 even when every index fetch fails, so without this
# probe the run continues on stale package lists and surfaces the problem several
# sections later as a bare `exit status 100`.
#
# The source list is rebuilt here rather than shared with apt_force_https: each
# path is tested with -f because Noble ships no *.list in sources.list.d, the shell
# leaves the unmatched glob literal, and grep then exits 2 on a nonexistent path —
# which under `set -e` + `pipefail` aborts the whole run.
#
# The `|| true` is load-bearing: grep exits 1 on no-match, and head closing the
# pipe early can leave grep on SIGPIPE — either of which would abort through
# pipefail rather than simply skipping the probe.
apt_src_files=()
for apt_src in /etc/apt/sources.list \
               /etc/apt/sources.list.d/*.sources \
               /etc/apt/sources.list.d/*.list; do
    [[ -f "$apt_src" ]] && apt_src_files+=("$apt_src")
done
. /etc/os-release
apt_probe_uri=""
if (( ${#apt_src_files[@]} > 0 )); then
    apt_probe_uri="$(
        grep -hEo 'https://([A-Za-z0-9.-]*\.)?archive\.ubuntu\.com[^[:space:]]*' \
            "${apt_src_files[@]}" 2>/dev/null | head -n1 || true
    )"
fi
if [[ -n "$apt_probe_uri" && -n "${VERSION_CODENAME:-}" ]] \
   && ! curl -fsS --max-time 20 -o /dev/null \
        "${apt_probe_uri%/}/dists/${VERSION_CODENAME}/InRelease"; then
    echo "[bootstrap] ERROR: cannot reach the Ubuntu archive over HTTPS at ${apt_probe_uri}." >&2
    echo "[bootstrap]        Package installation cannot proceed. Verify outbound 443 on this" >&2
    echo "[bootstrap]        instance's security group and the upstream Transit Gateway path." >&2
    exit 1
fi

apt_wait_lock
apt-get update
apt-get -y full-upgrade
# Note on awscli: Ubuntu Noble (24.04 LTS) removed the `awscli` apt package
# — it was v1 (deprecated, EOL July 2025) and the Debian/Ubuntu package was
# unmaintained. AWS officially distributes v2 as a self-contained binary
# from awscli.amazonaws.com. `unzip` here is needed to unpack the v2
# installer in section 2b below.
apt-get install -y \
    nginx postgresql-16 postgresql-contrib-16 postgresql-client-16 \
    curl jq xfsprogs acl unzip \
    certbot python3-certbot-nginx \
    ufw fail2ban auditd \
    unattended-upgrades update-notifier-common \
    ca-certificates gnupg

# ── 2b. AWS CLI v2 (official installer) ────────────────────────────────
# install_awscli_v2 and the single AWSCLI_VERSION pin live in
# infra/scripts/lib/host-common.sh (sourced in §1b). The pin used to be written
# here AND in .github/scripts/remote-bootstrap.sh §2, so a bump could reach one
# provisioning path and not the other — and which path a box took depends on
# whether it was Terraform-created or hand-created.
install_awscli_v2

# ── 3. Firewall + SSH hardening + unattended upgrades ──────────────────
ufw default deny incoming
ufw default allow outgoing
# NO `ufw allow 22/tcp`. Nothing in the pipeline uses SSH: deploy.yml and
# provision.yml both reach this host over SSM RunCommand, which needs no inbound
# port at all (the SSM agent dials out). The rule was CodeBuild-era, from when CI
# ssh'd in as a dedicated `velocityai-deploy` user — a user this script no longer
# creates (see the §15 cleanup block below).
#
# `ufw delete` is issued rather than merely omitting the rule, because a host
# bootstrapped before this change already has the rule persisted in
# /etc/ufw/user.rules and re-running bootstrap would otherwise leave it in place
# forever. `|| true` because deleting a rule that is not there exits non-zero,
# which is the normal case on a fresh box and must not abort under `set -e`.
ufw delete allow 22/tcp >/dev/null 2>&1 || true
ufw allow 80/tcp
ufw allow 443/tcp
# Postgres reachable only from RFC 1918 ranges Docker uses for its bridge
# networks (default bridge + compose-created bridges). The backend
# container connects to host.docker.internal:5432 (resolved to the docker0
# / compose-bridge gateway), and without this rule UFW silently drops the
# traffic — symptom is "Connection timed out" from psycopg2, not "refused".
# The VPC security group separately blocks 5432 from outside the EC2, so
# this is a narrow allow that only opens postgres to local containers.
ufw allow from 172.16.0.0/12 to any port 5432 proto tcp comment "Postgres from docker bridges"
ufw --force enable

cat >/etc/ssh/sshd_config.d/10-velocityai.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
PermitTunnel no
ClientAliveInterval 300
ClientAliveCountMax 2
MaxAuthTries 3
LoginGraceTime 30
EOF
# On Ubuntu Noble, ssh.service is often socket-activated (ssh.socket starts
# ssh.service on first connect), so a plain `systemctl reload ssh` against
# an inactive service fails with "ssh.service is not active, cannot reload"
# and set -e kills the bootstrap. reload-or-restart is the systemd-idiomatic
# command for "apply the new sshd_config, regardless of current state".
systemctl reload-or-restart ssh

cat >/etc/apt/apt.conf.d/52velocityai <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF
systemctl enable --now unattended-upgrades

timedatectl set-timezone UTC

# ── 4. Application user + directories ──────────────────────────────────
id -u "$APP_USER" >/dev/null 2>&1 \
    || useradd -r -m -d /opt/velocityai -s /usr/sbin/nologin "$APP_USER"
mkdir -p /opt/velocityai /opt/velocityai/data/skills /opt/velocityai/data/runs /var/log/velocityai /etc/velocityai
chown -R "$APP_USER:$APP_USER" /opt/velocityai /var/log/velocityai
# The backend + frontend containers run as uid:gid 10001:10001 (see
# backend/Dockerfile / frontend/Dockerfile). data/skills + data/runs are
# bind-mounted INTO the backend container (docker-compose.yml: data/runs ->
# /app/runs, data/skills -> /app/skills) and written by that non-root user, so
# they MUST be owned by 10001 — NOT $APP_USER (a system uid, e.g. 999) — or the
# container's per-run `mkdir /app/runs/<user>/<run>` fails with EACCES and every
# pipeline run aborts. This runs AFTER the recursive chown above so it wins, and
# is recursive so a recovery-mode volume with pre-existing content is fixed too.
chown -R 10001:10001 /opt/velocityai/data/skills /opt/velocityai/data/runs
chown root:"$APP_USER" /etc/velocityai
chmod 0750 /etc/velocityai

# ── 5. Data volume — fresh vs recovery ─────────────────────────────────
systemctl stop postgresql || true
# Format the data device if it has no filesystem signature yet. The
# filesystem-signature check below is separate from the recovery-mode
# decision: a partially-failed prior bootstrap can leave xfs in place
# but no postgres data, which is still "fresh" from initdb's perspective.
if blkid "$DATA_DEV" >/dev/null 2>&1; then
    echo "[bootstrap] data device has filesystem signature — skipping mkfs"
else
    echo "[bootstrap] data device blank — formatting xfs"
    mkfs.xfs -L vai-data "$DATA_DEV"
fi

mkdir -p "$DATA_MOUNT"
if ! mountpoint -q "$DATA_MOUNT"; then
    UUID=$(blkid -s UUID -o value "$DATA_DEV")
    grep -q "$UUID" /etc/fstab \
        || echo "UUID=$UUID $DATA_MOUNT xfs defaults,nofail 0 2" >> /etc/fstab
    mount "$DATA_MOUNT"
fi
chown postgres:postgres "$DATA_MOUNT"

# Recovery-mode detection — based on actual Postgres data (PG_VERSION marker
# file written by a successful initdb), NOT filesystem-signature presence.
# Previously the check fired on xfs presence; a partial bootstrap that
# formatted xfs but died before initdb would mis-classify as "recovery"
# and skip the initdb that actually has to run.
if [[ -f "$DATA_MOUNT/16/main/PG_VERSION" ]]; then
    echo "[bootstrap] postgres data dir present — recovery mode"
    RECOVERY=1
else
    echo "[bootstrap] postgres data dir absent — fresh provision"
    RECOVERY=0
fi

# ── 6. Postgres init / configure ───────────────────────────────────────
# DATABASE_PASSWORD is provisioned by Terraform's random_password in
# infra/modules/secrets/main.tf — script just reads it. (The composite
# DATABASE_URL is composed at app-start by /usr/local/bin/velocityai-load-secrets
# from this same password; we don't store DATABASE_URL in SSM separately.)
PG_DATA="$DATA_MOUNT/16/main"
if [[ $RECOVERY -eq 0 ]]; then
    # PostgreSQL 16 initdb syntax notes:
    #   - `--pwprompt` is a flag (no value); the previous `--pwprompt=false`
    #     made initdb error with "option '--pwprompt' doesn't allow an
    #     argument" and the bootstrap died here.
    #   - Match the Debian/Ubuntu pg_createcluster default: peer for the
    #     local Unix socket (so `sudo -u postgres psql` works without
    #     password), scram-sha-256 for TCP (the velocityai app container
    #     connects over TCP with a real password from SSM).
    #   - No --pwfile / --pwprompt: the postgres SUPERUSER role gets no
    #     password set at initdb time. The velocityai role created in the next
    #     block is the one with a real scram-sha-256 hash, and that's the
    #     only role the app ever uses over TCP.
    sudo -u postgres /usr/lib/postgresql/16/bin/initdb -D "$PG_DATA" \
        --auth-local=peer --auth-host=scram-sha-256
fi

PG_CONF=/etc/postgresql/16/main/postgresql.conf
PG_HBA=/etc/postgresql/16/main/pg_hba.conf
# listen_addresses = '*' is paired with a tight pg_hba.conf below + a
# firewall that blocks 5432/tcp from external sources, so postgres is
# reachable only by:
#   - host-local processes via 127.0.0.1
#   - docker containers connecting via their bridge gateway (typically
#     172.17-31.x.1, depending on which docker-compose network they're on)
# The backend container's DATABASE_URL uses `host.docker.internal` which
# host-gateway resolves to the bridge gateway, hitting postgres on that
# interface. Binding to 127.0.0.1 ONLY (the previous setting) made the
# container's TCP connect fail because postgres wasn't accepting on the
# bridge IP — symptom was "connection refused" or a misleading
# "could not translate host name" from libpq.
sed -i \
    -e "s|^#*data_directory.*|data_directory = '$PG_DATA'|" \
    -e "s|^#*listen_addresses.*|listen_addresses = '*'|" \
    -e "s|^#*shared_buffers.*|shared_buffers = 4GB|" \
    -e "s|^#*effective_cache_size.*|effective_cache_size = 10GB|" \
    -e "s|^#*work_mem.*|work_mem = 32MB|" \
    -e "s|^#*maintenance_work_mem.*|maintenance_work_mem = 512MB|" \
    -e "s|^#*log_min_duration_statement.*|log_min_duration_statement = 1000|" \
    "$PG_CONF"
# pg_hba.conf: peer auth for the postgres superuser on the local socket
# (no password needed), scram-sha-256 for everyone else. Host entries
# cover loopback + the docker bridge ranges that compose/dockerd allocate
# from (172.16.0.0/12 covers 172.17.0.0/16 through 172.31.0.0/16, which
# is the full RFC 1918 range Docker hands out by default). The VPC
# security group + ufw both block 5432 from outside the EC2, so the
# /12 grant is only reachable from local containers in practice.
cat > "$PG_HBA" <<'EOF'
local   all   postgres                  peer
local   all   all                       scram-sha-256
host    all   all      127.0.0.1/32     scram-sha-256
host    all   all      ::1/128          scram-sha-256
host    all   all      172.16.0.0/12    scram-sha-256
EOF

mkdir -p /etc/systemd/system/postgresql@16-main.service.d
cat > /etc/systemd/system/postgresql@16-main.service.d/oom.conf <<'EOF'
[Service]
OOMScoreAdjust=-900
EOF
systemctl daemon-reload
systemctl enable --now postgresql@16-main
# Restart so the postgresql.conf / pg_hba.conf rewrites above take effect
# on re-runs. listen_addresses changes specifically require a restart (not
# just SIGHUP / reload). On a fresh box this is a no-op equivalent of the
# first start above; on re-run it picks up the new config without manual
# intervention.
systemctl restart postgresql@16-main

if [[ $RECOVERY -eq 0 ]]; then
    DB_PW=$(aws ssm get-parameter --region "$REGION" \
        --name "$PARAM_PREFIX/DATABASE_PASSWORD" \
        --with-decryption --query 'Parameter.Value' --output text)
    # The password is interpolated into a single-quoted SQL literal below. A `'`
    # would end the literal early, and psql then echoes the failing statement
    # (password included) into three logs. Refuse it WITHOUT printing the value
    # (SEC-14). Generated passwords are alphanumeric, so this only trips on a
    # hand-set value.
    if [[ "$DB_PW" == *"'"* ]]; then
        echo "[bootstrap] FATAL: ${PARAM_PREFIX}/DATABASE_PASSWORD contains a single quote (') and cannot be used in the CREATE USER statement. Set a value without one (value not shown)." >&2
        exit 1
    fi
    sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
CREATE USER velocityai WITH ENCRYPTED PASSWORD '$DB_PW';
CREATE DATABASE velocityai OWNER velocityai;
\c velocityai
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO velocityai;
SQL
fi

# ── 7. Swap ────────────────────────────────────────────────────────────
if ! swapon --show | grep -q swapfile; then
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab \
        || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
sysctl -w vm.swappiness=10
echo 'vm.swappiness = 10' > /etc/sysctl.d/99-velocityai.conf

# ── 8. Docker engine + Compose plugin (Docker's official APT repo) ─────
echo "[bootstrap] installing Docker engine + Compose plugin"
install -m 0755 -d /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
fi
# Trust-on-first-use is not enough for a key that signs root-installed packages:
# pin Docker's published release-key fingerprint and refuse (and delete) any
# other key, so a tampered download cannot persist for the next run (SEC-09).
DOCKER_KEY_FPR="9DC858229FC7DD38854AE2D88D81803C0EBFCD88"
_docker_fprs="$(gpg --show-keys --with-colons /etc/apt/keyrings/docker.gpg | awk -F: '$1=="fpr"{print $10}')"
if ! grep -qx "$DOCKER_KEY_FPR" <<<"$_docker_fprs"; then
    rm -f /etc/apt/keyrings/docker.gpg
    echo "[bootstrap] FATAL: Docker apt key fingerprint does not match the pinned ${DOCKER_KEY_FPR} — removed the key and aborting" >&2
    exit 1
fi
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker

echo "[bootstrap] Docker installed: $(docker --version), $(docker compose version)"

# ── 8b. IMDS containment for the pptx_export Node subprocess (C2-2) ────
# This section adds NO firewall rule: every candidate way to block IMDS for the
# LLM-code-executing Node child either has no effect on bridge-originating
# traffic or breaks the backend's own legitimate boto3 IMDS use. The full
# analysis — five rejected enforcement points, the five layered controls that
# are in place instead, and the sidecar refactor that is the real fix — lives in
# docs/CICD-DESIGN-DECISIONS.md, "IMDS containment for the pptx_export Node
# subprocess (C2-2)". What remains here are two observations, because the TF
# compute module owns IMDS posture and the instance role cannot re-assert it.


# Observation 1: IMDSv2 token-required mode is on. A v1 GET (no token
# header) should return 401 Unauthorized. If a v1 GET succeeds, the EC2
# launch template has drifted from TF — page operator.
if curl -sf --max-time 2 http://169.254.169.254/latest/meta-data/ \
    >/dev/null 2>&1; then
    echo "[bootstrap] CRITICAL: IMDSv1 (no token) is reachable — the EC2 IMDS posture has drifted from TF. Run \`aws ec2 modify-instance-metadata-options --http-tokens required\` immediately, then re-apply terraform to bring the launch template back in sync."
    # Don't `exit 1` — bootstrap completing is more valuable than failing
    # here, and the CloudTrail UnexpectedKmsDecrypt alarm (C2-1) is the
    # safety net for any actual exfil. The log line is the operator
    # signal; cwagent ships it to /velocityai/${env}/system.
else
    echo "[bootstrap] OK: IMDSv1 (no token) returns 401 — IMDSv2 token-required is enforced (C2-2 baseline)"
fi

# Observation 2: hop_limit visibility. We can't query the configured
# hop_limit from inside the instance (the SDK call requires
# ec2:DescribeInstances which is not granted to the instance role and
# arguably shouldn't be — it would let any in-container shell enumerate
# the EC2 fleet). The TF compute module is the SoT; this is a comment
# placeholder so operators reading the bootstrap know where to look:
echo "[bootstrap] IMDS hop_limit is set in TF: infra/modules/compute/main.tf::metadata_options.http_put_response_hop_limit (currently 2 — Docker bridge requires >= 2)"

# ── 9. ECR login + refresh timer ───────────────────────────────────────
ECR_REGISTRY="${VELOCITYAI_ECR_REGISTRY:-}"
if [[ -z "$ECR_REGISTRY" ]]; then
    echo "[bootstrap] ERROR: VELOCITYAI_ECR_REGISTRY not set" >&2
    exit 1
fi

aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY"

cat > /etc/systemd/system/velocityai-ecr-login.service <<'UNIT'
[Unit]
Description=Refresh Docker login to ECR
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/velocityai/bootstrap.env
ExecStart=/bin/bash -c '/usr/local/bin/aws ecr get-login-password --region $VELOCITYAI_REGION | /usr/bin/docker login --username AWS --password-stdin $VELOCITYAI_ECR_REGISTRY'
UNIT

cat > /etc/systemd/system/velocityai-ecr-login.timer <<'TIMER'
[Unit]
Description=Refresh Docker login to ECR every 6 hours

[Timer]
OnCalendar=*-*-* 00,06,12,18:00:00
RandomizedDelaySec=5min
Persistent=true

[Install]
WantedBy=timers.target
TIMER

systemctl daemon-reload
systemctl enable --now velocityai-ecr-login.timer

# ── 10. docker-compose.yml (+ prod logging override) from S3 ───────────
# Terraform's app layer uploads both the canonical docker-compose.yml and its
# M-01 production logging override (aws_s3_object.compose_yaml /
# .compose_prod_yaml) to s3://$BACKUP_BUCKET/config/ on every apply. The
# instance role's s3-config-read policy grants GetObject on that exact
# prefix. Re-running this script picks up the latest files.
aws s3 cp "s3://${BACKUP_BUCKET}/config/docker-compose.yml" \
    /opt/velocityai/docker-compose.yml --region "$REGION"
aws s3 cp "s3://${BACKUP_BUCKET}/config/docker-compose.prod.yml" \
    /opt/velocityai/docker-compose.prod.yml --region "$REGION"
chown "$APP_USER:$APP_USER" /opt/velocityai/docker-compose.yml /opt/velocityai/docker-compose.prod.yml
chmod 0644 /opt/velocityai/docker-compose.yml /opt/velocityai/docker-compose.prod.yml

# ── 10b. Resolve which images this host should run ─────────────────────────
# Precedence, most authoritative first:
#
#   1. SSM ${PARAM_PREFIX}/deploy/{backend,frontend}_image — digest-pinned refs
#      written by .github/workflows/deploy.yml AFTER its health gate passed, so
#      they name the last version that provably served traffic in this
#      environment. This is what lets a REPLACED / REBUILT instance return to
#      the current release on its own, without waiting for a pipeline run.
#      Before this existed, the deployed version lived ONLY in this box's
#      /etc/velocityai/app.env and died with the instance, so a rebuild fell
#      back to (2) and tried to pull a tag CI had never built.
#
#   2. s3://$BACKUP_BUCKET/config/deploy.env — Terraform's var.image_tag
#      (aws_s3_object.deploy_env, app layer). Only meaningful before the first
#      CI deploy: Terraform is deliberately not in the deploy loop, so this
#      object goes stale the moment CI ships anything. Kept as the pre-first-
#      deploy seed, NOT as a source of truth.
#
# There is deliberately NO third fallback. One used to exist —
# ${ECR_REGISTRY}/velocityai/<component>:${IMAGE_TAG} with IMAGE_TAG defaulting
# to "latest" — and it could never work: these ECR repositories are IMMUTABLE and
# the pipeline pushes a distinct per-release tag, so no `:latest` is ever
# published. Its only effect was to replace an honest "no deploy record found"
# with a concrete-looking image reference that always failed to pull, which §18b
# then reported as "the pinned images are not in ECR yet" — technically true,
# actively misleading, and it buried the real cause (neither SSM deploy/* nor
# S3 deploy.env had a pin).
#
# When neither source yields BOTH refs, the refs stay EMPTY. §11 writes no pin
# lines and §18b takes its existing clean-skip path, which is the correct
# description of a host that has nothing to run yet.
#
# Only (1) is accepted when BOTH refs are present: a half-written pair would
# otherwise run a backend and frontend from different releases.
DEPLOY_BACKEND_IMAGE=""
DEPLOY_FRONTEND_IMAGE=""
IMAGE_PIN_SOURCE=""

# Only `ParameterNotFound` means "no deploy record" (prints nothing, returns 0).
# Any other failure (throttling, expired credentials, a network blip) used to be
# folded into "absent" by a blanket `|| true`, so a transient SSM error silently
# sent the host down the stale-S3 fallback below. It now returns 1, which aborts
# the bootstrap under `set -e` at the `$(...)` assignment sites (REL-20).
ssm_deploy_param() {
    local out err_file rc=0
    err_file="$(mktemp)"
    out="$(aws ssm get-parameter \
        --name "${PARAM_PREFIX}/deploy/$1" \
        --region "$REGION" \
        --query 'Parameter.Value' --output text 2>"$err_file")" || rc=$?
    if [[ "$rc" -eq 0 ]]; then
        rm -f "$err_file"
        printf '%s\n' "$out"
        return 0
    fi
    if grep -q 'ParameterNotFound' "$err_file"; then
        rm -f "$err_file"
        return 0
    fi
    echo "[bootstrap] ERROR: could not read ${PARAM_PREFIX}/deploy/$1 from SSM (not a ParameterNotFound): $(head -c 300 "$err_file")" >&2
    rm -f "$err_file"
    return 1
}

_ssm_backend="$(ssm_deploy_param backend_image)"
_ssm_frontend="$(ssm_deploy_param frontend_image)"
# `--output text` renders a JSON null as the literal string "None"; treat that
# as absent rather than letting it become an image reference.
if [[ "$_ssm_backend" == "None" ]]; then _ssm_backend=""; fi
if [[ "$_ssm_frontend" == "None" ]]; then _ssm_frontend=""; fi

if [[ -n "$_ssm_backend" && -n "$_ssm_frontend" ]]; then
    DEPLOY_BACKEND_IMAGE="$_ssm_backend"
    DEPLOY_FRONTEND_IMAGE="$_ssm_frontend"
    IMAGE_PIN_SOURCE="SSM ${PARAM_PREFIX}/deploy/* (last known-good deploy)"
elif aws s3 cp "s3://${BACKUP_BUCKET}/config/deploy.env" /tmp/deploy.env --region "$REGION" 2>/dev/null; then
    # Same `|| true` reasoning: grep exits 1 when the key is absent, and under
    # `pipefail` that would propagate out of the command substitution.
    DEPLOY_BACKEND_IMAGE="$(grep -E '^BACKEND_IMAGE=' /tmp/deploy.env | cut -d= -f2- || true)"
    DEPLOY_FRONTEND_IMAGE="$(grep -E '^FRONTEND_IMAGE=' /tmp/deploy.env | cut -d= -f2- || true)"
    rm -f /tmp/deploy.env
    IMAGE_PIN_SOURCE="s3://${BACKUP_BUCKET}/config/deploy.env (Terraform var.image_tag — may be stale)"
fi

# Both or neither. A single ref on its own is not usable: compose needs both
# services, and running one from a recorded pin while the other has none would
# be a split release.
BACKEND_IMAGE_REF=""
FRONTEND_IMAGE_REF=""
if [[ -n "$DEPLOY_BACKEND_IMAGE" && -n "$DEPLOY_FRONTEND_IMAGE" ]]; then
    BACKEND_IMAGE_REF="$DEPLOY_BACKEND_IMAGE"
    FRONTEND_IMAGE_REF="$DEPLOY_FRONTEND_IMAGE"
fi

if [[ -n "$BACKEND_IMAGE_REF" ]]; then
    echo "[bootstrap] image pins resolved from: ${IMAGE_PIN_SOURCE}"
    echo "[bootstrap]   backend  ${BACKEND_IMAGE_REF}"
    echo "[bootstrap]   frontend ${FRONTEND_IMAGE_REF}"
else
    IMAGE_PIN_SOURCE="none — no deploy record in SSM ${PARAM_PREFIX}/deploy/* or s3://${BACKUP_BUCKET}/config/deploy.env"
    echo "[bootstrap] no image pins available (${IMAGE_PIN_SOURCE})"
    echo "[bootstrap] this host has nothing to run yet; §18b will skip starting the app"
fi

# ── 11. /etc/velocityai/app.env image-tag pin ──────────────────────────────
# ECR repos are IMMUTABLE, so every release is addressed by a distinct tag and
# ultimately by digest. The pins written here come from §10b, which reads the
# SSM deploy/* parameters that deploy.yml recorded (digest-exact) — not from any
# :latest alias, which would never resolve on an immutable repo.
#
# On every bootstrap run we overwrite the BACKEND_IMAGE / FRONTEND_IMAGE pin
# lines so the box starts on the release the pipeline last deployed.
#
# The canonical loader (infra/scripts/velocityai-load-secrets.sh, fetched in §12)
# preserves FIVE keys across subsequent velocityai-app.service starts — its
# grep is `^(BACKEND_IMAGE|FRONTEND_IMAGE|ENV|VELOCITYAI_ENVIRONMENT|
# VELOCITYAI_CW_LOG_GROUP)=` — and this block is the only writer of all five.
# Three are written unconditionally; the two image pins only when §10b resolved
# a release (see below). Everything else in app.env is re-derived from SSM
# ${PARAM_PREFIX}/* on each start. Keep the two lists in step: a key added here
# but not to the loader's preserve pattern is silently dropped on the first app
# restart.
mkdir -p /etc/velocityai
if [[ -f /etc/velocityai/app.env ]]; then
    # Strip the managed lines; keep everything else operators added.
    grep -vE '^(ENV|BACKEND_IMAGE|FRONTEND_IMAGE|VELOCITYAI_ENVIRONMENT|VELOCITYAI_CW_LOG_GROUP)=' /etc/velocityai/app.env \
        > /etc/velocityai/app.env.new || true
else
    # Fresh box: seed with the header comment so future operators know
    # where these values come from.
    cat > /etc/velocityai/app.env.new <<EOF
# Populated by /usr/local/bin/velocityai-load-secrets on every velocityai-app start.
# The loader preserves exactly these five keys: BACKEND_IMAGE, FRONTEND_IMAGE,
# ENV, VELOCITYAI_ENVIRONMENT, VELOCITYAI_CW_LOG_GROUP. Everything else is
# overwritten from SSM ${PARAM_PREFIX}/*.

EOF
fi
cat >> /etc/velocityai/app.env.new <<EOF
ENV=production
VELOCITYAI_ENVIRONMENT=${ENVIRONMENT}
VELOCITYAI_CW_LOG_GROUP=/velocityai/${ENVIRONMENT}/app
EOF
# Pin lines ONLY when §10b actually resolved a release. Writing
# `BACKEND_IMAGE=` with an empty value would be worse than omitting it: compose
# interpolates it into `image:`, so the service would resolve to an empty
# reference and fail with a confusing manifest error instead of §18b's clear
# "nothing to run yet" skip. An absent key is also what the loader's
# `grep -qxF` post-conditions and §18b's emptiness test below expect.
if [[ -n "$BACKEND_IMAGE_REF" && -n "$FRONTEND_IMAGE_REF" ]]; then
    cat >> /etc/velocityai/app.env.new <<EOF
BACKEND_IMAGE=${BACKEND_IMAGE_REF}
FRONTEND_IMAGE=${FRONTEND_IMAGE_REF}
EOF
else
    echo "[bootstrap] no image pins written to /etc/velocityai/app.env (no deploy record yet)"
fi
mv /etc/velocityai/app.env.new /etc/velocityai/app.env
chown root:"$APP_USER" /etc/velocityai/app.env
chmod 0640 /etc/velocityai/app.env

# ── 12. /usr/local/bin/velocityai-load-secrets ─────────────────────────────
# Fetched from S3, never generated here. The canonical source is
# infra/scripts/velocityai-load-secrets.sh, uploaded by the app layer to
# s3://$BACKUP_BUCKET/config/velocityai-load-secrets.sh — the same delivery
# mechanism as this script and reconcile-host-config.sh.
#
# This block used to ALSO carry a ~180-line inline heredoc copy of the loader,
# described as "a compatibility fallback for old artifact buckets". It was dead
# code in the worst way: the `aws s3 cp` below ran unconditionally and
# overwrote it moments later, so the heredoc version never executed even once —
# while still being the thing a reader would study to learn what the loader
# does, and still drifting away from the real file with every edit to it. And
# because the fetch ran under `set -e` with no retry, a config/ object that was
# not yet uploaded aborted the whole bootstrap rather than falling back to
# anything. The "fallback" protected nothing it claimed to protect.
#
# Retried on the same 30 x 10s schedule as reconcile-host-config.sh below: a
# fresh instance can reach this point before the app layer has finished
# uploading. Absent after all attempts is fatal and loud — without the loader
# the box has no way to read its own configuration out of SSM, so continuing
# would only move the failure to a less legible place.
for i in $(seq 1 30); do
    if aws s3 cp "s3://${BACKUP_BUCKET}/config/velocityai-load-secrets.sh" \
         /opt/velocityai/velocityai-load-secrets.sh --region "$REGION"; then
        break
    fi
    # Last failed attempt is fatal; a stale on-disk copy must not pass (REL-21).
    if [[ "$i" -eq 30 ]]; then
        echo "[bootstrap] ERROR: could not fetch velocityai-load-secrets.sh from s3://${BACKUP_BUCKET}/config/ after 30 attempts" >&2
        echo "[bootstrap] ERROR: the host cannot load its configuration from SSM without it — aborting" >&2
        exit 1
    fi
    echo "[bootstrap] velocityai-load-secrets.sh not available yet (attempt $i) — retrying"
    sleep 10
done
install -o root -g root -m 0755 \
    /opt/velocityai/velocityai-load-secrets.sh \
    /usr/local/bin/velocityai-load-secrets

# ── 13/14. Host configuration (nginx + CloudWatch agent) ───────────────
#
# The declarative half of this script now lives in
# infra/scripts/reconcile-host-config.sh, uploaded by the app layer to
# s3://$BACKUP_BUCKET/config/reconcile-host-config.sh (aws_s3_object
# .reconcile_script, source_hash = filemd5). Same delivery mechanism as this
# script itself.
#
# WHY: bootstrap runs exactly once per instance (velocityai-firstboot.service
# is gated on /var/lib/velocityai/.bootstrap-done), but nginx and the agent
# config legitimately change with the application. The reconcile script is
# idempotent and is re-run by CI on every deploy, so a repo edit reaches a
# LIVE host. Genuinely once-per-instance provisioning -- including ISSUING the
# TLS cert below -- stays here.
mkdir -p /var/www/letsencrypt /etc/nginx/snippets

# Retry the fetch. Under `set -e` (line 27) a single transient S3 failure would
# abort provisioning; the firstboot wrapper already retries the bootstrap-script
# fetch 30x for exactly this reason (user_data.sh.tpl:85-92) and this inherits
# the same posture.
for i in $(seq 1 30); do
    if aws s3 cp "s3://${BACKUP_BUCKET}/config/reconcile-host-config.sh" \
         /opt/velocityai/reconcile-host-config.sh --region "$REGION"; then
        break
    fi
    # Last failed attempt is fatal; a stale on-disk copy must not pass (REL-21).
    if [[ "$i" -eq 30 ]]; then
        echo "[bootstrap] ERROR: could not fetch reconcile-host-config.sh from S3" >&2
        exit 1
    fi
    echo "[bootstrap] reconcile-host-config.sh not available yet (attempt $i) — retrying"
    sleep 10
done
chmod 0755 /opt/velocityai/reconcile-host-config.sh

# Initial cert (HTTP-01 webroot) — only if no cert exists yet for this domain.
# Runs BEFORE the reconcile so the reconcile's `nginx -t` has a certificate to
# validate against. The temporary bootstrap-http site below only needs the
# webroot, not the real site file.
# Let's Encrypt validates over the public internet: $DOMAIN must resolve to a
# globally routable address AND be reachable here on port 80. A private-IP
# domain fails with "no valid A records found for <domain>" — LE refuses
# RFC1918 answers outright. Detect that up front so a private-network host
# falls back to a self-signed cert instead of aborting the entire provision
# under `set -e` (certbot is not wrapped, so its failure strands every later
# section and the completion sentinel).
#
# getent is libc, so this needs no dnsutils/bind9-host package installed.
domain_has_public_ip() {
    local d="$1" ip
    while read -r ip; do
        case "$ip" in
            ''|0.0.0.0|10.*|127.*|169.254.*|192.168.*)   continue ;;
            172.1[6-9].*|172.2[0-9].*|172.3[01].*)       continue ;;
            100.6[4-9].*|100.[7-9][0-9].*|100.1[0-1][0-9].*|100.12[0-7].*) continue ;;
            *) return 0 ;;
        esac
    done < <(getent ahostsv4 "$d" 2>/dev/null | awk '{print $1}' | sort -u)
    # Global-unicast IPv6 (2000::/3) also counts; private/link-local v6 is f*.
    while read -r ip; do
        case "$ip" in
            2*|3*) return 0 ;;
        esac
    done < <(getent ahostsv6 "$d" 2>/dev/null | awk '{print $1}' | sort -u)
    return 1
}

if [[ ! -d /etc/letsencrypt/live/$DOMAIN ]] && ! domain_has_public_ip "$DOMAIN"; then
    echo "[bootstrap] WARNING: ${DOMAIN} does not resolve to a public address —" >&2
    echo "[bootstrap]          Let's Encrypt HTTP-01 cannot validate it. Installing a" >&2
    echo "[bootstrap]          self-signed certificate so nginx can serve TLS and" >&2
    echo "[bootstrap]          provisioning can complete. NOT valid for public use." >&2
    install -d -m 0755 /etc/letsencrypt/live "/etc/letsencrypt/live/${DOMAIN}"
    openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
        -keyout "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" \
        -out    "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" \
        -subj   "/CN=${DOMAIN}" \
        -addext "subjectAltName=DNS:${DOMAIN}"
    # nginx points ssl_trusted_certificate at chain.pem; a self-signed leaf is
    # its own issuer, and an empty file there makes `nginx -t` fail.
    cp "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" "/etc/letsencrypt/live/${DOMAIN}/chain.pem"
    cp "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" "/etc/letsencrypt/live/${DOMAIN}/cert.pem"
    chmod 0600 "/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
    chmod 0644 "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" \
               "/etc/letsencrypt/live/${DOMAIN}/chain.pem" \
               "/etc/letsencrypt/live/${DOMAIN}/cert.pem"
    echo "[bootstrap] self-signed certificate installed for ${DOMAIN} (3650 days)"
    BOOTSTRAP_DEGRADED+=("tls-self-signed")
elif [[ ! -d /etc/letsencrypt/live/$DOMAIN ]]; then
    cat > /etc/nginx/sites-available/bootstrap-http <<EOF2
server {
    listen 80 default_server;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 200 'bootstrap'; add_header Content-Type text/plain; }
}
EOF2
    ln -sfn /etc/nginx/sites-available/bootstrap-http /etc/nginx/sites-enabled/bootstrap-http
    rm -f /etc/nginx/sites-enabled/velocityai
    # Ubuntu's stock nginx package ships sites-enabled/default with its own
    # `listen 80 default_server`, which conflicts with bootstrap-http's own
    # default_server and makes `nginx -t` / reload fail with "a duplicate
    # default server for 0.0.0.0:80" — aborting firstboot before the ACME
    # cert can ever be issued. Must be removed here, not just by the later
    # reconcile step, since this reload happens first.
    rm -f /etc/nginx/sites-enabled/default
    systemctl reload nginx
    certbot certonly --webroot -w /var/www/letsencrypt \
        --non-interactive --agree-tos --email "$ACME_EMAIL" -d "$DOMAIN"
    rm /etc/nginx/sites-enabled/bootstrap-http
fi

# Certificate auto-renewal. The apt `certbot` package ships certbot.timer and
# its postinst normally enables it, but we do NOT rely on that: an unenabled
# timer is a silent 90-day fuse that ends in a hard TLS outage, and this call
# is idempotent. The renewal-heartbeat alarm (modules/monitoring/main.tf,
# cert_renew_heartbeat_stale) watches /velocityai/<env>/letsencrypt for the
# renewal log line, so it can only fire correctly if this timer runs.
systemctl enable --now certbot.timer

# Writes nginx + agent config, installs/validates/reloads nginx, then installs
# the CloudWatch agent (if absent) and applies its config via fetch-config,
# which also starts it, and installs the hourly runs-folder backup job.
# L-03/H-07: nginx stays fail-closed (exit 1 aborts bootstrap here rather than
# shipping); a DEGRADED result (exit 2: CloudWatch agent or runs backup job) is
# reported loudly but does not abort bootstrap — §14a below asserts agent
# health explicitly and feeds the BOOTSTRAP_DEGRADED gate.
set +e
bash /opt/velocityai/reconcile-host-config.sh
RECONCILE_STATUS=$?
set -e
if [[ "$RECONCILE_STATUS" -eq 1 ]]; then
    echo "[bootstrap] ERROR: reconcile-host-config.sh failed on nginx (exit 1) — aborting" >&2
    exit 1
elif [[ "$RECONCILE_STATUS" -ne 0 ]]; then
    echo "[bootstrap] WARNING: reconcile-host-config.sh exited $RECONCILE_STATUS (CloudWatch agent or runs backup job DEGRADED, see /var/log/velocityai-reconcile.log) — continuing; §14a below asserts agent health explicitly" >&2
    BOOTSTRAP_DEGRADED+=("reconcile-degraded")
fi


# ── 14a. Assert the agent is actually running (not just asked to run) ──
#
# WHY THIS IS NOT `exit 1` IN PLACE. Everything from §15 to §20 runs after
# this point: the §15 cleanup of the retired velocityai-deploy identity, the
# shared CloudWatch namespace helper, the
# pg_dump / skills-backup / stuck-workflow scripts, EVERY systemd unit
# including velocityai-app.service, the first velocityai-load-secrets run
# that materialises DATABASE_URL and SECRET_KEY into /etc/velocityai/app.env,
# the app start, and the completion sentinel. Aborting here would leave a box
# with Postgres, nginx and TLS but no application, no backups, no boot-time
# start and no sentinel — strictly worse than a blind CloudWatch agent. So the
# failure is recorded and the script continues; §20 exits non-zero.
#
# The nearest precedent in this file is the §8b IMDSv1 drift check, which
# deliberately does not exit and says "the log line is the operator signal;
# cwagent ships it". That reasoning is exactly what a dead cwagent breaks, so
# a log line alone is not sufficient here — hence the deferred non-zero exit.
#
# Two independent checks, because either one alone gives a false PASS:
#   - `systemctl is-active` alone passes while the agent is in a crash-restart
#     loop between restarts (the B1/FIX-149 failure mode: unwritable logfile).
#   - `agent-ctl -a status` alone reports the LAST requested state, and returns
#     "running" from its status file even in some cases where the unit has since
#     died, so it is not a liveness proof on its own.
# `|| return 1` is explicit rather than relying on the last command's status,
# so adding a check later cannot silently change the function's result.
assert_cloudwatch_agent_running() {
    # §14's reconcile restarts the agent via fetch-config immediately before this
    # runs, so a short settle window is genuinely useful. It is NOT, however, what
    # made this check fail on dev.
    #
    # DO NOT pipe agent-ctl into grep here. `set -o pipefail` is in force for this
    # whole script, so a pipeline inherits the exit status of the LEFT side: when
    # agent-ctl exits non-zero while printing `"status": "running"`, the check
    # reports failure even though the match succeeded. That is deterministic, not
    # a race — it is why this assertion failed all 12 attempts on a host whose
    # agent was demonstrably healthy and publishing metrics the entire time.
    # Capture the output, then match it as a plain string.
    local attempt status_json
    for attempt in $(seq 1 12); do
        status_json="$(/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
                         -a status 2>/dev/null || true)"
        # Whitespace-tolerant on purpose: agent-ctl pretty-prints today, but a
        # compact `{"status":"running"}` must not be read as stopped. The previous
        # fixed-string pattern `"status": "running"` missed that form entirely.
        if systemctl is-active --quiet amazon-cloudwatch-agent \
           && [[ "$status_json" =~ \"status\"[[:space:]]*:[[:space:]]*\"running\" ]]; then
            echo "[bootstrap] OK: CloudWatch agent is active and reporting status=running (check ${attempt}/12)"
            return 0
        fi
        sleep 5
    done

    echo "[bootstrap] ERROR: CloudWatch agent did not report status=running within 60s" >&2
    # Dump the on-box evidence. Without this the failure is undiagnosable from
    # CI: the agent log lives on the instance and the SSM command output is all
    # a reviewer ever sees, so "does not report status=running" is a dead end.
    # The .d listing is included because fetch-config MERGES every config in
    # that directory, so a stale leftover config silently changes what the
    # running agent does (e.g. a second metrics namespace).
    echo "[bootstrap] --- systemctl status amazon-cloudwatch-agent ---" >&2
    systemctl status amazon-cloudwatch-agent --no-pager -l 2>&1 | tail -n 20 >&2 || true
    echo "[bootstrap] --- agent-ctl -a status ---" >&2
    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status 2>&1 | tail -n 20 >&2 || true
    echo "[bootstrap] --- merged configs in amazon-cloudwatch-agent.d ---" >&2
    ls -la /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d/ 2>&1 | tail -n 20 >&2 || true
    echo "[bootstrap] --- tail amazon-cloudwatch-agent.log ---" >&2
    tail -n 40 /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log 2>&1 | tail -n 40 >&2 || true
    return 1
}

assert_cloudwatch_agent_running || BOOTSTRAP_DEGRADED+=("cloudwatch-agent")

# ── 15. Remove the retired velocityai-deploy SSH identity ──────────────────
# This section used to CREATE a `velocityai-deploy` system user with an
# authorized_keys file, a `/usr/local/bin/velocityai-update-image-tag` sed
# wrapper, and a sudoers stanza granting it NOPASSWD on that wrapper plus
# `systemctl restart velocityai-app.service`.
#
# All of it was CodeBuild-era: CI used to SSH in as that user and mutate
# /etc/velocityai/app.env through the wrapper. Nothing does that now.
# deploy.yml reaches this host over SSM RunCommand and remote-deploy.sh rewrites
# the image pins itself, running as root in the SSM session — so the user, the
# wrapper and the sudoers grant were an unused standing credential and an unused
# privilege escalation path. deploy.yml's own header states the design plainly:
# "no SSH, no open port 22".
#
# What remains is the REMOVAL, which must be idempotent: a host bootstrapped
# before this change still carries all three artifacts, and bootstrap is the only
# thing that runs on it regularly enough to clean them up. Every step tolerates
# absence, so this is a no-op on a fresh box.
#
# The sshd hardening drop-in in §3 is deliberately KEPT — it is not part of this
# cleanup. Break-glass human access via SSM Session Manager is unaffected: it
# does not use sshd, a local user, or port 22.
if [[ -f /etc/sudoers.d/velocityai-deploy ]]; then
    echo "[bootstrap] removing retired sudoers stanza /etc/sudoers.d/velocityai-deploy"
    rm -f /etc/sudoers.d/velocityai-deploy
fi
if [[ -f /usr/local/bin/velocityai-update-image-tag ]]; then
    echo "[bootstrap] removing retired wrapper /usr/local/bin/velocityai-update-image-tag"
    rm -f /usr/local/bin/velocityai-update-image-tag
fi
if id velocityai-deploy >/dev/null 2>&1; then
    echo "[bootstrap] removing retired user velocityai-deploy (and its home + authorized_keys)"
    # No processes should be running as it; `pkill` is tolerant of none matching.
    pkill -u velocityai-deploy >/dev/null 2>&1 || true
    userdel --remove velocityai-deploy >/dev/null 2>&1 \
        || echo "[bootstrap] WARNING: could not fully remove velocityai-deploy — check \`id velocityai-deploy\` and /home/velocityai-deploy" >&2
fi

# ── 16a. Shared CloudWatch metric namespace for on-host publishers ──────────
#
# ONE derivation site for the per-environment namespace used by every on-host
# `aws cloudwatch put-metric-data` caller. Fail-closed by design: publishers
# that cannot resolve their environment refuse to publish, loudly.
#
# The namespace MUST match modules/monitoring's cw_metric_namespace
# ("VelocityAI/" + title(environment)), which is what every alarm queries. The
# cases are spelled out literally rather than derived from the variable, so a new
# environment name fails loudly here instead of silently publishing to a
# namespace no alarm watches.
#
# Callers get VELOCITYAI_ENVIRONMENT from
# EnvironmentFile=/etc/velocityai/bootstrap.env on velocityai-pg-dump.service
# and velocityai-stuck-workflows-check.service.
# The map itself lives in host-common.sh as cw_namespace(), so this wrapper and
# reconcile-host-config.sh share ONE derivation (R-13). reconcile used
# `${ENVIRONMENT^}` instead, which is not equivalent: it happily yields
# "VelocityAI/Staging" or "VelocityAI/Qa" — a valid namespace no alarm queries, so
# metrics vanish silently and every alarm sits in INSUFFICIENT_DATA looking like a
# quiet system.
cat > /usr/local/bin/velocityai-cw-namespace <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null
. /opt/velocityai/lib/host-common.sh
if [[ -z "${VELOCITYAI_ENVIRONMENT:-}" ]]; then
    echo "velocityai-cw-namespace: VELOCITYAI_ENVIRONMENT is unset (expected from /etc/velocityai/bootstrap.env) - refusing to guess" >&2
    exit 1
fi
cw_namespace "$VELOCITYAI_ENVIRONMENT"
EOF
chmod 0755 /usr/local/bin/velocityai-cw-namespace

# ── 16. Backups: pg_dump + skills tarball + stuck-workflow probe ───────
# The hourly runs-folder backup (velocityai-runs-backup.{service,timer},
# s3://$BACKUP_BUCKET/runs/<UTC timestamp>/runs.tar.gz) is NOT here: §14's
# reconcile-host-config.sh §4b installs it, because that script also runs on
# every deploy and so reaches hosts bootstrapped before the job existed.
cat > /usr/local/bin/velocityai-pg-dump <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
: "${VELOCITYAI_BACKUP_BUCKET:?VELOCITYAI_BACKUP_BUCKET is required}"
: "${VELOCITYAI_KMS_KEY_ID:?VELOCITYAI_KMS_KEY_ID is required}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
DUMP="$TMP/velocityai-${TS}.sql.gz"
pg_dump --format=plain --no-owner --no-acl velocityai | gzip -9 > "$DUMP"
aws s3 cp "$DUMP" "s3://${VELOCITYAI_BACKUP_BUCKET}/postgres/${TS}/velocityai.sql.gz" \
    --region "${VELOCITYAI_REGION:-eu-central-1}" \
    --sse aws:kms \
    --sse-kms-key-id "$VELOCITYAI_KMS_KEY_ID"
CW_NAMESPACE=$(/usr/local/bin/velocityai-cw-namespace)
aws cloudwatch put-metric-data \
    --namespace "$CW_NAMESPACE" \
    --metric-name PgDumpHeartbeat \
    --value 1 \
    --region "${VELOCITYAI_REGION:-eu-central-1}"
echo "pg_dump complete: $(stat -c%s "$DUMP") bytes uploaded to S3; metric published to $CW_NAMESPACE"
EOF
chmod 0755 /usr/local/bin/velocityai-pg-dump

cat > /usr/local/bin/velocityai-skills-backup <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
: "${VELOCITYAI_BACKUP_BUCKET:?VELOCITYAI_BACKUP_BUCKET is required}"
: "${VELOCITYAI_KMS_KEY_ID:?VELOCITYAI_KMS_KEY_ID is required}"
TS=$(date -u +%Y%m%d)
tar -czf - -C /opt/velocityai/data skills \
    | aws s3 cp - "s3://${VELOCITYAI_BACKUP_BUCKET}/skills/${TS}.tar.gz" \
        --region "${VELOCITYAI_REGION:-eu-central-1}" \
        --sse aws:kms \
        --sse-kms-key-id "$VELOCITYAI_KMS_KEY_ID"
EOF
chmod 0755 /usr/local/bin/velocityai-skills-backup

cat > /usr/local/bin/velocityai-stuck-workflows-check <<'EOF'
#!/usr/bin/env bash
# Audit D P2-3 — push StuckRunningWorkflows custom metric.
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL is required}"
AWS_REGION="${AWS_REGION:-eu-central-1}"
HOST_DB_URL="${DATABASE_URL//host.docker.internal/127.0.0.1}"
COUNT=$(psql "$HOST_DB_URL" -tAc \
    "SELECT count(*) FROM workflow_runs \
     WHERE status='running' AND created_at < NOW() - INTERVAL '60 minutes'")
COUNT=${COUNT:-0}
CW_NAMESPACE=$(/usr/local/bin/velocityai-cw-namespace)
aws cloudwatch put-metric-data \
    --namespace "$CW_NAMESPACE" \
    --metric-name StuckRunningWorkflows \
    --value "$COUNT" \
    --region "$AWS_REGION"
EOF
chmod 0755 /usr/local/bin/velocityai-stuck-workflows-check

# ── 16b. logrotate for velocityai's own self-logs ───────────────────────
#
# M-09: /var/log/velocityai-bootstrap.log and /var/log/velocityai-reconcile.log
# are opened in append mode (`tee -a`) by both scripts and grow unbounded —
# every deploy appends to velocityai-reconcile.log (this script's own
# reconcile call, plus every CI redeploy's reconcile call, plus any manual
# SSM run). H-06 ships these off-box, but ingestion is not rotation: without
# this, the on-disk copies still grow forever between agent reads. Weekly
# rotation, 8 weeks retained, compressed — same order of magnitude as the
# disk_root_high alarm's safety margin.
cat > /etc/logrotate.d/velocityai <<'EOF'
/var/log/velocityai-*.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
chmod 0644 /etc/logrotate.d/velocityai

# ── 17. systemd units (Appendix B) ─────────────────────────────────────
cat > /etc/systemd/system/velocityai-app.service <<'EOF'
[Unit]
Description=VelocityAI app stack (backend + frontend) via Docker Compose
After=docker.service network-online.target postgresql.service
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/velocityai
EnvironmentFile=/etc/velocityai/app.env
ExecStartPre=/usr/local/bin/velocityai-load-secrets
ExecStartPre=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
ExecStart=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans
ExecStop=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.prod.yml down
ExecReload=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.prod.yml restart
TimeoutStartSec=600
Restart=on-failure
RestartSec=30s

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/velocityai-pg-dump.service <<'EOF'
[Unit]
Description=VelocityAI Postgres logical dump to S3
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=postgres
Group=postgres
EnvironmentFile=/etc/velocityai/bootstrap.env
EnvironmentFile=/etc/velocityai/app.env
ExecStart=/usr/local/bin/velocityai-pg-dump
TimeoutStartSec=600
EOF

cat > /etc/systemd/system/velocityai-pg-dump.timer <<'EOF'
[Unit]
Description=Hourly VelocityAI PG dump

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=120
Unit=velocityai-pg-dump.service

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/velocityai-skills-backup.service <<'EOF'
[Unit]
Description=VelocityAI skills backup to S3
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=velocityai
Group=velocityai
EnvironmentFile=/etc/velocityai/bootstrap.env
ExecStart=/usr/local/bin/velocityai-skills-backup
EOF

cat > /etc/systemd/system/velocityai-skills-backup.timer <<'EOF'
[Unit]
Description=Daily VelocityAI skills backup

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=600
Unit=velocityai-skills-backup.service

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/velocityai-stuck-workflows-check.service <<'EOF'
[Unit]
Description=VelocityAI stuck-running WorkflowRun probe
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=velocityai
Group=velocityai
EnvironmentFile=/etc/velocityai/bootstrap.env
EnvironmentFile=/etc/velocityai/app.env
ExecStart=/usr/local/bin/velocityai-stuck-workflows-check
TimeoutStartSec=60
EOF

cat > /etc/systemd/system/velocityai-stuck-workflows-check.timer <<'EOF'
[Unit]
Description=Run stuck-workflows probe every 15 minutes

[Timer]
OnCalendar=*:0/15
Persistent=true
RandomizedDelaySec=60
Unit=velocityai-stuck-workflows-check.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now \
    velocityai-pg-dump.timer \
    velocityai-skills-backup.timer \
    velocityai-stuck-workflows-check.timer

# ── 18. App service — load secrets, start ──────────────────────────────
/usr/local/bin/velocityai-load-secrets
# Tear down any existing containers before (re-)starting the service. This
# forces fresh containers on every bootstrap re-run, which is necessary so
# that any change to host state that influences container provisioning
# (default ACLs on /var/lib/docker/containers — see §8 above, image-tag
# pins in /etc/velocityai/app.env, etc.) takes effect even when neither the
# image digest nor compose-detectable env has changed. Idempotent: on a
# fresh box there are no containers to remove.
( cd /opt/velocityai && docker compose -f docker-compose.yml -f docker-compose.prod.yml down --remove-orphans 2>/dev/null || true )
# `systemctl enable` registers the unit at boot — idempotent, safe to
# rerun. `systemctl restart` then forces a fresh ExecStartPre+ExecStart
# cycle.
#
# This split (enable + restart) is INTENTIONAL and important — the
# previous `systemctl enable --now` collapsed both into one call, but
# `--now` is internally `enable + start`, and for a `Type=oneshot`
# service already in `Active (exited)` state from a previous bootstrap,
# `start` is a no-op. That made the first deploy succeed (unit not yet
# enabled → enable+start) but every subsequent deploy silently skip the
# `docker compose pull` + `docker compose up -d --remove-orphans` steps
# in velocityai-app.service, leaving the box running yesterday's containers
# even though /etc/velocityai/app.env now points at the new image tag.
# `systemctl restart` correctly transitions oneshot
# Active(exited) → deactivating (runs ExecStop, our `docker compose
# down`) → inactive → activating (runs ExecStartPre+ExecStart) →
# active(exited). The on-disk `docker compose down` above is redundant
# with ExecStop but kept as a belt-and-suspenders teardown for the
# rare case where the unit file's ExecStop has been edited away from
# what we expect.
systemctl enable velocityai-app.service

# ── 18b. Start the app ONLY if its images actually exist in ECR ────────────
# `systemctl restart` on a unit whose images cannot be pulled does not fail
# quietly: velocityai-app.service declares Restart=on-failure / RestartSec=30s,
# so the ExecStartPre `docker compose pull` fails, systemd retries forever, and
# the box sits in a permanent 30-second crash loop. Worse, this section runs
# under `set -e`, so the failed `restart` ABORTED the whole bootstrap before
# §20 could write /var/lib/velocityai/.bootstrap-done — and because
# velocityai-firstboot.service is gated on that sentinel's ABSENCE, every
# subsequent reboot re-ran the entire provision and failed at exactly this
# point again.
#
# A host with no deployable image yet is a LEGITIMATE state, not a defect: on a
# brand-new environment nothing has been built, and the documented contract is
# that a Deploy workflow run starts the application. So this is a clean skip —
# NOT appended to BOOTSTRAP_DEGRADED — and provisioning completes normally so
# the sentinel is written and firstboot stops re-running. The unit stays
# `enable`d, so once images exist it comes up on boot; the GitHub deploy
# (.github/scripts/remote-deploy.sh) drives `docker compose` directly and does
# not depend on this start having succeeded.
#
# The probe is a real `docker pull` rather than a registry metadata query
# because pullability by THIS host's credentials is the property that actually
# matters, and it warms the local cache so the unit's own pull is a cache hit.
# §9's ECR login is still valid here.
APP_IMAGES_AVAILABLE=1
if [[ -z "$BACKEND_IMAGE_REF" || -z "$FRONTEND_IMAGE_REF" ]]; then
    # §10b found no deploy record at all, so there is nothing to probe. Skip
    # straight to the clean-skip path below rather than calling `docker pull ""`.
    APP_IMAGES_AVAILABLE=0
else
    for _image_ref in "$BACKEND_IMAGE_REF" "$FRONTEND_IMAGE_REF"; do
        if docker pull "$_image_ref" >/dev/null 2>&1; then
            echo "[bootstrap] image available: ${_image_ref}"
        else
            echo "[bootstrap] image NOT available: ${_image_ref}" >&2
            APP_IMAGES_AVAILABLE=0
        fi
    done
fi

if [[ "$APP_IMAGES_AVAILABLE" -eq 1 ]]; then
    systemctl restart velocityai-app.service

    # ── 19. Smoke test ─────────────────────────────────────────────────
    sleep 15
    if ! curl -fsS http://127.0.0.1:8000/health; then
        echo "[bootstrap] WARN: /health probe failed — velocityai-app.service may still be starting"
        echo "[bootstrap]       check: sudo systemctl status velocityai-app.service"
        echo "[bootstrap]       check: sudo docker compose -f /opt/velocityai/docker-compose.yml -f /opt/velocityai/docker-compose.prod.yml logs --tail=200"
    fi
else
    # Clear any crash loop left by an earlier run before leaving the unit idle,
    # so `systemctl status` reflects "not started yet" rather than "failed".
    systemctl stop velocityai-app.service >/dev/null 2>&1 || true
    systemctl reset-failed velocityai-app.service >/dev/null 2>&1 || true
    echo "[bootstrap] SKIP: not starting velocityai-app.service — the pinned images are not in ECR yet."
    echo "[bootstrap]       pins came from: ${IMAGE_PIN_SOURCE}"
    echo "[bootstrap]       This is expected before the first successful Deploy workflow run."
    echo "[bootstrap]       Run the GitHub 'Deploy' workflow for this environment to build, push and start the app."
fi
# ── 20. Completion sentinel ────────────────────────────────────────────
# Signals that the full host bootstrap finished. Consumed by:
#   - velocityai-firstboot.service (its ConditionPathExists guard, so the
#     first-boot self-provision runs exactly once per instance);
#   - the CI redeploy in .github/scripts/remote-deploy.sh (formerly infra/
#     buildspec.yml), which — on a freshly-created instance that is still
#     self-provisioning — waits for this file before attempting a container
#     redeploy (avoids racing docker compose against an install that hasn't
#     put Docker on the box yet).
install -d -m 0755 /var/lib/velocityai

# The sentinel is written BEFORE the degraded gate on purpose: the host IS
# provisioned, and withholding it would make velocityai-firstboot re-run the
# whole bootstrap on every reboot and make CI's wait-for-sentinel loop time
# out. The non-zero exit below is the SIGNAL; the sentinel is STATE.
if [[ ${#BOOTSTRAP_DEGRADED[@]} -gt 0 ]]; then
    date -u --iso-8601=seconds > /var/lib/velocityai/.bootstrap-done
    echo "[bootstrap] DEGRADED: ${BOOTSTRAP_DEGRADED[*]}" >&2
    echo "[bootstrap] The host is provisioned but one or more subsystems are unhealthy." >&2
    echo "[bootstrap] complete (DEGRADED) $(date -u --iso-8601=seconds)" >&2
    exit 1
fi

date -u --iso-8601=seconds > /var/lib/velocityai/.bootstrap-done
echo "[bootstrap] complete $(date -u --iso-8601=seconds)"


