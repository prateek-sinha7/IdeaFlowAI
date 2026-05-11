#!/usr/bin/env bash
# Flowin production EC2 bootstrap.
#
# Materialized form of docs/SIMPLE_AWS_DEPLOYMENT.md Appendix D — runnable,
# idempotent, ~6 minutes wall-clock on a clean box.
#
# Detects two modes at run:
#   - Fresh provision (data volume blank): formats + initdb, generates DB
#     password into SSM, installs all packages, fetches docker-compose.yml,
#     authenticates to ECR, brings up flowin-app.service.
#   - Recovery from snapshot (data volume already has xfs + a Postgres
#     data dir): skips initdb, reuses existing DB password from SSM,
#     same Docker / ECR / image-pull path.
#
# Invocation: this is normally run from the EC2's first-boot phase via SSM
# RunCommand AFTER cloud-init has placed /etc/flowin/bootstrap.env on disk
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
exec > >(tee -a /var/log/flowin-bootstrap.log) 2>&1
echo "[bootstrap] start $(date -u --iso-8601=seconds)"

if [[ "$EUID" -ne 0 ]]; then
    echo "[bootstrap] ERROR: must run as root (or via sudo)" >&2
    exit 1
fi

# ── 0. Wait for cloud-init to finish ───────────────────────────────────
# Must come BEFORE sourcing /etc/flowin/bootstrap.env: that file is written
# by user_data which runs as cloud-init's final stage. `aws ec2 wait
# instance-status-ok` (used by the calling deploy.sh) only confirms system
# reachability; on a fast SSM dispatch the box can report status-ok before
# cloud-init's final stage has written bootstrap.env, and we'd die at the
# file-existence check below.
echo "[bootstrap] waiting for cloud-init final stage..."
while ! cloud-init status --wait > /dev/null 2>&1; do sleep 2; done

# ── 1. Source operator-controlled values written by user_data ──────────
#
# /etc/flowin/bootstrap.env is created by Terraform's compute module user_data
# (see infra/modules/compute/user_data.sh.tpl). It carries:
#   FLOWIN_REGION         — AWS region (e.g. eu-central-1)
#   FLOWIN_PARAM_PREFIX   — SSM Parameter Store prefix, e.g. /flowin/prod
#   FLOWIN_ENVIRONMENT    — short env tag (prod / staging / …)
#   FLOWIN_FQDN           — public hostname (nip.io or Route 53)
#   FLOWIN_KMS_KEY_ID     — project CMK ARN/alias for backup encryption
#   FLOWIN_BACKUP_BUCKET  — S3 bucket for pg_dump + skills tarballs
#   FLOWIN_ECR_REGISTRY   — <ACCOUNT>.dkr.ecr.<region>.amazonaws.com
#   FLOWIN_ACME_EMAIL     — email for Let's Encrypt registration
#
# Also expects FLOWIN_IMAGE_TAG from the calling environment (deploy.sh
# `aws ssm send-command` injects this via `export` prepended to the script
# body). Defaults to "latest" for legacy compatibility, but deploy.sh
# always sets a git-sha tag so re-runs don't collide with ECR IMMUTABLE.
#
# docker-compose.yml is downloaded from s3://$FLOWIN_BACKUP_BUCKET/config/
# (uploaded by Terraform's aws_s3_object.compose_yaml in envs/prod/main.tf).
# The EC2 needs no git auth.
if [[ ! -f /etc/flowin/bootstrap.env ]]; then
    echo "[bootstrap] ERROR: /etc/flowin/bootstrap.env missing — terraform apply hasn't completed?" >&2
    exit 1
fi
# shellcheck source=/dev/null
. /etc/flowin/bootstrap.env

IMAGE_TAG="${FLOWIN_IMAGE_TAG:-latest}"

REGION="${FLOWIN_REGION:-eu-central-1}"
DOMAIN="${FLOWIN_FQDN:?FLOWIN_FQDN missing in /etc/flowin/bootstrap.env}"
PARAM_PREFIX="${FLOWIN_PARAM_PREFIX:-/flowin/prod}"
ENVIRONMENT="${FLOWIN_ENVIRONMENT:-prod}"
# Capitalize first letter for CloudWatch namespace ("prod" -> "Prod"). Matches
# the monitoring module's `cw_metric_namespace = "Flowin/${title(env)}"`.
ENV_TITLE="${ENVIRONMENT^}"
ACME_EMAIL="${FLOWIN_ACME_EMAIL:-security@example.com}"
BACKUP_BUCKET="${FLOWIN_BACKUP_BUCKET:?FLOWIN_BACKUP_BUCKET missing in /etc/flowin/bootstrap.env}"
DATA_DEV=/dev/nvme1n1
DATA_MOUNT=/var/lib/postgresql
APP_USER=flowin

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

cat >/etc/ssh/sshd_config.d/10-flowin.conf <<'EOF'
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

cat >/etc/apt/apt.conf.d/52flowin <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF
systemctl enable --now unattended-upgrades

timedatectl set-timezone UTC

# ── 4. Application user + directories ──────────────────────────────────
id -u "$APP_USER" >/dev/null 2>&1 \
    || useradd -r -m -d /opt/flowin -s /usr/sbin/nologin "$APP_USER"
mkdir -p /opt/flowin /opt/flowin/data/skills /var/log/flowin /etc/flowin
chown -R "$APP_USER:$APP_USER" /opt/flowin /var/log/flowin
chown root:"$APP_USER" /etc/flowin
chmod 0750 /etc/flowin

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
    mkfs.xfs -L flowin-data "$DATA_DEV"
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
# DATABASE_URL is composed at app-start by /usr/local/bin/flowin-load-secrets
# from this same password; we don't store DATABASE_URL in SSM separately.)
PG_DATA="$DATA_MOUNT/16/main"
if [[ $RECOVERY -eq 0 ]]; then
    # PostgreSQL 16 initdb syntax notes:
    #   - `--pwprompt` is a flag (no value); the previous `--pwprompt=false`
    #     made initdb error with "option '--pwprompt' doesn't allow an
    #     argument" and the bootstrap died here.
    #   - Match the Debian/Ubuntu pg_createcluster default: peer for the
    #     local Unix socket (so `sudo -u postgres psql` works without
    #     password), scram-sha-256 for TCP (the flowin app container
    #     connects over TCP with a real password from SSM).
    #   - No --pwfile / --pwprompt: the postgres SUPERUSER role gets no
    #     password set at initdb time. The flowin role created in the next
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
CREATE USER flowin WITH ENCRYPTED PASSWORD '$DB_PW';
CREATE DATABASE flowin OWNER flowin;
\c flowin
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO flowin;
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
echo 'vm.swappiness = 10' > /etc/sysctl.d/99-flowin.conf

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

# POSIX ACL so cwagent can read /var/lib/docker/containers/*.log without
# being in the docker group (docker.sock = root-equivalent). `|| true`
# because the cwagent user may not exist yet — repeated after cwagent install
# in §13.
#
# `o::r` is intentional and load-bearing. /var/lib/docker/containers is
# mode 0710 by default — owner:root, group:root, other:---. When setfacl
# sets a default ACL it inherits the dir's current "other" bits as the
# default for new files. That meant new container bind-mount files
# (notably /etc/hosts, which docker generates per container and bind-mounts
# in) got mode 0640 — readable only by root and the cwagent named entry.
# Containers running as a non-root user (our Dockerfile sets uid 10001
# `flowin`) then can't read /etc/hosts and DNS lookups for entries we
# added via `extra_hosts: host.docker.internal:host-gateway` fail with
# "Temporary failure in name resolution". Forcing `o::r` here restores the
# normal world-readable /etc/hosts so app containers can use the host.
setfacl -R -m u:cwagent:rX,o::r /var/lib/docker/containers || true
setfacl -R -d -m u:cwagent:rX,o::r /var/lib/docker/containers || true

echo "[bootstrap] Docker installed: $(docker --version), $(docker compose version)"

# ── 9. ECR login + refresh timer ───────────────────────────────────────
ECR_REGISTRY="${FLOWIN_ECR_REGISTRY:-}"
if [[ -z "$ECR_REGISTRY" ]]; then
    echo "[bootstrap] ERROR: FLOWIN_ECR_REGISTRY not set" >&2
    exit 1
fi

aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY"

cat > /etc/systemd/system/flowin-ecr-login.service <<'UNIT'
[Unit]
Description=Refresh Docker login to ECR
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/flowin/bootstrap.env
ExecStart=/bin/bash -c '/usr/local/bin/aws ecr get-login-password --region $FLOWIN_REGION | /usr/bin/docker login --username AWS --password-stdin $FLOWIN_ECR_REGISTRY'
UNIT

cat > /etc/systemd/system/flowin-ecr-login.timer <<'TIMER'
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
systemctl enable --now flowin-ecr-login.timer

# ── 10. docker-compose.yml from S3 ─────────────────────────────────────
# Terraform's envs/prod aws_s3_object.compose_yaml uploads the canonical
# docker-compose.yml to s3://$BACKUP_BUCKET/config/docker-compose.yml on
# every apply. The instance role's s3-config-read policy grants GetObject
# on that exact prefix. Re-running this script picks up the latest file.
aws s3 cp "s3://${BACKUP_BUCKET}/config/docker-compose.yml" \
    /opt/flowin/docker-compose.yml --region "$REGION"
chown "$APP_USER:$APP_USER" /opt/flowin/docker-compose.yml
chmod 0644 /opt/flowin/docker-compose.yml

# ── 11. /etc/flowin/app.env image-tag pin ──────────────────────────────
# ECR repos are IMMUTABLE — deploy.sh pushes :<git-sha> (never :latest).
# On every bootstrap run we overwrite the BACKEND_IMAGE / FRONTEND_IMAGE
# pin lines so a redeploy points at the just-pushed tag; flowin-load-secrets
# preserves these pin lines on subsequent flowin-app.service starts (it
# only reloads SSM-sourced secrets, not the image pins).
mkdir -p /etc/flowin
if [[ -f /etc/flowin/app.env ]]; then
    # Strip the three managed lines; keep everything else operators added.
    grep -vE '^(ENV|BACKEND_IMAGE|FRONTEND_IMAGE)=' /etc/flowin/app.env \
        > /etc/flowin/app.env.new || true
else
    # Fresh box: seed with the header comment so future operators know
    # where these values come from.
    cat > /etc/flowin/app.env.new <<EOF
# Populated by /usr/local/bin/flowin-load-secrets on every flowin-app start.
# The loader preserves BACKEND_IMAGE / FRONTEND_IMAGE / ENV lines below;
# everything else is overwritten from SSM ${PARAM_PREFIX}/*.

EOF
fi
cat >> /etc/flowin/app.env.new <<EOF
ENV=production
BACKEND_IMAGE=${ECR_REGISTRY}/flowin-${ENVIRONMENT}-backend:${IMAGE_TAG}
FRONTEND_IMAGE=${ECR_REGISTRY}/flowin-${ENVIRONMENT}-frontend:${IMAGE_TAG}
EOF
mv /etc/flowin/app.env.new /etc/flowin/app.env
chown root:"$APP_USER" /etc/flowin/app.env
chmod 0640 /etc/flowin/app.env

# ── 12. /usr/local/bin/flowin-load-secrets ─────────────────────────────
# Quoted heredoc — no shell expansion at install time. The generated script
# sources /etc/flowin/bootstrap.env at run time, so REGION/PREFIX/FQDN come
# from whatever Terraform last wrote, not from this bootstrap's invocation.
cat > /usr/local/bin/flowin-load-secrets <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

# Read REGION / PREFIX / FQDN from the same bootstrap.env Terraform writes
# via user_data. Lets `terraform apply` change any of these without a
# re-bootstrap — next flowin-app.service restart picks them up.
# shellcheck source=/dev/null
. /etc/flowin/bootstrap.env

OUT=/etc/flowin/app.env
TMP=$(mktemp /etc/flowin/app.env.XXXXXX)
chmod 0640 "$TMP"; chown root:flowin "$TMP"

REGION="${FLOWIN_REGION:-eu-central-1}"
PREFIX="${FLOWIN_PARAM_PREFIX:-/flowin/prod}"
DOMAIN="${FLOWIN_FQDN:-}"

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
        SECRET_KEY|ACCESS_TOKEN_EXPIRE_HOURS|LANGSMITH_TRACING|LANGSMITH_API_KEY|LANGSMITH_PROJECT)
            emit "$rel" "$value" ;;
        DATABASE_PASSWORD)
            emit DATABASE_URL "postgresql://flowin:${value}@host.docker.internal:5432/flowin" ;;
        llm/region)               emit AWS_REGION                  "$value" ;;
        llm/model_id)             emit BEDROCK_MODEL_ID            "$value" ;;
        llm/inference_profile_id) emit BEDROCK_INFERENCE_PROFILE_ID "$value" ;;
        *)
            echo "[flowin-load-secrets] WARN: ignoring unknown parameter ${name}" >&2 ;;
    esac
done < <(aws ssm get-parameters-by-path \
            --path "$PREFIX" --recursive --with-decryption \
            --region "$REGION" \
            --query 'Parameters[].[Name,Value]' --output text)

# Fallback: if SSM didn't supply a non-empty CORS_ORIGINS, default to a
# single-origin list containing the FQDN we're serving from. Matches the
# common case (single domain) and lets the operator opt-out by setting
# /flowin/$env/CORS_ORIGINS to a non-empty JSON list.
if [[ "$CORS_SET" -eq 0 && -n "$DOMAIN" ]]; then
    emit CORS_ORIGINS "[\"https://${DOMAIN}\"]"
fi

mv "$TMP" "$OUT"
chmod 0640 "$OUT"; chown root:flowin "$OUT"
EOF
chmod +x /usr/local/bin/flowin-load-secrets

# ── 13. nginx (Appendix A) ─────────────────────────────────────────────
mkdir -p /var/www/letsencrypt /etc/nginx/snippets

cat > /etc/nginx/conf.d/flowin-limits.conf <<'EOF'
limit_req_zone $binary_remote_addr zone=flowin_login:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=flowin_register:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=flowin_change_pw:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=flowin_api:10m rate=120r/m;

log_format flowin '$remote_addr - $remote_user [$time_local] '
                  '"$request_method $uri $server_protocol" '
                  '$status $body_bytes_sent "$http_referer" '
                  '"$http_user_agent" rt=$request_time';
EOF

cat > /etc/nginx/snippets/flowin-proxy-headers.conf <<'EOF'
proxy_http_version 1.1;
proxy_set_header   Host              $host;
proxy_set_header   X-Real-IP         $remote_addr;
proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header   X-Forwarded-Proto $scheme;
proxy_set_header   Connection        "";
proxy_redirect     off;
EOF

# The full nginx site is written with $DOMAIN interpolated. Keeping the
# heredoc unquoted because we WANT shell expansion of $DOMAIN; nginx vars
# (like $host, $request_uri) are escaped with \ to survive bash.
cat > /etc/nginx/sites-available/flowin <<EOF
upstream flowin_backend {
    server 127.0.0.1:8000;
    keepalive 64;
}
upstream flowin_frontend {
    server 127.0.0.1:3000;
    keepalive 32;
}

map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        try_files \$uri =404;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    # nginx 1.24 (apt-shipped on Ubuntu Noble) does not recognize the
    # standalone http2 directive — that syntax was added in 1.25.1. The
    # listen-parameter form works on both 1.24 (required) and 1.25+
    # (deprecated but accepted), so this stays portable across Noble's
    # lifetime. Revisit when apt-shipped nginx moves past 1.25.
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN};

    server_tokens off;
    client_max_body_size 1m;
    client_body_timeout 30s;
    client_header_timeout 30s;

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/${DOMAIN}/chain.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 169.254.169.253 valid=60s;
    resolver_timeout 5s;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; connect-src 'self' https://${DOMAIN} wss://${DOMAIN}; frame-src 'self' blob:" always;

    access_log /var/log/nginx/access.log flowin;
    error_log  /var/log/nginx/error.log warn;

    location /api/auth/login {
        limit_req zone=flowin_login burst=5 nodelay;
        limit_req_status 429;
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
    }
    location /api/auth/register {
        limit_req zone=flowin_register burst=3 nodelay;
        limit_req_status 429;
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
    }
    location /api/auth/change-password {
        limit_req zone=flowin_change_pw burst=5 nodelay;
        limit_req_status 429;
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
    }
    location /api/ {
        limit_req zone=flowin_api burst=20 nodelay;
        limit_req_status 429;
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
        proxy_buffering    off;
        proxy_request_buffering off;
        proxy_read_timeout 300s;
    }
    location = /health {
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
        access_log         off;
    }
    location = /openapi.json {
        proxy_pass         http://flowin_backend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
    }
    location = /docs  { return 404; }
    location = /redoc { return 404; }

    location /ws/chat {
        proxy_pass              http://flowin_backend;
        proxy_http_version      1.1;
        proxy_set_header        Upgrade \$http_upgrade;
        proxy_set_header        Connection \$connection_upgrade;
        proxy_set_header        Host \$host;
        proxy_set_header        X-Real-IP \$remote_addr;
        proxy_set_header        X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header        X-Forwarded-Proto \$scheme;
        proxy_read_timeout      5400s;
        proxy_send_timeout      5400s;
        proxy_buffering         off;
        proxy_request_buffering off;
    }

    location / {
        proxy_pass         http://flowin_frontend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
        proxy_buffering    on;
        proxy_read_timeout 60s;
    }

    location /_next/static/ {
        proxy_pass         http://flowin_frontend;
        include            /etc/nginx/snippets/flowin-proxy-headers.conf;
        proxy_cache_valid  200 1y;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
}
EOF
ln -sfn /etc/nginx/sites-available/flowin /etc/nginx/sites-enabled/flowin
rm -f /etc/nginx/sites-enabled/default

# Initial cert (HTTP-01 webroot) — only if no cert exists yet for this domain
if [[ ! -d /etc/letsencrypt/live/$DOMAIN ]]; then
    cat > /etc/nginx/sites-available/bootstrap-http <<EOF2
server {
    listen 80 default_server;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 200 'bootstrap'; add_header Content-Type text/plain; }
}
EOF2
    ln -sfn /etc/nginx/sites-available/bootstrap-http /etc/nginx/sites-enabled/bootstrap-http
    rm -f /etc/nginx/sites-enabled/flowin
    systemctl reload nginx
    certbot certonly --webroot -w /var/www/letsencrypt \
        --non-interactive --agree-tos --email "$ACME_EMAIL" -d "$DOMAIN"
    rm /etc/nginx/sites-enabled/bootstrap-http
    ln -sfn /etc/nginx/sites-available/flowin /etc/nginx/sites-enabled/flowin
fi

nginx -t
systemctl reload nginx
systemctl enable --now certbot.timer

# ── 14. CloudWatch agent ───────────────────────────────────────────────
if ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
    wget -q https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb \
        -O /tmp/cw-agent.deb
    dpkg -i /tmp/cw-agent.deb
    rm /tmp/cw-agent.deb
fi
# Re-grant ACL now that cwagent user exists. See §8 above for why o::r is
# load-bearing (preserves world-read on per-container /etc/hosts so non-
# root containers can do DNS).
setfacl -R -m u:cwagent:rX,o::r /var/lib/docker/containers
setfacl -R -d -m u:cwagent:rX,o::r /var/lib/docker/containers

# CloudWatch agent config — materialized from SIMPLE_AWS_DEPLOYMENT.md §10.1.
# - `${ENV_TITLE}` / `${ENVIRONMENT}` interpolate at install time (bash).
# - `\${aws:InstanceId}` / `\${aws:InstanceType}` are escaped: the CloudWatch
#   agent resolves those itself from instance metadata at runtime.
# - The collect_list mirrors the doc (nginx access/error, postgres, audit,
#   auth, unattended-upgrades, letsencrypt) PLUS the Docker JSON log path
#   that captures backend+frontend stdout via the json-file log driver.
mkdir -p /opt/aws/amazon-cloudwatch-agent/etc
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<EOF
{
  "agent": {
    "metrics_collection_interval": 60,
    "logfile": "/var/log/amazon-cloudwatch-agent.log",
    "run_as_user": "cwagent"
  },
  "metrics": {
    "namespace": "Flowin/${ENV_TITLE}",
    "metrics_collected": {
      "cpu":    {"measurement": ["cpu_usage_idle","cpu_usage_iowait","cpu_usage_user","cpu_usage_system"], "totalcpu": true, "metrics_collection_interval": 60},
      "mem":    {"measurement": ["mem_used_percent","mem_available"], "metrics_collection_interval": 60},
      "disk":   {"measurement": ["used_percent","inodes_free"], "resources": ["/", "/var/lib/postgresql"], "metrics_collection_interval": 60},
      "diskio": {"measurement": ["io_time","write_bytes","read_bytes"], "resources": ["*"], "metrics_collection_interval": 60},
      "swap":   {"measurement": ["swap_used_percent"], "metrics_collection_interval": 60},
      "net":    {"measurement": ["bytes_sent","bytes_recv","drop_in","drop_out"], "resources": ["*"], "metrics_collection_interval": 60}
    },
    "append_dimensions": {
      "InstanceId":   "\${aws:InstanceId}",
      "InstanceType": "\${aws:InstanceType}"
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {"file_path": "/var/log/nginx/access.log",                            "log_group_name": "/flowin/${ENVIRONMENT}/nginx-access", "log_stream_name": "{instance_id}",        "timezone": "UTC"},
          {"file_path": "/var/log/nginx/error.log",                             "log_group_name": "/flowin/${ENVIRONMENT}/nginx-error",  "log_stream_name": "{instance_id}",        "timezone": "UTC"},
          {"file_path": "/var/log/postgresql/postgresql-16-main.log",           "log_group_name": "/flowin/${ENVIRONMENT}/postgres",     "log_stream_name": "{instance_id}",        "timezone": "UTC"},
          {"file_path": "/var/log/audit/audit.log",                             "log_group_name": "/flowin/${ENVIRONMENT}/system",       "log_stream_name": "{instance_id}",        "timezone": "UTC"},
          {"file_path": "/var/log/auth.log",                                    "log_group_name": "/flowin/${ENVIRONMENT}/auth",         "log_stream_name": "{instance_id}",        "timezone": "UTC"},
          {"file_path": "/var/log/unattended-upgrades/unattended-upgrades.log", "log_group_name": "/flowin/${ENVIRONMENT}/system",       "log_stream_name": "{instance_id}",        "timezone": "UTC"},
          {"file_path": "/var/log/letsencrypt/letsencrypt.log",                 "log_group_name": "/flowin/${ENVIRONMENT}/letsencrypt",  "log_stream_name": "{instance_id}",        "timezone": "UTC"},
          {"file_path": "/var/lib/docker/containers/*/*-json.log",              "log_group_name": "/flowin/${ENVIRONMENT}/app",          "log_stream_name": "{instance_id}/docker", "timezone": "UTC"}
        ]
      }
    }
  }
}
EOF

# fetch-config also starts the agent if it isn't running. We don't `systemctl
# enable` separately — the agent's deb postinst already does that.
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config -m ec2 -s \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

# ── 15. flowin-deploy user + restricted sudoers + image-tag wrapper ────
if ! id flowin-deploy >/dev/null 2>&1; then
    useradd --system --create-home --shell /bin/bash flowin-deploy
    install -d -o flowin-deploy -g flowin-deploy -m 0700 /home/flowin-deploy/.ssh
    install -o flowin-deploy -g flowin-deploy -m 0600 /dev/null \
        /home/flowin-deploy/.ssh/authorized_keys
fi

cat > /usr/local/bin/flowin-update-image-tag <<'WRAPPER'
#!/bin/bash
# /usr/local/bin/flowin-update-image-tag — called by `sudo` from CI.
# Usage: flowin-update-image-tag (backend|frontend) <image_uri>
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
sed -i.bak "s|^${upper}_IMAGE=.*|${upper}_IMAGE=${image}|" /etc/flowin/app.env
rm -f /etc/flowin/app.env.bak
WRAPPER
chmod 0755 /usr/local/bin/flowin-update-image-tag
chown root:root /usr/local/bin/flowin-update-image-tag

# Restricted sudoers via visudo -cf to refuse a malformed install.
SUDOERS_TMP=$(mktemp)
cat > "$SUDOERS_TMP" <<'SUDO'
# /etc/sudoers.d/flowin-deploy — generated by Flowin bootstrap.
flowin-deploy ALL=(root) NOPASSWD: /usr/local/bin/flowin-update-image-tag backend *
flowin-deploy ALL=(root) NOPASSWD: /usr/local/bin/flowin-update-image-tag frontend *
flowin-deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart flowin-app.service
SUDO
chmod 0440 "$SUDOERS_TMP"
if visudo -cf "$SUDOERS_TMP"; then
    install -o root -g root -m 0440 "$SUDOERS_TMP" /etc/sudoers.d/flowin-deploy
else
    echo "[bootstrap] ERROR: flowin-deploy sudoers stanza failed visudo check" >&2
    rm -f "$SUDOERS_TMP"
    exit 1
fi
rm -f "$SUDOERS_TMP"

# ── 16. Backups: pg_dump + skills tarball + stuck-workflow probe ───────
cat > /usr/local/bin/flowin-pg-dump <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
: "${FLOWIN_BACKUP_BUCKET:?FLOWIN_BACKUP_BUCKET is required}"
: "${FLOWIN_KMS_KEY_ID:?FLOWIN_KMS_KEY_ID is required}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
DUMP="$TMP/flowin-${TS}.sql.gz"
pg_dump --format=plain --no-owner --no-acl flowin | gzip -9 > "$DUMP"
aws s3 cp "$DUMP" "s3://${FLOWIN_BACKUP_BUCKET}/postgres/${TS}/flowin.sql.gz" \
    --region "${FLOWIN_REGION:-eu-central-1}" \
    --sse aws:kms \
    --sse-kms-key-id "$FLOWIN_KMS_KEY_ID"
echo "pg_dump complete: $(stat -c%s "$DUMP") bytes uploaded to S3"
EOF
chmod 0755 /usr/local/bin/flowin-pg-dump

cat > /usr/local/bin/flowin-skills-backup <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
: "${FLOWIN_BACKUP_BUCKET:?FLOWIN_BACKUP_BUCKET is required}"
: "${FLOWIN_KMS_KEY_ID:?FLOWIN_KMS_KEY_ID is required}"
TS=$(date -u +%Y%m%d)
tar -czf - -C /opt/flowin/data skills \
    | aws s3 cp - "s3://${FLOWIN_BACKUP_BUCKET}/skills/${TS}.tar.gz" \
        --region "${FLOWIN_REGION:-eu-central-1}" \
        --sse aws:kms \
        --sse-kms-key-id "$FLOWIN_KMS_KEY_ID"
EOF
chmod 0755 /usr/local/bin/flowin-skills-backup

cat > /usr/local/bin/flowin-stuck-workflows-check <<'EOF'
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
aws cloudwatch put-metric-data \
    --namespace Flowin/Prod \
    --metric-name StuckRunningWorkflows \
    --value "$COUNT" \
    --region "$AWS_REGION"
EOF
chmod 0755 /usr/local/bin/flowin-stuck-workflows-check

# ── 17. systemd units (Appendix B) ─────────────────────────────────────
cat > /etc/systemd/system/flowin-app.service <<'EOF'
[Unit]
Description=Flowin app stack (backend + frontend) via Docker Compose
After=docker.service network-online.target postgresql.service
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/flowin
EnvironmentFile=/etc/flowin/app.env
ExecStartPre=/usr/local/bin/flowin-load-secrets
ExecStartPre=/usr/bin/docker compose pull
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose down
ExecReload=/usr/bin/docker compose restart
TimeoutStartSec=600
Restart=on-failure
RestartSec=30s

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/flowin-pg-dump.service <<'EOF'
[Unit]
Description=Flowin Postgres logical dump to S3
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=postgres
Group=postgres
EnvironmentFile=/etc/flowin/bootstrap.env
EnvironmentFile=/etc/flowin/app.env
ExecStart=/usr/local/bin/flowin-pg-dump
TimeoutStartSec=600
EOF

cat > /etc/systemd/system/flowin-pg-dump.timer <<'EOF'
[Unit]
Description=Hourly Flowin PG dump

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=120
Unit=flowin-pg-dump.service

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/flowin-skills-backup.service <<'EOF'
[Unit]
Description=Flowin skills backup to S3
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=flowin
Group=flowin
EnvironmentFile=/etc/flowin/bootstrap.env
ExecStart=/usr/local/bin/flowin-skills-backup
EOF

cat > /etc/systemd/system/flowin-skills-backup.timer <<'EOF'
[Unit]
Description=Daily Flowin skills backup

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=600
Unit=flowin-skills-backup.service

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/flowin-stuck-workflows-check.service <<'EOF'
[Unit]
Description=Flowin stuck-running WorkflowRun probe
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=flowin
Group=flowin
EnvironmentFile=/etc/flowin/bootstrap.env
EnvironmentFile=/etc/flowin/app.env
ExecStart=/usr/local/bin/flowin-stuck-workflows-check
TimeoutStartSec=60
EOF

cat > /etc/systemd/system/flowin-stuck-workflows-check.timer <<'EOF'
[Unit]
Description=Run stuck-workflows probe every 15 minutes

[Timer]
OnCalendar=*:0/15
Persistent=true
RandomizedDelaySec=60
Unit=flowin-stuck-workflows-check.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now \
    flowin-pg-dump.timer \
    flowin-skills-backup.timer \
    flowin-stuck-workflows-check.timer

# ── 18. App service — load secrets, start ──────────────────────────────
/usr/local/bin/flowin-load-secrets
# Tear down any existing containers before (re-)starting the service. This
# forces fresh containers on every bootstrap re-run, which is necessary so
# that any change to host state that influences container provisioning
# (default ACLs on /var/lib/docker/containers — see §8 above, image-tag
# pins in /etc/flowin/app.env, etc.) takes effect even when neither the
# image digest nor compose-detectable env has changed. Idempotent: on a
# fresh box there are no containers to remove.
( cd /opt/flowin && docker compose down --remove-orphans 2>/dev/null || true )
systemctl enable --now flowin-app.service

# ── 19. Smoke test ─────────────────────────────────────────────────────
sleep 15
if ! curl -fsS http://127.0.0.1:8000/health; then
    echo "[bootstrap] WARN: /health probe failed — flowin-app.service may still be starting"
    echo "[bootstrap]       check: sudo systemctl status flowin-app.service"
    echo "[bootstrap]       check: sudo docker compose -f /opt/flowin/docker-compose.yml logs --tail=200"
fi
echo "[bootstrap] complete $(date -u --iso-8601=seconds)"
