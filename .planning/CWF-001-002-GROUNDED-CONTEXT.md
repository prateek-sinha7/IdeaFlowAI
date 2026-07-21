# CWF-001 / CWF-002 — Grounded Fix Context (for gsd-quick)

> Root-caused + fix-designed by a deep investigation agent that read `.planning/IMPLEMENTATION-REGISTER.md`
> **IN FULL (all 4043 lines to EOF)** on `feat/ui-2` (proof: last line = the BUG-021/quick-260717-t9i
> verification entry). All `file:line` spot-checked against current code. This is the SINGLE reference for
> the executor — implement against these specs and respect **every** cited locked decision. Do NOT shortcut;
> do NOT break the cited invariants; delete no superseded code without grepping callers.

## Context
Live-Bedrock custom-workflow QA: a custom workflow whose agents are in a **consumer-before-producer** order
saves (201) + launches (200) with no warning, then fails at runtime with `"Workflow DAG is unsatisfiable:
Agent 'X' consumes 'Y' but no upstream agent produces it"` — and the failed, **0-agent, empty-output** run
is mislabeled **`completed`**. Separately, the per-agent model actually used is never recorded. A
correctly-ordered run completes fine (control run `3c958122`). D1 and D2 **compound** on the repro
(`["swot-analyst","market-research-agent"]`, consumer first): D1 emits a generic `error`; D2 mislabels it.

## Binding locked-decisions / invariants (from the full-register read — do NOT violate)
- **INV-1 / SC-001** — kernel knows no workflow by name. `resolver.py` + `engine.py` are KERNEL; `run_commands.py`, `runs.py`, `user_workflows.py` are APP-LAYER (generic `pipeline_type`/event-type refs allowed there; NO workflow-name literal in any fix).
- **INV-3** — event-parity + deliverable bytes, proven by the 5 characterization goldens (`prototype`, `od_prototype`, `prototype_revision`, `od_ppt`, `app_builder`). The event snapshot is an **order-canonical multiset**; any NEW `agent_*`/`pipeline_*` payload key stays parity-neutral **only** if added to `_VOLATILE_STRIP_KEYS`.
- **INV-5** — the compiler is thin: `_validate_dag` (`compiler.py:858-904`) checks only `depends_on` cycles + duplicate ids. Do **NOT** add produces/consumes logic to the compiler.
- **INV-12** — no dual implementation: reuse the resolver's existing graph helpers; do not re-implement DAG logic.
- **Q3** — additive migrations only. `WorkflowRun.model_id` **already exists** (migration 0014, `workflow.py:37`) and inherits `owner_id`/`workspace_id` from `WorkflowRun` → **no new migration, no new columns**.
- **Register line 484** — the engine executes in resolver **topo order**, which *legitimately reorders* contract-coupled code-gen agents in `dotnet`/`mulesoft`/`app_builder`; the resolver's topo order + tie-break are **depended upon**.
- **`resolver.py:14` + `test_workflow_resolver.py::test_multi_producer_nearest_upstream_wins`** — the multi-producer tie-break ("fewest edges; ties → latest declared order") is a pinned, tested behavior.
- **Phase 21/22 (register 2136/2252)** — user-workflow `agent_ids`/`model_overrides`/`selections` are re-validated with the EXACT predicates at **BOTH save AND launch** ("load-bearing security invariant"); WR-02 added `Field(min_length=1)`. This save+launch seam is the precedented home for the D1 compose-time guard.
- **Phase 29 (register 2793)** — `_drive_launch_to_queue` and `_drive_revision_to_queue` are sanctioned **LOCK-B twins**: "must stay behaviorally identical … a future change must be mirrored by hand." The revision driver is the correct fail-safe template for D2.
- **Phase 13 IN-02 / IN-03 (register 1386, OPEN)** — the exact status-lifecycle class D2 lives in (DB-`failed`-vs-FE-`success` disagreement; drainers not early-breaking on `pipeline_failed`).
- **Phase 26 (register 2577)** — pricing derives from the single `model_catalog.py` source; `test_model_catalog::test_single_source_grep` **bans `claude-(haiku|sonnet|opus)-4` literals outside `model_catalog.py`**. `cost`/`model_id` are already in `_VOLATILE_STRIP_KEYS`.
- **Run-status column is a free `String`** (no `sa.Enum`, Phase 44 line 3703) — additive status values need no migration.

---

## FIX D2 (MANDATORY) — launch driver mislabels errored/failed runs as `completed`
- **File:** `backend/app/api/run_commands.py`, `_drive_launch_to_queue` (event ladder ~1382–1423; terminal assignment ~1429–1444).
- **Root cause (confirmed):** the ladder tracks `agent_error`, `pipeline_complete` (+`degraded`), `pipeline_cancelled` — but NOT the generic `error` event nor `pipeline_failed`. So a generic `error` with no prior `agent_error` → `any_agent_errored=False` → the terminal `else` at `:1442` → `"completed"`. The **revision** twin `_drive_revision_to_queue` (`:1642-1682`) already tracks `pipeline_failed` (`:1649`) and defaults its `else` to `"failed"` (`:1682`).
- **Approach:** reconcile the launch driver TOWARD the revision twin (Phase 29 LOCK-B). (a) Add ladder tracking: `elif utype == "error": pipeline_error_seen = True` (capture `data.error`/`code`) and `elif utype == "pipeline_failed": pipeline_failed_seen = True`. (b) Make the terminal assignment fail-safe: a run is `completed`/`degraded` only when a clean terminal was observed; any `error` / `pipeline_failed` / `agent_error`-without-clean-terminal → `"failed"` + persist `wr.error`. Preserve precedence `cancelled > degraded > failed > completed`.
- **Constraints respected:** app-layer status derivation — NOT kernel, NOT golden-covered (the characterization harness drives `execute()` and asserts deliverable bytes + the event multiset, NOT the `WorkflowRun.status` DB write) → **INV-3 not exposed**. Closes Phase 13 IN-02/IN-03. Honors Phase 29 (reconcile the twins). INV-1/SC-001: keys on generic event types. No migration.
- **At-risk tests / RED→GREEN:** `backend/tests/unit/test_rest_run_launch.py` (currently asserts `status=="completed"` ~line 317 — update); `test_rest_revisions.py` (already asserts `"failed"` — the pattern). ADD: feed `_drive_launch_to_queue` a stream ending in `{"type":"error","code":"workflow_unsatisfiable"}` (and separately `pipeline_failed`) → assert `wr.status=="failed"` (fails today, passes after). Re-run the 5 `test_characterization_*.py` (unaffected — clean terminals).
- **Scope fences:** do NOT touch the engine's terminal emission; keep the two drivers behaviorally identical; do NOT convert status to `sa.Enum`.

## FIX D1 (PRIMARY) — order-dependent satisfiability with no compose-time guard
- **Root cause (confirmed):** `resolver.py:118-119` counts a producer only if `idx < consumer_idx`; empty → error `resolver.py:121-131`. Runs only at `engine.py:1572` (error yielded `:1589-1598`); engine executes topo order anyway (`:1600`). No earlier guard: `compiler._validate_dag` (depends_on only), `user_workflows.py:247-335` (persists reordered ids verbatim `:322`), `run_commands.py:1234-1245` (mints `running` before any DAG check), `ComposerPage.tsx` (`moveAgent` 146-154 / `handleDrop` 167-182 reorder freely; send in-order `:256`/`:291`).
- **Approach (candidate b — PREFERRED):** an **order-independent** produces/consumes satisfiability check + **producer-first topological pre-sort**, added at the app-layer save + launch boundaries and surfaced in the composer:
  1. `backend/app/api/user_workflows.py` `create_user_workflow` (+ PATCH sibling): after the existing predicate block (~:298), run an order-independent satisfiability check on the resolved agents' `produces`/`consumes`; a consumed non-exempt type with NO producer anywhere (or a real cycle) → `422` with a clear message naming the missing edge; otherwise topo-sort the ids producer-first and persist the sorted order (`:322`).
  2. `backend/app/api/run_commands.py` launch path: same check + pre-sort **before** `status="running"` is minted (~:1234) — defense-in-depth; also repairs fresh Run-once and legacy mis-ordered saved rows.
  3. `frontend/src/components/workflow/composer/ComposerPage.tsx`: surface unsatisfiable consumers inline and pre-sort (or block Save/Run) so the user sees it pre-launch.
  The helper MUST be order-independent and **reuse** the resolver's existing `_detect_cycles`/`_topological_sort` (INV-12) via a NEW **additive** entry point — do **NOT** modify `validate()`'s `idx < consumer_idx` (`resolver.py:119`) or the `max(upstream,…)` tie-break (`resolver.py:138`).
- **Why candidate (a) is REJECTED (register-cited):** making `validate()` order-independent edits KERNEL code whose topo order is depended upon (line 484, `app_builder`/`dotnet`/`mulesoft`) and whose tie-break is pinned (`resolver.py:14` + `test_multi_producer_nearest_upstream_wins`); `app_builder` is a characterization golden → **INV-3 risk**. Candidate (b) only ever reorders USER compositions (file-backed built-in manifests are already producer-first and pass unchanged) → cannot perturb a golden.
- **Constraints respected:** INV-1/SC-001 (keys on generic `produces`/`consumes`, no workflow name); INV-3 (kernel resolver byte-identical → 5 goldens unchanged); INV-5 (guard NOT in the compiler); Q3 (no new table). Matches Phase 22 WR-02 fail-fast-at-save precedent.
- **At-risk tests / RED→GREEN:** `test_workflow_resolver.py` (MUST stay green — proves kernel untouched, esp. `test_multi_producer_nearest_upstream_wins`); `test_user_workflows*.py`; `test_rest_run_launch.py`; the 5 `test_characterization_*.py`; FE `ComposerPage.test.tsx`, `composer-run.spec.ts`, `ts-d.composer.spec.ts`. RED→GREEN: save/launch `["swot-analyst","market-research-agent"]` (consumer-first) — today launches a `running` run that dies unsatisfiable; after, save reorders to producer-first (launch OK) or rejects with a clear message.
- **Scope fences:** do NOT edit `resolver.py:119`/`:138` or `validate()`; do NOT add produces/consumes to the compiler; do NOT re-sort file-backed built-in manifests (user compositions only); do NOT change `engine.py:1589-1598`.

## FIX CWF-002 (ENHANCEMENT, optional) — per-agent model never persisted/queryable; circular cost
- **Root cause (confirmed):** `WorkflowRun.model_id` (`workflow.py:37`) has zero assignment sites; the mint (`run_commands.py:1234-1245`) omits it → `estimate_cost_usd(wr.model_id or BEDROCK_INFERENCE_PROFILE_ID, …)` (`:1464-1465`) always prices at the default. No model in `agent_start` (`engine.py:2931-2935`) / `agent_complete` (`engine.py:3684-3694`) / summary / detail. The effective model IS computed (`ModelResolver.resolve`, Phase 6) but discarded.
- **Approach:** (a) add the resolved `model_id` to the `agent_complete` payload (`engine.py:3684-3694`) AND to `_VOLATILE_STRIP_KEYS`; (b) persist the run's effective `model_id` onto `WorkflowRun.model_id` in the launch driver's terminal DB block (`run_commands.py:1425-1477`), from the value already threaded as `model_id=` at `:1333`; (c) surface it read-side in `runs.py` summary/detail.
- **Constraints respected:** INV-3 (new key MUST be in `_VOLATILE_STRIP_KEYS` — precedent: `agent_model_fallback`, `cost`/`model_id`); Q3 (column already exists — no migration); Phase 26 single-source pricing (use `ModelCatalog`/`estimate_cost_usd`; introduce NO `claude-*-4` literal — `test_single_source_grep` will fail); INV-1 (generic `model_id`).
- **At-risk tests / RED→GREEN:** 5 `test_characterization_*.py` (prove the new key is stripped → byte-identical); `test_model_catalog.py::test_single_source_grep`; `test_model_pricing.py`; `test_rest_run_launch.py`. RED→GREEN: launch with a non-Haiku override → assert `wr.model_id` written + `estimated_cost_usd` reflects it (fails today, passes after).
- **Scope fences:** do NOT touch `ModelResolver` precedence (Phase 6 D-02 locked); do NOT change `estimate_cost_usd` math or the `model_catalog.py` pricing source; ISS-033 direct-call token gap is out of scope.

## Global constraints for the executor
- Branch **`feat/ui-2`** only — NEVER `main`/`dev`/`staging`. NO commit trailer (no Co-Authored-By / Claude-Session). NEVER push. Worktrees OFF → run sequential.
- Do NOT run live Bedrock in the executor — the orchestrator owns live proofs. Verify offline (targeted pytest + the 5 goldens + resolver/compiler/composer suites; `lint-imports`).
- python3.11, no venv. Respect the import-linter kernel/app boundary. Keep SC-001 grep clean (no workflow-name literal in any guarded component).
