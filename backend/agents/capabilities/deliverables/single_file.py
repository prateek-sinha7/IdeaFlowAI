"""agents/capabilities/deliverables/single_file.py — the ``single_file`` resolver.

Folds the engine's prototype build branch (engine.py:506-518) AND the prototype
revision branch (:489-504) into ONE deliverable resolver keyed by
``deliverable.name`` — NO workflow-name branch (that name-based dispatch is
L4/L8, deleted in 07-05). The single named file the build loop / revision agent
wrote on disk IS the deliverable; the sandbox is read ONLY through ``ctx.runner``
(the D-03 handle), never a direct ``app.*`` import (Pitfall 4).

Fallback chain (the folded prototype + revision behavior):
  1. ``deliverable.name`` (default ``prototype.html``) read from the sandbox
  2. when a ``previous_run``-seeded ORIGINAL is present (in-place revision): prefer
     the seeded original over a NON-HTML stream and ``<artifact>``-unwrap the chosen
     value — byte-identical to the legacy ``prototype_revision`` branch, so a
     non-HTML confirmation never overwrites the user's prototype
  3. otherwise (forward build) the last-streamed agent output, returned raw.

This also absorbs the L10 readback (engine.py:1902, today gated on the prototype
workflow names) — reading ``deliverable.name`` from the sandbox here replaces
that workflow-name-gated readback (Pitfall 5).
"""

from __future__ import annotations

import logging
from typing import Any

from agents.capabilities.deliverables._artifact import unwrap_artifact
from agents.capabilities.deliverables._mimetype import default_mimetype
from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

_DEFAULT_NAME = "prototype.html"


@register("deliverable", "single_file", user_allowed=True)
class SingleFileResolver:
    """Resolve a single named file from the sandbox (``name='single_file'``).

    Satisfies the ``DeliverableResolver`` port (``name`` + ``resolve``). Resolves
    by ``deliverable.name`` / ``deliverable.strategy`` — never by pipeline name.
    """

    name = "single_file"

    @staticmethod
    def default_mimetype(deliverable_name: str | None) -> str:
        """Default deliverable shape hint (ISS-021): infer from the declared name ext."""
        return default_mimetype("single_file", deliverable_name)

    def resolve(self, ctx: Any) -> Any:
        runner = ctx.runner
        deliverable = getattr(ctx, "deliverable", None)
        filename = getattr(deliverable, "name", None) or _DEFAULT_NAME

        # (1) The named file the build loop / revision agent wrote IS the deliverable.
        built = runner.sandbox.read(filename)
        if built:
            return built

        last_streamed = getattr(ctx, "last_streamed", "") or ""
        original = getattr(ctx, "revision_original_html", "") or ""

        # (2) Revision fallback — a previous_run-seeded ORIGINAL means this run edits
        # an existing artifact in place. Byte-identical to the legacy
        # ``prototype_revision`` branch (engine.py@acd1636:489-504): prefer the
        # seeded original when the stream is NOT HTML (so a non-HTML confirmation
        # never overwrites the user's prototype), and unwrap an ``<artifact>`` tag.
        # Keyed on the ORIGINAL's presence — never on a pipeline-type name (INV-1).
        if original:
            streamed = last_streamed.strip()
            looks_like_html = streamed[:60].lower().lstrip().startswith(
                ("<!doctype", "<html")
            )
            chosen = streamed if looks_like_html else (original or streamed)
            logger.warning(
                "single_file: %s not written by agent — fell back to %s",
                filename,
                "streamed HTML" if looks_like_html else "seeded original",
            )
            return unwrap_artifact(chosen)

        # (3) Forward-build fallback — no seeded original; the streamed output IS the
        # deliverable, returned raw (matching the legacy forward prototype branch).
        if last_streamed.strip():
            logger.warning(
                "single_file: %s not written by agent — falling back to streamed output",
                filename,
            )
            return last_streamed

        return ""
