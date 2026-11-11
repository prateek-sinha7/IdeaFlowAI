"""``/api/connectors`` over a real (SQLite) database with the real connector store.

Only the providers are fake. Proves what the in-memory unit tests cannot: rows are
written and read through SQL, tokens are encrypted at rest, the OAuth state is stored
hashed and consumed once, a reconnect updates one row, and a disconnect writes audit
rows. PostgreSQL-specific behaviour is in ``tests/integration/db``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.connectors.pkce import hash_state
from app.connectors.services import ConnectorServices, build_connector_services
from app.models.connector import ConnectorAuditLog, ConnectorConnection, OAuthState
from app.models.database import Base
from app.models.user import User
from tests.fakes.connector_app import (
    CurrentUser,
    connect_through_api,
    make_connector_app,
    make_user,
)
from tests.fakes.connector_services import ConnectorWorld
from tests.fakes.connector_settings import make_settings
from tests.fakes.connector_store import MutableClock
from tests.fakes.oauth_provider import FakeOAuthProvider, query_of

USER = "user-a"
OTHER = "user-b"


@dataclass
class _Db:
    factory: sessionmaker[Session]
    services: ConnectorServices
    provider: FakeOAuthProvider
    current: CurrentUser

    def session(self) -> Session:
        return self.factory()


@pytest.fixture
def api() -> Iterator[tuple[TestClient, _Db]]:
    """A client over the connectors router with a real database and fake providers."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        for uid in (USER, OTHER):
            session.add(
                User(id=uid, email=f"{uid}@example.com", cognito_sub=f"sub-{uid}")
            )
        session.commit()
    settings = make_settings()
    provider = FakeOAuthProvider()
    services = build_connector_services(
        settings, factory, http_factory=provider.http_factory
    )
    current = CurrentUser(make_user(USER))
    # The router only needs ``services``; reuse the app builder with a world shell.
    world = ConnectorWorld(
        services=services,
        settings=settings,
        clock=MutableClock(),
        store=None,  # type: ignore[arg-type]  # unused by the router
        provider=provider,
    )
    with TestClient(make_connector_app(world, current)) as client:
        yield client, _Db(factory, services, provider, current)
    engine.dispose()


def _location_query(response) -> dict[str, str]:
    return {
        k: v[0]
        for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()
    }


class TestJiraFlow:
    def test_jira_flow_stores_encrypted_connection_and_lists_it_when_user_connects(
        self, api: tuple[TestClient, _Db]
    ) -> None:
        client, db = api

        response = connect_through_api(client, "jira")

        assert response.status_code == 303
        assert _location_query(response) == {"connector": "jira", "result": "connected"}
        with db.session() as session:
            row = session.query(ConnectorConnection).one()
            assert (row.user_id, row.connector_key, row.status) == (
                USER,
                "jira",
                "active",
            )
            assert row.provider_account_id == "acc-1"
            assert row.provider_metadata == {
                "sites": [
                    {
                        "id": "cloud-1",
                        "name": "Acme",
                        "url": "https://acme.atlassian.net",
                    }
                ]
            }
            assert "atl_access_initial" not in row.access_token_ciphertext
            assert "atl_refresh_initial" not in (row.refresh_token_ciphertext or "")
        listed = client.get("/api/connectors").json()["connectors"]
        assert {c["key"]: c["status"] for c in listed} == {
            "github": "not_connected",
            "jira": "connected",
        }

    def test_jira_flow_stores_state_hashed_and_consumes_it_when_callback_runs(
        self, api: tuple[TestClient, _Db]
    ) -> None:
        client, db = api
        started = client.post("/api/connectors/jira/authorize").json()
        state = query_of(started["authorization_url"])["state"]
        with db.session() as session:
            pending = session.query(OAuthState).one()
            assert pending.state_hash == hash_state(state)
            assert state not in pending.state_hash
            assert pending.consumed_at is None
            assert pending.user_id == USER

        client.get(
            "/api/connectors/oauth/callback",
            params={"state": state, "code": "c1"},
            follow_redirects=False,
        )

        with db.session() as session:
            assert session.query(OAuthState).one().consumed_at is not None

    def test_callback_reports_invalid_state_and_writes_nothing_when_replayed(
        self, api: tuple[TestClient, _Db]
    ) -> None:
        client, db = api
        started = client.post("/api/connectors/jira/authorize").json()
        state = query_of(started["authorization_url"])["state"]
        params = {"state": state, "code": "c1"}
        client.get(
            "/api/connectors/oauth/callback", params=params, follow_redirects=False
        )
        db.provider.requests.clear()

        replay = client.get(
            "/api/connectors/oauth/callback", params=params, follow_redirects=False
        )

        assert _location_query(replay)["reason"] == "invalid_state"
        assert db.provider.requests == []
        with db.session() as session:
            assert session.query(ConnectorConnection).count() == 1

    def test_reconnect_updates_the_single_row_and_bumps_version_when_connected_twice(
        self, api: tuple[TestClient, _Db]
    ) -> None:
        client, db = api

        connect_through_api(client, "jira")
        connect_through_api(client, "jira")

        with db.session() as session:
            rows = session.query(ConnectorConnection).all()
            assert len(rows) == 1
            assert rows[0].token_version == 2

    def test_tools_list_returns_declared_tools_and_connected_status_when_jira_connected(
        self, api: tuple[TestClient, _Db]
    ) -> None:
        client, _ = api
        connect_through_api(client, "jira")

        body = client.get("/api/connectors/jira/tools").json()

        assert body["status"] == "connected"
        assert len(body["tools"]) == 10

    def test_disconnect_revokes_deletes_row_and_audits_when_connected(
        self, api: tuple[TestClient, _Db]
    ) -> None:
        client, db = api
        connect_through_api(client, "jira")

        response = client.delete("/api/connectors/jira")

        assert response.json() == {
            "status": "disconnected",
            "provider_revocation": "revoked",
        }
        with db.session() as session:
            assert session.query(ConnectorConnection).count() == 0
            actions = [
                (a.action, a.outcome)
                for a in session.query(ConnectorAuditLog).order_by(
                    ConnectorAuditLog.created_at
                )
            ]
        assert ("authorize_started", "ok") in actions
        assert ("connected", "ok") in actions
        assert ("disconnected", "ok") in actions


class TestGithubFlow:
    def test_github_flow_records_scopes_from_header_when_user_connects(
        self, api: tuple[TestClient, _Db]
    ) -> None:
        client, db = api

        response = connect_through_api(client, "github")

        assert _location_query(response) == {
            "connector": "github",
            "result": "connected",
        }
        with db.session() as session:
            row = session.query(ConnectorConnection).one()
            assert row.provider_account_login == "octocat"
            assert row.granted_scopes == ["repo"]

    def test_github_flow_stores_nothing_when_issuer_missing(
        self, api: tuple[TestClient, _Db]
    ) -> None:
        client, db = api
        started = client.post("/api/connectors/github/authorize").json()
        state = query_of(started["authorization_url"])["state"]

        response = client.get(
            "/api/connectors/oauth/callback",
            params={"state": state, "code": "c1"},
            follow_redirects=False,
        )

        assert _location_query(response)["reason"] == "issuer_missing"
        with db.session() as session:
            assert session.query(ConnectorConnection).count() == 0


class TestIsolation:
    def test_list_shows_only_callers_connection_when_two_users_connected(
        self, api: tuple[TestClient, _Db]
    ) -> None:
        client, db = api
        connect_through_api(client, "jira")
        db.current.user = make_user(OTHER)

        other_view = client.get("/api/connectors").json()["connectors"]
        other_delete = client.delete("/api/connectors/jira").json()

        assert {c["key"]: c["status"] for c in other_view}["jira"] == "not_connected"
        assert other_delete["provider_revocation"] == "not_attempted"
        with db.session() as session:
            assert (
                session.query(ConnectorConnection).filter_by(user_id=USER).count() == 1
            )
