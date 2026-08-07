"""tests/unit/test_login_timing_and_pii.py — two P2 fixes from
COGNITO-AUTH-QA-BUGS.md:

1. "Login Timing Enumeration": an unknown email must pay the same cost class
   as a known one before ``POST /api/auth/login`` returns 401, closing the
   timing oracle that let an attacker distinguish "no such account" from
   "wrong password" by response latency.
2. "Authentication PII in Logs": ``core.auth_events.emit(email=...)`` must
   never write the plaintext address into the log line — only a stable,
   non-reversible hash.

Local-auth path only (no live AWS calls) — mirrors ``test_logout.py``'s
in-memory-SQLite + real ``TestClient`` harness for the login endpoint, plus a
direct unit test of ``auth_events.emit`` for the PII fix (no HTTP needed).
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import router as auth_router
from app.core import auth_events
from app.core.auth_events import AuthEvent
from app.core.security import hash_password
from app.models.database import Base, get_db
from app.models.revoked_token import RevokedToken  # noqa: F401
from app.models.user import User
from app.models.chat import ChatSession, Message  # noqa: F401
from app.models.workflow import WorkflowRun  # noqa: F401


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        test_client.app = app  # for the db-seeding helper below
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _seed_user(client, email="alice@example.com", password="password123") -> User:
    db = next(client.app.dependency_overrides[get_db]())
    try:
        u = User(
            id="u-1",
            email=email,
            password_hash=hash_password(password),
            auth_provider="local",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


class TestLoginTimingEnumeration:
    def test_unknown_email_still_401s(self, client):
        """The fix must not change the OUTCOME — still a generic 401."""
        resp = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "whatever"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    def test_unknown_email_pays_comparable_latency_to_known_email_wrong_password(
        self, client
    ):
        """The timing gap between an unknown email and a known email with a
        wrong password must be small relative to the bcrypt cost each pays —
        proving the unknown-email path now does real work instead of
        returning immediately off a bare DB miss.

        Not a strict equality (system jitter), but the unknown-email path
        must be within the same order of magnitude as the known-email path,
        not orders of magnitude faster as it was pre-fix (a bare indexed
        DB-miss lookup vs. a full bcrypt verify).
        """
        _seed_user(client, email="known@example.com", password="password123")

        def _timed_login(email: str) -> float:
            start = time.perf_counter()
            resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": "definitely-wrong"},
            )
            elapsed = time.perf_counter() - start
            assert resp.status_code == 401
            return elapsed

        # Warm up (first bcrypt call sometimes pays a one-time cost).
        _timed_login("known@example.com")

        known_times = [_timed_login("known@example.com") for _ in range(3)]
        unknown_times = [
            _timed_login("nobody-at-all@example.com") for _ in range(3)
        ]

        known_avg = sum(known_times) / len(known_times)
        unknown_avg = sum(unknown_times) / len(unknown_times)

        # Pre-fix, the unknown-email path was ~2 orders of magnitude faster
        # (a bare indexed miss vs. a bcrypt verify). Post-fix it should be
        # within a generous 5x envelope of the known-email path — loose
        # enough to avoid CI flakiness, tight enough to catch a regression
        # back to the "return immediately" shape.
        assert unknown_avg >= known_avg / 5, (
            f"unknown-email login ({unknown_avg:.4f}s) is implausibly faster "
            f"than a known-email wrong-password attempt ({known_avg:.4f}s) — "
            "the timing-enumeration fix may have regressed"
        )


class TestAuthEventPiiRedaction:
    def test_emit_never_writes_plaintext_email(self, caplog):
        """core.auth_events.emit(email=...) must hash the address before it
        reaches the log line — never the raw value."""
        plaintext_email = "attacker-target@example.com"
        with caplog.at_level("WARNING", logger="app.auth.events"):
            auth_events.emit(
                AuthEvent.LOGIN_FAILURE, email=plaintext_email, reason="unknown_user"
            )
        assert len(caplog.records) == 1
        message = caplog.records[0].message
        assert plaintext_email not in message
        assert "email_hash" in message

    def test_hash_is_stable_for_the_same_email(self, caplog):
        """The SAME email must hash to the SAME value across calls, so
        repeated-attempt aggregation/alerting still works post-redaction."""
        import json

        email = "repeat-offender@example.com"
        with caplog.at_level("WARNING", logger="app.auth.events"):
            auth_events.emit(AuthEvent.LOGIN_FAILURE, email=email, reason="unknown_user")
            auth_events.emit(AuthEvent.LOGIN_FAILURE, email=email, reason="unknown_user")
        hashes = [json.loads(r.message)["email_hash"] for r in caplog.records]
        assert hashes[0] == hashes[1]

    def test_hash_differs_for_different_emails(self, caplog):
        import json

        with caplog.at_level("WARNING", logger="app.auth.events"):
            auth_events.emit(AuthEvent.LOGIN_FAILURE, email="a@example.com", reason="unknown_user")
            auth_events.emit(AuthEvent.LOGIN_FAILURE, email="b@example.com", reason="unknown_user")
        hashes = [json.loads(r.message)["email_hash"] for r in caplog.records]
        assert hashes[0] != hashes[1]
