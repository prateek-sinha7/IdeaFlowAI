"""QA-KB-080 analysis probe. Read-only on application source AND on the test file: every
change is made in memory.

Part 1  Unpatched: the ISS-098 guard dies on the TypeError the bug describes.
Part 2  Widen ONLY the fake's run_fanout signature (event_queue=None) in memory: the guard's body
        now reaches the injected CancelledError and passes -> the product arm
        (wave_scheduler.py:492-503) holds, and the signature change alone is sufficient.
Part 3  Mutant: widen the fake AND drop the `except asyncio.CancelledError` arm from an in-memory copy
        of wave_scheduler.py -> the guard FAILS with its own ISS-098 message, i.e. once unblocked the
        guard discriminates (it is not a vacuous pass).

Run from the repo root:  backend/.venv/bin/python evidence/qa-kb-080/analysis-probe-widened-fake-and-mutant.py
"""
import asyncio
import re
import sys
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

import tests.agents.test_wave_scheduler_cancel_row as m  # noqa: E402


async def _widened(self, requests, ctx, *, step=None, event_queue=None):
    raise asyncio.CancelledError()
    yield  # pragma: no cover


def run(label):
    try:
        asyncio.run(m.test_cancelled_error_mid_wave_marks_row_terminal())
        print(f"{label}: test body PASSED")
    except TypeError as exc:
        print(f"{label}: TypeError -> {exc}")
    except AssertionError as exc:
        print(f"{label}: AssertionError -> {str(exc)[:110]}")


run("1 unpatched fake                       ")
m._CancelMidWaveRunner.run_fanout = _widened
run("2 fake widened (event_queue=None)      ")

# Part 3: mutate an in-memory copy of wave_scheduler.py (the arm at :492-503), re-import the test.
name = "agents.capabilities.strategies.wave_scheduler"
path = BACKEND / "agents/capabilities/strategies/wave_scheduler.py"
src = path.read_text()
mutated, n = re.subn(
    r"            except asyncio\.CancelledError:\n(?:.*\n)*?                raise\n(?=            except Exception:)",
    "", src, count=1)
assert n == 1, "arm not found"
mod = types.ModuleType(name)
mod.__file__, mod.__package__ = str(path), "agents.capabilities.strategies"
sys.modules[name] = mod
exec(compile(mutated, str(path), "exec"), mod.__dict__)
m.WaveSchedulerStrategy = mod.WaveSchedulerStrategy  # the test resolves it from its module globals
run("3 widened fake + CancelledError arm cut")
