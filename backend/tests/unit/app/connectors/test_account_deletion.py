"""``AccountDeletion``: collect under a lock, revoke after the commit, never raise.

Unit scope: the database is replaced by a mocked ``Session`` and a patched
``ConnectionStore.records_for_update`` (the SQL, including ``FOR UPDATE``, is proven in
``tests/integration/repositories/test_account_deletion_db.py``). The provider is the
fake OAuth provider on a mock transport.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.connectors.account_deletion import AccountDeletion, CollectedGrant
from app.connectors.crypto import TokenCipher
from app.connectors.oauth import OAuthClient
from app.connectors.registry import ConnectorRegistry
from app.connectors.store import ConnectionRecord, ConnectionStore
from tests.fakes.connector_settings import make_settings
from tests.fakes.oauth_provider import (
    ATLASSIAN_REVOKE_URL,
    ATLASSIAN_TOKEN_URL,
    GITHUB_GRANT_URL,
    GITHUB_TOKEN_URL,
    FakeOAuthProvider,
    atlassian_token_body,
    empty_response,
    github_token_body,
    json_response,
    timeout_response,
)
from tests.fakes.connector_store import MutableClock

USER = "user-a"
GRANT_URL = GITHUB_GRANT_URL.format(client_id="github-client-id")


class _Fixture:
    """Deletion service over a fake provider, with a cipher and a movable clock."""

    def __init__(self) -> None:
        self.settings = make_settings()
        self.clock = MutableClock()
        self.cipher = TokenCipher(self.settings.TOKEN_ENCRYPTION_KEY)
        self.provider = FakeOAuthProvider()
        self.forgotten: list[str] = []
        self.deletion = AccountDeletion(
            registry=ConnectorRegistry(self.settings),
            cipher=self.cipher,
            client=OAuthClient(self.provider.http_factory),
            forget_user=self.forgotten.append,
            clock=self.clock,
        )

    def record(
        self,
        key: str,
        *,
        access: str = "access-token",
        refresh: str | None = "refresh-token",
        expires_in: timedelta | None = timedelta(hours=1),
        corrupt: bool = False,
        user_id: str = USER,
    ) -> ConnectionRecord:
        now: datetime = self.clock()
        return ConnectionRecord(
            id=f"conn-{key}",
            user_id=user_id,
            connector_key=key,
            status="active",
            provider_account_id="acct",
            provider_account_login=None,
            provider_account_name=None,
            granted_scopes=(),
            provider_metadata=None,
            access_token_expires_at=now + expires_in if expires_in else None,
            refresh_token_expires_at=None,
            token_version=1,
            last_refreshed_at=None,
            last_error_code=None,
            created_at=now,
            updated_at=now,
            access_token_ciphertext="garbage"
            if corrupt
            else self.cipher.encrypt(access),
            refresh_token_ciphertext=(
                self.cipher.encrypt(refresh) if refresh is not None else None
            ),
        )


@pytest.fixture
def fx() -> _Fixture:
    """Deletion service, cipher and fake provider on a movable clock."""
    return _Fixture()


@pytest.fixture
def db() -> MagicMock:
    """A mocked session: ``collect`` must not touch it beyond the patched read."""
    return MagicMock(spec=Session)


def _serve(
    monkeypatch: pytest.MonkeyPatch, records: list[ConnectionRecord]
) -> list[str]:
    """Patch the locked read to return ``records``; return the user ids it was asked for."""
    asked: list[str] = []

    def _records_for_update(_db: Session, user_id: str) -> list[ConnectionRecord]:
        asked.append(user_id)
        return [r for r in records if r.user_id == user_id]

    monkeypatch.setattr(
        ConnectionStore, "records_for_update", staticmethod(_records_for_update)
    )
    return asked


class TestCollect:
    def test_collect_decrypts_tokens_of_every_connection_when_user_has_two(
        self, db: MagicMock, fx: _Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = _serve(
            monkeypatch,
            [
                fx.record("github", access="gh-access", refresh="gh-refresh"),
                fx.record("jira", access="jira-access", refresh="jira-refresh"),
            ],
        )

        grants = fx.deletion.collect(db, USER)

        assert asked == [USER]
        assert [g.connector_key for g in grants] == ["github", "jira"]
        assert all(g.attemptable for g in grants)
        assert (grants[0].access_token, grants[0].refresh_token) == (
            "gh-access",
            "gh-refresh",
        )
        assert grants[1].refresh_token == "jira-refresh"

    def test_collect_marks_not_attemptable_when_token_undecryptable(
        self, db: MagicMock, fx: _Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(monkeypatch, [fx.record("github", corrupt=True)])

        assert fx.deletion.collect(db, USER) == [
            CollectedGrant("github", attemptable=False)
        ]

    def test_collect_marks_not_attemptable_when_connector_not_configured(
        self, db: MagicMock, fx: _Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(monkeypatch, [fx.record("jira")])
        unconfigured = AccountDeletion(
            registry=ConnectorRegistry(make_settings(JIRA_OAUTH_CLIENT_ID="")),
            cipher=fx.cipher,
            client=OAuthClient(fx.provider.http_factory),
            forget_user=fx.forgotten.append,
        )

        assert unconfigured.collect(db, USER) == [
            CollectedGrant("jira", attemptable=False)
        ]

    def test_collect_marks_not_attemptable_when_connector_unknown(
        self, db: MagicMock, fx: _Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(monkeypatch, [fx.record("gone")])

        assert fx.deletion.collect(db, USER) == [
            CollectedGrant("gone", attemptable=False)
        ]

    def test_collect_returns_nothing_when_user_has_no_connections(
        self, db: MagicMock, fx: _Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(monkeypatch, [fx.record("github", user_id="user-b")])

        assert fx.deletion.collect(db, USER) == []

    def test_collect_makes_no_provider_call_and_no_session_write_when_collecting(
        self, db: MagicMock, fx: _Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(monkeypatch, [fx.record("github")])

        fx.deletion.collect(db, USER)

        assert fx.provider.requests == []
        assert db.mock_calls == []

    def test_collect_hides_tokens_from_repr_when_grant_printed(
        self, db: MagicMock, fx: _Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(
            monkeypatch,
            [
                fx.record(
                    "github", access="visible-secret-1", refresh="visible-secret-2"
                )
            ],
        )

        assert "visible-secret" not in repr(fx.deletion.collect(db, USER))

    def test_collect_propagates_database_error_when_locked_read_fails(
        self, db: MagicMock, fx: _Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sqlalchemy.exc import OperationalError

        def _boom(_db: Session, _user_id: str) -> list[ConnectionRecord]:
            raise OperationalError("SELECT", {}, Exception("lock timeout"))

        monkeypatch.setattr(ConnectionStore, "records_for_update", staticmethod(_boom))

        with pytest.raises(OperationalError):
            fx.deletion.collect(db, USER)


class TestRevoke:
    def test_revoke_deletes_github_grant_with_collected_token_when_not_expired(
        self, fx: _Fixture
    ) -> None:
        grant = CollectedGrant(
            "github",
            attemptable=True,
            access_token="gh-access",
            refresh_token="gh-refresh",
            access_token_expires_at=fx.clock() + timedelta(hours=2),
        )

        result = fx.deletion.revoke(USER, [grant])

        assert result == {"github": "revoked"}
        calls = fx.provider.calls("DELETE", GRANT_URL)
        assert [c.json_body for c in calls] == [{"access_token": "gh-access"}]
        assert fx.provider.calls("POST", GITHUB_TOKEN_URL) == []

    def test_revoke_refreshes_in_memory_first_when_github_token_near_expiry(
        self, fx: _Fixture
    ) -> None:
        fx.provider.respond(
            "POST",
            GITHUB_TOKEN_URL,
            json_response(200, github_token_body(access_token="gh-fresh")),
        )
        grant = CollectedGrant(
            "github",
            attemptable=True,
            access_token="gh-stale",
            refresh_token="gh-refresh",
            access_token_expires_at=fx.clock() + timedelta(seconds=299),
        )

        result = fx.deletion.revoke(USER, [grant])

        assert result == {"github": "revoked"}
        refresh_call = fx.provider.calls("POST", GITHUB_TOKEN_URL)[0]
        assert (refresh_call.form_body or {})["grant_type"] == "refresh_token"
        assert fx.provider.calls("DELETE", GRANT_URL)[0].json_body == {
            "access_token": "gh-fresh"
        }

    def test_revoke_reports_failed_when_github_refresh_is_rejected(
        self, fx: _Fixture
    ) -> None:
        fx.provider.respond(
            "POST", GITHUB_TOKEN_URL, json_response(200, {"error": "bad_refresh_token"})
        )
        grant = CollectedGrant(
            "github",
            attemptable=True,
            access_token="gh-stale",
            refresh_token="gh-refresh",
            access_token_expires_at=fx.clock() - timedelta(hours=1),
        )

        result = fx.deletion.revoke(USER, [grant])

        assert result == {"github": "failed"}
        assert fx.provider.calls("DELETE", GRANT_URL) == []

    def test_revoke_reports_failed_when_expired_github_token_has_no_refresh_token(
        self, fx: _Fixture
    ) -> None:
        grant = CollectedGrant(
            "github",
            attemptable=True,
            access_token="gh-stale",
            refresh_token=None,
            access_token_expires_at=fx.clock() - timedelta(hours=1),
        )

        assert fx.deletion.revoke(USER, [grant]) == {"github": "failed"}

    @pytest.mark.parametrize("status", [404, 422])
    def test_revoke_counts_already_gone_as_revoked_when_github_answers_404_or_422(
        self, fx: _Fixture, status: int
    ) -> None:
        fx.provider.respond("DELETE", GRANT_URL, empty_response(status))
        grant = CollectedGrant("github", attemptable=True, access_token="gh-access")

        assert fx.deletion.revoke(USER, [grant]) == {"github": "revoked"}

    def test_revoke_sends_refresh_token_to_atlassian_when_jira_collected(
        self, fx: _Fixture
    ) -> None:
        grant = CollectedGrant(
            "jira", attemptable=True, access_token="a", refresh_token="jira-refresh"
        )

        result = fx.deletion.revoke(USER, [grant])

        assert result == {"jira": "revoked"}
        body = fx.provider.calls("POST", ATLASSIAN_REVOKE_URL)[0].json_body or {}
        assert body["token"] == "jira-refresh"
        assert body["token_type_hint"] == "refresh_token"

    def test_revoke_reports_not_attempted_without_provider_call_when_not_attemptable(
        self, fx: _Fixture
    ) -> None:
        result = fx.deletion.revoke(USER, [CollectedGrant("github", attemptable=False)])

        assert result == {"github": "not_attempted"}
        assert fx.provider.requests == []

    def test_revoke_maps_timeout_and_server_error_to_failed_when_provider_down(
        self, fx: _Fixture
    ) -> None:
        fx.provider.respond("DELETE", GRANT_URL, timeout_response)
        fx.provider.respond("POST", ATLASSIAN_REVOKE_URL, empty_response(503))
        grants = [
            CollectedGrant("github", attemptable=True, access_token="a"),
            CollectedGrant(
                "jira", attemptable=True, access_token="b", refresh_token="c"
            ),
        ]

        result = fx.deletion.revoke(USER, grants)

        assert result == {"github": "failed", "jira": "failed"}

    def test_revoke_continues_with_next_grant_when_one_raises_unexpectedly(
        self, fx: _Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = fx.deletion._revoke_one
        calls: list[str] = []

        def _flaky(grant: CollectedGrant) -> str:
            calls.append(grant.connector_key)
            if grant.connector_key == "github":
                raise RuntimeError("boom")
            return original(grant)

        monkeypatch.setattr(fx.deletion, "_revoke_one", _flaky)
        grants = [
            CollectedGrant("github", attemptable=True, access_token="a"),
            CollectedGrant(
                "jira", attemptable=True, access_token="b", refresh_token="c"
            ),
        ]

        result = fx.deletion.revoke(USER, grants)

        assert result == {"github": "failed", "jira": "revoked"}
        assert calls == ["github", "jira"]

    def test_revoke_clears_users_tool_cache_when_done(self, fx: _Fixture) -> None:
        fx.deletion.revoke(USER, [])

        assert fx.forgotten == [USER]

    def test_revoke_does_not_raise_when_cache_clear_fails(
        self, fx: _Fixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _broken(_user_id: str) -> None:
            raise RuntimeError("cache exploded")

        deletion = AccountDeletion(
            registry=fx.deletion._registry,
            cipher=fx.cipher,
            client=OAuthClient(fx.provider.http_factory),
            forget_user=_broken,
        )

        with caplog.at_level(logging.WARNING, logger="app.connectors.account_deletion"):
            assert deletion.revoke(USER, []) == {}

        assert "cache exploded" not in caplog.text

    def test_revoke_logs_connector_and_reason_without_tokens_when_it_fails(
        self, fx: _Fixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        fx.provider.respond("DELETE", GRANT_URL, empty_response(500))
        grant = CollectedGrant(
            "github", attemptable=True, access_token="super-secret-access"
        )

        with caplog.at_level(logging.DEBUG):
            fx.deletion.revoke(USER, [grant])

        assert "connector=github" in caplog.text
        assert "super-secret-access" not in caplog.text
        assert "github-secret-sentinel" not in caplog.text
        assert "super-secret-access" not in repr(grant)

    def test_revoke_leaves_token_endpoint_unused_when_unrelated_jira_grant_revoked(
        self, fx: _Fixture
    ) -> None:
        fx.provider.respond(
            "POST", ATLASSIAN_TOKEN_URL, json_response(200, atlassian_token_body())
        )

        fx.deletion.revoke(
            USER,
            [
                CollectedGrant(
                    "jira", attemptable=True, access_token="a", refresh_token="b"
                )
            ],
        )

        assert fx.provider.calls("POST", ATLASSIAN_TOKEN_URL) == []
