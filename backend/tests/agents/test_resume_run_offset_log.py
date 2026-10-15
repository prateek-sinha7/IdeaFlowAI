"""QA-KB-090 / ISS-950: resume_run's offset log must use the plan step count.

For a manifest-less prototype_v2_revision (registry roster 1, plan 3) the log must read
"at step offset 1/3" and must not say "all steps complete" while steps remain.
"""

import asyncio
import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
import app.models.database as db_mod
from app.models.database import Base
from app.models.workflow import WorkflowRun
import agents.execution_engine.engine as engine_mod
from agents.execution_engine.engine import ExecutionEngine, compile_for_run


def _resume_logs(monkeypatch, caplog, typ: str, offset: int) -> list[str]:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=eng)
    maker = sessionmaker(
        bind=eng, autocommit=False, autoflush=False, expire_on_commit=False
    )
    session = maker()
    session.add(
        WorkflowRun(
            id="r1",
            user_id="u1",
            owner_id="u1",
            workspace_id="ws",
            status="generating",
            type=typ,
            input="brief",
        )
    )
    session.commit()
    monkeypatch.setattr(db_mod, "SessionLocal", maker)
    orig = engine_mod.ScopedStore
    monkeypatch.setattr(
        engine_mod,
        "ScopedStore",
        lambda *a, **k: orig(*a, **{**k, "session": k.get("session", session)}),
    )

    engine = ExecutionEngine()

    async def noop_drive(run_id, **kw):
        return None

    async def fake_offset(*a, **k):
        return offset

    monkeypatch.setattr(engine, "_drive_resumed_stream", noop_drive)
    monkeypatch.setattr(engine, "_compute_resume_offset", fake_offset)
    with caplog.at_level(logging.INFO, logger="agents.execution_engine.engine"):
        asyncio.run(engine.resume_run("r1"))
    return [r.getMessage() for r in caplog.records]


@pytest.mark.issue("ISS-950")
def test_offset_log_uses_plan_step_count(monkeypatch, caplog):
    """ISS-950 — offset 1 of a 3-step plan logs 1/3, not 1/1."""
    assert len(compile_for_run("prototype_v2_revision").steps) == 3
    msgs = _resume_logs(monkeypatch, caplog, "prototype_v2_revision", 1)
    assert any("at step offset 1/3" in m for m in msgs), msgs


@pytest.mark.issue("ISS-950")
def test_no_all_steps_complete_while_steps_remain(monkeypatch, caplog):
    """ISS-950 — offset 2 of 3 must not log 'all steps complete'."""
    msgs = _resume_logs(monkeypatch, caplog, "prototype_v2_revision", 2)
    assert not any("all steps complete" in m for m in msgs), msgs
