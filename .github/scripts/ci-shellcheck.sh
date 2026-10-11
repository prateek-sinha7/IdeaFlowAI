#!/usr/bin/env bash
# Blocking ShellCheck analysis over every tracked shell script.
#
# Warning severity is BLOCKING. The previous pipeline ran this with `|| true`
# and `continue-on-error: true`, which made the signal decorative. If a finding
# is genuinely not applicable, silence it at the line with a justified
# `# shellcheck disable=SCxxxx` comment so the exception is reviewable, rather
# than disabling the whole command.
#
# NO `--shell=bash`. That flag OVERRIDES each script's own shebang, so a
# `#!/bin/sh` script was being analysed under bash rules: bashisms it must not
# contain were accepted silently, and POSIX-only portability warnings were never
# raised. Several scripts here are delivered to a host via SSM and have to stay
# POSIX-sh compatible on their first executable line, so that is exactly the
# class of bug this check exists to catch. Let the shebang decide the dialect.
#
# PINNED BINARY. CI installs ShellCheck through .github/actions/install-checksummed-tool
# at the version in ci.yml's SHELLCHECK_VERSION (sha256-verified) and passes it here
# as SHELLCHECK_EXPECTED_VERSION. This script records the version it actually runs
# and fails if that differs, so a runner-image bump can never change which rules
# apply without a reviewed edit. Under GITHUB_ACTIONS the variable is mandatory, so
# CI cannot silently fall back to whichever copy is on PATH. Locally, with neither
# set, the version is only printed.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

shellcheck --version
installed_version="$(shellcheck --version | sed -n 's/^version: //p')"
if [[ -n "${SHELLCHECK_EXPECTED_VERSION:-}" ]]; then
  expected_version="${SHELLCHECK_EXPECTED_VERSION#v}"
  if [[ "${installed_version}" != "${expected_version}" ]]; then
    echo "::error::ShellCheck ${installed_version} is installed but ${expected_version} is pinned (SHELLCHECK_EXPECTED_VERSION=${SHELLCHECK_EXPECTED_VERSION})."
    exit 1
  fi
elif [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
  echo "::error::SHELLCHECK_EXPECTED_VERSION is not set; CI must run the pinned ShellCheck, not whichever is on PATH."
  exit 1
fi

mapfile -d '' -t scripts < <(git ls-files -z '*.sh')

if ((${#scripts[@]} == 0)); then
  echo "::error::no tracked shell scripts found; the scope is wrong"
  exit 1
fi

echo "Analysing ${#scripts[@]} shell script(s) at warning severity."
shellcheck --severity=warning --external-sources "${scripts[@]}"
echo "ShellCheck found no problems at warning severity or above."
