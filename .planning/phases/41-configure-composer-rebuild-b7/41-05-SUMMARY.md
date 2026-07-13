---
phase: 41-configure-composer-rebuild-b7
plan: 05
subsystem: ui
tags: [react, svg, node-graph, composer, canvas, selections, capabilities, vitest, playwright-fidelity]

# Dependency graph
requires:
  - phase: 41-04
    provides: full-page ComposerPage + Simple⇄Canvas toggle + the AgentsPopup shared data model (pipelineAgents + SelectionsMap + declaredCapabilities) and exported sub-components (AdvancedExpander/AgentPromptSection/getRole/getAgentInitials)
provides:
  - Composer Canvas view — a hand-rolled SVG node-graph (bezier edges + arrow markers under absolute-positioned agent nodes; Brief→agents left→right sequential chain; +-insert on edges + at the chain end; zoom/Fit)
  - Inline per-node config rail (Model dropdown · Validator toggle · amber Review-gate toggle · Retry stepper · reused Custom-prompt) matched to the approved proposal
  - 2×2 docked Run summary (Agents / Review-gate / Est-duration; est-cost omitted ND-AG) reusing the Simple view's computed summary data
  - Extracted shared lever primitives — applyLeverPatch (pure reducer) + useAgentCapabilities (fetch/filter hook) — the single writers/source for both AdvancedExpander and the Canvas rail (INV-3)
affects: [41-06, 41-07, composer, canvas, selections]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hand-rolled node-graph: an <svg> edge layer (no viewBox) sharing the stage px coordinate space with absolute-positioned node divs, so bezier endpoints computed from node left/top align with the nodes — NO graph/dnd library (D-04)"
    - "Shared lever logic extracted to pure helper (applyLeverPatch) + hook (useAgentCapabilities); every surface that writes a SelectionsMap entry delegates to the same reducer (INV-3, one writer)"
    - "Design-match gate (ND-AJ): a shipped surface with no .dc.html mock is captured populated via a guarded Playwright driver + assembled beside the vendored approved proposal for human sign-off"

key-files:
  created:
    - "frontend/src/components/workflow/composer/CanvasView.tsx"
    - "frontend/src/components/workflow/composer/CanvasNode.tsx"
    - "frontend/src/components/workflow/composer/CanvasConfigRail.tsx"
    - "frontend/src/components/workflow/composer/CanvasView.test.tsx"
  modified:
    - "frontend/src/components/workflow/composer/ComposerPage.tsx"
    - "frontend/src/components/workflow/composer/ComposerPage.test.tsx"
    - "frontend/src/components/workflow/AgentsPopup.tsx"
    - "frontend/e2e/tests/zzz-shell-baseline.spec.ts"
    - "frontend/e2e/fidelity/assemble-phase41-gallery.mjs"

key-decisions:
  - "GAP-1: the Canvas config rail renders the proposal's INLINE panel (Model dropdown + Validator/Review-gate toggles + Retry stepper) instead of the reused collapsed AdvancedExpander — but reuses the lever LOGIC via the extracted applyLeverPatch + useAgentCapabilities (INV-3, not forked)"
  - "GAP-2: the Canvas docked summary is the proposal's 2×2 stat-card grid built inline from the SAME summary data the Simple view computes; the Simple view keeps its SummaryRail (its mock uses tiles+rows)"
  - "Review-gate toggle attaches the first user_allowed non-validation gate generically (SC-001 — no hardcoded gate name); Validator toggle attaches the first user_allowed validator and applyLeverPatch auto-couples the validation gate (EMP-04)"
  - "ND-AL registered: Composer Custom-prompt (Simple + Canvas) reuses the shared AgentPromptSection rather than the proposal's inline editable textarea (INV-3 reuse; field present, presentation differs)"

patterns-established:
  - "applyLeverPatch(current, patch): the pure per-step selection reducer — patch + clear-unset + validator→gate coupling — extracted verbatim from AdvancedExpander.updateLever"
  - "useAgentCapabilities(token?): the /api/capabilities fetch + user_allowed kind-filter hook feeding the lever options"

requirements-completed: [CMPUI-03]

# Metrics
duration: ~80min
completed: 2026-07-14
---

# Phase 41 Plan 05: Composer Canvas view Summary

**Hand-rolled SVG node-graph Canvas view (bezier edges + absolute agent nodes) with an inline per-node config rail (Model/Validator/Review-gate/Retry/Custom-prompt) and a 2×2 docked Run summary — design-matched to the approved proposal (ND-AJ) and bound to the same shared SelectionsMap as the Simple view, with zero graph/dnd library.**

## Performance

- **Duration:** ~80 min (build + two design-match revision rounds)
- **Tasks:** 2 (Task 1 auto/TDD; Task 2 blocking design-match checkpoint — human-approved)
- **Files modified/created:** 9

## Accomplishments

- **Hand-rolled node-graph (D-04):** `CanvasView.tsx` renders an `<svg>` edge layer (bezier `path`s + grey/brand arrow markers `#arw`/`#arwb`) UNDER absolute-positioned `CanvasNode` cards in a left→right sequential chain, preceded by a dark Brief trigger pill. The edge into the selected node is tinted brand. `+` insert affordances sit on the edges and at the chain end (all call the shared add-agent path); zoom −/100%/+ and Fit controls. No graph/dnd library — the SVG shares the stage px coordinate space with the nodes so endpoints align.
- **Node cards:** avatar · name · role · Core badge (`getRole`) · model pill · Validator/Gate/Retry override chips (on/gate states derived from `SelectionsMap`) · l/r ports; click-select (brand ring), optional-agent remove.
- **Inline config rail (GAP-1, proposal-matched):** `CanvasConfigRail.tsx` — Model dropdown (whole catalog), Validator toggle, amber Review-gate toggle, Retry stepper (− N +), and the reused `AgentPromptSection` (Custom prompt). Lever writes go through the SHARED `applyLeverPatch`; options come from the SHARED `useAgentCapabilities` hook. Handlers fire on normal events (no setState-in-render), so no new warning.
- **2×2 docked Run summary (GAP-2, proposal-matched):** inline grid — Agents / Review-gate / Est-duration (est-cost omitted, ND-AG) + capability chips + Save-to-catalogue / Run-once (inert until 41-06), built from the same computed data the Simple view passes.
- **Shared-logic extraction (INV-3):** pulled `applyLeverPatch` (pure reducer) + `useAgentCapabilities` (fetch/filter hook) out of `AdvancedExpander`; `AdvancedExpander.updateLever` now delegates to `applyLeverPatch` and its fetch uses `useAgentCapabilities` — behavior-preserving, proven by the preservation battery below.

## Task Commits

1. **Task 1: hand-roll the Canvas view (TDD)** — `acb616be` (feat) — CanvasView/CanvasNode/CanvasConfigRail + wiring + CanvasView.test.tsx; ComposerPage.test.tsx stale "Canvas → placeholder" assertion updated.
2. **Populated Canvas fidelity capture driver** — `70fbab5d` (test) — guarded zzz-shell-baseline driver + assembler prefers the populated shot.
3. **Design-match closeout — inline rail + 2×2 summary** — `50164527` (feat) — GAP-1 + GAP-2 + the applyLeverPatch/useAgentCapabilities extraction + driver selects the gated node.

**Plan metadata:** this closeout commit (docs: SUMMARY + assembler ND-AL + STATE).

## Files Created/Modified

- `composer/CanvasView.tsx` — the hand-rolled node-graph (SVG edges + absolute nodes + rail + 2×2 docked summary).
- `composer/CanvasNode.tsx` — one agent node card (avatar/name/role/Core/model-pill/override-chips/ports).
- `composer/CanvasConfigRail.tsx` — the inline per-node config rail (Model/Validator/Review-gate/Retry + reused Custom-prompt).
- `composer/ComposerPage.tsx` — Canvas branch now mounts CanvasView (placeholder removed).
- `composer/CanvasView.test.tsx` — 12 behavior tests (nodes/edges, inline rail levers → SelectionsMap incl. validator→gate coupling, 2×2 summary, no-graph-lib + reuse guards).
- `composer/ComposerPage.test.tsx` — updated the one Canvas-toggle assertion to the node-graph contract.
- `workflow/AgentsPopup.tsx` — added exported `applyLeverPatch` + `useAgentCapabilities`; `AdvancedExpander` refactored to use both.
- `e2e/tests/zzz-shell-baseline.spec.ts` — populated Canvas capture driver.
- `e2e/fidelity/assemble-phase41-gallery.mjs` — prefer the populated Canvas shot; registered ND-AL; range refs bumped to ND-AE..AL.

## Decisions Made

See `key-decisions` frontmatter. Core: reuse the lever LOGIC (extracted helper + hook) while matching the proposal's inline presentation; keep the Simple view's SummaryRail unchanged; register ND-AL for the shared Custom-prompt presentation.

## Deviations from Plan

The plan built the config rail by mounting the reused `AdvancedExpander` (as the Simple view does). At the design-match checkpoint the reviewer required the proposal's inline levers + 2×2 summary instead. This was handled as design-match fixes (GAP-1/GAP-2), reusing the lever logic via the extracted `applyLeverPatch`/`useAgentCapabilities` so INV-3 holds (no forked lever code). Additive deviations:

- **[Rule 3 — capture infra]** Added a populated-Canvas capture driver to `zzz-shell-baseline.spec.ts` and taught the assembler to prefer the populated shot (mirrors the 41-04 populated-Simple driver) — outside the plan's `files_modified` but it is the capture harness the ND-AJ checkpoint drives.
- **[Rule 1 — superseded test]** Updated the `ComposerPage.test.tsx` "Canvas → placeholder" assertion (the placeholder was replaced by the real node-graph) and the `CanvasView.test.tsx` rail assertions (AdvancedExpander → inline levers) to the new contract.

**Total deviations:** 3 (1 design-match reviewer-directed, 1 capture-infra, 1 superseded-test). No scope creep; no new dependencies; no graph library.

## Issues Encountered

- **Behavior-preservation of the extracted lever logic** — verified via the full battery: `AdvancedExpander.test` + `AgentsPopup.reskin` + `ComposerPage.test` + `IdeaInputPage.selections` + `IdeaInputPage.modelOverrides` + `IdeaInputPage.declaredCapabilities` = **34/34 green**; `ts-e.model-picker` (mocked e2e) = **7 passed, 1 skipped** (env-gated no-jwt). The `selections`→`run_pipeline` contract (TS-E-03/04) is unchanged.
- **Known inherited warning (NOT introduced):** the shared `AdvancedExpander.updateLever` still calls `onSelectionsChange` inside its `setSelections` updater (setState-in-render dev warning when a lever changes) — the tracked follow-up from 41-04; left as-is (the Canvas rail is event-driven and does not reproduce it).

## Verify

- `npx tsc --noEmit` clean (excl. pre-existing `mockApi.ts`).
- `CanvasView.test.tsx` 12/12; `ComposerPage.test.tsx` 10/10.
- No graph/dnd lib in `composer/`; config rail reuses `applyLeverPatch`/`useAgentCapabilities`/`AgentPromptSection`/`SelectionsMap`.
- Populated Canvas capture `shots-shell/current/composer-canvas-populated__shell.png` (5 nodes, 5 edges, gated node selected → amber Review-gate toggle ON, brand active edge) assembled beside the approved proposal; **human design-match sign-off: APPROVED**.

## User Setup Required

None — FE-only, additive, no external service configuration.

## Next Phase Readiness

- CMPUI-03 met; the Canvas view is wired to the header toggle and the shared data model. Run-once is inert (wired in 41-06).
- **Wave 5 is NOT fully closed:** 41-07 is also Wave 5 and remains pending. 41-06 (Composer Run wiring) is next per the roadmap.

---
*Phase: 41-configure-composer-rebuild-b7*
*Completed: 2026-07-14*
