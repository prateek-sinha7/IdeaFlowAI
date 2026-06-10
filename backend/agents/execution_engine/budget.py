"""agents/execution_engine/budget.py — the per-run fan-out budget manager (Phase 11).

A ``BudgetManager`` is a PER-RUN object (INV-2 — never stashed on the engine
singleton): it holds the resolved per-run caps (subagents / concurrency / depth /
wall-clock) derived from the workflow's declared ``Limits`` plus the module-constant
defaults, and exposes the ``reserve()`` seam the single kernel ``run_fanout`` spawn
path calls BEFORE any spawn (Pitfall 4 — enforcement-point discipline).

In THIS plan ``reserve()`` is a STUB SEAM: it records the requested units onto the
running ``BudgetSnapshot`` and returns WITHOUT raising. The real enforcement (raising
``BudgetExceeded`` when a reservation would exceed a cap) lands in 11-04 (FANOUT-09 /
RESEARCH Open Question 2) — the call site exists now so 11-04 is a body change, not a
new wiring. ``spent()`` returns the accumulated counts.

Import-direction: this module is kernel-side and imports ONLY stdlib + the
``agents.workflows.plan`` ``Limits`` data type (a pure dataclass, no ``app.*`` reach) —
so the import-linter kernel→ports scaffold stays green.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — typing only
    from agents.workflows.plan import Limits


# ---------------------------------------------------------------------------
# Module-constant defaults (the per-run caps when the manifest declares no Limits)
# ---------------------------------------------------------------------------

DEFAULT_MAX_SUBAGENTS = 8
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_MAX_DEPTH = 2
DEFAULT_WALL_CLOCK_SECONDS = 900
MERGE_AGENT_MAX_ATTEMPTS = 2
BUDGET_WARN_THRESHOLD = 0.8


class BudgetExceeded(Exception):
    """Raised when a reservation would exceed a per-run cap (enforced 11-04).

    Defined now so the call site + the ``except BudgetExceeded`` discipline can be
    written this plan; ``reserve()`` does NOT raise it yet (the stub seam).
    """


@dataclass
class BudgetSnapshot:
    """The accumulated spend at a point in time (returned by ``spent()``)."""

    tokens: int = 0
    cost: dict | None = None
    subagents: int = 0
    depth: int = 0
    wall_clock_seconds: float = 0.0


class BudgetManager:
    """Per-run budget caps + the ``reserve()`` enforcement seam (FANOUT-09).

    Constructed from the workflow's declared ``Limits`` (or ``None``) plus the
    module-constant defaults: an unspecified cap falls back to its default. In this
    plan ``reserve()`` is a no-op-returning stub (records the requested units); the
    raising enforcement lands in 11-04.
    """

    def __init__(self, limits: "Limits | None" = None) -> None:
        self.max_subagents = (
            limits.max_subagents
            if limits is not None and limits.max_subagents is not None
            else DEFAULT_MAX_SUBAGENTS
        )
        self.max_depth = (
            limits.max_depth
            if limits is not None and limits.max_depth is not None
            else DEFAULT_MAX_DEPTH
        )
        self.wall_clock_seconds = (
            limits.wall_clock_seconds
            if limits is not None and limits.wall_clock_seconds is not None
            else DEFAULT_WALL_CLOCK_SECONDS
        )
        # Concurrency is not a Limits field (it is engine-enforced at min(declared, 4));
        # the manager carries the default cap so run_fanout can read it uniformly.
        self.max_concurrency = DEFAULT_MAX_CONCURRENCY
        self._snapshot = BudgetSnapshot()

    def reserve(
        self,
        *,
        tokens: int = 0,
        subagents: int = 0,
        concurrency: int = 0,
        depth: int = 0,
    ) -> None:
        """Reserve budget units BEFORE a spawn (STUB SEAM — enforcement is 11-04).

        Records the requested units onto the running snapshot and returns without
        raising. The 11-04 body adds the cap checks that raise ``BudgetExceeded``
        when a reservation would exceed ``max_subagents`` / ``max_depth`` /
        wall-clock (FANOUT-09). The call site in ``run_fanout`` is present NOW so
        11-04 is a body change, not a new wiring (Pitfall 4).
        """
        self._snapshot.tokens += tokens
        self._snapshot.subagents += subagents
        if depth > self._snapshot.depth:
            self._snapshot.depth = depth

    def spent(self) -> BudgetSnapshot:
        """Return the accumulated spend snapshot."""
        return self._snapshot
