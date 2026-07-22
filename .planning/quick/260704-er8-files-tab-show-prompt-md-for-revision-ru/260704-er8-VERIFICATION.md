---
phase: quick-260704-er8
verified: 2026-07-04T10:52:00Z
status: passed
score: 5/5 must-haves verified
re_verification:
  previous_status: none
  previous_score: n/a
---

# Phase quick-260704-er8: Files tab — show prompt.md for revision runs Verification Report

**Phase Goal:** The Files tab renders a run-input `prompt.md` for REVISION runs (previously only original/brief runs got one), by deriving the primary row content as `parsed.revisionInstruction || parsed.brief` — single `parseRunInput` call, parsed-shape dispatch, no workflowType/run-name branch; filename stays `prompt.md` for all runs; clarifications branch unchanged.
**Verified:** 2026-07-04T10:52:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | A REVISION run (revisionInstruction, empty brief) renders a `prompt.md` row whose content is the revision instruction | ✓ VERIFIED | `FilesTab.tsx:60` `const primary = parsed.revisionInstruction \|\| parsed.brief;` guarded `if (primary)` → row with `content: primary`. Parser `runInput.ts:74-79` sets `revisionInstruction` and leaves `brief=""` for the revision marker. Test `FilesTab.runInput.test.tsx:90-98` renders REVISION_INPUT, asserts `prompt.md` present and download fires `createObjectURL` (proving real downloadable content). Vitest: 35/35 pass. |
| 2 | An ORIGINAL run (non-empty brief) still renders `prompt.md` with the brief (zero regression) | ✓ VERIFIED | Same code path: `primary = ... \|\| parsed.brief`. Tests at L53-64 and L100-103 render plain-brief input and assert `prompt.md` present. Green. |
| 3 | No `revision-request.md` row is ever emitted — filename is `prompt.md` for every run | ✓ VERIFIED | `FilesTab.tsx:64` `name: "prompt.md"` for both shapes (single row, no rename branch). Test L93 `expect(screen.queryByText("revision-request.md")).toBeNull()`. |
| 4 | A run parsing to neither instruction nor brief shows no `prompt.md` row (no empty row) | ✓ VERIFIED | `if (primary)` guard at L61 gates the push; empty parse → `primary=""` (falsy) → no row. Test L76-82 (neither prop threaded) asserts no "Run input" section / no `prompt.md`. |
| 5 | `clarifications.md` still renders only when clarifications rounds exist, unchanged | ✓ VERIFIED | Clarifications branch `FilesTab.tsx:73-85` untouched (`if (clarifications?.length)`). Tests L60-64 and L105-109 assert `clarifications.md` null when no rounds, present when `ROUNDS` threaded. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `frontend/src/components/results/FilesTab.tsx` | `runInputFileRows` derives primary row from `parsed.revisionInstruction \|\| parsed.brief`, one `parseRunInput` call, parsed-shape dispatch | ✓ VERIFIED | L59 single call, L60 dispatch, L61 guard. `contains: "revisionInstruction \|\| parsed.brief"` present verbatim at L60. |
| `frontend/src/components/results/FilesTab.runInput.test.tsx` | Revision + zero-regression + no-clarifications specs | ✓ VERIFIED | 3 new specs (L90-109) + `REVISION_INPUT` const with `REVISION REQUEST` marker (L87-88). All green. |
| `.planning/FIX-REGISTER.md` | FIX-033 summary-table row | ✓ VERIFIED | L43, exactly 9 pipes, directly after FIX-032 (L42). Contains `FIX-033`. |
| `.planning/ISSUES-REGISTER.md` | Appended issue row for the revision prompt.md gap | ✓ VERIFIED | L39 `ISS-030`, 7 pipes, status `**FIXED** (quick-260704-er8)`, mentions `prompt.md`. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `FilesTab.tsx` | `lib/runInput.ts` | `parseRunInput` called ONCE; `revisionInstruction \|\| brief` | ✓ WIRED | Import at L12; exactly one call site (L59, confirmed via grep `parseRunInput\(`); other 3 occurrences are import + doc-comments. `runInput.ts` unmodified by this phase. |
| `FilesTab.tsx` | run-input prompt.md row | row id `run-input-prompt` → default `downloadBlob` branch | ✓ WIRED | Row id preserved at L63; `handleDownload` (L436-517) has no special case for `run-input-prompt`, so it falls to the `else → downloadBlob` branch (L515). No new download code. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Targeted vitest (FilesTab/StartingPoint/runInput/revisionChip) | `vitest run FilesTab StartingPoint runInput revisionChip` | 7 files / 35 tests passed | ✓ PASS |
| tsc identity (only pre-existing errors) | `tsc -p tsconfig.json --noEmit` | 2 errors, both `e2e/fixtures/mockApi.ts` (TS2352, pre-existing); none in FilesTab.tsx | ✓ PASS |
| Revision-download real content | test L96-97 clicks download → `createObjectURL` called | Passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| FIX-033 | 260704-er8-PLAN.md | Files tab shows no run-input file for revision runs — prompt.md derived only from parsed.brief | ✓ SATISFIED | Fix implemented (FilesTab.tsx:60), tested, logged in FIX-REGISTER L43. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| — | — | No TBD/FIXME/XXX/placeholder markers in modified files | — | None. Grep of the two frontend files for debt markers returned nothing relevant. |

### Invariant / Scope Checks

| Check | Status | Evidence |
| --- | --- | --- |
| SC-001/INV-1: no `workflowType`/`pipeline_type`/run-name branch in `runInputFileRows` | ✓ | Function signature is `(runInput?, clarifications?)`; grep of L57-87 for those tokens → NONE. |
| INV-12: `parseRunInput` reused, called once, no new marker regex/second parser | ✓ | 1 call site; `runInput.ts` untouched; no new regex added to FilesTab.tsx. |
| INV-3: frontend-only, no backend/characterization-golden change | ✓ | `git diff 30cf7971..bf1c8547 --name-only` = 2 frontend files + 2 register docs only. No backend, no golden. |
| Commits atomic on `new-workflow-engine`, no Co-Authored-By trailer | ✓ | Branch `new-workflow-engine`; 3 commits `7496361e`/`69e0d213`/`bf1c8547`; commit bodies contain no `Co-Authored-By` trailer. |
| Working tree clean outside quick dir | ✓ | `git status --porcelain` clean apart from the orchestrator-owned quick/ plan dir. |

### Human Verification Required

None. The change is fully covered by real-DOM vitest specs (including the download path via `createObjectURL`), and offline evidence is conclusive. Per project policy, live-environment visual confirmation (rendered Files tab for an actual persisted revision run) may be spot-checked at end-of-milestone but does not block completion.

### Gaps Summary

No gaps. All 5 observable truths verified against the actual codebase, all 4 artifacts present and substantive, both key links wired, all invariants (SC-001, INV-1, INV-3, INV-12) upheld, targeted vitest green (35/35), tsc clean apart from the 2 known pre-existing `mockApi.ts` errors, diff scope limited to the two frontend files plus the two allowed register docs, and commits are clean on `new-workflow-engine` with no Co-Authored-By trailer. Phase goal achieved.

---

_Verified: 2026-07-04T10:52:00Z_
_Verifier: Claude (gsd-verifier)_
