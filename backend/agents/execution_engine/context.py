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
substrate fields: ``artifacts: ArtifactGraph`` (the per-run typed handoff that replaced
the untyped prior-agent output mirror — INV-3, deleted 05-07), ``workspace_id`` (the default per-run
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

import asyncio
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
    # writes ArtifactRefs here (and through the scoped store to the DB) and reads
    # consume() from here — the SOLE artifact source since the prior-agent output
    # mirror was deleted in 05-07 (INV-3/INV-12, L15 ☑).
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
    # model_resolver: the per-run ModelResolver (agents.model_policy.ModelResolver),
    # constructed at execute() entry once the workflow is compiled (so CompiledWorkflow.model
    # seeds tier 4). Consulted at each _run_agent model site to pick the effective model id by
    # the D-02 precedence (override > step.model > AgentSpec.model > workflow.model >
    # session model_id or Haiku). Typed ``object | None`` (NOT the concrete type) — IDENTICAL
    # to ``scoped_store`` above — so this pure-data module gains no inbound import (the resolver
    # imports ``app.core.config``/``agents.workflows``, which this kernel-pure context must not).
    model_resolver: object | None = None
    # model_overrides: the validated per-run ``{agent_id → model_id}`` override map (D-08).
    # Defaults to ``{}`` (this plan; 06-04 wires the WS ingress + catalog validation). Seeds the
    # resolver's tier-1 (user override) and is persisted to ``run_capabilities`` (06-04). Empty
    # dict here ⇒ tier 1 never fires ⇒ the parity default holds (INV-3).
    model_overrides: dict = field(default_factory=dict)
    # runner: the D-03 KernelServices handle (Phase 7) — the SINGLE object the
    # capability strategies/resolvers reach kernel + ``app.*`` primitives through:
    # the run-one-agent-yielding-events primitive (wrapping ``_run_agent`` — create_runner
    # + astream + the MODEL-02 fallback chain + the per-task vs engine thread-id shape
    # ``f"{run_id}:{spec.id}:{task_num}"`` vs ``f"{run_id}:{spec.id}"``), the per-run sandbox
    # (read/write/path_for/root), ``static_check``, ``render_check``, and the sandbox
    # deliverable helpers (``count_sandbox_deliverables``/``serialize_sandbox_deliverable``).
    # Typed ``object | None`` (NOT the concrete type) — IDENTICAL to ``scoped_store``/
    # ``model_resolver`` above — so this pure-data module stays import-pure: the concrete
    # ``KernelServices`` class lives under the kernel (``execution_engine/``) and is attached
    # here by ``execute()`` (07-04); capabilities reach it dynamically via ``ctx.runner`` and
    # NEVER import the kernel/app (the import-linter contract — T-07-01-03).
    runner: object | None = None

    # ── Migrated per-run state (was stashed on the singleton pre-0B) ─────────────────
    # od_context: loaded template / design-system / craft content; flows engine →
    # AgentContext per agent for od_prototype / od_ppt `injects`.
    od_context: dict | None = None
    # run_images: transient per-run image carrier holding normalized
    # {mime_type, data(base64)} entries, consumed by the ``run_images`` input_provider
    # capability (image-input Wave 1). Default None ⇒ dormant (no image flow).
    run_images: list | None = None
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
    # build_task_number / build_task_total: the current/total build-loop task counters
    # injected into the `=== CURRENT TASK ===` marker. NON-artifact build-loop scratch —
    # relocated here (off the deleted prior-agent output dict) in 05-07 so the typed
    # ArtifactGraph carries only genuine artifacts (INV-3). Phase 7 moves these into the
    # TaskLoopStrategy alongside current_task_block.
    build_task_number: str = ""
    build_task_total: str = ""
    # failed_invocations: ISS-028 — the set of ``(agent_id, task_number)`` pairs whose
    # ``_run_agent`` invocation surfaced an ``agent_error`` and did NOT recover (no
    # ``results`` entry for the SAME pair). The terminal degraded decision subtracts the
    # COMPLETED ``(agent_id, task_number)`` pairs from this set, so a same-agent task_loop
    # where task K completes but task K+1 hard-errors is correctly ``degraded`` (the
    # agent_id-only subtraction it replaced zeroed it out — a half-built deliverable
    # reported as a clean ``pipeline_complete``). ``task_number`` is "" for a single_shot
    # agent, so the single-invocation timeout-recovery case (WR-05) still subtracts
    # cleanly. Empty for every all-success run → DORMANT on the characterization goldens
    # (the scripted model never errors mid-loop), so INV-3 byte-parity holds. Per-run
    # (CTX-02 — never on the engine singleton).
    failed_invocations: set = field(default_factory=set)

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

    # ── Run-wide odds and ends ────────────────────────────────────────────────────────
    # (The sanctioned temporary prior-agent output mirror was DELETED in 05-07 once the
    #  typed ``ArtifactGraph`` was proven the sole source — INV-3/INV-12, L15 ☑.)
    # cancel_event: cooperative cancellation signal (the Stop button); checked per chunk.
    cancel_event: object | None = None
    # disk_skills: per-user disk SKILL.md overrides, keyed by agent id, loaded once/run.
    disk_skills: dict = field(default_factory=dict)
    # prewarmed_constitution: the owner's Constitution, awaited ONCE at run entry (before
    # the SYNC create_runner calls) and threaded into each per-agent AgentContext so the
    # sync factory reads it WITHOUT awaiting inside the running event loop (AGENTRT-06 /
    # F4 / R12 — the production no-op fix). None ⇒ no Constitution set (graceful no-op;
    # the characterization runs carry none → snapshots byte-identical). Pre-warm at run
    # entry is the lower-risk option (RESEARCH A3 / D-08): no await-in-running-loop hazard.
    prewarmed_constitution: str | None = None
    # depth: sub-run nesting depth (0 = top-level run). Reserved for the fan-out phases.
    depth: int = 0
    # budget: the per-run fan-out BudgetManager (Phase 11 / FANOUT-09). A PER-RUN object
    # (INV-2 — never on the engine singleton) carrying the resolved caps; the single
    # kernel run_fanout spawn path calls ``budget.reserve(...)`` BEFORE any spawn
    # (Pitfall 4 enforcement-point discipline). ``reserve()`` is a no-op stub this plan;
    # the raising enforcement lands 11-04. None ⇒ no budget bound (a direct unit-style
    # invocation) ⇒ run_fanout skips the reserve call (graceful no-op). Typed
    # forward-ref ``object | None`` to keep this pure-data module free of the budget import.
    budget: object | None = None
    # ── Deliverable routing (07-05) ─────────────────────────────────────────────────
    # deliverable: the compiled DeliverableSpec (strategy + name) for this run, set at
    # run entry from ``compiled.deliverable`` so the per-agent mid-stream transforms in
    # ``_run_agent`` (the single-file disk readback + the ppt carousel sanitize) key off
    # the DECLARED deliverable strategy — NOT a ``pipeline_type`` name-branch (INV-1).
    # Replaces the former L10 prototype-name readback gate and the L3 ppt-name-set
    # mid-stream sanitize gate (both deleted from the kernel in 07-05).
    deliverable: object | None = None
    # last_streamed: the final agent's streamed output, set just before the deliverable
    # resolver runs so the resolver capability reads it off ctx (single_file / ppt /
    # streamed_text fallbacks). Typed ``object``-free str default.
    last_streamed: str = ""
    # seed_files: the DECLARED ``compiled.seed_files`` dict (Q29 / CR-07), threaded onto
    # the context at run entry so the ``previous_run`` provider + the ``task_loop``
    # reference-file writer read the DECLARED seed list (honoring the
    # ``seed_files.from_run`` declared surface) instead of the hardcoded
    # ``("spec.md","design.md","tasks.md")`` constant. All authored manifests are ``{}``
    # so the consumers fall back to the legacy triple — byte-identical (Pitfall 2). The
    # compiler stays thin (INV-5): it only carries the declaration; control flow lives in
    # the provider/strategy.
    seed_files: dict = field(default_factory=dict)
    # current_step: the compiled ``Step`` currently being run (08-08 / CR-01). Set by
    # KernelServices.run_agent for the duration of one agent invocation + reset after
    # (the same scratch idiom as build_task_number/current_task_block). The engine's
    # before_write hook firing in _run_agent reads ``current_step.hooks`` so hook
    # firing is DECLARATION-DRIVEN: only the hooks the step DECLARES fire. None ⇒ no
    # step bound (a direct unit-style _run_agent invocation) ⇒ no hooks fire (parity).
    # Typed ``object | None`` to keep this pure-data module free of the plan import.
    current_step: object | None = None
    # is_revision_workflow: True when the run's manifest declares the ``previous_run``
    # context provider (a revise-prior-run workflow). Gates the per-agent single_file
    # MID-STREAM disk readback in _run_agent off (the legacy L10 readback excluded the
    # revision path — a revision's mid-stream output is the edited streamed text, not a
    # fresh disk file); the FINAL single_file deliverable resolver still reads the file.
    is_revision_workflow: bool = False
    # is_resuming: True when this run is a durable IN-PROCESS RESUME of a run
    # interrupted by a backend restart (RESUME-04 / WAVE-03, set by resume_run before
    # re-entering the dispatch loop at the first incomplete step). The wave_scheduler
    # strategy reads it to enable MID-WAVE resume: a completed wave (terminal wave_runs
    # row) is skipped wholesale, and within the in-flight wave only the workers WITHOUT
    # a terminal subagent_runs row are re-fanned-out (completed fragments were made
    # durable pre-merge in Phase 11). ``False`` for every normal run ⇒ the strategy is
    # byte/event-identical (the mid-wave filter is dormant).
    is_resuming: bool = False
    # The RESUME-09 per-step SKIP CURSOR (field below) — the set of
    # already-completed task/worker identities per step, KERNEL-COMPUTED from the
    # run's own owner-scoped durable rows (task_loop step: the DISTINCT ``task_id``
    # set from ``store.tree`` where ``producer_agent == step agent``; wave step: the
    # ``task_id`` set from ``read_subagent_runs`` where ``status == "complete"``) and
    # stamped BEFORE the dispatch loop re-enters. The strategies READ it via a
    # ``getattr(ctx, <field>, None)`` handle and SKIP the completed
    # identities — the AGENT never decides the skip set (it still RECEIVES completed
    # work as injected context via the unchanged ``latest_typed_content`` machinery;
    # re-invocation of remaining work stays on the same ``run_agent``/``run_fanout``
    # paths — INV-13). The read is a ``getattr(ctx, <field>, None)`` so an older ctx
    # without the field degrades to no-skip. Keyed on ``task_id`` (plan-global,
    # identity-based) NOT
    # ``worker_index`` (wave-local, ambiguous — Edge-Case 5); a ``set`` de-dups the
    # fix-loop re-persist of the same task_id (Edge-Case 1). Fail-safe direction is
    # RE-RUN: any read failure / ambiguity leaves this ``None`` so nothing is skipped
    # (data-loss-avoiding). ``None`` on every normal (non-resume) run so the strategies'
    # ``getattr`` read is None and dispatch is byte/event-identical (INV-3 dormant;
    # mirrors ``is_resuming``). Transient per-run scratch on the context (INV-2 — never
    # the engine singleton). ``{step_agent_id: {task_id, ...}}``.
    resume_completed_task_ids: "dict[str, set[str]] | None" = None
    # resume_completed_ordered (RESUME-16 cumulative): for a task_loop step, the SAME
    # completed keys as ``resume_completed_task_ids`` but in original build ORDER (by
    # ``min(version)`` per task_id) — the ORDER the common-prefix reconcile needs (a SET
    # cannot express "skip the matching PREFIX, re-run the divergence suffix"). Waves need
    # no order (per-key set-membership). ``None`` on every normal run ⇒ empty prefix ⇒
    # dispatch byte/event-identical (INV-3 dormant). Transient per-run scratch (INV-2).
    # ``{task_loop_step_agent_id: [task_key, ...]}``.
    resume_completed_ordered: "dict[str, list[str]] | None" = None
    # redo_directive: the optional free-text "redo with additional instructions"
    # note for a human-review-gate re-run (REDO-GATE). Additive per-run scratch (the
    # same D-03 idiom as build_task_number / current_step), so the generic
    # _compose_context_message injector can append a `=== ADDITIONAL INSTRUCTIONS
    # (REVISE) ===` block on a re-run WITHOUT a signature change (no test blast
    # radius). The set/clear discipline lives in _run_agent's redo loop: it is
    # published to ectx ONLY around the compose call for the re-run and cleared
    # UNCONDITIONALLY right after, so an empty-output / errored / non-redo path can
    # never leak it onto the next agent (consume-once, F3). Default-empty ⇒ DORMANT
    # on every non-redo run (no block appended) ⇒ INV-3 byte-parity holds. The
    # ``derived_from`` lineage of a re-run is intentionally NOT an ectx field — it is
    # a _run_agent loop local so it cannot leak across agents (F3).
    redo_directive: str = ""
    # spec_revision_prior_artifact: the PRIOR version of the artifact an agent is being
    # asked to amend, published for exactly ONE dispatch. Joins the consume-once
    # injection-seam family (``redo_directive`` / ``spec_revision_context`` /
    # ``steering_notes``) and follows its discipline exactly.
    #
    # TWO publishers, ONE field and ONE renderer (INV-12 — the alternative was a second
    # field and a second block meaning the same thing):
    #   * ``_run_spec_revision_sub_pipeline`` sets it immediately before the specify
    #     sub-dispatch and RESTORES it in the same ``finally`` that restores
    #     ``spec_revision_context`` (BUGFIX-SPEC-REVISION-CONTEXT D1 / FIX-217);
    #   * ``_run_agent``'s redo loop sets it around the re-run's compose call and restores
    #     it immediately after (ISS-086 / FIX-228) — a "Request changes" re-run is an
    #     amendment, and the agent cannot amend a document it cannot see.
    # Both publishers SAVE/RESTORE rather than clear, because a redo can fire at a gate
    # opened inside a revision pass: zeroing there would strip the outer pass's own
    # subject mid-flight (the quick-260811-si4 defect-A shape).
    #
    # It is the agent's ONLY channel to its own prior output: self-consumption is
    # structurally impossible (``_filter_consumed_outputs`` breaks on
    # ``upstream.id == spec.id``), the re-run threads a FRESH checkpoint id so nothing is
    # replayed, and the gated authoring agents declare ``consumes: []`` + ``tools: []``.
    # Default-empty ⇒ DORMANT on every non-revision, non-redo dispatch (no block appended)
    # ⇒ INV-3 byte-parity holds. Transient per-run scratch (INV-2 — never the singleton).
    spec_revision_prior_artifact: str = ""
    # spec_revision_context: the ANALYSIS REPORT a revision pass is acting on, published
    # for the pass's dispatches so ``_compose_context_message`` can render the revision
    # block (KAN-101). The third member of the consume-once injection-seam family beside
    # ``redo_directive`` and ``spec_revision_prior_artifact``, and set/cleared by the same
    # ``_run_spec_revision_sub_pipeline`` try/finally.
    #
    # DECLARED here as of quick-260811-si4. It has worked as an UNDECLARED attribute only
    # because ``ExecutionContext`` is a non-slots dataclass, which meant a bare read on a
    # fresh context raised ``AttributeError`` and every caller had to spell
    # ``getattr(ectx, "spec_revision_context", "")``. The sub-pipeline's re-entrancy
    # save/restore reads the field at entry, so it needs a real default. Behaviour is
    # identical (the renderer already guards on truthiness) — default-empty ⇒ DORMANT on
    # every non-revision dispatch ⇒ INV-3 byte-parity holds. Transient per-run scratch
    # (INV-2).
    spec_revision_context: str = ""
    # revision_attempt: the revision sub-pipeline's index, published so ``_run_agent``
    # can derive a FRESH ``:rev{N}`` checkpoint thread for the re-run. Without it the
    # revision reuses the first pass's thread and correctness depends on the
    # checkpointer replaying that turn — the P23 replay class the ``:redo{N}`` and
    # ``:retry{n}`` suffixes already close (BUGFIX-SPEC-REVISION-CONTEXT D3). Mirrors
    # ``_run_agent``'s ``redo_attempt`` local; named distinctly from that function's
    # ``spec_revision_attempt`` local so the two are not confused for one another.
    # Default 0 ⇒ DORMANT (no suffix) ⇒ INV-3 byte-parity holds. Transient per-run
    # scratch (INV-2).
    revision_attempt: int = 0
    # revision_high_water: a MONOTONE per-run mark of the highest revision index ever
    # published by ``_run_spec_revision_sub_pipeline``. Unlike every other member of this
    # scratch family it is deliberately **never cleared and never restored** — that is its
    # entire job.
    #
    # ``_run_agent``'s ``spec_revision_attempt`` is a per-INVOCATION local, so a revision
    # pass that re-enters itself (the analyze re-run inside a pass is itself gated, and the
    # gate ACTION is client-controlled — the eligibility flag is an FE affordance the engine
    # never enforces) has two levels each computing index 1 and each minting the SAME
    # ``:rev1`` checkpoint thread id. The second pass is then served the first pass's
    # LangGraph conversation replay — the P23 class the ``:redo{N}`` and ``:retry{n}``
    # suffixes already close. The sub-pipeline derives its EFFECTIVE index from this mark
    # (``revision_index if it exceeds the mark else mark + 1``), so no two passes — sibling
    # or nested, at any depth — can collide (BUGFIX-NESTED-REVISION defect A).
    #
    # Default 0 ⇒ a first cycle still resolves to 1 ⇒ ``:rev1`` unchanged ⇒ DORMANT on every
    # non-revision run ⇒ INV-3 byte-parity holds. Transient per-run scratch (INV-2), no
    # storage: no migration, no table, no column.
    revision_high_water: int = 0
    # steering_notes: the consume-once MID-RUN steering queue (D-06 / CHAT-03 /
    # ND-11 — the THIRD member of the consume-once injection-seam family beside
    # ``redo_directive`` and KAN-101's ``spec_revision_context``; COEXIST, not
    # unify, per ND-11-SEAM-DECISION.md). A user message to a RUNNING run cannot
    # be injected mid-generation (an agent invocation runs to completion — D-03),
    # so the mechanical router (29-09) ENQUEUES it here and the generic
    # ``_compose_context_message`` injector renders the pending notes as a single
    # ``=== USER GUIDANCE ===`` block at the NEXT agent dispatch (the marker family
    # the chat launch surface strips — POR §6), then CLEARS them (read+clear during
    # composition — the consume-once key-link). Each entry is a
    # ``{"text": str, "sticky": bool}`` dict: a ONE-SHOT directive (``sticky``
    # False) is rendered once then dropped; STICKY (uploaded-context) notes
    # (``sticky`` True) persist and re-render on every subsequent dispatch (D-06
    # sticky-vs-one-shot). Additive per-run scratch (the same D-03 idiom as
    # ``redo_directive``) so the injector appends the block WITHOUT a signature
    # change. Transient (NOT a durable field): across ``resume_run`` it is
    # re-derived from the persisted ``run_events`` chat turns (ND-9 / 29-02), so
    # no new column/table is added here (LOCK-B). Steering keys on THIS generic
    # queue only — no workflow/agent name branch (SC-001/INV-1). Default-empty ⇒
    # DORMANT on every golden run (no block emitted, no mutation) ⇒ INV-3
    # byte-parity holds.
    steering_notes: list = field(default_factory=list)
    # pending_turn_images: the consume-once MID-RUN per-turn image queue (UPLD-02
    # residue, 30-03). The IMAGE analogue of ``steering_notes``: images attached to
    # an in-flight chat turn on the Phase-29 ``POST /api/runs/{id}/messages`` path are
    # cap-validated (the shared ``_validate_images`` ingress caps) then enqueued here
    # by ``chat_router.apply_turn_images``. The engine DRAINS this queue onto the
    # ONE-SHOT ``turn_images_once`` carrier (below) at the NEXT dispatch (before
    # ``_compose_input_blocks``) so an ``injects:[images]`` agent's HumanMessage carries
    # the base64 image content-blocks — exactly where run-entry images already flow.
    # Each entry is a normalized ``{mime_type, data(base64)}`` dict (mirrors
    # ``_normalize_run_images``). PAYLOAD-TRANSIENT (ND-10/LOCK-E): never persisted to
    # sandbox/DB/run_events — the durable ``chat_message`` row keeps its attachment refs
    # stamped ``retained:false`` (no bytes); across ``resume_run`` this queue is empty
    # (ND-9 — images do not survive replay/reopen). Additive per-run scratch (the same
    # D-03 idiom as ``steering_notes``) keyed on THIS generic queue only — no
    # workflow/agent name (SC-001/INV-1). Default-empty ⇒ DORMANT on every golden run
    # (no image → nothing drained → dispatch payload byte-identical) ⇒ INV-3.
    pending_turn_images: list = field(default_factory=list)
    # turn_images_once: the CONSUME-ONCE render carrier for per-turn images (30-03,
    # HI-01). DISTINCT from the sticky run-entry ``run_images`` above: ``run_images`` is
    # set once at run entry and the ``run_images`` provider re-renders it on EVERY
    # ``injects:[images]`` dispatch (legitimately sticky for the whole run), whereas this
    # one-shot carrier holds only the images ``_drain_turn_images`` moved off
    # ``pending_turn_images`` for the NEXT dispatch. ``_compose_input_blocks`` renders it
    # into exactly THAT dispatch's blocks and then clears it (read+clear co-located, the
    # ``steering_notes`` idiom), so a per-turn image reaches ONE dispatch and never
    # re-delivers on a later one. (Draining per-turn images onto the sticky ``run_images``
    # instead was the pre-fix bug: every subsequent dispatch re-attached the stale image.)
    # Default-empty ⇒ DORMANT on every golden run (nothing to render) ⇒ INV-3 byte-parity.
    turn_images_once: list = field(default_factory=list)

    # ── KRN-005 (task.md R-03): scratch-mutation serialization for concurrent
    # fan-out children ────────────────────────────────────────────────────────
    # scratch_lock: guards the save/mutate/dispatch/restore window
    # ``KernelServices.run_agent`` uses to bind per-invocation scratch
    # (``current_step``, ``build_task_number``, ``build_task_total``,
    # ``current_task_block``, ``current_prototype_skeleton``) onto this ONE
    # shared ``ExecutionContext``. A parallel fan-out spawns N children under
    # ``asyncio.gather``, and every child's ``run_worker`` -> ``run_agent`` calls
    # land on the SAME ``ctx.runner`` (one ``KernelServices`` instance) and
    # therefore the SAME ``ectx`` (INV-2 is about the ENGINE singleton, not
    # about isolating siblings from each other — fan-out children were never
    # given separate contexts). Two children's save/restore windows interleaving
    # is a genuine data race: child A saves its `prev_*`, child B's write
    # clobbers A's fields mid-flight, A's own `finally` restore then overwrites
    # B's still-in-flight values with A's stale snapshot — either child can end
    # up running (or being torn down) under the WRONG task/step scratch.
    #
    # This lock does not clone or isolate context — the read-only handles
    # (``runner``, ``budget``, ``scoped_store``, ``artifacts``) still legitimately
    # need to be one shared kernel surface — it only makes the scratch
    # save-mutate-restore window ATOMIC per invocation, so concurrent children
    # serialize through it one at a time instead of interleaving. This trades
    # away true concurrency of the SCRATCH-BINDING step only (a few attribute
    # writes) while the actual agent invocation (the slow, network-bound part)
    # still runs unlocked/concurrently — see the lock's acquire/release site in
    # ``KernelServices.run_agent``.
    #
    # A fresh, unshared ``asyncio.Lock()`` per run (default_factory — never one
    # instance reused across runs, which would serialize UNRELATED concurrent
    # runs against each other). Typed ``object`` (not ``asyncio.Lock`` directly)
    # to avoid importing asyncio's lock type into type-checking call sites that
    # don't need it; the runtime value is always a real ``asyncio.Lock``.
    scratch_lock: object = field(default_factory=asyncio.Lock)
