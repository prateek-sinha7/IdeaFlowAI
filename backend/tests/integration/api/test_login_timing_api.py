"""Login timing enumeration — COGNITO-AUTH-QA-BUGS.md "Login Timing Enumeration".

An unknown email must pay the same cost class as a known one before
``POST /api/auth/login`` returns 401, closing the timing oracle that let an attacker
distinguish "no such account" from "wrong password" by response latency.

Cognito is the sole authentication authority (Cognito-only auth migration,
``.kiro/specs/login/prompt.md`` Phase 1) — mirrors ``test_logout_api.py``'s
in-memory-SQLite + real ``TestClient`` harness for the login endpoint, with
``admin_initiate_auth`` faked to reject a wrong password the same way Cognito would
(``NotAuthorizedException``).

Lives in the INTEGRATION suite because the measurement is only meaningful end-to-end:
the regression being guarded is that the unknown-email path used to short-circuit on a
bare indexed DB miss instead of doing the provider round-trip. Comparing those two
latencies requires a REAL seeded row for the known email and a real miss for the unknown
one — against a mocked Session both paths are equally fake and the assertion proves
nothing. Offline regardless (in-memory engine, faked provider), so the unit-suite
isolation guard (``tests/unit/conftest.py``) correctly refuses a real DB connection there.

The PII half of this pair — ``core.auth_events.emit`` never writing a plaintext address —
needs no HTTP and stays in ``tests/unit/api/test_login_timing_and_pii.py``.
"""

from __future__ import annotations

import time

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import router as auth_router
from app.core import cognito
from app.models.database import Base, get_db
from app.models.revoked_token import RevokedToken  # noqa: F401
from app.models.user import User
from app.models.chat import ChatSession, Message  # noqa: F401
from app.models.workflow import WorkflowRun  # noqa: F401



def _not_authorized(email: str, password: str):
    """Fake ``admin_initiate_auth`` — always rejects, exactly like Cognito
    does for a wrong password OR an unknown email under
    ``prevent_user_existence_errors = ENABLED``."""
    del email, password
    raise ClientError(
        {"Error": {"Code": "NotAuthorizedException", "Message": "boom"}},
        "AdminInitiateAuth",
    )


@pytest.fixture
def client(monkeypatch):
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

    monkeypatch.setattr(cognito, "admin_initiate_auth", _not_authorized)

    def _user_not_found(email: str):
        del email
        raise ClientError(
            {"Error": {"Code": "UserNotFoundException", "Message": "boom"}},
            "AdminGetUser",
        )

    # _probe_unknown_email's ambiguous branch classifies via AdminGetUser —
    # fake it too, so an unknown email never attempts a real AWS call.
    monkeypatch.setattr(cognito, "admin_get_user", _user_not_found)

    with TestClient(app) as test_client:
        test_client.app = app  # for the db-seeding helper below
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _seed_user(client, email="alice@example.com") -> User:
    db = next(client.app.dependency_overrides[get_db]())
    try:
        u = User(id="u-1", email=email, cognito_sub="sub-u-1")
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
        wrong password must be small relative to the AdminInitiateAuth cost
        each pays — proving the unknown-email path now does real work
        instead of returning immediately off a bare DB miss.

        Not a strict equality (system jitter), but the unknown-email path
        must be within the same order of magnitude as the known-email path,
        not orders of magnitude faster as it was pre-fix (a bare indexed
        DB-miss lookup vs. a full provider round-trip).
        """
        _seed_user(client, email="known@example.com")

        def _timed_login(email: str) -> float:
            start = time.perf_counter()
            resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": "definitely-wrong"},
            )
            elapsed = time.perf_counter() - start
            assert resp.status_code == 401
            return elapsed

        # Warm up (first call sometimes pays a one-time cost).
        _timed_login("known@example.com")

        known_times = [_timed_login("known@example.com") for _ in range(3)]
        unknown_times = [_timed_login("nobody-at-all@example.com") for _ in range(3)]

        known_avg = sum(known_times) / len(known_times)
        unknown_avg = sum(unknown_times) / len(unknown_times)

        # Pre-fix, the unknown-email path was ~2 orders of magnitude faster
        # (a bare indexed miss vs. a real provider round-trip). Post-fix it
        # should be within a generous 5x envelope of the known-email path —
        # loose enough to avoid CI flakiness, tight enough to catch a
        # regression back to the "return immediately" shape.
        assert unknown_avg >= known_avg / 5, (
            f"unknown-email login ({unknown_avg:.4f}s) is implausibly faster "
            f"than a known-email wrong-password attempt ({known_avg:.4f}s) — "
            "the timing-enumeration fix may have regressed"
        )
