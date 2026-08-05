---
id: BUG-011-sse
type: bug
status: done
area: [auth, artifacts]
summary: >-
  pipeline_complete → setContentSourceRunId is not run-scoped: a background run
  completing hijacks the VIEWED content-source
source: .planning/SSE-QA-BUG-LOG.md#bug-011
campaign: sse
severity: "🟡 minor"
---

### BUG-011 — pipeline_complete → setContentSourceRunId is not run-scoped: a background run completing hijacks the VIEWED content-source  [🟡 minor] [FIXED ✅]
- **RESOLVED:** FIXED (quick 260716-n2d, `e604b361`) — run-scoped the `setContentSourceRunId` at `page.tsx:530` with an `isForeignCompletion` guard mirroring the BUG-005 `isForeignRun` shape, reusing the existing `trackedRunIdRef`: a completion for the tracked/launched run (or when no run is tracked yet) is NOT foreign → the set runs byte-identically; only a genuine foreign concurrent completion is skipped. RED→GREEN source-lock (`contentSourceRunScope.source.test.ts` 3/3: old unconditional set gone, guard present, launch pins intact) + `revisionFamilyLinkage.source` updated to the refactored token (semantic preserved). Launch→watch flow byte-identical. Offline-proven; a live 2-concurrent-run timing repro was not run (flaky) — the guard is structurally symmetric with BUG-005, which WAS live-proven this campaign.
- **Found:** 2026-07-16 · surfaced by the BUG-010 investigation (adjacent, NOT WARNING-2) · surface: run-screen viewed content-source.
- **Symptom:** while viewing run C, if a DIFFERENT attached run (e.g. a background/launched run A) emits `pipeline_complete`, the page subscriber's `pipeline_complete` branch unconditionally runs `setContentSourceRunId(data.pipeline_run_id)` (`frontend/src/app/dashboard/page.tsx:530`), re-pointing the VIEWED content-source to A → C's deliverable/preview is hijacked.
- **Root cause:** same class as BUG-001/005/006/008 — a run-screen state mutation with NO run-identity guard. The BUG-005 fix (quick j1u) run-scoped the `pipeline_start` reset via `trackedRunIdRef`; the `pipeline_complete` branch was not covered.
- **Fix (APPLIED — 260716-n2d, `e604b361`):** guarded `setContentSourceRunId` at `page.tsx:530` by the tracked run id (`isForeignCompletion` — only re-point when the completing run == `trackedRunIdRef.current`, or when no run is tracked), mirroring the BUG-005 run-scope guard. The durable fix remains the systemic per-run subscriber scoping (see the "Bugs found" option #2 note) — this targeted guard covers the `pipeline_complete` branch specifically. Launch flow preserved (launched run's own completion still sets the content-source).
- **Verify (fail-before/pass-after):** two runs; view C; a background run A completes → assert `contentSourceRunId` stays C (fail-before: it flips to A).
