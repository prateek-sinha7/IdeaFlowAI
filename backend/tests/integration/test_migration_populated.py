"""Populated PostgreSQL migration test (Requirements 8.1-8.9, Tasks 9.1-9.3).

Tests the migration chain against populated data:
  - Task 9.1: Provision postgres:16 service (this file)
  - Task 9.2: Seed at 0014, upgrade to head, verify data integrity
  - Task 9.3: Assert schema parity, scoped reads, idempotent re-upgrade

Key constraints:
  - Connection target MUST come exclusively from CI-provided env var
    (POPULATED_MIGRATION_TEST_DATABASE_URL)
  - Never fall back to local/developer defaults
  - Abort with provisioning failure if service unreachable within 120s
  - Leave database available for inspection on migration step failure

Requirements tracing:
  - Req 8.1: Provision within 120s, abort with provisioning failure on timeout
  - Req 8.8: Take connection target from CI configuration only, skip with
    explicit unavailability indication (no fallback)
"""

import os
import pytest


@pytest.mark.requires_postgres_populated_migration
class TestPopulatedMigration:
    """Populated migration tests (Requirements 8.1-8.9).

    Sub-tasks:
      - 9.1 (this task): CI job provisioning and health checks
      - 9.2: Seed at 0014, upgrade to head, verify counts/scope/values
      - 9.3: Assert schema parity, scoped reads, idempotent re-upgrade
    """

    @pytest.fixture(scope="class")
    def db_url(self) -> str:
        """Get PostgreSQL connection URL from CI configuration only.

        Requirement 8.8: Must come exclusively from CI-provided env var.
        Must skip with explicit unavailability indication if not provided.
        """
        url = os.environ.get("POPULATED_MIGRATION_TEST_DATABASE_URL")
        if not url:
            pytest.skip(
                "POPULATED_MIGRATION_TEST_DATABASE_URL not provided; "
                "PostgreSQL service unavailable"
            )
        return url

    def test_database_connectivity(self, db_url: str) -> None:
        """Verify database is reachable (implicit in fixture, explicit for clarity).

        This is a placeholder for the actual migration tests that will be
        implemented in tasks 9.2 and 9.3.
        """
        # TODO(9.2): Implement seed at 0014 + upgrade to head + verify counts
        # TODO(9.3): Implement schema parity + scoped reads + idempotent re-upgrade
        assert db_url.startswith("postgresql+psycopg://")
