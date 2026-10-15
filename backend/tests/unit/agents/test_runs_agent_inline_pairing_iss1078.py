"""ISS-1078: the spawn-only strategies must declare runs_agent_inline=False.

Deleting the declaration makes the step-boundary dedupe skip the declared human
gate (zero gates). Read through the kernel's own reader, never a name list (INV-1).
Green from birth: the wave_scheduler case is the new guard; verify by mutation
(delete wave_scheduler.py runs_agent_inline) -- it must fail.
"""

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.execution_engine.engine import ExecutionEngine


@pytest.mark.issue("ISS-1078")
@pytest.mark.parametrize("strategy", ["task_loop", "fanout_batch", "wave_scheduler"])
def test_spawn_only_strategy_declares_not_inline(strategy):
    assert (
        ExecutionEngine()._strategy_runs_agent_inline(strategy, CapabilityRegistry())
        is False
    )
