"""agents/capabilities/context_pack/ — the kernel-side targeted context subset (REPO-03).

Pure-stdlib, kernel-side. Importing it fires the ``@register`` in ``pack`` so
``discover()`` binds ``("context_pack", "default")``. The brownfield analog of the
prototype ``html_skeleton`` compaction: instead of the whole repo, an agent gets a
TARGETED subset (a target file + selector-chosen neighbors), lineage-tracked.
Reaches disk only via ``ctx.runner`` and the store via ``ctx.scoped_store``.
"""

from __future__ import annotations

from . import pack  # noqa: F401 — import for the @register side effect

__all__ = ["pack"]
