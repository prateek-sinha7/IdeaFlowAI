# Phase 40: Shell Mock Fidelity (restyle surfaces) — Context

**Gathered:** 2026-07-12
**Status:** Ready for planning
**Source:** Orchestrator scoping pass (read-only surface map + reviewed shell baseline gallery + committed shell fidelity oracle). Follows the plan-ingestion preference: the scope is settled — copy it faithfully; skip interactive re-discovery/research. This is the shell sibling of Phase 39 (run-screen fidelity) and reuses Phase 39's method 1:1.

<domain>
## Phase Boundary

Bring the **SHELL surfaces** to full visual fidelity with the VelocityAI mocks, **as-is**, using the SAME anti-drift method Phase 39 used for the run screen. **RESTYLE-FIRST (user ruling 2026-07-12):** Phase 40 covers ONLY the close-to-mock / merely-blocked surfaces — **Home · Library · Analytics · Account Settings · Workflow History · Workflow Catalogue ("My Workflows")** — brought to mock parity, PLUS the harness fixes that unblock the blocked/empty surfaces. Every surface AND every sub-view/sub-tab gets a mock-vs-current gallery section + a blocking human pixel sign-off.

**Target mocks (the literal spec):**
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Workspace v2.dc.html` — the JS-toggled shell state machine (Home · Library +Agents/Skills/Hooks +agent-drawer · Catalogue · History · Analytics · Account Settings +tabs).
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Composer.dc.html` — full-page Composer (**OUT of scope this phase — see deferred**).

Out of scope (DEFERRED to Phase 41): the **Configure "one-screen" rebuild** (the mock's single "Configure your run" screen that our app splits across IdeaInputPage + LaunchWizard + ConfigureScreen) AND the **Composer full-page rebuild** (mock = full page; ours = AgentsPopup modal). The run/execution screen (Phase 39 territory) and its components are NOT touched.
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### D40-1 — Same method + rigor as Phase 39 (the user's explicit directive)
"Phase 40 follows the same style of planning and parity to mock UIs just like Phase 39 did." Every mechanism Phase 39 used is reused verbatim: the two-sided fidelity oracle, per-surface **blocking** `checkpoint:human-verify` gates, the intended-divergence register, and the pixel-exact bar. Fidelity is INVERTED against D-15's "reuse over rebuild" default for chrome/layout (reproduce the mock's composition exactly) EXCEPT where a shared/composer-owned component forces a deferral (ND-Z).

### D40-2 — Restyle-first scope (user ruling 2026-07-12)
The six in-scope surfaces are the ones that are already close-to-mock or merely blocked (a crash / empty fixtures). Configure single-screen + Composer full-page are real REBUILDS (a design decision, not a restyle) and are deferred to Phase 41. Do NOT plan them here.

### D40-3 — The fidelity ORACLE already exists — reuse, do NOT rebuild
The shell oracle is BUILT + committed (13633a0e):
- `frontend/e2e/fidelity/capture-shell-mocks.mjs` (TARGET/mock side — drives the DC mock's own nav to each surface).
- `frontend/e2e/tests/zzz-shell-baseline.spec.ts` (CURRENT/app side, gated `SHELL_CAPTURE=1`).
- `frontend/e2e/fidelity/assemble-shell-gallery.mjs` (pairs into `gallery-shell.html`; carries the ND register).
All three reuse the Phase-39 `serve-mocks.mjs` + the mocked fixtures. Phase 40 FORMALIZES them (repo-relative outputs, `--surface` filter, finalized ND register) — it does not re-invent them.

### D40-4 — Live data, never fiction (SC-001 / ND-D)
Every shell surface binds to real live data (runs, analytics, saved workflows, the launchable catalog) — never the mock's hardcoded rows/counts/charts. Where a surface renders empty in mocked mode, W1 SEEDS representative capture scaffolding (test-only, like Phase 39's audit seeding) so the diff is fair; production still shows only real data.

### D40-5 — Verification is a screenshot-diff gate + human sign-off, not prose (the load-bearing decision)
The prior 12 UI phases drifted because fidelity was never the acceptance test; Phase 39 held because it was. For EACH surface + sub-view: the side-by-side gallery section is regenerated, closed to the intended-divergence register, and a **human signs off on the images** (a blocking checkpoint). No surface is "done" on a prose claim. There is deliberately NO automated pixel-diff (ND-D live data never equals the mock's fixed values).

### D40-6 — Intended-divergence register CONTINUES at ND-W (ND-A..ND-V are Phase 39's — never reuse)
Carry ND-A/B/C/D unchanged (brand "VelocityAI" · nav "My Workflows" · nav purple underline · live/real data). Phase 40's new keeps are ND-W..ND-Z (see the register in `40-UI-SPEC.md` and `assemble-shell-gallery.mjs`). The canonical register lives in `assemble-shell-gallery.mjs` (finalized in 40-01).

## Claude's Discretion
- Exact component decomposition per surface (new sub-components vs. extending existing), provided the file map is respected and no dual implementations survive (delete superseded code — INV-3/INV-12). The legacy unused `components/home/CreationHub.tsx` twin is an INV-3 cleanup candidate the Home wave may remove.
- The precise shape of the seeded capture scaffolding (`/api/user-workflows`, `/api/runs` history set, `/api/analytics/summary`) — must be representative + test-only, never a production shape.
- Whether the "Usage & Limits" tab relabel and the "Run History" title are aligned-to-mock or kept — the planner's rulings are ND-W (keep "Run History") and align "Usage & Limits" (see open questions in the UI-SPEC).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The design contract (the spec)
- `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Workspace v2.dc.html` — the shell state machine (per-surface `sc-if` blocks + nav handlers; see the surface table in SURFACE-MAP §1).
- `.planning/phases/40-shell-mock-fidelity-restyle-b6/40-UI-SPEC.md` — per-surface fidelity spec + the ND-A..D / ND-W..Z register + the acceptance oracle.
- Scoping surface map (surface→component + divergences + blockers): `/Users/1000060523/.claude/jobs/e660aea4/tmp/phase40-scope/SURFACE-MAP.md`.
- Reviewed baseline gallery (32 mock-vs-current pairs): `/Users/1000060523/.claude/jobs/e660aea4/tmp/phase40-scope/gallery-shell.html`.

### The fidelity oracle (reuse + formalize — already committed 13633a0e)
- `frontend/e2e/fidelity/capture-shell-mocks.mjs` (TARGET side), `frontend/e2e/tests/zzz-shell-baseline.spec.ts` (CURRENT side, gated `SHELL_CAPTURE=1`), `frontend/e2e/fidelity/assemble-shell-gallery.mjs` (the gallery + ND caption).
- `frontend/e2e/fidelity/serve-mocks.mjs` (Phase-39 local HTTP mock server — reused).
- `frontend/e2e/fixtures/{mockApi,mockWs,dashboard}.ts` (the mocked harness — W1 stubs `/api/user-workflows` + seeds data here).

### Source files (the surface → component map — verified read-only)
- **Home:** `frontend/src/components/catalog/HomeLaunchGrid.tsx` (eyebrow :150 · h1 :153 · "Create workflow" :167 · vertical row list :186-188 — becomes a 3×2 card grid + recents) + `frontend/src/components/layout/DashboardLayout.tsx` (the "Start with a prompt" textarea `home-launch-prompt` :1502-1510 ABOVE the grid mount :1519 — becomes the mock's prompt UNDER the h1). Legacy twin: `components/home/CreationHub.tsx` (unused, INV-3 candidate).
- **Library:** `frontend/src/components/library/LibraryPage.tsx` (`Tabs` Agents/Skills/Hooks :356-360; agent detail reuses `AgentCapabilitiesModal` from `workflow/AgentsPopup` :348 — composer-owned, ND-Z).
- **Analytics:** `frontend/src/components/analytics/AnalyticsPage.tsx` (KPI row :309 · daily-activity `BarChart` :347 · success `DonutChart` :372 · by-pipeline :413; binds `/api/analytics/summary`) + `frontend/src/components/analytics/charts/{BarChart,DonutChart}.tsx`.
- **Account Settings:** `frontend/src/components/settings/AccountSettings.tsx` (tabs Profile/AI-Model/Limits/Constitution :155-158; profile = email only :97; models from `/api/settings/preferences` + `/api/capabilities`).
- **Workflow History:** `frontend/src/components/history/WorkflowHistory.tsx` (title "Run History" :767; `filterType`/`sortKey`/`searchQuery` :123-127; date-bucketed family groups via `history/RevisionFamilyView.tsx`; binds `/api/runs`).
- **Catalogue / My Workflows:** `frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx` (h1 "My Workflows" :222; `userWorkflows.filter` :170 CRASHES when `/api/user-workflows` is unstubbed; card grid :298; empty state :273).

### Locked decisions / prior work
- `.planning/IMPLEMENTATION-REGISTER.md` — Phase 39 entry (the ND-A..ND-V register + the fidelity oracle method); Phase 36 (fused Home / D-11 nav / HomeLaunchGrid); Phase 38 (Analytics endpoint + charts); Phase 35 (shell chrome + tokens).
- `39-UI-SPEC.md` / `39-01-PLAN.md` / `39-07-PLAN.md` — the plan template + the oracle-formalization template this phase mirrors.
</canonical_refs>

<specifics>
## Specific fidelity gaps (from the reviewed baseline — the per-surface target)

1. **Home (biggest gap):** mock = eyebrow + "What would you like to build" h1, then the prompt UNDER the h1 with an Attach/Voice/**Build** action row, then an "Or start from a deliverable" **3×2 card grid** (Product requirements / Pitch / Interactive prototype / End-to-end app / Platform workflows / Custom workflow), then a "Jump back in" recents strip. Ours = a "Start with a prompt" box ABOVE the h1, then "Create workflow" + a vertical deliverable **list** (not a grid) and no recents. Ordering + grid-vs-list + missing recents are the real gaps (Voice not reproduced — ND-X).
2. **Library:** mock = "Library" h1 + count + search + Agents/Skills/Hooks tabs + card grid, and a right-side agent-detail **drawer** (Overview/Skills/Hooks/Config). Ours = LibraryPage with the same tab triad + a card grid, but the agent detail opens the composer-owned `AgentCapabilitiesModal`. Restyle the header/tab-chrome/card grids; the drawer rebuild defers to Phase 41 (ND-Z).
3. **Analytics:** strong structural match already (KPI row · daily-activity bars · success donut · by-pipeline · recent runs · token/model breakdown all present). Mostly styling / number-format to mock parity, on live/seeded data (ND-D).
4. **Account Settings:** mock tabs Profile / AI Model / **Usage & Limits** / Constitution + a richer profile form (name/role/org) + password. Ours = Profile / AI Model / **Limits** / Constitution + email-only profile. Align the tab label to "Usage & Limits"; build the richer profile form bound to REAL user fields only (no fabricated name/role/org — ND-Y).
5. **Workflow History:** mock = "Workflow History", type-filter chips + Sort tabs + TODAY/EARLIER/OLDER grouped rows with status badges + token/version chips. Ours = "Run History" (keep — ND-W), same filter/sort/group skeleton but empty in mocked mode (W1 seeds runs). Capture populated + filter-empty + zero states.
6. **Catalogue / My Workflows:** mock = "Workflow Catalogue" grid of pipelines + saved workflows. Ours = SavedWorkflowsPage ("My Workflows" — ND-B) but it **crashes** in mocked mode (`/api/user-workflows` unstubbed). W1 stubs it; then restyle the grid to the mock.

## Proposed waves (planner refined — see the PLAN files)
- **W1 (40-01) Harness:** stub `/api/user-workflows` + seed History/Analytics/Home-recents data; formalize the shell oracle (repo-relative outputs, `--surface` filter, finalized ND register); own SHELL-01..04; regenerate the baseline gallery.
- **W2 (40-02..40-07) Surfaces (parallel — disjoint files):** Home · Library · Analytics · Account Settings · Workflow History · Catalogue — each = build-to-mock + regenerate its gallery section + a blocking human fidelity sign-off + (where a spec exists) an e2e re-anchor.
</specifics>

<deferred>
## Deferred Ideas (→ Phase 41, do NOT plan here)
- **Configure "one-screen" rebuild** — the mock's single "Configure your run" screen (brief + Templates/Design-System/Review-Gates/Workflow-Settings accordions + full-screen overlays) maps to THREE app implementations across TWO routes (IdeaInputPage on `/dashboard`, LaunchWizard on `/workflow/create`, ConfigureScreen on `/workflow/configure`). A faithful single-screen rebuild is a design decision, not a restyle.
- **Composer full-page rebuild** — mock = a full-page pipeline builder (identity + reorderable agent rows + per-agent model picker + overrides + right Summary rail); ours = AgentsPopup **modal**. User ruled Composer = full-page, as a SEPARATE rebuild phase.
- **Wizard template + design-system stubs** — `/api/prototype/templates`, `/api/prototype/design-systems`, `/api/ppt/templates` are unstubbed; those two wizard sub-views are Configure-scope → deferred with Configure.
- **The `ts-e.model-picker` e2e re-anchor** — model-picker/agent-config is Configure/Composer territory → defers with Configure (Phase 41).
- **Library agent-detail drawer (ND-Z)** — the shared `AgentCapabilitiesModal` is composer-owned; the mock's right-drawer rebuild lands with the Composer rebuild in Phase 41.
</deferred>

<scope_fence>
## Negative Space / Forbidden (a phase that violates these is NOT done)
- Do NOT plan or build the Configure single-screen rebuild or the Composer full-page rebuild — Phase 41 (only note them as the deferred follow-up).
- Do NOT touch the run/execution screen (Phase 39 territory) or its components.
- Do NOT clone the mocks' inert/hardcoded/fiction data — bind to real live data; do NOT fabricate profile fields the backend does not persist (SC-001 / ND-D / ND-Y).
- Do NOT touch the intended divergences (brand "VelocityAI" / nav "My Workflows" / nav underline / "Run History" title) toward the mock (ND-A/B/C/W).
- Do NOT rebuild the shell fidelity oracle — reuse + formalize the committed scripts (D40-3).
- No dual implementations (INV-3/INV-12) — deleting any superseded shell code (e.g. the unused `CreationHub` twin) is part of the change.
- Additive only; `feat/ui-2` only (NEVER main/staging); no commit trailer; never push without an explicit go-ahead.
- Backend limited to mock stubs/seeding (test-only) + additive FE. No migrations expected.
- Every fidelity gate is an EXECUTABLE `checkpoint:human-verify` (blocking) — never a prose self-certify (the plan-checker rejects a non-checkpoint fidelity gate).

---

*Phase: 40-shell-mock-fidelity-restyle-b6*
*Context gathered: 2026-07-12 via orchestrator scoping (plan-ingestion path)*
</scope_fence>
