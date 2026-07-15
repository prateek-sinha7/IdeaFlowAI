---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 09
subsystem: ui
tags: [react, nextjs, run-screen, artifact-cards, agent-detail, artifactPreview, discriminateArtifact]

# Dependency graph
requires:
  - phase: 42-05
    provides: shared name-free artifactPreview module (discriminateArtifact + SpecPreview/TasksPreview/AnalysisPreview)
provides:
  - "Settled agent-detail artifact cards (pages/sections · tasks · checks) keyed on the shared discriminator"
  - "Handoff line derived from dagEdges (producer→consumer + artifact label) with next-agent fallback"
  - "Exported pure deriveArtifactCardModel helper (card kind + data + handoff) for reuse/testing"
affects: [42-11 phase-reconcile, run-screen-fidelity, agent-detail]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Card TYPE selected by the name-free discriminateArtifact (never an agent/workflow id literal — SC-001)"
    - "Conditional-degrade cards: an agent with no recognized artifact tag (or a tasks agent with empty protoCompletedTasks) renders exactly as today (no card)"
    - "Brittle output-parses reuse the shared preview parsers and are explicitly flagged with registered backend/additive follow-ups (F1/F2)"

key-files:
  created:
    - frontend/src/components/results/AgentDetailPanel.artifactCards.test.tsx
  modified:
    - frontend/src/components/results/AgentDetailPanel.tsx
    - frontend/src/components/results/AgentThinkingTab.tsx

key-decisions:
  - "Handoff line renders ONLY alongside an artifact card (hasCard gate) so the build agent + no-artifact agents stay byte-unchanged (matches the human-check: 'Build Agent still shows only its unchanged construction card')."
  - "discriminateArtifact is called with agent.output only (AgentRunState has no artifactKind field) — content-tag sniff, name-free."
  - "New card data threaded via optional props (agents/agentIndex/protoCompletedTasks/protoCompletedTaskCount/dagEdges) from AgentThinkingTab — absent → no cards (generic degrade)."

patterns-established:
  - "Pure exported derivation helper + thin render component: deriveArtifactCardModel is unit-tested in isolation; SettledArtifactCards renders it."

requirements-completed: [RUNUI-06, RUNUI-07, RUNUI-08]

# Metrics
duration: ~35min
completed: 2026-07-15
---

# Phase 42 Plan 09: Settled Agent-Detail Artifact Cards Summary

**Three conditional, generically-keyed artifact cards (pages/sections · tasks · checks) + a dagEdges-derived handoff line in the settled L2 agent detail, reusing the shared artifactPreview module — frontend-only, zero backend/golden/transport change, with the two brittle output-parses (F1/F2) flagged and deferred.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-07-15T01:50Z
- **Completed:** 2026-07-15T02:00Z
- **Tasks:** 3
- **Files modified:** 3 (2 modified, 1 created)

## Accomplishments
- Added the exported pure `deriveArtifactCardModel(agent, index, agents, data)` helper — picks the card kind via the shared name-free `discriminateArtifact`, derives the tasks rows/count from `protoCompletedTasks`, the checks badge from `validationPassed`/`validationIssues`, and the handoff target from `dagEdges` (with next-agent fallback).
- Rendered the three settled cards between the reasoning block and the tool calls: pages/sections (reused `SpecPreview`), tasks ("N planned" in brand `#3C2CDA` + a row per task title), checks (green verdict badge `#1F7A4D` on `#E7F0EA`, reused `AnalysisPreview`), plus the handoff line (down-arrow + "{artifact_type} → {next agent}").
- Cards render CONDITIONALLY on the generic discriminator: a tasks agent with empty `protoCompletedTasks` (single_shot) and any no-artifact agent render exactly as today (no card); the handoff line is gated to card-bearing agents so the Build Agent's construction card is untouched.
- Registered the two brittle-parse follow-ups (F1 coverage/counts aggregate, F2 sections extractor) as OUT-OF-SCOPE backend/additive follow-ups in code comments + this SUMMARY's deferred items.

## Task Commits

Each task was committed atomically (conventional-commits, no trailer):

1. **Task 1: Card-type selection + data derivation (helper + tests)** — `662d4d98` (feat) — TDD: RED (9 failing helper tests) → GREEN (`deriveArtifactCardModel`).
2. **Task 2: Render the three cards + handoff line** — `0da355a5` (feat) — `SettledArtifactCards` + prop wiring in `AgentThinkingTab`; +4 render tests.
3. **Task 3: Register F1/F2 brittle-parse follow-ups OUT OF SCOPE** — `2c33a6ff` (docs) — consolidated F1/F2 registration block + inline site markers.

## Files Created/Modified
- `frontend/src/components/results/AgentDetailPanel.tsx` — `deriveArtifactCardModel` + `deriveHandoff` helpers, `SettledArtifactCards` render component, new optional props, F1/F2 registration + brittle markers.
- `frontend/src/components/results/AgentThinkingTab.tsx` — threads `agents`/`agentIndex`/`protoCompletedTasks`/`protoCompletedTaskCount`/`dagEdges` into the L2 `AgentDetailPanel`.
- `frontend/src/components/results/AgentDetailPanel.artifactCards.test.tsx` — 13 tests: helper card-selection + conditional degrade + handoff (dagEdges/fallback/none) + SC-001 name-free selection, plus rendered-card + no-card-build-agent cases.

## Decisions Made
- **Handoff gated to card-bearing agents.** The plan's human-check requires the Build Agent to show "only its (unchanged) construction card"; rendering the handoff line only when an artifact card is shown keeps the build agent and all no-artifact agents byte-unchanged while still matching the mock for spec/tasks/analysis agents.
- **`discriminateArtifact(agent.output)` (no artifactKind arg).** `AgentRunState` carries no `artifactKind` field, so the content-tag sniff is the sole (name-free) signal — consistent with `InlineGateActions`'s existing usage.

## Deviations from Plan

None — plan executed exactly as written. No auto-fixes required. No package installs. No backend/golden/transport touched (verified: `git diff --name-only 662d4d98^..HEAD | grep -Ec "\.py|backend/|golden|api/|useWorkflow|useRunStream"` == 0).

**Minor implementation note (not a deviation):** the plan's Task-2 acceptance grep `grep -c "dangerouslySetInnerHTML" == 0` initially tripped on my own explanatory comment ("no dangerouslySetInnerHTML"); reworded to "no raw-HTML injection" so the guard reads 0. No functional change — the cards never use `dangerouslySetInnerHTML`.

## Deferred Items (OUT OF SCOPE — for 42-11 reconcile)

- **F1 — structured coverage/counts aggregate.** A `{coverage,counts{P0..P3}}` aggregate on `GET /runs/{id}/validation-results` (backend/additive, goldens untouched). Until then the checks card's coverage/verdict TEXT is a BRITTLE parse of the analyzer's `<analysis>` output via the reused `AnalysisPreview`. Flagged in code at the checks card.
- **F2 — event-free `sections` extractor.** An additive `sections` extractor + `/artifacts?kind=sections` (backend/additive). Until then the pages/sections card is a BRITTLE parse of the spec agent's `<spec>` `## ` headings via the reused `SpecPreview`. Flagged in code at the pages card.

Both are backend/additive, outside this plan's frontend-only fence (SC-001/LOCK-B). Any card needing them = OUT OF SCOPE → flagged, not built.

## Issues Encountered
None.

## Verification

- **tsc:** `npx tsc --noEmit` — 0 errors (excluding pre-existing `mockApi`).
- **New tests GREEN:** `npx vitest run AgentDetailPanel.artifactCards` — 13/13 pass (helper selection + conditional degrade + handoff + SC-001 + rendered cards + no-card build agent).
- **Baseline held EXACTLY:** full `npx vitest run` — 8 failed / 694 passed. The 8 failures are exactly the pre-existing set in the same 4 files (`PreviewPanel.switcher`×3, `PreviewPanel.degraded`×1, `HomeLaunchGrid.inspect`×2, `FilesTab.runInput`×2). Zero net-new failures; +13 new tests all green.
- **FE-only:** cumulative plan diff = 3 frontend files (`AgentDetailPanel.tsx`, `AgentDetailPanel.artifactCards.test.tsx`, `AgentThinkingTab.tsx`); backend/transport grep == 0.
- **Guards:** `discriminateArtifact` present (3); no NEW name-gate (`/build|construct/i|prototype-|pipeline_type|spec.id ==` == 0); `dangerouslySetInnerHTML` == 0; `construction-block` testid preserved (KEEP); `dagEdges` referenced (12); brittle/F1/F2 flags present (12).
- **Fidelity harness:** `FIDELITY_CAPTURE=1 npm run e2e -- zzz-baseline` — 8/8 passed, including "CAPTURE settled prototype run" (drives the settled Steps surface where the cards render). No crash.

## Confirmations (per task brief)
- The three cards render CONDITIONALLY on the generic `discriminateArtifact` (never an agent/workflow-id literal — SC-001), with the handoff line from `dagEdges`/order fallback.
- The KEEP construction card (build agent), the Context-received panel, and the reasoning/tool/input/output sections are untouched; an agent with no recognized artifact tag renders exactly as today (no card, no handoff).
- F1/F2 are flagged in code and deferred (backend/additive, out of the FE-only fence) — not built.

## Next Phase Readiness
- Cards ship on the §9-verified frontend data path; no engine/golden dependency introduced.
- 42-11 reconcile should fold F1 (coverage/counts aggregate) + F2 (sections extractor) into the register as backend/additive follow-ups.

## Self-Check: PASSED

- All 4 files exist on disk (3 source/test + SUMMARY).
- All 3 task commits present in git history (`662d4d98`, `0da355a5`, `2c33a6ff`).

---
*Phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-*
*Completed: 2026-07-15*
