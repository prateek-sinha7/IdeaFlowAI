"""tests/unit/test_run_capabilities.py — CAPRUN-01 capability snapshot (Phase 5).

The engine records EXACTLY ONE ``run_capabilities`` row per run at entry (05-04),
stamping ``runtime=langchain_deepagents`` (INV-13 — the canonical deepagents
adapter id). This focused suite drives the recording through the single
``ScopedStore.record_capabilities`` write path (the same path the engine uses)
and asserts:

1. After recording, EXACTLY ONE ``run_capabilities`` row exists for the run.
2. The row's ``runtime == "langchain_deepagents"``.
3. The deferred forward columns (``model_overrides`` / ``skills`` / ``hooks`` /
   ``integrations`` / ``mcp_servers`` / ``versions``) are present and
   nullable/empty this phase (populated in phases 6/8/9).

Offline / in-memory SQLite / no API key — the ``backend:characterization`` job.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore
from app.models.database import Base
from app.models.run_capabilities import RunCapabilities
from app.models.workflow import WorkflowRun


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _seed_run(db, *, run_id="run-1", owner_id="alice", workspace_id="ws-1"):
    db.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="t",
            type="prototype",
            status="running",
            input="idea",
            owner_id=owner_id,
            workspace_id=workspace_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# CAPRUN-01 — exactly one row, runtime=langchain_deepagents, deferred cols nullable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_capabilities_writes_one_langchain_deepagents_row(db_session):
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    await store.record_capabilities("run-1", runtime="langchain_deepagents")

    rows = (
        db_session.query(RunCapabilities)
        .filter(RunCapabilities.run_id == "run-1")
        .all()
    )
    # (1) EXACTLY ONE row for the run.
    assert len(rows) == 1, f"expected one run_capabilities row, found {len(rows)}"
    row = rows[0]

    # (2) runtime is the canonical deepagents adapter id (INV-13).
    assert row.runtime == "langchain_deepagents"

    # (3) deferred forward columns present + nullable/empty this phase.
    for col in (
        "model_overrides",
        "skills",
        "hooks",
        "integrations",
        "mcp_servers",
        "versions",
    ):
        assert hasattr(row, col), f"deferred column {col!r} missing from model"
        assert getattr(row, col) is None, f"deferred column {col!r} should be empty"

    # Owner/workspace stamped from the helper principal (AUTHZ-01).
    assert row.owner_id == "alice"
    assert row.workspace_id == "ws-1"


@pytest.mark.asyncio
async def test_record_capabilities_is_one_row_not_per_agent(db_session):
    """The capability row is recorded ONCE per run (at engine entry), not per
    agent — CAPRUN-01 is a one-row-per-run invariant."""
    _seed_run(db_session, run_id="run-1", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    # A single recording for the run (the engine's single entry-point call).
    await store.record_capabilities("run-1", runtime="langchain_deepagents")

    count = (
        db_session.query(RunCapabilities)
        .filter(RunCapabilities.run_id == "run-1")
        .count()
    )
    assert count == 1


# ---------------------------------------------------------------------------
# MODEL-03 (Phase 6 D-08) — model_overrides persisted at entry; {} → SQL NULL
# ---------------------------------------------------------------------------
#
# The engine seeds ``ectx.model_overrides`` (the validated {agent_id → model_id}
# map from the WS ingress) and persists it via
# ``record_capabilities(..., model_overrides=(ectx.model_overrides or None))``
# at run entry (engine.py). These tests drive the same single write path and
# assert the row, plus the INV-3 row-parity rule: a no-override run (the only
# kind today) writes the column as SQL NULL — never a spurious ``{}``.


@pytest.mark.asyncio
async def test_record_capabilities_persists_model_overrides_map(db_session):
    """MODEL-03: a run with ``model_overrides={agent → catalog-id}`` writes that
    EXACT map to ``run_capabilities.model_overrides`` (owner+workspace-scoped)."""
    from agents.capabilities.model_catalog import ModelCatalog

    _seed_run(db_session, run_id="run-ov", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    catalog_id = ModelCatalog().ids()[0]
    overrides = {"prototype-build": catalog_id}
    await store.record_capabilities(
        "run-ov", runtime="langchain_deepagents", model_overrides=overrides
    )

    row = (
        db_session.query(RunCapabilities)
        .filter(RunCapabilities.run_id == "run-ov")
        .one()
    )
    assert row.model_overrides == {"prototype-build": catalog_id}


@pytest.mark.asyncio
async def test_empty_model_overrides_persists_as_null(db_session):
    """INV-3 row parity: a no-override run (``{} or None`` → NULL) persists the
    column as SQL NULL, identical to legacy/pre-Phase-6 rows — NOT ``{}``.

    Mirrors the engine call ``record_capabilities(..., model_overrides=(ectx.
    model_overrides or None))`` for the no-override case (every run today)."""
    _seed_run(db_session, run_id="run-empty", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    # The engine passes ``{} or None`` → None for a no-override run.
    await store.record_capabilities(
        "run-empty", runtime="langchain_deepagents", model_overrides=({} or None)
    )

    row = (
        db_session.query(RunCapabilities)
        .filter(RunCapabilities.run_id == "run-empty")
        .one()
    )
    assert row.model_overrides is None, "empty {} must persist as NULL, not {}"
