# Deferred items — quick 260716-j1u (FE run-screen cluster)

Append-only log of out-of-scope discoveries during BUG-001/002/003/005 execution.

## DEF-BUG-002-generic-reopen — run screen shows empty state for a reopened GENERIC/CUSTOM deliverable

- **Found during:** Task 5 regression gate (ts-t.history TS-T-04).
- **What:** After BUG-002 routed History row taps to the shared run screen (execution-chat-lane) via `onOpenRun`, reopening a `custom`/unknown-type run whose output is HTML renders the run screen's PreviewPanel EMPTY ("Output will appear here") instead of the sandboxed `Deliverable Preview` iframe. TYPED deliverables (user_stories, proven by TS-T-03; ppt/prototype/app_builder) render correctly.
- **Root cause (surface):** `handleSelectWorkflowRun` (page.tsx) clears `genericDeliverable` on reopen and the generic-fallback content seed (page.tsx ~1302-1319 `else → setGenericDeliverable`) does not repopulate it on this path, so PreviewPanel receives no generic deliverable. NOT investigated to full root cause (out of the 4-bug scope).
- **Pre-existing vs introduced:** the Home-recents open path uses the SAME `handleSelectWorkflowRun`, so it shares this generic-reopen gap — BUG-002 EXPOSED it for custom History taps rather than introducing it.
- **Coverage retained:** the sandboxed-iframe SECURITY contract (allow-scripts, no allow-same-origin, srcdoc) for the generic reopen is fully pinned in-browser by `WorkflowHistory.genericReopen.test.tsx`. Only the run-screen RENDERING of a reopened generic deliverable is unproven.
- **Tracking test:** `e2e/tests/ts-t.history.spec.ts` → `TS-T-04b` (test.fixme). Un-fixme once the run screen renders a reopened generic/custom deliverable.
- **Fix owner:** a follow-up (page.tsx reopen seed or PreviewPanel), not part of BUG-001/002/003/005.

## WARNING-2 (plan-checker, NOTED not fixed) — trackedRunIdRef priority mistracks "background build A while viewing run C"

- **What:** BUG-005's `trackedRunIdRef` syncs from `activePipelineRunId ?? contentSourceRunId`. In the "background build A while viewing a DIFFERENT run C" case this priority can point the tracked id at A rather than the viewed C, so A's `pipeline_start` could still be treated as self. Outside the four bugs' scope; explicitly NOT fixed now (risk). Follow-up if the concurrent background-build-vs-viewed-run case is prioritized.
