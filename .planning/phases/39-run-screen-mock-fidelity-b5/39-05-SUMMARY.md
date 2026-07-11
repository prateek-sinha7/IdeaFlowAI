---
phase: 39-run-screen-mock-fidelity-b5
plan: 05
subsystem: ui
tags: [react, run-screen, run-header, version-menu, share, download, status-badge, tab-order, mock-fidelity, tailwind, tokens, playwright, screenshot-gallery]

# Dependency graph
requires:
  - phase: 39-run-screen-mock-fidelity-b5 (plan 01)
    provides: the intended-divergence register ND-A..ND-G + the additive useWorkflow surfacing (createdAt / deliverableFilename / deliverableVersion) this header REUSES, and the lane onBackToHistory seam this wires
  - phase: 39-run-screen-mock-fidelity-b5 (plan 07)
    provides: the two-sided fidelity oracle (serve/capture-mocks + assemble-gallery + FIDELITY_CAPTURE zzz-baseline) this plan drives for the header surface
provides:
  - The mock's right-column run-header ROW above the tab bar — a Version ▾ menu (from the existing runFamily), a client-only Share (copy run deep link, ND-H), and a primary Download — plus a live status badge (streaming / Awaiting you / Paused · review gate / Run failed) and a status-tinted version chip, all keyed on the generic runState/pipelineState (SC-001/ND-D)
  - The corrected tab order Preview · Steps · Files · Audit (was Preview · Files · Steps · Audit) with the Steps review dot while the run is paused
  - The lane Back-to-history + run-metadata wiring through DashboardLayout into both the lane header and the run header
  - LiveVersionChip retired — one version affordance only (INV-12/INV-3)
  - This closeout: the failed badge now NAMES the live failure location (first failed agent) reusing resolveAgentNames — the same signal the lane's failure card uses (ND-D live), resolving the plan's interim generic "Run failed" toward the mock's "Run failed at the <stage>" pattern
  - Intended-divergence register additions ND-H (Share client-only) + ND-I (failed run keeps the full four-tab row — a single uniform tab model across all states)
affects: [39-06]

# Tech tracking
tech-stack:
  added: []  # no new dependency — existing lucide-react + Phase-32 CSS tokens + the existing runFamily/download/resolveAgentNames seams
  patterns:
    - "The run header is a presentational RunHeader fed entirely by PreviewPanel-computed live values (runState/pipelineState/runFamily); NO fetch/endpoint inside the header (ND-H no-network invariant, grep-guarded)"
    - "Failed-badge reason DERIVED from the same live failed-agent signal (resolveAgentNames on pipelineState.failedAgents || degradedFailedAgents || reopenedFailedAgents) the lane's 'What went wrong' card uses — never a second resolver, never the mock's fixed text (INV-12/ND-D)"
    - "A single uniform tab model (Preview · Steps · Files · Audit, no counts, default Preview) across settled / live / failed — the mock varies the tab SET/COUNTS/DEFAULT per outcome; we keep one model (ND-I)"

key-files:
  created:
    - frontend/src/components/preview/RunHeader.tsx
    - frontend/src/components/preview/RunHeader.test.tsx
  modified:
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/layout/DashboardLayout.tsx

key-decisions:
  - "Version ▾ / Share / Download reuse the EXISTING runFamily derivation + download path (INV-12) — the header lifts the already-computed sortedMembers/activeIdx/handleSelectVersion; no new family fetch, no new endpoint"
  - "Share is client-only in v1 (ND-H): copies the owner-auth-gated run deep link to the clipboard; NO backend endpoint, NO share token, NO migration — a faithful reproduction of the button the mock shows without adding an unauth read surface"
  - "The failed badge names the LIVE failure location (first failed agent via resolveAgentNames) with the middot connector ' · ' (house style, matches the adjacent 'v1 · partial' chip) — never the mock's fixed 'security gate' text (ND-D live/generic); empty → the bare 'Run failed' (regression-free)"
  - "Failed run keeps the full four-tab row (ND-I): the mock omits Preview + adds per-tab counts + defaults to Audit on a failed run, but a state-dependent tab set is behavior, not styling — the user ruled (2026-07-11) to keep one uniform tab model; a Preview tab on a failed run still shows the failure affordance (DegradedRunAffordance), so no dead surface"
  - "LiveVersionChip retired — its menu internals now live in RunHeader's VersionMenu so there are not two version affordances (INV-3/INV-12)"

patterns-established:
  - "headerFailureReason = headerFailed ? resolveAgentNames(failedAgentNames, failedAgentNameById)[0] : undefined — the failed-badge reason feed, reusing the lane's failed-agent signal"
  - "RunHeader failureReason?: string prop — optional, additive; absent → bare 'Run failed', present → 'Run failed · {agent name}'"

requirements-completed: []  # RUNUI-06 already Complete (39-01); RUNUI-07 (Share / Version ▾ / net-new affordances) lands its header two-thirds here — the "Renders as" switch is 39-06, so RUNUI-07 stays partial until 39-06 closes it.

# Metrics
duration: ~1h (header build across 4 commits + this closeout ruling + captures) — closeout ~15m
completed: 2026-07-11
---

# Phase 39 Plan 05: Run Header — Mock Fidelity Summary

**The mock's right-column run header now sits above the tab bar — a Version ▾ menu (from the existing runFamily), a client-only Share (copy run deep link, ND-H), and a primary Download, plus a live status badge and a status-tinted version chip keyed on the generic runState/pipelineState (SC-001/ND-D) — with the tab order corrected to Preview · Steps · Files · Audit, the Steps review dot while paused, the lane Back-to-history + run-metadata wiring, and LiveVersionChip retired (INV-12). This closeout applied two adjudicated failed-state rulings: the failed run keeps the full four-tab row (ND-I, keep-ours), and the failed badge now NAMES the live failure location — the first failed agent via the same resolveAgentNames signal the lane's failure card uses (ND-D live, a fidelity MATCH toward the mock's "Run failed at the <stage>" pattern).**

## Performance

- **Duration:** ~1h total (header build + shell wiring + captures); this closeout ~15m
- **Completed:** 2026-07-11
- **Files:** 2 created (RunHeader.tsx + RunHeader.test.tsx) + 2 modified (PreviewPanel.tsx, DashboardLayout.tsx)

## Accomplishments

- **Run-header row** — a new `RunHeader.tsx` renders the mock's header ROW above the tab bar inside PreviewPanel's right column: a **Version ▾ menu** built on the existing `runFamily` derivation, a **Share** button, and a primary **Download** button in the settled state; a **status badge** (streaming / "Waiting on you" / "Paused · review gate" / "Run failed") + a status-tinted **version chip** ("v1" / "v1 draft" / "v1 · partial") in the live/failed states — all keyed on the generic `runState`/`pipelineState` (SC-001/ND-D), never a workflow-name branch.
- **Tab order + review dot** — reordered the tabs to **Preview · Steps · Files · Audit** (was Preview · Files · Steps · Audit; internal ids + testids stable) and added the pulsing **review dot** on the Steps tab while the run is paused (open gate / clarify round).
- **Share (client-only, ND-H)** — `onShare` copies the owner-auth-gated run deep link to the clipboard with a transient "Link copied" affordance; disabled while running, absent while failed. NO fetch/endpoint from the header (grep-guarded). Share uses the mock's upload-style icon (lucide `Upload`, not `Share2`).
- **Shell wiring** — threaded the lane **Back-to-history** (`onBackToHistory`, defined in 39-01) + run metadata through `DashboardLayout` into both the lane header and the run header (ND-D live values).
- **LiveVersionChip retired** — its version-menu internals now live in `RunHeader`'s `VersionMenu`, so there are not two version affordances (INV-3/INV-12).
- **Closeout — failed badge names the live failure location** — the hardcoded literal "Run failed" now appends the first failed agent's human name via `resolveAgentNames(failedAgentNames, failedAgentNameById)[0]` — the SAME live signal the lane's "What went wrong" card already uses — with the middot connector " · " (house style). Empty → the bare "Run failed" (regression-free). This resolves the plan's interim generic wording toward the mock's "Run failed at the <stage>" pattern, generically + live (ND-D).

## Task Commits

Each change was committed atomically (no trailer, on `feat/ui-2`):

1. **RunHeader — Version menu / Share / Download / status badge + tab reorder** — `8292e0a1` (feat)
2. **Wire the lane Back-to-history + run metadata into the run shell** — `5003aca4` (feat)
3. **Re-anchor header-affected e2e + add run-header fidelity captures** — `bd19369f` (test)
4. **Share uses the mock's upload-style icon (lucide Upload, not Share2)** — `f11d0a99` (fix)
5. **Closeout — failed badge names the live failure location (ND rulings)** — `9f47893c` (feat)
6. **Complete the run-header plan — SUMMARY + STATE + ROADMAP** — this docs commit (docs)

## Files Created/Modified

- `frontend/src/components/preview/RunHeader.tsx` — the right-column run header: `VersionMenu` (from runFamily), Share (client-only, ND-H), Download, and the `StatusBadge` keyed on runState. This closeout added the optional `failureReason?: string` prop (threaded params + inline type + `RunHeaderProps` + the `RunHeader`→`StatusBadge` pass-through) and changed the failed branch's text node to `Run failed{failureReason ? \` · ${failureReason}\` : ""}`.
- `frontend/src/components/preview/PreviewPanel.tsx` — computes and threads the header inputs; this closeout added `headerFailureReason = headerFailed ? resolveAgentNames(failedAgentNames, failedAgentNameById)[0] : undefined` (reusing the already-in-scope failed-agent ids + id→name map) and passed `failureReason={headerFailureReason}` to `<RunHeader/>`.
- `frontend/src/components/preview/RunHeader.test.tsx` — this closeout added one focused test: `<RunHeader runState="terminal" failed versionLabel="v1" failureReason="Security reviewer" />` asserts the badge reads "Run failed · Security reviewer" (the fidelity contract); the existing bare "Run failed" terminal test still passes (reason optional).
- `frontend/src/components/layout/DashboardLayout.tsx` — lane Back-to-history + run-metadata wiring into the header shell.

## Intended-Divergence Register

Inherits **ND-A..ND-G** (39-01-PLAN) + **ND-H** (39-05-PLAN — Share client-only), and adds:

- **ND-I — Failed run keeps the full four-tab row.** The mock's failed run omits the Preview tab, shows per-tab record counts (Steps 5 · Audit 10 · Files 3), and defaults to Audit. We keep all four tabs (Preview · Steps · Files · Audit), no counts, default Preview — a single uniform tab model across settled/live/failed. Rationale: the mock varies the tab SET/COUNTS/DEFAULT per run outcome; a state-dependent tab set is behavior, not styling, and the user ruled (2026-07-11) to keep the uniform model. A Preview tab on a failed run still shows the failure affordance (DegradedRunAffordance), so no dead surface.

**Not a divergence — a fidelity MATCH:** the failed badge REASON is now **LIVE (ND-D)**. It names the first failed agent (`resolveAgentNames`, the same signal the lane's "What went wrong" card uses), which **resolves** the plan's interim "generic 'Run failed'" wording toward the mock's "Run failed at the <stage>" pattern. It is therefore a fidelity match, not a registered divergence. Connector is " · " (house style — matches the adjacent "v1 · partial" version chip), never the mock's fixed "at the security gate" literal.

## Decisions Made

- **Reuse, don't rebuild (INV-12).** Version ▾ / Download reuse the existing `runFamily` derivation + download path; the failed-badge reason reuses `resolveAgentNames` (the lane's failed-agent signal) — no new resolver, no new fetch, no new endpoint.
- **Share stays client-only (ND-H, D39-2 scope fence).** A copy-link is faithful to the button the mock shows without adding an unauth read surface; a true public share token is out of the visual scope.
- **Keep one uniform tab model (ND-I).** The user ruled to keep all four tabs / no counts / default Preview across all states rather than fork the tab set per outcome.
- **Name the live failure location, generically (ND-D).** The failed badge appends the first failed agent name via the shared signal, with the house-style middot — never the mock's fixed "security gate" text.

## Deviations from Plan

**None** — the header plan executed as written; this closeout applied two post-plan user rulings (2026-07-11): ND-I (keep the four-tab row — no code change, register only) and the failed-badge live reason (a small additive change to RunHeader + PreviewPanel + one test). Both are within the header's scope; no backend / useWorkflow / useRunChat contract touched, no new resolver, no network in the header.

## Issues Encountered

None during the closeout. The exact line anchors in the ruling matched the current files (verified before editing): `resolveAgentNames` import at PreviewPanel.tsx:27; `failedAgentNames`/`failedAgentNameById`/`headerFailed` derivations in scope above the badge feed; the `StatusBadge` failed branch and `RunHeaderProps` at the described spots in RunHeader.tsx.

## Verification

Honest, observed results (not presumed):

- `npx tsc --noEmit` (frontend): **clean, exit 0** — no new errors in the two touched source files.
- `npm run test -- src/components/preview/RunHeader.test.tsx`: **Test Files 1 passed (1) · Tests 8 passed (8)** — including the new "names the live failure location on the failed badge (ND-D reason)" test asserting "Run failed · Security reviewer", and the pre-existing bare "Run failed" terminal test.
- ND-H no-network guard on `RunHeader.tsx` — `grep -nE "fetch\(|/api/|https?://|endpoint"`: the only hit is the file-header comment "there is NO backend endpoint and no network request in this file" (the word "endpoint" in a negation); **zero actual network calls** (`fetch(` / `/api/` / `http` = 0).
- Failed-header capture regenerated — `FIDELITY_CAPTURE=1 npm run e2e -- zzz-baseline`: **5 passed**; `frontend/e2e/fidelity/shots/current/header__failed.png` rewritten (20:58, 6642→7735 bytes — the badge widened by the appended live reason). This ephemeral "our side" capture is gitignored by design; the human fidelity sign-off against the mock is the orchestrator's checkpoint, not self-certified here.

## Requirement Status

- **RUNUI-06** (Run screen matches its mock): the run-header surface half is delivered; the requirement was already marked Complete in 39-01 (it spans all surfaces).
- **RUNUI-07** (net-new affordances): its **Share** + **Version ▾** thirds landed here; the "Renders as" renderer switch is 39-06, so RUNUI-07 stays **partial** until 39-06 closes it.

## Threat Flags

None — no new network endpoint, auth path, or trust-boundary surface. T-39-05-01 (Share info-disclosure) mitigated by copying only the owner-auth-gated run route (no public/unauth token, no new endpoint — ND-H). The failed-badge reason renders an agent name through React JSX escaping; no `dangerouslySetInnerHTML`.

## Known Stubs

None. The failed-badge reason is live — empty failed-agent list falls back to the bare "Run failed" (never a fabricated stage name).

## Next Phase Readiness

- The run header is built + wired; the two adjudicated failed-state rulings are applied. The regenerated failed-header capture is ready for the human fidelity sign-off against the Failed mock (orchestrator checkpoint).
- **39-06 (Preview browser chrome + "Renders as" switch wrapping the reused renderers)** is next; it closes RUNUI-07.
- **Concern (inherited):** the broader mocked e2e suite is still systemically stale against the feat/ui-2 redesign (D-39-07-1) — this plan re-anchored only the header-affected specs, per the per-surface re-anchor decision.

## Self-Check: PASSED

- `RunHeader.tsx` + `RunHeader.test.tsx` present; `PreviewPanel.tsx` + `DashboardLayout.tsx` present and modified.
- The failed-badge reason edits verified in the working tree diff (headerFailureReason feed + failureReason prop + the badge text node + the new test).
- Verification observed: tsc clean (exit 0), RunHeader.test 8/8 (incl. the new reason test), ND-H network grep = 0 actual calls, failed-header capture regenerated (5 passed, header__failed.png rewritten 20:58).

---
*Phase: 39-run-screen-mock-fidelity-b5*
*Completed: 2026-07-11*
