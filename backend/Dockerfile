# syntax=docker/dockerfile:1.7
#
# Production Dockerfile for the Flowin backend.
#
# Two stages:
#   1. builder  — installs build toolchains and compiles wheels into /opt/venv.
#   2. runtime  — slim image, copies /opt/venv, runs as non-root user `flowin`.
#
# Notes on build hygiene:
#   * Only `requirements.txt` is COPYed before `pip install` so unrelated
#     source changes don't bust the (slow) dependency layer.
#   * apt-get update + install live in a single RUN to prevent stale-cache
#     poisoning across rebuilds.
#   * `requirements.txt` mixes runtime + test deps (pytest, hypothesis). We
#     install the lot rather than refactor the file; ~5 MB of dead weight is
#     acceptable to avoid coupling this Dockerfile to a requirements split.

# ============================================================================
# Stage 1 — builder
# ============================================================================
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for native wheels: gcc/build-essential drive the C compiler,
# libpq-dev exposes pg_config (psycopg2-binary normally ships wheels but
# this guarantees a build path on unusual arches), libffi-dev is required
# by `cryptography` when it falls back to source.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        libffi-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create the venv that the runtime stage will inherit. Using a venv (rather
# than the system site-packages) keeps the install tree relocatable — the
# COPY into the runtime stage is just a directory copy.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Cache-friendly: install deps before copying app source so source-only
# changes hit the cached layer.
WORKDIR /build
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Trim install-time bloat that doesn't belong in a runtime image:
#   * __pycache__ — pip writes .pyc on install despite PYTHONDONTWRITEBYTECODE
#     applying only to *new* compilations; reclaiming ~70 MB.
#   * In-package tests/ dirs — numpy alone ships ~70 MB of test fixtures we
#     never execute. Other libs (passlib, sqlalchemy) add another few MB.
# This step lives in the builder stage so the cleaned tree is what gets
# COPYed into the runtime stage. Net image saving: ~140 MB.
RUN find /opt/venv -depth -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find /opt/venv/lib -depth -type d -name 'tests' -prune -exec rm -rf {} + \
    && find /opt/venv/lib -depth -type d -name 'test' -prune -exec rm -rf {} + \
    && find /opt/venv/lib -depth -type d \( -name 'pip' -o -name 'pip-*' -o -name 'setuptools' -o -name 'setuptools-*' -o -name 'wheel' -o -name 'wheel-*' -o -name 'pkg_resources' \) -prune -exec rm -rf {} + \
    && rm -f /opt/venv/bin/pip /opt/venv/bin/pip3 /opt/venv/bin/pip3.13


# ============================================================================
# Stage 2 — runtime
# ============================================================================
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}"

# Runtime-only OS deps:
#   * libpq5     — psycopg2's shared lib at runtime (libpq-dev is build-only)
#   * curl       — used by HEALTHCHECK below
#   * ca-certs   — TLS for outbound calls (Bedrock, LangSmith, Anthropic API)
# Everything else from the builder stage (gcc, libpq-dev, build-essential)
# stays out of this layer to keep the image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Bring the pre-built venv across.
COPY --from=builder /opt/venv /opt/venv

# Non-root user. Numeric UID/GID 10001 makes the image safe to run on
# Kubernetes / hardened hosts that enforce `runAsNonRoot` and don't bother
# resolving names from /etc/passwd. The matching `flowin` name is added so
# `whoami` / `ps` output stays readable in interactive debugging.
RUN groupadd --system --gid 10001 flowin \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --shell /sbin/nologin flowin

WORKDIR /app

# Copy only the bits we need at runtime. tests/, pptx/, skills/ etc. are
# excluded by .dockerignore as a defence-in-depth (in case the COPY pattern
# ever changes). We deliberately do NOT copy backend/skills/ — that path
# is a bind-mounted EBS volume in production (per-user agent state).
COPY --chown=flowin:flowin app/ ./app/
COPY --chown=flowin:flowin alembic/ ./alembic/
COPY --chown=flowin:flowin alembic.ini ./alembic.ini

# Entrypoint: runs migrations, then exec's uvicorn. Mode 0755 so the non-root
# user can execute it.
COPY --chown=flowin:flowin --chmod=0755 docker-entrypoint.sh ./docker-entrypoint.sh

# Skills directory: clean target for the runtime bind-mount. Owned by the
# non-root user so the volume mount is writable from inside the container.
RUN mkdir -p /app/skills \
    && chown -R flowin:flowin /app /app/skills

USER 10001:10001

EXPOSE 8000

# /health is defined in app/main.py and returns 200 once the app is ready.
# --start-period gives the lifespan hook (incl. alembic check + DB connect)
# room to settle before failures start counting against --retries.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["curl", "--fail", "--silent", "--show-error", "http://localhost:8000/health"]

ENTRYPOINT ["./docker-entrypoint.sh"]
