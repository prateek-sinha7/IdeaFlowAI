#!/bin/sh
# Container entrypoint for the Flowin backend.
#
# We intentionally keep this in /bin/sh (not bash) so it runs on the slim
# python:3.13-slim-bookworm image without pulling bash in.
#
# Order of operations:
#   1. `alembic upgrade head` — bring the schema to the latest revision before
#      uvicorn starts accepting traffic. main.py's lifespan refuses to boot
#      without an `alembic_version` table when ENV != development, so this
#      step is required for a healthy startup.
#   2. `exec uvicorn ...` — replace the shell process with uvicorn so SIGTERM
#      from `docker stop` is delivered directly to uvicorn (clean shutdown
#      within the default 10s grace period).
#
# `--proxy-headers` and `--forwarded-allow-ips '*'` are required because
# nginx fronts this container in production. Without them FastAPI sees the
# proxy's IP as request.client.host instead of the real client.
set -eu

# 0. Data-volume permissions. /app/skills and /app/runs are bind mounts, and a
#    bind mount shows the HOST directory's owner, not the one baked into the
#    image — so the image's chown can't help. The image starts as root just
#    long enough to give both mount roots to the runtime user (10001), then
#    re-execs this script as 10001 via setpriv; nothing below runs as root.
#    Top-level only (no -R): fast on a large runs/ tree. A runtime that already
#    starts the container as non-root (e.g. runAsNonRoot) skips this block.
if [ "$(id -u)" = "0" ]; then
    for d in /app/skills /app/runs; do
        mkdir -p "$d"
        chown 10001:10001 "$d" \
            || echo "[entrypoint] WARNING: could not chown $d to 10001 — fix ownership on the host" >&2
    done
    exec setpriv --reuid=10001 --regid=10001 --init-groups "$0" "$@"
fi

echo "[entrypoint] running alembic upgrade head"
alembic upgrade head
echo "[entrypoint] starting uvicorn"
# KAN-151 D8: Bound uvicorn's graceful-shutdown wait to 5 seconds. Without this,
# H11Protocol.shutdown() does NOT close a connection whose response is still
# streaming (SSE), so a live SSE stream makes lifespan.shutdown() unreachable
# and docker SIGKILLs at stop_grace_period (30s, the backend service in
# docker-compose.yml).
# With --timeout-graceful-shutdown 5, streams are force-cancelled after 5s,
# allowing the lifespan body to run. Deploy downtime: 30s -> ~5-8s graceful exit.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips '*' \
    --timeout-graceful-shutdown 5
