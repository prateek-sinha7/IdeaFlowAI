---
phase: 40-shell-mock-fidelity-restyle-b6
plan: 02
subsystem: frontend-shell
tags: [ui-fidelity, home, restyle, shell-mock]
requires: ["40-01"]
provides: ["Home landing restyled to the Hexaware Workspace v2 mock — prompt-under-h1 (Attach + Build, no Voice), a live-data 3-column deliverable card grid, and a live 'Jump back in' recents strip"]
affects:
  - frontend/src/components/catalog/HomeLaunchGrid.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
tech-stack:
  added: []
  patterns:
    - "mock-composition restyle over live endpoints (GET /api/workflows deliverable rows + GET /api/runs recents) — data-driven, never the mock's fixed labels (ND-D)"
    - "prompt relocated UNDER the h1 as a slot into HomeLaunchGrid; the DashboardLayout home branch simplified to mount HomeLaunchGrid with prompt/recents props (superseded prompt box + recents strip removed — INV-3)"
key-files:
  created: []
  modified:
    - frontend/src/components/catalog/HomeLaunchGrid.tsx
    - frontend/src/components/catalog/HomeLaunchGrid.test.tsx
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/e2e/tests/ts-b.selection.spec.ts
    - frontend/e2e/tests/ts-c.input-trigger.spec.ts
decisions:
  - "Adopted the mock composition: eyebrow (ND-A 'VelocityAI') → h1 → the prompt input WITH an Attach button + a primary Build submit (NO Voice — ND-X, there is no product voice-input capability) → the 'Or start from a deliverable' card grid → the 'Jump back in' recents strip."
  - "The deliverable rows became a live-data 3-column CARD grid from GET /api/workflows (ND-D) replacing the vertical divide-y list; count/labels are data-driven (a 7th live row → 7 cards), never the mock's fixed 6. The existing launch fork, tier gating, SURF-03 inspect, and the Phase-38 real per-card estimate are preserved."
  - "The 'Jump back in' recents strip is sourced from the live GET /api/runs list (reusing WorkflowHistory's WorkflowRun shape — no new endpoint); it is absent/graceful when there are no runs (ND-D — never a fabricated placeholder)."
  - "The DashboardLayout home branch was simplified to mount HomeLaunchGrid with the prompt/recents props, removing the superseded prompt box + separate recents strip (INV-3 — no dual Home composition)."
  - "ts-b/ts-c re-anchored to the card-grid layout (card selection launches; the concrete Mulesoft migration input drives ts-c); the removed migration meta-picker was flagged, not silently weakened."
metrics:
  duration: ~40m
  completed: 2026-07-12
---

# Phase 40 Plan 02: Home Surface Restyle Summary

Restyled the Home landing to the `Hexaware Workspace v2.dc.html` Home surface — the prompt moves UNDER the h1 with an Attach + primary Build action row (no Voice — ND-X), the deliverables become a live-data 3-column card grid bound to `GET /api/workflows` (ND-D), and a live "Jump back in" recents strip renders from `GET /api/runs`. Every existing behavior — the SC-001 data-driven launch fork, tier/lock gating, the Phase-38 real per-card estimate, and saved-workflow launch — is preserved; the two Home mocked-e2e specs (ts-b/ts-c) are re-anchored green to the new grid.

## What changed

- **Prompt relocated + restyled:** moved the `home-launch-prompt` from ABOVE the h1 to UNDER it, restyled to the mock's input shell with an **Attach** affordance + a primary **Build** submit button (NO Voice — ND-X). Build carries the brief text down the existing launch fork (`handleHomeSelectFeature`), wiring unchanged.
- **Deliverable card grid:** the vertical `divide-y` row list became a responsive 3-column card grid from the live `GET /api/workflows` fetch (ND-D). Each card carries the row's display name, description, the Phase-38 real estimate (`~N agents · ~Xm`), and the lock/allowed state; the whole card is the click target → `onSelectFeature(row.id)`.
- **"Jump back in" recents:** a live strip of the N most-recent runs from `GET /api/runs` (title · humanized type · relative time · status), each deep-linking to its run; absent when there are no recents (ND-D — never fabricated).
- **DashboardLayout simplification:** the home branch now mounts `HomeLaunchGrid` with the prompt/recents props, removing the superseded prompt box + separate recents strip (INV-3).
- **e2e re-anchor:** `ts-b.selection` (card-grid selection → launch) and `ts-c.input-trigger` (the concrete Mulesoft migration input → execution swap) re-anchored to the redesigned layout; behavioral assertions unchanged (the removed migration meta-picker flagged, not weakened).

## Intended-Divergence register touch

This surface exercises (all pre-registered — no new ND letter added; the canonical register lives in the 40-01-owned `assemble-shell-gallery.mjs`, untouched by this plan):
- **ND-A** — brand eyebrow "VelocityAI" (not the mock's "HEXAWARE").
- **ND-D** — the deliverable cards + recents come from LIVE `/api/workflows` + real recent runs, never the mock's fixed 6 labels / hardcoded recents.
- **ND-X** — the mock's prompt "Voice" affordance is NOT reproduced (there is no product voice-input capability); Attach IS reproduced as it is a real image-input feature.

## Regenerated gallery (`--surface home`)

The Home sections (`home__shell`, `home__shellfull`) were regenerated into `frontend/e2e/fidelity/gallery-shell.html` at the plan's checkpoint — current side via `SHELL_CAPTURE=1 npx playwright test --project=mocked zzz-shell-baseline`, target side from 40-01, assembled via `assemble-shell-gallery.mjs --surface home`.

## Verification results

- `npx tsc --noEmit` — 0 errors.
- `HomeLaunchGrid.test.tsx` — green (grid card count from live rows + the Build submit + no-Voice + recents present/absent cases).
- `ts-b.selection` + `ts-c.input-trigger` (mocked project) — re-anchored green to the card-grid Home.
- No package-manager installs (reuses lucide-react + tokens).

## Deviations from Plan

None material — the plan executed as written. The removed migration meta-picker (an artifact of the pre-grid layout) was surfaced to the reviewer at the checkpoint rather than silently dropped; ts-c was re-anchored to the concrete Mulesoft migration input instead.

## Known Stubs

None. The deliverable cards and recents are both live-data (ND-D); empty states are graceful (the recents strip is absent when there are no runs), not stubbed placeholders.

## Checkpoint

Task 3 was a blocking `checkpoint:human-verify` — the regenerated Home gallery (`home__shell` / `home__shellfull`) was handed to the reviewer and **approved**, closed to ND-A / ND-D / ND-X.
