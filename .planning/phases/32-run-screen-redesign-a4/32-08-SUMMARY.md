---
phase: 32-run-screen-redesign-a4
plan: 08
subsystem: ui
tags: [sc-2, sc-001, inv-3, iss-019, kan-99, kan-101, run-screen, steps-drilldown, wave-tree, inline-gate, tdd]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4 (plan 01)
    provides: "canonical token layer (@theme inline brand/ink/surface/line/status ramp + radius ladder)"
  - phase: 32-run-screen-redesign-a4 (plan 02)
    provides: "token-consuming primitives (Card/Badge/Button)"
  - phase: 32-run-screen-redesign-a4 (plan 05)
    provides: "reviewGateData.updateSpecsEligible/artifactKind flags + pipelineState markers"
  - phase: 32-run-screen-redesign-a4 (plan 06/07)
    provides: "the dormant gate/clarify passthrough props threaded DashboardLayout -> PreviewPanel -> AgentThinkingTab (laneGate + callbacks + clarifyQuestions)"
  - phase: 28-chat-contracts-guards-a0
    provides: "STEPS-ARTIFACT-DERIVATION-CONTRACT (dual-source construction §2, KAN-99 N-1 cap §3, L3 shape §4)"
  - phase: 31 (generic inline components)
    provides: "InlineGateActions / InlineClarifyActions (4 KAN behaviors + updateSpecsEligible + KAN-100 fence, SC-001-clean)"
provides:
  - "The Steps tab is a unified GENERIC drill-down that renders EVERY workflow (prototype included) off one agent-timeline + dual-source construction path — the drill-down knows no pipeline by name (SC-001, INV-3)"
  - "The SC-001 prototype-* render-path literals are GONE: AgentThinkingTab (isPrototypePipeline branch deleted), ReviewGatePanel (isSpec/isTasks/isAnalysis de-literalized), PrototypePipelineView (DELETED, superseded)"
  - "L3 construction is DUAL-SOURCE: task_progress (completed_count) merged with the wave/subagent tree; WaveTreePanel mounted INSIDE the drill-down (ISS-019 below-the-fold fix), relocated from the standalone left-column slot (INV-3 one mount)"
  - "KAN-99 N-1 cap: the construction checklist caps at total-1 until the construction agent truly completes (later-agent-started OR run-ended) — completed_count==total-1 is not a stall"
  - "Inline gate/clarify render in the Steps trace via the REUSED generic InlineGateActions/InlineClarifyActions (KAN-101/95/100/98), driven off updateSpecsEligible, over the same approve_review/submit_questionnaire channels"
affects: [plan-09 (AuditTab internals), plan-10 (color-class re-anchor), run-screen FE, Phase 37 (composer literal sites — untouched here)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Generic-drill-down-supersedes-bespoke-view: deleting the prototype-only PrototypePipelineView + its isPrototypePipeline literal branch, routing prototype runs through the same generic AgentThinkingTab path (INV-3 no dual impl)"
    - "Dual-source construction merge: task-universe = distinct wave taskIds (Source B), completion = protoCompletedTaskCount (Source A); WaveTreePanel mounted in the drill-down"
    - "KAN-99 terminal signal derived generically: construction agent (build/construct id family) done AND (a later agent started OR pipeline not running) — never a further task_progress"
    - "SC-001 renderer-selection off the DECLARED artifactKind + the artifact wrapper tag (<spec>/<tasks>/<analysis>) content sniff, never an agent-id literal; the Update-Specs affordance off the generic updateSpecsEligible flag (mirrors InlineGateActions)"
    - "Reuse of the generic InlineGateActions/InlineClarifyActions inline in Steps (one approve_review/submit_questionnaire channel regardless of surface)"

key-files:
  created:
    - frontend/src/components/results/__tests__/StepsDrilldown.test.tsx
  modified:
    - frontend/src/components/results/AgentThinkingTab.tsx
    - frontend/src/components/workflow/WaveTreePanel.tsx
    - frontend/src/components/preview/ReviewGatePanel.tsx
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/layout/DashboardLayout.waveMount.test.tsx
    - frontend/src/components/results/AgentThinkingTab.prototypePreamble.test.tsx
  deleted:
    - frontend/src/components/results/PrototypePipelineView.tsx
    - frontend/src/components/results/PrototypePipelineView.buildGate.test.tsx

key-decisions:
  - "PrototypePipelineView DELETED (not generalized) per INV-3's stated preference — its 3 positional phase-agent lookups (prototype-specify/plan/analyze) could not be generalized off a declared flag because AgentRunState carries no artifactKind, and the generic AgentThinkingTab render path is a complete superset renderer for all agents. The bespoke spec-page-map / task-checklist visualizations are superseded by the generic agent-timeline + the new dual-source ConstructionDrilldown."
  - "pipelineLabel gained a generic `id.startsWith('prototype-')` family rule so prototype runs still read 'Prototype Pipeline' in the unified header — a structural prefix, NOT one of the three gated prototype-specify/plan/analyze literals (grep-clean)."
  - "ReviewGatePanel renderer/label selection keys on artifactKind (spec/task_list/summary) with a name-free <spec>/<tasks>/<analysis> content-tag fallback; the analyze gate's kind is the generic 'summary' fallback (backend _artifact_kind_for), so the content tag is the load-bearing discriminator for AnalysisPreview."
  - "Update-the-Specs (ReviewGatePanel AND inline) renders off `updateSpecsEligible && onUpdateSpecs` — the generic server flag (kinds spec/task_list/summary) — replacing the isAnalysis literal gate. This is the intended SC-001 generalization (any spec-authoring gate can trigger the KAN-101 loop)."
  - "ISS-019 fixed by RELOCATING WaveTreePanel from the below-the-fold left-column slot into the Steps drill-down; waves threaded DashboardLayout -> PreviewPanel -> AgentThinkingTab; the standalone mount + import removed (INV-3 one WaveTreePanel mount). The DashboardLayout waveMount integration test re-anchored to assert the relocation."

patterns-established:
  - "Delete-if-superseded (INV-3): a bespoke, name-keyed view is removed once a generic superset renderer covers it — deleting the superseded code is part of the change."

requirements-completed: [SC-2]

# Metrics
duration: ~50min
completed: 2026-07-08
---

# Phase 32 Plan 08: Steps 3-Level Drill-Down + Dual-Source L3 + Inline Gate/Clarify + SC-001 De-literalization Summary

**The "Thinking" tab is restructured into a single GENERIC Steps drill-down that renders every workflow off one agent-timeline + a dual-source construction block (task_progress merged with the wave/subagent tree, WaveTreePanel now mounted INSIDE the drill-down — ISS-019 fixed), carries the KAN-99 N-1 checklist cap, hosts the paused gate/clarify inline via the REUSED generic InlineGateActions/InlineClarifyActions (KAN-101/95/100/98), and closes the SC-001 render-path literal leak by DELETING the prototype-only PrototypePipelineView and de-literalizing AgentThinkingTab + ReviewGatePanel — all reskinned to plan-01 tokens.**

## Performance
- **Duration:** ~50 min
- **Completed:** 2026-07-08
- **Tasks:** 3 (Task 2 + Task 3 TDD: RED -> GREEN)
- **Files:** 9 touched (1 created, 6 modified, 2 deleted)

## Accomplishments
- **Task 1 — unify the drill-down + SC-001 (SC-2/SC-001/INV-3):** deleted the `isPrototypePipeline` branch (the `["prototype-specify","prototype-plan","prototype-analyze",...].includes(a.id)` literal list) and the prototype-only `PrototypePipelineView` (+ its buildGate test); prototype runs now render through the generic agent-timeline path (INV-3). Reskinned AgentThinkingTab navy `#1B2A4A`/`#E8EDF5` to the plan-01 `brand`/`brand-fill` tokens (raw `#1B2A4A`/`#2563eb` = 0). Added a generic `prototype-` family label so the header still reads "Prototype Pipeline". Guarded the running-agent `scrollIntoView` (jsdom/webview safety).
- **Task 2 — L3 dual-source + WaveTreePanel + KAN-99 (SC-2/ISS-019, TDD):** wrote the StepsDrilldown fixtures FIRST (RED), then added `ConstructionDrilldown` merging `task_progress` (`protoCompletedTaskCount`) with the wave/subagent tree; mounted `WaveTreePanel` inside the drill-down and RELOCATED it from the below-fold left slot (threaded `waves` DashboardLayout -> PreviewPanel -> AgentThinkingTab; removed the standalone mount + import; INV-3 one mount). KAN-99 N-1 cap enforced (checklist caps at total-1 until the construction agent truly completes). Reskinned WaveTreePanel status chips to the plan-01 status tokens (IN-05 cancelled -> failed-terminal).
- **Task 3 — inline gate/clarify + ReviewGatePanel SC-001 (SC-2/KAN cluster, TDD):** wrote the inline-gate/clarify fixtures FIRST (RED), then consumed the plan-06/07 passthrough props and rendered `InlineGateActions`/`InlineClarifyActions` inline in the Steps trace (Update-the-Specs off `updateSpecsEligible`, KAN-100 terminal fence, retained edit, reject-confirm, canonical `[{question_id,answer}]` emit — all inherited). De-literalized `ReviewGatePanel`: dropped the `agentId === "prototype-specify"/"prototype-plan"/"prototype-analyze"` checks — icon/label/description + preview renderer now key on the declared `artifactKind` + the artifact wrapper tag, and Update-the-Specs off `updateSpecsEligible` (DashboardLayout forwards both flags).

## Task Commits
1. **Task 1: unify drill-down + remove prototype-* literals** — `e26a2e47` (feat)
2. **Task 2 (RED): failing StepsDrilldown fixtures** — `808ee7a0` (test)
3. **Task 2 (GREEN): L3 dual-source + WaveTreePanel + KAN-99 cap** — `971437f0` (feat)
4. **Task 3 (RED): failing inline gate/clarify assertions** — `b62bdb3e` (test)
5. **Task 3 (GREEN): inline gate/clarify + ReviewGatePanel de-literalize** — `aec51b0e` (feat)

## Files Created/Modified
- `frontend/src/components/results/__tests__/StepsDrilldown.test.tsx` (created) — 8 scripted-fixture tests: dual-source merge, KAN-99 N-1 cap (2/3 while running, 3/3 on agent_complete), WaveTreePanel-mounted-in-drilldown, inline gate render + Update-Specs gated on updateSpecsEligible + KAN-100 fence, inline clarify canonical emit.
- `frontend/src/components/results/AgentThinkingTab.tsx` (modified) — deleted the SC-001 prototype branch + PrototypePipelineView import; token reskin; `ConstructionDrilldown` (dual-source + KAN-99 cap); `waves` prop + WaveTreePanel mount; consumed gate/clarify passthrough via InlineGateActions/InlineClarifyActions; scrollIntoView guard.
- `frontend/src/components/workflow/WaveTreePanel.tsx` (modified) — status chips + accents reskinned to plan-01 status/brand tokens (raw hex 0; IN-05 preserved).
- `frontend/src/components/preview/ReviewGatePanel.tsx` (modified) — de-literalized isSpec/isTasks/isAnalysis off artifactKind + content-tag; Update-Specs off updateSpecsEligible; added `artifactKind`/`updateSpecsEligible` props.
- `frontend/src/components/preview/PreviewPanel.tsx` (modified) — `waves` passthrough prop forwarded to AgentThinkingTab.
- `frontend/src/components/layout/DashboardLayout.tsx` (modified) — relocated WaveTreePanel (removed standalone mount + import; forward `waves` to PreviewPanel); forward `artifactKind`/`updateSpecsEligible` to ReviewGatePanel.
- `frontend/src/components/layout/DashboardLayout.waveMount.test.tsx` (modified) — re-anchored to the relocation (stub PreviewPanel renders the real WaveTreePanel from its forwarded `waves`; asserts no below-fold slot).
- `frontend/src/components/results/AgentThinkingTab.prototypePreamble.test.tsx` (modified) — re-anchored to the unified generic path.
- `frontend/src/components/results/PrototypePipelineView.tsx` + `.buildGate.test.tsx` (deleted) — superseded (INV-3).

## Decisions Made
See `key-decisions` frontmatter. Headline: PrototypePipelineView DELETED per INV-3 (generalization infeasible without an artifactKind on AgentRunState); renderer selection keyed on artifactKind + content-tag; Update-Specs off the generic updateSpecsEligible flag; ISS-019 fixed by relocating the WaveTreePanel mount into the drill-down.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Guarded running-agent scrollIntoView**
- **Found during:** Task 1 (unified path exposed a latent crash).
- **Issue:** Once prototype runs route through the generic path, the running-agent auto-scroll effect calls `runningRef.current.scrollIntoView` — unimplemented in jsdom (and possibly some webviews) — throwing `TypeError` and failing the prototypePreamble spec.
- **Fix:** Guarded with a `typeof el.scrollIntoView === "function"` check (defensive render, T-32-08-02).
- **Files modified:** `AgentThinkingTab.tsx`.
- **Verification:** results/ 36/36 green.
- **Committed in:** `e26a2e47`.

**2. [Rule 3 - Blocking] Threaded `waves` through PreviewPanel + DashboardLayout (outside files_modified)**
- **Found during:** Task 2 (ISS-019 relocation).
- **Issue:** Mounting WaveTreePanel INSIDE the drill-down + removing the below-fold standalone mount requires `waves` to reach AgentThinkingTab, which flows only via PreviewPanel <- DashboardLayout — both outside the plan's `files_modified`.
- **Fix:** Added an optional `waves` passthrough on PreviewPanel; DashboardLayout forwards `waves` to PreviewPanel and drops the standalone `<WaveTreePanel>` mount + its now-unused import (INV-3 one mount). Re-anchored the DashboardLayout `waveMount` integration test to assert the relocation.
- **Files modified:** `PreviewPanel.tsx`, `DashboardLayout.tsx`, `DashboardLayout.waveMount.test.tsx`.
- **Verification:** layout + preview suites green; tsc 0.
- **Committed in:** `971437f0`.

**3. [Rule 3 - Blocking] Forwarded artifactKind/updateSpecsEligible to ReviewGatePanel (DashboardLayout, outside files_modified)**
- **Found during:** Task 3 (ReviewGatePanel de-literalization).
- **Issue:** De-literalizing ReviewGatePanel requires the declared `artifactKind`/`updateSpecsEligible` flags at its mount; DashboardLayout (outside files_modified) owns that mount.
- **Fix:** Added the two props to the ReviewGatePanel mount (values already on `reviewGateData`).
- **Files modified:** `DashboardLayout.tsx`.
- **Verification:** preview/ReviewGatePanel 7/7 green; SC-001 grep 0.
- **Committed in:** `aec51b0e`.

**4. [Test re-anchor] prototypePreamble + waveMount tests updated for intentional relocations**
- **Found during:** Tasks 1 + 2.
- **Issue:** The prototypePreamble test asserted the deleted PrototypePipelineView's "Prototype Pipeline" via the bespoke phase view + a now-invalid DOM order; the waveMount test asserted the removed below-fold mount.
- **Fix:** Re-anchored both to the new reality (generic path; relocated wave mount) — the delta of intentional changes, not a masked regression.
- **Committed in:** `e26a2e47` (prototypePreamble), `971437f0` (waveMount).

---

**Total deviations:** 3 auto-fixed (1 missing-critical, 2 blocking) + 2 test re-anchors. **Impact:** all necessary for the relocation/de-literalization + tsc-identity; no scope creep — the composer literal sites (AgentsPopup/AgentLibraryData, Phase 37) were NOT touched; the generic dispatch, sandboxed-iframe contract, and AuditTab signature are untouched.

## Issues Encountered
- **Pre-existing, out-of-scope failures (logged, NOT fixed):** 5 `workflow/` failures surfaced by the broad delta suite, all in files this plan never touched and none importing my changed files:
  1. `AgentProgressPanel.test.tsx > "_revision completion … filter"` (documented pre-existing since plan 06).
  2–4. `ReviewGatesSection.test.tsx` — LIBRARY_AGENTS count reconciliation (ppt=3/prototype=4/all=54) + membership + the no-gates onChange payload (AgentLibraryData / Phase 37 territory).
  5. `IdeaInputPage.declaredCapabilities.test.tsx` — SURF-03 live-fetch (network-gated).
  Structurally impossible for a WaveTreePanel/AgentThinkingTab/ReviewGatePanel reskin to cause (data reconciliation + network fetch). Logged to `deferred-items.md` per the scope boundary.

## Verification Observed
- **StepsDrilldown (new):** `npx vitest run …/StepsDrilldown.test.tsx` -> **8/8 green** (dual-source, KAN-99 2/3 -> 3/3, WaveTree mounted, inline gate/clarify + updateSpecsEligible gating + KAN-100 fence + canonical clarify emit).
- **results/ suite:** **36/36 green** (buildGate test removed with its component; prototypePreamble re-anchored).
- **layout/ + preview/ suites:** green (waveMount re-anchored 4/4; ReviewGatePanel 7/7; preview 43/43).
- **Delta suite** `vitest run results/ workflow/ preview/ReviewGatePanel.test.tsx`: **103 passed, 5 pre-existing failures** (enumerated above) — no NEW behavioral failure; the reskin's color-class changes are expected (plan 10 re-anchors).
- **tsc identity:** `npx tsc --noEmit | grep -v mockApi.ts | grep -c "error TS"` = **0**.
- **SC-001 grep:** `grep -ciE "prototype-specify|prototype-analyze|prototype-plan"` over `AgentThinkingTab.tsx` = **0** and `ReviewGatePanel.tsx` = **0** (and PrototypePipelineView deleted).
- **Raw hex:** `grep -cE "#1B2A4A|#2563eb"` = **0** in AgentThinkingTab AND WaveTreePanel.
- **KAN-99:** the cap holds at N-1 (2/3) while running and reaches N (3/3) only on agent_complete — asserted; no stall at total-1.
- **WaveTreePanel mounted in drill-down:** asserted in StepsDrilldown + the re-anchored waveMount (renders inside the Preview/Steps surface, no below-fold slot).
- **Phase 37 sites untouched:** `AgentsPopup.tsx` / `AgentLibraryData.ts` ABSENT from the plan diff (confirmed).

## User Setup Required
None — pure FE restructure/reskin + render of already-received WS state; no package install, no env, no new network/auth surface.

## Known Stubs
None. The construction task-universe falls back to the task-loop count when no waves are present, and WaveTreePanel owns its own "No waves running." empty state — both are real defensive-render paths, not empty-data UI stubs.

## Threat Flags
None — no new trust boundary. T-32-08-01 mitigated (Steps/gate keyed on generic event/artifact kinds + updateSpecsEligible; SC-001 grep 0 across AgentThinkingTab + ReviewGatePanel). T-32-08-02 mitigated (defensive rendering of scripted-fixture event shapes; statusKind neutral fallback; scrollIntoView guarded; no crash on missing wave/task fields). T-32-08-03 mitigated (inline gate reuses InlineGateActions' KAN-100 !isPipelineRunning fence — asserted).

## Next Phase Readiness
- The Steps tab is a unified, name-free, token-reskinned drill-down with dual-source L3, KAN-99, inline gate/clarify, and WaveTreePanel above the fold. Plan 09 owns AuditTab internals (signature untouched). Plan 10 re-anchors any color-class assertions changed by the reskin. Phase 37 owns the composer/config literal sites (AgentsPopup/AgentLibraryData), deliberately left untouched.

## Self-Check: PASSED

- Files: StepsDrilldown.test.tsx, AgentThinkingTab.tsx, WaveTreePanel.tsx, ReviewGatePanel.tsx, PreviewPanel.tsx, DashboardLayout.tsx — all FOUND; PrototypePipelineView.tsx + buildGate.test.tsx — DELETED (confirmed absent).
- Commits: `e26a2e47`, `808ee7a0`, `971437f0`, `b62bdb3e`, `aec51b0e` — all present in git log.
- Guardrails: SC-001 grep 0 (AgentThinkingTab + ReviewGatePanel); raw hex 0; tsc 0; StepsDrilldown 8/8; KAN-99 N-1 cap enforced; WaveTreePanel mounted in drill-down (relocated, INV-3 one mount); AgentsPopup/AgentLibraryData absent from diff.

---
*Phase: 32-run-screen-redesign-a4*
*Completed: 2026-07-08*
