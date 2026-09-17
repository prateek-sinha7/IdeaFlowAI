"""An established SSE stream re-runs the FULL verifier, not a subset of it.

Phase 2 of the Cognito-only auth migration: *"SSE (``run_stream.py``) periodic
check: re-run the full verifier (signature + ``exp``) like ``/ws/handoff``."*

The pre-existing periodic check (the P1 fix for COGNITO-AUTH-QA-BUGS.md "Stream
Revocation: Logout/Password/Role Changes Don't Terminate Established
Connections") re-checked the per-jti denylist and the
``max(password_changed_at, tokens_valid_from)`` cutoff -- but it worked from the
claims REMEMBERED at attach time, so it could not re-check ``exp`` or the
signature. A stream therefore outlived its own credential: a run lasting hours
kept streaming on a token that expired in the first minute. ``/ws/handoff`` never
had that property, because it re-runs the real verifier per message.

These tests drive ``run_stream._revocation_check`` through the endpoint's closure
by exercising the endpoint's own generator, using tokens minted by
``FakeCognitoAuth`` -- real RS256, real signature, real ``exp`` -- so "expired" here
means what it means in production rather than what a mock says it means.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.run_event  # noqa: F401 - register the table
import app.models.workflow  # noqa: F401 - register the table
import app.models.workspace  # noqa: F401 - register the table
from app.api.run_stream import recheck_stream_credential, router
from app.models.database import Base, get_db
from app.models.workflow import WorkflowRun
from tests.fakes.cognito_pool import FakeCognitoPool
from tests.fixtures.user_factory import FakeCognitoAuth, create_user

EMAIL = "streamer@example.com"


@pytest.fixture()
def env(monkeypatch):
    """A real endpoint over a real verifier, with only the AWS call replaced."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()

    import app.models.database as db_module

    monkeypatch.setattr(db_module, "SessionLocal", Session)
    monkeypatch.setattr(db_module, "engine", engine)

    fake = FakeCognitoAuth(monkeypatch, pool=FakeCognitoPool())
    fake.configure_settings()
    fake.seed_pool_user(EMAIL)
    user = create_user(session, EMAIL, "pw", cognito_sub=fake.sub_for(EMAIL))

    run = WorkflowRun(
        id="run-1",
        user_id=user.id,
        type="prototype",
        status="completed",
        input="build a landing page",
        workspace_id="ws-1",
    )
    session.add(run)
    session.commit()

    app = FastAPI()
    app.include_router(router)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db

    try:
        yield {
            "client": TestClient(app),
            "session": session,
            "fake": fake,
            "user": user,
            "run_id": "run-1",
        }
    finally:
        session.close()
        engine.dispose()


def _attach(env, token: str):
    return env["client"].get(
        f"/api/runs/{env['run_id']}/events/stream",
        headers={"Authorization": f"Bearer {token}"},
    )


class TestAttach:
    """Attach-time behaviour, asserted as a CONTRAST rather than a happy path.

    A valid token here gets a 404: this harness deliberately does not stand up the
    artifact store that the endpoint's second owner check
    (``ScopedStore.get_run`` -> 404) reads, and building it would add a lot of
    scaffolding to re-prove something ``test_sse_stream.py`` already covers.

    The contrast is what carries the meaning. 404 means the request got PAST
    authentication and was stopped by the owner gate; 401 means authentication
    itself rejected it. So "valid -> 404, expired -> 401" pins the verifier as
    the thing making the decision, which a bare ``assert 401`` could not: an
    endpoint that rejected every request would satisfy that just as well.
    """

    def test_a_valid_token_passes_authentication(self, env):
        token = env["fake"].mint_token(EMAIL)

        resp = _attach(env, token)

        assert resp.status_code == 404, "expected the owner gate, not an auth failure"

    def test_an_expired_token_is_rejected_by_authentication(self, env):
        token = env["fake"].mint_token(
            EMAIL, issued_at=int(time.time()) - 7200, expires_in=3600
        )

        resp = _attach(env, token)

        assert resp.status_code == 401

    def test_the_raw_bearer_is_still_required(self, env):
        """The endpoint gained a bearer_scheme dependency for the re-check; a
        missing Authorization header must still be rejected, not treated as an
        anonymous attach."""
        resp = env["client"].get(f"/api/runs/{env['run_id']}/events/stream")

        assert resp.status_code in (401, 403)


class TestPeriodicRecheck:
    """Exercises the endpoint's ``_revocation_check`` closure directly.

    Reaching it through a live stream would mean holding a connection open past
    ``SSE_REVOCATION_CHECK_INTERVAL_SECONDS`` (30s by default) -- a 30-second unit
    test that would still only prove the cadence, not the decision. The decision
    is what changed in Phase 2, so it is what is asserted; the cadence is already
    covered by ``test_sse_stream.py``'s drain tests.
    """

    def _revocation_check(self, env, token: str):
        """The REAL production function the endpoint's closure delegates to.

        It sits at module scope in ``run_stream.py`` precisely so this test can
        call it. Re-creating the check here instead would mean asserting against
        a copy of the logic, which would keep passing after the real one changed.
        """
        del env
        return recheck_stream_credential(token)

    def test_a_still_valid_token_keeps_the_stream_open(self, env):
        token = env["fake"].mint_token(EMAIL)

        assert self._revocation_check(env, token) is None

    def test_an_expired_token_terminates_the_stream(self, env):
        """The gap Phase 2 closes: this returned ``None`` before, because ``exp``
        was never re-examined after attach."""
        token = env["fake"].mint_token(
            EMAIL, issued_at=int(time.time()) - 7200, expires_in=3600
        )

        assert self._revocation_check(env, token) == "credential_expired"

    def test_a_token_signed_by_another_key_terminates_the_stream(self, env, monkeypatch):
        """Signature is re-checked too, so a pool key rotation ends the stream
        rather than letting it run on a key the pool no longer publishes."""
        other = FakeCognitoAuth(monkeypatch)
        token = other.mint_token(EMAIL)  # signed by a DIFFERENT RSA key

        assert self._revocation_check(env, token) == "credential_expired"

    def test_a_disabled_account_terminates_the_stream(self, env):
        """Disabling a user mid-stream must end their stream. The old check read
        the row directly and looked only at deletion, so ``status='disabled'``
        left an established stream running."""
        token = env["fake"].mint_token(EMAIL)
        env["user"].status = "disabled"
        env["session"].commit()

        assert self._revocation_check(env, token) == "account_removed"

    def test_a_blanket_revocation_terminates_the_stream(self, env):
        """The pre-existing behaviour, re-asserted against the rewritten check so
        the rewrite cannot silently drop it."""
        from datetime import datetime, timedelta, timezone

        token = env["fake"].mint_token(EMAIL)
        env["user"].tokens_valid_from = datetime.now(timezone.utc) + timedelta(
            seconds=60
        )
        env["session"].commit()

        assert self._revocation_check(env, token) == "credentials_changed"
