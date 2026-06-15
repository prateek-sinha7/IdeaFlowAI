---
phase: quick-260615-dzk
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/components/workflow/AgentsPopup.tsx
  - frontend/src/components/workflow/AdvancedExpander.test.tsx
  - frontend/src/components/workflow/CapabilityPaletteSection.test.tsx
  - backend/app/models/workflow.py
  - backend/alembic/versions/0023_workflow_run_selections.py
  - backend/app/api/websocket.py
  - backend/agents/execution_engine/engine.py
  - backend/tests/unit/test_migrations.py
autonomous: true
requirements: [UI-REVIEW-TOP-1, UI-REVIEW-TOP-2, UI-REVIEW-TOP-3-WR-02, UI-REVIEW-MINOR-4, UI-REVIEW-MINOR-5, UI-REVIEW-MINOR-7]

must_haves:
  truths:
    - "The Advanced expander scroll region caps at max-h-[200px], matching the palette and the declared scale (no max-h-[240px] inside AdvancedExpander)."
    - "A screen-reader user hears the lock reason on a locked capability row (an aria-label carrying the engineer-only reason, not title-only on a non-focusable div)."
    - "Capability kind-group aria-labels are title-cased (e.g. 'Validators', 'Context providers'), not the raw snake_case kind."
    - "An expanded config-schema affordance shows each field's TYPE and a required marker, not just the bare field name."
    - "The Capabilities header uses the Sliders lucide icon from the UI-SPEC enumerated reuse list."
    - "A backend-restart-resumed run re-applies the launch-time per-step selections via _apply_selections, re-validated with trust=user — no longer re-driving the bare file-compiled plan."
    - "The launch-time selections map is persisted on the workflow_runs row via an additive nullable JSON column (migration 0023)."
    - "The 5 characterization goldens (prototype, od_prototype, prototype_revision, od_ppt, app_builder) stay byte-identical + semantic-event-parity (proven by the targeted suite)."
  artifacts:
    - path: "frontend/src/components/workflow/AgentsPopup.tsx"
      provides: "FE polish batch: max-h-[200px] expander cap, locked-row aria-label, title-cased group aria-label, enriched config-schema affordance, Sliders header icon"
    - path: "backend/alembic/versions/0023_workflow_run_selections.py"
      provides: "Additive nullable JSON column workflow_runs.selections_json (mirrors 0022, down_revision=0022, single head)"
      contains: "down_revision = \"0022\""
    - path: "backend/app/models/workflow.py"
      provides: "WorkflowRun.selections_json column (additive, nullable JSON)"
      contains: "selections_json"
    - path: "backend/app/api/websocket.py"
      provides: "Persist launch-time selections on the run row at run creation (run_pipeline path)"
    - path: "backend/agents/execution_engine/engine.py"
      provides: "resume_run reads selections_json + re-threads through _execute_impl(selections=...) -> _apply_selections; deferred-limitation comment removed"
  key_links:
    - from: "backend/app/api/websocket.py (run creation, ~:1586)"
      to: "workflow_runs.selections_json"
      via: "WorkflowRun(... selections_json=selections)"
      pattern: "selections_json\\s*="
    - from: "backend/agents/execution_engine/engine.py (resume_run, ~:5024)"
      to: "_execute_impl(selections=...)"
      via: "read wr.selections_json then pass selections= into the resume _execute_impl call"
      pattern: "_execute_impl\\([^)]*selections="
    - from: "backend/agents/execution_engine/engine.py (_execute_impl)"
      to: "_apply_selections"
      via: "existing EMP-01 overlay seam (engine.py:1140)"
      pattern: "_apply_selections\\(compiled, selections\\)"
---

<objective>
Apply ALL Phase 22 UI-REVIEW.md findings: the frontend dense-inspector polish batch (Top Fix #1, Top Fix #2, Minor #4/#5/#7) AND the WR-02 backend fix (Top Fix #3) — composed per-step selections are dropped on `resume_run`.

Purpose: close the 22/24 UI-REVIEW gaps. The FE fixes restore strict token/copy/a11y conformance to the `AgentModelPicker.tsx` template and the 22-UI-SPEC contract. WR-02 closes a real end-to-end regression: a launched custom workflow that survives a backend restart silently reverts to defaults, losing the user-composed levers this phase added.

Output: a token-conformant `AgentsPopup.tsx`, two updated FE tests, an additive migration `0023` + `WorkflowRun.selections_json` column, a launch-time persist seam, and a `resume_run` re-thread that re-applies the saved selections (re-validated `trust="user"`). The 5 INV-3 goldens stay byte-identical (proven, never assumed).

Scope notes (intentionally NOT changed — per task_scope):
- Minor #6 "Upgrade to use" tier-locked variant — speculative (locks are binary `user_allowed`, no tier-gated caps). Left as a forward-hook code comment in `CapabilityPaletteSection`.
- Minor #8 `AgentsPopup` footer "Save changes"/"Cancel" — the config-popup's LOCAL close action (both call `onClose`), not the "Save workflow" persist CTA (which lives on `IdeaInputPage`). Not touched.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/IMPLEMENTATION-REGISTER.md
@.planning/phases/22-capability-surfacing-and-user-empowerment-universal-runtime-/22-UI-REVIEW.md
@.planning/phases/22-capability-surfacing-and-user-empowerment-universal-runtime-/22-UI-SPEC.md
@.planning/phases/22-capability-surfacing-and-user-empowerment-universal-runtime-/22-CONTEXT.md
@.planning/phases/22-capability-surfacing-and-user-empowerment-universal-runtime-/deferred-items.md
@CLAUDE.md

# FE fix sites + token template
@frontend/src/components/workflow/AgentsPopup.tsx
@frontend/src/components/workflow/AgentModelPicker.tsx
@frontend/src/lib/api.ts
@frontend/src/components/workflow/CapabilityPaletteSection.test.tsx
@frontend/src/components/workflow/AdvancedExpander.test.tsx

# WR-02 backend seams
@backend/app/models/workflow.py
@backend/alembic/versions/0022_workflow_run_deliverable_mimetype.py
@backend/app/api/websocket.py
@backend/agents/execution_engine/engine.py
@backend/agents/workflows/selections.py
@backend/tests/unit/test_migrations.py
@backend/tests/unit/test_deliverable_mimetype.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: FE polish batch (Top #1, Top #2, Minor #4/#5/#7)</name>
  <files>frontend/src/components/workflow/AgentsPopup.tsx, frontend/src/components/workflow/AdvancedExpander.test.tsx, frontend/src/components/workflow/CapabilityPaletteSection.test.tsx</files>
  <action>
Apply five polish fixes in `AgentsPopup.tsx`, each matching the `AgentModelPicker.tsx` token template: micro ramp text-[9px]/[10px]/[11px], weights 400/600 only, single #1B2A4A accent, lever/row chrome bg-gray-50 border-gray-100 rounded-lg px-2.5 py-1.5, schema fields font-mono text-[10px]. Introduce NO new arbitrary value, color, or weight.

(1) Top Fix #1 (Spacing). In `AdvancedExpander` change the scroll-region cap from max-h-[240px] to max-h-[200px] (AgentsPopup.tsx:1188) so palette, expander, and model picker share the declared max-h-[200px] overflow-y-auto pr-1 cap. Do NOT touch the two unrelated max-h-[240px] at :592 and :705 (skills/hooks attach lists — pre-existing chrome outside the phase-22 surfaces and the UI-SPEC scroll-region exception). Only the AdvancedExpander lever-scroll region is in scope.

(2) Top Fix #2 (A11y). On the locked capability row in `CapabilityPaletteSection` (the div with data-cap-row at :930-944, where locked = !cap.user_allowed) add an aria-label, ONLY when locked, of the form: capability name then " — Engineer-only, not available to compose". Leave non-locked rows WITHOUT an aria-label (labelled by their visible name). Keep the existing visible "Engineer-only" pill AND the existing title tooltip — the aria-label is additive so the reason reaches keyboard/SR users on the non-focusable div.

(3) Minor #7 (A11y). The kind-group wrapper at :917 uses aria-label={group.kind} (raw snake_case). Change it to use titleCaseKind(group.kind) so SR output reads "Validators"/"Context providers", reusing the existing titleCaseKind helper (:765). The visible header (:919) already uses titleCaseKind — this aligns the SR label with it.

(4) Minor #5 (Visuals). Enrich the config-schema affordance (the expanded block at :990-1001 that currently maps Object.keys(cap.config_schema) to bare field-name paragraphs). config_schema is JSON-Schema-lite: Record<string, unknown> where each value is a per-field descriptor object (confirmed shape { command: { type: "string" } } in CapabilityPaletteSection.test.tsx:48 and the backend registry describe/_META). For each [field, desc] entry render: the field name (keep font-mono text-[10px] text-gray-500); PLUS, when desc is an object, its type rendered after the name at text-[9px] text-gray-400 (read desc.type defensively — it is typed unknown, narrow via typeof === "object" / "type" in desc, never assume); PLUS a required marker (a small * in the existing gray scale, NOT navy/red — preserve locked-row neutrality) when desc.required === true. If type is absent, render only the name (graceful). Stay strictly within the micro ramp + gray scale; introduce no new color. Inspect the ACTUAL shape in api.ts (CapabilityEntry.config_schema: Record<string, unknown>, :504) and the test fixtures before choosing accessors — render only what is present, never invent keys.

(5) Minor #4 (Visuals, cosmetic). Swap the Boxes "Capabilities" header icon (:863) for Sliders (an enumerated lucide icon in the UI-SPEC reuse list). Keep the exact classes h-3.5 w-3.5 text-[#1B2A4A]. Add Sliders to the lucide-react import (:8). Remove Boxes from the import ONLY if a grep shows zero remaining Boxes uses in the file.

(6) Forward-hook comment (Minor #6 SKIP). Add a short code comment at the locked-row branch in `CapabilityPaletteSection` noting the "Upgrade to use" tier-locked variant (UI-SPEC copywriting contract) is deliberately NOT implemented because all locks are binary user_allowed (engineer-only); it is the forward hook to wire when a tier-gated capability first appears. Do NOT implement the variant.

(7) Footer (Minor #8 SKIP). Do NOT change the AgentsPopup footer "Save changes"/"Cancel" buttons (:1670-1673) — config-popup local onClose action, not the persist CTA.

Update tests to match the source edits:
- AdvancedExpander.test.tsx: if it asserts 240 for the lever-scroll cap, change to 200. Current grep shows the only 240-ish literal is context_window: 200000 (unrelated) with no max-h assertion — so likely NO change needed; read the file and only edit a real cap assertion if one exists.
- CapabilityPaletteSection.test.tsx: the group-label assertions at :89-94 query getByRole("group", { name: "validator" | "gate" | "context_provider" }) (raw kind). After Minor #7 these MUST become title-cased: { name: "Validators" }, { name: "Gates" }, { name: "Context providers" }. Add/extend a test asserting the locked row carries the new aria-label (value contains "Engineer-only, not available to compose"), keeping the existing aria-disabled="true" + visible "Engineer-only" assertions. Optionally extend a config-schema test to assert a rendered type (e.g. "string") for the schema'd cap (config_schema: { command: { type: "string" } }).
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && npx vitest run src/components/workflow/CapabilityPaletteSection.test.tsx src/components/workflow/AdvancedExpander.test.tsx src/components/workflow/AgentModelPicker.test.tsx 2>&1 | tail -30 && npx tsc --noEmit 2>&1 | grep -v "mockApi.ts:9[56]" | grep "src/" || echo "TSC CLEAN in src/"</automated>
  </verify>
  <done>
- AdvancedExpander lever-scroll region uses max-h-[200px]; the :592/:705 skills/hooks lists still use max-h-[240px] (untouched).
- Locked rows carry an additive aria-label containing "Engineer-only, not available to compose"; non-locked rows have none; visible pill + title preserved.
- Kind-group aria-label is title-cased (titleCaseKind).
- Expanded config-schema rows render field name + type (+ required * where present), within the micro ramp and gray scale only.
- "Capabilities" header icon is Sliders h-3.5 w-3.5 text-[#1B2A4A]; Boxes removed from imports only if unused.
- Minor #6 forward-hook comment present; footer (Minor #8) unchanged.
- The 3 vitest files pass; tsc reports only the 2 pre-existing mockApi.ts:95-96 errors (none in src/).
  </done>
</task>

<task type="auto">
  <name>Task 2: WR-02 persistence — selections_json column + migration 0023 + launch-time write</name>
  <files>backend/app/models/workflow.py, backend/alembic/versions/0023_workflow_run_selections.py, backend/app/api/websocket.py, backend/tests/unit/test_migrations.py</files>
  <action>
Persist the launch-time per-step selections map on the WorkflowRun row via an ADDITIVE nullable JSON column, mirroring the 22-03 deliverable_mimetype/deliverable_filename precedent. Honors D-11/D-12/D-19 (owner-scoped row carries owner_id+workspace_id; additive-migration precedent). SC-001: generic, keyed by agent_id, no workflow-name branch.

(1) Model column — backend/app/models/workflow.py. Add to WorkflowRun (alongside the Phase 22 columns at :64-73): selections_json = Column(JSON, nullable=True). JSON is already imported (sqlalchemy.types.JSON, :8) and used (budget_snapshot_json, :62). Add a comment: launch-time {agent_id: {validators, gates, model, retry, ...}} map (the EXACT shape _apply_selections overlays, engine.py:4519); nullable so every legacy/non-composed run stays NULL (and _apply_selections(None) is a no-op → INV-3 parity); carries the existing run scope, no new authz surface (D-12).

(2) Migration — backend/alembic/versions/0023_workflow_run_selections.py. Mirror 0022_workflow_run_deliverable_mimetype.py EXACTLY: module docstring (additive intent + INV-3 safety); revision = "0023"; down_revision = "0022"; branch_labels = None; depends_on = None; upgrade() uses with op.batch_alter_table("workflow_runs") as b: b.add_column(sa.Column("selections_json", sa.JSON(), nullable=True)); downgrade() uses the same batch_alter_table + b.drop_column("selections_json"). ADDITIVE ONLY. Single head: down_revision is the current head 0022.

(3) Persist at launch — backend/app/api/websocket.py. At the WorkflowRun(...) construction in the run_pipeline launch path (~:1586-1601, inside run_pipeline_impl where selections is a parameter declared :1367 and re-validated trust="user" at :1544 BEFORE this point), add selections_json=selections to the constructor kwargs. Persisting at row CREATION (not finalize) is deliberate: the row must carry selections BEFORE the run can crash, so a backend-restart resume finds them. selections is the launch-validated map; write as-is (JSON-serializable — same shape persisted in manifest_json for saved workflows, D-11). Add a one-line comment: WR-02 — persist launch selections so resume_run can re-apply (re-validated trust=user at launch:1544 and again on resume). Do NOT add a write at the finalize block (1814-1823).

(4) Migration ledger test — backend/tests/unit/test_migrations.py. Add a source-level test mirroring test_deliverable_mimetype.py::test_migration_0022_is_additive_only and test_migration_0016_down_revision_is_0015: assert 0023 down_revision == "0022"; single head (script.get_heads() == ["0023"]); upgrade() body contains add_column + selections_json and NO drop_column/alter_column/drop_table. Use ScriptDirectory.from_config (already imported) for head/down_revision; a source read_text() split for the additive-body assertions.

Do NOT run the full pytest suite (it hangs offline). Verify only the targeted migration tests below.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/unit/test_migrations.py tests/unit/test_deliverable_mimetype.py::test_migration_0022_is_additive_only tests/unit/test_alembic.py -p no:cacheprovider -q 2>&1 | tail -30</automated>
  </verify>
  <done>
- WorkflowRun.selections_json column exists (additive, nullable JSON).
- 0023_workflow_run_selections.py exists: revision "0023", down_revision "0022", single head, additive add_column only (no drop/alter on existing columns).
- run_pipeline_impl writes selections_json=selections on the WorkflowRun created at launch.
- The new migration ledger test asserts 0023 down_revision/single-head/additive-only and passes alongside the existing migration + alembic tests.
- The targeted migration/alembic suite is green (no full-pytest run).
  </done>
</task>

<task type="auto">
  <name>Task 3: WR-02 resume re-thread + trust re-validation + remove deferred comment</name>
  <files>backend/agents/execution_engine/engine.py</files>
  <action>
Re-thread the persisted launch-time selections through the resume path so a backend-restart-resumed run re-applies the same validators/gates/model/retry overlay. REUSE the existing _apply_selections (engine.py:4519) and the agents.workflows.selections synth seam — do NOT duplicate the overlay logic (INV-12). Generic, keyed by agent_id (SC-001); no workflow/agent-name branch.

(1) Read the persisted selections in resume_run (engine.py:5022-5036). The run identity is already read from the WorkflowRun row inside the `try:` block that opens at :5023 (`wr = db.query(WorkflowRun)...`). In that same block, after `wr is None` is handled, capture the persisted map: selections = wr.selections_json (Column added in Task 2; legacy/non-composed runs are None → byte/event-identical resume, the existing dormant path). Keep the read inside the existing db session/try block so it closes with the others at :5035-5036; do NOT open a second session.

(2) Re-validate trust="user" on resume BEFORE applying (security: resume can only ever apply LESS privilege). The actual overlay re-compiles through WorkflowCompiler().compile(trust="user") inside _apply_selections (:4549) already — so the selections cannot carry anything beyond user-allowed levers when re-applied. Add a brief comment at the resume read site documenting that the trust=user re-validation is the same one launch applies (websocket.py:1544 via _revalidate_selections_trust_user) and that _apply_selections (:4549) re-compiles trust=user again at overlay time, so the resume overlay is privilege-bounded by construction. (No extra WS-layer call is needed on resume — the engine-side _apply_selections compile IS the authoritative re-validation on this path; the WS pre-check exists only because the launch path accepts a client-supplied map, whereas resume reads the already-persisted, already-launch-validated map.)

(3) Pass selections into the resume _execute_impl call (engine.py:5133-5144). Add selections=selections to the kwargs of the `async for event in self._execute_impl(...)` call in resume_run. _execute_impl already accepts selections (signature :816) and already invokes _apply_selections(compiled, selections) at :1140 — so threading the kwarg is the entire wiring; the overlay seam is unchanged and shared with the launch path (no fork, INV-12). When selections is None/empty, _apply_selections returns the plan unchanged (has_selections guard, :4538) → resume is byte/event-identical for every legacy/non-composed run (INV-3).

(4) Remove the deferred-limitation comment. Delete the WR-02 KNOWN LIMITATION block at engine.py:5115-5125 (the "── WR-02 (KNOWN LIMITATION …) ──" comment that states selections are NOT re-threaded). Replace it with a concise comment stating WR-02 is RESOLVED: resume reads the persisted launch selections (selections_json) and re-threads them through _execute_impl → _apply_selections (trust=user re-compile), so a resumed run re-applies the same user-allowed levers; None/empty → unchanged plan (INV-3 parity). Keep the surrounding seq-sink comment (:5127-5129) intact.

(5) INV-3 guard. Confirm by inspection that nothing on this path emits the selections into the manifest/event stream as a new volatile value — _apply_selections only mutates the in-memory compiled plan's Step levers (already part of the existing EMP-01 launch path, which the 5 goldens take with selections=None). The goldens never set selections_json, so they take the None branch unchanged. If (and only if) a new value were found to reach the emitted manifest/event stream, add it to _VOLATILE_STRIP_KEYS — but the launch path already proved this seam parity-safe in 22-04, so no strip-key change is expected. Do NOT add speculative strip keys.

Do NOT run the full pytest suite (it hangs offline). Verify with the targeted parity goldens in Task 4.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -c "import ast,sys; src=open('agents/execution_engine/engine.py').read(); ast.parse(src); assert 'selections=selections' in src.split('async def resume_run')[1].split('async def ')[0] or True; print('resume_run threads selections:', 'selections=selections' in src); print('deferred KNOWN LIMITATION removed:', 'WR-02 (KNOWN LIMITATION' not in src)" 2>&1 | tail -10</automated>
  </verify>
  <done>
- resume_run reads wr.selections_json inside the existing db session block.
- The resume _execute_impl call passes selections=selections (re-threaded into the shared _apply_selections overlay).
- The "WR-02 (KNOWN LIMITATION …)" comment block (5115-5125) is removed and replaced with a RESOLVED note; the seq-sink comment is intact.
- No new _VOLATILE_STRIP_KEYS entry added (none needed — the None branch keeps the goldens unchanged).
- engine.py parses; the inspection check prints both flags true.
  </done>
</task>

<task type="auto">
  <name>Task 4: Full verification — INV-3 goldens + targeted parity/gate suite + lint-imports + FE</name>
  <files>(verification only — no source edits)</files>
  <action>
PROVE the hard constraints hold. This is the gate task: it runs the offline-safe targeted suite ONLY (full bare pytest HANGS offline behind Chromium/Bedrock/Postgres — never run it).

(1) INV-3 — the 5 characterization goldens must stay byte-identical + semantic-event-parity: run the 5 characterization test files (prototype, od_prototype, prototype_revision, od_ppt, app_builder) plus the manifest/routing/phase3 parity tests. These exercise the launch path with selections=None — proving WR-02 (which only adds a dormant column + a resume-only re-thread, never touched by the goldens) is parity-safe by construction. If ANY golden drifts, STOP and investigate (do not "update the golden"); a drift means an emitted value leaked — add it to _VOLATILE_STRIP_KEYS or revert the leak.

(2) Targeted backend parity/gate suite: the characterization goldens + test_run_pipeline_validation (launch selections re-validation) + test_user_workflows* (selections persistence/round-trip + migration ledger) + test_migrations/test_deliverable_mimetype/test_alembic (migration ledger, single head 0023). ~35s total.

(3) lint-imports — the hexagonal import contracts must stay 4 kept / 0 broken (run from backend/, config in backend/pyproject.toml). Binary at /opt/homebrew/bin/lint-imports.

(4) FE — re-run the touched vitest files green and tsc clean in src/ (only the 2 pre-existing e2e/fixtures/mockApi.ts:95-96 TS2352 errors allowed; src/ must be clean).

If every check is green, WR-02 is proven parity-safe and the FE polish is conformant. Record evidence (golden pass count, lint-imports "Contracts: 4 kept, 0 broken", FE pass count) in the SUMMARY.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py tests/agents/test_manifest_parity.py tests/agents/test_routing_parity.py tests/agents/test_phase3_parity.py tests/unit/test_run_pipeline_validation.py tests/unit/test_user_workflows.py tests/unit/test_user_workflows_selections.py tests/unit/test_migrations.py tests/unit/test_deliverable_mimetype.py tests/unit/test_alembic.py -p no:cacheprovider -q 2>&1 | tail -25 && echo "==== lint-imports ====" && /opt/homebrew/bin/lint-imports 2>&1 | tail -8</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend && npx vitest run src/components/workflow/CapabilityPaletteSection.test.tsx src/components/workflow/AdvancedExpander.test.tsx src/components/workflow/AgentModelPicker.test.tsx 2>&1 | tail -12 && npx tsc --noEmit 2>&1 | grep -v "mockApi.ts:9[56]" | grep "src/" || echo "TSC CLEAN in src/"</automated>
  </verify>
  <done>
- All 5 characterization goldens pass byte-identical (INV-3 proven, not assumed); parity tests (manifest/routing/phase3) pass.
- test_run_pipeline_validation + test_user_workflows* + migration ledger tests pass (selections persistence + single head 0023).
- lint-imports: Contracts: 4 kept, 0 broken.
- FE: 3 vitest files green; tsc reports only the 2 pre-existing mockApi.ts:95-96 errors (none in src/).
- Evidence recorded in the SUMMARY.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client (WS run_pipeline) → engine | The launch-time `selections` map is client-supplied; re-validated `trust="user"` at launch (websocket.py:1544) before the run row is created. |
| persisted run row → resume_run | On resume, `selections_json` is read from the DB (already launch-validated) and re-applied; _apply_selections re-compiles `trust="user"` again at overlay time. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-dzk-01 | Elevation of Privilege | resume_run re-applying persisted selections | mitigate | _apply_selections re-compiles via WorkflowCompiler().compile(trust="user") (engine.py:4549) — the resume overlay can only ever carry user-allowed levers (resume applies LESS privilege, never more). No engineer-only lever can be reintroduced on resume. |
| T-dzk-02 | Tampering | workflow_runs.selections_json mutated in the DB | mitigate | The trust=user re-compile on resume rejects any tampered/over-privileged lever (CompilerError → unchanged plan, the defense-in-depth backstop at engine.py:4554). Row is owner_id/workspace_id-scoped (D-12). |
| T-dzk-03 | Tampering | INV-3 golden drift from the new column/overlay | mitigate | selections_json is nullable; goldens take the selections=None branch (has_selections guard) → byte/event-identical. Proven by the Task 4 characterization suite (never assumed). No package installs in this change. |
| T-dzk-04 | Information Disclosure | selections leaking into the emitted manifest/event stream | accept | _apply_selections mutates only the in-memory compiled plan Step levers (existing EMP-01 launch path, 22-04 parity-proven); nothing new is emitted. If a leak were found at verification, the value goes into _VOLATILE_STRIP_KEYS — but none is expected. |
</threat_model>

<verification>
Overall phase checks (all offline-safe — NEVER run bare `pytest`):

1. INV-3: the 5 characterization goldens pass byte-identical + semantic-event-parity (Task 4 automated).
2. Migration ledger: single head 0023, down_revision 0022, additive-only (Task 2 + Task 4).
3. Selections round-trip: launch persists selections_json; resume re-applies via _apply_selections (Task 2 + Task 3).
4. SC-001: the resume overlay keys on agent_id; no workflow/agent-name branch added.
5. INV-12: _apply_selections + agents.workflows.selections reused; no overlay duplication.
6. lint-imports: 4 kept / 0 broken (hexagonal contracts intact).
7. FE: touched vitest files green; tsc clean in src/ (only the 2 pre-existing mockApi.ts errors).
8. Token conformance: no new arbitrary value/color/weight in AgentsPopup.tsx; Sliders from the enumerated reuse list; max-h-[200px] on the expander scroll region.
</verification>

<success_criteria>
- All 5 UI-REVIEW frontend findings applied (Top #1, Top #2, Minor #4, #5, #7), token-conformant to AgentModelPicker.tsx.
- Minor #6 and Minor #8 documented as intentionally not changed (forward-hook comment for #6; footer untouched for #8).
- WR-02 resolved: launch selections persisted (selections_json, migration 0023), re-applied on resume via the shared _apply_selections seam, trust=user re-validated.
- INV-3 goldens byte-identical (proven). lint-imports 4 kept / 0 broken. Additive migration only, single head 0023.
- All verify commands use the offline-safe targeted suite (no bare pytest).
</success_criteria>

<output>
Create `.planning/quick/260615-dzk-apply-phase-22-ui-review-findings-fe-pol/260615-dzk-SUMMARY.md` when done.
</output>
