#!/usr/bin/env bash
# scripts/local-dev/install-prereqs.sh
#
# Checks (and, where a package manager can do it safely, installs) the
# system-level prerequisites needed to run Flowin locally:
#   - Python 3.13+   (backend/pyproject.toml requires-python >=3.13.0)
#   - Node.js 24.x   (frontend/package.json engines.node >=24.0.0 <25.0.0)
#   - git
#
# These are the versions CI and the Docker images use. Older ones (Python 3.12,
# EOL Node 20) are rejected by the project, so this script no longer installs them.
#
# It never pipes a downloaded script into a shell, and never runs `sudo bash` on
# remote content. macOS: installs through an existing Homebrew. Linux: installs
# git through apt; for Python and Node it prints install instructions and stops,
# because the usual one-line installers are remote scripts run as root.
#
# This script does NOT install AWS credentials/SSO config — Bedrock auth
# still needs to be set up separately (see README.txt).
#
# Usage:
#   scripts/local-dev/install-prereqs.sh

set -euo pipefail

log() { echo "==> $*"; }

REQUIRED_PY_MINOR=13
REQUIRED_NODE_MAJOR=24

OS="$(uname -s)"
MISSING=()

# python3.13+ on PATH (python3.13 or a python3 that is already >= 3.13).
have_python() {
  if command -v python3.13 >/dev/null 2>&1; then
    return 0
  fi
  command -v python3 >/dev/null 2>&1 \
    && python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, ${REQUIRED_PY_MINOR}) else 1)" 2>/dev/null
}

# Node exactly on the required major (engines.node rejects 25+ as well as <24).
have_node() {
  command -v node >/dev/null 2>&1 \
    && [[ "$(node --version | sed 's/^v//' | cut -d. -f1)" -eq "$REQUIRED_NODE_MAJOR" ]]
}

case "$OS" in
  Darwin)
    if ! command -v brew >/dev/null 2>&1; then
      echo "ERROR: Homebrew not found. Install it from https://brew.sh (review the installer" >&2
      echo "before running it), then re-run this script." >&2
      exit 1
    fi

    log "Updating Homebrew..."
    brew update

    if ! have_python; then
      log "Installing Python 3.${REQUIRED_PY_MINOR}..."
      brew install "python@3.${REQUIRED_PY_MINOR}"
    else
      log "Python 3.${REQUIRED_PY_MINOR}+ already present."
    fi

    if ! have_node; then
      log "Installing Node.js ${REQUIRED_NODE_MAJOR}..."
      brew install "node@${REQUIRED_NODE_MAJOR}"
      brew link --overwrite --force "node@${REQUIRED_NODE_MAJOR}"
    else
      log "Node.js ${REQUIRED_NODE_MAJOR}.x already present."
    fi

    if ! command -v git >/dev/null 2>&1; then
      log "Installing git..."
      brew install git
    else
      log "git already present."
    fi
    ;;

  Linux)
    if ! have_python; then
      MISSING+=("Python 3.${REQUIRED_PY_MINOR}+: install it with your distro, or run 'uv python install 3.${REQUIRED_PY_MINOR}' (https://docs.astral.sh/uv/)")
    else
      log "Python 3.${REQUIRED_PY_MINOR}+ already present."
    fi

    if ! have_node; then
      MISSING+=("Node.js ${REQUIRED_NODE_MAJOR}.x: install it with nvm or fnm ('nvm install ${REQUIRED_NODE_MAJOR}'), or from https://nodejs.org/en/download")
    else
      log "Node.js ${REQUIRED_NODE_MAJOR}.x already present."
    fi

    if ! command -v git >/dev/null 2>&1; then
      if command -v apt-get >/dev/null 2>&1; then
        log "Installing git..."
        sudo apt-get update -y
        sudo apt-get install -y git
      else
        MISSING+=("git: install it with your distro's package manager")
      fi
    else
      log "git already present."
    fi

    if [[ "${#MISSING[@]}" -gt 0 ]]; then
      echo "ERROR: missing prerequisites. Install them, then re-run this script:" >&2
      printf '  - %s\n' "${MISSING[@]}" >&2
      exit 1
    fi
    ;;

  *)
    echo "ERROR: unsupported OS '$OS'. Install Python 3.${REQUIRED_PY_MINOR}+, Node.js ${REQUIRED_NODE_MAJOR}.x, and git manually." >&2
    exit 1
    ;;
esac

log "Prerequisite check complete."
python3 --version || python3.13 --version
node --version
git --version
