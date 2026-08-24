"""tests/agents/test_resume_marker_workspace.py — 12-09 Gap 2c + the marker NOT NULL fix.

Two coupled defects, one root cause (workflow_runs.workspace_id NULL on WS-path rows
while the run_events sink wrote a real workspace_id):

  * Gap 2c — ``pipeline_reconnected.status`` was null on reconnect: the
    owner+workspace-scoped ``ScopedStore.get_run`` (constructed with the workspace
    recovered from run_events, non-null) never matched the workflow_runs row (NULL
    workspace). FIX: ``_execute_impl`` stamps the resolved workspace back onto the row
    via the EXISTING ``authz.set_run_scope`` seam (INV-3/INV-12 — no parallel stamper);
  * the ``_stamp_resume_marker`` NOT NULL IntegrityError: the marker passed
    ``wr.workspace_id`` (NULL) into ``append_event`` → ``run_events.workspace_id``
    NOT NULL violation → the run_resuming marker was LOST on every in-process
    auto-resume. FIX: the marker recovers the run's REAL workspace_id via
    ``_recover_workspace_id`` (the run_events-sourced value, matching the sink).

Offline / in-memory SQLite / no API key / no network — the ``backend:characterization``
job. Reuses the ``_ResumeHarness`` from test_restart_resume.py.
"""

from __future__ import annotations

import uuid

import pytest

from tests.agents.test_restart_resume import (  # noqa: E402
    _ResumeHarness,
    _make_session,
    _seed_workflow_run,
)


# ===========================================================================
# (1a) — set_run_scope makes the owner+workspace-scoped get_run resolve a
#        non-null status for a WS-path-shaped row; cross-owner stays ∅ (IDOR)
# ===========================================================================


@pytest.mark.asyncio
async def test_set_run_scope_resolves_scoped_get_run_and_preserves_idor():
    from agents.authz import ScopedStore

    session, _db_engine = _make_session()
    run_id = f"mk-{uuid.uuid4().hex[:8]}"
    owner = "mk-user"
    workspace_id = "ws-mk"
    # Reproduce the WS-path shape: workflow_runs.workspace_id left NULL while the
    # run_events sink wrote rows under the REAL workspace_id.
    _seed_workflow_run(session, run_id, owner=owner, status="generating")
    sink_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    await sink_store.append_event(
        run_id, seq=1, event_id="mk-1", type="agent_start", payload_json={"seq": 1}
    )
    session.commit()

    scoped = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    # PRE-FIX shape: the owner+workspace-scoped read misses the NULL-workspace row.
    assert await scoped.get_run(run_id) is None, (
        "precondition: a NULL-workspace workflow_runs row must not match the "
        "owner+workspace-scoped get_run (the Gap 2c null-status shape)"
    )

    # The consistency fix: stamp via the EXISTING set_run_scope seam.
    await scoped.set_run_scope(run_id, owner, workspace_id)

    row = await scoped.get_run(run_id)
    assert row is not None, "after stamping, the scoped get_run must resolve the run"
    assert row.status is not None and row.status == "generating", (
        "pipeline_reconnected.status source must be non-null after stamping"
    )

    # IDOR preserved: a cross-owner store still resolves ∅ …
    cross = ScopedStore(owner_id="someone-else", workspace_id=workspace_id, session=session)
    assert await cross.get_run(run_id) is None, "cross-owner get_run must stay ∅"
    # … and a cross-owner re-scope attempt fails loud (IN-02), never clobbers.
    with pytest.raises(PermissionError):
        await cross.set_run_scope(run_id, "someone-else", "ws-evil")
    session.close()


# ===========================================================================
# (1b) — the ENGINE wiring: a driven run stamps workflow_runs.workspace_id
#        consistently with the run_events sink (the forward-path Gap 2c fix)
# ===========================================================================


@pytest.mark.asyncio
async def test_engine_drive_stamps_workflow_runs_workspace_consistent_with_sink():
    from agents.authz import ScopedStore
    from app.models.run_event import RunEvent
    from app.models.workflow import WorkflowRun

    session, db_engine = _make_session()
    run_id = f"st-{uuid.uuid4().hex[:8]}"
    owner = "st-user"
    # WS-path shape: row created BEFORE the workspace exists (workspace_id NULL).
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    call_log: dict[str, int] = {}
    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        # resume_run re-drives through _execute_impl — the SINGLE construction
        # path where the workspace is resolved + (now) stamped back on the row.
        await engine.resume_run(run_id)

    wr = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert wr.workspace_id is not None, (
        "the driven run must stamp workflow_runs.workspace_id (Gap 2c root cause)"
    )
    evt = session.query(RunEvent).filter(RunEvent.run_id == run_id).first()
    assert evt is not None, "the drive must have persisted run_events"
    assert wr.workspace_id == evt.workspace_id, (
        "workflow_runs.workspace_id must be CONSISTENT with the run_events sink "
        f"(run={wr.workspace_id!r} vs events={evt.workspace_id!r})"
    )
    # The reconnect-shaped read (owner + the workspace recovered from run_events)
    # now resolves the run row → pipeline_reconnected.status is non-null.
    reconnect_store = ScopedStore(
        owner_id=owner, workspace_id=evt.workspace_id, session=session
    )
    row = await reconnect_store.get_run(run_id)
    assert row is not None and row.status is not None
    session.close()


# ===========================================================================
# (2) — _stamp_resume_marker recovers the REAL workspace_id: the run_resuming
#       marker persists (no NOT NULL IntegrityError) under the sink workspace
# ===========================================================================


@pytest.mark.asyncio
async def test_stamp_resume_marker_persists_under_recovered_workspace():
    from agents.authz import ScopedStore
    from app.models.workflow import WorkflowRun

    session, db_engine = _make_session()
    run_id = f"rm-{uuid.uuid4().hex[:8]}"
    owner = "rm-user"
    workspace_id = "ws-rm"
    # WorkflowRun row with workspace_id=None, but run_events persisted under the
    # REAL workspace (the in-process auto-resume shape that hit the IntegrityError).
    _seed_workflow_run(session, run_id, owner=owner, status="generating")
    sink_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    N = 3
    for seq in range(1, N + 1):
        await sink_store.append_event(
            run_id, seq=seq, event_id=f"rm-{seq}",
            type=f"agent_chunk_{seq}", payload_json={"seq": seq},
        )
    session.commit()

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        wr = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        assert wr.workspace_id is None, "precondition: WS-path row (NULL workspace)"
        await engine._stamp_resume_marker(wr)

    # The marker persisted (NO IntegrityError) under the RECOVERED real workspace —
    # read back through the owner+workspace-scoped store (the sink scope).
    read_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    rows = await read_store.read_events(run_id, after_seq=0)
    markers = [r for r in rows if r.type == "run_resuming"]
    assert markers, (
        "the run_resuming marker must persist under the recovered workspace_id "
        "(pre-fix: lost to the run_events.workspace_id NOT NULL IntegrityError)"
    )
    assert markers[0].workspace_id == workspace_id
    # Contiguous seq: the marker rides the durable tail at max(seq)+1.
    assert markers[0].seq == N + 1
    session.close()


# ===========================================================================
# (3) — no durable workspace at all → best-effort: logs, never raises
# ===========================================================================


@pytest.mark.asyncio
async def test_stamp_resume_marker_without_durable_rows_does_not_raise():
    from app.models.run_event import RunEvent
    from app.models.workflow import WorkflowRun

    session, db_engine = _make_session()
    run_id = f"nr-{uuid.uuid4().hex[:8]}"
    # NO run_events / artifact_refs / wave_runs — recovery returns None.
    _seed_workflow_run(session, run_id, owner="nr-user", status="generating")

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        wr = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        # Best-effort parity: a None recovery falls through to the logged-warning
        # path — _stamp_resume_marker must NOT raise.
        await engine._stamp_resume_marker(wr)

    # Test plumbing only: the harness injects ONE shared session, so the marker's
    # internally-caught IntegrityError leaves it pending-rollback (production uses
    # a fresh, closed-in-finally SessionLocal). Reset before the read-back.
    session.rollback()
    # No NULL-workspace marker row was inserted (append_event's NOT NULL guard held).
    rows = (
        session.query(RunEvent)
        .filter(RunEvent.run_id == run_id, RunEvent.type == "run_resuming")
        .all()
    )
    assert rows == [], "a None workspace must never produce a persisted marker row"
    session.close()


# ===========================================================================
# (4) — DB-001 (task.md R-02): concurrent resume-marker writers do not
#       silently collide. Before the fix, ``_stamp_resume_marker`` did a
#       single unretried read-max(seq)+1-then-append_event; a losing writer's
#       IntegrityError was swallowed by the bare ``except Exception`` and its
#       marker was dropped with no trace. After the fix (routing through
#       ``ScopedStore.append_event_next_seq``), every concurrent marker call
#       survives with a distinct seq — none are silently lost.
# ===========================================================================


@pytest.mark.asyncio
async def test_stamp_resume_marker_survives_concurrent_racing_writers():
    import asyncio

    from agents.authz import ScopedStore
    from app.models.run_event import RunEvent
    from app.models.workflow import WorkflowRun

    session, db_engine = _make_session()
    run_id = f"cc-{uuid.uuid4().hex[:8]}"
    owner = "cc-user"
    workspace_id = "ws-cc"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")
    # Seed one durable row so the marker's seq computation has a real tail to race
    # against (an empty tail would make every concurrent writer race for seq=1).
    seed_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    await seed_store.append_event(
        run_id, seq=1, event_id="cc-seed", type="agent_chunk_1", payload_json={"seq": 1},
    )
    session.commit()

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        wr = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()

        # N "concurrent" resume-marker attempts against the SAME run — the harness's
        # shared SQLite session makes these interleave cooperatively (asyncio.gather)
        # rather than truly parallel-thread, but each call still independently reads
        # the tail and attempts an insert, exercising the exact race the fix targets:
        # two callers computing the same next_seq before either commits.
        N = 6
        await asyncio.gather(*[engine._stamp_resume_marker(wr) for _ in range(N)])

    read_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    rows = await read_store.read_events(run_id, after_seq=0)
    markers = [r for r in rows if r.type == "run_resuming"]

    assert len(markers) == N, (
        f"every concurrent _stamp_resume_marker call must persist its OWN marker row "
        f"(no silent collision-drop) — expected {N}, got {len(markers)}"
    )
    seqs = [m.seq for m in markers]
    assert len(set(seqs)) == len(seqs), f"marker seqs must be unique, got {seqs}"
    # No gaps/duplicates across the whole persisted log for this run either.
    all_seqs = sorted(r.seq for r in rows)
    assert all_seqs == list(range(1, len(rows) + 1)), (
        f"the run's full seq log must stay contiguous and unique, got {all_seqs}"
    )
    session.close()
