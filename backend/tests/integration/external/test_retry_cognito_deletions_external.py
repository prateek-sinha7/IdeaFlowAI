"""``app.scripts.retry_cognito_deletions`` — resolving queued pool deletions.

Phase 3 of the Cognito-only auth migration, Decision 6. Covers the script's
``main()`` end to end against ``FakeCognitoPool`` and a real SQLite session,
via monkeypatched ``SessionLocal``/``settings`` rather than the CLI's own
argv/exit-code plumbing — the exit code IS asserted (report vs. cannot-run
vs. partial-failure), but the DB/pool setup is test-native.

Lives in ``tests/integration/external/`` alongside the other Cognito-adapter suites: the
provider is stubbed by ``FakeCognitoPool`` while the QUEUE is real rows. Every assertion
is about what the batch did to ``pending_cognito_deletions`` — a resolved row removed, a
persistent failure's ``attempts`` incremented and left pending, a past-max row skipped,
and report mode writing NOTHING. Those are row-state claims a mocked Session cannot make.

The pure backoff-curve arithmetic (``min(2 * attempt, 300)``) needs no queue and stays in
``tests/unit/services/test_retry_cognito_deletions.py``.
"""
from __future__ import annotations

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.database import Base
from app.models.pending_cognito_deletion import PendingCognitoDeletion
from app.scripts import retry_cognito_deletions as script
from tests.fakes.cognito_pool import FakeCognitoPool


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(script, "SessionLocal", Session)
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", "pool-under-test")

    pool = FakeCognitoPool().install(monkeypatch)

    session = Session()
    try:
        yield {"session": session, "pool": pool, "Session": Session}
    finally:
        session.close()
        engine.dispose()


def _pending(session, *, cognito_sub: str, attempts: int = 0) -> PendingCognitoDeletion:
    row = PendingCognitoDeletion(
        user_id_snapshot=f"u-{cognito_sub}",
        cognito_sub=cognito_sub,
        email_hash="a" * 16,
        attempts=attempts,
    )
    session.add(row)
    session.commit()
    return row


class TestNoPoolConfigured:
    def test_exits_non_zero_when_pool_id_unset(self, env, monkeypatch):
        monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", "")

        assert script.main(["--report"]) == script.EXIT_CANNOT_RUN


class TestReportMode:
    def test_report_writes_nothing(self, env):
        _pending(env["session"], cognito_sub="sub-1")

        assert script.main(["--report"]) == script.EXIT_OK

        assert env["session"].query(PendingCognitoDeletion).count() == 1

    def test_report_with_nothing_pending_is_a_clean_no_op(self, env):
        assert script.main(["--report"]) == script.EXIT_OK


class TestApplyMode:
    def test_a_row_whose_pool_user_is_now_gone_resolves_and_is_removed(self, env):
        """UserNotFoundException on the retry is success (idempotent), same
        rule as core.cognito_admin._tolerate_missing."""
        _pending(env["session"], cognito_sub="already-deleted-sub")

        assert script.main(["--apply"]) == script.EXIT_OK

        assert env["session"].query(PendingCognitoDeletion).count() == 0

    def test_a_row_whose_pool_user_still_exists_is_deleted_and_resolved(self, env):
        env["pool"].add(sub="still-there", email="stuck@example.com")
        _pending(env["session"], cognito_sub="still-there")

        assert script.main(["--apply"]) == script.EXIT_OK

        assert env["session"].query(PendingCognitoDeletion).count() == 0
        assert "still-there" not in env["pool"]

    def test_a_persistent_failure_increments_attempts_and_stays_pending(
        self, env, monkeypatch
    ):
        from app.core import cognito

        def _boom(_username):
            raise ClientError(
                {"Error": {"Code": "InternalErrorException", "Message": "boom"}},
                "AdminDeleteUser",
            )

        monkeypatch.setattr(cognito, "admin_delete_user", _boom)
        row = _pending(env["session"], cognito_sub="stuck-sub")

        exit_code = script.main(["--apply"])

        assert exit_code == script.EXIT_CANNOT_RUN
        env["session"].refresh(row)
        assert row.attempts == 1
        assert row.last_error == "InternalErrorException"

    def test_a_row_past_max_attempts_is_not_retried(self, env, monkeypatch):
        from app.core import cognito

        calls = {"n": 0}

        def _spy(_username):
            calls["n"] += 1

        monkeypatch.setattr(cognito, "admin_delete_user", _spy)
        _pending(env["session"], cognito_sub="exhausted-sub", attempts=10)

        script.main(["--apply", "--max-attempts", "10"])

        assert calls["n"] == 0

    def test_mixed_batch_resolves_the_fixable_and_leaves_the_broken_one(
        self, env, monkeypatch
    ):
        from app.core import cognito

        real_delete = cognito.admin_delete_user

        def _selective(username):
            if username == "broken-sub":
                raise ClientError(
                    {"Error": {"Code": "InternalErrorException", "Message": "boom"}},
                    "AdminDeleteUser",
                )
            return real_delete(username)

        monkeypatch.setattr(cognito, "admin_delete_user", _selective)
        env["pool"].add(sub="fixable-sub", email="fixable@example.com")
        _pending(env["session"], cognito_sub="fixable-sub")
        _pending(env["session"], cognito_sub="broken-sub")

        exit_code = script.main(["--apply"])

        assert exit_code == script.EXIT_CANNOT_RUN
        remaining = env["session"].query(PendingCognitoDeletion).all()
        assert len(remaining) == 1
        assert remaining[0].cognito_sub == "broken-sub"

class TestBackoffIsNotPaidOnSuccess:
    """A fully successful batch must not sleep at all.

    The previous implementation slept after every row except the last,
    regardless of outcome, so draining N healthy rows cost the whole backoff
    ladder for no reason. Asserting ``time.sleep`` is never called is the only
    way to see that from the outside — the run's observable result is identical
    either way, just slower.
    """

    def test_all_successful_rows_never_sleep(self, env, monkeypatch):
        slept: list[int] = []
        monkeypatch.setattr(script.time, "sleep", lambda s: slept.append(s))

        # Three rows whose pool users are already absent. UserNotFoundException
        # counts as success (idempotent delete), so every row resolves and there
        # is no failure to back off from.
        for n in range(3):
            _pending(env["session"], cognito_sub=f"sub-missing-{n}")

        assert script.main(["--apply"]) == script.EXIT_OK
        assert slept == []
