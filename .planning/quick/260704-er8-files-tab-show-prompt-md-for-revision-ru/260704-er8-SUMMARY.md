---
phase: quick-260704-er8
plan: 01
subsystem: frontend/results
tags: [files-tab, run-input, revision, prompt.md, FIX-033, ISS-030]
requires: [frontend/src/lib/runInput.ts parseRunInput]
provides:
  - "runInputFileRows derives prompt.md from parsed.revisionInstruction || parsed.brief (parsed-shape dispatch, one parseRunInput call)"
affects:
  - frontend/src/components/results/FilesTab.tsx
tech-stack:
  added: []
  patterns: ["parsed-shape dispatch (revisionInstruction wins, brief otherwise) mirroring StartingPointCard.isRevision"]
key-files:
  created: []
  modified:
    - frontend/src/components/results/FilesTab.tsx
    - frontend/src/components/results/FilesTab.runInput.test.tsx
    - .planning/FIX-REGISTER.md
    - .planning/ISSUES-REGISTER.md
decisions:
  - "prompt.md filename kept for BOTH original and revision runs (product decision); no revision-request.md."
  - "parseRunInput called exactly ONCE; dispatch purely on parsed shape — no workflowType/run-name branch (SC-001), no second parser (INV-12)."
  - "Row id stays run-input-prompt so it keeps flowing through the default downloadBlob branch — no new download code."
metrics:
  duration: "~10 min"
  completed: 2026-07-04
---

# Phase quick-260704-er8 Plan 01: Files tab — show prompt.md for revision runs Summary

Revision runs now render a downloadable `prompt.md` in the Files tab by deriving the primary run-input row from `parsed.revisionInstruction || parsed.brief` instead of `brief` alone.

## What Was Done

### Task 1 — FilesTab derivation fix (`7496361e`)
`runInputFileRows` in `FilesTab.tsx` previously parsed the run input and emitted `prompt.md` only from `parseRunInput(runInput).brief`, guarded `if (brief)`. A revision run's input parses to `revisionInstruction=<instruction>` with an EMPTY `brief`, so revisions never got a `prompt.md` (live or reopened). Changed to a ONE-TIME parse — `const parsed = parseRunInput(runInput ?? "")` then `const primary = parsed.revisionInstruction || parsed.brief` — and the guard to `if (primary)`, with `content: primary` / `size: formatSize(primary.length)`. Row id/name/type/icon/format/mimeType unchanged (`run-input-prompt` / `prompt.md` / `Run input` / `FileText` / `Markdown (.md)` / `text/markdown`). The `clarifications` branch is untouched. Doc-comment updated to state prompt.md = the parsed revision instruction OR the brief (parsed-shape, not brief-only).

### Task 2 — Test coverage (`69e0d213`)
Extended `FilesTab.runInput.test.tsx` (reusing the existing motion/storyExporter/createObjectURL harness) with three specs inside `describe("FilesTab — Run input section")`:
1. Revision input (`=== EXISTING PROTOTYPE HTML === … === REVISION REQUEST ===add another page tab called comparison=== END REQUEST ===`) renders `prompt.md`, no `revision-request.md`, and clicking download fires the `downloadBlob` path (`createObjectURL` called once).
2. Plain-brief original run still renders `prompt.md` (zero regression).
3. Revision run with no `clarifications` prop → `prompt.md` renders, `clarifications.md` is null.

### Task 3 — Registers (`bf1c8547`)
Appended `FIX-033` to `.planning/FIX-REGISTER.md` (9-pipe row after FIX-032) and `ISS-030` to `.planning/ISSUES-REGISTER.md` (7-pipe row after ISS-029, status **FIXED** (quick-260704-er8)).

## Deviations from Plan

**1. [Rule 3 - Blocking] FIX-033 / ISS-030 `||` reworded to `OR` to satisfy the pipe-count gate**
- **Found during:** Task 3
- **Issue:** The plan's specified Root Cause / Evidence prose contained the literal token `parsed.revisionInstruction || parsed.brief`. Its two `|` bytes are counted by the plan's own verify gate (`tr -cd '|' | wc -c` must equal `9` for FIX-033), and they also break markdown-table cell parsing. Backslash-escaping (`\|\|`) does not help because the gate counts raw pipe bytes.
- **Fix:** Reworded the `||` occurrence in both register rows to `OR` (FIX-033: "`parsed.revisionInstruction` OR `parsed.brief`"; ISS-030: "parsed.revisionInstruction OR parsed.brief"). Meaning preserved; FIX-033 now has exactly 9 pipes, ISS-030 exactly 7.
- **Files modified:** `.planning/FIX-REGISTER.md`, `.planning/ISSUES-REGISTER.md`
- **Commit:** `bf1c8547`

## Verification

- **Vitest (targeted):** `node_modules/.bin/vitest run FilesTab StartingPoint runInput revisionChip` → 7 files / 35 tests passed (incl. the 3 new revision/zero-regression/no-clarifications cases).
- **tsc-identity:** `node_modules/.bin/tsc -p tsconfig.json --noEmit` → only the 2 pre-existing `e2e/fixtures/mockApi.ts` TS2352 errors; ZERO new errors (none in FilesTab.tsx).
- **Register gate:** `REGISTERS_OK` — FIX-033 present (9 pipes) after FIX-032; ISS-030 present (7 pipes).
- **Scope:** git diff limited to `FilesTab.tsx`, `FilesTab.runInput.test.tsx`, `FIX-REGISTER.md`, `ISSUES-REGISTER.md`. No backend files touched, no golden regenerated, dev server on :3000 not relaunched, backend pytest not run.
- **Cleanliness:** no `git stash` used; working tree clean (only the untracked quick/ plan dir remains, orchestrator-owned).
- **Branch:** `new-workflow-engine` (never main); commits carry NO `Co-Authored-By` trailer.

## Success Criteria

- [x] Revision run renders `prompt.md` with content === the revision instruction; no `revision-request.md`.
- [x] Original (plain-brief) run still renders `prompt.md` — zero regression.
- [x] `parseRunInput` called exactly ONCE; parsed-shape dispatch only (SC-001/INV-1/INV-12).
- [x] Row id stays `run-input-prompt` (default downloadBlob branch); no new download code.
- [x] Targeted vitest green; tsc shows only the 2 known errors; diff limited to the two frontend files + allowed docs.
- [x] FIX-033 logged (9-pipe row after FIX-032); ISS-030 appended (7-pipe row).

## Commits

- `7496361e` — fix(260704-er8): derive prompt.md from revisionInstruction||brief so revision runs get a run-input file
- `69e0d213` — test(260704-er8): FilesTab prompt.md for revision runs + zero-regression
- `bf1c8547` — docs(260704-er8): log FIX-033 + ISS-030 (files-tab revision prompt.md)

## Self-Check: PASSED

- All 4 modified files + SUMMARY.md verified present on disk.
- All 3 commits (`7496361e`, `69e0d213`, `bf1c8547`) verified in git history.
