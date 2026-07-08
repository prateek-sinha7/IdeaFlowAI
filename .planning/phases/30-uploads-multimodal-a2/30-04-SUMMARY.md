---
phase: 30-uploads-multimodal-a2
plan: 04
subsystem: ui
tags: [react, vitest, canvas, createImageBitmap, image-upload, multimodal]

# Dependency graph
requires:
  - phase: 30-uploads-multimodal-a2
    provides: "the OUT-OF-BAND images payload (D3) attach flow in IdeaInputPage + the retained:false chat-turn image ref (30-03 _persist_chat_message)"
  - phase: 25 (starting-point-card)
    provides: "StartingPointCard run-inputs render surface (Workstream C2)"
provides:
  - "resizeImage: client-side aspect-preserving canvas downscale → bounded base64 (degrade-not-block, no-upscale) wired into the image attach flow"
  - "ND-10 'image not retained' placeholder in StartingPointCard, derived solely from a retained:false image ref (no <img>, no fetch, no durable storage)"
affects: [uploads, multimodal, reopen, image-persistence, Phase-34-live-pass]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Client-side canvas downscale before base64 (createImageBitmap decode + <img> fallback), degrade-not-block to the original file bytes"
    - "Payload-transient attachment ref → honest 'not retained' placeholder (props-only, no byte restoration)"

key-files:
  created:
    - frontend/src/lib/resizeImage.ts
    - frontend/src/lib/resizeImage.test.ts
  modified:
    - frontend/src/components/workflow/IdeaInputPage.tsx
    - frontend/src/components/workflow/IdeaInputPage.imageInput.test.tsx
    - frontend/src/components/results/StartingPointCard.tsx
    - frontend/src/components/results/StartingPointCard.test.tsx

key-decisions:
  - "resize is a CLIENT optimization only — the server _validate_images caps stay authoritative (T-30-12 accept); base64 never enters the brief (D3 unchanged)"
  - "Default maxEdge 1568 (vision-model optimal, keeps a re-encode well under the ~3.75 MB per-image cap); png stays lossless, jpeg/webp re-encode at quality 0.85"
  - "ANY decode/canvas/encode failure degrades to the original file base64 — resizeImage never throws / never blocks the attach"
  - "ND-10 placeholder derived SOLELY from the retained:false image ref — no <img>, no byte fetch, no durable storage (image persistence stays deferred)"
  - "attachmentRefs is an OPTIONAL prop on StartingPointCard — absent/empty leaves the no-attachment path visually unchanged (dormant); the caller-side wiring of run_events refs is out of this plan's file scope"

patterns-established:
  - "Degrade-not-block image transform: try decode+canvas, fall through to FileReader passthrough on any failure"
  - "Honest payload-transient reopen surface: render presence-only placeholders from retained:false refs, never reconstruct bytes"

requirements-completed: [UPLD-04]

# Metrics
duration: ~8 min
completed: 2026-07-08
---

# Phase 30 Plan 04: Client-side image resize + ND-10 not-retained placeholder Summary

**Client-side canvas downscale (aspect-preserving, no-upscale, degrade-safe) wired into the image attach flow before base64, plus an honest "image not retained" placeholder on reopen derived solely from the retained:false attachment ref.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-08T04:09:00Z
- **Completed:** 2026-07-08T04:12:00Z
- **Tasks:** 2
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments
- `resizeImage(file, opts?)` helper: `createImageBitmap` decode (with an `<img>`+onload fallback), aspect-preserving downscale so the longest edge ≤ `maxEdge` (default 1568), png lossless / jpeg-webp bounded-quality re-encode, prefix-stripped base64 output, and a no-upscale passthrough for images already within the bound.
- Degrade-not-block: any decode/context/encode failure resolves to the original file's base64 — never throws, never blocks the attach.
- Wired `resizeImage` into `IdeaInputPage`'s image branch before building the `attachedImages` entry; images still ride OUT-OF-BAND as the `images` payload (D3), base64 never enters the brief, and an image-less run stays byte-identical.
- ND-10 "image not retained" placeholder in `StartingPointCard` (new optional `attachmentRefs` prop): a `{kind:"image", retained:false}` ref renders an `ImageOff` icon + muted text; no `<img>`, no fetch, no durable storage. No-ref / retained / non-image paths are visually unchanged.

## Task Commits

Each task was committed atomically (TDD test+impl per task):

1. **Task 1: Client-side image resize helper wired into the attach flow (UPLD-04)** — `5fc698e6` (feat)
2. **Task 2: ND-10 "image not retained" placeholder on reopen** — `a4843ea6` (feat)

**Plan metadata:** _(this docs commit)_

## Files Created/Modified
- `frontend/src/lib/resizeImage.ts` — client-side canvas downscale → bounded base64 (aspect-preserving, no-upscale, degrade-not-block).
- `frontend/src/lib/resizeImage.test.ts` — downscale / no-upscale passthrough / prefix-strip / degrade specs (mocked `createImageBitmap` + canvas).
- `frontend/src/components/workflow/IdeaInputPage.tsx` — image attach branch now routes through `resizeImage`; out-of-band images payload unchanged.
- `frontend/src/components/workflow/IdeaInputPage.imageInput.test.tsx` — mock `createImageBitmap` (within-bound passthrough) so the existing D3 assertions hold while confirming the attach routes through resize.
- `frontend/src/components/results/StartingPointCard.tsx` — `AttachmentRef` type + optional `attachmentRefs` prop; ND-10 not-retained image placeholder; presence folded into `hasContent`.
- `frontend/src/components/results/StartingPointCard.test.tsx` — placeholder for retained:false image ref (+ no `<img>`), image-only run, pluralization, and unchanged no-ref / retained / non-image paths.

## Decisions Made
- resize is a client optimization only; server caps stay authoritative (T-30-12 accept). No new npm dependencies — platform canvas / `createImageBitmap` APIs only (T-30-SC accept).
- Default `maxEdge` 1568 (vision-model optimal, comfortably under the ~3.75 MB server per-image cap); png lossless, jpeg/webp at quality 0.85.
- ND-10 placeholder is presence-only from the retained:false ref (T-30-13 mitigate) — the UI cannot imply an image was kept.
- `attachmentRefs` is an optional/dormant prop: the caller-side wiring of run_events chat_message refs into StartingPointCard is NOT in this plan's file scope (files_modified = StartingPointCard.tsx + its test only), so it is left for the surface that reopens a run to thread the refs. The component-level honest render + contract are proven here.

## Deviations from Plan

None - plan executed exactly as written. Both tasks were TDD (test + implementation) committed as one atomic feat commit each, rather than split test/feat commits, to keep the task commit atomic as directed by the sequential-executor contract.

## Issues Encountered
- Routing the attach flow through `resizeImage` risked hanging the existing `imageInput` test: in jsdom `createImageBitmap` is undefined, so the `<img>` fallback would never resolve. Resolved by mocking `createImageBitmap` in the imageInput test to return a small within-bound bitmap → resizeImage passthrough reproduces the original base64, keeping the D3 out-of-band assertions exact.

## Deferred / Live-only
- No live-server / e2e / Playwright checks were run (offline verification discipline). The three named vitest files are green offline (16/16). No live-only checks were required for this frontend plan.
- The caller-side wiring that threads a reopened run's `retained:false` image refs into `StartingPointCard.attachmentRefs` (from the durable run_events chat_message rows) is deferred to the surface that owns reopen prop-threading — out of this plan's file scope.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- UPLD-04 delivered; `resizeImage` is available for any other attach surface.
- ND-10 honest placeholder contract is in place at the component level; wiring the refs from run_events on the reopen surfaces can land whenever that surface is next touched.

## Self-Check: PASSED

- Files: resizeImage.ts, resizeImage.test.ts, StartingPointCard.tsx, 30-04-SUMMARY.md all FOUND.
- Commits: 5fc698e6 (Task 1), a4843ea6 (Task 2) both FOUND.
- Verification: `npx vitest run src/lib/resizeImage.test.ts src/components/workflow/IdeaInputPage.imageInput.test.tsx src/components/results/StartingPointCard.test.tsx` → 3 files / 16 tests passed.

---
*Phase: 30-uploads-multimodal-a2*
*Completed: 2026-07-08*
