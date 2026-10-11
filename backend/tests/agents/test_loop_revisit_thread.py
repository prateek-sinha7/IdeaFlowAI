"""Re-dispatching a step in one run must give it a FRESH checkpoint thread.

Same class as the ``:redo{n}`` and ``:retry{n}`` regressions, on the path a
conditional route takes.

Live evidence (run fafea1bc): the Coverage Check judged ``synthesis.md``
"incomplete" because it described an undocumented Stage 4, and routed back to
the Synthesizer. The Synthesizer REMOVED the stage. The checker then re-ran,
resumed its own pass-1 checkpoint, replayed its original verdict verbatim in 7
seconds without re-reading the corrected file, and routed back again — three
passes, three byte-identical answers, then ``budget_aborted`` on
``loop_iterations``. A gate that cannot observe the fix it demanded makes every
route loop unwinnable.

The counter is per DISPATCH and not ``step_visit_counts`` on purpose. The first
attempt at this fix keyed on the visit counter and only half worked: run
d1b62f76 shows the Synthesizer correctly getting ``…:wmvl34:visit1`` while the
Coverage Check re-ran on the bare ``…:y16vzf`` both times, because the visit
counter is incremented for the route TARGET only. The checker re-runs as
ordinary forward progress through the step list, which that counter does not
model.
"""

import pytest

from tests.unit.agents.test_redo_gate_safety import (
    ScriptedFakeChatModel,
    _EngineHarness,
    _drive_agent,
    _make_ectx,
    _text_turn,
)


async def _threads_over_dispatches(n: int) -> list[str]:
    """Dispatch one agent ``n`` times in a single run; return its thread ids."""
    from agents.loader import load_agent_spec

    spec = load_agent_spec("domain-analyst")  # text-only, single_shot

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_text_turn("out. "))
    ) as h:
        ectx = _make_ectx("loop-thread-run", gate_agent_ids=[])
        for _ in range(n):
            await _drive_agent(h.engine, spec, ectx, [], [spec])
        return [t for t in h.thread_ids if t]


@pytest.mark.asyncio
async def test_first_dispatch_keeps_the_bare_thread_id() -> None:
    """INV-3: an ordinary run is byte-identical, like :redo/:rev/:retry."""
    from agents.loader import load_agent_spec

    spec = load_agent_spec("domain-analyst")
    assert await _threads_over_dispatches(1) == [f"loop-thread-run:{spec.id}"]


@pytest.mark.asyncio
async def test_every_re_dispatch_gets_its_own_thread() -> None:
    """The bug reused one thread for every pass, so the step answered from memory."""
    from agents.loader import load_agent_spec

    spec = load_agent_spec("domain-analyst")
    base = f"loop-thread-run:{spec.id}"
    assert await _threads_over_dispatches(4) == [
        base,
        f"{base}:visit1",
        f"{base}:visit2",
        f"{base}:visit3",
    ]


@pytest.mark.asyncio
async def test_the_four_passes_of_run_fafea1bc_are_all_distinct() -> None:
    tids = await _threads_over_dispatches(4)
    assert len(set(tids)) == 4, f"a loop pass REUSED a checkpoint thread: {tids}"


@pytest.mark.asyncio
async def test_a_gate_step_re_running_forward_also_gets_a_fresh_thread() -> None:
    """What the visit-counter version missed.

    The Coverage Check is never a route TARGET — the route points at the
    Synthesizer — so ``step_visit_counts`` stays 0 for it however many times it
    runs. Counting dispatches is what gives it a clean conversation.
    """
    from agents.loader import load_agent_spec

    spec = load_agent_spec("domain-analyst")

    with _EngineHarness(
        lambda aid, idx: ScriptedFakeChatModel(_text_turn("out. "))
    ) as h:
        ectx = _make_ectx("gate-thread-run", gate_agent_ids=[])
        await _drive_agent(h.engine, spec, ectx, [], [spec])
        await _drive_agent(h.engine, spec, ectx, [], [spec])
        tids = [t for t in h.thread_ids if t]

    assert ectx.step_visit_counts.get(spec.id, 0) == 0, (
        "fixture guard: this step is not a route target, so the visit counter "
        "stays 0 — which is exactly why keying on it did not fix the checker"
    )
    assert tids[1] != tids[0], "the second dispatch REUSED the first one's thread"
    assert tids[1].endswith(":visit1")
