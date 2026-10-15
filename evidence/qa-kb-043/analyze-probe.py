"""QA-KB-043 analyzer probe (ISS-105).  SCRATCH: offline, no server, no LLM, writes nothing in the repo.

What it settles (each section prints raw observations, no pass/fail framing):
  0. how many event-loop turns other tasks get while shutdown_run_infrastructure() runs, per config
  1. a naive gather(shutdown, mutator) with only queues seeded -- does the mutator ever run first?
  2. mutation inside the ONLY pre-snapshot window (step 1 Concierge await): a driver finishing
     (_cleanup_pipeline) and a run registering, then what the summary and the queues look like
  3. a subscriber detach (_unsubscribe) swept across N loop turns relative to shutdown
  4. which registries a plain subscriber detach actually mutates
  5. the step-2 guards: a queue whose put_nowait raises, and a registry whose keys() raises

DATABASE_URL is pinned to a throwaway sqlite file BEFORE any app import, exactly as
tests/conftest.py does, because backend/.env points at the live Postgres.

Run from backend/:   .venv/bin/python <this file>
"""

import asyncio
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='qa_kb_043_')}/probe.db"
sys.path.insert(0, os.getcwd())

import app.agents.checkpointer as cp  # noqa: E402
import app.api.run_engine as eng  # noqa: E402
import app.api.run_shutdown as sd  # noqa: E402
from app.api import run_commands as rc  # noqa: E402


async def _noop_close() -> None:
    return None


cp.close_checkpointer = _noop_close  # step 4 resolves this name at call time
sd.settings.SHUTDOWN_STOP_RUNS = False  # the production branch
sd.settings.SHUTDOWN_CONCIERGE_DRAIN_SECONDS = 5.0
sd.settings.SHUTDOWN_TASK_DRAIN_SECONDS = 1.0


def reset() -> None:
    eng._PIPELINE_QUEUES.clear()
    eng._PIPELINE_TASKS.clear()
    eng._CANCEL_EVENTS.clear()
    eng._SUBSCRIBERS.clear()
    eng._QUEUE_GENERATIONS.clear()
    for t, _g in list(eng._PUMP_TASKS.values()):
        t.cancel()
    eng._PUMP_TASKS.clear()
    rc._CONCIERGE_STREAM_TASKS.clear()
    rc._LIVE_ECTX.clear()


def drain(q: asyncio.Queue) -> list:
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except asyncio.QueueEmpty:
            return out


async def loop_turns_during(coro):
    """Event-loop turns other tasks got while ``coro`` ran (0 == it never suspended)."""
    n = 0
    stop = False

    async def ticker():
        nonlocal n
        while not stop:
            n += 1
            await asyncio.sleep(0)

    t = asyncio.create_task(ticker())
    await asyncio.sleep(0)  # let the ticker take its first turn
    base = n
    res = await coro
    delta = n - base
    stop = True
    await t
    return res, delta


def seed_queues(*ids):
    return {r: eng._get_or_create_queue(r) for r in ids}


async def pending_task():
    ev = asyncio.Event()

    async def _w():
        await ev.wait()

    return asyncio.create_task(_w())


async def main() -> None:
    print("=== 0. loop turns granted to other tasks while shutdown_run_infrastructure() runs ===")
    reset()
    seed_queues("run-a", "run-b", "run-c")
    s, d = await loop_turns_during(sd.shutdown_run_infrastructure())
    print(f"A queues only          : turns={d}  queues_sentinelled={s['queues_sentinelled']} errors={s['errors']}")

    reset()
    seed_queues("run-a", "run-b", "run-c")
    eng._PIPELINE_TASKS["run-a"] = await pending_task()
    await eng._subscribe("run-a")  # creates the pump task
    s, d = await loop_turns_during(sd.shutdown_run_infrastructure())
    print(f"B + one pump (step 2b) : turns={d}  pump_drained={s['pump_tasks_drained']} errors={s['errors']}")

    reset()
    seed_queues("run-a", "run-b", "run-c")

    async def _short():
        await asyncio.sleep(0.05)

    ct = asyncio.create_task(_short())
    rc._CONCIERGE_STREAM_TASKS.add(ct)
    ct.add_done_callback(rc._CONCIERGE_STREAM_TASKS.discard)
    s, d = await loop_turns_during(sd.shutdown_run_infrastructure())
    print(f"C + concierge (step 1) : turns>0 is {d > 0}  concierge_persisted={s['concierge_persisted']} errors={s['errors']}")

    print("\n=== 1. naive gather(shutdown, mutator), only queues seeded ===")
    reset()
    seed_queues("run-a", "run-b", "run-c")
    order = []

    async def shut():
        s = await sd.shutdown_run_infrastructure()
        order.append("shutdown_done")
        return s

    async def mut():
        order.append(f"mutator_start(queues_seen={sorted(eng._PIPELINE_QUEUES)})")
        eng._cleanup_pipeline("run-b")
        order.append("mutator_done")

    s, _ = await asyncio.gather(shut(), mut())
    print("order:", order)
    print("queues_sentinelled:", s["queues_sentinelled"], "errors:", s["errors"])

    print("\n=== 2. mutation inside the only pre-snapshot window (step 1 Concierge await) ===")
    reset()
    conc_release = asyncio.Event()

    async def conc():
        await conc_release.wait()

    ct = asyncio.create_task(conc())
    rc._CONCIERGE_STREAM_TASKS.add(ct)
    ct.add_done_callback(rc._CONCIERGE_STREAM_TASKS.discard)
    queues = seed_queues("run-a", "run-b", "run-c", "run-e")
    drivers = {}
    for r in queues:
        drivers[r] = await pending_task()
        eng._PIPELINE_TASKS[r] = drivers[r]
        eng._CANCEL_EVENTS[r] = asyncio.Event()
    shut_task = asyncio.create_task(sd.shutdown_run_infrastructure())
    await asyncio.sleep(0)  # shutdown is now parked inside step 1
    eng._cleanup_pipeline("run-b")  # two drivers finish mid-drain
    eng._cleanup_pipeline("run-e")
    queues["run-late"] = eng._get_or_create_queue("run-late")  # one run registers mid-drain
    conc_release.set()
    s = await shut_task
    print("summary: runs_in_flight=%s live_queues=%s queues_sentinelled=%s "
          "runs_left_for_boot_restore=%s concierge_persisted=%s errors=%s"
          % (s["runs_in_flight"], s["live_queues"], s["queues_sentinelled"],
             s["runs_left_for_boot_restore"], s["concierge_persisted"], s["errors"]))
    print("drivers actually still registered after shutdown:", sorted(eng._PIPELINE_TASKS))
    for r, q in queues.items():
        print(f"  queue {r}: contents={drain(q)}")
    for t in drivers.values():
        t.cancel()

    print("\n=== 3. detach sweep: gather(shutdown, _unsubscribe(q1) after N loop turns) ===")
    for n in range(0, 6):
        reset()
        eng._get_or_create_queue("run-1")
        eng._PIPELINE_TASKS["run-1"] = await pending_task()
        q1 = await eng._subscribe("run-1")
        q2 = await eng._subscribe("run-1")

        async def detach(n=n, q1=q1):
            for _ in range(n):
                await asyncio.sleep(0)
            await eng._unsubscribe("run-1", q1)

        s, _ = await asyncio.gather(sd.shutdown_run_infrastructure(), detach())
        print(f"N={n}: pump in_flight={s['pump_tasks_in_flight']} drained={s['pump_tasks_drained']} "
              f"cancelled={s['pump_tasks_cancelled']} queues_sentinelled={s['queues_sentinelled']} "
              f"errors={s['errors']} q1(detached)={drain(q1)} q2(kept)={drain(q2)} "
              f"_PUMP_TASKS_left={sorted(eng._PUMP_TASKS)}")

    print("\n=== 4. what a plain subscriber detach mutates ===")
    reset()
    eng._get_or_create_queue("run-1")
    q = await eng._subscribe("run-1")

    def snap():
        return {
            "_PIPELINE_QUEUES": sorted(eng._PIPELINE_QUEUES),
            "_PUMP_TASKS": sorted(eng._PUMP_TASKS),
            "_SUBSCRIBERS": {k: len(v) for k, v in eng._SUBSCRIBERS.items()},
        }

    print("before detach:", snap())
    await eng._unsubscribe("run-1", q)
    print("after  detach:", snap())

    print("\n=== 5. step-2 guards ===")
    reset()

    class _Full:
        def put_nowait(self, _item):
            raise asyncio.QueueFull

    eng._PIPELINE_QUEUES["run-full"] = _Full()
    good = eng._get_or_create_queue("run-ok")
    s = await sd.shutdown_run_infrastructure()
    print(f"per-item guard : queues_sentinelled={s['queues_sentinelled']} errors={s['errors']} "
          f"run-ok queue={drain(good)} checkpointer_closed={s['checkpointer_closed']}")

    class _BoomKeys(dict):
        def keys(self):
            raise RuntimeError("dictionary changed size during iteration")

    reset()
    saved = eng._PIPELINE_QUEUES
    eng._PIPELINE_QUEUES = _BoomKeys()
    try:
        s = await sd.shutdown_run_infrastructure()
    finally:
        eng._PIPELINE_QUEUES = saved
    print(f"outer guard    : queues_sentinelled={s['queues_sentinelled']} errors={s['errors']} "
          f"checkpointer_closed={s['checkpointer_closed']}")
    reset()

    print("\n=== 6. per-turn churn + recording registry, real function vs an in-memory copy with an await injected into the step-2 loop ===")
    import inspect

    src = inspect.getsource(sd.shutdown_run_infrastructure)
    needle = "                _PIPELINE_QUEUES[run_id].put_nowait(None)\n"
    assert needle in src, "step-2 put_nowait line moved; update the probe"
    ns = dict(sd.__dict__)
    exec(compile(src.replace(needle, "                await asyncio.sleep(0)\n" + needle), "<mutated>", "exec"), ns)
    variants = {"real": sd.shutdown_run_infrastructure, "await-injected": ns["shutdown_run_infrastructure"]}

    class _Rec(dict):
        def keys(self):
            self.seen = set(super().keys())  # what the registry held when step 2 read it
            return super().keys()

    for name, fn in variants.items():
        reset()
        rec = _Rec()
        saved = eng._PIPELINE_QUEUES
        eng._PIPELINE_QUEUES = rec
        try:
            hold = asyncio.Event()

            async def conc():
                await hold.wait()

            ct = asyncio.create_task(conc())
            rc._CONCIERGE_STREAM_TASKS.add(ct)
            ct.add_done_callback(rc._CONCIERGE_STREAM_TASKS.discard)
            for i in range(6):
                eng._get_or_create_queue(f"run-{i}")

            async def churn():
                popped = 0
                for turn in range(60):
                    if turn == 5:
                        hold.set()  # release step 1 after a few churned turns
                    if turn % 2 == 0 and popped < 6:
                        eng._cleanup_pipeline(f"run-{popped}")
                        popped += 1
                    else:
                        eng._get_or_create_queue(f"late-{turn}")
                    await asyncio.sleep(0)

            s, _ = await asyncio.gather(fn(), churn())
            seen = len(getattr(rec, "seen", ()))
            print(f"{name:15s}: queues_sentinelled={s['queues_sentinelled']} registry_at_step2={seen} "
                  f"match={s['queues_sentinelled'] == seen} errors={s['errors']}")
        finally:
            eng._PIPELINE_QUEUES = saved
    reset()


asyncio.run(main())
print("\npsycopg2 imported:", "psycopg2" in sys.modules)
