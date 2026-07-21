---
phase: 40-shell-mock-fidelity-restyle-b6
plan: 06
subsystem: frontend-shell
tags: [ui-fidelity, history, restyle, shell-mock, revision-families]
requires: ["40-01"]
provides: ["Run History surface at mock parity — type-filter chips + Sort tabs (Newest/Longest/Tokens) + TODAY/EARLIER THIS WEEK/OLDER date groups, with per-row token count + elapsed, purple version chip, and always-visible kebab, all over live/seeded /api/runs data"]
affects:
  - frontend/src/components/history/WorkflowHistory.tsx
  - frontend/src/components/history/RevisionFamilyView.tsx
tech-stack:
  added: []
  patterns:
    - "styling/label parity restyle over unchanged /api/runs (INV-12 — family grouping, sort, search, delete, revision behaviour preserved)"
    - "row-level fidelity via presentation-only fields already on each list row (tokenUsage.total_tokens, created_at, duration) — no extra fetch, ND-D never-fabricate"
key-files:
  created: []
  modified:
    - frontend/src/components/history/WorkflowHistory.tsx
    - frontend/src/components/history/RevisionFamilyView.tsx
    - frontend/src/components/history/WorkflowHistory.test.tsx
    - frontend/src/components/history/WorkflowHistory.grouping.test.tsx
    - frontend/e2e/tests/ts-t.history.spec.ts
decisions:
  - "The title stays 'Run History' (ND-W — matches the profile-menu label), not the mock's 'Workflow History'."
  - "All rows are live/seeded /api/runs data (ND-D), never the mock's fixed 9-run list; family grouping + the tokens/duration sort behaviour is preserved."
  - "Row-level fidelity fix (user-ruled 'fix now' at Batch-B closeout): RevisionFamilyView's FamilyGroupCard rows are consumed ONLY by WorkflowHistory (grep-verified — RunDetailPage imports only VersionTimeline, ZERO run-screen importers), so the row restyle is history-scoped with no run-screen regression risk."
metrics:
  duration: ~40m
  completed: 2026-07-12
---

# Phase 40 Plan 06: Run History Parity Summary

Brought the History surface to visual parity with the `Hexaware Workspace v2.dc.html` History surface — a chip / Sort-tab / date-group / badge restyle over the *unchanged* live/seeded `/api/runs` data, keeping the app title "Run History" (ND-W). A trailing, human-ruled row-level fidelity fix (in the `RevisionFamilyView` family-card rows) added the mock's per-row token count + elapsed, the purple version chip, and an always-visible kebab.

## What changed

- **WorkflowHistory restyle (commit `552e0673`):** the type-filter chips, the Sort segmented control, the TODAY / EARLIER / OLDER date-group headers (uppercase label + faded count + hairline rule), the status badges, and the three states (populated / filter-empty / zero) aligned to the mock over live `/api/runs`. The family grouping, sort, search, delete, and revision behaviour are preserved (INV-12). `ts-t.history` re-anchored to the restyled surface.
- **Row-level fidelity fix + chrome tweaks (Batch-B closeout, this commit):**
  - `RevisionFamilyView.tsx` — the `FamilyGroupCard` rows now render the mock's right-side composition:
    - a **token count + elapsed** column (`formatTokenCount(tokenUsage.total_tokens)` over the relative `created_at`) via a new `RowStats` helper — both from fields already on the row, no extra fetch; ND-D omits the token line when the run carries no usage datum (never a fake "0").
    - the multi-member family's version affordance is now the mock's **purple pill + chevron** (`bg-brand-fill` / `text-brand` = the mock's `#ECEAFC` / `#3C2CDA`), merging the former grey `v{N}` count-pill and the separate chevron toggle into the single control the mock shows. The inner span keeps the `"{N} versions"` a11y label; the button keeps the `Show/Collapse versions` toggle label + `aria-expanded`.
    - the **kebab** (`⋮` Run-actions menu) is now always visible (removed the `opacity-0 group-hover` reveal), keeping the CRUD/reopen/delete contract + aria.
    - the single-member row's decorative trailing chevron is removed and the sub-line trimmed to `type · duration` (the relative date moved into the RowStats column), matching the mock row.
  - `WorkflowHistory.tsx` — Sort labels aligned to the mock (**Newest / Longest / Tokens**, in the mock's order) while the sort KEYS + the `Sort by {key}` aria-labels stay stable (behaviour + a11y contract unchanged); the "Earlier" bucket header reads **"Earlier this week"** (→ "EARLIER THIS WEEK" uppercased) while the `bucket` enum + section aria-label stay Today/Earlier/Older; the active filter-chip fill moved from app-purple to the mock's near-black (`bg-ink-900` = `#15161A`).

## Intended-Divergence register touch

- **ND-W** — the title stays "Run History", not the mock's "Workflow History".
- **ND-D** — every row is live/seeded `/api/runs` data (token counts, durations, statuses, version counts differ from the mock's fixed 9-run list); the token line is omitted for a run with no metered usage rather than fabricating a count.

## Regenerated gallery (`--surface history`)

2 pairs regenerated into `frontend/e2e/fidelity/gallery-shell.html`: `history__shell`, `history__shellfull`. Current side refreshed via `SHELL_CAPTURE=1 npx playwright test --project=mocked zzz-shell-baseline`; assembled via `assemble-shell-gallery.mjs --surface history`. Post-fix eyeball vs `target/history__shell.png`: the rows now show the token count over the relative time on the right, the purple `v2 ›` version chip, and the always-visible `⋮` kebab; the Sort tabs read Newest / Longest / Tokens; the buckets read TODAY / EARLIER THIS WEEK / OLDER; the active filter chip is near-black.

## Verification results

- `npx tsc --noEmit` — 0 errors.
- `npx vitest run` on the history suite — 40/40 green across WorkflowHistory.test / .grouping / .family / .genericReopen / .revise / .runInput and RunDetailPage.test. Both `RevisionFamilyView` consumers verified non-regressing: `WorkflowHistory` (family cards) and `RunDetailPage` (VersionTimeline) tests all pass; the `getByLabelText("N versions")` + `getByLabelText("Show versions")` a11y contracts hold across the merged purple pill.
- `npx playwright test --project=mocked ts-t.history` — 5/5 green (incl. TS-T-06 delete via the now-always-visible kebab).
- `ts-z.catalog` + `ts-z2.saved-workflows` (mocked) — 5/5 green (no cross-surface regression).

## Deviations from Plan

**1. [Rule 1 — Fidelity bug] History rows missing the mock's token/elapsed + purple version chip + persistent kebab (user-ruled "fix now")**
- **Found during:** Batch-B closeout eyeballing (`current/history__shell.png` vs `target/`).
- **Issue:** family-card rows showed a plain grey `v{N}` pill, a hover-hidden kebab, and no per-row token/elapsed figures.
- **Fix:** added the `RowStats` token+elapsed column, made the version chip the mock's purple pill+chevron toggle, made the kebab always-visible, and aligned the Sort labels + bucket copy + active-chip fill.
- **Files modified:** `RevisionFamilyView.tsx`, `WorkflowHistory.tsx` (+ `WorkflowHistory.grouping.test.tsx` bucket-copy assertion updated to "Earlier this week").
- **Commit:** this plan's `feat(40)` row-fidelity commit.

## Known Stubs

None. All rows bind to live/seeded `/api/runs`. The token line is intentionally omitted for runs with no metered usage (ND-D), not a stub.

## Checkpoint

The History surface (commit `552e0673`) was handed to the human reviewer at the plan's blocking `checkpoint:human-verify` and **approved**. The trailing row-level fidelity fix was a user-ruled "fix now" applied at the Batch-B closeout over that approval, re-captured and re-eyeballed against the mock.
