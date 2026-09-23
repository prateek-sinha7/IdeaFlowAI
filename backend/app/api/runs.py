"""Run-history CRUD API endpoints (relocated from /api/workflows — D-02).

This router owns the WorkflowRun read/delete/export surface that previously
lived under ``/api/workflows``. The move (Phase 4 / D-02) reclaims
``/api/workflows`` for manifest-derived definitions (see ``workflows.py``) and
establishes ``/api/runs`` as the run-history sub-resource home the §22 plan
envisions (Phase 5 lands ``/api/runs/{id}/artifacts|events`` here).

The relocation is a clean break with NO legacy redirect aliases: RESEARCH § "D-02
— API-Key Public Surface Check (RESOLVED)" confirmed these routes are JWT-only
(``Depends(get_current_user)``) with no external API-key consumer, so the 10
frontend refs are repointed atomically (Plan 04-05 Task 3).

Security carried over VERBATIM from the original handlers:
  * IDOR (ASVS V4 / T-04-12): every query that reads a run keeps the per-user
    ``.filter(WorkflowRun.user_id == current_user.id)`` ownership filter, so a
    cross-owner request resolves to 404, never another user's data.
  * HTTP response splitting (T-04-14): the export-pptx filename is sanitized
    with ``re.sub(r"[^A-Za-z0-9._-]", "_", title)[:40]`` exactly as before.
"""

import json
import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.sandbox import (
    FamilyLockTimeout,
    GIT_METADATA_PATHS,
    RESERVED_PATHS,
    RunSandbox,
    family_lock,
)
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.artifact_ref import ArtifactRef
from app.models.database import get_db
from app.models.exec_runs import ExecRun
from app.models.gate_events import GateEvent
from app.models.hook_runs import HookRun
from app.models.run_capabilities import RunCapabilities
from app.models.run_event import RunEvent
from app.models.run_provenance_audit import (
    RunProvenanceAudit,
    lookup_idempotent_restore,
)
from app.models.run_finalization import RunFinalization
from app.models.subagent_run import SubagentRun
from app.models.user import User
from app.models.validation_results import ValidationResult
from app.models.wave_run import WaveRun
from app.models.workflow import WorkflowRun
from app.models.workflow_clarification import WorkflowClarification

router = APIRouter(prefix="/api/runs", tags=["runs"])
logger = logging.getLogger("app.api.runs")


# --- Request/Response Schemas ---


class ExportPptxRequest(BaseModel):
    """Request body for POST /api/runs/export-pptx.

    All four fields are optional, but at least one of ``workflow_id``,
    ``js_code`` or ``html`` MUST be present (enforced inside the handler
    rather than via Pydantic, since the field that matters depends on the
    extraction strategy chosen).

    Caps exist to bound subprocess input and prevent trivial DoS via huge
    payloads — they are intentionally generous (a real PptxGenJS function
    is rarely > 100 KB) and not a substitute for the sandboxing work
    tracked separately under the pptx_export hardening item.
    """

    workflow_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="UUID of a WorkflowRun belonging to the caller; agent output is fetched server-side.",
    )
    js_code: Optional[str] = Field(
        default=None,
        max_length=512_000,
        description="Raw PptxGenJS JavaScript (the generatePresentation function body).",
    )
    html: Optional[str] = Field(
        default=None,
        max_length=2_000_000,
        description="An HTML preview containing a generatePresentation() function in a <script> block.",
    )
    title: str = Field(
        default="Presentation",
        max_length=120,
        description="Filename hint for the Content-Disposition response header.",
    )


class WorkflowRunResponse(BaseModel):
    """Workflow run data returned in API responses."""

    id: str
    title: str
    type: str
    status: str
    input: str
    output: Optional[str] = None
    agent_outputs: Optional[str] = None
    agent_count: int
    duration: Optional[float] = None
    error: Optional[str] = None
    token_usage: Optional[str] = None
    # CWF-002 (fix c): the effective model the run used (WorkflowRun.model_id, migration
    # 0014 column — now written by the launch driver). Auto-materialized into BOTH the
    # list (summary) and detail responses by _run_response's model_fields getattr loop.
    model_id: Optional[str] = None
    # UXFIX-02 (22-03 / D-19): the persisted declared/resolved deliverable shape
    # so history-reopen drives the deliverable mimetype from the persisted value
    # (legacy rows NULL → FE deriveDeliverableMimetype heuristic fallback, parity).
    deliverable_mimetype: Optional[str] = None
    deliverable_filename: Optional[str] = None
    # Workstream A (POR §4.2 / D-06,D-07): revision-family read surface.
    #   * parent_run_id — the verbatim self-FK column (resolved by from_attributes);
    #     None for a standalone run, else the id of the run this one revises.
    #   * root_run_id — server-computed (NOT an ORM column): the last OWNED
    #     ancestor reached by walking parent_run_id up the chain. A standalone run
    #     roots to its own id; a foreign/missing parent terminates the walk so no
    #     foreign run is ever named. Required (contract-strong) — injected by
    #     _run_response since from_attributes cannot supply a computed field.
    parent_run_id: Optional[str] = None
    root_run_id: str
    # KAN-130: expose the chaining indicator so the frontend can show "(Chained)"
    # in the Jump Back In section. source_run_id is set when a run was launched
    # by chaining from a prior run's output. The column already exists (migration
    # 0014 forward field) — no migration needed; from_attributes resolves it.
    source_run_id: Optional[str] = None
    # R-20 (spec 014 / T41): the instance_id of the conditional-gate step that
    # diverted this run to another workflow, if any. None for a non-diverted run.
    diverted_at_step_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    # ── Task 9.3: chain-source + finalization projection (sandbox-git-versioning-v2) ──
    #
    # All fields are Optional with default None so existing clients see no change.
    #
    # chain_source — present only when the caller owns the source run.  A
    #   cross-owner source (or no source) → None.  Never partially disclosed.
    #   Shape: {id, short_id, workflow_id, published_status, visible_tag | None}
    chain_source: Optional[dict] = None
    # chain_context_installed — from run_finalizations.chain_context_installed
    #   directly, NOT through FinalizationRecord, so a run that never reaches the
    #   finalizer still reports whether it received a chain payload (written at
    #   install time by mark_chain_context_installed before agent 1).
    chain_context_installed: Optional[bool] = None
    # payload_chainable / non_chainable_reason — mirrored from WorkflowRun columns
    #   (migration 0044, written in the same transaction as published_status).
    payload_chainable: Optional[bool] = None
    non_chainable_reason: Optional[str] = None
    # chain_unavailable_reason — the bounded reason code from run_provenance_audits
    #   for a chain_context_unavailable event.  None when chain context was
    #   successfully installed or not applicable.
    chain_unavailable_reason: Optional[str] = None
    # finalization_reason — the degraded_reason from run_finalizations when the
    #   run finished degraded; None for completed/cancelled/failed/running.
    finalization_reason: Optional[str] = None

    model_config = {"from_attributes": True}

    # KAN-113: SQLite returns timezone-naive datetimes even though we write UTC.
    # Pydantic v2 serialises a naive datetime without a +00:00 suffix, so
    # JavaScript Date.parse() treats it as local time → wrong "Nh ago" display.
    # Promote to UTC-aware before ISO-formatting (matches _coerce_to_aware_utc
    # in dependencies.py — same pattern, applied at the serialisation boundary).
    @field_serializer("created_at", "completed_at")
    def _serialize_dt(self, v: Optional[datetime]) -> Optional[str]:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()


def _iso_utc(v: Optional[datetime]) -> Optional[str]:
    """UTC-promote then ISO-format a stored datetime (KAN-113).

    The free-function twin of the response models' ``_serialize_dt`` field
    serializer, for plain-dict projections that have no Pydantic model to hang one
    on. Same rule: a naive stamp is ``Date.parse``'d as LOCAL time in the browser.
    """
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


class WorkflowRunListResponse(BaseModel):
    """Slim run data for the history list endpoint (KAN-131).

    Excludes the heavy ``output``, ``agent_outputs``, and ``input`` fields that
    are only needed when a run is opened. Omitting them reduces the list payload
    from ~2.8MB to <50KB for 50 rows — a ~50x reduction.
    The full ``WorkflowRunResponse`` is returned by ``GET /api/runs/{id}``.
    """

    id: str
    title: str
    type: str
    status: str
    agent_count: int
    duration: Optional[float] = None
    error: Optional[str] = None
    token_usage: Optional[str] = None
    deliverable_mimetype: Optional[str] = None
    deliverable_filename: Optional[str] = None
    parent_run_id: Optional[str] = None
    root_run_id: str
    # R-20 (spec 014 / T41): see WorkflowRunResponse — same field, same meaning.
    diverted_at_step_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "completed_at")
    def _serialize_dt(self, v: Optional[datetime]) -> Optional[str]:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()


# ---------------------------------------------------------------------------
# Workstream A — revision-family read helpers (POR §4.2 + §4.3, app-layer only).
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Sentinel for an ancestor id that is missing OR owned by another user — the
# owned walk terminates here (root = the last OWNED ancestor, POR §3.2). Kept
# distinct from None (which means "no parent") so the family walk never leaks a
# foreign run into a root/family response (threat T-A-03).
# ---------------------------------------------------------------------------
_FOREIGN_ANCESTOR = object()


def _compute_root_ids(db: Session, user_id: str, runs: list) -> dict[str, str]:
    """Return ``{run_id: root_run_id}`` for every run in ``runs`` via a memoized
    in-Python owned-ancestor walk with batched parent fetches.

    Chosen over a recursive CTE for SQLite (tests) + Postgres (prod) portability
    — the POR grants implementation freedom here. ``root_run_id`` is the last
    OWNED ancestor reachable by following ``parent_run_id`` up the chain: a NULL
    parent, a missing parent, or a parent owned by another user all terminate
    the walk (POR §3.2), so a foreign link never leaks foreign run metadata.

    Latency invariant: a page whose rows ALL have NULL parent_run_id issues ZERO
    additional queries (the frontier is empty on the first pass); otherwise one
    extra batched query per chain-depth level. Cycle guard: each per-run walk
    carries a visited set so a corrupt cyclic chain terminates at the revisited
    node instead of looping forever (threat T-A-04).
    """
    # parent_of[id] -> parent id (str), None (no parent), or _FOREIGN_ANCESTOR
    # (missing / not owned → walk terminator). Seed from the page rows.
    parent_of: dict[str, object] = {r.id: r.parent_run_id for r in runs}

    # Iteratively resolve unknown ancestors, OWNED-only, one depth-level per pass.
    while True:
        frontier = {
            pid
            for pid in parent_of.values()
            if isinstance(pid, str) and pid not in parent_of
        }
        if not frontier:
            break
        rows = (
            db.query(WorkflowRun.id, WorkflowRun.parent_run_id)
            .filter(
                WorkflowRun.id.in_(frontier),
                WorkflowRun.user_id == user_id,
            )
            .all()
        )
        fetched = {rid: ppid for rid, ppid in rows}
        for pid in frontier:
            # A frontier id the OWNED fetch did not return is missing or owned by
            # another user → mark as the walk terminator (never re-queried).
            parent_of[pid] = fetched.get(pid, _FOREIGN_ANCESTOR)

    # Resolve each run's root by walking parent_of, memoizing across the page.
    root_cache: dict[str, str] = {}

    def _root_of(start: str) -> str:
        chain: list[str] = []
        cur = start
        visited: set[str] = set()
        while True:
            if cur in root_cache:
                resolved = root_cache[cur]
                break
            if cur in visited:
                # Cycle — terminate at the current node (its own root).
                resolved = cur
                break
            visited.add(cur)
            parent = parent_of.get(cur, _FOREIGN_ANCESTOR)
            # Step ONLY into an OWNED parent. A None parent (no parent), the
            # foreign sentinel, or a parent id that itself resolves to a
            # foreign/missing node all terminate the walk — cur is the last owned
            # ancestor, i.e. the root. (parent_of[x] is a real str/None iff x is
            # owned; it is the sentinel iff x is foreign/missing.)
            if (
                not isinstance(parent, str)
                or parent_of.get(parent, _FOREIGN_ANCESTOR) is _FOREIGN_ANCESTOR
            ):
                resolved = cur
                break
            chain.append(cur)
            cur = parent
        root_cache[cur] = resolved
        for node in chain:
            root_cache[node] = resolved
        return resolved

    return {r.id: _root_of(r.id) for r in runs}


def _build_chain_projection(
    db: Session,
    run: WorkflowRun,
    user_id: str,
) -> dict:
    """Build the chain-source + finalization projection for a single run.

    Returns a dict of the new Optional fields (all default None on any error).
    Ownership-scoped: a cross-owner source projects as chain_source=None.

    Called only from _run_response (detail endpoint) — not from the list or
    family endpoints, which use a slimmer projection.
    """
    result: dict = {
        # source_run_id is gated — only disclosed when the caller owns the source.
        # Set to None here; overwritten to src.id below when ownership is confirmed.
        "source_run_id": None,
        "chain_source": None,
        "chain_context_installed": None,
        "payload_chainable": None,
        "non_chainable_reason": None,
        "chain_unavailable_reason": None,
        "finalization_reason": None,
    }

    # ── payload_chainable / non_chainable_reason — mirrored on WorkflowRun ────
    # Read directly from the ORM column (already loaded on the run object).
    result["payload_chainable"] = getattr(run, "payload_chainable", None)
    result["non_chainable_reason"] = getattr(run, "non_chainable_reason", None)

    # ── chain_context_installed — from run_finalizations (NOT FinalizationRecord)
    # so a run that never fully finalizes still reports the install state written
    # by mark_chain_context_installed before agent 1 (Requirement 21 AC 8).
    try:
        fin_row = (
            db.query(
                RunFinalization.chain_context_installed,
                RunFinalization.non_chainable_reason,
                RunFinalization.payload_chainable,
            )
            .filter(
                RunFinalization.run_id == run.id,
                RunFinalization.owner_id == user_id,
            )
            .first()
        )
        if fin_row is not None:
            result["chain_context_installed"] = fin_row.chain_context_installed
            # Prefer the finalization row's payload columns when present —
            # they are the canonical durable record; WorkflowRun columns are
            # the mirrored convenience copy.
            if fin_row.payload_chainable is not None:
                result["payload_chainable"] = fin_row.payload_chainable
            if fin_row.non_chainable_reason is not None:
                result["non_chainable_reason"] = fin_row.non_chainable_reason
    except Exception:  # noqa: BLE001 — projection failure must never 500 the endpoint
        pass

    # ── finalization_reason — degraded_reason from run_finalizations ─────────
    try:
        deg_row = (
            db.query(RunFinalization.non_chainable_reason)
            .filter(
                RunFinalization.run_id == run.id,
                RunFinalization.owner_id == user_id,
            )
            .first()
        )
        # The finalization_reason field reports why a run degraded.  The
        # non_chainable_reason is the closest column in the current schema.
        # When a dedicated degraded_reason column is added it should be read
        # here instead; for now surface non_chainable_reason for degraded runs.
        if deg_row is not None and getattr(run, "status", None) == "degraded":
            result["finalization_reason"] = deg_row.non_chainable_reason
    except Exception:  # noqa: BLE001
        pass

    # ── chain_unavailable_reason — from run_provenance_audits ─────────────────
    try:
        unavail_row = (
            db.query(RunProvenanceAudit.outcome)
            .filter(
                RunProvenanceAudit.run_id == run.id,
                RunProvenanceAudit.owner_id == user_id,
                RunProvenanceAudit.operation == "chain_context_unavailable",
            )
            .order_by(RunProvenanceAudit.created_at.desc())
            .first()
        )
        if unavail_row is not None:
            result["chain_unavailable_reason"] = unavail_row.outcome
    except Exception:  # noqa: BLE001
        pass

    # ── chain_source — owner-scoped source run projection ────────────────────
    # Only present when source_run_id is set AND the caller owns that source run.
    # A cross-owner source → absent (never partially disclosed).
    source_run_id = getattr(run, "source_run_id", None)
    if source_run_id:
        try:
            src = (
                db.query(
                    WorkflowRun.id,
                    WorkflowRun.type,
                    WorkflowRun.status,
                    WorkflowRun.git_tag,
                )
                .filter(
                    WorkflowRun.id == source_run_id,
                    # Ownership predicate — cross-owner source returns None (IDOR
                    # protection; Requirement 21 AC 4).
                    WorkflowRun.user_id == user_id,
                    WorkflowRun.user_id.isnot(None),
                )
                .first()
            )
            if src is not None:
                # short_id is the first 8 chars, matching the frontend convention.
                result["chain_source"] = {
                    "id": src.id,
                    "short_id": src.id[:8],
                    "workflow_id": src.type,
                    "published_status": src.status,
                    "visible_tag": src.git_tag,  # None for untagged runs
                }
                # source_run_id is safe to disclose — caller owns both runs.
                result["source_run_id"] = src.id
        except Exception:  # noqa: BLE001
            pass

    return result


def _build_finalization_projection(
    db: Session,
    run_id: str,
    user_id: str,
) -> dict:
    """Slim projection used by family members — chain_context_installed only.

    Cheaper than _build_chain_projection (single query, no source lookup).
    Returns a dict with chain_context_installed, payload_chainable,
    non_chainable_reason.
    """
    result: dict = {
        "chain_context_installed": None,
        "payload_chainable": None,
        "non_chainable_reason": None,
    }
    try:
        row = (
            db.query(
                RunFinalization.chain_context_installed,
                RunFinalization.payload_chainable,
                RunFinalization.non_chainable_reason,
            )
            .filter(
                RunFinalization.run_id == run_id,
                RunFinalization.owner_id == user_id,
            )
            .first()
        )
        if row is not None:
            result["chain_context_installed"] = row.chain_context_installed
            result["payload_chainable"] = row.payload_chainable
            result["non_chainable_reason"] = row.non_chainable_reason
    except Exception:  # noqa: BLE001
        pass
    return result


def _run_response(
    run, root_id: str, *, db: Session | None = None, user_id: str | None = None
) -> "WorkflowRunResponse":
    """Build a ``WorkflowRunResponse`` injecting the server-computed root_run_id.

    ``from_attributes`` cannot supply ``root_run_id`` (it is not an ORM column),
    so every OTHER field is materialized from the row by iterating
    ``model_fields`` — which auto-tracks future field additions with no
    hand-maintained list — and ``root_run_id`` is injected explicitly, keeping it
    a required ``str`` (contract-strong).

    When ``db`` and ``user_id`` are supplied the chain-source + finalization
    projection is populated (task 9.3).  The detail endpoint (get_run) always
    supplies both; other callers may omit them and get None for the new fields.
    """
    # The model_fields loop covers all scalar ORM-backed fields.  The new
    # Optional fields (chain_source, chain_context_installed, …) are NOT ORM
    # columns so getattr(run, name) would return AttributeError / None — they
    # are excluded from the loop and injected explicitly below.
    _COMPUTED_FIELDS = {
        "root_run_id",
        # source_run_id is the raw ORM column but must be gated: a cross-owner
        # source run id must never leak to the caller (IDOR protection,
        # Requirement 21 AC 4).  It is therefore derived from the chain_source
        # projection rather than copied verbatim from the ORM row.
        "source_run_id",
        "chain_source",
        "chain_context_installed",
        "payload_chainable",
        "non_chainable_reason",
        "chain_unavailable_reason",
        "finalization_reason",
    }
    kwargs = {
        name: getattr(run, name, None)
        for name in WorkflowRunResponse.model_fields
        if name not in _COMPUTED_FIELDS
    }
    kwargs["root_run_id"] = root_id

    # Populate chain/finalization fields when db is available.
    if db is not None and user_id is not None:
        chain_proj = _build_chain_projection(db, run, user_id)
        kwargs.update(chain_proj)
        # IDOR guard (Requirement 21 AC 4): if the ownership-scoped projection
        # did not populate chain_source (cross-owner or missing source), also
        # null out source_run_id so the raw ORM column value is never disclosed.
        # _build_chain_projection already returns source_run_id=None in this
        # case, but this explicit post-step makes the invariant impossible to
        # violate by a future change to the projection function.
        if not kwargs.get("chain_source"):
            kwargs["source_run_id"] = None
    else:
        for f in _COMPUTED_FIELDS - {"root_run_id"}:
            kwargs[f] = None

    return WorkflowRunResponse(**kwargs)


def _run_list_response(run, root_id: str) -> WorkflowRunListResponse:
    """Build a slim ``WorkflowRunListResponse`` for the history list (KAN-131).

    Identical pattern to ``_run_response`` but uses the slim schema that
    excludes ``output``, ``agent_outputs``, and ``input`` — reducing the list
    payload from ~2.8MB to <50KB for 50 rows.
    """
    kwargs = {
        name: getattr(run, name)
        for name in WorkflowRunListResponse.model_fields
        if name != "root_run_id"
    }
    kwargs["root_run_id"] = root_id
    return WorkflowRunListResponse(**kwargs)


# --- Endpoints ---


@router.get("", response_model=list[WorkflowRunListResponse])
def list_runs(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    type: Optional[str] = None,
    status_filter: Optional[str] = None,
):
    """List workflow runs for the authenticated user (slim — no output/agent_outputs).

    Ordered by created_at descending (most recent first).
    Returns ``X-Total-Count`` header with the total matching run count.
    Heavy fields (output, agent_outputs, input) are excluded — fetch the full
    run via ``GET /api/runs/{id}`` when a specific run is opened.
    """
    # KAN-131: only load the columns the list schema needs — skip the heavy
    # Text columns (output, agent_outputs, input) entirely so SQLite/Postgres
    # never reads them off disk. This is the dominant performance win.
    _LIST_COLS = [
        WorkflowRun.id,
        WorkflowRun.title,
        WorkflowRun.type,
        WorkflowRun.status,
        WorkflowRun.agent_count,
        WorkflowRun.duration,
        WorkflowRun.error,
        WorkflowRun.token_usage,
        WorkflowRun.deliverable_mimetype,
        WorkflowRun.deliverable_filename,
        WorkflowRun.parent_run_id,
        WorkflowRun.diverted_at_step_id,
        WorkflowRun.user_id,
        WorkflowRun.created_at,
        WorkflowRun.completed_at,
    ]
    query = db.query(*_LIST_COLS).filter(WorkflowRun.user_id == current_user.id)

    if type:
        query = query.filter(WorkflowRun.type == type)
    if status_filter:
        query = query.filter(WorkflowRun.status == status_filter)

    # Count before applying limit/offset so the total reflects filters.
    # Uses the same WHERE clause as the page query — no extra round trip on a
    # cold query; SQLite/Postgres both plan it as a single index scan.
    total = query.count()
    response.headers["X-Total-Count"] = str(total)

    runs = (
        query.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit).all()
    )
    # Compute the owned root for the whole page once (batched ancestor walk); a
    # NULL-parent page issues zero extra queries (POR §4.2 latency invariant).
    # Note: column-select rows support attribute access by column name, so
    # _compute_root_ids and _run_list_response work identically to ORM objects.
    roots = _compute_root_ids(db, current_user.id, runs)
    return [_run_list_response(r, roots[r.id]) for r in runs]


@router.post("/export-pptx")
def export_pptx(
    request: ExportPptxRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a .pptx file from Agent 3's PptxGenJS code.

    Tries to get the code from:
    1. workflow_id → agent_outputs (the ppt-code-generator agent's output)
    2. js_code field directly
    3. html field → extract generatePresentation() from HTML

    Returns: .pptx binary download.
    """
    from fastapi.responses import Response
    from app.services.pptx_export import generate_pptx_from_code

    js_code = request.js_code or ""
    html_content = request.html or ""
    workflow_id = request.workflow_id or ""
    title = request.title

    # The set of agent IDs whose `output` is canonical PptxGenJS source. The
    # previous substring scan (`"code" in aid or "generator" in aid or
    # "ppt-code" in aid`) had four false positives (`app-code-generator`,
    # `barcode-extractor`, `prototype-generator`, `code-reviewer`) — a user
    # who had run a non-PPT pipeline in the same workflow_id could silently
    # download a deck built from the wrong agent's output. Exact match
    # against the registered IDs eliminates that class of mistake.
    _PPT_CODE_AGENT_IDS = {"ppt-code-generator"}

    # Strategy 1: Get Agent 3 output from workflow DB
    if not js_code and workflow_id:
        wr = (
            db.query(WorkflowRun)
            .filter(
                WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id
            )
            .first()
        )
        if wr and wr.agent_outputs:
            try:
                outputs = json.loads(wr.agent_outputs)
                for agent in outputs:
                    if agent.get("agent_id", "") in _PPT_CODE_AGENT_IDS:
                        js_code = agent.get("output", "")
                        break
            except Exception:
                pass

    # Strategy 2: Extract from HTML
    if not js_code and html_content:
        # Find generatePresentation function in script tags
        scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script>", html_content)
        for script in scripts:
            m = re.search(
                r"((?:async\s+)?function\s+generatePresentation\s*\([^)]*\)\s*\{)",
                script,
            )
            if m:
                start = m.start()
                depth = 0
                end = start
                for i in range(m.end() - 1, len(script)):
                    if script[i] == "{":
                        depth += 1
                    elif script[i] == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end > start:
                    js_code = script[start:end]
                    break

        # Also try full HTML search
        if not js_code:
            m = re.search(
                r"((?:async\s+)?function\s+generatePresentation\s*\([^)]*\)\s*\{)",
                html_content,
            )
            if m:
                start = m.start()
                depth = 0
                end = start
                for i in range(start, len(html_content)):
                    if html_content[i] == "{":
                        depth += 1
                    elif html_content[i] == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end > start:
                    js_code = html_content[start:end]

    if not js_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not find PptxGenJS code. Try re-running the pipeline.",
        )

    try:
        pptx_bytes = generate_pptx_from_code(js_code, title=title)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PPTX: {str(e)[:200]}",
        )

    # Sanitize the filename to ASCII alphanumerics + `_-.` only. The previous
    # `title.replace(' ', '_')[:40]` did NOT strip CR/LF/control chars or
    # double-quote, which let a maliciously-crafted title smuggle additional
    # headers (HTTP response splitting). The Pydantic max_length on `title`
    # bounds the size; this re.sub bounds the alphabet.
    safe_title = re.sub(r"[^A-Za-z0-9._-]", "_", title)[:40] or "Presentation"
    filename = f"{safe_title}.pptx"
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{workflow_id}", response_model=WorkflowRunResponse)
def get_run(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific workflow run by ID.

    Returns 404 if the workflow does not exist or does not belong to the user.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    roots = _compute_root_ids(db, current_user.id, [workflow_run])
    return _run_response(
        workflow_run, roots[workflow_run.id], db=db, user_id=current_user.id
    )


@router.delete(
    "/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_run(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a workflow run and all its child rows.

    Cleans up all 9 child tables that FK into workflow_runs before deleting
    the parent row — required because PRAGMA foreign_keys=ON (database.py)
    enforces FK integrity and none of the child tables declare ON DELETE CASCADE.

    Also handles the self-referential parent_run_id FK: child WorkflowRun rows
    (revision chains) have their parent_run_id nulled before the parent is deleted.

    Returns 204 No Content on success.
    Returns 404 if the workflow does not exist or does not belong to the user.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    # ── Delete child rows in dependency order before removing the parent ──────
    # All 9 audit tables FK into workflow_runs.id with no ON DELETE CASCADE.
    # Column names differ per table — confirmed from each model file.
    db.query(RunEvent).filter(RunEvent.run_id == workflow_id).delete(
        synchronize_session=False
    )
    db.query(ArtifactRef).filter(ArtifactRef.run_id == workflow_id).delete(
        synchronize_session=False
    )
    db.query(WorkflowClarification).filter(
        WorkflowClarification.workflow_run_id == workflow_id
    ).delete(synchronize_session=False)
    db.query(GateEvent).filter(GateEvent.run_id == workflow_id).delete(
        synchronize_session=False
    )
    db.query(HookRun).filter(HookRun.run_id == workflow_id).delete(
        synchronize_session=False
    )
    db.query(ExecRun).filter(ExecRun.run_id == workflow_id).delete(
        synchronize_session=False
    )
    db.query(RunCapabilities).filter(RunCapabilities.run_id == workflow_id).delete(
        synchronize_session=False
    )
    db.query(ValidationResult).filter(ValidationResult.run_id == workflow_id).delete(
        synchronize_session=False
    )
    db.query(SubagentRun).filter(SubagentRun.parent_run_id == workflow_id).delete(
        synchronize_session=False
    )
    db.query(WaveRun).filter(WaveRun.run_id == workflow_id).delete(
        synchronize_session=False
    )

    # ── Self-referential FK: null out parent_run_id on any child revision runs ─
    # Deleting the parent while revision children point to it via parent_run_id
    # would also violate the self-referential FK. Null the reference instead of
    # cascade-deleting the child runs (preserves the revision run history).
    db.query(WorkflowRun).filter(WorkflowRun.parent_run_id == workflow_id).update(
        {WorkflowRun.parent_run_id: None}, synchronize_session=False
    )

    db.delete(workflow_run)
    db.commit()

    return None


# ---------------------------------------------------------------------------
# Chain context endpoint — extracts structured text from a completed run
# for use as context in the next chained pipeline.
# ---------------------------------------------------------------------------


class ChainContextResponse(BaseModel):
    """Structured context extracted from a completed workflow run."""

    workflow_id: str
    pipeline_type: str
    title: str
    brief: str  # Original user input
    structured_summary: str  # Extracted text content (not HTML)
    agent_summaries: list[dict]  # Per-agent key outputs
    context_block: str  # Ready-to-inject context string


def _extract_chain_context(workflow_run: WorkflowRun) -> ChainContextResponse:
    """Extract structured, chain-ready context from a completed WorkflowRun.

    For each pipeline type, extracts the most useful text content:
    - od_ppt / ppt: extracts the slide spec JSON from the brief-analyst output
    - user_stories: extracts the backlog text from the compiler output
    - prototype: extracts the component spec from the analyst
    - app_builder: extracts the architecture summary from the system-design agent
    - mulesoft / dotnet: extracts the migration plan from the inventory agent
    - custom: extracts the final output text
    """

    pipeline_type = workflow_run.type
    brief = workflow_run.input or ""
    title = workflow_run.title or ""

    # KAN-116 (Bug 3): strip === ... === marker text from title and brief before
    # embedding them in the context_block. If a prior run had polluted title/input
    # (stored before FIX-087), the nested markers would break parseRunInput on the FE.
    # Generic regex — no pipeline-name literals (SC-001/INV-1).
    import re as _re_ctx

    _marker_re = _re_ctx.compile(r"===.*?===", _re_ctx.DOTALL)

    def _clean_for_context(text: str) -> str:
        """Strip === ... === blocks and return the first clean line."""
        if "===" not in text:
            return text
        # For title: extract revision instruction or brief via the same logic as _clean_run_title
        rev_match = _re_ctx.search(
            r"===\s*REVISION REQUEST\s*===\s*(.*?)\s*(?:===|$)", text, _re_ctx.DOTALL
        )
        if rev_match:
            return rev_match.group(1).split("\n")[0].strip()
        # Strip all === ... === blocks and return first non-empty line
        stripped = _marker_re.sub("", text).strip()
        return (
            stripped.split("\n")[0].strip() if stripped else text.split("\n")[0].strip()
        )

    title = _clean_for_context(title)
    # For brief, just take the first clean line before any context block
    brief_first_line = brief.split("\n")[0].strip()
    if "===" not in brief_first_line:
        brief = brief_first_line  # use clean first line as the brief preview
    else:
        brief = _clean_for_context(brief)

    # Parse agent_outputs JSON array
    agent_outputs: list[dict] = []
    if workflow_run.agent_outputs:
        try:
            agent_outputs = json.loads(workflow_run.agent_outputs)
        except Exception:
            pass

    # ── Pipeline-specific extraction ──────────────────────────────────────
    agent_summaries: list[dict] = []
    structured_summary = ""

    # Helper: find agent output by ID
    def get_agent_output(agent_id: str) -> str:
        for a in agent_outputs:
            if a.get("agent_id") == agent_id:
                return a.get("output", "")
        return ""

    # Helper: extract <spec>...</spec> JSON from text
    def extract_spec(text: str) -> str:
        m = re.search(r"<spec>([\s\S]*?)</spec>", text)
        if m:
            try:
                spec = json.loads(m.group(1))
                # Format as readable text
                lines = [f"Title: {spec.get('title', '')}"]
                if spec.get("audience"):
                    lines.append(f"Audience: {spec['audience']}")
                if spec.get("tone"):
                    lines.append(f"Tone: {spec['tone']}")
                if spec.get("theme_choice"):
                    lines.append(f"Theme: {spec['theme_choice']}")
                slides = spec.get("slides", [])
                if slides:
                    lines.append(f"\nSlide Plan ({len(slides)} slides):")
                    for s in slides:
                        lines.append(
                            f"  Slide {s.get('index', '?')}: {s.get('title', '')} [{s.get('type', '')}]"
                        )
                        if s.get("content"):
                            lines.append(f"    Content: {str(s['content'])[:200]}")
                return "\n".join(lines)
            except Exception:
                return m.group(1)[:2000]
        return ""

    if pipeline_type in ("ppt", "ppt_revision"):
        # Extract slide spec from brief-analyst
        analyst_output = get_agent_output("ppt-brief-analyst")
        spec_text = extract_spec(analyst_output)
        if spec_text:
            structured_summary = f"Presentation Slide Plan:\n{spec_text}"
            agent_summaries.append(
                {"agent": "Presentation Strategist", "summary": spec_text[:500]}
            )
        elif analyst_output:
            structured_summary = analyst_output[:3000]
            agent_summaries.append(
                {"agent": "Presentation Strategist", "summary": analyst_output[:500]}
            )

    elif pipeline_type in ("user_stories", "user_stories_revision"):
        # Extract from backlog compiler (last agent)
        compiler_output = get_agent_output("backlog-compiler")
        if not compiler_output:
            # Fall back to final output
            compiler_output = workflow_run.output or ""
        if compiler_output:
            structured_summary = compiler_output[:4000]
            agent_summaries.append(
                {"agent": "Backlog Compiler", "summary": compiler_output[:500]}
            )

    elif pipeline_type in (
        "prototype",
        "prototype_revision",
        "prototype_large_revision",  # tiered revision — no spec-writer output
        "prototype_feature_revision",  # tiered revision — no spec-writer output
    ):
        # The spec writer (first agent) emits a Markdown spec wrapped in
        # <spec>...</spec>. Read THAT — not the HTML deliverable, and not the
        # retired "requirements-analyst" agent which isn't in this pipeline
        # (the old lookup always returned "" → empty chain context).
        # For prototype_revision, the revision agent doesn't have a spec writer —
        # use the revision instruction extracted from the run's input instead.
        spec_output = get_agent_output("prototype-specify") or get_agent_output(
            "prototype-plan"
        )
        if spec_output:
            m = re.search(r"<spec>([\s\S]*?)</spec>", spec_output)
            spec_text = m.group(1).strip() if m else spec_output
            structured_summary = f"Prototype Specification:\n{spec_text[:3500]}"
            agent_summaries.append({"agent": "Spec Writer", "summary": spec_text[:500]})
        elif pipeline_type in (
            "prototype_revision",
            "prototype_large_revision",
            "prototype_feature_revision",
        ):
            # Tiered revision runs have no spec-writer output — extract the
            # revision instruction from the run's input as a fallback summary.
            # NOTE: get_chain_context should have walked up to the root prototype
            # run before calling this; this branch only fires if the walk failed
            # (e.g. a direct call with a revision run_id and no root found).
            import re as _re_local

            rev_match = _re_local.search(
                r"===\s*REVISION REQUEST\s*===\s*\n(.*?)\n===\s*END REQUEST\s*===",
                workflow_run.input or "",
                _re_local.DOTALL,
            )
            if rev_match:
                instruction = rev_match.group(1).strip()
                structured_summary = f"Prototype Revision: {instruction}"
                agent_summaries.append(
                    {"agent": "Revision Specialist", "summary": instruction[:500]}
                )

    elif pipeline_type in ("app_builder", "app_builder_revision"):
        # Extract from system design agent
        design_output = get_agent_output("app-system-design")
        stories_output = get_agent_output("app-user-stories")
        parts = []
        if stories_output:
            parts.append(f"User Stories:\n{stories_output[:1500]}")
            agent_summaries.append(
                {"agent": "App User Stories", "summary": stories_output[:300]}
            )
        if design_output:
            parts.append(f"System Design:\n{design_output[:1500]}")
            agent_summaries.append(
                {"agent": "System Design", "summary": design_output[:300]}
            )
        structured_summary = "\n\n".join(parts)

    elif pipeline_type in ("mulesoft_to_springboot",):
        inventory_output = get_agent_output("mulesoft-inventory")
        decomp_output = get_agent_output("mulesoft-decomposition")
        parts = []
        if inventory_output:
            parts.append(f"Mulesoft Inventory:\n{inventory_output[:2000]}")
        if decomp_output:
            parts.append(f"Migration Decomposition:\n{decomp_output[:2000]}")
        structured_summary = "\n\n".join(parts)

    elif pipeline_type in ("dotnet_to_azure",):
        inventory_output = get_agent_output("dotnet-inventory")
        mapping_output = get_agent_output("dotnet-azure-target-mapping")
        parts = []
        if inventory_output:
            parts.append(f".NET Inventory:\n{inventory_output[:2000]}")
        if mapping_output:
            parts.append(f"Azure Target Mapping:\n{mapping_output[:2000]}")
        structured_summary = "\n\n".join(parts)

    else:
        # Generic: use final output
        structured_summary = (workflow_run.output or "")[:3000]

    # Fallback: if no structured summary, use the final output
    if not structured_summary and workflow_run.output:
        output = workflow_run.output
        # Skip HTML artifacts
        if not re.search(r"<!DOCTYPE|<html", output, re.IGNORECASE):
            structured_summary = output[:3000]

    # Build the ready-to-inject context block
    context_block = ""
    if structured_summary:
        context_block = (
            f"=== CONTEXT FROM PREVIOUS PIPELINE ({pipeline_type}) ===\n"
            f"Title: {title}\n"
            f"Original Brief: {brief[:200]}\n\n"
            f"{structured_summary}\n"
            f"=== END PREVIOUS CONTEXT ==="
        )

    return ChainContextResponse(
        workflow_id=str(workflow_run.id),
        pipeline_type=pipeline_type,
        title=title,
        brief=brief,
        structured_summary=structured_summary,
        agent_summaries=agent_summaries,
        context_block=context_block,
    )


@router.get("/{workflow_id}/chain-context", response_model=ChainContextResponse)
def get_chain_context(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Extract structured chain context from a completed workflow run.

    Returns the key text content from the run's agent outputs, formatted
    as a ready-to-inject context block for the next chained pipeline.
    Only returns context for completed runs owned by the current user.

    For *_revision pipeline types (od_ppt_revision, ppt_revision, etc.) the
    revision run itself has no brief-analyst / spec-writer output — those agents
    run only on the original pipeline.  We therefore walk up one level to the
    parent run and extract its context instead, preserving the slide-plan /
    spec structure the chained pipeline needs.  The revision instruction from
    the *_revision run's input is appended as additional context so the
    downstream pipeline knows what changed.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.id == workflow_id,
            WorkflowRun.user_id == current_user.id,
        )
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    # KAN-137: for *_revision pipeline types, extract context from the ROOT
    # non-revision ancestor (the original pipeline). A revision of a revision
    # (v1 → v2 → v3) has a parent that is itself a *_revision run — walk up
    # the chain until we reach a non-revision base run. Each revision run in
    # the chain has no brief-analyst / spec-writer output, so only the root
    # has the structural context the chained pipeline needs.
    # Generic suffix check (SC-001/INV-1 — no pipeline-name literals).
    source_run = workflow_run
    if workflow_run.type.endswith("_revision") and workflow_run.parent_run_id:
        # Walk up the revision chain to find the root non-revision ancestor.
        # Cap at 20 hops to prevent an infinite loop on corrupted data.
        candidate = workflow_run
        for _ in range(20):
            if not candidate.type.endswith("_revision") or not candidate.parent_run_id:
                break
            parent_run = (
                db.query(WorkflowRun)
                .filter(
                    WorkflowRun.id == candidate.parent_run_id,
                    WorkflowRun.user_id == current_user.id,
                )
                .first()
            )
            if not parent_run:
                break
            candidate = parent_run
        if candidate is not workflow_run:
            source_run = candidate

    ctx = _extract_chain_context(source_run)

    return ctx


# ---------------------------------------------------------------------------
# Phase 5 — typed-artifact / durable-replay read surface (API-04, API-05).
#
# Both endpoints route every read through the SINGLE default-deny ``ScopedStore``
# helper (``agents/authz.py``, §19) — the engine and the API share one enforced
# read path. A cross-owner / missing run resolves to ``None`` at the helper and
# is surfaced as 404 here (never 403 — no existence leak; the runs.py:14-17 IDOR
# precedent, D-08). These handlers are ``async def`` because the ``ScopedStore``
# methods are coroutines (D-08); they accept the injected request ``Session`` via
# ``Depends(get_db)`` so the helper reuses the one acquisition path.
# ---------------------------------------------------------------------------


def _build_lineage_tree(refs: list, *, include_content: bool) -> list[dict]:
    """Assemble the nested lineage TREE from a flat list of scoped ArtifactRef
    rows (D-10). Roots = refs with neither ``derived_from`` nor any in-set
    ``parents``; each node carries the typed ref fields + ``children: []`` built
    by walking ``parents``/``derived_from``. Cycles / dangling parent ids are
    tolerated (an unreachable ref still surfaces as a root so nothing is lost).
    Inline ``content`` is EXCLUDED unless ``include_content`` (D-10 — reduces
    incidental exposure of large artifact bodies, T-5-CONTENT).
    """
    ids = {r.id for r in refs}

    def _node(r) -> dict:
        node = {
            "id": r.id,
            "kind": r.kind,
            "producer_step": r.producer_step,
            "producer_agent": r.producer_agent,
            "task_id": r.task_id,
            "content_hash": r.content_hash,
            "version": r.version,
            "visibility": r.visibility,
            "retention": r.retention,
            "location": r.location,
            "parents": list(r.parents or []),
            "derived_from": r.derived_from,
            "children": [],
        }
        if include_content:
            node["content"] = r.content
        return node

    nodes = {r.id: _node(r) for r in refs}

    # A ref's parent set = explicit derived_from + the parents[] list, restricted
    # to ids present in THIS run's scoped set (a parent outside the set can't be a
    # tree edge — the child becomes a root instead).
    def _parent_ids(r) -> list[str]:
        pids: list[str] = []
        if r.derived_from and r.derived_from in ids:
            pids.append(r.derived_from)
        for pid in r.parents or []:
            if pid in ids and pid not in pids:
                pids.append(pid)
        return pids

    # WR-04: attach each node under AT MOST ONE parent, and never close a cycle.
    # The previous loop appended the same nodes[r.id] object under every in-set
    # parent, so one dict was shared across multiple children lists — and a
    # mutual-parent pair (A↦B, B↦A both in-set) produced a self-referential
    # structure that FastAPI's JSON encoder rejects with "Circular reference
    # detected". Here each node is attached to exactly one parent (the first in-set
    # parent that does not create a cycle); nodes that cannot be attached surface
    # as roots so nothing is lost.
    #
    # `_attached_parent[child_id] = parent_id` records the single chosen edge so we
    # can walk a candidate parent's ancestry and refuse an edge whose parent is a
    # descendant of the child (that would close a cycle).
    _attached_parent: dict[str, str] = {}

    def _would_cycle(child_id: str, parent_id: str) -> bool:
        # True iff child_id is already an ancestor of parent_id via chosen edges
        # (so attaching child under parent would form a loop). Also covers self.
        cur = parent_id
        seen: set[str] = set()
        while cur is not None and cur not in seen:
            if cur == child_id:
                return True
            seen.add(cur)
            cur = _attached_parent.get(cur)
        return False

    roots: list[dict] = []
    for r in refs:
        pids = _parent_ids(r)
        chosen_parent: Optional[str] = None
        for pid in pids:
            if pid == r.id:
                continue  # self-edge — never attach
            if _would_cycle(r.id, pid):
                continue  # closing this edge would create a cycle — skip it
            chosen_parent = pid
            break
        if chosen_parent is None:
            roots.append(nodes[r.id])
        else:
            nodes[chosen_parent]["children"].append(nodes[r.id])
            _attached_parent[r.id] = chosen_parent
    return roots


@router.get("/{workflow_id}/artifacts")
async def get_run_artifacts(
    workflow_id: str,
    include: Optional[str] = None,
    kind: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the run's typed ``ArtifactRef`` lineage TREE (API-04, D-10).

    Each node carries the ref fields (id/kind/producer step/agent/task/
    content_hash/version/visibility/retention/location/parents/derived_from)
    plus ``children: []`` assembled by walking ``parents``/``derived_from`` from
    the roots. Inline ``content`` is excluded by default; pass
    ``?include=content`` to include it (same-owner only). A cross-owner or
    missing run returns 404 (IDOR → 404, never 403).

    ``?kind=X`` (Workstream A, D-8) filters the refs to exact-kind matches BEFORE
    the tree is assembled, enabling precise fetches like
    ``?kind=clarifications&include=content`` instead of pulling the whole tree.
    Filtering before tree-building means a filtered-out parent drops its edge, so
    a surviving child surfaces as a root (the in-set parent restriction in
    ``_build_lineage_tree`` already guarantees this). An unknown kind yields an
    empty refs list → an empty tree (NOT a 422). With no ``kind`` param the code
    path is byte-identical to the pre-Workstream-A behavior by construction.
    """
    # Resolve the run with the owner filter first (for authed users owner_id ==
    # user_id) to obtain its workspace_id, then construct the ScopedStore so the
    # uniform owner+workspace scope holds for the lineage read.
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    from agents.authz import ScopedStore

    store = ScopedStore(
        owner_id=current_user.id,
        workspace_id=workflow_run.workspace_id,
        session=db,
    )
    # Defense in depth: re-resolve through the single enforced read path so the
    # ownership boundary lives in ONE place (§19); cross-owner → None → 404.
    if await store.get_run(workflow_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    refs = await store.lineage(workflow_id)
    # D-8: exact-kind filter applied to the already owner+workspace-scoped refs
    # BEFORE tree-building. Pure in-Python equality — the value never reaches a
    # query (no LIKE, no SQL; ASVS V5 posture free). Unknown kind → empty list.
    if kind is not None:
        refs = [r for r in refs if r.kind == kind]
    tree = _build_lineage_tree(refs, include_content=(include == "content"))
    return {"workflow_id": workflow_id, "artifacts": tree}


@router.get("/{workflow_id}/events")
async def get_run_events(
    workflow_id: str,
    after: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the run's ``run_events`` rows with ``seq > after`` (API-05, D-11).

    Rows are ordered by ``seq`` ascending, each carrying ``seq`` + a unique
    ``event_id`` (idempotent replay). ``after`` is int-coerced by FastAPI
    (non-int → 422; ASVS V5 — never reaches raw SQL) and flows into the
    parameterized ORM ``.filter()``. A cross-owner or missing run returns 404.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    from agents.authz import ScopedStore

    store = ScopedStore(
        owner_id=current_user.id,
        workspace_id=workflow_run.workspace_id,
        session=db,
    )
    if await store.get_run(workflow_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    rows = await store.read_events(workflow_id, after_seq=after)
    return {
        "workflow_id": workflow_id,
        "after": after,
        "events": [
            {
                "seq": r.seq,
                "event_id": r.event_id,
                "type": r.type,
                "payload_json": r.payload_json,
                # ISS-358: surface the row's own write time. The app-layer chat
                # types (chat_message/chat_reply, run_commands.py) persist no
                # timestamp in their payload, so this column is the ONLY send time
                # a replayed turn has — without it the transcript re-dates every
                # historical message to page-load time. Projected here, at the
                # shared durable reader, so EVERY event type gets it at once
                # rather than per-consumer. UTC-promoted for the same KAN-113
                # reason _serialize_dt is: a naive stamp is Date.parse'd as LOCAL
                # time in the browser, which is the very defect being fixed.
                "created_at": _iso_utc(r.created_at),
            }
            for r in rows
        ],
    }


class FamilyMemberResponse(BaseModel):
    """One run in a revision family (POR §4.3). Carries only the lightweight
    listing fields — NOT the heavy input/output/agent_outputs bodies — since the
    timeline UI renders chips, and a full member fetch goes through get_run."""

    id: str
    type: str
    title: str
    status: str
    revision_index: int  # 1-based chronological position within the family
    parent_run_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    git_tag: Optional[str] = (
        None  # task 6.4 — the git tag created on completed runs (e.g. "v1"); None = not tagged
    )
    # ── Task 9.3: finalization projection for family members ─────────────────
    # All Optional/None so existing clients see no change.
    payload_chainable: Optional[bool] = None
    non_chainable_reason: Optional[str] = None
    chain_context_installed: Optional[bool] = None

    # KAN-113: same UTC-promotion serialiser as WorkflowRunResponse (SQLite naive
    # datetime → JavaScript Date.parse local-time misread → wrong "Nh ago" label).
    @field_serializer("created_at", "completed_at")
    def _serialize_dt(self, v: Optional[datetime]) -> Optional[str]:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()


class RunFamilyResponse(BaseModel):
    """The owned revision family of a run: its root + all owned descendants."""

    root_id: str
    members: list[FamilyMemberResponse]


def _owned_family_members(
    db: Session, user_id: str, root_id: str
) -> list[FamilyMemberResponse]:
    """BFS DOWN from ``root_id`` over OWNED children only → the ordered family
    member list (1-based ``revision_index``, root's out-of-family parent nulled).

    Extracted from ``get_run_family`` so ``get_run_summary`` reuses the SAME owned
    walk instead of duplicating it (INV-12 / no dual impl). Every query is
    owner-scoped (``user_id == user_id``) so no foreign run metadata enters the
    list; a visited-id set guards a cyclic parent chain (threat T-A-04). Members
    are ordered ``(created_at ASC, id ASC)`` — the id tiebreak makes same-timestamp
    ordering deterministic on SQLite — and every non-root member's parent is
    in-family by BFS construction, so the ``in members`` nulling never leaks a
    foreign id.

    FIX-173 added a cross-family guard here that dropped any child whose canonical
    base type differed from the root's, to stop concurrent PPT + prototype revision
    sessions contaminating each other's version dropdown. **That guard is removed.**

    It could not do the job it was written for. FIX-173's contamination came from a
    race in which ``contentSourceRunId`` transiently pointed at the wrong run when
    ``postRevision`` fired — so the child's ``parent_run_id`` AND its
    ``source_run_id`` were both written from the same wrong value. A read-path check
    cannot tell that row apart from a deliberate one; the type comparison was a
    proxy that happened to catch the reported case, not a detector.

    Meanwhile it rejected legitimate rows. Two kinds, both shipped features:

      * A deliberate cross-type revision. A ``custom`` run whose deliverable is
        ``prototype.html`` routes through ``handleRevisePrototype``
        (DashboardLayout's ``|| !!prototypeContent`` clause), producing a
        ``prototype_revision`` child of a ``custom`` root. The user asked for it;
        the guard disowned it, and ``/versions/N`` then resolved by index into a
        family that was missing a member.
      * A divert. ``ex_A3_divert`` → ``ex_A3_b_spanish`` is a different pipeline BY
        DESIGN, so a base-type comparison can never admit a diverted child.

    Contamination must be prevented where it is created — by not writing a parent
    link from a transient id — not by filtering reads. Until that write-path
    hardening exists, a cross-type child is admitted and logged (below) so the
    condition is observable instead of silently dropping a member.

    (FIX-179 also stripped an ``od_`` variant prefix here, so an ``od_prototype``
    root would admit its ``prototype_revision`` children. That label is collapsed
    and its rows migrated, so the prefix strip went with it.)
    """
    members: dict[str, WorkflowRun] = {}
    root_row = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == root_id, WorkflowRun.user_id == user_id)
        .first()
    )
    if root_row is not None:
        members[root_row.id] = root_row

    # Kept ONLY to describe an admitted cross-type child in the log line below —
    # nothing branches on it. ``prototype_revision`` → ``"prototype"``.
    def _canonical_base(t: str) -> str:
        """Strip a tiered or generic ``_revision`` suffix."""
        for suffix in ("_large_revision", "_feature_revision", "_revision"):
            if t.endswith(suffix):
                return t[: -len(suffix)]
        return t

    root_base_type: str | None = (
        _canonical_base(root_row.type) if root_row is not None else None
    )

    frontier = {root_id}
    visited = {root_id}
    while frontier:
        children = (
            db.query(WorkflowRun)
            .filter(
                WorkflowRun.parent_run_id.in_(frontier),
                WorkflowRun.user_id == user_id,
            )
            .all()
        )
        frontier = set()
        for child in children:
            if child.id in visited:
                continue  # cycle guard — never re-enqueue an already-seen run
            # A cross-type child is ADMITTED (see the docstring: deliberate
            # cross-type revisions and diverts are both legitimate). Logged, not
            # dropped, so a genuine FIX-173-style contamination is still visible
            # — previously it and every legitimate cross-type child were silently
            # discarded alike, which made a missing version indistinguishable from
            # a version that never existed.
            if (
                root_base_type is not None
                and _canonical_base(child.type) != root_base_type
            ):
                logger.info(
                    "run_family: admitting cross-type child %s (%s) under root %s (%s)",
                    child.id,
                    child.type,
                    root_id,
                    root_base_type,
                )
            visited.add(child.id)
            members[child.id] = child
            frontier.add(child.id)

    ordered = sorted(members.values(), key=lambda r: (r.created_at, r.id))

    # ── Task 9.3: batch-load finalization state for all family members ─────────
    # One query for the whole page rather than N per-member round trips.
    # Ownership-scoped (owner_id == user_id) — default-deny.
    member_ids = [r.id for r in ordered]
    fin_by_run: dict[str, object] = {}
    if member_ids:
        try:
            fin_rows = (
                db.query(
                    RunFinalization.run_id,
                    RunFinalization.chain_context_installed,
                    RunFinalization.payload_chainable,
                    RunFinalization.non_chainable_reason,
                )
                .filter(
                    RunFinalization.run_id.in_(member_ids),
                    RunFinalization.owner_id == user_id,
                )
                .all()
            )
            for fr in fin_rows:
                fin_by_run[fr.run_id] = fr
        except Exception:  # noqa: BLE001 — projection failure must not break the family endpoint
            pass

    return [
        FamilyMemberResponse(
            id=r.id,
            type=r.type,
            title=r.title,
            status=r.status,
            revision_index=idx,
            parent_run_id=(r.parent_run_id if r.parent_run_id in members else None),
            created_at=r.created_at,
            completed_at=r.completed_at,
            git_tag=getattr(
                r, "git_tag", None
            ),  # task 6.4 — nullable; None when run pre-dates git versioning
            # Task 9.3: finalization projection
            chain_context_installed=(
                fin_by_run[r.id].chain_context_installed if r.id in fin_by_run else None
            ),
            payload_chainable=(
                fin_by_run[r.id].payload_chainable
                if r.id in fin_by_run
                else getattr(r, "payload_chainable", None)
            ),
            non_chainable_reason=(
                fin_by_run[r.id].non_chainable_reason
                if r.id in fin_by_run
                else getattr(r, "non_chainable_reason", None)
            ),
        )
        for idx, r in enumerate(ordered, start=1)
    ]


# Per-agent fields that are summary-SAFE to surface (identity + KPI telemetry
# only). Deliberately EXCLUDES the raw content fields — output / input_prompt /
# thinking_text / tool_calls / context_sources — which could carry a secret, so
# the summary never echoes untrusted agent bytes (threat T-36-02-Leak / V7).
_SUMMARY_SAFE_AGENT_KEYS = (
    "agent_id",
    "name",
    "role",
    "icon",
    "duration",
    "error",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "model_id",
)


class RunSummaryResponse(BaseModel):
    """Aggregated, read-only summary of an owned run — the data spine for the
    Wave-2 Run-detail page (SHELL-03).

    Every field maps to an EXISTING ``WorkflowRun`` column or the owned family
    walk (ZERO invented fields, ZERO new tables/migrations). The endpoint only
    READS, so the 5 backend goldens are untouched by construction (INV-3):
      * KPI stats  → ``duration`` + ``agent_count`` + ``token_usage`` columns
      * failure banner → ``status`` + ``error`` columns
      * per-agent breakdown → ``agent_outputs`` (safe-projected, no raw bytes)
      * version/revision timeline → the ``parent_run_id`` family walk (reused).
    """

    id: str
    title: str
    type: str
    status: str
    input: Optional[str] = None  # the owner's OWN top-level brief/prompt (run.input)
    duration: Optional[float] = None
    agent_count: int
    token_usage: dict
    error: Optional[str] = None
    agents: list  # per-agent breakdown (summary-safe fields only)
    root_id: str
    members: list[FamilyMemberResponse]


@router.get("/{workflow_id}/family", response_model=RunFamilyResponse)
def get_run_family(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the owned revision family (root + all owned descendants) of a run.

    POR §4.3 / D-2 / D-6. Every step is owner-scoped (``user_id ==
    current_user.id``): the entry resolve, the root walk, AND every BFS step, so
    a cross-owner or missing run resolves to 404 (never 403 — the runs.py:14-17
    IDOR posture) and a foreign parent in the chain terminates the walk with NO
    foreign run metadata entering the response (threats T-A-02/03).

    Members are ordered ``(created_at ASC, id ASC)`` — the id tiebreak makes
    same-timestamp ordering deterministic on SQLite — and each carries a 1-based
    ``revision_index`` (chronological v-number, D-2) plus its ``parent_run_id``,
    which is nulled for the root (whose parent is out-of-family) so no dangling
    foreign pointer leaks.
    """
    # (a) Owner-scoped entry resolve — missing / cross-owner → 404.
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    # (b) Resolve the family root via the owned ancestor walk (terminates at any
    # foreign/missing link, so root is always an OWNED run id).
    root_id = _compute_root_ids(db, current_user.id, [workflow_run])[workflow_run.id]

    # (c)–(e) Collect + order the owned family via the shared BFS-down helper
    # (deterministic chronological order, 1-based revision_index, root parent
    # nulled). Extracted so /summary reuses the SAME owned walk (no dual impl).
    member_responses = _owned_family_members(db, current_user.id, root_id)
    return RunFamilyResponse(root_id=root_id, members=member_responses)


@router.get("/{workflow_id}/summary", response_model=RunSummaryResponse)
def get_run_summary(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate an owned run into the Wave-2 Run-detail summary (SHELL-03).

    Additive + READ-ONLY: reads ONLY existing ``WorkflowRun`` columns plus the
    owned revision-family walk — inventing zero fields and adding zero tables /
    migrations, so the 5 backend goldens are untouched by construction (INV-3)
    and no engine/transport is touched (LOCK-B).

    Owner-scoped via ``_owner_gate_or_404`` on ``WorkflowRun.user_id`` — the
    principal, NEVER the nullable ``owner_id`` — so a cross-owner or missing run
    resolves to 404 (IDOR → 404, never 403, never a 200 with another owner's
    data; P13/P25). The owned family walk terminates at any foreign ancestor, so
    no foreign run metadata leaks into the timeline (threat T-36-02-IDOR).
    """
    # (1) Owner gate — user_id keyed; missing / cross-owner → 404.
    run = _owner_gate_or_404(db, workflow_id, current_user.id)

    # (2) Tolerant parse of the two stored JSON blobs. Stored text is never
    # trusted to be well-formed → parse each inside try/except with a []/{}
    # fallback so a malformed blob degrades to an empty aggregate, never a 500
    # (DoS guard; mirrors the runs.py agent_outputs idiom above, threat
    # T-36-02-DoS).
    raw_agents: list = []
    if run.agent_outputs:
        try:
            parsed = json.loads(run.agent_outputs)
            if isinstance(parsed, list):
                raw_agents = parsed
        except Exception:
            pass

    token_usage: dict = {}
    if run.token_usage:
        try:
            parsed_tu = json.loads(run.token_usage)
            if isinstance(parsed_tu, dict):
                token_usage = parsed_tu
        except Exception:
            pass

    # (3) Per-agent breakdown — project ONLY the summary-safe identity + KPI
    # fields; NEVER echo the raw output / input_prompt / thinking_text /
    # tool_calls that could carry a secret (threat T-36-02-Leak / V7).
    agents = [
        {k: a.get(k) for k in _SUMMARY_SAFE_AGENT_KEYS if k in a}
        for a in raw_agents
        if isinstance(a, dict)
    ]

    # (4) Version/revision timeline — REUSE the owned ancestor walk for the root
    # and the SAME owned BFS-down member list get_run_family builds (no dual impl).
    root_id = _compute_root_ids(db, current_user.id, [run])[run.id]
    members = _owned_family_members(db, current_user.id, root_id)

    return RunSummaryResponse(
        id=run.id,
        title=run.title,
        type=run.type,
        status=run.status,
        # The owner's OWN top-level brief (run.input) — owner-gated already; this is
        # the same prompt the base detail showed the owner (the revision-instruction
        # preview reads it). NEVER child-agent output/input_prompt/secrets (V7 keeps
        # those out of the per-agent projection above).
        input=run.input,
        duration=run.duration,
        agent_count=run.agent_count,
        token_usage=token_usage,
        error=run.error,
        agents=agents,
        root_id=root_id,
        members=members,
    )


@router.get("/{workflow_id}/hook-runs")
async def get_hook_runs(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all ``hook_runs`` rows for a completed or active workflow run (KAN-73).

    Used by the frontend Audit tab to populate the audit trail on history-reopen.
    Owner-scoped (returns 404 on a cross-owner or missing run). Rows are ordered
    by ``created_at`` ascending so the Audit tab shows events in execution order.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    from app.models.hook_runs import HookRun

    rows = (
        db.query(HookRun)
        .filter(HookRun.run_id == workflow_id, HookRun.owner_id == current_user.id)
        .order_by(HookRun.created_at.asc())
        .all()
    )
    return {
        "workflow_id": workflow_id,
        "hook_runs": [
            {
                "id": r.id,
                "hook": r.hook,
                "event": r.event,
                "outcome": r.outcome,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


def _owner_gate_or_404(db: Session, workflow_id: str, user_id: str) -> WorkflowRun:
    """Layer-1 owner gate shared by the audit reads (mirrors ``get_hook_runs``).

    Gates the run by ``WorkflowRun.user_id == current_user.id`` — the principal,
    NEVER the nullable ``owner_id`` — so a cross-owner or missing run resolves to
    404 (IDOR → 404, never 403, never a 200 with another owner's rows; P13/P25).
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == user_id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )
    return workflow_run


@router.get("/{workflow_id}/gate-events")
async def get_gate_events(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the run's ``gate_events`` rows for the Audit tab (SC-3).

    Additive, read-only, owner-scoped read over the engine-populated
    ``gate_events`` table. Two-layer owner gate (mirrors ``get_hook_runs``):
    Layer 1 gates the run by ``user_id`` (→ 404 on cross-owner/missing); Layer 2
    re-filters the child rows by ``owner_id`` (defense-in-depth, T-32-03-01/03).
    Rows are ordered by ``created_at`` ascending so the Audit tab shows events in
    execution order.
    """
    _owner_gate_or_404(db, workflow_id, current_user.id)

    rows = (
        db.query(GateEvent)
        .filter(GateEvent.run_id == workflow_id, GateEvent.owner_id == current_user.id)
        .order_by(GateEvent.created_at.asc())
        .all()
    )
    return {
        "workflow_id": workflow_id,
        "gate_events": [
            {
                "id": r.id,
                "run_id": r.run_id,
                "step": r.step,
                "gate": r.gate,
                "outcome": r.outcome,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/{workflow_id}/validation-results")
async def get_validation_results(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the run's ``validation_results`` rows for the Audit tab (SC-3).

    Additive, read-only, owner-scoped read over the engine-populated
    ``validation_results`` table. Two-layer owner gate identical to
    ``get_gate_events`` (Layer 1 ``user_id`` → 404; Layer 2 ``owner_id``
    re-filter). Ordered by ``created_at`` ascending.
    """
    _owner_gate_or_404(db, workflow_id, current_user.id)

    rows = (
        db.query(ValidationResult)
        .filter(
            ValidationResult.run_id == workflow_id,
            ValidationResult.owner_id == current_user.id,
        )
        .order_by(ValidationResult.created_at.asc())
        .all()
    )
    return {
        "workflow_id": workflow_id,
        "validation_results": [
            {
                "id": r.id,
                "run_id": r.run_id,
                "step": r.step,
                "validator": r.validator,
                "severity": r.severity,
                "attempt": r.attempt,
                "issues": r.issues,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/{workflow_id}/exec-runs")
async def get_exec_runs(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the run's ``exec_runs`` rows for the Audit tab (SC-3).

    Additive, read-only, owner-scoped read over the engine-populated ``exec_runs``
    table. Two-layer owner gate identical to ``get_gate_events``. The projection
    surfaces the ``output_digest`` column AS STORED (truncated by design) and
    NEVER re-reads or expands the raw child output, which could carry a secret
    (T-32-03-02 / ASVS V7). Ordered by ``created_at`` ascending.
    """
    _owner_gate_or_404(db, workflow_id, current_user.id)

    rows = (
        db.query(ExecRun)
        .filter(ExecRun.run_id == workflow_id, ExecRun.owner_id == current_user.id)
        .order_by(ExecRun.created_at.asc())
        .all()
    )
    return {
        "workflow_id": workflow_id,
        "exec_runs": [
            {
                "id": r.id,
                "run_id": r.run_id,
                "step": r.step,
                "argv_json": r.argv_json,
                "outcome": r.outcome,
                "exit_code": r.exit_code,
                "duration_ms": r.duration_ms,
                "policy_snapshot_json": r.policy_snapshot_json,
                "output_digest": r.output_digest,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Share endpoints (Option B — public deliverable sharing).
#
# POST /api/runs/{id}/share  — owner mints a share token (or refreshes it).
# DELETE /api/runs/{id}/share — owner revokes the share.
# GET /s/{token}             — unauthenticated route registered in app/main.py;
#                              returns ONLY the deliverable (output +
#                              deliverable_mimetype). Never echoes input,
#                              agent_outputs, token_usage, or any PII.
# ---------------------------------------------------------------------------

# Default share link lifetime: 30 days (owner-revocable at any time).
_SHARE_TTL_DAYS = 30

# Regex that matches every ``filename:``-block path in the deliverable string
# (WorkflowRun.output). Used by the share guard below to assert that no
# reserved-path content was serialised into the output column before a share
# token is minted or served.  The pattern is anchored to the opening fence so
# it never false-positives on path-like strings *inside* file content.
_SHARE_FILENAME_BLOCK_RE = re.compile(
    r"^```filename:\s*(?P<path>[^\n]+)",
    re.MULTILINE,
)

# Combined exclusion set for the share boundary: every registry-reserved
# prefix plus the two git-metadata paths.  Derived once at module load so
# every call shares the same frozen object (no per-request allocation).
_SHARE_EXCLUDED: frozenset[str] = RESERVED_PATHS | GIT_METADATA_PATHS


def _assert_share_output_clean(output: str, run_id: str) -> None:
    """Assert that no reserved path appears in the deliverable output string.

    Parses every ``filename:``-block header in *output* and checks it against
    ``RESERVED_PATHS | GIT_METADATA_PATHS`` (V2-Q7 / Requirement 18 AC 7).
    Raises ``RuntimeError`` if a violation is found so the caller can log and
    refuse the request before any reserved content is served.

    The serialiser (``serialize_sandbox_deliverable``) already filters these
    paths at write time — this is an additional defence-in-depth assertion at
    the share boundary, matching the security checklist for task 2.6.

    ``run_id`` is included in the error message for operator diagnostics only;
    it is never forwarded to clients.
    """
    for m in _SHARE_FILENAME_BLOCK_RE.finditer(output):
        relpath: str = m.group("path").strip()
        # Check the full relative path against every reserved entry.
        # A reserved entry ending in "/" matches any path that starts with it
        # (subtree); a bare name (e.g. ".gitignore") matches exactly.
        for entry in _SHARE_EXCLUDED:
            if entry.endswith("/"):
                if relpath.startswith(entry) or relpath == entry.rstrip("/"):
                    raise RuntimeError(
                        f"share guard: reserved path {relpath!r} found in "
                        f"deliverable output for run {run_id!r} "
                        f"(matched registry entry {entry!r})"
                    )
            else:
                # Bare name: match the full relpath or its basename component.
                basename = relpath.rsplit("/", 1)[-1]
                if relpath == entry or basename == entry:
                    raise RuntimeError(
                        f"share guard: reserved path {relpath!r} found in "
                        f"deliverable output for run {run_id!r} "
                        f"(matched registry entry {entry!r})"
                    )


class ShareRunResponse(BaseModel):
    """Response for POST /api/runs/{id}/share."""

    share_token: str
    share_url: str
    expires_at: Optional[str] = None


@router.post("/{workflow_id}/share", response_model=ShareRunResponse)
def create_or_refresh_share(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mint (or refresh) a public share token for the run's deliverable.

    IDOR: owner gate via user_id — cross-owner / missing → 404, never 403.
    Only the output + deliverable_mimetype are served at /s/{token}; no
    input, agent_outputs, token_usage, or PII is ever exposed.

    Re-calling this endpoint replaces any existing token (refresh semantics),
    which is the same pattern as rotating an API key — the old link stops
    working and the caller gets a fresh one.
    """
    run = _owner_gate_or_404(db, workflow_id, current_user.id)

    # A run must be completed and have a deliverable to share.
    if run.status not in ("completed", "degraded"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "run_not_shareable",
                "message": "Only completed runs with a deliverable can be shared.",
            },
        )
    if not run.output:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "no_deliverable",
                "message": "This run has no deliverable output to share.",
            },
        )

    # Registry-derived share guard (Requirement 18 AC 7, task 2.6):
    # Refuse to mint a token if the serialised deliverable contains any path
    # from RESERVED_PATHS or GIT_METADATA_PATHS.  The serialiser already
    # excludes these at write time; this is defence-in-depth at the share
    # boundary so a historical or hand-written output column can never
    # inadvertently expose .chain/, .logs/, .git/, or any other reserved path
    # to an unauthenticated caller.
    try:
        _assert_share_output_clean(run.output, run.id)
    except RuntimeError:
        logger.exception(
            "share guard: reserved path in deliverable output, refusing share "
            "token mint for run_id=%s",
            workflow_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "share_guard_violation",
                "message": "Unable to create share link for this run.",
            },
        )

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=_SHARE_TTL_DAYS)

    run.share_token = token
    run.share_expires_at = expires_at
    db.commit()

    # The /s/ route lives at the app root (unauthenticated).
    # We avoid importing settings here (circular risk) and build the path only.
    share_path = f"/s/{token}"
    return ShareRunResponse(
        share_token=token,
        share_url=share_path,
        expires_at=expires_at.isoformat(),
    )


@router.delete(
    "/{workflow_id}/share",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def revoke_share(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke the public share for a run (clear share_token).

    Idempotent: revoking a run that has no share is a no-op (204).
    """
    run = _owner_gate_or_404(db, workflow_id, current_user.id)
    run.share_token = None
    run.share_expires_at = None
    db.commit()
    return None


def get_shared_run_by_token(token: str, db: Session):
    """Look up a run by share token; return None for missing/expired tokens.

    Used by the /s/{token} unauthenticated route in app/main.py.
    NEVER raises — the caller decides the HTTP response.
    """
    run = db.query(WorkflowRun).filter(WorkflowRun.share_token == token).first()
    if run is None:
        return None
    # Check expiry (allow a 60-second grace window for clock skew).
    if run.share_expires_at is not None:
        exp = run.share_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc) - timedelta(seconds=60):
            return None
    # Registry-derived share guard (Requirement 18 AC 7, task 2.6):
    # Verify the deliverable output contains no reserved paths before serving
    # it to an unauthenticated caller. This is the serve-time check that
    # complements the mint-time check in create_or_refresh_share.  If the
    # assertion fails the share is treated as unavailable (returns None) so
    # the caller sees 404 — identical to a missing or expired token.
    # NEVER raises per the function contract; logs the violation instead.
    if run.output:
        try:
            _assert_share_output_clean(run.output, run.id)
        except RuntimeError:
            logger.exception(
                "share guard: reserved path in deliverable output, "
                "refusing share serve for run_id=%s",
                run.id,
            )
            return None
    return run


# ── Restore (Requirement 9, task 8.1 / 8.2) ──────────────────────────────────


class RestoreRequest(BaseModel):
    """Request body for ``POST /api/runs/{run_id}/restore``.

    ``tag`` must be an exact match against the owned sandbox's visible tag
    list (Requirement 9 AC 2) — it is never accepted as a raw revspec.

    ``idempotency_key`` deduplicates retries: the same key returns the result
    of the first successful commit without creating a second one (Requirement
    9 AC 10).  Blocked restores deliberately do NOT record the key so that the
    block can clear and a re-attempt will proceed normally.
    """

    tag: str = Field(
        max_length=128,
        description="Exact visible tag name to restore (e.g. 'v1').",
    )
    idempotency_key: str = Field(
        max_length=256,
        description="Caller-supplied deduplication key.  Same key returns the first result.",
    )


class RestoreResponse(BaseModel):
    """Response from ``POST /api/runs/{run_id}/restore``."""

    run_id: str
    tag: str
    commit_id: str | None
    outcome: str  # "committed" | "no_change" | "blocked"


def _validate_tag_for_restore(tag: str, sandbox: RunSandbox) -> str:
    """Exact-match ``tag`` against the sandbox's visible tag list.

    Replicates the same gate as ``run_files._validate_ref``:  a free-form
    ref from user input is NEVER passed to a git subprocess (Requirement 9
    AC 2).  Returns ``tag`` unchanged on success.

    Raises:
        HTTPException(400): when ``tag`` is not an exact match in the list.
    """
    list_tags_fn = getattr(sandbox, "list_tags", lambda: [])
    try:
        valid_tags: list[str] = list_tags_fn()
    except Exception:  # noqa: BLE001 — fail-closed: unknown error → empty list
        valid_tags = []
    if tag not in valid_tags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_ref", "message": "Requested tag not found."},
        )
    return tag


def _has_active_family_member(db: Session, revision_root_id: str, user_id: str) -> bool:
    """Return True when any member of the revision family is non-terminal.

    "Active" means status is not one of the five terminal states.  This check
    runs under the family lock so the window between the check and the restore
    commit is serialized (Requirement 9 AC 5).

    Delegates to the family-scoped BFS in run_commands to avoid the overly
    conservative user-wide check (FR-057).
    """
    from app.api.run_commands import _has_active_chain_revision

    return _has_active_chain_revision(db, revision_root_id, user_id)


@router.post("/{run_id}/restore", response_model=RestoreResponse)
async def restore_version(
    run_id: str,
    body: RestoreRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restore the run's sandbox to a previous version tag.

    Creates a **forward commit** materializing the tracked tree at ``tag`` —
    never ``reset --hard``, never a tag rewrite, never ``checkout``.  Every
    existing commit and tag survives (Requirement 9 AC 7–8).

    Sequence (Requirement 9 AC 1–12):
      1. ORM owner gate → 404 on cross-owner / missing (IDOR by design).
      2. Idempotency check — BEFORE the active-family guard (AC 10).
      3. Revision-root resolution → 404 on failure.
      4. Sandbox construction + sandbox-dir existence check.
      5. Tag validation — exact match against ``list_tags()`` (AC 2).
      6. Acquire family lock.
      7. Active-family guard under the lock (AC 5).
      8. Detect + reconcile any persistent git state (``restore-precondition``).
      9. Materialize the tracked tree at the tag without moving HEAD.
     10. Commit through the ONE security-gated primitive (``commit_in_sandbox``
         with ``audit_operation="restore"``).  A blocked commit is a refusal —
         the idempotency key is NOT written (AC 11).
     11. Persist the ``run_provenance_audits`` row with the idempotency key.
     12. Return ``RestoreResponse``.

    **Blocked restores deliberately omit the idempotency key** (task 8.2).
    A blocked restore did not restore anything; the block may clear once the
    offending content is removed; burning the key now would make a legitimate
    retry return a stale "blocked" answer forever.

    **``commit_in_sandbox`` is the ONLY path to a sandbox commit** (task 4.1,
    Requirement 11 AC 9).  It owns mandatory secret scanning, declared
    pre_commit hooks, and the post_commit observer dispatch.  restore_version
    passes a minimal ``SimpleNamespace`` ectx and step so the primitive can
    run without a full ``ExecutionContext``.
    """
    from types import SimpleNamespace  # noqa: PLC0415

    from agents.execution_engine.engine import (  # noqa: PLC0415
        CommitInSandboxResult,
        commit_in_sandbox,
    )
    from app.agents.runtime.local import GitCommandError  # noqa: PLC0415

    # ── Layer 1 — ORM owner gate (IDOR → 404, never 403) ────────────────────
    run = _owner_gate_or_404(db, run_id, current_user.id)

    # ── Idempotency check — BEFORE the active-family guard ───────────────────
    # A successful prior restore with this key returns its cached result even
    # when a new run has since started (Requirement 9 AC 10, task 8.2).
    prior = lookup_idempotent_restore(db, current_user.id, body.idempotency_key)
    if prior is not None:
        return RestoreResponse(
            run_id=run_id,
            tag=prior["tag_name"] or body.tag,
            commit_id=prior["commit_id"],
            outcome=prior["outcome"] or "committed",
        )

    # ── Resolve revision root → 404 on failure ───────────────────────────────
    root_result = resolve_revision_root(db, run_id, current_user.id)
    if isinstance(root_result, RevisionRootUnresolved):
        logger.warning(
            "restore: revision root unresolved run=%s reason=%s visited=%d repeated=%s",
            run_id,
            root_result.reason,
            root_result.visited_count,
            root_result.repeated_node,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )
    assert isinstance(root_result, RevisionRootResolved)
    revision_root_id = root_result.root_id

    # ── Build sandbox handle (uses revision root for the directory) ──────────
    sandbox = RunSandbox(
        current_user.id,
        revision_root_id,
        current_run_id=run_id,
        runs_root=settings.RUNS_ROOT,
    )

    if not sandbox.root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sandbox not found",
        )

    # ── Validate the tag — exact match in the visible tag list ───────────────
    # Never pass a raw user-supplied string to a git subprocess (Requirement 9
    # AC 2).  _validate_tag_for_restore raises 400 on a miss.
    safe_tag = _validate_tag_for_restore(body.tag, sandbox)

    # ── Minimal ectx and step for commit_in_sandbox ──────────────────────────
    # commit_in_sandbox requires an ectx-shaped object and a step-shaped object.
    # For restore there is no ExecutionContext; we construct minimal
    # SimpleNamespace stubs with the fields the primitive reads.
    # ``last_commit_blocked`` is a write target — it must be mutable.
    workspace_id: str = run.workspace_id or ""
    _ectx = SimpleNamespace(
        run_id=run_id,
        owner_id=current_user.id,
        user_id=current_user.id,
        workspace_id=workspace_id,
        runner=None,
        final_status=None,
        deliverable=None,
        last_commit_blocked=False,
    )
    _step = SimpleNamespace(
        agent_id="restore",
        hooks=[],
        tools=None,
    )

    # ── Active-family guard under the family lock ────────────────────────────
    # Requirement 9 AC 5: acquire the family lock, check for non-terminal
    # family members under that same lock, fail closed on lock timeout.
    try:
        with family_lock(current_user.id, revision_root_id):
            if _has_active_family_member(db, revision_root_id, current_user.id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "family_run_active",
                        "message": (
                            "Cannot restore while a run in this family is active. "
                            "Try again once all runs have completed."
                        ),
                    },
                )

            # ── Detect + reconcile persistent git state ───────────────────────
            # Requirement 10 AC 14 (task 7.3): detect MERGE_HEAD, stale index.lock,
            # orphan worktrees, etc. left by a prior crash and reconcile with the
            # ``restore-precondition`` message class before touching the working tree.
            # ``detect_persistent_git_state`` returns {"state": "clean", ...} when
            # task 7.3 is not yet landed — that is safe: the reconcile call is a
            # no-op and we proceed normally.
            _git_state = sandbox.detect_persistent_git_state()
            if _git_state.get("state", "clean") != "clean":
                logger.info(
                    "restore: reconciling persistent git state run=%s state=%s",
                    run_id,
                    _git_state.get("state"),
                )
                _reconcile_outcome = sandbox.reconcile_persistent_git_state(_git_state)
                logger.info(
                    "restore: git state reconciled run=%s outcome=%s",
                    run_id,
                    _reconcile_outcome,
                )
                if _reconcile_outcome == "reconcile_failed":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "code": "git_state_reconcile_failed",
                            "message": (
                                "The sandbox has unrecoverable git state from a prior "
                                "crash. Operator intervention required."
                            ),
                        },
                    )

            # ── Materialize the tracked tree at the requested tag ─────────────
            # ``materialize_tree_at_ref`` writes the working tree to match ``ref``
            # without moving HEAD, without changing the index, and without committing.
            # A ``no_change`` result means HEAD already equals the tag; no commit
            # is needed.  A git failure propagates as ``GitCommandError`` — the
            # restore is refused, not silently treated as a no-op (Requirement 9
            # AC 7 / Requirement 10 AC 7).
            try:
                materialize_result = sandbox.materialize_tree_at_ref(safe_tag)
            except AttributeError as _attr_exc:
                # task 8.3 not yet landed — surface a clear 501
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail={
                        "code": "not_implemented",
                        "message": "materialize_tree_at_ref is not available (task 8.3).",
                    },
                ) from _attr_exc
            except GitCommandError as _git_exc:
                logger.error(
                    "restore: materialize_tree_at_ref failed run=%s tag=%s (%s)",
                    run_id,
                    safe_tag,
                    _git_exc,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "code": "restore_materialize_failed",
                        "message": "Failed to materialize the requested version.",
                    },
                ) from _git_exc

            mat_status: str = getattr(materialize_result, "status", "error")

            if mat_status == "no_change":
                # HEAD already equals the tag — nothing to commit.  A no-op
                # restore is honest: report it as such and record the key so
                # retries get the same answer (Requirement 9 AC 12).
                commit_sha: str | None = None
                outcome_str = "no_change"

            elif mat_status == "materialized":
                # The working tree was rewritten to match the tag; HEAD is
                # unchanged; the index is back at HEAD.  Commit this through the
                # ONE security-gated primitive (task 4.1, Requirement 11 AC 9).
                # Message is engine-rendered: run id + tag only, NO user content.
                _msg = f"restore: {run_id[:8]} to {safe_tag}"
                commit_result: CommitInSandboxResult = await commit_in_sandbox(
                    sandbox,
                    _msg,
                    _ectx,
                    _step,
                    audit_operation="restore",
                    audit_detail={
                        "tag_name": safe_tag,
                        "idempotency_key": body.idempotency_key,
                    },
                    registry=None,  # no declared hooks on the restore path
                )

                if commit_result.blocked:
                    # Blocked restores deliberately do NOT write the idempotency
                    # key (task 8.2) so a legitimate retry can attempt again once
                    # the blocking content is removed.
                    logger.warning(
                        "restore: commit BLOCKED by scan run=%s tag=%s reason=%s",
                        run_id,
                        safe_tag,
                        commit_result.block_reason,
                    )
                    return RestoreResponse(
                        run_id=run_id,
                        tag=safe_tag,
                        commit_id=None,
                        outcome="blocked",
                    )

                if commit_result.no_change:
                    # Nothing was staged even though materialize reported changes —
                    # treat as a no-op (tree already at this state).
                    commit_sha = None
                    outcome_str = "no_change"
                else:
                    commit_sha = commit_result.sha or None
                    outcome_str = "committed"

            else:
                # Defensive: status="error" or unknown value.  The git command
                # should have raised GitCommandError; if we reach here it means
                # MaterializeResult.status carried an unexpected sentinel.
                logger.error(
                    "restore: materialize_tree_at_ref returned unexpected status=%r "
                    "run=%s tag=%s — refusing to commit",
                    mat_status,
                    run_id,
                    safe_tag,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "code": "restore_materialize_failed",
                        "message": "Failed to materialize the requested version.",
                    },
                )

            # ── Persist the audit row with the idempotency key ────────────────
            # Both the committed and no-change paths write the key here so that
            # retries return the same answer.  The blocked path returned early
            # above without writing the key (task 8.2).
            audit_row = RunProvenanceAudit(
                id=str(uuid.uuid4()),
                owner_id=current_user.id,
                workspace_id=workspace_id,
                run_id=run_id,
                operation="restore",
                source_ref=safe_tag,
                idempotency_key=body.idempotency_key,
                commit_sha=commit_sha,
                tag_name=safe_tag,
                outcome=outcome_str,
            )
            try:
                db.add(audit_row)
                db.commit()
            except IntegrityError:
                # A concurrent request with the same idempotency key already
                # committed the partial unique index entry — treat it as an
                # idempotent hit and return the stored result.
                db.rollback()
                logger.info(
                    "restore: idempotency collision on key=%s run=%s — fetching stored result",
                    body.idempotency_key,
                    run_id,
                )
                stored = lookup_idempotent_restore(
                    db, current_user.id, body.idempotency_key
                )
                if stored is not None:
                    return RestoreResponse(
                        run_id=run_id,
                        tag=stored["tag_name"] or safe_tag,
                        commit_id=stored["commit_id"],
                        outcome=stored["outcome"] or outcome_str,
                    )
                # Extremely unlikely race: the concurrent write succeeded but the
                # follow-up read found nothing.  Surface the in-memory result so
                # the caller is not left without an answer.
                return RestoreResponse(
                    run_id=run_id,
                    tag=safe_tag,
                    commit_id=commit_sha,
                    outcome=outcome_str,
                )

            return RestoreResponse(
                run_id=run_id,
                tag=safe_tag,
                commit_id=commit_sha,
                outcome=outcome_str,
            )

    except HTTPException:
        raise
    except FamilyLockTimeout:
        logger.warning(
            "restore: family lock timeout run=%s revision_root=%s",
            run_id,
            revision_root_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "family_lock_timeout",
                "message": (
                    "Could not acquire the family lock. "
                    "Another operation is in progress — try again shortly."
                ),
            },
        )
    except Exception:
        logger.exception("restore: unexpected error run=%s", run_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "restore_failed",
                "message": "Restore failed unexpectedly.",
            },
        )
