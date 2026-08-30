"""tests/unit/test_register_password_echo.py — ISS-257.

`POST /api/auth/register` validates its body against `RegisterRequest` (which
still enforces `password: str = Field(..., min_length=8)`) before the handler
itself unconditionally 403s ("self-registration is disabled") — see
`app/api/auth.py:73-88`. Because `app/main.py` registers no
`RequestValidationError` handler anywhere in the app (grep confirms zero
`exception_handler`/`RequestValidationError` hits under `backend/app/`),
FastAPI/Pydantic's default 422 handler serializes its standard error shape,
which embeds the *entire rejected value* in `detail[].input` — so a too-short
password submitted to this endpoint round-trips back to the client in
plaintext inside the 422 body.

Same in-memory-SQLite + real `TestClient` harness as `test_login_timing_and_pii.py`.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import router as auth_router
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

    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.issue("ISS-257")
@pytest.mark.xfail(reason="ISS-257 unfixed", strict=True)
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
