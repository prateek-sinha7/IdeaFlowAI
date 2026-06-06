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

D-01 minimal field set ONLY: just the fields with real backing today. The heavy
later-phase fields (the compiled-workflow plan, the workspace, the artifact graph, the
budget manager, the model resolver, and the workspace identifier) are NOT laid down here —
their types do not exist until Phases 4/9/5/11/6 (INV-12: no abstraction you don't yet
use). The dataclass grows in each later phase as its types land.

Import-direction constraint: this module defines data only. It imports ONLY stdlib +
``__future__`` — never ``agents.factory`` or any ``engine`` internals — so the Phase-1
import-linter kernel→ports scaffold stays green.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
    owner_id: str                                     # owner principal = user_id or "anon" (D-04)

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
