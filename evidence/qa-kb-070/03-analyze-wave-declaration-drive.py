"""QA-KB-070 / ISS-897 sibling measurement (scratch; OFFLINE scripted model; NO repo writes).

Question: what does deleting `runs_agent_inline = False` from WaveSchedulerStrategy
(backend/agents/capabilities/strategies/wave_scheduler.py:245) do to a REAL run?

Reuses the ISS-097 harness from tests/integration/agents/test_restart_resume_db.py
(`sample_wave`, single-wave plan, in-memory SQLite, scripted model) and adds what the
launch wizard writes when the user ticks the wave worker under "Review gates":

    gate_agent_ids=["sample-wave-worker"]  +  selections["sample-wave-worker"].gates=["human"]

`_count_gate_entries(engine, delegate=False)` counts every entry into `_run_review_gate`
(inline sites AND the declared gates:[human] path) without opening a blocking gate.

  AS SHIPPED : runs_agent_inline = False  -> the declared gate runs     -> expect 1 entry
  UNDECLARED : attribute deleted (== True) -> WR-02 dedupe eats the gate -> expect 0 entries

Run from backend/:
    QA_SCRATCH=/tmp/qa070 .venv/bin/python -I ../evidence/qa-kb-070/03-analyze-wave-declaration-drive.py
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

SCRATCH = Path(os.environ["QA_SCRATCH"])
SCRATCH.mkdir(parents=True, exist_ok=True)
_DB = SCRATCH / "qa_kb_070_wave.db"
if _DB.exists():
    _DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"   # MUST precede any app import
os.environ.setdefault("ENV", "development")
sys.path.insert(0, ".")                            # cwd is backend/

import app.models  # noqa: F401,E402
from app.models.database import Base, engine as _db_engine  # noqa: E402

assert str(_db_engine.url).startswith("sqlite"), f"NOT hermetic: {_db_engine.url}"
Base.metadata.create_all(bind=_db_engine)

from tests.integration.agents.test_restart_resume_db import (  # noqa: E402
    _FIXTURE_ID,
    _SINGLE_WAVE_PLAN,
    _count_gate_entries,
    _make_session,
    _ResumeHarness,
    _seed_workflow_run,
)

WORKER = "sample-wave-worker"
OWNER = "qa070-user"


async def drive(label: str) -> None:
    session, db_engine = _make_session()
    run_id = f"qa070w-{uuid.uuid4().hex[:8]}"
    _seed_workflow_run(session, run_id, owner=OWNER, status="generating")
    events: list[dict] = []
    with _ResumeHarness(
        session, {}, fail_on=set(), db_engine=db_engine, plan=_SINGLE_WAVE_PLAN
    ) as h:
        engine = h.make_engine()
        entries = _count_gate_entries(engine, delegate=False)
        async for ev in engine.execute(
            agents=list(h.specs),
            user_message="Run the wave workflow.",
            pipeline_run_id=run_id,
            pipeline_type=_FIXTURE_ID,
            user_id=OWNER,
            gate_agent_ids=[WORKER],                       # the wizard tick
            selections={WORKER: {"gates": ["human"]}},     # withHumanGate
        ):
            events.append(ev)
    types = [e.get("type") for e in events]
    print(
        f"[{label}] review-gate entries: {len(entries)} {entries}  "
        f"pipeline_complete={'pipeline_complete' in types}  "
        f"errors={sum(1 for t in types if t == 'error')}"
    )
    session.close()


if __name__ == "__main__":
    from agents.capabilities.strategies.wave_scheduler import WaveSchedulerStrategy

    print(f"WaveSchedulerStrategy.runs_agent_inline = {WaveSchedulerStrategy.runs_agent_inline}")
    asyncio.run(drive("AS SHIPPED - runs_agent_inline = False   "))
    WaveSchedulerStrategy.runs_agent_inline = True   # == the attribute deleted (kernel default True)
    asyncio.run(drive("UNDECLARED - runs_agent_inline deleted   "))
