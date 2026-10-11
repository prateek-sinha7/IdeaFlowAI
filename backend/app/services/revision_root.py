"""app/services/revision_root.py — the canonical revision-root resolver.

Moved here from ``app/api/runs.py`` (move, not copy — INV-12) so the execution
kernel can resolve a run's revision root without importing the web layer: the
import-linter contract "kernel imports only capability ports (scaffold)" forbids
``agents.execution_engine -> app.api``, and the kernel reaches this resolver from
``engine._resolve_root_id`` and ``KernelServices.open_source_sandbox``.

``app.api.runs`` imports these names back for its own route handlers, so every
existing ``from app.api.runs import resolve_revision_root`` caller is unchanged.
"""

from dataclasses import dataclass
from typing import Union

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.workflow import WorkflowRun

# ---------------------------------------------------------------------------
# V2 — canonical revision-root resolver (Requirement 2, V2-Q1).
#
# resolve_revision_root is the SINGLE app-side function that resolves which
# physical sandbox directory a run belongs to.  Every consumer (engine launch,
# resume, factory, RunTrace, file routes, upload, sweeper, restore, previous-run
# reads, family locking, and the chain-source reader) MUST route through this
# function once task 3.3 is complete.
#
# Design contracts (Requirement 2 AC 1–12):
#   • Walks parent_run_id ONLY — source_run_id is NEVER followed (V2-Q1).
#   • Owner-scoped by non-null WorkflowRun.user_id; the filter is stated
#     explicitly so a future nullable-column change cannot silently weaken it.
#   • Visited-set cycle guard — a cycle is a hard failure, not a "use the last
#     unique node" fallback (supersedes v1 Requirement 1 AC 4).
#   • One typed failure outcome for every error class: cycle, missing ancestor,
#     cross-owner ancestry, null principal, and DB error all produce
#     RevisionRootUnresolved with a bounded reason string.
#   • NEVER selects the last unique node on a cycle.
#   • NEVER falls back to the requested run id on any failure.
#   • NEVER returns a partial root.
#
# Offline characterization harnesses may construct RunSandbox with an explicitly
# absent sandbox_root_id (defaulting current_run_id to the logical run id) — that
# is a valid offline path, not a resolution failure, and it never calls this
# function (Requirement 2 AC 6).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RevisionRootResolved:
    """Successful resolution: ``root_id`` is the revision-root run id."""

    root_id: str


@dataclass(frozen=True)
class RevisionRootUnresolved:
    """Typed failure.  Every error class produces this result so callers have
    exactly one handling branch (Requirement 2 AC 10–11).

    ``reason`` is one of:
      ``"null_principal"``     — ``user_id`` was empty/None; refused before any query.
      ``"cycle"``              — ``parent_run_id`` chain forms a cycle.
      ``"missing_or_cross_owner"`` — an ancestor row was not found or belongs to
                                     another user.
      ``"db_error"``           — SQLAlchemy raised during the walk.

    ``run_id`` is the run that was being resolved when the failure occurred.
    ``visited_count`` is the number of nodes visited before the failure (useful
    for support diagnostics without leaking ancestry shape to the client).
    ``repeated_node`` is the node that closed the cycle, or ``None`` for non-cycle
    failures (Requirement 2 AC 12 — "record the visited-set size, the repeated
    node, and the failure class for support").
    """

    reason: str
    run_id: str
    visited_count: int
    repeated_node: str | None


#: The result type returned by :func:`resolve_revision_root`.
ResolveRevisionRootResult = Union[RevisionRootResolved, RevisionRootUnresolved]


def resolve_revision_root(
    db: Session,
    run_id: str,
    user_id: str,
) -> ResolveRevisionRootResult:
    """Walk ``parent_run_id`` links to find the revision root for ``run_id``.

    Returns a :class:`RevisionRootResolved` on success or a
    :class:`RevisionRootUnresolved` on any failure.  Never raises — callers
    branch on the result type.

    ``user_id`` MUST be non-null (the non-null condition is stated explicitly
    in the ORM filter so a future nullable-column migration cannot silently
    weaken the ownership predicate — Requirement 2 AC 4).

    The walk is bounded by the visited set: every node is visited at most once,
    so the total number of DB round trips is at most the chain depth.

    Callers that receive ``RevisionRootUnresolved`` MUST:
      • Return a generic non-enumerating error to the client (never expose
        another owner's run id, ancestry shape, or path).
      • Log ``visited_count``, ``repeated_node``, and ``reason`` server-side for
        support (Requirement 2 AC 12).
      • For the TTL sweeper: treat the failure as **protected** (never deletable).
    """
    if not user_id:
        return RevisionRootUnresolved(
            reason="null_principal",
            run_id=run_id,
            visited_count=0,
            repeated_node=None,
        )

    visited: set[str] = set()
    current = run_id

    while True:
        if current in visited:
            # A cycle was detected: current is the node that closes the loop.
            # NEVER select the last unique node — fail closed (Requirement 2 AC 10).
            return RevisionRootUnresolved(
                reason="cycle",
                run_id=run_id,
                visited_count=len(visited),
                repeated_node=current,
            )
        visited.add(current)

        try:
            row = (
                db.query(WorkflowRun.id, WorkflowRun.parent_run_id)
                .filter(
                    WorkflowRun.id == current,
                    # Ownership predicate — stated explicitly so it cannot be
                    # weakened by a future schema change (Requirement 2 AC 4).
                    WorkflowRun.user_id == user_id,
                    WorkflowRun.user_id.isnot(None),
                )
                .first()
            )
        except SQLAlchemyError:
            return RevisionRootUnresolved(
                reason="db_error",
                run_id=run_id,
                visited_count=len(visited),
                repeated_node=None,
            )

        if row is None:
            # Missing row OR owned by another user — fail closed without
            # distinguishing which, so the client cannot enumerate ownership
            # (Requirement 2 AC 5, AC 11–12).
            return RevisionRootUnresolved(
                reason="missing_or_cross_owner",
                run_id=run_id,
                visited_count=len(visited),
                repeated_node=None,
            )

        _id, parent_run_id = row
        if parent_run_id is None:
            # No parent: ``current`` is the revision root.
            return RevisionRootResolved(root_id=current)

        # Advance one step up the parent chain.
        current = parent_run_id
