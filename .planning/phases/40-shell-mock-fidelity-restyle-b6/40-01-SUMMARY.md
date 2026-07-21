---
phase: 40-shell-mock-fidelity-restyle-b6
plan: 01
subsystem: testing
tags: [playwright, e2e, mock-fixtures, fidelity-oracle, screenshot-gallery, shell-ui]

# Dependency graph
requires:
  - phase: 39-run-screen-mock-fidelity
    provides: the fidelity screenshot oracle pattern (capture/assemble/env-gated spec) + shell oracle scaffolding this reuses
provides:
  - "MockApi stub for GET /api/user-workflows (fixes the Catalogue `userWorkflows.filter is not a function` crash in mocked mode)"
  - "Opt-in shell-capture seeding (DEFAULT_USER_WORKFLOWS + SEEDED_HISTORY_RUNS + SEEDED_ANALYTICS) installed via dashboard.seedShell()"
  - "A formalized, repo-relative, SHELL_CAPTURE-gated shell fidelity oracle with a per-surface --surface filter and the finalized ND-A..D + ND-W..Z register"
  - "SHELL-01..04 owned as the Phase-40 shell-mock-fidelity requirements (fidelity lens over the Workstream-B ids)"
affects: [40-02, 40-03, 40-04, 40-05, 40-06, 40-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Opt-in test-fixture seeding: MockApi defaults stay byte-identical (empty); a page-object seedShell() installs populated scaffolding only for the capture spec (SC-001/ND-D)"
    - "Two-sided screenshot oracle with a per-side tag alias so divergent mock/current tags pair in the gallery"

key-files:
  created:
    - .planning/phases/40-shell-mock-fidelity-restyle-b6/40-01-SUMMARY.md
  modified:
    - frontend/e2e/fixtures/mockApi.ts
    - frontend/e2e/fixtures/dashboard.ts
    - frontend/e2e/tests/zzz-shell-baseline.spec.ts
    - frontend/e2e/fidelity/assemble-shell-gallery.mjs
    - frontend/e2e/fidelity/capture-shell-mocks.mjs
    - frontend/e2e/fidelity/README.md
    - frontend/.gitignore
    - .planning/REQUIREMENTS.md

key-decisions:
  - "SHELL-01..04 already existed (Workstream-B, Phases 35–38) and are referenced by all 7 Phase-40 plans; rather than mint duplicate contradictory ids, Phase 40 OWNS/closes them via a fidelity-lens subsection (no dangling, no duplicate checkboxes)"
  - "Made all three oracle pieces repo-relative under a single shared base (e2e/fidelity/shots-shell/{target,current} + gallery-shell.html); PHASE40_OUT overrides for scratch"
  - "Aliased the mock tag agent-detail-drawer ↔ our library-agent-detail so the ND-Z deferred-drawer pair renders left/right (W2)"
  - "Did NOT mark SHELL-01/SHELL-04 complete — 40-01 is the harness wave; those close after the Wave-2 surface plans + Phase 41 (the Library drawer)"

patterns-established:
  - "seedShell() opt-in scaffolding: defaults empty (no spec regresses), capture spec opts in"
  - "Gallery tag normalization (normTag) to pair divergent per-side surface tags"

requirements-completed: []  # 40-01 is the harness wave; SHELL-01/04 close after Wave 2 + Phase 41

# Metrics
duration: ~40min
completed: 2026-07-12
---

# Phase 40 Plan 01: Shell Fidelity Harness + Oracle Summary

**Stubbed the blocked `/api/user-workflows` (Catalogue no longer crashes in mocked mode), added opt-in seeded History/Analytics/Home-recents scaffolding, and finalized the repo-relative, per-surface shell fidelity oracle carrying the ND-A..D + ND-W..Z register — unblocking every Wave-2 surface plan's fidelity checkpoint.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-07-12
- **Tasks:** 3
- **Files modified:** 8 (7 frontend test-infra/docs + 1 planning doc)

## Accomplishments

- **Catalogue unblocked:** `GET /api/user-workflows` now returns an ARRAY (default `[]`, fixing the `userWorkflows.filter is not a function` crash at `SavedWorkflowsPage.tsx:170`); `setUserWorkflows` + `DEFAULT_USER_WORKFLOWS` (3 rows) seed it for the capture. Verified visually: Catalogue renders 3 workflow cards.
- **Populated surfaces for a fair diff:** `SEEDED_HISTORY_RUNS` (a 2-version prototype revision family + a failed + a cancelled run, across TODAY/EARLIER/OLDER buckets, with `token_usage`) feeds both Run History and the Home "Jump back in" recents; `SEEDED_ANALYTICS` fills every AnalyticsSummary key. Verified visually: History shows date-bucketed family groups + status/token/version chips; Analytics shows 7.16M tokens / 85% success / by-pipeline + by-model bars.
- **Opt-in seeding:** all seeding is installed via `dashboard.seedShell()` (called before `goto()`); MockApi DEFAULTS stay byte-identical (empty `userWorkflows`, zero-state `analytics`), so no existing spec regresses.
- **Formalized oracle:** `zzz-shell-baseline.spec.ts` (SHELL_CAPTURE-gated, repo-relative), `capture-shell-mocks.mjs` + `assemble-shell-gallery.mjs` (repo-relative default base, `--surface` filter), the finalized ND-A..D + ND-W..Z register as the canonical source of truth, README documented, `shots-shell/` + `gallery-shell.html` git-ignored.
- **Requirement traceability:** SHELL-01..04 owned as the Phase-40 shell-mock-fidelity requirements (fidelity lens); no dangling ids across the 7 plans.

## Task Commits

1. **Tasks 1 + 2: MockApi stub + opt-in seeding + formalized shell oracle** — `<hash-1>` (feat)
2. **Task 3: own SHELL-01..04 Phase-40 fidelity traceability** — folded into the same atomic commit (docs portion)

_(Single atomic commit for the Wave-1 harness per the orchestrator instruction; see the completion report for the hash.)_

## Files Created/Modified

- `frontend/e2e/fixtures/mockApi.ts` — `/api/user-workflows` GET/POST/PATCH/DELETE handlers; `userWorkflows`/`analytics` fields + `setUserWorkflows`/`setAnalytics` setters; `DEFAULT_USER_WORKFLOWS`, `SEEDED_HISTORY_RUNS`, `seededHistoryFamily`, `SEEDED_ANALYTICS`, `DEFAULT_ANALYTICS`; extended `RawRun` with optional revision fields.
- `frontend/e2e/fixtures/dashboard.ts` — `seedShell()` opt-in installer.
- `frontend/e2e/tests/zzz-shell-baseline.spec.ts` — installs `seedShell()` before `goto()`; repo-relative `current/` output.
- `frontend/e2e/fidelity/assemble-shell-gallery.mjs` — finalized ND register, `--surface` filter, repo-relative base, `agent-detail-drawer`↔`library-agent-detail` alias (W2).
- `frontend/e2e/fidelity/capture-shell-mocks.mjs` — repo-relative `target/` output default (path-only change; capture logic untouched).
- `frontend/e2e/fidelity/README.md` — Phase-40 shell harness section (commands, layout, per-surface regeneration, ND list).
- `frontend/.gitignore` — ignore `shots-shell/` + `gallery-shell.html`.
- `.planning/REQUIREMENTS.md` — "Shell Mock Fidelity (Phase 40 [B6])" subsection owning SHELL-01..04 as a fidelity lens.

## Decisions Made

See `key-decisions` frontmatter. The load-bearing one: SHELL-01..04 pre-existed as Workstream-B requirements and are referenced by all 7 Phase-40 plans, so Phase 40 CLOSES them (fidelity lens) rather than minting duplicate ids.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The plan's per-e2e `tsconfig.json` does not exist**
- **Found during:** Task 1 (verify block referenced `npx tsc --noEmit -p e2e/tsconfig.json`)
- **Issue:** There is no `frontend/e2e/tsconfig.json`; the e2e sources are typechecked by the ROOT `frontend/tsconfig.json` (`include: **/*.ts`).
- **Fix:** Ran the gate via the root `npx tsc --noEmit` (the plan's main VERIFY) — 0 errors. No file created.
- **Verification:** `npx tsc --noEmit` → 0 `error TS`.

**2. [Rule 1 - Fixture correctness] Layout inconsistency between the spec, target capture, and assembler**
- **Found during:** Task 2
- **Issue:** The committed spec wrote `<PHASE40_OUT>/shots/current` while the assembler/target read `<ROOT>/shots/{target,current}` with a `/tmp/phase40-scope` default — the repo-relative (unset) default diverged, so the gallery could not pair.
- **Fix:** Unified all three onto a single repo-relative base (`e2e/fidelity/shots-shell/{target,current}` + `gallery-shell.html`), PHASE40_OUT overriding. This required a path-only edit to `capture-shell-mocks.mjs` (its capture logic is untouched, per "reuse as-is").
- **Verification:** Ran capture (current + target) + assemble end-to-end → 31 pairs; `--surface history` → 2 pairs.

**3. [Scope — deferred] SHELL-01/SHELL-04 not marked complete**
- 40-01 is the harness wave; it does not restyle the shell chrome (SHELL-01) or build the Configure surface / Library drawer (SHELL-04). Those close after the Wave-2 surface plans + Phase 41. Left the requirement checkboxes/traceability as Pending; documented Phase-40 ownership in the new fidelity subsection. `requirements-completed` intentionally empty.

---

**Total deviations:** 3 (2 auto-fixed, 1 scope-correctness). No scope creep — all changes are test-infra/docs only; no `frontend/src/**` app component was touched.

## Warnings folded in (plan-checker)

- **W1 (ts-a disposition):** The shell CHROME (top bar / nav pill / profile menu) is NOT restyled this phase and the MockApi seeding is OPT-IN (defaults byte-unchanged), so `ts-a.auth.spec.ts` needs NO selector re-anchor. **Proven:** with my changes, `ts-a` runs 3/4 pass; the 1 failure (TS-A-06, the retired "NEW" pill reconciliation assertion) fails IDENTICALLY on the baseline fixtures (restored HEAD versions, re-ran) — i.e. pre-existing and unrelated to the seeding. This demonstrates the defaults are untouched.
- **W2 (gallery tag alias):** The mock side emits `agent-detail-drawer`; our side emits `library-agent-detail`. The assembler now aliases them (`normTag`) so the ND-Z deferred-Library-drawer section renders as a left/right pair (verified: 0 unpaired `agent-detail-drawer` sections; `library-agent-detail__shell` renders as a pair).

## Issues Encountered

- History's seeded prototype family root (created 3h before an early-morning capture) lands in the EARLIER bucket rather than TODAY; the diff still shows ≥2 populated date-bucket groups (EARLIER + OLDER) with family/version chips, satisfying the "populated across buckets" requirement.

## Known Stubs

The seeded MockApi data (`DEFAULT_USER_WORKFLOWS` / `SEEDED_HISTORY_RUNS` / `SEEDED_ANALYTICS`) is intentional, opt-in, test-only capture scaffolding (labelled NOT production data), installed only by `dashboard.seedShell()` for the shell fidelity capture under SC-001/ND-D. Production endpoints return only real owner-scoped data. This is by design, not a shipped stub.

## Verification Results

- `npx tsc --noEmit` (root, covers e2e) → **0 errors**.
- vitest `WorkflowHistory.grouping` + `launchImageAndRecents.source` → **8/8 pass**.
- `SHELL_CAPTURE=1 npx playwright test --project=mocked zzz-shell-baseline` → **2/2 pass**, 25 current-side shots (Catalogue renders, History/Analytics populated — visually confirmed).
- `node capture-shell-mocks.mjs` → 27 target shots; `node assemble-shell-gallery.mjs` → **31 pairs**; `--surface history` → **2 pairs**.
- Task greps: `api/user-workflows`, `setUserWorkflows`, `ND-W`, `ND-Z`, `surface` present; `ND-F?` absent; `gallery-shell.html` git-ignored.
- `ts-a` smoke → 3/4 pass; the 1 failure proven pre-existing on baseline fixtures (no regression from seeding).
- `ts-t.history` (5) → **5/5 pass** (specs that set their own runs are unregressed).
- SHELL-01..04 defined + owned; no dangling ids across the 7 Phase-40 plans.

## Next Phase Readiness

Wave 2 (40-02..40-07) is unblocked: the gallery renders every in-scope surface (Catalogue no longer crashes; History/Analytics/Home-recents populated), the oracle regenerates per-surface via `--surface`, and the ND register is the canonical ignore-list. Each surface plan re-anchors its own mocked-e2e spec green in its wave.

---
*Phase: 40-shell-mock-fidelity-restyle-b6*
*Completed: 2026-07-12*
