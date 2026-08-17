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
from agents.capabilities.deliverables._mimetype import default_mimetype
from agents.capabilities.registry import register


@register(
    "deliverable",
    "streamed_text",
    description="Resolve the deliverable as the agent's streamed text output (no sandbox file read).",
    # No sandbox file access at all (unlike serialized_sandbox, which reads
    # arbitrary sandbox files and IS user_allowed=True below) — this is the
    # least-privileged deliverable resolver, so a user/db manifest may
    # reference it too (CAP-03).
    user_allowed=True,
)
class StreamedTextResolver:
    """Return the artifact-unwrapped streamed deliverable (``name='streamed_text'``).

    Satisfies the ``DeliverableResolver`` port. No workflow-name branch.
    """

    name = "streamed_text"

    @staticmethod
    def default_mimetype(deliverable_name: str | None = None) -> str:
        """Default deliverable shape hint (ISS-021): streamed text → text/markdown."""
        return default_mimetype("streamed_text", deliverable_name)

    def resolve(self, ctx: Any) -> Any:
        last_streamed = getattr(ctx, "last_streamed", "") or ""
        return unwrap_artifact(last_streamed)
