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

    async def write_ref(self, ref: Any, *, force_db_version: bool = False) -> str:
        """Persist an ``ArtifactRef`` dataclass (agents/artifacts/graph.py) to the
        ``artifact_refs`` ORM row and return the row id.

        The dataclass↔row mapping lives HERE (D-02). ``version`` mirrors the thin
        store's per-(run, kind) versioning: ``1 + count of same (run_id, kind)``.
        The principal stamped on the row is the helper's ``(owner_id,
        workspace_id)`` — the row's ``owner_id`` comes from the dataclass when
        present (it carries the producing owner) else the helper principal.

        Versioning source of truth (WR-01 / CR-01): when the caller shares the
        per-run ``ArtifactGraph`` (the engine path), the dataclass ``version`` and
        the DB ``COUNT(*)`` agree by construction, so the dataclass value is
        honored. When the caller CANNOT share a graph (the clarify path constructs
        a throwaway ``ArtifactGraph`` per round, so its ``version`` is always 1),
        it must pass ``force_db_version=True`` so the DB ``existing_count + 1`` is
        the authoritative per-(run, kind) version — keeping the column monotonic
        across calls (artifact_ref.py:43 invariant) and the reconnect read
        deterministic (websocket.py orders by ``version ASC`` and takes the last).

        AUTHZ-03 (CR-02): the resolved ``owner_id`` MUST be a real principal — a
        falsy owner defeats the default-deny filter (an owner-``None`` row matches
        no scoped read and bypasses the "real principal" invariant), so this single
        write seam rejects it loudly rather than silently persisting a dead row.
        """
        from sqlalchemy import func

        from app.models.artifact_ref import ArtifactRef as ArtifactRefRow

        resolved_owner = getattr(ref, "owner_id", None) or self._owner_id
        if not resolved_owner:
            raise ValueError(
                "artifact_refs.owner_id must be a real principal (AUTHZ-03); "
                "got a falsy owner from both the ref and the ScopedStore"
            )

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
            if force_db_version:
                # The caller's dataclass version is not cross-call meaningful
                # (throwaway graph) — the DB count is authoritative.
                version = existing_count + 1
            else:
                version = getattr(ref, "version", None) or (existing_count + 1)
            row = ArtifactRefRow(
                id=getattr(ref, "id", None) or str(uuid.uuid4()),
                run_id=ref.run_id,
                owner_id=resolved_owner,
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
            # WR-03: created_at is a Python-side default(datetime.now) set at flush
            # time, so back-to-back writes in one task-loop iteration can tie at the
            # stored precision. Add stable secondary keys (version, id) so the order
            # between same-timestamp refs is deterministic for any consumer that
            # relies on lineage() insertion order.
            return query.order_by(
                ArtifactRefRow.created_at.asc(),
                ArtifactRefRow.version.asc(),
                ArtifactRefRow.id.asc(),
            ).all()
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

    async def persist_budget_snapshot(self, run_id: str, snapshot: dict) -> None:
        """Write the fan-out ``BudgetSnapshot`` to ``workflow_runs.budget_snapshot_json``.

        The 0014 forward column finally written (OBS-01): on run completion / abort
        (BudgetExceeded) / cancel the engine persists the run's accumulated budget spend
        (tokens / cost / subagents / depth / wall_clock). The row is resolved under the
        owner+workspace scope filter so a cross-owner caller can never stamp another
        owner's run (default-deny). A missing/cross-owner row is a no-op (the same
        graceful degrade as the read path — audit must never abort the run).
        """
        from app.models.workflow import WorkflowRun

        session, owned = self._acquire()
        try:
            query = session.query(WorkflowRun).filter(WorkflowRun.id == run_id)
            query = self._scope_owner_ws(query, WorkflowRun)
            row = query.first()
            if row is None:
                return
            row.budget_snapshot_json = snapshot
            session.commit()
        finally:
            if owned:
                session.close()

    async def set_run_scope(
        self, run_id: str, owner_id: str, workspace_id: str
    ) -> None:
        """Stamp ``(owner_id, workspace_id)`` onto an existing ``workflow_runs`` row.

        CR-01: a run created at the WS layer before its workspace is known (the
        revision path — the workspace is the parent artifact's workspace, resolved
        only inside the engine) must have its scope written back so the
        owner+workspace-scoped reads (``get_run`` / ``read_events`` /
        ``_scope_owner_ws``) resolve it. Without this the /events endpoint 404s for
        every such run and the row violates the never-None AUTHZ-01/03 invariant.

        Both ``owner_id`` and ``workspace_id`` MUST be real principals — a falsy
        value would re-open the default-deny hole, so this seam rejects it loudly
        (AUTHZ-03 fail-loud, never by widening nullability). The lookup is
        UNSCOPED-by-owner (the row may still carry a None owner/workspace at this
        point), but the write only ever STAMPS the caller-supplied real principal.

        IN-02: because the lookup is unscoped-by-owner, a future/misused caller could
        re-scope a row that already belongs to a DIFFERENT owner, silently clobbering
        it. Defend the seam: only stamp when the row's existing ``owner_id`` is None
        (never scoped) or already equals the supplied owner; a mismatch is a misuse
        and FAILS LOUD with ``PermissionError`` rather than performing a cross-owner
        overwrite.
        """
        if not owner_id or not workspace_id:
            raise ValueError(
                "set_run_scope requires a real (owner_id, workspace_id) "
                "(AUTHZ-01/03); refusing to stamp a falsy principal on "
                f"workflow_runs row {run_id!r}"
            )
        from app.models.workflow import WorkflowRun

        session, owned = self._acquire()
        try:
            row = (
                session.query(WorkflowRun)
                .filter(WorkflowRun.id == run_id)
                .first()
            )
            if row is None:
                # Offline harness / no FK row — nothing to stamp. The caller's
                # best-effort wrapper degrades the same way append_event does.
                return None
            # IN-02: same-owner sanity guard. Stamping is only legal onto an
            # unscoped row (owner None) or a row already owned by this principal.
            # A cross-owner stamp is a contract violation — fail loud, never clobber.
            existing_owner = getattr(row, "owner_id", None)
            if existing_owner is not None and existing_owner != owner_id:
                raise PermissionError(
                    "set_run_scope refused: workflow_runs row "
                    f"{run_id!r} is already owned by a different principal "
                    "(cross-owner re-scope is not permitted, AUTHZ-03)"
                )
            row.owner_id = owner_id
            row.workspace_id = workspace_id
            session.commit()
            return None
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
    # Repository — create the repo row + link the kind=repo workspace (RUNTIME-03)
    # ------------------------------------------------------------------

    async def create_repository(
        self,
        *,
        provider: str,
        url: str,
        default_branch: str,
        workspace_id: str | None = None,
        auth_ref: str | None = None,
    ) -> str:
        """Insert ONE ``repositories`` row + link the ``kind='repo'`` workspace.

        Persists exactly one ``repositories`` row (stamped with the helper
        principal ``owner_id`` + the run's ``workspace_id``, AUTHZ-01) and, when a
        ``workspace_id`` is supplied, sets that ``workspaces`` row's ``kind='repo'``
        + ``repo_id`` so the two are linked (the FK wired by migration 0017). The
        ``workspace_id`` defaults to the helper's principal workspace when omitted.

        Mirrors ``create_workspace`` / ``record_capabilities`` (the run-entry
        writers): default-deny, owner/workspace-scoped. ``provider`` is a free
        String (``github`` / ``gitlab`` / ``local``); ``auth_ref`` is the
        scoped-credential pointer, never the secret. Returns the repository id.
        """
        from app.models.repository import Repository
        from app.models.workspace import Workspace

        ws_id = workspace_id or self._workspace_id

        session, owned = self._acquire()
        try:
            repo_id = str(uuid.uuid4())
            session.add(
                Repository(
                    id=repo_id,
                    owner_id=self._owner_id,
                    workspace_id=ws_id,
                    provider=provider,
                    url=url,
                    default_branch=default_branch,
                    auth_ref=auth_ref,
                )
            )
            # Link the kind=repo workspace row to the new repository (FK target),
            # scoped to the helper principal so a cross-owner workspace is never
            # mutated (default-deny — a non-matching row links nothing).
            if ws_id is not None:
                ws_row = (
                    session.query(Workspace)
                    .filter(
                        Workspace.id == ws_id,
                        Workspace.owner_id == self._owner_id,
                    )
                    .first()
                )
                if ws_row is not None:
                    ws_row.kind = "repo"
                    ws_row.repo_id = repo_id
            session.commit()
            return repo_id
        finally:
            if owned:
                session.close()

    async def get_repository(self, repo_id: str) -> Any | None:
        """Return the owner+workspace-scoped ``repositories`` row, or ``None``.

        A cross-owner repo id resolves to ``None`` (default-deny) → the T-09-02-ID
        denial source: the persistence test asserts a cross-owner read raises
        ``PermissionError`` via :meth:`assert_repo_owned`.
        """
        from app.models.repository import Repository

        session, owned = self._acquire()
        try:
            query = session.query(Repository).filter(Repository.id == repo_id)
            query = self._scope_owner_ws(query, Repository)
            return query.first()
        finally:
            if owned:
                session.close()

    async def assert_repo_owned(self, repo_id: str) -> None:
        """Raise ``PermissionError`` iff this caller does not own ``repo_id`` (T-09-02-ID).

        Reads the repo's TRUE ``owner_id`` via an UNSCOPED-by-owner lookup and
        compares it to ``self._owner_id`` (the ``assert_owns`` idiom, D-07). A
        cross-owner read therefore fails loud rather than silently returning the
        default-deny ``None`` — the explicit denial gate the persistence test pins.
        An absent repo (same-owner missing / TTL-swept) returns ``None``.
        """
        from app.models.repository import Repository

        session, owned = self._acquire()
        try:
            repo = (
                session.query(Repository)
                .filter(Repository.id == repo_id)
                .first()
            )
        finally:
            if owned:
                session.close()

        if repo is None:
            return None
        if repo.owner_id != self._owner_id:
            raise PermissionError(
                f"owner {self._owner_id!r} may not read repository "
                f"{repo_id!r} (owned by {repo.owner_id!r})"
            )
        return None

    # ------------------------------------------------------------------
    # McpCredential — scoped write + owner-scoped read (09-05 / MCP-02)
    # ------------------------------------------------------------------

    async def write_mcp_credential(
        self,
        *,
        server: str,
        secret: str,
        scope: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        """Store a per-owner MCP server credential (encrypted). Returns the row id.

        The secret is Fernet-encrypted (``app.core.crypto.encrypt_pat``) before it
        touches the DB — never the plaintext (the ``UserGithubCredential`` PAT
        precedent). The row is stamped with the helper principal ``owner_id`` + the
        run's ``workspace_id`` (AUTHZ-01) so the default-deny filter scopes every
        read; a credential is NEVER global. ``server`` is the catalog ``mcp_server``
        name; ``scope`` records the granted read/write scope (e.g. ``gitlab_read``).
        """
        from app.core.crypto import encrypt_pat
        from app.models.mcp_credential import McpCredential

        ws_id = workspace_id or self._workspace_id
        session, owned = self._acquire()
        try:
            cred_id = str(uuid.uuid4())
            session.add(
                McpCredential(
                    id=cred_id,
                    owner_id=self._owner_id,
                    workspace_id=ws_id,
                    server=server,
                    scope=scope,
                    encrypted_secret=encrypt_pat(secret),
                )
            )
            session.commit()
            return cred_id
        finally:
            if owned:
                session.close()

    async def read_mcp_credential(self, cred_id: str) -> str | None:
        """Return the DECRYPTED secret for an OWNED MCP credential, or ``None``.

        Owner+workspace-scoped (default-deny): a cross-owner credential id resolves
        to ``None`` here. The explicit cross-owner DENIAL is :meth:`assert_mcp_cred_owned`
        — a cross-owner read raises ``PermissionError`` (T-09-05-ID), the gate the
        catalog test pins. A same-owner row decrypts via ``app.core.crypto.decrypt_pat``.
        """
        from app.core.crypto import decrypt_pat
        from app.models.mcp_credential import McpCredential

        session, owned = self._acquire()
        try:
            query = session.query(McpCredential).filter(McpCredential.id == cred_id)
            query = self._scope_owner_ws(query, McpCredential)
            row = query.first()
        finally:
            if owned:
                session.close()
        if row is None:
            return None
        return decrypt_pat(row.encrypted_secret)

    async def assert_mcp_cred_owned(self, cred_id: str) -> None:
        """Raise ``PermissionError`` iff this caller does not own ``cred_id`` (T-09-05-ID).

        Reads the credential's TRUE ``owner_id`` via an UNSCOPED-by-owner lookup and
        compares it to ``self._owner_id`` (the ``assert_owns`` idiom). A cross-owner
        read fails LOUD rather than silently returning the default-deny ``None`` — the
        explicit per-owner-credential denial gate (T-09-05-ID). An absent credential
        (same-owner missing / swept) returns ``None``.
        """
        from app.models.mcp_credential import McpCredential

        session, owned = self._acquire()
        try:
            row = (
                session.query(McpCredential)
                .filter(McpCredential.id == cred_id)
                .first()
            )
        finally:
            if owned:
                session.close()
        if row is None:
            return None
        if row.owner_id != self._owner_id:
            raise PermissionError(
                f"owner {self._owner_id!r} may not read MCP credential "
                f"{cred_id!r} (owned by {row.owner_id!r})"
            )
        return None

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
    # Phase-8 capability-hardening tables — owner/workspace-scoped writes (D-10)
    #
    # gate_events / validation_results / hook_runs each carry owner_id +
    # workspace_id (AUTHZ-01); every write stamps the helper principal so the
    # default-deny read filter (_scope_owner_ws) scopes them. gate_events is the
    # LIVE writer this plan (08-02); validation_results / hook_runs are consumed in
    # 08-04 / 08-07 but land their writers here so the seam is complete.
    # ------------------------------------------------------------------

    async def record_gate_event(
        self,
        run_id: str,
        step: str,
        gate: str,
        outcome: str,
        detail: Any = None,
    ) -> str:
        """Insert one ``gate_events`` row stamped with the helper principal (08-02).

        ``outcome`` ∈ ``pass | block | wait_human``. The row carries owner_id +
        workspace_id so a cross-owner read returns nothing (default-deny,
        T-08-02-ID). Returns the row id.
        """
        from app.models.gate_events import GateEvent

        session, owned = self._acquire()
        try:
            row = GateEvent(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=self._owner_id,
                workspace_id=self._workspace_id,
                step=step,
                gate=gate,
                outcome=outcome,
                detail=detail,
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            if owned:
                session.close()

    async def read_gate_events(self, run_id: str) -> list[Any]:
        """Return the run's owner+workspace-scoped ``gate_events`` rows (default-deny).

        A cross-owner read returns nothing → the T-08-02-ID mitigation proof.
        """
        from app.models.gate_events import GateEvent

        session, owned = self._acquire()
        try:
            query = session.query(GateEvent).filter(GateEvent.run_id == run_id)
            query = self._scope_owner_ws(query, GateEvent)
            return query.order_by(GateEvent.created_at.asc()).all()
        finally:
            if owned:
                session.close()

    async def record_validation_result(
        self,
        run_id: str,
        step: str,
        validator: str,
        *,
        severity: str | None = None,
        attempt: int = 0,
        issues: Any = None,
    ) -> str:
        """Insert one ``validation_results`` row (consumed in 08-04).

        Lands here so the scoped-writer seam for all three §18 tables is complete;
        the Validator framework (08-04) is its caller.
        """
        from app.models.validation_results import ValidationResult

        session, owned = self._acquire()
        try:
            row = ValidationResult(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=self._owner_id,
                workspace_id=self._workspace_id,
                step=step,
                validator=validator,
                severity=severity,
                attempt=attempt,
                issues=issues,
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            if owned:
                session.close()

    async def record_hook_run(
        self,
        run_id: str,
        hook: str,
        event: str,
        outcome: str,
        detail: Any = None,
    ) -> str:
        """Insert one ``hook_runs`` row (consumed in 08-07).

        Lands here so the scoped-writer seam for all three §18 tables is complete;
        the executable hook framework (08-07) is its caller.
        """
        from app.models.hook_runs import HookRun

        session, owned = self._acquire()
        try:
            row = HookRun(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=self._owner_id,
                workspace_id=self._workspace_id,
                hook=hook,
                event=event,
                outcome=outcome,
                detail=detail,
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            if owned:
                session.close()

    # ------------------------------------------------------------------
    # Phase-10 exec audit table — owner/workspace-scoped writes (EXEC-01)
    #
    # exec_runs carries owner_id + workspace_id (AUTHZ-01); every write stamps the
    # helper principal so the default-deny read filter (_scope_owner_ws) scopes
    # them. The writer is reached at the exec_command enforcement point via the
    # workspace recorder callback (KernelServices.record_exec_run), so EVERY exec
    # outcome (allowed/denied/killed) is audited bypass-proof (T-10-01-07).
    # ------------------------------------------------------------------

    async def record_exec_run(
        self,
        run_id: str,
        step: str,
        argv: Any,
        outcome: str,
        *,
        exit_code: int | None = None,
        duration_ms: int | None = None,
        policy_snapshot: Any = None,
        output_digest: str | None = None,
    ) -> str:
        """Insert one ``exec_runs`` row stamped with the helper principal (EXEC-01).

        ``outcome`` ∈ ``allowed | denied | killed``. The row carries owner_id +
        workspace_id so a cross-owner read returns nothing (default-deny,
        T-10-01-08). ``argv`` is the argv LIST (never a shell string — the IN-02
        fix); ``output_digest`` is a TRUNCATED digest, never raw child output
        (T-10-01-03 / T-10-01-06). Returns the row id.
        """
        from app.models.exec_runs import ExecRun

        session, owned = self._acquire()
        try:
            row = ExecRun(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=self._owner_id,
                workspace_id=self._workspace_id,
                step=step,
                argv_json=list(argv) if argv is not None else [],
                outcome=outcome,
                exit_code=exit_code,
                duration_ms=duration_ms,
                policy_snapshot_json=policy_snapshot,
                output_digest=output_digest,
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            if owned:
                session.close()

    async def read_exec_runs(self, run_id: str) -> list[Any]:
        """Return the run's owner+workspace-scoped ``exec_runs`` rows (default-deny).

        A cross-owner read returns nothing → the T-10-01-08 mitigation proof.
        """
        from app.models.exec_runs import ExecRun

        session, owned = self._acquire()
        try:
            query = session.query(ExecRun).filter(ExecRun.run_id == run_id)
            query = self._scope_owner_ws(query, ExecRun)
            return query.order_by(ExecRun.created_at.asc()).all()
        finally:
            if owned:
                session.close()

    # ------------------------------------------------------------------
    # subagent_runs — fan-out child audit writer/updater/reader (Phase 11)
    #
    # subagent_runs carries owner_id + workspace_id (AUTHZ-01); every write stamps
    # the helper principal so the default-deny read filter (_scope_owner_ws) scopes
    # them. ONE row is written per fan-out child at spawn time (status='running')
    # through the single kernel run_fanout spawn path, flipped terminal on
    # completion. A cross-owner read returns nothing — the FANOUT-10 mitigation
    # (T-11-01-03): a user can never read another owner's fan-out children.
    # ------------------------------------------------------------------

    async def record_subagent_run(
        self,
        parent_run_id: str,
        *,
        parent_step: str,
        worker_agent: str,
        depth: int,
        isolation: str,
        status: str,
        tokens: int | None = None,
        cost: Any = None,
    ) -> str:
        """Insert one ``subagent_runs`` row stamped with the helper principal (FANOUT-10).

        ``isolation`` ∈ ``shared_read | sub_sandbox | worktree`` (free String) and
        ``status`` ∈ ``running | complete | failed | cancelled`` (free String). The
        row carries owner_id + workspace_id so a cross-owner read returns nothing
        (default-deny, T-11-01-03). Returns the row id.
        """
        from app.models.subagent_run import SubagentRun

        session, owned = self._acquire()
        try:
            row = SubagentRun(
                id=str(uuid.uuid4()),
                parent_run_id=parent_run_id,
                owner_id=self._owner_id,
                workspace_id=self._workspace_id,
                parent_step=parent_step,
                worker_agent=worker_agent,
                depth=depth,
                isolation=isolation,
                status=status,
                tokens=tokens,
                cost=cost,
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            if owned:
                session.close()

    async def update_subagent_run(
        self,
        row_id: str,
        *,
        status: str,
        tokens: int | None = None,
        cost: Any = None,
    ) -> None:
        """Flip a ``subagent_runs`` row terminal (default-deny scoped lookup).

        The row is resolved under the owner+workspace scope filter so a cross-owner
        caller can never mutate another owner's child row. A missing/cross-owner row
        is a no-op (the same graceful degrade as the read path).
        """
        from app.models.subagent_run import SubagentRun

        session, owned = self._acquire()
        try:
            query = session.query(SubagentRun).filter(SubagentRun.id == row_id)
            query = self._scope_owner_ws(query, SubagentRun)
            row = query.first()
            if row is None:
                return
            row.status = status
            if tokens is not None:
                row.tokens = tokens
            if cost is not None:
                row.cost = cost
            session.commit()
        finally:
            if owned:
                session.close()

    async def read_subagent_runs(self, parent_run_id: str) -> list[Any]:
        """Return the parent run's owner+workspace-scoped ``subagent_runs`` rows.

        A cross-owner read returns nothing → the FANOUT-10 mitigation proof
        (T-11-01-03).
        """
        from app.models.subagent_run import SubagentRun

        session, owned = self._acquire()
        try:
            query = session.query(SubagentRun).filter(
                SubagentRun.parent_run_id == parent_run_id
            )
            query = self._scope_owner_ws(query, SubagentRun)
            return query.order_by(SubagentRun.created_at.asc()).all()
        finally:
            if owned:
                session.close()

    # ------------------------------------------------------------------
    # wave_runs — per-executed-wave audit (Phase 12 / WAVE-02)
    #
    # wave_runs carries owner_id + workspace_id (AUTHZ-01); every write stamps the
    # helper principal so the default-deny read filter (_scope_owner_ws) scopes them.
    # ONE row is written per executed wave at dispatch time (status='running') by the
    # wave_scheduler strategy through the single kernel run_fanout spawn path, flipped
    # terminal on wave completion. A cross-owner read returns nothing — the T-12-01-IDOR
    # mitigation: a user can never read another owner's wave-scheduling state. This is
    # the durable substrate the mid-wave resume (12-03) reads. Clones the
    # record/update/read_subagent_run recipe EXACTLY.
    # ------------------------------------------------------------------

    async def record_wave_run(
        self,
        run_id: str,
        *,
        step: str,
        wave_index: int,
        task_ids: Any,
        status: str,
    ) -> str:
        """Insert one ``wave_runs`` row stamped with the helper principal (WAVE-02).

        ``status`` ∈ ``running | completed | failed | cancelled`` (free String). The
        row carries owner_id + workspace_id so a cross-owner read returns nothing
        (default-deny, T-12-01-IDOR). Returns the row id.
        """
        from app.models.wave_run import WaveRun

        session, owned = self._acquire()
        try:
            row = WaveRun(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=self._owner_id,
                workspace_id=self._workspace_id,
                step=step,
                wave_index=wave_index,
                task_ids=list(task_ids),
                status=status,
            )
            session.add(row)
            session.commit()
            return row.id
        finally:
            if owned:
                session.close()

    async def update_wave_run(self, row_id: str, *, status: str) -> None:
        """Flip a ``wave_runs`` row terminal (default-deny scoped lookup).

        The row is resolved under the owner+workspace scope filter so a cross-owner
        caller can never mutate another owner's wave row. A missing/cross-owner row is
        a no-op (the same graceful degrade as the read path).
        """
        from app.models.wave_run import WaveRun

        session, owned = self._acquire()
        try:
            query = session.query(WaveRun).filter(WaveRun.id == row_id)
            query = self._scope_owner_ws(query, WaveRun)
            row = query.first()
            if row is None:
                return
            row.status = status
            session.commit()
        finally:
            if owned:
                session.close()

    async def read_wave_runs(self, run_id: str) -> list[Any]:
        """Return the run's owner+workspace-scoped ``wave_runs`` rows (wave_index asc).

        A cross-owner read returns nothing → the T-12-01-IDOR mitigation proof. Ordered
        by ``wave_index`` asc / ``created_at`` asc so the 12-03 resume reads waves in
        execution order.
        """
        from app.models.wave_run import WaveRun

        session, owned = self._acquire()
        try:
            query = session.query(WaveRun).filter(WaveRun.run_id == run_id)
            query = self._scope_owner_ws(query, WaveRun)
            return query.order_by(
                WaveRun.wave_index.asc(), WaveRun.created_at.asc()
            ).all()
        finally:
            if owned:
                session.close()

    async def workspace_budget_spent(self, workspace_id: str | None = None) -> dict:
        """Aggregate the workspace's ALREADY-spent fan-out budget (OBS-01 / default-deny).

        Sums ``subagent_runs`` across ALL of the workspace's runs for THIS owner —
        the per-workspace aggregate ``BudgetManager.reserve`` checks against the
        configured workspace ceiling so a second run in the same workspace is refused
        once the aggregate is exhausted (T-11-04-01 fork-bomb mitigation at the
        workspace grain). Keyed ``owner_id + workspace_id`` (``_scope_owner_ws``) so a
        cross-owner workspace's spend is NEVER counted (default-deny, T-11-04-04: a user
        can never see or be throttled by another owner's workspace aggregate). Returns
        ``{"subagents": <count>, "tokens": <sum>}``; a missing store / cross-owner read
        returns zeros (graceful degrade, the read-path precedent).

        ``workspace_id`` defaults to the helper's principal workspace when omitted.
        """
        from app.models.subagent_run import SubagentRun

        ws_id = workspace_id or self._workspace_id
        session, owned = self._acquire()
        try:
            query = session.query(SubagentRun)
            # Scope to THIS owner; constrain to the target workspace (default-deny).
            query = query.filter(
                SubagentRun.owner_id == self._owner_id,
                SubagentRun.workspace_id == ws_id,
            )
            rows = query.all()
            subagents = len(rows)
            tokens = sum(int(getattr(r, "tokens", 0) or 0) for r in rows)
            return {"subagents": subagents, "tokens": tokens}
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
