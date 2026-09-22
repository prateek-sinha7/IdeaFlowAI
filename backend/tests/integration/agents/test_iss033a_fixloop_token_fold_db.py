"""ISS-033a validation fix-loop token fold — the END-TO-END (DB-touching) half.

Split out of ``tests/unit/agents/test_iss033a_fixloop_token_fold_offline.py``, which
pins the chain from the narrowest seam outward. Sections 1-2 (the loop routes ``usage``
into the injected sink; ``KernelServices`` threads its constructor sink into the loop)
are zero-I/O and STAY in the unit suite. Sections 3-4 below drive the REAL ``prototype``
pipeline via ``_drive``, i.e. the full ``ExecutionEngine.execute()``, which opens a
``SessionLocal()`` to persist run events — the unit-isolation guard in
``tests/unit/conftest.py`` rejects that by design, so they live here.

  3. end-to-end on the REAL ``prototype`` pipeline: the ``pipeline_complete`` totals
     now EXCEED the sum of the visible ``agent_complete`` totals by exactly the fix
     sub-agents' spend. That inequality is the ISS-033 statement itself;
  4. the fold must NOT reach ``results`` — ``agents_completed = len(results)``, so a
     fix attempt counted as an agent would corrupt the run's agent count.

Offline (scripted model, no Bedrock / no network) — but NOT zero-I/O.
"""

from __future__ import annotations

import pytest

from tests.agents._scripted_model import _drive


def _pipeline_complete(events: list[dict]) -> dict:
    for ev in events:
        if ev.get("type") == "pipeline_complete":
            return ev["data"]
    raise AssertionError("no pipeline_complete event was emitted")


def _visible_agent_totals(events: list[dict]) -> tuple[int, int]:
    """Sum the per-agent ``agent_complete`` tokens — everything the UI can SEE."""
    tin = sum(
        (ev.get("data") or {}).get("input_tokens", 0) or 0
        for ev in events
        if ev.get("type") == "agent_complete"
    )
    tout = sum(
        (ev.get("data") or {}).get("output_tokens", 0) or 0
        for ev in events
        if ev.get("type") == "agent_complete"
    )
    return tin, tout


#: The prototype golden runs 2 tasks × 2 bounded fix attempts = 4 fix sub-agents, each
#: consuming the ``prototype-build`` script's turns (50/20 then 10/5 — the fix agent
#: gets a FRESH scripted model per ``create_runner``). Hard-coded rather than derived
#: so a silent change in what the fix loop invokes fails loudly here.
_EXPECTED_FIXLOOP_INPUT = 240
_EXPECTED_FIXLOOP_OUTPUT = 100


@pytest.mark.asyncio
async def test_prototype_run_total_includes_fix_loop_tokens() -> None:
    """The run's reported totals EXCEED the visible per-agent totals by exactly the
    fix sub-agents' spend — the previously invisible money, now counted."""
    events = await _drive("prototype")
    totals = _pipeline_complete(events)
    visible_in, visible_out = _visible_agent_totals(events)

    assert visible_in > 0 and visible_out > 0, "the harness produced no agent tokens"

    assert totals["total_input_tokens"] - visible_in == _EXPECTED_FIXLOOP_INPUT
    assert totals["total_output_tokens"] - visible_out == _EXPECTED_FIXLOOP_OUTPUT
    assert totals["total_tokens"] == (
        totals["total_input_tokens"] + totals["total_output_tokens"]
    )


# ---------------------------------------------------------------------------
# the fold must not turn fix attempts into "agents"
# ---------------------------------------------------------------------------
#: ``agents_completed = len(results)`` counts ``_run_agent`` INVOCATIONS, not steps:
#: the prototype's 5 steps plus the build agent's second task = 6, which is why it
#: legitimately exceeds ``agents_total`` (5). Pinned literally so the four fix
#: sub-agents showing up here (6 → 10) fails loudly.
_EXPECTED_AGENTS_COMPLETED = 6


@pytest.mark.asyncio
async def test_fix_loop_tokens_do_not_inflate_agents_completed() -> None:
    """The fix spend goes to ``aux_token_usage``, never to ``results`` — so four fix
    sub-agents must not appear as four more completed agents (a regression guard:
    green before AND after, unlike the seam tests in the unit half)."""
    events = await _drive("prototype")
    totals = _pipeline_complete(events)
    agent_completes = sum(1 for ev in events if ev.get("type") == "agent_complete")

    assert totals["agents_completed"] == agent_completes
    assert totals["agents_completed"] == _EXPECTED_AGENTS_COMPLETED
