# Phase 40: Shell Mock Fidelity — UI Design Contract

**Created:** 2026-07-12
**Status:** Ready for planning
**Design source of truth:** the mock files ARE the contract (rendered, not paraphrased). This spec pins the tokens, the per-surface fidelity, the intended divergences (ND-A..D carried + ND-W..Z new), and the acceptance oracle. Sibling of `39-UI-SPEC.md`.

## Source of truth
- `Hexaware Workspace v2.dc.html` — the shell state machine (Home / Library +sub-tabs +agent-drawer / Catalogue / History / Analytics / Account Settings +tabs), under `/Users/1000060523/Documents/Work/VelocityAI-New-UI/`.
- Reviewed baseline gallery (mock vs current, 32 pairs): `/Users/1000060523/.claude/jobs/e660aea4/tmp/phase40-scope/gallery-shell.html`.
- Surface → component map + blockers: `/Users/1000060523/.claude/jobs/e660aea4/tmp/phase40-scope/SURFACE-MAP.md`.
- When a value is ambiguous, read the `.dc.html` source — it carries the exact hex, weight, size, spacing, and DOM structure.

## Design tokens (reuse Phase 32/35 — do NOT introduce a new system)
- **Type:** Manrope (UI/headings), Heebo/serif (reading/display) — already loaded (`frontend/src/app/layout.tsx`). The app already uses `font-serif` italic display h1s (HomeLaunchGrid :153, SavedWorkflowsPage :222) — keep.
- **Palette:** paper `#F0EEE7` / `surface-paper`; card `surface-card`; near-black ink `#15161A` / `ink-900`; warm ink ramp `ink-300..600`; single accent purple `#3C2CDA` / `brand`; hairlines `line-border`/`line-divider`. Semantic: `status-passed` (green), warn (amber), `status-failed` (red). Route ALL new chrome through these tokens — no raw hex unless a token is genuinely absent (add a token instead).
- **Geometry:** cards ~10–14px radius; the Phase-35 dark top bar + nav pill (Home · Library · My Workflows) + profile menu are already shipped and are NOT re-restyled here (they are the shell chrome; this phase restyles the surface BODIES).

## Per-surface fidelity (target → current). Full gap list in `40-CONTEXT.md` <specifics>.
1. **Home** → prompt UNDER the h1 with an Attach (no Voice, ND-X) + **Build** action row; an "Or start from a deliverable" **3×2 card grid** from the live `/api/workflows` list (ND-D), replacing the vertical row list; a "Jump back in" **recents** strip from live recent runs.
2. **Library** → "Library" h1 + count + search + Agents/Skills/Hooks tab chrome + card grids to the mock; the agent-detail **drawer** (Overview/Skills/Hooks/Config) DEFERS to Phase 41 (ND-Z) — Phase 40 keeps the shared modal.
3. **Analytics** → styling / number-format pass to mock parity (KPI row · daily-activity bars · success donut · by-pipeline · recent runs · token/model), on live/seeded data (ND-D).
4. **Account Settings** → tabs Profile / AI Model / **Usage & Limits** (relabel from "Limits") / Constitution; a richer profile form bound to REAL user fields only (no fabricated name/role/org — ND-Y).
5. **Workflow History** → keep title "**Run History**" (ND-W); type-filter chips + Sort tabs + TODAY/EARLIER/OLDER grouped rows + status/token/version badges; populated + filter-empty + zero states (seeded, ND-D).
6. **Catalogue / My Workflows** → keep "**My Workflows**" (ND-B); the mock's "Workflow Catalogue" grid of pipelines + saved workflows, on live/stubbed `/api/user-workflows` data (ND-D).

## INTENDED-DIVERGENCE REGISTER (the canonical list lives in `assemble-shell-gallery.mjs`)
Every deliberate departure from the mock is registered here. A screenshot-diff that flags one of these is CLOSED, not a failure. Any OTHER visual departure is a fidelity bug. Phase 40 CONTINUES the lettering at ND-W (ND-A..ND-V belong to Phase 39 — never reuse).

| # | Divergence | Mock says | We ship | Why |
|---|-----------|-----------|---------|-----|
| **ND-A** | Brand wordmark | "HEXAWARE" | "VelocityAI" | product brand (SC-001) — carried from Phase 39 |
| **ND-B** | Catalogue nav label + surface title | "Catalogue" | "My Workflows" | D-11 (Catalogue reserved for the future marketplace) — carried |
| **ND-C** | Nav active-state | mock's pill-fill | purple underline | ND-13.1 — carried |
| **ND-D** | All shell data | hardcoded rows/counts/charts | LIVE data (runs, analytics, saved workflows, the launchable catalog) from real endpoints; empty→W1-seeded scaffolding for the diff only | SC-001 — carried |
| **ND-W** | Workflow History title | "Workflow History" | "Run History" | app vocabulary consistency — the profile-menu item is ALSO "Run History"; parallel to ND-B |
| **ND-X** | Home prompt affordances | Attach + **Voice** buttons | Attach only | Attach is a real image-input feature; there is NO product voice-input capability — parallel to Phase-39 ND-F (demo-only affordances not reproduced) |
| **ND-Y** | Account Settings profile form | fabricated name / role / organization fields | only the profile fields backed by real user data (email, plan/tier) — no fabricated fields | SC-001 (never fabricate unpersisted data) — a specialization of ND-D |
| **ND-Z** | Library agent-detail | a right-side agent-detail **drawer** (Overview/Skills/Hooks/Config) | Phase 40 keeps the shared `AgentCapabilitiesModal`; the drawer rebuild lands with the Composer rebuild in **Phase 41** | the modal is composer-owned; restyle-first scope (D40-2) — do NOT fork the shared component here |

## Acceptance oracle (the gate — not prose)
- Fidelity is proven by the **side-by-side shell gallery** (`gallery-shell.html`), per surface + per sub-view/sub-tab/state, closed to this register, with a **human sign-off** on the images (a blocking `checkpoint:human-verify`). Regenerate the surface's section each wave via the committed oracle (`zzz-shell-baseline.spec.ts` current side + `capture-shell-mocks.mjs` target side + `assemble-shell-gallery.mjs --surface <name>`). NO automated pixel-diff (ND-D live data ≠ the mock's fixed values). No surface is "done" on a prose claim.
- Standard technical checks additionally: `npx tsc --noEmit` clean; targeted vitest for the touched component green; the surface's mocked-e2e spec re-anchored green (where one exists).

## Open questions for the orchestrator (planner rulings, confirm or override)
- **ND-W:** the planner KEEPS "Run History" (matches the app's profile-menu label). Override to align to the mock's "Workflow History" if the user prefers the mock label everywhere.
- **Settings tab label:** the planner ALIGNS "Limits" → "Usage & Limits" (a pure fidelity fix, no ND). Override to keep "Limits" (would become a new ND) if desired.
- **ND-Z:** the planner DEFERS the Library agent-detail drawer to Phase 41 (shared composer-owned modal). Override to build a Library-local drawer in Phase 40 if the drawer parity is required now (adds a task + risks composer coupling).

---
*Phase: 40-shell-mock-fidelity-restyle-b6 · UI design contract*
