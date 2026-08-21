"""Characterization: `sample_subagents_parallel` deliverable + event snapshot
(SAFE-01 / SAFE-02 / SAFE-03 / INV-3) — the fan-out/sibling-group family.

The four 003 characterization suites (prototype, prototype_revision, ppt,
app_builder) all drive the SERIAL agent-per-step dispatch path. None of them
exercises the ``subagents: {mode: parallel}`` sibling-group path: children
compiled with a shared ``dispatched_by`` are SKIPPED by the serial dispatch
loop (engine.py:2596-2603) and instead spawned concurrently through the kernel
``run_fanout`` path. The planned dispatch-loop conversion touches exactly that
skip logic, so this suite pins the fan-out family's byte/event identity
alongside the other four before that refactor lands.

Drives ``sample_subagents_parallel`` (page parent + apple/ball/cat siblings,
``mode: parallel``) fully OFFLINE via the shared ``_drive`` harness — same
scripted-model recipe as the other four, no dedicated script branches added.
The three siblings and the parent all fall through to the harness's generic
per-agent-id text turn (``_scripts_for``'s fallback branch), which calls no
tools, so the parent never writes ``page.html``; the ``single_file`` resolver
(agents/capabilities/deliverables/single_file.py) then falls back to the
parent's own last-streamed text as the deliverable — deterministic, just not
literal HTML (hence the ``.txt`` golden extension, matching ``app_builder``'s
serialized-bundle convention rather than ``prototype``'s HTML one).

Event ordering: the three siblings run concurrently, so their per-child
``agent_start``/``agent_chunk``/``tool_call``/``agent_complete`` events arrive
on the parallel_group strategy's merge queue in a run-to-run-unstable order —
the SAME class of async-interleaving nondeterminism the event-snapshot's
order-canonical MULTISET comparison (``_canonical_order``, see
``characterization/_normalize.py``'s ORDERING NOTE) already exists to absorb.
The wrapper events (``subagent_spawned``/``subagent_result``) are additionally
emitted in a fixed worker-index order by the kernel itself (fanout.py:585-591,
630-632), so only the per-child leaf events ride the multiset comparison.

Regenerate the goldens deliberately with ``SNAPSHOT_UPDATE=1``.
"""

from __future__ import annotations

import pytest

from tests.agents._scripted_model import _drive
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

_PIPELINE = "sample_subagents_parallel"


@pytest.mark.asyncio
async def test_sample_subagents_parallel_deliverable_byte_snapshot() -> None:
    events = await _drive(_PIPELINE)
    assert events, f"{_PIPELINE} produced no events"

    deliverable = extract_final_output(events).encode("utf-8")
    assert_deliverable_snapshot("sample_subagents_parallel.txt", deliverable)


@pytest.mark.asyncio
async def test_sample_subagents_parallel_event_snapshot() -> None:
    """Lock the normalized semantic event stream for the fan-out family.

    Same anti-false-green discipline as the other four: required-keys +
    vocabulary assertions run BEFORE the equality compare, and
    ``assert_seq_contiguous`` pins strict per-run ``seq`` numbering even though
    the per-child leaf events themselves compare as a multiset.
    """
    events = await _drive(_PIPELINE)
    assert events, f"{_PIPELINE} produced no events"

    seen = {e.get("type") for e in events}
    unknown = seen - _DOCUMENTED_EVENT_TYPES
    assert not unknown, (
        f"{_PIPELINE} emitted UNDOCUMENTED event type(s): {sorted(unknown)}"
    )

    # The sibling-group skip logic is the specific behavior this suite exists to
    # pin: every worker (page/apple/ball/cat) must start EXACTLY ONCE. A missing
    # `dispatched_by` skip in the serial loop double-runs a child; a broken
    # fan-out wire drops it entirely — either failure is a real dispatch-loop
    # regression this multiset-tolerant suite would otherwise not catch on its
    # own (order is deliberately not asserted, only membership + count).
    started = [
        e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"
    ]
    assert sorted(started) == sorted([
        "custom-agent:page", "custom-agent:apple", "custom-agent:ball", "custom-agent:cat",
    ]), started

    for ev in events:
        required = _REQUIRED_DATA_KEYS.get(ev.get("type"))
        if required is None:
            continue
        missing = required - set((ev.get("data") or {}).keys())
        assert not missing, (
            f"{_PIPELINE} event '{ev.get('type')}' is MISSING required data keys "
            f"{sorted(missing)}"
        )

    assert_seq_contiguous(events)

    normalized = _canonical_order(_normalize(events))
    if SNAPSHOT_UPDATE:
        write_events_golden("sample_subagents_parallel.events.json", normalized)
        return

    golden = load_events_golden("sample_subagents_parallel.events.json")
    assert golden is not None, (
        "sample_subagents_parallel.events.json golden missing — run once with "
        "SNAPSHOT_UPDATE=1 and COMMIT golden/sample_subagents_parallel.events.json "
        "so the default run is a real assertion."
    )
    assert normalized == golden, (
        "sample_subagents_parallel normalized event stream diverged from the "
        "committed golden — a dropped/reordered event, a lost required key, or a "
        "sibling-group skip-logic regression (double-run / dropped worker). If "
        "intentional (sanctioned 0C change), regenerate with SNAPSHOT_UPDATE=1 and "
        "review the diff (SAFE-02)."
    )
