"""QA-KB-105 analysis probe -- NOT part of the test suite (lives under evidence/, run by path).

Question: when a RESUME reaches the engine's `workflow_unsatisfiable` exit
(engine.py:5239-5249: one `error` frame, then `return`), what is the end state through the REAL
endpoint / the REAL restart scan with the REAL engine?  Four shapes:

  U  user POST /resume of a failed / cancelled run          (_drive_user_resume + _reconcile_terminal_status)
  R  restart auto-resume, branch (b), two boots             (restore_non_terminal_runs -> resume_run)
  G  restart re-arm of a gate-parked run, branch (a), two boots
        G-review   open review gate   (_rearm_gate_run -> resume_run)
        G-clarify  open clarify round (_rearm_gate_run -> _replay_clarify_run)
  C  control: the same user resume with the DAG left satisfiable (the harness is sound)

The DAG is forced unsatisfiable by patching WorkflowResolver.validate (the same call the engine
makes at engine.py:5215); nothing else is faked beyond what test_restart_resume_db.py's harness
already fakes.  Everything is offline: in-memory SQLite (StaticPool) shared by the harness, the
app's global engine pinned to a throwaway sqlite FILE before `app.*` is imported, no model
call, no network, no live DB.

Run (from backend/):
  DATABASE_URL=sqlite:////<scratch>/probe.db KB105_OUT=<out.txt> PYTHONPATH=. .venv/bin/python -m pytest \
      ../evidence/qa-kb-105/analysis-plugins/kb105_probe_test.py -c pyproject.toml --rootdir=. \
      -p no:cacheprovider -q -s
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

# Hard guard: refuse to run against anything but a throwaway sqlite file.
assert os.environ.get("DATABASE_URL", "").startswith("sqlite:"), "set DATABASE_URL=sqlite:///... first"

import app.models  # noqa: E402,F401  (registers every model on Base.metadata)
from app.models.database import Base, engine as _global_engine  # noqa: E402

Base.metadata.create_all(bind=_global_engine)

import app.api.run_engine as ws_mod  # noqa: E402
import tests.integration.agents.test_qa_kb_102_silent_resume as t  # noqa: E402
from tests.integration.agents.test_restart_resume_db import (  # noqa: E402
    _make_session,
    _ResumeHarness,
    _seed_open_questionnaire_gate,
    _seed_open_review_gate,
    _wire_user_resume_drive,
)

OUT = os.environ["KB105_OUT"]
OWNER, WS = t.OWNER, t.WS


def emit(line: str = "") -> None:
    with open(OUT, "a") as fh:
        fh.write(line + "\n")


def _clear() -> None:
    for d in (ws_mod._PIPELINE_TASKS, ws_mod._PIPELINE_QUEUES, ws_mod._CANCEL_EVENTS, ws_mod._SUBSCRIBERS):
        d.clear()


def _force_unsatisfiable(monkeypatch) -> None:
    """Make the engine's own DAG validation (engine.py:5215) return unsatisfiable."""
    from agents.execution_engine import resolver as r

    def _validate(self, agents):
        return r.ValidationResult(
            satisfiable=False,
            errors=["Agent 'custom-agent:b' consumes 'x' but no upstream agent produces it."],
        )

    monkeypatch.setattr(r.WorkflowResolver, "validate", _validate)


def _dump(label, session, run_id, items=None) -> None:
    from agents.capabilities.gate_pendency import derive_open_gate, strip_premature_stops
    from app.models.run_event import RunEvent
    from app.models.workflow import WorkflowRun

    session.expire_all()
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    evs = session.query(RunEvent).filter(RunEvent.run_id == run_id).order_by(RunEvent.seq.asc()).all()
    emit(
        f"== {label}: status={row.status!r} error={row.error!r} "
        f"completed_at={'SET' if row.completed_at else None} duration={row.duration!r}"
    )
    emit(
        "   tail: "
        + repr(
            [
                (
                    e.seq,
                    e.type,
                    (e.payload_json or {}).get("error")
                    if e.type in ("pipeline_failed", "error")
                    else (e.payload_json or {}).get("satisfiable")
                    if e.type == "workflow_validated"
                    else None,
                )
                for e in evs
            ]
        )
    )
    types = [e.type for e in evs]
    emit(
        f"   counts: run_resuming={types.count('run_resuming')} error={types.count('error')} "
        f"pipeline_failed={types.count('pipeline_failed')} pipeline_complete={types.count('pipeline_complete')} "
        f"pipeline_cancelled={types.count('pipeline_cancelled')}"
    )
    emit(
        f"   derive_open_gate(unfiltered)={derive_open_gate(evs)} "
        f"derive_open_gate(strip_premature_stops)={derive_open_gate(strip_premature_stops(evs))}"
    )
    if items is not None:
        emit(
            "   live queue: "
            + repr([None if i is None else (i["type"], (i["data"] or {}).get("error")) for i in items])
        )
    emit(f"   registries: queues={list(ws_mod._PIPELINE_QUEUES)} tasks={list(ws_mod._PIPELINE_TASKS)}")


async def _boot(session, db_engine, monkeypatch, run_id) -> None:
    """One backend boot: restore_non_terminal_runs on a fresh engine over the SAME durable DB."""
    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _wire_user_resume_drive(monkeypatch, db_engine, engine)
        t._arm(engine)
        await engine.restore_non_terminal_runs()
        for _ in range(200):
            await asyncio.sleep(0.05)
            task = ws_mod._PIPELINE_TASKS.get(run_id)
            if task is None or task.done():
                break
        await asyncio.sleep(0.3)


# --------------------------------------------------------------------------------------- U
async def test_u_user_resume_failed(monkeypatch):
    _clear()
    _force_unsatisfiable(monkeypatch)
    session, db = _make_session()
    rid = f"u-failed-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "failed", "custom", t._manifest(broken=False))
    await t._seed_prior(session, rid, "failed")
    items = await t._post_resume(monkeypatch, session, db, rid)
    _dump("U1 user resume, prior=failed, DAG unsatisfiable", session, rid, items)


async def test_u_user_resume_cancelled(monkeypatch):
    from agents.authz import ScopedStore

    _clear()
    _force_unsatisfiable(monkeypatch)
    session, db = _make_session()
    rid = f"u-canc-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "cancelled", "custom", t._manifest(broken=False))
    await t._seed_prior(session, rid, "failed")
    st = ScopedStore(owner_id=OWNER, workspace_id=WS, session=session)
    await st.append_event(rid, seq=99, event_id="ev-cx", type="pipeline_cancelled", payload_json={})
    session.commit()
    items = await t._post_resume(monkeypatch, session, db, rid)
    _dump("U2 user resume, prior=cancelled, DAG unsatisfiable", session, rid, items)


async def test_u_user_resume_degraded(monkeypatch):
    _clear()
    _force_unsatisfiable(monkeypatch)
    session, db = _make_session()
    rid = f"u-degr-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "degraded", "custom", t._manifest(broken=False))
    await t._seed_prior(session, rid, "degraded")
    items = await t._post_resume(monkeypatch, session, db, rid)
    _dump("U3 user resume, prior=degraded, DAG unsatisfiable", session, rid, items)


# --------------------------------------------------------------------------------------- R
async def test_r_restart_branch_b(monkeypatch):
    from agents.authz import ScopedStore

    _clear()
    _force_unsatisfiable(monkeypatch)
    session, db = _make_session()
    rid = f"r-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "running", "custom", t._manifest(broken=False))
    store = ScopedStore(owner_id=OWNER, workspace_id=WS, session=session)
    await store.append_event(rid, seq=1, event_id="ev-1", type="pipeline_start", payload_json={"pipeline_run_id": rid})
    await store.append_event(rid, seq=2, event_id="ev-2", type="agent_start", payload_json={"agent_id": "custom-agent:a"})
    await store.append_event(
        rid, seq=3, event_id="ev-3", type="agent_complete",
        payload_json={"agent_id": "custom-agent:a", "duration": 4.2, "total_tokens": 10, "input_tokens": 6, "output_tokens": 4},
    )
    session.commit()
    emit("== R0 before any boot")
    _dump("R0 seeded running row", session, rid)
    for boot in (1, 2):
        await _boot(session, db, monkeypatch, rid)
        _dump(f"R{boot} after boot {boot}, DAG unsatisfiable", session, rid)


# --------------------------------------------------------------------------------------- G
async def test_g_review_gate_rearm(monkeypatch):
    _clear()
    _force_unsatisfiable(monkeypatch)
    session, db = _make_session()
    rid = f"g-rev-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "waiting_for_user", "custom", t._manifest(broken=False))
    await _seed_open_review_gate(session, rid, OWNER, WS, f"{rid}:custom-agent:a:1")
    _dump("G1.0 review-gate parked, seeded", session, rid)
    for boot in (1, 2):
        await _boot(session, db, monkeypatch, rid)
        _dump(f"G1.{boot} review gate, after boot {boot}, DAG unsatisfiable", session, rid)


async def test_g_clarify_rearm(monkeypatch):
    _clear()
    _force_unsatisfiable(monkeypatch)
    session, db = _make_session()
    rid = f"g-cla-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "waiting_for_user", "custom", t._manifest(broken=False))
    questions = [
        {
            "question_id": "r1_q1",
            "question_text": "Replayed?",
            "options": ["yes", "no"],
            "answer_type": "single_choice",
            "impact_level": "high",
            "ambiguity_category": "Functional Scope",
        }
    ]
    await _seed_open_questionnaire_gate(session, rid, OWNER, WS, questions, round_num=1)
    _dump("G2.0 clarify-parked, seeded", session, rid)
    for boot in (1, 2):
        await _boot(session, db, monkeypatch, rid)
        _dump(f"G2.{boot} clarify, after boot {boot}, DAG unsatisfiable", session, rid)


# --------------------------------------------------------------------------------------- C
async def test_c_control_satisfiable(monkeypatch):
    _clear()
    session, db = _make_session()
    rid = f"c-{uuid.uuid4().hex[:6]}"
    t._seed_run(session, rid, "failed", "custom", t._manifest(broken=False))
    await t._seed_prior(session, rid, "failed")
    items = await t._post_resume(monkeypatch, session, db, rid)
    _dump("C user resume, prior=failed, DAG LEFT satisfiable (control)", session, rid, items)
