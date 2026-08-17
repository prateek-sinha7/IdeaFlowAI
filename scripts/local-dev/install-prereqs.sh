#!/usr/bin/env bash
# scripts/local-dev/install-prereqs.sh
#
# Installs the system-level prerequisites needed to run Flowin locally:
#   - Python 3.12+
#   - Node.js 20+ (npm comes with it)
#   - git
#
# macOS: uses Homebrew (installs Homebrew itself if missing).
# Linux: uses apt-get (Debian/Ubuntu). Other distros: install manually.
#
# This script does NOT install AWS credentials/SSO config — Bedrock auth
# still needs to be set up separately (see README.txt).
#
# Usage:
#   scripts/local-dev/install-prereqs.sh

set -euo pipefail

log() { echo "==> $*"; }

OS="$(uname -s)"

case "$OS" in
  Darwin)
    if ! command -v brew >/dev/null 2>&1; then
      log "Homebrew not found. Installing Homebrew..."
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi

    log "Updating Homebrew..."
    brew update

    if ! command -v python3.12 >/dev/null 2>&1 && ! python3 --version 2>/dev/null | grep -qE '3\.(1[2-9]|[2-9][0-9])'; then
      log "Installing Python 3.12..."
      brew install python@3.12
    else
      log "Python 3.12+ already present."
    fi

    if ! command -v node >/dev/null 2>&1 || [[ "$(node --version | sed 's/^v//' | cut -d. -f1)" -lt 20 ]]; then
      log "Installing Node.js 20+..."
      brew install node@20
      brew link --overwrite --force node@20
    else
      log "Node.js 20+ already present."
    fi

    if ! command -v git >/dev/null 2>&1; then
      log "Installing git..."
      brew install git
    else
      log "git already present."
    fi
    ;;

  Linux)
    if ! command -v apt-get >/dev/null 2>&1; then
      echo "ERROR: this script only automates apt-based Linux (Debian/Ubuntu)." >&2
      echo "Install Python 3.12+, Node.js 20+, and git manually for your distro." >&2
      exit 1
    fi

    log "Updating apt package lists..."
    sudo apt-get update -y

    if ! command -v python3.12 >/dev/null 2>&1; then
      log "Installing Python 3.12..."
      sudo apt-get install -y software-properties-common
      sudo add-apt-repository -y ppa:deadsnakes/ppa
      sudo apt-get update -y
      sudo apt-get install -y python3.12 python3.12-venv python3-pip
    else
      log "Python 3.12+ already present."
    fi

    if ! command -v node >/dev/null 2>&1 || [[ "$(node --version | sed 's/^v//' | cut -d. -f1)" -lt 20 ]]; then
      log "Installing Node.js 20+..."
      curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
      sudo apt-get install -y nodejs
    else
      log "Node.js 20+ already present."
    fi

    if ! command -v git >/dev/null 2>&1; then
      log "Installing git..."
      sudo apt-get install -y git
    else
      log "git already present."
    fi
    ;;

  *)
    echo "ERROR: unsupported OS '$OS'. Install Python 3.12+, Node.js 20+, and git manually." >&2
    exit 1
    ;;
esac

log "Prerequisite check complete."
python3 --version || python3.12 --version
node --version
git --version
