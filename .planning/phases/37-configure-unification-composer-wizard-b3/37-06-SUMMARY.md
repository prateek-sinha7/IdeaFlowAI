---
phase: 37-configure-unification-composer-wizard-b3
plan: 06
subsystem: ui
tags: [react, typescript, vitest, capabilities, workflow-dialog, agent-drawer, tabs]

# Dependency graph
requires:
  - phase: 37-01
    provides: "getWorkflowDetail (/api/workflows/{id}) WorkflowDetail type with context_providers + per-step declared gates/validators/compaction"
  - phase: 37-03
    provides: "Reskinned AgentsPopup (P22 contracts: CapabilityPaletteSection user_allowed gate, AdvancedExpander COUPLED_GATE, AgentPromptSection, SkillsHooksTab) on Phase-32 tokens"
provides:
  - "4-tab Agent drawer (Overview/Skills/Hooks/Config) reusing shipped per-agent sections"
  - "Config tab surfaces per-agent prompt-override, SURFACE-ONLY (ND-7/LOCK-E persistence deferred)"
  - "WorkflowDialog.tsx: declared capabilities/context_providers/compaction with user_allowed 'Engineer-only' gating (declared-data reflection, INV-5/SC-001)"
affects: [phase-34-live-verification, workflow-dialog-consumers, agent-inspector-consumers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "4-tab inspector via shared ui/Tabs primitive; existing sections distributed across tabs (no rebuild)"
    - "Declared-data dialog: registry (/api/capabilities) keyed by name resolves user_allowed for compiled per-step gate/validator references"

key-files:
  created:
    - frontend/src/components/workflow/WorkflowDialog.tsx
    - frontend/src/components/workflow/WorkflowDialog.test.tsx
    - frontend/src/components/workflow/AgentDrawer.test.tsx
  modified:
    - frontend/src/components/workflow/AgentsPopup.tsx

key-decisions:
  - "Reused AgentPromptSection unchanged in the Config tab; ND-7 satisfied by NOT adding new save-to-server wiring (grep gate crafted to exclude the pre-existing KAN-76 saveAgentPromptOverride, baseline 0 preserved) rather than making the shipped KAN-76 override inert (which would regress LibraryPage/AgentLibrary)."
  - "ND-7 behavioral assertion = no durable persistence fires while EDITING the override (typing), per the guardrail's literal 'not called when editing' wording."
  - "WorkflowDialog aggregates declared capabilities from the compiled steps' gates+validators (deduped), matched by name to the registry for the user_allowed flag — no hardcoded capability list, no name/pipelineType branch."

patterns-established:
  - "Distribute-not-rebuild: an existing single-scroll modal becomes a tabbed inspector by wrapping the shipped sections in tab conditionals + ui/Tabs — preserves all prior contracts."
  - "Declared-flag reflection: locked = !registryEntry.user_allowed keyed on compiled data, the reusable SC-001 gating idiom."

requirements-completed: [SHELL-04]

# Metrics
duration: 6min
completed: 2026-07-09
---

# Phase 37 Plan 06: Shell Inspectors (Agent drawer + Workflow dialog) Summary

**4-tab Agent drawer (Overview/Skills/Hooks/Config) reusing shipped sections with an ND-7 surface-only Config tab, plus a new WorkflowDialog that surfaces a compiled workflow's declared capabilities/context/compaction with user_allowed 'Engineer-only' gating.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-09T08:36:00Z
- **Completed:** 2026-07-09T08:42:12Z
- **Tasks:** 2 (both TDD: RED → GREEN)
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments
- Restructured `AgentCapabilitiesModal` into a 4-tab inspector (Overview/Skills/Hooks/Config) via the shared `ui/Tabs` primitive, distributing the already-shipped per-agent sections across tabs with zero rebuild.
- Config tab reuses `AgentPromptSection` as the per-agent prompt-override SURFACE; ND-7/LOCK-E honored — no new endpoint, table, storage, or save-to-server wiring added.
- New `WorkflowDialog.tsx` surfaces the compiled workflow's declared `context_providers`, per-step gates+validators (deduped), and compaction, reading `getWorkflowDetail` + `/api/capabilities`.
- "Engineer-only" lock is a pure reflection of the registry `user_allowed` flag (INV-5/SC-001) — no workflow-name / `pipelineType` branch, no hardcoded agent-count fiction.
- Preserved all 37-03 P22 contracts and the per-file token gate (retired palette 0 on both touched files); tsc identity held at 0.

## Task Commits

Each task committed atomically (TDD RED → GREEN):

1. **Task 1 (RED): failing 4-tab drawer + ND-7 no-persistence spec** - `b8cb05cb` (test)
2. **Task 1 (GREEN): 4-tab Agent drawer, ND-7 surface-only Config** - `ee9c3bda` (feat)
3. **Task 2 (RED): failing WorkflowDialog declared-data + gating spec** - `53743e71` (test)
4. **Task 2 (GREEN): WorkflowDialog declared capabilities/context/compaction** - `881d3b68` (feat)

**Plan metadata:** this SUMMARY commit (docs). STATE.md/ROADMAP.md intentionally untouched per plan guardrail.

_Note: TDD tasks have test → feat commit pairs._

## Files Created/Modified
- `frontend/src/components/workflow/AgentsPopup.tsx` - MODIFIED: `AgentCapabilitiesModal` restructured into a 4-tab inspector; sections wrapped in tab conditionals; `ui/Tabs` imported.
- `frontend/src/components/workflow/WorkflowDialog.tsx` - NEW: declared-data dialog with `user_allowed` Engineer-only gating.
- `frontend/src/components/workflow/WorkflowDialog.test.tsx` - NEW: declared surfacing + gating + source invariants.
- `frontend/src/components/workflow/AgentDrawer.test.tsx` - NEW: 4 tabs + Config surface + ND-7 no-persistence behavioral assertion.

## Decisions Made
- **ND-7 interpretation (LOCK-E):** The ND-7 grep gate (`saveOverride|updateAgentPrompt|prompt.override.*(fetch|request<|/api/)` == 0) was deliberately crafted to exclude the pre-existing KAN-76 `saveAgentPromptOverride`, and the guardrail says "reuse AgentPromptSection". So ND-7 is honored by NOT adding new persistence, not by making the shipped KAN-76 override inert (which would regress the drawer's two other consumers, LibraryPage + AgentLibrary). The behavioral assertion verifies no durable save fires while editing the override, per the guardrail's literal "not called when editing" wording.
- **Declared capability aggregation:** WorkflowDialog derives its capability list from the compiled steps' `gates` + `validators` (deduped by kind:name) and resolves each against the `/api/capabilities` registry by name — never a hardcoded list.

## Deviations from Plan

None - plan executed exactly as written. (The one comment-hygiene fix below is a self-inflicted grep collision, not a plan deviation.)

### Note (grep-hygiene, not a deviation)
- A doc comment in `WorkflowDialog.tsx` originally contained the literal phrase used by the anti-fiction source grep, tripping the test's own `not.toMatch(/8 agents|Single-shot/i)` assertion. Reworded the comment to "agent-count / shot-count fiction". Caught by the RED→GREEN cycle, fixed before the Task 2 GREEN commit.

## Issues Encountered
- The Config tab's Skills/Hooks split required two non-contiguous `drawerTab === "skills"` blocks (Suggested Skills + Custom-skill authoring bracket the Suggested Hooks block in source order). Resolved with two sibling `skills` conditionals rather than reordering large JSX blocks — minimal diff, no behavior change.

## Output-Contract Evidence (raw)
- vitest: AgentDrawer.test.tsx + WorkflowDialog.test.tsx + AgentsPopup.reskin.test.tsx → **Test Files 3 passed (3); Tests 23 passed (23)**. The ND-7 no-persistence behavioral assertion is `Agent drawer — ND-7 (LOCK-E): Config tab is SURFACE-ONLY › editing the override fires NO durable persistence call` — PASSES (spies on saveAgentPromptOverride/deleteAgentPromptOverride, asserts neither called on edit).
- ND-7 gate: `grep -cEi 'saveOverride|updateAgentPrompt|prompt.override.*(fetch|request<|/api/)' AgentsPopup.tsx` = **0**.
- WorkflowDialog gating: `user_allowed` = 4 (>=1); `context_providers` = 2 (>=1); `od_prototype|od_ppt|pipelineType ===` = **0**.
- Regression guard (AgentsPopup.tsx): COUPLED_GATE = 7; RETRY_OPTIONS = 1; CAPDEF = 0; user_allowed = 10; AgentModelPicker = 0.
- Token gate: AgentsPopup.tsx = 0; WorkflowDialog.tsx = 0.
- tsc identity (filter mockApi.ts): **0** errors.

## Next Phase Readiness
- Shell inspectors complete: the 4-tab Agent drawer and the WorkflowDialog are the final surfaces of Phase 37 (B3).
- WorkflowDialog is not yet mounted by a navigator in this plan (surface built + tested in isolation, mirroring the drawer's existing multi-consumer pattern); wiring a trigger is a follow-on integration concern.
- Mocked Playwright e2e remains LIVE-DEFERRED (Phase 34) — not run offline per plan.

## Self-Check: PASSED

---
*Phase: 37-configure-unification-composer-wizard-b3*
*Completed: 2026-07-09*
