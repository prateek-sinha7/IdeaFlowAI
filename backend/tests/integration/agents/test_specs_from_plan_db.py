"""FIX-266 layer 4 — ``resume_run()`` reports the composer's display names.

Moved out of ``tests/unit/agents/workflows/test_specs_from_plan.py`` in Batch 6: this
is the behavioural layer, and it drives the real ``resume_run()`` against an in-memory
SQLite ``workflow_runs`` row (it even swaps ``app.models.database.SessionLocal``), which
is integration work. Layers 1-3 of that file — ``_specs_from_plan`` against constructed
Steps, the same function against the real compiled ``sample_subagents_parallel``
manifest, and the source guard that resume paths call the shared helper — need no
database and stayed in the unit suite.
"""

from __future__ import annotations

import pytest

from agents.execution_engine.engine import ExecutionEngine


@pytest.mark.asyncio
async def test_resume_run_builds_display_names_for_a_real_composed_workflow():
    """FIX-266, behavioral: resume_run() on a `sample_subagents_parallel` row (no
    static registry membership, so it MUST take the plan-fallback branch at
    engine.py:8793) reaches the resume-offset call with an `agents` list carrying
    the composer's display_name — not the template's "Custom Agent" name.
    Complements the source-guard test above with a live call through resume_run()
    itself, using the same fixture and expected names pinned in layer 2."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401 — register models on Base.metadata
    import app.models.database as db_mod
    from app.models.database import Base
    from app.models.workflow import WorkflowRun

    db = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=db)
    session = sessionmaker(bind=db, autocommit=False, autoflush=False)()
    session.add(
        WorkflowRun(
            id="resume-fixture-run",
            user_id="u1",
            owner_id="u1",
            workspace_id=None,
            status="running",
            type="sample_subagents_parallel",
            input="topic",
        )
    )
    session.commit()

    orig_session_local = db_mod.SessionLocal
    db_mod.SessionLocal = sessionmaker(
        bind=db, autocommit=False, autoflush=False, expire_on_commit=False
    )

    class _ReachedOffset(Exception):
        pass

    captured: dict = {}

    # Mirrors ExecutionEngine._compute_resume_offset's real signature, which gained
    # an optional ``compiled`` kwarg the resume path now passes.
    async def _spy_offset(
        run_id, user_id, session_id, pipeline_type, agents, compiled=None
    ):
        captured["agents"] = agents
        raise _ReachedOffset()

    engine = ExecutionEngine()
    engine._compute_resume_offset = _spy_offset  # type: ignore[assignment]

    try:
        try:
            await engine.resume_run("resume-fixture-run")
        except _ReachedOffset:
            pass

        assert "agents" in captured, "resume_run never reached the offset call"
        names = {s.id: s.name for s in captured["agents"]}
        assert names == {
            "custom-agent:apple": "Apple Writer",
            "custom-agent:ball": "Ball Writer",
            "custom-agent:cat": "Cat Writer",
            "custom-agent:page": "Page Builder",
        }
        assert "Custom Agent" not in names.values(), (
            "resume_run reported the TEMPLATE's name instead of its display_name — "
            "the exact FIX-266 regression, this time via the real resume path"
        )
    finally:
        db_mod.SessionLocal = orig_session_local
        session.close()
