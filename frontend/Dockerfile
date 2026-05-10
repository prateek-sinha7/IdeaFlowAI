# syntax=docker/dockerfile:1.7

# ----------------------------------------------------------------------------
# Stage 1: deps — install npm dependencies (deterministic via npm ci)
# ----------------------------------------------------------------------------
FROM node:20-alpine AS deps

# libc6-compat is needed for some npm native modules on alpine (musl vs glibc).
RUN apk add --no-cache libc6-compat

WORKDIR /app

# Copy only manifests so this layer is cached unless deps change.
COPY package.json package-lock.json ./

# npm ci is deterministic and fails on lockfile mismatch. We intentionally do
# NOT pass --only=production: Next.js requires devDeps (typescript, tailwind,
# eslint-config-next, @types/*) at build time.
RUN npm ci

# ----------------------------------------------------------------------------
# Stage 2: builder — produce the standalone Next.js bundle
# ----------------------------------------------------------------------------
FROM node:20-alpine AS builder

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
ARG NEXT_PUBLIC_WS_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

# Disable Next.js anonymous telemetry to Vercel.
ENV NEXT_TELEMETRY_DISABLED=1

# Builds .next/standalone (server.js + minimal node_modules) and .next/static.
RUN npm run build

# ----------------------------------------------------------------------------
# Stage 3: runner — minimal runtime image
# ----------------------------------------------------------------------------
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
# Bind to all interfaces; the standalone server respects HOSTNAME.
ENV HOSTNAME=0.0.0.0

# Non-root user/group with fixed UID/GID 10001 (matches backend convention).
RUN addgroup --system --gid 10001 nodejs \
    && adduser --system --uid 10001 --ingroup nodejs nextjs

# public/ is not bundled into .next/standalone — copy it explicitly.
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

# .next/standalone contains server.js + a pruned node_modules. Mounted at /app.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./

# .next/static is also not bundled into standalone — Next expects it served
# from .next/static at runtime.
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

# wget is provided by busybox in alpine — no install needed.
# 127.0.0.1 (NOT localhost): busybox wget resolves localhost to ::1 first, but
# Next.js standalone binds 0.0.0.0 (IPv4 only), so a localhost spider silently
# times out and the healthcheck stays "starting" forever.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:3000/ || exit 1

# Exec form so signals (SIGTERM, SIGINT) reach node directly.
CMD ["node", "server.js"]
