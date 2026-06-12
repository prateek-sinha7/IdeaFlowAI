"""13-05 — FE-exact ``run_revision`` contract regression (F2 / 13-UAT.md Gap 2).

The frontend (DashboardLayout.tsx:388-403) sends ``run_revision`` frames with
``target_artifact_type: "ppt_output" | "od_ppt_output"`` — values NO producer
write ever persisted, so before 13-05 EVERY FE revision failed the FR-014
lookup. This is the contract regression for that frame: it completes a scripted
run end-to-end through the PUBLIC ``ExecutionEngine.execute()`` (so the 13-05
completion path persists the run deliverable ORGANICALLY — nothing is seeded by
hand for the chain to find), then drives ``_handle_revision`` with the FE-exact
fields and asserts the revision proceeds and embeds the parent deliverable.

On pre-13-05 code this test FAILS with the FR-014 ValueError ("No artifact of
type 'od_ppt_output' ...") — exactly the live UAT failure (Gap 2, finding F2).

Offline: scripted models via ``tests.agents._scripted_model._drive`` (no
Bedrock / no network); in-memory SQLite (StaticPool) monkeypatched onto
``app.models.database.SessionLocal`` so the engine's best-effort ScopedStore
writes PERSIST (instead of degrading) and the cross-run revision reads resolve.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table the engine's ScopedStore path touches on Base.metadata
# BEFORE create_all: workflow_runs, artifact_refs, workspaces, run_events,
# run_capabilities (execute() records capabilities + arms the run-events sink).
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
from agents.execution_engine.engine import ExecutionEngine
from app.models.database import Base
from tests.agents._scripted_model import _drive

# _drive() runs execute() with user_id="harness-user" → that string is the
# owner principal every ScopedStore write is stamped with.
OWNER = "harness-user"


@pytest.fixture
def db_factory(monkeypatch):
    """In-memory SQLite (StaticPool, shared connection) wired into
    ``app.models.database.SessionLocal`` so every engine-path ``ScopedStore``
    (execute()'s writes AND _handle_revision's cross-run reads) hits THIS DB."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr("app.models.database.SessionLocal", TestingSession, raising=False)
    try:
        yield TestingSession
    finally:
        Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_fe_exact_run_revision_against_a_completed_run(db_factory) -> None:
    """F2 / Gap 2: the FE's exact run_revision payload against a REAL completed
    parent run passes FR-014 and drives the revision to pipeline_complete."""
    # ── 1) Complete a scripted od_ppt run end-to-end via the PUBLIC execute().
    # The 13-05 completion block persists the run deliverable itself — this test
    # deliberately seeds NO artifact rows, so the only way the revision below can
    # resolve is through what the run path organically persisted.
    run_events = await _drive("od_ppt")
    run_completes = [e for e in run_events if e["type"] == "pipeline_complete"]
    assert run_completes, "scripted od_ppt run did not complete"
    parent_run_id = run_completes[-1]["data"]["pipeline_run_id"]
    parent_deliverable = run_completes[-1]["data"]["final_output"]
    assert parent_deliverable, "scripted run produced an empty deliverable"

    # ── 2) The FE-exact revision frame (DashboardLayout.tsx:388-403): the
    # websocket ingress forwards target_artifact_type VERBATIM to the engine.
    engine = ExecutionEngine()
    sent: list[dict] = []

    async def websocket_send_fn(event: dict) -> None:
        sent.append(event)

    await engine._handle_revision(
        parent_run_id=parent_run_id,
        target_artifact_type="od_ppt_output",  # FE-exact — never a persisted kind
        instruction="Make the closing slide a clear call to action.",
        pipeline_run_id="run-rev-fe-contract",
        websocket_send_fn=websocket_send_fn,
        owner_id=OWNER,
    )

    # ── 3) The revision PROCEEDED: no failure event, one pipeline_complete with
    # the FE-derived revision pipeline_type.
    failures = [e for e in sent if e["type"] == "state_restoration_failed"]
    assert not failures, f"revision failed: {failures}"

    completes = [e for e in sent if e["type"] == "pipeline_complete"]
    assert len(completes) == 1, "expected exactly one revision pipeline_complete"
    data = completes[0]["data"]
    # WR-06 (13 review fix): the emitted pipeline_type is the FE-ROUTED revision
    # alias (the dashboard preview routing matches od_ppt_revision — the verbatim
    # "od_ppt_output_revision" matched no branch, so the revision never reached
    # the preview panel).
    assert data["pipeline_type"] == "od_ppt_revision"

    # ── 4) The revision context embeds the PARENT deliverable content — the
    # FR-014 chain resolved the run's organically-persisted completion ref.
    final_output = data["final_output"]
    assert "=== ORIGINAL ARTIFACT (type: od_ppt_output) ===" in final_output
    assert parent_deliverable in final_output
    assert "=== REVISION INSTRUCTION ===" in final_output
    assert "Make the closing slide a clear call to action." in final_output
