#!/usr/bin/env bash
# Require a reachable, genuine PostgreSQL service and create the two disposable
# databases the mandatory partition uses.
#
# An unavailable service is a FAILED gate. It is never a skip and never a
# fallback to another engine: the whole point of this partition is to prove the
# repository's real migration, sequencing and concurrency contracts against
# PostgreSQL (Requirement 2.12).
#
# Inputs (environment): PGPASSWORD
set -euo pipefail

host="${POSTGRES_HOST:-localhost}"
port="${POSTGRES_PORT:-5432}"
user="${POSTGRES_USER:-ci_test}"
admin_db="${POSTGRES_DB:-ci_test_db}"
readiness_timeout_seconds="${POSTGRES_READINESS_TIMEOUT:-120}"

deadline=$((SECONDS + readiness_timeout_seconds))
until pg_isready --host="${host}" --port="${port}" --username="${user}" >/dev/null 2>&1; do
  if ((SECONDS >= deadline)); then
    echo "::error::PostgreSQL at ${host}:${port} was not ready within"
    echo "::error::${readiness_timeout_seconds}s. This is a failed mandatory gate."
    exit 1
  fi
  sleep 2
done
echo "PostgreSQL is accepting connections."

# Confirm it really is PostgreSQL before trusting the partition's evidence.
server_version="$(psql --host="${host}" --port="${port}" --username="${user}" \
  --dbname="${admin_db}" --tuples-only --no-align --command 'SHOW server_version;')"
echo "Server version: ${server_version}"
case "${server_version}" in
  16.*) ;;
  *)
    echo "::error::Expected PostgreSQL 16.x, got '${server_version}'."
    echo "::error::The migration contracts are validated against the production major only."
    exit 1
    ;;
esac

# Separate disposable databases keep the populated-migration fixtures from
# colliding with the ordinary contract tests.
for db in ci_test_ordinary ci_test_populated_migration; do
  psql --host="${host}" --port="${port}" --username="${user}" --dbname="${admin_db}" \
    --command "DROP DATABASE IF EXISTS ${db};"
  psql --host="${host}" --port="${port}" --username="${user}" --dbname="${admin_db}" \
    --command "CREATE DATABASE ${db};"
  echo "Created disposable database ${db}."
done
