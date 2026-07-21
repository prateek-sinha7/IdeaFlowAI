# Phase 41: Configure Unification + Composer Rebuild [B7] — Context

**Gathered:** 2026-07-13
**Status:** Ready for planning
**Source:** Orchestrator scoping pass (read-only surface map + reviewed Phase-41 baseline gallery + the committed Phase-40 shell fidelity oracle + the USER-APPROVED Composer Canvas proposal). Follows the plan-ingestion preference: the scope + the five decisions are SETTLED — copy them faithfully; skip interactive re-discovery/research. This is the second-and-final fidelity phase of the shell milestone (B-series): it delivers the TWO structural REBUILDS Phase 40 explicitly deferred.

<domain>
## Phase Boundary

Phase 41 delivers the two **structural REBUILDS** (not restyles) Phase 40 deferred (see `40-CONTEXT.md` `<deferred>`):

1. **CONFIGURE — unify the split flow into the mock's ONE "Configure your run" screen.** Today the mock's single screen is split across THREE components on TWO routes with THREE reachabilities: `IdeaInputPage.tsx` (LIVE, `/dashboard` brief path), `LaunchWizard.tsx` (LIVE, `/workflow/create` od_ wizard), `ConfigureScreen.tsx` (DORMANT, `/workflow/configure` accordion surface — structurally CLOSEST to the mock but reached by NO in-app nav and its Launch is a no-op). Rebuild into ONE screen: an always-open **Step-1 brief card** + four inline **ADVANCED CONFIGURATION** accordions (Templates · Design System · Review Gates · Workflow Settings), each with a live "Currently using: X" summary line + a Browse/Open overlay. MOCK-FIDELITY.

2. **COMPOSER — a full-page custom-workflow surface with a Simple ⇄ Canvas view toggle**, both bound to `AgentsPopup.tsx`'s existing agent/model/override/summary data model. Today the composer is an `AgentsPopup` MODAL off "Advanced". Rebuild as a full page:
   - **Simple view** = MOCK-FIDELITY to `Hexaware Composer.dc.html` (identity card + reorderable agent rows + inline model picker + Validator/Gate/Retry override chips + Custom-prompt + Capability palette + Skills & hooks + sticky Summary rail).
   - **Canvas view** = a hand-rolled node-graph visual designer, **already designed + USER-APPROVED**. Its build spec is the static mockup `composer-canvas-proposal.html` — that proposal (NOT a `.dc.html` mock) is the acceptance reference. Nodes = the agent list, node config → a right config-rail (`SelectionsMap[id]` + prompt override), edges = sequential order, docked Run summary.

The Library agent-detail **drawer** (Phase-40 ND-Z deferral — the mock's right-side Overview/Skills/Hooks/Config drawer, currently the shared `AgentCapabilitiesModal`) also lands here (it closes SHELL-04's Agent-drawer clause).

**Target references (the literal spec):**
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Workspace v2.dc.html` — the `isConfig` surface (~:166) + the four overlays (`overlayTemplate` :827 · `overlayDs` :858 · `overlayGates` :876 · `modalWorkflow` :776) = the CONFIGURE spec; the `drawerOpen` Library agent-detail drawer (:709) = ND-Z.
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Composer.dc.html` — the full-page COMPOSER **Simple view** spec.
- `/Users/1000060523/.claude/jobs/e660aea4/tmp/phase41-scope/composer-canvas-proposal.html` — the APPROVED **Canvas view** build target (a design reference, not a mock).
</domain>

<decisions>
## Implementation Decisions (SETTLED 2026-07-13 by the user — do NOT re-open)

Each carries a numeric id (for decision-coverage traceability) and its scoping mnemonic.

### D-01 (D-CFG-ROUTE) — Configure unification target
Revive the DORMANT `ConfigureScreen.tsx` (it already has the four accordions, declared-signal-gated, draft-backed) as the ONE unified "Configure your run" screen; wire in-app nav to it and give it a REAL `onLaunch` through the EXISTING launch seam (`onStartPipeline` → `startPipeline`, `dashboard/page.tsx:1451`). **DELETE** the overlapping Configure code in `IdeaInputPage.tsx` (brief-launch path) + `LaunchWizard.tsx` + `WizardStepper.tsx` — no dual Configure implementation survives (INV-3, no shadow). Concrete target: mount `ConfigureScreen` as a `mainView="configure"` surface inside `DashboardLayout` (mirrors the existing `input`/`execution` surfaces + the mock's hidden-global-nav shell state), so `onLaunch` funnels straight into `onStartPipeline` with no sessionStorage-draft bridge.

### D-02 (D-CFG-STUBS) — harness stubs for Templates/Design-System
A harness wave stubs `GET /api/prototype/templates`, `/api/prototype/design-systems`, `/api/ppt/templates` in `e2e/fixtures/mockApi.ts` (+ representative seed rows) so the Templates + Design-System accordions/overlays render in mocked mode for a fair fidelity gate. Mirrors Phase-40's 40-01. Test-only; production still returns real registry data (SC-001/ND-D).

### D-03 (D-CMP-ENTRY) — Composer full-page routing + entry + toggle
The full-page Composer is reached per the mock: Home's "Compose a custom workflow" card (`HomeLaunchGrid`) + edit-from-My-Workflows (`SavedWorkflowsPage` `onLaunchSaved`). Concrete target: a `mainView="composer"` surface in `DashboardLayout`. The **Simple ⇄ Canvas** view toggle lives in the Composer header (per-session state; not persisted).

### D-04 (D-CMP-CANVAS) — hand-roll the Canvas
Hand-roll the canvas: an `<svg>` edge layer (bezier `path`s + arrow markers) UNDER absolute-positioned node `div`s, a linear left→right sequential chain (Brief → agents). **NO graph library** — `package.json` has none (no reactflow/@xyflow/dagre/elkjs/cytoscape/d3/dnd-kit); the approved proposal is itself hand-rolled; a new dep violates "extend, don't replace". `motion` (already installed) is available for interactions. Reuse the existing AgentsPopup native HTML5 drag-reorder pattern.

### D-05 (D-CMP-RUN) — wire Run-once through the existing seam
The Composer's "Run once" launches the composed workflow through the EXISTING `onStartPipeline` seam (lands on the run screen). This is ADDITIVE FE wiring to an existing seam — **NO engine/backend/manifest change, NO new contract, NO fabricated cost** (ND-AG; no metering — parallel to ND-AC). Est. **duration** IS derived live from per-agent `estimated_duration`. This is the ONE non-presentation piece; keep it minimal + additive with its own functional test.

### D-06 (D-CMP-SAVE) — Save-to-catalogue reuses createUserWorkflow
The Composer's Save-to-catalogue reuses the existing `createUserWorkflow` seam (via `NameWorkflowModal`); `base_pipeline_type` is fixed at composer entry (ND-AH — the deliverable family is chosen upstream on Home, not in-composer).

## Claude's Discretion
- Exact component decomposition per surface (new sub-components under `components/workflow/configure/` and `components/workflow/composer/` vs. extending existing), provided the file map is respected and no dual implementation survives (INV-3/INV-12).
- The precise shape of the seeded template/DS/ppt-template rows (representative + test-only, never a production shape).
- Whether `AgentCapabilitiesModal` is restructured in place (inside `AgentsPopup.tsx`) or extracted to a shared module for the ND-Z drawer — as long as the composer sub-components stay reused, not forked.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The design contract (the spec)
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Workspace v2.dc.html` — the CONFIGURE surface (`isConfig` ~:166) + overlays (`overlayTemplate` :827 · `overlayDs` :858 · `overlayGates` :876 · `modalWorkflow` :776) + the Library agent-detail `drawerOpen` (:709, ND-Z).
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Composer.dc.html` — the full-page COMPOSER **Simple view**.
- `/Users/1000060523/.claude/jobs/e660aea4/tmp/phase41-scope/composer-canvas-proposal.html` — the APPROVED **Canvas view** build target (design reference; a copy is embedded live in the baseline gallery).
- `.planning/phases/41-configure-composer-rebuild-b7/41-UI-SPEC.md` — per-surface fidelity spec + the ND-AE..AJ register + the acceptance oracle.
- Scoping surface map (surface→component file:line + rebuild approach + divergences + the five decisions): `/Users/1000060523/.claude/jobs/e660aea4/tmp/phase41-scope/SURFACE-MAP.md`.
- Reviewed baseline gallery (Configure + Composer mock-vs-current, the four Configure overlays, the Canvas proposal embedded live): `/Users/1000060523/.claude/jobs/e660aea4/tmp/phase41-scope/gallery-phase41.html`.

### The fidelity oracle (reuse + extend — the Phase-40 shell oracle + the new Phase-41 assembler)
- `frontend/e2e/fidelity/assemble-phase41-gallery.mjs` (already scaffolded — carries the ND-AE..AI candidates; W1 FORMALIZES it: repo-relative default, `--surface` filter, ND-AE..AJ finalized, current-side tags pointed at the real new surfaces).
- `frontend/e2e/fidelity/capture-shell-mocks.mjs` (TARGET/mock side — already captures `config`/`config-full` + `composer`/`composer-full`; reuse as-is).
- `frontend/e2e/tests/zzz-shell-baseline.spec.ts` (CURRENT/app side, gated `SHELL_CAPTURE=1` — W1 extends it with the Configure + Composer-Simple + Composer-Canvas capture drivers).
- `frontend/e2e/fixtures/{mockApi,dashboard}.ts` (the mocked harness — W1 stubs the template/DS/ppt APIs + seeds here).

### Source files (surface → component map — verified read-only in SURFACE-MAP §2)
- **CONFIGURE:** `components/workflow/ConfigureScreen.tsx` (the accordions Describe :273 / Templates :289 / Design System :297 / Review Gates :309 / Workflow Settings via `AdvancedExpander` :312; `acceptsTemplateDs` gate :132; `ComposedLaunchCommand` :60 + `onLaunch` :81 + `handleLaunch` :238); `app/workflow/configure/page.tsx` (renders ConfigureScreen with NO onLaunch → inert); `components/workflow/IdeaInputPage.tsx` (brief-launch Configure code to DELETE — `handleRun` :347, Advanced→AgentsPopup :795); `components/workflow/LaunchWizard.tsx` + `WizardStepper.tsx` (the wizard Configure code to DELETE).
- **COMPOSER (data owner + exported sub-components):** `components/workflow/AgentsPopup.tsx` — the MODAL `AgentsPopup` (:1747, the shell to REPLACE) + the EXPORTED sub-components to REUSE: `AgentCapabilitiesModal` (:410), `CapabilityPaletteSection` (:1098), `AdvancedExpander` (:1412, per-agent Validator/Gate/Model/Retry → `SelectionsMap`), `SkillsHooksTab` (:790); `AgentPromptSection` (:209, custom prompt); `createUserWorkflow` save (:1781). The agent list + order = the caller's `pipelineAgents`; per-agent model/validators/gates/retry = `SelectionsMap`; `getRole` :132 → the "Core" badge.
- **The launch seam (D-05):** `DashboardLayout.tsx` `onStartPipeline` prop (:66, :281) → wired at `dashboard/page.tsx:1451` → `startPipeline(type, message, agentIds, skills, hooks, extraParams)` (`useWorkflow`); `mainView` union :173 + surface switch :1479+.
- **Entry wiring (D-01/D-03):** `HomeLaunchGrid.tsx` (deliverable cards + the "custom" entry) + `DashboardLayout.tsx` `onSelectFeature` (:849/:929 → `mainView="input"`) + `SavedWorkflowsPage.tsx` `onLaunchSaved` (:359).
- **ND-Z drawer:** `components/library/LibraryPage.tsx` (agent detail → `AgentCapabilitiesModal` :348) + the mock's `drawerOpen` (:709).

### Locked decisions / prior work
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase 39 (ND-A..V + the fidelity oracle method) + Phase 40 (ND-W..AD + the shell oracle + the ND-Z/Configure/Composer deferrals).
- `frontend/e2e/fidelity/assemble-shell-gallery.mjs` — the canonical ND-A..AD register (Phase 41 continues at **ND-AE**).
- `40-UI-SPEC.md` / `40-01-PLAN.md` / `40-03-PLAN.md` / `40-05-PLAN.md` — the plan + oracle-formalization + per-surface-checkpoint templates this phase mirrors 1:1.
- `.planning/REQUIREMENTS.md` — SHELL-04 (Generic Configure surface + Agent drawer + Workflow dialog, PENDING) is CLOSED by this phase; the new B7 requirement family (CFGUI/CMPUI/HARN) is owned by 41-01.
</canonical_refs>

<specifics>
## Per-surface fidelity target (from the reviewed baseline + SURFACE-MAP §3)

1. **CONFIGURE (one screen):** header bar (back · eyebrow · title "Configure your run" · Save draft · Start run →) + Step-1 "① Describe what you're building" brief card (textarea + Attach + no Voice [ND-AI] + ⌘Enter send) + "ADVANCED CONFIGURATION" four accordions each with a live "Currently using: X" summary line + a Browse/Open overlay: Templates → `overlayTemplate` grid; Design System → `overlayDs` grouped chips; Review Gates → `overlayGates` per-agent toggle manager; Workflow Settings → `modalWorkflow` tab-rail (Overview/Skills&Hooks/Capabilities/Context). Templates + Design-System accordions render ONLY when the deliverable declares `opendesign` (ND-AE); selections bind to LIVE registries, "None selected" until picked (ND-AF).
2. **COMPOSER Simple view:** full-page; identity card (Name / Deliverable-type read-only [ND-AH] / Description) + reorderable agent ROWS (up/down + index + avatar + name + Core lock badge + role + inline model picker + Validator/Gate/Retry override chips + Custom-prompt → + remove) + Capability palette card + Skills & hooks card + sticky Summary rail (agents · review gates · strategy · est. duration [live] · declared caps · Save-to-catalogue · Run once). No fabricated est. cost (ND-AG).
3. **COMPOSER Canvas view:** the approved proposal — dot-grid canvas + hint bar + `<svg>` bezier edge layer (arrow markers, active edge brand-tinted) + a dark Brief trigger pill + agent nodes (178px, absolute, left→right; avatar/name/role/Core/model-pill/override-chips/ports) + +-insert on edges + at chain end + zoom/Fit controls + a right rail (config for the selected node: Model / Overrides [Validator/Review-gate/Retry] / Custom-prompt + a docked Run summary). Hand-rolled (ND-AD-style, D-04). Acceptance = **match the approved proposal**, NOT the `.dc.html` mock (ND-AJ).
4. **Library agent-detail drawer (ND-Z):** the mock's right-side Overview/Skills/Hooks/Config drawer, rebuilt from the shared `AgentCapabilitiesModal` (closes SHELL-04's Agent-drawer clause).

## Multi-source coverage audit (all four sources → a plan)

| Source | Item | Covered by |
|--------|------|-----------|
| GOAL (ROADMAP §Phase 41) | Configure one-screen rebuild (mock-fidelity) | 41-02, 41-03 |
| GOAL | Composer full-page Simple ⇄ Canvas rebuild | 41-04, 41-05 |
| GOAL | Wire Run + Save (existing seam, additive) | 41-06 |
| REQ | CFGUI-01 Configure fidelity | 41-02 |
| REQ | CFGUI-02 Configure unification + delete superseded (INV-3) | 41-03 |
| REQ | CMPUI-01 Composer full-page + entry + toggle | 41-04 |
| REQ | CMPUI-02 Composer Simple view fidelity | 41-04 |
| REQ | CMPUI-03 Composer Canvas view (proposal-match) | 41-05 |
| REQ | CMPUI-04 Composer Run + Save | 41-06 |
| REQ | CMPUI-05 / SHELL-04 Library agent-detail drawer (ND-Z) | 41-07 |
| REQ | HARN-01 stubs + oracle | 41-01 |
| RESEARCH (SURFACE-MAP) | hand-roll canvas (no lib); reuse exported sub-components; stubs blocker | 41-01, 41-04, 41-05 |
| CONTEXT | D-01..D-06 (settled) | 41-01..41-06 (cited inline) |

No item is unplanned. Exclusions (not gaps): the run/execution screen (Phase 39) and the six Phase-40 shell surfaces are out of scope; ECS/backend items belong to other milestones.

## Proposed waves (planner refined — see the PLAN files)
- **W1 (41-01) Harness:** stub the template/DS/ppt APIs + seed; formalize the Phase-41 fidelity oracle (repo-relative, `--surface`, ND-AE..AJ, current-side tags for the new surfaces) + a canvas capture target; own the B7 requirement docs. Autonomous.
- **W2 (41-02) Configure screen build:** revive `ConfigureScreen` into the ONE screen (Step-1 brief + four accordions + summary lines + overlays + top header) reusing the shipped bodies; fidelity checkpoint.
- **W3 (41-03) Configure unify + delete:** mount as `mainView="configure"` + real `onLaunch` → `onStartPipeline`; repoint in-app nav; DELETE the IdeaInputPage/LaunchWizard/WizardStepper Configure code (INV-3); reconcile e2e. Autonomous.
- **W4 (41-04) Composer shell + Simple view:** full-page `mainView="composer"` surface + entry (Home card + edit-from-My-Workflows) + Simple⇄Canvas toggle + the Simple (mock) view reusing the exported sub-components; delete the AgentsPopup modal wrapper (INV-3); fidelity checkpoint.
- **W5 (41-05) Composer Canvas view:** the hand-rolled node-graph to the approved proposal; design-match checkpoint.
- **W6 (41-06 ‖ 41-07):** 41-06 Run-once → `onStartPipeline` + Save → `createUserWorkflow` (functional test); 41-07 the Library agent-detail drawer (ND-Z) + fidelity checkpoint. Disjoint files → parallel.
</specifics>

<deferred>
## Deferred Ideas (do NOT plan here)
- Any engine/backend/manifest/migration change, or a new Run contract — the ONLY functional touch is the additive Composer-Run wiring to the EXISTING `onStartPipeline` seam.
- Est. **cost** metering / a real Run-cost number (ND-AG / ND-AC — no metering endpoint exists; never fabricate).
- A recent-runs data wire for the Analytics right-column card (ND-AA follow-up — not this phase).
- Any new graph/dnd dependency (D-04 — hand-roll).
- The run/execution screen (Phase 39) and the six Phase-40 shell surfaces — untouched.
</deferred>

<scope_fence>
## Negative Space / Forbidden (a phase that violates these is NOT done)
- NO engine/backend/manifest/migration change; NO new Run contract. The one functional touch = additive Composer-Run wiring to the EXISTING `onStartPipeline` seam.
- NO new dependency — hand-roll the canvas (D-04); reuse the exported AgentsPopup sub-components (do NOT fork them).
- Do NOT touch the run/execution screen (Phase 39) or the six Phase-40 shell surfaces (Home/Library-except-ND-Z-drawer/Analytics/Settings/History/Catalogue bodies).
- No dual implementations (INV-3/INV-12): DELETE the superseded Configure code (IdeaInputPage brief-launch + LaunchWizard + WizardStepper) and the AgentsPopup MODAL wrapper — no shadows.
- Preserve the intended divergences carried from Phase 39/40 (ND-A brand · ND-B "My Workflows" · ND-C nav underline · ND-D live data · ND-X/AI no Voice) toward the mock.
- Do NOT clone the mock's fabricated selections/counts/cost — bind to LIVE registries + read "None selected"/derive live (SC-001 / ND-AF / ND-AG).
- Every mock-fidelity gate is an EXECUTABLE `checkpoint:human-verify` (blocking) — never a prose self-certify. The Canvas gate's reference is the APPROVED PROPOSAL, not a `.dc.html` mock (ND-AJ).
- Additive only; `feat/ui-2` only (NEVER main/staging); no commit trailer; never push without an explicit go-ahead.

---
*Phase: 41-configure-composer-rebuild-b7*
*Context gathered: 2026-07-13 via orchestrator scoping (plan-ingestion path)*
</scope_fence>
</content>
</invoke>
