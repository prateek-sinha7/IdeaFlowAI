"""QA-KB-030 analyzer check #2 (scratch): the PRE-step before-human gate shares the predicate (engine.py:6309)."""
import asyncio, sys
from types import SimpleNamespace
sys.path.insert(0, ".")
from agents.capabilities.registry import CapabilityRegistry
from agents.execution_engine.engine import ExecutionEngine

engine = ExecutionEngine()
real = CapabilityRegistry()
spec = SimpleNamespace(id="build-agent", name="Build", gate=None)
ectx = SimpleNamespace(gate_agent_ids=["build-agent"], suppress_review_gate=False,
                       resume_approved_gate_keys=None, run_id="r1", step_visit_counts={})


class _Fake:
    calls = 0
    async def evaluate(self, step, ectx):
        _Fake.calls += 1
        return SimpleNamespace(outcome="pass", detail=None, events=[])


class _Reg:
    def resolve(self, kind, name):
        if kind == "gate" and name in ("human", "before-human"):
            return _Fake()
        return real.resolve(kind, name)


async def drive(label, gate_name, phase):
    _Fake.calls = 0
    step = SimpleNamespace(agent_id="build-agent", gates=[gate_name])
    inline = engine._should_gate(spec, ectx) and engine._strategy_runs_agent_inline("task_loop", _Reg())
    async for _ in engine._evaluate_gates(step, ectx, _Reg(), phase=phase, inline_gated=inline):
        pass
    print(f"  [{label}] gate={gate_name:12s} phase={phase:4s} inline_gated={inline} -> evaluated {_Fake.calls}x")

asyncio.run(drive("CURRENT ", "before-human", "pre"))
asyncio.run(drive("CURRENT ", "human", "post"))
from agents.capabilities.strategies.task_loop import TaskLoopStrategy
TaskLoopStrategy.runs_agent_inline = False
asyncio.run(drive("PROPOSED", "before-human", "pre"))
asyncio.run(drive("PROPOSED", "human", "post"))
