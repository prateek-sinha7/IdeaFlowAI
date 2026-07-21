---
phase: 35
slug: shell-chrome-reskin-pages-b1
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-09
---

# Phase 35 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detailed per-deliverable evidence lives in `35-RESEARCH.md` → `## Validation Architecture`.
> This phase is FRONTEND-ONLY, OFFLINE, and VERIFIED BY DELTA (DEF-29-06-1) — no live server, no backend change.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest (unit/component) + Playwright `--project=mocked` (e2e) + `tsc --noEmit` (types) |
| **Config file** | `frontend/vitest` (via `package.json`), `frontend/playwright.config.ts` (project `mocked` @ L32), `frontend/tsconfig.json` (noEmit:true) |
| **Quick run command** | `cd frontend && npm run test` (=`vitest --run`) |
| **Full suite command** | `cd frontend && npm run test && npx tsc --noEmit && npm run e2e` |
| **Retired-palette gate (per touched file)** | `grep -rEn '#1B2A4A\|#2563eb\|#f5f5f0\|\bInter\b\|\bFraunces\b\|\bJetBrains\b' <file>` must equal **0** |
| **Token-authority gate (per touched file, D-15)** | file consumes `@theme` token classes (`bg/text/border-{brand,ink-*,surface-*,line-*,status-*}`, `font-sans/serif/mono`) AND has **no** stray stock palette (`gray-/slate-/blue-/emerald-*`, raw `#hex`) — the grep gate is a FLOOR, not a ceiling |
| **Estimated runtime** | vitest ~30–60s · tsc ~20–40s · mocked e2e ~2–5 min |

---

## Sampling Rate

- **After every task commit:** `cd frontend && npm run test` + the per-file retired-palette + token-authority greps on the files that task touched.
- **After every plan wave:** `npx tsc --noEmit` (identity — no NEW type errors vs baseline) + `npm run e2e` (mocked) compared **BY DELTA** against the pre-existing baseline captured in Wave 0.
- **Before verify:** full suite green BY DELTA (do NOT chase absolute-green — DEF-29-06-1).
- **Max feedback latency:** ~60s (unit) / ~5 min (mocked e2e).

---

## Per-Task Verification Map

Derived during planning from each PLAN.md task. Every task's `<acceptance_criteria>` MUST include: (1) retired-palette grep = 0 on its files, (2) positive `@theme` token/primitive usage + no stray stock palette, (3) a behavior-preservation assertion (existing vitest/e2e spec still green BY DELTA), and (4) where the surface is interactive, an a11y assertion (keyboard + aria). See `35-RESEARCH.md` → `## Validation Architecture` for the per-deliverable evidence set.

| Task ID | Plan | Wave | Deliverable | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| (populated by gsd-planner) | — | — | — | vitest / e2e-mocked / tsc / grep | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Capture the pre-existing mocked-Playwright baseline (`npm run e2e` result set) so later runs verify **by delta**, not absolute-green (DEF-29-06-1).
- [ ] Add/confirm component render + a11y specs (keyboard + aria) for the interactive shell surfaces before reskin: `AppHeader` (nav pill + profile menu), `NotificationPanel` (bell/panel), and reskin-render checks for `AccountSettings`, `LibraryPage`, `admin/page`.
- [ ] No framework install needed — vitest + Playwright(`mocked`) + tsc already present.

---

## Manual-Only Verifications

| Behavior | Why Manual | Test Instructions |
|----------|-----------|-------------------|
| Any check requiring a LIVE server or real backend (e.g. live auth redirect, live notifications feed) | Phase is offline-only; live feed is Phase 38; backend untouched (INV-3) | Mark **live-deferred** — do NOT block phase completion; defer to the end-of-milestone live pass |

---

## Validation Sign-Off

- [ ] Every task has an automated verify (vitest / mocked-e2e / tsc / grep) or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 baseline captured before reskin edits land
- [ ] No watch-mode flags (`--run` / non-interactive only)
- [ ] Feedback latency < 60s (unit)
- [ ] `nyquist_compliant: true` set once the per-task map is populated and green by delta

**Approval:** pending
