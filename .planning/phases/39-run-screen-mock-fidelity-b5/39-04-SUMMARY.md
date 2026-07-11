---
phase: 39-run-screen-mock-fidelity-b5
plan: 04
subsystem: ui
tags: [react, run-screen, audit, compliance, mock-fidelity, tailwind, tokens, playwright, screenshot-gallery]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4
    provides: the redesigned Audit tab (real 3-endpoint reader, status/severity tokens) this reskins to the mock
  - phase: 39-run-screen-mock-fidelity-b5 (plan 07)
    provides: the two-sided fidelity oracle (serve/capture-mocks + assemble-gallery + FIDELITY_CAPTURE zzz-baseline) + the shared MockApi audit stubs this plan enriches
provides:
  - The Audit tab brought pixel-as-is to the mock across settled (passed all gates) + failed (blocked/denied), human-approved closed to ND-A..ND-T
  - Header "Audit trail · N records" + subline + a brand Export ▾ menu (CSV / JSON wired via the existing exporter; Compliance-report disabled — ND-6 no PDF)
  - An attribution + compliance summary card (live Run id · Started · Duration; owner/workspace elided) with the 6-stat grid (Checks/Passed/Warnings/Blocked/Denied/Secret-scans), coverage chips, and the green/red verdict banner
  - The fuller category taxonomy (Governance / Security / Activity with finer gate / validation / secret-scan / exec / perf / behavioral sub-labels) DERIVED from the real gate/validation/exec fetches — never fabricated (SC-001/ND-D)
  - Collapsible "What is this?" key/value entries + All/Gov/Sec/Act group filter + Blocked-only toggle + free-text search + the dashed integrity footer
  - Intended-divergence register additions ND-R (group filters replace the mock's severity buttons) / ND-S (owner/workspace elided) / ND-T (static explainer copy + CSV/JSON-only export)
  - An optional additive `AuditRunMeta` prop (owner/workspace/started/duration) for a later shell to thread live attribution
affects: [39-05, 39-06]

# Tech tracking
tech-stack:
  added: []  # no new dependency — existing lucide-react + Phase-32 CSS tokens + the existing auditExporter
  patterns:
    - "Audit taxonomy DERIVED from real fetch signals (secret-scan/perf/behavioral appear only when a live row carries the signal) — never a cloned mock row (SC-001/ND-D)"
    - "Single 3-state outcome (pass/warn/block) computed once per row from gate.outcome | validation.severity | exec.outcome, driving both the icon-wrap glyph and the verdict badge"
    - "Harness seeding (NOT production data): richer audit categories + a failed variant seeded in MockApi via setAuditVariant so the fidelity capture exercises every category + the red banner"

key-files:
  created: []
  modified:
    - frontend/src/components/results/AuditTab.tsx
    - frontend/src/components/results/__tests__/AuditTab.test.tsx
    - frontend/e2e/fixtures/mockApi.ts
    - frontend/e2e/tests/zzz-baseline.spec.ts
    - frontend/e2e/fidelity/capture-mocks.mjs
    - frontend/e2e/fidelity/assemble-gallery.mjs

key-decisions:
  - "Reused the existing getRunGateEvents / getRunValidationResults / getRunExecRuns fetchers + exportAuditCSV/JSON exporter unchanged (SC-001/INV-12) — this plan is presentation + a fuller category mapping over data that already flows (D39-4)"
  - "Adopted the mock's filter row exactly (All/Gov/Sec/Act + Blocked-only + Search) and RETIRED the prior standalone CRITICAL/HIGH/MEDIUM/LOW severity-filter buttons — severity stays a per-row chip (ND-R, INV-12 no dual filter row)"
  - "Elide owner/workspace in the attribution row (the audit fetches don't carry them) rather than fabricate them; Started/Duration derived from the row timestamps unless a live runMeta is threaded (ND-S / T-39-04-01)"
  - "The 'What is this?' explainer is static per-category UI copy and coverage chips are derived per fine-category present; the Compliance-report export option is disabled — CSV/JSON only, no signed PDF (ND-T / ND-6)"
  - "Derive behavioral-hook from gate/validation label signals rather than reviving the deprecated hook_runs source (D39-4 replaced hook_runs) — stays on the three real fetches"

patterns-established:
  - "deriveFineCategory(source,label,step,gateKind): net-new categories (secret-scan/perf/behavioral) keyed on real row signals only"
  - "MockApi.setAuditVariant('settled'|'failed'): the failed capture returns the blocked/denied/secrets-hit audit set so the red 'governance stopped this run' banner is exercised"

requirements-completed: []  # RUNUI-06 + RUNUI-08 already completed in 39-01; RUNUI-07 stays PARTIAL — the fuller Audit categories (its 4th affordance) landed here, but Share / Version ▾ / "Renders as" are 39-05/06. Not closed.

# Metrics
duration: ~1h15m (autonomous build + captures, then one human-verify checkpoint round)
completed: 2026-07-11
---

# Phase 39 Plan 04: Audit Tab — Mock Fidelity Summary

**The Audit tab is now pixel-as-is to the mock across settled (passed all gates) + failed (blocked/denied) — an "Audit trail · N records" header + Export ▾ menu, a live attribution + 6-stat compliance grid + coverage chips + green/red verdict banner, an All/Governance/Security/Activity group filter + Blocked-only + Search, and collapsible "What is this?" entries carrying the fuller category taxonomy — all derived from the existing real gate/validation/exec fetches (SC-001), closed to the intended-divergence register ND-A..ND-T.**

## Performance

- **Duration:** ~1h15m (autonomous build + fidelity captures, one human-verify checkpoint round)
- **Completed:** 2026-07-11
- **Tasks:** 2 autonomous + 1 checkpoint (human-verify)
- **Files modified:** 6 (1 component + 1 test + 4 harness)

## Accomplishments

- **Header + Export menu** — replaced the plain title/coverage/counter header with the mock's "Audit trail" title (Manrope light 19px) + shield + "N records" pill + subline, and the plain CSV/JSON export buttons with a brand **Export ▾** menu (CSV — flattened rows / JSON — raw rows wired via the existing `exportAuditCSV`/`exportAuditJSON`; a disabled Compliance-report entry — ND-6 no PDF path).
- **Attribution + compliance summary card** — a live attribution row (Run id truncated · Started · Duration derived from the row timestamps; owner/workspace elided per ND-S), the **6-stat compliance grid** (Checks / Passed / Warnings / Blocked / Denied / Secret-scans, coloured via the status tokens), **coverage chips** one-per-fine-category-present, and the **verdict banner**: green "0 blocked · 0 denied · 0 critical — run passed all governance gates." when clean, red "{n} blocked · {n} denied · {n} critical — governance stopped this run." when not — all off the computed counts (ND-D).
- **Fuller category taxonomy + collapsible entries** — each real row is mapped to the mock's finer category (gate / validation / exec) with the net-new sub-categories (secret-scan → Security, perf → Perf/Activity, behavioral → Governance) **derived from signals in the live row**; entries carry the circular pass/warn/block glyph, title + meta, category chip, optional severity chip, verdict badge, chevron, and a collapsible body with the violet "What is this?" explainer + key/value detail rows. Added the mock's **All/Governance/Security/Activity** group filter (live counts) + **Blocked / denied only** toggle + **Search** box, and the dashed **integrity footer**.
- **Fidelity oracle** — regenerated the two-sided gallery for the audit surface with 3 fully-paired sections (`audit__settled`, `audit-expanded__settled`, `audit__failed`); a human signed off all three closed to ND-A..ND-T.

## Task Commits

Each task was committed atomically (no trailer, on `feat/ui-2`):

1. **Task 1: Header + attribution + 6-stat grid + coverage banner + Export menu** — `b6fa1cbd` (feat)
2. **Task 2: Fuller category taxonomy + collapsible "What is this?" rows + group filters + integrity footer** — `237eb405` (feat)
3. **Harness: seed audit categories + failed variant; capture expanded + failed; register ND-R/S/T** — `7d563256` (test)
4. **Harness fix: target Audit expand click hits an entry, not the attribution row** — `2499cec1` (test)

_Task 3 (the human-verify checkpoint) added no code commit — it ran the capture automation and paused for the human sign-off._

## Files Created/Modified

- `frontend/src/components/results/AuditTab.tsx` — full reskin to the mock: header + Export ▾ menu, attribution + 6-stat compliance card, coverage chips + verdict banner, fuller `FineCategory` taxonomy (`deriveFineCategory`) + 3-state outcome (`deriveOutcome3`), collapsible `AuditRowCard` with "What is this?" + `detailRows`, group filter + blocked-only + search, integrity footer; optional additive `AuditRunMeta` prop. Retired the superseded severity-filter row, old row card, `VerdictChip`, `CounterPill`, `CATEGORY_META`, and the unused `counts` memo (INV-12).
- `frontend/src/components/results/__tests__/AuditTab.test.tsx` — re-anchored: export test opens the Export ▾ menu; the severity-filter test → group-filter / blocked-only / search / expand tests; added grid + green/red banner cases (15 tests).
- `frontend/e2e/fixtures/mockApi.ts` — seeded richer audit rows exercising every fine-category + a `setAuditVariant("failed")` blocked/denied/secrets-hit set (harness seeding for the capture, NOT fabricated production data).
- `frontend/e2e/tests/zzz-baseline.spec.ts` — capture `audit-expanded__settled` (expand an entry) + `audit__failed` (red variant, via `setAuditVariant`).
- `frontend/e2e/fidelity/capture-mocks.mjs` — expand the target settled Audit entry (match the entry HH:MM:SS timestamp, not the attribution row).
- `frontend/e2e/fidelity/assemble-gallery.mjs` — registered ND-R / ND-S / ND-T; caption range ND-A..ND-T.

_Note: `frontend/src/lib/exporters/auditExporter.ts` was in the plan's `files_modified` but was **reused unchanged** — the Export ▾ menu calls the existing `exportAuditCSV`/`exportAuditJSON` (INV-12)._

## Decisions Made

- **Presentation over the existing real fetches (D39-4/SC-001).** The Audit tab was already real (not a stub); this plan is the mock's composition + a fuller category mapping on top of `getRunGateEvents`/`getRunValidationResults`/`getRunExecRuns`, reusing the existing exporter. No backend, contract, or fetcher change.
- **Group filters replace the mock-absent severity buttons (ND-R).** The mock's filter row is All/Governance/Security/Activity + Blocked-only + Search — no severity control. Adopted exactly; the standalone CRITICAL/HIGH/MEDIUM/LOW filter buttons were retired (severity stays a per-row chip; blocked-only covers the "show me the problems" need).
- **Elide, never fabricate, unknown attribution (ND-S / T-39-04-01).** Owner/workspace are not in the owner-scoped audit fetches, so they are elided; Run id (truncated) + Started/Duration are live-derived. A later shell can thread the additive `AuditRunMeta` prop.
- **Static UI copy + derived coverage + no PDF (ND-T / ND-6).** The "What is this?" explainer is static per-category copy; coverage chips are derived per fine-category present (not the mock's fixed 7-word list); the Compliance-report export is disabled — CSV/JSON only.
- **Behavioral-hook derived from labels, not the deprecated hook_runs source.** D39-4 replaced `hook_runs`; behavioral rows are derived from gate/validation label signals so the tab stays on the three real fetches.

## Deviations from Plan

**None** — plan executed as written. Two mechanical clarifications inside scope (not scope deviations):

1. The plan's test path `AuditTab.test.tsx` is actually `__tests__/AuditTab.test.tsx` — edited the real file.
2. `auditExporter.ts` (listed in `files_modified`) needed no change — the Export ▾ menu reuses the existing exporter (INV-12), so it was left untouched.

## Issues Encountered

- **Target Audit expand click hit the attribution row.** The first `getByText(/Jul 4/)` in `capture-mocks.mjs` matched the mock's "Started Jul 4 2026" attribution, not an entry, so the target `audit-expanded__settled` shot didn't expand. Fixed by matching the entry meta's HH:MM:SS timestamp (the attribution shows only HH:MM UTC) — the target now expands a real entry (`2499cec1`).

## Verification

Honest, observed results (not presumed):

- `npx tsc --noEmit`: **clean** across the whole frontend (0 errors, incl. e2e).
- `npx vitest run src/components/results/__tests__/AuditTab.test.tsx`: **15/15 passed** (exporter cases + 3-endpoint reader + merged rows + grid + green-clean + red-blocked banner + group filter + blocked-only + search + expand).
- Banned mock-literal grep in `AuditTab.tsx` (`14.8M`/`f3a1c9`/`09:00:57`/`24m 6s`/`Behavioral guideline active — Quality Gate`): **0**. `getRunGateEvents` present (2).
- `FIDELITY_CAPTURE=1 npm run e2e -- zzz-baseline`: **5 passed** — current shots `audit__settled` / `audit-expanded__settled` / `audit__failed` produced and self-inspected.
- `capture-mocks.mjs` + `assemble-gallery.mjs --surface audit`: **3 paired sections** (settled / expanded / failed); the human signed off all three closed to ND-A..ND-T.
- Removed `sev-filter` testid references across `src/` + `e2e/`: **0**.

## Requirement Status

- **RUNUI-06** (SC-1, Audit matches its mock): the Audit surface half is delivered + human-approved; the requirement was already marked Complete in 39-01 (it spans all surfaces).
- **RUNUI-07** (SC-2, net-new affordances): its **fuller Audit categories** third landed here (secret-scan / performance / behavioral). RUNUI-07 stays **Pending** — Share, the Version ▾ menu, and the "Renders as" switch are 39-05/06.
- **RUNUI-08** (SC-3, live data): honored (all stats/rows from the real fetches; no cloned mock values) — already Complete in 39-01.

## Threat Flags

None — no new network endpoint, auth path, or trust-boundary surface. T-39-04-01 (attribution info-disclosure) mitigated by eliding owner/workspace the fetches don't return (ND-S). T-39-04-02 (XSS) — all row detail + the static explainer render through React JSX escaping; no `dangerouslySetInnerHTML` (grep 0).

## Known Stubs

None that block the plan's goal. The seeded audit rows in `mockApi.ts` (secret-scan / perf / behavioral categories + the failed variant) are **harness capture scaffolding**, not production data — a live run's Audit tab derives its categories from whatever the three real fetches recorded; empty categories show 0 and no rows (ND-D).

## Next Phase Readiness

- The Audit tab is done and human-approved across settled + failed; the fidelity oracle + gallery are ready.
- **39-05 (run header — Version ▾ / Share / Download + tab order + shell wiring)** is next; it may thread the additive `AuditRunMeta` prop to surface live owner/workspace in the attribution row (currently elided per ND-S).
- **Concern (inherited):** the broader mocked e2e suite is still systemically stale against the feat/ui-2 redesign (D-39-07-1) — this plan re-anchored only the Audit surface's specs (the vitest + the `zzz-baseline` capture), per the per-surface re-anchor decision.

## Self-Check: PASSED

- `AuditTab.tsx` + `__tests__/AuditTab.test.tsx` present and modified; `mockApi.ts` / `zzz-baseline.spec.ts` / `capture-mocks.mjs` / `assemble-gallery.mjs` present and modified.
- All task commits verified in git: `b6fa1cbd`, `237eb405`, `7d563256`, `2499cec1`.
- Verification observed: tsc clean, vitest 15/15, fidelity capture 5, gallery = 3 paired audit sections (human-approved).

---
*Phase: 39-run-screen-mock-fidelity-b5*
*Completed: 2026-07-11*
