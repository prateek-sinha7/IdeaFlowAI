---
phase: 32-run-screen-redesign-a4
plan: 09
subsystem: ui
tags: [react, audit, governance, csv-export, json-export, tokens, sc-3, nd-6, idor]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4 (plan 03)
    provides: the 3 owner-scoped audit endpoints (GET /api/runs/{id}/gate-events, /validation-results, /exec-runs) with IDOR->404 two-layer owner gate
  - phase: 32-run-screen-redesign-a4 (plan 01)
    provides: the token layer (status ramp + severity ladder + radius/ink/surface/line tokens) consumed here
provides:
  - Three typed client fetchers (getRunGateEvents/getRunValidationResults/getRunExecRuns) that map 404 -> empty envelope
  - auditExporter util (exportAuditCSV / exportAuditJSON) — client-side blob download only (ND-6)
  - AuditTab repointed off hook_runs onto the 3 endpoints, with counters/coverage chips/severity filters + export
affects: [34 (live milestone-end verification pass), run-screen audit UX]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "404-aware client fetchers: a cross-owner/missing run resolves to an EMPTY typed envelope (never a foreign row) — the tab's info-disclosure mitigation (T-32-09-01)"
    - "CSV export escaping: quote-wrap + double-internal-quote for commas/quotes/newlines PLUS a formula-injection guard (leading =,+,-,@ -> single-quote prefix) so a cell cannot break structure or execute (T-32-09-03)"
    - "Governance one-chroma exception: verdict/severity chips consume the status-ramp + severity-ladder tokens; every other surface stays on the token layer (SC-1)"

key-files:
  created:
    - frontend/src/lib/exporters/auditExporter.ts
    - frontend/src/components/results/__tests__/AuditTab.test.tsx
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/components/results/AuditTab.tsx

key-decisions:
  - "Kept the `hookRuns?` prop on AuditTabProps as a DORMANT (unconsumed) legacy prop so the PreviewPanel mount signature is unchanged — the guardrail mandates PreviewPanel mount untouched, and removing the prop would break tsc at PreviewPanel.tsx:941. The tab derives 100% of its data from the 3 endpoints."
  - "Fetchers map 404 -> empty envelope at the client seam (not in the tab) so every consumer of these fetchers is IDOR-safe by construction; other errors rethrow."
  - "Rendered verdict chips (gate/exec) via a status-ramp chip and validation severity via severity-ladder vars — these are the ONLY green/amber/red usages; everything else uses ink/surface/line/radius tokens + primitives."
  - "Added a formula-injection guard (=,+,-,@ leads) to the CSV escaper in addition to the required structural escaping — CSV injection is the named threat (T-32-09-03)."

patterns-established:
  - "Pattern: owner-scoped audit fetcher returns an empty typed envelope on 404 so the UI renders gracefully and never surfaces another owner's data"
  - "Pattern: client-side CSV export escapes structurally AND neutralizes spreadsheet formula-injection leads"

requirements-completed: [SC-3]

# Metrics
duration: ~18min
completed: 2026-07-08
---

# Phase 32 Plan 09: Audit-Tab Repoint + Client-Side Export Summary

**AuditTab reads the 3 owner-scoped plan-03 endpoints (gate-events / validation-results / exec-runs) instead of the wrong hook_runs source, with client-side stat counters / coverage chips / severity filters and CSV/JSON blob export (ND-6), all tokenized except the governance status/severity palette.**

## Performance

- **Duration:** ~18 min
- **Completed:** 2026-07-08
- **Tasks:** 3 (2 of them TDD RED->GREEN)
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- Three typed 404-aware client fetchers on `lib/api.ts` targeting the plan-03 endpoints; a cross-owner/missing run resolves to an empty envelope (never a foreign row, T-32-09-01).
- `auditExporter.ts` — `exportAuditCSV` / `exportAuditJSON` client-side blob downloads; CSV escapes commas/quotes/newlines and neutralizes formula-injection leads; no PDF, no backend export route (ND-6, grep 0).
- `AuditTab.tsx` repointed off `getRunHookRuns`/`hook_runs` (grep 0) onto the 3 endpoints, merging into a unified row model with per-category coverage chips, governance/exec verdict counters, severity filters that narrow the rendered rows, and Export CSV/JSON buttons over the current (filtered) rows.
- Tokenized every surface/line/ink/radius via the plan-01 tokens + primitives; the governance status palette (green/amber/red) is the sole one-chroma exception on verdict/severity chips.

## Task Commits

1. **Task 1: 3 owner-scoped audit-endpoint client fetchers** — `947fdfde` (feat)
2. **Task 2 (TDD): auditExporter CSV/JSON util** — `c0f3c89e` (test RED) → `6cd31271` (feat GREEN)
3. **Task 3 (TDD): AuditTab repoint + counters/filters/export** — `6cb80af4` (test RED) → `05d4ae1d` (feat GREEN)

_TDD gates: exporter RED committed with "no tests" (import fails on missing module) then GREEN 5/5; AuditTab RED committed failing 5/5 (tab still called getRunHookRuns) then GREEN 10/10._

## Files Created/Modified
- `frontend/src/lib/api.ts` — added `GateEventRow`/`ValidationResultRow`/`ExecRunRow` + response types and `getRunGateEvents`/`getRunValidationResults`/`getRunExecRuns` fetchers (404 → empty envelope). `getRunHookRuns` left untouched (still used by nothing here; not deleted — out of scope).
- `frontend/src/lib/exporters/auditExporter.ts` — created; `exportAuditCSV`/`exportAuditJSON` blob-download util mirroring `prototypeExporter`, with union-of-keys header, structural CSV escaping, and formula-injection guard.
- `frontend/src/components/results/AuditTab.tsx` — rewritten to read the 3 endpoints, normalize into a unified `AuditRow` model, render coverage chips/counters/severity filters + export bar, tokenized with the governance-palette exception. `hookRuns?` prop retained dormant for mount compat.
- `frontend/src/components/results/__tests__/AuditTab.test.tsx` — created; 5 exporter specs (JSON pretty-print, CSV header+rows, escaping, formula-injection, no-fetch) + 5 AuditTab specs (3-endpoint read not getRunHookRuns, merged render, severity filter narrows, export invokes util, graceful empty on 404).

## Decisions Made
- **`hookRuns?` prop kept dormant** so the PreviewPanel mount (`hookRuns` + `workflowRunId`) compiles unchanged (guardrail: PreviewPanel mount untouched). The tab no longer consumes it — all data comes from the 3 endpoints.
- **404 handled at the fetcher seam** (→ empty envelope), making every fetcher caller IDOR-safe by construction; the tab additionally shows a graceful empty state.
- **Formula-injection guard added to CSV** on top of the required structural escaping — the threat register names CSV injection (T-32-09-03) as the tampering vector.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] CSV formula-injection neutralization**
- **Found during:** Task 2 (auditExporter)
- **Issue:** Structural quote-wrap escaping alone does not stop spreadsheet formula injection (a cell like `=cmd()` is still evaluated on open) — the named tampering threat T-32-09-03.
- **Fix:** Prefix any cell whose first char is `=`, `+`, `-`, `@` (or a control char) with a single quote before structural escaping.
- **Files modified:** frontend/src/lib/exporters/auditExporter.ts
- **Verification:** Dedicated test asserts `'=cmd()`, `'+1`, `'-2`, `'@x` in the output; 5/5 exporter tests green.
- **Committed in:** `6cd31271` (Task 2 GREEN)

---

**Total deviations:** 1 auto-fixed (1 missing-critical security hardening)
**Impact on plan:** The guard strengthens the explicitly-named CSV-injection mitigation. No scope creep.

## Issues Encountered
None — the plan executed as written; the exporter tests + AuditTab tests share one file (`AuditTab.test.tsx`) per the plan's `<files>` field, so the exporter suite imports the real util while the AuditTab suite spies on it (no module mock conflict).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- SC-3 tab+export half complete: the Audit tab reads the 3 owner-scoped endpoints, renders counters/coverage chips/severity filters, exports CSV/JSON client-side (no PDF/backend route), and keeps the governance palette as the sole one-chroma exception.
- Live end-to-end verification (real Bedrock run populating gate_events/validation_results/exec_runs, then reopening the Audit tab) is deferred to the Phase 34 milestone-end live pass — offline vitest covers the read/merge/filter/export/empty-404 contract.
- No blockers.

---
*Phase: 32-run-screen-redesign-a4*
*Completed: 2026-07-08*

## Self-Check: PASSED

- api.ts, auditExporter.ts, AuditTab.tsx, AuditTab.test.tsx, 32-09-SUMMARY.md all present on disk
- Task commits 947fdfde + c0f3c89e + 6cd31271 + 6cb80af4 + 05d4ae1d all present in git log
- Verified offline: AuditTab.test.tsx 10/10 green; tsc identity 0 (grep -v mockApi.ts); getRunHookRuns in AuditTab = 0; ND-6 grep (pdf/api-export) in auditExporter = 0; preview+results delta 97/97 green
