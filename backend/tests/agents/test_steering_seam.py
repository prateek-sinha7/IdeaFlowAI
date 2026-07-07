"""Offline fault-injection proof for the mid-run steering seam (D-06 / CHAT-03 / ND-11).

POR §4 Wave-2 exit: "a steering note demonstrably lands in the next agent's composed
context (offline fault-injection)". These tests drive the GENERIC context injector
``ExecutionEngine._compose_context_message`` DIRECTLY with a scripted ``ExecutionContext``
(no live model, no DB, no Bedrock) and assert:

  (1) a pending steering note lands in the ``=== USER GUIDANCE ===`` block of the NEXT
      dispatch, then is CLEARED after one composition (consume-once, the redo_directive idiom);
  (2) a STICKY (uploaded-context) note persists across TWO dispatches while a ONE-SHOT
      directive is consumed after the first (D-06 sticky-vs-one-shot);
  (3) with NO pending notes the composed context carries NO ``=== USER GUIDANCE ===`` marker
      (golden-neutral — the INV-3 dormancy the 5 characterization goldens rely on).

The seam keys on the generic ``ectx.steering_notes`` queue only — no workflow/agent-name
branch (SC-001/INV-1).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.execution_engine.context import ExecutionContext
from agents.execution_engine.engine import ExecutionEngine

_GUIDANCE_OPEN = "=== USER GUIDANCE ==="
_GUIDANCE_END = "=== END USER GUIDANCE ==="


def _spec(agent_id: str = "agent-a"):
    """A minimal agnostic spec: no injects/tools/consumes → the injector composes just
    the base brief (+ any steering block), so the assertions isolate the steering seam."""
    return SimpleNamespace(
        id=agent_id, name="Agent A", role="tester", injects=[], tools=[], consumes=[]
    )


async def _compose(engine: ExecutionEngine, ectx: ExecutionContext, spec=None) -> str:
    spec = spec or _spec()
    return await engine._compose_context_message(
        spec=spec,
        index=0,
        ordered_agents=[spec],
        user_message="build me a thing",
        planning_context={},
        ectx=ectx,
    )


# ---------------------------------------------------------------------------
# (1) a pending note lands in the next dispatch + is consumed once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_note_lands_in_next_dispatch_and_is_consumed_once() -> None:
    engine = ExecutionEngine()
    ectx = ExecutionContext(run_id="r-steer-1", owner_id="o-steer-1")
    ectx.steering_notes = [{"text": "Use a dark theme", "sticky": False}]

    # First dispatch: the note lands inside a delimited === USER GUIDANCE === block.
    first = await _compose(engine, ectx)
    assert _GUIDANCE_OPEN in first
    assert _GUIDANCE_END in first
    assert "Use a dark theme" in first
    # It must be a properly closed block (opener before closer).
    assert first.index(_GUIDANCE_OPEN) < first.index(_GUIDANCE_END)

    # Consume-once: the one-shot note is cleared from the queue after one composition.
    assert ectx.steering_notes == []

    # Second dispatch (nothing re-enqueued): no guidance block leaks onto the next agent.
    second = await _compose(engine, ectx)
    assert _GUIDANCE_OPEN not in second


@pytest.mark.asyncio
async def test_multiple_pending_notes_all_render_in_one_block() -> None:
    engine = ExecutionEngine()
    ectx = ExecutionContext(run_id="r-steer-multi", owner_id="o-steer-multi")
    ectx.steering_notes = [
        {"text": "First guidance", "sticky": False},
        {"text": "Second guidance", "sticky": False},
    ]
    out = await _compose(engine, ectx)
    assert out.count(_GUIDANCE_OPEN) == 1  # ONE block, both notes joined inside it
    assert "First guidance" in out
    assert "Second guidance" in out
    assert ectx.steering_notes == []


# ---------------------------------------------------------------------------
# (2) sticky persists across two dispatches; one-shot does not
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sticky_persists_across_dispatches_one_shot_does_not() -> None:
    engine = ExecutionEngine()
    ectx = ExecutionContext(run_id="r-steer-2", owner_id="o-steer-2")
    ectx.steering_notes = [
        {"text": "STICKY uploaded context", "sticky": True},
        {"text": "ONE-SHOT directive", "sticky": False},
    ]

    # Dispatch 1: BOTH render.
    first = await _compose(engine, ectx)
    assert "STICKY uploaded context" in first
    assert "ONE-SHOT directive" in first

    # After consume-once: only the sticky note survives on the queue.
    assert ectx.steering_notes == [{"text": "STICKY uploaded context", "sticky": True}]

    # Dispatch 2: the sticky note re-renders; the one-shot directive is gone.
    second = await _compose(engine, ectx)
    assert _GUIDANCE_OPEN in second
    assert "STICKY uploaded context" in second
    assert "ONE-SHOT directive" not in second

    # The sticky note STILL persists for a third dispatch.
    assert ectx.steering_notes == [{"text": "STICKY uploaded context", "sticky": True}]
    third = await _compose(engine, ectx)
    assert "STICKY uploaded context" in third


# ---------------------------------------------------------------------------
# (3) golden-neutral: no notes → no marker (INV-3 dormancy)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_notes_emits_no_marker_golden_neutral() -> None:
    engine = ExecutionEngine()
    ectx = ExecutionContext(run_id="r-steer-3", owner_id="o-steer-3")
    # Default carrier is empty (the golden-run state).
    assert ectx.steering_notes == []

    out = await _compose(engine, ectx)
    assert _GUIDANCE_OPEN not in out
    assert _GUIDANCE_END not in out
    # The queue is untouched (no mutation on the dormant path).
    assert ectx.steering_notes == []


@pytest.mark.asyncio
async def test_notes_without_text_consume_but_emit_no_block() -> None:
    # Defensive: a malformed/empty-text entry is consumed (one-shot) but never emits a block.
    engine = ExecutionEngine()
    ectx = ExecutionContext(run_id="r-steer-4", owner_id="o-steer-4")
    ectx.steering_notes = [{"text": "", "sticky": False}]
    out = await _compose(engine, ectx)
    assert _GUIDANCE_OPEN not in out
    assert ectx.steering_notes == []  # still consumed
