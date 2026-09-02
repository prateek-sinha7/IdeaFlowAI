# Domain 9 — frontend·history — Run Report
**Date:** 2026-09-02T11:00:00Z  
**Cards:** 13  **Batches:** 1  **Rounds:** 1

---

## Summary

| Outcome | Cards |
|---------|-------|
| FIXED (new FIX cards) | 6 (ISS-198, ISS-207, ISS-208, ISS-209, ISS-213 → FIX-466; ISS-414 → FIX-467) |
| PARTIAL (open, linked) | 1 (ISS-219 — units decision partially resolved, chip units mismatch remains) |
| ESCALATED | 2 (ISS-325, ISS-629 — human decisions required) |
| SECONDARY GLOB / no fix needed in WorkflowHistory.tsx | 4 (ISS-077, ISS-113, ISS-145, ISS-412) |

**Verification:** tsc --noEmit 0 errors. vitest WorkflowHistory.test.tsx 13/13 passed (--maxWorkers=1).  
**Dedup regenerated:** 144 open → 139 units (6 resolved cards dropped).

---

## Round 1

### Batch B1 — `frontend/src/components/history/WorkflowHistory.tsx` [sonnet]

All 13 cards, 1 fix site, 1 read, 1 tsc + vitest verify.

| Card | Outcome | FIX |
|------|---------|-----|
| ISS-198 | FIXED | FIX-466 |
| ISS-207 | FIXED | FIX-466 |
| ISS-208 | FIXED | FIX-466 |
| ISS-209 | FIXED | FIX-466 |
| ISS-213 | FIXED | FIX-466 |
| ISS-414 | FIXED | FIX-467 |
| ISS-219 | PARTIAL | linked to FIX-466 (see below) |
| ISS-325 | ESCALATED | see below |
| ISS-629 | ESCALATED | see below |
| ISS-077 | NO CHANGE | secondary glob; primary fix site is `frontend/src/lib/api.ts` |
| ISS-113 | NO CHANGE | secondary glob; primary fix site is `AuditTab.tsx` |
| ISS-145 | NO CHANGE | secondary glob; stale-baseline informational card |
| ISS-412 | NO CHANGE | secondary glob; primary fix site is `AppBuilderPreview.tsx` (fixed in domain 5) |

---

## Fix narratives

### FIX-466 — Pagination restored (ISS-198/207/208/209/213)

Root: `handleLoadMore` was fully implemented but had zero call sites — dead code since commit `ce08bf542` ("Revert merge staging into dev", 2026-08-17) collaterally deleted the Load More footer. The component already held `totalRuns` from the API's `X-Total-Count` but never displayed or acted on it.

Five changes in `WorkflowHistory.tsx`:

1. **Header text** `{runs.length} runs` → `{totalRuns} runs` (ISS-198).
2. **All chip** `typeCounts.all = families.length` → `typeCounts.all = totalRuns` (ISS-198 / ISS-219 option 2).
3. **IntersectionObserver** sentinel div at bottom of list — fires `handleLoadMore` when scrolled into view; shows a `Loader2` spinner while `loadingMore` is true; hidden when `runs.length >= totalRuns` (ISS-198).
4. **`handleDeleteConfirm`** now calls `setTotalRuns(prev => Math.max(0, prev - 1))` after the optimistic `setRuns` filter, keeping offset bookkeeping correct for future Load More calls (ISS-209).
5. **Partial-scope affordance** `"Showing X of Y runs — scroll down to load more"` shown below the search input when `runs.length < totalRuns`, making the scope of search/sort/chips explicit (ISS-207/208/213).

ISS-219 is partially resolved: the header now shows run counts. The per-type chip counts still reflect family-card counts from the loaded window (not true per-type aggregates); fixing that fully requires a backend `list_runs` per-type count aggregate, which is a future change.

### FIX-467 — Delete dialog names the run (ISS-414, replicate FIX-372)

Replaced `const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)` with `const [deleteRow, setDeleteRow] = useState<WorkflowRun | null>(null)` — same FIX-372 shape applied to this component. `handleDeleteClick` now stores the whole run row; `DeleteModal` gained a `runName?: string` prop that interpolates the run title into the body text: `"${name}" and all its output will be permanently deleted.`

---

## Escalations

### ISS-325 — S-21-05 test premise broke (ESCALATED)
`test_the_family_counts_as_one_against_a_filter_chip` in `suites/21_run_families_and_versions/` times out on `^Presentation\s*\d` chip. The test's own docstring scopes its assertion to "every family size 1" — a premise the seed data has already broken (a genuine 2-member family exists). The docstring says "the day they diverge, write S-21-01." **Human action needed:** write S-21-01 or re-baseline the test at the pre-change SHA.

### ISS-629 — Spec S-21-07/08/09 contradicts the app (ESCALATED)
`21-run-families-and-versions.feature.md` S-21-07 requires a "Workflow versions" region on `/runs/{id}` — that region is `VersionTimeline`, rendered only by `RunDetailPage`. But `WorkflowHistory.handleSelectRun` routes every tap to `onOpenRun` (the shared run screen), making the internal detail unreachable. The card states: "Nobody should write code until [the spec contradiction] is answered." **Human action needed:** either rewrite S-21-07/08/09 against the Version menu (already covered by ISS-230/296/607 tests) or finish INV-3 and mount one surface.

---

## Verification (observed)

```
tsc --noEmit (frontend/):
  EXIT_CODE=0, 0 errors

vitest WorkflowHistory.test.tsx (--maxWorkers=1):
  13/13 passed, EXIT_CODE=0, 99.10s
  Note: --maxWorkers=3 caused a pre-existing forks-pool worker timeout on this
  Windows machine (ISS-145 pre-existing). Single-worker run is clean.

Knowledge rebuild (--skip-architecture):
  Stage 1 index: 1150 cards indexed, INDEX.md + state.yaml updated, 16 card cross-refs updated
  Stage 2 context: FAILED — pre-existing UnicodeDecodeError cp1252 0x90 in MOD-*.md
  Stage 3 validate_links: 9 broken links, all pre-existing in MOD-backend.md (.venv312 paths)

Dedup regenerated: 144 → 139 units
  ISS-198, ISS-207, ISS-208, ISS-209, ISS-213, ISS-414 no longer in open backlog ✓
```

---

## Cards created this run

| Type | ID | Title |
|------|----|-------|
| FIX | FIX-466 | Pagination restored (5 ISS) |
| FIX | FIX-467 | Delete dialog names run (ISS-414) |

---

## Invariants checked

- **SC-001 / INV-1:** no `if pipeline_type ==` / `spec.id ==` under `backend/agents/execution_engine/` — confirmed, no backend edits.
- **Import-linter:** no backend/ edit, contracts unaffected.
- **Migrations additive only:** no migration.
- **INV-3 goldens:** no backend/python change, no golden touched.

---

## Pre-existing issues found (not ours)

- `build_context.py` stage 2 UnicodeDecodeError cp1252 0x90 — pre-existing, documented in DISPATCH.md.
- 9 broken links in MOD-backend.md pointing to .venv312/ paths — pre-existing.
- vitest forks-pool worker timeout at --maxWorkers=3 on Windows — pre-existing (ISS-145).

---

## Ready to commit

### Files changed this domain

```
frontend/src/components/history/WorkflowHistory.tsx
.knowledge/cards/20260902-1100-FIX-466.md  (new)
.knowledge/cards/20260902-1100-FIX-467.md  (new)
.knowledge/cards/20260828-1400-ISS-198.md  (status: resolved)
.knowledge/cards/20260828-1617-ISS-207.md  (status: resolved)
.knowledge/cards/20260828-1617-ISS-208.md  (status: resolved)
.knowledge/cards/20260828-1617-ISS-209.md  (status: resolved)
.knowledge/cards/20260828-1618-ISS-213.md  (status: resolved)
.knowledge/cards/20260828-1706-ISS-219.md  (last_updated + FIX-466 partial link)
.knowledge/cards/20260828-2202-ISS-414.md  (status: resolved)
.knowledge/INDEX.md  (rebuilt)
.knowledge/state.yaml  (rebuilt)
bug-hunter/OPEN-ISSUES-DEDUP.md  (regenerated)
.kiro/bug-fix-workflow/STATE.md  (updated)
.kiro/bug-fix-workflow/reports/20260902-1100-domain-09-frontend-history.md  (new)
```

### Suggested commit message

```
fix(history): restore pagination, wire Load More, name delete dialog

ISS-198: header now shows totalRuns not runs.length; typeCounts.all uses
totalRuns; IntersectionObserver sentinel wires handleLoadMore on scroll.
ISS-207/208/213: partial-scope affordance when list is capped.
ISS-209: handleDeleteConfirm decrements totalRuns to keep offset in sync.
ISS-414: deleteRow stores full run row so DeleteModal can name the run
(replicates FIX-372/SavedWorkflowsPage).

tsc: 0 errors. vitest 13/13.
```

---

## Needs a human

- **ISS-325** — write S-21-01 or re-baseline `test_the_family_counts_as_one_against_a_filter_chip`
- **ISS-629** — decide: rewrite S-21-07/08/09 against Version menu OR finish INV-3
- **ISS-219** — per-type chip counts still use family-card units from the loaded window; full fix requires a backend per-type aggregate (option 3 from ISS-198's Fix location)
- **xfail markers** in `tests/integration/e2e/suites/06_run_history/test_run_history_pagination.py` — 5 tests carry `@pytest.mark.xfail(strict=True)`; once live servers confirm XPASS, remove the markers in a follow-up verify pass

---

## UNEXPECTED_CHANGES

None — only WorkflowHistory.tsx was edited in application source.
