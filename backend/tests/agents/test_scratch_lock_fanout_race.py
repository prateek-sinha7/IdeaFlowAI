"""tests/agents/test_scratch_lock_fanout_race.py — KRN-005 (task.md R-03).

Proves ``KernelServices.run_agent`` no longer lets two concurrently-gathered
fan-out children race on the ONE shared ``ExecutionContext``'s scratch fields
(``current_task_block`` / ``build_task_number`` / ``current_step``). Before the
fix, ``run_agent``'s save -> mutate -> await(child body) -> restore window ran
UNLOCKED, so two children interleaving under ``asyncio.gather`` could observe —
or restore over — each other's scratch mid-flight.

Offline / pure asyncio (no DB, no network, no model). Drives the REAL
``KernelServices.run_agent`` against a real ``ExecutionContext``, with the
engine's heavy ``_run_agent`` monkeypatched to a scripted async generator that
(a) yields control back to the event loop (so a race window actually opens) and
(b) records what ``ectx.current_task_block`` reads as DURING its own body — the
exact field a genuine race would corrupt.
"""

from __future__ import annotations

import asyncio

import pytest

from agents.execution_engine.context import ExecutionContext
from agents.execution_engine.engine import ExecutionEngine
from agents.execution_engine.kernel_services import KernelServices


def _make_services(ectx: ExecutionContext) -> KernelServices:
    engine = ExecutionEngine.__new__(ExecutionEngine)
    return KernelServices(
        engine=engine,
        ectx=ectx,
        sandbox=None,
        ordered_agents=[],
        user_message="",
        pipeline_run_id=ectx.run_id,
        pipeline_type="custom",
        planning_context={},
        attached_skills=None,
        attached_hooks=None,
        model_id=None,
        cancel_event=None,
        results=[],
    )


@pytest.mark.asyncio
async def test_concurrent_run_agent_calls_never_observe_each_others_task_block(monkeypatch):
    ectx = ExecutionContext(run_id="race-run", owner_id="race-owner")
    services = _make_services(ectx)

    observed: dict[str, list[str]] = {}

    async def _scripted_run_agent(
        spec, index, ordered_agents, user_message, sandbox, pipeline_run_id,
        pipeline_type, planning_context, attached_skills, attached_hooks,
        model_id, results, cancel_event, ectx_arg, *, invocation_gated=True,
    ):
        # Yield control mid-invocation (twice) so a genuine race window is open —
        # a concurrently-running sibling's save/mutate would land here if the
        # scratch bind window were not serialized.
        for _ in range(3):
            observed.setdefault(spec.id, []).append(ectx_arg.current_task_block)
            await asyncio.sleep(0)
        yield {"type": "agent_complete", "data": {"agent_id": spec.id}}

    monkeypatch.setattr(services._engine, "_run_agent", _scripted_run_agent, raising=False)

    class _Spec:
        def __init__(self, id_: str) -> None:
            self.id = id_
            self.agent_id = id_

    services._ordered_agents = [_Spec("worker-A"), _Spec("worker-B")]

    async def _drive(worker_label: str) -> None:
        step = _Spec(worker_label)
        async for _ in services.run_agent(
            step, ectx, task_number=1, total_tasks=2, task_block=f"task-for-{worker_label}",
        ):
            pass

    # Two "fan-out children" concurrently sharing the SAME KernelServices/ectx —
    # exactly what run_fanout does under asyncio.gather.
    await asyncio.gather(_drive("worker-A"), _drive("worker-B"))

    # Each worker must have observed ONLY its OWN task block throughout its ENTIRE
    # invocation — never the other's. Before the fix this could fail (interleaved
    # save/mutate/restore corrupting the shared field mid-flight).
    assert observed["worker-A"] == ["task-for-worker-A"] * 3
    assert observed["worker-B"] == ["task-for-worker-B"] * 3

    # The scratch is restored to empty after both invocations complete (no leak).
    assert ectx.current_task_block == ""
    assert ectx.build_task_number == ""


@pytest.mark.asyncio
async def test_scratch_lock_serializes_concurrent_bind_windows():
    """Directly proves mutual exclusion: two ``run_agent`` calls sharing one
    ``ectx`` cannot have overlapping [bind..restore] windows."""
    ectx = ExecutionContext(run_id="race-run-2", owner_id="race-owner")
    services = _make_services(ectx)

    in_flight: list[str] = []
    max_concurrent = 0

    async def _scripted_run_agent(
        spec, index, ordered_agents, user_message, sandbox, pipeline_run_id,
        pipeline_type, planning_context, attached_skills, attached_hooks,
        model_id, results, cancel_event, ectx_arg, *, invocation_gated=True,
    ):
        nonlocal max_concurrent
        in_flight.append(spec.id)
        max_concurrent = max(max_concurrent, len(in_flight))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        in_flight.remove(spec.id)
        yield {"type": "agent_complete", "data": {"agent_id": spec.id}}

    services._engine._run_agent = _scripted_run_agent  # type: ignore[method-assign]

    class _Spec:
        def __init__(self, id_: str) -> None:
            self.id = id_
            self.agent_id = id_

    services._ordered_agents = [_Spec("w0"), _Spec("w1"), _Spec("w2")]

    async def _drive(worker_label: str) -> None:
        step = _Spec(worker_label)
        async for _ in services.run_agent(step, ectx, task_number=1, total_tasks=3, task_block="x"):
            pass

    await asyncio.gather(_drive("w0"), _drive("w1"), _drive("w2"))

    assert max_concurrent == 1, (
        "the scratch-bound invocation window must be serialized across concurrent "
        f"fan-out children (observed max concurrent in-flight = {max_concurrent})"
    )
