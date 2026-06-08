"""agents/capabilities/deliverables/single_file.py — the ``single_file`` resolver.

Folds the engine's prototype build branch (engine.py:506-518) AND the prototype
revision branch (:489-504) into ONE deliverable resolver keyed by
``deliverable.name`` — NO workflow-name branch (that name-based dispatch is
L4/L8, deleted in 07-05). The single named file the build loop / revision agent
wrote on disk IS the deliverable; the sandbox is read ONLY through ``ctx.runner``
(the D-03 handle), never a direct ``app.*`` import (Pitfall 4).

Fallback chain (the folded prototype + revision behavior):
  1. ``deliverable.name`` (default ``prototype.html``) read from the sandbox
  2. the last-streamed agent output (``ctx.last_streamed``)
  3. the ``previous_run``-seeded ORIGINAL HTML (``ctx.revision_original_html``)
     — the revision last-ditch fallback when the agent never wrote the file.

This also absorbs the L10 readback (engine.py:1902, today gated on the prototype
workflow names) — reading ``deliverable.name`` from the sandbox here replaces
that workflow-name-gated readback (Pitfall 5).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_NAME = "prototype.html"


class SingleFileResolver:
    """Resolve a single named file from the sandbox (``name='single_file'``).

    Satisfies the ``DeliverableResolver`` port (``name`` + ``resolve``). Resolves
    by ``deliverable.name`` / ``deliverable.strategy`` — never by pipeline name.
    """

    name = "single_file"

    def resolve(self, ctx: Any) -> Any:
        runner = ctx.runner
        deliverable = getattr(ctx, "deliverable", None)
        filename = getattr(deliverable, "name", None) or _DEFAULT_NAME

        # (1) The named file the build loop / revision agent wrote IS the deliverable.
        built = runner.sandbox.read(filename)
        if built:
            return built

        # (2) Fall back to the last streamed output (NEVER serialize the sandbox —
        # it bundles the spec.md/design.md/tasks.md reference scaffolding).
        last_streamed = getattr(ctx, "last_streamed", "") or ""
        streamed = last_streamed.strip()
        if streamed:
            logger.warning(
                "single_file: %s not written by agent — falling back to streamed output",
                filename,
            )
            return last_streamed

        # (3) Last-ditch: the previous_run-seeded ORIGINAL (revision path).
        original = getattr(ctx, "revision_original_html", "") or ""
        if original:
            logger.warning(
                "single_file: %s not written and no stream — falling back to seeded original",
                filename,
            )
            return original

        return ""
