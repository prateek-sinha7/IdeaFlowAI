"""tests/agents/test_resume_context_v3.py — Requirement 23 AC6 behavioral test.

Verifies FR-065: resume_run() with a DB row whose od_context_json diverges from
.context/ — the file wins.

fix attempt 1 (V9): the original version of this file only unit-tested the helper
`rebuild_od_context_from_sandbox()` directly — never driving `resume_run()` itself,
never creating a `WorkflowRun` row, and never setting `od_context_json`. That helper
in isolation was already covered by
`test_phase6_sandbox_versioning.py::test_rebuild_od_context_reconstructs_dict_from_files`
and `::test_rebuild_od_context_returns_none_when_no_context_dir`, so the old tests here
added nothing and left the actual merge/override logic inside `resume_run()`
(engine.py ~12833-12869: read `od_context_json` off the row, then override to the
rebuilt `.context/` value only when non-None) completely untested — exactly the gap
GAPS.md's P2 row names. This version drives `engine.resume_run(run_id)` itself
(the `test_specs_from_plan.py` layer-4 / `test_restart_resume.py` pattern: an
in-memory SQLite `workflow_runs` row + a real on-disk sandbox), and asserts on the
`od_context` the engine actually threads downstream — captured via a spy on
`ExecutionEngine._drive_resumed_stream` (the call immediately after the merge logic,
one hop from `_execute_impl`; `_compute_resume_offset` is stubbed to return 0
immediately, exactly as the FIX-266 precedent does, since offset computation is
orthogonal to FR-065 and this avoids exercising unrelated durable-store internals).

Offline-safe: uses temp RUNS_ROOT + an ephemeral in-memory SQLite DB, no Bedrock/
Postgres/Chromium/LLM calls (the spy raises before any agent would be dispatched).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _make_in_memory_db():
    """Create an ephemeral SQLite DB with the full model schema, mirroring
    `test_specs_from_plan.py::test_resume_run_builds_display_names_for_a_real_composed_workflow`.
    """
    import app.models  # noqa: F401 — register models on Base.metadata
    from app.models.database import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    return engine, session


async def _fake_offset(run_id, user_id, session_id, pipeline_type, agents) -> int:
    """Stub for `_compute_resume_offset` — offset computation is orthogonal to
    FR-065 (see module docstring); returning 0 lets resume_run() proceed straight
    to the od_context merge + `_drive_resumed_stream` call under test."""
    return 0


@pytest.mark.asyncio
async def test_resume_run_uses_context_file_over_diverging_db_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-065 behavioral: resume_run() prefers `.context/` over a diverging DB column.

    A `WorkflowRun` row is created with `od_context_json` set to a DB value, and the
    run's real on-disk sandbox has a `.context/selections.json` with a DIFFERENT
    value. `resume_run()` must thread the FILE version — not the DB value — into
    the downstream execution entry point.
    """
    from app.agents.sandbox import RunSandbox
    from app.api.launch_context import rebuild_od_context_from_sandbox
    from app.core.config import settings as _settings
    import app.models.database as db_mod
    from app.models.workflow import WorkflowRun
    from agents.execution_engine.engine import ExecutionEngine

    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_settings, "RUNS_ROOT", runs_root)

    run_id = "resume-fr065-run"
    user_id = "resume-fr065-user"

    db_od_context_value = {
        "template_id": "db-tpl-123",
        "ds_id": "db-ds-456",
        "template_name": "DB Template",
        "ds_name": "DB Design System",
        "no_template": False,
        "is_design_system_required": True,
    }
    file_od_context_value = {
        "template_id": "file-tpl-789",
        "ds_id": "file-ds-012",
        "template_name": "File Template",
        "ds_name": "File Design System",
        "no_template": False,
        "is_design_system_required": True,
    }

    # Sandbox lives at $RUNS_ROOT/{user_id}/{run_id} (root run, no parent → the chain
    # root IS run_id, so resume_run()'s RunSandbox resolves to this same directory).
    sandbox_dir = runs_root / user_id / run_id
    context_dir = sandbox_dir / ".context"
    context_dir.mkdir(parents=True, exist_ok=True)
    (context_dir / "selections.json").write_text(
        json.dumps(file_od_context_value), encoding="utf-8"
    )

    # Sanity: the fixture actually diverges (guards against a future accidental
    # edit making db/file values equal, which would let this test pass vacuously).
    rebuilt_sanity = rebuild_od_context_from_sandbox(RunSandbox(user_id, run_id))
    assert rebuilt_sanity is not None
    assert rebuilt_sanity["template_id"] != db_od_context_value["template_id"]

    db_engine, session = _make_in_memory_db()
    session.add(
        WorkflowRun(
            id=run_id,
            user_id=user_id,
            owner_id=user_id,
            workspace_id=None,
            status="running",
            type="sample_subagents_parallel",
            input="topic",
            od_context_json=db_od_context_value,
        )
    )
    session.commit()

    orig_session_local = db_mod.SessionLocal
    db_mod.SessionLocal = sessionmaker(
        bind=db_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    class _ReachedDriveStream(Exception):
        pass

    captured: dict = {}

    async def _spy_drive_resumed_stream(run_id, **kwargs):
        captured["od_context"] = kwargs.get("od_context")
        raise _ReachedDriveStream()

    engine = ExecutionEngine()
    engine._compute_resume_offset = _fake_offset  # type: ignore[assignment]
    engine._drive_resumed_stream = _spy_drive_resumed_stream  # type: ignore[assignment]

    try:
        try:
            await engine.resume_run(run_id)
        except _ReachedDriveStream:
            pass

        assert "od_context" in captured, "resume_run never reached _drive_resumed_stream"
        threaded = captured["od_context"]
        assert threaded is not None, (
            "resume_run must thread a non-None od_context when .context/ exists"
        )
        assert threaded["template_id"] == "file-tpl-789", (
            f"resume_run must use the .context/ file version; "
            f"got {threaded['template_id']!r}"
        )
        assert threaded["ds_id"] == "file-ds-012"
        assert threaded["template_id"] != db_od_context_value["template_id"], (
            "resume_run must NOT thread the DB od_context_json value when "
            ".context/ files exist — the file must win (FR-065)"
        )
    finally:
        db_mod.SessionLocal = orig_session_local
        session.close()


@pytest.mark.asyncio
async def test_resume_run_falls_back_to_db_column_when_context_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-065 fallback: resume_run() uses the DB od_context_json column when the
    sandbox has no `.context/` directory (pre-migration-8.1 sandbox, or a non-OD
    run whose DB column happens to be populated)."""
    from app.core.config import settings as _settings
    import app.models.database as db_mod
    from app.models.workflow import WorkflowRun
    from agents.execution_engine.engine import ExecutionEngine

    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_settings, "RUNS_ROOT", runs_root)

    run_id = "resume-fr065-fallback-run"
    user_id = "resume-fr065-fallback-user"

    db_od_context_value = {
        "template_id": "db-tpl-only-123",
        "ds_id": "db-ds-only-456",
        "template_name": "DB Only Template",
        "ds_name": "DB Only Design System",
        "no_template": False,
        "is_design_system_required": True,
    }

    # Sandbox dir exists but has NO .context/ — the pre-task-8.1 / non-OD case.
    (runs_root / user_id / run_id).mkdir(parents=True, exist_ok=True)

    db_engine, session = _make_in_memory_db()
    session.add(
        WorkflowRun(
            id=run_id,
            user_id=user_id,
            owner_id=user_id,
            workspace_id=None,
            status="running",
            type="sample_subagents_parallel",
            input="topic",
            od_context_json=db_od_context_value,
        )
    )
    session.commit()

    orig_session_local = db_mod.SessionLocal
    db_mod.SessionLocal = sessionmaker(
        bind=db_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    class _ReachedDriveStream(Exception):
        pass

    captured: dict = {}

    async def _spy_drive_resumed_stream(run_id, **kwargs):
        captured["od_context"] = kwargs.get("od_context")
        raise _ReachedDriveStream()

    engine = ExecutionEngine()
    engine._compute_resume_offset = _fake_offset  # type: ignore[assignment]
    engine._drive_resumed_stream = _spy_drive_resumed_stream  # type: ignore[assignment]

    try:
        try:
            await engine.resume_run(run_id)
        except _ReachedDriveStream:
            pass

        assert "od_context" in captured, "resume_run never reached _drive_resumed_stream"
        threaded = captured["od_context"]
        assert threaded == db_od_context_value, (
            "resume_run must fall back to the DB od_context_json column when "
            f".context/ is absent; got {threaded!r}, expected {db_od_context_value!r}"
        )
    finally:
        db_mod.SessionLocal = orig_session_local
        session.close()
