---
phase: quick-260718-puj
plan: 01
subsystem: workflow-engine
tags: [cwf-001, resolver, composer, produces-consumes, satisfiability]
requires:
  - agents/execution_engine/resolver.py (_detect_cycles/_topological_sort helpers)
  - agents/loader.py (load_agent_spec)
provides:
  - WorkflowResolver.presort() — additive order-independent producer-first pre-sort
  - app.api.composition_order (presort_specs/presort_agent_ids + UnsatisfiableComposition)
  - compose-time satisfiability guard at save (user_workflows) + launch (run_commands)
  - composer row reorder + inline unsatisfiable rejection
affects:
  - POST /api/user-workflows (persists producer-first; 422 on unsatisfiable)
  - POST /api/runs (custom agent_ids pre-sorted pre-mint; 422 workflow_unsatisfiable)
tech-stack:
  added: []
  patterns: [ports-and-adapters app->agents, additive-entry-point, REUSE graph helpers INV-12]
key-files:
  created:
    - backend/app/api/composition_order.py
  modified:
    - backend/agents/execution_engine/resolver.py
    - backend/app/api/user_workflows.py
    - backend/app/api/run_commands.py
    - backend/tests/unit/test_workflow_resolver.py
    - backend/tests/unit/test_user_workflows.py
    - backend/tests/unit/test_user_workflows_selections.py
    - backend/tests/unit/test_rest_run_launch.py
    - frontend/src/components/workflow/composer/ComposerPage.tsx
    - frontend/src/components/workflow/composer/ComposerPage.test.tsx
decisions:
  - Candidate (b): new additive presort() reusing kernel graph helpers; validate()/:119/:138 byte-unchanged
  - App-layer composition_order.py is the single import seam (honors user_workflows' no-direct-engine-import convention)
  - Launch rejection is HTTP 422 code=workflow_unsatisfiable (matches must_haves truth + test)
metrics:
  duration: ~35m
  completed: 2026-07-18
---

# Phase quick-260718-puj Plan 01: CWF-001 FIX D1 — compose-time produces/consumes satisfiability Summary

Custom workflows composed consumer-before-producer no longer save/launch into a runtime "Workflow DAG is unsatisfiable" death: a new additive `WorkflowResolver.presort()` (order-independent, reusing the kernel's `_detect_cycles`/`_topological_sort`) drives an app-layer guard at both the save and launch boundaries that reorders a fixable composition producer-first or rejects a genuinely-unsatisfiable one with a clear message, and the composer surfaces the result.

## What was built

- **`WorkflowResolver.presort()`** (`resolver.py`, additive public method): builds an order-independent `produces_map` (artifact_type → set of producing agent ids over ALL agents, no index filter), excludes self as a producer, skips `_EXEMPT_TYPES`, raises `ValueError("Workflow DAG is unsatisfiable: …no agent in the workflow produces it.")` for an unproduced non-exempt consumed type, reuses `_detect_cycles` for real cycles, and returns `_topological_sort` output (producer-first). `validate()` / `:119` (`idx < consumer_idx`) / `:138` (`max()` tie-break) untouched.
- **`app/api/composition_order.py`** (new app-layer module): `UnsatisfiableComposition(ValueError)`, `presort_specs(specs)` (delegates to the resolver, re-raises `ValueError` as `UnsatisfiableComposition`), `presort_agent_ids(ids)` (loads specs via `agents.loader.load_agent_spec` then delegates). Generic produces/consumes only — no workflow-name / pipeline_type literal (SC-001). Legal `app → agents` import direction.
- **`create_user_workflow`** (`user_workflows.py`): after the selections compile block and before name-uniqueness, `presort_agent_ids(body.agent_ids)` → persist `sorted_ids` (was `body.agent_ids`); `UnsatisfiableComposition` → HTTP 422 naming the missing edge. Imports the app-layer helper (honors the module's no-direct-engine-import convention). PATCH cannot change agent order (documented).
- **`launch_run`** (`run_commands.py`): inside the custom `if agent_ids:` branch only (after `load_agent_spec`), `presort_specs(agents)` BEFORE the mint; `UnsatisfiableComposition` → `_reject("workflow_unsatisfiable", …, http_status=422)` (no WorkflowRun row). Built-in `else`/`get_pipeline_agents` branch untouched (scope fence).
- **Composer** (`ComposerPage.tsx`): `handleSave` captures the `createUserWorkflow` response and, when `resp?.agent_ids?.length`, reorders the visible rows to the persisted producer-first order; the 422 rejection already surfaces inline via the existing `saveError` render.
- **Fixtures**: `_AGENT_B` `report-generator` → `swot-analyst` in `test_user_workflows.py` + `test_user_workflows_selections.py` (report-generator consumes `documentation-agent`, genuinely unsatisfiable; swot-analyst consumes market-research-agent = `_AGENT_A`'s produced type → producer-first chain that presorts to itself). A negative-path unsatisfiable→422 test is retained.

## RED → GREEN evidence

- **Task 1 (resolver/composition_order):** new presort tests `6 failed` (`AttributeError: no attribute 'presort'`) → after implementation `23 passed` (incl. untouched `test_multi_producer_nearest_upstream_wins`).
- **Task 2 (wiring):** `test_post_reorders_consumer_first_to_producer_first` / `test_post_rejects_unsatisfiable_composition` / `test_unsatisfiable_custom_composition_rejected_pre_mint` — `3 failed` (save kept sent order; unsatisfiable saved 201; launch minted a run) → after wiring `68 passed` across the three app-layer suites.
- **Task 3 (composer):** with the reorder block disabled, "producer-first pre-sort" test `1 failed` (rows stayed consumer-first) → restored → `12 passed`.

## Verification (offline, python3.11 / vitest)

- `test_workflow_resolver.py test_user_workflows.py test_user_workflows_selections.py test_rest_run_launch.py` → **91 passed**.
- 5 characterization goldens (prototype / od_prototype / prototype_revision / od_ppt / app_builder) → **10 passed** (byte/event-identical — kernel untouched).
- `lint-imports` → **4 kept, 0 broken** (exit 0; `app.api.composition_order → agents.execution_engine.resolver` is the legal direction).
- Frontend `ComposerPage.test.tsx` → **12 passed**; `npx tsc --noEmit` → **exit 0**.
- **Skipped (per plan — optional):** mocked Playwright `composer-run.spec.ts` / `ts-d.composer.spec.ts` — a dev server is live on :3000 and the orchestrator owns this verification. Not run here.
- Live Bedrock / full backend suite NOT run (hangs offline; orchestrator owns live proofs).

## Deviations from Plan

**1. [Rule 3 - blocking] Launch rejection HTTP status = 422 (not `_reject`'s 400 default).**
- **Found during:** Task 2. The plan action text shows `raise _reject("workflow_unsatisfiable", str(exc))`, but `_reject` defaults to HTTP 400, whereas the plan's `must_haves` truth and the Task-2 test both require **422**.
- **Fix:** passed `http_status=status.HTTP_422_UNPROCESSABLE_ENTITY` to `_reject` so the launch path returns 422 with `detail.code == "workflow_unsatisfiable"`, matching the stated success criteria.
- **Files:** `backend/app/api/run_commands.py`. **Commit:** c50afe8f.

No other deviations — architecture guardrails (candidate (b) only; validate()/:119/:138 byte-unchanged; app→app import via composition_order; no compiler edit; no migration; generic produces/consumes only) all honored.

## Known Stubs

None.

## Threat Flags

None — the change adds no new network endpoint, auth path, file access, or schema surface. It hardens the two existing trust boundaries (`POST /api/user-workflows`, `POST /api/runs`) named in the plan's threat register (T-CWF1-01 mitigate).

## Commits

- `8446a44b` feat(engine): add order-independent WorkflowResolver.presort() + composition_order entry point
- `c50afe8f` fix(engine): guard custom-composition satisfiability at save + launch (CWF-001 D1)
- `17114dac` feat(composer): surface CWF-001 D1 pre-sort + unsatisfiable rejection

## Self-Check: PASSED

- FOUND: backend/app/api/composition_order.py
- FOUND: presort in backend/agents/execution_engine/resolver.py
- FOUND commits 8446a44b, c50afe8f, 17114dac on feat/ui-2
