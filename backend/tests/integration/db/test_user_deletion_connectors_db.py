"""Account deletion and the connector tables, on real PostgreSQL.

SQLite does not enforce the migration's foreign keys or row locks the way PostgreSQL
does, so the delete order, the ``FOR UPDATE`` taken by ``AccountDeletion.collect`` and
the all-or-nothing rollback are proven here. The database is a private throwaway one
upgraded to Alembic head (``PYTEST_POSTGRES_ADMIN_URL``, else the testcontainers
server, which needs Docker).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.account_deletion import AccountDeletion
from app.connectors.crypto import TokenCipher
from app.connectors.oauth import OAuthClient
from app.connectors.registry import ConnectorRegistry
from app.core.user_deletion import delete_user_dependents
from app.models.connector import ConnectorAuditLog, ConnectorConnection, OAuthState
from app.models.user import User
from tests.factories.connector_factory import (
    ConnectorConnectionFactory,
    OAuthStateFactory,
)
from tests.fakes.connector_settings import make_settings
from tests.fakes.oauth_provider import FakeOAuthProvider
from tests.integration.db.conftest import (
    alembic_config_for,
    postgres_admin_url,
    throwaway_database,
)

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def pg_engine(request: pytest.FixtureRequest) -> Generator[Engine, None, None]:
    """Engine on a throwaway PostgreSQL database migrated to Alembic head."""
    with throwaway_database(postgres_admin_url(request), "conndelete") as url:
        command.upgrade(alembic_config_for(url), "head")
        engine = create_engine(url, pool_pre_ping=True)
        try:
            yield engine
        finally:
            engine.dispose()


@pytest.fixture
def pg_session(pg_engine: Engine) -> Generator[Session, None, None]:
    """A session on the throwaway database."""
    db = sessionmaker(bind=pg_engine, autoflush=False, autocommit=False)()
    try:
        yield db
    finally:
        db.close()


def _add_user(db: Session, user_id: str) -> User:
    user = User(
        id=user_id, email=f"{user_id}@example.com", cognito_sub=f"sub-{user_id}"
    )
    db.add(user)
    db.commit()
    return user


def _seed(db: Session, cipher: TokenCipher, user_id: str) -> None:
    db.add(
        ConnectorConnectionFactory.build(
            user_id=user_id,
            connector_key="github",
            access_token_ciphertext=cipher.encrypt("gh-access"),
            refresh_token_ciphertext=cipher.encrypt("gh-refresh"),
        )
    )
    db.add(
        ConnectorConnectionFactory.build(
            user_id=user_id,
            connector_key="jira",
            access_token_ciphertext=cipher.encrypt("jira-access"),
            refresh_token_ciphertext=cipher.encrypt("jira-refresh"),
        )
    )
    db.add(OAuthStateFactory.build(user_id=user_id))
    db.add(
        ConnectorAuditLog(
            user_id=user_id, connector_key="jira", action="connected", outcome="ok"
        )
    )
    db.commit()


def _deletion(cipher: TokenCipher) -> AccountDeletion:
    return AccountDeletion(
        registry=ConnectorRegistry(make_settings()),
        cipher=cipher,
        client=OAuthClient(FakeOAuthProvider().http_factory),
        forget_user=lambda _user_id: None,
    )


@pytest.fixture
def cipher() -> TokenCipher:
    """A cipher on a generated key."""
    return TokenCipher(make_settings().TOKEN_ENCRYPTION_KEY)


class TestDeleteOrder:
    def test_collect_then_delete_commits_in_one_transaction_when_user_has_connections(
        self, pg_session: Session, cipher: TokenCipher
    ) -> None:
        user = _add_user(pg_session, "u1")
        _add_user(pg_session, "bystander")
        _seed(pg_session, cipher, "u1")
        _seed(pg_session, cipher, "bystander")

        grants = _deletion(cipher).collect(pg_session, "u1")
        counts = delete_user_dependents(pg_session, "u1")
        pg_session.delete(user)
        pg_session.commit()

        assert [g.connector_key for g in grants] == ["github", "jira"]
        assert counts == {
            "connector_audit_log": 1,
            "oauth_states": 1,
            "connector_connections": 2,
        }
        assert pg_session.query(User).filter_by(id="u1").count() == 0
        assert pg_session.query(ConnectorConnection).count() == 2  # bystander's
        assert pg_session.query(OAuthState).filter_by(user_id="bystander").count() == 1

    def test_rollback_keeps_every_connector_row_when_transaction_fails(
        self, pg_session: Session, cipher: TokenCipher
    ) -> None:
        user = _add_user(pg_session, "u1")
        _seed(pg_session, cipher, "u1")

        _deletion(cipher).collect(pg_session, "u1")
        delete_user_dependents(pg_session, "u1")
        pg_session.delete(user)
        pg_session.rollback()

        assert (
            pg_session.query(ConnectorConnection).filter_by(user_id="u1").count() == 2
        )
        assert pg_session.query(OAuthState).filter_by(user_id="u1").count() == 1
        assert pg_session.query(ConnectorAuditLog).filter_by(user_id="u1").count() == 1
        assert pg_session.query(User).filter_by(id="u1").count() == 1

    def test_user_delete_cascades_connector_rows_when_dependents_not_deleted_first(
        self, pg_session: Session, cipher: TokenCipher
    ) -> None:
        user = _add_user(pg_session, "u1")
        _seed(pg_session, cipher, "u1")

        pg_session.delete(user)
        pg_session.commit()

        assert pg_session.query(ConnectorConnection).count() == 0
        assert pg_session.query(OAuthState).count() == 0
        assert pg_session.query(ConnectorAuditLog).count() == 0


class TestCollectLock:
    def test_collect_holds_row_lock_until_transaction_ends_when_collecting(
        self, pg_engine: Engine, pg_session: Session, cipher: TokenCipher
    ) -> None:
        _add_user(pg_session, "u1")
        _seed(pg_session, cipher, "u1")

        _deletion(cipher).collect(pg_session, "u1")  # transaction stays open

        with pg_engine.connect() as other:
            with pytest.raises(OperationalError):
                other.execute(
                    text(
                        "SELECT id FROM connector_connections "
                        "WHERE user_id = :u FOR UPDATE NOWAIT"
                    ),
                    {"u": "u1"},
                )
        pg_session.rollback()
