# Phase 41: Configure Unification + Composer Rebuild — UI Design Contract

**Created:** 2026-07-13
**Status:** Ready for planning
**Design source of truth:** the mock/proposal files ARE the contract (rendered, not paraphrased). This spec pins the tokens, the per-surface fidelity target, the intended divergences (ND-A..D carried + ND-AE..AJ new), and the acceptance oracle. Sibling of `40-UI-SPEC.md`.

## Source of truth
- **CONFIGURE + ND-Z drawer:** `Hexaware Workspace v2.dc.html` — `isConfig` (~:166) + `overlayTemplate` (:827) · `overlayDs` (:858) · `overlayGates` (:876) · `modalWorkflow` (:776); Library agent-detail `drawerOpen` (:709).
- **COMPOSER Simple view:** `Hexaware Composer.dc.html` (full-page).
- **COMPOSER Canvas view:** `composer-canvas-proposal.html` (the APPROVED proposal — a design REFERENCE, not a `.dc.html` mock; ND-AJ).
- Surface → component map + rebuild approach + blockers: `/Users/1000060523/.claude/jobs/e660aea4/tmp/phase41-scope/SURFACE-MAP.md`.
- Reviewed baseline gallery (Configure + Composer mock-vs-current + the four overlays + the Canvas proposal embedded live): `/Users/1000060523/.claude/jobs/e660aea4/tmp/phase41-scope/gallery-phase41.html`.
- When a value is ambiguous, read the `.dc.html` / proposal source — it carries the exact hex, weight, size, spacing, and DOM structure.

## Design tokens (reuse Phase 32/35/39/40 — do NOT introduce a new system)
- **Type:** Manrope (UI/headings), serif for display h1s — already loaded. Keep the existing `font-serif` display h1 convention.
- **Palette:** paper `#F0EEE7`/`surface-paper`; card `surface-card`; ink ramp `ink-300..900`; single accent purple `#3C2CDA`/`brand`; hairlines `line-border`/`line-divider`; semantic passed/warn/failed. The Canvas proposal's `:root` (in `composer-canvas-proposal.html`) maps 1:1 to these tokens (brand `#3C2CDA`, paper `#F0EEE7`, card `#FCFBF7`, warm `#F6F4EE`, amber gate `#9A6B1E`). Route ALL new chrome through the existing tokens — no raw hex unless a token is genuinely absent (add a token instead).
- **Geometry:** cards ~10–14px radius; the Phase-35 dark top bar + nav pill + profile menu are the shell chrome and are NOT re-restyled here (Composer/Configure are hidden-global-nav surfaces per the mock, but the app's shell chrome stays). Canvas nodes = 178px cards; SVG bezier edges with arrow markers (`marker#arw` grey / `marker#arwb` brand) per the proposal.

## Per-surface fidelity (target → current). Full gap list in `41-CONTEXT.md` `<specifics>` + SURFACE-MAP §3.
1. **CONFIGURE (one screen)** → replace the three split impls with ONE: header bar (back · eyebrow · "Configure your run" · Save draft · Start run →) + always-open Step-1 brief card (Attach, no Voice [ND-AI], ⌘Enter send) + four accordions (Templates · Design System · Review Gates · Workflow Settings) each with a live "Currently using: X" summary line + a Browse/Open overlay. Templates/DS gated on declared `opendesign` (ND-AE); selections live + "None selected" until picked (ND-AF). Reuse the shipped bodies (TemplateGallery / DesignSystemPicker / ReviewGatesSection / AdvancedExpander) verbatim.
2. **COMPOSER Simple view** → full-page identity card (Name / Deliverable-type read-only [ND-AH] / Description) + reorderable agent rows (index · avatar · name · Core badge · role · inline model picker · Validator/Gate/Retry chips · Custom-prompt → · remove) + Capability palette + Skills & hooks + sticky Summary rail (agents · gates · strategy · est. duration [live] · declared caps · Save-to-catalogue · Run once). No fabricated cost (ND-AG). Bound to the AgentsPopup shared data model (no data rework).
3. **COMPOSER Canvas view** → the approved proposal: dot-grid + `<svg>` bezier edges (arrow markers, active edge brand) + Brief trigger pill + absolute 178px agent nodes (left→right sequential) + ports + +-insert on edges/at chain-end + zoom/Fit + a right rail (selected-node config: Model / Overrides / Custom-prompt) + a docked Run summary. Hand-rolled (D-04). Acceptance = match-the-proposal (ND-AJ).
4. **Library agent-detail drawer (ND-Z)** → the mock's right-side Overview/Skills/Hooks/Config drawer, rebuilt from `AgentCapabilitiesModal`; closes SHELL-04's Agent-drawer clause.

## INTENDED-DIVERGENCE REGISTER (the canonical list is finalized in `assemble-phase41-gallery.mjs`)
Every deliberate departure from the mock is registered here. A screenshot-diff that flags one of these is CLOSED, not a failure; any OTHER visual departure is a fidelity bug. Phase 41 CONTINUES the lettering at **ND-AE** (ND-A..D carried from Phase 39; ND-W..AD are Phase 40's — never reuse).

| # | Divergence | Mock says | We ship | Why |
|---|-----------|-----------|---------|-----|
| **ND-A** | Brand wordmark | "HEXAWARE" | "VelocityAI" | product brand (SC-001) — carried |
| **ND-B** | Catalogue nav label + surface title | "Catalogue" | "My Workflows" | D-11 (Catalogue reserved for the future marketplace) — carried |
| **ND-C** | Nav active-state | mock's pill-fill | purple underline | ND-13.1 — carried |
| **ND-D** | All data | hardcoded rows/counts | LIVE data; empty→W1 seed for the diff only | SC-001 — carried |
| **ND-AE** | Configure Templates/Design-System accordions | mock always renders all four accordions | Templates + Design System render ONLY when the deliverable declares the `opendesign` context provider; a user_stories/custom run shows only Review Gates + Workflow Settings | SC-001 — ConfigureScreen already gates on the declared signal (`acceptsTemplateDs` :132) |
| **ND-AF** | Configure selections | fabricated "Currently using: Analytics Hub / Ink & Alabaster / 150 systems / 8 capabilities" | bound to the LIVE template/DS/capability registries; reads "None selected" until picked | SC-001 (a specialization of ND-D) |
| **ND-AG** | Composer Run cost + primary action | Summary rail shows "Est. cost $4.50" + "Run once now" launching from the composer | est. cost OMITTED (no metering — parallel to ND-AC); Run routes through the real `onStartPipeline` seam; est. **duration** IS derived live from per-agent `estimated_duration` | SC-001 (never fabricate consumption numbers) |
| **ND-AH** | Composer "Deliverable type" | an editable identity-card dropdown | `base_pipeline_type` fixed at composer entry → rendered read-only (the composer composes AGENTS; the deliverable family is chosen upstream on Home) | SC-001 / composer scope |
| **ND-AI** | Configure Step-1 brief affordances | Attach + **Voice** | Attach only | no product voice-input capability (carries ND-X) |
| **ND-AJ** | Composer Canvas reference | the Canvas view has NO shipped `.dc.html` mock | acceptance = match-the-**approved-proposal** (`composer-canvas-proposal.html`), a design reference; the gate is a design-match human sign-off, not a mock-fidelity screenshot-diff | the Canvas view was designed + user-approved as a proposal, not shipped in the DC mock |

## Acceptance oracle (the gate — not prose)
- **Mock-fidelity surfaces (Configure, Composer-Simple, ND-Z drawer):** proven by the **side-by-side Phase-41 gallery** (`gallery-phase41.html`), per surface + per overlay/state, closed to this register, with a blocking **`checkpoint:human-verify`** on the images. Regenerate the surface's section each wave via the oracle: our side `SHELL_CAPTURE=1 npm --prefix frontend run e2e -- zzz-shell-baseline`, the target side `node frontend/e2e/fidelity/capture-shell-mocks.mjs` (already captured), then `node frontend/e2e/fidelity/assemble-phase41-gallery.mjs --surface <name>`. NO automated pixel-diff (ND-D live data ≠ the mock's fixed values).
- **Composer-Canvas (ND-AJ):** proven by a blocking **`checkpoint:human-verify`** whose reference is the APPROVED PROPOSAL (`composer-canvas-proposal.html`), rendered SIDE-BY-SIDE with a fresh capture of our built canvas — acceptance is "matches the approved proposal," not a `.dc.html` mock.
- **Run-wiring (D-05):** proven by an automated **functional** test (mocked-e2e) that "Run once" fires `onStartPipeline` with the composed type + agent ids and lands on the run screen — the ONE functional (non-presentation) gate.
- Standard technical checks additionally per plan: `npx tsc --noEmit` clean; targeted vitest for each touched component green; touched mocked-e2e specs re-anchored green (incl. the Phase-39/40-deferred `ts-e.model-picker` re-anchor, which lands here since it is Composer/agent-config territory).

## Open questions for the orchestrator (planner rulings, confirm or override)
- **D-01 mechanism:** the planner mounts the unified Configure as a `mainView="configure"` surface (funnels `onLaunch` straight into `onStartPipeline`, no sessionStorage-draft bridge, matches the mock's shell-state machine). Override to keep it on the `/workflow/configure` route (would keep the draft→/dashboard bridge) if a standalone route is required.
- **D-03 mechanism:** the planner mounts the Composer as a `mainView="composer"` surface (consistent with `input`/`execution`). Override to a dedicated `/workflow/compose` route if a shareable composer URL is required.
- **ND-AJ:** the planner treats the Canvas gate as proposal-match (not mock-fidelity). This is settled by D-CMP-CANVAS + the user-approved proposal.

---
*Phase: 41-configure-composer-rebuild-b7 · UI design contract*
</content>
