---
phase: 36
slug: home-history-my-workflows-b2
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-09
---

# Phase 36 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> OFFLINE + BY-DELTA discipline (Phase-35 precedent). No live server, no full pytest.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (FE)** | vitest 4.1.5 (verified present) |
| **Framework (BE)** | pytest (TARGETED suites only — full suite HANGS offline: Chromium/Bedrock/Postgres-gated) |
| **Config file** | `frontend/vitest.config.*` (FE); `backend/pytest.ini`/`pyproject` (BE, targeted) |
| **Quick run command (FE)** | `cd frontend && npx vitest run <changed-file.test.tsx>` |
| **Full suite command (FE)** | `cd frontend && npx vitest run && npx tsc --noEmit` |
| **Type identity (FE)** | `cd frontend && npx tsc --noEmit` — must be delta-clean (no NEW errors vs baseline) |
| **Backend command** | `python3.11 -m pytest <targeted test paths>` + `/opt/homebrew/bin/lint-imports` (MUST be 4 kept / 0 broken) |
| **Estimated runtime** | FE vitest changed-file ~seconds; targeted BE + lint-imports ~35s |

---

## Sampling Rate

- **After every task commit:** Run the FE quick command for the changed component's `*.test.tsx`; for backend tasks run the targeted BE test + `lint-imports`.
- **After every plan wave:** Run FE full suite (`vitest run` + `tsc --noEmit`) and the per-file retired-palette grep on every reskinned/new file.
- **Before verify:** FE full suite green + `tsc --noEmit` delta-clean + `lint-imports` 4/0 + retired-palette grep = 0 on all touched files.
- **Max feedback latency:** ~35 seconds (targeted BE) / seconds (FE changed-file).

---

## Per-file token-completeness gate (Phase-35 discipline — BLOCKING per reskinned/new file)

For every file this phase reskins or creates:

```
grep -rEn '#1B2A4A|#2563eb|#f5f5f0|\bInter\b|\bFraunces\b|\bJetBrains\b' <file>   # MUST be 0
```

AND positive proof of Phase-32 token / `components/ui/` primitive usage with no stray stock palette (`gray-`, `blue-`, raw `#hex`). Note: `var(--font-fraunces)` is a DEAD variable (live fonts are Manrope/Heebo per `frontend/src/app/layout.tsx`) → migrate to `font-serif`. The `\bInter\b` anchor is safe (does NOT match `setInterval`). `WorkflowHistory.tsx` is the largest reskin surface (~102 stock-Tailwind classes + ~37 raw hexes at research time) — budget accordingly.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 36-NN-NN | NN | N | SC-1..4 | T-36-* / — | owner-scoped 404 on cross-owner run-summary | unit | `python3.11 -m pytest backend/.../test_run_summary.py` | ❌ W0 | ⬜ pending |

*Planner/executor fill concrete rows per plan. Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Backend: `backend/app/tests/.../test_run_summary.py` — owner-scope (200 owner / 404 cross-owner / 404 missing), aggregation shape over EXISTING columns (no new fields), INV-3 goldens untouched.
- [ ] FE: reuse existing `WorkflowHistory.*.test.tsx`, `WorkflowCatalog.test.tsx` (rename → `HomeLaunchGrid.test.tsx`), `DashboardLayout.*.test.tsx` — update vi.mock module paths on rename.
- [ ] No new framework install — vitest + pytest + lint-imports all present.

*Existing infrastructure covers most phase requirements; add the run-summary endpoint test.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mocked Playwright e2e (list grouping, kebab, run-detail nav) | SC 1–4 | Offline webServer TIMEOUT (Phase-35 precedent) | LIVE-DEFERRED — capture a baseline; run under a live server in the end-of-milestone live pass |
| KAN-96 running→live view branch (live SSE/WS) | SC-2 | Needs a live run | LIVE-DEFERRED (Phase 34 live confirmation) |

*Any check needing a live server is LIVE-DEFERRED — do not hang, do not fabricate.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (verified: 12/12 tasks across 5 plans carry an `<automated>` block)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has one)
- [x] Wave 0 covers all MISSING references (backend `test_runs_api_summary.py` in 36-02; FE `SavedWorkflowsPage.test.tsx` in 36-03; component tests in 36-01/36-04/36-05)
- [x] No watch-mode flags (vitest `run`, not watch — grep-confirmed 0)
- [x] Feedback latency < 35s (targeted BE ~35s; FE changed-file ~seconds)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-09 (plan-phase plan-checker verification; strategy compliant. `wave_0_complete` stays false — Wave-0 test stubs are written during execute-phase, then the executor/nyquist-auditor flips it.)
