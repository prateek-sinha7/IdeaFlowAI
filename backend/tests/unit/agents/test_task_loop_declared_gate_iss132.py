"""ISS-132 / QA-KB-030: task_loop opts out of the inline review gate per call
(invocation_gated=False) but never declares runs_agent_inline=False, so the
step-boundary dedupe skips the declared human / before-human gate: zero gates."""

from types import SimpleNamespace

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.execution_engine.engine import ExecutionEngine

_REAL = CapabilityRegistry()


class _CountingGate:
    calls = 0

    async def evaluate(self, step, ectx):
        _CountingGate.calls += 1
        return SimpleNamespace(outcome="pass", detail=None, events=[])


class _Reg:
    def resolve(self, kind, name):
        if kind == "gate" and name in ("human", "before-human"):
            return _CountingGate()
        return _REAL.resolve(kind, name)


@pytest.mark.issue("ISS-132")
def test_task_loop_declares_not_inline():
    """ISS-132: kernel must read runs_agent_inline=False for task_loop."""
    assert ExecutionEngine()._strategy_runs_agent_inline("task_loop", _REAL) is False


async def _declared_gate_runs(gate_name: str, phase: str) -> int:
    engine = ExecutionEngine()
    spec = SimpleNamespace(id="build-agent", name="Build", gate=None)
    ectx = SimpleNamespace(
        gate_agent_ids=["build-agent"],
        suppress_review_gate=False,
        resume_approved_gate_keys=None,
        run_id="r1",
        step_visit_counts={},
    )
    step = SimpleNamespace(agent_id="build-agent", gates=[gate_name])
    # same predicate engine.py uses at the step boundary (:6309 pre, :6721 post)
    inline = engine._should_gate(spec, ectx) and engine._strategy_runs_agent_inline(
        "task_loop", _Reg()
    )
    _CountingGate.calls = 0
    async for _ in engine._evaluate_gates(
        step, ectx, _Reg(), phase=phase, inline_gated=inline
    ):
        pass
    return _CountingGate.calls


@pytest.mark.issue("ISS-132")
@pytest.mark.asyncio
async def test_ticked_task_loop_post_human_gate_fires_once():
    """ISS-132: ticked task_loop step with declared post-step human gate gets one review."""
    assert await _declared_gate_runs("human", "post") == 1


@pytest.mark.issue("ISS-132")
@pytest.mark.asyncio
async def test_ticked_task_loop_pre_before_human_gate_fires_once():
    """ISS-132: ticked task_loop step with declared pre-step before-human gate gets one review."""
    assert await _declared_gate_runs("before-human", "pre") == 1
