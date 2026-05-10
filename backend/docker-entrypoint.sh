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

echo "[entrypoint] running alembic upgrade head"
alembic upgrade head
echo "[entrypoint] starting uvicorn"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips '*'
