"""QA-KB-080 analysis probe (read-only, in memory): follow the TypeError through wave_scheduler.run.

With the UNPATCHED fake, which arm of the dispatch try/except sees the TypeError, what does it
write to wave_runs, and which events does the strategy yield before the exception escapes into the test?

Run from the repo root:  backend/.venv/bin/python evidence/qa-kb-080/analysis-probe-where-the-typeerror-goes.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import tests.agents.test_wave_scheduler_cancel_row as m  # noqa: E402
from agents.capabilities.strategies.wave_scheduler import WaveSchedulerStrategy  # noqa: E402
from tests.unit.agents.test_wave_scheduler import _t  # noqa: E402


async def main():
    strat = WaveSchedulerStrategy()
    runner = m._CancelMidWaveRunner()
    ctx = m._CancelCtx(runner)
    step = m._CancelStep("wave-step")
    tasks = [_t("ta", targets=["a.txt"])]

    class _FakeParser:
        def parse(self, _text):
            return tasks

    strat._registry = type("R", (), {"resolve": lambda self, k, n: _FakeParser()})()
    events = []
    try:
        async for ev in strat.run(step, ctx):
            events.append(ev["type"])
    except BaseException as exc:  # noqa: BLE001
        print("escaped into the caller:", type(exc).__name__, "-", str(exc)[:90])
    print("events yielded before escaping:", events)
    print("wave_runs flips recorded by the fake:", runner.updated)


asyncio.run(main())
