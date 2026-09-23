"""tests/unit/test_register_password_echo_fixture_mounts_real_app.py — ISS-357.

`test_register_password_echo.py` proves ISS-257 (a too-short password must not
be echoed back in `POST /api/auth/register`'s 422 body) with a fixture that
builds its own `FastAPI()` and mounts only `auth_router`:

    app = FastAPI()
    app.include_router(auth_router)

ISS-257's fix (FIX-332) is a `RequestValidationError` handler registered on
`app.main.app` (see `app/main.py:331-332`) that redacts the rejected value. A
bare `FastAPI()` never mounts that handler — it falls back to FastAPI's own
*default* `RequestValidationError` handler, which still embeds the full
rejected value in `detail[].input`. So the harness that exists to prove the
redaction fix can never observe it: "the app under test is not the
application" (ISS-357).

This test guards that: it hits the same endpoint through the same harness the
existing test uses, and asserts the password is NOT echoed — which only holds
while that harness mounts the real application.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, get_db
from app.models.revoked_token import RevokedToken  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.chat import ChatSession, Message  # noqa: F401
from app.models.workflow import WorkflowRun  # noqa: F401


@pytest.fixture
def client():
    # Mirrors test_register_password_echo.py's fixture verbatim (ISS-357).
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

    # ISS-357: the REAL application object, imported late and NOT entered as a
    # context manager (the lifespan runs restore_non_terminal_runs()).
    from app.main import app

    app.dependency_overrides[get_db] = override_get_db

    yield TestClient(app)

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.issue("ISS-357")
def test_password_echo_harness_observes_app_mains_redaction_fix(client):
    """ISS-357 — the ISS-257 test harness must exercise app.main's own
    RequestValidationError handler (FIX-332), not fall back to FastAPI's
    default handler, which still leaks the rejected value.
    """
    resp = client.post(
        "/api/auth/register",
        json={"email": "nobody@example.com", "password": "short7!"},
    )
    assert resp.status_code == 422, resp.text
    assert "short7!" not in resp.text, (
        "the harness's bare FastAPI() has no RequestValidationError handler "
        "of its own, so it falls back to FastAPI's default handler (which "
        "still embeds the rejected value in detail[].input) instead of "
        "app.main's redacting one from FIX-332 — the harness can neither "
        f"confirm the real fix nor reject a wrong one: {resp.text[:300]!r}"
    )
