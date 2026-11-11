"""Shared wiring for the connectors unit tests.

Everything is in memory: ``FakeConnectionStore`` replaces the database,
``FakeOAuthProvider`` replaces the providers' HTTP endpoints, and ``MutableClock``
replaces the wall clock. The runtime classes run unmodified.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.connectors.crypto import TokenCipher
from app.connectors.oauth import OAuthClient, OAuthService
from app.connectors.registry import ConnectorRegistry
from app.connectors.tokens import TokenProvider
from app.core.config import Settings
from tests.fakes.connector_settings import CLIENT_SECRETS, REDIRECT_URI, make_settings
from tests.fakes.connector_store import FakeConnectionStore, MutableClock
from tests.fakes.oauth_provider import FakeOAuthProvider

USER_ID = "user-a"
OTHER_USER_ID = "user-b"

__all__ = [
    "CLIENT_SECRETS",
    "OTHER_USER_ID",
    "REDIRECT_URI",
    "USER_ID",
    "Wired",
    "make_settings",
    "wire",
    "wired",
]


@dataclass
class Wired:
    """The connectors runtime on in-memory fakes."""

    settings: Settings
    clock: MutableClock
    store: FakeConnectionStore
    provider: FakeOAuthProvider
    cipher: TokenCipher
    registry: ConnectorRegistry
    client: OAuthClient
    tokens: TokenProvider
    oauth: OAuthService


def wire(settings: Settings | None = None, **token_options: float) -> Wired:
    """Build the runtime. ``token_options`` go to ``TokenProvider``."""
    settings = settings or make_settings()
    clock = MutableClock()
    store = FakeConnectionStore(clock)
    provider = FakeOAuthProvider()
    cipher = TokenCipher(settings.TOKEN_ENCRYPTION_KEY)
    registry = ConnectorRegistry(settings)
    client = OAuthClient(provider.http_factory)
    tokens = TokenProvider(
        registry=registry,
        store=store,  # type: ignore[arg-type]  # FakeConnectionStore mirrors ConnectionStore
        cipher=cipher,
        client=client,
        clock=clock,
        **token_options,  # type: ignore[arg-type]
    )
    oauth = OAuthService(
        registry=registry,
        store=store,  # type: ignore[arg-type]
        cipher=cipher,
        client=client,
        token_source=tokens,
        clock=clock,
    )
    return Wired(
        settings=settings,
        clock=clock,
        store=store,
        provider=provider,
        cipher=cipher,
        registry=registry,
        client=client,
        tokens=tokens,
        oauth=oauth,
    )


@pytest.fixture
def wired() -> Wired:
    """A fully configured runtime on fakes."""
    return wire()
