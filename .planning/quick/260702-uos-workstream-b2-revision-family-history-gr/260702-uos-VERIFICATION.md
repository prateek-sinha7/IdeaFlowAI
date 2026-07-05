---
phase: 260702-uos
verified: 2026-07-02T22:35:00Z
status: gaps_found
score: 7/7 plan truths verified — but a blocking cross-suite regression violates the "zero regression" contract
overrides_applied: 0
gaps:
  - truth: "Zero regression — existing WorkflowHistory tests still pass (truth #1 'zero regression' clause + the mandated B1/regression-spec regression guard)."
    status: failed
    reason: >
      The new detail-view useEffect adds getRunFamily(token, selectedRun.rootRunId) at
      WorkflowHistory.tsx:191. Three PRE-EXISTING, UNTOUCHED test files mock @/lib/api but
      do NOT export getRunFamily. When they open a run detail (which they do to test
      revise/reopen flows) the useEffect fires and vitest hard-throws
      "No 'getRunFamily' export is defined on the '@/lib/api' mock", crashing render.
      PROVEN by bisect: against pre-B2 WorkflowHistory.tsx (commit 260c4dd6) all 18 tests
      in the 3 files PASS; against current HEAD all 18 FAIL. This is a regression B2
      introduced. Production is unaffected (real getRunFamily export exists + .catch guard),
      but the existing test suite is now red and the SUMMARY's "zero regression" +
      "Self-Check: PASSED" are false for these files.
    artifacts:
      - path: "frontend/src/components/history/WorkflowHistory.revise.test.tsx"
        issue: "vi.mock('@/lib/api') omits getRunFamily → all specs throw on detail open. 18 combined failures across the 3 files."
      - path: "frontend/src/components/history/WorkflowHistory.test.tsx"
        issue: "Same missing getRunFamily mock export."
      - path: "frontend/src/components/history/WorkflowHistory.genericReopen.test.tsx"
        issue: "Same missing getRunFamily mock export."
    missing:
      - "Add `getRunFamily: (token, id) => mockGetRunFamily(token, id)` (with a `const mockGetRunFamily = vi.fn(...)` returning a benign RunFamily or resolving null-safe) to the @/lib/api vi.mock in all 3 pre-existing test files — mirroring what WorkflowHistory.family.test.tsx already does at line 25 — then confirm all 3 files return to green."
deferred: []
---

# Phase 260702-uos: Workstream B2 — Revision-family history grouping + detail version timeline — Verification Report

**Phase Goal:** FE, POR §5 deliverables 3+4 per WORKSTREAM-B-UI-SPEC.md — (3) history list grouped by rootRunId into family cards; (4) detail version-timeline radiogroup chips with getWorkflow switch + AnimatePresence cross-fade. Frontend-only, reuse-first.
**Verified:** 2026-07-02T22:35:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Multi-run family → ONE root card w/ `v{N}` pill + latest status; single-run/legacy-NULL-parent → plain row, no pill/expander | ✓ VERIFIED | `groupRunsByFamily` buckets by `rootRunId`, sorts createdAt ASC, root = `id===rootRunId`, latest = last (RevisionFamilyView.tsx:104-129). `FamilyGroupCard` `isMulti = members.length>=2` branches: single-member renders exact flat row no pill/chevron (230-263); multi renders `v{N}` pill (297-302) + latest StatusBadge (303). Family test 1 (`getByLabelText("3 versions")` + plain "Solo run") + test 2 (single-member: no "Show versions", no "N versions" pill) — both green. |
| 2 | Expanding a family → chronological version rows with "↳ revises v{n}" microcopy | ✓ VERIFIED | Expanded child rows map members v1..vN (RevisionFamilyView.tsx:320-346); `revisesN` = 1-based parent index via `findIndex(id===parentRunId)` fallback `i-1` (325-326); "↳ revises v{n}" span at 339-341. Test 1 asserts `↳ revises v1` (r1→root=v1) and `↳ revises v2` (r2→r1=v2) after expand — green. |
| 3 | Detail version-timeline chip row only when family >=2 members; role=radiogroup, chips role=radio + aria-checked, active chip matches open version | ✓ VERIFIED | `VersionTimeline` returns null when `!family \|\| members.length<2` (414); container `role="radiogroup"` (442); chips `role="radio"` `aria-checked={isActive}` `tabIndex` roving (453-456). Wired above tab bar in WorkflowHistory.tsx:623-628 (before tab-bar div :630). Tests 3 & 5 assert 3 radios, active = 3rd (loaded latest), radiogroup present — green. |
| 4 | Clicking a chip → getWorkflow(memberId) into same surface, AnimatePresence mode="wait" cross-fade keyed selectedRun.id, active chip follows | ✓ VERIFIED | `handleSelectVersion` calls `getWorkflow(token, memberId)` → `setSelectedRun` (WorkflowHistory.tsx:201-211, tab-preserving). Content wrapped `<AnimatePresence mode="wait"><motion.div key={selectedRun.id} .../>` (692-699). Test 4 (id-keyed mock) asserts getWorkflow called with "root" and active chip moves to v1 — green. |
| 5 | Revision version shows "↳ Revises v{n-1} — {preview}"; root shows none | ✓ VERIFIED | Context line rendered only when `activeMember.parent_run_id` truthy (RevisionFamilyView.tsx:471-475), preview from `extractRevisionInstructionPreview(activeInput)`. Test 3 asserts `make the header blue` from `=== REVISION REQUEST ===\nmake the header blue` — green. Root (null parent) → no line. |
| 6 | Chip row keyboard-navigable radiogroup (Arrow nav + managed focus) | ✓ VERIFIED | `handleKeyDown` Arrow L/U prev, R/D next (clamped), Enter/Space activate (421-433); managed focus via `chipRefs` + `userSwitched` ref, focuses active chip only after user switch in useEffect keyed on activeRunId (392-411). Test 5 confirms radiogroup + radio/aria-checked. |
| 7 | Zero backend files changed; type-filter tabs count each family once per base type | ✓ VERIFIED | `git diff --name-only 260c4dd6..HEAD -- backend/` empty. `typeCounts` iterates families, `baseWorkflowType(g.root.type)`, `all = families.length` (WorkflowHistory.tsx:826-830). |

**Score:** 7/7 plan truths verified in isolation — HOWEVER a cross-suite regression (below) violates truth #1's "zero regression" clause and the mandate's explicit regression guard → overall gaps_found.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `RevisionFamilyView.tsx` | groupRunsByFamily, FamilyGroupCard, VersionTimeline, extractRevisionInstructionPreview, statusDotClass | ✓ VERIFIED | 478 lines, all exports present + substantive; INV-12 shim comment (351-354); imported by WorkflowHistory.tsx:37. |
| `WorkflowHistory.tsx` | Grouped list + detail timeline wiring | ✓ VERIFIED | groupRunsByFamily render (823-953), getRunFamily fetch (186-196), handleSelectVersion (201-211), AnimatePresence mode="wait" (692). |
| `WorkflowHistory.family.test.tsx` | 5 real-DOM behavior specs | ✓ VERIFIED | 5 specs, real rendered-DOM asserts (not source-lock), all green. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| WorkflowHistory list view | groupRunsByFamily → FamilyGroupCard | client-side grouping by rootRunId | ✓ WIRED | :823-824, :940-951 |
| WorkflowHistory detail | getRunFamily(token, rootRunId) | useEffect keyed rootRunId → family state | ✓ WIRED | :186-196 (cancellable, stable key) |
| VersionTimeline chip | handleSelectVersion → getWorkflow(token, memberId) | onSelectVersion callback | ✓ WIRED | :201-211, :627 |
| detail content region | AnimatePresence mode="wait" keyed selectedRun.id | cross-fade all tabs | ✓ WIRED | :692-699 |
| FamilyGroupCard | openMenuId/onToggleMenu/onDeleteClick (W1) | delete menu threaded; DeleteModal stays in parent | ✓ WIRED | RowMenu (RevisionFamilyView.tsx:169-206) threaded :259,:304; DeleteModal remains WorkflowHistory.tsx:958-959 |

### Folded-in Fix Verification (W1/W2/W3/I1)

| Fix | Requirement | Status | Evidence |
|-----|-------------|--------|----------|
| W1 | Single-member row keeps delete menu; props threaded; DeleteModal stays in WorkflowHistory | ✓ VERIFIED | RowMenu with Trash2/Delete (RevisionFamilyView.tsx:195-200), threaded on both single (259) and multi (304) rows; handleDeleteClick + DeleteModal intact in WorkflowHistory (213-217, 958-959). Delete-from-history NOT dropped. |
| W2 | Chevron uses controlled `${expanded ? "rotate-90":""}`, NOT group-open | ✓ VERIFIED | Controlled ternary at RevisionFamilyView.tsx:313. `group-open` ABSENT from FamilyGroupCard (only appears in a comment :305 and in a pre-existing native `<details class="group">`/`<summary>` at WorkflowHistory.tsx:499 — correct, unrelated to B2). |
| W3 | Defensive v{N} window-count note | ✓ VERIFIED | `versionCount = group.members.length` + POR §11 comment (RevisionFamilyView.tsx:270-273). |
| I1 | Version-switch test uses id-keyed mockGetWorkflow (non-vacuous) | ✓ VERIFIED | `mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve(byId[id]))` (family.test.tsx:194-195) → active chip follow is a REAL assertion. |

### Reuse-First Spot-Checks (truth #7 / INV-12)

| Node | Class | UI-SPEC analog | Status |
|------|-------|----------------|--------|
| v{N} pill | `text-[9px] font-semibold px-1 rounded bg-gray-200 text-gray-500` | filter-count-pill WorkflowHistory.tsx:806 | ✓ inherited |
| active chip fill | `bg-[#1B2A4A] text-white` | accent fill (also used :661 Download btn) | ✓ inherited |
| chip shape | `text-[11px] font-medium px-3 py-1.5 rounded-md` | detail-tab button :636 | ✓ inherited |
| status dot | `w-1.5 h-1.5 rounded-full bg-emerald/amber/gray/blue-400` | Sidebar semantic map | ✓ inherited |
| extractRevisionInstructionPreview | preview-only slice shim, ≤60 chars | INV-12 Workstream-C hand-off comment (351-354) | ✓ shim, not a 2nd parser |

No invented hex/radii/font-sizes found.

### Behavioral Spot-Checks / Gate Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| tsc — no new errors in touched files | `npx tsc --noEmit \| grep "error TS"` | Exactly 3 errors: mockApi.ts(95,21) TS2352, mockApi.ts(96,22) TS2352, IdeaInputPage.tsx(738,9) TS17001 — all in UNTOUCHED files. Zero in RevisionFamilyView.tsx / WorkflowHistory.tsx / family.test.tsx | ✓ PASS |
| new family specs | `npx vitest run …WorkflowHistory.family.test.tsx` | Test Files 1 passed; Tests 5 passed | ✓ PASS (5/5) |
| regression guard (B1 revise + list + reopen) | `npx vitest run …revise.test.tsx …test.tsx …genericReopen.test.tsx` | Test Files 3 failed; Tests 18 failed — "No 'getRunFamily' export is defined on the '@/lib/api' mock" at WorkflowHistory.tsx:191 | ✗ FAIL (0/18) |
| regression bisect (pre-B2 control) | same 3 files vs `260c4dd6:WorkflowHistory.tsx` | Test Files 3 passed; Tests 18 passed | confirms B2 caused the regression |
| FE-only scope | `git diff --name-only 260c4dd6..HEAD` | only the 3 frontend/src/history files; backend diff empty | ✓ PASS (INV-3) |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| RevisionFamilyView.tsx | 355 | `extractRevisionInstructionPreview` shim | ℹ️ Info | Intentional, documented INV-12 preview-only shim with Workstream-C hand-off comment — not a defect. |
| WorkflowHistory.tsx | 191 | new getRunFamily call unmocked in 3 existing specs | 🛑 Blocker | Root cause of the 18-test regression (see Gaps). |

No unreferenced TBD/FIXME/XXX debt markers in touched files.

### Human Verification (informational — not blocking)

Per the mandate, visual pixel-fidelity of the family cards / version chips against WORKSTREAM-B-UI-SPEC.md is the job of the closing UI-audit, not this verifier. Noted, not blocked on. Every class traces to an inherited analog (spot-checks above), so the offline reuse-first contract is satisfied; only literal pixel rendering remains for the UI audit.

### Gaps Summary

All 7 plan truths and the 4 folded-in fixes (W1/W2/W3/I1) are correctly implemented and independently verified — the D3/D4 feature itself is complete, substantive, and wired, with the 5 new specs green and tsc clean in every touched file.

The blocking gap is a **regression the SUMMARY missed**: B2's new `getRunFamily(token, selectedRun.rootRunId)` detail-view fetch (WorkflowHistory.tsx:191) runs on every detail open, but three pre-existing, untouched test files (`WorkflowHistory.test.tsx`, `WorkflowHistory.revise.test.tsx`, `WorkflowHistory.genericReopen.test.tsx`) mock `@/lib/api` without a `getRunFamily` export. vitest hard-throws on the undefined mock export, crashing render → **18 previously-green tests now fail**. A control bisect against pre-B2 code confirms all 18 passed before B2. Production is unaffected (the real export exists and the call is `.catch`-guarded), but the SUMMARY's "zero regression" and "Self-Check: PASSED" claims are false for the existing suite, and the mandate's explicit regression guard fails.

Fix is small and mechanical: add `getRunFamily` to the `@/lib/api` `vi.mock` in the 3 files (mirroring what `WorkflowHistory.family.test.tsx:25` already does), then confirm the suite returns to green.

---

_Verified: 2026-07-02T22:35:00Z_
_Verifier: Claude (gsd-verifier)_
