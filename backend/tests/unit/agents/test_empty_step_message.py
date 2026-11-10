"""A later step with no control block gets the STEP START block, not an empty message.

Offline: drives ``ExecutionEngine._compose_context_message`` directly with a scripted
``ExecutionContext`` (no live model, no DB). Setup mirrors ``test_steering_seam.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.execution_engine.context import ExecutionContext
from agents.execution_engine.engine import _STEP_START_BLOCK, ExecutionEngine

_REQUEST_OPEN = "=== ORIGINAL USER REQUEST ==="


def _spec(agent_id: str):
    return SimpleNamespace(
        id=agent_id, name=agent_id, role="tester", injects=[], tools=[], consumes=[]
    )


async def _compose(index: int, specs: list, ectx: ExecutionContext) -> str:
    engine = ExecutionEngine()
    return await engine._compose_context_message(
        spec=specs[index],
        index=index,
        ordered_agents=specs,
        user_message="build me a thing",
        planning_context={},
        ectx=ectx,
    )


@pytest.mark.asyncio
async def test_first_step_keeps_original_request_and_no_start_block() -> None:
    specs = [_spec("agent-a"), _spec("agent-b")]
    ectx = ExecutionContext(run_id="r-empty-0", owner_id="o-empty-0")

    message = await _compose(0, specs, ectx)

    assert _REQUEST_OPEN in message
    assert "STEP START" not in message


@pytest.mark.asyncio
async def test_later_step_without_control_block_gets_start_block() -> None:
    specs = [_spec("agent-a"), _spec("agent-b")]
    ectx = ExecutionContext(run_id="r-empty-1", owner_id="o-empty-1")

    message = await _compose(1, specs, ectx)

    assert message == _STEP_START_BLOCK
