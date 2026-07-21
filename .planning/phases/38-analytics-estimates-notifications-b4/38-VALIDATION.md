---
phase: 38
slug: analytics-estimates-notifications-b4
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-10
---

# Phase 38 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Additive READ-only backend + FE reskin/extract/wire. Verify BY DELTA, OFFLINE.
> Source: 38-RESEARCH.md `## Validation Architecture`. No REQ-IDs mapped in ROADMAP
> (phase_req_ids=null); rows key to Success Criteria SC-1/SC-2 + invariants + the
> research-inferred SHELL-05.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Backend framework** | pytest via `python3.11 -m pytest` (`backend/tests/unit/`, `backend/tests/agents/`) |
| **Backend config** | `backend/pyproject.toml` (import-linter contracts under `[[tool.importlinter.contracts]]`) |
| **Frontend framework** | vitest + `tsc --noEmit` (identity) + per-file retired-palette grep |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/unit/test_analytics_api.py -x` · `cd frontend && npx vitest run src/components/analytics` |
| **Full suite command** | targeted only (see Sampling) — **NEVER full pytest (hangs offline: Chromium/Bedrock/Postgres-gated)** |
| **Estimated runtime** | backend targeted ~10–20s · vitest targeted ~10–30s · lint-imports ~5s |

---

## Sampling Rate

- **After every task commit:** the targeted `pytest -k` / `vitest run <dir>` for the touched surface + the per-file retired-palette grep (`#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains` → 0).
- **After every plan wave:** `test_analytics_api.py` full + `vitest run src/components/analytics src/components/catalog src/hooks` + `tsc --noEmit` identity + `/opt/homebrew/bin/lint-imports` (4 kept / 0 broken).
- **Before `/gsd-verify-work`:** the 5 characterization goldens byte-identical + lint-imports 4/0 + all targeted suites green.
- **Max feedback latency:** < 60 seconds.
- **NEVER** full pytest. Mocked Playwright e2e times out offline → **live-deferred to Phase 34**.

---

## Per-Task Verification Map

| Behavior | Success Criterion | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists |
|----------|-------------------|------------|-----------------|-----------|-------------------|-------------|
| Owner A's `/analytics/summary` includes only A's runs | SC-1 | T-38-01 (cross-owner leak) | `WHERE user_id == current_user.id`; cross-owner → 404 | unit | `python3.11 -m pytest tests/unit/test_analytics_api.py -k owner_isolation -x` | ❌ W0 |
| `?range=7d` totals == recompute of seeded window | SC-1 | — | date-scoped aggregate correct | unit | `python3.11 -m pytest tests/unit/test_analytics_api.py -k recompute -x` | ❌ W0 |
| Malformed `token_usage` blob → empty aggregate, not 500 | SC-1 | T-38-02 (DoS) | `json.loads` in try/except → `{}` | unit | `python3.11 -m pytest tests/unit/test_analytics_api.py -k malformed -x` | ❌ W0 |
| `range=all|today|7d|30d` date scoping | SC-1 | T-38-03 (enum allow-list) | `range` is allow-listed enum | unit | `python3.11 -m pytest tests/unit/test_analytics_api.py -k range -x` | ❌ W0 |
| Date-filter change → getAnalyticsSummary called → chart re-renders w/ new numbers | SC-1 | — | N/A | component | `npx vitest run src/components/analytics/AnalyticsPage` | ❌ W0 |
| Donut/Bar render `role="img"` + `aria-label` (chart text alt) | SC-2 (a11y) | — | N/A | component | `npx vitest run src/components/analytics/charts` | ❌ W0 |
| AnalyticsPage + chart files retired-palette grep = 0 (token gate) | SC-1/SC-2 | — | N/A | grep | `grep -REc "#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains" <file> → 0` | n/a |
| Home card shows real "~N agents · ~Xm" from step_count + history avg (not hardcoded) | SC-2 | — | N/A | component | `npx vitest run src/components/catalog/HomeLaunchGrid` | exists (extend) |
| Notification appears for each of gate/running/done/failed transitions | SC-2 | T-38-04 (SC-001 no name-branch) | keyed on generic run status, not workflow name | component | `npx vitest run src/hooks/useNotifications` (+ DashboardLayout wiring) | ❌ W0 |
| Notifications feed keyboard + aria (a11y) | SC-2 (a11y) | — | N/A | component | `npx vitest run src/components/ui/NotificationPanel` | exists (extend) |
| 5 characterization goldens byte/event-identical | INV-3 | — | additive read-only → untouched | characterization | `python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_characterization_prototype_revision.py` | exists |
| capabilities never import kernel/app — 4 kept / 0 broken | import-linter | — | hexagonal boundary | lint | `/opt/homebrew/bin/lint-imports` | exists |
| No new type errors vs baseline | tsc identity | — | N/A | type | `cd frontend && npx tsc --noEmit` (identity vs baseline) | exists |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/unit/test_analytics_api.py` — owner-isolation + cross-owner-404 + recompute-correctness + malformed-blob-guard + range date-scoping (backend aggregation endpoints).
- [ ] `frontend/src/components/analytics/charts/DonutChart.test.tsx` + `BarChart.test.tsx` — render + `role="img"`/`aria-label` a11y.
- [ ] `frontend/src/components/analytics/AnalyticsPage.test.tsx` — filter→refetch→re-render + retired-palette-absent assertion.
- [ ] `frontend/src/hooks/useNotifications.test.tsx` — `gate` kind + failed/cancelled transitions (extend or new).
- [ ] Framework install: none — pytest / vitest / tsc all present.

---

## Manual-Only Verifications

| Behavior | Success Criterion | Why Manual | Test Instructions |
|----------|-------------------|------------|-------------------|
| Live notification PUSH over the real connection | SC-2 (deferred) | Needs a live server/connection (SSE/WS) — the feed derivation logic is built + unit-tested offline; only the live push is connection-dependent | **Live-deferred to Phase 34**: on a real run, confirm gate/running/done/failed notifications arrive pushed (not just on refetch) |
| Full mocked-Playwright e2e regression | SC-1/SC-2 | Mocked Playwright times out offline | **Live-deferred to Phase 34** live pass |

---

## Validation Sign-Off

- [ ] All tasks have an `<automated>` verify command or a Wave 0 test dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING (❌ W0) references
- [ ] No watch-mode flags (all commands are one-shot `run`/`-x`)
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter (after Wave 0 stubs land)

**Approval:** pending
