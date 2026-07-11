---
phase: 39-run-screen-mock-fidelity-b5
plan: 02
subsystem: ui
tags: [steps, react, drill-down, waves, context-sources, fidelity, screenshot-diff, tailwind-tokens]

# Dependency graph
requires:
  - phase: 39-07
    provides: repaired mocked-e2e harness + fidelity screenshot oracle (capture-mocks / assemble-gallery / zzz-baseline)
  - phase: 32
    provides: Steps 3-level drill-down + dual-source construction + KAN-99 cap + inline gate/clarify + Phase-32 token layer
  - phase: 39-01
    provides: runStats (formatDuration/formatTokenCount) + parseFailedAgents (resolveAgentNames/buildAgentNameById) reuse pattern
provides:
  - "Steps tab rebuilt to the mock's three-level navigation: overview spine → 2-column agent detail (sticky Context received) → task detail"
  - "StepsOverviewSpine.tsx — L1 overview (stepper progress → Starting-point → collapsed Clarifications → agent spine with approved-gate strips)"
  - "AgentDetailPanel.tsx — L2 2-column agent detail + sticky Context-received panel + the reconciled single nested construction block"
  - "TaskDetailPanel.tsx — L3 single-task detail"
  - "Construction reconciled to ONE integrated nested waves→tasks block (separate WaveTreePanel retired from Steps)"
  - "Approved-gate strips fetched live via getRunGateEvents and mapped to agents by step (ND-M resolved)"
  - "ND register extended to ND-P (task↔wave grouping) in the fidelity gallery"
affects: [39-03, 39-04, 39-05, 39-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "AgentThinkingTab as a three-view state machine (overview | agentDetail | taskDetail) mirroring the mock's stepView/taskView"
    - "Shared formatContextSource() helper (single derivation for the sticky Context panel — INV-12)"
    - "Task↔wave join on the trailing integer of each taskId, with a single-group fallback when the join is unclean (ND-P)"

key-files:
  created:
    - frontend/src/components/results/StepsOverviewSpine.tsx
    - frontend/src/components/results/AgentDetailPanel.tsx
    - frontend/src/components/results/TaskDetailPanel.tsx
  modified:
    - frontend/src/components/results/AgentThinkingTab.tsx
    - frontend/src/components/results/ClarificationsCard.tsx
    - frontend/src/components/results/AgentThinkingTab.test.tsx
    - frontend/src/components/results/__tests__/StepsDrilldown.test.tsx
    - frontend/e2e/tests/ts-j.streaming.spec.ts
    - frontend/e2e/tests/ts-k.wave-tree.spec.ts
    - frontend/e2e/tests/zzz-baseline.spec.ts
    - frontend/e2e/fixtures/dashboard.ts
    - frontend/e2e/fidelity/assemble-gallery.mjs
    - frontend/e2e/fidelity/capture-mocks.mjs

key-decisions:
  - "Three-view state machine in AgentThinkingTab; the flat AgentTimelineCard vertical list retired (INV-3) — its sub-sections re-home inside AgentDetailPanel"
  - "Deep-Planner card DROPPED from the Steps overview to match the mock; the live Starting-point (run input) card KEPT (ND-K, human-approved live extra)"
  - "Approved-gate strips derive from the live getRunGateEvents endpoint (the Audit tab's source), mapped to their agent by step — no invented gate data; ND-M resolved"
  - "Construction reconciled to ONE nested waves→tasks block; the separate WaveTreePanel 'Wave / Subagent tree' is retired from Steps (still used by DashboardLayout / PreviewPanel / dashboard page)"
  - "Wave labels display 1-based to match the mock; wave kind (parallel/sequential) derived from concurrent-worker count; wave badge from lifecycle status"
  - "Per-task tool calls (ND-N) and per-task duration (ND-O) omitted — no live per-task field; never fabricated"
  - "SC-001: the former isPrototypePipeline branch removed — every workflow renders through the generic overview→detail drill"

patterns-established:
  - "Pattern 1: Steps surfaces derive every value from live AgentRunState / pipelineState (ND-D) — no cloned mock transcript"
  - "Pattern 2: reused renderers/helpers (InlineGateActions, InlineClarifyActions, ClarificationsCard, StartingPointCard, runStats, parseFailedAgents) not rebuilt (INV-12)"

requirements-completed: [RUNUI-06, RUNUI-08]

# Metrics
duration: ~3h (single session, multi-checkpoint)
completed: 2026-07-11
---

# Phase 39 Plan 02: Steps Tab Summary

**The Steps tab rebuilt to the mock's three-level drill — overview spine → 2-column agent detail with a sticky Context-received rail → task detail — all off live events, with the construction fan-out reconciled into ONE nested "waves → tasks" block.**

## Performance

- **Duration:** ~3h (single session across the plan's build + fidelity checkpoints)
- **Started:** 2026-07-11T15:32:40+02:00 (first task commit)
- **Completed:** 2026-07-11T18:44:01+02:00 (construction reconciliation)
- **Tasks:** 2 auto tasks + 1 blocking human-verify checkpoint (with a ruled-on reconciliation iteration)
- **Files modified:** 3 created + ~10 modified (components, tests, e2e harness, page object, fidelity assembler)

## Accomplishments

- **L1 overview spine** (`StepsOverviewSpine.tsx`): status line + segmented per-agent progress, the live Starting-point card, a collapsed **Clarifications** card rebuilt to the mock, and a compact navigable agent spine with the two **approved-gate strips** ("Review gate — {gate} · approved by you") fetched via `getRunGateEvents` and mapped by `step`.
- **L2 agent detail** (`AgentDetailPanel.tsx`): a `1fr 288px` grid — full execution on the left (reasoning · artifact · tools · full input · output, token-reskinned) and a `position:sticky` **"Context received"** panel built from live `agent.contextSources` (name + size/compression, "N sources fed in", kernel footer).
- **Reconciled construction block**: the former DUAL representation (a flat task list PLUS a separate "Wave / Subagent tree") is merged into the mock's SINGLE integrated "Construction · waves & subagents · N/N done" block with build **tasks NESTED under their wave** (wave header shows kind + status badge). Separate wave tree retired from Steps (INV-12).
- **L3 task detail** (`TaskDetailPanel.tsx`): a single construction task's status node, "Task N · {title}", and reasoning card from the live task summary; opened from a nested `construction-task-row`, back-navigating to L2.
- **Live + failed states** folded in: running row → Live pill + animated segment + streaming caret / "Reasoning (live)"; failed → red reason card + skipped "Not run" rings + "Pipeline halted" banner (derived from pipeline state, `parseFailedAgents` reused).
- **SC-001**: the `isPrototypePipeline` name-gate removed — every workflow renders through the same generic drill.
- **Fidelity harness**: `zzz-baseline` captures the internals (overview → detail → construction → task); the gallery pairs them against the mocks with the ND-A..ND-P register.

## Task Commits

1. **Task 1: L1 overview spine + L2 2-column agent detail + sticky Context panel** — `60958d10` (feat)
2. **Task 2: L3 task detail + live/failed states on the overview spine** — `6359544e` (feat)
3. **e2e re-anchor to the redesigned drill-down** — `02523b4c` (test)
4. **Fidelity-capture fixes (drill testid + failed seeding)** — `a3f81e40` (test)
5. **Overview pixel-as-is to the mock (order + rebuilt Clarifications)** — `89eb3141` (fix)
6. **Approved-gate strips on the settled spine + drop the Deep-Planner card** — `c6d222b9` (fix)
7. **Capture the Steps internals + fix two L3 task-detail defects** — `35fdbd3b` (fix)
8. **Reconcile the construction split into one nested waves→tasks block** — `5976a3a0` (fix)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `StepsOverviewSpine.tsx` (NEW) — L1 overview spine: stepper progress, Starting-point, collapsed Clarifications, agent spine, approved-gate strips, halted banner.
- `AgentDetailPanel.tsx` (NEW) — L2 2-column agent detail, sticky Context-received panel, the reconciled nested construction block, shared `formatContextSource` helper.
- `TaskDetailPanel.tsx` (NEW) — L3 single-task detail.
- `AgentThinkingTab.tsx` — restructured into overview/agentDetail/taskDetail views; flat `AgentTimelineCard` list retired; construction data threaded to L2/L3.
- `ClarificationsCard.tsx` — rebuilt to the mock's collapsible Clarifications card.
- `AgentThinkingTab.test.tsx`, `StepsDrilldown.test.tsx` — re-anchored to the three-level nav + the single nested block.
- `ts-j.streaming.spec.ts`, `ts-k.wave-tree.spec.ts`, `zzz-baseline.spec.ts` — re-anchored to the redesigned Steps + nested block; Build-Agent context seeded.
- `dashboard.ts` (e2e page object) — `waveHeading/waveEmpty/waveGroup` retargeted to the nested block (1-based labels).
- `assemble-gallery.mjs` / `capture-mocks.mjs` — Steps internal captures + ND-A..ND-P register (ND-L split RESOLVED, ND-P added).

## Intended-Divergence Register (ND-A..ND-P)

Steps-relevant entries the human signed off (full list in `frontend/e2e/fidelity/assemble-gallery.mjs`):

- **ND-D** — every Steps value is LIVE from `AgentRunState`/`pipelineState`, never the mock's fixed 97s/30.1k/14.8M transcript (SC-001).
- **ND-K** — the live **Starting-point** (run input) card is KEPT below the stepper (mock's clean overview omits it); the **Deep-Planner** card was DROPPED to match the mock.
- **ND-L** — the mock's per-agent artifact preview (pages/task-count/checks grid) has no live structured field, so we surface the real "Agent output"; the Build Agent's construction fan-out IS reproduced live. **RESOLVED (39-02): the fan-out no longer renders as two blocks — it is the single nested waves→tasks block (INV-12).**
- **ND-N** — L3 per-task **tool calls** omitted: the live trace records tool calls at the agent level, not per subagent task.
- **ND-O** — per-task **duration** omitted: `protoCompletedTasks` carries `{number,title,summary}` with no timing field; never fabricated (applies to the L3 line AND the nested task row).
- **ND-P** (NEW) — **task↔wave grouping**: joined on the trailing integer of each `taskId`; when the join cleanly covers every task, tasks nest under their own wave, else ALL tasks nest under a single wave group (still one integrated block).

## Reused (not rebuilt) — INV-12

- `runStats` — `formatDuration` / `formatTokenCount` (shared with 39-01).
- `parseFailedAgents` — `resolveAgentNames` / `buildAgentNameById` for the halted banner.
- `getRunGateEvents` — the Audit tab's live gate source, reused for the approved-gate strips.
- `InlineGateActions` / `InlineClarifyActions` — inline gate/clarify submit channels unchanged.
- `ClarificationsCard` / `StartingPointCard` — reused (Clarifications restyled to the mock).
- `WaveTreePanel` — RETAINED for its other consumers (DashboardLayout, PreviewPanel, dashboard/page); only its Steps usage was retired.

## Decisions Made

See `key-decisions` in the frontmatter. Headline: three-view state machine; Deep-Planner dropped / Starting-point kept; live gate strips via `getRunGateEvents`; construction reconciled to one nested block; 1-based wave labels; per-task tools/duration omitted; name-gate removed.

## Deviations from Plan

None as auto-deviations. The construction reconciliation (commit `5976a3a0`) was a **human-ruled fidelity fix at the blocking checkpoint**, not an unplanned auto-fix: the initial build rendered the fan-out as two blocks (a flat task list + the reused WaveTreePanel), and the human ruled to merge them into the mock's single nested block before approval. This was executed within the plan's files + the fidelity harness, then re-verified and re-approved.

## Issues Encountered

- **Construction "split" at the checkpoint** — the first cut satisfied the plan's literal dual-source contract (checklist + wave tree) but diverged from the mock's single integrated block. Resolved by nesting tasks under waves (ND-P join) and retiring the separate tree; the Build-Agent Context panel also showed "0 sources fed in" and was fixed by seeding a real `agent_input` (tasks.md + spec.md) in the harness.
- **Coupled specs** — removing the standalone wave tree broke `StepsDrilldown` vitest + `ts-k.wave-tree` e2e + the `dashboard` page object (they asserted "Wave / Subagent Tree" / worker leaves / "Wave 0"). Re-anchored to the nested block (construction header, 1-based wave groups, nested `construction-task-row`, `construction-empty` affordance).

## Verification

- `npx tsc --noEmit` — clean (0 errors, excluding the pre-existing `mockApi.ts` baseline).
- **vitest — 18 pass**: `StepsDrilldown.test.tsx`, `AgentThinkingTab.test.tsx`, `DashboardLayout.waveMount.test.tsx`.
- **e2e — 11 pass**: `ts-j.streaming` (8) + `ts-k.wave-tree` (3), mocked project.
- **Fidelity capture — 5 pass** (`zzz-baseline`); gallery regenerated: the Steps section = 6 paired mock/ours shots, `steps-construction__settled` shows the single nested block + "2 sources fed in".
- Touched-component `gray-*` palette count: 0.
- Human sign-off: Steps approved across overview / L2 detail / reconciled construction block / L3 task detail, closed to ND-A..ND-P.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **39-03 (Files tab)** is next in Wave 2: dark Final-output hero + agent-outputs timeline + Run-input cards. It reuses the same token layer and the `runStats`/`parseFailedAgents` helpers already in place; no dependency on Steps internals.
- RUNUI-06 / RUNUI-08 (phase-level, already Complete) advanced by this plan; RUNUI-07 / RUNUI-09 remain open for later waves.

## Self-Check: PASSED

- Created files verified on disk: `StepsOverviewSpine.tsx`, `AgentDetailPanel.tsx`, `TaskDetailPanel.tsx`, `39-02-SUMMARY.md`.
- All 8 task commits verified in git history: `60958d10`, `6359544e`, `02523b4c`, `a3f81e40`, `89eb3141`, `c6d222b9`, `35fdbd3b`, `5976a3a0`.

---
*Phase: 39-run-screen-mock-fidelity-b5*
*Completed: 2026-07-11*
