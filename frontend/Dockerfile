# syntax=docker/dockerfile:1.7

# ----------------------------------------------------------------------------
# Image design (see .agents/tasks/frontend-image-hardening-plan.md)
#
# Build stages (deps, builder) use node:<ver>-trixie-slim. They need a shell
# and npm, and they are never shipped or scanned, so a full slim image is fine.
#
# The runner stage uses Google distroless (gcr.io/distroless/nodejs24-debian13,
# :nonroot). It contains glibc, libstdc++, CA certificates, tzdata and the Node
# binary. It has NO shell, NO package manager, and no npm/yarn/corepack, which
# removes most of the packages scanners report and the tools an attacker would
# use after getting code execution.
#
# Why Debian (glibc) and not Alpine (musl): next/image uses sharp, and
# package-lock.json resolves the glibc binary @img/sharp-linux-x64.
#
# Why Debian 13: zlib 1.3.1, so CVE-2023-45853 (unfixed on bookworm) is gone.
#
# Every FROM is digest-pinned and asserted against backend/tools/ci/
# pin_authority.py (frontend_build_image / frontend_runtime_image) by
# backend/tests/unit/tools/ci/test_toolchain_pins.py. The distroless tag does
# not carry the Node patch version; CI's image smoke test
# (.github/scripts/ci-frontend-image-smoke.sh) asserts that the runtime's
# process.version equals pin_authority.node_runtime_version.
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# Stage 1: deps — install npm dependencies (deterministic via npm ci)
# ----------------------------------------------------------------------------
FROM node:24.22.3-trixie-slim@sha256:af02d57b57719b9657a45199a79264a9437940cd55b3c7b3fc99615654f124a0 AS deps

WORKDIR /app

# Copy only manifests so this layer is cached unless deps change.
COPY package.json package-lock.json ./

# npm ci is deterministic and fails on lockfile mismatch. We intentionally do
# NOT pass --omit=dev: Next.js requires devDeps (typescript, tailwind,
# eslint-config-next, @types/*) at build time. None of them reach the runner:
# it receives only the traced .next/standalone/node_modules.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

# ----------------------------------------------------------------------------
# Stage 2: builder — produce the standalone Next.js bundle
# ----------------------------------------------------------------------------
FROM node:24.22.3-trixie-slim@sha256:af02d57b57719b9657a45199a79264a9437940cd55b3c7b3fc99615654f124a0 AS builder

WORKDIR /app

# Re-use the deps layer's node_modules.
COPY --from=deps /app/node_modules ./node_modules

# Copy the rest of the source.
COPY . .

# NEXT_PUBLIC_* vars are inlined into the JS bundle at BUILD time, not runtime.
# They must be present here. Defaulting to empty string means "use relative
# URLs", which works fine when the app is served behind nginx that proxies
# both `/` and `/api`.
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Disable Next.js anonymous telemetry to Vercel.
ENV NEXT_TELEMETRY_DISABLED=1

# Builds .next/standalone (server.js + minimal node_modules) and .next/static.
# /out/next-cache becomes the runner's only app-writable directory. It is
# created here because the distroless runner has no shell to run mkdir.
RUN npm run build \
    && mkdir -p /out/next-cache

# ----------------------------------------------------------------------------
# Stage 3: runner — distroless runtime (no shell, no package manager)
# ----------------------------------------------------------------------------
FROM gcr.io/distroless/nodejs24-debian13:nonroot@sha256:9fc11f6ee65993285c0fe3c4c9bbc4fd275fd4470572f58834ce490df91056e3 AS runner

LABEL org.opencontainers.image.title="velocityai-frontend" \
      org.opencontainers.image.description="VelocityAI Next.js standalone frontend" \
      org.opencontainers.image.base.name="gcr.io/distroless/nodejs24-debian13:nonroot"

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# App code is copied WITHOUT --chown, so it stays owned by root. The runtime
# user can read it but cannot modify server.js or the JS served to browsers.
#
# .next/standalone contains server.js + a pruned node_modules. Mounted at /app.
COPY --from=builder /app/.next/standalone ./
# public/ is not bundled into .next/standalone — copy it explicitly.
COPY --from=builder /app/public ./public
# .next/static is also not bundled into standalone — Next expects it served
# from .next/static at runtime.
COPY --from=builder /app/.next/static ./.next/static

# The only directory the app writes to: Next's server cache (next/image
# optimisation output). docker-compose.yml mounts a tmpfs here, owned by the
# same UID, because the production root filesystem is read-only.
COPY --from=builder --chown=10001:10001 /out/next-cache ./.next/cache

# Fixed UID/GID 10001 (matches the backend and infra/scripts/bootstrap-ec2.sh).
# Distroless has no /etc/passwd entry for it; Next.js does not need one, and
# the CI smoke test proves the server starts and serves under it.
USER 10001:10001

EXPOSE 3000

# Exec form: there is no /bin/sh in this image, so a shell-form HEALTHCHECK
# would always fail. Absolute node path: distroless does not put /nodejs/bin
# on PATH. 127.0.0.1 (NOT localhost) because Next.js's standalone server binds
# 0.0.0.0 (IPv4 only) and `localhost` can resolve to ::1 first — a v6 probe
# would silently time out and the healthcheck would stay "starting" forever.
# docker-compose.yml deliberately does not override this probe, so each image
# carries the one that matches its own filesystem (rollback-safe).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["/nodejs/bin/node", "-e", "require('http').get('http://127.0.0.1:3000/', r => process.exit(r.statusCode < 400 ? 0 : 1)).on('error', () => process.exit(1))"]

# Exec form so signals (SIGTERM, SIGINT) reach node directly.
ENTRYPOINT ["/nodejs/bin/node"]
CMD ["server.js"]
