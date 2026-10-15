"""tests/agents/test_resume_seed_bounded_aggregate.py — ISS-639 / ISS-873 / ISS-874.

The resume-tier seq seeds (``resume_run``, ``_replay_clarify_run``) and the boot probe
``_is_resumable_in_flight`` derive one scalar from a whole-log ``read_events(after_seq=0)``
instead of the bounded ``ScopedStore._max_event_seq`` aggregate.

Offline / in-memory SQLite / no network.
"""

from __future__ import annotations

import uuid

import pytest

from agents.authz import ScopedStore
from tests.integration.agents.test_restart_resume_db import (  # noqa: E402
    _ResumeHarness,
    _make_session,
    _seed_open_questionnaire_gate,
    _seed_workflow_run,
)


class _Spy:
    """Class-level counters on ScopedStore.read_events / _max_event_seq."""

    def __init__(self):
        self.reads: list[int] = []
        self.max_calls = 0

    def __enter__(self):
        self._orig_read = ScopedStore.read_events
        self._orig_max = ScopedStore._max_event_seq
        spy = self

        async def _read(self_, rid, *, after_seq=0, **kw):
            spy.reads.append(after_seq)
            return await spy._orig_read(self_, rid, after_seq=after_seq, **kw)

        async def _max(self_, rid, *a, **kw):
            spy.max_calls += 1
            return await spy._orig_max(self_, rid, *a, **kw)

        ScopedStore.read_events = _read
        ScopedStore._max_event_seq = _max
        return self

    def __exit__(self, *exc):
        ScopedStore.read_events = self._orig_read
        ScopedStore._max_event_seq = self._orig_max


async def _seed_tail(session, run_id, owner, ws, n, first=1):
    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    for seq in range(first, first + n):
        await store.append_event(
            run_id,
            seq=seq,
            event_id=f"t-{seq}",
            type=f"agent_chunk_{seq}",
            payload_json={"seq": seq},
        )
    session.commit()


def _capture_driver(engine, captured):
    async def _fake_drive(run_id, **kw):
        captured["start_seq"] = kw.get("start_seq")

    engine._drive_resumed_stream = _fake_drive


@pytest.mark.issue("ISS-639")
@pytest.mark.asyncio
async def test_resume_run_seed_uses_bounded_aggregate():
    session, db_engine = _make_session()
    run_id = f"iss639-{uuid.uuid4().hex[:8]}"
    owner, ws = "iss639-user", "ws-iss639"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")
    await _seed_tail(session, run_id, owner, ws, 4)
    # Higher seqs under another owner / workspace must be ignored by the seed.
    await _seed_tail(session, run_id, "other-owner", "ws-other", 3, first=50)
    captured: dict = {}
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _capture_driver(engine, captured)

        async def _offset(*a, **k):
            return 0

        engine._compute_resume_offset = _offset
        with _Spy() as spy:
            await engine.resume_run(run_id)
    assert captured.get("start_seq") == 5
    assert 0 not in spy.reads, f"resume_run seed read whole log: {spy.reads}"
    assert spy.max_calls == 1
    session.close()


@pytest.mark.issue("ISS-639")
@pytest.mark.asyncio
async def test_replay_clarify_seed_uses_bounded_aggregate():
    session, db_engine = _make_session()
    run_id = f"iss639c-{uuid.uuid4().hex[:8]}"
    owner, ws = "iss639c-user", "ws-iss639c"
    _seed_workflow_run(
        session, run_id, owner=owner, status="waiting_for_user", workspace_id=ws
    )
    qs = [
        {
            "question_id": "r1_q1",
            "question_text": "?",
            "options": ["y", "n"],
            "answer_type": "single_choice",
            "impact_level": "high",
            "ambiguity_category": "Functional Scope",
        }
    ]
    await _seed_open_questionnaire_gate(session, run_id, owner, ws, qs)
    await _seed_tail(session, run_id, owner, ws, 7, first=2)  # tail seq 8
    captured: dict = {}
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _capture_driver(engine, captured)
        with _Spy() as spy:
            await engine._replay_clarify_run(run_id)
    assert captured.get("start_seq") == 9
    # One whole-log read is the legitimate content read (derive_open_gate / questions).
    assert spy.reads.count(0) == 1, f"seed must not re-read the whole log: {spy.reads}"
    assert spy.max_calls == 1
    session.close()


@pytest.mark.issue("ISS-873")
@pytest.mark.asyncio
async def test_is_resumable_in_flight_probe_is_bounded():
    session, db_engine = _make_session()
    run_id = f"iss873-{uuid.uuid4().hex[:8]}"
    owner, ws = "iss873-user", "ws-iss873"
    _seed_workflow_run(
        session, run_id, owner=owner, status="generating", workspace_id=ws
    )
    await _seed_tail(session, run_id, owner, ws, 3)
    from app.models.workflow import WorkflowRun

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        wr = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        with _Spy() as spy:
            result = await engine._is_resumable_in_flight(wr)
    assert result is True
    assert not spy.reads, f"existence probe read whole log: {spy.reads}"
    session.close()


@pytest.mark.issue("ISS-874")
@pytest.mark.asyncio
async def test_append_event_next_seq_does_not_read_whole_log():
    session, _db = _make_session()
    run_id = f"iss874-{uuid.uuid4().hex[:8]}"
    owner, ws = "iss874-user", "ws-iss874"
    _seed_workflow_run(
        session, run_id, owner=owner, status="generating", workspace_id=ws
    )
    await _seed_tail(session, run_id, owner, ws, 3)
    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    with _Spy() as spy:
        created, seq = await store.append_event_next_seq(
            run_id, event_id="new-1", type="chat_message", payload_json={}
        )
    assert (created, seq) == (True, 4)
    assert not spy.reads, f"append_event_next_seq read whole log: {spy.reads}"
    session.close()
