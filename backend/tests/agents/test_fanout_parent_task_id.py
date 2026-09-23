"""tests/agents/test_fanout_parent_task_id.py — nested fan-out parentage.

A wave member already knows its own name: ``wave_scheduler`` puts ``task_id`` on
each member's request and ``fanout.py`` stamps it onto that member's events. Its
CHILDREN knew nothing, so a task agent spawned by a member could not be nested
under it in the UI.

These tests pin the one-field pass-down that closes that gap, and — the invariant
that actually matters — that a fan-out OUTSIDE a wave emits a byte-identical
payload to before, since ``_derive_fanout`` serves every runtime fan-out.
"""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest

from agents.execution_engine.engine import ExecutionEngine


class _Runner:
    """A run_fanout stand-in yielding the two lifecycle events verbatim."""

    def __init__(self):
        self.seen_requests = None

    async def run_fanout(self, requests, ctx, *, step=None):
        self.seen_requests = requests
        yield {"type": "subagent_spawned",
               "data": {"worker": 0, "agent": "custom-agent:fi-readers", "depth": 1}}
        yield {"type": "subagent_result",
               "data": {"worker": 0, "status": "complete"}}


def _ectx(runner, *, task_id):
    step = SimpleNamespace(
        agent_id="custom-agent:fi-readers",
        tools=SimpleNamespace(spawn_subagents=True),
        fanout=None,
    )
    ectx = SimpleNamespace(runner=runner, current_step=step)
    if task_id is not None:
        ectx.task_id = task_id
    return ectx


def _event(*tasks):
    return {"tool": "spawn_subagents",
            "result": json.dumps({"fanout_request": list(tasks), "mode": "parallel"})}


async def _drain(ectx, event):
    return [e async for e in ExecutionEngine._derive_fanout(
        ExecutionEngine.__new__(ExecutionEngine), event, ectx)]


@pytest.mark.asyncio
async def test_child_events_name_the_wave_member_that_spawned_them():
    runner = _Runner()
    out = await _drain(_ectx(runner, task_id="s01"), _event("read page 1", "read page 2"))

    assert [e["type"] for e in out] == ["subagent_spawned", "subagent_result"]
    assert all(e["data"]["parent_task_id"] == "s01" for e in out)
    # The stamp never mutates run_fanout's own dict.
    assert out[0]["data"]["worker"] == 0


@pytest.mark.asyncio
async def test_a_fanout_outside_a_wave_is_byte_identical():
    """THE invariant: no wave, no task_id, no stamp — payloads unchanged."""
    runner = _Runner()
    out = await _drain(_ectx(runner, task_id=None), _event("do a thing"))

    assert out == [
        {"type": "subagent_spawned",
         "data": {"worker": 0, "agent": "custom-agent:fi-readers", "depth": 1}},
        {"type": "subagent_result", "data": {"worker": 0, "status": "complete"}},
    ]
    assert not any("parent_task_id" in e["data"] for e in out)


@pytest.mark.asyncio
async def test_an_empty_request_stamps_nothing():
    runner = _Runner()
    assert await _drain(_ectx(runner, task_id="s01"), _event()) == []


def test_run_worker_accepts_the_task_id_it_is_now_handed():
    from agents.execution_engine.kernel_services import KernelServices

    params = inspect.signature(KernelServices.run_worker).parameters
    assert "task_id" in params
    assert params["task_id"].default is None


def test_fanout_forwards_the_task_id_it_already_has():
    """fanout.py held the worker's task_id but never passed it down."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "agents/execution_engine/fanout.py"
    body = src.read_text()
    call = body.split("runner.run_worker(")[1].split("):")[0]
    assert 'task_id=worker.get("task_id")' in call
