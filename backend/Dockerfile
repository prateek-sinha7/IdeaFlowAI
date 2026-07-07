# syntax=docker/dockerfile:1.7
#
# Production Dockerfile for the Flowin backend.
#
# Three stages:
#   1. builder      — installs build toolchains and compiles wheels into /opt/venv.
#   2. pptx-builder — installs Node 20 + pptxgenjs into /opt/pptx/node_modules.
#   3. runtime      — slim image, copies /opt/venv + /opt/pptx + node binary,
#                     runs as non-root user `flowin`.
#
# Notes on build hygiene:
#   * Only `requirements.txt` is COPYed before `pip install` so unrelated
#     source changes don't bust the (slow) dependency layer.
#   * apt-get update + install live in a single RUN to prevent stale-cache
#     poisoning across rebuilds.
#   * `requirements.txt` mixes runtime + test deps (pytest, hypothesis). We
#     install the lot rather than refactor the file; ~5 MB of dead weight is
#     acceptable to avoid coupling this Dockerfile to a requirements split.
#   * The Node toolchain lives in its own builder stage so that pptxgenjs
#     version bumps don't invalidate the Python wheel cache (and vice versa).

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
# Stage 2 — pptx-builder
# ============================================================================
# Dedicated stage for installing pptxgenjs. Kept separate from the Python
# builder so that JS-side version bumps don't bust the (slow) pip-install
# layer and so the Python builder stays lean. Only /opt/pptx/node_modules is
# copied forward into the runtime stage.
#
# We use the official `node:20-bookworm-slim` image rather than installing
# Node 20 on top of `python:3.13-slim-bookworm` via the NodeSource setup
# script. Reasons:
#   * Same base distro (Debian Bookworm), so the Node 20 binaries and
#     shared libraries are ABI-compatible with the runtime stage's apt-
#     installed Node 20 (same Debian, same libc).
#   * Avoids an HTTPS fetch of the NodeSource setup script during the
#     build, which is fragile on networks that intercept TLS.
#   * Mirrors the approach already used by frontend/Dockerfile, so the two
#     services pull Node from the same upstream and we don't add a second
#     pattern for the same problem.
FROM node:20-bookworm-slim AS pptx-builder

# Install pptxgenjs at the exact version pinned by frontend/package-lock.json.
# `--prefix /opt/pptx` lays out node_modules under /opt/pptx/node_modules/
# without requiring a package.json. The same path is mirrored in the runtime
# stage so the Python service can reference it via PPTX_NODE_MODULES_DIR.
RUN npm install --prefix /opt/pptx --no-audit --no-fund --omit=dev pptxgenjs@3.12.0


# ============================================================================
# Stage 3 — runtime
# ============================================================================
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}" \
    OD_ROOT=/app/opendesign

# Runtime-only OS deps:
#   * libpq5     — psycopg2's shared lib at runtime (libpq-dev is build-only)
#   * curl       — used by HEALTHCHECK below
#   * ca-certs   — TLS for outbound calls (Bedrock, LangSmith, Anthropic API)
#   * libstdc++6 — the official Node 20 binary we copy below links against
#                  it; libc.so.6 / libm.so.6 / libgcc_s.so.1 are already
#                  present in python:3.13-slim-bookworm.
# Everything else from the builder stage (gcc, libpq-dev, build-essential)
# stays out of this layer to keep the image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        ca-certificates \
        libstdc++6 \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Bring the pre-built venv across.
COPY --from=builder /opt/venv /opt/venv

# Headless Chromium for prototype render-validation (app/agents/render_check.py).
# `playwright` (the Python package) arrived in the venv above; this fetches the
# browser binary + its OS libraries. Run as root, BEFORE the USER switch, into a
# fixed path the non-root runtime user can launch from (PLAYWRIGHT_BROWSERS_PATH).
# Adds ~350 MB to the image — the cost of in-image headless validation.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN apt-get update \
    && playwright install --with-deps chromium \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R 10001:10001 /opt/playwright

# Node 20 runtime binary, taken from the same official image used by the
# pptx-builder stage so the ABI matches the node_modules copied below.
# We need only the `node` binary itself — `npm` is not invoked at runtime;
# the FastAPI service in pptx_export.py spawns `node <script>` directly.
COPY --from=node:20-bookworm-slim /usr/local/bin/node /usr/local/bin/node

# Bring the pre-installed pptxgenjs node_modules across. Owned by the non-root
# runtime user so `node` can read them when invoked from the FastAPI process.
COPY --from=pptx-builder --chown=10001:10001 /opt/pptx/node_modules /opt/pptx/node_modules

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
# agents/ is a second top-level package the app imports (folder-per-agent
# architecture): app/main.py -> app.api.* -> `from agents.execution_engine...`.
# It also holds runtime DATA the loader reads from disk (prompts/*/AGENT.md,
# guardrails/*.md) — see the .dockerignore *.md re-include that keeps those in
# the build context.
COPY --chown=flowin:flowin agents/ ./agents/
COPY --chown=flowin:flowin alembic/ ./alembic/
COPY --chown=flowin:flowin alembic.ini ./alembic.ini

# OpenDesign reference content (design-templates, design-systems, craft rules,
# prompt-templates) that app/services/od_loader.py reads from disk. Supplied as
# a NAMED build context (buildx: --build-context opendesign=skills/opendesign;
# compose: build.additional_contexts) because the tree lives at the repo root,
# OUTSIDE this image's ./backend build context. Baked to /app/opendesign — a
# path the /app/skills EBS bind-mount can NOT shadow — and selected at runtime
# via ENV OD_ROOT above. Without this the loader finds nothing in deployed
# environments (the volume is empty) and every OpenDesign gallery is empty.
COPY --chown=flowin:flowin --from=opendesign . ./opendesign/

# Pre-render OpenDesign gallery thumbnails at BUILD time. Headless Chromium was
# installed above (for render_check) and the OpenDesign tree is now baked at
# /app/opendesign, so we screenshot each template's example.html to a static
# thumbnail.jpg. The catalog UI serves these as a plain <img>; any template
# without one falls back to live iframe (HTML+JS) rendering in the browser — so
# this step is best-effort (the script ALWAYS exits 0) and never blocks the
# build. Runs as root here (before the USER switch) so Chromium gets
# --no-sandbox and the output is re-chowned to the non-root runtime user.
COPY --chown=flowin:flowin scripts/generate_template_thumbnails.py ./scripts/generate_template_thumbnails.py
RUN python scripts/generate_template_thumbnails.py --dir /app/opendesign/design-templates \
    && chown -R 10001:10001 /app/opendesign

# Entrypoint: runs migrations, then exec's uvicorn. Mode 0755 so the non-root
# user can execute it.
COPY --chown=flowin:flowin --chmod=0755 docker-entrypoint.sh ./docker-entrypoint.sh

# Bind-mount targets for the EBS data volume: per-user skills + per-run agent
# sandboxes (the deepagents disk filesystem, RUNS_ROOT=/app/runs). Created empty
# and owned by the non-root user so both mounts are writable inside the container.
RUN mkdir -p /app/skills /app/runs \
    && chown -R flowin:flowin /app /app/skills /app/runs

USER 10001:10001

EXPOSE 8000

# /health is defined in app/main.py and returns 200 once the app is ready.
# --start-period gives the lifespan hook (incl. alembic check + DB connect)
# room to settle before failures start counting against --retries.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["curl", "--fail", "--silent", "--show-error", "http://localhost:8000/health"]

ENTRYPOINT ["./docker-entrypoint.sh"]
