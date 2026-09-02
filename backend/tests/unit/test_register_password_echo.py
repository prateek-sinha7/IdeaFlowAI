"""tests/unit/test_register_password_echo.py — ISS-257.

`POST /api/auth/register` validates its body against `RegisterRequest` (which
still enforces `password: str = Field(..., min_length=8)`) before the handler
itself unconditionally 403s ("self-registration is disabled") — see
`app/api/auth.py:73-88`. Without a `RequestValidationError` handler on the
application, FastAPI/Pydantic's default 422 handler serializes its standard
error shape, which embeds the *entire rejected value* in `detail[].input` — so
a too-short password submitted to this endpoint would round-trip back to the
client in plaintext inside the 422 body. `app/main.py:331` registers that
handler (FIX-332); this test mounts the real `app.main.app` so it can observe
it (ISS-357 — a bare `FastAPI()` never could).

Same in-memory-SQLite + real `TestClient` harness as `test_login_timing_and_pii.py`.
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

    # ISS-357: the REAL application object — the RequestValidationError handler
    # this test exists to prove lives on `app.main.app` (`app/main.py:331`), so a
    # bare `FastAPI()` carrying only `auth_router` falls back to FastAPI's default
    # 422 handler and can never see it. Imported late, and deliberately NOT entered
    # as a context manager: `with TestClient(app)` runs the lifespan, and booting
    # the real application runs restore_non_terminal_runs() against the real DB
    # (see tests/unit/test_shutdown_reachability.py:65).
    from app.main import app

    app.dependency_overrides[get_db] = override_get_db

    yield TestClient(app)

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.issue("ISS-257")
def test_a_too_short_password_is_never_echoed_back_in_the_422_body(client):
    """ISS-257 — a rejected password must not round-trip in the 422 response."""
    rejected_password = "short7!"  # 7 chars, below RegisterRequest's min_length=8
    assert len(rejected_password) < 8

    resp = client.post(
        "/api/auth/register",
        json={"email": "nobody@example.com", "password": rejected_password},
    )

    assert resp.status_code == 422, resp.text
    assert rejected_password not in resp.text, (
        "the rejected password was echoed back verbatim in the 422 body: "
        f"{resp.text[:300]!r}"
    )
