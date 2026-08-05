---
id: REQ-28
type: req
status: done
area: [sse, workflow, agents]
summary: >-
  Configure Unification + Composer Rebuild (Phase 41 [B7])
source: .planning/REQUIREMENTS.md#configure-unification-composer-rebuild-phase-41
covers: [UI-SPEC]
---

### Configure Unification + Composer Rebuild (Phase 41 [B7])

The two structural REBUILDS Phase 40 deferred — the unified **Configure** screen
and the full-page **Composer** (Simple + Canvas) — to mock/proposal fidelity, plus
the harness that unblocks their fidelity gates. Closes SHELL-04. Intended
divergences ND-AE..AJ (see `41-UI-SPEC.md` / `assemble-phase41-gallery.mjs`).

- [ ] **CFGUI-01**: The unified one-screen Configure surface — Step-1 brief + four accordions (Templates · Design System · Review Gates · Workflow Settings) + overlays — matches the mock (screenshot-diff + HUMAN sign-off), closed to the ND-AE..AI register.
- [ ] **CFGUI-02**: ConfigureScreen revived as the SINGLE Configure screen with a real `onLaunch` through the existing `onStartPipeline` seam + in-app nav; the overlapping Configure code in IdeaInputPage (brief-launch) + LaunchWizard + WizardStepper is DELETED — no dual Configure implementation survives (INV-3).
- [ ] **CMPUI-01**: The Composer is a full-page surface with entry from Home + edit-from-My-Workflows and a Simple⇄Canvas toggle, bound to the AgentsPopup shared data model; the modal shell is replaced (INV-3).
- [ ] **CMPUI-02**: The Simple view matches `Hexaware Composer.dc.html` — identity card + reorderable agent rows + model picker + override chips + custom prompt + capability palette + skills & hooks + summary rail (screenshot-diff + HUMAN sign-off).
- [ ] **CMPUI-03**: The hand-rolled node-graph Canvas view matches the APPROVED proposal `composer-canvas-proposal.html` — design-match HUMAN sign-off (ND-AJ); no graph library (D-CMP-CANVAS).
- [x] **CMPUI-04**: Run-once launches through the existing `onStartPipeline` seam (functional test) + Save-to-catalogue reuses `createUserWorkflow`; no engine/backend/manifest change, no fabricated cost (ND-AG). *(41-06, commit 19f9fdf7 — composer-run.spec.ts mocked 2/2 green)*
- [ ] **CMPUI-05**: The Library agent-detail right-drawer rebuilt from AgentCapabilitiesModal — closes SHELL-04's Agent-drawer clause (ND-Z).
- [ ] **HARN-01**: The Configure template/DS/ppt APIs stubbed + seeded (opt-in) + the Phase-41 fidelity oracle formalized (repo-relative, per-surface `--surface`-regenerable, carrying ND-AE..AJ + a Canvas design-match target).

## Milestone v3.0 Requirements — Top-Tier Resume & Durable Execution

> POR: `.planning/RESUME-CAPABILITY-DESIGN-DRAFT.md` (all 7 design decisions LOCKED §8; LOCK-E/ND-4 supersede record §8.1). Continues the v1.0 RESUME-01..04 family. Substrate = `artifact_refs` (NOT git — Q1); cursor computed by the KERNEL, never an agent; every phase golden-safe (INV-3), additive-only (Q3), kernel name-free (INV-1/SC-001), single-dispatch-path (INV-12), deepagents-only (INV-13).
