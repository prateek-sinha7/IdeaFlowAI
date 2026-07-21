---
phase: 38-analytics-estimates-notifications-b4
plan: 03
subsystem: frontend-notifications
tags: [notifications, feed, gate-kind, dashboard-wiring, sc-2, shell-05]
requires:
  - "useNotifications hook (running/completed/failed/cancelled)"
  - "NotificationPanel + Badge status-ramp token layer (Phase 32 --status-amber)"
  - "DashboardLayout generic pipelineState markers (failed/cancelled/reviewGateData)"
provides:
  - "PipelineNotification.status gains \"gate\" kind"
  - "markGatePaused(id) transition (paused, no completedAt)"
  - "amber gate StatusIcon + Badge branch (--status-amber)"
  - "wired markFailed/markCancelled/markGatePaused off generic markers"
affects:
  - "Phase 34 live PUSH consumes the gate kind + markGatePaused over the real connection"
tech-stack:
  added: []
  patterns:
    - "TDD RED->GREEN on the hook transition contract (renderHook + act)"
    - "terminal/gate transitions key OFF generic pipelineState markers, never a workflow name (SC-001/INV-1)"
    - "gate reuses the Phase-32 --status-amber ramp (no raw hex)"
key-files:
  created:
    - frontend/src/hooks/useNotifications.test.tsx
  modified:
    - frontend/src/hooks/useNotifications.ts
    - frontend/src/components/ui/NotificationPanel.tsx
    - frontend/src/components/ui/Badge.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
decisions:
  - "gate is a PAUSED (not terminal) state: markGatePaused sets status:\"gate\" + read:false and does NOT stamp completedAt, mirroring markFailed otherwise."
  - "Badge.tsx extended with a gate key on the amber ramp (in-scope extension per Task 2: 'extend Badge.tsx if it lacks a gate case')."
  - "gate wiring reuses the SAME condition as runLaneState===\"gate\" (reviewGateData && pipelineState.isRunning) — one generic marker, no name branch."
metrics:
  duration: "~3 min"
  completed: "2026-07-10"
  tasks: 3
  files: 5
---

# Phase 38 Plan 03: Notifications Feed Gate Kind + Terminal Wiring Summary

Added the honest `gate` notification kind (amber `--status-amber`) plus a `markGatePaused` transition to `useNotifications`, rendered it in `NotificationPanel`/`Badge`, and wired `markFailed`/`markCancelled`/`markGatePaused` in `DashboardLayout` off the GENERIC `pipelineState` markers (`failed`/`cancelled`/`reviewGateData`) so failed, cancelled, and gate-paused runs now each produce a feed notification — with zero workflow-name branch and zero transport touch.

## What Was Built

- **Task 1 (TDD RED):** `useNotifications.test.tsx` — `renderHook` + `act` tests for the four transitions (gate/failed/cancelled + type-level gate). Observed RED: `markGatePaused` did not exist (1 failed, 3 passed).
- **Task 2 (TDD GREEN):**
  - `useNotifications.ts` — `status` union gains `"gate"`; new `markGatePaused(id)` (sets `status:"gate"`, `read:false`, no `completedAt`); exported from the hook return.
  - `NotificationPanel.tsx` — `StatusIcon` gate branch renders an amber `PauseCircle` via `text-status-amber`.
  - `Badge.tsx` — `gate` key on the amber ramp; `normalizeStatus` maps `gate`/`review`/`paused`.
  - GREEN: useNotifications 4/4 pass.
- **Task 3 (wiring):** `DashboardLayout.tsx` — destructured `markGatePaused`; the terminal effect now fires `markFailed` on `pipelineState.failed` and `markCancelled` on `pipelineState.cancelled` (guarded on `currentPipelineNotifId.current`, after the completed branch resets it); a new effect fires `markGatePaused` off `reviewGateData && pipelineState.isRunning` (the same condition as `runLaneState==="gate"`).

## Verification (observed)

- `npx vitest run src/hooks/useNotifications` → Test Files 1 passed, Tests 4 passed.
- `npx vitest run src/hooks src/components/ui/NotificationPanel` → 10 files, 44 tests passed (NotificationPanel a11y regression green).
- grep gates: `"gate"` in hook = 3 (≥1); `markGatePaused` in hook = 2 (≥2); `gate` in panel = 5 (≥1); amber in panel = 2 (≥1); panel retired-palette = 0; panel a11y (role=menu/aria) = 3 (>0); transport hook = 0; transport panel = 0; transport DL diff = 0; DL `markFailed(|markCancelled(|markGatePaused(` = 3 (≥3, all CALLED); DL name-branch in wiring = 0.
- `npx tsc --noEmit` (excl mockApi.ts) → 0 errors (identity baseline held).

## Deviations from Plan

None functional. In-scope extension: **`Badge.tsx` was edited** (add a `gate` key on the amber ramp) — explicitly sanctioned by Task 2 ("extend `Badge.tsx` if it lacks a gate case") and the negative-space clause. Without it, `Badge status="gate"` would fall through to the neutral `queued` grey instead of amber.

## Known Scope Boundary

- **Session-scoped feed; reload-survival deferred.** The notifications feed is derived purely from the owner's in-memory client `pipelineState` (`useNotifications` `useState`). It does NOT survive a page reload — reload-survival requires backend persistence, which is OUT OF SCOPE for this plan.
- **LOCK-B — live PUSH LIVE-DEFERRED to Phase 34.** No SSE/WS/transport code was added or modified; the derivation is pure client state off `pipelineState`. Live notification PUSH over the real connection and mocked Playwright e2e are deferred to Phase 34.

## Self-Check: PASSED

- FOUND: frontend/src/hooks/useNotifications.test.tsx
- FOUND: frontend/src/hooks/useNotifications.ts (gate kind + markGatePaused)
- FOUND: frontend/src/components/ui/NotificationPanel.tsx (gate StatusIcon)
- FOUND: frontend/src/components/ui/Badge.tsx (gate key)
- FOUND: frontend/src/components/layout/DashboardLayout.tsx (wired transitions)
- FOUND commit ec5a31f6 (test), 64f09b49 (feat hook+panel), 9ad3e8ba (feat wiring)
