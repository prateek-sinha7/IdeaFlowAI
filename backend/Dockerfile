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
#   * Only `pyproject.toml` and `uv.lock` are COPYed before the dependency
#     export/install so unrelated source changes don't bust the (slow)
#     dependency layer. `uv.lock` (Task 3.16) is the single committed
#     resolution authority; there is no separate requirements-prod.txt to
#     drift out of sync with it — `uv export --frozen --no-dev` derives the
#     production-only, hash-bearing install list from the lock at build time.
#   * apt-get update + install live in a single RUN to prevent stale-cache
#     poisoning across rebuilds.
#   * The Node toolchain lives in its own builder stage so that pptxgenjs
#     version bumps don't invalidate the Python wheel cache (and vice versa).

# ============================================================================
# Stage 1 — builder
# ============================================================================
FROM python:3.13-slim-bookworm@sha256:b6bd71b0dd3811ddbcbc523ec2965fd1e1bcfdf7a20ab24679273d3bee726129 AS builder

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

# `uv` is used in this stage ONLY to export the production dependency slice
# from the committed backend/uv.lock — it never runs `uv sync`/`uv pip
# install` itself, so the actual install below still targets a plain
# `python -m venv`, matching the runtime stage's plain-venv PATH. Installed
# via pip (from PyPI, exact version, no floating range) rather than a
# separate curl|sh install script, since this builder stage already has a
# working pip and this is the only place `uv` is needed at build time.
RUN pip install --no-cache-dir uv==0.11.3

# Create the venv that the runtime stage will inherit. Using a venv (rather
# than the system site-packages) keeps the install tree relocatable — the
# COPY into the runtime stage is just a directory copy.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Cache-friendly: export + install deps before copying app source so
# source-only changes hit the cached layer.
#
# `backend/uv.lock` (committed, Task 3.16) is the SOLE dependency-resolution
# authority for this image — there is no second, separately-maintained
# requirements file to drift out of sync with it. `uv export --frozen`
# refuses to re-resolve if uv.lock and pyproject.toml disagree (fails the
# build instead of silently installing something the lock didn't pin), and
# `--no-dev` produces exactly `[project.dependencies]` — no test/static/
# security tooling in the runtime image. The export is hash-bearing
# (`--require-hashes` below verifies every wheel/sdist against the digest
# uv.lock recorded), so this build gets the same integrity guarantee a
# committed requirements-prod.txt with `--hash` lines would, without a
# second file someone could forget to regenerate.
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project -o requirements-prod.lock.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --require-hashes -r requirements-prod.lock.txt


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
FROM node:20-bookworm-slim@sha256:3d0f05455dea2c82e2f76e7e2543964c30f6b7d673fc1a83286736d44fe4c41c AS pptx-builder

# Install pptxgenjs at the exact version pinned by frontend/package-lock.json.
# `--prefix /opt/pptx` lays out node_modules under /opt/pptx/node_modules/
# without requiring a package.json. The same path is mirrored in the runtime
# stage so the Python service can reference it via PPTX_NODE_MODULES_DIR.
RUN npm install --prefix /opt/pptx --no-audit --no-fund --omit=dev pptxgenjs@3.12.0


# ============================================================================
# Stage 3 — runtime
# ============================================================================
FROM python:3.13-slim-bookworm@sha256:b6bd71b0dd3811ddbcbc523ec2965fd1e1bcfdf7a20ab24679273d3bee726129 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}" \
    OD_ROOT=/app/opendesign \
    GLOBAL_SKILLS_ROOT=/app/builtin-skills/global

# Runtime-only OS deps:
#   * libpq5     — psycopg2's shared lib at runtime (libpq-dev is build-only)
#   * curl       — used by HEALTHCHECK below
#   * ca-certs   — TLS for outbound calls (Bedrock, LangSmith, Anthropic API)
#   * libstdc++6 — the official Node 20 binary we copy below links against
#                  it; libc.so.6 / libm.so.6 / libgcc_s.so.1 are already
#                  present in python:3.13-slim-bookworm.
#   * git        — used by app/services/handoff_github.py (GitHub handoff capability)
#                  and agents/runtime/local.py (worktree isolation for parallel agents).
#                  Required for production, not just testing.
# Everything else from the builder stage (gcc, libpq-dev, build-essential)
# stays out of this layer to keep the image small.
# Phase 7: Install playwright browser deps in the same apt-get call to minimize layers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        ca-certificates \
        libstdc++6 \
        git \
        # Playwright deps (for chromium binary installation below)
        libatomic1 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libatspi2.0-0 \
        libcairo2 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libegl1 \
        libgbm1 \
        libglib2.0-0 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libx11-6 \
        libxcb1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxrandr2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# LibreOffice, headless — the converter for .docx / .xlsx / .pptx uploads
# (spec 019, FR-027). This is the ONE apt layer spec 019 admits: `pdf_tools`
# turns an Office file into a PDF here and then materialises it with exactly the
# code a native PDF takes, so there is no second extractor to keep in step.
#
# It also repairs spec 017's deck check. `pptx_tools._render_slides` has always
# shelled out to `soffice`, so on a developer machine (Homebrew LibreOffice) it
# converted and passed, while in THIS image it found nothing and passed anyway —
# green in both places for opposite reasons (FR-027a).
#
# --no-install-recommends is what keeps this at the low end of its range: it
# drops the Java runtime, the GUI stack and the sample documents. Only the three
# filters we actually convert are installed; fonts-liberation is metric-compatible
# with Arial/Times so a Word document paginates close to where Word put it.
# No poppler: rendering is pypdfium2, in-process (FR-042).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        libreoffice-calc \
        libreoffice-impress \
        fonts-liberation \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# setuptools CVE-2025-47273 (path traversal in PackageIndex, fixed in 78.1.1).
# setuptools is NOT a project dependency (absent from backend/uv.lock); the
# image scans find it in the SYSTEM interpreter's site-packages that the
# python:3.13-slim-bookworm base ships. It has a published fix, so it is
# upgraded here rather than accepted in backend/tools/ci/scan_accepts.py.
#
# `/usr/local/bin/python` explicitly: PATH puts /opt/venv/bin first, so a bare
# `pip` would target the venv, which is the wrong interpreter. Conditional on
# presence so this never ADDS setuptools to a base that does not carry it.
# Runs before the venv is copied in, so it cannot touch the locked venv.
RUN if /usr/local/bin/python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('setuptools') else 1)"; then \
        /usr/local/bin/python -m pip install --no-cache-dir --upgrade 'setuptools==80.9.0'; \
    fi

# Bring the pre-built venv across.
COPY --from=builder /opt/venv /opt/venv

# Headless Chromium for prototype render-validation (app/agents/render_check.py).
# `playwright` (the Python package) arrived in the venv above via the builder's
# `uv export --frozen --no-dev` — which means it MUST be declared in
# pyproject.toml's [project.dependencies], NOT in [dependency-groups].dev.
# It was dev-only until this was fixed, so `--no-dev` stripped it and this very
# step failed every build with `playwright: not found` (exit 127). If you are
# tempted to move it back to the dev group, this line breaks again.
# this step fetches the browser binary + its OS libraries. Run as root, BEFORE the USER switch,
# into a fixed path the non-root runtime user can launch from (PLAYWRIGHT_BROWSERS_PATH).
# Adds ~350 MB to the image — the cost of in-image headless validation.
# Phase 6: Note that playwright is a PRODUCTION dependency, not a test dependency,
# used for the render_check capability.
# Phase 7: All deps installed in single apt-get call above; just invoke playwright install.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN playwright install --with-deps chromium \
    && chown -R 10001:10001 /opt/playwright

# Node 20 runtime binary, taken from the pptx-builder STAGE rather than by
# repeating the node image reference. That stage is already
# `FROM node:20-bookworm-slim@sha256:3d0f...`, so this copies from the identical
# image by construction and the digest is written once.
#
# R-10: this used to repeat the full `node:20-bookworm-slim@sha256:...` reference
# inline. Two copies of a digest is a silent-divergence hazard of the exact kind
# this Dockerfile cares about: bumping only one would ship a `node` binary built
# against a different image than the `node_modules` copied below it, and an ABI
# mismatch between them surfaces at runtime inside pptx_export, not at build time.
#
# We need only the `node` binary itself — `npm` is not invoked at runtime;
# the FastAPI service in pptx_export.py spawns `node <script>` directly.
COPY --from=pptx-builder /usr/local/bin/node /usr/local/bin/node

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

# Copy only the bits we need at runtime. tests/, tools/, skills/ etc. are
# excluded by .dockerignore as a defence-in-depth (in case the COPY pattern
# ever changes). We deliberately do NOT copy backend/skills/ — that path
# is a bind-mounted EBS volume in production (per-user agent state).
# The one exception is skills/global/ (the built-in Skills catalog), baked to
# /app/builtin-skills/global further down, outside that mount.
COPY --chown=flowin:flowin app/ ./app/
# agents/ is a second top-level package the app imports (folder-per-agent
# architecture): app/main.py -> app.api.* -> `from agents.execution_engine...`.
# It also holds runtime DATA the loader reads from disk (prompts/*/AGENT.md,
# guardrails/*.md) — see the .dockerignore *.md re-include that keeps those in
# the build context.
COPY --chown=flowin:flowin agents/ ./agents/
COPY --chown=flowin:flowin alembic/ ./alembic/
COPY --chown=flowin:flowin alembic.ini ./alembic.ini

# Pre-migration deploy gate. `.github/scripts/remote-deploy.sh` runs this in a
# one-off container from THIS image (compose run --entrypoint python) after
# `compose pull` and before `up -d`:
#   scripts/migrate_local_users_to_cognito.py --report --fail-on-unlinked
# It is read-only. It has to be baked in because the gate must assert what THIS
# image's migrations require — docker-entrypoint.sh runs `alembic upgrade head`
# under `set -eu`, so a row migration 0038 rejects otherwise becomes a container
# that never binds its port rather than a legible deploy failure. Copied as a
# single file, not the whole scripts/ tree: nothing else in there is needed at
# runtime and the rest carries operator-only tooling.
COPY --chown=flowin:flowin scripts/migrate_local_users_to_cognito.py ./scripts/migrate_local_users_to_cognito.py

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
    && chown -R flowin:flowin /app/opendesign

# Entrypoint: runs migrations, then exec's uvicorn. Mode 0755 so the non-root
# user can execute it.
COPY --chown=flowin:flowin --chmod=0755 docker-entrypoint.sh ./docker-entrypoint.sh

# Bind-mount targets for the EBS data volume: per-user skills + per-run agent
# sandboxes (the deepagents disk filesystem, RUNS_ROOT=/app/runs). Created empty
# and owned by the non-root user so both mounts are writable inside the container.
RUN mkdir -p /app/skills /app/runs \
    && chown -R flowin:flowin /app /app/skills /app/runs

# Repo-shipped, read-only runtime DATA. Copied AFTER the chown above and without
# --chown, so all three trees stay root-owned and read-only to the runtime user.
#
# Built-in global Skills catalog: backend/skills/global/<id>/SKILL.md plus each
# skill's sibling reference files. app/agents/skills_catalog.py scans it (Library
# Skills tab, manifest `skills:` such as prototype-specify's, composer-selected
# skills) and skill staging copies a skill's folder into the run sandbox from it.
# It CANNOT live at /app/skills/global: /app/skills is the per-user EBS bind-mount
# above and shadows anything baked there, which is why every manifest skill failed
# with "unresolvable step skill id" in deployed environments. Baked here instead
# and selected via ENV GLOBAL_SKILLS_ROOT (same pattern as OD_ROOT/opendesign).
COPY skills/global/ ./builtin-skills/global/
# Global Hooks catalog (app/agents/hooks_catalog.py reads <backend>/hooks/global).
# /app/hooks is not a mount, so it is baked at the path the loader already reads.
COPY hooks/global/ ./hooks/global/
# Shipped PPT reference docs (app/agents/skills.py PPTX_SKILLS_DIR = <backend>/pptx).
COPY pptx/ ./pptx/
# Fail the BUILD, not a user's run, if any tree the runtime reads is missing,
# including the OpenDesign files the pptx tools resolve under OD_ROOT.
RUN test -n "$(find "$GLOBAL_SKILLS_ROOT" -mindepth 2 -maxdepth 2 -name SKILL.md -print -quit)" \
    && test -n "$(find /app/hooks/global -mindepth 2 -maxdepth 2 -name HOOK.md -print -quit)" \
    && test -f /app/pptx/SKILL.md \
    && test -f /app/pptx/pptxgenjs.md \
    && test -f "$OD_ROOT/skills/pptx-html-fidelity-audit/scripts/verify_layout.py" \
    && test -d "$OD_ROOT/fonts"

USER 10001:10001

EXPOSE 8000

# /health is defined in app/main.py and returns 200 once the app is ready.
# --start-period gives the lifespan hook (incl. alembic check + DB connect)
# room to settle before failures start counting against --retries.
#
# NOTE: in production this is NOT the effective healthcheck. docker-compose.yml
# declares its own `healthcheck:` for the backend service, and a compose-level
# healthcheck overrides the image's. Kept anyway: it is what makes `docker run`
# of this image self-describing, and it documents the probe compose should agree
# with. Change one, check the other.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["curl", "--fail", "--silent", "--show-error", "http://localhost:8000/health"]

ENTRYPOINT ["./docker-entrypoint.sh"]
