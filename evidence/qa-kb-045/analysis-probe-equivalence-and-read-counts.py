"""Scratch probe for QA-KB-045 (NOT part of the repo, NOT a test).

Offline, in-memory SQLite. Proves (1) the equivalence the root card asks to be verified on a
seeded fixture, and (2) the current (pre-fix) read_events call counts on the two real drivers.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

sys.path.insert(0, ".")

from sqlalchemy import event  # noqa: E402

from agents.authz import ScopedStore  # noqa: E402
from tests.integration.agents.test_restart_resume_db import (  # noqa: E402
    _ResumeHarness,
    _make_session,
    _seed_open_questionnaire_gate,
    _seed_workflow_run,
)


async def exp1_equivalence() -> None:
    print("=== EXP 1: max(read_events)+1  vs  _max_event_seq+1  (seeded fixture) ===")
    session, db = _make_session()
    stmts: list[str] = []

    @event.listens_for(db, "before_cursor_execute")
    def _grab(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        stmts.append(" ".join(statement.split()))

    r1, r2 = "r-with-rows", "r-empty"
    for rid in (r1, r2):
        _seed_workflow_run(session, rid, owner="A", status="generating")

    def store(owner, ws):
        return ScopedStore(owner_id=owner, workspace_id=ws, session=session)

    # scope (A, ws1): seq 1..7 ; scope (A, ws2): seq 1..3 and 50 ; scope (B, ws1): seq 1..12
    for seq in range(1, 8):
        await store("A", "ws1").append_event(r1, seq, f"a1-{seq}", "t", {"n": seq})
    for seq in (1, 2, 3, 50):
        await store("A", "ws2").append_event(r1, seq, f"a2-{seq}", "t", {"n": seq})
    for seq in range(1, 13):
        await store("B", "ws1").append_event(r1, seq, f"b1-{seq}", "t", {"n": seq})
    session.commit()

    cases = [
        ("A", "ws1", r1),
        ("A", "ws2", r1),
        ("B", "ws1", r1),
        ("A", None, r1),  # workspace_id None -> IS NULL -> nothing
        ("A", "ws-unknown", r1),
        ("nobody", "ws1", r1),
        ("A", "ws1", r2),  # run with no rows
        ("A", "ws1", "missing-run"),
    ]
    bad = 0
    for owner, ws, rid in cases:
        s = store(owner, ws)
        rows = await s.read_events(rid, after_seq=0)
        old = max((r.seq for r in rows), default=0) + 1
        new = (await s._max_event_seq(rid)) + 1
        flag = "OK " if old == new else "DIFF"
        bad += old != new
        print(f"  {flag} owner={owner!r:9} ws={ws!r:13} run={rid!r:15} rows_materialised={len(rows):3d} old={old:3d} new={new:3d}")
    print("  => mismatches:", bad)

    # _is_resumable_in_flight sibling: bool(read_events) vs _max_event_seq > 0
    sib_bad = 0
    for owner, ws, rid in cases:
        s = store(owner, ws)
        old_b = bool(await s.read_events(rid, after_seq=0))
        new_b = (await s._max_event_seq(rid)) > 0
        sib_bad += old_b != new_b
    print("  => existence-probe (bool(read_events) vs _max_event_seq>0) mismatches:", sib_bad)

    stmts.clear()
    await store("A", "ws1").read_events(r1, after_seq=0)
    print("  SQL read_events      :", [x for x in stmts if "run_events" in x][-1][:230])
    stmts.clear()
    await store("A", "ws1")._max_event_seq(r1)
    print("  SQL _max_event_seq   :", [x for x in stmts if "run_events" in x][-1][:230])
    session.close()


async def exp2_driver_read_counts() -> None:
    print("\n=== EXP 2: pre-fix read_events(after_seq=0) calls on the REAL drivers ===")
    # --- resume_run -----------------------------------------------------------------
    session, db = _make_session()
    run_id = f"p-{uuid.uuid4().hex[:6]}"
    owner, ws = "p-user", "ws-p"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")
    pre = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    N = 9
    for seq in range(1, N + 1):
        await pre.append_event(run_id, seq, f"pre-{seq}", f"agent_chunk_{seq}", {"n": seq})
    session.commit()

    calls: list[tuple[str, int]] = []
    orig_read, orig_max = ScopedStore.read_events, ScopedStore._max_event_seq

    async def _read(self, rid, after_seq=0, **kw):
        calls.append(("read_events", after_seq))
        return await orig_read(self, rid, after_seq=after_seq, **kw)

    async def _max(self, rid):
        calls.append(("_max_event_seq", -1))
        return await orig_max(self, rid)

    ScopedStore.read_events, ScopedStore._max_event_seq = _read, _max
    try:
        with _ResumeHarness(session, {}, fail_on=set(), db_engine=db) as h:
            engine = h.make_engine()
            captured: dict = {}

            async def _offset0(*a, **k):
                return 0

            async def _spy_drive(rid, **k):
                captured.update(k)

            engine._compute_resume_offset = _offset0  # isolate: offset computation is not the seed
            engine._drive_resumed_stream = _spy_drive
            await engine.resume_run(run_id)
    finally:
        ScopedStore.read_events, ScopedStore._max_event_seq = orig_read, orig_max
    print(f"  resume_run  (tail N={N}): start_seq={captured.get('start_seq')}  expected N+1={N + 1}")
    print(f"    store calls: {calls}")
    session.close()

    # --- _replay_clarify_run -----------------------------------------------------------
    session, db = _make_session()
    run_id = f"c-{uuid.uuid4().hex[:6]}"
    owner, ws = "c-user", "ws-c"
    _seed_workflow_run(
        session, run_id, owner=owner, status="waiting_for_user", type_="prototype", workspace_id=ws
    )
    q = [{"question_id": "r1_q1", "question_text": "Scope?", "options": ["a", "b"],
          "answer_type": "single_choice", "impact_level": "high",
          "ambiguity_category": "Functional Scope"}]
    await _seed_open_questionnaire_gate(session, run_id, owner, ws, q, round_num=1)
    pre = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    for seq in range(2, 9):  # tail grows to seq 8
        await pre.append_event(run_id, seq, f"pad-{seq}", f"agent_chunk_{seq}", {"n": seq})
    session.commit()

    calls.clear()
    ScopedStore.read_events, ScopedStore._max_event_seq = _read, _max
    try:
        with _ResumeHarness(session, {}, fail_on=set(), db_engine=db) as h:
            engine = h.make_engine()
            captured = {}

            async def _spy_drive2(rid, **k):
                captured.update(k)

            engine._drive_resumed_stream = _spy_drive2
            await engine._replay_clarify_run(run_id)
    finally:
        ScopedStore.read_events, ScopedStore._max_event_seq = orig_read, orig_max
    print(f"  _replay_clarify_run (tail=8): start_seq={captured.get('start_seq')}  expected 9")
    print(f"    store calls: {calls}")
    session.close()


async def main() -> None:
    await exp1_equivalence()
    await exp2_driver_read_counts()


asyncio.run(main())
