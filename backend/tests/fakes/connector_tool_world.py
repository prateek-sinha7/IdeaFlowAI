"""Helpers that connect users and build a ``ToolRuntime`` on the fake connectors world."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.connectors.oauth import CallbackParams
from app.connectors.tools.base import ToolRuntime
from tests.fakes.connector_services import ConnectorWorld
from tests.fakes.oauth_provider import query_of

GITHUB_ISSUER = "https://github.com/login/oauth"


def connect(world: ConnectorWorld, user_id: str, connector_key: str) -> None:
    """Run the authorize and callback flow so ``user_id`` has an active connection."""
    started = world.services.oauth.start_authorization(user_id, connector_key)
    state = query_of(started.authorization_url)["state"]
    iss = GITHUB_ISSUER if connector_key == "github" else None
    outcome = world.services.oauth.complete_callback(
        CallbackParams(state=state, code="auth-code", iss=iss)
    )
    assert outcome.connected, outcome


def tool_runtime(
    world: ConnectorWorld, async_client_factory: Callable[..., Any]
) -> ToolRuntime:
    """A ``ToolRuntime`` over the world's registry, store, tokens and audit."""
    services = world.services
    return ToolRuntime(
        registry=services.registry,
        store=services.store,
        tokens=services.tokens,
        audit=services.audit,
        async_client_factory=async_client_factory,
    )
