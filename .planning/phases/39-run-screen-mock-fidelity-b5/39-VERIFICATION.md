---
phase: 39-run-screen-mock-fidelity-b5
verified: 2026-07-11T22:20:00Z
status: passed
verdict: PASS-WITH-CONCERNS
score: 8/8 must-haves verified (1 carries a non-blocking WARNING)
re_verification: null
overrides_applied: 0
concerns:
  - id: W-1
    severity: warning
    truth: "Intended-divergence register ND-A..ND-J complete + each divergence justified"
    reason: >-
      Numbering collision in the ND register. 39-01 assigned ND-I = "Header Stop
      control (live)" and ND-J = "Attachment chips on a failed run" (these are the
      entries carried in the canonical fidelity-gallery caption assemble-gallery.mjs,
      which runs ND-A..ND-T). 39-05-SUMMARY then re-used ND-I for "failed run keeps
      the uniform four-tab row" and 39-06-SUMMARY re-used ND-J for "self-chromed
      renderers render in their own frame (Option-B double-frame ruling)". The two
      later divergences are real, justified in their SUMMARYs, and correctly
      implemented in code — but they collide with 39-01's ND-I/ND-J letters AND are
      ABSENT from the canonical assemble-gallery.mjs register (which stops at ND-T
      and still shows the 39-01 meanings for I/J).
    impact: >-
      Documentation/auditability only. The phase goal (per-surface fidelity) is
      achieved; both divergences are implemented (uniform TAB_CONFIG + isSelfChromedRender)
      and were human-signed-off per surface. No functional gap.
    recommendation: >-
      Renumber the two late divergences to ND-U (39-05 four-tab) and ND-V (39-06
      self-chromed) and add both entries to frontend/e2e/fidelity/assemble-gallery.mjs
      so the gallery caption is a complete, collision-free register. Given this
      phase's explicit anti-drift purpose, reconcile before the milestone audit.
    decision_needed: "Reconcile the ND-register collision now, or defer to milestone audit."
    resolution: >-
      RESOLVED 2026-07-12: renumbered the two closeout divergences to ND-U (four-tab
      row) / ND-V (self-chromed) and added both to assemble-gallery.mjs; 39-01's
      ND-I/ND-J (Stop-control / attachment-chips) unchanged.
---

# Phase 39: Run Screen Mock Fidelity [B5] — Verification Report

**Phase Goal:** Bring the run/execution screen to full visual fidelity with the VelocityAI-New-UI mocks (`Hexaware Run` / `Run - Live` / `Run - Failed`) — the left conversation lane, the run header, all four tabs (Preview / Steps / Files / Audit) with every sub-navigation level, across settled / live-streaming / failed — as-is. Re-aligns the run screen Phase 32 built.
**Verified:** 2026-07-11T22:20:00Z
**Verdict:** PASS-WITH-CONCERNS
**Re-verification:** No — initial verification.
**Branch:** feat/ui-2 · **Phase commit range:** `83980599^`..`ab433a11` (HEAD)

## Verdict

**PASS-WITH-CONCERNS.** All four ROADMAP success criteria and all declared invariants are verified in the codebase. The single concern is a non-blocking **ND-register numbering collision** (W-1 in frontmatter): the two late divergences from 39-05 (uniform four-tab row) and 39-06 (self-chromed renderers) re-use the ND-I/ND-J letters 39-01 already assigned, and are missing from the canonical gallery caption. Both divergences are nonetheless real, justified, and correctly implemented — the goal is met. This is a bookkeeping fix, not a defect.

The 4 remaining mocked-e2e failures, the ND-J self-chromed double-frame resolution, and the quarantined `ts-l` tests are **INTENTIONAL / deferred — not defects** (see SC-4 and the notes below).

## Goal Achievement — Observable Truths (Must-Haves)

| # | Must-Have (SC / Invariant) | Status | Evidence |
|---|---|---|---|
| 1 | **SC-1** Each run-screen surface matches its mock per the ND register — proven by the side-by-side screenshot-diff oracle (human sign-off) | ✓ VERIFIED (human-attested) | Fidelity harness exists + substantive: `serve-mocks.mjs` (98L), `capture-mocks.mjs` (160L), `assemble-gallery.mjs` (161L, ND-A..ND-T caption), `zzz-baseline.spec.ts` gated by `test.skip(!process.env.FIDELITY_CAPTURE …)`. Each surface SUMMARY records a human-approved close (lane 5 states / Steps 4 levels / Files settled+failed / Audit settled+failed / header + preview captures regenerated). SC-1 taken as verified via the human-gallery method per verification instruction (ND-D: live data ≠ mock literals, so no re-checkable pixel oracle). |
| 2 | **SC-2** Net-new affordances land: Share, Version ▾ menu, "Renders as" switch, fuller Audit categories | ✓ VERIFIED | `RunHeader.tsx`: `VersionMenu` (from runFamily), `onShare`/`handleShare` (client-only, ND-H — 0 network calls), `Download`, `StatusBadge`. `PreviewChrome.tsx` exports `RendersAsSwitch` (`data-testid="renders-as-switch"`), imported + mounted in `PreviewPanel.tsx` (both self-chromed and plain branches). `AuditTab.tsx`: `deriveFineCategory` yields secret-scan / perf / behavioral sub-categories derived from the real `getRunGateEvents`/`getRunValidationResults`/`getRunExecRuns` fetches. |
| 3 | **SC-3** Data real/live, renderers reused, intended divergences preserved | ✓ VERIFIED | Five deliverable renderers UNTOUCHED across the whole phase: `git diff --stat 83980599^..HEAD -- UserStoryPreview/PPTPreview/PrototypePreview/AppBuilderPreview/MarkdownPreview = EMPTY`. No cloned mock fiction: grep for `14.8M`/`151.6 KB`/`apple-reference-prototype.html`/`150 design systems`/`ak@hexaware`/`HEXAWARE`/`Catalogue` in preview+results+chat production src = **0**. Brand preserved: `VelocityAI` + `My Workflows` in `AppHeader.tsx`; purple-underline nav active-state (`border-b-2 … border-brand`, comment "purple-underline active"). |
| 4 | **SC-4** Mocked e2e green again + fidelity harness runs | ✓ VERIFIED (4 intentional shell-surface fails) | **Verifier ran the full mocked suite**: `138 passed · 4 failed · 21 skipped` (down from the ~84-failure stale baseline). The 4 failures are EXACTLY the deferred shell-surface set — `TS-A-06` + `TS-B-05` (home-grid `NEW` pill), `TS-C-08` (migration input meta "Modernise a legacy estate"), `TS-E-02` (dropped `user_allowed` filter). Each failing test's own in-file comment marks it as a retired/old-contract assertion pending reconciliation → **Phase 40 (shell) territory, not a run-screen regression**. All run-screen specs (ts-i/j/k/n/m/o/q/…) pass. `ts-l` `TS-L-03`×3 + `TS-L-04` are `test.fixme` with in-file reasons (cost display removed in KAN-83 / documented drill-in flake) — quarantined, NOT deleted/loosened. Fidelity harness runs (FIDELITY_CAPTURE zzz-baseline captures present). |
| 5 | **INV** Intended-divergence register ND-A..ND-J complete + each justified | ⚠️ PASS-WITH-CONCERN | Register in `assemble-gallery.mjs` runs ND-A..ND-T, each with a written justification. ND-A..ND-H match expectation. **Concern W-1:** 39-05's "four-tab row" and 39-06's "self-chromed renderers" re-use ND-I/ND-J (already assigned by 39-01 to Stop-control / attachment-chips) and are absent from the gallery caption. Divergences are real + justified in SUMMARYs + implemented in code — bookkeeping collision only. |
| 6 | **INV** No dual implementations (INV-3/INV-12): LiveVersionChip + tab-bar RendererSwitcher retired; no 2nd deliverable-dispatch | ✓ VERIFIED | `LiveVersionChip.tsx` **deleted** (not on disk; phase diff = 231 deletions / 0 insertions; remaining hits are comments/test-strings only). `RendererSwitcher` = **0** occurrences in `frontend/src/`. Single `renderDeliverable()` dispatch in PreviewPanel (reused by both PreviewChrome and RendersAsSwitch — no second dispatch). |
| 7 | **INV** No architecture / backend / hook-contract change beyond additive surfacing | ✓ VERIFIED | `git diff --stat 83980599^..HEAD -- backend/` = **EMPTY** (0 backend files). `useRunChat.ts`/`useRunStream.ts` unchanged. `useWorkflow.ts` = +15/-1 (additive field surfacing). `types/index.ts` additive: `PipelineRunState.deliverableFilename?`/`deliverableVersion?`/`createdAt?` all optional. `RunHeader.failureReason?` additive optional prop. |
| 8 | **INV** `tsc --noEmit` clean + touched-component vitest green | ✓ VERIFIED | `npx tsc --noEmit` (frontend) → **exit 0, 0 errors** (including `mockApi.ts`). Touched-component vitest (RunHeader, PreviewPanel, PreviewPanel.versionChip, AuditTab, FilesTab, LaneRunHeader, AgentThinkingTab, StepsDrilldown) → **8 files / 81 tests passed**. |

**Score:** 8/8 must-haves verified (must-have #5 carries a non-blocking WARNING).

## Behavioral Spot-Checks (Verifier-run, not SUMMARY-trusted)

| Behavior | Command | Result | Status |
|---|---|---|---|
| Frontend type-checks clean | `npx tsc --noEmit` | exit 0, 0 errors | ✓ PASS |
| Touched components pass unit tests | `npx vitest run` (8 suites) | 8 files / 81 tests passed | ✓ PASS |
| Mocked e2e suite green again | `npx playwright test --project=mocked` | 138 passed · 4 failed (all intentional shell-surface) · 21 skipped | ✓ PASS (SC-4 met) |
| Deliverable renderers untouched | `git diff --stat 83980599^..HEAD -- <5 renderers>` | empty diff | ✓ PASS |
| No backend change | `git diff --stat 83980599^..HEAD -- backend/` | empty diff | ✓ PASS |
| No cloned mock fiction literals | grep 7 mock literals across run-screen src | 0 hits | ✓ PASS |

## Required Artifacts

| Artifact | Provides | Status |
|---|---|---|
| `frontend/src/components/preview/RunHeader.tsx` (371L) | Version ▾ / Share / Download / StatusBadge (SC-2) | ✓ VERIFIED (wired in PreviewPanel; no network) |
| `frontend/src/components/preview/PreviewChrome.tsx` (217L) | Browser chrome + exported `RendersAsSwitch` (SC-2) | ✓ VERIFIED (imported + mounted in PreviewPanel) |
| `frontend/src/components/results/AuditTab.tsx` (822L) | Fuller Audit categories over real fetches (SC-2/SC-3) | ✓ VERIFIED (deriveFineCategory on 3 live fetches) |
| `frontend/src/components/chat/LaneRunHeader.tsx` (265L) + RunChatLane transcript | Structured left-lane transcript (SC-1) | ✓ VERIFIED (5-state gallery, human-approved) |
| `frontend/src/components/results/{StepsOverviewSpine,AgentDetailPanel,TaskDetailPanel}.tsx` | Steps 3-level drill (SC-1) | ✓ VERIFIED (vitest + gallery) |
| `frontend/e2e/fidelity/{serve-mocks,capture-mocks,assemble-gallery}.mjs` + `zzz-baseline.spec.ts` | Two-sided fidelity oracle (SC-1/SC-4) | ✓ VERIFIED (files present, FIDELITY_CAPTURE-gated) |
| `frontend/src/components/preview/LiveVersionChip.tsx` | (retired) | ✓ DELETED (INV-12) |

## Anti-Patterns / Debt-Marker Gate

| Scan | Result |
|---|---|
| `TBD`/`FIXME`/`XXX` in phase-touched source | **0** (gate clear) |
| `TODO`/`HACK`/`PLACEHOLDER`/"not implemented" | Only HTML `placeholder=` attrs + ND-F explanatory prose — no stub implementations |
| Cloned mock fiction literals | **0** |
| `test.fixme` in ts-l | 4 tests (TS-L-03×3 + TS-L-04), each with in-file reason — honest quarantine, not loosening |

## Intended / Deferred — NOT Defects (explicit)

- **4 remaining mocked-e2e failures** (TS-A-06, TS-B-05, TS-C-08, TS-E-02) are shell-surface — home-grid `NEW` pill, migration input meta, and the dropped `user_allowed` model-filter — carried by tests still asserting retired contracts. They belong to **Phase 40 (shell)**, are documented in `deferred-items.md` (D-39-07-1), and are NOT run-screen regressions.
- **ND-J self-chromed double-frame resolution** (Option-B ruling, 2026-07-11): prototype/app_builder render in their own frame, our chrome for plain deliverables. Implemented via `isSelfChromedRender` — a registered, user-adjudicated divergence, no renderer edits (ND-G intact).
- **ND-I uniform four-tab row** (39-05, user ruling): the failed run keeps Preview·Steps·Files·Audit rather than forking the tab set — behavior, not styling; implemented in `TAB_CONFIG`.
- **`ts-l` TS-L-03×3 + TS-L-04** are `test.fixme` (skipped, not deleted) with documented reasons (cost display removed in KAN-83; documented harness-timing flake, app verified correct).

## Concern (Requires Developer Decision — non-blocking)

**W-1 — ND-register numbering collision.** `ND-I` and `ND-J` are each used for two different divergences across the phase's own artifacts (39-01: Stop-control / attachment-chips — the versions that live in the canonical `assemble-gallery.mjs` caption; 39-05/06: four-tab-row / self-chromed-frame — documented only in their SUMMARYs and absent from the gallery caption, which stops at ND-T). Every divergence is justified and correctly implemented, so the phase goal holds — but for a phase whose stated purpose is rigorous anti-drift verification, the register should be collision-free and complete. **Recommendation:** renumber to ND-U (four-tab) / ND-V (self-chromed) and add both to `assemble-gallery.mjs`. Decide: reconcile now, or defer to milestone audit.

## Gaps Summary

No goal-blocking gaps. All four ROADMAP success criteria are verified in the codebase (not merely claimed): the net-new affordances exist and are wired, the renderers are provably untouched, the data is live (no cloned fiction), no dual implementations survive, the backend/hook contracts are unchanged, `tsc` + touched vitest are green, and the mocked e2e suite is green modulo 4 intentional shell-surface deferrals. The one open item is the advisory ND-register bookkeeping collision (W-1) — a documentation fix, not a functional gap.

---

_Verified: 2026-07-11T22:20:00Z_
_Verifier: Claude (gsd-verifier) — goal-backward, adversarial. Evidence gathered by reading the modified source, git-diffing the full phase commit range, running tsc + vitest + the full mocked Playwright suite._
