#!/usr/bin/env bash
# Validate the compose files shipped to hosts with `docker compose config`.
#
# F-19: docker-compose.yml and docker-compose.prod.yml are copied to every host
# and run there with `docker compose up`, but nothing in CI ever parsed them. A
# typo, a bad merge between the base and the prod overlay, or a new `${VAR}`
# with no default only surfaced on the host, mid-deploy.
#
# Two stacks are validated, because that is what the hosts run:
#   1. docker-compose.yml alone (local builds and the base stack);
#   2. docker-compose.yml + docker-compose.prod.yml (every deployed host).
#
# Interpolation uses ci/compose-ci.env, which holds PLACEHOLDER values only for
# the variables the files reference without a default. Compose treats an unset
# variable as a WARNING ("The \"X\" variable is not set. Defaulting to a blank
# string.") and still exits 0, so this script fails on that line too: a new
# un-defaulted variable must be added to ci/compose-ci.env (and to the host's
# app.env) in a reviewed change, not discovered at deploy time.
#
# Both stacks are always validated, then the script fails if either did.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

env_file="ci/compose-ci.env"
if [[ ! -f "${env_file}" ]]; then
  echo "::error::${env_file} is missing; compose interpolation cannot be checked"
  exit 1
fi

docker compose version

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT

failed=0

# validate <label> <compose -f arguments...>
validate() {
  local label="$1"
  shift
  local status=0

  echo "Validating ${label}"
  docker compose --env-file "${env_file}" "$@" config --quiet 2>"${tmp}" || status=$?

  if [[ -s "${tmp}" ]]; then
    cat "${tmp}"
  fi

  if ((status != 0)); then
    echo "::error::docker compose config failed for ${label} (exit ${status})"
    failed=1
    return 0
  fi

  if grep -q 'variable is not set' "${tmp}"; then
    echo "::error::${label} references a variable with no default that ${env_file} does not define"
    failed=1
    return 0
  fi

  echo "${label}: valid"
}

base_args=(-f docker-compose.yml)
prod_args=(-f docker-compose.yml -f docker-compose.prod.yml)

validate "docker-compose.yml" "${base_args[@]}"
validate "docker-compose.yml + docker-compose.prod.yml" "${prod_args[@]}"

exit "${failed}"
