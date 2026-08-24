#!/usr/bin/env bash
# VelocityAI host configuration reconciler.
#
# Idempotently configures nginx and the CloudWatch agent on a bootstrapped host.
# Requires root and /etc/velocityai/bootstrap.env with VELOCITYAI_ENVIRONMENT
# and VELOCITYAI_FQDN. Exit 1 means nginx/config failure; exit 2 means only
# CloudWatch-agent degradation, allowing the caller to apply its env policy.

set -euo pipefail
exec > >(tee -a /var/log/velocityai-reconcile.log) 2>&1
echo "[reconcile] start $(date -u --iso-8601=seconds)"

if [[ "$EUID" -ne 0 ]]; then
    echo "[reconcile] ERROR: must run as root (or via sudo)" >&2
    exit 1
fi

# Nginx failures are fail-closed. Agent failures are recorded and returned as
# exit 2 because observability is not the request path.
RECONCILE_DEGRADED=()

# ── 1. Load host identity ──────────────────────────────────────────────
if [[ ! -f /etc/velocityai/bootstrap.env ]]; then
    echo "[reconcile] ERROR: /etc/velocityai/bootstrap.env missing" >&2
    exit 1
fi

# shellcheck source=/dev/null
. /etc/velocityai/bootstrap.env

REGION="${VELOCITYAI_REGION:-eu-central-1}"
DOMAIN="${VELOCITYAI_FQDN:?VELOCITYAI_FQDN missing in /etc/velocityai/bootstrap.env}"
ENVIRONMENT="${VELOCITYAI_ENVIRONMENT:?VELOCITYAI_ENVIRONMENT missing in /etc/velocityai/bootstrap.env}"
ENV_TITLE="${ENVIRONMENT^}"
ACME_EMAIL="${VELOCITYAI_ACME_EMAIL:-security@example.com}"

echo "[reconcile] ENVIRONMENT=$ENVIRONMENT DOMAIN=$DOMAIN"

# ── 2. Backup and rollback helpers ────────────────────────────────────
BACKUP_DIR="/var/backups/velocityai-config-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# One list is used for backup and rollback so every modified file is restorable.
BACKED_UP_FILES=(
    /etc/nginx/conf.d/velocityai-limits.conf
    /etc/nginx/snippets/velocityai-proxy-headers.conf
    /etc/nginx/sites-available/velocityai
    /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
)

DEFAULT_SITE_WAS_ENABLED=0
[[ -e /etc/nginx/sites-enabled/default ]] && DEFAULT_SITE_WAS_ENABLED=1

for _src in "${BACKED_UP_FILES[@]}"; do
    if [[ -f "$_src" ]]; then
        cp -p "$_src" "$BACKUP_DIR/$(basename "$_src")" \
            || { echo "[reconcile] ERROR: could not back up $_src" >&2; exit 1; }
    fi
done

echo "[reconcile] Backups written to $BACKUP_DIR"

# Restore the pre-run configuration after an nginx validation/apply failure.
# Do not reload a running nginx after restoration: it is already serving the
# previous known-good configuration in memory. Start it only if currently down.
restore_and_die() {
    local msg="$1"
    echo "[reconcile] FAILED: $msg" >&2
    echo "[reconcile] rolling back host config from $BACKUP_DIR" >&2

    local src dst
    for dst in "${BACKED_UP_FILES[@]}"; do
        src="$BACKUP_DIR/$(basename "$dst")"
        if [[ -f "$src" ]]; then
            cp -p "$src" "$dst" && echo "[reconcile]   restored $dst" >&2
        else
            rm -f "$dst" && echo "[reconcile]   removed $dst (absent before this run)" >&2
        fi
    done

    if [[ "$DEFAULT_SITE_WAS_ENABLED" -eq 1 && ! -e /etc/nginx/sites-enabled/default ]]; then
        ln -sfn /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default \
            && echo "[reconcile]   re-enabled sites-enabled/default" >&2
    fi

    if ! systemctl is-active --quiet nginx; then
        if nginx -t 2>/dev/null; then
            systemctl start nginx && echo "[reconcile]   nginx started on restored config" >&2
        else
            echo "[reconcile]   WARNING: nginx is down and the restored config does not validate" >&2
        fi
    fi

    echo "[reconcile] rollback complete; backup retained at $BACKUP_DIR" >&2
    exit 1
}

# Agent failures restore its prior config when available and continue so the
# caller can distinguish degraded monitoring (2) from broken ingress (1).
degrade_agent() {
    local msg="$1"
    local tag="$2"
    echo "[reconcile] AGENT DEGRADED: $msg" >&2
    local live=/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
    local bak="$BACKUP_DIR/amazon-cloudwatch-agent.json"
    if [[ -f "$bak" ]]; then
        cp -p "$bak" "$live" && echo "[reconcile]   restored $live" >&2
    fi
    RECONCILE_DEGRADED+=("$tag: $msg")
}

# Retain 10 backups; this runs on every deploy and must not fill the root disk.
# shellcheck disable=SC2012
ls -1dt /var/backups/velocityai-config-* 2>/dev/null | tail -n +11 \
    | xargs -r rm -rf

# ── 3. nginx ───────────────────────────────────────────────────────────
mkdir -p /var/www/letsencrypt /etc/nginx/snippets

cat > /etc/nginx/conf.d/velocityai-limits.conf <<'EOF'
limit_req_zone $binary_remote_addr zone=velocityai_login:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=velocityai_register:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=velocityai_change_pw:10m rate=10r/m;
# COGNITO-MIGRATION-PLAN §3.6 / §7 Phase 1: /api/auth/refresh is a NEW endpoint
# (Phase 3) with no dedicated rate limit before this — silent token-refresh
# calls are more frequent than an interactive login, so this zone is more
# permissive than velocityai_login but still bounded.
limit_req_zone $binary_remote_addr zone=velocityai_refresh:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=velocityai_api:10m rate=120r/m;
limit_conn_zone $binary_remote_addr zone=velocityai_stream:10m;

# JSON access logs support CloudWatch metric filters. Normalise an absent
# upstream to "-" so nginx-generated responses remain distinguishable from
# backend responses, and remove $status zero-padding to keep JSON valid.
map $upstream_addr $velocityai_upstream_addr {
    default $upstream_addr;
    ""      "-";
}
map $status $velocityai_status {
    default          $status;
    ~^0+(?<d>[0-9])$ $d;
}

# $uri excludes query strings to avoid logging tokens or other sensitive data.
log_format velocityai escape=json
  '{"time":"$time_iso8601","remote_addr":"$remote_addr","xff":"$http_x_forwarded_for",'
  '"method":"$request_method","uri":"$uri","proto":"$server_protocol",'
  '"status":$velocityai_status,"upstream_status":"$upstream_status",'
  '"upstream_addr":"$velocityai_upstream_addr",'
  '"bytes_sent":$body_bytes_sent,"request_time":$request_time,'
  '"upstream_connect_time":"$upstream_connect_time",'
  '"upstream_header_time":"$upstream_header_time",'
  '"upstream_response_time":"$upstream_response_time",'
  '"connection":$connection,"connection_requests":$connection_requests,'
  '"ssl_protocol":"$ssl_protocol","request_id":"$request_id",'
  '"referer":"$http_referer","user_agent":"$http_user_agent"}';
EOF

# Forward nginx's request ID so access and application logs correlate.
cat > /etc/nginx/snippets/velocityai-proxy-headers.conf <<'EOF'
proxy_http_version 1.1;
proxy_set_header   Host              $host;
proxy_set_header   X-Real-IP         $remote_addr;
proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header   X-Forwarded-Proto $scheme;
proxy_set_header   Connection        "";
proxy_set_header   X-Request-ID      $request_id;
proxy_redirect     off;
EOF

# $DOMAIN is interpolated by bash; nginx variables are escaped.
cat > /etc/nginx/sites-available/velocityai <<EOF
upstream velocityai_backend {
    server 127.0.0.1:8000;
    keepalive 64;
}
upstream velocityai_frontend {
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

    access_log /var/log/nginx/access.log velocityai;

    location /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        try_files \$uri =404;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    # Compatible with Ubuntu Noble nginx 1.24 and later.
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
    # SAMEORIGIN permits the application's same-origin preview iframes.
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; connect-src 'self' https://${DOMAIN} wss://${DOMAIN}; frame-src 'self' blob:" always;

    access_log /var/log/nginx/access.log velocityai;
    error_log  /var/log/nginx/error.log warn;

    location /api/auth/login {
        limit_req zone=velocityai_login burst=5 nodelay;
        limit_req_status 429;
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
    }
    location /api/auth/register {
        limit_req zone=velocityai_register burst=3 nodelay;
        limit_req_status 429;
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
    }
    location /api/auth/change-password {
        limit_req zone=velocityai_change_pw burst=5 nodelay;
        limit_req_status 429;
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
    }
    location /api/auth/refresh {
        limit_req zone=velocityai_refresh burst=10 nodelay;
        limit_req_status 429;
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
    }
    # SSE uses a connection cap, not request-rate limiting. It must precede
    # the generic /api/ prefix location.
    location ~ ^/api/runs/[^/]+/events/stream/?$ {
        limit_conn         velocityai_stream 64;
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
        proxy_buffering    off;
        proxy_request_buffering off;
        proxy_read_timeout 5400s;
        proxy_send_timeout 5400s;
        proxy_cache        off;
    }
    location /api/ {
        limit_req zone=velocityai_api burst=20 nodelay;
        limit_req_status 429;
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
        proxy_buffering    off;
        proxy_request_buffering off;
        proxy_read_timeout 300s;
    }
    location = /health {
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
        access_log         off;
    }
    location = /openapi.json {
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
    }
    location = /docs  { return 404; }
    location = /redoc { return 404; }

    location /ws/chat {
        proxy_pass              http://velocityai_backend;
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

    location /ws/handoff/ {
        proxy_pass              http://velocityai_backend;
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

    location /mcp/ {
        limit_req zone=velocityai_api burst=20 nodelay;
        limit_req_status 429;
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
        proxy_buffering    off;
        proxy_request_buffering off;
        proxy_read_timeout 300s;
    }

    location /install/ {
        limit_req zone=velocityai_api burst=20 nodelay;
        limit_req_status 429;
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
    }

    location / {
        proxy_pass         http://velocityai_frontend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
        proxy_buffering    on;
        proxy_read_timeout 60s;
    }

    # Content-addressed assets may be cached indefinitely.
    location /_next/static/ {
        proxy_pass         http://velocityai_frontend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
        add_header Cache-Control "public, max-age=31536000, immutable" always;
    }
}
EOF

ln -sfn /etc/nginx/sites-available/velocityai /etc/nginx/sites-enabled/velocityai
rm -f /etc/nginx/sites-enabled/default

# Fail closed when TLS is expected but unavailable; otherwise a post-bootstrap
# deployment could leave an unvalidated site configuration on disk.
NGINX_APPLIED=0
if [[ -d /etc/letsencrypt/live/$DOMAIN ]]; then
    if ! nginx -t; then
        restore_and_die "nginx -t validation failed (see log above)"
    fi
    systemctl reload nginx
    NGINX_APPLIED=1
    echo "[reconcile] nginx reloaded successfully"
elif [[ -f /var/lib/velocityai/.bootstrap-done ]]; then
    restore_and_die "TLS cert directory /etc/letsencrypt/live/$DOMAIN is missing on an already-provisioned host — refusing to leave an unvalidated nginx config live"
else
    echo "[reconcile] WARNING: /etc/letsencrypt/live/$DOMAIN does not exist — skipping nginx validation"
    echo "[reconcile] (nginx will fail to start until TLS cert is provisioned by bootstrap or manually)"
fi

# ── 4. CloudWatch agent ────────────────────────────────────────────────
# Every failure in this section is reported through degrade_agent and returns
# status 2 rather than interrupting a deploy solely for observability.
CW_AGENT_OK=1

# Install the AWS-signed latest package when missing. The published Debian/
# Ubuntu distribution provides latest rather than stable versioned .deb URLs;
# authenticity is enforced by the pinned AWS GPG fingerprint and signature.
CW_AGENT_DEB_URL="https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb"
CW_AGENT_DEB_URL_FALLBACK="https://amazoncloudwatch-agent-eu-central-1.s3.eu-central-1.amazonaws.com/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb"
CW_AGENT_SIG_URL="${CW_AGENT_DEB_URL}.sig"
CW_AGENT_GPG_KEY_URL="https://s3.amazonaws.com/amazoncloudwatch-agent/assets/amazon-cloudwatch-agent.gpg"
CW_AGENT_GPG_FINGERPRINT="937616F3450B7D806CBD9725D58167303B789C72"

if ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
    echo "[reconcile] amazon-cloudwatch-agent not installed — installing latest signed release"
    _cw_tmpdir=$(mktemp -d)
    _cw_deb="$_cw_tmpdir/amazon-cloudwatch-agent.deb"
    _cw_sig="$_cw_tmpdir/amazon-cloudwatch-agent.deb.sig"
    _cw_key="$_cw_tmpdir/amazon-cloudwatch-agent.gpg"

    if curl -fsSL --retry 3 --retry-delay 5 "$CW_AGENT_DEB_URL" -o "$_cw_deb"; then
        echo "[reconcile] Downloaded .deb from primary URL"
    elif curl -fsSL --retry 3 --retry-delay 5 "$CW_AGENT_DEB_URL_FALLBACK" -o "$_cw_deb"; then
        echo "[reconcile] Downloaded .deb from fallback (eu-central-1) URL"
    else
        degrade_agent "could not download amazon-cloudwatch-agent.deb from primary or fallback URLs" "cwagent-download"
        CW_AGENT_OK=0
    fi

    if [[ "$CW_AGENT_OK" -eq 1 ]]; then
        if ! curl -fsSL --retry 3 --retry-delay 5 "$CW_AGENT_SIG_URL" -o "$_cw_sig" \
            || ! curl -fsSL --retry 3 --retry-delay 5 "$CW_AGENT_GPG_KEY_URL" -o "$_cw_key"; then
            degrade_agent "could not download amazon-cloudwatch-agent.deb signature or GPG key" "cwagent-sig-key"
            CW_AGENT_OK=0
        fi
    fi

    if [[ "$CW_AGENT_OK" -eq 1 ]]; then
        # gpg reports import progress on STDERR. The previous form merged that
        # stream into stdout (`--import "$_cw_key" 2>&1`) INSIDE the command
        # substitution, so $_cw_fpr came out as gpg's chatter followed by the
        # fingerprint:
        #     gpg: key D58167303B789C72: public key "Amazon CloudWatch Agent" imported
        #     ...
        #     937616F3450B7D806CBD9725D58167303B789C72
        # That never compares equal to the bare pinned fingerprint, so a
        # CORRECT, properly signed AWS key was rejected on every run and the
        # agent was never installed — every host log group fed by the agent
        # (system, nginx-*, postgres, letsencrypt, deploy, auth) stayed empty
        # while the deploy reported success, because a degraded agent is only a
        # warning on dev (see remote-deploy.sh §5 FIX-CWA-02).
        #
        # Discard the import's output entirely and capture ONLY the awk result.
        # Running the import inside `if` also removes a `set -e` hazard: as an
        # `x="$(a && b)"` assignment, a failed import made the whole assignment
        # non-zero and aborted the script with exit 1 (nginx failure semantics)
        # instead of degrading to exit 2 (agent-only). The trailing `|| true`
        # covers the same hazard on the pipeline: `awk ... {exit}` closes the
        # pipe early, which can hand gpg a SIGPIPE and trip pipefail.
        _cw_fpr=""
        if gpg --no-default-keyring --keyring "$_cw_tmpdir/keyring.gpg" \
                --import "$_cw_key" >/dev/null 2>&1; then
            _cw_fpr="$(gpg --no-default-keyring --keyring "$_cw_tmpdir/keyring.gpg" \
                --with-colons --fingerprint 2>/dev/null \
                    | awk -F: '/^fpr:/ {print $10; exit}' || true)"
        fi
        if [[ "$_cw_fpr" != "$CW_AGENT_GPG_FINGERPRINT" ]]; then
            degrade_agent "amazon-cloudwatch-agent GPG key fingerprint mismatch (got '${_cw_fpr:-<none>}', expected '${CW_AGENT_GPG_FINGERPRINT}') — refusing to trust this key" "cwagent-key-fingerprint"
            CW_AGENT_OK=0
        elif ! gpg --no-default-keyring --keyring "$_cw_tmpdir/keyring.gpg" --verify "$_cw_sig" "$_cw_deb" >/dev/null 2>&1; then
            degrade_agent "amazon-cloudwatch-agent.deb failed signature verification — refusing to install an untrusted package" "cwagent-signature"
            CW_AGENT_OK=0
        elif ! dpkg -i "$_cw_deb"; then
            degrade_agent "dpkg -i amazon-cloudwatch-agent (signature-verified) failed" "cwagent-install"
            CW_AGENT_OK=0
        else
            _cw_installed_version="$(dpkg-deb -f "$_cw_deb" Version 2>/dev/null || echo unknown)"
            echo "[reconcile] amazon-cloudwatch-agent v${_cw_installed_version} installed (signature verified)"
        fi
    fi
    rm -rf "$_cw_tmpdir"
fi

if [[ "$CW_AGENT_OK" -eq 1 ]] && ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
    degrade_agent "amazon-cloudwatch-agent is still not installed after the install attempt" "cwagent-missing"
    CW_AGENT_OK=0
fi

if [[ "$CW_AGENT_OK" -eq 1 ]]; then
    # Keep cwagent and app containers able to read required Docker/log paths.
    if ! setfacl -R -m u:cwagent:rX,o::r /var/lib/docker/containers; then
        degrade_agent "setfacl (read ACL) on /var/lib/docker/containers failed — app containers may lose host.docker.internal resolution to Postgres" "cwagent-acl-read"
    fi
    if ! setfacl -R -d -m u:cwagent:rX,o::r /var/lib/docker/containers; then
        degrade_agent "setfacl (default ACL) on /var/lib/docker/containers failed — new container log directories will not inherit the o::r grant" "cwagent-acl-default"
    fi

    # auth/postgres logs are adm-readable; audit and certbot logs need explicit ACLs.
    if ! usermod -aG adm cwagent; then
        degrade_agent "usermod -aG adm cwagent failed — auth.log / postgres logs will not be readable by the agent" "cwagent-adm-group"
    fi
    if [[ -f /var/log/audit/audit.log ]] && ! setfacl -m u:cwagent:r /var/log/audit/audit.log; then
        degrade_agent "setfacl on /var/log/audit/audit.log failed — the agent cannot read audit.log" "cwagent-acl-audit"
    fi
    if [[ -d /var/log/letsencrypt ]] && ! setfacl -R -m u:cwagent:rX /var/log/letsencrypt; then
        degrade_agent "setfacl on /var/log/letsencrypt failed — the agent cannot read letsencrypt.log" "cwagent-acl-letsencrypt"
    fi

    # The agent runs as cwagent; only logs/ needs cwagent ownership.
    mkdir -p /opt/aws/amazon-cloudwatch-agent/etc
    install -d -o cwagent -g cwagent /opt/aws/amazon-cloudwatch-agent/logs
    cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<EOF
{
  "agent": {
    "metrics_collection_interval": 60,
    "logfile": "/opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log",
    "run_as_user": "cwagent"
  },
  "metrics": {
    "namespace": "VelocityAI/${ENV_TITLE}",
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
          {"file_path": "/var/log/nginx/access.log",                            "log_group_name": "/velocityai/${ENVIRONMENT}/nginx-access", "log_stream_name": "{instance_id}/nginx-access",        "timezone": "UTC"},
          {"file_path": "/var/log/nginx/error.log",                             "log_group_name": "/velocityai/${ENVIRONMENT}/nginx-error",  "log_stream_name": "{instance_id}/nginx-error",         "timezone": "UTC"},
          {"file_path": "/var/log/postgresql/postgresql-16-main.log",           "log_group_name": "/velocityai/${ENVIRONMENT}/postgres",     "log_stream_name": "{instance_id}/postgres",            "timezone": "UTC"},
          {"file_path": "/var/log/audit/audit.log",                             "log_group_name": "/velocityai/${ENVIRONMENT}/system",       "log_stream_name": "{instance_id}/audit",               "timezone": "UTC"},
          {"file_path": "/var/log/auth.log",                                    "log_group_name": "/velocityai/${ENVIRONMENT}/auth",         "log_stream_name": "{instance_id}/auth",                "timezone": "UTC"},
          {"file_path": "/var/log/unattended-upgrades/unattended-upgrades.log", "log_group_name": "/velocityai/${ENVIRONMENT}/system",       "log_stream_name": "{instance_id}/unattended-upgrades", "timezone": "UTC"},
          {"file_path": "/var/log/syslog",                                      "log_group_name": "/velocityai/${ENVIRONMENT}/system",       "log_stream_name": "{instance_id}/syslog",              "timezone": "UTC"},
          {"file_path": "/var/log/letsencrypt/letsencrypt.log",                 "log_group_name": "/velocityai/${ENVIRONMENT}/letsencrypt",  "log_stream_name": "{instance_id}/letsencrypt",         "timezone": "UTC"},
          {"file_path": "/var/log/velocityai-bootstrap.log",                    "log_group_name": "/velocityai/${ENVIRONMENT}/deploy",       "log_stream_name": "{instance_id}/bootstrap",           "timezone": "UTC"},
          {"file_path": "/var/log/velocityai-reconcile.log",                   "log_group_name": "/velocityai/${ENVIRONMENT}/deploy",       "log_stream_name": "{instance_id}/reconcile",           "timezone": "UTC"},
          {"file_path": "/opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log", "log_group_name": "/velocityai/${ENVIRONMENT}/deploy", "log_stream_name": "{instance_id}/cwagent-self",      "timezone": "UTC"}
        ]
      }
    }
  }
}
EOF

    echo "[reconcile] CloudWatch agent config written to /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json"

    # fetch-config translates JSON and restarts the agent; writing JSON alone
    # does not change the running agent configuration.
    if ! /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
           -a fetch-config -m ec2 -s \
           -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json; then
        degrade_agent "amazon-cloudwatch-agent-ctl fetch-config failed — the agent is not shipping this config" "cwagent-fetch-config"
    fi

    if ! systemctl is-active --quiet amazon-cloudwatch-agent; then
        degrade_agent "amazon-cloudwatch-agent is not active after fetch-config (check /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log)" "cwagent-not-active"
    fi
    if ! systemctl is-enabled --quiet amazon-cloudwatch-agent; then
        degrade_agent "amazon-cloudwatch-agent is not enabled for boot" "cwagent-not-enabled"
    fi
    echo "[reconcile] CloudWatch agent config applied and agent is active"
fi

# ── 5. Completion ──────────────────────────────────────────────────────
if [[ ${#RECONCILE_DEGRADED[@]} -gt 0 ]]; then
    echo "[reconcile] DEGRADED: ${RECONCILE_DEGRADED[*]}" >&2
    echo "[reconcile] nginx changes (if any) were applied; the CloudWatch agent has unresolved issues — see above." >&2
    echo "[reconcile] complete (DEGRADED) $(date -u --iso-8601=seconds)" >&2
    exit 2
fi

echo "[reconcile] SUCCESS: host config reconciliation finished"
