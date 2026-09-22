"""parallel_group fan-out — the END-TO-END (DB-touching) half.

Split out of ``tests/unit/agents/test_parallel_group_strategy.py``. That file's
compile-shape and strategy-dispatch tests are zero-I/O and STAY in the unit suite;
this end-to-end proof drives the real ``ExecutionEngine.execute()`` (via ``_drive``),
which opens a ``SessionLocal()`` to persist run events — the unit-isolation guard in
``tests/unit/conftest.py`` rejects that by design.

Carries the module-scoped ``discover()`` / ``CapabilityRegistry`` fixture the original
file applied as ``autouse``, since the ``sample_subagents_parallel`` workflow's custom
agents must be registered before the run compiles.

Offline (scripted model, no Bedrock) — but NOT zero-I/O.
"""

from __future__ import annotations

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover


@pytest.fixture(scope="module", autouse=True)
def _registry():
    discover()
    return CapabilityRegistry()


@pytest.mark.asyncio
async def test_every_child_runs_exactly_once_end_to_end():
    """The children must be spawned, and spawned ONCE.

    Two failure modes this catches, and they pull in opposite directions:
      * forget the `dispatched_by` skip → each child runs TWICE (once in the
        serial loop, once as a worker), doubling cost and racing on its artifact;
      * skip them without wiring the fan-out → they never run at all and the
        parent finds no files.
    """
    from tests.agents._scripted_model import _drive

    events = await _drive("sample_subagents_parallel")
    assert events

    started = [e["data"].get("agent_id") for e in events if e["type"] == "agent_start"]
    # Each child now emits its own live agent_start (per-child streaming via the
    # fan-out side-channel queue), same as the parent — but EXACTLY ONCE each.
    # A `dispatched_by` regression would double a child's agent_start (once in
    # the serial loop, once as a worker); a missing fan-out wire would drop it
    # entirely. Order isn't asserted (workers race), only exactly-once-each.
    assert sorted(started) == sorted(
        [
            "custom-agent:page",
            "custom-agent:apple",
            "custom-agent:ball",
            "custom-agent:cat",
        ]
    ), started

    spawned = [e for e in events if e["type"] == "subagent_spawned"]
    assert len(spawned) == 3, f"expected 3 spawned children, got {len(spawned)}"
