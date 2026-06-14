---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
verified: 2026-06-15T00:30:00Z
status: passed
score: 17/17 must-have requirements verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 16/17
  gaps_closed:
    - "SURF-03 — the composer shows a launchable workflow's declared per-step capabilities sourced from the compiled plan, before composing"
  gaps_remaining: []
  regressions: []
---

# Phase 22: Capability Surfacing and User Empowerment — Verification Report

**Phase Goal:** Cash the SC-001 dividend at the UX layer — make every registered capability VISIBLE (live `GET /api/capabilities`, grouped by kind, trust/tier-gated) and COMPOSABLE (user opts a workflow's steps into user-allowed capabilities, saves, launches through the EXISTING run path with ZERO kernel workflow-name branches); plus close the `model:`/`retry:`/`injects:` compiler-wiring gaps (WIRE), the 4 UX data-faithfulness fixes (UXFIX), the 2 product decisions (DECIDE), and one consolidated live-Bedrock evidence pass (LIVE).
**Verified:** 2026-06-15T00:30:00Z
**Status:** passed
**Re-verification:** Yes — after SURF-03 gap closure (commit 5d36a394, FE-only)

## Re-Verification Summary

The prior verification (2026-06-15T00:15:00Z) recorded **16/17 verified, status `gaps_found`**, with the SOLE gap being **SURF-03 hollow on the live path** — the `declaredCapabilities` prop was plumbed `AgentsPopup` → `CapabilityPaletteSection` but never populated at the live call site, and the compiled-plan projection was never fetched.

Commit **5d36a394** (`fix(22-fix): wire compiled-plan projection into composer (SURF-03)`, FE-only, exactly 4 files: `api.ts`, `IdeaInputPage.tsx`, `DashboardLayout.tsx`, + new `IdeaInputPage.declaredCapabilities.test.tsx`) closes it. SURF-03 is now **VERIFIED on the live path** (Level-4 data FLOWING). The FE-only fix did not touch any backend file; all backend invariants (5 goldens, SC-001 banned-patterns) re-confirmed green and all other 16 must-haves remain VERIFIED. Final score: **17/17, status `passed`**.

## Goal Achievement

### Observable Truths

| #  | Truth (requirement) | Status | Evidence |
| -- | ------------------- | ------ | -------- |
| 1  | SURF-01 — palette reads the live registry, grouped by kind, no hardcoded cap-name array | ✓ VERIFIED | `CapabilityPaletteSection` in `AgentsPopup.tsx:793` fetches `GET /api/capabilities` (line 820), groups by whatever `kind` the payload returns (842-850, no hardcoded kind list), embedded NOT standalone (no `CapabilityPalette.tsx` exists). Test `CapabilityPaletteSection.test.tsx` renders a fixture-only cap `zzz_fixture_only` referenced nowhere in FE source (SC-001 proof). Re-run green. |
| 2  | SURF-02 — `/api/capabilities` returns description + security_gated + populated config_schema (registry-sourced, no `{}` stub) | ✓ VERIFIED | `registry._META` + `describe()` (registry.py:168/370); `capabilities.py:132-142` projects `description`/`config_schema` from `registry.describe(...)` and derives `security_gated = not user_allowed`; the `{}` stub is gone. `CapabilityEntry` in `api.ts:498-505` mirrors the fields. Unaffected by FE-only fix. |
| 3  | SURF-03 — composer shows a workflow's declared per-step capabilities sourced from the compiled plan, before composing | ✓ VERIFIED | **GAP CLOSED (5d36a394).** `api.ts:631-639` exports `getWorkflowDetail(token, id)` → `GET /api/workflows/{id}` with `WorkflowDetail`/`WorkflowStepDetail` types mirroring `workflows.py:245-309`. `IdeaInputPage.tsx:263-302` fetches the projection in a useEffect with cancelled-guard when `workflowId` is present, maps each step's `strategy`/`gates`/`validators`/`compaction`/`task_source.kind` to declared caps (NO hardcoded cap-name list — grep clean, SC-001), and **passes `declaredCapabilities` into `<AgentsPopup>` at line 682**. `DashboardLayout.tsx:1212` threads `workflowId={workflowType}` for built-in launchable AND saved workflows. No-id ⇒ no fetch, strip hidden (correct for from-scratch). The strip renders on the live path (`AgentsPopup.tsx:871`). LIVE-path test `IdeaInputPage.declaredCapabilities.test.tsx` renders REAL IdeaInputPage + AgentsPopup (mocks only the `@/lib/api` network seam), asserts `getWorkflowDetail` is called AND the "Declared by this workflow" strip renders the projection-sourced caps; the no-id case asserts no fetch + no strip. Both this test and the isolated `CapabilityPaletteSection.test.tsx` fixture test pass (9 tests, 2 files). |
| 4  | EMP-01 — compose into user-allowed caps; selection reaches the run path | ✓ VERIFIED | FE `IdeaInputPage.handleRun` threads `selectionsRef.current` into `extraParams.selections`; `useWorkflow` merges via `Object.assign(payload, context)` into the `run_pipeline` message; WS reads `message_data.get("selections")` (632) → `execute(selections=...)` → `engine._apply_selections` (1140). Advanced expander exposes validator/gate/model/retry levers. WR-01 fix intact (unchanged by FE-only fix). |
| 5  | EMP-02 — trust/tier gating in UI AND server; smuggled cap rejected at SAVE + LAUNCH | ✓ VERIFIED | Palette renders `user_allowed=false` rows locked (`AgentsPopup.tsx:924`). Server: `_compile_selections_trust_user` (save, user_workflows.py:150) + `_revalidate_selections_trust_user` (launch, websocket.py:158); CR-01 fix adds `validate_selection_model_ids` at BOTH. `test_user_workflows_selections.py` save-reject + launch-reject green. Unaffected. |
| 6  | EMP-03 — saved workflows persist per-step selections, owner-scoped, IDOR→404, re-validated at launch | ✓ VERIFIED | Persisted in `manifest_json` (reused column, additive — no migration); `_owned()` raises 404; round-trip + IDOR→404 + launch-revalidate tested. `UserWorkflowSummary.selections` exposed (`api.ts:653-667`); `DashboardLayout.savedComposition.selections` re-loads on saved-workflow launch (WR-01, line 1204). Unaffected. |
| 7  | EMP-04 — selecting a cap requiring a gate auto-attaches it | ✓ VERIFIED | FE auto-attaches `validation` gate inline on validator select (`AgentsPopup.tsx:1148`, notice at 1343); backend synth seam mirrors it (`selections.py:101`); compiler §13 coupling backstop intact. Unaffected. |
| 8  | WIRE-01 — compiler materializes top-level + per-step `model:` | ✓ VERIFIED | `compiler.py:526` per-step `model=...`; `:247` top-level `model=workflow_model`; `Step(model=...)` at 544. Backend untouched by fix. |
| 9  | WIRE-02 — compiler materializes per-step `retry:` (FE numeric coerced to `{max_attempts}`) | ✓ VERIFIED | `compiler.py:527` `retry=...`; CR-02 fix `_coerce_retry` (selections.py:49) numeric → `{max_attempts:N}`, `0`→omit. Backend untouched. |
| 10 | WIRE-03 — `injects:` consumed or fails loud; no key accepted-but-dropped | ✓ VERIFIED | `compiler.py:528` `injects=...`; factory merges order-stable, name-free. Parametrized `test_allowed_step_keys.py` proves every `_ALLOWED_STEP_KEYS` entry is consumed-or-raises (INV-5). Backend untouched. |
| 11 | UXFIX-01 — catalog shows authored `display_name` | ✓ VERIFIED | `manifest.py` carries authored `display_name`; `WorkflowSummary.display_name` in `api.ts:557`. Unaffected. |
| 12 | UXFIX-02 — `deliverable_mimetype`/`filename` persist via additive migration 0022; reopen from persisted | ✓ VERIFIED | Migration `0022_*` (down_revision `0021`, two nullable `add_column`, additive); FE `index.ts` reopen reads persisted value (`RawWorkflowRun.deliverable_mimetype` normalized in `api.ts:297-298`). Goldens byte-identical. Unaffected. |
| 13 | UXFIX-03 — data-driven catalog is the default home | ✓ VERIFIED | `DashboardLayout.tsx` mounts `WorkflowCatalog` as the default `home` landing; `CreationHub.WORKFLOWS` no longer drives it. `DashboardLayout.catalogHome.test.tsx` green. Unaffected. |
| 14 | UXFIX-04 — generic mimetype renderer is the PRIMARY dispatch | ✓ VERIFIED | `PreviewPanel.tsx:473-508` — first-party types are routed table entries; null/custom/unknown falls through to `GenericDeliverablePreview` as the primary route. `PreviewPanel.genericDeliverable.test.tsx` green. Unaffected. |
| 15 | DECIDE-01 — ART-04 keep-by-default; 3 stale "confirm" labels reconciled; WAVE-03/N8 untouched | ✓ VERIFIED | `REQUIREMENTS.md:49` ART-04 keep-by-default (TTL opt-in); REPO-02/REPO-04/FANOUT-05 now SETTLED; WAVE-03 (N8) deliberately out of scope. Unaffected. |
| 16 | DECIDE-02 — MODEL-05 premium-open-to-all-tiers; model picker tier filter dropped | ✓ VERIFIED | `REQUIREMENTS.md:64` MODEL-05 premium-open + Haiku default/fallback; `AgentModelPicker.tsx:77-82` drops the `user_allowed` tier filter. `AgentModelPicker.test.tsx` green. Unaffected. |
| 17 | LIVE-01 — offline per-item evidence record covers all 8 standing deferrals; phase gates on offline (D-24) | ✓ VERIFIED | `22-LIVE-01-EVIDENCE.md` records all 10 sub-items with landed offline structural fix + DEFERRED-to-milestone-end-live-pass disposition; default profile (473293451041) + `claude-haiku-4-5`. Phase completion gates on offline evidence per the project `defer-live-verification` convention. Unaffected. |

**Score:** 17/17 must-have requirements verified

### Required Artifacts (key)

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `frontend/src/lib/api.ts` | `getWorkflowDetail(token,id)` → `GET /api/workflows/{id}` + types mirroring BE projection | ✓ VERIFIED | Lines 585-639: `WorkflowStepDetail`/`WorkflowDeliverable`/`WorkflowDetail` interfaces mirror `workflows.py:245-309`; `getWorkflowDetail` encodes the id, JWT-auth, 404 surfaced |
| `frontend/.../IdeaInputPage.tsx` | accept `workflowId`, fetch projection, map projection-sourced caps, pass `declaredCapabilities` | ✓ VERIFIED | `workflowId?` prop (65/182); useEffect fetch + cancelled-guard (263-302); projection-sourced mapping (281-291, no hardcoded names); prop passed to `<AgentsPopup>` (682); no-id ⇒ no fetch (264-267) |
| `frontend/.../DashboardLayout.tsx` | thread workflow id into IdeaInputPage (built-in + saved) | ✓ VERIFIED | `workflowId={workflowType}` at line 1212 (single live mount of IdeaInputPage) |
| `frontend/.../AgentsPopup.tsx` | `declaredCapabilities` prop → strip render | ✓ VERIFIED | Prop typed (79); forwarded to `CapabilityPaletteSection` (1659); SURF-03 strip with `length > 0` guard (871-889) now fed live |
| `frontend/.../IdeaInputPage.declaredCapabilities.test.tsx` | LIVE-path test (real page + popup, mock only network) | ✓ VERIFIED | Renders REAL IdeaInputPage + AgentsPopup; asserts `getWorkflowDetail` called + strip renders projection caps; pins no-id case; PASSES |
| `backend/app/api/workflows.py` | per-step compiled projection (strategy/gates/validators/task_source) | ✓ VERIFIED | `GET /{id}` (245-309): 404 on unknown id (path-traversal mitigation), compiles + projects each step; unchanged by FE fix |
| `backend/agents/workflows/compiler.py` | model/retry/injects pass-through | ✓ VERIFIED | Lines 526-548; top-level model 247 (unchanged) |
| `backend/agents/workflows/selections.py` | synth seam + CR-01/CR-02 | ✓ VERIFIED | `validate_selection_model_ids`, `_coerce_retry`, shared save+launch seam (unchanged) |
| `backend/alembic/versions/0022_*.py` | additive migration | ✓ VERIFIED | down_revision 0021, 2 nullable add_column, reversible (unchanged) |
| `.planning/REQUIREMENTS.md` | ART-04/MODEL-05 + 17 traceability rows | ✓ VERIFIED | All 17 IDs present (unchanged) |
| `22-LIVE-01-EVIDENCE.md` | per-item evidence | ✓ VERIFIED | 10 sub-items, default profile / Haiku 4.5 (unchanged) |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `IdeaInputPage` | `GET /api/workflows/{id}` | `getWorkflowDetail(jwt, workflowId)` in useEffect | ✓ WIRED | Call + `.then` populating state `setDeclaredCapabilities(mapped)` (274-292) |
| `IdeaInputPage` | `AgentsPopup` | `declaredCapabilities={declaredCapabilities}` prop | ✓ WIRED | Live call site line 682 (was the broken link — now connected) |
| `AgentsPopup` | `CapabilityPaletteSection` | `declaredCapabilities={declaredCapabilities}` | ✓ WIRED | Forwarded at 1659; consumed by strip at 871 |
| `DashboardLayout` | `IdeaInputPage` | `workflowId={workflowType}` | ✓ WIRED | Line 1212 — supplies the id that triggers the fetch |
| `workflows.py:get_workflow` | compiled `ExecutionPlan` | `compile_for_run(workflow_id)` → step projection | ✓ WIRED | Real compile + per-step projection (267-298), not static |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| CapabilityPaletteSection (palette) | `capabilities` | `fetchCapabilities()` → `GET /api/capabilities` | Yes (registry-backed) | ✓ FLOWING |
| CapabilityPaletteSection (SURF-03 strip) | `declaredCapabilities` | `IdeaInputPage` useEffect → `getWorkflowDetail(jwt,id)` → `GET /api/workflows/{id}` → mapped projection → prop | **Yes (live path)** | **✓ FLOWING** (was ✗ HOLLOW_PROP — fixed by 5d36a394) |
| engine `_apply_selections` | `selections` | WS `message_data.get("selections")` → execute → engine | Yes (live FE path) | ✓ FLOWING |
| AgentModelPicker | `models` | `getCapabilities().model_catalog` | Yes | ✓ FLOWING |

### Requirements Coverage

All 17 declared requirement IDs SATISFIED: SURF-01 ✓, SURF-02 ✓, **SURF-03 ✓ (live-path wired)**, EMP-01 ✓, EMP-02 ✓, EMP-03 ✓, EMP-04 ✓, WIRE-01 ✓, WIRE-02 ✓, WIRE-03 ✓, UXFIX-01 ✓, UXFIX-02 ✓, UXFIX-03 ✓, UXFIX-04 ✓, DECIDE-01 ✓, DECIDE-02 ✓, LIVE-01 ✓. No orphaned requirements.

### Behavioral Spot-Checks (re-verification)

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| SURF-03 live-path strip renders projection caps + no-id no-fetch; isolated palette fixture | `vitest run IdeaInputPage.declaredCapabilities.test.tsx CapabilityPaletteSection.test.tsx` | 9 passed (2 files) | ✓ PASS |
| Full FE suite (no regression from FE-only fix) | `vitest run` | 153 passed (21 files) | ✓ PASS |
| FE typecheck | `tsc --noEmit` | exit 0; only pre-existing `e2e/fixtures/mockApi.ts` readonly-cast errors (not touched by 5d36a394; last edited by 925e683a) | ✓ PASS (no new errors) |
| 5 characterization goldens (backend invariant — FE fix has no BE impact) | `pytest -k characterization` | 10 passed | ✓ PASS |
| SC-001 banned-patterns (kernel name-free) | `pytest -k banned_patterns` | 11 passed | ✓ PASS |
| No hardcoded capability-name list in IdeaInputPage mapping (SC-001) | `grep -E 'render_check|static_check|per_task_subagent|...' IdeaInputPage.tsx` | 0 matches | ✓ PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` declared for this phase (non-migration; verification driven by the targeted pytest + vitest suites above). Step 7c: SKIPPED (no declared probes).

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
| ---- | ------- | -------- | ------ |
| (key modified files: api.ts, IdeaInputPage.tsx, DashboardLayout.tsx) | TBD/FIXME/XXX | — | None — scan returned 0 unreferenced debt markers |
| IdeaInputPage.tsx / AgentsPopup.tsx | `declaredCapabilities` HOLLOW prop | — | RESOLVED — prop now populated on the live path (5d36a394); strip data FLOWING |

### Invariants

| Invariant | Status | Evidence |
| --------- | ------ | -------- |
| INV-3 — 5 characterization goldens byte/event-identical | ✓ | All 5 golden tests (10) pass post-fix (FE-only fix has no BE/deliverable impact) |
| SC-001 — kernel name-free + no hardcoded cap-name list in new FE | ✓ | `test_banned_patterns.py` (11 passed); IdeaInputPage mapping is purely projection-sourced (grep clean) |
| INV-13 — `create_deep_agent` only in adapter | ✓ | Backend untouched by FE-only fix |
| Ports & Adapters | ✓ | Backend untouched (no import-graph change) |
| INV-5 — no DSL, strict step-key | ✓ | `_ALLOWED_STEP_KEYS` untouched |
| Additive migrations only | ✓ | No migration in this fix (FE-only) |

### Gaps Summary

**No gaps remain.** The single prior gap (SURF-03 hollow on the live path) is closed by commit 5d36a394: the composer now fetches the compiled-plan projection (`getWorkflowDetail` → `GET /api/workflows/{id}`) when a known workflow id is opened, maps each step's declared capabilities entirely from the projection (no hardcoded names — SC-001), and feeds them into the AgentsPopup "Declared by this workflow" strip on the live path. A live-path test (real IdeaInputPage + real AgentsPopup, mocking only the network seam) proves the prop is populated and the strip renders — exactly the integration test the prior gap demanded. The SURF-03 SPEC acceptance ("opening a built-in launchable workflow in the composer shows its per-step declared capabilities sourced from the compiled plan, not a hardcoded description") is now met.

The FE-only fix touched exactly 4 files (`api.ts`, `IdeaInputPage.tsx`, `DashboardLayout.tsx`, + the new test) and is confirmed non-regressing: the full FE suite (153 tests) and the backend invariant gates (5 goldens + SC-001 banned-patterns) are all green; the other 16 must-haves remain VERIFIED. Phase goal achieved — capabilities VISIBLE (SURF-01/02) and COMPOSABLE (EMP-01..04 reaching execution with zero kernel branch), plus the WIRE/UXFIX/DECIDE/LIVE closures. **Final: 17/17, status `passed`.**

---

_Verified: 2026-06-15T00:30:00Z (re-verification after SURF-03 gap closure)_
_Verifier: Claude (gsd-verifier)_
