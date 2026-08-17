"""tests/agents/test_gate_revision_discriminator.py — ISS-052: tell the doubled gate apart.

One "Update the Specs" click opens the analyze gate THREE times: ``[0]`` the outer
first-pass gate, ``[1]`` the analyze re-run INSIDE the revision sub-pipeline, ``[2]`` the
gate re-opened once the pass returns. ``[1]`` and ``[2]`` carry the SAME ``gate_key``
(``f"{run_id}:{agent_id}"`` names a gate SLOT, not a FIRING) and the SAME output bytes —
live run ``5ecb990f`` seq 24652/24655: 11,974 chars, sha1 ``0136795fc392``, 5 ms apart with
no agent run between — yet they carry OPPOSITE affordances (``update_specs_eligible``
False vs True). Nothing on the wire distinguished them, so the user could not tell which
gate they were on and a tester misread the pair badly enough to file a wrong major issue
(ISS-062, closed as a misdiagnosis).

What is proven here:

  * **The pair is unique per firing.** ``(revision_cycle, revision_in_flight)`` is
    ``(0, False) / (1, True) / (1, False)`` across ``[0] / [1] / [2]``. ``revision_cycle``
    ALONE cannot separate ``[1]`` from ``[2]`` — both are cycle 1 — which is exactly why
    the FE's re-arm latch needs both. Test 1.
  * **The cycle index is durable and advances.** A second sibling cycle publishes 2. This
    is the server-side per-cycle signal ISS-063 needs (its FE counter is ``useState(0)``,
    incremented only from a live FE-armed inference and never back-filled). Test 2.
  * **The REAL gate stamps them.** Its sibling ``test_spec_revision_cycles.py`` stubs
    ``_run_review_gate`` out, so it can only prove what the engine PASSES. Test 3 drives
    the real primitive and reads the emitted ``review_gate_ready.data``. Test 4 pins the
    default the declared/user gate path rides on (mirroring ``redoable``).
  * **SC-001 / INV-3.** No workflow or agent-id literal anywhere on the path, and both keys
    are in the volatile strip set so the characterization goldens stay byte-identical.
    Tests 5 and 6.

Offline-safe: scripted model only — no Bedrock / Postgres / Chromium.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory checkpointer
# BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import ScriptedFakeChatModel  # noqa: E402,F401

_CYCLE = "revision_cycle"
_IN_FLIGHT = "revision_in_flight"


def _stamps(records: list[dict]) -> list[tuple]:
    """The ``(revision_cycle, revision_in_flight)`` pair sampled at each gate firing."""
    return [(r[_CYCLE], r[_IN_FLIGHT]) for r in records]


async def _first_ready(engine, **gate_kwargs) -> dict:
    """Open ONE real ``_run_review_gate`` and return its ``review_gate_ready`` payload.

    The generator is closed at the yield rather than resolved: this test is about what the
    gate PUBLISHES, and resolving it would need a client task that proves nothing extra.
    """
    agen = engine._run_review_gate(**gate_kwargs)
    try:
        event = await agen.__anext__()
    finally:
        await agen.aclose()
    assert event.get("type") == "review_gate_ready", (
        f"the gate's first emission is no longer review_gate_ready; got {event}"
    )
    return event["data"]


# ===========================================================================
# 1 + 2 — the discriminator across a real revision drive
# ===========================================================================


@pytest.mark.asyncio
async def test_each_gate_firing_carries_a_distinct_revision_stamp() -> None:
    """Over ONE cycle the three analyze-gate firings publish three DIFFERENT stamps.

    ``[0]`` no revision has run (0, False); ``[1]`` cycle 1 is on the stack (1, True);
    ``[2]`` cycle 1 has returned (1, False). Pairwise distinctness is the whole point —
    it is what lets the UI (and the FE's one-action latch, whose reset effect keys on
    ``output`` + ``gateKey``, NEITHER of which changes between ``[1]`` and ``[2]``) tell
    the two identical-looking gates apart.
    """
    from tests.agents.test_spec_revision_cycles import _drive_cycles

    records, _tids, _ectx, _ordered, _events = await _drive_cycles("iss052-stamp", {0})

    assert len(records) == 3, (
        f"expected 3 gate firings for one cycle; got {[r['firing'] for r in records]}"
    )
    stamps = _stamps(records)

    assert stamps == [(0, False), (1, True), (1, False)], (
        "the outer / in-pass / re-opened analyze gates must publish "
        f"(0,False)/(1,True)/(1,False); got {stamps}"
    )
    assert len(set(stamps)) == 3, (
        "two gate firings published the SAME discriminator, so they are still "
        f"indistinguishable on the wire (ISS-052); got {stamps}"
    )
    # The load-bearing pair: same gate_key, same output, same cycle — only in-flight differs.
    assert stamps[1][0] == stamps[2][0] and stamps[1][1] != stamps[2][1], (
        "the in-pass and re-opened gates belong to the SAME cycle and must be separated by "
        f"the in-flight flag alone; got {stamps[1]} vs {stamps[2]}"
    )


@pytest.mark.asyncio
async def test_a_second_cycle_advances_the_published_cycle_index() -> None:
    """Two sibling cycles ⇒ the published cycle index reaches 2.

    ISS-063 needs a DURABLE per-cycle signal (the FE's ``specRevisionCount`` is live-session
    state that never back-fills). This is that signal: it rides ``review_gate_ready``, so it
    is on the durable ``run_events`` log and survives a reopen.
    """
    from tests.agents.test_spec_revision_cycles import _drive_cycles

    records, _tids, _ectx, _ordered, _events = await _drive_cycles("iss052-second", {0, 2})

    assert len(records) == 5, (
        f"expected 5 gate firings for two cycles; got {[r['firing'] for r in records]}"
    )
    cycles = [r[_CYCLE] for r in records]

    assert cycles == [0, 1, 1, 2, 2], (
        f"the cycle index must advance 0 -> 1 -> 2 across two sibling cycles; got {cycles}"
    )
    assert [r[_IN_FLIGHT] for r in records] == [False, True, False, True, False], (
        "the in-flight flag must be True at exactly the two in-pass gates; got "
        f"{[r[_IN_FLIGHT] for r in records]}"
    )


# ===========================================================================
# 3 + 4 — the REAL gate primitive publishes it (and its default)
# ===========================================================================


@pytest.mark.asyncio
async def test_real_gate_stamps_the_discriminator_on_review_gate_ready() -> None:
    """``_run_review_gate`` puts both keys on the event the FE actually receives.

    Its sibling ``test_spec_revision_cycles.py`` stubs this primitive out, so without this
    test the engine could pass the values correctly and never publish them.
    """
    from tests.agents.test_update_specs_enforcement import _fresh_engine

    data = await _first_ready(
        _fresh_engine(),
        pipeline_run_id="iss052-real",
        agent_id="gated-agent",
        agent_name="Gated Agent",
        output="THE ANALYZE OUTPUT",
        redoable=True,
        update_specs_eligible=True,
        artifact_kind="summary",
        revision_cycle=2,
        revision_in_flight=True,
    )

    assert data.get(_CYCLE) == 2, (
        f"review_gate_ready did not carry the revision cycle; got {sorted(data)}"
    )
    assert data.get(_IN_FLIGHT) is True, (
        f"review_gate_ready did not carry the in-flight flag; got {sorted(data)}"
    )


@pytest.mark.asyncio
async def test_gate_defaults_the_discriminator_for_the_declared_path() -> None:
    """Omitting the discriminator publishes ``(0, False)`` — never absent, never None.

    The declared/user-composed ``gate:human`` path reaches this primitive through
    ``run_human_gate``, which passes neither key (exactly as it passes no ``redoable``).
    A declared gate is not inside a revision pass, so ``(0, False)`` is the truthful
    default AND the one that renders no revision badge at all.
    """
    from tests.agents.test_update_specs_enforcement import _fresh_engine

    data = await _first_ready(
        _fresh_engine(),
        pipeline_run_id="iss052-declared",
        agent_id="declared-step",
        agent_name="Declared Step",
        output="the gated output",
    )

    assert data.get(_CYCLE) == 0, f"expected a 0 default; got {data.get(_CYCLE)!r}"
    assert data.get(_IN_FLIGHT) is False, (
        f"expected a False default; got {data.get(_IN_FLIGHT)!r}"
    )
    # Same default-bearing path the redoable fence rides — pinned together so a future
    # signature change cannot silently make one of them default-true.
    assert data.get("redoable") is False


# ===========================================================================
# 5 + 6 — SC-001 (no literal) and INV-3 (goldens byte-identical)
# ===========================================================================


def test_discriminator_introduces_no_agent_id_literal() -> None:
    """Every engine line mentioning either key derives it from generic run scratch, never
    from a workflow/agent-id comparison (SC-001) — mirrors the eligibility guard."""
    import agents.execution_engine.engine as engine_mod

    lines = Path(engine_mod.__file__).read_text().splitlines()
    stamp_lines = [ln for ln in lines if _CYCLE in ln or _IN_FLIGHT in ln]
    assert stamp_lines, "the revision discriminator never appears in engine.py"
    for ln in stamp_lines:
        assert "prototype-" not in ln, (
            f"discriminator line names a workflow/agent literal (SC-001 leak): {ln!r}"
        )
        assert "pipeline_type" not in ln, (
            f"discriminator line branches on pipeline_type (SC-001 leak): {ln!r}"
        )


def test_discriminator_keys_are_in_volatile_strip_set() -> None:
    """Both keys are additive metadata NOT in the required-key set, so they are stripped
    from the canonical-JSON multiset — mirroring the redoable / update_specs_eligible
    precedent — keeping the characterization event goldens byte-identical (INV-3).

    The goldens drive with ``gate_agent_ids=[]`` so they contain ZERO gate events; this
    strip is the guard that keeps that true if a golden ever starts gating.
    """
    from tests.agents.characterization._normalize import _VOLATILE_STRIP_KEYS

    assert _CYCLE in _VOLATILE_STRIP_KEYS
    assert _IN_FLIGHT in _VOLATILE_STRIP_KEYS
