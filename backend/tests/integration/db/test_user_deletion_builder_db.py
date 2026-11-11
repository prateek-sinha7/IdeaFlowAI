"""``delete_user_dependents`` and the AI Workflow Builder tables, on real PostgreSQL.

Replaces the builder case that ran on SQLite in
``tests/integration/repositories/test_user_deletion_dependents_db.py``. SQLite does
not enforce the migration's foreign keys the way PostgreSQL does, so a wrong delete
order would pass there and fail here. The database is a private throwaway one
upgraded to Alembic head (``PYTEST_POSTGRES_ADMIN_URL``, else the testcontainers
server, which needs Docker).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from alembic import command
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.user_deletion import delete_user_dependents
from app.models.user import User
from app.models.workflow_builder import (
    WorkflowBuilderDraft,
    WorkflowBuilderMessage,
    WorkflowBuilderSession,
)
from tests.integration.db.conftest import (
    alembic_config_for,
    postgres_admin_url,
    throwaway_database,
)

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def pg_session(request: pytest.FixtureRequest) -> Generator[Session, None, None]:
    """Session on a throwaway PostgreSQL database migrated to Alembic head."""
    with throwaway_database(postgres_admin_url(request), "wbdelete") as url:
        command.upgrade(alembic_config_for(url), "head")
        engine = create_engine(url, pool_pre_ping=True)
        db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
        try:
            yield db
        finally:
            db.close()
            engine.dispose()


def _add_user(db: Session, user_id: str) -> User:
    """Insert and commit one user."""
    user = User(
        id=user_id, email=f"{user_id}@example.com", cognito_sub=f"sub-{user_id}"
    )
    db.add(user)
    db.commit()
    return user


def _add_builder_rows(db: Session, owner: User, session_id: str) -> None:
    """Insert one session, one message and one draft owned by ``owner``."""
    db.add(
        WorkflowBuilderSession(
            id=session_id,
            user_id=owner.id,
            owner_id=owner.id,
            workspace_id=owner.id,
            title="t",
            mode="create",
            skill_hash="h",
        )
    )
    db.commit()
    db.add(
        WorkflowBuilderMessage(
            id=f"{session_id}-m",
            session_id=session_id,
            user_id=owner.id,
            owner_id=owner.id,
            workspace_id=owner.id,
            seq=1,
            role="user",
            turn_id=f"{session_id}-t",
            status="accepted",
            content="hi",
        )
    )
    db.add(
        WorkflowBuilderDraft(
            id=f"{session_id}-d",
            session_id=session_id,
            user_id=owner.id,
            owner_id=owner.id,
            workspace_id=owner.id,
            revision=0,
            kind="seed",
            manifest={},
            manifest_hash="x",
        )
    )
    db.commit()


class TestDeleteUserDependentsBuilderRows:
    def test_delete_user_dependents_removes_builder_rows_when_user_owns_them(
        self, pg_session: Session
    ) -> None:
        user = _add_user(pg_session, "u1")
        bystander = _add_user(pg_session, "bystander")
        _add_builder_rows(pg_session, user, "wbs-1")
        _add_builder_rows(pg_session, bystander, "wbs-2")

        counts = delete_user_dependents(pg_session, user.id)
        pg_session.delete(user)
        pg_session.commit()

        assert counts == {
            "workflow_builder_messages": 1,
            "workflow_builder_drafts": 1,
            "workflow_builder_sessions": 1,
        }
        assert [s.user_id for s in pg_session.query(WorkflowBuilderSession)] == [
            bystander.id
        ]
        assert [m.user_id for m in pg_session.query(WorkflowBuilderMessage)] == [
            bystander.id
        ]
        assert [d.user_id for d in pg_session.query(WorkflowBuilderDraft)] == [
            bystander.id
        ]
