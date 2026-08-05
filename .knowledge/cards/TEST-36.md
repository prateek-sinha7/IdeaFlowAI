---
id: TEST-36
type: test
status: done
area: [sse, workflow, agents, artifacts]
summary: >-
  TS-U — Revision runs (F2 end-to-end) — the real revision loop (Phase 14/15)
source: .planning/TEST-REGISTER.md#ts-u-revision-runs-f2-end-to-end-the-real-revisi
covers: [TS-U-01, TS-U-02, TS-U-03, TS-U-04, TS-U-05, TS-U-06, TS-U-07, TS-U-08]
---

### TS-U — Revision runs (F2 end-to-end) — the real revision loop (Phase 14/15)

The revision loop must be tested end-to-end per workflow. A revision dispatches **real** agents (a model runs), produces a **revised** deliverable (not the instruction echo), persists `derived_from` lineage, and bypasses clarify.

| ID | Title | Steps | Expected | Status |
|---|---|---|---|---|
| TS-U-01 | **od_ppt revise (SC1)** | from a completed od_ppt run, click revise, enter `Add a slide about ROI` | a **revision run streams** (real agent cards/output) → revised deck in `Slide Deck Preview`; existing deck stays visible until new output (section contract — content not cleared for `*_revision`) | ✅ (S03 live, 118 frames) |
| TS-U-02 | No clarify on revision (A1) | observe a revision run | **zero** `questionnaire_ready` frames (manifest `planner: skip`); no clarify form | 🟡 (live: 0 across 4) |
| TS-U-03 | Lineage (SC2) | after a revision completes | persists a `derived_from` ref to the parent (owner/workspace-scoped, exact kind); a **failed** revision writes NOTHING (no poisoned parent) | 🟡 |
| TS-U-04 | Revision-of-revision | revise a revision | resolves via FR-014 chain link 1; produces a 2nd revised deliverable | 🟢 / 🔴 UI |
| TS-U-05 | Terminal fidelity (SC4) | drive a revision to each outcome | row lands `completed`/`degraded`/`failed`/`cancelled` correctly — **never stuck `revising`**; a failed revision is not offered as a future parent | 🟡 |
| TS-U-06 | Surgical-diff prototype revise | revise a prototype with `Add a Reports page` | agent returns only changed sections; engine merges into full HTML; updated prototype renders | 🔴 |
| TS-U-07 | User-story / app revise | revise via the per-preview `Revise` bars | each preview's revision input (exact placeholders per type) + `Revise` button starts a `*_revision` run | 🔴 |
| TS-U-08 | Reconnect during revision (WR-03) | reload mid-revision | live-attach frames carry `section` = `{base}_output`; panels rebuild | 🟡 (29 frames ✅) |
