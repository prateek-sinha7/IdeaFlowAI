---
id: REQ-23
type: req
status: done
area: [workflow, artifacts]
summary: >-
  Run-Screen Mock Fidelity (Phase 39)
source: .planning/REQUIREMENTS.md#run-screen-mock-fidelity-phase-39
---

### Run-Screen Mock Fidelity (Phase 39)

- [x] **RUNUI-06**: Every run-screen surface (left lane, run header, Preview/Steps/Files/Audit + all sub-navigation) matches its VelocityAI-New-UI mock across settled/live/failed to the intended-divergence register — proven by a side-by-side screenshot-diff gallery + human sign-off, not a prose claim (Phase 39 SC-1)
- [x] **RUNUI-07**: Net-new as-is affordances land — Share (client-only link), the Version ▾ menu (from `runFamily`), the "Renders as" deliverable-type switch, and the fuller Audit categories (secret-scan / performance / behavioral) (Phase 39 SC-2)
- [x] **RUNUI-08**: Data stays real & live (SC-001) — no cloned mock values; the deliverable renderers are reused not rebuilt; intended divergences (VelocityAI / My Workflows / nav underline) preserved (Phase 39 SC-3)
- [ ] **RUNUI-09**: The mocked e2e suite is green again against feat/ui-2 (home-grid / launch-flow / run-family fixes) and the fidelity screenshot harness + side-by-side gallery run under `frontend/e2e` (Phase 39 SC-4)
