# Phase 35: Shell Chrome + Reskin Pages [B1] - Context

**Gathered:** 2026-07-09
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss) — grounded in the locked POR §82 + D-11/D-15 + ND-12 + evidence + ROADMAP SC.

<domain>
## Phase Boundary

Converge the app SHELL to the Workspace-v2 idiom and reskin the remaining reskin-only pages — all on the Phase-32 token/primitive layer. **FRONTEND-ONLY** (reskin + wire static→real controls against EXISTING endpoints); NO new backend (ND-12 drops the identity-trap backends; the admin extras are deferred). Depends on Phase 32 (token layer). Note the sequence override: this runs BEFORE Phase 34 (the live pass) because 35–38 need only Phase 32, not 34.

Deliverables (ROADMAP SC 1–2 + POR §82 + ND-12):
1. **Shell chrome:** dark top bar (`#111114`) + centered **nav pill (Home · Library · My Workflows**, D-11) + profile menu (Settings/Analytics/History/Admin/Logout) + notifications panel. Matches Workspace v2 on tokens — NO per-page palette fork.
2. **Account Settings:** make the static mock fields REAL controls (wire to existing settings endpoints; do NOT build new backend).
3. **Template picker, DS picker, Review-gates popover** restyles (on tokens/primitives; DS picker shows the real ~14 count — LOCK-F, no catalog expansion).
4. **Library (Agents/Skills/Hooks)** restyle with real controls where the mock had static text.
5. **Login/Register — reskin-only (ND-12):** the core is already wired and RICHER than the mock; ADD the dark brand panel; do NOT regress the password-create flow. **DROP the identity traps** (SSO/SCIM, password reset, email invitations, account-suspension — each a backend project, mock fiction).
6. **Admin — reskin (ND-12):** chrome/stats/table/tier-dropdown/delete (data all exists); KEEP the product's Runs/Role/Joined columns + password-create; DEFER the mock's Status/Last-active columns + email-invite flow (additive `users` columns + endpoint — NOT this phase).

Note the notifications split: Phase 35 builds the notifications PANEL chrome; the live feed is Phase 38.

Authoritative inputs (READ): POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §82 (Phase-35 brief), D-11 (nav = Home · Library · My Workflows; **"Catalogue" is RESERVED** for the future marketplace — do NOT use it for saved workflows; the `WorkflowCatalog`→`HomeLaunchGrid` rename is Phase 36, NOT here), D-15 (design authority: `evidence 11 §B` is THE shared-surface source of truth for tokens/nav/status/idioms/terminology; adopt the mocks' visual language, KEEP the product's richer behavior, REUSE existing components — a face-value rebuild REGRESSES), ND-12 (the login/admin reskin scope + the dropped identity traps + the deferred admin extras). Evidence: `02-workspace-shell-teardown.md` (THE shell-chrome canonical — the only mock with working notifications + profile menu; current-product↔mock file map), `10-login-admin-teardown.md` (login/admin reskin + the mock-fiction register), `11-cross-mock-reconciliation.md §B` (running=blue `#3C2CDA`, "Not run"=grey, nav purple-underline, radius buttons 10/cards 14).
</domain>

<decisions>
## Implementation Decisions — LOCKED (POR §3 / D-11 / D-15 / ND-12; do NOT re-open)

- **Nav = Home · Library · My Workflows (D-11).** "Catalogue" reserved for the future marketplace — never label saved workflows "Catalogue". The `WorkflowCatalog`→`HomeLaunchGrid` rename is Phase 36.
- **Reskin-look, keep-behavior (D-15):** adopt the Workspace-v2 visual language on the Phase-32 tokens; REUSE existing components + the product's richer behavior; NO per-page palette fork. Shell-chrome canonical = Workspace v2 (evidence 02).
- **Login/Admin reskin-only (ND-12):** keep the product's richer wiring (password-create, Runs/Role/Joined columns); ADD the login dark brand panel; DROP the identity traps (SSO/SCIM/password-reset/email-invite/account-suspension — mock fiction, each a separate backend project); DEFER admin Status/Last-active + email-invite (additive backend, not this phase).
- **DS picker = the real ~14 count (LOCK-F)** — no catalog expansion.

INVARIANTS: **SC-001** (nav/shell/pickers keyed on generic routes/data, NEVER a workflow-name branch — INV-1), **INV-3** (FRONTEND-only — the 5 backend goldens untouched by construction), **token authority** (consume the Phase-32 `@theme` tokens + primitives; NO new hardcoded palette — that is the whole point of the reskin; no retired navy `#1B2A4A`/`#2563eb`/Inter/Fraunces/JetBrains), **a11y** (nav/profile-menu/notifications/popover keyboard + aria), **NO new backend** (ND-12 drops the trap backends; admin extras deferred; wire only to existing endpoints). Reuse the Phase-32 primitives (Button/Card/Tabs/Badge/Pill). LOCK-B unaffected (no transport touch).
</decisions>

<code_context>
## Existing Code Insights (from evidence 02/10 + Phase 32)

The shell/top-bar/nav/profile/notifications live in the app-shell layout components (`frontend/src/components/layout/*` + the nav/header); Account Settings, the Template/DS pickers, the Review-gates popover, and the Library (Agents/Skills/Hooks) pages are existing surfaces to restyle (evidence 02/10 map each mock ↔ its current-product file — READ them for the exact paths). Login/Register + Admin are existing wired pages (evidence 10) — reskin only, keep the richer wiring. Consume the Phase-32 token layer (`frontend/src/styles/globals.css` `@theme`) + `frontend/src/components/ui/` primitives (Button/Card/Tabs/Badge/Pill). Offline verify: `vitest run`, mocked Playwright `--project=mocked` VERIFIED BY DELTA vs the pre-existing baseline (DEF-29-06-1 — do NOT chase absolute-green), `tsc --noEmit` identity; NO live server, NO backend change. The pattern-mapper should map each reskin target to its current file before planning.
</code_context>

<specifics>
## Specific Ideas

Reskin the shell chrome (dark top bar `#111114` + nav pill Home·Library·My Workflows + profile menu + notifications-panel chrome) → Account Settings real controls → Template/DS pickers + Review-gates popover → Library (Agents/Skills/Hooks) → Login/Register (add dark brand panel, keep password-create) → Admin (chrome/stats/table/tier/delete, keep Runs/Role/Joined). All on Phase-32 tokens + primitives, no palette fork, a11y on the interactive shell. Verify by delta; goldens untouched by construction (FE-only).
</specifics>

<deferred>
## Deferred Ideas

Identity traps — SSO/SCIM, password reset, email invitations, account-suspension (mock fiction, DROPPED). Admin Status/Last-active columns + email-invite flow (additive backend — deferred). Live notifications FEED (Phase 38 — this phase does the panel chrome only). Home/History/My-Workflows restructure + `WorkflowCatalog`→`HomeLaunchGrid` rename (Phase 36). Configure/Composer/Wizard (Phase 37). Analytics data (Phase 38). Handoff screen (deferred post-v2.0). The Concierge live-wiring (Phase 34).

## Execution-viability note (autonomous run)
FRONTEND-only reskin + static→real control wiring against existing endpoints — offline-verifiable (vitest + mocked Playwright delta + tsc identity). No live server, no backend change (ND-12 drops the trap backends). Verify BY DELTA vs the pre-existing baseline; if a check needs a live server, mark it live-deferred — do not hang, do not fabricate.
</deferred>
