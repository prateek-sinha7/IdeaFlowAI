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
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.deliverables._artifact import (
    sanitize_carousel_deck_html,
    unwrap_artifact,
)


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
