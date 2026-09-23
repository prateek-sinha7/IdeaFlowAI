"""tests/unit/test_duplicate_context_guard.py — duplicate-context guard
(Task 11.9, Requirement 21 AC 10, sandbox-git-versioning-v2).

Validates the server-side guard in _launch_run_core (run_commands.py task 9.3):

  When a launch carries BOTH `source_workflow_run_id` AND a legacy
  "=== CONTEXT FROM PREVIOUS PIPELINE ===" block in the message body:
    - The legacy block is STRIPPED from the content before the run is minted
    - The strip is recorded as a `legacy_context_block_stripped` audit row
    - The run IS minted (the strip does not abort the launch)
    - The minted run's content does not contain the context block

  When the launch carries ONLY the legacy context block (no source_workflow_run_id):
    - The block is PRESERVED (plain legacy run, block is its chain mechanism)

  When the launch carries ONLY source_workflow_run_id (no legacy block):
    - No strip occurs; no audit row for this strip operation

Tests drive the run_commands router with an in-memory SQLite session,
recording-engine stub, and a seeded user — same pattern as test_rest_run_launch.py.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register models before create_all
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import app.models.run_finalization  # noqa: F401
import app.models.run_provenance_audit  # noqa: F401
import app.models.user  # noqa: F401
import agents.execution_engine.engine as engine_mod

from app.models.run_provenance_audit import RunProvenanceAudit
from app.models.workflow import WorkflowRun

_LEGACY_MARKER = "=== CONTEXT FROM PREVIOUS PIPELINE"
_LEGACY_BLOCK = (
    f"\n{_LEGACY_MARKER} ===\n\nThis is the old context from the source run.\n"
    "It contains some design information.\n"
)


class _FakeUser:
    def __init__(self, id: str, tier: str = "enterprise"):
        self.id = id
        self.preferred_model = None
        self.tier = tier


class _RecordingEngine:
    """Stub engine recording execute() kwargs and emitting a minimal terminal stream."""
    last_kwargs: dict | None = None
    invoked = False

    async def execute(self, **kwargs):
        _RecordingEngine.invoked = True
        _RecordingEngine.last_kwargs = kwargs
        yield {"type": "pipeline_start", "data": {"agents": []}}
        yield {"type": "pipeline_complete", "data": {"final_output": "done"}}


@pytest.fixture
def env(monkeypatch):
    from app.api import run_engine as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)

    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    import app.api.run_commands as rc_module
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())

    _RecordingEngine.invoked = False
    _RecordingEngine.last_kwargs = None
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _RecordingEngine())

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {
        "ws": ws_module,
        "client": client,
        "state": state,
        "Session": TestingSession,
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env) -> _FakeUser:
    from app.models.user import User

    db = env["ws"]._get_db()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_source_run(env, user_id: str) -> WorkflowRun:
    """Seed a source run owned by user_id so source_workflow_run_id validation passes."""
    db = env["ws"]._get_db()
    try:
        run = WorkflowRun(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title="Source run",
            type="user_stories",
            status="completed",
            input="build backlog",
            output="some output",
            agent_count=3,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    finally:
        db.close()


def _count_strip_audits(env, user_id: str) -> int:
    db = env["ws"]._get_db()
    try:
        return (
            db.query(RunProvenanceAudit)
            .filter(
                RunProvenanceAudit.owner_id == user_id,
                RunProvenanceAudit.operation == "legacy_context_block_stripped",
            )
            .count()
        )
    finally:
        db.close()


def _latest_run_content(env) -> str | None:
    """Read the input/content from the most recently created WorkflowRun."""
    db = env["ws"]._get_db()
    try:
        run = (
            db.query(WorkflowRun)
            .order_by(WorkflowRun.created_at.desc())
            .first()
        )
        return run.input if run else None
    finally:
        db.close()


def _post_launch(env, **body):
    return env["client"].post("/api/runs", json=body)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Both source_workflow_run_id AND legacy block → block stripped
# ─────────────────────────────────────────────────────────────────────────────

class TestDuplicateContextStripped:
    def test_legacy_block_stripped_when_source_run_id_present(self, env):
        """An older frontend that sends both must have the block stripped."""
        user = _seed_user(env)
        env["state"]["user"] = user
        source_run = _seed_source_run(env, user.id)

        brief = "Build me a user-stories backlog"
        # Older frontend appends the legacy context block after the brief
        message = brief + _LEGACY_BLOCK

        resp = _post_launch(
            env,
            message=message,
            pipeline_type="user_stories",
            source_workflow_run_id=source_run.id,
        )
        # Run is minted (strip does not abort the launch)
        assert resp.status_code == 200, resp.text

        # The persisted content must NOT contain the legacy marker
        content = _latest_run_content(env)
        assert content is not None
        assert _LEGACY_MARKER not in content, (
            "Legacy context block was NOT stripped from the persisted content"
        )

    def test_brief_preserved_after_strip(self, env):
        """The user's brief (before the context block) is preserved after stripping."""
        user = _seed_user(env)
        env["state"]["user"] = user
        source_run = _seed_source_run(env, user.id)

        brief = "Generate a sprint backlog for the login feature"
        message = brief + _LEGACY_BLOCK

        resp = _post_launch(
            env,
            message=message,
            pipeline_type="user_stories",
            source_workflow_run_id=source_run.id,
        )
        assert resp.status_code == 200, resp.text

        content = _latest_run_content(env)
        assert content is not None
        # The brief text must survive
        assert "sprint backlog" in content

    def test_strip_audit_row_recorded(self, env):
        """A legacy_context_block_stripped audit row is created for the strip event."""
        user = _seed_user(env)
        env["state"]["user"] = user
        source_run = _seed_source_run(env, user.id)

        resp = _post_launch(
            env,
            message="Some brief" + _LEGACY_BLOCK,
            pipeline_type="user_stories",
            source_workflow_run_id=source_run.id,
        )
        assert resp.status_code == 200, resp.text

        count = _count_strip_audits(env, user.id)
        assert count >= 1, (
            "Expected a legacy_context_block_stripped audit row, found none"
        )

    def test_strip_audit_row_references_source_run(self, env):
        """The audit row's source_ref is the source_workflow_run_id."""
        user = _seed_user(env)
        env["state"]["user"] = user
        source_run = _seed_source_run(env, user.id)

        resp = _post_launch(
            env,
            message="Some brief" + _LEGACY_BLOCK,
            pipeline_type="user_stories",
            source_workflow_run_id=source_run.id,
        )
        assert resp.status_code == 200, resp.text

        db = env["ws"]._get_db()
        try:
            row = (
                db.query(RunProvenanceAudit)
                .filter(
                    RunProvenanceAudit.owner_id == user.id,
                    RunProvenanceAudit.operation == "legacy_context_block_stripped",
                )
                .first()
            )
            assert row is not None
            assert row.source_ref == source_run.id
            assert row.outcome == "stripped"
        finally:
            db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Only legacy block (no source_workflow_run_id) → block is PRESERVED
# ─────────────────────────────────────────────────────────────────────────────

class TestLegacyBlockPreservedWithoutSourceId:
    def test_legacy_block_not_stripped_without_source_run_id(self, env):
        """A plain legacy run that only has the context block keeps it intact."""
        user = _seed_user(env)
        env["state"]["user"] = user

        brief = "Old chained launch without v2 source_run_id"
        message = brief + _LEGACY_BLOCK

        resp = _post_launch(
            env,
            message=message,
            pipeline_type="user_stories",
            # NO source_workflow_run_id — plain legacy chain
        )
        assert resp.status_code == 200, resp.text

        # Guard fires ONLY when source_workflow_run_id is set — verify no audit row
        count = _count_strip_audits(env, user.id)
        assert count == 0, (
            "No strip audit should be created for a plain legacy launch"
        )

    def test_run_minted_with_legacy_block_intact(self, env):
        """Legacy block content survives when no source_workflow_run_id is set."""
        user = _seed_user(env)
        env["state"]["user"] = user

        message = "Old-style brief" + _LEGACY_BLOCK
        resp = _post_launch(
            env,
            message=message,
            pipeline_type="user_stories",
        )
        assert resp.status_code == 200, resp.text
        # Run was minted
        assert _RecordingEngine.invoked is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. Only source_workflow_run_id (no legacy block) → no strip, no audit row
# ─────────────────────────────────────────────────────────────────────────────

class TestSourceRunIdOnlyNoStrip:
    def test_no_strip_without_legacy_block(self, env):
        """A v2-native launch (source_run_id only, no legacy block) creates no strip row."""
        user = _seed_user(env)
        env["state"]["user"] = user
        source_run = _seed_source_run(env, user.id)

        resp = _post_launch(
            env,
            message="Clean v2 brief with no context block",
            pipeline_type="user_stories",
            source_workflow_run_id=source_run.id,
        )
        assert resp.status_code == 200, resp.text

        count = _count_strip_audits(env, user.id)
        assert count == 0, (
            "No strip audit row expected for a clean v2 launch without a legacy block"
        )

    def test_v2_native_launch_content_unchanged(self, env):
        """Message content is unchanged for a v2-native launch."""
        user = _seed_user(env)
        env["state"]["user"] = user
        source_run = _seed_source_run(env, user.id)

        brief = "Generate a user story for checkout flow"
        resp = _post_launch(
            env,
            message=brief,
            pipeline_type="user_stories",
            source_workflow_run_id=source_run.id,
        )
        assert resp.status_code == 200, resp.text
        content = _latest_run_content(env)
        assert content is not None
        assert "checkout flow" in content
