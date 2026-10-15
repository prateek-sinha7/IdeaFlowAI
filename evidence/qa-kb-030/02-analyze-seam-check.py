"""QA-KB-030 analyzer check (scratch, offline, no repo writes).

Exercises the two REAL engine seams that decide whether a task_loop step gets a
human gate, and shows what changes if TaskLoopStrategy declared runs_agent_inline=False
(simulated by an in-process class-attribute set; no source file is edited).
"""
import asyncio
import logging
import sys
from types import SimpleNamespace

sys.path.insert(0, ".")

from agents.capabilities.registry import CapabilityRegistry
from agents.execution_engine.engine import ExecutionEngine

logging.basicConfig(level=logging.INFO, format="LOG %(name)s: %(message)s")
logging.getLogger("agents.execution_engine.engine").setLevel(logging.INFO)

engine = ExecutionEngine()
real = CapabilityRegistry()

print("== 1. what the kernel reads off each resolved strategy (engine._strategy_runs_agent_inline)")
for name in ("single_shot", "task_loop", "parallel_group", "fanout_batch", "wave_scheduler"):
    impl = real.resolve("strategy", name)
    print(
        f"  {name:15s} declared={getattr(impl, 'runs_agent_inline', '<undeclared>')!s:13s} "
        f"kernel_reads={engine._strategy_runs_agent_inline(name, real)}"
    )

# A step ticked in the per-run gate picker (gate_agent_ids) AND declaring gates:[human].
spec = SimpleNamespace(id="build-agent", name="Build", gate=None)
ectx = SimpleNamespace(gate_agent_ids=["build-agent"], suppress_review_gate=False,
                       resume_approved_gate_keys=None, run_id="r1", step_visit_counts={})
step = SimpleNamespace(agent_id="build-agent", gates=["human"])

print("\n== 2. the inline-gate predicate as _run_agent sees it (invocation scope)")
print("  step-boundary read   _should_gate(spec, ectx)                       =",
      engine._should_gate(spec, ectx))
print("  task_loop invocation _should_gate(spec, ectx, invocation_gated=False) =",
      engine._should_gate(spec, ectx, invocation_gated=False),
      "  <- task_loop.py:360 passes invocation_gated=False => inline gate NEVER fires")


class _FakeHumanGate:
    """Stand-in for the registered human gate: records that the declared gate ran."""
    calls = 0

    async def evaluate(self, step, ectx):
        _FakeHumanGate.calls += 1
        return SimpleNamespace(outcome="pass", detail=None, events=[{"type": "gate_probe"}])


class _Reg:
    def resolve(self, kind, name):
        if kind == "gate" and name == "human":
            return _FakeHumanGate()
        return real.resolve(kind, name)


async def drive(label):
    _FakeHumanGate.calls = 0
    runs_inline = engine._strategy_runs_agent_inline("task_loop", _Reg())
    inline_gated = engine._should_gate(spec, ectx) and runs_inline   # engine.py:6309 / :6721
    seen = []
    async for ev, outcome, detail in engine._evaluate_gates(
        step, ectx, _Reg(), phase="post", inline_gated=inline_gated
    ):
        seen.append(outcome)
    print(f"  [{label}] runs_agent_inline_read={runs_inline} inline_gated={inline_gated} "
          f"-> declared human gate evaluated {_FakeHumanGate.calls}x")


print("\n== 3. declared gates:[human] on a ticked task_loop step, post-step _evaluate_gates")
asyncio.run(drive("CURRENT  (task_loop undeclared => True)"))

# Simulate the proposed one-line fix in-process only.
from agents.capabilities.strategies.task_loop import TaskLoopStrategy
TaskLoopStrategy.runs_agent_inline = False
asyncio.run(drive("PROPOSED (task_loop.runs_agent_inline = False)"))
