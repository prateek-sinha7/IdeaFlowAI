---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
kind: review-fix
date: 2026-06-15
source_review: 22-REVIEW.md
---

# Phase 22 — Review Fix Pass

Post-review fix pass addressing the confirmed BLOCKERs + key warnings from
`22-REVIEW.md`. This is NOT a new plan — STATE.md / ROADMAP.md plan counters are
deliberately left untouched. Each fix committed atomically under scope `22`.

## Findings Fixed

| ID    | Severity | Status  | Summary |
| ----- | -------- | ------- | ------- |
| CR-01 | BLOCKER  | FIXED   | Selection-supplied per-step `model` id bypassed the `ModelCatalog` allow-list. |
| CR-02 | BLOCKER  | FIXED   | Retry lever emitted a bare scalar → compiler 422. |
| WR-01 | WARNING  | FIXED   | Launch never sent `selections` — the EMP-01 overlay was dead on the live FE path. |
| WR-03 | WARNING  | FIXED   | `_apply_selections` swallowed ALL exceptions (silent fail-open). |
| WR-04 | WARNING  | FIXED   | Selection `model` id unvalidated at SAVE too. |
| IN-02 | INFO     | FIXED   | Model checks now use `is_allowed` (covers `user_allowed`) — correct-by-construction. |
| IN-03 | INFO     | FIXED   | Stray `print()` debug on the WS hot path → `logger.debug`. |
| WR-02 | WARNING  | DEFERRED| `resume_run` drops `selections` — documented (code comment + deferred-items.md), no migration. |

### CR-01 + WR-04 (BLOCKER — model-id allow-list bypass)
- Added `validate_selection_model_ids()` to the shared synth seam
  (`agents/workflows/selections.py`) — uses `ModelCatalog().is_allowed` (so it also
  honours `user_allowed`, IN-02).
- Enforced at BOTH chokepoints: launch (`websocket._revalidate_selections_trust_user`)
  and save (`user_workflows._compile_selections_trust_user`) — same error-string shape,
  save == launch invariant preserved.
- Defense-in-depth: `model_policy.ModelResolver.resolve` now catalog-validates tier-2
  `step.model` when it is the selected tier, before `build_model` — the kernel never
  trusts an unvalidated id regardless of caller.

### CR-02 (BLOCKER — retry lever 422)
- `selections.py::_coerce_retry`: a numeric / numeric-string `retry` → `{max_attempts: N}`;
  `0`/unset → omitted (no-retry parity); dicts pass through unchanged. Applied at the
  single synth seam so save and launch behave identically.
- FE already emits a clean numeric (`Number(e.target.value)`, key dropped when empty) —
  the `AdvancedExpander.test.tsx` `retry: 2` assertion is consistent with the reconciled
  shape (FE numeric → backend coerces). No FE retry-emit change needed.

### WR-01 (primary feature gap — selections never reached launch)
- `IdeaInputPage.handleRun` now threads `selectionsRef.current` into
  `extraParams.selections` (included only when ≥1 lever set → byte-identical no-op payload).
- `DashboardLayout.savedComposition` carries `selections`; threaded as `initialSelections`
  into `IdeaInputPage` → `AgentsPopup` → `AdvancedExpander` (seeds state + the ref) so a
  launched SAVED workflow re-loads AND re-sends its persisted `manifest_json` levers.
- `UserWorkflowSummary` type now exposes `selections` (the backend `_project` already
  returns it).

### WR-03 (fail-open)
- `engine._apply_selections` catch narrowed from `except Exception` to `except CompilerError`
  (the only expected rejection). Unexpected exception types now propagate (programmer errors
  surface instead of silently dropping the overlay).

### IN-03 (cheap)
- The three `print("[WS] …")` statements on the WS connection/message hot path replaced
  with `logger.debug(...)`.

## Deferred

### WR-02 (resume drops selections)
Deferred per scope — no new migration this pass. Documented with a code comment at the
`resume_run` `_execute_impl` site and logged to `deferred-items.md` as a tracked
follow-up. A restart-resumed run re-drives the bare file-compiled plan; resolution needs
an additive nullable column (or run JSON) persisting the launch `selections` + re-threading
through `resume_run → _execute_impl → _apply_selections`. Not a security issue (resume can
only ever apply LESS privilege than the engineer authored).

### Out of review scope (not requested)
- WR-05 (PATCH route stale-agent selection), IN-01 (FE PATCH affordance for
  selections/model_overrides), IN-04 (`__invalid_selection__` sentinel DX) — not in the
  requested fix set; left for a follow-up.

## Regression Tests Added
- `backend/tests/unit/test_user_workflows_selections.py`: disallowed selection model
  rejected at SAVE (`test_save_rejects_disallowed_selection_model`), at LAUNCH
  (`test_launch_rejects_disallowed_selection_model`), and at the resolver
  (`test_model_resolver_rejects_disallowed_step_model`); bare numeric retry accepted at
  save/launch and reaches a live `RetryPolicy(max_attempts=N>0)`
  (`test_bare_retry_coerces_and_reaches_compiled_step`); `0` retry omitted
  (`test_zero_retry_omits_no_wrapper`).
- `frontend/src/components/workflow/IdeaInputPage.selections.test.tsx`: the run payload
  carries `selections` when levers are set, omits them when none (INV-3), and re-sends
  seeded selections on a saved-workflow launch.

## Verification (all green)

| Check | Result |
| ----- | ------ |
| 5 characterization goldens (prototype, od_prototype, prototype_revision, od_ppt, app_builder) | PASS (INV-3 byte-identical) |
| `test_banned_patterns.py` (SC-001 no workflow-name branch) | PASS (11) |
| `lint-imports` (Ports & Adapters) | 4 kept / 0 broken |
| `test_user_workflows.py` + `test_user_workflows_selections.py` | PASS (19 + 23) |
| `test_capabilities_api.py` | PASS (12) |
| `test_compiler.py` + `test_compiler_trust.py` | PASS (26 + 25) |
| `test_model_resolver.py` | PASS (25) |
| FE full vitest | PASS (151 / 20 files) |
| FE `tsc --noEmit` | only the 2 pre-existing `e2e/fixtures/mockApi.ts` casts (out of scope, documented); 0 errors in `src/` |

_Fix pass: 2026-06-15 — Claude (gsd-execute)_
