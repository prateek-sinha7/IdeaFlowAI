---
phase: 37-configure-unification-composer-wizard-b3
plan: 03
subsystem: ui
tags: [react, tailwind-v4, design-tokens, composer, capabilities, user-workflows, vitest]

# Dependency graph
requires:
  - phase: 32-tokens
    provides: "@theme token layer (brand/ink/surface/line ramps) consumed by the reskin"
  - phase: 35-shell-chrome-reskin-pages-b1
    provides: "Phase-35 token discipline (per-file retired-palette=0 + positive @theme usage)"
  - phase: 37-01
    provides: "Wave-1 groundwork this composer reskin builds on"
provides:
  - "Composer (AgentsPopup) reskinned onto Phase-32 tokens with every P22 reuse contract intact"
  - "Footer Save workflow wired to owner-scoped createUserWorkflow via NameWorkflowModal"
  - "AgentsPopup.reskin.test.tsx pinning COUPLED_GATE, retry-int, user_allowed lock, Save-wire, no-visibility, no-AgentModelPicker-mount, retired-palette=0"
affects: [composer, wizard, configure-screen, agent-drawer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Source-scan vitest gate: read component source, assert retired-palette regex has 0 matches (RED-first token gate)"
    - "Callback-mirror: intercept onSelectionsChange to keep a local liveSelections copy for the save payload while still forwarding upward"

key-files:
  created:
    - frontend/src/components/workflow/AgentsPopup.reskin.test.tsx
  modified:
    - frontend/src/components/workflow/AgentsPopup.tsx
    - frontend/src/components/workflow/AgentLibrary.tsx

key-decisions:
  - "Retired navy #1B2A4A -> brand token utilities (text-brand/bg-brand/border-brand + /opacity variants); #E8EDF5 -> brand-fill; #c8d4e8 -> brand-border; #f5f5f0 -> var(--surface-warm)"
  - "AgentModelPicker standalone NOT mounted (INV-3): inline live-catalog Model lever already satisfies per-agent model selection"
  - "Save payload omits empty model_overrides/selections maps (INV-3 byte-identical)"

patterns-established:
  - "Reskin = className/style token swap only; behavior, constants, and data flow untouched and test-pinned"

requirements-completed: [SHELL-04]

# Metrics
duration: ~35min
completed: 2026-07-09
---

# Phase 37 Plan 03: Composer (AgentsPopup) Reskin Summary

**Reskinned the composer (capability palette + AdvancedExpander + AgentLibrary) onto Phase-32 brand tokens with zero P22 regression, and wired the footer Save to the owner-scoped createUserWorkflow via NameWorkflowModal.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-09
- **Tasks:** 2 (both TDD, RED→GREEN)
- **Files modified:** 3 (2 modified, 1 created)

## Accomplishments
- All 16 retired-palette hits in AgentsPopup.tsx and both in AgentLibrary.tsx migrated to `@theme` tokens (per-file gate now 0).
- Every shipped P22 reuse contract preserved verbatim and test-pinned: COUPLED_GATE='validation' auto-attach + notice, RETRY_OPTIONS=[1,2,3] as ints, live `/api/capabilities` registry render, `user_allowed=false` Engineer-only lock.
- Footer "Save workflow" now opens the existing NameWorkflowModal and, on confirm, calls owner-scoped `createUserWorkflow` with `{name, description?, base_pipeline_type, agent_ids, model_overrides?, selections?}` — live per-step selections mirrored into the payload.
- `AgentsPopup.reskin.test.tsx` (11 tests) pins the token gate, the four reuse contracts, ND-12 (no visibility/sharing), INV-3 (no AgentModelPicker mount), and the Save behavior.

## Task Commits

1. **Task 1 (RED): reskin contract test** - `cdfd01c8` (test)
2. **Task 1 (GREEN): reskin palette + AdvancedExpander to tokens** - `93fe3ad3` (refactor)
3. **Task 2 (RED): extend test for Save-wire + AgentLibrary gate** - `62d7faab` (test)
4. **Task 2 (GREEN): wire Save->createUserWorkflow + reskin AgentLibrary** - `fa371118` (feat)

## Files Created/Modified
- `frontend/src/components/workflow/AgentsPopup.tsx` - Token reskin of CapabilityPaletteSection, AdvancedExpander, ICON_STYLES, AgentPromptSection badges, flow-grid drag border, and library button; Save-to-catalogue wiring (state + handler + NameWorkflowModal render); selections mirror.
- `frontend/src/components/workflow/AgentLibrary.tsx` - `#f5f5f0` inline backgrounds -> `var(--surface-warm)`.
- `frontend/src/components/workflow/AgentsPopup.reskin.test.tsx` - NEW reskin contract test (11 tests).

## Decisions Made
- Mapped the retired navy accent `#1B2A4A` to the canonical `brand` token (matching sibling reskins TemplateGallery/DesignSystemPicker), including `/5` and `/15` opacity variants for tinted fills/borders.
- Kept the pre-existing 3 explanatory `AgentModelPicker` comments (lines ~50/64/1008) — they are references to the pattern, not a mount/import; the corrected gate (`<AgentModelPicker|import.*AgentModelPicker`) is 0.
- Save closes the popup on success; owner-only CRUD is the whole surface (ND-12 controls declared out — no visibility/team-sharing field).

## Deviations from Plan

### Recorded drift finding (per plan instruction)

**AgentModelPicker gate — plan literal is a defect; used the corrected gate.**
- **Found during:** Task 2.
- **Issue:** The plan's acceptance literal `grep -c "AgentModelPicker" AgentsPopup.tsx == 0` is unsatisfiable without deleting 3 pre-existing explanatory COMMENTS (lines ~50/64/1008) that legitimately reference the pattern and are NOT a mount. This matches the 37-CONTEXT 2026-07-09 amendment: the standalone `AgentModelPicker.tsx` is dead code (imported only by its own test); the inline live-catalog Model lever (`AdvancedExpander`, live catalog, threads via `updateLever`) already satisfies per-agent model selection, so re-mounting would be an INV-3 dual-implementation.
- **Resolution:** Did NOT mount or import the standalone component; did NOT delete the 3 comments. Pinned the REAL invariant via the corrected gate `grep -cE '<AgentModelPicker|import.*AgentModelPicker' == 0` (verified 0) and a test assertion.
- **Committed in:** `fa371118` (test in `62d7faab`).

### Comment wording adjustment (self-inflicted, fixed inline)
- **Found during:** Task 2 GREEN.
- **Issue:** My first-draft code comments contained the words "visibility"/"team-sharing", tripping the ND-12 gate `grep -cEi 'visibility|just me|team-shar|shared with' == 0`.
- **Fix:** Reworded the two comments to "ND-12 controls DECLARED OUT — owner-only CRUD is the whole surface"; gate back to 0.
- **Committed in:** `fa371118`.

---

**Total deviations:** 1 recorded drift finding (AgentModelPicker gate) + 1 inline comment fix. No behavioral or data changes — this was a LOOK change only.
**Impact on plan:** None on scope. Reuse-over-rebuild honored throughout.

## Issues Encountered
- `import.meta.url` did not resolve as a file URL under this vitest setup (`TypeError: The URL must be of scheme file`). Switched the source-scan test to `resolve(process.cwd(), "src/components/workflow/...")` — vitest runs with cwd at the frontend root.

## Evidence (raw gate outputs)

Reskin test: `Test Files 1 passed (1) / Tests 11 passed (11)`.
Pre-existing composer tests (regression check): `Test Files 3 passed (3) / Tests 17 passed (17)`.

Reuse contracts (`AgentsPopup.tsx`):
- `grep -c 'COUPLED_GATE'` = 7 (>=7) ✓
- `grep -c 'RETRY_OPTIONS = [1, 2, 3]'` = 1 (==1) ✓
- `grep -ci 'CAPDEF'` = 0 (==0) ✓
- `grep -c 'user_allowed'` = 10 (>=10) ✓
- `grep -c 'createUserWorkflow'` = 3 (>=1) ✓
- `grep -cE '<AgentModelPicker|import.*AgentModelPicker'` = 0 (==0) ✓
- `grep -cEi 'visibility|just me|team-shar|shared with'` = 0 (==0) ✓

Token gate (retired palette): AgentsPopup.tsx = 0, AgentLibrary.tsx = 0 ✓
tsc identity: `npx tsc --noEmit | grep -v mockApi.ts | grep -c error` = 0 ✓

Mocked Playwright e2e: LIVE-DEFERRED (offline webServer timeout) — not run per plan.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Composer reskin complete; the Configure screen / stepper waves can compose these token-clean surfaces.
- No blockers. STATE.md and ROADMAP.md intentionally left untouched per execution guardrails.

---
*Phase: 37-configure-unification-composer-wizard-b3*
*Completed: 2026-07-09*

## Self-Check: PASSED
- All 4 files present on disk (AgentsPopup.tsx, AgentLibrary.tsx, AgentsPopup.reskin.test.tsx, 37-03-SUMMARY.md).
- All 4 task commits present in git log (cdfd01c8, 93fe3ad3, 62d7faab, fa371118).
