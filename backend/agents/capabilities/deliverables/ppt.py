"""agents/capabilities/deliverables/ppt.py — the ``ppt`` deck deliverable.

The PPT resolver owns the carousel-sanitize + artifact-unwrap transform as a
declared capability (PARITY-07). The streamed deck IS the deliverable; before
unwrapping it the resolver strips the slide-hiding CSS the od_ppt composer may
hallucinate (so a horizontal-carousel deck renders all slides):

    return unwrap_artifact(sanitize_carousel_deck_html(last_streamed))

This resolver owns BOTH carousel-sanitize behaviors the engine performs today
(Pitfall 3 / PARITY-07):
  * the final-output sanitize (engine.py:1394), and
  * the mid-stream sanitize in ``_run_agent`` (engine.py:1916, today gated on the
    PPT workflow names — that L3 gate is deleted in 07-05).
Both kernel call sites can be deleted in 07-05 because the behavior lives here.
No sandbox read, no ``app.*`` import — the transform is import-pure.

WR-02 (07-09 confirm-then-fix): the deep review flagged that this resolver applies
``unwrap_artifact(sanitize_carousel_deck_html(x))`` (NEW) while the legacy engine
applied ``sanitize(unwrap(x))`` (acd1636 unwrapped first). We built the documented
repro — an ``<artifact>``-wrapped carousel deck carrying the carousel-breaking
``.slide:not(.active){display:none}`` rule — and confirmed both orderings produce
BYTE-IDENTICAL output: ``sanitize`` only removes carousel-conflicting CSS that lives
inside the deck body (which survives both orderings) and its carousel detection scans
the whole string (so the wrapper never changes whether it fires), while ``unwrap``
discards everything outside the artifact. The NEW order is therefore parity-safe and is
KEPT as-is; the equivalence is pinned by
``tests/agents/test_deliverable_resolvers.py::test_ppt_sanitize_unwrap_order_is_equivalent_on_wrapped_carousel``.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.deliverables._artifact import (
    sanitize_carousel_deck_html,
    unwrap_artifact,
)
from agents.capabilities.registry import register


@register("deliverable", "ppt")
class PptResolver:
    """Carousel-sanitize + artifact-unwrap the streamed deck (``name='ppt'``).

    Satisfies the ``DeliverableResolver`` port. No workflow-name branch — the
    sanitize transform is itself a no-op on non-carousel / non-HTML input, so it
    is safe to apply unconditionally to the ppt-declared deliverable.
    """

    name = "ppt"

    def resolve(self, ctx: Any) -> Any:
        last_streamed = getattr(ctx, "last_streamed", "") or ""
        return unwrap_artifact(sanitize_carousel_deck_html(last_streamed))
