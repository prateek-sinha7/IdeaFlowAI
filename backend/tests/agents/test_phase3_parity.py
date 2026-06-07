"""Phase 3 (0C) — pages/routes + validation-pass parity (COMPACT-02 / Req 6 / D-03).

This module is the SEMANTIC-PARITY half of the token-trim phase. The 0C change is the
ONE sanctioned non-byte-identical engine edit (INV-3): build-task-2+ now injects the
compact `_extract_html_skeleton` state-map instead of the full current HTML. Because it
is gated on SEMANTICS (not byte-identity), this test proves the produced deliverable's
structure is unchanged after compaction:

  * the set of `<section data-page>` IDs is identical before/after compaction, and
  * the `const routes` map key set is identical, and
  * validation is equal-or-better — zero net-new validation-FAILURE events.

It drives BOTH `prototype` and the `od_prototype` alias fully OFFLINE via
`_scripted_model._drive` (no DB / Bedrock / API key — importing `_drive` wires
`RUNS_ROOT`→temp + `ENV=development` at import time). The `data-page` IDs and `routes`
keys are derived with the SAME regexes `_extract_html_skeleton` uses (engine.py:2667 /
engine.py:2661) so the test and the helper agree on what a "page" / "route" is.

Pre-0C reference (falsifiable claim "the set is unchanged"):
  The committed `golden/prototype.html` is the stable post-0B reference deliverable —
  the scripted model writes a FIXED single-section HTML regardless of prompt content
  (see `_scripted_model.py:269-281`), so the committed golden IS the pre-compaction
  reference set. We derive the reference page/route sets from that committed golden,
  NOT from a freshly-driven "before" run (the engine edit is already live in this wave).

If the engine edit had dropped or renamed a `data-page` section, this test would FAIL
(the produced set would diverge from the committed-golden reference) — the ratchet is
real, not vacuous.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.agents._scripted_model import _drive
from tests.agents.characterization import extract_final_output, golden_path

# ── The SAME regexes `_extract_html_skeleton` uses (single source of truth for
#    what counts as a "page" / a "route") — engine.py:2667 (data-page) and
#    engine.py:2661 (const routes). Keeping them identical here means the parity
#    assertion measures exactly what the compaction helper summarizes. ──────────
_DATA_PAGE_RE = re.compile(r'<section[^>]+data-page=["\']([^"\']+)["\']', re.IGNORECASE)
_ROUTES_RE = re.compile(r"const routes\s*=\s*\{([^}]+)\}", re.DOTALL)
# Route keys inside the `const routes = { ... }` block: `key: "..."` / `key: '...'`.
_ROUTE_KEY_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*:")

# Failure-signal event types (a subset of the documented vocabulary that denotes a
# validation / run FAILURE). "Equal-or-better validation" = the count of these does
# NOT increase vs the pre-0C reference (which is zero on a clean scripted run).
_FAILURE_EVENT_TYPES = frozenset(
    {
        "error",
        "agent_error",
        "state_restoration_failed",
        "planner_timeout",
        "pipeline_cancelled",
    }
)


def _page_ids(html: str) -> set[str]:
    """Derive the `<section data-page>` ID set using the helper's own regex."""
    return set(_DATA_PAGE_RE.findall(html))


def _route_keys(html: str) -> set[str]:
    """Derive the `const routes` map key set using the helper's own regexes.

    Returns the empty set when there is no `const routes` block (the scripted
    single-section deliverable has none — a stable, asserted shape).
    """
    m = _ROUTES_RE.search(html)
    if not m:
        return set()
    return set(_ROUTE_KEY_RE.findall(m.group(1)))


def _failure_event_count(events: list[dict]) -> int:
    """Count validation/run FAILURE events in a drive's event stream."""
    return sum(1 for e in events if e.get("type") in _FAILURE_EVENT_TYPES)


# ── Pre-0C reference, derived from the committed golden deliverable ────────────
# The committed prototype golden is the post-0B reference (the scripted model writes
# fixed HTML regardless of prompt), so its page/route sets are the pre-compaction
# reference the produced deliverable must still match after the skeleton wiring.
_REFERENCE_HTML = golden_path("prototype.html").read_text(encoding="utf-8")
_REFERENCE_PAGE_IDS = _page_ids(_REFERENCE_HTML)
_REFERENCE_ROUTE_KEYS = _route_keys(_REFERENCE_HTML)


def test_reference_golden_has_a_stable_nonempty_page_set() -> None:
    """Guard: the committed reference deliverable defines the parity set non-vacuously.

    The scripted `prototype-build` writes exactly one `<section data-page='dashboard'>`
    and no `const routes` block (see `_scripted_model.py:269-281`). Pin that stable
    shape so the parity assertions below cannot pass vacuously against an empty set —
    if the committed golden ever lost its only section, this guard fails first.
    """
    assert _REFERENCE_PAGE_IDS, (
        "the committed prototype.html golden must define at least one data-page "
        "section to anchor the parity assertion"
    )
    assert _REFERENCE_PAGE_IDS == {"dashboard"}, (
        f"expected the scripted reference to have exactly the 'dashboard' page; "
        f"got {sorted(_REFERENCE_PAGE_IDS)}"
    )
    # The scripted single-section deliverable carries no `const routes` block.
    assert _REFERENCE_ROUTE_KEYS == set(), (
        f"expected the scripted reference to have no const routes map; "
        f"got route keys {sorted(_REFERENCE_ROUTE_KEYS)}"
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
async def test_od_prototype_pages_routes_parity() -> None:
    """COMPACT-02 / Req 6: the od_prototype alias has identical pages/routes parity.

    `od_prototype` rides the same `prototype-build` path (the alias resolves to the
    prototype agents — `_scripted_model.py:354`), so the single skeleton edit covers
    it too. The produced deliverable's page/route sets must match the same reference.
    """
    events = await _drive("od_prototype")
    assert events, "od_prototype produced no events"

    deliverable = extract_final_output(events)
    produced_pages = _page_ids(deliverable)
    produced_routes = _route_keys(deliverable)

    assert produced_pages, "the produced od_prototype deliverable has NO data-page section"
    assert produced_pages == _REFERENCE_PAGE_IDS, (
        f"od_prototype data-page ID set changed after compaction: produced "
        f"{sorted(produced_pages)} != reference {sorted(_REFERENCE_PAGE_IDS)}"
    )
    assert produced_routes == _REFERENCE_ROUTE_KEYS, (
        f"od_prototype routes key set changed after compaction: produced "
        f"{sorted(produced_routes)} != reference {sorted(_REFERENCE_ROUTE_KEYS)}"
    )


@pytest.mark.asyncio
async def test_validation_pass_equal_or_better() -> None:
    """COMPACT-02 / Req 6: validation is equal-or-better — zero net-new failures.

    The pre-0C reference is a clean run (zero validation-FAILURE events). After
    compaction both `prototype` and `od_prototype` must still complete with NO
    net-new failure events AND must reach `pipeline_complete` (a run that errored
    out would otherwise trivially have "no more failures"). Falsifiable: a
    compaction that broke the build would surface an `error`/`agent_error` event
    or never complete, and this test would FAIL.
    """
    # Pre-0C reference failure count is zero (a clean scripted run). "Equal-or-better"
    # = the post-compaction count must not exceed it.
    _REFERENCE_FAILURES = 0

    for label in ("prototype", "od_prototype"):
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
