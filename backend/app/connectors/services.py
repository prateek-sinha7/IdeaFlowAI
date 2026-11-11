"""Composition root of the connectors runtime.

``build_connector_services`` wires the registry, store, cipher, OAuth client,
token provider and OAuth service from one ``Settings`` snapshot. The API layer
(and tests) hold a ``ConnectorServices`` and never construct the pieces
themselves, so a test can swap the HTTP factory for a fake provider.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from langchain_mcp_adapters.sessions import McpHttpClientFactory

from app.connectors.account_deletion import AccountDeletion
from app.connectors.audit import ConnectorAudit
from app.connectors.binder import ConnectorRunToolBinder
from app.connectors.crypto import TokenCipher, TokenCodec
from app.connectors.errors import ConnectorNotConfigured
from app.connectors.http import (
    HttpClientFactory,
    default_http_client_factory,
    mcp_client_factory,
)
from app.connectors.oauth import OAuthClient, OAuthService
from app.connectors.registry import ConnectorRegistry
from app.connectors.store import ConnectionStore, SessionFactory, utcnow
from app.connectors.tokens import TokenProvider
from app.connectors.tool_listing import ToolListingService
from app.connectors.tools.base import ToolRuntime
from app.connectors.tools.remote_mcp import RemoteMcpBinder, RemoteMcpLister
from app.connectors.tools.schema_cache import ToolSchemaCache
from app.core.config import Settings


class _UnavailableCipher:
    """Stands in for the cipher when ``TOKEN_ENCRYPTION_KEY`` is missing or invalid.

    Every connector reports ``not_configured`` in that case, so no flow reaches the
    cipher. If one does, it fails closed instead of storing a plaintext token.
    """

    def encrypt(self, plaintext: str) -> str:
        raise ConnectorNotConfigured("connectors")

    def decrypt(self, ciphertext: str) -> str:
        raise ConnectorNotConfigured("connectors")


@dataclass(frozen=True)
class ConnectorServices:
    """The wired connectors runtime."""

    registry: ConnectorRegistry
    store: ConnectionStore
    cipher: TokenCodec
    oauth_client: OAuthClient
    tokens: TokenProvider
    oauth: OAuthService
    tool_cache: ToolSchemaCache
    tool_listing: ToolListingService
    audit: ConnectorAudit
    account_deletion: AccountDeletion
    binder: ConnectorRunToolBinder


def build_connector_services(
    settings: Settings,
    session_factory: SessionFactory,
    *,
    http_factory: HttpClientFactory | None = None,
    mcp_http_client_factory: McpHttpClientFactory = mcp_client_factory,
    clock: Callable[[], datetime] = utcnow,
    store: ConnectionStore | None = None,
) -> ConnectorServices:
    """Build the connectors runtime for ``settings``.

    ``http_factory`` defaults to real provider clients with
    ``CONNECTOR_HTTP_TIMEOUT_SECONDS``; tests pass a factory on a fake transport.
    ``mcp_http_client_factory`` builds the async client of MCP connections; tests
    pass one on an in-process transport. ``store`` replaces the database-backed
    store (tests only).
    """
    registry = ConnectorRegistry(settings)
    cipher: TokenCodec
    try:
        cipher = TokenCipher(settings.TOKEN_ENCRYPTION_KEY)
    except ValueError:
        cipher = _UnavailableCipher()
    store = store if store is not None else ConnectionStore(session_factory, clock)
    client = OAuthClient(
        http_factory
        or default_http_client_factory(settings.CONNECTOR_HTTP_TIMEOUT_SECONDS)
    )
    tokens = TokenProvider(
        registry=registry,
        store=store,
        cipher=cipher,
        client=client,
        skew_seconds=settings.CONNECTOR_REFRESH_SKEW_SECONDS,
        clock=clock,
    )
    tool_cache = ToolSchemaCache(
        settings.CONNECTOR_TOOL_SCHEMA_TTL_SECONDS, clock=clock
    )
    oauth = OAuthService(
        registry=registry,
        store=store,
        cipher=cipher,
        client=client,
        token_source=tokens,
        clock=clock,
        on_connection_changed=tool_cache.invalidate,
    )
    remote_mcp = RemoteMcpLister(
        registry=registry,
        tokens=tokens,
        cache=tool_cache,
        httpx_client_factory=mcp_http_client_factory,
        clock=clock,
    )
    audit = ConnectorAudit(store)
    runtime = ToolRuntime(
        registry=registry,
        store=store,
        tokens=tokens,
        audit=audit,
        async_client_factory=mcp_http_client_factory,
    )
    binder = ConnectorRunToolBinder(
        runtime=runtime,
        remote=RemoteMcpBinder(
            runtime=runtime,
            lister=remote_mcp,
            httpx_client_factory=mcp_http_client_factory,
        ),
    )
    return ConnectorServices(
        registry=registry,
        store=store,
        cipher=cipher,
        oauth_client=client,
        tokens=tokens,
        oauth=oauth,
        tool_cache=tool_cache,
        tool_listing=ToolListingService(
            registry=registry, store=store, remote_mcp=remote_mcp
        ),
        audit=audit,
        account_deletion=AccountDeletion(
            registry=registry,
            cipher=cipher,
            client=client,
            forget_user=tool_cache.invalidate_user,
            skew_seconds=settings.CONNECTOR_REFRESH_SKEW_SECONDS,
            clock=clock,
        ),
        binder=binder,
    )


_services: ConnectorServices | None = None
_services_lock = threading.Lock()


def get_connector_services() -> ConnectorServices:
    """FastAPI dependency: the process-wide connectors runtime, built on first use.

    Tests replace it with ``app.dependency_overrides``; ``reset_connector_services``
    clears the cached instance.
    """
    global _services
    if _services is None:
        with _services_lock:
            if _services is None:
                from app.core.config import settings
                from app.models.database import SessionLocal

                _services = build_connector_services(settings, SessionLocal)
    return _services


def reset_connector_services() -> None:
    """Forget the cached runtime (tests, and settings reloads)."""
    global _services
    with _services_lock:
        _services = None
