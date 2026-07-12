---
phase: 40-shell-mock-fidelity-restyle-b6
plan: 05
subsystem: frontend-shell
tags: [ui-fidelity, settings, restyle, shell-mock]
requires: ["40-01"]
provides: ["Account Settings surface at mock parity — Profile / AI Model / Usage & Limits / Constitution tabs, restyled per-tab over live user data (email, plan/tier) + the live model-preference save, never fabricating name/role/organization or usage-metering numbers"]
affects:
  - frontend/src/components/settings/AccountSettings.tsx
tech-stack:
  added: []
  patterns:
    - "styling/label parity restyle over unchanged endpoints (INV-12 — /api/settings/preferences + /api/auth/me contracts untouched; the model-preference save + change-password flow preserved)"
    - "real-data-only fidelity: the mock's fabricated profile + usage fields are omitted, not reproduced (SC-001/ND-D)"
key-files:
  created: []
  modified:
    - frontend/src/components/settings/AccountSettings.tsx
    - frontend/src/components/settings/AccountSettings.test.tsx
decisions:
  - "The 'Limits' tab is relabelled 'Usage & Limits' and the model tab reads 'AI Model' — pure fidelity label alignments to the mock's sub-nav (planner ruling, not a ND)."
  - "The Profile tab renders ONLY fields backed by real user data (email, plan/tier); the mock's name/role/organization fields are NOT reproduced (ND-Y — never fabricate unpersisted data)."
  - "The AI-Model selector stays the existing live-bound <select> dropdown (updatePreferences), not the mock's static radio-card list — the model list is live (ND-D) and the control shape is kept so the pinned save-preference behaviour parity holds (ND-AB)."
  - "The 'Usage & Limits' tab omits the mock's fabricated per-user 'This month' usage bars — there is no usage-metering endpoint, so we render the real plan banner + the live per-plan deliverable-access grid instead of fabricating consumption numbers (ND-AC)."
metrics:
  duration: ~30m
  completed: 2026-07-12
---

# Phase 40 Plan 05: Account Settings Parity Summary

Brought `AccountSettings` to visual parity with the `Hexaware Workspace v2.dc.html` Settings surface — a per-tab styling + sub-nav-label pass over the *unchanged* `/api/settings/preferences` + `/api/auth/me` endpoints. All four tabs (Profile / AI Model / Usage & Limits / Constitution) match the mock composition, but every rendered value stays bound to real user data (email, plan/tier) or the live model list — the mock's fabricated profile fields and per-user usage bars are omitted rather than faked (ND-Y / ND-AC).

## What changed

- **AccountSettings restyle (commit `ba3a0fe9`):** the four-tab shell, form chrome, section spacing/typography, plan banner, and the per-plan deliverable-access grid aligned to the mock. The `Limits` tab is relabelled **"Usage & Limits"** and the model tab reads **"AI Model"** to match the mock's sub-nav. The Profile form is the mock's richer layout but bound only to `email` + `plan/tier`; the change-password flow and the live model-preference save (`updatePreferences`) are preserved unchanged (INV-12).
- **Sub-tab mock-nav label fix (commit `dbdc5e61`):** the AccountSettings test's sub-tab nav labels re-anchored to "AI Model" / "Usage & Limits" (kept the test green against the relabelled tabs).

## Intended-Divergence register touch

- **ND-A** — brand "VelocityAI" (not "HEXAWARE") in the shell chrome.
- **ND-C** — nav/tab active-state = purple underline (not the mock's pill-fill).
- **ND-D** — the AI-Model tab lists the live available models; the plan banner + access grid reflect the real tier — never the mock's hardcoded lists/numbers.
- **ND-Y** — the Profile tab renders only real-data fields (email, plan/tier); the mock's name/role/organization fields are not fabricated.
- **ND-AB** — the AI-Model selector stays the live-bound `<select>` (updatePreferences), not the mock's static radio-card list, so the pinned save-preference behaviour parity holds.
- **ND-AC** — the "Usage & Limits" tab omits the mock's fabricated "This month" usage bars (no usage-metering endpoint); it renders the real plan banner + live per-plan deliverable-access grid instead.

## Regenerated gallery (`--surface settings`)

Current-side captures refreshed via `SHELL_CAPTURE=1 npx playwright test --project=mocked zzz-shell-baseline`; per-tab pairs assembled via `assemble-shell-gallery.mjs --surface settings`. Eyeballed vs the mock Settings surface per tab.

## Verification results

- `npx tsc --noEmit` — 0 errors.
- `npx vitest run AccountSettings.test.tsx` — green (the model-preference save + change-password + tab-nav contracts; the sub-nav labels pinned to "AI Model" / "Usage & Limits").

## Deviations from Plan

None — the surface was restyled as written; the real-data-only omissions (ND-Y/AB/AC) were pre-declared intended divergences, not deviations.

## Known Stubs

None. All Settings values are live (email, plan/tier, model list). The omitted profile/usage fields are registered intended divergences (ND-Y/AC), not stubs — a usage-metering wire would be a future phase.

## Checkpoint

The Settings surface (commit `ba3a0fe9`) was handed to the human reviewer at the plan's blocking `checkpoint:human-verify` and **approved**.
