---
phase: quick-260718-puj
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/agents/execution_engine/resolver.py
  - backend/app/api/composition_order.py
  - backend/app/api/user_workflows.py
  - backend/app/api/run_commands.py
  - backend/tests/unit/test_workflow_resolver.py
  - backend/tests/unit/test_user_workflows.py
  - backend/tests/unit/test_user_workflows_selections.py
  - backend/tests/unit/test_rest_run_launch.py
  - frontend/src/components/workflow/composer/ComposerPage.tsx
  - frontend/src/components/workflow/composer/ComposerPage.test.tsx
autonomous: true
requirements: [CWF-001-D1]
must_haves:
  truths:
    - "Saving custom agents [swot-analyst, market-research-agent] (consumer-first) persists producer-first [market-research-agent, swot-analyst] with 201 — no unsatisfiable run at launch."
    - "Saving a genuinely-unsatisfiable composition (a consumed non-exempt type no selected agent produces, or a real produces/consumes cycle) returns 422 with a message naming the missing edge."
    - "Launching a custom agent_ids composition pre-sorts producer-first BEFORE the WorkflowRun is minted; a genuinely-unsatisfiable custom launch is rejected pre-mint (no run row created)."
    - "The composer visibly reorders its rows to the persisted producer-first order on save, and surfaces an unsatisfiable-composition rejection inline (blocks Save/Run pre-launch)."
    - "The kernel resolver validate() (resolver.py:119 idx<consumer_idx filter, :138 max() tie-break) is byte-unchanged: test_multi_producer_nearest_upstream_wins and all 5 characterization goldens stay green."
  artifacts:
    - path: "backend/agents/execution_engine/resolver.py"
      provides: "New additive order-independent WorkflowResolver.presort() reusing _detect_cycles/_topological_sort"
      contains: "def presort"
    - path: "backend/app/api/composition_order.py"
      provides: "App-layer entry point: presort_specs/presort_agent_ids + UnsatisfiableComposition"
      contains: "class UnsatisfiableComposition"
    - path: "backend/app/api/user_workflows.py"
      provides: "create_user_workflow satisfiability guard + producer-first persisted order"
    - path: "backend/app/api/run_commands.py"
      provides: "launch_run pre-mint pre-sort/reject for custom agent_ids"
    - path: "frontend/src/components/workflow/composer/ComposerPage.tsx"
      provides: "handleSave surfaces the producer-first pre-sort + inline unsatisfiable rejection"
  key_links:
    - from: "backend/app/api/user_workflows.py"
      to: "backend/app/api/composition_order.py"
      via: "presort_agent_ids(body.agent_ids) before persist"
      pattern: "presort_agent_ids"
    - from: "backend/app/api/run_commands.py"
      to: "backend/app/api/composition_order.py"
      via: "presort_specs(agents) inside `if agent_ids:` before mint"
      pattern: "presort_specs"
    - from: "backend/app/api/composition_order.py"
      to: "backend/agents/execution_engine/resolver.py"
      via: "WorkflowResolver().presort(specs)"
      pattern: "\\.presort\\("
    - from: "frontend/src/components/workflow/composer/ComposerPage.tsx"
      to: "createUserWorkflow response.agent_ids"
      via: "setPipelineAgents reordered to persisted order"
      pattern: "agent_ids"
---

<objective>
Fix CWF-001 D1: the composer/API let a user order custom-workflow agents consumer-before-producer; the row saves (201) and launches (200) with no warning, then the run dies at runtime with "Workflow DAG is unsatisfiable". Add an ORDER-INDEPENDENT produces/consumes satisfiability check + a producer-first topological pre-sort at the app-layer SAVE and LAUNCH boundaries, and surface it in the composer.

This is candidate (b) from `.planning/CWF-001-002-GROUNDED-CONTEXT.md` (FIX D1 section). Candidate (a) — making the kernel `validate()` order-independent — is REJECTED because it edits kernel code whose topo order + multi-producer tie-break are depended upon (register line 484; resolver.py:14; app_builder characterization golden = INV-3 risk). We only ever reorder USER compositions; file-backed built-in manifests are already producer-first and stay untouched.

Purpose: no custom composition can be saved or launched in an order that can never satisfy its produces/consumes contracts; the user sees the reorder (or a clear rejection) at compose-time instead of a mysterious runtime death.
Output: a new additive `WorkflowResolver.presort()`, a thin app-layer `composition_order.py` entry point reusing it, wiring at `create_user_workflow` + `launch_run`, and composer surfacing — plus RED→GREEN tests.

SCOPE FENCES (do NOT violate — grounded context §"FIX D1" scope fences):
- Do NOT edit `resolver.py:119` (`idx < consumer_idx`), `resolver.py:138` (`max(upstream, …)` tie-break), or `WorkflowResolver.validate()`.
- Do NOT touch D2 (already fixed in `_drive_launch_to_queue`) or CWF-002.
- Do NOT add produces/consumes logic to the compiler (INV-5).
- Do NOT re-sort file-backed built-in manifests — the presort runs ONLY on user-supplied `agent_ids` (custom compositions).
- Do NOT change `engine.py:1589-1598`.
- Q3: no new table, no migration. INV-1/SC-001: key on GENERIC produces/consumes only — NO workflow-name / pipeline_type literal in any guarded component.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/CWF-001-002-GROUNDED-CONTEXT.md
@backend/CLAUDE.md
@backend/agents/execution_engine/resolver.py
@backend/app/api/user_workflows.py
@backend/app/api/run_commands.py
@frontend/src/components/workflow/composer/ComposerPage.tsx

# Grounded facts already established (do not re-derive):
# - swot-analyst: consumes=["market-research-agent"], produces=["swot-analyst"] (artifact type == agent id)
# - market-research-agent: consumes=[], produces=["market-research-agent"]
# - report-generator: consumes=["documentation-agent"], produces=["report-generator"]
#   => the existing test fixture [market-research-agent, report-generator] is GENUINELY UNSATISFIABLE
#      (documentation-agent is not produced by any selected agent) and MUST change (Task 2).
# - launch_run resolves custom specs only in the `if agent_ids:` branch (run_commands.py:1141-1151);
#   the `else` branch (get_pipeline_agents) is a built-in manifest and MUST NOT be pre-sorted.
# - import-linter has NO contract forbidding app.api -> agents.execution_engine (run_commands.py
#   already imports agents.execution_engine.engine). user_workflows.py's "MUST NOT import
#   agents.execution_engine" is a module docstring convention — honored by having it import the
#   app-layer composition_order helper, never the resolver directly.
# - createUserWorkflow returns UserWorkflowSummary { agent_ids: string[] } (frontend api.ts).
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add order-independent WorkflowResolver.presort() + app-layer composition_order entry point</name>
  <files>backend/agents/execution_engine/resolver.py, backend/app/api/composition_order.py, backend/tests/unit/test_workflow_resolver.py</files>
  <behavior>
    - presort([swot(consumes market-research-agent), market-research-agent(produces market-research-agent)]) returns [market-research-agent, swot]; feeding that result back into resolver.validate() yields satisfiable=True (proves the pre-sorted order is satisfiable under the UNTOUCHED kernel validate()).
    - presort([consumer(consumes "nope")]) raises ValueError matching "no agent in the workflow produces it".
    - presort of a real cycle [a produces x consumes y, b produces y consumes x] raises ValueError (cycle).
    - presort skips _EXEMPT_TYPES (planning_context, constitution) — an agent consuming only exempt types is a root, never unsatisfiable.
    - presort excludes self as a producer (an agent consuming a type only it produces is unsatisfiable — cannot be its own upstream).
    - EXISTING test_multi_producer_nearest_upstream_wins stays green (validate() untouched).
    - composition_order.presort_specs(specs) returns reordered specs or raises UnsatisfiableComposition(message); presort_agent_ids(ids) loads specs via agents.loader.load_agent_spec then delegates to presort_specs, returning sorted ids.
  </behavior>
  <action>
    In `resolver.py`, ADD a new PUBLIC method `presort(self, agents: list) -> list` to `WorkflowResolver` (do NOT touch `validate()`, `:119`, or `:138`). It is ORDER-INDEPENDENT: build `produces_map` as artifact_type -> set of producing agent ids over ALL agents (no index filter). For each consumer, for each consumed type: skip if in `_EXEMPT_TYPES`; compute the producer set EXCLUDING the consumer's own id; if empty, append an error string of the exact form "Agent '{consumer.id}' consumes '{type}' but no agent in the workflow produces it." (note the order-independent wording "no agent in the workflow" — NOT "no upstream agent"); otherwise add every producer id to `dependencies[consumer.id]`. If any errors, raise `ValueError("Workflow DAG is unsatisfiable: " + "; ".join(errors))`. Then reuse `self._detect_cycles(agents, dependencies)`; if it returns cycle errors, raise `ValueError("Workflow DAG is unsatisfiable: " + "; ".join(cycle_errors))`. Otherwise return `self._topological_sort(agents, dependencies)`. This REUSES the two existing graph helpers (INV-12) — do not re-implement DAG logic. Determinism note: `_topological_sort` seeds and scans in `agents` list order, so the output order is deterministic from the input order (the producer sets are used only for membership). Empty `agents` raises ValueError with the same "Workflow DAG is unsatisfiable: Workflow must contain at least 1 agent." prefix.

    Create NEW app-layer module `backend/app/api/composition_order.py`. Define `class UnsatisfiableComposition(ValueError)` (a distinct type so call sites catch only this). Define `def presort_specs(specs: list) -> list` that constructs `WorkflowResolver()` (imported from `agents.execution_engine.resolver` — the legal app -> agents direction; run_commands.py already imports agents.execution_engine.engine, and no import-linter contract forbids this), calls `.presort(specs)`, and on `ValueError` re-raises as `UnsatisfiableComposition(str(exc))`. Define `def presort_agent_ids(agent_ids: list[str]) -> list[str]` that lazy-imports `from agents.loader import load_agent_spec`, loads `specs = [load_agent_spec(a) for a in agent_ids]`, then returns `[s.id for s in presort_specs(specs)]`. Keep the module docstring generic (produces/consumes only) — NO workflow-name / pipeline_type literal (SC-001). This module is the single "additive entry point on the resolver/app layer" the grounded context calls for.

    In `test_workflow_resolver.py`, ADD (reusing the existing `_AgentSpec` dataclass stub and `resolver` fixture): test_presort_reorders_consumer_first (asserts the reordered ids AND that `resolver.validate(reordered).satisfiable is True`); test_presort_rejects_missing_producer (pytest.raises ValueError, match="no agent in the workflow produces it"); test_presort_rejects_cycle (pytest.raises ValueError); test_presort_exempt_types_are_roots (an agent consuming only planning_context/constitution presorts without error). Do NOT modify or delete any existing test — test_multi_producer_nearest_upstream_wins must remain untouched and green.
  </action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/unit/test_workflow_resolver.py -q</automated>
  </verify>
  <done>presort() exists on WorkflowResolver and reuses _detect_cycles/_topological_sort; validate()/:119/:138 are byte-unchanged; composition_order.py exports UnsatisfiableComposition + presort_specs + presort_agent_ids; all new presort tests pass and test_multi_producer_nearest_upstream_wins still passes.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire the guard at create_user_workflow (persist sorted / 422) + launch_run (pre-mint pre-sort/reject); fix at-risk fixtures</name>
  <files>backend/app/api/user_workflows.py, backend/app/api/run_commands.py, backend/tests/unit/test_user_workflows.py, backend/tests/unit/test_user_workflows_selections.py, backend/tests/unit/test_rest_run_launch.py</files>
  <behavior>
    - POST /api/user-workflows with agent_ids ["swot-analyst","market-research-agent"] (consumer-first) returns 201 and the persisted/returned agent_ids are ["market-research-agent","swot-analyst"] (producer-first).
    - POST /api/user-workflows with a genuinely-unsatisfiable set (e.g. ["swot-analyst"] alone — consumes market-research-agent, absent) returns 422 whose detail names the missing edge.
    - Launching (POST /api/runs) with a custom agent_ids that is genuinely-unsatisfiable is rejected PRE-MINT: 422/reject code "workflow_unsatisfiable" and no WorkflowRun row is created.
    - Existing test_user_workflows*.py and test_rest_run_launch.py behaviors stay green after the fixture change.
  </behavior>
  <action>
    In `user_workflows.py` `create_user_workflow`, AFTER the existing predicate block (the `_compile_selections_trust_user(...)` call, ~:296-298) and BEFORE the name-uniqueness query (~:301), import `from app.api.composition_order import presort_agent_ids, UnsatisfiableComposition` (do NOT import agents.execution_engine here — keep the module docstring convention true by going through the app-layer helper). Compute `sorted_ids = presort_agent_ids(body.agent_ids)` wrapped in try/except `UnsatisfiableComposition as exc` -> `raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))`. Then persist the SORTED ids: change the `agents=json.dumps(body.agent_ids)` at :322 to `agents=json.dumps(sorted_ids)`. Leave `model_overrides`, `selections`, and every other field as-is (model_overrides/selections are keyed by agent_id, so reorder is safe). The PATCH sibling `update_user_workflow` does NOT accept `agent_ids` (its request model has only name/description/model_overrides/selections), so there is nothing to reorder there — add a one-line comment noting the guard lives at create + launch and PATCH cannot change agent order.

    In `run_commands.py` `launch_run`, INSIDE the `if agent_ids:` branch only (after `agents = [load_agent_spec(aid) for aid in agent_ids]` at :1151), import `from app.api.composition_order import presort_specs, UnsatisfiableComposition` and reorder: `try: agents = presort_specs(agents) except UnsatisfiableComposition as exc: raise _reject("workflow_unsatisfiable", str(exc))`. This runs BEFORE the mint at :1234 (`status="running"`), so it is defense-in-depth AND repairs legacy mis-ordered saved rows + fresh Run-once. Do NOT add the presort to the `else` branch (`get_pipeline_agents` — file-backed built-in manifests; scope fence). Do NOT modify the D2 event-ladder logic already present in `_drive_launch_to_queue`.

    Fix the at-risk fixtures (RED->GREEN — these fixtures currently encode an unrunnable composition that the new guard correctly exposes): in BOTH `test_user_workflows.py` and `test_user_workflows_selections.py`, change the module constant `_AGENT_B = "report-generator"` to `_AGENT_B = "swot-analyst"`. Reason: swot-analyst consumes market-research-agent (= _AGENT_A's produced type), so `[_AGENT_A, _AGENT_B]` is a valid producer-first chain that presorts to itself (all existing `== [_AGENT_A, _AGENT_B]` assertions stay true), whereas report-generator consumes documentation-agent (never produced) and would now 422. Do not change any other line that references the `_AGENT_B` symbol.

    ADD endpoint tests:
    - In `test_user_workflows.py`: test_post_reorders_consumer_first_to_producer_first — POST a body with agent_ids=["swot-analyst","market-research-agent"] and model_overrides={} (market-research-agent produces the type swot consumes); assert 201 and `r.json()["agent_ids"] == ["market-research-agent","swot-analyst"]`. test_post_rejects_unsatisfiable_composition — POST agent_ids=["swot-analyst"], model_overrides={}; assert 422 and the detail names the missing edge (contains "market-research-agent" and "produces it"). Build these bodies explicitly (do not rely on `_valid_body`'s model_overrides, which targets _AGENT_A).
    - In `test_rest_run_launch.py`: test_unsatisfiable_custom_composition_rejected_pre_mint — using the existing `env`/`_post_launch` helpers, `_post_launch(env, message="x", pipeline_type="user_stories", agent_ids=["swot-analyst"])` (both agents are allow-listed for any base via the custom pool; user_stories is runnable by the default seeded tier, avoiding the enterprise entitlement gate); assert status 422, `resp.json()["detail"]["code"] == "workflow_unsatisfiable"`, and `_run_count(env)` is unchanged (no run minted). Mirror the shape of the existing `test_unsupported_pipeline_type_rejected_pre_mint`.
  </action>
  <verify>
    <automated>cd backend && python3.11 -m pytest tests/unit/test_user_workflows.py tests/unit/test_user_workflows_selections.py tests/unit/test_rest_run_launch.py -q</automated>
  </verify>
  <done>create_user_workflow persists producer-first ids and 422s a genuinely-unsatisfiable set; launch_run rejects an unsatisfiable custom composition pre-mint (no run row) and only pre-sorts the `if agent_ids:` branch; _AGENT_B fixture updated in both files; all three suites green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Surface the pre-sort + unsatisfiable rejection in the composer; regression + goldens</name>
  <files>frontend/src/components/workflow/composer/ComposerPage.tsx, frontend/src/components/workflow/composer/ComposerPage.test.tsx</files>
  <behavior>
    - On a successful save whose response carries agent_ids, the composer reorders its visible agent rows to the persisted producer-first order (surfaces the backend pre-sort).
    - On a save that fails with an unsatisfiable-composition rejection, the composer renders the backend's clear message inline (the existing saveError region) and does NOT reorder — the save is blocked and the user sees why pre-launch.
    - The existing save test (mock resolves { id: "wf-1" } with no agent_ids) still passes — the reorder is guarded on a present, non-empty agent_ids.
  </behavior>
  <action>
    In `ComposerPage.tsx` `handleSave`, capture the resolved response from `createUserWorkflow(...)` (typed `UserWorkflowSummary`). After a successful save, if `resp?.agent_ids?.length`, reorder `pipelineAgents` to the persisted order: setPipelineAgents(prev => resp.agent_ids.map(id => prev.find(a => a.id === id)).filter(Boolean) as AgentDef[]). Guard for the empty/absent case so a response without agent_ids leaves the rows untouched (the existing test mock returns only { id }). The failure path is already correct: the `catch` sets `saveError` from `(e as Error).message`, and `createUserWorkflow` throws `ApiError` whose message is the backend 422 `detail` (the clear "consumes X but no agent produces it") — so the unsatisfiable rejection already surfaces via the existing saveError render (lines ~487-491). Do NOT compute produces/consumes on the client (the FE AgentDef/AgentLibraryData carry no produces/consumes — that data is server-only); the backend is the authoritative source and the composer surfaces its result. Selections are keyed by agent_id and are unaffected by the row reorder.

    In `ComposerPage.test.tsx`, ADD two tests (reuse the existing mockCreateUserWorkflow + renderComposer harness): (1) "surfaces the producer-first pre-sort — reorders rows on save": render with initialAgentIds=["epic-architect","domain-analyst"], mock createUserWorkflow to resolve { id:"wf-1", agent_ids:["domain-analyst","epic-architect"] }, drive Save-to-catalogue -> NameWorkflowModal Save, then assert the agent-row order flips (domain-analyst now precedes epic-architect via getAllByTestId(/^agent-row-/)). (2) "surfaces an unsatisfiable-composition rejection inline": mock createUserWorkflow to reject with new Error("Agent 'swot-analyst' consumes 'market-research-agent' but no agent in the workflow produces it."), drive Save, then assert that message text renders. Do NOT modify existing tests.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/components/workflow/composer/ComposerPage.test.tsx</automated>
  </verify>
  <done>handleSave reorders rows to the persisted producer-first order on save and surfaces the unsatisfiable rejection inline; both new tests pass and all pre-existing ComposerPage tests remain green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| composer/client → POST /api/user-workflows | untrusted composition (agent order) crosses into persistence |
| client → POST /api/runs (launch) | untrusted / replayed saved composition crosses into run mint + engine |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-CWF1-01 | Tampering | create_user_workflow / launch_run | mitigate | order-independent produces/consumes satisfiability check + producer-first pre-sort at BOTH save and launch (pre-mint); a consumed non-exempt type with no producer, or a real cycle, is rejected with a clear message naming the missing edge |
| T-CWF1-02 | Denial of Service | resolver.presort graph build | mitigate | bounded agent count (FE MAX_OPTIONAL=8 + server allow-list); O(V+E) Kahn topo + DFS cycle detection reused from the resolver; cycles rejected fast, never executed |
| T-CWF1-03 | Information disclosure / status integrity | run status lifecycle | accept | mislabeled-completed run is D2, already fixed in _drive_launch_to_queue — out of scope for D1 |
| T-CWF1-SC | Tampering | package installs | accept | no npm/pip/cargo installs introduced by this change — no new dependency surface |
</threat_model>

<verification>
Offline verification (python3.11, no venv; the orchestrator owns live-Bedrock proofs):

- Resolver + goldens (kernel untouched):
  `cd backend && python3.11 -m pytest tests/unit/test_workflow_resolver.py tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_app_builder.py -q`
- App-layer wiring:
  `cd backend && python3.11 -m pytest tests/unit/test_user_workflows.py tests/unit/test_user_workflows_selections.py tests/unit/test_rest_run_launch.py -q`
- Import boundary: `/opt/homebrew/bin/lint-imports` (from backend/) — must exit 0 (composition_order.py -> agents.execution_engine.resolver is the legal app->agents direction; no engine->app.api regression).
- Frontend unit: `cd frontend && npx vitest run src/components/workflow/composer/ComposerPage.test.tsx`
- Frontend e2e (mocked, must stay green): `cd frontend && npm run e2e -- e2e/tests/composer-run.spec.ts e2e/tests/ts-d.composer.spec.ts` — if a spec asserts a specific post-save row order that the mocked response would now reorder, reconcile the spec (selector/expectation drift), never delete a behavior assertion.

Do NOT run live Bedrock or the full backend suite (it hangs offline on Chromium/Bedrock/Postgres gates).
</verification>

<success_criteria>
- Consumer-first custom save persists producer-first order (201); genuinely-unsatisfiable save returns 422 naming the missing edge.
- Custom launch pre-sorts producer-first before mint; genuinely-unsatisfiable custom launch is rejected pre-mint with no WorkflowRun row.
- Composer reorders rows to the persisted order on save and surfaces the unsatisfiable rejection inline.
- resolver.validate()/:119/:138 byte-unchanged; test_multi_producer_nearest_upstream_wins + all 5 characterization goldens green.
- lint-imports exit 0; no workflow-name / pipeline_type literal in any guarded component (SC-001); no migration/new table (Q3); guard not in the compiler (INV-5); resolver graph helpers reused, no dual DAG impl (INV-12).
- Branch feat/ui-2; no commit trailer; never push.
</success_criteria>

<output>
Create `.planning/quick/260718-puj-fix-cwf-001-d1-compose-time-produces-con/260718-puj-SUMMARY.md` when done.
</output>
