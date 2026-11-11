"""``AccountDeletion.collect`` against a real (SQLite) session.

The locked read must return only the deleting user's connections, decrypt their
tokens and write nothing. ``FOR UPDATE`` itself is a PostgreSQL feature, proven in
``tests/integration/db/test_user_deletion_connectors_db.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.connectors.account_deletion import AccountDeletion, CollectedGrant
from app.connectors.crypto import TokenCipher
from app.connectors.oauth import OAuthClient
from app.connectors.registry import ConnectorRegistry
from app.models.connector import ConnectorConnection
from app.models.database import Base
from app.models.user import User
from tests.factories.connector_factory import ConnectorConnectionFactory
from tests.fakes.connector_settings import make_settings
from tests.fakes.oauth_provider import FakeOAuthProvider


@pytest.fixture
def db() -> Iterator[Session]:
    """A SQLite session with every table and two users."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    session.add(User(id="user-a", email="a@example.com", cognito_sub="sub-a"))
    session.add(User(id="user-b", email="b@example.com", cognito_sub="sub-b"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def cipher() -> TokenCipher:
    """A cipher on a generated key."""
    return TokenCipher(make_settings().TOKEN_ENCRYPTION_KEY)


def _deletion(cipher: TokenCipher) -> AccountDeletion:
    return AccountDeletion(
        registry=ConnectorRegistry(make_settings()),
        cipher=cipher,
        client=OAuthClient(FakeOAuthProvider().http_factory),
        forget_user=lambda _user_id: None,
    )


def _seed(db: Session, cipher: TokenCipher, user_id: str, key: str, token: str) -> None:
    db.add(
        ConnectorConnectionFactory.build(
            user_id=user_id,
            connector_key=key,
            access_token_ciphertext=cipher.encrypt(token),
            refresh_token_ciphertext=cipher.encrypt(f"{token}-refresh"),
        )
    )
    db.commit()


class TestCollect:
    def test_collect_returns_only_the_users_decrypted_grants_when_two_users_have_connections(
        self, db: Session, cipher: TokenCipher
    ) -> None:
        _seed(db, cipher, "user-a", "github", "a-gh")
        _seed(db, cipher, "user-a", "jira", "a-jira")
        _seed(db, cipher, "user-b", "github", "b-gh")

        grants = _deletion(cipher).collect(db, "user-a")

        assert [(g.connector_key, g.access_token) for g in grants] == [
            ("github", "a-gh"),
            ("jira", "a-jira"),
        ]
        assert grants[0].refresh_token == "a-gh-refresh"

    def test_collect_writes_nothing_when_reading_connections(
        self, db: Session, cipher: TokenCipher
    ) -> None:
        _seed(db, cipher, "user-a", "github", "a-gh")
        statements: list[str] = []
        event.listen(
            db.get_bind(),
            "before_cursor_execute",
            lambda _conn, _cur, statement, *_rest: statements.append(statement),
        )

        _deletion(cipher).collect(db, "user-a")

        writes = [
            s
            for s in statements
            if s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        assert writes == []
        assert db.query(ConnectorConnection).count() == 1

    def test_collect_marks_not_attemptable_when_ciphertext_is_garbage(
        self, db: Session, cipher: TokenCipher
    ) -> None:
        db.add(
            ConnectorConnectionFactory.build(
                user_id="user-a",
                connector_key="github",
                access_token_ciphertext="not-a-fernet-token",
            )
        )
        db.commit()

        assert _deletion(cipher).collect(db, "user-a") == [
            CollectedGrant("github", attemptable=False)
        ]

    def test_collect_returns_expiry_of_access_token_when_connection_has_one(
        self, db: Session, cipher: TokenCipher
    ) -> None:
        expiry = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
        db.add(
            ConnectorConnectionFactory.build(
                user_id="user-a",
                connector_key="github",
                access_token_ciphertext=cipher.encrypt("t"),
                refresh_token_ciphertext=None,
                access_token_expires_at=expiry,
            )
        )
        db.commit()

        (grant,) = _deletion(cipher).collect(db, "user-a")

        assert grant.access_token_expires_at == expiry
        assert grant.refresh_token is None
