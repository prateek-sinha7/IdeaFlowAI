---
phase: 39-run-screen-mock-fidelity-b5
plan: 06
subsystem: ui
tags: [react, run-screen, preview, browser-chrome, renders-as-switch, deliverable-renderers, streaming, mock-fidelity, tailwind, tokens, playwright, screenshot-gallery]

# Dependency graph
requires:
  - phase: 39-run-screen-mock-fidelity-b5 (plan 01)
    provides: the intended-divergence register ND-A..ND-I this surface inherits (esp. ND-D live data, ND-F no image placeholder, ND-G reuse the renderers)
  - phase: 39-run-screen-mock-fidelity-b5 (plan 05)
    provides: the RunHeader-computed live header inputs (headerVersionLabel / pipelineState.deliverableFilename / isStillRunning) this plan REUSES for the chrome URL bar + streaming detection
  - phase: 39-run-screen-mock-fidelity-b5 (plan 07)
    provides: the two-sided fidelity oracle (serve/capture-mocks + assemble-gallery + FIDELITY_CAPTURE zzz-baseline) this plan drives for the preview surface
provides:
  - The mock's PREVIEW BROWSER CHROME (new PreviewChrome.tsx) — traffic-light dots, a centered URL/file bar carrying the REAL live deliverable filename + a version chip, and a "100%" zoom + open-in-new affordance — WRAPPING the reused deliverable renderer unchanged (ND-G)
  - The "Renders as" SEGMENTED deliverable-type switch inside the chrome (reskinned from the old tab-bar <select> RendererSwitcher), fed by the EXISTING rendererOptions/rendererOverride dispatch — the genuinely-available typed renderers for THIS deliverable, never the mock's fixed 5-way (ND-D)
  - The STREAMING build variant — a "building {name}…" URL + an indeterminate progress bar over the content surface, no screenshot placeholder (ND-F); the failed run keeps DegradedRunAffordance UNWRAPPED
  - Closes RUNUI-07 (the net-new "Renders as" switch) — the last of the header/switch net-new affordances
affects: []

# Tech tracking
tech-stack:
  added: []  # no new dependency — lucide-react (Lock/ExternalLink) + Phase-32 CSS tokens + the existing rendererOptions/rendererOverride dispatch + the existing blob-open pattern
  patterns:
    - "PreviewChrome is a PASSIVE FRAME (T-39-06-01/02): it renders no deliverable content and injects no raw HTML — the sandboxed-iframe contract stays entirely with the reused renderers (untouched); the filename renders as escaped text"
    - "The 'Renders as' pills drive the SAME renderDeliverable() dispatch as before — the pills set rendererOverride, renderDeliverable() applies it (INV-12, no second dispatch). Reskinned from a <select> to segmented buttons, which also removes the old <option>-role collision with the Version-menu listbox so the switch can now surface for first-party deliverables too"
    - "The chrome's URL-bar filename + streaming detection REUSE the live values the header already computes (pipelineState.deliverableFilename, headerVersionLabel, isStillRunning) — no new fetch, no new prop contract (ND-D)"

key-files:
  created:
    - frontend/src/components/preview/PreviewChrome.tsx
  modified:
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/components/preview/PreviewPanel.test.tsx
    - frontend/e2e/tests/zzz-baseline.spec.ts  # capture-infra: adds preview__live (mirrors 39-05's header-capture add, bd19369f)

key-decisions:
  - "The chrome WRAPS the reused renderer as children (ND-G) — renderDeliverable() is unchanged and the five renderers (UserStoryPreview/PPTPreview/PrototypePreview/AppBuilderPreview/MarkdownPreview) are NOT edited (they are not in files_modified; the Task-1 diff grep for those filenames is 0). The settled double-frame this initially surfaced (our browser chrome + the renderer's own toolbar for prototype/app_builder) was RESOLVED at the checkpoint by the user's Option-B ruling (ND-J): self-chromed renderers render in their own frame (no our-chrome, switch kept above); plain deliverables keep our chrome. Still no renderer edits (ND-G intact)."
  - "The 'Renders as' options come from the EXISTING rendererOptions derivation (Auto + the typed renderers genuinely available for THIS deliverable), NOT the mock's hardcoded 5-way (Prototype/User-Stories/Deck/App/Doc). For a prototype the row reads Auto · Prototype (ND-D live). The mock literals Deck/App code/Doc are absent from the source (grep 0)."
  - "The URL bar shows the REAL deliverable filename (pipelineState.deliverableFilename → genericDeliverable.filename → a derived name), never the mock's fixed 'index.html' (ND-D). Settled capture shows 'apple-reference-prototype.html'; streaming shows 'building deliverable-v1…' because no live filename exists until the build completes (honest live value, not fabricated)."
  - "The streaming variant drops the mock's 'drop a screenshot' image placeholder (ND-F): the content surface shows the live renderer output (which already streams) or a calm 'Building your deliverable…' state under the indeterminate progress bar. `grep image-slot` across PreviewPanel.tsx + PreviewChrome.tsx = 0."
  - "The failed run keeps the existing DegradedRunAffordance path exactly, UNWRAPPED — the Failed mock has no Preview surface, so a failed run shows the degraded card, not a chromed preview (asserted in vitest with a terminal-failed, no-content pipelineState)."
  - "Retired the old tab-bar <select> RendererSwitcher (INV-3/INV-12 — no dual switch); its logic (value→null-on-Auto) is preserved in the segmented pills inside the chrome."

patterns-established:
  - "PreviewChrome({ filename, versionLabel, streaming, rendererOptions, rendererValue, onRendererChange, onOpen, children }) — the passive browser frame; children = the reused renderer output"
  - "previewFilename = pipelineState?.deliverableFilename || genericDeliverable?.filename || `deliverable-${headerVersionLabel}` — the live URL-bar filename feed"

requirements-completed: [RUNUI-07]  # the net-new "Renders as" deliverable-type switch — the last of RUNUI-07's affordances (Share/Version ▾ landed 39-05). RUNUI-06/08 were already Complete (39-01).

# Metrics
duration: ~40m (chrome build + wrap + switch reskin + streaming/failed + tests + captures)
completed: 2026-07-11
---

# Phase 39 Plan 06: Preview Browser Chrome + "Renders as" Switch — Mock Fidelity Summary

**The Preview tab now frames the deliverable in the mock's browser chrome — a new `PreviewChrome.tsx` with traffic-light dots, a centered URL/file bar carrying the REAL live deliverable filename + a version chip, and a "100%" zoom + open-in-new affordance — WRAPPING the existing deliverable renderers unchanged (ND-G, not rebuilt from the mock's hardcoded website). Beneath the top bar sits the mock's "Renders as" segmented deliverable-type switch, reskinned from the old tab-bar `<select>` and fed by the SAME `rendererOptions`/`rendererOverride` dispatch (ND-D — the genuinely-available typed renderers for this deliverable, never the mock's fixed 5-way; the URL bar shows the real filename, never "index.html"). The streaming build shows a "building …" URL + an indeterminate progress bar with no screenshot placeholder (ND-F); the failed run keeps the degraded affordance unwrapped. This closes RUNUI-07.**

## Performance

- **Duration:** ~40m (component + wrap + switch reskin + streaming/failed variants + tests + fidelity captures)
- **Completed:** 2026-07-11
- **Files:** 1 created (PreviewChrome.tsx) + 2 modified (PreviewPanel.tsx, PreviewPanel.test.tsx) + 1 capture-infra (zzz-baseline.spec.ts)

## Accomplishments

- **PreviewChrome (new)** — reproduces `Hexaware Run.dc.html:184-206`: a `rounded-[14px]` card with a 46px top bar (three `#E4E1D8` traffic-light dots, a centered `max-w-[520px]` URL bar with a lock icon + the real filename + a `brand-fill`/`brand` version chip, and a right-side "100%" + `ExternalLink` open-in-new), and a scrollable `#EEECE5` content surface (`p-[22px]`) into which the reused renderer is slotted. Colors route through the Phase-32 tokens where exact (`brand`/`brand-fill`/`ink-*`/`line-divider`/`line-faint-row`/`surface-paper`) and mock-exact arbitraries where no token matches (`#FBFAF6`/`#EEECE5`/`#E4E1D8`).
- **"Renders as" segmented switch** — reskinned the old tab-bar `<select>` `RendererSwitcher` into the mock's pill row beneath the top bar (`Hexaware Run.dc.html:201-205`): a "RENDERS AS" eyebrow + segmented buttons (active = ink fill, inactive = white/line). It is fed by the EXISTING `rendererOptions` derivation (Auto + the typed renderers genuinely available for THIS deliverable) and sets the EXISTING `rendererOverride` state, so `renderDeliverable()` applies it with no second dispatch (INV-12). Because the pills are buttons (not `<option>`s), the old `<option>`-role collision with the Version-menu listbox is gone — so the switch now surfaces for first-party deliverables too (it shows whenever `rendererOptions.length > 1`).
- **Streaming build variant** — when `isStillRunning`, the chrome drops the lock/zoom/open + the switch row, the URL bar reads "building {filename}…" in `ink-300`, and an indeterminate `brand`-on-`brand-border` progress bar sweeps across the top of the content surface (scoped `@keyframes preview-chrome-bar`, matching the mock's `translateX(-100%)→320%`). No screenshot placeholder (ND-F): the live renderer streams inside, or a calm "Building your deliverable…" state fills until content arrives.
- **Failed run preserved** — the failed branch still renders `DegradedRunAffordance` UNWRAPPED (the Failed mock has no Preview surface); no chrome wraps the failure card.
- **open-in-new** — the chrome's open affordance is wired to a client-only blob-URL open (the same pattern `PPTTabActions.handleFullScreen` uses; NO network, no new surface); the chrome itself stays a passive frame.

## Task Commits

Each change was committed atomically (no trailer, on `feat/ui-2`):

1. **PreviewChrome browser frame + settled wrap + Renders-as switch + streaming build + failed pass + tests** — `704919e0` (feat). *(Tasks 1 and 2 were committed together: both are `type="auto"`, touch the same three files, and the streaming variant lives inside the same `PreviewChrome` component + the same Preview-body render block as the settled wrap — splitting at file granularity would have produced a non-green or dead-code intermediate. Both tasks' acceptance gates are green in this commit.)*
2. **Capture the Preview streaming chrome (preview__live) for the fidelity gallery** — `3edf4c8c` (test). *(Capture-infra only — mirrors 39-05's `bd19369f` which added the header captures to this spec.)*
3. **Complete the Preview plan — SUMMARY + STATE + ROADMAP** — `ea72bab8` (docs).
4. **Checkpoint refinement (ND-J, Option B): self-chromed renderers keep their own frame** — extracted `RendersAsSwitch` from `PreviewChrome` (ONE impl, two mount points, INV-12) and gated the settled branch on `isSelfChromedRender` (prototype/app_builder render their own frame with the switch above; plain deliverables keep our chrome). No renderer edits (ND-G intact). (feat)
5. **Docs: register ND-J + flip the double-frame note to resolved** — this docs commit (docs).

## Files Created/Modified

- `frontend/src/components/preview/PreviewChrome.tsx` (NEW) — the passive browser-chrome frame: top bar (dots + URL/file bar + zoom/open), the settled "Renders as" segmented switch row, and the content surface with the streaming progress-bar overlay. Props: `filename`, `versionLabel`, `streaming`, `rendererOptions`, `rendererValue`, `onRendererChange`, `onOpen`, `children`. No `dangerouslySetInnerHTML` (grep 0); no `image-slot` (grep 0). **ND-J refinement:** exports the reusable `RendersAsSwitch` (the `renders-as-switch` strip) so PreviewChrome mounts it internally AND the self-chromed settled branch mounts the SAME strip standalone (one impl, two mount points — INV-12).
- `frontend/src/components/preview/PreviewPanel.tsx` — added the `PreviewChrome`/`RendersAsSwitch` import; derived `previewFilename` + a client-only `handlePreviewOpen`; rewrote the Preview-tab body to a failure → streaming-chrome → empty → settled ladder; removed the tab-bar `RendererSwitcher` usage and DELETED the superseded `RendererSwitcher` `<select>` function (INV-3, no shadow). **ND-J refinement:** derived `isSelfChromedRender = (rendererOverride ?? renderType) ∈ {prototype, app_builder}` and split the settled branch — self-chromed → `RendersAsSwitch` strip (when >1 option) above `renderDeliverable()` directly (no our-chrome); plain → `PreviewChrome` as before.
- `frontend/src/components/preview/PreviewPanel.test.tsx` — 4 new cases: (1) the settled chrome frames the reused renderer + the URL bar shows the real filename; (2) the "Renders as" switch offers only the live typed set (Auto · Prototype), never the mock's 5-way; (3) the streaming chrome shows the "building …" URL + progress bar and omits the settled switch row; (4) the failed run keeps `DegradedRunAffordance` unwrapped (no chrome).
- `frontend/e2e/tests/zzz-baseline.spec.ts` — capture-infra: the live streaming test now captures `preview__live` so the fidelity gallery pairs the streaming chrome against the Live mock (alongside the existing `preview__settled`).

## Intended-Divergence Register

Inherits **ND-A..ND-I** (39-01 ND-A..ND-G/I + 39-05 ND-H) and **ADDS ND-J** (the self-chromed-renderer ruling below):

- **ND-J — Self-chromed renderers (prototype, app_builder) render in their OWN frame, not our browser chrome.** The mock frames every deliverable in one browser chrome; our prototype/IDE renderers bring their own frame, so wrapping them doubled it. Per the user's ruling (2026-07-11, Option B) we skip our chrome for those two types (keeping the "Renders as" switch above) and keep our chrome for plain deliverables (user_stories/ppt/markdown/generic). No renderer edits (ND-G intact); a prototype's frame is the renderer's own richer preview (Source/Tweaks/Open), a deliberate departure from the mock's URL-bar chrome for these types. Keyed on the EFFECTIVE render type (`rendererOverride ?? renderType`) so a forced-override "Renders as" pick matches what actually renders. Streaming + failed are unchanged (the ruling was specifically the settled double-frame).
- **ND-G — the renderers are REUSED, not rebuilt.** The chrome is a passive frame; the five renderers are untouched (Task-1 diff grep = 0). The settled double-frame this surfaced is now RESOLVED via ND-J (Option B) — no renderer was edited.
- **ND-D — live data, not the mock's fiction.** The URL bar shows the real filename (`apple-reference-prototype.html` settled; `building deliverable-v1…` while streaming, since no live filename exists until the build completes). The "Renders as" set is the live typed set (Auto · Prototype), not the mock's fixed Prototype/User-Stories/Deck/App/Doc.
- **ND-F — no screenshot placeholder.** The mock's streaming `<image-slot>` "drop a screenshot" placeholder is not reproduced; the surface streams the live renderer or shows a calm building state. `grep image-slot` = 0.

## Decisions Made

- **Wrap, don't rebuild (ND-G/INV-12).** `renderDeliverable()` and the five renderers are unchanged; the chrome slots their output as `children`. The "Renders as" pills reuse the existing `rendererOptions`/`rendererOverride` dispatch — no second dispatch, no new logic.
- **Live URL bar + type switch (ND-D).** Real filename + the genuinely-available typed renderers; the mock's fixed 5-way and "index.html" are absent from the source (grep 0).
- **No screenshot placeholder (ND-F).** The streaming surface streams the live renderer / a calm building state under the progress bar.
- **Failed stays degraded (unwrapped).** The Failed mock has no Preview surface, so the failed run shows `DegradedRunAffordance`, not a chromed preview.
- **Retire the old switcher (INV-3).** The tab-bar `<select>` `RendererSwitcher` is deleted; the segmented pills supersede it (no dual switch).

## Deviations from Plan

- **[Rule 3 — capture-infra] Added `preview__live` to `zzz-baseline.spec.ts`.** The checkpoint (Task 3) requires regenerating `current/preview__*` for **settled + live**, but the live capture test only shot `full`/`steps` — there was no `preview__live`. Added a single `preview__live` capture to the live streaming test (Preview is the default tab; click + shot). This mirrors how 39-05 (`bd19369f`) added the header captures to the same spec. The file is outside the plan's three `files_modified`, but it is the capture harness the checkpoint drives, not feature source.
- **[commit granularity] Tasks 1 + 2 committed together** — see Task Commits note above (same component, same render block, splitting would break the green-at-each-commit invariant). Both tasks' acceptance gates pass in `704919e0`.

Otherwise the plan executed as written.

## Issues Encountered

- **Self-inflicted grep-guard trip (fixed).** My first-draft doc comments in `PreviewChrome.tsx`/`PreviewPanel.tsx` contained the literal tokens `image-slot` and `dangerouslySetInnerHTML` (in ND-F / passivity prose), which the mechanical guards count. Reworded the comments to avoid the literal tokens; both guards now read 0. No behavior change.
- **Line anchors.** The plan's PreviewPanel anchors had drifted by the 39-05 edits; located the current spots by the described code (renderDeliverable at ~776, rendererOptions at ~741, the Preview body at ~906, the tab-bar switcher at ~872, the RendererSwitcher function at ~1001) — all matched the described logic.

## Verification

Honest, observed results (not presumed):

- `npx tsc --noEmit` (frontend, excluding the pre-existing mockApi.ts errors per the plan's verify): **0 errors** in the touched files.
- `npx vitest run src/components/preview/PreviewPanel.test.tsx`: **Test Files 1 passed (1) · Tests 10 passed (10)** — the 4 pre-existing header/tab tests + the 6 chrome/switch/streaming/failed + ND-J tests (the plain-deliverable chrome test now targets user_stories; two new ND-J tests assert prototype/app_builder render WITHOUT `preview-chrome` — keeping `renders-as-switch`).
- **Grep guards (all pass):** renderer files in the diff (`UserStoryPreview|PPTPreview|PrototypePreview|AppBuilderPreview|MarkdownPreview`) = **0**; `image-slot` in PreviewPanel.tsx + PreviewChrome.tsx = **0 / 0**; `dangerouslySetInnerHTML` in PreviewChrome = **0**; the mock's fixed 5-way literals `"Deck"`/`"App code"`/`"Doc"` = **absent (0)**.
- **Captures regenerated:** `FIDELITY_CAPTURE=1 npm run e2e -- zzz-baseline` → **5 passed**; `current/preview__settled.png` + `current/preview__live.png` rewritten (21:17). `node capture-mocks.mjs` → target `preview__settled/live/failed` captured (21:18, network was available). `node assemble-gallery.mjs --surface preview` → **3 pair(s)**, `gallery.html` rewritten (21:19). These captures are ephemeral / gitignored by design; the human fidelity sign-off against the mocks is the orchestrator's checkpoint, NOT self-certified here.
- **Mechanical smoke check** (not a fidelity judgment): the settled shot shows the browser chrome (dots · `apple-reference-prototype.html` · v1 · 100% · open) + the "RENDERS AS" Auto/Prototype pills wrapping the reused PrototypePreview; the live shot shows "building deliverable-v1…" + the sweeping progress bar + the calm building state. The chrome mounts and wraps correctly.

## Requirement Status

- **RUNUI-07** (net-new as-is affordances): **CLOSED** — the "Renders as" deliverable-type switch is the last of RUNUI-07's affordances (Share + Version ▾ landed 39-05).
- **RUNUI-06 / RUNUI-08** (run screen matches its mock / renderers reused): already Complete (39-01); this surface delivers their Preview half.

## Threat Flags

None — no new network endpoint, auth path, or trust-boundary surface. T-39-06-01 (XSS via chrome-wrapped HTML): mitigated — the chrome is a passive frame; the sandboxed-iframe contract stays with the untouched renderers. T-39-06-02 (URL-bar filename XSS): mitigated — the filename renders as escaped React text; no `dangerouslySetInnerHTML` in the chrome (grep 0). The `handlePreviewOpen` blob-open is client-only (no network). T-39-06-SC: no package-manager installs in this plan.

## Known Stubs

None. The "100%" zoom label is a static composition element (the mock shows it static too — not a live zoom control); the open-in-new is wired to a real client-only blob open. Everything else is live (filename, version, typed-renderer set, streaming state).

## Next Phase Readiness

- The Preview surface is built + captured; the regenerated `preview__settled` / `preview__live` gallery pairs are ready for the human fidelity sign-off against `Hexaware Run.dc.html` / `Hexaware Run - Live.dc.html` (orchestrator's blocking checkpoint — NOT self-certified, and NOT pushed).
- **This is the FINAL run-screen surface** (39-01..39-06 done). After the human approves the Preview fidelity, the phase's remaining thread is RUNUI-09's broader mocked-e2e "suite green" half (D-39-07-1 — the suite is still systemically stale vs feat/ui-2; each surface wave re-anchored only its own specs).

## Self-Check: PASSED

- `PreviewChrome.tsx` present (created); `PreviewPanel.tsx` + `PreviewPanel.test.tsx` present and modified; `zzz-baseline.spec.ts` modified (capture-infra).
- Commits `704919e0` (feat) + `3edf4c8c` (test) exist on `feat/ui-2` (verified via `git log`).
- Verification observed: tsc 0 errors (touched files), vitest 8/8, all four grep guards pass, captures regenerated (5 passed; preview settled+live rewritten 21:17; gallery 3 pairs 21:19).

---
*Phase: 39-run-screen-mock-fidelity-b5*
*Completed: 2026-07-11 — human fidelity sign-off pending (orchestrator checkpoint)*
