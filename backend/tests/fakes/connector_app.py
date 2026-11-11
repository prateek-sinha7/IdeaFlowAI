"""A minimal FastAPI app that serves only the connectors router, for API tests.

``CurrentUser`` is the switchable caller: set ``.user`` to act as a user, to ``None``
to act as an anonymous caller (the dependency then answers 401, like the real one).
The connectors services come from a ``ConnectorWorld`` so tests control the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.api.connectors import router
from app.connectors.services import get_connector_services
from app.core.dependencies import get_current_user
from app.models.user import User
from tests.fakes.connector_services import ConnectorWorld
from tests.fakes.oauth_provider import query_of

GITHUB_ISSUER = "https://github.com/login/oauth"


def make_user(user_id: str) -> User:
    """An unsaved ``User`` with a stable id."""
    return User(
        id=user_id, email=f"{user_id}@example.com", cognito_sub=f"sub-{user_id}"
    )


@dataclass
class CurrentUser:
    """The caller the app sees; ``None`` means no bearer token."""

    user: User | None


def make_connector_app(world: ConnectorWorld, current: CurrentUser) -> FastAPI:
    """Build the app: connectors router, services from ``world``, caller from ``current``."""
    app = FastAPI()
    app.include_router(router)

    def _current_user() -> User:
        if current.user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
        return current.user

    app.dependency_overrides[get_connector_services] = lambda: world.services
    app.dependency_overrides[get_current_user] = _current_user
    return app


def connect_through_api(
    client: TestClient,
    key: str,
    *,
    code: str = "auth-code",
    iss: str | None = None,
    **extra_params: Any,
) -> Any:
    """Run authorize then callback; return the callback response (a 303)."""
    started = client.post(f"/api/connectors/{key}/authorize")
    assert started.status_code == 200, started.text
    state = query_of(started.json()["authorization_url"])["state"]
    params: dict[str, Any] = {"state": state, "code": code, **extra_params}
    if iss is None and key == "github":
        iss = GITHUB_ISSUER
    if iss is not None:
        params["iss"] = iss
    return client.get(
        "/api/connectors/oauth/callback", params=params, follow_redirects=False
    )
