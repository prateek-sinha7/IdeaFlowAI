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
# instance-status-ok` (used by the calling deploy.sh) only confirms system
# reachability; on a fast SSM dispatch the box can report status-ok before
# cloud-init's final stage has written bootstrap.env, and we'd die at the
# file-existence check below.
echo "[bootstrap] waiting for cloud-init final stage..."
while ! cloud-init status --wait > /dev/null 2>&1; do sleep 2; done

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
#
# Also expects VELOCITYAI_IMAGE_TAG from the calling environment (deploy.sh
# `aws ssm send-command` injects this via `export` prepended to the script
# body). Defaults to "latest" for legacy compatibility, but deploy.sh
# always sets a git-sha tag so re-runs don't collide with ECR IMMUTABLE.
#
# docker-compose.yml is downloaded from s3://$VELOCITYAI_BACKUP_BUCKET/config/
# (uploaded by Terraform's aws_s3_object.compose_yaml in envs/prod/main.tf).
# The EC2 needs no git auth.
if [[ ! -f /etc/velocityai/bootstrap.env ]]; then
    echo "[bootstrap] ERROR: /etc/velocityai/bootstrap.env missing — terraform apply hasn't completed?" >&2
    exit 1
fi
# shellcheck source=/dev/null
. /etc/velocityai/bootstrap.env

IMAGE_TAG="${VELOCITYAI_IMAGE_TAG:-latest}"

REGION="${VELOCITYAI_REGION:-eu-central-1}"
DOMAIN="${VELOCITYAI_FQDN:?VELOCITYAI_FQDN missing in /etc/velocityai/bootstrap.env}"
PARAM_PREFIX="${VELOCITYAI_PARAM_PREFIX:-/velocityai/prod}"
ENVIRONMENT="${VELOCITYAI_ENVIRONMENT:-prod}"
# Capitalize first letter for CloudWatch namespace ("prod" -> "Prod"). Matches
# the monitoring module's `cw_metric_namespace = "VelocityAI/${title(env)}"`.
ENV_TITLE="${ENVIRONMENT^}"
ACME_EMAIL="${VELOCITYAI_ACME_EMAIL:-security@example.com}"
BACKUP_BUCKET="${VELOCITYAI_BACKUP_BUCKET:?VELOCITYAI_BACKUP_BUCKET missing in /etc/velocityai/bootstrap.env}"
DATA_DEV=/dev/nvme1n1
DATA_MOUNT=/var/lib/postgresql
APP_USER=velocityai

# ── 2. Patch & baseline tools ──────────────────────────────────────────
export DEBIAN_FRONTEND=noninteractive
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
# Ubuntu's apt repo no longer ships awscli; AWS-recommended path is to
# download the v2 self-contained binary directly. Idempotent: `aws/install
# --update` is a no-op if v2 is already installed at the same/newer version.
# Pinning the version (vs latest) makes deploys reproducible; bump
# AWSCLI_VERSION here to roll forward.
AWSCLI_VERSION="2.17.42"
if ! command -v aws >/dev/null 2>&1 \
    || [[ "$(aws --version 2>&1 | awk -F'[/ ]' '{print $2}')" != "${AWSCLI_VERSION}" ]]; then
    AWSCLI_TMP="$(mktemp -d)"
    trap 'rm -rf "$AWSCLI_TMP"' EXIT
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-${AWSCLI_VERSION}.zip" \
        -o "${AWSCLI_TMP}/awscliv2.zip"
    unzip -q "${AWSCLI_TMP}/awscliv2.zip" -d "${AWSCLI_TMP}"
    "${AWSCLI_TMP}/aws/install" --update --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli
    rm -rf "$AWSCLI_TMP"
    trap - EXIT
fi
echo "[bootstrap] aws cli version: $(aws --version)"

# ── 3. Firewall + SSH hardening + unattended upgrades ──────────────────
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
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
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker

echo "[bootstrap] Docker installed: $(docker --version), $(docker compose version)"

# ── 8b. IMDS containment for the pptx_export Node subprocess (C2-2) ────
#
# Audit C / TF-Sec CRITICAL-2: the pptx_export.py service spawns a Node
# subprocess running LLM-generated rendering code. G1-C1 hardened that
# subprocess with:
#   - scrubbed env (no AWS_*, DATABASE_URL, SECRET_KEY in the child env)
#   - prlimit-style rlimits (CPU, AS, NOFILE)
#   - a Semaphore that caps concurrency at 3
# But the child INHERITS the container's network namespace. Inside that
# namespace, 169.254.169.254 (IMDSv2) is reachable because
# `infra/modules/compute/main.tf` sets `http_put_response_hop_limit = 2`
# — required so Docker's bridge can forward IMDS to ANY container — and
# the EC2 security group can't block link-local IMDS (it bypasses VPC
# routing entirely; 169.254.169.254 is reached via a special hypervisor
# route not visible to security groups).
#
# The Node child can therefore call:
#   curl -sH "X-aws-ec2-metadata-token-ttl-seconds: 21600" -X PUT \
#     http://169.254.169.254/latest/api/token \
#     | xargs -I{} curl -H "X-aws-ec2-metadata-token: {}" \
#     http://169.254.169.254/latest/meta-data/iam/security-credentials/<role>
# …and exfiltrate STS credentials valid for ~6h. Those credentials carry
# Bedrock invoke, SSM Get* on /velocityai/${ENV}/*, KMS Decrypt against the
# project CMK, and S3 PutObject on the backup bucket.
#
# ── Why we can NOT cleanly block this in bootstrap-ec2.sh today ────────
#
# Five candidate enforcement points, four of them broken for our shape:
#
# 1. `iptables -I DOCKER-USER -d 169.254.169.254 -j DROP`
#    Drops IMDS from ALL containers. But the BACKEND container ALSO uses
#    IMDS via boto3 (instance-role credential resolution chain). Blocking
#    all containers breaks legitimate boto3 → SSM / Bedrock / S3 calls.
#    Verdict: REJECTED — would break the running service.
#
# 2. `iptables -A OUTPUT -m owner --uid-owner 10001 -d 169.254.169.254 -j DROP`
#    Drops IMDS from any process running as uid 10001 on the host. But
#    UID 10001 inside the container does NOT map to UID 10001 on the host
#    in our config — there's no user namespace, but the OUTPUT chain on
#    the host doesn't see traffic that originates from inside Docker's
#    bridge network anyway (it goes through the FORWARD path with the
#    container's bridge IP as source). The `--uid-owner` match requires
#    locally-originating traffic. Verdict: REJECTED — no effect on
#    bridge-network-originating IMDS attempts.
#
# 3. cgroup-based block: `iptables -A OUTPUT -m cgroup --cgroup <id>`
#    Container processes ARE in distinct cgroups (per docker), but the
#    Node subprocess inherits the backend container's cgroup. Distinguishing
#    parent (backend uvicorn) from child (Node) by cgroup is not feasible
#    inside the same container's namespace.
#    Verdict: REJECTED — same-cgroup parent and child are indistinguishable.
#
# 4. `unshare -n` (network-namespace isolation for the Node child)
#    pptx_export.py:48 documents the rejection: "unshare -n would require
#    CAP_SYS_ADMIN we don't grant." Granting it would let the LLM-generated
#    Node code mount filesystems, escape the cgroup, etc. — worse than the
#    IMDS surface. Verdict: REJECTED — net negative.
#
# 5. Per-process network namespace via a setuid wrapper that drops IMDS
#    and then exec's Node:
#    Possible in principle but: (a) requires us to ship a setuid binary
#    inside the container, which we explicitly reject as a hardening
#    practice; (b) the LLM-generated Node code could just curl 169.254.x
#    after the wrapper exec's — the wrapper drops privileges but doesn't
#    keep the namespace, since unshare -n requires CAP_SYS_ADMIN per (4).
#    Verdict: REJECTED — same blocker as (4).
#
# ── What we DO have ────────────────────────────────────────────────────
#
# Containment is currently layered as follows:
#   (a) process-level — env-scrubbed subprocess (pptx_export.py:277-320),
#       so even if Node calls IMDS the IAM creds are fresh, not the long-
#       lived host vars.
#   (b) process-level — rlimits cap CPU, address space, file descriptors.
#   (c) process-level — concurrency cap (Semaphore = 3 max parallel).
#   (d) VPC-egress level — the EC2 security group restricts the host's
#       egress to {80, 443, 53, VPC-internal endpoint ranges}; an
#       attacker exfiltrating credentials over arbitrary TCP ports is
#       blocked at the SG. (Bedrock, SSM, KMS are 443 — that's what the
#       SG INTENDS to allow because the legitimate workload needs them.)
#   (e) detection — Phase C C2-1 (this branch, modules/monitoring) adds a
#       CloudTrail trail + metric filter + CloudWatch alarm on any
#       SSM Get* on /velocityai/${ENV}/* or KMS Decrypt from a principal
#       OTHER than the instance role. An LLM-RCE-exfil attempt would
#       trigger the UnexpectedSecretRead / UnexpectedKmsDecrypt alarm
#       within 5 minutes — the "find out" surface for the surface (d)
#       leaves open.
#
# ── The REAL fix (deferred to a follow-up branch) ──────────────────────
#
# Sidecar refactor: spin a separate `pptx-renderer` container in
# docker-compose.yml with:
#   network_mode: "none"     # NO network namespace at all — can't reach 169.254
#   read_only: true
#   cap_drop: [ALL]
#   pids_limit: 32
#   mem_limit: 256m
#   cpus: 0.5
# The backend (FastAPI) then HTTP-POSTs `js_code` to the renderer over
# the internal compose network (which the renderer ISN'T attached to —
# they share a unix socket bind-mounted from the host, or the backend
# `docker exec`s a one-shot command into the renderer). The renderer
# can't reach IMDS because it has no network namespace; the backend
# (which DOES need IMDS for boto3) keeps its current network and
# never executes LLM-generated code itself.
#
# TODO(C3-x, separate PR — see docs/_audit/TRIAGE_PHASE_C.md group C3):
#   1. Add `pptx-renderer` service to docker-compose.yml with `network_mode: none`.
#   2. Build a minimal Node-only image (no boto3, no AWS SDK, no curl).
#   3. Refactor pptx_export.py to POST js_code to the renderer over a
#      unix-domain socket bind-mounted from the host into both containers.
#   4. Once landed, this whole §8b comment block can be deleted (the
#      sidecar's `network_mode: none` is the real fix; the layered
#      controls (a)-(e) above become defence-in-depth rather than the
#      primary control).
#
# Until then, the layered controls above are what we have. This section
# adds NO iptables rule because every candidate rule is either ineffective
# (rejected in 1-5 above) or breaks legitimate backend traffic.
#
# What this section DOES add: assertion checks. The TF compute module
# (`infra/modules/compute/main.tf::metadata_options`) is the authoritative
# source for IMDS posture (http_tokens=required, hop_limit=2). The
# instance role does NOT carry `ec2:ModifyInstanceMetadataOptions` (we
# don't want the host able to grant itself more permissive IMDS), so the
# bootstrap can only OBSERVE the current setting, not re-assert it.
#
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

# deploy.env (aws_s3_object.deploy_env, app layer) carries the resolved image
# URIs for the deployed tag against the SHARED repos (velocityai/backend +
# velocityai/frontend — built once, promoted by tag). It is authoritative; the
# CI redeploy and this bootstrap both read it. Fall back to constructing the
# refs from VELOCITYAI_IMAGE_TAG on a very first boot before the first apply.
DEPLOY_BACKEND_IMAGE=""
DEPLOY_FRONTEND_IMAGE=""
if aws s3 cp "s3://${BACKUP_BUCKET}/config/deploy.env" /tmp/deploy.env --region "$REGION" 2>/dev/null; then
    DEPLOY_BACKEND_IMAGE="$(grep -E '^BACKEND_IMAGE=' /tmp/deploy.env | cut -d= -f2-)"
    DEPLOY_FRONTEND_IMAGE="$(grep -E '^FRONTEND_IMAGE=' /tmp/deploy.env | cut -d= -f2-)"
    rm -f /tmp/deploy.env
fi
BACKEND_IMAGE_REF="${DEPLOY_BACKEND_IMAGE:-${ECR_REGISTRY}/velocityai/backend:${IMAGE_TAG}}"
FRONTEND_IMAGE_REF="${DEPLOY_FRONTEND_IMAGE:-${ECR_REGISTRY}/velocityai/frontend:${IMAGE_TAG}}"

# ── 11. /etc/velocityai/app.env image-tag pin ──────────────────────────────
# ECR repos are IMMUTABLE — deploy.sh pushes :<git-sha> (never :latest).
# On every bootstrap run we overwrite the BACKEND_IMAGE / FRONTEND_IMAGE
# pin lines so a redeploy points at the just-pushed tag; velocityai-load-secrets
# preserves these pin lines on subsequent velocityai-app.service starts (it
# only reloads SSM-sourced secrets, not the image pins).
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
# The loader preserves BACKEND_IMAGE / FRONTEND_IMAGE / ENV / VELOCITYAI_* lines
# below; everything else is overwritten from SSM ${PARAM_PREFIX}/*.

EOF
fi
cat >> /etc/velocityai/app.env.new <<EOF
ENV=production
BACKEND_IMAGE=${BACKEND_IMAGE_REF}
FRONTEND_IMAGE=${FRONTEND_IMAGE_REF}
VELOCITYAI_ENVIRONMENT=${ENVIRONMENT}
VELOCITYAI_CW_LOG_GROUP=/velocityai/${ENVIRONMENT}/app
EOF
mv /etc/velocityai/app.env.new /etc/velocityai/app.env
chown root:"$APP_USER" /etc/velocityai/app.env
chmod 0640 /etc/velocityai/app.env

# ── 12. /usr/local/bin/velocityai-load-secrets ─────────────────────────────
# Quoted heredoc — no shell expansion at install time. The generated script
# sources /etc/velocityai/bootstrap.env at run time, so REGION/PREFIX/FQDN come
# from whatever Terraform last wrote, not from this bootstrap's invocation.
cat > /usr/local/bin/velocityai-load-secrets <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

# Read REGION / PREFIX / FQDN from the same bootstrap.env Terraform writes
# via user_data. Lets `terraform apply` change any of these without a
# re-bootstrap — next velocityai-app.service restart picks them up.
# shellcheck source=/dev/null
. /etc/velocityai/bootstrap.env

OUT=/etc/velocityai/app.env
TMP=$(mktemp /etc/velocityai/app.env.XXXXXX)
chmod 0640 "$TMP"; chown root:velocityai "$TMP"

REGION="${VELOCITYAI_REGION:-eu-central-1}"
PREFIX="${VELOCITYAI_PARAM_PREFIX:-/velocityai/prod}"
DOMAIN="${VELOCITYAI_FQDN:-}"

# Preserve CI-managed image-tag pins + the operator-defined ENV.
if [[ -f "$OUT" ]]; then
    grep -E '^(BACKEND_IMAGE|FRONTEND_IMAGE|ENV)=' "$OUT" >> "$TMP" || true
fi

emit() {
    # Raw VAR=VALUE (no shell-quoting). Both systemd's EnvironmentFile
    # parser and Docker Compose's env-file reader treat everything after
    # the first `=` up to end-of-line as the literal value. Previously
    # this used `printf %s=%q` which works for shell re-evaluation but
    # produces backslash-escaped output (e.g. `CORS_ORIGINS=\[\"…\"\]`)
    # that systemd/Compose pass through verbatim, breaking JSON-shaped
    # values like CORS_ORIGINS (pydantic_settings sees the backslashes
    # and json.loads raises). SSM parameter values are guaranteed not to
    # contain literal newlines, so raw VAR=VALUE is safe here.
    printf '%s=%s\n' "$1" "$2" >> "$TMP"
}

CORS_SET=0
PUBLIC_BASE_URL_SET=0
while IFS=$'\t' read -r name value; do
    rel="${name#${PREFIX}/}"
    case "$rel" in
        CORS_ORIGINS)
            # Empty/missing CORS_ORIGINS in SSM triggers the FQDN fallback
            # below — the operator only has to populate this parameter for
            # multi-origin deployments (staging mirror, alternate domain, …).
            if [[ -n "$value" ]]; then
                emit CORS_ORIGINS "$value"
                CORS_SET=1
            fi
            ;;
        PUBLIC_BASE_URL)
            # Same FQDN-fallback shape as CORS_ORIGINS. Set this parameter only
            # when the public URL diverges from https://${VELOCITYAI_FQDN} (custom
            # apex domain, CDN in front, etc.). The /velocityai-handoff installer
            # endpoint reads PUBLIC_BASE_URL to format the curl|bash one-liner
            # baked into ~/.claude/commands/velocityai-handoff.md.
            if [[ -n "$value" ]]; then
                emit PUBLIC_BASE_URL "$value"
                PUBLIC_BASE_URL_SET=1
            fi
            ;;
        SECRET_KEY|ACCESS_TOKEN_EXPIRE_HOURS|LANGSMITH_TRACING|LANGSMITH_API_KEY|LANGSMITH_PROJECT|HANDOFF_MAX_TRANSCRIPT_BYTES)
            emit "$rel" "$value" ;;
        DATABASE_PASSWORD)
            emit DATABASE_URL "postgresql://velocityai:${value}@host.docker.internal:5432/velocityai" ;;
        llm/region)               emit AWS_REGION                  "$value" ;;
        llm/model_id)             emit BEDROCK_MODEL_ID            "$value" ;;
        llm/inference_profile_id) emit BEDROCK_INFERENCE_PROFILE_ID "$value" ;;
        llm/coding_model_id)      emit BEDROCK_CODING_MODEL_ID     "$value" ;;
        *)
            echo "[velocityai-load-secrets] WARN: ignoring unknown parameter ${name}" >&2 ;;
    esac
done < <(aws ssm get-parameters-by-path \
            --path "$PREFIX" --recursive --with-decryption \
            --region "$REGION" \
            --query 'Parameters[].[Name,Value]' --output text)

# Fallback: if SSM didn't supply a non-empty CORS_ORIGINS, default to a
# single-origin list containing the FQDN we're serving from. Matches the
# common case (single domain) and lets the operator opt-out by setting
# /velocityai/$env/CORS_ORIGINS to a non-empty JSON list.
if [[ "$CORS_SET" -eq 0 && -n "$DOMAIN" ]]; then
    emit CORS_ORIGINS "[\"https://${DOMAIN}\"]"
fi

# Same fallback for PUBLIC_BASE_URL — when SSM didn't override, derive from
# the FQDN Terraform wrote into bootstrap.env. This is what the handoff
# installer endpoint will hand back to users in the curl|bash one-liner.
if [[ "$PUBLIC_BASE_URL_SET" -eq 0 && -n "$DOMAIN" ]]; then
    emit PUBLIC_BASE_URL "https://${DOMAIN}"
fi

mv "$TMP" "$OUT"
chmod 0640 "$OUT"; chown root:velocityai "$OUT"
EOF
chmod +x /usr/local/bin/velocityai-load-secrets

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
    echo "[bootstrap] reconcile-host-config.sh not available yet (attempt $i) — retrying"
    sleep 10
done
[[ -s /opt/velocityai/reconcile-host-config.sh ]] || {
    echo "[bootstrap] ERROR: could not fetch reconcile-host-config.sh from S3" >&2; exit 1; }
chmod 0755 /opt/velocityai/reconcile-host-config.sh

# Initial cert (HTTP-01 webroot) — only if no cert exists yet for this domain.
# Runs BEFORE the reconcile so the reconcile's `nginx -t` has a certificate to
# validate against. The temporary bootstrap-http site below only needs the
# webroot, not the real site file.
if [[ ! -d /etc/letsencrypt/live/$DOMAIN ]]; then
    cat > /etc/nginx/sites-available/bootstrap-http <<EOF2
server {
    listen 80 default_server;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 200 'bootstrap'; add_header Content-Type text/plain; }
}
EOF2
    ln -sfn /etc/nginx/sites-available/bootstrap-http /etc/nginx/sites-enabled/bootstrap-http
    rm -f /etc/nginx/sites-enabled/velocityai
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
# which also starts it. L-03/H-07: nginx stays fail-closed (exit 1 aborts
# bootstrap here rather than shipping); a CloudWatch-agent-only DEGRADED
# result (exit 2) is reported loudly but does not abort bootstrap — §14a below
# asserts agent health explicitly and feeds the BOOTSTRAP_DEGRADED gate.
set +e
bash /opt/velocityai/reconcile-host-config.sh
RECONCILE_STATUS=$?
set -e
if [[ "$RECONCILE_STATUS" -eq 1 ]]; then
    echo "[bootstrap] ERROR: reconcile-host-config.sh failed on nginx (exit 1) — aborting" >&2
    exit 1
elif [[ "$RECONCILE_STATUS" -ne 0 ]]; then
    echo "[bootstrap] WARNING: reconcile-host-config.sh exited $RECONCILE_STATUS (CloudWatch-agent DEGRADED, see /var/log/velocityai-reconcile.log) — continuing; §14a below asserts agent health explicitly" >&2
    BOOTSTRAP_DEGRADED+=("reconcile-cwagent")
fi


# ── 14a. Assert the agent is actually running (not just asked to run) ──
#
# WHY THIS IS NOT `exit 1` IN PLACE. Everything from §15 to §20 runs after
# this point: the velocityai-deploy user + its restricted sudoers, the
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
    if ! systemctl is-active --quiet amazon-cloudwatch-agent; then
        echo "[bootstrap] ERROR: amazon-cloudwatch-agent unit is not active" >&2
        return 1
    fi
    if ! /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
           -a status 2>/dev/null | grep -q '"status": "running"'; then
        echo "[bootstrap] ERROR: amazon-cloudwatch-agent-ctl does not report status=running" >&2
        return 1
    fi
    echo "[bootstrap] OK: CloudWatch agent is active and reporting status=running"
    return 0
}

assert_cloudwatch_agent_running || BOOTSTRAP_DEGRADED+=("cloudwatch-agent")

# ── 15. velocityai-deploy user + restricted sudoers + image-tag wrapper ────
if ! id velocityai-deploy >/dev/null 2>&1; then
    useradd --system --create-home --shell /bin/bash velocityai-deploy
    install -d -o velocityai-deploy -g velocityai-deploy -m 0700 /home/velocityai-deploy/.ssh
    install -o velocityai-deploy -g velocityai-deploy -m 0600 /dev/null \
        /home/velocityai-deploy/.ssh/authorized_keys
fi

cat > /usr/local/bin/velocityai-update-image-tag <<'WRAPPER'
#!/bin/bash
# /usr/local/bin/velocityai-update-image-tag — called by `sudo` from CI.
# Usage: velocityai-update-image-tag (backend|frontend) <image_uri>
set -euo pipefail
if [ "$#" -ne 2 ]; then
    echo "ERROR: usage: $0 (backend|frontend) <image_uri>" >&2
    exit 64
fi
component="$1"
image="$2"
case "$component" in
    backend|frontend) ;;
    *) echo "ERROR: component must be backend or frontend, got: $component" >&2; exit 65 ;;
esac
if [ "${#image}" -gt 255 ] || ! [[ "$image" =~ ^[a-z0-9._/:-]+$ ]]; then
    echo "ERROR: image URI rejected — must match ^[a-z0-9._/:-]+$ (max 255 chars)" >&2
    exit 66
fi
upper="${component^^}"
sed -i.bak "s|^${upper}_IMAGE=.*|${upper}_IMAGE=${image}|" /etc/velocityai/app.env
rm -f /etc/velocityai/app.env.bak
WRAPPER
chmod 0755 /usr/local/bin/velocityai-update-image-tag
chown root:root /usr/local/bin/velocityai-update-image-tag

# Restricted sudoers via visudo -cf to refuse a malformed install.
#
# L-02: a single `trap ... RETURN`-style cleanup replaces the previous two
# separate `rm -f "$SUDOERS_TMP"` lines (one in the failure branch, one after
# the `if`) — a leftover from a careless edit pass. `trap` here fires on the
# function/script's own EXIT, which is safe because this file has no other
# EXIT trap active at this point (grep confirms: this is the only trap in
# the whole script).
SUDOERS_TMP=$(mktemp)
trap 'rm -f "$SUDOERS_TMP"' EXIT
cat > "$SUDOERS_TMP" <<'SUDO'
# /etc/sudoers.d/velocityai-deploy — generated by VelocityAI bootstrap.
velocityai-deploy ALL=(root) NOPASSWD: /usr/local/bin/velocityai-update-image-tag backend *
velocityai-deploy ALL=(root) NOPASSWD: /usr/local/bin/velocityai-update-image-tag frontend *
velocityai-deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart velocityai-app.service
SUDO
chmod 0440 "$SUDOERS_TMP"
if visudo -cf "$SUDOERS_TMP"; then
    install -o root -g root -m 0440 "$SUDOERS_TMP" /etc/sudoers.d/velocityai-deploy
else
    echo "[bootstrap] ERROR: velocityai-deploy sudoers stanza failed visudo check" >&2
    exit 1
fi
trap - EXIT
rm -f "$SUDOERS_TMP"

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
cat > /usr/local/bin/velocityai-cw-namespace <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${VELOCITYAI_ENVIRONMENT:-}" ]]; then
    echo "velocityai-cw-namespace: VELOCITYAI_ENVIRONMENT is unset (expected from /etc/velocityai/bootstrap.env) - refusing to guess" >&2
    exit 1
fi
case "$VELOCITYAI_ENVIRONMENT" in
    dev)   echo "VelocityAI/Dev"   ;;
    stage) echo "VelocityAI/Stage" ;;
    prod)  echo "VelocityAI/Prod"  ;;
    *)
        echo "velocityai-cw-namespace: unknown environment '$VELOCITYAI_ENVIRONMENT' (expected dev|stage|prod)" >&2
        exit 1
        ;;
esac
EOF
chmod 0755 /usr/local/bin/velocityai-cw-namespace

# ── 16. Backups: pg_dump + skills tarball + stuck-workflow probe ───────
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
systemctl restart velocityai-app.service

# ── 19. Smoke test ─────────────────────────────────────────────────────
sleep 15
if ! curl -fsS http://127.0.0.1:8000/health; then
    echo "[bootstrap] WARN: /health probe failed — velocityai-app.service may still be starting"
    echo "[bootstrap]       check: sudo systemctl status velocityai-app.service"
    echo "[bootstrap]       check: sudo docker compose -f /opt/velocityai/docker-compose.yml -f /opt/velocityai/docker-compose.prod.yml logs --tail=200"
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


