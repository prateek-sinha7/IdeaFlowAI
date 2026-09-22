"""``verify_cognito_cutover.py``'s new schema checks actually detect what they claim.

Phase 2 of the Cognito-only auth migration adds three checks to the cutover gate
(C2 schema, C3 Alembic head, C6 tier-group round-trip). A verification script is
the one kind of code where "it ran and printed PASS" proves the least: a check
that silently cannot fail is worse than no check, because it converts an unknown
into a false assurance. So each new check is exercised against a schema/state
that SHOULD trip it.

These run against SQLite. That is adequate here and not a stand-in for
PostgreSQL: what is under test is SQLAlchemy reflection of column presence and
nullability plus the contents of ``alembic_version`` — dialect-independent
properties. The checks' real subject (has migration 0038 been applied to THIS
database) is asserted in production by running the script itself.
``test_reflection_is_dialect_independent_enough_for_these_checks`` pins that
justification rather than leaving it as prose.

Lives in ``tests/integration/db/`` (moved from ``tests/unit/api/``): the checks build
a real SQLAlchemy engine and reflect a real schema, and the unit-isolation guard in
``tests/unit/conftest.py`` refuses EVERY DBAPI connection — in-memory SQLite included —
directing such tests to the integration suite. Mocking the Session is not an option
here because SQLAlchemy reflection IS the mechanism under test. This folder is the
right mirror rather than ``integration/api/``: the subject is
``scripts/verify_cognito_cutover.py``'s schema/``alembic_version`` checks, which sits
alongside ``test_alembic.py`` / ``test_migrations.py`` / ``test_migration_0038_preflight.py``
(0038 being the very migration these checks gate on), not an API router.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.user import User


def _load_verifier():
    """Import the script by path — ``backend/scripts/`` is not a package.

    It is not importable as ``scripts.verify_cognito_cutover`` either, and it
    deliberately does not ship in the runtime image (only ``app/`` does), so a
    normal import is not available. Loading by spec is what lets the check
    FUNCTIONS be tested without invoking ``main()`` and its ``os.chdir``.
    """
    path = Path(__file__).resolve().parents[3] / "scripts" / "verify_cognito_cutover.py"
    spec = importlib.util.spec_from_file_location("_verify_cognito_cutover", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


#: The CURRENT schema is created from the ORM model itself rather than
#: hand-written DDL. Hand-writing it means maintaining a second, silently
#: divergent copy of the users table: the first attempt at this file omitted
#: `password_changed_at`, `preferred_model`, `tokens_valid_from`,
#: `roles_synced_at`, `mfa_verified_at` and
#: `encrypted_cognito_refresh_token`, so C1's ORM query blew up on a "current"
#: schema that was nothing of the sort.
CURRENT = "orm"

#: The pre-0038 shape: local-credential columns present, `cognito_sub` NULLABLE,
#: no `status`. Written out in full because it describes a schema the ORM can no
#: longer generate — that is the whole point of it. Every post-0038 column the
#: model still has IS included, so the only differences from CURRENT are the
#: three 0038 changes; otherwise a failure could not be attributed to them.
PRE_0038 = """
CREATE TABLE users (
    id VARCHAR NOT NULL PRIMARY KEY,
    email VARCHAR NOT NULL UNIQUE,
    password_hash VARCHAR,
    auth_provider VARCHAR NOT NULL DEFAULT 'local',
    password_changed_at TIMESTAMP,
    tier VARCHAR NOT NULL DEFAULT 'basic',
    is_admin BOOLEAN NOT NULL DEFAULT 0,
    preferred_model VARCHAR,
    cognito_sub VARCHAR,
    tokens_valid_from TIMESTAMP,
    roles_synced_at TIMESTAMP,
    mfa_verified_at TIMESTAMP,
    encrypted_cognito_refresh_token TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def _db(users_ddl: str, *, stamped: list[str]):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    if users_ddl == CURRENT:
        User.__table__.create(engine)
    else:
        with engine.begin() as conn:
            conn.execute(text(users_ddl))
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR PRIMARY KEY)")
        )
        for revision in stamped:
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": revision},
            )
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _run(users_ddl: str, *, stamped: list[str]):
    """Run ``_check_db`` and return ``(report, outcomes_by_check_prefix)``."""
    engine, session = _db(users_ddl, stamped=stamped)
    report = verifier.Report()
    recorded: dict[str, str] = {}

    def capture(status, check, detail):
        recorded[check.split()[0]] = status
        if status == verifier._FAIL:
            report.failed = True

    report.record = capture  # type: ignore[method-assign]
    try:
        verifier._check_db(session, report)
    finally:
        session.close()
        engine.dispose()
    return report, recorded


class TestOnACurrentSchema:
    def test_every_check_passes(self):
        report, recorded = _run(
            CURRENT, stamped=[verifier.EXPECTED_ALEMBIC_HEAD]
        )

        assert not report.failed, recorded
        assert set(recorded) >= {"C1", "C2", "C2b", "C2c", "C3", "C6"}
        assert all(status == verifier._PASS for status in recorded.values()), recorded


class TestC2DetectsAnUnmigratedSchema:
    def test_residual_local_credential_columns_fail(self):
        _report, recorded = _run(PRE_0038, stamped=["0037"])

        assert recorded["C2"] == verifier._FAIL

    def test_a_nullable_cognito_sub_fails(self):
        _report, recorded = _run(PRE_0038, stamped=["0037"])

        assert recorded["C2b"] == verifier._FAIL

    def test_a_missing_status_column_fails(self):
        _report, recorded = _run(PRE_0038, stamped=["0037"])

        assert recorded["C2c"] == verifier._FAIL

    def test_c1_is_skipped_rather_than_raising_on_an_unmigrated_schema(self):
        """The ordering guarantee, which this test is the reason for.

        C1 queries through the ORM, whose model carries post-0038 columns. On an
        unmigrated table that SELECT raises ``OperationalError: no such column:
        users.status`` — so before the schema checks were moved ahead of it, the
        operator got a stack trace and "ERROR during verification" instead of
        C2's actionable "migration 0038 has NOT been applied". The unmigrated
        database is the case this script exists to diagnose, so it must not be
        the case that crashes it.
        """
        _report, recorded = _run(PRE_0038, stamped=["0037"])

        assert recorded["C1"] == verifier._SKIP
        assert recorded["C2"] == verifier._FAIL


class TestC3AlembicHead:
    def test_a_stale_head_fails(self):
        _report, recorded = _run(CURRENT, stamped=["0037"])

        assert recorded["C3"] == verifier._FAIL

    def test_two_heads_fail(self):
        """Two stamped revisions make `alembic upgrade head` fail, which
        crash-loops the container — the exact condition the project has already
        hit twice (0031 and 0032 both had to be re-homed)."""
        _report, recorded = _run(
            CURRENT, stamped=[verifier.EXPECTED_ALEMBIC_HEAD, "0039"]
        )

        assert recorded["C3"] == verifier._FAIL

    def test_no_stamped_revision_fails(self):
        _report, recorded = _run(CURRENT, stamped=[])

        assert recorded["C3"] == verifier._FAIL


class TestC6TierGroupRoundTrip:
    def test_it_passes_against_the_real_catalog(self):
        """Guards the live entitlement table, not a fixture: every tier in
        TIER_PIPELINES must have a Cognito group that resolves back to it."""
        _report, recorded = _run(
            CURRENT, stamped=[verifier.EXPECTED_ALEMBIC_HEAD]
        )

        assert recorded["C6"] == verifier._PASS

    def test_it_fails_when_a_tier_has_no_group(self, monkeypatch):
        """Proves C6 can actually fail. Adds a tier to the catalog WITHOUT a
        group — the exact shape `hexaware` was in before Phase 2."""
        from app.core import entitlements

        monkeypatch.setitem(entitlements.TIER_PIPELINES, "ungrouped-tier", set())

        _report, recorded = _run(
            CURRENT, stamped=[verifier.EXPECTED_ALEMBIC_HEAD]
        )

        assert recorded["C6"] == verifier._FAIL


class TestExpectedHeadIsCurrent:
    def test_the_expected_head_matches_the_newest_migration_on_disk(self):
        """A guard against the constant going stale.

        ``EXPECTED_ALEMBIC_HEAD`` is deliberately a literal so the DATABASE check
        is not tautological — but that means adding a migration and forgetting to
        bump it turns C3 into a false alarm on every environment. This test
        compares it against the filenames, which is the one place that comparison
        is legitimate: here the checkout IS the subject.
        """
        versions = Path(__file__).resolve().parents[3] / "alembic" / "versions"
        revisions = sorted(
            p.name.split("_", 1)[0]
            for p in versions.glob("[0-9][0-9][0-9][0-9]_*.py")
        )

        assert revisions, "no migrations found — wrong path?"
        assert verifier.EXPECTED_ALEMBIC_HEAD == revisions[-1], (
            "verify_cognito_cutover.EXPECTED_ALEMBIC_HEAD is stale; bump it when "
            "adding a migration."
        )


def test_reflection_is_dialect_independent_enough_for_these_checks():
    """Sanity-pin on the mechanism the C2 checks rely on: SQLAlchemy reports
    column presence and nullability the same way whatever the dialect."""
    engine, session = _db(CURRENT, stamped=["0040"])
    try:
        columns = {c["name"]: c for c in sa.inspect(engine).get_columns("users")}
        assert columns["cognito_sub"]["nullable"] is False
        assert "password_hash" not in columns
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
