"""tests/agents/test_constitution_prod.py — AGENTRT-06 (F4 / R12).

The constitution-injected-in-prod gate. Before this fix, ``_inject_constitution``
(``agents/factory.py``) had an event-loop-running branch that read ONLY the
in-process ``WorkflowMemory._mem`` dict, so a Postgres/DB-stored Constitution was
silently NOT injected in production (under FastAPI's running event loop). The R12
no-op.

The fix (RESEARCH A3 / D-08 — the lower-risk option): the async engine pre-warms the
owner's Constitution ONCE at run entry (``await get_constitution(...)`` before the
SYNC ``create_runner`` calls) and stashes the value on ``AgentContext`` so the sync
factory reads it WITHOUT awaiting inside the running loop. A DB-stored Constitution
then appears in the composed prompt under a running event loop.

These tests run the composition path under a running event loop (``async def`` test
bodies + ``pytest.mark.asyncio``) so they reproduce the production condition the old
``_mem``-only branch silently failed.

Parity note (RESEARCH A4 — verified): the 5 characterization runs set NO Constitution,
so this fix is INVISIBLE to those snapshots (they stay byte-identical). This file is a
NEW, additive test — never a snapshot re-baseline.
"""

from __future__ import annotations

import asyncio

import pytest

from agents.factory import AgentContext, _compose_system_prompt
from agents.loader import load_agent_spec
from agents.workflow_memory.memory import WorkflowMemory


_GOVERNED_AGENT = "domain-analyst"
_CONSTITUTION_BODY = (
    "PRINCIPLE 1: Always cite the source domain.\n"
    "PRINCIPLE 2: Never invent regulatory clauses."
)
_CONSTITUTION_MARKER = "## Constitution (Governing Principles"


async def _prewarm(memory: WorkflowMemory, user_id: str) -> str | None:
    """Mirror the engine's run-entry pre-warm: await get_constitution ONCE."""
    return await memory.get_constitution(user_id)


@pytest.mark.asyncio
async def test_db_constitution_injected_under_running_loop() -> None:
    """A stored Constitution appears in the composed prompt under a running loop.

    Reproduces production: an event loop is already running (this async test body),
    so the old ``_mem``-only running-loop branch would have dropped a DB-stored
    Constitution. With the pre-warm-at-run-entry fix the value is read sync-safely
    from the context and the block is injected.
    """
    # Confirm we ARE under a running loop (the production condition).
    assert asyncio.get_event_loop().is_running()

    user_id = "owner-prod-1"
    memory = WorkflowMemory(use_db=False)  # the offline store the unit harness uses
    await memory.set_constitution(user_id, _CONSTITUTION_BODY)

    # Engine run-entry pre-warm (awaited ONCE, before the sync create_runner path).
    prewarmed = await _prewarm(memory, user_id)
    assert prewarmed == _CONSTITUTION_BODY, "pre-warm must read the stored Constitution"

    ctx = AgentContext(
        user_request="Analyze the lending domain.",
        user_id=user_id,
        prewarmed_constitution=prewarmed,
    )
    spec = load_agent_spec(_GOVERNED_AGENT)
    system_prompt = _compose_system_prompt(spec, ctx)

    assert _CONSTITUTION_MARKER in system_prompt, (
        "A DB-stored Constitution must be injected into the composed prompt under a "
        "running event loop (AGENTRT-06 / R12 fix)."
    )
    assert _CONSTITUTION_BODY in system_prompt, (
        "The full Constitution body must appear verbatim in the composed prompt."
    )


@pytest.mark.asyncio
async def test_no_constitution_is_graceful_noop_under_running_loop() -> None:
    """With NO Constitution set, the composed prompt is unchanged (graceful no-op).

    This is the characterization condition (the 5 snapshots set no Constitution), so
    the pre-warm must be INVISIBLE: the prompt must carry no Constitution block.
    """
    assert asyncio.get_event_loop().is_running()

    ctx = AgentContext(
        user_request="Analyze the lending domain.",
        user_id="owner-no-constitution",
        prewarmed_constitution=None,  # nothing pre-warmed → graceful no-op
    )
    spec = load_agent_spec(_GOVERNED_AGENT)
    system_prompt = _compose_system_prompt(spec, ctx)

    assert _CONSTITUTION_MARKER not in system_prompt, (
        "With no Constitution set the composed prompt must carry no Constitution block "
        "(parity with the characterization snapshots)."
    )


@pytest.mark.asyncio
async def test_prewarm_runs_without_event_loop_error() -> None:
    """The pre-warmed read must not raise RuntimeError under a running loop.

    The old branch tried ``loop.run_until_complete`` (or read ``_mem``) inside a
    running loop; the pre-warm fix reads a plain cached value so no
    ``RuntimeError: event loop already running`` can occur during composition.
    """
    assert asyncio.get_event_loop().is_running()

    user_id = "owner-prod-2"
    memory = WorkflowMemory(use_db=False)
    await memory.set_constitution(user_id, _CONSTITUTION_BODY)
    prewarmed = await _prewarm(memory, user_id)

    ctx = AgentContext(
        user_request="Analyze the lending domain.",
        user_id=user_id,
        prewarmed_constitution=prewarmed,
    )
    spec = load_agent_spec(_GOVERNED_AGENT)

    # Composition must complete with no event-loop RuntimeError.
    system_prompt = _compose_system_prompt(spec, ctx)
    assert _CONSTITUTION_MARKER in system_prompt
