---
id: BUG-019-sse
type: bug
status: done
summary: >-
  A fresh top-level launch shows the PREVIOUS run's name in the left-lane header title
source: .planning/SSE-QA-BUG-LOG.md#bug-019
campaign: sse
severity: "🟠 major"
---

### BUG-019 — A fresh top-level launch shows the PREVIOUS run's name in the left-lane header title  [🟠 major] [FIXED ✅ — LIVE-PROVEN]
- **RESOLVED:** FIXED + LIVE-PROVEN (quick 260717-rs7; commit `1f3730d8`; feat/ui-2, NOT pushed). Root cause: `frontend/src/components/layout/DashboardLayout.tsx:1381-1387` — on a fresh launch (`contentSourceRunId == null`) `viewedRun` fell back to `recentRuns?.[0]` (the PREVIOUS run, because nothing inserts the new run into `recentRuns` at launch — no live-runs poll), so its title shadowed `submittedBrief`. The unfixed second half of the BUG-001 family; type-agnostic. Fix (1 line, :1384): `: recentRuns?.[0]` → `: undefined` → fresh launch resolves `runHeaderTitle` to `submittedBrief`; reopen/completion (`!= null` branch) untouched. RED→GREEN vitest (rewrote the laneTitle launch case: title == submittedBrief, NOT RUN_A.title); 24 tests green; tsc clean. Regression: mocked Playwright ts-chat/ts-t.history 11/11. **LIVE-PROVEN** (screenshot `bug019-freshlaunch-title.png`): fresh user_stories launch (Home → "Generate product requirements" → brief → Run) shows header title = the new brief "A fresh inventory tracker app…", NOT "an apple replica site" (recents[0]); eyebrow "USER STORIES". Detail: `.planning/BUG-019-020-GROUNDED-CONTEXT.md`. See BUG-021 for the related (open) transcript-body carryover.
