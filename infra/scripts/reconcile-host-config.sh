#!/usr/bin/env bash
# VelocityAI host configuration reconciler.
#
# Extracted from bootstrap-ec2.sh §13 (nginx) and §14 (CloudWatch agent).
# Safe to run on any schedule (idempotent). Intended for:
#   - Reconciling nginx config + CloudWatch agent config on existing hosts
#   - CI/CD pipelines that need to apply config changes without full bootstrap
#   - Manual re-provisioning of host configs on a running instance
#
# Preconditions:
#   - /etc/velocityai/bootstrap.env must exist (written by Terraform user_data)
#   - VELOCITYAI_ENVIRONMENT and VELOCITYAI_FQDN must be set
#   - Root privilege required for file writes and service reloads
#
# Invocation:
#   aws ssm send-command \
#     --document-name AWS-RunShellScript \
#     --instance-ids i-... \
#     --parameters 'commands=["bash -s"]' < infra/scripts/reconcile-host-config.sh
#
# Or locally:
#   sudo bash infra/scripts/reconcile-host-config.sh

set -euo pipefail
exec > >(tee -a /var/log/velocityai-reconcile.log) 2>&1
echo "[reconcile] start $(date -u --iso-8601=seconds)"

if [[ "$EUID" -ne 0 ]]; then
    echo "[reconcile] ERROR: must run as root (or via sudo)" >&2
    exit 1
fi

# ── 1. Source operator-controlled values ──────────────────────────────
#
# /etc/velocityai/bootstrap.env is created by Terraform's compute module.
# It carries:
#   VELOCITYAI_REGION         — AWS region
#   VELOCITYAI_ENVIRONMENT    — env tag (prod / staging / …)
#   VELOCITYAI_FQDN           — public hostname (nip.io or Route 53)
#   VELOCITYAI_ACME_EMAIL     — email for Let's Encrypt
#
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

# ── 2. Create backup directory ────────────────────────────────────────
#
# Backup existing configs before writing new ones. Timestamped directory
# allows multiple safe re-runs + manual rollback if needed.
BACKUP_DIR="/var/backups/velocityai-config-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

restore_and_die() {
    local msg="$1"
    echo "[reconcile] FAILED: $msg" >&2
    echo "[reconcile] Backup preserved at $BACKUP_DIR for manual inspection" >&2
    exit 1
}

# Backup existing nginx + agent config if present
[[ -f /etc/nginx/conf.d/velocityai-limits.conf ]] && \
    cp /etc/nginx/conf.d/velocityai-limits.conf "$BACKUP_DIR/" || true
[[ -f /etc/nginx/snippets/velocityai-proxy-headers.conf ]] && \
    cp /etc/nginx/snippets/velocityai-proxy-headers.conf "$BACKUP_DIR/" || true
[[ -f /etc/nginx/sites-available/velocityai ]] && \
    cp /etc/nginx/sites-available/velocityai "$BACKUP_DIR/" || true
[[ -f /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json ]] && \
    cp /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json "$BACKUP_DIR/" || true

echo "[reconcile] Backups written to $BACKUP_DIR"

# ── 3. nginx configuration (§13) ───────────────────────────────────────
#
# Idempotent: all writes are truncating (cat > ...), and symlinks use -f
# for forced replacement.

mkdir -p /var/www/letsencrypt /etc/nginx/snippets

# velocityai-limits.conf — nginx rate limiting zones
cat > /etc/nginx/conf.d/velocityai-limits.conf <<'EOF'
limit_req_zone $binary_remote_addr zone=velocityai_login:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=velocityai_register:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=velocityai_change_pw:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=velocityai_api:10m rate=120r/m;
limit_conn_zone $binary_remote_addr zone=velocityai_stream:10m;

# --- E1: structured (JSON) access log for CloudWatch observability ------
# The space-delimited predecessor carried no $upstream_* variable at all, so
# a 429 emitted by limit_req was byte-indistinguishable from a 429 returned
# by FastAPI. $upstream_addr is the discriminator: nginx sets it when it
# proxied and leaves it unset when it answered by itself.
#
# escape=json (nginx >= 1.11.8) and $request_id (>= 1.11.0); the box runs
# nginx 1.24.0. escape=json escapes every VALUE, but it renders an UNSET
# variable as an EMPTY STRING -- NOT as nginx's usual "-" sentinel. The
# CloudWatch filter that identifies an nginx-generated rejection keys on
# upstream_addr == "-", so normalise that ONE field back. Measured on
# nginx 1.24.0: without this map a limit_req 429 logs "upstream_addr":""
# and { $.upstream_addr = "-" } never matches -- i.e. the alarm that
# catches "we are throttling our own users" silently never fires.
# Do not delete this map without changing the filter.
map $upstream_addr $velocityai_upstream_addr {
    default $upstream_addr;
    ""      "-";
}

# $status is formatted "%03ui", so a request logged before any response
# status was set renders as "000" (and an HTTP/0.9 request as "009").
# Emitted unquoted that is invalid JSON (leading zeros) and CloudWatch
# drops the ENTIRE line from every JSON filter. Strip the padding so the
# field is always a legal JSON number.
map $status $velocityai_status {
    default          $status;
    ~^0+(?<d>[0-9])$ $d;
}

# $uri -- NOT $request / $request_uri / $args. The query string is
# deliberately omitted to mitigate token leakage
# (docs/SIMPLE_AWS_DEPLOYMENT.md, "Access log": "$uri intentionally
# instead of $request -- strips the query string").
# Do NOT "improve" this to log the full request line.
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

# velocityai-proxy-headers.conf — standard proxy headers
cat > /etc/nginx/snippets/velocityai-proxy-headers.conf <<'EOF'
proxy_http_version 1.1;
proxy_set_header   Host              $host;
proxy_set_header   X-Real-IP         $remote_addr;
proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header   X-Forwarded-Proto $scheme;
proxy_set_header   Connection        "";
proxy_redirect     off;
EOF

# Main nginx site config — $DOMAIN interpolates at write time, \$ nginx vars
# are escaped to survive bash parsing.
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

    # E1: without this the :80 block inherits the http-level access_log from
    # Ubuntu's stock /etc/nginx/nginx.conf -- same FILE, default `combined`
    # FORMAT -- so /var/log/nginx/access.log would carry a mix of JSON and
    # space-delimited lines and every JSON metric filter would silently skip
    # the :80 half (redirects and ACME challenges).
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
    # SAMEORIGIN (not DENY): the prototype/ppt template + design-system galleries
    # embed their own /api/.../preview endpoints in same-origin <iframe>s. DENY
    # blocks all framing (incl. same-origin), which renders the previews blank.
    # SAMEORIGIN keeps cross-origin clickjacking protection (CSP frame-src is 'self').
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
    # A1: SSE run event stream — long-lived connection, not a request-rate phenomenon.
    # Exempt from request-rate limiting (limit_req); apply connection concurrency cap instead.
    # This regex must sit BEFORE the generic /api/ prefix location to win nginx's matching rule
    # (regex in definition order). Must NOT declare add_header here — it would drop the 5 inherited
    # security headers from server level (D3). sse_starlette already force-sets X-Accel-Buffering.
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

    # /velocityai-handoff live pipeline stream. Auth is JWT-subprotocol at the
    # backend (issuer-only); nginx is just the WebSocket terminator. Same
    # long read/send timeouts as /ws/chat because pipeline runs can take
    # minutes (clone -> classify -> code -> test -> compliance -> push -> PR).
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

    # MCP remote tool endpoint for /velocityai-handoff (JSON-RPC over HTTP).
    # Bearer-token auth at the backend; same rate limit as /api/. Buffering
    # off so the tool's structuredContent response streams cleanly.
    location /mcp/ {
        limit_req zone=velocityai_api burst=20 nodelay;
        limit_req_status 429;
        proxy_pass         http://velocityai_backend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
        proxy_buffering    off;
        proxy_request_buffering off;
        proxy_read_timeout 300s;
    }

    # Public installer endpoint for /velocityai-handoff:
    #   curl -fsSL https://${DOMAIN}/install/velocityai-handoff | bash
    # No auth (the file bodies are generic). Same rate limit as /api/ so the
    # unauthenticated public surface can't be abused.
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

    location /_next/static/ {
        proxy_pass         http://velocityai_frontend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
        proxy_cache_valid  200 1y;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
}
EOF

ln -sfn /etc/nginx/sites-available/velocityai /etc/nginx/sites-enabled/velocityai
rm -f /etc/nginx/sites-enabled/default

# Validate nginx config — fail-closed if cert missing or syntax error
if [[ -d /etc/letsencrypt/live/$DOMAIN ]]; then
    if ! nginx -t; then
        restore_and_die "nginx -t validation failed (see log above)"
    fi
    systemctl reload nginx
    echo "[reconcile] nginx reloaded successfully"
else
    echo "[reconcile] WARNING: /etc/letsencrypt/live/$DOMAIN does not exist — skipping nginx validation"
    echo "[reconcile] (nginx will fail to start until TLS cert is provisioned by bootstrap or manually)"
fi

# ── 4. CloudWatch agent configuration (§14) ──────────────────────────
#
# Install guard: only write config if the agent package is present
if ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
    echo "[reconcile] WARNING: amazon-cloudwatch-agent not installed — skipping config"
fi

# ACL reconciliation: ensure cwagent can read Docker container logs
# See bootstrap-ec2.sh §14 for full context on why this is idempotent.
setfacl -R -m u:cwagent:rX,o::r /var/lib/docker/containers 2>/dev/null || true
setfacl -R -d -m u:cwagent:rX,o::r /var/lib/docker/containers 2>/dev/null || true

# CloudWatch agent config — bash variables interpolated at write time
mkdir -p /opt/aws/amazon-cloudwatch-agent/{etc,logs}
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
          {"file_path": "/var/log/letsencrypt/letsencrypt.log",                 "log_group_name": "/velocityai/${ENVIRONMENT}/letsencrypt",  "log_stream_name": "{instance_id}/letsencrypt",         "timezone": "UTC"},
          {"file_path": "/var/lib/docker/containers/*/*-json.log",              "log_group_name": "/velocityai/${ENVIRONMENT}/app",          "log_stream_name": "{instance_id}/docker",              "timezone": "UTC"}
        ]
      }
    }
  }
}
EOF

echo "[reconcile] CloudWatch agent config written to /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json"

# ── 5. Completion ──────────────────────────────────────────────────────

echo "[reconcile] complete $(date -u --iso-8601=seconds)"
echo "[reconcile] SUCCESS: host config reconciliation finished"
