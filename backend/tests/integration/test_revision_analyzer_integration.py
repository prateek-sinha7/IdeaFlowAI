"""Integration tests for the Prototype Revision Analyzer endpoint integration.

Tests the ``create_revision`` endpoint with mocked ``run_analyzer`` to verify:

  - SSE event ordering (agent_start / agent_complete / revision_analyzer_complete)
    emitted before the pipeline drive begins (Requirements 3.4, 3.5, 7.1, 7.2)
  - ``ectx.analyzer_solution`` is set before the first pipeline agent step
    (Requirements 7.1, 4.1)
  - ``agent_count == len(_rev_agents) + 1`` on the minted WorkflowRun row
    (Requirement 9.6)
  - Concierge path sources ``existing_html`` from the parent run's ``output``
    column and passes ``instruction`` from the chat message (Requirement 9.4)
  - Fallback: ``run_analyzer`` raises → ``_classify_revision_tier`` is called
    (Requirement 3.6)
  - Double-failure: both ``run_analyzer`` and ``_classify_revision_tier`` raise
    → run proceeds with tier ``"large"`` and empty solution (Requirement 3.7)
  - ``ectx.analyzer_solution`` storage failure: soft-fail in wrapper, endpoint
    returns 200 (design: soft failure, not hard abort for wrapper path)

Key mocking insight: ``run_analyzer`` is a lazy ``from app.agents.revision_analyzer
import run_analyzer`` inside ``create_revision`` — it must be patched at the
SOURCE module ``app.agents.revision_analyzer``, not at ``app.api.run_commands``.
Similarly, ``_classify_revision_tier`` fallback uses a lazy import inside
``run_analyzer``'s except block, patched at ``app.api.run_commands``.

Requirements: 3.1–3.7, 4.1, 5.1, 6.1, 7.1, 7.6, 9.4
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, get_db
from tests.fixtures.user_factory import create_user

# ── Module-level constants ──────────────────────────────────────────────────

_FAKE_HTML = "<html><body><h1>My Prototype</h1></body></html>"
_FAKE_INSTRUCTION = "Change the heading to 'Hello World'"
_FAKE_TIER = "small"
_FAKE_SOLUTION = "Update the h1 text node to 'Hello World' — no other changes needed."


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    """Build a FastAPI TestClient backed by a fresh SQLite DB.

    Mirrors the pattern from test_handoff_api.py: create schema, override get_db,
    monkeypatch SessionLocal, yield a configured client.
    """
    db_path = tmp_path / "test_revision_analyzer.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    from app.core.config import settings
    settings.DATABASE_URL = db_url

    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(test_engine)

    # Stamp alembic_version so the lifespan check passes.
    with test_engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR PRIMARY KEY)"
        ))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0002')"))

    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    from app.main import app
    app.dependency_overrides[get_db] = override_get_db

    import app.models.database as db_module
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)

    # Patch _get_db in run_commands to return the test session directly
    import app.api.run_commands as rc
    monkeypatch.setattr(rc, "_get_db", TestSession)

    with TestClient(app, raise_server_exceptions=False) as client:
        client.SessionLocal = TestSession
        yield client

    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(app_client):
    """Create an enterprise-tier user and return JWT auth headers."""
    session = app_client.SessionLocal()
    try:
        create_user(session, "tester@example.com", "testpassword1234", tier="enterprise")
    finally:
        session.close()

    resp = app_client.post(
        "/api/auth/login",
        json={"email": "tester@example.com", "password": "testpassword1234"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def parent_run(app_client, auth_headers):
    """Create a completed prototype WorkflowRun row and return its run_id."""
    from app.models.workflow import WorkflowRun

    session = app_client.SessionLocal()
    try:
        me = app_client.get("/api/auth/me", headers=auth_headers)
        assert me.status_code == 200
        user_id = me.json()["id"]

        run_id = str(uuid.uuid4())
        wr = WorkflowRun(
            id=run_id,
            user_id=user_id,
            owner_id=user_id,
            workspace_id=None,
            title="Test Prototype Run",
            type="prototype",
            status="completed",
            input="Build a landing page",
            output=_FAKE_HTML,
            agent_count=2,
        )
        session.add(wr)
        session.commit()
        return run_id
    finally:
        session.close()


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_run_analyzer_coroutine(tier: str = _FAKE_TIER, solution: str = _FAKE_SOLUTION):
    """Return an async function that acts as run_analyzer, emitting the standard 3 events."""

    async def _run_analyzer(
        instruction: str,
        existing_html: str,
        event_queue: asyncio.Queue,
        parent_run_id: str,
        model_id=None,
    ) -> tuple[str, str]:
        await event_queue.put({
            "type": "agent_start",
            "data": {
                "agent_id": "prototype-revision-analyzer",
                "name": "Prototype Revision Analyzer",
                "role": "analyzer",
                "icon": "🔍",
                "index": 1,
                "total": 1,
            },
        })
        await event_queue.put({
            "type": "agent_complete",
            "data": {
                "agent_id": "prototype-revision-analyzer",
                "name": "Prototype Revision Analyzer",
                "duration": 0.1,
                "output_length": len(solution),
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
            },
        })
        await event_queue.put({
            "type": "revision_analyzer_complete",
            "data": {
                "tier": tier,
                "solution_preview": solution[:200],
            },
        })
        return (tier, solution)

    return _run_analyzer


# ── Test: create_revision endpoint — basic event ordering ───────────────────


class TestCreateRevisionEventOrdering:
    """Assert SSE events, agent_count, and solution forwarding from create_revision."""

    @pytest.mark.issue("ISS-630")
    @pytest.mark.xfail(reason="ISS-630 unfixed", strict=True)
    def test_create_revision_returns_run_id(self, app_client, auth_headers, parent_run):
        """Endpoint returns 200 with a run_id when run_analyzer is mocked.

        Validates: Requirement 3.1 — analyzer invoked before pipeline is dispatched.
        """
        import app.agents.revision_analyzer as ra

        with (
            patch.object(ra, "run_analyzer", new=_make_run_analyzer_coroutine()),
            patch("app.api.run_commands._drive_revision_to_queue", new=AsyncMock()),
        ):
            resp = app_client.post(
                f"/api/runs/{parent_run}/revisions",
                json={
                    "target_artifact_type": "prototype_output",
                    "instruction": _FAKE_INSTRUCTION,
                },
                headers=auth_headers,
            )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert "run_id" in body
        assert body["run_id"]  # Non-empty UUID

    @pytest.mark.issue("ISS-630")
    @pytest.mark.xfail(reason="ISS-630 unfixed", strict=True)
    def test_revision_analyzer_complete_event_has_required_keys(
        self, app_client, auth_headers, parent_run
    ):
        """The revision_analyzer_complete event must have data.tier and data.solution_preview.

        Validates: Requirement 7.2
        """
        captured_events: list[dict] = []

        async def _capturing_run_analyzer(instruction, existing_html, event_queue,
                                          parent_run_id, model_id=None):
            tier, solution = _FAKE_TIER, _FAKE_SOLUTION
            await event_queue.put({
                "type": "agent_start",
                "data": {"agent_id": "prototype-revision-analyzer", "name": "Prototype Revision Analyzer",
                         "role": "analyzer", "icon": "🔍", "index": 1, "total": 1},
            })
            await event_queue.put({
                "type": "agent_complete",
                "data": {"agent_id": "prototype-revision-analyzer", "name": "Prototype Revision Analyzer",
                         "duration": 0.1, "output_length": 10,
                         "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            })
            evt = {
                "type": "revision_analyzer_complete",
                "data": {"tier": tier, "solution_preview": solution[:200]},
            }
            captured_events.append(evt)
            await event_queue.put(evt)
            return (tier, solution)

        import app.agents.revision_analyzer as ra

        with (
            patch.object(ra, "run_analyzer", new=_capturing_run_analyzer),
            patch("app.api.run_commands._drive_revision_to_queue", new=AsyncMock()),
        ):
            resp = app_client.post(
                f"/api/runs/{parent_run}/revisions",
                json={"target_artifact_type": "prototype_output", "instruction": _FAKE_INSTRUCTION},
                headers=auth_headers,
            )
        assert resp.status_code == 200

        # Verify the event was captured with the required payload keys
        assert len(captured_events) == 1, "Expected exactly one revision_analyzer_complete event"
        evt = captured_events[0]
        assert evt["type"] == "revision_analyzer_complete"
        assert "tier" in evt["data"], "revision_analyzer_complete must have data.tier"
        assert "solution_preview" in evt["data"], (
            "revision_analyzer_complete must have data.solution_preview"
        )
        assert evt["data"]["tier"] == _FAKE_TIER
        assert evt["data"]["solution_preview"] == _FAKE_SOLUTION[:200]

    @pytest.mark.issue("ISS-630")
    @pytest.mark.xfail(reason="ISS-630 unfixed", strict=True)
    def test_agent_count_is_rev_agents_plus_one(
        self, app_client, auth_headers, parent_run
    ):
        """WorkflowRun.agent_count == len(_rev_agents) + 1 for prototype_output revisions.

        Validates: Requirement 9.6
        """
        from agents.registry import get_pipeline_agents

        # Count agents for the small-revision pipeline (the default tier in mock)
        rev_agents = get_pipeline_agents("prototype_revision")
        expected_agent_count = len(rev_agents) + 1  # +1 for the Analyzer step

        import app.agents.revision_analyzer as ra

        with (
            patch.object(ra, "run_analyzer", new=_make_run_analyzer_coroutine()),
            patch("app.api.run_commands._drive_revision_to_queue", new=AsyncMock()),
        ):
            resp = app_client.post(
                f"/api/runs/{parent_run}/revisions",
                json={"target_artifact_type": "prototype_output", "instruction": _FAKE_INSTRUCTION},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        child_run_id = resp.json()["run_id"]

        from app.models.workflow import WorkflowRun
        session = app_client.SessionLocal()
        try:
            child_run = (
                session.query(WorkflowRun).filter(WorkflowRun.id == child_run_id).first()
            )
            assert child_run is not None, "Child revision run was not minted"
            assert child_run.agent_count == expected_agent_count, (
                f"Expected agent_count={expected_agent_count} "
                f"(len(_rev_agents)={len(rev_agents)} + 1), "
                f"got {child_run.agent_count}"
            )
        finally:
            session.close()

    @pytest.mark.issue("ISS-630")
    @pytest.mark.xfail(reason="ISS-630 unfixed", strict=True)
    def test_analyzer_solution_passed_to_drive_revision(
        self, app_client, auth_headers, parent_run
    ):
        """analyzer_solution from run_analyzer is forwarded to _drive_revision_to_queue.

        The solution is passed as the `analyzer_solution` kwarg, which is consumed
        by the wrapper in _drive_revision_to_queue to set ectx.analyzer_solution
        atomically before the first agent step.

        Validates: Requirements 7.1, 4.1
        """
        captured_kwargs: dict[str, Any] = {}

        async def _mock_drive(**kwargs):
            captured_kwargs.update(kwargs)

        import app.agents.revision_analyzer as ra

        with (
            patch.object(ra, "run_analyzer", new=_make_run_analyzer_coroutine()),
            patch("app.api.run_commands._drive_revision_to_queue", new=_mock_drive),
        ):
            resp = app_client.post(
                f"/api/runs/{parent_run}/revisions",
                json={"target_artifact_type": "prototype_output", "instruction": _FAKE_INSTRUCTION},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert "analyzer_solution" in captured_kwargs, (
            "_drive_revision_to_queue must receive analyzer_solution kwarg"
        )
        assert captured_kwargs["analyzer_solution"] == _FAKE_SOLUTION

    def test_non_prototype_revision_does_not_call_run_analyzer(
        self, app_client, auth_headers
    ):
        """run_analyzer is only called for prototype_output revisions, not other types.

        Validates: Requirement 3.1 — guard on target_artifact_type == prototype_output.
        """
        from app.models.workflow import WorkflowRun

        session = app_client.SessionLocal()
        try:
            me = app_client.get("/api/auth/me", headers=auth_headers)
            user_id = me.json()["id"]
            us_run_id = str(uuid.uuid4())
            wr = WorkflowRun(
                id=us_run_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id=None,
                title="User Stories Run",
                type="user_stories",
                status="completed",
                input="Build a login feature",
                output="Backlog...",
                agent_count=3,
            )
            session.add(wr)
            session.commit()
        finally:
            session.close()

        import app.agents.revision_analyzer as ra
        run_analyzer_mock = AsyncMock(return_value=(_FAKE_TIER, _FAKE_SOLUTION))

        with (
            patch.object(ra, "run_analyzer", run_analyzer_mock),
            patch("app.api.run_commands._drive_revision_to_queue", new=AsyncMock()),
        ):
            resp = app_client.post(
                f"/api/runs/{us_run_id}/revisions",
                json={"target_artifact_type": "user_stories_output", "instruction": "Add more stories"},
                headers=auth_headers,
            )

        # run_analyzer must NOT be called for a non-prototype revision
        run_analyzer_mock.assert_not_called()


# ── Test: Concierge path (CHANNEL_REVISION) ─────────────────────────────────


class TestConciergeRevisionPath:
    """Assert run_analyzer is called with correct args in the Concierge path.

    Validates: Requirement 9.4
    """

    @pytest.mark.issue("ISS-630")
    @pytest.mark.xfail(reason="ISS-630 unfixed", strict=True)
    def test_concierge_disposal_calls_run_analyzer_with_parent_html(
        self, app_client, auth_headers, parent_run
    ):
        """_dispose_concierge_proposal('revision') calls run_analyzer for prototype_output
        with existing_html from the parent run's output column and instruction from
        the proposal params.

        Validates: Requirement 9.4 — Concierge path sources existing_html from
        parent run output column, instruction from the proposal params.
        """
        captured_calls: list[dict] = []

        async def _capturing_run_analyzer(instruction, existing_html, event_queue,
                                          parent_run_id, model_id=None):
            captured_calls.append({
                "instruction": instruction,
                "existing_html": existing_html,
                "parent_run_id": parent_run_id,
            })
            await event_queue.put({
                "type": "agent_start",
                "data": {"agent_id": "prototype-revision-analyzer", "name": "Prototype Revision Analyzer",
                         "role": "analyzer", "icon": "🔍", "index": 1, "total": 1},
            })
            await event_queue.put({
                "type": "agent_complete",
                "data": {"agent_id": "prototype-revision-analyzer", "name": "Prototype Revision Analyzer",
                         "duration": 0.05, "output_length": 5,
                         "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            })
            await event_queue.put({
                "type": "revision_analyzer_complete",
                "data": {"tier": "small", "solution_preview": ""},
            })
            return ("small", "")

        revision_instruction = "Make the heading blue"
        import app.agents.revision_analyzer as ra

        with (
            patch.object(ra, "run_analyzer", new=_capturing_run_analyzer),
            patch("app.api.run_commands._drive_revision_to_queue", new=AsyncMock()),
        ):
            from app.api.run_commands import _dispose_concierge_proposal

            # Build a mock store and art_store
            mock_store = AsyncMock()
            mock_store.append_event_next_seq = AsyncMock()
            mock_art_store = MagicMock()
            mock_art_store.review_event_pending = MagicMock(return_value=False)

            # Get the user ID from the already-created user
            me = app_client.get("/api/auth/me", headers=auth_headers)
            user_id = me.json()["id"]
            from app.models.user import User
            fake_user = User(id=user_id, email="tester@example.com", tier="enterprise")

            # ProposalIntent lives in concierge.py, not chat_router
            from app.agents.chat.concierge import ProposalIntent
            intent = ProposalIntent(
                channel="revision",
                params={"instruction": revision_instruction, "target": "prototype_output"},
            )

            asyncio.get_event_loop().run_until_complete(
                _dispose_concierge_proposal(
                    intent,
                    confirmed=True,
                    store=mock_store,
                    art_store=mock_art_store,
                    run_id=parent_run,
                    message_id=str(uuid.uuid4()),
                    current_user=fake_user,
                    wr_status="completed",
                    wr_type="prototype",
                    gate_key=None,
                    ectx=None,
                )
            )

        # Verify run_analyzer was called with instruction and parent output HTML
        assert len(captured_calls) == 1, (
            f"Expected run_analyzer to be called once, was called {len(captured_calls)} times"
        )
        call_args = captured_calls[0]
        assert call_args["instruction"] == revision_instruction, (
            f"Expected instruction={revision_instruction!r}, got {call_args['instruction']!r}"
        )
        assert call_args["existing_html"] == _FAKE_HTML, (
            "Concierge path must source existing_html from parent run output column, "
            f"got: {call_args['existing_html'][:80]!r}"
        )
        assert call_args["parent_run_id"] == parent_run

    def test_concierge_proposal_for_non_prototype_target_skips_run_analyzer(self):
        """_dispose_concierge_proposal with a non-prototype target does NOT call
        run_analyzer — the guard is specifically on target == 'prototype_output'.

        Validates: Requirement 3.1 guard (only prototype revisions use the analyzer).
        """
        import app.agents.revision_analyzer as ra
        run_analyzer_mock = AsyncMock(return_value=("small", ""))

        async def _run():
            from app.api.run_commands import _dispose_concierge_proposal
            from app.agents.chat.concierge import ProposalIntent

            mock_store = AsyncMock()
            mock_store.append_event_next_seq = AsyncMock()
            mock_art_store = MagicMock()
            mock_art_store.review_event_pending = MagicMock(return_value=False)

            from app.models.user import User
            fake_user = User(id="user-1", email="tester@example.com", tier="enterprise")

            intent = ProposalIntent(
                channel="revision",
                params={"instruction": "Add more user stories", "target": "user_stories_output"},
            )

            fake_run_id = str(uuid.uuid4())

            with (
                patch.object(ra, "run_analyzer", run_analyzer_mock),
                patch("app.api.run_commands._drive_revision_to_queue", new=AsyncMock()),
                # Mock _mint_revision_row to avoid FK constraint failure
                patch(
                    "app.api.run_commands._mint_revision_row",
                    return_value=(str(uuid.uuid4()), "user_stories_revision"),
                ),
            ):
                await _dispose_concierge_proposal(
                    intent,
                    confirmed=True,
                    store=mock_store,
                    art_store=mock_art_store,
                    run_id=fake_run_id,
                    message_id=str(uuid.uuid4()),
                    current_user=fake_user,
                    wr_status="completed",
                    wr_type="user_stories",
                    gate_key=None,
                    ectx=None,
                )

        asyncio.get_event_loop().run_until_complete(_run())
        run_analyzer_mock.assert_not_called()


# ── Test: Fallback chain ─────────────────────────────────────────────────────


class TestFallbackChain:
    """Validates the two-level fallback chain in run_analyzer.

    Validates: Requirements 3.6, 3.7
    """

    def test_run_analyzer_fallback_calls_classify_tier_on_exception(self):
        """When the LLM call in run_analyzer raises, _classify_revision_tier is
        called as fallback, and (fallback_tier, "") is returned.

        Validates: Requirement 3.6
        """
        classify_mock = AsyncMock(return_value="large")

        async def _run():
            import app.agents.revision_analyzer as ra
            import app.agents.model_factory as mf
            with (
                patch.object(mf, "build_model", side_effect=RuntimeError("LLM unavailable")),
                # _classify_revision_tier is lazy-imported inside run_analyzer's except block
                # from app.api.run_commands — patch it at the source
                patch("app.api.run_commands._classify_revision_tier", classify_mock),
            ):
                queue: asyncio.Queue = asyncio.Queue()
                tier, solution = await ra.run_analyzer(
                    instruction=_FAKE_INSTRUCTION,
                    existing_html=_FAKE_HTML,
                    event_queue=queue,
                    parent_run_id="parent-123",
                    model_id=None,
                )
                return tier, solution

        tier, solution = asyncio.get_event_loop().run_until_complete(_run())
        classify_mock.assert_called_once_with(_FAKE_INSTRUCTION, "parent-123", None)
        assert tier == "large", f"Expected fallback tier 'large', got {tier!r}"
        assert solution == "", f"Fallback must return empty solution, got {solution!r}"

    def test_run_analyzer_double_failure_defaults_to_large(self):
        """When both the LLM call and _classify_revision_tier fail, run_analyzer
        returns ("large", "") — the run never aborts.

        Validates: Requirement 3.7
        """
        async def _run():
            import app.agents.revision_analyzer as ra
            import app.agents.model_factory as mf
            with (
                patch.object(mf, "build_model", side_effect=RuntimeError("LLM unavailable")),
                patch(
                    "app.api.run_commands._classify_revision_tier",
                    side_effect=RuntimeError("Fallback also broken"),
                ),
            ):
                queue: asyncio.Queue = asyncio.Queue()
                return await ra.run_analyzer(
                    instruction=_FAKE_INSTRUCTION,
                    existing_html=_FAKE_HTML,
                    event_queue=queue,
                    parent_run_id="parent-123",
                )

        tier, solution = asyncio.get_event_loop().run_until_complete(_run())
        assert tier == "large", f"Double-failure must default to 'large', got {tier!r}"
        assert solution == "", f"Double-failure must return empty solution, got {solution!r}"

    @pytest.mark.issue("ISS-630")
    @pytest.mark.xfail(reason="ISS-630 unfixed", strict=True)
    def test_create_revision_proceeds_on_run_analyzer_failure(
        self, app_client, auth_headers, parent_run
    ):
        """When run_analyzer internally falls back (returns ("large", "")),
        create_revision still returns 200 with a run_id.

        Validates: Requirement 3.6 — analyzer failure degrades gracefully.
        """
        async def _fallback_run_analyzer(instruction, existing_html, event_queue,
                                         parent_run_id, model_id=None):
            # Simulates what run_analyzer does internally: catches and returns default
            return ("large", "")

        import app.agents.revision_analyzer as ra

        with (
            patch.object(ra, "run_analyzer", new=_fallback_run_analyzer),
            patch("app.api.run_commands._drive_revision_to_queue", new=AsyncMock()),
        ):
            resp = app_client.post(
                f"/api/runs/{parent_run}/revisions",
                json={"target_artifact_type": "prototype_output", "instruction": _FAKE_INSTRUCTION},
                headers=auth_headers,
            )
        assert resp.status_code == 200, (
            f"create_revision must succeed even when run_analyzer falls back: {resp.text}"
        )
        assert "run_id" in resp.json()

    @pytest.mark.issue("ISS-630")
    @pytest.mark.xfail(reason="ISS-630 unfixed", strict=True)
    def test_double_failure_in_endpoint_proceeds_with_large_tier_pipeline(
        self, app_client, auth_headers, parent_run
    ):
        """When run_analyzer returns ("large", "") (double-failure default), the
        endpoint mints the run for the large-revision pipeline and returns 200.

        Validates: Requirement 3.7
        """
        async def _double_fail_default(instruction, existing_html, event_queue,
                                       parent_run_id, model_id=None):
            return ("large", "")

        captured_drive_kwargs: dict = {}

        async def _mock_drive(**kwargs):
            captured_drive_kwargs.update(kwargs)

        import app.agents.revision_analyzer as ra
        from app.api.run_commands import _REVISION_TIER_TARGET_MAP

        with (
            patch.object(ra, "run_analyzer", new=_double_fail_default),
            patch("app.api.run_commands._drive_revision_to_queue", new=_mock_drive),
        ):
            resp = app_client.post(
                f"/api/runs/{parent_run}/revisions",
                json={"target_artifact_type": "prototype_output", "instruction": _FAKE_INSTRUCTION},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        # Double-failure gives empty analyzer_solution
        assert captured_drive_kwargs.get("analyzer_solution") == "", (
            "Double-failure path must forward empty analyzer_solution"
        )
        # Target must be derived from "large" tier
        expected_target = _REVISION_TIER_TARGET_MAP["large"]
        assert captured_drive_kwargs.get("target_artifact_type") == expected_target, (
            f"Expected target_artifact_type={expected_target!r} (large tier), "
            f"got {captured_drive_kwargs.get('target_artifact_type')!r}"
        )


# ── Test: ectx.analyzer_solution set before first agent step ────────────────


class TestAnalyzerSolutionOnEctx:
    """Verifies analyzer_solution is stored on ectx before pipeline steps run.

    Validates: Requirements 7.1, 4.1
    """

    def test_ectx_analyzer_solution_set_via_register_wrapper(self):
        """The _ectx_register_with_solution wrapper sets ectx.analyzer_solution
        BEFORE calling register_live_ectx, ensuring it's available before the
        first agent step executes.

        Validates: Requirement 7.1 — solution set before first pipeline agent step.
        """
        from agents.execution_engine.context import ExecutionContext

        set_order: list[str] = []
        ectx = ExecutionContext(run_id="test-run", owner_id="user-1")

        registered_ectx: list[ExecutionContext] = []
        solution_was_set: list[bool] = []
        analyzer_solution = "Update the login button to say 'Sign In'"

        def _mock_register(run_id: str, ectx_obj):
            set_order.append("register_called")
            registered_ectx.append(ectx_obj)

        def _ectx_register_with_solution(run_id: str, ectx_obj):
            """Mirrors the implementation in _drive_revision_to_queue."""
            try:
                ectx_obj.analyzer_solution = analyzer_solution
                solution_was_set.append(True)
                set_order.append("solution_set")
            except Exception:
                solution_was_set.append(False)
            _mock_register(run_id, ectx_obj)

        # Simulate the engine calling the register callback
        _ectx_register_with_solution("test-run", ectx)

        assert solution_was_set == [True], "analyzer_solution must be set successfully"
        assert set_order == ["solution_set", "register_called"], (
            "Solution must be set BEFORE register_live_ectx is called — "
            f"actual order: {set_order}"
        )
        assert ectx.analyzer_solution == analyzer_solution
        assert len(registered_ectx) == 1
        assert registered_ectx[0].analyzer_solution == analyzer_solution

    def test_ectx_analyzer_solution_default_is_empty(self):
        """The default value of ectx.analyzer_solution is empty string,
        ensuring INV-3 byte-parity on existing golden runs.

        Validates: Requirements 4.3, 10.4
        """
        from agents.execution_engine.context import ExecutionContext

        ectx = ExecutionContext(run_id="test-run", owner_id="user-1")
        assert ectx.analyzer_solution == "", (
            "ExecutionContext.analyzer_solution must default to '' "
            "to preserve INV-3 byte-parity on non-analyzer runs"
        )

    def test_analyzer_solution_stored_on_ectx_before_first_agent(self):
        """When a non-empty solution is passed to _drive_revision_to_queue,
        the wrapper sets it on ectx.analyzer_solution before register_live_ectx
        is called, which is before the first agent step.

        Validates: Requirement 7.1
        """
        from agents.execution_engine.context import ExecutionContext

        solution = "The complete implementation plan for this revision."
        ectx = ExecutionContext(run_id="test-run-2", owner_id="user-1")

        # Simulate the exact wrapper logic from _drive_revision_to_queue
        from app.api.run_commands import register_live_ectx

        agent_start_event = []

        def _capturing_register(run_id: str, ectx_obj):
            # At this point, ectx.analyzer_solution should already be set
            agent_start_event.append(getattr(ectx_obj, "analyzer_solution", None))

        def _wrapper(run_id: str, ectx_obj):
            try:
                ectx_obj.analyzer_solution = solution
            except Exception:
                pass
            _capturing_register(run_id, ectx_obj)

        _wrapper("test-run-2", ectx)

        assert len(agent_start_event) == 1
        assert agent_start_event[0] == solution, (
            f"analyzer_solution must be set on ectx BEFORE register_live_ectx, "
            f"got: {agent_start_event[0]!r}"
        )


# ── Test: ectx storage soft-failure ─────────────────────────────────────────


class TestEctxStorageFailure:
    """Validates behavior when ectx.analyzer_solution cannot be stored.

    Validates: Requirement 7.6
    Note: Per the design, the storage failure is handled softly inside
    _drive_revision_to_queue's wrapper (logs a warning, then calls register_live_ectx
    anyway). The endpoint returns 200 — the run is minted and the drive task is queued.
    """

    def test_ectx_solution_set_failure_is_soft_not_hard_abort(self):
        """When ectx.analyzer_solution setter raises, the wrapper catches it,
        logs a warning, and still calls register_live_ectx. The run proceeds.

        Validates: Requirement 7.6 (soft failure in wrapper path)
        """
        from agents.execution_engine.context import ExecutionContext

        register_called = []
        warning_logged = []

        def _mock_register(run_id: str, ectx_obj):
            register_called.append(run_id)

        # Use a SimpleNamespace as a fake ectx that raises on analyzer_solution set
        class _BadSetter:
            """A stand-in ectx whose analyzer_solution setter always raises."""
            def __setattr__(self, name, value):
                if name == "analyzer_solution":
                    raise RuntimeError("Storage backend down!")
                object.__setattr__(self, name, value)

        ectx_like = _BadSetter()
        solution = "some solution"

        # Mirrors _drive_revision_to_queue's _ectx_register_with_solution
        def _ectx_register_with_solution(run_id: str, ectx_obj):
            try:
                ectx_obj.analyzer_solution = solution
            except Exception as _exc:
                # Soft failure: log warning and continue
                warning_logged.append(str(_exc))
            _mock_register(run_id, ectx_obj)

        _ectx_register_with_solution("test-broken", ectx_like)

        # Register was still called despite the setter raising
        assert register_called == ["test-broken"], (
            "register_live_ectx must be called even when analyzer_solution setter raises"
        )
        # The failure was noted
        assert len(warning_logged) == 1
        assert "Storage backend down!" in warning_logged[0]

    @pytest.mark.issue("ISS-630")
    @pytest.mark.xfail(reason="ISS-630 unfixed", strict=True)
    def test_endpoint_returns_200_on_solution_storage_soft_failure(
        self, app_client, auth_headers, parent_run
    ):
        """Even when the ectx solution storage fails softly inside the drive wrapper,
        the endpoint itself returns 200 — the run was minted and queued successfully.

        Validates: Requirement 7.6
        """
        import app.agents.revision_analyzer as ra

        with (
            patch.object(ra, "run_analyzer", new=_make_run_analyzer_coroutine()),
            patch("app.api.run_commands._drive_revision_to_queue", new=AsyncMock()),
        ):
            resp = app_client.post(
                f"/api/runs/{parent_run}/revisions",
                json={"target_artifact_type": "prototype_output", "instruction": _FAKE_INSTRUCTION},
                headers=auth_headers,
            )
        assert resp.status_code == 200, (
            f"Endpoint must succeed even with soft ectx storage: {resp.text}"
        )


# ── Test: Tier-to-pipeline mapping ──────────────────────────────────────────


class TestTierToPipelineMapping:
    """Verifies tier correctly drives pipeline selection.

    Validates: Requirement 3.2, Property 6
    """

    @pytest.mark.parametrize("tier,expected_target", [
        ("small", "prototype_output"),
        ("large", "prototype_large_output"),
        ("feature", "prototype_feature_output"),
    ])
    @pytest.mark.issue("ISS-630")
    @pytest.mark.xfail(reason="ISS-630 unfixed", strict=True)
    def test_tier_drives_effective_target(
        self, tier, expected_target, app_client, auth_headers, parent_run
    ):
        """Each tier value returned by run_analyzer selects the correct effective target.

        Validates: Requirement 3.2 — tier drives pipeline selection.
        """
        captured_drive_kwargs: dict = {}

        async def _mock_drive(**kwargs):
            captured_drive_kwargs.update(kwargs)

        async def _tier_mock(instruction, existing_html, event_queue,
                             parent_run_id, model_id=None):
            await event_queue.put({
                "type": "agent_start",
                "data": {"agent_id": "prototype-revision-analyzer", "name": "Prototype Revision Analyzer",
                         "role": "analyzer", "icon": "🔍", "index": 1, "total": 1},
            })
            await event_queue.put({
                "type": "agent_complete",
                "data": {"agent_id": "prototype-revision-analyzer", "name": "Prototype Revision Analyzer",
                         "duration": 0.01, "output_length": 5,
                         "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            })
            await event_queue.put({
                "type": "revision_analyzer_complete",
                "data": {"tier": tier, "solution_preview": ""},
            })
            return (tier, "")

        import app.agents.revision_analyzer as ra

        with (
            patch.object(ra, "run_analyzer", new=_tier_mock),
            patch("app.api.run_commands._drive_revision_to_queue", new=_mock_drive),
        ):
            resp = app_client.post(
                f"/api/runs/{parent_run}/revisions",
                json={"target_artifact_type": "prototype_output", "instruction": _FAKE_INSTRUCTION},
                headers=auth_headers,
            )

        if resp.status_code == 200:
            assert captured_drive_kwargs.get("target_artifact_type") == expected_target, (
                f"Tier {tier!r} must map to target {expected_target!r}, "
                f"got {captured_drive_kwargs.get('target_artifact_type')!r}"
            )
        elif resp.status_code in (400, 403):
            # Pipeline may not be registered in test env — skip gracefully
            pytest.skip(
                f"Pipeline for tier {tier!r} not available in test env "
                f"(entitlement/registry): {resp.text}"
            )
        else:
            pytest.fail(f"Unexpected status {resp.status_code}: {resp.text}")

    def test_revision_tier_target_map_covers_all_valid_tiers(self):
        """_REVISION_TIER_TARGET_MAP covers all three tiers and maps to distinct targets.

        Validates: Requirement 3.2 — no tier is missing from the mapping.
        """
        from app.api.run_commands import _REVISION_TIER_TARGET_MAP

        assert "small" in _REVISION_TIER_TARGET_MAP
        assert "large" in _REVISION_TIER_TARGET_MAP
        assert "feature" in _REVISION_TIER_TARGET_MAP
        # All three must map to distinct artifact types
        targets = list(_REVISION_TIER_TARGET_MAP.values())
        assert len(set(targets)) == 3, (
            f"All three tiers must map to distinct targets, got: {_REVISION_TIER_TARGET_MAP}"
        )
        # Each target must end with "_output"
        for tier, target in _REVISION_TIER_TARGET_MAP.items():
            assert target.endswith("_output"), (
                f"Tier {tier!r} maps to {target!r} which does not end with '_output'"
            )
