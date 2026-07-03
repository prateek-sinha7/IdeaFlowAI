---
phase: quick-260703-byv
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/results/AgentThinkingTab.tsx
  - frontend/src/components/results/PrototypePipelineView.tsx
  - frontend/src/components/results/AgentThinkingTab.prototypePreamble.test.tsx
  - frontend/src/components/results/PrototypePipelineView.buildGate.test.tsx
autonomous: true
requirements:
  - FIX-1-prototype-preamble       # StartingPointCard + ClarificationsCard never render for the prototype pipeline
  - FIX-2-build-flash-gate         # build checklist flashes all-done at every between-task transition

must_haves:
  truths:
    - "In the PROTOTYPE Thinking view (both live-after-build-starts AND every reopen), StartingPointCard and ClarificationsCard render as a preamble ABOVE PrototypePipelineView — all three present in narrative order Starting point → Clarifications → prototype phases."
    - "A prototype run with runInput but NO clarify shows StartingPointCard and NO ClarificationsCard (ClarificationsCard returns null for a PROCEED run)."
    - "The prototype build checklist NEVER flashes all-tasks-completed during a between-task transition (buildAgent status 'done' while the run is still running and no later phase has started); it keeps showing realtimeCompletedCount-done."
    - "When the build loop truly ends (a later phase/agent started OR the run is no longer running), all build tasks show completed."
    - "tsc-identity gate holds: exactly 3 total `error TS` occurrences AND 0 after filtering mockApi|IdeaInputPage → GATE_OK (identity check, not a file:line grep)."
    - "Regression guard: every audited suite that renders AgentThinkingTab / PrototypePipelineView / PreviewPanel / WorkflowHistory / FilesTab / DashboardLayout / AgentProgressPanel runs GREEN."
    - "INV-3 by construction: `git status --porcelain backend` is empty (FE-only; engine + 5 characterization goldens untouched)."
  artifacts:
    - path: "frontend/src/components/results/AgentThinkingTab.tsx"
      provides: "isPrototypePipeline branch renders StartingPointCard + ClarificationsCard preamble, then PrototypePipelineView"
      contains: "isPrototypePipeline"
    - path: "frontend/src/components/results/PrototypePipelineView.tsx"
      provides: "buildTrulyDone gate replacing transient buildStatus==='done'/buildIsDone at the terminal render sites"
      contains: "buildTrulyDone"
    - path: "frontend/src/components/results/AgentThinkingTab.prototypePreamble.test.tsx"
      provides: "Rendered-DOM spec: prototype run with runInput+clarifications → all three render; runInput no-clarify → StartingPoint present, Clarifications absent"
      min_lines: 40
    - path: "frontend/src/components/results/PrototypePipelineView.buildGate.test.tsx"
      provides: "Rendered-DOM spec: mid-loop (build done, isRunning true, not all tasks done) → NOT all completed; terminal (run ended) → all completed"
      min_lines: 40
  key_links:
    - from: "AgentThinkingTab.tsx isPrototypePipeline branch"
      to: "StartingPointCard + ClarificationsCard"
      via: "same prop expressions as the main render (input=runInput / originalBriefRootRunId / revisionParentVersion; clarifications=resolvedClarifications; loading=clarificationsLoading)"
      pattern: "StartingPointCard"
    - from: "PrototypePipelineView currentTaskIndex + TaskListVisualization allDone/currentTaskIndex + Phase-4 Build card"
      to: "buildTrulyDone"
      via: "substituted for buildStatus==='done'/buildIsDone at all terminal sites; currentTaskIndex falls back to realtimeCompletedCount during the transient-done window"
      pattern: "buildTrulyDone"
---

<objective>
Fix TWO FE-only defects in the prototype Thinking view. ZERO backend, reuse-first (placement + one boolean gate; no new hex/radius/font, no new workflow-name branch — keep the existing `isPrototypePipeline` agent-id check, SC-001).

- FIX 1 (Phase-25 C2 completeness gap): `StartingPointCard` + `ClarificationsCard` never render for the PROTOTYPE pipeline because `AgentThinkingTab` early-returns `<PrototypePipelineView/>` BEFORE the main render where those cards live. Hoist them as a preamble above the prototype view.
- FIX 2 (pre-existing day-one flash): the build checklist flashes ALL tasks "completed" at every between-task transition because the backend emits `agent_complete{prototype-build}` at the END of EACH task (INV-3 parity-locked — MUST NOT change), which flips the single FE `prototype-build` row to `done`, and the view derives all-done from that transient status. Introduce a `buildTrulyDone` gate so a TRANSIENT between-task "done" cannot mark all tasks complete.

Purpose: correct the prototype timeline narrative (Starting point → Clarifications → phases) and stop the false all-complete flash.
Output: 2 modified components + 2 new rendered-DOM vitest specs; backend byte-identical.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@./CLAUDE.md

# FIX 1 lives here — the isPrototypePipeline early-return (:604–:611) and the main-render card usages (:634 StartingPointCard, :646 ClarificationsCard)
@frontend/src/components/results/AgentThinkingTab.tsx

# FIX 2 lives here — the build-status derivation (:396–:407, :421) and the render sites (:521–:522, :589, :622); TaskListVisualization (:319–:371)
@frontend/src/components/results/PrototypePipelineView.tsx

# Reuse targets — do NOT re-author these cards
@frontend/src/components/results/StartingPointCard.tsx
@frontend/src/components/results/ClarificationsCard.tsx

# Test idioms to clone (render + screen + vi.mock TokenUsageSummary; AgentRunState/PipelineRunState fixtures)
@frontend/src/components/results/AgentThinkingTab.narrativeOrder.test.tsx
@frontend/src/components/results/StartingPointCard.test.tsx
@frontend/src/components/results/ClarificationsCard.test.tsx
</context>

<tasks>

<task type="auto">
  <name>Task 1 (FIX 1): Hoist StartingPointCard + ClarificationsCard as a preamble above PrototypePipelineView</name>
  <files>frontend/src/components/results/AgentThinkingTab.tsx</files>
  <action>
In the main export `AgentThinkingTab` (destructures `{ agents, pipelineState, runInput, originalBriefRootRunId, revisionParentVersion, clarifications, clarificationsLoading }` at ~:589), replace the bare early return at ~:610–611:

  `if (isPrototypePipeline) { return <PrototypePipelineView agents={agents} pipelineState={pipelineState} />; }`

with a branch that ALSO renders the two already-authored cards as a PREAMBLE, THEN the pipeline view — reusing the EXACT prop expressions already present in the main render (do NOT re-author, do NOT invent new props):
  - `<StartingPointCard input={runInput} originalBriefRootRunId={originalBriefRootRunId} revisionParentVersion={revisionParentVersion} />` — copied verbatim from the main-render usage at ~:634–638.
  - `<ClarificationsCard clarifications={resolvedClarifications} loading={clarificationsLoading} />` — copied verbatim from ~:646, where `resolvedClarifications = clarifications ?? pipelineState?.clarifications` (~:599) is already in scope above the early return.

Narrative order is Starting point → Clarifications → [prototype phases]. Wrap the two preamble cards in a container that matches the main-render wrapper (`className="... px-4 py-4 space-y-3"`, the same timeline `space-y-3` spacing the cards' `relative pl-8` dots expect) so the timeline styling is preserved, then render `<PrototypePipelineView agents={agents} pipelineState={pipelineState} />` below it. Use a fragment or a `flex flex-col` wrapper as the surrounding brownfield style dictates so scroll/height is preserved — match the existing layout idiom, introduce no new tokens.

Do NOT touch: the `isPrototypePipeline` agent-id check (~:607–609, SC-001 — keep it), the `hasAnyData`/EmptyState guard (~:600–604), the main-render card usages (~:634/:646 stay for the non-prototype path), or the two upstream mounts (PreviewPanel ~:746, WorkflowHistory ~:791 already thread runInput/clarifications/originalBriefRootRunId/revisionParentVersion into AgentThinkingTab — unchanged).

Note (correct-by-design, no code needed): `ClarificationsCard` already returns null for a PROCEED run (no rounds, not loading), so a clarify-less prototype correctly shows no Clarifications card.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && npx vitest --run src/components/results/AgentThinkingTab.narrativeOrder.test.tsx</automated>
  </verify>
  <done>The `isPrototypePipeline` branch renders StartingPointCard + ClarificationsCard (via resolvedClarifications + clarificationsLoading) as a preamble, then PrototypePipelineView. No card re-authored, no new props/tokens, the agent-id check and the two mounts untouched. narrativeOrder suite green.</done>
</task>

<task type="auto">
  <name>Task 2 (FIX 2): Introduce buildTrulyDone gate so a transient between-task "done" cannot mark all tasks complete</name>
  <files>frontend/src/components/results/PrototypePipelineView.tsx</files>
  <action>
FIRST, CONFIRM against the current source which terminal signals genuinely exist in THIS component (do not assume from the root-cause text): in `PrototypePipelineView` the derivations at ~:396–422 include `realtimeCompletedCount` (~:396), `buildIsDone` (~:397), `buildIsRunning` (~:398), `totalTasks` (~:399), `buildStatus`/`validateStatus` (via `getStatus`, ~:421–422), and `pipelineState?.isRunning`. The research proposed `buildStatus === "done" && (validateStatus !== "idle" || pipelineState?.isRunning === false)` — but for a prototype the build agent may be the LAST agent (no separate validate phase), so `pipelineState?.isRunning === false` is the load-bearing clause; `validateStatus !== "idle"` covers the case where a later phase started. Use WHICHEVER of these terminal signals actually exist in the file — do not add a signal the component does not already have.

Define `const buildTrulyDone = buildStatus === "done" && (validateStatus !== "idle" || pipelineState?.isRunning === false);` (adjust the OR clauses to the confirmed signals). Then substitute `buildTrulyDone` for the TRANSIENT `buildStatus === "done"` / `buildIsDone` checks at the terminal render sites, and — critically — keep the checklist showing the real completed count during the between-task window:

  1. `currentTaskIndex` (~:403–407): use `buildTrulyDone` for the "all done → totalTasks" branch, and make the "in-progress → realtimeCompletedCount" branch ALSO cover the transient-done window (not just `buildIsRunning`). Between tasks the agent status is "done" while the run is still running, so `buildIsRunning` is false there — the index MUST fall back to `realtimeCompletedCount` (via `buildIsRunning || (buildStatus === "done" && !buildTrulyDone)`, or equivalent), NEVER -1, so `TaskListVisualization`'s `i < currentTaskIndex` keeps the already-completed tasks checked.
  2. `TaskListVisualization` invocation (~:521–522): `allDone={buildTrulyDone}` (was `buildStatus === "done"`). Keep `currentTaskIndex={buildStatus === "idle" ? -1 : currentTaskIndex}`.
  3. Phase-4 Build card body (~:589 live block, ~:622 "All N tasks completed" block): gate the "All {N} tasks completed" summary (~:622) on `buildTrulyDone` (was `buildStatus === "done"`), and ensure the live per-task block (~:589, currently `buildStatus === "running"`) also renders during the transient-done window so the card never goes blank AND never flashes all-complete between tasks (e.g. show it whenever `tasksData && !buildTrulyDone`). Confirm the exact gating against the current JSX before editing.

Do NOT change `protoCompletedTaskCount` / `realtimeCompletedCount` (correct as-is). Do NOT touch the backend or any lifecycle-event emission — the between-task `agent_complete{prototype-build}` stays (INV-3 parity-locked). Robustness: because the checklist tracks `realtimeCompletedCount` until `buildTrulyDone`, the final all-done shows correctly even if the model skips `report_task_complete` on the last task (the terminal signal, not the count, drives all-done).
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && npx vitest --run src/components/results/PrototypePipelineView.buildGate.test.tsx 2>/dev/null || echo "buildGate spec created in Task 3"</automated>
  </verify>
  <done>`buildTrulyDone` derived from the CONFIRMED terminal signals present in the file. Substituted at currentTaskIndex, TaskListVisualization allDone, and the Phase-4 "All N completed" block; currentTaskIndex falls back to realtimeCompletedCount (not -1) during the transient-done window; the live per-task block covers that window. protoCompletedTaskCount and the backend untouched.</done>
</task>

<task type="auto">
  <name>Task 3 (Tests + gates): Rendered-DOM specs, regression guard, tsc-identity, backend-clean</name>
  <files>frontend/src/components/results/AgentThinkingTab.prototypePreamble.test.tsx, frontend/src/components/results/PrototypePipelineView.buildGate.test.tsx</files>
  <action>
Author TWO new REAL rendered-DOM vitest specs (clone the idioms in AgentThinkingTab.narrativeOrder.test.tsx / StartingPointCard.test.tsx / ClarificationsCard.test.tsx: `render` + `screen` from @testing-library/react, `vi.mock("@/components/workflow/TokenUsageSummary", ...)`, construct `AgentRunState` / `PipelineRunState` fixtures from @/types/index):

(a) `AgentThinkingTab.prototypePreamble.test.tsx` — FIX 1:
  - PROTOTYPE run: `agents` include an agent with id `"prototype-build"` (status `"running"`, so `isPrototypePipeline` is true AND hasAnyData is true) + `runInput` (a plain brief) + `clarifications` (one ClarifyRound). Assert ALL THREE render: StartingPointCard (`getByText("Starting point")`), ClarificationsCard (`getByText("Clarifications")`), AND PrototypePipelineView still renders (assert its header, e.g. `getByText("Prototype Pipeline")`).
  - PROTOTYPE run with `runInput` but NO clarify (no `clarifications` prop, `pipelineState.clarifications` unset): assert StartingPointCard present (`getByText("Starting point")`) AND ClarificationsCard ABSENT (`queryByText("Clarifications")` is null).

(b) `PrototypePipelineView.buildGate.test.tsx` — FIX 2 (render `<PrototypePipelineView>` directly):
  - Provide a `planAgent` (id `"prototype-plan"`, status `"done"`) whose `output` contains at least 3 parseable task blocks (`## Task 1: ...` / `## Task 2: ...` / `## Task 3: ...`, each with a `**Goal**:` line — matches parseTasks at ~:102–135) so `totalTasks` = 3.
  - MID-LOOP: `buildAgent` (id `"prototype-build"`) status `"done"`, NO validate agent, `pipelineState.isRunning = true`, `pipelineState.protoCompletedTaskCount = 1`. Assert NOT all tasks completed — the checklist shows only the realtimeCompletedCount-done state (e.g. `queryByText("3/3 done")` is null AND `queryByText(/All 3 tasks completed/i)` is null; the `1/3 done` count is present). Prove buildTrulyDone is false.
  - TERMINAL: same fixtures but `pipelineState.isRunning = false` (run ended, build was the last agent). Assert all tasks completed (`getByText("3/3 done")` OR `getByText(/All 3 tasks completed/i)` present). Prove buildTrulyDone is true.

Then run the FULL regression guard + gates in the verify block below.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && npx vitest --run src/components/results/AgentThinkingTab.prototypePreamble.test.tsx src/components/results/PrototypePipelineView.buildGate.test.tsx src/components/results/AgentThinkingTab.narrativeOrder.test.tsx src/components/results/StartingPointCard.test.tsx src/components/results/ClarificationsCard.test.tsx src/components/results/FilesTab.test.tsx src/components/results/FilesTab.baseVersion.test.tsx src/components/results/FilesTab.runInput.test.tsx src/components/history/WorkflowHistory.test.tsx src/components/history/WorkflowHistory.family.test.tsx src/components/history/WorkflowHistory.revise.test.tsx src/components/history/WorkflowHistory.genericReopen.test.tsx src/components/history/WorkflowHistory.runInput.test.tsx src/components/preview/PreviewPanel.versionChip.test.tsx src/components/preview/PreviewPanel.degraded.test.tsx src/components/preview/PreviewPanel.genericDeliverable.test.tsx src/components/preview/PreviewPanel.revisionChip.test.tsx src/components/layout/DashboardLayout.catalogHome.test.tsx src/components/layout/DashboardLayout.waveMount.test.tsx src/components/workflow/AgentProgressPanel.test.tsx</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && OUT=$(npx tsc --noEmit 2>&1 || true); TOTAL=$(printf '%s\n' "$OUT" | grep -c 'error TS' || true); UNEXPECTED=$(printf '%s\n' "$OUT" | grep 'error TS' | grep -vc -E 'mockApi|IdeaInputPage' || true); if [ "$TOTAL" = "3" ] && [ "$UNEXPECTED" = "0" ]; then echo "GATE_OK total=$TOTAL unexpected=$UNEXPECTED"; else echo "GATE_FAIL total=$TOTAL unexpected=$UNEXPECTED"; printf '%s\n' "$OUT" | grep 'error TS'; exit 1; fi</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin && test -z "$(git status --porcelain backend)" && echo "BACKEND_CLEAN" || { echo "BACKEND_DIRTY"; git status --porcelain backend; exit 1; }</automated>
  </verify>
  <done>Both new specs pass (FIX 1: all-three-render + no-clarify-absent; FIX 2: mid-loop not-all-done + terminal all-done). Regression guard: all 20 audited suites green (known-red WorkflowCatalog×5 + unrelated NOT included, per baseline). tsc prints `GATE_OK total=3 unexpected=0`. `git status --porcelain backend` empty (BACKEND_CLEAN).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| WS/API run data → Thinking-view render | run input / clarify rounds / agent statuses already flow into AgentThinkingTab; no NEW boundary is crossed. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-byv-01 | Tampering | render logic (AgentThinkingTab / PrototypePipelineView) | accept | FE-only presentational change; reuses existing props + parsers, adds no data path, no new input parsing, no untrusted sink. |
| T-byv-02 | Tampering | backend engine + characterization goldens | mitigate | INV-3 by construction — zero backend edits; enforced by `git status --porcelain backend` gate in Task 3. |
| T-byv-SC | Tampering | package installs | accept | No npm/pip/cargo installs in this plan; no new dependency introduced. |
</threat_model>

<verification>
- Task 1: narrativeOrder suite green; prototype branch renders the preamble cards.
- Task 2: buildTrulyDone derived from confirmed terminal signals; substituted at all terminal sites.
- Task 3: both new specs pass; 20-suite regression guard green; tsc-identity `GATE_OK total=3 unexpected=0`; `BACKEND_CLEAN`.
</verification>

<success_criteria>
- Prototype Thinking view (live-after-build-starts AND reopen) shows StartingPointCard + ClarificationsCard above PrototypePipelineView; clarify-less prototype shows StartingPoint only.
- Build checklist never flashes all-complete between tasks; shows realtimeCompletedCount-done until the loop truly ends, then all-complete.
- `cd frontend && npx tsc --noEmit` → exactly 3 `error TS`, 0 after filtering mockApi|IdeaInputPage (GATE_OK).
- All 20 audited render suites green.
- `git status --porcelain backend` empty.
</success_criteria>

<output>
Create `.planning/quick/260703-byv-fix-prototype-thinking-view-render-start/260703-byv-SUMMARY.md` when done.
</output>
