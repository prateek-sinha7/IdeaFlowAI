"""tests/agents/test_resume_marker_seq_allocation.py — ISS-125.

``_stamp_resume_marker`` allocates its seq through ``ScopedStore.append_event_next_seq``
(FIX-240/DB-001), which fixed the non-retrying append but NOT the read cost: that method
still derives the next seq via ``read_events(run_id, after_seq=0)`` — an unbounded read of
every row for the run — instead of the bounded ``_max_event_seq`` aggregate the same file
already exposes (and that ``append_event_at_or_after`` uses for its own tail probe). The
marker is a best-effort audit row; it should never need to materialise a run's entire
event log to compute one integer.

Offline / in-memory SQLite / no API key / no network — the ``backend:characterization`` job.
"""

from __future__ import annotations

import uuid

import pytest

from agents.authz import ScopedStore
from tests.agents.test_restart_resume import (  # noqa: E402
    _ResumeHarness,
    _make_session,
    _seed_workflow_run,
)


@pytest.mark.issue("ISS-125")
@pytest.mark.asyncio
async def test_stamp_resume_marker_does_not_read_entire_event_log():
    session, db_engine = _make_session()
    run_id = f"iss125-{uuid.uuid4().hex[:8]}"
    owner = "iss125-user"
    workspace_id = "ws-iss125"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")
    seed_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    # A handful of durable rows is enough to prove the point without a 26k/36k-row
    # fixture: any call to the unbounded read is the defect, regardless of row count.
    for seq in range(1, 4):
        await seed_store.append_event(
            run_id, seq=seq, event_id=f"iss125-{seq}",
            type=f"agent_chunk_{seq}", payload_json={"seq": seq},
        )
    session.commit()

    read_calls: list[int] = []
    orig_read_events = ScopedStore.read_events

    async def _counting_read_events(self, rid, *, after_seq=0, **kwargs):
        read_calls.append(after_seq)
        return await orig_read_events(self, rid, after_seq=after_seq, **kwargs)

    ScopedStore.read_events = _counting_read_events
    try:
        with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
            engine = h.make_engine()
            from app.models.workflow import WorkflowRun

            wr = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            await engine._stamp_resume_marker(wr)
    finally:
        ScopedStore.read_events = orig_read_events

    assert not read_calls, (
        "_stamp_resume_marker must allocate its seq via the bounded _max_event_seq "
        f"probe, not an unbounded read_events(after_seq=0) scan of the whole run log "
        f"(ISS-125); got {len(read_calls)} unbounded read call(s): {read_calls}"
    )
    session.close()
