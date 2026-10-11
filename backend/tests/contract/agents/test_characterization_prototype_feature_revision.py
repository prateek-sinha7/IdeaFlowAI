"""Characterization: `prototype_feature_revision` deliverable byte-snapshot (SAFE-01 / INV-3).

The characterization baseline for the ``prototype_feature_revision`` pipeline (the
feature-addition revision: analyzer → feature-specify → plan → task_loop build →
validate). Locks the deliverable BYTE-FOR-BYTE and the semantic event stream before
any engine/factory refactor (INV-3). Byte-identity half of SAFE-01.

Verifies (task 10.3 requirements 2.3, 2.4, 4.2, 5.3):
  * ``prototype-revision-analyzer`` appears as step 0 with ``agent_start`` /
    ``agent_complete`` events.
  * ``=== REVISION ANALYSIS ===`` is injected into the context of step 1
    (``prototype-revision-feature-specify``).

Drives fully OFFLINE via ``_drive``; snapshots ``pipeline_complete.final_output``.
Carries no live-LLM marker so CI runs it; regenerate with ``SNAPSHOT_UPDATE=1``.
"""

from __future__ import annotations

import pathlib

import pytest

from tests.agents._scripted_model import _RUNS_ROOT, _drive
from tests.agents.characterization import (
    SNAPSHOT_UPDATE,
    assert_deliverable_snapshot,
    extract_final_output,
)
from tests.agents.characterization._normalize import (
    _DOCUMENTED_EVENT_TYPES,
    _REQUIRED_DATA_KEYS,
    _canonical_order,
    _normalize,
    assert_seq_contiguous,
    load_events_golden,
    write_events_golden,
)


@pytest.mark.asyncio
async def test_prototype_feature_revision_deliverable_byte_snapshot() -> None:
    events = await _drive("prototype_feature_revision")
    assert events, "prototype_feature_revision produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("prototype_feature_revision.html", deliverable)


@pytest.mark.asyncio
async def test_prototype_feature_revision_event_snapshot() -> None:
    """Lock the normalized semantic event stream for ``prototype_feature_revision`` (SAFE-02 / SAFE-03)."""
    events = await _drive("prototype_feature_revision")
    assert events, "prototype_feature_revision produced no events"

    seen = {e.get("type") for e in events}
    unknown = seen - _DOCUMENTED_EVENT_TYPES
    assert not unknown, f"prototype_feature_revision emitted UNDOCUMENTED event type(s): {sorted(unknown)}"

    for ev in events:
        required = _REQUIRED_DATA_KEYS.get(ev.get("type"))
        if required is None:
            continue
        missing = required - set((ev.get("data") or {}).keys())
        assert not missing, (
            f"prototype_feature_revision event '{ev.get('type')}' is MISSING required data "
            f"keys {sorted(missing)}"
        )

    assert_seq_contiguous(events)

    normalized = _canonical_order(_normalize(events))
    if SNAPSHOT_UPDATE:
        write_events_golden("prototype_feature_revision.events.json", normalized)
        return

    golden = load_events_golden("prototype_feature_revision.events.json")
    assert golden is not None, (
        "prototype_feature_revision.events.json golden missing — run once with "
        "SNAPSHOT_UPDATE=1 and COMMIT golden/prototype_feature_revision.events.json."
    )
    assert normalized == golden, (
        "prototype_feature_revision normalized event stream diverged from the committed "
        "golden (dropped/reordered event or lost required key). Regenerate "
        "intentionally with SNAPSHOT_UPDATE=1 (SAFE-02)."
    )


@pytest.mark.asyncio
async def test_prototype_feature_revision_analyzer_is_step_0() -> None:
    """Req 2.3/2.4/5.3: prototype-revision-analyzer must fire as step 0 with agent_start + agent_complete."""
    events = await _drive("prototype_feature_revision")
    assert events, "prototype_feature_revision produced no events"

    # Collect all agent_start and agent_complete events for prototype-revision-analyzer.
    analyzer_starts = [
        e
        for e in events
        if e.get("type") == "agent_start"
        and (e.get("data") or {}).get("agent_id") == "prototype-revision-analyzer"
    ]
    analyzer_completes = [
        e
        for e in events
        if e.get("type") == "agent_complete"
        and (e.get("data") or {}).get("agent_id") == "prototype-revision-analyzer"
    ]

    assert analyzer_starts, (
        "prototype_feature_revision: no agent_start event found for "
        "prototype-revision-analyzer (step 0). "
        "The YAML manifest must have prototype-revision-analyzer as step 0 with "
        "produces_solution_plan: true (Req 2.3/2.4)."
    )
    assert analyzer_completes, (
        "prototype_feature_revision: no agent_complete event found for "
        "prototype-revision-analyzer (step 0). "
        "The engine hook must fire after the step (Req 4.2/5.3)."
    )

    # Verify analyzer fires BEFORE the feature-specify agent (step 1).
    analyzer_start_idx = next(
        i
        for i, e in enumerate(events)
        if e.get("type") == "agent_start"
        and (e.get("data") or {}).get("agent_id") == "prototype-revision-analyzer"
    )
    specify_start_idx = next(
        (
            i
            for i, e in enumerate(events)
            if e.get("type") == "agent_start"
            and (e.get("data") or {}).get("agent_id")
            == "prototype-revision-feature-specify"
        ),
        None,
    )
    if specify_start_idx is not None:
        assert analyzer_start_idx < specify_start_idx, (
            "prototype-revision-analyzer agent_start must appear BEFORE "
            "prototype-revision-feature-specify agent_start (step 0 precedes step 1)."
        )


@pytest.mark.asyncio
async def test_prototype_feature_revision_revision_analysis_in_step1_context() -> None:
    """Req 4.2/5.3, updated by M10 (GAPS §0.3/§1 P1 Q4 rollout): the solution plan
    reaches step 1 (feature-specify), but the CHANNEL changed. Both agents are
    migrated (``prompt_policy: governance``) as of M10, so the row-17 world block
    (``=== REVISION ANALYSIS ===``, gated ``not _is_migrated`` in
    ``_compose_context_message``) no longer pastes into the context_message — the
    engine instead writes the analyzer's streamed output, unconditionally, to
    ``.agents/01-prototype-revision-analyzer.md`` (``write_agent_output``, step index
    0), and prototype-revision-feature-specify's own Sandbox Reading Guide points it
    there. Proves BOTH halves: the paste is gone AND the real producer→consumer file
    read actually works (not a check that would also pass on a broken pipe)."""
    events = await _drive("prototype_feature_revision")
    assert events, "prototype_feature_revision produced no events"

    # Find agent_input events for prototype-revision-feature-specify (step 1).
    specify_inputs = [
        e
        for e in events
        if e.get("type") == "agent_input"
        and (e.get("data") or {}).get("agent_id")
        == "prototype-revision-feature-specify"
    ]

    assert specify_inputs, (
        "prototype_feature_revision: no agent_input event found for "
        "prototype-revision-feature-specify. Cannot verify the solution plan delivery."
    )

    for ev in specify_inputs:
        ctx_msg = (ev.get("data") or {}).get("context_message", "")
        assert "=== REVISION ANALYSIS ===" not in ctx_msg, (
            "prototype_feature_revision: === REVISION ANALYSIS === is still being "
            "PASTED into prototype-revision-feature-specify's context_message — both "
            "agents are migrated (governance), so this world block (row 17) must stay "
            "gated behind `not _is_migrated`.\n"
            f"context_message (first 500 chars): {ctx_msg[:500]!r}"
        )

    run_id = (specify_inputs[0].get("data") or {}).get("pipeline_run_id")
    assert (
        run_id
    ), "agent_input event carried no pipeline_run_id — cannot locate the sandbox"
    solution_plan_path = (
        pathlib.Path(_RUNS_ROOT)
        / "harness-user"
        / run_id
        / ".agents"
        / "01-prototype-revision-analyzer.md"
    )
    assert solution_plan_path.is_file(), (
        "prototype_feature_revision: the analyzer's solution plan was not written to "
        f"{solution_plan_path} — prototype-revision-feature-specify's Sandbox Reading "
        "Guide has nothing to read (the paste is retired with no working disk substitute)."
    )
    assert "## Solution Plan" in solution_plan_path.read_text(encoding="utf-8"), (
        f"{solution_plan_path} exists but does not contain the analyzer's "
        "'## Solution Plan' output contract"
    )
