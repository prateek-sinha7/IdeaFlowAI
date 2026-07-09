# Phase 37: Configure Unification + Composer/Wizard [B3] - Context

**Gathered:** 2026-07-09
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss) — grounded in the locked POR §86 + D-15/C + ND-12 + LOCK-E/F + evidence 08 + ROADMAP SC.

<domain>
## Phase Boundary — the milestone's biggest restructure

One generic per-run setup surface for EVERY deliverable type + the Composer/Wizard rebuild + the Agent drawer + the Workflow dialog. This is the phase with a real **architectural change** (D-15/C), not just a reskin. FRONTEND-heavy + an ADDITIVE backend/run-launch change (generic template/DS inputs). Depends on Phase 36; ND-1/ND-7/ND-8 are decided (LOCK-E/F).

Deliverables (ROADMAP SC 1–3 + POR §86):
1. **Configure screen (generic per-run setup):** Describe + Templates + Design System + Review Gates + Workflow Settings accordions for ANY deliverable type. **⭐ The D-15/C architectural change:** promote template/DS from the prototype-ONLY wizard to **declared run inputs for EVERY deliverable** — the run-launch path must accept template/DS GENERICALLY (an SC-001-style declared input, NOT a prototype-hardcoded branch). This MUST be ADDITIVE: the existing prototype/PPT template/DS flow stays **byte-identical** (INV-3 goldens); other deliverables merely GAIN the declared option.
2. **Composer + Wizard rebuild (evidence 08 / ND-12):** ~13 surfaces are **reskins of already-built P22 code — REUSE, do NOT rebuild from the mock's stale hardcoded versions**: the LIVE `/api/capabilities` palette (NOT the mock's hardcoded 8), the `AdvancedExpander` levers INCLUDING the validator→gate coupling, the built-but-UNMOUNTED `AgentModelPicker` (mount it inline), and `/api/user-workflows` CRUD. Genuine NEW work = a unified **Template→DS→Discovery stepper** with a **Web/Deck toggle** (NEW-BUILD) + wiring the orphaned `DiscoveryForm`.
3. **Agent drawer** (4-tab inspector: Overview/Skills/Hooks/Config) live against real data — **ND-7 gate: per-agent prompt-override PERSISTENCE is DEFERRED (LOCK-E)**; surface the Config tab but do NOT build durable override persistence. **Workflow dialog:** surfaces declared capabilities/context/compaction with "Engineer-only" gating = the `user_allowed` reflection.
4. **Draft-run persistence (ND-1 consumer #2)** — per LOCK-E, ND-1 is **CLIENT-SIDE ONLY, kept until launch (NO draft rows / no DB persistence)**.

**Deferred backend — do NOT build face-value from the mock (ND-12 / Category-B/D):** workflow visibility/team-sharing, pre-run cost/duration estimates, discovery page-selection.

Authoritative inputs (READ): POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §86 (the Phase-37 brief), D-15 + D-15/C (the generic template/DS run-input decision — the run-launch path accepts template/DS generically), §56 (ND-12: the ~13-surface composer/wizard reskin scope + reuse list + the deferred backend), §41 (LOCK-E: defer ND-7 override-persistence, ND-1 client-side-only), §42 (LOCK-F: DS ~14, output="Deliverable", P22 display_names), §47 (ND-7 gate). Evidence: `08-composer-wizard-teardown.md` (THE map — the ~13 surfaces ↔ their current P22 code, the reuse list, the NEW-BUILD stepper + orphaned DiscoveryForm), `12-coverage-and-backend-map.md` (the run-launch path + `/api/capabilities` + `/api/user-workflows` + the AdvancedExpander/AgentModelPicker current state). The `gsd-pattern-mapper` MUST map every reused surface to its current file BEFORE planning (reuse is the dominant mode here).
</domain>

<decisions>
## Implementation Decisions — LOCKED (POR §3 / D-15/C / ND-12 / LOCK-E/F; do NOT re-open)

- **⭐ D-15/C — generic template/DS run inputs.** Template/DS become DECLARED run inputs any deliverable can opt into (SC-001: keyed on a declared capability/manifest flag, NEVER a prototype-only branch). ADDITIVE only — prototype/PPT's existing template/DS run-launch flow stays byte-identical (INV-3 goldens prove it); the change lets OTHER deliverables accept template/DS, it does not alter prototype's.
- **Reuse over rebuild (D-15 / evidence 08).** REUSE the live `/api/capabilities` registry (not the mock's hardcoded 8 caps), the `AdvancedExpander` levers + validator→gate coupling, the built-but-unmounted `AgentModelPicker` (mount inline), `/api/user-workflows` CRUD. A face-value rebuild from the mock REGRESSES (mock hardcodes 8 caps, bool retry vs `[1,2,3]`, drops validator→gate). NEW-BUILD only: the unified Template→DS→Discovery stepper (Web/Deck toggle) + wiring the orphaned `DiscoveryForm`.
- **ND-7 gate (LOCK-E):** the Agent-drawer Config tab surfaces per-agent prompt-override but its PERSISTENCE is DEFERRED — do NOT build durable override storage.
- **ND-1 (LOCK-E):** draft-run persistence is CLIENT-SIDE only (kept until launch, no draft rows / no DB).
- **Workflow dialog:** "Engineer-only" gating reflects the capability `user_allowed` flag (declared data, not a code branch — INV-5).
- **DS picker = real ~14 (LOCK-F, ND-8);** output = "Deliverable"; deliverable-type names = P22 `display_name`s.

INVARIANTS: **SC-001/INV-1** (template/DS/gates/settings keyed on DECLARED inputs + `user_allowed`, NEVER a workflow-name/prototype-only branch — the milestone's core-value test, applied to run-launch inputs), **INV-3** (the generic template/DS change is ADDITIVE — the 5 characterization goldens byte/event-identical; prototype/PPT run-launch unchanged; any new `pipeline_complete` key → `_VOLATILE_STRIP_KEYS`), **INV-5** (manifests stay data — the template/DS/`user_allowed` declarations compile as data, no DSL), **INV-13** (no runner change), import-linter (any backend impl kernel-pure or app-side against ports; 4/0), **additive migrations only** (Q3 — client-side draft-run = no table; if any run-launch column is truly needed it's additive + owner+workspace), **token gate** (Phase-35 discipline — per-file retired-palette=0 + positive `@theme`/primitive), **a11y**, **LOCK-B** (no transport touch). Reuse Phase-32 primitives + Phase-35 shell + Phase-36 surfaces.
</decisions>

<code_context>
## Existing Code Insights (from evidence 08/12 + prior phases)

The composer/wizard surfaces are already-built P22 code (evidence 08 maps each ↔ its file): the live `/api/capabilities` palette, `AdvancedExpander` (with the validator→gate coupling), the unmounted `AgentModelPicker` (mount it), `/api/user-workflows` CRUD, the orphaned `DiscoveryForm` (wire it). The run-launch path (where prototype/PPT accept template + design-system today) is the D-15/C target — make it accept template/DS via a DECLARED input generically (additive; prototype's path byte-identical). The Configure screen unifies Describe + Templates + DS + Review Gates + Workflow Settings as accordions for any deliverable. Agent drawer + Workflow dialog read the real capability/manifest data. Consume the Phase-32 tokens + Phase-35 shell + Phase-36 surfaces. Offline verify: `vitest run`, `tsc --noEmit` identity, per-file retired-palette grep=0; backend targeted suites + the 5 characterization goldens byte-identical + `/opt/homebrew/bin/lint-imports` 4/0; `python3.11`; full pytest HANGS — never run it. Mocked Playwright times out offline → e2e live-deferred. The pattern-mapper's reuse map is load-bearing — plan reuse, not rebuild.
</code_context>

<specifics>
## Specific Ideas

Land the D-15/C generic template/DS run-input change FIRST (additive, prototype byte-identical, goldens proven) since the Configure screen depends on it. Then: the Configure screen (Describe/Templates/DS/Review Gates/Workflow Settings accordions for any deliverable); the Composer/Wizard reskin REUSING the live `/api/capabilities` palette + `AdvancedExpander` (validator→gate) + inline `AgentModelPicker` + `/api/user-workflows` CRUD; the NEW unified Template→DS→Discovery stepper (Web/Deck toggle) + wired `DiscoveryForm`; the Agent drawer (4-tab, ND-7 override-persistence deferred); the Workflow dialog (capabilities/context/compaction + `user_allowed` gating); client-side draft-run persistence (ND-1, no rows). Per-file token gate, a11y, reuse-don't-rebuild. Verify by delta; goldens byte-identical.
</specifics>

<deferred>
## Deferred Ideas

Backend NOT built (ND-12/Category-B/D): workflow visibility/team-sharing, pre-run cost/duration estimates, discovery page-selection. ND-7 per-agent prompt-override PERSISTENCE (LOCK-E — drawer surfaces it, no durable store). ND-1 draft rows (client-side only). Live Concierge/steering (Phase 34). Analytics/notifications feed (Phase 38). Mocked-Playwright e2e (offline timeout — live-deferred). Handoff (post-v2.0).

## Execution-viability note (autonomous run)
FE-heavy reuse + an ADDITIVE run-launch change — offline-verifiable (vitest + tsc identity + per-file grep; backend targeted suites + the 5 goldens byte-identical + lint-imports 4/0). The riskiest task (D-15/C generic template/DS) is gated by the goldens staying byte-identical — prove it, do not presume. Mocked Playwright is live-deferred (offline webServer timeout). Live confirmation → Phase 34. If a check needs a live server, mark it live-deferred — do not hang, do not fabricate.
</deferred>
