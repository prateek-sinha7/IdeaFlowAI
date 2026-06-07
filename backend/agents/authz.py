"""agents/authz.py — the single default-deny scoped store helper (§19, AUTHZ-01/02).

This module is the RELOCATED L16 ownership seam (formerly the pure
``agents/execution_engine/authz.py`` predicate — CTX-03 / INV-8) GROWN into the
one enforced read/write path for the typed-artifact substrate (D-06 / D-07).
The old ``agents/execution_engine/authz.py`` is DELETED in the same change
(move-don't-copy — INV-12).

Why a single helper: §19 mandates that the ownership boundary is enforced in ONE
place, not scattered across callers. ``ScopedStore`` is constructed with the
caller principal ``(owner_id, workspace_id)`` plus a DB session, and exposes the
ONLY enforced read/write surface for artifacts, runs, workspaces, events, and
capabilities. Every READ applies the default-deny filter
``WHERE owner_id = :owner AND (workspace_id = :ws OR visibility IN ('workspace','public'))``
for models that carry a ``visibility`` column (``ArtifactRef``), and
``WHERE owner_id = :owner AND workspace_id = :ws`` for models that do not
(``WorkflowRun`` / ``Workspace`` / ``RunEvent`` / ``RunCapabilities``). A
cross-owner read therefore returns nothing → 404 at the API
(``app/api/runs.py`` IDOR→404 precedent; never 403).

``assert_owns`` (relocated) becomes a REAL-LOOKUP method (D-07): it reads the
parent run's TRUE ``owner_id`` from the store (regardless of the caller's
principal) and raises the typed ``PermissionError`` on mismatch. This replaces
the Phase-2 by-convention ``parent_owner_id`` argument with a store lookup while
preserving the Phase-2 message shape so the L16 denial behavior is unchanged.

Import-direction constraint (T-5-WEBIMPORT / RESEARCH #1): this module imports
``app.models.*`` + ``SessionLocal`` ONLY — NEVER ``app.api.*``. Keeping the web
layer out of the import graph prevents the ``engine → authz → app.api`` chain
from forming (enforced by ``lint-imports``).

DB premise (D-08, RESEARCH #2 corrected CONTEXT): the DB is FULLY SYNC — there is
NO ``AsyncSession``. Methods reuse the existing sync-``SessionLocal()``-inside-
``async def`` idiom from the thin store (``agents/artifact_store/store.py``):
when no ``Session`` is injected the method opens ``SessionLocal()`` in a
try/``db.close()`` finally (the engine path); when a ``Session`` is injected the
method uses it (the endpoint path via ``Depends(get_db)``). This gives ONE
acquisition path callers opt into.

Anonymous-principal rule (D-09 / AUTHZ-03): ``owner_id`` is always a REAL
principal string (``user_id`` or ``anon:<session_id>``, never ``None``). An anon
owner is subject to the same default-deny filter as any named owner — a second
anon session cannot read the first's rows.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Models that widen the default-deny filter with public/workspace visibility.
_VISIBLE_TO_WORKSPACE = ("workspace", "public")


class ScopedStore:
    """The single default-deny scoped store helper (§19, D-06/D-07).

    Constructed with the caller principal ``(owner_id, workspace_id)`` and an
    optional injected SQLAlchemy ``Session``. Every read is owner+visibility
    scoped; ``assert_owns`` looks up the parent run's true owner from the store.

    Acquisition (D-08): pass ``session=Depends(get_db)`` from an endpoint to
    reuse the request session, or leave ``session=None`` (the engine path) and
    each method opens/closes its own ``SessionLocal()``.
    """

    def __init__(
        self,
        owner_id: str,
        workspace_id: str | None = None,
        session: Any = None,
    ) -> None:
        # owner_id is a REAL principal string (user_id or anon:<session_id>),
        # never None — the default-deny filter must always have a real owner.
        self._owner_id = owner_id
        self._workspace_id = workspace_id
        self._session = session

    # ------------------------------------------------------------------
    # Session acquisition (sync ORM inside async def — D-08 / RESEARCH #2)
    # ------------------------------------------------------------------

    def _acquire(self) -> tuple[Any, bool]:
        """Return ``(session, owned)``.

        When a ``Session`` was injected, reuse it and report ``owned=False`` so
        the caller does NOT close it (the endpoint owns its request session).
        Otherwise open a fresh ``SessionLocal()`` and report ``owned=True`` so
        the caller closes it in a finally.
        """
        if self._session is not None:
            return self._session, False
        from app.models.database import SessionLocal

        return SessionLocal(), True

    # ------------------------------------------------------------------
    # Default-deny scope filters
    # ------------------------------------------------------------------

    def _scope_with_visibility(self, query: Any, model: Any) -> Any:
        """Owner + (own-workspace OR workspace/public visibility) filter.

        Applied to models carrying a ``visibility`` column (``ArtifactRef``):
        ``owner_id = :owner AND (workspace_id = :ws OR visibility IN
        ('workspace','public'))``.
        """
        return query.filter(
            model.owner_id == self._owner_id,
            (
                (model.workspace_id == self._workspace_id)
                | (model.visibility.in_(_VISIBLE_TO_WORKSPACE))
            ),
        )

    def _scope_owner_ws(self, query: Any, model: Any) -> Any:
        """Owner + workspace filter for models WITHOUT a ``visibility`` column
        (``WorkflowRun`` / ``Workspace`` / ``RunEvent`` / ``RunCapabilities``):
        ``owner_id = :owner AND workspace_id = :ws``.
        """
        return query.filter(
            model.owner_id == self._owner_id,
            model.workspace_id == self._workspace_id,
        )

    # ------------------------------------------------------------------
    # ArtifactRef — write + scoped reads
    # ------------------------------------------------------------------

    async def write_ref(self, ref: Any) -> str:
        """Persist an ``ArtifactRef`` dataclass (agents/artifacts/graph.py) to the
        ``artifact_refs`` ORM row and return the row id.

        The dataclass↔row mapping lives HERE (D-02). ``version`` mirrors the thin
        store's per-(run, kind) versioning: ``1 + count of same (run_id, kind)``.
        The principal stamped on the row is the helper's ``(owner_id,
        workspace_id)`` — the row's ``owner_id`` comes from the dataclass when
        present (it carries the producing owner) else the helper principal.
        """
        from sqlalchemy import func

        from app.models.artifact_ref import ArtifactRef as ArtifactRefRow

        session, owned = self._acquire()
        try:
            existing_count = (
                session.query(func.count(ArtifactRefRow.id))
                .filter(
                    ArtifactRefRow.run_id == ref.run_id,
                    ArtifactRefRow.kind == ref.kind,
                )
                .scalar()
            ) or 0
            version = getattr(ref, "version", None) or (existing_count + 1)
            row = ArtifactRefRow(
                id=getattr(ref, "id", None) or str(uuid.uuid4()),
                run_id=ref.run_id,
                owner_id=getattr(ref, "owner_id", None) or self._owner_id,
                workspace_id=getattr(ref, "workspace_id", None)
                or self._workspace_id,
                kind=ref.kind,
                producer_step=ref.producer_step,
                producer_agent=ref.producer_agent,
                task_id=getattr(ref, "task_id", None),
                content=ref.content,
                content_hash=ref.content_hash,
                location=ref.location,
                version=version,
                parents=list(getattr(ref, "parents", []) or []),
                derived_from=getattr(ref, "derived_from", None),
                visibility=getattr(ref, "visibility", "private"),
                retention=getattr(ref, "retention", "run_ttl"),
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            if owned:
                session.close()

    async def get_ref(self, ref_id: str) -> Any | None:
        """Return the owner+visibility-scoped ``ArtifactRef`` row, or ``None``.

        A cross-owner ref id resolves to ``None`` (default-deny) → 404 at the API.
        """
        from app.models.artifact_ref import ArtifactRef as ArtifactRefRow

        session, owned = self._acquire()
        try:
            query = session.query(ArtifactRefRow).filter(
                ArtifactRefRow.id == ref_id
            )
            return self._scope_with_visibility(query, ArtifactRefRow).first()
        finally:
            if owned:
                session.close()

    async def list_refs(
        self, run_id: str, kind: str | None = None
    ) -> list[Any]:
        """Return the run's owner+visibility-scoped ``ArtifactRef`` rows.

        Optionally filtered to a single ``kind``. Ordered by ``version`` ascending
        (oldest first), mirroring the thin store's ``list_by_type`` shape.
        """
        from app.models.artifact_ref import ArtifactRef as ArtifactRefRow

        session, owned = self._acquire()
        try:
            query = session.query(ArtifactRefRow).filter(
                ArtifactRefRow.run_id == run_id
            )
            if kind is not None:
                query = query.filter(ArtifactRefRow.kind == kind)
            query = self._scope_with_visibility(query, ArtifactRefRow)
            return query.order_by(ArtifactRefRow.version.asc()).all()
        finally:
            if owned:
                session.close()

    async def lineage(self, run_id: str) -> list[Any]:
        """Return the run's owner+visibility-scoped refs for an in-memory tree
        walk (ART-01 — no DB recursive CTE; the per-run set is small)."""
        from app.models.artifact_ref import ArtifactRef as ArtifactRefRow

        session, owned = self._acquire()
        try:
            query = session.query(ArtifactRefRow).filter(
                ArtifactRefRow.run_id == run_id
            )
            query = self._scope_with_visibility(query, ArtifactRefRow)
            return query.order_by(ArtifactRefRow.created_at.asc()).all()
        finally:
            if owned:
                session.close()

    async def tree(self, run_id: str) -> list[Any]:
        """Alias of :meth:`lineage` — the run's scoped refs for tree shaping."""
        return await self.lineage(run_id)

    # ------------------------------------------------------------------
    # RunEvent — append + scoped replay
    # ------------------------------------------------------------------

    async def append_event(
        self,
        run_id: str,
        seq: int,
        event_id: str,
        type: str,
        payload_json: Any,
    ) -> str:
        """Insert a ``run_events`` row stamped with the helper principal."""
        from app.models.run_event import RunEvent

        session, owned = self._acquire()
        try:
            row = RunEvent(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=self._owner_id,
                workspace_id=self._workspace_id,
                seq=seq,
                event_id=event_id,
                type=type,
                payload_json=payload_json,
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            if owned:
                session.close()

    async def read_events(self, run_id: str, after_seq: int) -> list[Any]:
        """Return owner+workspace-scoped ``run_events`` rows with ``seq >
        after_seq`` ordered by ``seq`` ascending (idempotent replay, API-05)."""
        from app.models.run_event import RunEvent

        session, owned = self._acquire()
        try:
            query = session.query(RunEvent).filter(
                RunEvent.run_id == run_id,
                RunEvent.seq > after_seq,
            )
            query = self._scope_owner_ws(query, RunEvent)
            return query.order_by(RunEvent.seq.asc()).all()
        finally:
            if owned:
                session.close()

    # ------------------------------------------------------------------
    # WorkflowRun — scoped lookup
    # ------------------------------------------------------------------

    async def get_run(self, run_id: str) -> Any | None:
        """Return the owner+workspace-scoped ``WorkflowRun`` row, or ``None``.

        A cross-owner run id resolves to ``None`` (default-deny) → the 404 source
        at the API (``app/api/runs.py`` IDOR→404 precedent)."""
        from app.models.workflow import WorkflowRun

        session, owned = self._acquire()
        try:
            query = session.query(WorkflowRun).filter(WorkflowRun.id == run_id)
            query = self._scope_owner_ws(query, WorkflowRun)
            return query.first()
        finally:
            if owned:
                session.close()

    # ------------------------------------------------------------------
    # Workspace — create + (the scoped read rides _scope_owner_ws)
    # ------------------------------------------------------------------

    async def create_workspace(
        self,
        run_id: str,
        kind: str = "sandbox",
        runtime: str = "local",
    ) -> str:
        """Insert a ``workspaces`` row and return its id.

        The new workspace's ``workspace_id`` is set equal to its own ``id`` so the
        uniform ``workspace_id = :ws`` scope filter holds for workspace reads too
        (see ``app/models/workspace.py``). ``owner_id`` is the helper principal.
        """
        from app.models.workspace import Workspace

        session, owned = self._acquire()
        try:
            ws_id = str(uuid.uuid4())
            row = Workspace(
                id=ws_id,
                owner_id=self._owner_id,
                workspace_id=ws_id,  # self-id (AUTHZ-01 uniform filter)
                kind=kind,
                runtime=runtime,
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            if owned:
                session.close()

    # ------------------------------------------------------------------
    # RunCapabilities — record
    # ------------------------------------------------------------------

    async def record_capabilities(
        self,
        run_id: str,
        runtime: str,
        **deferred: Any,
    ) -> str:
        """Insert one ``run_capabilities`` row for the run.

        ``runtime`` is the executing adapter id (``langchain_deepagents`` —
        stamped by the engine in 05-04). ``**deferred`` carries the forward
        capability fields (``model_overrides``/``skills``/``hooks``/
        ``integrations``/``mcp_servers``/``versions``) populated in later phases.
        """
        from app.models.run_capabilities import RunCapabilities

        session, owned = self._acquire()
        try:
            row = RunCapabilities(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=self._owner_id,
                workspace_id=self._workspace_id,
                runtime=runtime,
                model_overrides=deferred.get("model_overrides"),
                skills=deferred.get("skills"),
                hooks=deferred.get("hooks"),
                integrations=deferred.get("integrations"),
                mcp_servers=deferred.get("mcp_servers"),
                versions=deferred.get("versions"),
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            if owned:
                session.close()

    # ------------------------------------------------------------------
    # assert_owns — the relocated L16 seam, now a real store lookup (D-07)
    # ------------------------------------------------------------------

    async def assert_owns(self, parent_run_id: str) -> None:
        """Raise ``PermissionError`` iff this caller does not own ``parent_run_id``.

        D-07 change vs the Phase-2 pure predicate: the parent's TRUE ``owner_id``
        is looked up from the store via an UNSCOPED-by-owner read (it must read
        the parent's real owner regardless of who the caller is), then compared
        to ``self._owner_id``. On mismatch the typed ``PermissionError`` is raised
        with the Phase-2 message shape; on match (or an absent parent — the
        same-owner missing/TTL-swept degrade path) ``None`` is returned.

        The raised ``PermissionError`` is what the engine seed block (05-04)
        propagates ABOVE its graceful-degrade ``try`` so a cross-owner parent is
        never silently seeded (Highest-Risk Behavior 4 — L16 must not regress).
        """
        from app.models.workflow import WorkflowRun

        session, owned = self._acquire()
        try:
            # UNSCOPED-by-owner: read the parent's true owner regardless of caller.
            parent = (
                session.query(WorkflowRun)
                .filter(WorkflowRun.id == parent_run_id)
                .first()
            )
        finally:
            if owned:
                session.close()

        if parent is None:
            # Absent / TTL-swept parent → no cross-owner leak possible; defer to
            # the engine's graceful-degrade try (CTX-05 parity). Same-owner
            # missing parent must NOT raise.
            return None

        parent_owner = parent.owner_id
        if parent_owner != self._owner_id:
            raise PermissionError(
                f"owner {self._owner_id!r} may not seed from parent run "
                f"{parent_run_id!r} (owned by {parent_owner!r})"
            )
        return None


__all__ = ["ScopedStore"]
