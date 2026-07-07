# Phase 28: Chat Contracts & Guards [A0] - Context

**Gathered:** 2026-07-07
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss) — grounded in the locked POR + evidence pack.

<domain>
## Phase Boundary

Every contract the later v2.0 phases build against is pinned BEFORE any code: (1) the chat event vocabulary + golden guards, (2) the Steps artifact-derivation rules, (3) the live-state contract, (4) the e2e mockWs chat driver contract, and (5) the ND decision records — now RESOLVED (see the decision lock). This is a contracts/tests/docs phase — no production runtime behavior beyond additive test scaffolding and normalizer/vocabulary entries that keep the 5 characterization goldens byte/event-identical.

Authoritative inputs (READ THESE — do not re-derive):
- **POR:** `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` — §2 (D-01..D-15), §3 (the ⭐ AUTONOMOUS-RUN DECISION LOCK — every ND is resolved there), §6 (contract changes), §7 (landmines).
- **Evidence:** `.planning/v2.0-evidence/03-backend-chat-surface-map.md` (event taxonomy, `_DOCUMENTED_EVENT_TYPES`, `_VOLATILE_STRIP_KEYS`, run_events), `07-synthesized-contracts.md` (the D-12 live-state table + figure-to-field pinning + coverage cross-check), `01-run-ui-teardown.md` (Steps artifact blocks ×4 kinds → their data sources), `11-cross-mock-reconciliation.md` §B (canonical shared-surface spec), `12-coverage-and-backend-map.md` (index).
- **Post-merge facts:** `approve_review` carries 4 actions incl. `update_specs` (KAN-101); `pipeline_not_running` terminal fence (KAN-100); gates are event-driven (KAN-94); gate edits not echoed over WS (KAN-98). The image-input spine already landed (evidence 12; quick tasks edw/frv/gvq).
</domain>

<decisions>
## Implementation Decisions — LOCKED (POR §3 decision lock; do NOT re-open)

- New event types `chat_message`, `chat_reply`, `stream_attached` → add to `_DOCUMENTED_EVENT_TYPES` (`tests/agents/test_phase3_cutover_verify.py`); volatile subkeys → `_VOLATILE_STRIP_KEYS` (`tests/agents/characterization/_normalize.py`). Characterization proof: chat events NEVER fire on the 5 golden pipelines (scripted harness emits none) → goldens stay byte/event-identical (INV-3).
- Artifact-derivation contracts for Steps L2: pages ← prototype route table (`route_table.py`); tasks ← `task_list` artifact; checks ← `validation_results`; construction ← `wave_*`/`subagent_*`/`task_progress` (dual-source, with the KAN-99 N-1 checklist cap).
- The D-12 live-state contract (evidence 07 §1, incl. the post-merge deltas: `update_specs`, reject-confirm, terminal fence, spec-revision loop-back state, planner window) is captured as a UI-SPEC-ready table.
- Figure-to-field pinning (evidence 07 §3): every number the run screens show maps to a producing field — verify `agent_input.context_sources` carries name+size; cache % from P26 telemetry.
- mockWs e2e chat driver contract defined (new driver, matching the existing `mockWs.ts` frame shape `{type, data:{…, event_id, seq}}`).
- Decision records: transcribe the POR decision lock (LOCK-A..G) into this phase's outputs as the resolved ND-1..ND-13 record — they are DECIDED, this phase just formalizes them. Transport is ADDITIVE-ONLY (LOCK-B). Concierge always-on (ND-2); defer team-sharing/resume-from-failed/prompt-override/image-persistence (LOCK-E); output name "Deliverable", DS real count, P22 type names (LOCK-F).

INVARIANTS: SC-001/INV-1 (no kernel workflow-name branch), INV-3 (5 goldens byte/event-identical), INV-13, import-linter 4/0, additive-only.
</decisions>

<code_context>
## Existing Code Insights

Codebase context gathered during plan-phase research. Key anchors from the evidence: `backend/app/api/websocket.py` (event emission + `_DOCUMENTED_EVENT_TYPES` usage), `backend/tests/agents/test_phase3_cutover_verify.py:182-227` (documented event types), `backend/tests/agents/characterization/_normalize.py:101-170` (`_VOLATILE_STRIP_KEYS`), `backend/agents/execution_engine/engine.py` (run_events emit boundary), `frontend/e2e/fixtures/mockWs.ts` (e2e driver to extend). Offline verification: use the targeted parity/gate suite (~35s) + lint-imports at `/opt/homebrew/bin/lint-imports` — the full backend pytest hangs offline.
</code_context>

<specifics>
## Specific Ideas

Deliverables: (1) the two new-event-type + volatile-key additions with a characterization proof test; (2) a written artifact-derivation contract doc for Steps L2; (3) the D-12 live-state contract table (UI-SPEC input for phases 31/32); (4) the mockWs chat driver contract; (5) the resolved-decisions record. Keep it contracts + tests + docs — zero kernel edits, goldens byte-identical.
</specifics>

<deferred>
## Deferred Ideas

Per LOCK-E: workflow team-sharing, resume-from-failed-step, per-agent prompt-override persistence, image-persistence-on-reopen — all deferred out of this milestone. Draft-run persistence (ND-1) not built (client-side chat only).
</deferred>
