"""Read-only timing probe for QA-KB-045: the REAL ScopedStore code paths on the biggest local runs.

Only SELECTs are issued (read_events / _max_event_seq are pure reads). Uses session=None so the
real _run_bounded path (worker thread + 10 s asyncio.wait_for) is exercised, exactly like the
engine's tail_store in resume_run.
"""
import asyncio
import sys
import time

sys.path.insert(0, ".")

from sqlalchemy import create_engine, text  # noqa: E402

from agents.authz import _STORE_CALL_TIMEOUT_SECONDS, ScopedStore, StoreTimeout  # noqa: E402
from app.core.config import settings  # noqa: E402

eng = create_engine(
    settings.DATABASE_URL,
    connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=60000"},
)
with eng.connect() as c:
    targets = c.execute(
        text(
            "SELECT run_id, owner_id, workspace_id, count(*) n FROM run_events "
            "GROUP BY run_id, owner_id, workspace_id ORDER BY n DESC LIMIT 4"
        )
    ).all()

print("StoreTimeout bound (s):", _STORE_CALL_TIMEOUT_SECONDS)


async def main():
    for run_id, owner, ws, n in targets:
        store = ScopedStore(owner_id=owner, workspace_id=ws)  # session=None -> _run_bounded
        t0 = time.monotonic()
        try:
            rows = await store.read_events(run_id, after_seq=0)
            old = max((r.seq for r in rows), default=0) + 1
            t_read = time.monotonic() - t0
            res = "rows=%d start=%d" % (len(rows), old)
        except StoreTimeout as e:
            t_read = time.monotonic() - t0
            res = "StoreTimeout (%s)" % e
            old = None
        del_rows = None  # noqa: F841
        t1 = time.monotonic()
        new = (await store._max_event_seq(run_id)) + 1
        t_max = time.monotonic() - t1
        print(
            "run=%s... rows_in_db=%-7d read_events+max: %6.2fs  [%s]   _max_event_seq+1: %6.4fs  start=%d  same=%s"
            % (str(run_id)[:8], n, t_read, res, t_max, new, old == new)
        )


asyncio.run(main())
