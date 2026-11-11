"""``DELETE /api/admin/users/{id}`` with connected GitHub and Jira accounts.

The route handler runs against a real (SQLite) database with the real
``AccountDeletion``; only the providers are fake. Covers: one revoke per connection
with the stored token and only after the commit, the rows gone, the audit event with
counts and outcomes, a provider outage that still deletes, and a failed transaction
that makes no provider call.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api import admin as admin_mod
from app.connectors.crypto import TokenCipher
from app.connectors.services import ConnectorServices, build_connector_services
from app.core import auth_events
from app.core.entitlements import ADMIN_GROUP, group_for_tier
from app.models.connector import ConnectorAuditLog, ConnectorConnection, OAuthState
from app.models.database import Base
from app.models.user import User
from tests.factories.connector_factory import (
    ConnectorConnectionFactory,
    OAuthStateFactory,
)
from tests.fakes.cognito_pool import FakeCognitoPool
from tests.fakes.connector_settings import make_settings
from tests.fakes.oauth_provider import (
    ATLASSIAN_REVOKE_URL,
    GITHUB_GRANT_URL,
    FakeOAuthProvider,
    empty_response,
    timeout_response,
)

GRANT_URL = GITHUB_GRANT_URL.format(client_id="github-client-id")
TARGET = "target-1"


class _World:
    def __init__(self, session: Session, factory: sessionmaker[Session]) -> None:
        self.session = session
        self.factory = factory
        self.settings = make_settings()
        self.cipher = TokenCipher(self.settings.TOKEN_ENCRYPTION_KEY)
        self.provider = FakeOAuthProvider()
        self.services: ConnectorServices = build_connector_services(
            self.settings, factory, http_factory=self.provider.http_factory
        )
        #: Whether the target user row still existed when each provider call arrived.
        self.user_present_at_call: list[bool] = []

    def watch(self, method: str, url: str, status: int = 204) -> None:
        """Answer ``method url`` and record whether the user was still in the database."""

        def _respond(request: httpx.Request) -> httpx.Response:
            with self.factory() as other:
                self.user_present_at_call.append(
                    other.query(User).filter(User.id == TARGET).first() is not None
                )
            return httpx.Response(status, request=request)

        self.provider.respond(method, url, _respond)

    def connect(self, key: str, access: str, refresh: str) -> None:
        self.session.add(
            ConnectorConnectionFactory.build(
                user_id=TARGET,
                connector_key=key,
                access_token_ciphertext=self.cipher.encrypt(access),
                refresh_token_ciphertext=self.cipher.encrypt(refresh),
                access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
            )
        )
        self.session.commit()


@pytest.fixture
def world(tmp_path: Path) -> Iterator[_World]:
    """A file-backed SQLite database (separate connections), an admin and a target user.

    A file, not ``sqlite://``: the "only after the commit" test reads through a second
    connection, which must not see the deleting session's uncommitted changes.
    """
    engine = create_engine(
        f"sqlite:///{tmp_path / 'connectors.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    session.add(
        User(
            id="admin-1",
            email="admin@example.com",
            cognito_sub="sub-admin",
            tier="enterprise",
            is_admin=True,
        )
    )
    session.add(
        User(id=TARGET, email="t@example.com", cognito_sub="sub-t", tier="basic")
    )
    session.add(User(id="bystander", email="b@example.com", cognito_sub="sub-b"))
    session.commit()
    try:
        yield _World(session, factory)
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> FakeCognitoPool:
    """A fake Cognito user pool with the admin and the target registered."""
    fake = FakeCognitoPool().install(monkeypatch)
    fake.add(
        sub="sub-admin",
        email="admin@example.com",
        groups={ADMIN_GROUP, group_for_tier("enterprise")},
    )
    fake.add(sub="sub-t", email="t@example.com", groups={group_for_tier("basic")})
    return fake


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Every ``USER_DELETED`` event the route emits with its fields."""
    captured: list[dict[str, Any]] = []
    original = auth_events.emit

    def _spy(event: auth_events.AuthEvent, **fields: Any) -> None:
        if event == auth_events.AuthEvent.USER_DELETED and "dependent_counts" in fields:
            captured.append(fields)
        original(event, **fields)

    monkeypatch.setattr(auth_events, "emit", _spy)
    return captured


def _delete(world: _World) -> Any:
    admin = world.session.get(User, "admin-1")
    return admin_mod.delete_user(
        user_id=TARGET, admin=admin, db=world.session, connectors=world.services
    )


@pytest.mark.usefixtures("pool")
class TestDeleteUserWithConnectors:
    def test_delete_user_revokes_each_grant_with_stored_token_when_user_has_two(
        self, world: _World, events: list[dict[str, Any]]
    ) -> None:
        world.connect("github", "gh-access", "gh-refresh")
        world.connect("jira", "jira-access", "jira-refresh")

        response = _delete(world)

        assert response.status_code == 204
        grant_calls = world.provider.calls("DELETE", GRANT_URL)
        assert [c.json_body for c in grant_calls] == [{"access_token": "gh-access"}]
        revoke_calls = world.provider.calls("POST", ATLASSIAN_REVOKE_URL)
        assert [(c.json_body or {})["token"] for c in revoke_calls] == ["jira-refresh"]

    def test_delete_user_calls_providers_only_after_the_commit_when_user_has_connections(
        self, world: _World
    ) -> None:
        world.connect("github", "gh-access", "gh-refresh")
        world.connect("jira", "jira-access", "jira-refresh")
        world.watch("DELETE", GRANT_URL)
        world.watch("POST", ATLASSIAN_REVOKE_URL, 200)

        _delete(world)

        assert world.user_present_at_call == [False, False]

    def test_delete_user_removes_connector_rows_and_keeps_bystanders_when_deleting(
        self, world: _World
    ) -> None:
        world.connect("github", "gh-access", "gh-refresh")
        world.session.add(OAuthStateFactory.build(user_id=TARGET))
        world.session.add(
            ConnectorAuditLog(
                user_id=TARGET,
                connector_key="github",
                action="connected",
                outcome="ok",
                created_at=datetime.now(timezone.utc),
            )
        )
        world.session.add(
            ConnectorConnectionFactory.build(user_id="bystander", connector_key="jira")
        )
        world.session.commit()

        _delete(world)

        assert world.session.query(User).filter_by(id=TARGET).count() == 0
        assert (
            world.session.query(ConnectorConnection).filter_by(user_id=TARGET).count()
            == 0
        )
        assert world.session.query(OAuthState).filter_by(user_id=TARGET).count() == 0
        assert (
            world.session.query(ConnectorAuditLog).filter_by(user_id=TARGET).count()
            == 0
        )
        assert (
            world.session.query(ConnectorConnection)
            .filter_by(user_id="bystander")
            .count()
            == 1
        )

    def test_delete_user_reports_counts_and_outcomes_in_event_when_user_had_connections(
        self, world: _World, events: list[dict[str, Any]]
    ) -> None:
        world.connect("github", "gh-access", "gh-refresh")
        world.connect("jira", "jira-access", "jira-refresh")
        world.provider.respond("POST", ATLASSIAN_REVOKE_URL, empty_response(503))

        _delete(world)

        (event,) = events
        assert event["dependent_counts"]["connector_connections"] == 2
        assert event["connector_revocations"] == {
            "github": "revoked",
            "jira": "failed",
        }

    def test_delete_user_leaves_revocation_field_out_when_user_had_no_connections(
        self, world: _World, events: list[dict[str, Any]]
    ) -> None:
        _delete(world)

        (event,) = events
        assert "connector_revocations" not in event
        assert world.provider.requests == []

    def test_delete_user_returns_204_and_deletes_when_provider_times_out(
        self, world: _World
    ) -> None:
        world.connect("github", "gh-access", "gh-refresh")
        world.provider.respond("DELETE", GRANT_URL, timeout_response)

        response = _delete(world)

        assert response.status_code == 204
        assert world.session.query(User).filter_by(id=TARGET).count() == 0

    def test_delete_user_reports_not_attempted_when_token_cannot_be_decrypted(
        self, world: _World, events: list[dict[str, Any]]
    ) -> None:
        world.session.add(
            ConnectorConnectionFactory.build(
                user_id=TARGET,
                connector_key="github",
                access_token_ciphertext="not-a-fernet-token",
            )
        )
        world.session.commit()

        _delete(world)

        assert events[0]["connector_revocations"] == {"github": "not_attempted"}
        assert world.provider.requests == []

    def test_delete_user_makes_no_provider_call_when_transaction_fails(
        self, world: _World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world.connect("github", "gh-access", "gh-refresh")
        world.connect("jira", "jira-access", "jira-refresh")

        def _boom(_db: Session, _user_id: str) -> dict[str, int]:
            raise RuntimeError("deletion transaction failed")

        monkeypatch.setattr(admin_mod, "delete_user_dependents", _boom)

        with pytest.raises(RuntimeError):
            _delete(world)
        world.session.rollback()

        assert world.provider.requests == []
        assert (
            world.session.query(ConnectorConnection).filter_by(user_id=TARGET).count()
            == 2
        )


def test_token_values_stay_out_of_logs_when_user_with_connections_is_deleted(
    world: _World, pool: FakeCognitoPool, caplog: pytest.LogCaptureFixture
) -> None:
    world.connect("github", "gh-access-sentinel", "gh-refresh-sentinel")
    world.connect("jira", "jira-access-sentinel", "jira-refresh-sentinel")

    with caplog.at_level(0):
        _delete(world)

    for sentinel in (
        "gh-access-sentinel",
        "gh-refresh-sentinel",
        "jira-access-sentinel",
        "jira-refresh-sentinel",
        "github-secret-sentinel",
        "jira-secret-sentinel",
    ):
        assert sentinel not in caplog.text
