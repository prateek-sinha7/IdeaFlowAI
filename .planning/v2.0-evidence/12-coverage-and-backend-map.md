# Coverage Matrix & Backend-Architecture Map — Milestone v2.0

> **Synthesis doc** (not a verbatim agent report). Consolidates evidence 01–11 into two one-glance answers: (1) is every screen covered? (2) what backend work does the whole milestone need? Authored 2026-07-07 after the second teardown batch. The per-claim detail lives in the numbered evidence docs; this is the index.

## Part 0 — The load-bearing principle (LOCKED, D-15)

**Adopt the mocks' visual language; keep the current product's richer behavior and live data-driven surfaces; reuse existing components over rebuilding from the mock's hardcoded versions.** Several mocks are *behind* the shipped product — the composer mock hardcodes 8 capabilities (P22 ships a live `/api/capabilities` palette), models retry as a bool (product uses `[1,2,3]`), and omits the validator→gate coupling the backend enforces; Admin hides three real columns (Runs/Role/Joined) and shows three unbacked ones; Login is a static regression of a fully-wired form. **A literal, face-value rebuild would regress functionality.** Every phase reskins the *look* and preserves the *behavior*.

## Part 1 — Screen coverage matrix (every mock → phase → status)

Delta: RESKIN (restyle) · RESTRUCTURE (layout differs) · NEW-BUILD (no surface) · BACKEND (data no API provides).

| Mock file | Screen(s) | Owning phase | Delta | Status |
|---|---|---|---|---|
| `Hexaware Run.dc.html` + Live + Failed | Run screen (chat lane + Preview/Steps/Files/Audit) | 31 (chat lane) + 32 (redesign) | RESTRUCTURE | Covered — evidence 01, 07 |
| `Hexaware Run - Design System.dc.html` | Token/shape authority | 32 (token layer) | — | Arbiter — evidence 11 §B |
| `Hexaware Workspace v2.dc.html` — Home | Home (hero + grid + recents) | 36 | RESTRUCTURE | Covered — evidence 02 |
| Workspace v2 — Library | Agent Library (Agents/Skills/Hooks) | 35 | RESKIN | Covered |
| Workspace v2 — Catalogue → **My Workflows** | Saved workflows | 36 (rename D-11) | RESKIN/RESTRUCTURE | Covered |
| Workspace v2 — Workflow History → **Run History** | Run history + revision families | 36 | RESTRUCTURE | Covered |
| Workspace v2 — Run detail/reopen | Per-run summary page | 36 | NEW-BUILD + BACKEND | Covered — needs run-summary endpoint |
| Workspace v2 — Analytics | Analytics dashboard | 38 | RESKIN/RESTRUCTURE | Covered — needs aggregation endpoints |
| Workspace v2 — Account Settings | Settings | 35 | RESKIN | Covered |
| Workspace v2 — Notifications | Notifications panel + feed | 35 (panel) + 38 (feed) | RESKIN/RESTRUCTURE | Covered |
| Workspace v2 — Agent drawer | Agent inspector | 37 | RESTRUCTURE | Covered |
| Workspace v2 — Workflow dialog | Capability/context surfacing | 37 | RESTRUCTURE | Covered |
| Workspace v2 — Template/DS/Gates pickers | Pickers | 35 (restyle) + 37 (generic wiring) | RESKIN | Covered |
| Workspace v2 — Top bar / profile / nav | Shell chrome | 35 | RESKIN/RESTRUCTURE | Covered (nav = Home·Library·My Workflows, D-11) |
| **`Hexaware Composer.dc.html`** | Standalone workflow builder | **37 (upgraded)** | RESTRUCTURE (~13 reskins of P22 code) | **NOW covered — evidence 08** |
| **`Hexaware Wizard.dc.html`** | Template/DS/discovery setup | **37 (upgraded)** | RESTRUCTURE + NEW-BUILD (stepper) | **NOW covered — evidence 08** |
| **`Hexaware Login.dc.html`** | Login/Register | **35 (folded in)** | RESKIN + small RESTRUCTURE | **NOW covered — evidence 10** |
| **`Hexaware Admin.dc.html`** | Admin/user-management | **35 (reskin) + deferred backend** | RESKIN + RESTRUCTURE | **NOW covered — evidence 10** |
| **`Hexaware Handoff.dc.html`** | Code-handoff / Draft-PR | **DEFERRED (post-v2.0)** | RESTRUCTURE + BACKEND | **Decided out — evidence 09, ND-12** |

**Every mock file is now accounted for.** 18 surfaces phased; Handoff explicitly deferred with reasons.

## Part 2 — Backend-architecture map (every backend change, categorized)

**Category A — new read endpoints over data that already exists (cheap, additive, per-phase detail):**
- `gate_events` / `validation_results` / `exec_runs` endpoints — Audit tab (Phase 32). Data since P8.
- run-summary aggregation endpoint — Run-detail page (Phase 36). Aggregates run_events + `/family` + `token_usage`.
- date-scoped analytics rollups (daily series, per-pipeline/model, spend) — Phase 38. Over P26 telemetry.
- expose `tokNum`/`durSec` on the runs list — History sort (Phase 36). Fields exist.

**Category B — additive migrations / new columns (real backend work, decision-gated):**
- Admin: `display_name`, account `status` (invited/active/suspended), `last_active_at` on `users` + an email-invite endpoint — *only if matching mock columns* (evidence 10). **Recommend: defer; keep richer current admin.**
- Notifications feed store or derivation (Phase 38).
- Draft-run persistence (ND-1) · per-agent prompt-override persistence (ND-7).

**Category C — genuine architectural changes (elevate to decisions now):**
- **Generic template/DS as declared run inputs for every deliverable type** (Phase 37) — today prototype/ppt-only via split routes; the run-launch path must accept template/DS generically. SC-001-aligned, load-bearing. Evidence 08 §B7.
- Handoff Diff/Tests/Compliance backend contracts (unified diff, quantitative test results, structured compliance checks) — **deferred** post-v2.0 (evidence 09).

**Category D — surfaces the mocks imply but the product lacks → DROP (mock-fiction, not build):**
- SSO / SCIM, password reset ("Forgot?"), email invitations, account-suspension lifecycle (evidence 10). Each is an identity/auth project, not a reskin. **Keep the current, functionally-richer login/admin flows.**
- Workflow visibility / team-sharing ("Just me / Team", evidence 08) — no column, no endpoint, no UI; this is the P21-deferred sharing/marketplace scope. **Defer.**
- Pre-run cost + duration estimates for a composed workflow (evidence 08) — no endpoint today (only post-run). **Defer or scope as opt-in.**
- Discovery page-selection (evidence 08) — absent end-to-end. **Defer or drop.**

**Category E — run/chat backend (already architected, this milestone's core):** SSE+REST transport (D-13), `chat_message`/steering seam, `chat:concierge` + `compaction:chat_history` + `context_provider:uploaded_files` capabilities, `POST /api/runs/{id}/files`. See POR §2/§6.

**Net:** beyond the run/chat core, the shell needs **four cheap read endpoints (A)**, **one genuine architectural change (C: generic template/DS)**, and a **short list of deferrable/droppable backend items (B/D)** — nothing unknown, nothing that blocks the reskin phases.

## Part 3 — Cross-mock consistency (the "were the HTMLs updated together?" answer)

**No — they weren't, and evidence 11 catalogs the drift.** The foundation is consistent (two fonts, core tokens, dark top bar); the secondary layer drifts in six clusters. The rebuild cites **evidence 11 §B (the canonical shared-surface spec)** as the single source of truth for nav, tokens, the status model, component idioms, and terminology — NOT any individual mock. Highest-risk resolved conflicts: `running` is blue everywhere (Handoff's amber = bug); "Not run" is neutral grey (Failed's amber = bug); one badge form per run status; the Design System file must *add* a status palette (it documents none) and resolve its own radius contradiction.

**7 conflicts need a human ruling (evidence 11 §C)** — recommended defaults in the POR's ND-13; the two that need product input are the canonical deliverable-type names and the real per-type agent roster (the mocks show three different rosters).
