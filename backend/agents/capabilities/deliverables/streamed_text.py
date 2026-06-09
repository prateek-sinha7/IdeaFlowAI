"""agents/capabilities/deliverables/streamed_text.py — text deliverable.

Lift of the engine's text branch (engine.py:527-528):

    # Text / PPT: the streamed output IS the deliverable; unwrap an <artifact> tag.
    return _unwrap_artifact(last_streamed)

The last-streamed agent output (``ctx.last_streamed`` — ``results[-1]["output"]``)
IS the deliverable; an ``<artifact>`` wrapper (the PPT composer) is unwrapped via
the shared ``unwrap_artifact`` helper (also used by the ``ppt`` resolver). No
sandbox read, no ``app.*`` import.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.deliverables._artifact import unwrap_artifact
from agents.capabilities.registry import register


@register("deliverable", "streamed_text")
class StreamedTextResolver:
    """Return the artifact-unwrapped streamed deliverable (``name='streamed_text'``).

    Satisfies the ``DeliverableResolver`` port. No workflow-name branch.
    """

    name = "streamed_text"

    def resolve(self, ctx: Any) -> Any:
        last_streamed = getattr(ctx, "last_streamed", "") or ""
        return unwrap_artifact(last_streamed)
