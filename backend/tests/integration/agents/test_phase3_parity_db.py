"""COMPACT-02 / Req 6 prototype parity — the engine-driving (DB-touching) half.

Split out of ``tests/unit/agents/test_phase3_parity.py``. That module's
``test_reference_golden_has_a_stable_nonempty_page_set`` only reads the committed
golden off disk and stays in the unit suite; the two parity assertions below drive the
full prototype pipeline through ``_drive`` — the real ``ExecutionEngine.execute()``,
which opens a ``SessionLocal()`` to persist run events. The unit-isolation guard in
``tests/unit/conftest.py`` rejects that by design (the original docstring's "no DB"
claim was inaccurate: offline means no Bedrock, not zero-I/O).

The page/route REGEXES, the failure-event vocabulary, the derived helpers and the
golden-derived reference sets are IMPORTED from the unit module rather than copied.
They are deliberately "the SAME regexes ``_extract_html_skeleton`` uses (single source
of truth for what counts as a page / a route)", and the unit module also owns the
non-vacuity guard that proves the reference set is non-empty — duplicating them here
would let the two halves drift and let these assertions pass vacuously.
"""

from __future__ import annotations

import pytest

from tests.agents._scripted_model import _drive
from tests.agents.characterization import extract_final_output

# Single source of truth for the parity measure — imported, never copied.
from tests.unit.agents.test_phase3_parity import (
    _FAILURE_EVENT_TYPES,
    _REFERENCE_PAGE_IDS,
    _REFERENCE_ROUTE_KEYS,
    _failure_event_count,
    _page_ids,
    _route_keys,
)


@pytest.mark.asyncio
async def test_prototype_pages_routes_parity() -> None:
    """COMPACT-02 / Req 6: prototype data-page IDs + routes keys unchanged post-0C.

    Drives the full prototype pipeline offline (the build runs tasks 1 AND 2, so the
    task-2 skeleton-injection path is exercised), then derives the produced
    deliverable's page/route sets with the helper's own regexes and asserts they
    equal the pre-0C reference. Falsifiable: a dropped/renamed section would diverge.
    """
    events = await _drive("prototype")
    assert events, "prototype produced no events"

    deliverable = extract_final_output(events)
    produced_pages = _page_ids(deliverable)
    produced_routes = _route_keys(deliverable)

    assert produced_pages, (
        "the produced prototype deliverable has NO data-page section — compaction "
        "must not drop the page(s) (a zero-page result would pass route parity "
        "vacuously)"
    )
    assert produced_pages == _REFERENCE_PAGE_IDS, (
        f"data-page ID set changed after compaction: produced {sorted(produced_pages)} "
        f"!= reference {sorted(_REFERENCE_PAGE_IDS)} (semantic parity, Req 6)"
    )
    assert produced_routes == _REFERENCE_ROUTE_KEYS, (
        f"routes map key set changed after compaction: produced "
        f"{sorted(produced_routes)} != reference {sorted(_REFERENCE_ROUTE_KEYS)}"
    )


@pytest.mark.asyncio
async def test_validation_pass_equal_or_better() -> None:
    """COMPACT-02 / Req 6: validation is equal-or-better — zero net-new failures.

    The pre-0C reference is a clean run (zero validation-FAILURE events). After
    compaction `prototype` must still complete with NO
    net-new failure events AND must reach `pipeline_complete` (a run that errored
    out would otherwise trivially have "no more failures"). Falsifiable: a
    compaction that broke the build would surface an `error`/`agent_error` event
    or never complete, and this test would FAIL.
    """
    # Pre-0C reference failure count is zero (a clean scripted run). "Equal-or-better"
    # = the post-compaction count must not exceed it.
    _REFERENCE_FAILURES = 0

    for label in ("prototype",):
        events = await _drive(label)
        assert events, f"{label} produced no events"

        failures = _failure_event_count(events)
        assert failures <= _REFERENCE_FAILURES, (
            f"{label}: validation regressed after compaction — {failures} failure "
            f"event(s) vs reference {_REFERENCE_FAILURES} (equal-or-better, Req 6). "
            f"Failure events: "
            f"{[e.get('type') for e in events if e.get('type') in _FAILURE_EVENT_TYPES]}"
        )

        # A clean, completed run (so "no failures" is not because the run died early).
        assert any(e.get("type") == "pipeline_complete" for e in events), (
            f"{label}: run did not reach pipeline_complete — zero failures must come "
            f"from a clean completion, not an aborted run"
        )
