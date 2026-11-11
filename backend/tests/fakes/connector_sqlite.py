"""Connector services over a real (in-memory SQLite) database for integration tests.

Everything except the provider network is real: ``ConnectionStore`` reads and writes
the SQL tables, tokens are Fernet-encrypted at rest, and the OAuth flow, token
provider, audit sink and tool wrappers run unmodified. PostgreSQL-only behaviour
(row locks) is covered in ``tests/integration/db``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.connectors.http import mcp_client_factory
from app.connectors.oauth import CallbackParams
from app.connectors.services import ConnectorServices, build_connector_services
from app.connectors.tools.base import ToolRuntime
from app.core.config import Settings
from app.models.connector import ConnectorAuditLog
from app.models.database import Base
from app.models.user import User
from tests.fakes.connector_settings import make_settings
from tests.fakes.oauth_provider import FakeOAuthProvider, query_of

GITHUB_ISSUER = "https://github.com/login/oauth"


@dataclass
class SqliteConnectors:
    """Services, the fake providers and the session factory behind them."""

    services: ConnectorServices
    provider: FakeOAuthProvider
    factory: sessionmaker[Session]
    settings: Settings

    def connect(self, user_id: str, connector_key: str) -> None:
        """Run authorize and callback so ``user_id`` has an active connection."""
        started = self.services.oauth.start_authorization(user_id, connector_key)
        state = query_of(started.authorization_url)["state"]
        iss = GITHUB_ISSUER if connector_key == "github" else None
        outcome = self.services.oauth.complete_callback(
            CallbackParams(state=state, code="auth-code", iss=iss)
        )
        assert outcome.connected, outcome

    def tool_runtime(self, async_client_factory: Callable[..., Any]) -> ToolRuntime:
        """A ``ToolRuntime`` over these services."""
        services = self.services
        return ToolRuntime(
            registry=services.registry,
            store=services.store,
            tokens=services.tokens,
            audit=services.audit,
            async_client_factory=async_client_factory,
        )

    def audit_rows(self) -> list[ConnectorAuditLog]:
        """Every audit row, oldest first."""
        with self.factory() as session:
            return list(
                session.query(ConnectorAuditLog).order_by(ConnectorAuditLog.created_at)
            )


@contextmanager
def sqlite_connectors(
    users: Iterable[str],
    *,
    mcp_http_client_factory: Callable[..., Any] = mcp_client_factory,
    settings: Settings | None = None,
) -> Iterator[SqliteConnectors]:
    """Create the schema, the given users and the wired services."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        for user_id in users:
            session.add(
                User(
                    id=user_id,
                    email=f"{user_id}@example.com",
                    cognito_sub=f"sub-{user_id}",
                )
            )
        session.commit()
    settings = settings or make_settings()
    provider = FakeOAuthProvider()
    services = build_connector_services(
        settings,
        factory,
        http_factory=provider.http_factory,
        mcp_http_client_factory=mcp_http_client_factory,
    )
    try:
        yield SqliteConnectors(services, provider, factory, settings)
    finally:
        engine.dispose()
