#!/usr/bin/env bash
# scripts/local-dev/podman-up.sh
#
# Runs the VelocityAI container stack locally on macOS with Podman, built from
# whatever branch is currently checked out.
#
#   Postgres: NOT managed here. It is a system service with its own pod,
#             started separately on 127.0.0.1:5432. This script only checks
#             it is reachable.
#   Backend:  http://localhost:8000  (docker-compose.yml service `backend`)
#   Frontend: http://localhost:3000  (docker-compose.yml service `frontend`)
#
# The backend reaches Postgres at host.docker.internal:5432, the same shape as
# production (Postgres native on the host, outside compose).
#
# AWS: docker-compose.aws.yml mounts ~/.aws into the backend; the profile comes
# from AWS_PROFILE in app.env. Run `aws sso login --profile <name>` first.
# Runs: VELOCITY_RUNS_DIR in app.env is the host folder mounted at /app/runs.
#
# Usage:
#   scripts/local-dev/podman-up.sh            # build + start everything
#   scripts/local-dev/podman-up.sh --no-build # start with existing images
#   scripts/local-dev/podman-up.sh down       # stop backend + frontend (DB untouched)
#   scripts/local-dev/podman-up.sh status     # show what's running
#
# Frontend type-check: by default the frontend image is built with *.test.*
# files excluded from the Next.js build type-check (test files are never in
# the bundle; app code is still fully type-checked). Set STRICT_TYPECHECK=1 to
# build with the repo's tsconfig unchanged.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="$REPO_ROOT/app.env"
COMPOSE=(podman-compose -f "$REPO_ROOT/docker-compose.yml" -f "$SCRIPT_DIR/docker-compose.aws.yml")

log() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

env_value() { # env_value KEY -> value from app.env (last occurrence wins)
  grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-
}

wait_for() { # wait_for NAME SECONDS CMD...
  local name=$1 secs=$2; shift 2
  for ((i = 0; i < secs; i += 3)); do
    "$@" >/dev/null 2>&1 && { log "$name is up."; return 0; }
    sleep 3
  done
  die "$name did not become ready within ${secs}s"
}

ensure_machine() {
  command -v podman >/dev/null || die "podman not found (brew install podman)"
  command -v podman-compose >/dev/null || die "podman-compose not found (brew install podman-compose)"

  if ! podman machine inspect >/dev/null 2>&1; then
    log "Creating Podman machine (6 CPUs, 8 GB RAM, 100 GB disk)..."
    podman machine init --cpus 6 --memory 8192 --disk-size 100
  fi
  if [[ "$(podman machine inspect --format '{{.State}}')" != "running" ]]; then
    log "Starting Podman machine..."
    podman machine start
  fi

  # Base images are pinned to amd64 digests; Rosetta runs them far more
  # reliably than qemu (the Next.js build segfaults under qemu).
  if ! podman machine ssh 'test -e /proc/sys/fs/binfmt_misc/rosetta' 2>/dev/null; then
    echo "WARNING: Rosetta is not active in the Podman VM; amd64 builds may crash." >&2
    echo "         Add 'rosetta = true' under [machine] in ~/.config/containers/containers.conf" >&2
    echo "         and run: podman machine stop && podman machine start" >&2
  fi

  # Bind-mount sources from docker-compose.yml must exist inside the VM.
  # Owned by the VM user, which rootless podman maps to container root, so the
  # image's entrypoint can chown them to 10001 at start.
  podman machine ssh 'sudo mkdir -p /opt/velocityai/data/skills /opt/velocityai/data/runs \
    && sudo chown $(id -u):$(id -g) /opt/velocityai/data/skills /opt/velocityai/data/runs'
}

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    log "Creating app.env from app.env.example..."
    local sk
    sk=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
    sed -e "s|^SECRET_KEY=.*|SECRET_KEY=$sk|" \
        -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://sa:postgres@host.docker.internal:5432/velocityai|" \
        app.env.example > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
  fi

  local url
  url=$(env_value DATABASE_URL)
  [[ -n "$url" ]] || die "DATABASE_URL is not set in app.env"
  # Parse user / password / db name out of DATABASE_URL.
  read -r PG_USER PG_PASSWORD PG_DB < <(python3 -c '
import sys, urllib.parse as u
p = u.urlparse(sys.argv[1])
print(u.unquote(p.username or ""), u.unquote(p.password or ""), p.path.lstrip("/"))
' "$url")
  [[ -n "$PG_USER" && -n "$PG_PASSWORD" && -n "$PG_DB" ]] \
    || die "DATABASE_URL in app.env must include user, password and database name"
  [[ "$url" == *"@host.docker.internal:5432/"* ]] \
    || echo "WARNING: DATABASE_URL does not point at host.docker.internal:5432; the backend may not reach Postgres." >&2

  # Machine-/account-specific values live only in the git-ignored app.env.
  [[ -n "$(env_value AWS_PROFILE)" ]] \
    || die "AWS_PROFILE is not set in app.env (your AWS SSO profile name)"
  VELOCITY_RUNS_DIR=$(env_value VELOCITY_RUNS_DIR)
  [[ -n "$VELOCITY_RUNS_DIR" ]] \
    || die "VELOCITY_RUNS_DIR is not set in app.env (host folder for run sandboxes)"
  mkdir -p "$VELOCITY_RUNS_DIR"
  export VELOCITY_RUNS_DIR  # interpolated by docker-compose.aws.yml
}

require_postgres() {
  # Postgres belongs to the system, not this stack: only check it is listening.
  (exec 3<>/dev/tcp/127.0.0.1/5432) 2>/dev/null \
    || die "Postgres is not reachable on 127.0.0.1:5432. Start it first."
  log "Postgres is reachable on 127.0.0.1:5432."
}

build_images() {
  # Keep exactly one backend + one frontend image: no per-step layer images
  # (the build cache), so every build is a full build. The previous image is
  # untagged by the new one and pruned once the new containers are running.
  export BUILDAH_LAYERS=false
  log "Building backend image (branch: $(git branch --show-current))..."
  "${COMPOSE[@]}" build backend

  local api_url
  api_url=$(env_value NEXT_PUBLIC_API_URL)
  if [[ "${STRICT_TYPECHECK:-0}" == "1" ]]; then
    log "Building frontend image (strict type-check)..."
    podman build -t velocityai-frontend:local \
      --build-arg NEXT_PUBLIC_API_URL="$api_url" frontend
  else
    log "Building frontend image (test files excluded from type-check)..."
    local ctx
    ctx=$(mktemp -d)
    rsync -a --exclude node_modules --exclude .next frontend/ "$ctx/"
    python3 - "$ctx/tsconfig.json" <<'PY'
import re, sys
path = sys.argv[1]
src = open(path).read()
new, n = re.subn(r'"exclude"\s*:\s*\[([^\]]*)\]',
                 lambda m: '"exclude": [%s, "**/*.test.ts", "**/*.test.tsx", "**/*.spec.ts", "**/*.spec.tsx", "e2e", "typecheck"]' % m.group(1).strip(),
                 src, count=1)
if not n:
    sys.exit("could not find \"exclude\" in frontend/tsconfig.json")
open(path, "w").write(new)
PY
    local rc=0
    podman build -t velocityai-frontend:local \
      --build-arg NEXT_PUBLIC_API_URL="$api_url" "$ctx" || rc=$?
    rm -rf "$ctx"
    [[ $rc -eq 0 ]] || die "frontend image build failed"
  fi
}

start_app() {
  log "Starting backend + frontend..."
  # --force-recreate: podman-compose keeps an existing container when only its
  # image changed, so a fresh build would otherwise never be picked up.
  "${COMPOSE[@]}" up -d --no-build --force-recreate backend frontend
  wait_for "Backend (http://localhost:8000)" 180 curl -sf http://127.0.0.1:8000/health
  wait_for "Frontend (http://localhost:3000)" 180 curl -sf -o /dev/null http://127.0.0.1:3000/
}

status() {
  podman machine list
  echo
  podman pod ps
  echo
  podman ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
}

case "${1:-up}" in
  down)
    ensure_machine >/dev/null 2>&1 || true
    log "Stopping backend + frontend..."
    VELOCITY_RUNS_DIR="$(env_value VELOCITY_RUNS_DIR)"
    export VELOCITY_RUNS_DIR
    "${COMPOSE[@]}" down || true
    log "Done. Postgres is not managed here and keeps running."
    ;;
  status)
    status
    ;;
  up | --no-build)
    ensure_machine
    ensure_env
    require_postgres
    [[ "${1:-up}" == "--no-build" ]] || build_images
    start_app
    # Each build leaves the previous image + per-step layer images untagged
    # (<none>, ~2.5 GB per backend build). Drop them once the new containers run.
    if [[ "${1:-up}" != "--no-build" ]]; then
      log "Removing untagged images left by previous builds..."
      podman image prune -f >/dev/null
    fi
    echo
    status
    echo
    log "VelocityAI is running on branch $(git branch --show-current):"
    log "  Frontend: http://localhost:3000"
    log "  Backend:  http://localhost:8000  (health: /health)"
    log "  Postgres: 127.0.0.1:5432  db=$PG_DB user=$PG_USER  (not managed by this script)"
    log "Logs: podman-compose logs -f backend   |   Stop: $0 down"
    ;;
  *)
    die "unknown command '$1' (use: up | --no-build | down | status)"
    ;;
esac
