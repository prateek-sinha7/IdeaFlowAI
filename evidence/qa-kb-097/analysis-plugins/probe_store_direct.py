"""Minimal direct repro: ScopedStore.update_wave_run_merge_state / write_provenance_audit
against an in-memory SQLite session. Run with DATABASE_URL=sqlite:///:memory: (hermetic)."""
import asyncio, uuid, sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.models.database import Base
from app.models.wave_run import WaveRun
from app.models.run_provenance_audit import RunProvenanceAudit
from agents.authz import ScopedStore

eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(bind=eng)
session = sessionmaker(bind=eng, autocommit=False, autoflush=False)()

run_id, owner, ws = str(uuid.uuid4()), "u1", "ws1"
store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)


async def main():
    wid = await store.record_wave_run(run_id, step="sample-wave-worker", wave_index=0, task_ids=["t1"], status="completed")
    print("record_wave_run ->", wid[:8], "(ok)")
    try:
        await store.update_wave_run_merge_state(
            run_id, step_id="sample-wave-worker", merge_state="clean",
            merge_applied='["a"]', merge_conflicts="[]", merge_strategy="git_3way")
        row = session.query(WaveRun).filter(WaveRun.id == wid).one()
        print("update_wave_run_merge_state -> OK, merge_state =", row.merge_state, "strategy =", row.merge_strategy)
    except Exception as exc:
        print("update_wave_run_merge_state -> RAISED", type(exc).__name__, exc)
    try:
        rid = await store.write_provenance_audit(run_id, "snapshot_commit", commit_sha="abc123")
        n = session.query(RunProvenanceAudit).filter(RunProvenanceAudit.run_id == run_id).count()
        print("write_provenance_audit -> OK, rows =", n)
    except Exception as exc:
        print("write_provenance_audit -> RAISED", type(exc).__name__, exc)

asyncio.run(main())
