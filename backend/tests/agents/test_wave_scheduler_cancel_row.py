"""tests/agents/test_wave_scheduler_cancel_row.py — ISS-098.

``wave_scheduler.py`` catches ``except Exception:`` around the ``run_fanout`` call to
flip the in-flight wave's ``wave_runs`` row terminal (``failed``) on error. But
``asyncio.CancelledError`` has inherited from ``BaseException`` (not ``Exception``)
since Python 3.8, so a Stop-during-a-wave is NOT caught there and the row is left
reading ``running`` forever (self-corrected later by the WR-01 stale-row sweep on
resume, but wrong in the moment).

Offline / pure (no DB / network / API key) — a fake ``ctx.runner`` whose
``run_fanout`` raises ``asyncio.CancelledError`` mid-wave.
"""

from __future__ import annotations

import asyncio

import pytest

from agents.capabilities.strategies.wave_scheduler import WaveSchedulerStrategy
from tests.agents.test_wave_scheduler import _t


class _CancelMidWaveRunner:
    def __init__(self):
        self.updated: list[tuple[str, str]] = []

    def latest_typed_content(self, _step):
        return ""

    async def read_wave_runs(self):
        return []

    async def record_wave_run(self, *, step, wave_index, task_ids, status):
        return f"row-{wave_index}"

    async def update_wave_run(self, row_id, *, status):
        self.updated.append((row_id, status))

    async def run_fanout(self, requests, ctx, *, step=None):
        raise asyncio.CancelledError()
        yield  # pragma: no cover — makes this an async generator


class _CancelCtx:
    def __init__(self, runner):
        self.runner = runner
        self.is_resuming = False


class _CancelStep:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.task_source = type("TS", (), {"source_step": "plan", "parser": "json_tasks"})()


@pytest.mark.issue("ISS-098")
@pytest.mark.asyncio
async def test_cancelled_error_mid_wave_marks_row_terminal():
    """A CancelledError raised mid-wave must still flip the wave_runs row to a
    terminal status — not leave it stuck at ``running``."""
    strat = WaveSchedulerStrategy()
    runner = _CancelMidWaveRunner()
    ctx = _CancelCtx(runner)
    step = _CancelStep("wave-step")

    tasks = [_t("ta", targets=["a.txt"])]

    class _FakeParser:
        def parse(self, _text):
            return tasks

    strat._registry = type("R", (), {"resolve": lambda self, k, n: _FakeParser()})()

    with pytest.raises(asyncio.CancelledError):
        async for _ in strat.run(step, ctx):
            pass

    assert runner.updated, (
        "wave_runs row was never flipped off 'running' after a mid-wave CancelledError"
    )
    assert runner.updated[-1][1] in ("failed", "cancelled"), (
        f"wave_runs row left at non-terminal status: {runner.updated}"
    )
