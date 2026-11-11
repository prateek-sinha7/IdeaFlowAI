"""A complete ``ConnectorServices`` on in-memory fakes.

``build_world`` wires the real connectors runtime over ``FakeConnectionStore`` (no
database) and ``FakeOAuthProvider`` (no provider network). For the MCP connection it
uses ``mcp_http_client_factory``: pass ``FakeGitHubMcpServer.client_factory`` to talk
to an in-process server. Tests that need the real database build their own services
with ``build_connector_services``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.connectors.http import mcp_client_factory
from app.connectors.services import ConnectorServices, build_connector_services
from app.core.config import Settings
from tests.fakes.connector_settings import make_settings
from tests.fakes.connector_store import FakeConnectionStore, MutableClock
from tests.fakes.oauth_provider import FakeOAuthProvider


@dataclass
class ConnectorWorld:
    """The wired runtime plus the fakes behind it."""

    services: ConnectorServices
    settings: Settings
    clock: MutableClock
    store: FakeConnectionStore
    provider: FakeOAuthProvider


def _no_database() -> Any:
    raise AssertionError("this world has no database; use the fake store")


def build_world(
    settings: Settings | None = None,
    *,
    mcp_http_client_factory: Callable[..., Any] = mcp_client_factory,
) -> ConnectorWorld:
    """Build the connectors runtime on fakes."""
    settings = settings or make_settings()
    clock = MutableClock()
    provider = FakeOAuthProvider()
    store = FakeConnectionStore(clock)
    services = build_connector_services(
        settings,
        _no_database,
        http_factory=provider.http_factory,
        mcp_http_client_factory=mcp_http_client_factory,
        clock=clock,
        store=store,  # type: ignore[arg-type]  # FakeConnectionStore mirrors ConnectionStore
    )
    return ConnectorWorld(
        services=services,
        settings=settings,
        clock=clock,
        store=store,
        provider=provider,
    )
