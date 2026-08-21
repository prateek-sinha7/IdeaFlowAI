# 014 — Conditional Gates: Implementation Plan

**Spec**: [spec.md](spec.md) (28 requirements, 4 in-scope examples A1–A4, 4 deferred examples
B1–B4, 3 clarification rounds, 4 gaps closed as R-26/R-27 + 2 verified non-gaps)
**Grounding**: [reports/conditional-gates.md](reports/conditional-gates.md) — file/line-level
impact analysis
**Reference fixtures**: `backend/agents/workflows/sample_conditional_{previous_step,branch_new,
launch_new,target,human_input}/workflow.yaml` — checked in, `user_launchable: true`, currently
fail to compile (this plan is what makes them compile and run)

---

## 1. Goal & scope

**Problem.** The workflow compiler + engine execute a strict, cycle-free, linear sequence —
`for i, spec in enumerate(ordered_agents):` (`engine.py:2586`). No workflow can loop back to an
earlier step, branch to one of several continuations, or hand off to a different workflow
entirely. The existing gate vocabulary (`human`/`validation`/`approval`/`security`) only ever
resolves to `pass | block | wait_human` — none of them can redirect *where execution goes next*.

**Goal.** Add a `conditional` gate type such that:
- Any existing agent step can declare `gates: [conditional]` + a sibling `route:` block —
  no new step kind, no new compiled-step-graph shape (R-01/R-02).
- A step's own or an earlier step's captured decision (agent-produced, or a prior human gate's
  response) routes execution forward, backward (loop), or to a genuinely different workflow run
  — via one unified `outcomes: {condition_value: {trigger, target}}` map (R-05b, decision-log
  #11).
- In-workflow routing is a cursor move inside the SAME `WorkflowRun` (R-06). Cross-workflow
  triggering mints a SECOND, independent `WorkflowRun` linked by the pre-existing
  `parent_run_id` column, and the triggering run stops (R-12/R-13, "Option 2" — no v1 wait/
  resume).

**Non-goals (§5 of spec.md, restated for planning)**: multi-target fan-out from one outcome,
the Merge/Join Node (B2), synchronous `wait: true` triggering (B3), context-seeded triggers
(B4), a stitched run-history timeline, shared/team-owned workflow triggering, run-time route
editing via `selections.py`. None of these are touched by any phase below.

---

## 2. Constitution check — this repo's locked invariants

Cross-checked against `backend/CLAUDE.md` and the invariants already enforced by
`compiler.py`/`registry.py` (no separate constitution file exists in this repo — see §018 of
`003-workflow-engine-decoupling/plan.md` for the historical INV-numbered set this project
inherits):

| Invariant | How this plan honors it |
|---|---|
| **No-DSL (INV-5 / D-08)** — manifests are pure data, no control-flow keys | `route:` is pure data (dict of dicts), strict-key-validated (`_ALLOWED_ROUTE_KEYS`), exactly like `fanout:`. No `if:`/`when:`/`${...}` expression syntax anywhere (R-02). |
| **Registry name-resolution only (INV-4)** — capabilities resolve by `(kind, name)`, never dynamic import | `("gate", "conditional")` is a static `_KNOWN` entry, `resolve()` stays a dict lookup (R-01). |
| **Kernel stays workflow-agnostic** | `ConditionalGate.evaluate()` has zero `pipeline_type`/agent-id branches — it reads `route.outcomes` generically, same as every other gate. |
| **Additive-only events (INV-3)** | `pipeline_diverted` (R-28) is a NEW event type, not a repurposed `pipeline_complete` — existing handlers unaffected by construction. |
| **Migrations additive only** | R-14's new `"diverted"` status and R-26's `is_leaf` field need NO schema migration — `TERMINAL_STATES` is a Python frozenset, `Step.is_leaf` is a compiled-plan dataclass field, not a DB column. `parent_run_id` (R-15) is reused unmodified — zero migrations this entire spec. |
| **Ownership/authz (INV-8 / AUTHZ-01)** | R-15's unconditional owner/workspace inheritance follows the exact `SubagentRun`/`previous_run.py` precedent — no new ownership model invented. |
| **Fail-closed budgets** | R-07 (loop cap) and R-18 (trigger-depth cap) both reuse the existing `BudgetExceeded` pattern — no new exception type, no silent runaway. |

**No constitution violations requiring justification.** Every new mechanism in this spec mirrors
an existing, already-reviewed pattern (`fanout:` for `route:`, `SubagentRun`'s owner columns for
R-15, `BudgetExceeded` for the two new caps, `pipeline_cancelled`'s additive-event precedent for
`pipeline_diverted`). This is the single strongest signal this spec is *extension*, not
*architecture change* — confirmed again during planning.

---

## 3. Phase 0 — Research (unknowns resolved)

Spec.md's Clarifications + Decision Log already resolved every `NEEDS CLARIFICATION`-class
question raised during specification (28 requirements, 0 open markers — confirmed by the
`/speckit-clarify` pass). Two implementation-level unknowns remain, both scoped to a single
phase below rather than blocking the whole plan:

- **UNKNOWN-1**: `launch_run`'s exact HTTP-vs-core extraction boundary (R-16, RISK-04 in
  spec.md). Resolved by reading `app/api/run_commands.py:2213` end-to-end in Phase 4 (below),
  not deferred further — this is implementation research, not a product decision.
- **UNKNOWN-2**: `gate_events` audit-row keying under revisit (flagged as a deferred item at
  the end of the `/speckit-clarify` session — `record_gate_event`'s `(step, gate, outcome)`
  keying may have the same collision class R-08 already fixed for `gate_key`/
  `failed_invocations`). Resolved by inspecting `kernel_services.py:337-360` in Phase 1 (below)
  and extending the same visit-count-aware keying if the collision is real.

**Output**: both resolved inline in their respective phases below (see Phase 1 task 4, Phase 4
task 1) — no separate `research.md` needed; the spec's own Clarifications section already
serves that role for every product-level unknown.

---

## 4. Phase 1 — Data model & compiler (backend, no engine change)

**Scope**: `RouteSpec`/`RouteOutcome` dataclasses, the `route:` compiler pass, the
`("gate", "conditional")` registry entry, R-26's `is_leaf` computation, R-27's `produces` check.
**Zero engine.py changes in this phase** — the dispatch loop conversion is isolated to Phase 3
per RISK-02's explicit recommendation.

1. **`agents/workflows/plan.py`** — add `RouteOutcome` (`trigger: str`, `target: str`) and
   `RouteSpec` (`condition_agent: str | None`, `outcomes: dict[str, RouteOutcome]`,
   `default_next: str | None`, `loop_max_iterations: int = 5`, `trigger_max_depth: int = 5`).
   Add `Step.route: RouteSpec | None = None` and `Step.is_leaf: bool = False` (R-26 — computed
   by the compiler, not authored). *(R-01/R-02/R-04/R-05/R-26)*

2. **`agents/workflows/compiler.py`**:
   - Add `"route"` to `_ALLOWED_STEP_KEYS`; add `_ALLOWED_ROUTE_KEYS = {"condition_agent",
     "outcomes", "default_next", "loop_max_iterations", "trigger_max_depth"}` and
     `_ALLOWED_OUTCOME_KEYS = {"trigger", "target"}`.
   - Add `_compile_route()` mirroring `_compile_fanout()` (`:999`) — strict-key reject, coerce
     each `outcomes[...]` dict to a `RouteOutcome`. *(R-02)*
   - Cross-field check (R-03): if `"conditional"` is declared in a step's `gates:` but
     `route` is `None`/empty `outcomes`, OR `route` is non-empty but `"conditional"` is absent
     from `gates:`, raise `CompilerError`. This is a NEW *kind* of check (RISK-01 in spec.md) —
     no existing sibling key cross-validates against `gates:` today; keep it a one-off check in
     `_compile_step`, not a new generalized "capability requires gate" mechanism (scope
     discipline — a general mechanism is speculative until a second capability needs it).
   - Extend `_validate_route_targets()` (mirrors `_validate_fanout_source_upstream`, `:1260`):
     for every `route.outcomes[...]` with `trigger: "step"`, resolve `target` against the
     compiled step-id set; for `trigger: "workflow"`, resolve `target` against either the
     literal `"self"` or a real saved-workflow id (confirm the exact lookup helper —
     `agents/registry.py` or `app/api/user_workflows.py` — during this task, not assumed in
     advance); validate `default_next` the same way. *(R-10)*
   - **R-27**: extend the same validation pass — for every step declaring `route` with a
     non-empty `outcomes`, confirm `route.condition_agent` (or the step itself, when unset)
     declares `produces: ["route_decision"]` in the manifest. Compile error if not.
   - **R-26**: after all steps compile, compute `is_leaf` for every step — a step is a leaf iff
     no `route.outcomes[...]` (any step's) and no other step's `depends_on`/implicit-next
     targets it as a non-terminal continuation. Concretely: a step is NOT a leaf iff some
     `route` outcome or the default linear-next relationship points FROM it to another step.
     Set `Step.is_leaf` accordingly. This is a pure graph-shape computation over the already-
     validated `outcomes`/`depends_on` data — no new data source.
   - `_validate_dag()` (`:1299`) — **zero changes**; confirm via a regression test that
     `route.outcomes` values are never read by this function (R-09).

3. **`agents/capabilities/registry.py`** — add `("gate", "conditional")` to `_KNOWN` (mirrors
   `:110-113`). No changes to `resolve()`/`is_registered()`. *(R-01)*

4. **`agents/capabilities/gates/base.py`** — add `GATE_ROUTE = "route"` alongside the existing
   three outcomes. No new `GateOutcome` field — reuse `detail: dict | None` to carry the
   resolved outcome (`{"trigger": ..., "target": ...}`). *(from spec.md's original gate-layer
   scoping, folded into this phase since it's pure data-layer work.)*

5. **New file `agents/capabilities/gates/conditional.py`** — `ConditionalGate.evaluate(step,
   ctx) -> GateOutcome`, mirroring the plain-awaited pattern of `validation.py:72`/
   `security.py:81` (not the stream+collector pattern `human`/`approval` use):
   - Read the decision source via `condition_agent` (default: this step) using
     `_latest_typed_content` (or the human-gate captured-response equivalent — confirm exact
     helper name during this task by re-reading `kernel_services.py:1305`'s delegation target).
   - `json.loads` the content, extract `parsed["decision"]` (R-05b — fail closed on malformed
     JSON or a missing `"decision"` key: treat as no match, fall through to `default_next`).
   - Match against `route.outcomes` keys; if matched, return `GateOutcome(GATE_ROUTE, detail=
     {"trigger": outcome.trigger, "target": outcome.target})`. If unmatched, return `GateOutcome
     (GATE_PASS)` if `default_next` is set (engine advances normally to whatever step follows),
     else the step terminates the run — confirm exact "no default_next, no match" engine
     behavior against R-13's stop-and-hand-off framing during Phase 3, since it's the same
     "nowhere to go" shape.

6. **UNKNOWN-2 resolution (`gate_events` keying)**: read `kernel_services.py:337-360`
   (`record_gate_event`) end-to-end. If its `(step, gate, outcome)` keying can collide across
   loop passes the same way `gate_key`/`failed_invocations` could before R-08, extend it with
   the same visit-count discriminator in Phase 3 (where `step_visit_counts` is introduced) —
   do NOT fix it here in isolation, since the fix depends on `ExecutionContext.step_visit_counts`
   existing first.

**Accept**: `_compile_route`/`_validate_route_targets`/`is_leaf` computation covered by unit
tests using the five `sample_conditional_*` manifests as fixtures (they should now COMPILE,
though not yet RUN — running needs Phase 3's engine change). AC-01, AC-02, AC-09 (compile-time
half), AC-10 all pass at compiler level. `_validate_dag` regression test confirms zero drift.

---

## 5. Phase 2 — Per-run state (`ExecutionContext`)

**Scope**: the two new caps (R-07, R-18), isolated as their own phase since both are pure
additive state — no dispatch-loop change yet, so this phase is safely testable standalone.

1. **`agents/execution_engine/context.py`** — add `step_visit_counts: dict[str, int] =
   field(default_factory=dict)` (R-07) and a trigger-depth tracking mechanism for R-18. Per
   R-19 (clarified — fixed at 5 in v1), `RouteSpec.trigger_max_depth` is compiler-validated to
   equal exactly `5`; walking the `parent_run_id` chain at trigger time (R-18) is a
   `kernel_services.py` concern (Phase 4), but the depth-so-far value needs a home on
   `ExecutionContext` — add `trigger_depth: int = 0`, set at run-mint time from the parent's
   depth + 1 (0 for a non-triggered run).

2. Unit tests: `step_visit_counts` increments correctly across repeated dict mutation;
   `trigger_depth` propagates correctly through a mocked chain of 2-3 mint calls.

**Accept**: `ExecutionContext` carries both fields, independently unit-tested, zero interaction
with the dispatch loop yet (that's Phase 3).

---

## 6. Phase 3 — Engine dispatch loop conversion (isolated, per RISK-02)

**Scope**: the single highest-risk change in this spec (spec.md RISK-02, explicit
recommendation: "lands as its own isolated, heavily-tested plan phase before any routing logic
is layered on top"). This phase converts the loop mechanism; it does NOT yet wire the
`conditional` gate's outcome into it — that's Phase 4's job, deliberately separated so a bug in
the cursor mechanism itself is provably isolated from a bug in gate routing.

1. **`engine.py:2586`** — convert `for i, spec in enumerate(ordered_agents):` to an index-based
   `while cursor < len(ordered_agents):` loop with a mutable `cursor` variable, replacing every
   `i`-based reference inside the loop body with `cursor`. **This step alone must be
   behavior-preserving for every existing (non-routing) workflow** — write a characterization
   test first (mirrors `003-workflow-engine-decoupling`'s Phase 0 precedent: golden
   deliverable/event snapshots for a representative sample of today's pipelines, captured
   BEFORE this change, asserted byte-identical AFTER). *(R-06)*

2. **`:2685`/`:2711`** — the existing gate-outcome consumer arms (`if _outcome == "cancel":` /
   `if _outcome in ("block", "wait_human"):`) gain a **new `"route"` arm** reading the
   `GateOutcome.detail` set by `ConditionalGate` (Phase 1 task 5):
   - `trigger: "step"` → resolve `target`'s index in `ordered_agents`, set `cursor = that
     index` (NOT `cursor + 1`) instead of falling through to the default advance. Forward and
     backward are the SAME code path (R-06).
   - `trigger: "workflow"` → hand off to Phase 4's `run_trigger_workflow` delegate (not yet
     built this phase — stub the call site now, wire it in Phase 4).

3. **R-07 enforcement**: before advancing the cursor to a `trigger: "step"` target, check/
   increment `ectx.step_visit_counts[target]` against the target step's `route.
   loop_max_iterations` (5, per R-19's fixed ceiling — wait, confirm: `loop_max_iterations` is
   the LOOP cap from R-07, `trigger_max_depth` is the separate TRIGGER cap from R-18/R-19; do
   not conflate the two during implementation). Raise `BudgetExceeded` (existing pattern,
   `:2868`) on breach.

4. **R-08**: `gate_key` (`:6291`, `f"{pipeline_run_id}:{agent_id}"`) and
   `ectx.failed_invocations` keying both gain the visit-count discriminator
   (`f"{run_id}:{agent_id}:{visit_count}"`). Apply the SAME fix to `record_gate_event`
   (UNKNOWN-2 from Phase 1, if confirmed to need it) — this is the natural point to do so,
   since `step_visit_counts` now exists on `ExecutionContext`.

5. **R-11 (v1 scope cut, explicit)**: confirm `_first_incomplete_step` (`:8544`) and its
   companions are NOT modified this phase — a mid-loop/branch crash-restart resumes at the
   FIRST incomplete step by original position, which may be wrong for a looped/branched run.
   Document this as a known v1 limitation in the resume path's own docstring (a one-line
   addition, not a behavior change) rather than silently leaving it unstated in code.

**Accept**: characterization snapshots (task 1) byte-identical for every pre-existing pipeline
that never declares `route`. A1/A4 (loop) and A2 (branch) reference-fixture manifests, run
end-to-end for the first time, produce correct step-visit sequences (verified via
`step_visit_counts` inspection in a test, not yet full run — Phase 4 adds the cross-workflow
half needed for full A3). AC-03, AC-04 pass.

---

## 7. Phase 4 — Cross-workflow triggering

**Scope**: the genuinely new territory — R-12 through R-19, R-28. Depends on Phase 3's cursor
mechanism existing (the `"route"` consumer arm's stub) but is otherwise independent enough to
isolate, since it touches a disjoint file set (`run_commands.py`, `kernel_services.py`,
`state_machine.py`) vs. Phase 3's `engine.py`-internal change.

1. **UNKNOWN-1 resolution + `app/api/run_commands.py`**: read `launch_run` (`:2213`) end-to-end
   to confirm the exact HTTP-vs-core boundary (deferred from Phase 0 research). Extract the
   mint-and-spawn logic into a plain async function (e.g. `_launch_run_core(...)`) callable both
   by the existing HTTP handler (thin wrapper, byte-identical behavior — verify with a
   regression test hitting the HTTP endpoint before/after) and by the new kernel delegate below.
   *(R-16)*

2. **`agents/execution_engine/kernel_services.py`** — new delegate `run_trigger_workflow(step,
   ectx, *, workflow_ref: str) -> str` (returns the new run's id), parallel to `run_human_gate`
   (`:1233`)/`run_fanout` (`:1025`), not folded into either:
   - Resolve `workflow_ref` (`"self"` → the current workflow's own id; otherwise a saved
     `user_workflow_id` — confirm resolution helper, likely shared with Phase 1 task 2's
     `_validate_route_targets` lookup).
   - **R-18**: walk the `parent_run_id` chain from `ectx.run_id` upward (or use
     `ectx.trigger_depth` from Phase 2 directly — prefer the in-memory counter over a DB walk
     if it's already correctly propagated, confirm during implementation which is simpler/more
     correct). Compare against the FIXED ceiling of 5 (R-19, clarified). `BudgetExceeded` on
     breach.
   - Call the Phase 4 task 1 core with `parent_run_id = ectx.run_id`, `owner_id`/`workspace_id`
     = `ectx`'s own (R-15, unconditional inheritance — AUTHZ-01 pattern).
   - Return the new run's id up to the engine.

3. **`engine.py`** — wire Phase 3 task 2's stubbed `trigger: "workflow"` call site to actually
   invoke `run_trigger_workflow`. On return: *(R-13)* set `WorkflowRun.status = "diverted"`
   (R-14 — add `"diverted"` to `state_machine.py`'s `TERMINAL_STATES` frozenset, a one-line
   additive change, audit every OTHER place `TERMINAL_STATES` is enumerated by name or
   `status in TERMINAL_STATES` is checked per RISK-03 — grep sweep, not guesswork) and end the
   dispatch loop for THIS run — no `default_next` fallback, no wait on the new run.

4. **R-28**: emit the new additive `pipeline_diverted` SSE/websocket event
   (`{"pipeline_run_id": ..., "diverted_to_run_id": ..., "diverted_to_workflow": ...}`)
   immediately after the status transition, through the engine's existing generic event-forward
   path (same mechanism `pipeline_cancelled` already uses) — confirm the exact emit call site
   during implementation (near `:2239`/`:2633`/`:2701`'s `pipeline_cancelled` precedents).

5. **R-15 budget addendum** (clarified during `/speckit-clarify`, decision-log #19) — no code
   change needed beyond what task 2 already does: since the triggered run's `ExecutionContext`
   is constructed with the inherited `workspace_id`, `BudgetManager.reserve()`'s existing
   `workspace_spent + requested > workspace_ceiling` check already scopes correctly. Add a
   regression test confirming this (a triggered run's spend IS visible in the parent
   workspace's aggregate), rather than a new mechanism.

**Accept**: A3's reference fixture (`sample_conditional_launch_new` → `sample_conditional_
target`) runs end-to-end for the first time — R1 ends `diverted`, R2 mints with correct
`parent_run_id`/owner/workspace, `pipeline_diverted` fires on R1's stream before it closes.
AC-05, AC-06, AC-11 pass. RISK-03's `TERMINAL_STATES` audit is complete and documented (list of
every call site checked, not just "should be fine").

---

## 8. Phase 5 — Frontend types + canvas (parallel track, can start once Phase 1 lands)

**Scope**: R-21 through R-25. Per this repo's own convention (§22 of
`003-workflow-engine-decoupling/plan.md`: "the frontend contract is a parallel track touched
every phase"), this phase's `types/index.ts` work can start as soon as Phase 1's `RouteSpec`
shape is stable — it does not need to wait for Phases 2–4's backend runtime work, only for the
DATA SHAPE to be locked (which it already is, per spec.md §4.1).

1. **`frontend/src/types/index.ts`** — `ManifestStep`/`AgentDef` gain `route?: {
   condition_agent?: string; outcomes: Record<string, {trigger: "step" | "workflow"; target:
   string}>; default_next?: string; loop_max_iterations?: number; trigger_max_depth?: number }`,
   mirroring `RouteSpec` field-for-field. *(R-21)*

2. **`CanvasNode.tsx`** — existing agent-card node gains a route-target editor UI, surfaced when
   `"conditional"` is checked in that node's gates list. **No new node kind for in-workflow
   routing** (corrects an earlier draft's diamond-node proposal — confirmed in spec.md's
   revision history). One new node kind: the external-pipeline reference card for `trigger:
   "workflow"` outcomes. *(R-22)*

3. **`CanvasView.tsx`** — the single largest frontend item (spec.md RISK-05): convert the
   current `chainEdges`/`treeEdges` array-order layout (`:674-710`) to a real layered/graph
   layout; add the connect-to-existing-node gesture that, unlike the existing drag-reparent
   (`isDescendant` check, `:68-89`), MUST allow targeting an ancestor (the loop case). Loop-back
   edges render as curves around the row. *(R-23)* — recommend this task be scoped as its own
   sub-plan/spike given its size, rather than estimated inline here; flag for a follow-up
   design pass before implementation starts if the graph-layout library choice isn't already
   settled elsewhere in the codebase.

4. **External-pipeline picker** — reuses the existing "My Workflows" list component as its data
   source (confirmed via decision-log #8: "Reuse existing 'My Workflows' list, no new filtered
   picker" — identify the exact component during this task, not yet named in the spec). *(R-24)*

5. **`ComposerPage.tsx`** — `handleSave`/`handleRunOnce`/`buildWorkflowManifest` serialize the
   new `route` field per step; any node carrying non-empty `route` forces the full-manifest
   path (`needsFullManifest`, already the pattern for other non-flat-list step data). *(R-25)*

6. **Run-history UI** — two linked run cards for a diverted run (R-20): the diverted run's card
   shows "Diverted to `{workflow_id}` →"; the triggered run's card shows "← Continued from
   `{parent}`, step `{step_id}`". Consumes the `pipeline_diverted` event's payload (Phase 4
   task 4) for the live case, and `parent_run_id`+`status="diverted"` for the historical case.

**Accept**: AC-07 (canvas authors all three outcome kinds), AC-08 (linked run-history cards).
A2's branch fixture and A3's divert fixture both authorable end-to-end via the composer UI, not
just hand-written YAML.

---

## 9. File-by-file change map

| File | Phase | Change |
|---|---|---|
| `agents/workflows/plan.py` | 1 | `RouteOutcome`, `RouteSpec`, `Step.route`, `Step.is_leaf` |
| `agents/workflows/compiler.py` | 1 | `_compile_route`, R-03/R-27 cross-checks, `_validate_route_targets` extension, `is_leaf` computation |
| `agents/capabilities/registry.py` | 1 | `("gate", "conditional")` in `_KNOWN` |
| `agents/capabilities/gates/base.py` | 1 | `GATE_ROUTE` constant |
| `agents/capabilities/gates/conditional.py` | 1 | **NEW FILE** — `ConditionalGate.evaluate()` |
| `agents/execution_engine/context.py` | 2 | `step_visit_counts`, `trigger_depth` |
| `agents/execution_engine/engine.py` | 3, 4 | dispatch-loop cursor conversion; `"route"` consumer arm; `gate_key`/`failed_invocations` visit-count keying; `pipeline_diverted` emit |
| `agents/execution_engine/state_machine.py` | 4 | `TERMINAL_STATES` gains `"diverted"`; audit every other reference (RISK-03) |
| `agents/execution_engine/kernel_services.py` | 1 (audit), 4 | `run_trigger_workflow` delegate; `record_gate_event` visit-count keying if UNKNOWN-2 confirms it's needed |
| `app/api/run_commands.py` | 4 | `launch_run` core extraction (`_launch_run_core` or similar) |
| `frontend/src/types/index.ts` | 5 | `route` field on `ManifestStep`/`AgentDef` |
| `frontend/src/components/workflow/composer/CanvasNode.tsx` | 5 | route-target editor; external-pipeline node kind |
| `frontend/src/components/workflow/composer/CanvasView.tsx` | 5 | graph layout conversion; connect-to-node gesture |
| `frontend/src/components/workflow/composer/ComposerPage.tsx` | 5 | `route` serialization; `needsFullManifest` trigger |
| run-history UI component(s) | 5 | linked-cards rendering (component not yet named — identify during Phase 5) |
| `backend/agents/workflows/sample_conditional_*/workflow.yaml` | — | **already exist** (checked in this session) — Phase 1 makes them compile; Phase 3/4 make them run |

**Zero new database migrations across every phase** — `parent_run_id` (R-15), `TERMINAL_STATES`
(R-14), and `is_leaf` (R-26) are all reused-unmodified or in-memory/compiled-plan fields, not
schema changes.

---

## 10. Risks (carried forward from spec.md §7, with phase assignment)

| Risk | Phase | Mitigation |
|---|---|---|
| RISK-01 (compiler blast radius — new cross-check kind) | 1 | Kept as a one-off `_compile_step` check, not a generalized mechanism (scope discipline) |
| RISK-02 (dispatch loop conversion) | 3 | Isolated as its own phase; characterization snapshots BEFORE the cursor conversion, asserted byte-identical after, for every non-routing workflow |
| RISK-03 (new terminal state) | 4 | Explicit grep sweep of every `TERMINAL_STATES` reference before merging, not assumed safe |
| RISK-04 (extraction boundary) | 4 | UNKNOWN-1 — resolved by reading `launch_run` end-to-end at the start of Phase 4, not estimated in advance |
| RISK-05 (canvas layout rewrite) | 5 | Flagged as the single largest item; recommend its own scoping pass before implementation starts, separate from this plan's task-level detail |

**New risk found during planning:**

- **RISK-06 (Phase 3/4 sequencing dependency)**: Phase 4's `"route"` consumer arm for
  `trigger: "workflow"` is stubbed in Phase 3 but only wired in Phase 4 — if Phase 3 ships
  without Phase 4 immediately following, an in-workflow-only subset of the spec is live
  (A1/A2/A4 work, A3 does not). This is an ACCEPTABLE intermediate state (matches the
  strangler-migration precedent in `003-workflow-engine-decoupling`), but should be called out
  explicitly if Phase 3 and Phase 4 ship as separate PRs/releases rather than back-to-back —
  the reference fixtures `sample_conditional_launch_new`/`sample_conditional_target` will
  compile (Phase 1) but fail at runtime until Phase 4 lands, which is expected, not a bug.

---

## 11. Phase sequencing summary

```
Phase 1 (compiler, no engine change)
  │
  ├──> Phase 2 (ExecutionContext fields, independent)
  │
  └──> Phase 5 (frontend types, can start once Phase 1's shape is locked — parallel track)

Phase 1 + Phase 2 ──> Phase 3 (dispatch loop cursor conversion, ISOLATED — RISK-02)
                          │
                          └──> Phase 4 (cross-workflow triggering — wires Phase 3's stub)
                                   │
                                   └──> Phase 5's run-history UI (consumes pipeline_diverted)
```

Phases 1→2→3→4 are a strict backend dependency chain (each needs the previous). Phase 5 (frontend) forks off after Phase 1 for the type/canvas work, but its run-history sub-task (task 6) depends on Phase 4's `pipeline_diverted` event existing. This mirrors the "frontend as a parallel track touched every phase" pattern already established in `003-workflow-engine-decoupling/plan.md` §25.
