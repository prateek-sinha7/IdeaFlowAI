# Phase 38: Analytics, Estimates & Notifications [B4] - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss) — grounded in the locked POR §88 + §95 + evidence + ROADMAP SC.

<domain>
## Phase Boundary — the data-backed shell tail (LAST offline phase)

Real analytics aggregations powering the dashboard, per-deliverable estimates on Home cards, and a live notifications feed. Additive **READ-only** backend (aggregation endpoints over EXISTING run data) + FE (charts, estimates, feed wiring). Depends on Phase 35 (the shell + the notifications-panel chrome); independent of 36/37. This is the last offline phase before the Phase-34 live pass.

Deliverables (ROADMAP SC 1–2 + POR §88):
1. **Analytics aggregation endpoints** — date-scoped: daily series + per-pipeline/model rollups + spend. Additive READ-only over existing run data (`WorkflowRun` + `token_usage` + cost). Owner-scoped (IDOR→404). The dashboard filters actually **RECOMPUTE** against them (SC-1 — not static mock data).
2. **Chart components** — donut/bar, **self-contained token-styled SVG** (no heavy external chart lib — CSP-safe, consume the Phase-32 tokens).
3. **Per-deliverable estimates** — time/agent estimates on Home deliverable cards, derived from manifest step count + analytics history (real data, not hardcoded).
4. **Notifications feed** — wire the Phase-35 `NotificationPanel` (chrome-only today) to a LIVE feed with kinds **gate/running/done/failed**, from existing run-state data (owner-scoped).

Authoritative inputs (READ): POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §88 (the Phase-38 brief), §95 (the analytics aggregations endpoint — owner-scoped, IDOR→404, `user_id`-keyed). Evidence: `02-workspace-shell-teardown.md` (analytics + notifications idioms — the mock's static values become real), `12-coverage-and-backend-map.md` (the EXISTING run/token/cost data to aggregate — do NOT invent fields). Phase-35 `NotificationPanel` (the chrome to wire) + the Phase-32 token layer/primitives + the Phase-36 Home/`HomeLaunchGrid` cards (where estimates land).
</domain>

<decisions>
## Implementation Decisions — LOCKED (POR §3 / §88 / §95; do NOT re-open)

- **Analytics aggregations power the dashboard — filters RECOMPUTE (SC-1).** Date-scoped: daily series, per-pipeline/model rollups, spend. Real endpoints, not the mock's static numbers.
- **Charts self-contained** — token-styled SVG donut/bar; NO heavy external chart lib (CSP-safe; consume the Phase-32 `@theme` tokens; the governance status palette exception does NOT apply — one-chroma unless a datum is a run-status).
- **Estimates from real data** — manifest step count + analytics history averages (NOT hardcoded).
- **Notifications feed** — kinds gate/running/done/failed, wired from existing run-state; the Phase-35 panel is the chrome. Live push confirmation → Phase 34 if it needs the live connection.
- **Additive READ-only backend** — aggregate EXISTING run/token/cost data; NO new tables.

INVARIANTS: **SC-001/INV-1** (analytics/estimates/feed keyed on generic run data, NEVER a workflow-name branch), **INV-3** (the aggregation endpoints are additive read-only; the 5 characterization goldens byte/event-identical by construction), **owner-scoped aggregations** (two-layer `WorkflowRun.user_id == principal` → 404, NOT the nullable `owner_id`; import-linter 4/0), **additive migrations only** (Q3 — aggregate existing columns, NO new tables), **token gate** (charts/cards consume Phase-32 tokens; per-file retired-palette `#1B2A4A/#2563eb/#f5f5f0/Inter/Fraunces/JetBrains` = 0 + positive `@theme`/`ui/`), **a11y** (charts labelled/have text alternatives; feed keyboard + aria), **LOCK-B** (no transport touch). Reuse Phase-32 primitives + Phase-35 shell/panel + Phase-36 cards.
</decisions>

<code_context>
## Existing Code Insights (from evidence 02/12 + prior phases)

Analytics: clone the P13/P25 owner-scoped read-endpoint pattern; aggregate `WorkflowRun` + `token_usage` + cost columns date-scoped (evidence 12 maps the existing data — do NOT invent fields). The dashboard analytics view (wire the filters to recompute against the endpoints instead of static values). Chart components: NEW token-styled SVG donut/bar under `components/ui/` or a `charts/` dir (no external lib). Home cards: the Phase-36 `HomeLaunchGrid`/deliverable cards (add the estimate line). Notifications: the Phase-35 `NotificationPanel` (wire to the feed source — existing run-state, owner-scoped). Offline verify: `vitest run`, `tsc --noEmit` identity, per-file retired-palette grep=0; backend targeted suites (aggregation endpoint: owner 200 / cross-owner 404 / recompute correctness) + `/opt/homebrew/bin/lint-imports` 4/0; `python3.11`; full pytest HANGS — never run it; the 5 goldens byte-identical (aggregations are additive read-only). Mocked Playwright times out offline → e2e live-deferred.
</code_context>

<specifics>
## Specific Ideas

Date-scoped analytics aggregation endpoints (owner-scoped, additive read-only over existing run/token/cost data) → wire the dashboard filters to RECOMPUTE → donut/bar chart components (self-contained token-styled SVG) → per-deliverable time/agent estimates on Home cards (manifest steps + history) → notifications feed wired to the Phase-35 panel (gate/running/done/failed). Additive; goldens byte-identical; owner-scoped (IDOR→404); token gate per file; a11y on charts + feed. Verify by delta.
</specifics>

<deferred>
## Deferred Ideas

Live notification PUSH over the real connection (the feed logic is built; live push confirmation → Phase 34 if connection-dependent). Compliance-PDF / advanced analytics exports (out of scope). The Concierge live-wiring (Phase 34). Handoff screen (post-v2.0). Team/org-scoped analytics (LOCK-E deferred sharing).

## Execution-viability note (autonomous run)
Additive read-only backend + FE — offline-verifiable (vitest + tsc identity + per-file grep; backend aggregation tests owner/cross-owner/recompute + lint-imports 4/0; goldens byte-identical). NO new tables. Live notification push → Phase 34 if it needs the live connection. Verify BY DELTA; if a check needs a live server, mark it live-deferred — do not hang, do not fabricate.
</deferred>
