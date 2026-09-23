"""Finalization record — the durable projection of a run's terminal state.

``FinalizationRecord`` is the single typed carrier of everything the finalizer
knows after a run completes.  Its DB projection lives in ``run_finalizations``
(migration 0042) and its chainability columns are mirrored onto ``WorkflowRun``
(migration 0044) in the same transaction.

Public surface
--------------
persist_finalization_record(db, record)
    Upsert ``run_finalizations`` + mirror onto ``WorkflowRun``.
    Never overwrites ``chain_context_installed`` — that column belongs to
    ``mark_chain_context_installed`` (Requirement 21 AC 8).
    Enforces derived invariant: published_status != candidate_status →
    payload_chainable = False.

persist_finalization_record_safe(db, record) → FinalizationRecord
    Best-effort wrapper.  On failure logs the unpersisted state and returns
    the in-memory record unchanged so the finalizer tail can still emit the
    terminal event (departure N1, Requirement 5 AC 12).

read_finalization_record(db, run_id) → FinalizationRecord | None
    Returns ``None`` for both absent rows and partial rows (any of the five
    key fields missing).  A partial row must not be read as a complete record
    (Requirement 5 AC 25).

Import-boundary note (contract 4/0 — agents.execution_engine must not import
app.api): all ``app.*`` imports are deferred inside function bodies, matching
the established pattern in ``engine.py``.

Schema source: specs/sandbox-git-versioning-v2 tasks 5.1, 5.10.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("agents.execution_engine.finalization")

# ---------------------------------------------------------------------------
# FinalizationRecord dataclass
# ---------------------------------------------------------------------------

@dataclass
class FinalizationRecord:
    """Complete projection of a run's terminal finalization state.

    Every field maps 1-to-1 onto a column in ``run_finalizations``.
    The record is per-run and upsertable on ``run_id``.

    ``read_finalization_record`` returns ``None`` when any of the five key
    fields (``published_status``, ``candidate_status``, ``payload_chainable``,
    ``commit_sha``, ``run_id``) are absent — a partial row is treated as absent.

    Departure N1 (Requirement 5 AC 12): ``persist_finalization_record_safe``
    returns the in-memory record unchanged on a DB write failure so the
    finalizer tail can still emit a terminal event.

    Do NOT add ``internal_ref`` or any internal-git-ref field to the API or
    frontend projection (Requirement 5 / tasks.md 1.5).
    """

    # Identity — required, never None in a well-formed record.
    run_id: str
    owner_id: str
    workspace_id: str

    # Outcome
    published_status: str | None = None   # the durable DB status after convergence
    candidate_status: str | None = None   # the candidate outcome at payload build time

    # Chainability — derived invariant enforced at persist time:
    #   published_status != candidate_status  →  payload_chainable = False
    payload_chainable: bool | None = None
    non_chainable_reason: str | None = None

    # Payload materialization state
    payload_built: bool | None = None
    payload_materialized: bool | None = None

    # Git versioning state
    commit_sha: str | None = None
    internal_ref: str | None = None   # refs/ideaflow/runs/{run_id} — never exposed to API
    git_tag: str | None = None
    tag_state: str | None = None      # "created" | "rolled_back"

    # Chain-context installation (owned by mark_chain_context_installed — PRESERVED here)
    chain_context_installed: bool | None = None

    # Degradation reason (stored in non_chainable_reason when degraded)
    degraded_reason: str | None = None

    # Optional human-readable note for operator recovery (departure N1 logging)
    _unpersisted: bool = field(default=False, repr=False, compare=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enforce_chainability_invariant(record: FinalizationRecord) -> FinalizationRecord:
    """Return a copy of *record* with the derived chainability invariant applied.

    When ``published_status != candidate_status`` the payload is non-chainable:
    the run did not converge cleanly, so downstream chains must not read it
    (Requirement 5 AC 21, Requirement 4 AC 7, Requirement 21 AC 14).

    This reconciles reading ``candidate_status`` from an installed ``summary.md``
    with reading the published status from the DB without rewriting any snapshot.
    """
    if (
        record.published_status is not None
        and record.candidate_status is not None
        and record.published_status != record.candidate_status
    ):
        return FinalizationRecord(
            run_id=record.run_id,
            owner_id=record.owner_id,
            workspace_id=record.workspace_id,
            published_status=record.published_status,
            candidate_status=record.candidate_status,
            payload_chainable=False,
            non_chainable_reason=(
                record.non_chainable_reason or "published_status_diverged"
            ),
            payload_built=record.payload_built,
            payload_materialized=record.payload_materialized,
            commit_sha=record.commit_sha,
            internal_ref=record.internal_ref,
            git_tag=record.git_tag,
            tag_state=record.tag_state,
            chain_context_installed=record.chain_context_installed,
            degraded_reason=record.degraded_reason,
            _unpersisted=record._unpersisted,
        )
    return record


def _is_complete_row(row: object) -> bool:
    """Return True iff the DB row has all five key fields populated.

    A partial row (any of the five fields NULL) is treated as absent by
    ``read_finalization_record`` (Requirement 5 AC 25).
    """
    return all(
        getattr(row, f, None) is not None
        for f in ("run_id", "published_status", "candidate_status", "payload_chainable", "commit_sha")
    )


def _row_to_record(row: object) -> FinalizationRecord:
    """Convert a ``RunFinalization`` ORM row to a ``FinalizationRecord``."""
    return FinalizationRecord(
        run_id=row.run_id,  # type: ignore[attr-defined]
        owner_id=row.owner_id,  # type: ignore[attr-defined]
        workspace_id=row.workspace_id,  # type: ignore[attr-defined]
        published_status=row.published_status,  # type: ignore[attr-defined]
        candidate_status=row.candidate_status,  # type: ignore[attr-defined]
        payload_chainable=row.payload_chainable,  # type: ignore[attr-defined]
        non_chainable_reason=row.non_chainable_reason,  # type: ignore[attr-defined]
        payload_built=row.payload_built,  # type: ignore[attr-defined]
        payload_materialized=row.payload_materialized,  # type: ignore[attr-defined]
        commit_sha=row.commit_sha,  # type: ignore[attr-defined]
        internal_ref=row.internal_ref,  # type: ignore[attr-defined]
        git_tag=row.git_tag,  # type: ignore[attr-defined]
        tag_state=row.tag_state,  # type: ignore[attr-defined]
        chain_context_installed=row.chain_context_installed,  # type: ignore[attr-defined]
    )


# ---------------------------------------------------------------------------
# Core persist
# ---------------------------------------------------------------------------

def persist_finalization_record(db: "Session", record: FinalizationRecord) -> None:
    """Upsert ``run_finalizations`` and mirror chainability onto ``WorkflowRun``.

    Both writes happen in the SAME transaction so the two tables stay consistent.

    Contract:
    - ``chain_context_installed`` is PRESERVED — its writer is
      ``mark_chain_context_installed``.  Any value on the in-memory record is
      ignored; the column is never overwritten by this function.
    - Derived invariant: if ``published_status != candidate_status`` the
      function forces ``payload_chainable = False`` before persisting
      (Requirement 5 AC 21).
    - ``payload_chainable`` and ``non_chainable_reason`` are mirrored onto
      ``WorkflowRun`` in the same transaction (Requirement 15 AC 6).

    Raises on any DB error — callers that need best-effort behaviour should
    use ``persist_finalization_record_safe`` instead.

    Import-boundary: all ``app.*`` imports are deferred (contract 4/0 —
    agents.execution_engine must not import app.api; app.models is permitted
    via deferred import matching the engine.py established pattern).
    """
    # Apply the derived invariant before touching the DB.
    effective = _enforce_chainability_invariant(record)

    from app.models.run_finalization import RunFinalization  # noqa: PLC0415
    from app.models.workflow import WorkflowRun  # noqa: PLC0415

    now = datetime.now(timezone.utc)

    # ── Upsert run_finalizations ──────────────────────────────────────────
    row: RunFinalization | None = (
        db.query(RunFinalization)
        .filter(RunFinalization.run_id == effective.run_id)
        .first()
    )

    if row is None:
        row = RunFinalization(
            owner_id=effective.owner_id,
            workspace_id=effective.workspace_id,
            run_id=effective.run_id,
            created_at=now,
        )
        db.add(row)

    # Scalar columns — always update from the effective record.
    row.published_status = effective.published_status
    row.candidate_status = effective.candidate_status
    row.payload_chainable = effective.payload_chainable
    row.non_chainable_reason = effective.non_chainable_reason
    row.payload_built = effective.payload_built
    row.payload_materialized = effective.payload_materialized
    row.commit_sha = effective.commit_sha
    row.internal_ref = effective.internal_ref
    row.git_tag = effective.git_tag
    row.tag_state = effective.tag_state
    row.updated_at = now

    # chain_context_installed is PRESERVED — written only by mark_chain_context_installed.
    # Do NOT overwrite it here, even when the in-memory record carries a value.

    # ── Mirror chainability onto WorkflowRun (same transaction) ──────────
    wr: WorkflowRun | None = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == effective.run_id)
        .first()
    )
    if wr is not None:
        wr.payload_chainable = effective.payload_chainable
        wr.non_chainable_reason = effective.non_chainable_reason

    db.commit()

    logger.info(
        "finalization_record persisted run=%s published=%s candidate=%s "
        "payload_chainable=%s commit=%s tag=%s tag_state=%s",
        effective.run_id,
        effective.published_status,
        effective.candidate_status,
        effective.payload_chainable,
        effective.commit_sha,
        effective.git_tag,
        effective.tag_state,
    )


# ---------------------------------------------------------------------------
# Safe (best-effort) persist
# ---------------------------------------------------------------------------

def persist_finalization_record_safe(
    db: "Session",
    record: FinalizationRecord,
) -> FinalizationRecord:
    """Best-effort wrapper around ``persist_finalization_record``.

    On success returns the persisted record (with the derived invariant applied).
    On failure logs the unpersisted state and returns the in-memory record with
    ``_unpersisted=True`` so the finalizer tail can still emit a terminal event
    without crashing (departure N1, Requirement 5 AC 12).

    The returned record is never None — callers may always emit a terminal event
    from it.
    """
    effective = _enforce_chainability_invariant(record)
    try:
        persist_finalization_record(db, effective)
        return effective
    except Exception as exc:  # noqa: BLE001 — best-effort; never reraise
        logger.error(
            "persist_finalization_record FAILED run=%s — departure N1 — "
            "returning in-memory record for terminal-event emission. "
            "Unpersisted state: published=%s candidate=%s payload_chainable=%s "
            "commit=%s tag=%s. Error: %s",
            effective.run_id,
            effective.published_status,
            effective.candidate_status,
            effective.payload_chainable,
            effective.commit_sha,
            effective.git_tag,
            exc,
        )
        # Try to roll back so the session is not left in a broken state.
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        # Return the in-memory record flagged as unpersisted so callers can
        # record the departure and still emit a terminal event.
        return FinalizationRecord(
            run_id=effective.run_id,
            owner_id=effective.owner_id,
            workspace_id=effective.workspace_id,
            published_status=effective.published_status,
            candidate_status=effective.candidate_status,
            payload_chainable=effective.payload_chainable,
            non_chainable_reason=effective.non_chainable_reason,
            payload_built=effective.payload_built,
            payload_materialized=effective.payload_materialized,
            commit_sha=effective.commit_sha,
            internal_ref=effective.internal_ref,
            git_tag=effective.git_tag,
            tag_state=effective.tag_state,
            chain_context_installed=effective.chain_context_installed,
            degraded_reason=effective.degraded_reason,
            _unpersisted=True,
        )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def read_finalization_record(
    db: "Session",
    run_id: str,
) -> FinalizationRecord | None:
    """Return the complete ``FinalizationRecord`` for *run_id*, or ``None``.

    Returns ``None`` for BOTH:
    - absent rows (no ``run_finalizations`` row for this run_id), and
    - partial rows (any of the five key fields is NULL).

    A partial row is indistinguishable from absent to callers: the finalizer
    has not yet committed a complete record (Requirement 5 AC 25).

    The five key fields are: ``run_id``, ``published_status``,
    ``candidate_status``, ``payload_chainable``, ``commit_sha``.

    Import-boundary: deferred import of app.models (contract 4/0).
    """
    from app.models.run_finalization import RunFinalization  # noqa: PLC0415

    row: RunFinalization | None = (
        db.query(RunFinalization)
        .filter(RunFinalization.run_id == run_id)
        .first()
    )

    if row is None:
        return None

    if not _is_complete_row(row):
        logger.debug(
            "read_finalization_record: partial row for run=%s — treating as absent",
            run_id,
        )
        return None

    return _row_to_record(row)
