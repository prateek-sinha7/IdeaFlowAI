"""tests/unit/test_restore_guard_v3.py — family-scoped restore guard (FR-057).

Restore's active-run guard should be family-scoped, not user-wide (Requirement 9 AC 5).
An unrelated active run of the same user must NOT block restore on a terminal family;
an active family member MUST block restore.

Offline — in-memory SQLite (StaticPool) testing the _has_active_family_member function.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table touched
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
from app.models.database import Base
from app.models.workflow import WorkflowRun


class TestRestoreGuardFamilyScoped:
    """Restore guard should be family-scoped, not user-wide."""

    def test_unrelated_active_run_does_not_block(self):
        """
        Unit test: _has_active_family_member should return False when
        an unrelated active run exists, but this family is terminal.
        """
        db_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        Base.metadata.create_all(bind=db_engine)
        db = TestingSession()

        try:
            from app.api.runs import _has_active_family_member

            user_id = str(uuid.uuid4())

            # Family 1: completed root with completed revision
            family1_root = str(uuid.uuid4())
            family1_revision = str(uuid.uuid4())
            db.add(WorkflowRun(
                id=family1_root, user_id=user_id, owner_id=user_id,
                title="root", type="user_stories", status="completed",
                input="brief", agent_count=1,
            ))
            db.add(WorkflowRun(
                id=family1_revision, user_id=user_id, owner_id=user_id,
                title="revision", type="user_stories_revision", status="completed",
                input="brief", agent_count=1, parent_run_id=family1_root,
            ))
            db.commit()

            # Family 2: unrelated, active run
            family2_root = str(uuid.uuid4())
            db.add(WorkflowRun(
                id=family2_root, user_id=user_id, owner_id=user_id,
                title="unrelated", type="user_stories", status="running",
                input="brief", agent_count=1,
            ))
            db.commit()

            # The guard for family 1 should return False (no active members)
            # despite the active run in family 2
            result = _has_active_family_member(db, family1_root, user_id)
            assert result is False, "Unrelated active run should NOT block restore"

        finally:
            db.close()
            Base.metadata.drop_all(bind=db_engine)
            db_engine.dispose()

    def test_active_family_member_blocks(self):
        """
        Unit test: _has_active_family_member should return True when
        any family member is non-terminal.
        """
        db_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        Base.metadata.create_all(bind=db_engine)
        db = TestingSession()

        try:
            from app.api.runs import _has_active_family_member

            user_id = str(uuid.uuid4())

            # Family: completed root with active (running) revision
            family_root = str(uuid.uuid4())
            family_revision = str(uuid.uuid4())
            db.add(WorkflowRun(
                id=family_root, user_id=user_id, owner_id=user_id,
                title="root", type="user_stories", status="completed",
                input="brief", agent_count=1,
            ))
            db.add(WorkflowRun(
                id=family_revision, user_id=user_id, owner_id=user_id,
                title="revision", type="user_stories_revision", status="running",
                input="brief", agent_count=1, parent_run_id=family_root,
            ))
            db.commit()

            # The guard for this family should return True (has active member)
            result = _has_active_family_member(db, family_root, user_id)
            assert result is True, "Active family member should block restore"

        finally:
            db.close()
            Base.metadata.drop_all(bind=db_engine)
            db_engine.dispose()

    def test_all_terminal_statuses_allow(self):
        """
        Unit test: _has_active_family_member should return False for all
        terminal statuses (completed, failed, cancelled, degraded, diverted).
        """
        db_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        Base.metadata.create_all(bind=db_engine)
        db = TestingSession()

        try:
            from app.api.runs import _has_active_family_member

            user_id = str(uuid.uuid4())
            family_root = str(uuid.uuid4())

            # Seed a root
            db.add(WorkflowRun(
                id=family_root, user_id=user_id, owner_id=user_id,
                title="root", type="user_stories", status="completed",
                input="brief", agent_count=1,
            ))
            db.commit()

            # Add revisions with all terminal statuses
            for status in ["completed", "failed", "cancelled", "degraded", "diverted"]:
                revision_id = str(uuid.uuid4())
                db.add(WorkflowRun(
                    id=revision_id, user_id=user_id, owner_id=user_id,
                    title=f"revision-{status}", type="user_stories_revision",
                    status=status, input="brief", agent_count=1,
                    parent_run_id=family_root,
                ))
            db.commit()

            # All revisions are terminal, so the family should have no active members
            result = _has_active_family_member(db, family_root, user_id)
            assert result is False, "Family with all terminal statuses should not be active"

        finally:
            db.close()
            Base.metadata.drop_all(bind=db_engine)
            db_engine.dispose()

    def test_any_non_terminal_status_blocks(self):
        """
        Unit test: _has_active_family_member should return True for any
        non-terminal status in the family.
        """
        non_terminal_statuses = [
            "running", "planning", "clarifying", "generating",
            "analyzing", "revising", "waiting_for_user"
        ]

        from app.api.runs import _has_active_family_member

        for status in non_terminal_statuses:
            db_engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
            Base.metadata.create_all(bind=db_engine)
            db = TestingSession()

            try:
                user_id = str(uuid.uuid4())
                family_root = str(uuid.uuid4())
                family_revision = str(uuid.uuid4())

                # Seed root and revision with this status
                db.add(WorkflowRun(
                    id=family_root, user_id=user_id, owner_id=user_id,
                    title="root", type="user_stories", status="completed",
                    input="brief", agent_count=1,
                ))
                db.add(WorkflowRun(
                    id=family_revision, user_id=user_id, owner_id=user_id,
                    title="revision", type="user_stories_revision", status=status,
                    input="brief", agent_count=1, parent_run_id=family_root,
                ))
                db.commit()

                # This family has an active member
                result = _has_active_family_member(db, family_root, user_id)
                assert result is True, f"Family with {status} should be active"

            finally:
                db.close()
                Base.metadata.drop_all(bind=db_engine)
                db_engine.dispose()
