"""RunProvenanceAudit SQLAlchemy model — git provenance operation log.

Table ``run_provenance_audits`` — append-only audit log for git provenance
operations (tag, restore, snapshot_commit) performed against a run's sandbox.
Each row records a single operation.  An optional ``idempotency_key``
deduplicates retries via a partial unique index.

The row carries ``owner_id`` + ``workspace_id`` (both ``nullable=False``,
AUTHZ-01) so cross-owner reads return nothing (default-deny IDOR gate).

Indexes:
  - Partial unique on (owner_id, operation, idempotency_key)
    WHERE idempotency_key IS NOT NULL
  - Regular index on (owner_id, source_ref)
  - Regular index on run_id

Schema source: specs/sandbox-git-versioning-v2 task 5.1;
  ``outcome`` column and ``lookup_idempotent_restore`` added in task 8.2.
"""

import uuid
from datetime import datetime, timezone
from typing import TypedDict

from sqlalchemy import Column, DateTime, Index, String, text
from sqlalchemy.orm import Session

from app.models.database import Base


class RunProvenanceAudit(Base):
    """One row per git provenance operation — the audit trail for tag/restore/commit."""

    __tablename__ = "run_provenance_audits"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, nullable=False)  # AUTHZ-01
    workspace_id = Column(String, nullable=False)  # AUTHZ-01
    run_id = Column(String, nullable=False)

    # Operation descriptor — e.g. "snapshot_commit", "restore", "tag_created"
    operation = Column(String, nullable=False)

    # Source git ref the operation was applied against (e.g. a visible tag name)
    source_ref = Column(String, nullable=True)

    # Retry deduplication — operations with the same idempotency_key for the
    # same owner + operation are collapsed by the partial unique index below.
    # Two concurrent requests with the SAME key collapse here rather than
    # double-committing (Requirement 9 AC 10, task 8.2).
    idempotency_key = Column(String, nullable=True)

    # Result artifacts — typed columns, readable without decoding detail_json
    commit_sha = Column(String, nullable=True)
    tag_name = Column(String, nullable=True)

    # Bounded outcome classifier — e.g. "committed", "no_change", "blocked",
    # "degraded".  Set for every row; the restore idempotency lookup reads this
    # typed column directly so it never has to decode ``detail_json``
    # (Requirement 9 AC 10, task 8.2 "no detail blob").
    outcome = Column(String, nullable=True)

    # Free JSON blob for supplementary operation-specific detail.
    # NOT used by ``lookup_idempotent_restore`` — typed columns are the read
    # surface per task 8.2.
    detail_json = Column(String, nullable=True)

    created_at = Column(
        DateTime,
        nullable=True,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Partial unique: collapse concurrent replays when idempotency_key is set.
        Index(
            "uq_run_provenance_audits_idem",
            "owner_id",
            "operation",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_run_provenance_audits_owner_src", "owner_id", "source_ref"),
        Index("ix_run_provenance_audits_run", "run_id"),
    )


# ── Typed projection returned by the idempotency lookup ──────────────────────


class RestoreIdempotentResult(TypedDict):
    """Typed projection of a stored restore replay record.

    ``commit_id`` is the commit that was created (or that HEAD already pointed
    at for a no-op restore).  ``tag_name`` is the source tag that was restored
    from.  ``outcome`` is the bounded classifier written at record time —
    one of ``"committed"`` | ``"no_change"`` | ``"blocked"`` | ``"degraded"``.

    No free-form detail blob is included — typed columns only, per task 8.2.
    """

    commit_id: str | None
    tag_name: str | None
    outcome: str | None


def lookup_idempotent_restore(
    db: Session,
    owner_id: str,
    idempotency_key: str,
) -> "RestoreIdempotentResult | None":
    """Return the stored result of a previous restore with this idempotency key.

    Queries ``run_provenance_audits`` for ``operation="restore"`` with a
    matching ``owner_id`` and ``idempotency_key``.

    Returns a :class:`RestoreIdempotentResult` dict on a hit, or ``None`` when
    no prior record exists for this key.

    **The caller MUST invoke this BEFORE the active-family guard** so that a
    retried restore whose first attempt succeeded can return its cached result
    even when a new run has since started in the same family (Requirement 9
    AC 10).  A successful prior restore was committed with its idempotency key;
    a blocked restore deliberately omits the key so that the block can clear and
    a re-attempt will go through normally.

    Never raises — on a DB error returns ``None`` (fail-open for the lookup so
    the caller falls through to a fresh attempt; the fresh attempt may then
    fail-closed on the active guard or the family lock as appropriate).
    """
    try:
        row = (
            db.query(
                RunProvenanceAudit.commit_sha,
                RunProvenanceAudit.tag_name,
                RunProvenanceAudit.outcome,
            )
            .filter(
                RunProvenanceAudit.owner_id == owner_id,
                RunProvenanceAudit.operation == "restore",
                RunProvenanceAudit.idempotency_key == idempotency_key,
            )
            .first()
        )
    except Exception:  # noqa: BLE001
        return None

    if row is None:
        return None

    return RestoreIdempotentResult(
        commit_id=row.commit_sha,
        tag_name=row.tag_name,
        outcome=row.outcome,
    )
