"""agents.capabilities.deliverables — the ``DeliverableResolver`` capabilities.

The four resolver families decompose the engine's ``_resolve_final_output``
chooser (engine.py:447-528) into declared capabilities (PARITY-02 / PARITY-07):

  * ``single_file``        — read ``deliverable.name`` (default ``prototype.html``)
  * ``serialized_sandbox`` — the code-gen ``filename:``-block bundle
  * ``streamed_text``      — ``_unwrap_artifact(last_streamed)``
  * ``ppt``                — carousel-sanitize + artifact-unwrap (owns BOTH)

Each satisfies the ``DeliverableResolver`` port (``name`` attr + ``resolve(ctx)``)
and resolves by ``deliverable.name`` / ``deliverable.strategy`` — NEVER by a
workflow-name branch (INV-1). The sandbox / serialize / count primitives are
reached ONLY through the ``ctx.runner`` handle (the D-03 seam) — no ``app.*``
import (Pitfall 4 / import-linter).
"""
