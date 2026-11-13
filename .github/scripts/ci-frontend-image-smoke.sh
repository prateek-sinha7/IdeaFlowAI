#!/usr/bin/env bash
# Smoke-test the hardened frontend image the way production runs it.
#
# WHY THIS EXISTS
# frontend/Dockerfile ships on gcr.io/distroless/nodejs24-debian13:nonroot: no
# shell, no package manager, node at /nodejs/bin/node (NOT on PATH), code owned
# by root, and the process running as 10001:10001. docker-compose.yml runs it
# with a read-only root filesystem, tmpfs for /tmp and /app/.next/cache, all
# capabilities dropped and no-new-privileges. Nothing else in CI starts the
# image, and developers may not have Docker locally, so this script is the
# proof that the image still serves under those constraints and that the
# hardening is real.
#
# Checks (each one fails the step):
#   1. The container becomes `healthy` under the production runtime flags
#      (the image's own exec-form HEALTHCHECK).
#   2. GET / answers with a status below 400.
#   3. next/image optimises a public/ image (sharp's glibc binary loads, and
#      the server can write its cache to the tmpfs).
#   4. There is no shell: `docker exec <c> sh` fails.
#   5. The app cannot modify its own code: writing /app/server.js fails.
#   6. The image's configured user and the live process are both 10001:10001.
#   7. The runtime's process.version equals pin_authority.node_runtime_version
#      (the distroless tag names no patch version; only this run can see it).
#   8. The container logs contain no EROFS/EACCES (a write outside the tmpfs).
# It also records the image size in the evidence and the step summary.
#
# Inputs (environment):
#   IMAGE_REF   the locally loaded image to test (required)
#
# Usage: ci-frontend-image-smoke.sh <evidence-dir>
set -euo pipefail

evidence_dir="${1:?usage: ci-frontend-image-smoke.sh <evidence-dir>}"
image_ref="${IMAGE_REF:?IMAGE_REF must name the locally built frontend image}"
workspace="${GITHUB_WORKSPACE:-.}"

expected_user="10001:10001"
node_bin="/nodejs/bin/node"
host_port="13000"
container="frontend-smoke-$$"

mkdir -p "${evidence_dir}"
evidence_abs="$(cd "${evidence_dir}" && pwd)"
log_file="${evidence_abs}/frontend-image-smoke.log"
: >"${log_file}"

failures=0

log() {
  echo "$*" | tee -a "${log_file}"
}

fail() {
  echo "::error title=Frontend image smoke::$*"
  echo "FAIL: $*" >>"${log_file}"
  failures=$((failures + 1))
}

pass() {
  log "PASS: $*"
}

cleanup() {
  if docker container inspect "${container}" >/dev/null 2>&1; then
    {
      echo "---- container logs ----"
      docker logs "${container}" 2>&1 || true
    } >>"${log_file}"
    docker rm -f "${container}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# The authority module has no third-party imports, so load it straight from
# its file; no backend environment is needed.
expected_node="$(
  python3 - "${workspace}/backend/tools/ci/pin_authority.py" <<'PY'
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("pin_authority", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.get_node_runtime())
PY
)"
log "image:          ${image_ref}"
log "expected node:  v${expected_node}"
log "expected user:  ${expected_user}"

# ── Start it exactly as docker-compose.yml does ─────────────────────────────
docker run --detach --name "${container}" \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m \
  --tmpfs /app/.next/cache:rw,noexec,nosuid,nodev,size=128m,uid=10001,gid=10001,mode=0700 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 200 \
  --init \
  --memory 1g \
  --publish "127.0.0.1:${host_port}:3000" \
  "${image_ref}" >/dev/null

# ── 1. Health ───────────────────────────────────────────────────────────────
status="starting"
for _ in $(seq 1 45); do
  running="$(docker inspect -f '{{.State.Running}}' "${container}")"
  if [[ "${running}" != "true" ]]; then
    status="exited"
    break
  fi
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container}")"
  if [[ "${status}" == "healthy" || "${status}" == "unhealthy" || "${status}" == "none" ]]; then
    break
  fi
  sleep 2
done
if [[ "${status}" == "healthy" ]]; then
  pass "container is healthy under --read-only, --cap-drop ALL, no-new-privileges"
else
  fail "container health is '${status}' (expected healthy); see the container logs in ${log_file}"
fi

# ── 2. Root page ────────────────────────────────────────────────────────────
root_code="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 10 "http://127.0.0.1:${host_port}/" || echo 000)"
if ((root_code >= 200 && root_code < 400)); then
  pass "GET / -> ${root_code}"
else
  fail "GET / -> ${root_code} (expected 2xx/3xx)"
fi

# ── 3. next/image optimisation (sharp + writable cache) ─────────────────────
image_url="http://127.0.0.1:${host_port}/_next/image?url=%2Fhexaware-logo.png&w=64&q=75"
image_type="$(curl --silent --fail --output /dev/null --write-out '%{content_type}' --max-time 20 "${image_url}" || echo none)"
if [[ "${image_type}" == image/* ]]; then
  pass "next/image -> ${image_type}"
else
  fail "next/image returned content type '${image_type}' (expected image/*)"
fi

# ── 4. No shell ─────────────────────────────────────────────────────────────
if docker exec "${container}" sh -c true >/dev/null 2>&1; then
  fail "a shell is available in the runtime image"
else
  pass "no shell in the runtime image"
fi

# ── 5. Code is read-only to the app ─────────────────────────────────────────
if docker exec "${container}" "${node_bin}" -e "require('fs').appendFileSync('/app/server.js', '')" >/dev/null 2>&1; then
  fail "the runtime user can write /app/server.js"
else
  pass "the runtime user cannot write /app/server.js"
fi
if docker exec "${container}" "${node_bin}" -e "require('fs').writeFileSync('/app/.next/cache/.smoke', 'x')" >/dev/null 2>&1; then
  pass "the runtime user can write /app/.next/cache (tmpfs)"
else
  fail "the runtime user cannot write /app/.next/cache"
fi

# ── 6. User ─────────────────────────────────────────────────────────────────
config_user="$(docker image inspect -f '{{.Config.User}}' "${image_ref}")"
process_user="$(docker exec "${container}" "${node_bin}" -p "process.getuid() + ':' + process.getgid()" 2>/dev/null || echo unknown)"
if [[ "${config_user}" == "${expected_user}" && "${process_user}" == "${expected_user}" ]]; then
  pass "image user and process user are ${expected_user}"
else
  fail "image user '${config_user}', process user '${process_user}' (expected ${expected_user})"
fi

# ── 7. Node version ─────────────────────────────────────────────────────────
actual_node="$(docker exec "${container}" "${node_bin}" -p 'process.version' 2>/dev/null || echo unknown)"
if [[ "${actual_node}" == "v${expected_node}" ]]; then
  pass "runtime Node is ${actual_node}"
else
  fail "runtime Node is '${actual_node}' but pin_authority.node_runtime_version is v${expected_node}; re-resolve pin_authority.frontend_runtime_image"
fi

# ── 8. No writes outside the tmpfs ──────────────────────────────────────────
if docker logs "${container}" 2>&1 | grep -E 'EROFS|EACCES' >/dev/null; then
  fail "the server logged EROFS/EACCES: it writes outside /tmp and /app/.next/cache"
else
  pass "no EROFS/EACCES in the server logs"
fi

# ── Size evidence ───────────────────────────────────────────────────────────
size_bytes="$(docker image inspect -f '{{.Size}}' "${image_ref}")"
size_mb="$(awk -v b="${size_bytes}" 'BEGIN { printf "%.1f", b / 1048576 }')"
log "image size:     ${size_mb} MiB (${size_bytes} bytes, uncompressed)"
{
  echo "---- docker history ----"
  docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' "${image_ref}"
} >>"${log_file}"

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "### Frontend image smoke test"
    echo ""
    echo "- Image size: **${size_mb} MiB** (uncompressed)"
    echo "- Node: \`${actual_node}\`, user: \`${process_user}\`"
    echo "- Failures: **${failures}**"
    echo ""
    echo '```'
    grep -E '^(PASS|FAIL):' "${log_file}" || true
    echo '```'
  } >>"${GITHUB_STEP_SUMMARY}"
fi

if ((failures > 0)); then
  echo "::error::frontend image smoke test: ${failures} check(s) failed"
  exit 1
fi
log "frontend image smoke test: all checks passed"
