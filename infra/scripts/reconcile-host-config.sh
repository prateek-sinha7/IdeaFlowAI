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

# The files this script truncates, paired: source path -> basename inside
# $BACKUP_DIR. ONE list, used by both the backup loop and restore_and_die, so a
# file can never be backed up without being restorable (or vice versa).
BACKED_UP_FILES=(
    /etc/nginx/conf.d/velocityai-limits.conf
    /etc/nginx/snippets/velocityai-proxy-headers.conf
    /etc/nginx/sites-available/velocityai
    /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
)

# Whether /etc/nginx/sites-enabled/default existed when we started. Section 3
# removes it, and a rollback that leaves it removed is not a rollback.
DEFAULT_SITE_WAS_ENABLED=0
[[ -e /etc/nginx/sites-enabled/default ]] && DEFAULT_SITE_WAS_ENABLED=1

for _src in "${BACKED_UP_FILES[@]}"; do
    if [[ -f "$_src" ]]; then
        # cp failure must NOT be swallowed: restore_and_die would then silently
        # have nothing to restore. The previous `&& cp … || true` form hid this.
        cp -p "$_src" "$BACKUP_DIR/$(basename "$_src")" \
            || { echo "[reconcile] ERROR: could not back up $_src" >&2; exit 1; }
    fi
done

echo "[reconcile] Backups written to $BACKUP_DIR"

# Roll the host back to the config it had when this run started, then abort.
#
# Named restore_and_die because it RESTORES. The prior implementation only
# printed and exited, which left the truncated (invalid) config on disk with
# sites-enabled/default already deleted: nginx kept serving from memory, then
# failed to start on the next reboot or certbot renewal hook — an outage
# detached in time from the deploy that caused it.
#
# Deliberately does NOT reload nginx on the happy path of the rollback: the
# running process still holds the last-known-good config in memory, and a reload
# here would be a second chance to fail. We only reload if nginx is NOT running,
# where there is nothing to lose.
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
            # No backup means the file did not exist before this run, so the
            # correct rollback is removal, not leaving our version behind.
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
            echo "[reconcile]   WARNING: nginx is down and the RESTORED config does not validate" >&2
        fi
    fi

    echo "[reconcile] rollback complete; backup retained at $BACKUP_DIR" >&2
    exit 1
}

# Abort for failures that happen AFTER nginx has been validated and reloaded.
#
# Deliberately does NOT roll nginx back: at that point the new nginx config is
# already validated AND live, so reverting it on disk would silently undo a
# change that succeeded and would leave disk and memory disagreeing. Only the
# agent config is reverted, and the exit is still non-zero so CI fails.
die_after_nginx() {
    local msg="$1"
    echo "[reconcile] FAILED: $msg" >&2
    local live=/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
    local bak="$BACKUP_DIR/amazon-cloudwatch-agent.json"
    if [[ -f "$bak" ]]; then
        cp -p "$bak" "$live" && echo "[reconcile]   restored $live" >&2
    fi
    if [[ "${NGINX_APPLIED:-0}" -eq 1 ]]; then
        echo "[reconcile] nginx changes validated and applied successfully; NOT rolled back." >&2
    else
        echo "[reconcile] NOTE: nginx was NOT validated or reloaded this run (no TLS cert for $DOMAIN)." >&2
        echo "[reconcile] The nginx config on disk is new and UNVALIDATED — issue the cert, then re-run." >&2
    fi
    echo "[reconcile] backup retained at $BACKUP_DIR" >&2
    exit 1
}

# Keep the 10 most recent backups. This script is advertised as safe to run on
# any schedule and CI runs it on every deploy, so an unpruned directory grows
# without bound on the root volume — which the disk_root_high alarm would
# eventually report as a capacity problem rather than as litter.
# shellcheck disable=SC2012  # ls -t on a known-safe generated name pattern
ls -1dt /var/backups/velocityai-config-* 2>/dev/null | tail -n +11 \
    | xargs -r rm -rf

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

    # Hashed, content-addressed assets. Declares NO add_header: nginx's add_header
    # is replace-not-merge across levels, so one add_header would discard every
    # security header inherited from the server block (D3). The immutable
    # Cache-Control is already emitted by the upstream Next.js process (router-server.js).
    # proxy_cache_valid was inert (no proxy_cache zone). If this location ever
    # genuinely needs a header, it MUST include the security headers snippet.
    location /_next/static/ {
        proxy_pass         http://velocityai_frontend;
        include            /etc/nginx/snippets/velocityai-proxy-headers.conf;
    }
}
EOF

ln -sfn /etc/nginx/sites-available/velocityai /etc/nginx/sites-enabled/velocityai
rm -f /etc/nginx/sites-enabled/default

# Validate nginx config — fail-closed if cert missing or syntax error.
#
# NGINX_APPLIED records whether the new config was actually validated AND
# loaded, so die_after_nginx can report the truth instead of assuming it. On the
# cert-missing branch the config on disk references a certificate that does not
# exist yet, so nothing has been applied and a later failure must say so.
NGINX_APPLIED=0
if [[ -d /etc/letsencrypt/live/$DOMAIN ]]; then
    if ! nginx -t; then
        restore_and_die "nginx -t validation failed (see log above)"
    fi
    systemctl reload nginx
    NGINX_APPLIED=1
    echo "[reconcile] nginx reloaded successfully"
else
    echo "[reconcile] WARNING: /etc/letsencrypt/live/$DOMAIN does not exist — skipping nginx validation"
    echo "[reconcile] (nginx will fail to start until TLS cert is provisioned by bootstrap or manually)"
fi

# ── 4. CloudWatch agent: install, configure, apply ───────────────────
#
# This section owns the agent end-to-end. It used to live in bootstrap-ec2.sh
# §14; when it moved here the INSTALL and the `fetch-config` that applies the
# config were both dropped, and the remaining "install guard" only warned and
# then fell through. Net effect: a fresh host had no agent at all and an
# existing host had its config rewritten but never applied — while this script
# still exited 0 and CI reported a successful deploy. All three are restored
# below; do not reduce this back to "write the JSON and hope".
#
# Install if absent. `dpkg -s` is the cheap idempotence check, so a normal
# deploy skips the download entirely.
if ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
    echo "[reconcile] amazon-cloudwatch-agent not installed — installing"
    _cw_deb=$(mktemp --suffix=.deb)
    if ! curl -fsSL --retry 3 --retry-delay 5 \
           https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb \
           -o "$_cw_deb"; then
        rm -f "$_cw_deb"
        die_after_nginx "could not download amazon-cloudwatch-agent.deb"
    fi
    if ! dpkg -i "$_cw_deb"; then
        rm -f "$_cw_deb"
        die_after_nginx "dpkg -i amazon-cloudwatch-agent failed"
    fi
    rm -f "$_cw_deb"
    echo "[reconcile] amazon-cloudwatch-agent installed"
fi

# Fail closed. Past this point every step assumes the package (and the cwagent
# user the setfacl calls below reference) exists.
if ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
    die_after_nginx "amazon-cloudwatch-agent is still not installed after the install attempt"
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

# Apply the config. THIS IS THE STEP THAT MAKES THE CONFIG REAL — writing the
# JSON above on its own changes nothing, because the running agent reads the
# TRANSLATED .../etc/amazon-cloudwatch-agent.toml, not the JSON. `fetch-config`
# performs that translation and (re)starts the agent, so it is also what applies
# a changed nginx log_format's matching collect_list, and what picks up the
# per-source log_stream_name scheme.
#
# `-m ec2` selects the EC2 metadata mode; `-s` starts the agent after loading.
# We do not `systemctl enable` separately — the deb's postinst already does.
if ! /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
       -a fetch-config -m ec2 -s \
       -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json; then
    die_after_nginx "amazon-cloudwatch-agent-ctl fetch-config failed — the agent is not shipping this config"
fi

# Verify rather than assume. fetch-config can exit 0 while the agent then dies
# on a bad path or permission (the B1/FIX-149 crash-loop), which is exactly the
# silent blindness the liveness alarms exist to catch — catch it here instead,
# at deploy time, where an operator is watching.
if ! systemctl is-active --quiet amazon-cloudwatch-agent; then
    die_after_nginx "amazon-cloudwatch-agent is not active after fetch-config (check /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log)"
fi
echo "[reconcile] CloudWatch agent config applied and agent is active"

# ── 5. Completion ──────────────────────────────────────────────────────

echo "[reconcile] complete $(date -u --iso-8601=seconds)"
echo "[reconcile] SUCCESS: host config reconciliation finished"
