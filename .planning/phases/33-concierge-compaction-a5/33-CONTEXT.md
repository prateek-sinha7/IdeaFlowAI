# Phase 33: Concierge + Compaction [A5] - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss) — grounded in the locked POR §74 + D-04/D-05/D-08 + evidence + ROADMAP SC.

<domain>
## Phase Boundary

Add free-form conversation to every run via ONE orchestrator capability, keep long transcripts inside budget, and turn post-run chat into revision runs — all as REGISTERED capabilities on the Phase-29 backbone (depends on Phase 29, NOT Phase 32). BACKEND-heavy (3 new capabilities) + a little FE (confirm chips, "compact" affordance, context/token display).

Three new capabilities (each `@register` + `_KNOWN` + `discover()` in lockstep + drift-guard bump — POR §97):
1. **`chat:concierge` (D-05)** — per-run instances; deepagents via the sanctioned `deep_agent_runner` (INV-13), Haiku default, prompt-cached. Workflow-specificity comes from CONTEXT (compiled manifest, artifacts, events, conversation) — NEVER per-workflow code. Tools = **READ** (run events/artifacts/steps via `ScopedStore`, owner-scoped) + **PROPOSAL-ONLY** (`propose_steering_note`, `propose_revision`, `propose_gate_action` — action set incl. `update_specs`). The app layer EXECUTES proposals through the SAME channels as the Phase-29 router; consequential ones behind a **confirm chip**. "The Concierge proposes; the engine disposes."
2. **`compaction:chat_history` (D-08)** — backend-owned: summarize turns beyond budget, keep recent verbatim (deepagents `SummarizationMiddleware` for in-graph growth).
3. **`context_provider:conversation` (D-08)** — reads chat `run_events` (compacted) into Concierge/steering contexts.

Plus: **router escalation** — free-form (non-routable) turns escalate from the Phase-29 mechanical router (D-04) to the Concierge; routable turns (clarify/gate/steering/revision) still take ZERO model calls. **Post-run iteration (D-02)** — conversational revision turns produce revision runs stitched into the family transcript (live stitching). **FE** — confirm-chip UX for Concierge proposals; a "compact" affordance; token/context-usage display (P26 telemetry).

Deliverables map to ROADMAP SC 1–4:
1. Concierge answers run questions from REAL run data; proposals execute only through existing channels (proposal-only + confirm chip).
2. `compaction:chat_history` + `context_provider:conversation` bound the composed history — PROOF: a long transcript's composed context stays under budget with recent turns verbatim.
3. Post-run chat turns produce revision runs stitched into the family.
4. **SC-001 proof:** a brand-new custom workflow gets lane + router + Concierge with ZERO engine/FE/orchestrator code (all workflow-specificity = declared data or run context). This is the milestone's core-value proof.

Authoritative inputs (READ): POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §74 (Phase-33 brief), D-04 (router — the escalation seam; four gate actions incl. `update_specs`; event-driven gates KAN-94; terminal fence KAN-100), D-05 (the ONE-implementation / per-run-instances / proposal-only orchestrator — the binding design), D-08 (backend-owned compaction + conversation provider), §41 (LOCK-E: Concierge always-on), §47 (ND-2: Concierge behind a per-run toggle initially, Haiku default), §97 (the 3 capabilities + register lockstep), §104/§116 (invariants). Evidence: `03-backend-chat-surface-map.md` (the mechanical router, `run_events`, `ScopedStore`, steering/revision channels), `05-chat-library-research.md` (compaction verdict: ALWAYS backend — no FE library compresses), `12-coverage-and-backend-map.md`. Phase-29 artifacts to build ON (do NOT rebuild): `backend/app/api/chat_router.py` (the mechanical router — ADD the escalation branch), `run_commands.py` (proposal execution via the same channels), the `ectx.steering_notes` seam + revision channels, `run_events`.
</domain>

<decisions>
## Implementation Decisions — LOCKED (POR §3 / D-04 / D-05 / D-08; do NOT re-open)

- **ONE `chat:concierge` capability, per-run instances (D-05).** Workflow-specificity from CONTEXT, never per-workflow code. Proposal-only tools; the engine executes through the same channels as the router; consequential proposals behind a confirm chip. Optional per-workflow customization = declared manifest `chat:` data (suggestions, concierge notes), compiled as data (INV-5).
- **Mechanical router first, Concierge as escalation (D-04).** Routable turns stay zero-model-call; only free-form turns hit the Concierge. Route `update_specs` to the shipped KAN-101 loop (never rebuild spec-revision as a steering note or child run).
- **Compaction backend-owned (D-08).** Summarize-beyond-budget + keep-recent-verbatim; `context_provider:conversation` feeds compacted history. FE only DISPLAYS usage + a compact affordance — no FE compression.
- **Concierge rollout (ND-2):** default-on lane+router; Concierge behind a per-run toggle initially; Haiku default model.
- **Live-deferred to Phase 34:** live Concierge Q&A, multi-turn cache-point placement, live mid-run steering delivery. Build + offline-prove here; the live pass confirms (expect `human_needed` on those items).

INVARIANTS: **SC-001** (a brand-new custom workflow gets lane+router+Concierge with ZERO engine/FE/orchestrator code — no workflow-name branch anywhere new, INV-1), **INV-13** (Concierge model calls ONLY via `deep_agent_runner` — banned-pattern CI gate), **INV-3** (5 goldens byte/event-identical; chat/concierge events NEVER fire on golden paths; new event types → `_DOCUMENTED_EVENT_TYPES`, new `pipeline_complete` keys → `_VOLATILE_STRIP_KEYS`), **INV-5** (manifest `chat:` stays data), **INV-12** (ONE chat subsystem — reuse the Phase-29 seams, don't fork; do NOT touch ChatRunner / `test_chat_contract.py` golden / `user_message` semantics; `_INTERNAL_PIPELINES` stays), import-linter (capabilities never import kernel/`app`; heavy-dep Concierge impl under `app/agents/**` against ports), additive migrations only (Q3 — reuse `run_events`; owner+workspace on anything persisted), owner-scoped Concierge reads (IDOR→404 via `ScopedStore`). Bedrock caching is already ON (P26) — do NOT re-diagnose; multi-turn placement is the Phase-34 live check.
</decisions>

<code_context>
## Existing Code Insights (from evidence 03/05 + Phase 29/30)

Router: `backend/app/api/chat_router.py` (`route_chat_turn` — ADD the free-form→Concierge escalation branch; keep routable turns zero-model). Runner: the sanctioned `deep_agent_runner` / `from deepagents import create_deep_agent` (INV-13 — the Concierge runs here, Haiku, prompt-cached via the P26 `_BedrockCachePointsMiddleware`). Registry: `backend/agents/capabilities/registry.py` (`@register` + `_KNOWN` + `discover()` lockstep + drift-guard count — bump for the 3 new caps; CLONE the `context_provider:uploaded_files` pattern from Phase 30 for `context_provider:conversation`). Owner-scoped reads: `backend/agents/authz.py` `ScopedStore.read_events`/artifacts (the Concierge READ tools + `context_provider:conversation` source). Proposal execution: `run_commands.py` (the SAME gate/steering/revision channels the router uses). Compaction: deepagents `SummarizationMiddleware`; the `chat:` manifest key compiles as data. FE: the Phase-31 `RunChatLane` (add confirm chips for proposals + a "compact" affordance) + the P26 token widget (context-usage display). Offline verify: targeted capability/register/parity suites + `/opt/homebrew/bin/lint-imports` (4/0), `python3.11`; full pytest HANGS — never run it. Live Concierge/cache → Phase 34.
</code_context>

<specifics>
## Specific Ideas

Build the 3 registered capabilities (register lockstep + drift-guard bump): `chat:concierge` (deep_agent_runner/Haiku, read + proposal-only tools, per-run instance, confirm-chip execution through the router's channels), `compaction:chat_history` (summarize-beyond-budget / keep-recent-verbatim), `context_provider:conversation` (compacted `run_events`). Add the router's free-form→Concierge escalation. Wire post-run chat → revision runs stitched into the family (D-02). FE: confirm chips + compact affordance + context/token display. Prove SC-001 with a throwaway custom manifest getting lane+router+Concierge with ZERO code. Offline: register/discover lockstep tests, compaction-under-budget proof (long transcript → recent verbatim + summarized tail), proposal→channel execution tests, goldens byte-identical (concierge dormant on golden paths). Live Concierge Q&A/cache deferred to Phase 34.
</specifics>

<deferred>
## Deferred Ideas

Live Concierge Q&A + multi-turn cache-point placement + live mid-run steering (Phase 34 live pass — expect `human_needed`). Per-agent prompt-override, team-sharing, resume-from-failed (LOCK-E). The FE reskin is done (Phase 32); Phase 33 rides the token layer. Handoff screen deferred post-v2.0.

## Execution-viability note (autonomous run)
The 3 capabilities + router escalation + revision stitching are additive backend (+ small FE), offline-testable (register/discover lockstep, compaction-under-budget shape proof, proposal→channel unit tests, goldens byte-identical with concierge dormant). No live server needed for structural proof. Live Concierge/multimodal/cache confirmation → Phase 34. If a check needs live Bedrock/SSO, mark it live-deferred — do not hang, do not fabricate.
</deferred>
