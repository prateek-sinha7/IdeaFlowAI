# BUG-006 + BUG-007 — grounded fix spec (cluster close-out)

> Two minor, trivial, root-caused follow-ups from the live SSE QA campaign, both in `frontend/src/components/layout/DashboardLayout.tsx`. Full root causes: `.planning/SSE-QA-BUG-LOG.md` → BUG-006 / BUG-007 (READ THEM). Frontend-only. Executable spec for a `gsd-quick --validate`.

## BUG-006 🟡 — pipeline-type label stale for a history-opened run (a MISSED SWEEP of the FE-cluster fix)
- **Cause:** the `lane-run-type` chip (`LaneRunHeader.tsx:184,231`) is fed `runType={workflowType || pipelineState?.pipeline_type}` at `DashboardLayout.tsx:1745`, so it shows the stale `workflowType` (default `"user_stories"`, synced only by the `isRunning`-gated effect at `:330`) — a completed history-open (isRunning=false) never updates it → an app_builder run shows "USER_STORIES". Same class as BUG-001 (title) / BUG-003-L2 (revise-type), which the FE-cluster quick (260716-j1u) fixed via `recentRuns.find(r.id===contentSourceRunId)` — but it MISSED this third consumer (the display chip).
- **Fix:** `DashboardLayout.tsx:1745` → `runType={effectiveReviseType || pipelineState?.pipeline_type}` (the `effectiveReviseType`/`viewedRunType` input is ALREADY in scope from j1u at `:1248-1252`, currently unused by the display). Launch/live byte-identical (effectiveReviseType resolves to workflowType when `contentSourceRunId` is null); reopen shows the viewed run's type. Verify the exact in-scope variable name and use it.

## BUG-007 🟡 — one UI launch mints TWO runs (dev-only React StrictMode; prod mints once)
- **Cause:** the launch-consumer effect (`DashboardLayout.tsx:636-679`, prototype) mints via `useWorkflow.startPipeline` (no in-flight guard); its only guard is `if (!pendingOdProtoParams) return;` (`:637`) + an ASYNC clear. Under `next dev` React StrictMode double-invokes the mount effect; both synchronous invocations pass the guard before the async clear nulls the param → 2 mints. A production build (no StrictMode double-invoke) mints once, so this is a **dev-only artifact**, but the underlying effect is non-idempotent. Structural twin: the od_ppt consumer at `:685-727`.
- **Fix:** add a `useRef` object-identity latch to BOTH consumer effects — e.g. `if (launchedProtoParamsRef.current === pendingOdProtoParams) return; launchedProtoParamsRef.current = pendingOdProtoParams;` (and the od_ppt twin with its own ref) so the SAME param object mints once across StrictMode's double-invoke, while a NEW launch (new object) still mints. Do NOT set `reactStrictMode:false` (hides the real non-idempotency). Preserve the existing async clear.

## Scope fences
- **Frontend only**, ONLY `frontend/src/components/layout/DashboardLayout.tsx` + tests. No backend. Do NOT touch the j1u cluster fixes (title/revise-type/History routing/run-scope) — only ADD the missed display-chip binding (006) + the launch-consumer latches (007).
- Preserve the primary launch flow (a fresh launch with a NEW param object still mints exactly once; the display shows the launched run's type when `contentSourceRunId` is null).

## Constraints
- Branch **feat/ui-2**. NO commit trailer. NEVER push. FE tooling cwd-sensitive (from `frontend/`); kill :3000 before mocked Playwright.
- Keep the at-risk tests green (ts-u.revisions, revisionFamilyLinkage.source, ts-live-state, the j1u tests). SC-001: page.tsx exempt; guarded components literal-free (this is page-adjacent DashboardLayout — keep any workflow-name literals as-is, don't add new ones in guarded components).
- Establish the REAL green baseline by running (the "132/0" figure is stale).

## Verification (executor)
- `npx tsc --noEmit` clean.
- **BUG-006 fail-before/pass-after (vitest):** extend `DashboardLayout.laneTitle.test.tsx` (or a sibling) — assert `lane-run-type` tracks the viewed run's `type` across a 3-run recents where `contentSourceRunId` != `recents[0]` (RED before the :1745 change, GREEN after).
- **BUG-007 fail-before/pass-after (vitest):** a test that mounts the launch-consumer under StrictMode (or simulates the double mount-effect invoke) and asserts `startPipeline`/the mint fires ONCE for one param object (RED before the latch, GREEN after). If a StrictMode-mount test is impractical, a targeted unit test that invokes the consumer effect twice with the same param object and asserts one mint.
- Run the affected mocked Playwright + vitest (from frontend/) — stay green.
- Do NOT run a live Bedrock run — the orchestrator does the live check (reopen an app_builder run → type label correct; one wizard launch in a prod-like check mints once).
