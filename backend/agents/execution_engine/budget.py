"""agents/execution_engine/budget.py — the per-run fan-out budget manager (Phase 11).

A ``BudgetManager`` is a PER-RUN object (INV-2 — never stashed on the engine
singleton): it holds the resolved per-run caps (subagents / concurrency / depth /
wall-clock / tokens) derived from the workflow's declared ``Limits`` plus the
module-constant defaults, and ENFORCES them through the ``reserve()`` the single
kernel ``run_fanout`` spawn path calls BEFORE any spawn (Pitfall 4 —
enforcement-point discipline).

ENFORCEMENT (11-04 / FANOUT-09): ``reserve(*, subagents, concurrency, depth)`` raises
``BudgetExceeded`` (naming the breached dimension) when a reservation would exceed a
COUNTABLE cap — total subagents, concurrency, or depth (``ctx.depth + 1 > max_depth``,
i.e. a nested fan-out beyond the configured depth). Tokens + wall-clock are
check-at-boundary, NOT pre-reservable (you cannot pre-reserve unknown token spend —
the §6 ``reserve(*, tokens=0, subagents=0)`` dual shape, D-05): ``note_tokens(n)``
accumulates and raises when over ``max_tokens`` (when declared); ``note_wall_clock()``
raises when the wall-clock deadline (captured at the manager's ``arm()`` call) is past.

Per-workspace ceilings (OBS-01): ``from_limits(limits, *, workspace_ceiling=...)``
seeds an optional aggregate ceiling that ``reserve`` checks against the workspace's
ALREADY-spent subagents (passed in via ``workspace_spent``) so a second run in the
same workspace can be refused once the workspace aggregate is exhausted.

Import-direction: this module is kernel-side and imports ONLY stdlib + the
``agents.workflows.plan`` ``Limits`` data type (a pure dataclass, no ``app.*`` reach) —
so the import-linter kernel→ports scaffold stays green.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
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
    """Raised when a reservation would exceed a per-run / per-workspace cap (FANOUT-09).

    The message NAMES the breached dimension (subagents / concurrency / depth / tokens /
    wall_clock / workspace) so the abort event + the partial-results summary can report
    which ceiling tripped. Raised BEFORE the offending spawn (reserve-before-spawn) so a
    refused reservation leaves zero side effects (no extra ``subagent_runs`` rows).
    """

    def __init__(self, dimension: str, message: str) -> None:
        super().__init__(message)
        self.dimension = dimension


@dataclass
class BudgetSnapshot:
    """The accumulated spend at a point in time (returned by ``spent()``)."""

    tokens: int = 0
    cost: dict | None = None
    subagents: int = 0
    depth: int = 0
    wall_clock_seconds: float = 0.0


class BudgetManager:
    """Per-run budget caps + the ENFORCING ``reserve()`` (FANOUT-09 / OBS-01).

    Constructed from the workflow's declared ``Limits`` (or ``None``) plus the
    module-constant defaults: an unspecified cap falls back to its default (tokens stay
    uncapped unless the manifest declares ``max_tokens``). ``reserve()`` enforces the
    countable caps (subagents / concurrency / depth + the per-workspace aggregate);
    ``note_tokens`` / ``note_wall_clock`` enforce the check-at-boundary caps.
    """

    def __init__(
        self,
        limits: "Limits | None" = None,
        *,
        workspace_ceiling: int | None = None,
    ) -> None:
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
        # Tokens are UNCAPPED unless the manifest declares max_tokens (you cannot
        # pre-reserve unknown token spend — D-05 check-at-boundary).
        self.max_tokens = (
            limits.max_tokens
            if limits is not None and limits.max_tokens is not None
            else None
        )
        # Concurrency is not a Limits field (it is engine-enforced at min(declared, 4));
        # the manager carries the default cap so run_fanout can read + enforce it uniformly.
        self.max_concurrency = DEFAULT_MAX_CONCURRENCY
        # The per-workspace aggregate ceiling (OBS-01). None ⇒ unset (no UI; the
        # WORKSPACE_BUDGET settings seam supplies it). When set, reserve refuses once
        # ``workspace_spent + requested > workspace_ceiling``.
        self.workspace_ceiling = workspace_ceiling
        self._snapshot = BudgetSnapshot()
        self._deadline: float | None = None

    # ── Construction from a compiled workflow's Limits + the workspace ceiling ──
    @classmethod
    def from_limits(
        cls,
        limits: "Limits | None",
        *,
        workspace_ceiling: int | None = None,
    ) -> "BudgetManager":
        """Construct a manager resolving ``Limits`` over the module-constant defaults.

        An undeclared cap falls back to its default; ``max_tokens`` stays uncapped
        unless declared. ``workspace_ceiling`` is the optional per-workspace aggregate
        (from the WORKSPACE_BUDGET settings seam) checked at reserve time.
        """
        return cls(limits, workspace_ceiling=workspace_ceiling)

    def arm(self) -> None:
        """Capture the wall-clock deadline (called at ``run_fanout`` entry).

        ``note_wall_clock`` raises ``BudgetExceeded`` once ``time.monotonic()`` passes
        ``arm() + wall_clock_seconds``. Idempotent re-arm keeps the FIRST deadline so a
        nested fan-out cannot extend the run's wall-clock budget.
        """
        if self._deadline is None:
            self._deadline = time.monotonic() + self.wall_clock_seconds

    def reserve(
        self,
        *,
        tokens: int = 0,
        subagents: int = 0,
        concurrency: int = 0,
        depth: int = 0,
        workspace_spent: int = 0,
    ) -> None:
        """Reserve budget units BEFORE a spawn — ENFORCING (FANOUT-09 / OBS-01).

        Raises ``BudgetExceeded`` (naming the breached dimension) when the requested
        COUNTABLE units would exceed a resolved cap:

          * ``subagents`` — ``running_subagents + requested > max_subagents``;
          * ``concurrency`` — ``requested > max_concurrency``;
          * ``depth`` — ``depth + 1 > max_depth`` (a nested fan-out beyond the cap; the
            child level is ``ctx.depth`` and the spawn it is about to perform sits one
            level deeper, so a top-level run at depth 2 with max_depth=2 is refused);
          * per-workspace — ``workspace_spent + requested > workspace_ceiling`` (when a
            ceiling is configured) so a second run in the same workspace is refused once
            the aggregate is exhausted.

        Raised BEFORE recording the units, so a refused reservation leaves ZERO side
        effects (reserve-before-spawn — no extra ``subagent_runs`` rows). Tokens are
        accumulated (the §6 dual shape) but pre-reservation never raises on them — the
        token cap is check-at-boundary via ``note_tokens``.
        """
        # ── Depth (nested fan-out) ───────────────────────────────────────────
        # The spawn happens one level below ctx.depth; depth+1 > max_depth is refused.
        if subagents and depth + 1 > self.max_depth:
            raise BudgetExceeded(
                "depth",
                f"fan-out at depth {depth} would spawn at depth {depth + 1}, "
                f"exceeding max_depth={self.max_depth} (FANOUT-09)",
            )
        # ── Concurrency ──────────────────────────────────────────────────────
        if concurrency and concurrency > self.max_concurrency:
            raise BudgetExceeded(
                "concurrency",
                f"requested concurrency {concurrency} exceeds "
                f"max_concurrency={self.max_concurrency} (FANOUT-09)",
            )
        # ── Total subagents (this run) ───────────────────────────────────────
        if subagents and self._snapshot.subagents + subagents > self.max_subagents:
            raise BudgetExceeded(
                "subagents",
                f"reserving {subagents} subagent(s) on top of "
                f"{self._snapshot.subagents} already spent would exceed "
                f"max_subagents={self.max_subagents} (FANOUT-09)",
            )
        # ── Per-workspace aggregate (across the workspace's runs) ────────────
        if (
            subagents
            and self.workspace_ceiling is not None
            and workspace_spent + subagents > self.workspace_ceiling
        ):
            raise BudgetExceeded(
                "workspace",
                f"reserving {subagents} subagent(s) on top of {workspace_spent} "
                f"already spent across the workspace would exceed the per-workspace "
                f"ceiling {self.workspace_ceiling} (OBS-01)",
            )
        # All checks passed — record the units (the reservation is now committed).
        self._snapshot.tokens += tokens
        self._snapshot.subagents += subagents
        if depth > self._snapshot.depth:
            self._snapshot.depth = depth

    def note_tokens(self, n: int) -> None:
        """Check-at-boundary token accounting (raises when over ``max_tokens``).

        Accumulates ``n`` onto the running snapshot; raises ``BudgetExceeded`` when a
        declared ``max_tokens`` cap is breached. A ``None`` cap (the default — undeclared)
        never raises (tokens uncapped). You cannot pre-reserve unknown token spend, so
        this runs AFTER a worker reports its usage, not before the spawn (D-05).
        """
        self._snapshot.tokens += n
        if self.max_tokens is not None and self._snapshot.tokens > self.max_tokens:
            raise BudgetExceeded(
                "tokens",
                f"accumulated tokens {self._snapshot.tokens} exceed "
                f"max_tokens={self.max_tokens} (FANOUT-09)",
            )

    def note_wall_clock(self) -> None:
        """Check-at-boundary wall-clock enforcement (raises past the deadline).

        Updates the snapshot's elapsed wall-clock and raises ``BudgetExceeded`` once the
        ``arm()`` deadline is past — a mid-flight breach aborts gracefully (pending
        workers never spawn; the completed workers' fragments are surfaced). A no-op when
        the manager was never armed (a direct unit-style invocation).
        """
        if self._deadline is None:
            return
        now = time.monotonic()
        elapsed = self.wall_clock_seconds - (self._deadline - now)
        if elapsed > self._snapshot.wall_clock_seconds:
            self._snapshot.wall_clock_seconds = elapsed
        if now > self._deadline:
            raise BudgetExceeded(
                "wall_clock",
                f"wall-clock deadline ({self.wall_clock_seconds}s) exceeded "
                f"mid-flight — aborting with partial results (FANOUT-09)",
            )

    def warn_threshold_reached(self, dimension: str) -> bool:
        """True when the spend on ``dimension`` is ≥ ``BUDGET_WARN_THRESHOLD`` of its cap.

        Drives the ``budget_warning`` event ``run_fanout`` emits at ≥80% of any ceiling
        (OBS-01). An uncapped dimension (tokens with no ``max_tokens``) never warns.
        """
        if dimension == "subagents":
            cap = self.max_subagents
            spent = self._snapshot.subagents
        elif dimension == "depth":
            cap = self.max_depth
            spent = self._snapshot.depth
        elif dimension == "tokens":
            cap = self.max_tokens
            spent = self._snapshot.tokens
        elif dimension == "wall_clock":
            cap = self.wall_clock_seconds
            spent = self._snapshot.wall_clock_seconds
        else:
            return False
        if not cap:
            return False
        return spent >= BUDGET_WARN_THRESHOLD * cap

    def spent(self) -> BudgetSnapshot:
        """Return the accumulated spend snapshot (refreshing the wall-clock elapsed)."""
        if self._deadline is not None:
            elapsed = self.wall_clock_seconds - (self._deadline - time.monotonic())
            if elapsed > self._snapshot.wall_clock_seconds:
                self._snapshot.wall_clock_seconds = max(elapsed, 0.0)
        return self._snapshot
