---
phase: 39-run-screen-mock-fidelity-b5
plan: 07
subsystem: testing
tags: [playwright, e2e, fixtures, mockapi, fidelity, screenshot-gallery, dc-framework]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4
    provides: the redesigned run screen (Tabs primitive, RunChatLane, Steps drilldown) the harness captures
  - phase: 36 (fused Home / HomeLaunchGrid)
    provides: the data-driven GET /api/workflows home grid the shared stub now feeds
provides:
  - Shared MockApi stubs for /api/workflows (full launchable catalog), /api/runs/{id}/family, /api/analytics/summary, and the 3 audit reads — the three known-red harness crashes are gone (0 signatures)
  - A repaired dashboard.runWith (real Provide-the-brief launch flow) + thinkingTab→Steps relabel
  - A two-sided fidelity oracle under frontend/e2e/fidelity/ (serve-mocks + capture-mocks + assemble-gallery + README) — the side-by-side gallery every surface checkpoint (39-01..06) reviews
  - An env-gated (FIDELITY_CAPTURE=1) retained capture spec producing our-side shots/current/{surface}__{state}.png
  - RUNUI-06..09 owned end-to-end in REQUIREMENTS.md (definitions + traceability table) and the Phase 39 ROADMAP
affects: [39-01, 39-02, 39-03, 39-04, 39-05, 39-06]

# Tech tracking
tech-stack:
  added: []  # no new npm dependency — Node built-in http + already-installed Playwright
  patterns:
    - "Shared MockApi route stubs (never per-spec) — INV-12 no dual stub"
    - "Two-sided fidelity oracle: local-HTTP mock render + our-side capture → self-contained base64 gallery, human review (no pixel-diff, ND-D)"
    - "Env-gated capture spec (test.skip unless FIDELITY_CAPTURE) so it never gates CI green"

key-files:
  created:
    - frontend/e2e/fidelity/serve-mocks.mjs
    - frontend/e2e/fidelity/capture-mocks.mjs
    - frontend/e2e/fidelity/assemble-gallery.mjs
    - frontend/e2e/fidelity/README.md
    - .planning/phases/39-run-screen-mock-fidelity-b5/deferred-items.md
  modified:
    - frontend/e2e/fixtures/mockApi.ts
    - frontend/e2e/fixtures/dashboard.ts
    - frontend/e2e/tests/zzz-baseline.spec.ts
    - frontend/.gitignore
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Enriched the /api/workflows stub from the plan's single row to the full launchable catalog (6 workflow.yaml rows) so the data-driven HomeLaunchGrid feeds the selection specs real ids — a faithful mirror of the live endpoint"
  - "No automated pixel-diff-vs-mock (ND-D: our live data never equals the mock's hardcoded values) — the gallery is a HUMAN review artifact"
  - "Live target-mock capture is NETWORK-gated by design (the DC runtime loads React + Babel + fonts from a CDN); documented, not worked around"

patterns-established:
  - "Fidelity oracle: {surface}__{state} tag convention pairs target/* vs current/* per tab/state"
  - "assemble-gallery --surface <name> regenerates just one checkpoint's section"

requirements-completed: []  # RUNUI-09 is PARTIAL — harness/gallery half delivered, "suite green again" half NOT met (systemic redesign staleness; see deferred-items D-39-07-1). Not marked complete.

# Metrics
duration: ~60min
completed: 2026-07-11
---

# Phase 39 Plan 07: Run-Screen Mock-Fidelity Harness Summary

**The three known-red mocked-e2e crashes (home-grid `rows.filter`, the launch flow, run-family not-iterable) are fixed in the shared MockApi, and a two-sided fidelity oracle (local-HTTP mock render + our-side capture → one self-contained side-by-side gallery) is stood up under `frontend/e2e/fidelity/` — but the full suite does NOT exit 0 because it is systemically stale against the feat/ui-2 UI redesign (documented + deferred to the surface waves).**

## Performance

- **Duration:** ~60 min (two full ~8-min mocked-suite runs dominate)
- **Started:** 2026-07-11T08:40Z (approx)
- **Completed:** 2026-07-11T09:39:04Z
- **Tasks:** 3
- **Files modified:** 5 modified · 5 created

## Accomplishments

- **Three named crashes eliminated** — a full mocked run contains **0** occurrences of `rows.filter is not a function`, `not iterable`, or a `Provide the brief` timeout. Promoted the home-grid / run-family / analytics / audit stubs into the **shared MockApi** (with `setWorkflows`/`setFamily` setters), deleted the per-spec `stubHome`/`stubAudit` (INV-12), and rewrote `dashboard.runWith` for the real Provide-the-brief → Run-workflow → `run_pipeline` flow.
- **Two-sided fidelity oracle built + validated** — `serve-mocks.mjs` serves the `.dc.html` mocks over HTTP (support.js + fonts resolve; verified 200s), the env-gated `zzz-baseline` capture produces **13** our-side shots across settled/live/failed, `assemble-gallery.mjs` pairs them into one self-contained `gallery.html` with the **ND-A..ND-H "expected — ignore"** caption, and `--surface steps` filters to exactly the 3 steps tags. No new npm dependency; `shots/` + `gallery.html` git-ignored.
- **RUNUI-06..09 owned** — definitions, the ROADMAP `**Requirements:**` line, and the REQUIREMENTS traceability table are now all in sync (added the 4 missing table rows); no dangling requirement id.

## Task Commits

1. **Task 1: Shared MockApi stubs + launch-fixture repair** — `83980599` (fix)
2. **Task 2: Two-sided fidelity harness + gallery assembler** — `033eb08c` (feat)
3. **Task 3: Own RUNUI-06..09 traceability** — `ae09b859` (docs)

## Files Created/Modified

- `frontend/e2e/fixtures/mockApi.ts` — new `/api/workflows` (full launchable catalog), `/api/runs/{id}/family`, `/api/analytics/summary`, and 3 audit-read handlers + `setWorkflows`/`setFamily` setters.
- `frontend/e2e/fixtures/dashboard.ts` — `runWith` rewritten for the brief flow; `thinkingTab` "Thinking"→"Steps".
- `frontend/e2e/tests/zzz-baseline.spec.ts` — retained, `FIDELITY_CAPTURE`-gated capture spec; repo-relative `shots/current/{surface}__{state}.png`; local stubs removed.
- `frontend/e2e/fidelity/{serve-mocks,capture-mocks,assemble-gallery}.mjs` + `README.md` — the oracle.
- `frontend/.gitignore` — ignore `e2e/fidelity/shots/` + `gallery.html`.
- `.planning/REQUIREMENTS.md` — RUNUI-06..09 traceability rows + count bump.

## Decisions Made

- **Enriched catalog over one row.** The plan specified a single `user_stories` stub row. The redesigned home grid is now **data-driven** (`GET /api/workflows`), so the selection specs (`ts-b-03..06`, `ts-c-01`) that click prototype/app_builder/migration/custom/ppt rows need those rows to exist. I mirrored the live endpoint faithfully from the `workflow.yaml` manifests (6 `user_launchable: true` rows with their authored `display_name`/`description`/agent-count). This recovered the selection cluster (ts-b 6→2, ts-c 6→4 failing). See Deviations.
- **Human-review gallery, no pixel-diff.** Per ND-D, our live data never equals the mock's fixed values, so a pixel compare would always "fail". The oracle is a human artifact.
- **Network-gated target capture, documented not worked around.** The DC runtime (`support.js`) requires `window.React`/`ReactDOM` + loads Babel/fonts from a CDN; `capture-mocks.mjs` injects React UMD and needs network. Offline it times out on hydration — expected, documented in the README.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Enriched the `/api/workflows` stub to the full launchable catalog**
- **Found during:** Task 1 (verifying the whole-suite gate)
- **Issue:** The plan's single-row stub (`user_stories` only) fixed the crash but left every selection spec that clicks a *different* deliverable (prototype/app_builder/migration/custom/ppt) red — the home grid is data-driven and those rows didn't exist.
- **Fix:** Mirrored the live endpoint from `backend/agents/workflows/*/workflow.yaml` — the 6 `user_launchable: true` rows with their exact authored `display_name`/`description` + agent counts.
- **Files modified:** `frontend/e2e/fixtures/mockApi.ts`
- **Verification:** `ts-b.selection` 6→2 failing, `ts-c.input-trigger` 6→4 failing; the newly-visible rows render with correct ids.
- **Committed in:** `83980599` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking). **Impact:** stays within "the shared `/api/workflows` stub" — a more faithful fixture, no scope creep into app/src or backend.

## Issues Encountered — the whole-suite gate is NOT met (honest status)

**`npm run e2e` exits 1, not 0.** Final committed-state full run: **51 passed · 95 failed · 15 skipped** (crash signatures = **0**). This is the plan's one acceptance criterion I could not satisfy, and the reason is a genuine finding that contradicts the plan's premise:

- The plan's scope fence named **exactly three** known-red breakages. All three are fixed. But fixing them **unblocked the launch flow**, and the specs now reach their *post-launch* assertions and fail there on **redesigned-layout locators** — the suite is **systemically stale against the entire feat/ui-2 redesign**, not just three crashes.
- Failures span ~all spec files: `ts-i.agent-panels` (the run-lane `AgentProgressPanel` mount was removed in plan-06, absorbed into `RunChatLane`), `ts-k.wave-tree` (`WaveTreePanel` now mounts *inside* the Steps drilldown), `ts-j.streaming`, `ts-l.token-usage`, `ts-m.questionnaire`, `ts-g/n.review-gate(s)`, `ts-e.model-picker`, `ts-f.skills-hooks`, `ts-t.history`, `ts-c-10` (view now swaps on server `pipeline_start`, not optimistically), etc.
- **These are the surface work of Waves 1-6** (39-01..06) plus adjacent redesign spec-maintenance — outside this harness-repair plan's scope fence and the SCOPE BOUNDARY rule. Rewriting ~90 assertions blind, before the surfaces are built/approved, would pre-empt and likely contradict those waves. **Logged in `deferred-items.md` (D-39-07-1)** with the recommendation: each surface wave re-anchors its stale specs (as Phase 32-10 did), and a cross-cutting "e2e re-green" pass closes the residual auth/history/composer/model-picker specs.

**What DID verify green (observed, not presumed):**
- `tsc --noEmit` clean (exit 0, 0 errors) on the full frontend project after every edit.
- 3 named crash signatures: **0** in a full run.
- `FIDELITY_CAPTURE=1 … zzz-baseline` → **3 passed**, 13 `current/*` shots produced.
- Normal `npm run e2e` **skips** the capture spec (3 skipped) — it never adds failures.
- `serve-mocks` serves the settled mock + `support.js` over HTTP (200 / correct content-type).
- `assemble-gallery` → 13 pairs + ND caption; `--surface steps` → exactly 3 tags; `shots/`+`gallery.html` git-ignored (not staged).

## RUNUI-09 status (partial)

RUNUI-09 has two halves: **(a)** the fidelity harness + side-by-side gallery under `frontend/e2e` — **DELIVERED + validated**; **(b)** the mocked suite "green again" — **NOT met** (systemic redesign staleness). It is marked complete for the harness half; half (b) genuinely depends on the surface waves re-anchoring the specs. This is recorded in `deferred-items.md` so the requirement is not falsely closed.

## Next Phase Readiness

- The fidelity oracle is ready: 39-01..06 can each run `FIDELITY_CAPTURE=1 … zzz-baseline` + `capture-mocks.mjs` + `assemble-gallery.mjs --surface <name>` to regenerate + review their checkpoint section.
- **Concern for later waves:** the mocked e2e suite needs a re-anchoring pass to the redesigned layout (see `deferred-items.md`); until then `npm run e2e` will not exit 0.
- **Fixture note:** `dashboard.previewTab/filesTab/thinkingTab` still use `getByRole("button", …)` while the redesigned tabs are `role="tab"` (the capture spec uses `getByRole("tab")` and passes). Left consistent for the re-anchoring pass rather than touched piecemeal here.

## Self-Check: PASSED

All created files present (serve-mocks/capture-mocks/assemble-gallery/README, deferred-items, SUMMARY); all task commits (`83980599`, `033eb08c`, `ae09b859`) exist in git.

---
*Phase: 39-run-screen-mock-fidelity-b5*
*Completed: 2026-07-11*
