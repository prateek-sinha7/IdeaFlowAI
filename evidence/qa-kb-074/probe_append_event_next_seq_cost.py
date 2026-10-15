"""QA-KB-074 probe: what does ScopedStore.append_event_next_seq call on the CURRENT tree?

Run from backend/ (offline, in-memory SQLite, no live DB, no network):
    PYTHONPATH=. .venv/bin/python ../evidence/qa-kb-074/probe_append_event_next_seq_cost.py

It records every _run_bounded() call (the store's one DB gateway) and every read_events() call made
by one append_event_next_seq invocation, for a fresh event_id and for a replayed one. The three
docstrings named in QA-KB-074 claim the method "re-reads EVERY row" / "reads the whole log".
"""

from __future__ import annotations

import asyncio
import uuid

from agents.authz import ScopedStore
from tests.integration.agents.test_restart_resume_db import _make_session, _seed_workflow_run


async def main() -> None:
    session, _db = _make_session()
    run_id = f"qakb074-{uuid.uuid4().hex[:8]}"
    owner, ws = "qakb074-user", "ws-qakb074"
    _seed_workflow_run(session, run_id, owner=owner, status="generating", workspace_id=ws)
    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    for seq in range(1, 4):
        await store.append_event(
            run_id, seq=seq, event_id=f"t-{seq}", type="agent_chunk", payload_json={"seq": seq}
        )
    session.commit()

    ops: list[str] = []
    reads: list[int] = []
    orig_bounded = ScopedStore._run_bounded
    orig_read = ScopedStore.read_events

    async def _bounded(self_, name, body, **kw):
        ops.append(name)
        return await orig_bounded(self_, name, body, **kw)

    async def _read(self_, rid, after_seq=0, **kw):
        reads.append(after_seq)
        return await orig_read(self_, rid, after_seq=after_seq, **kw)

    ScopedStore._run_bounded = _bounded
    ScopedStore.read_events = _read
    try:
        for label, event_id in (("fresh event_id", "new-1"), ("replayed event_id", "new-1")):
            ops.clear()
            reads.clear()
            created, seq = await store.append_event_next_seq(
                run_id, event_id=event_id, type="chat_message", payload_json={}
            )
            print(f"{label:18s} -> (created={created}, seq={seq})")
            print(f"{'':18s}    _run_bounded calls : {ops}")
            print(f"{'':18s}    read_events calls  : {len(reads)}")
    finally:
        ScopedStore._run_bounded = orig_bounded
        ScopedStore.read_events = orig_read
    session.close()


asyncio.run(main())
