# Phase 32: Run-Screen Redesign [A4] - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss) — grounded in the locked POR §72 + evidence + ROADMAP SC.

<domain>
## Phase Boundary

Converge the run screen to the Hexaware Run design: **token layer + primitives FIRST**, then left = chat lane (the Phase-31 `RunChatLane`, now absorbing the `AgentProgressPanel` controls), right = **Preview / Steps / Files / Audit**, with Steps as a **3-level drill-down**. FRONTEND-heavy + 3 additive **read-only** backend endpoints (Audit). This is the reskin phase that D-15 gates the rest of the shell on — the token layer is a dependency for Phases 34/35/36/37, so land it clean.

Deliverables (ROADMAP SC 1–4 + POR §72):
1. **Token layer** (`globals.css` + tailwind): black/beige/one-blue `#3C2CDA` + Manrope/Heebo per the DS mock; + primitive set (Button/Card/Tabs/Badge/Pill). Run screens consume tokens — **NO new hardcoded palette**.
2. **Left = chat lane**: mount the Phase-31 `RunChatLane` as the left column (~390px), absorbing `AgentProgressPanel` controls (stop, revise-as-chat, suggestions-as-chips).
3. **Right tabs = Preview / Steps / Files / Audit**:
   - **Steps** = restructure `AgentThinkingTab` + `WaveTreePanel` into the 3-level drill-down (L1 overview spine → L2 agent detail + sticky "Context received" rail → L3 task detail, **dual-source**: `task_progress` for task-loop AND `subagent_*`/`wave_*` for fanout). Gate/clarify relocate from full-panel overlays to **inline Steps cards**. Preserve **KAN-99** (cap task checklist at N-1 until the build agent truly finishes — the final `task_progress` precedes the fix-loop).
   - **Preview** keeps `FIRST_PARTY_RENDERERS` + generic dispatch; add typed-renderer switcher as a manual override.
   - **Audit** = 3 new owner-scoped read endpoints (`GET /api/runs/{id}/gate-events`, `/validation-results`, `/exec-runs`) + client-side counters/coverage chips/filters + **CSV/JSON export** (ND-6). Governance status palette (green/amber/red) is the ONLY place the one-chroma rule is excepted.
4. **Failed/degraded/cancelled states faithful** (P16 affordances + "What went wrong" chat card). **E2E hardening**: fix brittle color-class assertions (`#1B2A4A`, `bg-gray-900`, `font-mono` `toHaveClass` lists), add `data-testid`s.

**FOLD IN — 2 Phase-31 review HIGHs that live on this exact surface (ISSUES-REGISTER):**
- **ISS-035 (HI-02, ACTIVE path):** the chat lane shows NO "Cancelled by you" ack after Stop — `pipeline_cancelled` sets no cancelled flag / pushes no chat message → `runLaneState` falls through to `idle` (violates LIVE-STATE-CONTRACT §1). SC-4 (cancelled faithful) MUST close this. The fix touches FIX-039-sensitive `useWorkflow.ts` — preserve the unconditional-accumulator-reset ordering.
- **ISS-036 (HI-01, latent SSE-ON):** thread `pipelineState.pipelineRunId` into `useRunChat.runId` (today bound to clarify-only `activePipelineRunId`, null while building) so the SSE command path would target the live run, not a fresh `POST /api/runs`. Cheap to do right while wiring; leaves SSE dormant (LOCK-B).

Authoritative inputs (READ — do not re-derive): POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §72 (the FULL Phase-32 brief incl. the 4 inline-gate KAN behaviors), §31 (D-12 live-state contract — amended state deltas), §29 (D-15 authority: tokens←DS mock, shared-surface truth = `evidence 11 §B`, behavior←product; reuse-don't-rebuild), §51 (ND-6 Audit export), §95 (the 3 endpoints — owner-scoped, IDOR→404, `user_id`-keyed). Evidence: `01-run-ui-teardown.md` (run-screen anatomy + result cards + tab structure), `07-synthesized-contracts.md` (D-12 live-state table), `11-cross-mock-reconciliation.md §B` (THE shared-surface source of truth: running=blue `#3C2CDA`, "Not run"=grey, one badge/status, radius buttons 10/cards 14, nav purple-underline), `02-workspace-shell-teardown.md` (token/DS extraction). Phase-28 contracts: `.planning/phases/28-chat-contracts-guards-a0/contracts/` (`LIVE-STATE-CONTRACT.md` — the state→render table incl. §1 cancelled; the Steps-L2 artifact-block derivation contracts: pages←`route_table.py`, tasks←`task_list`, checks←`validation_results`, construction←`wave_*`/`subagent_*`/`task_progress`). The DS mock `Hexaware Run - Design System.dc.html` for exact token values.
</domain>

<decisions>
## Implementation Decisions — LOCKED (POR §3 / D-15 / D-12; do NOT re-open)

- **Token layer FIRST**, then everything consumes it (no per-page palette fork). Tokens = DS mock EXTENDED with the status palette it omits + a resolved radius ladder (D-15 i). Shared-surface values come from `evidence 11 §B`, NOT any single mock (the mocks drift — running=blue is correct, Handoff's amber is a bug).
- **Reskin-look, keep-behavior (D-15):** adopt the visual language; KEEP the product's richer live-data behavior and REUSE existing components (`AgentThinkingTab`, `WaveTreePanel`, `PreviewPanel`/`FIRST_PARTY_RENDERERS`, the Phase-31 `RunChatLane`) over rebuilding from the mock's stale/hardcoded versions — a face-value rebuild REGRESSES.
- **Live-state contract (D-12):** real event → lane render + composer mode + Steps behavior, per state; the transcript ACCUMULATES across states/revisions; the mock's phase scrubber is excluded (a real phase indicator replaces it). Cancelled/degraded/planner-running/fix-loop are real states the mock omits — render them.
- **Inline gate-card behaviors** carry **KAN-101** (Update-the-Specs action + "Accept & continue to build" relabel on analyze gates — **generalized off a declared gate/artifact-kind flag**, NOT the `prototype-analyze`/`prototype-specify` name literals), **KAN-95** (reject-confirm dialog + navigate-home-on-reject), **KAN-100** (`isPipelineRunning` guard + terminal auto-dismiss + `approve_review`→`pipeline_not_running`), **KAN-98** (`retainAgentEdit` — gate edits persisted but not echoed, client retains). Reuse KAN-100's cancel-aware gate wait — do NOT re-implement Stop-while-paused.
- **Output name "Deliverable"** (LOCK-F). **Audit governance palette** is the sole one-chroma exception.

INVARIANTS: **SC-001** (Steps/gate/Preview keyed on GENERIC event/artifact types + declared flags, NEVER a workflow name — and FIX the existing `prototype-analyze`/`prototype-specify` literal leak into a declared flag), **INV-3** (the 3 Audit endpoints are additive read-only; the 5 backend goldens untouched — FE reskin can't touch them by construction), **INV-13** (no engine/runner change), import-linter 4/0 (endpoints kernel-pure or app-side, self-registered), **additive migrations only** (Q3 — none expected; the endpoints READ existing `gate_events`/`validation_results`/`exec_runs` tables the engine already populates), owner+workspace on the endpoints (IDOR→404, `user_id`-keyed per P13/P25 — NOT the nullable `owner_id`). **FIX-039** ordering preserved in `useWorkflow.ts`. **LOCK-B**: legacy WS stays the ACTIVE transport (SSE dormant); do NOT delete or activate it here.
</decisions>

<code_context>
## Existing Code Insights (from evidence 01/07 + Phase 31)

Run surface: `frontend/src/app/dashboard/page.tsx` + `frontend/src/components/layout/DashboardLayout.tsx` (run surface + tab host). Steps sources: `frontend/src/components/workflow/AgentThinkingTab.tsx` + `WaveTreePanel.tsx` (→ restructure into the 3-level drill-down; WaveTreePanel is the L3 fanout source — note ISS-019: it sits below the fold today, mount it into the drill-down). Preview: `PreviewPanel.tsx` + `FIRST_PARTY_RENDERERS` (keep generic dispatch, add the manual switcher). Lane + reducer: the Phase-31 `RunChatLane`/`useRunChat` + `useWorkflow.ts` (FIX-039 ordering; **ISS-035 cancel-ack + ISS-036 runId land here**); `AgentProgressPanel.tsx` (controls to absorb). Backend Audit reads: clone the P13/P25 owner-scoped read-endpoint pattern (`WorkflowRun.user_id == principal` two-layer → 404); tables `gate_events`/`validation_results`/`exec_runs` already exist (engine-populated). Tokens: `frontend/src/app/globals.css` + tailwind config. Offline verify: `vitest run`, mocked Playwright `--project=mocked` (verify BY DELTA vs the pre-existing 128-red baseline — DEF-29-06-1), `tsc --noEmit` identity; backend targeted suites + `/opt/homebrew/bin/lint-imports`; `python3.11`; full pytest HANGS — never run it.
</code_context>

<specifics>
## Specific Ideas

Land the token layer + primitives first (own wave) so the rest consumes them. Then: left-lane mount (folding ISS-035 cancelled-ack + ISS-036 runId), the Preview/Steps/Files/Audit tab restructure, the Steps 3-level drill-down (reuse AgentThinkingTab/WaveTreePanel, gate/clarify inline, the 4 KAN gate behaviors + the SC-001 literal-leak fix + KAN-99 N-1 cap), the 3 additive owner-scoped Audit endpoints + CSV/JSON export, failed/degraded/cancelled affordances + "What went wrong" card. Harden e2e: replace brittle color-class assertions with token/testid assertions; add data-testids. Verify BY DELTA. Backend goldens byte-identical.
</specifics>

<deferred>
## Deferred Ideas

SSE activation (LOCK-B — legacy WS stays active; ISS-036 wires it correctly but leaves it dormant). Compliance-PDF export (ND-6 — CSV/JSON only). The Concierge LLM (Phase 33). Shell chrome / nav / other pages (Phase 35+). Handoff screen (deferred post-v2.0). ISS-037 MED/LOW cluster — fold in opportunistically where the rework already touches that code (transcript-clear-on-run-switch, attachment render, sendMessage rejection), else leave tracked.

## Execution-viability note (autonomous run)
FE-heavy + 3 additive read-only endpoints — offline-verifiable (vitest + mocked Playwright delta + tsc identity; backend targeted suites + lint-imports). No live server needed for structural proof. Live multimodal/visual confirmation defers to the Phase-34 live pass. Verify BY DELTA against the pre-existing e2e baseline; if a check needs a live server, mark it live-deferred — do not hang, do not fabricate.
</deferred>
