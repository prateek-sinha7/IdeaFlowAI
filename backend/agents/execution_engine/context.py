"""agents/execution_engine/context.py — the per-RUN ``ExecutionContext`` value object.

Phase 0B (CTX-01 / CTX-02). The ``ExecutionEngine`` is a process-wide singleton; before
this phase it stashed every per-run datum (od_context, completed-task list, revision
baselines, the acquired checkpointer, …) on ``self``, so concurrent / fan-out runs would
have shared and clobbered each other's state (the INV-2 hazard). ``ExecutionContext`` lifts
all of that off the kernel: ``execute()`` constructs ONE instance per run and threads it
explicitly through the call tree (D-03 — an explicit parameter, never ``contextvars``).
After the lift the kernel holds only its three construction-time singletons
(``_resolver`` / ``_store`` / ``_state_machine``) and is stateless after ``__init__``.

This is the engine-level, per-RUN container. It is DISTINCT from
``agents/factory.py::AgentContext``, which is per-AGENT (rebuilt for every
``create_runner`` call). They coexist — do not conflate them.

D-01 minimal field set ONLY: just the fields with real backing today. The dataclass
grows in each later phase as its types land. Phase 5 (05-04) lands the FIRST typed
substrate fields: ``artifacts: ArtifactGraph`` (the per-run typed handoff that replaces
the untyped ``accumulated_outputs`` mirror — INV-3), ``workspace_id`` (the default per-run
workspace row id — D-04), and ``disk_principal`` (the decoupled byte-identity-guard
principal — D-09; see below). The remaining heavy later-phase fields (the compiled-workflow
plan, the budget manager, the model resolver) are still NOT laid down here — their types do
not exist yet (INV-12: no abstraction you don't yet use).

Import-direction constraint: this module defines data only. It imports ONLY stdlib +
``__future__`` + ``agents.artifacts.graph`` (the kernel-importable pure typed substrate,
which itself imports only stdlib — RESEARCH #1) — never ``agents.factory``, never
``app.models``/``app.api``, never any ``engine`` internals — so the Phase-1 import-linter
kernel→ports scaffold stays green. The single ``agents.artifacts`` import is intentionally
allowed because the graph is pure data with no ``app.*`` reach (05-04).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.artifacts.graph import ArtifactGraph


@dataclass
class ExecutionContext:
    """Per-run state for one ``ExecutionEngine.execute()`` invocation.

    Plain mutable ``@dataclass`` (NOT frozen): the prototype build loop appends to
    ``completed_tasks`` and reassigns ``current_task_block`` mid-run, and the revision
    seeding block populates the ``revision_*`` fields. Mutable defaults use
    ``field(default_factory=...)`` so two runs never share one list/dict/set instance.
    """

    # ── Run identity (required; populated at construction) ──────────────────────────
    run_id: str                                       # this run's pipeline_run_id
    # owner_id: the PERSISTED DB principal (AUTHZ-03/D-09). From 05-04 it is
    # ``user_id or f"anon:{session_id}"`` — ALWAYS a real non-None scoped subject (an
    # unauthenticated run gets ``anon:<session_id>``, never None). DO NOT key any on-disk
    # path off this field — disk keying uses ``disk_principal`` (the byte-identity guard,
    # below) which stays ``user_id or "anon"`` so anon runs' sandbox paths are unchanged.
    owner_id: str

    # ── Typed substrate + workspace (Phase 5 / 05-04) ────────────────────────────────
    # artifacts: the per-run in-memory typed artifact graph (ART-01). The engine
    # dual-writes ArtifactRefs here (and through the scoped store to the DB) alongside the
    # still-live accumulated_outputs mirror, and reads consume() from here (05-04). The
    # mirror is removed in 05-06 once parity proves the cutover (INV-3).
    artifacts: ArtifactGraph = field(default_factory=ArtifactGraph)
    # workspace_id: the default per-run workspace row id (D-04), created at execute() entry
    # via ScopedStore.create_workspace(run_id). Stamped on every persisted artifact_refs /
    # run_events / run_capabilities row for the AUTHZ-01 owner+workspace scope filter.
    workspace_id: str = ""
    # disk_principal: the DECOUPLED on-disk sandbox principal (byte-identity guard, D-09 /
    # CTX-05). Stays ``user_id or "anon"`` — the SAME value RunSandbox keyed disk with
    # before 05-04. Decoupling it from owner_id lets owner_id become anon:<session_id> (the
    # DB principal) WITHOUT changing any RunSandbox/create_runner disk path. For authed runs
    # disk_principal == owner_id == user_id; only anon runs differ. No disk-keying site may
    # use owner_id (Task 1 grep gate) — pass disk_principal there.
    disk_principal: str = ""
    # scoped_store: the per-run owner+workspace-scoped store helper
    # (``agents.authz.ScopedStore``) constructed at execute() entry. Threaded here so the
    # seq sink (05-04 Task 2 — append_event) and the typed dual-write (Task 3 — write_ref)
    # reuse the SAME scoped principal. Typed ``object | None`` (NOT the concrete type) so
    # this pure-data module stays free of the helper's ``app.models`` import (the helper
    # lives in the DB-touching ``agents.authz``, not the kernel-pure ``agents.artifacts``).
    scoped_store: object | None = None

    # ── Migrated per-run state (was stashed on the singleton pre-0B) ─────────────────
    # od_context: loaded template / design-system / craft content; flows engine →
    # AgentContext per agent for od_prototype / od_ppt `injects`.
    od_context: dict | None = None
    # completed_tasks: cumulative prototype task-completion list. RUN-LEVEL (the build
    # loop calls _run_agent once per task; a per-call local would make completed_count
    # non-monotonic — a visible UI regression). Appended in _run_agent.
    completed_tasks: list[dict] = field(default_factory=list)
    # gate_agent_ids: per-run HITL gate selection. None ⇒ the static AGENT.md
    # `gate: Human_Gate` set (today's behavior); a list ⇒ gate exactly those ids.
    gate_agent_ids: list[str] | None = None
    # parent_run_id: prototype_revision only — the original run whose spec/design/tasks
    # are seeded into this run's sandbox.
    parent_run_id: str | None = None
    # checkpointer: the process-wide cached LangGraph checkpointer (get_checkpointer()).
    # Acquired once per run and threaded into every create_runner; never closed per-run
    # (app-shutdown concern). Only its STORAGE location moves onto the context.
    checkpointer: object | None = None
    # current_task_block: the current `## Task N:` block injected into the build prompt.
    # D-02 TEMPORARY home — Phase 7 relocates this into TaskLoopStrategy (strategy-local
    # scratch lives in the strategy, not on ctx; no strategy exists yet in 0B).
    current_task_block: str = ""

    # ── Prototype-revision group (set defaults; conditionally populated in execute()) ─
    # revision_original_html: the seeded ORIGINAL prototype.html (pre-edit); read back
    # as the deliverable fallback.
    revision_original_html: str = ""
    # revision_instruction: the user's revision request, re-injected into the fix prompt.
    revision_instruction: str | None = None
    # revision_baseline_static: static-issue signatures of the pre-edit prototype, so the
    # fix-loop treats only NEW static issues as regressions.
    revision_baseline_static: set[str] = field(default_factory=set)
    # revision_baseline_console: console-error signatures of the pre-edit render (empty
    # when render is unavailable).
    revision_baseline_console: set[str] = field(default_factory=set)

    # ── Legacy mirror + run-wide odds and ends ───────────────────────────────────────
    # accumulated_outputs: the sanctioned temporary mirror (removed in a later phase per
    # INV-3). Kept here for the run-wide prior-agent output map.
    accumulated_outputs: dict[str, str] = field(default_factory=dict)
    # cancel_event: cooperative cancellation signal (the Stop button); checked per chunk.
    cancel_event: object | None = None
    # disk_skills: per-user disk SKILL.md overrides, keyed by agent id, loaded once/run.
    disk_skills: dict = field(default_factory=dict)
    # depth: sub-run nesting depth (0 = top-level run). Reserved for the fan-out phases.
    depth: int = 0
