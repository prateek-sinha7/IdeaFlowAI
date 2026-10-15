"""QA-KB-105 / ISS-1125 -- a resume that ends on the workflow_unsatisfiable `error` frame must
be recorded through _fail_resume (one new pipeline_failed, row failed, live frame), not end silently.
The DAG is forced unsatisfiable by patching WorkflowResolver.validate (engine.py:5215).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

import app.api.run_engine as ws_mod
from tests.integration.agents.test_qa_kb_102_silent_resume import (
    OWNER,
    PRIOR_ERROR,
    _arm,
    _clean_registries,
    _manifest,
    _post_resume,
    _seed_prior,
    _seed_run,
    _state,
)
from tests.integration.agents.test_restart_resume_db import (
    _make_session,
    _ResumeHarness,
    _wire_user_resume_drive,
)

_ = _clean_registries  # autouse fixture re-exported


def _force_unsatisfiable(monkeypatch):
    from agents.execution_engine import resolver as r

    monkeypatch.setattr(
        r.WorkflowResolver,
        "validate",
        lambda self, agents: r.ValidationResult(
            satisfiable=False,
            errors=["Agent 'custom-agent:b' consumes 'x' but nothing produces it."],
        ),
    )


@pytest.mark.issue("ISS-1125")
async def test_user_resume_unsatisfiable_dag_records_new_failure_and_live_frame(
    monkeypatch,
):
    """ISS-1125 -- user resume of a failed run, DAG unsatisfiable: new pipeline_failed, fresh .error, live frame."""
    _force_unsatisfiable(monkeypatch)
    session, db = _make_session()
    rid = f"u-{uuid.uuid4().hex[:8]}"
    _seed_run(session, rid, "failed", "custom", _manifest(broken=False))
    await _seed_prior(session, rid, "failed")
    items = await _post_resume(monkeypatch, session, db, rid)
    row, types = _state(session, rid)
    assert (
        types.count("pipeline_failed") == 2
    ), f"no failure recorded for the unsatisfiable resume: {types}"
    assert row.error and row.error != PRIOR_ERROR, f"stale error: {row.error!r}"
    assert any(
        i and i["type"] == "pipeline_failed" for i in items
    ), f"no pipeline_failed live frame: {items}"


@pytest.mark.issue("ISS-1125")
async def test_user_resume_of_cancelled_run_unsatisfiable_dag_ends_failed(monkeypatch):
    """ISS-1125 -- user resume of a cancelled run, DAG unsatisfiable: must end failed, not silently stay cancelled."""
    from agents.authz import ScopedStore

    _force_unsatisfiable(monkeypatch)
    session, db = _make_session()
    rid = f"c-{uuid.uuid4().hex[:8]}"
    _seed_run(session, rid, "cancelled", "custom", _manifest(broken=False))
    await _seed_prior(session, rid, "failed")
    st = ScopedStore(owner_id=OWNER, workspace_id="ws-kb102", session=session)
    await st.append_event(
        rid, seq=99, event_id="ev-cx", type="pipeline_cancelled", payload_json={}
    )
    session.commit()
    await _post_resume(monkeypatch, session, db, rid)
    row, types = _state(session, rid)
    assert row.status == "failed", f"status={row.status!r} events={types}"


@pytest.mark.issue("ISS-1125")
async def test_restart_auto_resume_unsatisfiable_dag_does_not_leave_running_ghost(
    monkeypatch,
):
    """ISS-1125 -- restart auto-resume, DAG unsatisfiable: row failed after boot, one run_resuming across two boots."""
    from agents.authz import ScopedStore

    _force_unsatisfiable(monkeypatch)
    session, db = _make_session()
    rid = f"r-{uuid.uuid4().hex[:8]}"
    _seed_run(session, rid, "running", "custom", _manifest(broken=False))
    store = ScopedStore(owner_id=OWNER, workspace_id="ws-kb102", session=session)
    await store.append_event(
        rid,
        seq=1,
        event_id="ev-1",
        type="pipeline_start",
        payload_json={"pipeline_run_id": rid},
    )
    await store.append_event(
        rid,
        seq=2,
        event_id="ev-2",
        type="agent_start",
        payload_json={"agent_id": "custom-agent:a"},
    )
    session.commit()
    for _ in range(2):
        with _ResumeHarness(session, {}, fail_on=set(), db_engine=db) as h:
            engine = h.make_engine()
            _wire_user_resume_drive(monkeypatch, db, engine)
            _arm(engine)
            await engine.restore_non_terminal_runs()
            for _ in range(200):
                await asyncio.sleep(0.05)
                t = ws_mod._PIPELINE_TASKS.get(rid)
                if t is None or t.done():
                    break
            await asyncio.sleep(0.2)
    row, types = _state(session, rid)
    assert row.status == "failed", f"ghost row: status={row.status!r} events={types}"
    assert (
        types.count("run_resuming") == 1 and types.count("pipeline_failed") == 1
    ), types
