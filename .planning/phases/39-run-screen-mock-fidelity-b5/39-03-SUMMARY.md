---
phase: 39-run-screen-mock-fidelity-b5
plan: 03
subsystem: ui
tags: [react, run-screen, files-tab, mock-fidelity, tailwind, tokens, playwright, screenshot-gallery]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4
    provides: the redesigned run screen (Phase-32 design tokens, FilesTab structure) this re-aligns to the mock
  - phase: 39-run-screen-mock-fidelity-b5 (plan 07)
    provides: the two-sided fidelity oracle (serve/capture-mocks + assemble-gallery + the FIDELITY_CAPTURE zzz-baseline spec) this plan regenerates + reviews
provides:
  - The FILES tab brought pixel-as-is to the mock across settled + failed — a mock-faithful header + Download All, a dark "Final output" hero, an agent-outputs timeline spine, a Run-input card pair, and the failed-run "Build incomplete" amber banner
  - FilesTab additive OPTIONAL props onOpenPreview (hero Preview → switches to the Preview tab) + runStatus (failed/degraded → banner); default-undefined → zero regression for callers that thread neither
  - FileItem.code (agent initials) + the agentInitials helper — the timeline avatar node's live label
  - ND-Q registered (Files hero static "validated" label) in the fidelity gallery's intended-divergence register
affects: [39-04, 39-05, 39-06]

# Tech tracking
tech-stack:
  added: []  # no new dependency — existing lucide-react + Phase-32 CSS tokens
  patterns:
    - "Files composition driven by the LIVE derivation helpers (deriveDeliverableFiles / runInputFileRows / agentOutputs) — never the mock's fixed file list (ND-D / SC-001)"
    - "Hero = files[0] (the derived final deliverable); timeline = one avatar node per live agent output; run-input = the two live runInputFileRows"
    - "Failed banner gated on a server-derived runStatus prop (PreviewPanel terminalFailure && !cancelled) — the file list reflects the reduced LIVE outputs, no fabricated planning-only rows"

key-files:
  created: []
  modified:
    - frontend/src/components/results/FilesTab.tsx
    - frontend/src/components/results/FilesTab.test.tsx
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/e2e/fixtures/dashboard.ts
    - frontend/e2e/tests/zzz-baseline.spec.ts
    - frontend/e2e/fidelity/assemble-gallery.mjs

key-decisions:
  - "Cloned the mock's Files composition (D39-1) via Phase-32 tokens on LIVE data; kept the register divergences (ND-D live counts/names/sizes, ND-Q the static 'validated' label)"
  - "Reused every derivation + download path (deriveDeliverableFiles / runInputFileRows / handleDownload — INV-12); NO new file-derivation code, only presentational restructure + two additive optional props + FileItem.code"
  - "The --surface-ink-black token already existed (globals.css) — no new token added for the hero"
  - "Re-anchored ONLY this surface's stale e2e (dashboard previewTab/filesTab → role=tab) per the re-anchor-per-surface decision; the broader D-39-07-1 suite staleness stays a separate follow-up"

patterns-established:
  - "Agent-outputs timeline spine: an absolute vertical rail behind per-agent 38px avatar nodes (agentInitials) beside the downloadable file-row card (mock Hexaware Run.dc.html:642-656)"
  - "Failed Files = amber Build-incomplete banner over the SAME live sections (reduced outputs), not a separate flat file list"

requirements-completed: [RUNUI-06, RUNUI-08]

# Metrics
duration: ~40min (2 autonomous tasks + e2e re-anchor + 1 human-verify checkpoint)
completed: 2026-07-11
---

# Phase 39 Plan 03: Files Tab — Mock Fidelity Summary

**The run screen's FILES tab is now pixel-as-is to the mock across settled + failed — a mock-faithful header + Download All, a dark "Final output" hero (icon tile · eyebrow · live deliverable name · format·size·validated · Preview+Download), an agent-outputs timeline spine (rail + live avatar nodes), a Run-input card pair, and the failed-run "Build incomplete" amber banner — all on live data, closed to ND-A..ND-Q.**

## Performance

- **Duration:** ~40 min (2 autonomous tasks + the Files-surface e2e re-anchor + one human-verify checkpoint round)
- **Started:** 2026-07-11T19:00Z (approx)
- **Completed:** 2026-07-11T19:14Z
- **Tasks:** 2 autonomous + 1 checkpoint (Task 3, human-approved)
- **Files modified:** 6 modified · 0 created

## Accomplishments

- **Header + dark Final-output hero (settled)** — replaced the retired `#f5f5f0`/`gray-*` container with a `bg-surface-paper` mock-composition: "Files" title (Manrope 300 22px) + "N files available · M deliverable" subline + a token-styled Download All; the dark hero (`bg-surface-ink-black` + radial brand glow, 52px translucent icon tile, "FINAL OUTPUT" eyebrow in `brand-on-dark`, the LIVE deliverable name + `{format} · {size} · validated`, a Preview action + a brand Download) naming `files[0]` from `deriveDeliverableFiles` (ND-D — never the mock's "apple-reference-prototype.html · 151.6 KB").
- **Agent-outputs timeline spine** — reskinned the "Agent outputs (N)" section into the mock's spine: an absolute vertical rail behind a 38px circular avatar node per agent (live `agentInitials` via the new `FileItem.code`) beside the downloadable file-row card. One node per LIVE agent output.
- **Run-input card pair** — the two live `runInputFileRows` (prompt.md / clarifications.md) render as the mock's bordered, clickable-to-download card pair, reordered AFTER the outputs to match the mock's DOM order.
- **Failed "Build incomplete" banner (W6)** — a run that is failed/degraded (via the new server-derived `runStatus` prop, wired from PreviewPanel's `terminalFailure && !isCancelledTerminal`) shows the amber banner ABOVE the reduced LIVE planning-artifact files; default-undefined → no banner (zero regression for completed runs).
- **Fidelity oracle** — regenerated the two-sided gallery (`--surface files`): `files__settled` + the below-the-fold `files-runinput__settled` sub-view + `files__failed`, each paired against the mock; a human signed off settled + failed pixel-as-is, closed to ND-A..ND-Q.

## Task Commits

Each task was committed atomically (no trailer):

1. **Task 1: Files header + dark Final-output hero + Run-input cards (token reskin)** — `6cd26170` (feat)
2. **Task 2: Agent-outputs timeline spine + failed 'Build incomplete' banner** — `710468e7` (feat)
3. **e2e re-anchor + failed-Files capture + ND-Q** — `6b88bcf3` (test)
4. **Settled run-input sub-view capture** — `ae578fed` (test)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `frontend/src/components/results/FilesTab.tsx` — token container reskin (retired `gray-*`/`#f5f5f0` → tokens across SectionHeader, renderFileRow, base-version, empty state); new header + dark Final-output hero + agent-outputs timeline spine + Run-input card pair + failed banner; additive `onOpenPreview`/`runStatus` props, `FileItem.code` + `agentInitials`. All derivation/download wiring unchanged (INV-12).
- `frontend/src/components/results/FilesTab.test.tsx` — updated header/hero assertions; +4 new cases (hero fires download + surfaces Preview, omit-Preview-when-unwired, timeline avatar initials, failed-banner conditional). 14/14 green.
- `frontend/src/components/preview/PreviewPanel.tsx` — thread `onOpenPreview={() => handleTabChange("preview")}` + `runStatus={terminalFailure && !isCancelledTerminal ? "failed" : undefined}` into the FilesTab call (prop pass only; no tab-order/TAB_CONFIG change — 39-05/06 territory untouched).
- `frontend/e2e/fixtures/dashboard.ts` — `previewTab()`/`filesTab()` re-anchored from stale `role="button"` to the redesigned `role="tab"` primitive (regex names tolerate tab counts).
- `frontend/e2e/tests/zzz-baseline.spec.ts` — failed run seeds the two planning agents' live output + captures `files__failed`; settled captures the scroll-to-bottom `files-runinput__settled` sub-view.
- `frontend/e2e/fidelity/assemble-gallery.mjs` — registered ND-Q (Files hero static "validated" label) + bumped the caption range to ND-A..ND-Q.

## Decisions Made

- **Reuse-not-rebuild (INV-12)** — the hero, timeline and run-input cards are pure presentation over the existing `deriveDeliverableFiles` / `runInputFileRows` / `genericAgentFiles` / `handleDownload`; the only new logic is `agentInitials` (avatar label) and two additive optional props. No file-derivation code was duplicated.
- **Server-derived failed signal** — `runStatus` is driven by PreviewPanel's existing `terminalFailure && !isCancelledTerminal` (never a client `terminal && !content` guess), so the banner shows for failed/degraded but not a deliberate cancel.
- **Re-anchor scope** — only the Files-surface tab locators were re-anchored to `role=tab` (recovering `ts-o.deliverables` 7/7 + `ts-chat-cards` 3/3); the whole-suite redesign staleness (D-39-07-1) remains a separate follow-up per the re-anchor-per-surface decision.

## Intended-Divergence Register (Files surface)

- **ND-D (inherited, live data — SC-001):** our settled Files shows the LIVE counts/names/sizes (7 files · 4 agents · `apple-reference.html` · 214 B) where the mock hardcodes 8 files · 5 agents · `apple-reference-prototype.html` · 151.6 KB; agent-output role/size meta labels are live too. The hero, timeline and run-input all bind to live derivation, never the mock's fixed list.
- **ND-Q (NEW this plan):** the Final-output hero's "validated" suffix is the mock's static deliverable-passed affirmation — a settled run reaches Files only after its validation gate. The deliverable NAME / format / size are LIVE; only the "validated" word is a fixed composition label. Registered in the gallery caption.

## Deviations from Plan

None — plan executed as written. The e2e re-anchor (dashboard `previewTab()`/`filesTab()` → `role=tab`) and the failed-Files + run-input capture additions were the coordinator-directed "re-anchor this surface's e2e" scope accompanying the plan, not auto-deviations; ND-Q was added per the plan's instruction to extend the intended-divergence register as needed for Files.

## Issues Encountered

- **Run-input below the fold** — on a settled run with 4 agent outputs the Run-input card pair sits below the 900px viewport, so the first `files__settled` capture cut its card bottoms. Added an explicit scroll-to-bottom of the Files pane before a `files-runinput__settled` sub-view so no Files section is left unverified at the checkpoint.

## Verification

- `npx tsc --noEmit` — clean (0 errors, identity vs baseline).
- `FilesTab.test.tsx` — **14/14** green (hero, Preview-action, timeline-initials, failed-banner cases added).
- Banned-literal greps — `text-gray-`/`bg-gray-`/`border-gray-`/`#f5f5f0` = **0**; mock literals ("apple-reference-prototype.html"/"151.6 KB") = **0**.
- Files-surface e2e — `ts-o.deliverables` **7/7** + `ts-chat-cards` **3/3** green after the `role=tab` re-anchor.
- Fidelity — `FIDELITY_CAPTURE=1 … zzz-baseline` (5 passed) + `capture-mocks.mjs` (target) + `assemble-gallery.mjs --surface files` (4 pairs); **human-approved** settled + failed pixel-as-is, closed to ND-A..ND-Q.

## Threat Flags

None — no new network endpoint, auth path, or trust-boundary surface. T-39-03-01 (download path) reuses the existing `downloadBlob`/`handleDownload`; T-39-03-02 (XSS) — all Files text renders through React JSX escaping, no `dangerouslySetInnerHTML` added.

## Next Phase Readiness

- The Files tab is done and human-approved across settled + failed; the fidelity oracle + Files gallery section are ready.
- **39-04 (Audit)** is next — the last Wave-2 tab.
- **39-05/06 note:** FilesTab now exposes `onOpenPreview` (hero Preview → Preview tab) — 39-05/06 own the tab order/TAB_CONFIG + run-header wiring and can reuse this callback; the prop pass added here does NOT touch tab order.

## Self-Check: PASSED

- `frontend/src/components/results/FilesTab.tsx` + `FilesTab.test.tsx` + `PreviewPanel.tsx` present and modified.
- All task commits verified in git (`6cd26170`, `710468e7`, `6b88bcf3`, `ae578fed`).
- Verification: `tsc --noEmit` clean; FilesTab vitest 14/14; Files-surface e2e 10/10; fidelity gallery = 3 paired Files shots, human-approved.

---
*Phase: 39-run-screen-mock-fidelity-b5*
*Completed: 2026-07-11*
