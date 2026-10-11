"""tests/agents/test_consumes_delivery_v3.py — row 12's disk substitution needs a READER.

L4 regression (live run `424d9f2a-3e65-40dc-85b4-7824ef95c87e`, `ex_A1_loop`).

``consumes:`` (R-29) is the routing CONTRACT, not a world block: an upstream
step's output is "injected into THIS step's context" (``plan.py:456``). GAPS
FR-030 row 12 RELOCATES that delivery to ``.agents/NN-<agent>.md``, and S0 put
the ``--- Output from ... ---`` paste behind ``if not _is_migrated:`` to make the
move. The relocation is only valid for an agent that can OPEN the file: a step
compiled with ``tools: {read_files: false}`` has no read tool at all, so the
blanket gate DELETED the edge instead of moving it.

Observed live: `ex_A1_loop`'s `check` gate was dispatched with an EMPTY
``context_message`` while its own ``context_sources`` still recorded
``{"type": "summary", "agent_id": "custom-agent:greet", "full_output_length": 103}``
— it judged a greeting it had never been shown, answered ``retry`` on all four
passes and ran the loop to R-07 ``loop_max_iterations`` exhaustion
(``budget_aborted`` → run ``failed``, no tag).

So ``_compose_context_message`` delivers consumed upstream outputs whenever the
disk substitute is unreachable. Everything else stays suppressed — this is a
scoped exception to row 12, not a seam-2 rollback.

Offline-safe: no model, no runner, no sandbox, no DB — the composer is called
directly with a hand-seeded ``ExecutionContext``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


_UPSTREAM_OUTPUT = "Hello! How can I help you today?"


def _spec(agent_id: str, *, produces=(), consumes=(), policy="body_only"):
    """The attribute surface ``_compose_context_message`` /
    ``_filter_consumed_outputs`` read off an agent spec."""
    return SimpleNamespace(
        id=agent_id,
        name=agent_id.split(":")[-1].title(),
        role="Custom Agent",
        prompt_policy=policy,
        injects=[],
        tools=[],
        produces=list(produces),
        consumes=list(consumes),
    )


def _step(*, read_files: bool | None):
    """A compiled Step for the consumer's dispatch — or ``None`` for the
    registry-agent shape (no compiled Step bound at all)."""
    if read_files is None:
        return None
    from agents.workflows.plan import Step, ToolPermissions

    return Step(
        agent_id="custom-agent",
        instance_id="check",
        tools=ToolPermissions(read_files=read_files, write_files=False, exec=False),
    )


async def _compose_for_consumer(*, read_files: bool | None) -> str:
    from agents.artifacts.graph import ArtifactGraph
    from agents.execution_engine.context import ExecutionContext
    from agents.execution_engine.engine import ExecutionEngine

    producer = _spec("custom-agent:greet", produces=["greeting"])
    consumer = _spec(
        "custom-agent:check", consumes=["greeting"], produces=["route_decision"]
    )

    ectx = ExecutionContext(run_id="l4-consumes-run", owner_id="anon")
    ectx.disk_principal = "anon"
    ectx.artifacts = ArtifactGraph()
    ectx.artifacts.write_ref(
        run_id=ectx.run_id,
        owner_id="anon",
        workspace_id="anon",
        kind="summary",
        producer_step=producer.id,
        producer_agent=producer.id,
        task_id=None,
        content=_UPSTREAM_OUTPUT,
        location="memory",
    )
    ectx.current_step = _step(read_files=read_files)

    return await ExecutionEngine()._compose_context_message(
        consumer,
        1,  # index > 0 — not the first agent, so the brief is gated off
        [producer, consumer],
        "loop",
        {},
        ectx,
    )


@pytest.mark.asyncio
async def test_migrated_consumer_without_read_files_still_gets_upstream_output() -> (
    None
):
    msg = await _compose_for_consumer(read_files=False)

    assert "--- Output from" in msg, (
        "a migrated step with tools.read_files=False cannot open "
        ".agents/NN-<agent>.md, so suppressing the paste leaves its declared "
        "consumes: with NO delivery channel — the L4 ex_A1_loop empty-message defect"
    )
    assert (
        _UPSTREAM_OUTPUT in msg
    ), "the upstream CONTENT, not just the envelope, must reach the consumer"


@pytest.mark.asyncio
async def test_migrated_consumer_with_read_files_keeps_row12_suppression() -> None:
    msg = await _compose_for_consumer(read_files=True)

    assert "--- Output from" not in msg, (
        "a migrated agent that CAN read the sandbox must still read "
        ".agents/NN-<agent>.md itself — row 12 holds wherever it is reachable"
    )
    assert _UPSTREAM_OUTPUT not in msg


@pytest.mark.asyncio
async def test_migrated_consumer_with_no_compiled_step_is_unchanged() -> None:
    """INV-3: a registry-agent dispatch carries no compiled Step, and
    ``read_files`` defaults True (plan.py:65) — "unknown" means "can read", so
    every already-migrated pipeline is byte-unchanged."""
    msg = await _compose_for_consumer(read_files=None)

    assert "--- Output from" not in msg
    assert _UPSTREAM_OUTPUT not in msg
