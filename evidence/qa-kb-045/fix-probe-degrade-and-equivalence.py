"""QA-KB-045 fixer probe (scratch, not a repo test).

1. Degrade guards: resume_run / _replay_clarify_run seed start_seq=1 and
   _is_resumable_in_flight returns False when ScopedStore._max_event_seq raises.
2. ISS-873 exactness: bool(read_events(after_seq=0)) == (_max_event_seq > 0).
3. ISS-874 equivalence: the pre-fix append_event_next_seq loop (copied verbatim
   below) and the fixed method give the same (created, seq) and the same final
   rows on every scenario.

All on in-memory SQLite. DATABASE_URL is pinned to a scratch SQLite file BEFORE
any app import so nothing can reach the developer Postgres.
"""

import asyncio
import os
import sys
import uuid

SCRATCH = os.path.dirname(os.path.abspath(__file__))
BACKEND = "/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/backend"
os.environ["DATABASE_URL"] = f"sqlite:///{SCRATCH}/probe.db"
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

import app.models  # noqa: E402,F401
from agents.authz import ScopedStore, StoreTimeout  # noqa: E402
from app.models.run_event import RunEvent  # noqa: E402
from tests.integration.agents.test_restart_resume_db import (  # noqa: E402
    _ResumeHarness,
    _make_session,
    _seed_open_questionnaire_gate,
    _seed_workflow_run,
)

RESULTS: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


async def seed_tail(session, run_id, owner, ws, n, first=1):
    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    for seq in range(first, first + n):
        await store.append_event(
            run_id, seq=seq, event_id=f"t-{seq}", type=f"agent_chunk_{seq}",
            payload_json={"seq": seq},
        )
    session.commit()


class RaiseMax:
    def __init__(self, exc):
        self.exc = exc

    def __enter__(self):
        self.orig = ScopedStore._max_event_seq
        exc = self.exc

        async def _boom(self_, rid, *a, **k):
            raise exc

        ScopedStore._max_event_seq = _boom
        return self

    def __exit__(self, *e):
        ScopedStore._max_event_seq = self.orig


# ── 1. degrade guards ────────────────────────────────────────────────────────
async def degrade_resume_run(exc):
    session, db_engine = _make_session()
    run_id = f"dg-{uuid.uuid4().hex[:8]}"
    owner, ws = "dg-user", "ws-dg"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")
    await seed_tail(session, run_id, owner, ws, 4)
    captured = {}
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()

        async def _fake_drive(rid, **kw):
            captured["start_seq"] = kw.get("start_seq")

        async def _offset(*a, **k):
            return 0

        engine._drive_resumed_stream = _fake_drive
        engine._compute_resume_offset = _offset
        raised = None
        with RaiseMax(exc):
            try:
                await engine.resume_run(run_id)
            except Exception as e:  # noqa: BLE001
                raised = e
    session.close()
    return raised, captured.get("start_seq")


async def degrade_replay_clarify(exc):
    session, db_engine = _make_session()
    run_id = f"dgc-{uuid.uuid4().hex[:8]}"
    owner, ws = "dgc-user", "ws-dgc"
    _seed_workflow_run(session, run_id, owner=owner, status="waiting_for_user", workspace_id=ws)
    qs = [{"question_id": "r1_q1", "question_text": "?", "options": ["y", "n"],
           "answer_type": "single_choice", "impact_level": "high",
           "ambiguity_category": "Functional Scope"}]
    await _seed_open_questionnaire_gate(session, run_id, owner, ws, qs)
    await seed_tail(session, run_id, owner, ws, 7, first=2)
    captured = {}
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()

        async def _fake_drive(rid, **kw):
            captured["start_seq"] = kw.get("start_seq")

        engine._drive_resumed_stream = _fake_drive
        raised = None
        with RaiseMax(exc):
            try:
                await engine._replay_clarify_run(run_id)
            except Exception as e:  # noqa: BLE001
                raised = e
    session.close()
    return raised, captured.get("start_seq")


async def resumable_probe(exc=None, seed_scope="own"):
    from app.models.workflow import WorkflowRun

    session, db_engine = _make_session()
    run_id = f"rp-{uuid.uuid4().hex[:8]}"
    owner, ws = "rp-user", "ws-rp"
    _seed_workflow_run(session, run_id, owner=owner, status="generating", workspace_id=ws)
    if seed_scope == "own":
        await seed_tail(session, run_id, owner, ws, 3)
    elif seed_scope == "other":
        await seed_tail(session, run_id, "other-owner", "ws-other", 3)
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        wr = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        raised = None
        result = None
        try:
            if exc is not None:
                with RaiseMax(exc):
                    result = await engine._is_resumable_in_flight(wr)
            else:
                result = await engine._is_resumable_in_flight(wr)
        except Exception as e:  # noqa: BLE001
            raised = e
        # ISS-873 exactness, straight on the store, same scope as the engine.
        store = ScopedStore(owner_id=owner, workspace_id=ws)
        old_form = bool(await store.read_events(run_id, after_seq=0))
        new_form = (await store._max_event_seq(run_id)) > 0
    session.close()
    return raised, result, old_form, new_form


# ── 3. ISS-874: the PRE-FIX loop, verbatim from authz.py before this change ──
async def old_append_event_next_seq(self, run_id, *, event_id, type, payload_json,
                                    _max_attempts=8):
    from sqlalchemy.exc import IntegrityError

    for _ in range(max(1, _max_attempts)):
        existing = await self.read_events(run_id, after_seq=0)
        for row in existing:
            if getattr(row, "event_id", None) == event_id:
                return False, int(getattr(row, "seq", 0) or 0)  # idempotent no-op
        next_seq = (
            max((int(getattr(r, "seq", 0) or 0) for r in existing), default=0) + 1
        )
        try:
            await self.append_event(run_id, next_seq, event_id, type, payload_json)
            return True, next_seq
        except IntegrityError:
            if self._session is not None:
                self._session.rollback()
            continue
    raise RuntimeError(
        f"append_event_next_seq: exhausted seq-allocation retries for run {run_id!r}"
    )


def dump(session, run_id):
    session.expire_all()
    rows = session.query(RunEvent).filter(RunEvent.run_id == run_id).all()
    return sorted((r.owner_id, r.workspace_id, r.seq, r.event_id) for r in rows)


async def scenario(name, impl):
    """Run one scenario with `impl` ('old'|'new'); return (calls, final rows)."""
    session, db_engine = _make_session()
    run_id = "run-874"
    owner, ws = "alice", "ws-1"
    _seed_workflow_run(session, run_id, owner=owner, status="generating", workspace_id=ws)
    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)

    async def call(event_id, st=store):
        if impl == "old":
            return await old_append_event_next_seq(
                st, run_id, event_id=event_id, type="chat_message", payload_json={}
            )
        return await st.append_event_next_seq(
            run_id, event_id=event_id, type="chat_message", payload_json={}
        )

    out = []
    if name == "S1_empty":
        out.append(await call("new-1"))
    elif name == "S2_tail3":
        await seed_tail(session, run_id, owner, ws, 3)
        out.append(await call("new-1"))
    elif name == "S3_replay_existing":
        await seed_tail(session, run_id, owner, ws, 3)
        out.append(await call("t-2"))
    elif name == "S4_same_event_id_other_owner":
        await seed_tail(session, run_id, owner, ws, 3)
        o = ScopedStore(owner_id="bob", workspace_id=ws, session=session)
        await o.append_event(run_id, 50, "x", "chat_message", {})
        out.append(await call("x"))
    elif name == "S5_same_event_id_other_ws":
        await seed_tail(session, run_id, owner, ws, 3)
        o = ScopedStore(owner_id=owner, workspace_id="ws-2", session=session)
        await o.append_event(run_id, 60, "x", "chat_message", {})
        out.append(await call("x"))
    elif name == "S6_higher_seq_other_scope":
        await seed_tail(session, run_id, owner, ws, 3)
        await seed_tail(session, run_id, "bob", "ws-9", 3, first=50)
        out.append(await call("new-1"))
        out.append(await call("new-1"))  # replay
        out.append(await call("new-2"))
    elif name == "S7_sessionless_store":
        await seed_tail(session, run_id, owner, ws, 3)
        with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine):
            sl = ScopedStore(owner_id=owner, workspace_id=ws)  # session=None → _run_bounded thread path
            out.append(await call("new-1", sl))
            out.append(await call("new-1", sl))  # replay
    elif name == "S8_duplicate_event_id_race":
        # A concurrent writer commits OUR event_id at the tail between our read
        # and our insert: the insert collides, the retry must resolve it as the
        # idempotent no-op it is.
        await seed_tail(session, run_id, owner, ws, 3)
        state = {"n": 0}
        if impl == "old":
            real = store.read_events

            async def _stale(rid, after_seq):
                state["n"] += 1
                if state["n"] == 1:
                    snap = await real(rid, after_seq=after_seq)
                    await ScopedStore(owner_id=owner, workspace_id=ws, session=session
                                      ).append_event(rid, 4, "dup", "chat_message", {})
                    return snap  # stale: misses the concurrent row
                return await real(rid, after_seq=after_seq)

            store.read_events = _stale
        else:
            real = store._max_event_seq

            async def _stale(rid):
                state["n"] += 1
                if state["n"] == 1:
                    snap = await real(rid)
                    await ScopedStore(owner_id=owner, workspace_id=ws, session=session
                                      ).append_event(rid, 4, "dup", "chat_message", {})
                    return snap  # stale: misses the concurrent row
                return await real(rid)

            store._max_event_seq = _stale
        out.append(await call("dup"))
    rows = dump(session, run_id)
    session.close()
    return out, rows


async def main():
    # 1. degrade guards (generic exception and the real StoreTimeout)
    for exc in (RuntimeError("boom"), StoreTimeout("ScopedStore._max_event_seq timed out")):
        r, s = await degrade_resume_run(exc)
        check(f"degrade resume_run [{type(exc).__name__}]", r is None and s == 1,
              f"raised={r!r} start_seq={s}")
        r, s = await degrade_replay_clarify(exc)
        check(f"degrade _replay_clarify_run [{type(exc).__name__}]", r is None and s == 1,
              f"raised={r!r} start_seq={s}")
        r, res, _o, _n = await resumable_probe(exc=exc)
        check(f"degrade _is_resumable_in_flight [{type(exc).__name__}]",
              r is None and res is False, f"raised={r!r} result={res}")

    # 2. ISS-873 exactness + classifier result per scope
    for scope, want in (("own", True), ("other", False), ("none", False)):
        r, res, old_form, new_form = await resumable_probe(seed_scope=scope)
        check(f"ISS-873 scope={scope}", r is None and res is want and old_form == new_form,
              f"result={res} old_form={old_form} new_form={new_form}")

    # 3. ISS-874 old vs new
    for name in ("S1_empty", "S2_tail3", "S3_replay_existing",
                 "S4_same_event_id_other_owner", "S5_same_event_id_other_ws",
                 "S6_higher_seq_other_scope", "S7_sessionless_store",
                 "S8_duplicate_event_id_race"):
        old = await scenario(name, "old")
        new = await scenario(name, "new")
        check(f"ISS-874 {name}", old == new, f"old={old[0]} new={new[0]} rows_equal={old[1] == new[1]}")

    width = max(len(n) for n, _, _ in RESULTS)
    for n, ok, d in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {n.ljust(width)}  {d}")
    print(f"\n{sum(ok for _, ok, _ in RESULTS)}/{len(RESULTS)} checks passed")


asyncio.run(main())
