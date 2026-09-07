#!/usr/bin/env bash
# Prove the characterization goldens are byte-identical after the test run.
#
# Two independent checks, because they catch different mistakes:
#   1. the recorded digests still match  -> a test rewrote a golden in place
#   2. `git diff --exit-code` is clean   -> a golden was added or deleted
#
# Usage: ci-golden-verify.sh <digest-file-from-ci-golden-digest.sh>
set -euo pipefail

before="${1:?usage: ci-golden-verify.sh <digest-file>}"
golden_dir="backend/tests/agents/characterization/golden"

if [[ ! -f "${before}" ]]; then
  echo "::error::pre-run golden digest ${before} is missing; cannot prove INV-3."
  exit 1
fi

if [[ -n "${SNAPSHOT_UPDATE:-}" ]]; then
  echo "::error::SNAPSHOT_UPDATE is set to '${SNAPSHOT_UPDATE}'. Golden"
  echo "::error::regeneration must never happen inside a mandatory gate."
  exit 1
fi

if ! sha256sum --check --quiet --status "${before}"; then
  echo "::error::A characterization golden changed during the test run (INV-3)."
  sha256sum --check "${before}" 2>&1 | grep -v ': OK$' || true
  exit 1
fi

if ! git diff --exit-code --quiet -- "${golden_dir}"; then
  echo "::error::The golden tree has uncommitted changes after the run (INV-3)."
  git --no-pager diff --stat -- "${golden_dir}"
  exit 1
fi

if [[ -n "$(git status --porcelain -- "${golden_dir}")" ]]; then
  echo "::error::The golden tree has untracked or removed files after the run."
  git status --porcelain -- "${golden_dir}"
  exit 1
fi

echo "Characterization goldens are byte-identical."
