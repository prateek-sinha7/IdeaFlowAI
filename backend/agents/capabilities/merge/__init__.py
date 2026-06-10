"""agents/capabilities/merge/ — the MergeStrategy port + 4 registered impls (Phase 11).

The merge layer integrates the per-worker fan-out fragments back into the run's
primary workspace (FANOUT-07). The ``MergeStrategy`` port (``base.py``) mirrors the
``capabilities.base.ExecutionStrategy`` one-method-Protocol idiom; the 4 impls
(``copy_disjoint`` / ``git_3way`` / ``json`` / ``html_fragment``) each self-register
under the ``merge`` kind (``user_allowed=True``) so the ENGINE selects them by name
(A2 — the user never names a merge strategy; INV-7).

Import purity (import-linter / INV-13): every module in this package imports NOTHING
from ``agents.execution_engine`` or ``app.*`` and shells NOTHING (no subprocess, no
git) — ``git_3way`` reaches git ONLY through the ``ctx.runner`` handle (Phase-9 D-10).
"""

from __future__ import annotations
