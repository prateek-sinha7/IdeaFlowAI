"""QA-KB-108 / ISS-1144 -- a botocore BotoCoreError (expired AWS SSO token) during
POST /api/auth/login must be a handled 503 with CORS headers and one LOGIN_FAILURE event,
not an unhandled 500 the browser reports as a CORS block.

Hermetic: DB dependency stubbed, ``cognito.admin_initiate_auth`` patched, no network.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from botocore.exceptions import ClientError, TokenRetrievalError
from fastapi.testclient import TestClient

import app.api.auth as auth_api
from app.main import app
from app.models.database import get_db

ORIGIN = "http://localhost:3000"
BODY = {"email": "probe@example.com", "password": "Whatever1!aaaa"}


class _FakeDB:
    def query(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def first(self):
        return None

    def commit(self):
        pass

    def rollback(self):
        pass

    def add(self, *a, **k):
        pass


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _login(client, exc):
    with mock.patch.object(auth_api.cognito, "admin_initiate_auth", side_effect=exc):
        return client.post("/api/auth/login", json=BODY, headers={"Origin": ORIGIN})


def _events(caplog):
    return [
        json.loads(r.message) for r in caplog.records if r.name == "app.auth.events"
    ]


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "AdminInitiateAuth")


@pytest.mark.issue("ISS-1144")
def test_expired_sso_login_is_handled_503_with_cors(client, caplog):
    """ISS-1144 -- TokenRetrievalError gives 503 + CORS header + one provider_error event."""
    with caplog.at_level("WARNING", logger="app.auth.events"):
        r = _login(
            client,
            TokenRetrievalError(
                provider="sso", error_msg="Token has expired and refresh failed"
            ),
        )
    assert r.status_code == 503
    assert r.json()["detail"]
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    failures = [
        e
        for e in _events(caplog)
        if e.get("reason") == "provider_error:TokenRetrievalError"
    ]
    assert len(failures) == 1
    assert failures[0].get("provider") == "cognito"


def test_control_client_error_provider_5xx_stays_503(client, caplog):
    """Control: a ClientError provider failure keeps its 503 and provider_error event."""
    with caplog.at_level("WARNING", logger="app.auth.events"):
        r = _login(client, _client_error("InternalErrorException"))
    assert r.status_code == 503
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert any(
        e.get("reason") == "provider_error:InternalErrorException"
        for e in _events(caplog)
    )


def test_control_not_authorized_stays_401(client):
    """Control: wrong password stays 401, never turned into an outage."""
    r = _login(client, _client_error("NotAuthorizedException"))
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid credentials"
