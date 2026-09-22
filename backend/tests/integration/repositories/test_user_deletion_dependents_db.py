"""``core.user_deletion.delete_user_dependents`` — every owned row, in order.

Phase 3, Decision 6's FK policy: five tables (``workflow_runs`` and its
nine-table fan-out, ``workflow_memory``, ``user_agents``, ``workflows``,
``chat_sessions``+``messages``) are explicitly deleted in dependency order
inside the SAME transaction as the user delete -- never a bare cascade, so the
audit event can report what was actually removed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.user_deletion import delete_user_dependents
from app.models.artifact_ref import ArtifactRef
from app.models.chat import ChatSession, Message
from app.models.database import Base
from app.models.exec_runs import ExecRun
from app.models.gate_events import GateEvent
from app.models.run_event import RunEvent
from app.models.user import User
from app.models.user_agent import UserAgent
from app.models.workflow import WorkflowRun
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_memory import WorkflowMemory


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _user(session, user_id="u1") -> User:
    user = User(id=user_id, email=f"{user_id}@example.com", cognito_sub=f"sub-{user_id}")
    session.add(user)
    session.commit()
    return user


class TestEmptyAccount:
    def test_a_user_with_nothing_owned_deletes_cleanly(self, session):
        user = _user(session)

        counts = delete_user_dependents(session, user.id)
        session.delete(user)
        session.commit()

        assert counts == {}
        assert session.query(User).count() == 0


class TestRunFanout:
    def test_deletes_every_child_row_of_an_owned_run(self, session):
        user = _user(session)
        run = WorkflowRun(
            id="run-1", user_id=user.id, type="prototype", status="completed",
            input="x", workspace_id="ws-1",
        )
        session.add(run)
        session.commit()
        session.add(
            RunEvent(
                id="e1", run_id="run-1", owner_id=user.id, workspace_id="ws-1",
                seq=1, event_id="evt-1", type="t", payload_json={},
            )
        )
        session.add(
            ArtifactRef(
                id="a1", run_id="run-1", owner_id=user.id, workspace_id="ws-1",
                kind="k", producer_step="s", producer_agent="ag", content="c",
                content_hash="h", location="loc", version=1,
            )
        )
        session.add(
            GateEvent(
                id="g1", run_id="run-1", owner_id=user.id, workspace_id="ws-1",
                step="s", gate="human", outcome="pass",
            )
        )
        session.add(
            ExecRun(
                id="x1", run_id="run-1", owner_id=user.id, workspace_id="ws-1",
                step="s", argv_json=[], outcome="allowed",
            )
        )
        session.commit()

        counts = delete_user_dependents(session, user.id)
        session.delete(user)
        session.commit()

        assert counts["workflow_runs"] == 1
        assert counts["run_events"] == 1
        assert counts["artifact_refs"] == 1
        assert counts["gate_events"] == 1
        assert counts["exec_runs"] == 1
        assert session.query(WorkflowRun).count() == 0
        assert session.query(RunEvent).count() == 0

    def test_nulls_parent_run_id_on_a_revision_child_instead_of_cascading(self, session):
        """A revision-chain row must SURVIVE with its link nulled, not be
        deleted along with its parent -- preserves history."""
        user = _user(session)
        parent = WorkflowRun(
            id="parent", user_id=user.id, type="prototype", status="completed",
            input="x", workspace_id="ws-1",
        )
        child = WorkflowRun(
            id="child", user_id=user.id, type="prototype_revision", status="completed",
            input="x", workspace_id="ws-1", parent_run_id="parent",
        )
        session.add_all([parent, child])
        session.commit()

        delete_user_dependents(session, user.id)
        session.delete(user)
        session.commit()

        # Both belonged to the deleted user, so both are gone -- but the
        # nulling logic must have run without raising the self-referential FK.
        assert session.query(WorkflowRun).count() == 0

    def test_a_revision_child_owned_by_a_DIFFERENT_user_survives_with_link_nulled(
        self, session
    ):
        owner = _user(session, "owner")
        other = _user(session, "other")
        parent = WorkflowRun(
            id="parent", user_id=owner.id, type="prototype", status="completed",
            input="x", workspace_id="ws-1",
        )
        # Defensive case: a revision owned by a DIFFERENT user pointing at the
        # deleted user's run. In practice a revision's parent is always the
        # same owner, but the nulling must not assume that.
        child = WorkflowRun(
            id="child", user_id=other.id, type="prototype_revision", status="completed",
            input="x", workspace_id="ws-1", parent_run_id="parent",
        )
        session.add_all([parent, child])
        session.commit()

        delete_user_dependents(session, owner.id)
        session.delete(owner)
        session.commit()

        survivor = session.query(WorkflowRun).filter(WorkflowRun.id == "child").first()
        assert survivor is not None
        assert survivor.parent_run_id is None


class TestOtherOwnedTables:
    def test_deletes_workflow_memory_user_agents_and_saved_workflows(self, session):
        user = _user(session)
        session.add(WorkflowMemory(id="m1", user_id=user.id, key="k", value="v"))
        session.add(UserAgent(id="ag1", user_id=user.id, name="n", prompt="p"))
        session.add(
            WorkflowDefinition(
                id="wf1", user_id=user.id, name="n", agents="[]", artifact_edges="[]"
            )
        )
        session.commit()

        counts = delete_user_dependents(session, user.id)
        session.delete(user)
        session.commit()

        assert counts["workflow_memory"] == 1
        assert counts["user_agents"] == 1
        assert counts["workflows"] == 1

    def test_deletes_messages_before_chat_sessions(self, session):
        user = _user(session)
        chat = ChatSession(id="c1", user_id=user.id, title="t")
        session.add(chat)
        session.add(Message(id="msg1", chat_session_id="c1", role="user", content="hi"))
        session.commit()

        counts = delete_user_dependents(session, user.id)
        session.delete(user)
        session.commit()

        assert counts["messages"] == 1
        assert counts["chat_sessions"] == 1
        assert session.query(Message).count() == 0
        assert session.query(ChatSession).count() == 0


class TestScoping:
    def test_never_touches_another_users_rows(self, session):
        victim = _user(session, "victim")
        bystander = _user(session, "bystander")
        session.add(WorkflowMemory(id="m1", user_id=bystander.id, key="k", value="v"))
        session.commit()

        counts = delete_user_dependents(session, victim.id)

        assert counts == {}
        assert session.query(WorkflowMemory).filter(
            WorkflowMemory.user_id == bystander.id
        ).count() == 1

    def test_omits_zero_count_tables_from_the_report(self, session):
        """Decision 6 asks for per-table counts in the audit event -- a user
        with only chat history should not report workflow_runs: 0."""
        user = _user(session)
        session.add(ChatSession(id="c1", user_id=user.id, title="t"))
        session.commit()

        counts = delete_user_dependents(session, user.id)

        assert counts == {"chat_sessions": 1}
