---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
plan: 06
subsystem: ui
tags: [composer, advanced-expander, emp-01, emp-04, decide-02, selections, manifest-json, react, vitest, sc-001]

# Dependency graph
requires:
  - phase: 22-04
    provides: "the compact per-step selections map {agent_id:{validators?,gates?,model?,retry?}} persisted in manifest_json + _apply_selections overlay + EMP-04 validation-gate coupling in selections.py"
  - phase: 22-05
    provides: "the embedded CapabilityPaletteSection + the live /api/capabilities palette payload the levers source their options from"
provides:
  - "AdvancedExpander — an exported per-agent (agent ≈ step) Advanced expander inside AgentsPopup exposing Validator -> Gate -> Model -> Retry levers (EMP-01)"
  - "The composer authors the EXACT compact selections map 22-04 persists in manifest_json; reported upward via onSelectionsChange (pure data, no new run endpoint, SC-001)"
  - "EMP-04 (D-07): a validator selection auto-attaches the validation gate inline + renders the role=status auto-attach notice (mirrors selections.py; the compiler stays the authoritative server backstop)"
  - "DECIDE-02 (D-23): the user_allowed tier filter dropped at AgentModelPicker:76 — premium models offered to ALL tiers"
  - "IdeaInputPage threads the selections map into the createUserWorkflow save payload as selections (extends the P21 triple)"
affects: [the saved-workflow save path (22-04 persistence + launch _apply_selections consumes these selections)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lever options derived from the palette payload by kind (user_allowed validators/gates + the full model catalog) — never a hardcoded option list (SC-001)"
    - "Composer-side EMP-04 coupling MIRRORS the server selections.py rule (validator -> validation gate); the compiler RAISES as the backstop, never auto-injects"
    - "Unselected lever omits its key (parity with the Default model semantics) — empty selections map -> omitted from the payload (INV-3 byte-identical)"
    - "Upward-report ref pattern (selectionsRef) mirroring modelOverridesRef so the popup reporting a selection does not re-render the page"

key-files:
  created:
    - frontend/src/components/workflow/AdvancedExpander.test.tsx
  modified:
    - frontend/src/components/workflow/AgentsPopup.tsx
    - frontend/src/components/workflow/AgentModelPicker.tsx
    - frontend/src/components/workflow/AgentModelPicker.test.tsx
    - frontend/src/components/workflow/IdeaInputPage.tsx
    - frontend/src/lib/api.ts

key-decisions:
  - "AdvancedExpander is exported from AgentsPopup (render-testable in isolation) but EMBEDDED in the composer — NOT a standalone file (Pitfall 1 / D-01 / D-05 consistency with CapabilityPaletteSection)."
  - "The Gate select shows the user-PICKED gate (the non-coupling one); the auto-attached `validation` gate is invisible in the select but always present in the selections map when a validator is chosen — so the user never has to manually re-add it and never accidentally removes it."
  - "The selections map omits any unselected lever key (parity with Default); an empty map is omitted from the save payload entirely so a no-advanced-selection save stays byte-identical (INV-3)."
  - "EMP-04 coupling rule mirrored from selections.py (validator => validation gate). The composer auto-attaches for UX; the compiler's §13 coupling check stays the authoritative server backstop (RAISES, never auto-injects)."

requirements-completed: [EMP-01, EMP-04, DECIDE-02]

# Metrics
duration: ~14min
completed: 2026-06-14
---

# Phase 22 Plan 06: Per-Agent Advanced Expander + EMP-04 Auto-Attach + DECIDE-02 Summary

**Added an exported, collapsed-by-default per-agent `AdvancedExpander` to `AgentsPopup` (agent ≈ step, D-05) exposing the representative lever-set Validator → Gate → Model → Retry sourced ENTIRELY from the live `/api/capabilities` palette (user_allowed caps + the model catalog, no hardcoded list — SC-001); selections feed the EXACT compact `{agent_id:{validators?,gates?,model?,retry?}}` map 22-04 persists in `manifest_json` and `_apply_selections` consumes, threaded into the `createUserWorkflow` save payload as `selections` (omitted when empty — INV-3); a validator selection auto-attaches the `validation` gate inline with a `role="status"` notice (EMP-04/D-07, mirroring `selections.py`; the compiler stays the server backstop); and the `user_allowed` tier filter at `AgentModelPicker.tsx:76` is dropped so premium models are offered to all tiers (DECIDE-02/D-23) — all FE tests + tsc on touched files green.**

## Performance
- **Duration:** ~14 min
- **Tasks:** 2 (TDD: RED → GREEN)
- **Files modified:** 6 (1 created test + 5 modified)

## Accomplishments
- **EMP-01 (Advanced expander):** `AdvancedExpander` (exported, embedded in the AgentsPopup Agents tab) renders a per-agent "Advanced" toggle (collapsed by default; `ChevronRight`→`ChevronDown`; `aria-expanded`/`aria-controls`) revealing lever rows in the fixed order Validator → Gate → Model → Retry, each reusing the gray lever-row chrome. Validator/gate options derive from the palette's `user_allowed` caps of those kinds; the model lever offers the full catalog; retry offers 1/2/3 attempts. No hardcoded option list (SC-001).
- **EMP-01 (selections reach the payload):** selecting a lever updates a per-step selections map `{agent_id:{validators?,gates?,model?,retry?}}` reported via the new `onSelectionsChange` prop (mirroring the `onModelOverridesChange` ref pattern). `IdeaInputPage` holds it in `selectionsRef` and threads it into the `createUserWorkflow` save payload as `selections` (the EXACT 22-04 shape) — omitted when empty so a no-advanced save stays byte-identical (INV-3). `onRun`/launch unchanged.
- **EMP-04 (auto-attach, D-07):** selecting ≥1 validator auto-attaches the `validation` gate to that agent's selections (deduped) and renders an inline `role="status"` notice ("Added required validation gate — this capability needs it.") — mirroring the server `selections.py` coupling. The composer auto-attaches; the compiler's §13 coupling check stays the authoritative server backstop (it RAISES, never auto-injects — RESEARCH anti-pattern).
- **DECIDE-02 (D-23):** dropped the `palette.model_catalog.filter((m) => m.user_allowed)` at `AgentModelPicker.tsx:76` — every catalog entry is now offered to every tier; the "Default" no-override option is kept. The server `_validate_model_overrides` (22-04) remains the authoritative allow-list.
- **Unselected-lever parity:** an unselected lever omits its key from the map (parity with "Default") — proven by test.

## Task Commits
1. **Task 1 — RED: Advanced-expander + EMP-04 auto-attach + DECIDE-02 picker tests** — `d9292ad5` (test)
2. **Task 2 — GREEN: AdvancedExpander + auto-attach + thread selections + drop tier filter** — `181ba454` (feat)

_Note: project-level `tdd_mode: false`, but the plan's tasks declare `tdd="true"`; the RED commit (`d9292ad5`, 6 failing) precedes the GREEN commit (`181ba454`, 10 passing). No REFACTOR pass needed._

## Files Created/Modified
- `frontend/src/components/workflow/AdvancedExpander.test.tsx` (NEW) — toggle/aria-expanded, lever order, selections-map feed (validator+gate+model+retry), EMP-04 validation-gate auto-attach (`role="status"`), unselected-lever-no-override, locked-gate-not-offered (6 cases).
- `frontend/src/components/workflow/AgentsPopup.tsx` — exported `AdvancedExpander` + `StepSelection`/`SelectionsMap` types; `onSelectionsChange` prop; the expander mount in the Agents tab; EMP-04 coupling + auto-attach notice.
- `frontend/src/components/workflow/AgentModelPicker.tsx` — dropped the `user_allowed` tier filter at :76 (DECIDE-02); updated header comment.
- `frontend/src/components/workflow/AgentModelPicker.test.tsx` — DECIDE-02 case: a premium catalog entry (incl. one flagged `user_allowed=false`) is offered to a free-tier user; "Default" survives.
- `frontend/src/components/workflow/IdeaInputPage.tsx` — `selectionsRef` + `handleSelectionsChange`; passes `onSelectionsChange` to AgentsPopup; threads `selections` into the `createUserWorkflow` save payload (omitted when empty).
- `frontend/src/lib/api.ts` — added optional `selections` to the `createUserWorkflow` body type (the compact per-step map).

## Decisions Made
- The Gate `<select>` reflects the user-PICKED gate (the non-coupling one); the auto-attached `validation` gate is always present in the selections map when a validator is chosen but is not the visible select value — so the user can never accidentally drop the coupling.
- `AdvancedExpander` is exported for isolated render-testing but stays EMBEDDED in `AgentsPopup` (NOT a standalone file — Pitfall 1 / D-01 consistency).
- Empty selections map ⇒ omitted from the save payload (INV-3 byte-identical), exactly like `model_overrides`.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
- `npx tsc --noEmit` reports exactly the 2 pre-existing `TS2352` const-assertion casts in `frontend/e2e/fixtures/mockApi.ts:95-96` (already recorded in this phase's `deferred-items.md` and noted in 22-02/22-05 SUMMARYs). Touched files (the new test + AgentsPopup/AgentModelPicker/IdeaInputPage/api.ts) are tsc-clean; `src/` is unaffected. Out of scope (SCOPE BOUNDARY).
- The SC-001 grep over `AgentsPopup.tsx` returns one hit — `pipelineType === "custom" ? 8 : 5` at :1418 — which is the PRE-EXISTING agent-capacity-limit branch (present at HEAD before this plan, verified via `git show HEAD:`), NOT a new workflow-name branch driving lever options. The lever options derive purely from the palette `kind` (zero name branches), satisfying the plan's acceptance ("no new workflow-name branch driving lever options").

## Known Stubs
None — the levers source live palette data, the selections feed the real save payload (22-04 persists + launch overlays them), and an unselected lever simply omits its key. No empty/placeholder data flows to any UI.

## Threat Flags
None — no new network endpoint, auth path, or schema change. The composer authors pure data into the existing `createUserWorkflow` payload; the authoritative trust gate is the server `compile(trust="user")` at SAVE + LAUNCH (22-04). The FE auto-attach (EMP-04) and the FE lock affordances are advisory only.

## Verification Evidence
- `AdvancedExpander.test.tsx` 6/6 + `AgentModelPicker.test.tsx` 3/3 (incl. DECIDE-02 + the 2 WR-01 regressions) + `IdeaInputPage.modelOverrides.test.tsx` 2/2 — all GREEN.
- Full `src/components/workflow/` sweep: 43/43 passing (6 files).
- `npx tsc --noEmit`: only the 2 pre-existing `mockApi.ts` errors; touched files clean.
- SC-001: no new workflow-name branch driving lever options (the single `AgentsPopup.tsx` grep hit is the pre-existing capacity limit, not a lever branch).
- No backend touched ⇒ lint-imports / banned-patterns untouched.

## Self-Check: PASSED
- FOUND: frontend/src/components/workflow/AdvancedExpander.test.tsx
- FOUND: frontend/src/components/workflow/AgentsPopup.tsx
- FOUND: frontend/src/components/workflow/AgentModelPicker.tsx
- FOUND: frontend/src/components/workflow/IdeaInputPage.tsx
- FOUND commit: d9292ad5 (Task 1 RED)
- FOUND commit: 181ba454 (Task 2 GREEN)

---
*Phase: 22-capability-surfacing-and-user-empowerment-universal-runtime-*
*Completed: 2026-06-14*
