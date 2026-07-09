# Phase 36: Home + History + My Workflows [B2] - Context

**Gathered:** 2026-07-09
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss) — grounded in the locked POR §84 + D-11/D-15 + evidence + ROADMAP SC.

<domain>
## Phase Boundary

Restructure the three list surfaces (Home, History, My Workflows) and build the new Run detail/reopen page. FRONTEND-heavy + ONE additive **read-only** backend endpoint (run-summary). Depends on Phase 35 (shell); rides the Phase-32 token layer + the Phase-35 shell chrome.

Deliverables (ROADMAP SC 1–4 + POR §84):
1. **Fused Home:** prompt launcher + deliverable grid + recents strip — MERGE today's `input`/`home` views into one landing. Do the deferred **component rename `WorkflowCatalog`→`HomeLaunchGrid` (D-11)** here (it IS the home launch grid).
2. **History:** Today/Earlier/Older grouping + sort by tokens/duration (fields already exist) + REAL delete wiring. **Preserve KAN-96** (click branch: a running run → the live execution view, a terminal run → the detail page) and **KAN-92** (revision/chained runs now carry real async-generated titles — do NOT regress to `Revision:` placeholders). Revision families stay intact.
3. **My Workflows:** page rename (label) + working **kebab actions** (real, not static text).
4. **Run detail/reopen page (NEW-BUILD):** backed by a **run-summary read endpoint** aggregating EXISTING data — per-agent breakdown, KPI stats, failure banner, version/revision timeline. Owner-scoped, additive, NO new tables.

Authoritative inputs (READ): POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §84 (Phase-36 brief), D-11 (the `WorkflowCatalog`→`HomeLaunchGrid` rename lands HERE; nav = Home·Library·My Workflows; "Catalogue" RESERVED for the future marketplace), D-15 (design authority: `evidence 11 §B` is THE shared-surface source of truth; adopt visual language, KEEP the product's richer behavior, REUSE existing components), §95 (the run-summary endpoint — owner-scoped, IDOR→404, `user_id`-keyed). Evidence: `01-run-ui-teardown.md` (run detail anatomy), `02-workspace-shell-teardown.md` (home/history idioms), `12-coverage-and-backend-map.md` (the EXISTING data the run-summary aggregates — do not invent fields). Post-merge facts: KAN-92 (real async titles), KAN-96 (the click branch).
</domain>

<decisions>
## Implementation Decisions — LOCKED (POR §3 / D-11 / D-15; do NOT re-open)

- **`WorkflowCatalog`→`HomeLaunchGrid` rename (D-11)** lands in THIS phase (deferred from 35) — the component IS the home launch grid. "Catalogue" stays reserved (never a saved-workflows label).
- **Fused Home** merges the `input`/`home` views (P22 already made the catalog the home landing) — one launcher + deliverable grid + recents.
- **Preserve KAN-96** (running→live view, terminal→detail) + **KAN-92** (real async titles, not `Revision:` placeholders) — these are shipped behaviors; do NOT regress them.
- **Run-summary endpoint aggregates EXISTING data** (per-agent, KPIs, failure banner, version timeline) — additive READ-only, owner-scoped, NO new tables. Reuse the P13/P25 owner-gate pattern.
- **Reskin-look, keep-behavior (D-15):** REUSE existing components + the product's richer behavior; consume the Phase-32 tokens + Phase-35 shell; NO per-page palette fork.

INVARIANTS: **SC-001** (list/detail surfaces keyed on generic run data, NEVER a workflow-name branch — INV-1), **INV-3** (the run-summary endpoint is additive read-only; the 5 backend goldens untouched by construction), **token authority** (consume Phase-32 `@theme` tokens + `ui/` primitives; per-file grep-clean of retired palette `#1B2A4A/#2563eb/#f5f5f0/Inter/Fraunces/JetBrains` = 0 + no stray stock palette — the Phase-35 discipline), **owner-scoped run-summary** (two-layer `WorkflowRun.user_id == principal` → 404, NOT the nullable `owner_id`; import-linter 4/0), **additive migrations only** (Q3 — none; the endpoint reads existing tables), **a11y** (list rows/kebab menus/detail keyboard + aria), **LOCK-B** (no transport touch). Reuse the Phase-32 primitives + Phase-35 shell chrome.
</decisions>

<code_context>
## Existing Code Insights (from evidence 01/02/12 + Phase 35)

Home = today's `input`/`home` views (fuse into one landing); the `WorkflowCatalog.tsx` component → rename to `HomeLaunchGrid.tsx` (grep all importers + `onNavigate`/page-key consumers before renaming — SC-001 keeps routes generic). History = `WorkflowHistory.tsx` (add Today/Earlier/Older grouping + token/duration sort off existing fields + real delete; preserve the KAN-96 click branch + KAN-92 titles). My Workflows = `SavedWorkflowsPage.tsx` (rename label + wire real kebab actions). Run detail = NEW page. Backend: the run-summary read endpoint — clone the P13/P25 owner-scoped read pattern; aggregate `WorkflowRun` + per-agent + events (existing data — evidence 12 maps it; do NOT add fields/tables). Consume the Phase-32 token layer + `components/ui/` primitives + the Phase-35 shell. Offline verify: `vitest run`, `tsc --noEmit` identity, per-file retired-palette grep=0; backend targeted suites + `/opt/homebrew/bin/lint-imports` (4/0), `python3.11`; full pytest HANGS — never run it. Mocked Playwright times out offline (Phase-35 precedent, DEF) → e2e is live-deferred; verify FE via vitest + tsc + grep by delta.
</code_context>

<specifics>
## Specific Ideas

Fuse Home (launcher + deliverable grid + recents; rename `WorkflowCatalog`→`HomeLaunchGrid`) → History (Today/Earlier/Older grouping + token/duration sort + real delete, preserving KAN-96/KAN-92) → My Workflows (rename + real kebab actions) → Run detail/reopen page + the owner-scoped run-summary endpoint aggregating existing data. All on Phase-32 tokens + Phase-35 shell, per-file grep-clean, a11y on lists/kebabs/detail. Verify by delta (vitest + tsc + grep); backend goldens untouched by construction.
</specifics>

<deferred>
## Deferred Ideas

Analytics aggregations + live notifications feed (Phase 38). Configure/Composer/Wizard (Phase 37). Concierge live-wiring (Phase 34). Team-sharing/workflow-visibility (LOCK-E). Handoff screen (post-v2.0). The mocked-Playwright e2e run (offline webServer timeout — live-deferred like Phase 35; captured as a baseline).

## Execution-viability note (autonomous run)
FE restructure + ONE additive read-only endpoint — offline-verifiable (vitest + tsc identity + per-file grep by delta; backend targeted suites + lint-imports). Mocked Playwright is live-deferred (offline webServer timeout). No new tables, no transport change. Live confirmation → Phase 34. If a check needs a live server, mark it live-deferred — do not hang, do not fabricate.
</deferred>
