---
quick_id: 260716-sml
type: quick
mode: quick
branch: feat/ui-2
wave: 1
autonomous: true
depends_on: []
files_modified:
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx
  - frontend/src/app/dashboard/contentSourceRunType.source.test.ts
must_haves:
  truths:
    - "A NON-terminal reopen (isPipelineRunning=true, contentSourceRunType=od_prototype, stale workflowType=user_stories) shows the prototype type in the run-lane label AND the header pill — NOT 'User Stories'."
    - "A live launch (contentSourceRunType null) is byte-identical: viewedRunType stays undefined ⇒ effectiveReviseType === workflowType for both the lane label and the header pill."
    - "Terminal reopen label unchanged (still the viewed run's type); at-risk vitest suites stay green; tsc clean."
  artifacts:
    - path: "frontend/src/components/layout/DashboardLayout.tsx"
      provides: "Un-gated viewedRunType (durable-type-first) + header pill bound to effectiveReviseType"
    - path: "frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx"
      provides: "RED→GREEN render proof for the non-terminal reopen + launch no-regression"
    - path: "frontend/src/app/dashboard/contentSourceRunType.source.test.ts"
      provides: "Source-lock updated to the new un-gated shape + header-pill binding lock"
  key_links:
    - from: "DashboardLayout.tsx viewedRunType (:1274)"
      to: "effectiveReviseType (:1278)"
      via: "contentSourceRunType ?? (gated recents fallback)"
    - from: "DashboardLayout.tsx AppHeader (:1475)"
      to: "effectiveReviseType"
      via: "pipelineType={effectiveReviseType}"
---

<objective>
Fix BUG-012 follow-up: a NON-terminal reopen (a clarifying/building od_prototype run opened from history, where the durable replay leaves `isPipelineRunning` true) shows the stale `workflowType` default ("User Stories") in the run-lane type label and the header pill instead of the reopened run's real type.

Implement EXACTLY the two display-binding edits from the orchestrator-verified spec (`.planning/BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT.md`). The fix is cosmetic and display-only; launch→watch stays byte-identical.

Purpose: close the last tail of the stale-`workflowType` label family (BUG-006 + BUG-012) so reopened non-terminal runs read their real type end-to-end.
Output: 2 source edits in `DashboardLayout.tsx`, a RED→GREEN render test, and updated source-locks.
</objective>

<context>
@.planning/BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT.md
@frontend/src/components/layout/DashboardLayout.tsx
@frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx
@frontend/src/app/dashboard/contentSourceRunType.source.test.ts
@frontend/src/components/layout/AppHeader.tsx
</context>

<orientation>
All line numbers verified in this workspace on branch feat/ui-2.

- `viewedRunType` — `DashboardLayout.tsx:1274-1277` (currently `!isPipelineRunning`-gated).
- `effectiveReviseType` — `:1278` (`viewedRunType ?? workflowType`), already in scope.
- Header pill — `:1475` `pipelineType={workflowType}` (the ONLY `pipelineType={workflowType}` in DashboardLayout.tsx; the ComposerPage/WorkflowHistory occurrences are OTHER files — do not touch).
- Lane type label consumer — `:1771` `runType={effectiveReviseType || pipelineState?.pipeline_type}` (fed to RunChatLane; the laneTitle test echoes it into `data-testid="lane-run-type"`).
- LEAVE: `IdeaInputPage workflowType={workflowType}` (`:1661`) and `ComposerPage workflowType={workflowType}` (`:1696`) — launch controls, intentionally the launch type.
- `isPipelineRunning = pipelineState?.isRunning || false` (`:483`).
- `workflowType` init (`:255-261`): `od_prototype.pending` sessionStorage ⇒ "prototype", else "user_stories". Sync effect (`:335-351`) fires only while `pipelineState.isRunning` and normalises `pipelineState.pipeline_type` into `workflowType` (od_prototype→prototype). To hold `workflowType` STALE at "user_stories" while running, set `pipelineState.pipeline_type="user_stories"` and do NOT set the `od_prototype.pending` latch.
- `contentSourceRunType?: WorkflowType | null` prop (`:79`, destructured `:215`) — set ONLY on reopen, null on fresh-launch reset. Reliable "reopened run" signal independent of running state.
- AppHeader is STUBBED to `<div/>` in `DashboardLayout.laneTitle.test.tsx` (line 71) — the header pill cannot be render-asserted there; pin it with a source-lock instead.
</orientation>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Un-gate viewedRunType + bind header pill to the viewed type (RED→GREEN)</name>
  <files>frontend/src/components/layout/DashboardLayout.tsx, frontend/src/components/layout/DashboardLayout.laneTitle.test.tsx, frontend/src/app/dashboard/contentSourceRunType.source.test.ts</files>
  <behavior>
    Render RED→GREEN (add a new describe block "BUG-012 follow-up — non-terminal reopen" to DashboardLayout.laneTitle.test.tsx, mirroring the existing BUG-006 lane-run-type block):
    - Test A (fail-before, pass-after): a NON-terminal reopen — pipelineState={ isRunning: true, pipeline_type: "user_stories", agents: [], currentAgentIndex: -1, totalDuration: null, completedCount: 0 }, an od_prototype run in recentRuns, contentSourceRunId set to that run's id, contentSourceRunType="od_prototype", and NO od_prototype.pending latch (so workflowType stays the stale "user_stories" default). Assert screen.getByTestId("lane-run-type") textContent is "od_prototype" and NOT "user_stories". RED before the edit (gate makes viewedRunType undefined ⇒ effectiveReviseType falls back to stale "user_stories").
    - Test B (no-regression): a live launch — pipelineState.isRunning=true with pipeline_type="prototype", contentSourceRunId=null, contentSourceRunType omitted/null (viewedRunType undefined ⇒ effectiveReviseType===workflowType, which syncs to "prototype"). Assert lane-run-type is "prototype". Passes both before and after (byte-identical launch path).
    Note: isPipelineRunning=true drives mainView→"execution" via the sync effect (:343-344), so the execution view mounts without the od_prototype.pending latch — do not set that latch for Test A/B (it would force workflowType="prototype" and mask the bug).

    Source-lock (contentSourceRunType.source.test.ts), for the header pill (AppHeader is stubbed in the render test) and to keep the shape lock green after the edit:
    - UPDATE the existing "folds the durable type into viewedRunType" assertion (currently pins the pre-fix string `contentSourceRunType ?? recentRuns?.find((r) => r.id === contentSourceRunId)?.type`) to the NEW un-gated shape, e.g. assert layoutCollapsed contains `contentSourceRunType ?? (!isPipelineRunning && contentSourceRunId != null ? recentRuns?.find((r) => r.id === contentSourceRunId)?.type`.
    - ADD an assertion that the header pill binds the viewed type: layoutSource contains `pipelineType={effectiveReviseType}` (currently 0 occurrences; the edit adds exactly one at :1475).
  </behavior>
  <action>
Apply the two spec edits to `DashboardLayout.tsx`, EXACTLY as written in the spec (per `.planning/BUG-012-FOLLOWUP-LABEL-GROUNDED-CONTEXT.md` §The fix):

1. `:1274-1277` — un-gate the durable type. Replace the current `!isPipelineRunning && contentSourceRunId != null ? (contentSourceRunType ?? recentRuns?.find(...).type) : undefined` with the durable-first form: `contentSourceRunType ?? (!isPipelineRunning && contentSourceRunId != null ? recentRuns?.find((r) => r.id === contentSourceRunId)?.type : undefined)`. Keep the recents fallback gated on `!isPipelineRunning` so a fresh launch (contentSourceRunType null) stays byte-identical. Update the adjacent BUG-012 comment (`:1270-1273`) so it no longer claims the durable type is still gated on `!isPipelineRunning`.

2. `:1475` — bind the header pill to the viewed type: change `pipelineType={workflowType}` to `pipelineType={effectiveReviseType}` on the `<AppHeader>` element. `effectiveReviseType` is in scope (declared :1278). This is the ONLY AppHeader in this file.

Do NOT touch `IdeaInputPage` (:1661), `ComposerPage` (:1696), `PreviewPanel` (:1834 / PreviewPanel.tsx), the reducer, the SSE path, `workflowType` init/sync, or the j1u/lb6/n2d/o6z/r7d fixes. SC-001: both edits key on existing type variables (`contentSourceRunType`/`effectiveReviseType`) — add NO workflow-name string literal.

TDD order: write the render tests + update the source-locks FIRST, run them and SEE Test A fail (stale "user_stories") while the old source-lock still passes; then apply the two edits; re-run and confirm Test A + Test B pass and the updated source-lock passes.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit && npx vitest run src/components/layout/DashboardLayout.laneTitle.test.tsx src/components/layout/DashboardLayout.launchLatch.test.tsx src/app/dashboard/contentSourceRunType.source.test.ts src/app/dashboard/revisionFamilyLinkage.source.test.ts</automated>
  </verify>
  <done>
    - tsc clean.
    - New Test A: non-terminal reopen renders lane-run-type "od_prototype" (was "user_stories" before the edit — observed RED first).
    - New Test B: live launch renders lane-run-type "prototype" (byte-identical, green before and after).
    - contentSourceRunType.source.test.ts green with the updated un-gated viewedRunType shape lock + the new `pipelineType={effectiveReviseType}` header-pill lock.
    - At-risk suites green: DashboardLayout.laneTitle (incl. unchanged BUG-001/BUG-006 blocks), DashboardLayout.launchLatch, revisionFamilyLinkage.source.
    - Exactly two edits in DashboardLayout.tsx; no workflow-name literal added; IdeaInputPage/ComposerPage/PreviewPanel untouched.
  </done>
</task>

</tasks>

<verification>
- `cd frontend && npx tsc --noEmit` — clean.
- Targeted vitest (command in Task 1 verify) — all green, with Test A observed RED before the source edit.
- Manual source check: `grep -n "pipelineType={effectiveReviseType}" frontend/src/components/layout/DashboardLayout.tsx` returns exactly line ~1475; `grep -c "pipelineType={workflowType}" frontend/src/components/layout/DashboardLayout.tsx` returns 0.
- The 8 pre-Phase-42 vitest reds in untouched files are NOT regressions; the "132/0" mocked-e2e baseline is stale — do not chase it.
- Live proof is the orchestrator's job (executor does NOT run live Bedrock): reopen the clarify-paused od_prototype run ⇒ lane + header show a prototype label, not "USER_STORIES".
</verification>

<security_note>
No security surface: frontend-only, display-only rebinding of two existing in-scope type variables. No new dependency, no new package install, no trust-boundary change, no data flow change. STRIDE not applicable to this quick cosmetic fix.
</security_note>

<success_criteria>
- Non-terminal reopen shows the reopened run's real type in BOTH the run-lane label and the header pill (bug closed).
- Live launch→watch is byte-identical (viewedRunType undefined ⇒ effectiveReviseType === workflowType).
- Terminal-reopen label unchanged; SC-001 preserved (no workflow-name literal); tsc clean; at-risk vitest suites green.
- Exactly the spec's two edits; IdeaInputPage/ComposerPage/PreviewPanel/reducer/SSE untouched.
</success_criteria>

<constraints_recap>
- Branch feat/ui-2 (verify `git rev-parse --abbrev-ref HEAD`; do NOT switch). NO commit trailer. NEVER push.
- FE is cwd-sensitive: run all tsc/vitest from `frontend/`. Kill port :3000 before any mocked Playwright (not required for this vitest-only verify).
- Do NOT run live Bedrock. Do NOT touch PreviewPanel.tsx, the reducer, the SSE path, or the j1u/lb6/n2d/o6z/r7d fixes.
</constraints_recap>

<output>
Update `.planning/quick/260716-sml-fix-bug-012-follow-up-non-terminal-reope/` with a brief completion note (SUMMARY) when done: the two edits landed, RED→GREEN observed, at-risk suites green.
</output>
