"""tests/agents/test_run_worker_tools.py — a dispatched worker's OWN tool_sets reach it.

Regression for the bug where ``KernelServices.run_worker`` synthesized a heterogeneous
worker's step by starting from its own declared step (correct prompt/skills/instance_id)
but then unconditionally overwrote ``tools`` with the DISPATCHING PARENT step's grant —
so a reader step declaring ``tool_sets=["file_extract"]`` under a parent with
``tool_sets=[]`` (e.g. ``custom-agent:synthesizer``, a ``parallel_group`` dispatcher)
silently ran with NO tools. ``extract_text`` was consequently never callable by any
reader in ``pdf_to_prototype``, even though ``compile_for_run`` showed the grant present.

Verifies the fix at the shared construction point every subagent dispatch (fanout_batch,
wave_scheduler, parallel_group) routes through — ``run_worker`` — rather than in any one
strategy: a NAMED worker with its own declared step keeps ITS OWN ``tools``; a worker with
no declared step (self×N) still falls back to the parent's grant (unchanged behavior).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agents.execution_engine.kernel_services import KernelServices
from agents.workflows.plan import ToolPermissions


def _make_kernel(compiled_steps: list) -> KernelServices:
    """A bare KernelServices with only what ``run_worker`` touches populated."""
    kernel = object.__new__(KernelServices)
    kernel._steps_by_agent = {
        s.agent_id: s for s in compiled_steps if getattr(s, "agent_id", None)
    }
    kernel._ectx = SimpleNamespace()
    return kernel


async def _drain(agen):
    async for _ in agen:
        pass


@pytest.mark.asyncio
async def test_named_worker_keeps_its_own_declared_tool_sets():
    """A dispatched_by reader step's own tool_sets reach the constructed worker step."""
    reader = SimpleNamespace(
        agent_id="reader-2",
        tools=ToolPermissions(tool_sets=["file_extract"]),
        dispatched_by="custom-agent:synthesizer",
    )
    parent = SimpleNamespace(
        agent_id="custom-agent:synthesizer",
        tools=ToolPermissions(tool_sets=[]),
    )
    kernel = _make_kernel([reader, parent])

    captured: dict = {}

    async def _fake_run_agent(step, ctx, **kwargs):
        captured["worker_step"] = step
        return
        yield  # pragma: no cover — makes this an async generator

    kernel.run_agent = _fake_run_agent

    await _drain(
        kernel.run_worker(
            parent,
            ctx=None,
            worker_index=0,
            thread_id="t",
            agent_id="reader-2",
            input="",
        )
    )

    worker_step = captured["worker_step"]
    assert worker_step.tools.tool_sets == ["file_extract"]


@pytest.mark.asyncio
async def test_named_worker_with_no_declared_tool_sets_gets_none():
    """A declared child with tool_sets=[] must NOT inherit its parent's grants."""
    reader = SimpleNamespace(
        agent_id="reader-plain",
        tools=ToolPermissions(tool_sets=[]),
        dispatched_by="custom-agent:synthesizer",
    )
    parent = SimpleNamespace(
        agent_id="custom-agent:synthesizer",
        # The parent itself carries a (hypothetical) grant that must NOT leak
        # onto a child that declared none.
        tools=ToolPermissions(tool_sets=["playwright"]),
    )
    kernel = _make_kernel([reader, parent])

    captured: dict = {}

    async def _fake_run_agent(step, ctx, **kwargs):
        captured["worker_step"] = step
        return
        yield  # pragma: no cover

    kernel.run_agent = _fake_run_agent

    await _drain(
        kernel.run_worker(
            parent,
            ctx=None,
            worker_index=0,
            thread_id="t",
            agent_id="reader-plain",
            input="",
        )
    )

    worker_step = captured["worker_step"]
    assert worker_step.tools.tool_sets == []


@pytest.mark.asyncio
async def test_self_times_n_worker_falls_back_to_parents_tools():
    """A worker with no declared step of its own (self×N) still gets the parent's grant."""
    parent = SimpleNamespace(
        agent_id="fanout-parent",
        tools=ToolPermissions(tool_sets=["playwright"]),
    )
    kernel = _make_kernel([parent])

    captured: dict = {}

    async def _fake_run_agent(step, ctx, **kwargs):
        captured["worker_step"] = step
        return
        yield  # pragma: no cover

    kernel.run_agent = _fake_run_agent

    # A different worker_index but no distinct declared step (agent_id == parent's
    # own, workspace bound) — exercises the synthesis branch, not the identity-reuse one.
    await _drain(
        kernel.run_worker(
            parent,
            ctx=None,
            worker_index=1,
            thread_id="t",
            agent_id="fanout-parent",
            input="",
            workspace=object(),
        )
    )

    worker_step = captured["worker_step"]
    assert worker_step.tools.tool_sets == ["playwright"]
