# syntax=docker/dockerfile:1.7
#
# Production Dockerfile for the Flowin backend.
#
# Stages:
#   python-base  — the ONE pinned Python base reference (tag + multi-arch index
#                  digest). builder and runtime both derive from it, so the venv
#                  is always built against the exact interpreter it runs on.
#   builder      — build toolchain + uv; installs the locked, hash-verified
#                  production dependency set into /opt/venv. Thrown away.
#   pptx-builder — Node 24 LTS + pptxgenjs into /opt/pptx/node_modules. Thrown away.
#   runtime      — slim image: venv, node binary, pptxgenjs, headless Chromium,
#                  LibreOffice (-nogui), git and the app. Runs as 10001:10001.
#
# Design:
#   * Every FROM is pinned by tag + sha256 digest; when bumping, update
#     backend/tools/ci/pin_authority.py in the same change.
#   * Runs as 10001:10001. App code, venv, browsers and node_modules are
#     root-owned; only /app/skills, /app/runs (bind mounts) and /tmp are written.
#   * No curl, wget, xvfb, pip, compilers or full Chromium in the final image
#     (headless shell only). sh/bash/apt/dpkg remain: the entrypoint and
#     LibreOffice's launcher are shell scripts, and the rest are Essential
#     Debian packages.
#   * Verified by ci.yml container-scan (Trivy + Grype) and deploy.yml's
#     post-push scan and health gate.

# ============================================================================
# Stage 0 — python-base (single pinned reference)
# ============================================================================
FROM python:3.13-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS python-base

# ============================================================================
# Stage 1 — builder (never shipped)
# ============================================================================
FROM python-base AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for native wheels. Every production wheel currently resolves to a
# manylinux binary on linux/amd64 (checked 2026-11), so this is the fallback
# build path for other arches. It exists only in this throwaway stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        libffi-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# uv exports the production slice of backend/uv.lock. Hash-pinned (PyPI sha256
# of the uv 0.11.3 manylinux wheels) so a tampered index cannot swap it.
RUN printf '%s\n' 'uv==0.11.3 --hash=sha256:0fde893b5ab9f6997fe357138e794bac09d144328052519fbbe2e6f72145e457 --hash=sha256:55ba578752f29a3f2b22879b22a162edad1454e3216f3ca4694fdbd4093a6822 --hash=sha256:45006bcd9e8718248a23ab81448a5beb46a72a9dd508e3212d6f3b8c63aeb88a' \
        > /tmp/uv-requirements.txt \
    && pip install --no-cache-dir --require-hashes -r /tmp/uv-requirements.txt \
    && rm /tmp/uv-requirements.txt

# The venv is created WITHOUT pip: pip is not a runtime dependency (absent from
# the no-dev export) and its vendored setuptools 70.3.0 is a scanner finding.
# The system pip installs into it via `--python`.
RUN python -m venv --without-pip /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Only the lock inputs are copied first, so source-only changes keep the
# (slow) dependency layer cached. `uv export --frozen` fails the build if
# uv.lock and pyproject.toml disagree; `--no-dev` drops test/CI tooling.
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project -o requirements-prod.lock.txt

# --require-hashes: every wheel is verified against the digest uv.lock recorded.
# pip is NOT upgraded: the base's pip already supports --python and hashes.
RUN /usr/local/bin/python -m pip --python /opt/venv/bin/python install \
        --no-cache-dir --require-hashes -r requirements-prod.lock.txt \
    && /opt/venv/bin/python -m compileall -q -j 0 /opt/venv/lib


# ============================================================================
# Stage 2 — pptx-builder (never shipped)
# ============================================================================
# Node 24 LTS (Node 20 reached end of life on 2026-04-30). Same Debian release
# as the runtime, so the copied `node` binary is ABI-compatible with its libc
# and libstdc++. Version matches frontend/Dockerfile (24.22.3).
FROM node:24.22.3-trixie-slim@sha256:af02d57b57719b9657a45199a79264a9437940cd55b3c7b3fc99615654f124a0 AS pptx-builder

# pptxgenjs at the version pinned by frontend/package-lock.json. --ignore-scripts:
# neither pptxgenjs nor its dependency tree declares install hooks, so this only
# removes the ability of a compromised transitive package to run code at build.
RUN npm install --prefix /opt/pptx --no-audit --no-fund --omit=dev --ignore-scripts pptxgenjs@3.12.0


# ============================================================================
# Stage 3 — runtime
# ============================================================================
FROM python-base AS runtime

# Names AND values identical to the previous image (C1).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}" \
    OD_ROOT=/app/opendesign \
    GLOBAL_SKILLS_ROOT=/app/builtin-skills/global \
    USER_SKILLS_ROOT=/app/skills/users \
    GLOBAL_HOOKS_ROOT=/app/hooks/global \
    PPTX_SKILLS_ROOT=/app/pptx \
    RUNS_ROOT=/app/runs

# ONE apt layer for every runtime OS package, with security updates applied and
# the package lists removed in the same layer.
#   * apt-get upgrade — pulls Debian 13 security fixes published after the base
#     digest was cut (same suite; no feature upgrades).
#   * libpq5, ca-certificates, libstdc++6 — as before (libpq for psycopg's
#     pure-python fallback, TLS roots, node's C++ runtime).
#   * git — runtime dependency (app/agents/runtime/local.py, app/services/handoff_github.py).
#   * Chromium libraries — Playwright 1.64.1's debian13-x64 `chromium` list (what
#     `playwright install --with-deps` would add), plus libatomic1, libegl1 and
#     libpangocairo-1.0-0 kept from the earlier explicit list. libgtk-3-0t64 was
#     removed: the headless shell does not use GTK (Playwright lists it for
#     firefox, not chromium), and it alone pulled systemd, dbus-daemon,
#     dbus-user-session, dconf and gdk-pixbuf into the image.
#   * Fonts — Playwright 1.64.1's debian13 `tools` list MINUS xvfb. xvfb is a
#     virtual X server for HEADED browsers; every launch in this codebase is
#     headless. The fonts stay so screenshots/thumbnails render identically.
#   * LibreOffice core/writer/calc/impress, -nogui variants, + fonts-liberation —
#     Office->PDF converter (app/agents/tools/soffice.py, always --headless).
#     Built from the same libreoffice source at the same version as the GUI
#     packages; the -nogui core omits the GUI toolkit plugins, which drops
#     GStreamer, libzxing and the X session libraries. impress-nogui pulls
#     libreoffice-draw-nogui.
# Removed: curl (healthchecks now use Python's urllib), xvfb, libgtk-3-0t64.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        ca-certificates \
        libstdc++6 \
        git \
        libasound2t64 \
        libatomic1 \
        libatk-bridge2.0-0t64 \
        libatk1.0-0t64 \
        libatspi2.0-0t64 \
        libcairo2 \
        libcups2t64 \
        libdbus-1-3 \
        libdrm2 \
        libegl1 \
        libgbm1 \
        libglib2.0-0t64 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libx11-6 \
        libxcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        fonts-noto-color-emoji \
        fonts-unifont \
        libfontconfig1 \
        libfreetype6 \
        xfonts-scalable \
        fonts-liberation \
        fonts-ipafont-gothic \
        fonts-wqy-zenhei \
        fonts-tlwg-loma-otf \
        fonts-freefont-ttf \
        libreoffice-core-nogui \
        libreoffice-writer-nogui \
        libreoffice-calc-nogui \
        libreoffice-impress-nogui \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Remove pip from the SYSTEM interpreter. Nothing at runtime uses it: the app,
# alembic, uvicorn and every subprocess run /opt/venv/bin/python, a venv without
# system site-packages. Its vendored setuptools 70.3.0 (CVE-2025-47273) was the
# remaining setuptools finding; the base ships no standalone setuptools.
RUN /usr/local/bin/python -m pip uninstall --yes pip

# Locked venv from the builder. Root-owned: the app only reads it.
COPY --from=builder /opt/venv /opt/venv

# Headless Chromium for render_check / playwright tools / html_extract /
# acceptance_tools. Playwright 1.64.1 launches `chromium-headless-shell` for every
# headless launch (server/chromium/chromium.ts), so `--only-shell` skips the
# full 393 MB Chromium build that was installed but never launched. OS libraries
# came from the apt layer above, so no `--with-deps` (which also left apt lists
# behind). Root-owned: Playwright tolerates a read-only browsers path at launch.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN playwright install --only-shell chromium

# Build-time functional gate: fail the BUILD, not a user's run, when the apt list
# above cannot actually run Chromium or LibreOffice.
#   a) launch the headless shell, load about:blank and take a screenshot;
#   b) convert a text file to PDF with LibreOffice;
#   c) ldd both binaries for unresolved libraries (diagnostic).
# ldd alone is not enough: it checks only the libraries a binary links at load
# time. Both programs dlopen() more at run time (Chromium: EGL/GLES and its
# software renderer; LibreOffice: its VCL backend and import/export filters), so
# a missing dlopen'd library passes ldd and fails only when that code runs.
# Headless shell path for Playwright 1.64.1 (chromium-headless-shell revision
# 1248, browsers.json):
#   /opt/playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell
# Update it with the Playwright pin (tools/ci/pin_authority.py). `test -x` makes a
# stale path fail the build; without it ldd would error, grep would match
# nothing, and the check would pass vacuously. Runs as root, so Chromium gets
# --no-sandbox, as every launch in app/ does.
RUN python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True, args=['--no-sandbox']); page = b.new_page(); page.goto('about:blank'); page.screenshot(path='/tmp/smoke.png'); b.close(); p.stop()" \
    && test -s /tmp/smoke.png \
    && rm -f /tmp/smoke.png \
    && printf 'smoke' > /tmp/s.txt \
    && soffice --headless --norestore -env:UserInstallation=file:///tmp/lo \
        --convert-to pdf --outdir /tmp /tmp/s.txt \
    && test -s /tmp/s.pdf \
    && rm -rf /tmp/s.txt /tmp/s.pdf /tmp/lo \
    && test -x /opt/playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell \
    && ! ldd /opt/playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell | grep -q "not found" \
    && ! ldd /usr/lib/libreoffice/program/soffice.bin | grep -q "not found"

# Node runtime binary only (npm is not used at runtime; pptx_export.py spawns
# `node <script>`), copied from the pptx-builder STAGE so the node digest is
# written once. node_modules are root-owned; node only reads them.
COPY --from=pptx-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=pptx-builder /opt/pptx/node_modules /opt/pptx/node_modules

# Non-root user, numeric 10001:10001 (matches the host's data-volume owner and
# the entrypoint's setpriv target). System account: no home directory created,
# no login shell. The passwd entry keeps setpriv --init-groups working when the
# image is started as root (rollback path).
RUN groupadd --system --gid 10001 flowin \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --no-create-home \
        --shell /sbin/nologin flowin

WORKDIR /app

# Application code: root-owned, world-readable, NOT writable by 10001 (H5).
# tests/, tools/, per-user skills/ are excluded by .dockerignore as defence in
# depth. backend/skills/ is the per-user EBS bind mount and is not copied; the
# built-in catalog goes to /app/builtin-skills/global below.
COPY app/ ./app/
# agents/ is the second top-level package (app.api.* -> agents.execution_engine)
# and holds runtime DATA (prompts/*/AGENT.md, guardrails/*.md).
COPY agents/ ./agents/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

# Pre-migration deploy gate run by .github/scripts/remote-deploy.sh via
# `compose run --entrypoint python` before `up -d`. Read-only script.
COPY scripts/migrate_local_users_to_cognito.py ./scripts/migrate_local_users_to_cognito.py

# OpenDesign reference content read by app/services/od_loader.py, supplied as the
# named build context `opendesign` (buildx --build-context / compose
# additional_contexts). Baked outside the /app/skills mount; selected by OD_ROOT.
COPY --from=opendesign . ./opendesign/

# Build-time gallery thumbnails (best-effort; the script always exits 0). Runs as
# root before USER, writing into the root-owned tree. Because the script never
# fails the build, a missing Chromium library shows up only as fewer
# thumbnail.jpg files under /app/opendesign/design-templates.
COPY scripts/generate_template_thumbnails.py ./scripts/generate_template_thumbnails.py
RUN python scripts/generate_template_thumbnails.py --dir /app/opendesign/design-templates

# Entrypoint: optional root-only chown block, then alembic + exec uvicorn.
COPY --chmod=0755 docker-entrypoint.sh ./docker-entrypoint.sh

# Mount points for the EBS data volume. Only these two directories (not their
# parent, not -R) belong to 10001, so an unmounted `docker run` can still write
# them. A bind mount replaces them with the host directory, whose owner must be
# 10001 (infra/scripts/bootstrap-ec2.sh / reconcile-host-config.sh).
RUN mkdir -p /app/skills /app/runs \
    && chown 10001:10001 /app/skills /app/runs

# Repo-shipped, read-only runtime DATA (root-owned).
# Built-in global Skills catalog (app/agents/skills_catalog.py, GLOBAL_SKILLS_ROOT).
COPY skills/global/ ./builtin-skills/global/
# Global Hooks catalog (app/agents/hooks_catalog.py reads <backend>/hooks/global).
COPY hooks/global/ ./hooks/global/
# Shipped PPT reference docs (app/agents/skills.py PPTX_SKILLS_DIR).
COPY pptx/ ./pptx/

# Fail the BUILD when the workflow builder skill's Markdown or the builder's
# system prompt did not reach the image (the .dockerignore re-includes).
RUN for f in SKILL.md docs/problem-decomposition.md docs/quick-reference.md \
        docs/prompt-writing.md scripts/validate_manifest.py; do \
        test -f "/app/app/agents/workflow_builder/skills/velocity-workflow-creator/$f" \
            || exit 1; \
    done \
    && test -f /app/app/agents/workflow_builder/prompts/system_prompt.v2.md
# Fail the BUILD, not a user's run, if any tree the runtime reads is missing.
RUN test -n "$(find "$GLOBAL_SKILLS_ROOT" -mindepth 2 -maxdepth 2 -name SKILL.md -print -quit)" \
    && test -n "$(find /app/hooks/global -mindepth 2 -maxdepth 2 -name HOOK.md -print -quit)" \
    && test -f /app/pptx/SKILL.md \
    && test -f /app/pptx/pptxgenjs.md \
    && test -f "$OD_ROOT/skills/pptx-html-fidelity-audit/scripts/verify_layout.py" \
    && test -d "$OD_ROOT/fonts"

# Pre-compile app bytecode (H8). With PYTHONDONTWRITEBYTECODE=1 nothing is written
# at runtime, so the image works on a read-only root filesystem and still skips
# compilation on import. The venv was compiled in the builder.
RUN python -m compileall -q -j 0 /app/app /app/agents /app/alembic /app/scripts

# HOME is pinned to the runtime user's home (unchanged). /app is root-owned now,
# so nothing can be written there; see the report for what that affects.
ENV HOME=/app

# Run as the unprivileged user (H4). docker-entrypoint.sh's root-only block is
# kept for this release so a rollback to a root-start image still works; with
# USER set it is skipped (`id -u` != 0).
USER 10001:10001

EXPOSE 8000

# /health is defined in app/main.py. Same timings as before; the probe is the
# Python standard library instead of curl. Any exception (connection refused,
# HTTP >= 400, timeout) exits 1 = unhealthy, matching `curl --fail`.
# docker-compose.yml declares the same probe; a compose healthcheck overrides
# this one, so change both together.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"]

ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="velocityai-backend" \
      org.opencontainers.image.description="Velocity backend (FastAPI/uvicorn) with headless Chromium, LibreOffice and Node for document tooling" \
      org.opencontainers.image.source="https://github.com/Hexaware-HnI/velocityai" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.base.name="docker.io/library/python:3.13-slim-trixie" \
      org.opencontainers.image.base.digest="sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90"

# Exec form: docker-entrypoint.sh is PID 1 and `exec`s uvicorn, so SIGTERM from
# `docker stop` reaches uvicorn directly. Unchanged.
ENTRYPOINT ["./docker-entrypoint.sh"]
