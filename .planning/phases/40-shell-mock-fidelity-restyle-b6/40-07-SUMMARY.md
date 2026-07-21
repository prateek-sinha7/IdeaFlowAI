---
phase: 40-shell-mock-fidelity-restyle-b6
plan: 07
subsystem: frontend-shell
tags: [ui-fidelity, catalogue, saved-workflows, restyle, shell-mock]
requires: ["40-01"]
provides: ["My Workflows (Catalogue) surface at mock parity — the saved-workflow card grid, search-filtered state, and zero/empty state, over the live/stubbed /api/user-workflows data, no longer crashing in mocked mode"]
affects:
  - frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx
tech-stack:
  added: []
  patterns:
    - "styling parity restyle over unchanged /api/user-workflows (INV-12 — kebab rename/delete, search, saved-workflow launch preserved)"
    - "surface unblocked by the 40-01 /api/user-workflows mocked stub (was crashing in mocked mode)"
key-files:
  created: []
  modified:
    - frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx
    - frontend/src/components/savedworkflows/SavedWorkflowsPage.test.tsx
    - frontend/e2e/tests/ts-z2.saved-workflows.spec.ts
    - frontend/e2e/tests/ts-z.catalog.spec.ts
decisions:
  - "The title/nav stays 'My Workflows' (ND-B — the mock's 'Workflow Catalogue' is reserved for the future marketplace, D-11), not the mock's 'Workflow Catalogue'."
  - "The grid is the live/stubbed /api/user-workflows list (ND-D), never the mock's fixed saved-workflow set; the 40-01 stub unblocks the previously-crashing mocked surface."
  - "The mock's header '+ New workflow' CTA is NOT shipped on this surface (ND-AD) — the create-workflow entry lives on Home and the full Composer is the Phase-41 rebuild; we do not ship a dead/duplicate CTA (SC-001)."
metrics:
  duration: ~25m
  completed: 2026-07-12
---

# Phase 40 Plan 07: My Workflows (Catalogue) Parity Summary

Brought `SavedWorkflowsPage` to visual parity with the `Hexaware Workspace v2.dc.html` Catalogue surface — a card-grid restyle over the *unchanged* `/api/user-workflows` data, keeping the app title "My Workflows" (ND-B). The surface was previously crashing in mocked mode; the 40-01 `/api/user-workflows` stub unblocks it. All existing behaviour (kebab rename/delete, search, saved-workflow launch) is preserved.

## What changed

- **SavedWorkflowsPage restyle (commit `f02fc671`):** the saved-workflow card grid (avatar/init, type badge, name, description, agent count + updated time, Run CTA), the search-filtered state, and the zero/empty state aligned to the mock's Catalogue composition, over live/stubbed `/api/user-workflows` (ND-D). The kebab rename/delete, search, and saved-workflow launch behaviour are preserved (INV-12). `ts-z2.saved-workflows` (+ `ts-z.catalog`) re-anchored to the restyled surface.
- **ND-AD register (commit `dbdc5e61`):** the mock's header "+ New workflow" CTA is intentionally omitted (registered) — the create entry lives on Home; the Composer is a Phase-41 rebuild.

## Intended-Divergence register touch

- **ND-A** — brand "VelocityAI" (not "HEXAWARE") in the shell chrome.
- **ND-B** — the title/nav stays "My Workflows", not the mock's "Workflow Catalogue" (Catalogue reserved for the future marketplace).
- **ND-C** — nav active-state = purple underline (not the mock's pill-fill).
- **ND-D** — the grid is the live/stubbed `/api/user-workflows` list, never the mock's fixed saved-workflow set.
- **ND-AD** — the mock's header "+ New workflow" CTA is not shipped here (create lives on Home; Composer is Phase-41); no dead/duplicate CTA.

## Regenerated gallery (`--surface catalogue`)

Current-side captures refreshed via `SHELL_CAPTURE=1 npx playwright test --project=mocked zzz-shell-baseline`; pairs assembled via `assemble-shell-gallery.mjs --surface catalogue`. Eyeballed vs the mock Catalogue grid (populated / filtered / empty).

## Verification results

- `npx tsc --noEmit` — 0 errors.
- `npx vitest run SavedWorkflowsPage.test.tsx` — green (kebab rename/delete, search, launch contracts).
- `npx playwright test --project=mocked ts-z.catalog ts-z2.saved-workflows` — 5/5 green (compose→Save→appears→rename→launch; the mocked surface no longer crashes).

## Deviations from Plan

None — the surface was restyled as written; the omitted "+ New workflow" CTA is a pre-declared intended divergence (ND-AD), not a deviation.

## Known Stubs

None. The grid binds to the live/stubbed `/api/user-workflows` list. The omitted "+ New workflow" CTA is a registered intended divergence (ND-AD), not a stub.

## Checkpoint

The My Workflows (Catalogue) surface (commit `f02fc671`) was handed to the human reviewer at the plan's blocking `checkpoint:human-verify` and **approved**.
