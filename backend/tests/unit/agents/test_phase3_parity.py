"""Phase 3 (0C) — pages/routes + validation-pass parity (COMPACT-02 / Req 6 / D-03).

This module is the SEMANTIC-PARITY half of the token-trim phase. The 0C change is the
ONE sanctioned non-byte-identical engine edit (INV-3): build-task-2+ now injects the
compact `_extract_html_skeleton` state-map instead of the full current HTML. Because it
is gated on SEMANTICS (not byte-identity), this test proves the produced deliverable's
structure is unchanged after compaction:

  * the set of `<section data-page>` IDs is identical before/after compaction, and
  * the `const routes` map key set is identical, and
  * validation is equal-or-better — zero net-new validation-FAILURE events.

The two assertions that DRIVE `prototype` live in
`tests/integration/agents/test_phase3_parity_db.py`: `_scripted_model._drive` runs the
real `execute()`, which opens a `SessionLocal()` — the unit-isolation guard rejects that
(offline means no Bedrock/network, NOT zero-I/O; the older "no DB" note here was wrong).
This module keeps the golden-derived REFERENCE and the non-vacuity guard, and the
integration half imports them so the two cannot drift.

The `data-page` IDs and `routes` keys are derived with the SAME regexes
`_extract_html_skeleton` uses (engine.py:2667 / engine.py:2661) so the test and the
helper agree on what a "page" / "route" is.

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

from tests.agents.characterization import golden_path

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
