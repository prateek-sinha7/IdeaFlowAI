---
phase: 32-run-screen-redesign-a4
plan: 06
subsystem: ui
tags: [sc-4, sc-1, sc-001, inv-3, lock-f, run-screen, chat-lane, terminal-states, tdd]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4 (plan 01)
    provides: "canonical token layer (@theme inline brand/ink/surface/line/status ramp + radius ladder)"
  - phase: 32-run-screen-redesign-a4 (plan 02)
    provides: "token-consuming primitives (Button/Card/Badge/Pill)"
  - phase: 32-run-screen-redesign-a4 (plan 05)
    provides: "pipelineState.cancelled terminal marker + reviewGateData.updateSpecsEligible/artifactKind flags"
provides:
  - "RunChatLane reskinned to tokens/primitives (raw #1B2A4A/#2563eb = 0) with the AgentProgressPanel controls fully absorbed (Stop via Button)"
  - "Faithful terminal renders — cancelled ('Cancelled by you'+Run again), failed ('What went wrong'+agents_failed[]+sanitized error+Edit brief & run again), degraded ('completed with issues') — off generic pipelineState markers (SC-4, LIVE-STATE-CONTRACT §1)"
  - "DashboardLayout terminal runLaneState (cancelled/failed/degraded) + laneGate.updateSpecsEligible/approveLabel mapping — no workflow-name branch (SC-001)"
  - "INV-3: the duplicate AgentProgressPanel run-lane mount removed — RunChatLane is the SOLE stop/revise implementation"
  - "PreviewPanel additive optional gate/clarify passthrough props for plan 07/08 Steps"
affects: [plan-07, plan-08, plan-10 (color-class re-anchor), run-screen FE]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Terminal variant derived from generic pipelineState markers (cancelled/failed/degraded) inside the RunChatLane 'terminal' composer case — never a workflow name (SC-001)"
    - "sanitizeError(): first-line-only, length-capped error surfacing (T-32-06-01) — raw stack frames never rendered"
    - "Reuse of the shared parseFailedAgents (buildAgentNameById/resolveAgentNames) for id->name in the failed/degraded cards (INV-3 single parser)"
    - "laneGate mapping mirrors the redoable idiom: declared reviewGateData flags -> GateContext, no literal (SC-001)"

key-files:
  created:
    - frontend/src/components/chat/__tests__/RunChatLane.terminal.test.tsx
  modified:
    - frontend/src/components/chat/RunChatLane.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/layout/DashboardLayout.waveMount.test.tsx
    - frontend/src/components/preview/PreviewPanel.tsx

key-decisions:
  - "AgentProgressPanel.tsx RETAINED (not deleted), only its run-lane MOUNT removed — the residual caller is its own test suite + the Phase-31-documented plan-08 Steps relocation. INV-3 satisfied at the render level: exactly ONE mounted stop/revise implementation (RunChatLane); grep '<AgentProgressPanel' in production src = 0."
  - "Degraded routed to the terminal runLaneState per the plan's explicit Task-3(a) instruction (cancelled OR failed OR degraded -> terminal), even though LIVE-STATE-CONTRACT §1 lists degraded's composer as revision mode — followed the plan as authoritative; the 'completed with issues' card + relaunch renders faithfully."
  - "approveLabel derived from reviewGateData.artifactKind as `Approve the <kind>` (underscores humanized) — a generic, runtime-valued relabel (no source literal, SC-001); degrades to the InlineGateActions default when artifactKind is absent."
  - "PreviewPanel gate/clarify props added to the interface + wired at the mount but NOT yet destructured/consumed inside PreviewPanel — additive plumbing for plan 07/08 (tsc-identity, zero behavior change)."

requirements-completed: [SC-4, SC-1]

# Metrics
duration: ~14min
completed: 2026-07-08
---

# Phase 32 Plan 06: Run Chat Lane Reskin + Terminal States Summary

**RunChatLane is reskinned to the plan-01 tokens + plan-02 primitives (raw-hex 0) with the AgentProgressPanel controls fully absorbed and its duplicate run-lane mount DELETED (INV-3 — one stop/revise impl); it now renders the faithful cancelled / failed / degraded terminal cards off the generic plan-05 pipelineState markers (SC-4), while DashboardLayout derives the terminal runLaneState and maps the declared updateSpecsEligible/artifactKind flags into laneGate — with no workflow-name branch (SC-001) and the "Deliverable" label held (LOCK-F).**

## Performance
- **Duration:** ~14 min
- **Tasks:** 3 (Task 2 TDD: RED -> GREEN)
- **Files:** 5 (1 created, 4 modified)

## Accomplishments

- **Task 1 — reskin + absorption (SC-1):** routed RunChatLane's navy `#1B2A4A` composer / send-button / suggestion-chip / heading classes and the textarea focus ring through the plan-01 brand/ink/surface/line tokens + radius ladder (raw `#1B2A4A|#2563eb` count 0). The header Stop control now renders via the plan-02 `Button` primitive (secondary/sm). Added `data-testid="chat-lane-transcript"`; the generic-runState composer switch and the "Deliverable" ResultCard label are unchanged (LOCK-F, SC-001).
- **Task 2 — terminal states (SC-4, TDD):** wrote the terminal-render tests FIRST (observed RED — 3 failing), then implemented the three terminal cards inside the RunChatLane `terminal` composer case, keyed on the generic `pipelineState.cancelled/failed/degraded` markers: **Cancelled** -> "Cancelled by you" ack + "Run again"; **Failed** -> "What went wrong" card naming the failed agents (`failedAgents[]` via the shared `parseFailedAgents` resolver) + the sanitized first-line error + "Edit brief & run again"; **Degraded** -> "Completed with issues" naming the degraded agents. Added `sanitizeError()` (first line only, capped) so no raw stack frame is surfaced (T-32-06-01). Cards built from `Card`/`Badge`/`Button`.
- **Task 3 — DashboardLayout wiring + INV-3 (SC-4, SC-001):** extended `runLaneState` to yield `terminal` for `pipelineState.cancelled || failed || degraded` (generic markers, no workflow branch); extended `laneGate` to carry `updateSpecsEligible` and an `artifactKind`-derived `approveLabel`, mirroring the existing `redoable` mapping. **Removed the duplicate AgentProgressPanel run-lane mount** (its Stop/revise/suggestions are fully absorbed by the lane) plus its now-orphaned import and `handleFollowUp` helper. Added additive optional gate/clarify passthrough props to `PreviewPanel` (wired at the mount with live values) so plan 07/08 can host the same inline affordances in Steps.

## Task Commits
1. **Task 1:** `6a0dd2ae` (feat) — reskin RunChatLane to tokens/primitives + Stop via Button
2. **Task 2 (RED):** `510f43fb` (test) — failing terminal-render tests (cancelled/failed/degraded)
3. **Task 2 (GREEN):** `166621ff` (feat) — terminal renders off generic pipelineState markers
4. **Task 3:** `bd1912d9` (feat) — terminal runLaneState + updateSpecsEligible map + remove duplicate AgentProgressPanel mount (INV-3)

## Files Created/Modified
- `frontend/src/components/chat/__tests__/RunChatLane.terminal.test.tsx` (created) — 5 tests: cancelled/failed/degraded render assertions, sanitized-error-only (raw stack NOT surfaced), plain-terminal fallback, SC-001 no-literal grep.
- `frontend/src/components/chat/RunChatLane.tsx` (modified) — token/primitive reskin; `firstAgentError`/`sanitizeError` helpers; the three terminal cards; `data-testid=chat-lane-transcript`.
- `frontend/src/components/layout/DashboardLayout.tsx` (modified) — terminal runLaneState; laneGate updateSpecsEligible/approveLabel mapping; AgentProgressPanel mount + import + handleFollowUp removed; PreviewPanel passthrough wiring.
- `frontend/src/components/layout/DashboardLayout.waveMount.test.tsx` (modified) — re-anchored the 3 stub-dependent assertions onto `execution-chat-lane`; this also FIXED the pre-existing stale flex-budget failure (it anchored on the removed AgentProgressPanel wrapper expecting `flex-1`).
- `frontend/src/components/preview/PreviewPanel.tsx` (modified) — additive optional `laneGate`/gate-callbacks/`clarifyQuestions`/clarify-callbacks props (interface only; consumed by plan 07/08).

## Verification Observed
- **vitest (plan scope):** `npx vitest run src/components/chat/ src/components/layout/` -> **15 files / 107 tests passed** (includes the 5 new terminal tests + the re-anchored waveMount suite 4/4, previously 1 failing).
- **tsc identity:** `npx tsc --noEmit | grep -v mockApi.ts | grep -c "error TS"` = **0** (baseline 0 preserved; a transient 4-error regression from over-eagerly removing `completedPipelineTypes` state — whose setter IS called at L442/L1077 — was caught and reverted before commit).
- **RunChatLane raw hex:** `grep -riE "#1B2A4A|#2563eb" src/components/chat/RunChatLane.tsx` = **0**.
- **INV-3 (one stop/revise impl):** `grep '<AgentProgressPanel' (production src)` = **0**; `grep '<RunChatLane' (production src)` = **1**; `git show bd1912d9` shows the `-  <AgentProgressPanel` mount deletion.
- **SC-001:** no NEW `prototype-*` literal in DashboardLayout (grep 0); terminal/gate derivations key on generic pipelineState/reviewGateData signals only.
- **LOCK-F:** `"Deliverable"` label present in ResultCard (grep 3).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-existing stale waveMount flex-budget test**
- **Found during:** Task 3 baseline layout run.
- **Issue:** `DashboardLayout.waveMount.test.tsx > "flex-budgets the left execution column…"` was ALREADY failing on the committed baseline — it anchored `stub-agent-progress`.parentElement expecting `flex-1`/`min-h-0`, but the AgentProgressPanel wrapper was `flex-shrink-0 max-h-[34%]` (the lane became the flex-1 surface in Phase 31). Removing the mount (this plan) would also have broken the two passing stub-presence assertions.
- **Fix:** Re-anchored all three stub-dependent assertions onto `execution-chat-lane` (the true flex-1/min-h-0 surface) and corrected the wave-wrapper cap to `max-h-[30%]`. Suite now 4/4 green.
- **Files modified:** `DashboardLayout.waveMount.test.tsx`.
- **Commit:** `bd1912d9`.

**2. [Rule 3 - Blocking] Over-eager state removal caught by tsc**
- **Found during:** Task 3 tsc verify.
- **Issue:** an initial grep suggested `completedPipelineTypes` was orphaned by the mount removal; deleting the state broke `setCompletedPipelineTypes` calls at L442/L1077 (4 tsc errors).
- **Fix:** restored the `completedPipelineTypes` useState (the value read was the mount; the setter has live callers). tsc back to 0.
- **Commit:** `bd1912d9` (net diff carries the restored state).

### Non-deviation notes
- **AgentProgressPanel.tsx retained, not deleted** — the guardrail's second branch ("if a distinct non-lane caller remains, remove only the duplicate mount and note the residual caller"). Residual callers: its own test suite (`AgentProgressPanel.test.tsx`) + the Phase-31-documented plan-08 Steps relocation. The component's unmounted legacy Stop/revise code is dead in the run lane (never rendered); INV-3's "one stop/revise implementation" holds at the mount/render level.
- **Degraded -> terminal** followed the plan's explicit Task-3(a) instruction over the LIVE-STATE-CONTRACT §1 "revision mode" note; documented as a decision, not a silent divergence.

## Issues Encountered
- **Pre-existing, out-of-scope failure (logged, NOT fixed):** `AgentProgressPanel.test.tsx > "treats a _revision completion the same as its base for the filter"` fails on the committed baseline (the component still renders the "Presentation" chip for a `ppt_revision` run). File untouched by this plan; does not import RunChatLane/DashboardLayout/PreviewPanel; outside the plan's verification scope (`chat/` + `layout/`). Logged to `deferred-items.md` per the scope boundary.

## User Setup Required
None — pure FE reskin + render of already-received WS state; no package install, no env, no new network/auth surface (LOCK-B intact, no SSE activation).

## Known Stubs
None that block the plan goal. The PreviewPanel gate/clarify passthrough props are declared-but-unconsumed plumbing (interface + mount wiring with LIVE values) intentionally prepared for plan 07/08 Steps — documented, additive, tsc-identity; not an empty-data UI stub.

## Threat Flags
None — no new trust boundary. T-32-06-01 mitigated (sanitized first-line error only, no raw stack); T-32-06-02 mitigated (duplicate mount removed, one stop/revise impl); T-32-06-03 mitigated (terminal/gate derivations keyed on generic markers, no workflow-name literal).

## Next Phase Readiness
- The left chat lane is fully reskinned + terminal-complete; plan 07/08 can consume the PreviewPanel gate/clarify passthrough to surface the inline gate in Steps. Plan 10 re-anchors any color-class assertions changed by the reskin.
- One residual: AgentProgressPanel.tsx retains unmounted legacy controls + a pre-existing test failure — both slated for the plan-08 Steps relocation (tracked in `deferred-items.md`).

## Self-Check: PASSED

- Files: RunChatLane.terminal.test.tsx, RunChatLane.tsx, DashboardLayout.tsx, DashboardLayout.waveMount.test.tsx, PreviewPanel.tsx — all FOUND.
- Commits: `6a0dd2ae`, `510f43fb`, `166621ff`, `bd1912d9` — all FOUND in git log.
- Guardrails: raw-hex 0; INV-3 one mounted stop/revise (AgentProgressPanel production mounts 0, RunChatLane 1); SC-001 no new literal; LOCK-F "Deliverable" held; tsc 0; chat+layout 107/107.

---
*Phase: 32-run-screen-redesign-a4*
*Completed: 2026-07-08*
