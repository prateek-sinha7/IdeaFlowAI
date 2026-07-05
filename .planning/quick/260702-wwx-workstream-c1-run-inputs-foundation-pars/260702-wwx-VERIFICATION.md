---
phase: 260702-wwx-workstream-c1-run-inputs-foundation
verified: 2026-07-03T00:10:00Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
---

# Phase 260702-wwx: Workstream C1 — Run-Inputs Foundation Verification Report

**Phase Goal:** FE-only plumbing C2 consumes: (1) shared parseRunInput lib replacing the DashboardLayout safeCleanBrief dup AND B2's extractRevisionInstructionPreview shim (INV-12 one parser); (2) getRunArtifacts fetcher (first FE consumer of Workstream-A's ?kind= filter); (3) ClarifyRound type + PipelineRunState.clarifications + live retention. Frontend-only, no C2 cards/Files rows, no backend.
**Verified:** 2026-07-03T00:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | parseRunInput decomposes a 2-attachment brief into clean `brief` + `attachments[2]`, and an inline-revision blob into `revisionInstruction` + `existingArtifactBlock` + `brief===''` | VERIFIED | `runInput.ts:38-84` exact string-slice parser; EXISTING regex `:54` `/=== EXISTING [^\n=]*? ===\n([\s\S]*?)\n=== END EXISTING [^\n=]*? ===/g` matches open/close **independently, NO backreference** — correctly handles the real asymmetric labels `EXISTING PROTOTYPE HTML`/`END EXISTING HTML` (DashboardLayout.tsx:539). Attachments use `\1` backreference (`:45`), correct because attachment names ARE symmetric. Tests `runInput.test.ts:32-57` assert attachments[2] name+content and revision blob → brief===''. **Test run: 10/10 green.** |
| 2 | Clean/plain (no markers) passes through unchanged as `brief`; chained input yields `chainContext`; `=== USER PREFERENCES ===` yields `preferences` | VERIFIED | `runInput.ts:60-72` chain + prefs regexes; `:82` format-tolerant brief fallback. Tests `runInput.test.ts:11-28` (plain + instruction-only), `:68-87` (chain + preferences). Green. |
| 3 | getRunArtifacts issues `GET /api/runs/{id}/artifacts` with `?kind=` + `?include=content` + Bearer, returns `{workflow_id, artifacts}` (ArtifactNode has no created_at) | VERIFIED | `api.ts:383-399` URLSearchParams composes `kind`/`include=content`, `authHeaders(token)` Bearer, `request<RunArtifactsResponse>`. `ArtifactNode:359-373` has NO created_at. Test `api.getRunArtifacts.test.ts:26-77` asserts URL contains `/api/runs/run-1/artifacts` + `kind=clarifications` + `include=content`, method GET, `Bearer tok`, parsed shape; no-opts case asserts no `?`. Green. |
| 4 | Live clarify Q&A survives the panel clear (fold BEFORE `setQuestionnaireQuestions([])`); clarifications reset per fresh run | VERIFIED | `DashboardLayout.tsx:1061-1074` folds ClarifyRound then `:1076` clears panel (fold-before-clear order correct). `useWorkflow.ts:144-149` retainClarifyRound appends; `:25/:53` INITIAL_STATE + startPipeline reset `clarifications:[]`. Hook test `useWorkflow.clarifyRetention.test.ts:21-35`: append survives [r1,r2], empty after 2nd startPipeline. Green. |
| 5 | submittedBrief captured on live onStartPipeline launch, reset per run | VERIFIED | `page.tsx:802` state, `:1305` `setSubmittedBrief(message)` in the onStartPipeline wrapper on every launch (revision + fresh). |
| 6 | REGRESSION GUARD: DashboardLayout chain sites + RevisionFamilyView shim delegate with NO behavior change — 6 sibling suites stay green | VERIFIED | **Re-ran independently: 6 files / 30 tests all green** (WorkflowHistory.{family,test,revise,genericReopen} + DashboardLayout.{catalogHome,waveMount}). The B2 `family` test (`make the header blue` on unclosed revision) passes — delegation preserved behavior. |
| 7 | INV-12 one-parser: inline safeCleanBrief + shim marker-scan deleted; parseRunInput is the single project-wide parser | VERIFIED | `grep -c safeCleanBrief DashboardLayout.tsx` = 0; `grep -c 'MARKER = ' RevisionFamilyView.tsx` = 0; parseRunInput imported in both (`RevisionFamilyView.tsx:22/374`, `DashboardLayout.tsx:26/940/1013`). Remaining `=== REVISION REQUEST ===` hits (DashboardLayout :501-1315) are outbound COMPOSITION sites, not parsers — no duplicate parser remains. NET_NEGATIVE_OK. |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `frontend/src/lib/runInput.ts` | parseRunInput + ParsedRunInput | VERIFIED | 124 lines, exports both, 6 marker families, wired in 2 consumers |
| `frontend/src/lib/runInput.test.ts` | 7 parser cases | VERIFIED | 8 `it` cases (plain/instruction/attachments/revision-blob/unclosed/chain/prefs), green |
| `frontend/src/lib/api.ts` | getRunArtifacts + types | VERIFIED | `:359-399` types + fetcher |
| `frontend/src/lib/api.getRunArtifacts.test.ts` | fetch-mock URL+params+Bearer | VERIFIED | 2 cases (with-opts + no-opts), green |
| `frontend/src/types/index.ts` | ClarifyRound + clarifications? | VERIFIED | `:525-533` ClarifyRound, `:568` clarifications? |
| `frontend/src/hooks/useWorkflow.ts` | retainClarifyRound + reset | VERIFIED | `:144-149` append, `:25/:53` reset, `:160` returned |
| `frontend/src/hooks/useWorkflow.clarifyRetention.test.ts` | append survives + reset | VERIFIED | renderHook, green |
| `frontend/src/components/history/RevisionFamilyView.tsx` | delegates to parseRunInput | VERIFIED | `:372-382` delegates, marker-scan gone, :441 call site preserved |
| `frontend/src/components/layout/DashboardLayout.tsx` | chain rewire + clarify fold | VERIFIED | `:940/:1013` parseRunInput, `:1061-1076` fold-before-clear |
| `frontend/src/app/dashboard/page.tsx` | submittedBrief + wiring | VERIFIED | `:802/:1305` capture, `:1335` onRetainClarifyRound |

### Key Link Verification

| From | To | Via | Status |
|------|-----|-----|--------|
| DashboardLayout.tsx | runInput.ts | parseRunInput import replacing safeCleanBrief | WIRED (:26/:940/:1013, safeCleanBrief=0) |
| RevisionFamilyView.tsx | runInput.ts | extractRevisionInstructionPreview delegates | WIRED (:22/:374) |
| api.ts | GET /api/runs/{id}/artifacts | getRunArtifacts fetch | WIRED (:388) |
| DashboardLayout.tsx | useWorkflow.ts | onRetainClarifyRound folds before panel clear | WIRED (page.tsx:1335 → DashboardLayout:1061-1074 → useWorkflow:144) |

### Behavioral Spot-Checks / Gate Execution (re-run independently)

| Gate | Command | Result | Status |
|------|---------|--------|--------|
| tsc identity | `npx tsc --noEmit \| grep 'error TS'` | `total=3 new=0` — 2× mockApi.ts + 1× IdeaInputPage.tsx (untouched files) | GATE_OK |
| New specs | `vitest run runInput + api.getRunArtifacts + clarifyRetention` | 3 files / 10 tests passed | PASS |
| Regression guard | `vitest run` 6 sibling suites | 6 files / 30 tests passed | PASS |
| INV-12 net-negative | grep safeCleanBrief=0, MARKER=0, parseRunInput×2 | NET_NEGATIVE_OK | PASS |
| INV-3 backend | `git diff --name-only afecf23f..HEAD` | 10 files, ALL `frontend/src/**`, zero backend | PASS |

### Anti-Patterns Found

None. No TBD/FIXME/XXX in touched files. `submittedBrief` is captured-only (consumer is C2's StartingPointCard) — documented scope split, not a stub. No backreference-on-asymmetric-EXISTING bug (the flagged critical failure mode) — the EXISTING regex matches open/close independently via `[^\n=]*?`.

### Human Verification Required

None — deterministic FE plumbing, fully covered by unit/hook tests and static gates. The visual cards (StartingPointCard/ClarificationsCard/Files rows) are C2 scope, deliberately not shipped here.

### Gaps Summary

No gaps. All 7 must-have truths verified against real code and independently re-run gates. The three checker-flagged risk areas are all clean: (1) EXISTING-block match is label-tolerant (independent open/close, no backreference) — real asymmetric inputs like `EXISTING PROTOTYPE HTML`/`END EXISTING HTML` parse correctly; (2) the B2 shim delegation preserves the timeline preview (family test green); (3) INV-12 leaves exactly one parser — the remaining `=== REVISION REQUEST ===` strings are outbound composition, not a second parser. tsc identity holds (3/0), all 4 test/grep gates green, zero backend files touched.

---

_Verified: 2026-07-03T00:10:00Z_
_Verifier: Claude (gsd-verifier)_
