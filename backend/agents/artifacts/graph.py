"""agents/artifacts/graph.py — the per-RUN typed artifact substrate.

Phase 5 (ART-01..04). This module defines the typed handoff that replaced the
untyped prior-agent output mirror (a ``dict[str, str]`` carried on the engine,
deleted in 05-07): a typed ``ArtifactRef`` value object (full lineage field set + content-addressed
sha256) and an in-memory ``ArtifactGraph`` that owns hashing/versioning, typed
``produces``/``consumes`` routing, and an in-memory lineage walk.

Import-direction constraint (T-5-PURITY / RESEARCH #1): this module is
KERNEL-IMPORTABLE typed data. It imports ONLY stdlib + ``__future__`` — never
``app.models.*``, never ``app.api.*``, never any ``engine``/``factory``
internals. The dataclass↔ORM-row mapping (the persistence half) lives in the
store helper (05-03, per D-02), NOT here — keeping this file pure lets
``ExecutionContext`` import the graph (05-04) without dragging in ``app.models``
and so the import-linter kernel→ports scaffold stays green.

Scope (INV-12 — no abstraction you don't yet use): the graph is purely
in-memory. Persistence / dual-write is the engine+helper's job (05-03/05-04).
There is deliberately NO ``RuntimeEnvironment``/``Workspace`` field, NO
dedup-on-hash reuse, and NO retention sweep here — all deferred (P9/P12).

``content_hash`` is content-addressing for dedup/lineage, NOT a security control
(T-5-HASH, accept): sha256 over the inline ``content`` is deterministic and
carries no secret material.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# The ``kind`` vocabulary (snake_case — one name everywhere). The engine
# maps each AGENT.md ``produces``/``consumes`` string to one of these in 05-04.
# ``deliverable`` (13-05 / F2) labels the run-completion ref carrying the
# resolved final_output — the generic, workflow-agnostic kind the FR-014
# revision lookup falls back to. ``clarifications`` / ``planning_context``
# are the run-metadata kinds written by the clarify engine and the planner
# seed (real persisted kinds — added in IN-01 so the vocabulary matches
# every production writer).
#
# IN-01 (13 review fix): the vocabulary is ADVISORY-ENFORCED — ``write_ref``
# logs a WARNING (never raises) for a kind outside this set, so a typo'd kind
# that would silently miss every FR-014 chain link is observable in logs
# without breaking any write path. Carve-out: ``*_output`` kinds are the
# FE-supplied revision-target kinds (``ppt_output`` / ``od_ppt_output`` —
# data passing through ``_handle_revision``; a generic suffix, no
# workflow-name literal, SC-001) and do not warn.
ARTIFACT_KINDS: frozenset[str] = frozenset(
    {
        "spec",
        "plan",
        "task_list",
        "html_file",
        "file_bundle",
        "repo_inventory",
        "repo_diff",
        "context_pack",
        "validation_report",
        "merge_conflict",
        "summary",
        "patch",
        "deliverable",
        "clarifications",
        "planning_context",
        # Phase 47 (RESUME-12): the durable mirror of an uploaded document's
        # extracted-text sidecars + manifest snapshot, so a resumed run on a
        # wiped sandbox keeps its uploaded-document context. One kind for BOTH
        # sidecars and manifest, discriminated by ``location``. Additive — no
        # migration (the ``artifact_refs.kind`` column is a free String).
        "upload_text",
    }
)


@dataclass
class ArtifactRef:
    """A typed reference to one produced artifact version (plan §6:454-466 + D-01).

    Pure typed data — no behavior beyond being a record. The graph (not the
    caller) is responsible for assigning ``id``, ``content_hash`` and ``version``,
    so those arrive already computed. Mutable defaults use
    ``field(default_factory=...)`` so two refs never share one ``parents`` list.
    """

    # ── Identity + provenance (required) ─────────────────────────────────────
    id: str  # str(uuid.uuid4()) — assigned by the graph
    kind: str  # one of ARTIFACT_KINDS
    owner_id: str  # owner principal (user_id or anon string) — never None
    workspace_id: str
    run_id: str
    producer_step: str  # the workflow step that produced this (non-null)
    producer_agent: str  # the agent id that produced this (non-null)
    task_id: str | None  # the sub-task id, when produced inside a task loop
    # ── Content (D-01 — inline; the store helper persists this column) ───────
    content: str
    content_hash: str  # sha256(content.encode("utf-8")).hexdigest()
    location: str  # logical path/name (e.g. "spec.md")
    version: int  # 1 + count of prior refs of the same (run_id, kind)
    # ── Lineage + access (defaulted) ────────────────────────────────────────
    parents: list[str] = field(default_factory=list)
    derived_from: str | None = None
    visibility: str = "private"  # plan §6:465 default
    retention: str = "run_ttl"  # default; "keep" / "days:N" override verbatim


class ArtifactGraph:
    """Per-run, in-memory typed registry of ``ArtifactRef``s.

    Owns hashing + per-(run, kind) versioning so the typed contract is enforced
    in one place; supports typed ``consumes`` routing (ART-03) and an in-memory
    lineage walk (ART-01 — no DB recursive CTE; the per-run set is small).
    """

    def __init__(self) -> None:
        # Insertion-ordered registry of refs for this run.
        self._refs: list[ArtifactRef] = []
        self._by_id: dict[str, ArtifactRef] = {}

    # ── Write ────────────────────────────────────────────────────────────────
    def write_ref(
        self,
        *,
        run_id: str,
        owner_id: str,
        workspace_id: str,
        kind: str,
        producer_step: str,
        producer_agent: str,
        task_id: str | None,
        content: str,
        location: str,
        parents: list[str] | None = None,
        derived_from: str | None = None,
        visibility: str = "private",
        retention: str = "run_ttl",
    ) -> ArtifactRef:
        """Create, store, and return a typed ``ArtifactRef``.

        The graph generates ``id``, computes ``content_hash`` as a deterministic
        sha256 over the UTF-8 ``content`` (D-01), and assigns ``version`` as
        ``1 + count of existing refs with the same (run_id, kind)``.

        ``kind`` is advisory-validated against ``ARTIFACT_KINDS`` (IN-01): an
        out-of-vocabulary kind logs a WARNING (it would silently miss every
        typed ``consumes`` route and FR-014 chain link) but the write proceeds —
        the vocabulary must never break a run. ``*_output`` kinds (the
        FE-supplied revision-target kinds flowing through ``_handle_revision``)
        are the documented carve-out and do not warn.
        """
        if kind not in ARTIFACT_KINDS and not kind.endswith("_output"):
            logger.warning(
                "artifact kind %r is outside ARTIFACT_KINDS — typed consumes "
                "routing and the FR-014 revision lookup match kinds EXACTLY, "
                "so a typo here is silently unroutable (IN-01 advisory; "
                "write proceeds)",
                kind,
            )
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        version = 1 + sum(
            1 for r in self._refs if r.run_id == run_id and r.kind == kind
        )
        ref = ArtifactRef(
            id=str(uuid.uuid4()),
            kind=kind,
            owner_id=owner_id,
            workspace_id=workspace_id,
            run_id=run_id,
            producer_step=producer_step,
            producer_agent=producer_agent,
            task_id=task_id,
            content=content,
            content_hash=content_hash,
            location=location,
            version=version,
            parents=list(parents) if parents else [],
            derived_from=derived_from,
            visibility=visibility,
            retention=retention,
        )
        self._refs.append(ref)
        self._by_id[ref.id] = ref
        return ref

    def adopt(self, ref: ArtifactRef) -> ArtifactRef:
        """Insert an already-constructed ``ArtifactRef`` PRESERVING its id/hash/version.

        Durable-resume hydration (12-03 / RESUME-04): on a fresh-process resume the
        in-memory graph is empty, but the durable ``artifact_refs`` carry the outputs of
        the steps that completed before the restart. Re-driving the run at an OFFSET
        skips those steps, so their outputs must be re-seeded into the graph for the
        downstream steps that CONSUME them (e.g. the wave_scheduler step reads the plan
        step's task-list content). Unlike ``write_ref`` (which mints a new id + hash +
        version), ``adopt`` keeps the persisted identity verbatim so content-hash reuse
        + lineage stay stable. Idempotent: re-adopting a known id is a no-op.
        """
        if ref.id in self._by_id:
            return self._by_id[ref.id]
        self._refs.append(ref)
        self._by_id[ref.id] = ref
        return ref

    # ── Read ─────────────────────────────────────────────────────────────────
    def get(self, ref_id: str) -> ArtifactRef | None:
        """Return the ref with ``ref_id`` or ``None`` if not present."""
        return self._by_id.get(ref_id)

    def list_by_kind(self, kind: str) -> list[ArtifactRef]:
        """Return all refs of ``kind`` in insertion order."""
        return [r for r in self._refs if r.kind == kind]

    def consumed_for(self, consumes: list[str]) -> list[ArtifactRef]:
        """Typed routing (ART-03): refs whose ``.kind`` is in ``consumes``.

        Matches on ``ArtifactRef.kind`` equality — never a substring match on
        ids. The engine maps AGENT.md ``consumes`` strings to kinds in 05-04.
        """
        wanted = set(consumes)
        return [r for r in self._refs if r.kind in wanted]

    # ── Lineage ──────────────────────────────────────────────────────────────
    def lineage(self, ref_id: str) -> list[ArtifactRef]:
        """In-memory ancestry walk for ``ref_id`` (ART-01).

        Returns the ref plus every locally-known ancestor reachable via
        ``parents`` / ``derived_from``. Ancestor ids that are not present in this
        per-run graph (e.g. a parent-run source ref id in a revision) are simply
        skipped — only locally-resolvable refs are returned. Cycle-safe.
        """
        start = self._by_id.get(ref_id)
        if start is None:
            return []
        seen: dict[str, ArtifactRef] = {}
        stack: list[str] = [ref_id]
        while stack:
            current_id = stack.pop()
            if current_id in seen:
                continue
            current = self._by_id.get(current_id)
            if current is None:
                continue
            seen[current_id] = current
            for parent_id in current.parents:
                if parent_id not in seen:
                    stack.append(parent_id)
            if current.derived_from and current.derived_from not in seen:
                stack.append(current.derived_from)
        return list(seen.values())

    def tree(self, run_id: str | None = None) -> list[ArtifactRef]:
        """Return all refs (optionally scoped to ``run_id``) in insertion order.

        The full per-run lineage forest; callers (05-03 store helper / the
        ``GET /{id}/artifacts`` endpoint in 05-04) shape this into a nested tree.
        """
        if run_id is None:
            return list(self._refs)
        return [r for r in self._refs if r.run_id == run_id]
