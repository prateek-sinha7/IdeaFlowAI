"""agents/capabilities/repo_inventory/ — the kernel-side repo inventory (REPO-01).

Pure-stdlib, kernel-side capability package. Importing it fires the ``@register``
in ``inventory`` so ``discover()`` binds ``("repo_inventory", "default")``. The
capability reaches git/disk ONLY via the ``ctx.runner`` handle and lineage-tracks
its output via ``ctx.scoped_store`` — it imports NO ``app.*`` / engine module
(Pitfall 5; the import-linter pins this).
"""

from __future__ import annotations

from . import inventory  # noqa: F401 — import for the @register side effect

__all__ = ["inventory"]
