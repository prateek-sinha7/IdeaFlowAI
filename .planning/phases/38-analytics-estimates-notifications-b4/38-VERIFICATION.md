---
phase: 38-analytics-estimates-notifications-b4
verified: 2026-07-10T00:00:00Z
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
verdict: PASS
mode: offline-by-delta
gaps: []
deferred:
  - truth: "Live notification PUSH over the real connection (gate/running/done/failed pushed, not just on refetch)"
    addressed_in: "Phase 34"
    evidence: "38-VALIDATION.md Manual-Only + 38-03 SUMMARY LOCK-B: derivation built + unit-tested offline; live push is connection-dependent"
  - truth: "Live /api/analytics/summary endpoint round-trip against a running server"
    addressed_in: "Phase 34"
    evidence: "38-01/38-04 verification sections: live round-trip LIVE-DEFERRED"
  - truth: "Visual reskin verification (Phase-32 token render fidelity) + full mocked-Playwright e2e regression"
    addressed_in: "Phase 34"
    evidence: "Mocked Playwright times out offline; visual fidelity needs a live render"
human_verification: []
---

# Phase 38: Analytics, Estimates & Notifications [B4] Verification Report

**Phase Goal:** Deliver owner-scoped server-side analytics summary (SC-1: filters RECOMPUTE by re-query), a notifications feed off generic pipelineState markers + real Home deliverable estimates (SC-2) — with ZERO engine edits and additive-only backend.
**Verified:** 2026-07-10 (offline, by delta)
**Status:** PASS
**Re-verification:** No — initial verification
**Commit range:** `991f6f1c..HEAD` (HEAD `2227f241`)

## Goal Achievement

All 11 cross-cutting criteria (SC-1, SC-2, invariants a–i) verified against the codebase with commands actually run. No FAIL, no PARTIAL. Three items are genuinely LIVE-DEFERRED to Phase 34 (live push, live round-trip, visual/e2e) — none is an offline gap.

### Per-Criterion Verification Table

| # | Criterion | Status | Evidence (command → observed) |
|---|-----------|--------|-------------------------------|
| SC-1 | Owner-scoped `GET /api/analytics/summary?range=<enum>` aggregates caller's own runs; AnalyticsPage filters RECOMPUTE by re-query | PASS | `analytics.py:268` `db.query(WorkflowRun).filter(WorkflowRun.user_id == current_user.id)`; `AnalyticsPage.tsx:133` `useEffect(... getAnalyticsSummary(token, dateFilter) → setSummary)` keyed `[dateFilter]` (:156); `getWorkflows` in AnalyticsPage = 0. 4 backend tests + 9 analytics vitest all green. |
| SC-2 | Notifications feed gate/running/done/failed off generic markers; Home cards show REAL `~N agents · ~Xm` | PASS | hook `"gate"`=3, `markGatePaused`=2; DashboardLayout `markFailed(|markCancelled(|markGatePaused(`=3 (all CALLED); HomeLaunchGrid renders `~3 agents · ~5m` / `~5 agents` in DOM; 2 estimate tests + 4 hook tests + 4 panel tests green. |
| a | Owner-scope on `user_id` NOT `owner_id`; tests prove owner-200 / cross-owner isolation / recompute / malformed-range | PASS | `grep owner_id analytics.py`=0; `user_id == current_user.id` at :268. `test_owner_isolation` seeds A(3)+B(2 with 99.0/9999) → asserts A total==3, spend≈0.30, tokens 300/150 (B never leaks); `test_recompute` range=7d total==2 spend≈3.00; `test_malformed` 200-not-500 spend≈0.50; `test_range` all=3/today=1/zzz→200 fallback=2. `pytest test_analytics_api.py` → 4 passed. |
| b | ADDITIVE ONLY — no new table, no migration | PASS | diff `991f6f1c..HEAD`: `__tablename__`=0, `CREATE TABLE`=0, no alembic/migration file. Backend files touched: analytics.py (new), main.py (+5), test file only. |
| c | Hand-rolled inline SVG, NO external chart lib; `role="img"`+aria-label | PASS | `package.json` recharts/chart.js/d3/visx/victory/nivo = none; `charts/` chart-lib grep = 0; DonutChart/BarChart `role="img"`=2 each, `aria-label`=2 each. |
| d | Notifications key on generic markers, NO name-branch; LOCK-B no transport; SESSION-scoped | PASS | DashboardLayout Phase-38 diff added name-branch = 0; added lines key on `pipelineState.failed/.cancelled`, `reviewGateData && pipelineState?.isRunning`; transport (EventSource/WebSocket/stream) added in diff = 0. Session-scoped + reload-survival deferred (recorded in 38-03 SUMMARY). |
| e | INV-3 / no-dual-impl: inline `BarChart` + inline donut `<circle>` DELETED, replaced by extracted primitives | PASS | AnalyticsPage `grep "function BarChart|<circle "`=0; imports `./charts/BarChart` (:11) + `./charts/DonutChart` (:12). |
| f | `~N agents` from step_count/agent_count ALWAYS; `~Xm` only when history exists; NOT hardcoded; owner-scoped source | PASS | HomeLaunchGrid `getAnalyticsSummary|type_avg_duration_sec`=3, `step_count|agent_count`=3, hardcoded `24m/5-agents`=0. Estimate test "shows '~N agents · ~Xm' when history exists and '~N agents' (no time) when it doesn't" + "keys the average on the generic row id from owner-scoped 'all'-range summary" → both GREEN. |
| g | Retired-palette per touched/new FE file = 0 (DashboardLayout setInterval "Inter" is pre-existing false-pos, delta 0) + positive token usage | PASS | 8/9 touched files = 0; DashboardLayout = 2 (both `setInterval`/`clearInterval` at :187/:190; base 991f6f1c = 2; Phase-38 diff added retired lines = 0). Positive tokens present (AnalyticsPage 72, charts 8/9 per 38-02). |
| h | No workflow-name control flow in NEW analytics/estimate/notification code (pre-existing routing out of scope, delta 0) | PASS | New files (AnalyticsPage, charts, useNotifications) name-branch = 0. HomeLaunchGrid 2 (pre-existing handleClick :125/:129) + DashboardLayout 8 (pre-existing) — Phase-38 diff added name-branch to either = 0. |
| i | 5 goldens byte-identical; tsc identity; lint-imports 4/0 | PASS | 5 characterization goldens → `10 passed` (baseline 10, SNAPSHOT_UPDATE unset); `tsc --noEmit` (excl mockApi.ts) → 0 errors (baseline 0); `lint-imports` from backend/ → `4 kept, 0 broken`. |

**Score:** 11/11 criteria verified.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Analytics endpoint owner-isolation + recompute + malformed + range | `pytest tests/unit/test_analytics_api.py` | 4 passed in 0.22s | ✓ PASS |
| 5 characterization goldens byte-identical | `pytest tests/agents/test_characterization_*` (5 files) | 10 passed in 35.13s | ✓ PASS |
| Analytics FE (AnalyticsPage + 2 charts) | `vitest run src/components/analytics` | 3 files / 9 tests passed | ✓ PASS |
| Notifications hook (gate/failed/cancelled) | `vitest run src/hooks/useNotifications` | 1 file / 4 tests passed | ✓ PASS |
| NotificationPanel a11y regression | `vitest run src/components/ui/NotificationPanel` | 1 file / 4 tests passed | ✓ PASS |
| HomeLaunchGrid estimate line (2 new SC-2 tests) | `vitest run src/components/catalog/HomeLaunchGrid.test.tsx` | both estimate tests GREEN | ✓ PASS |
| tsc identity | `tsc --noEmit \| grep -v mockApi.ts \| grep -c error` | 0 (baseline 0) | ✓ PASS |
| Hexagonal boundary | `lint-imports` (from backend/) | 4 kept, 0 broken | ✓ PASS |

### Key Link Verification

| From | To | Via | Status | Detail |
|------|----|----|--------|--------|
| `analytics.py` | `WorkflowRun` | owner-scoped base query | WIRED | `.filter(WorkflowRun.user_id == current_user.id)` :268 |
| `main.py` | analytics router | `include_router` | WIRED | import :18, `include_router(analytics_router)` :180 |
| `AnalyticsPage.tsx` | `/api/analytics/summary` | `getAnalyticsSummary(token, dateFilter)` on filter change | WIRED | useEffect :133 keyed `[dateFilter]` → `setSummary(data)` :145 |
| `AnalyticsPage.tsx` | charts primitives | `import DonutChart/BarChart` | WIRED | :11–12; inline copies deleted (0 hits) |
| `DashboardLayout.tsx` | useNotifications transitions | generic terminal + gate markers | WIRED | markFailed/markCancelled off `pipelineState.failed/.cancelled`; markGatePaused off `reviewGateData && isRunning` |
| `HomeLaunchGrid.tsx` | `type_avg_duration_sec` | `getAnalyticsSummary(token, "all")` | WIRED | second cancelled-guarded fetch; `round(sec/60)` per `row.id` |

### Anti-Patterns / Known Reds (out of scope — NOT phase-38 caused)

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `DashboardLayout.tsx:187/190` | `setInterval`/`clearInterval` matches "Inter" retired-font grep | ℹ️ Info | Pre-existing (base = 2), delta 0; not an actual font usage. |
| `HomeLaunchGrid.test.tsx` "Phase 21 — Your workflows + kebab" | 5 tests fail | ℹ️ Info | PROVEN failing at base 991f6f1c (feature moved to SavedWorkflowsPage in an earlier phase). Phase 38 added 2 NEW estimate tests (both GREEN); did not touch the Phase-21 tests. Logged in `deferred-items.md`. |
| `HomeLaunchGrid.tsx:125/129` / `DashboardLayout.tsx` name-branches | `if (type === "prototype"/"ppt")` launch-routing | ℹ️ Info | Pre-existing launch routing; SC-h delta 0 (Phase 38 introduced none). |
| `ReviewGatesSection.test.tsx` (per baseline) | 3 failed / 16 passed | ℹ️ Info | Data-drift, byte-identical to base; not touched by Phase 38 (not re-run this pass — documented baseline). |

### Human Verification Required

None. All offline-verifiable criteria passed with commands run. The items below are LIVE-DEFERRED to Phase 34 (a later milestone phase), not human-needed decisions for this phase.

### LIVE-DEFERRED to Phase 34

1. **Live notification PUSH** over the real connection — confirm gate/running/done/failed arrive pushed (not just on refetch). Derivation logic built + unit-tested offline (38-03); only the live push is connection-dependent (LOCK-B: no transport touched).
2. **Live `/api/analytics/summary` round-trip** against a running server — the endpoint is owner-scoped + unit-tested offline; the live HTTP round-trip needs a running backend.
3. **Visual reskin fidelity** (Phase-32 token render) + **full mocked-Playwright e2e regression** — mocked Playwright times out offline; visual fidelity needs a live render.

### Gaps Summary

No gaps. Backend is additive read-only (no table, no migration, goldens byte-identical, lint-imports 4/0). SC-1 recompute is a genuine server re-query keyed on `dateFilter` (not a client re-filter). SC-2 notifications and Home estimates key on generic markers/`row.id` with zero new workflow-name branches and zero transport touch. Charts are hand-rolled a11y-labelled SVG with the inline copies deleted (INV-3 single implementation). Token gate is clean on every touched file (the single DashboardLayout hit is a pre-existing `setInterval` substring, delta 0). tsc identity holds. The three deferred items are explicitly scheduled for the Phase 34 live pass and do not block phase completion.

---

_Verified: 2026-07-10 (offline, by delta)_
_Verifier: Claude (gsd-verifier)_
