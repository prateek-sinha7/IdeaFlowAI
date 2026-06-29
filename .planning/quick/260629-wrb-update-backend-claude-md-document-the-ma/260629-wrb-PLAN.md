---
phase: quick-260629-wrb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified: [backend/CLAUDE.md]
autonomous: true
requirements: [DOC-MANIFEST-LAYER, DOC-PIPELINE-MANIFEST-STEP, DOC-ROUTING-PRODUCES-CONSUMES, DOC-FACTORY-FN-RENAME]
must_haves:
  truths:
    - "The Architecture Overview documents the manifest/compile_for_run/CompiledWorkflow layer (not only the registry) as the source of HOW agents run."
    - "The Data Flow (pipeline run_pipeline) diagram shows compile_for_run resolving + compiling the manifest at run entry, and the engine sourcing sequence/deliverable/clarify/planner from the compiled plan."
    - "The Adding a Pipeline section includes a REQUIRED step to create agents/workflows/<id>/workflow.yaml, noting compile_for_run raises FileNotFoundError without it and the step agent-ids must match PIPELINE_AGENTS membership/order."
    - "The AGENT.md schema marks context_from as legacy/vestigial and documents produces/consumes as the live inter-agent routing mechanism."
    - "The doc references _resolve_runner_tools (current factory function name) and no longer references _build_runner_tools."
    - "All unrelated sections (free-chat, tool sets behavior, guardrails, skills/hooks, testing, commit conventions) are unchanged."
  artifacts:
    - path: "backend/CLAUDE.md"
      provides: "Updated backend architecture guide reflecting the manifest-driven runtime"
      contains: "compile_for_run"
  key_links:
    - from: "backend/CLAUDE.md"
      to: "backend/agents/execution_engine/engine.py"
      via: "documents compile_for_run + the registry-membership assertion"
      pattern: "compile_for_run"
    - from: "backend/CLAUDE.md"
      to: "backend/agents/execution_engine/engine.py (_filter_consumed_outputs)"
      via: "documents produces/consumes as the routing mechanism"
      pattern: "produces.*consumes|consumes.*produces"
    - from: "backend/CLAUDE.md"
      to: "backend/agents/factory.py (_resolve_runner_tools)"
      via: "documents the current tool-resolution function name"
      pattern: "_resolve_runner_tools"
---

<objective>
Surgically update `backend/CLAUDE.md` (the backend architecture guide) so it documents the
LIVE manifest-driven runtime on this branch instead of the PRE-manifest (registry + `order`-only)
runtime it currently describes. Four verified-stale areas only — do NOT rewrite unrelated
sections; preserve the doc's existing voice, structure, and ordering.

Purpose: The guide is the principal-engineer reference for the backend. Its current
"the engine decides which agent runs next (reading the pipeline registry)" mental model is half
the story and actively misleading: the engine compiles a typed `CompiledWorkflow` from a
declarative `workflow.yaml` manifest at run entry, sources per-step capabilities/deliverable/
clarify/planner from it, and routes upstream context by the typed `produces`/`consumes` graph —
not by `context_from`. An engineer following the current "Adding a Pipeline" steps would ship a
pipeline that crashes at run entry with `FileNotFoundError` (no manifest).

Output: An edited `backend/CLAUDE.md` with the four fixes applied (Fix 1–4 below), every other
section byte-unchanged.

All four claims are VERIFIED against the code on this branch (cited per task). The executor MUST
re-confirm each symbol still exists before editing — line numbers may drift; symbol names are the
contract.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
# The file being edited (read in full first — note its section structure):
@backend/CLAUDE.md

# Source of truth for the claims (verify symbols before editing; do NOT edit these):
@backend/agents/execution_engine/engine.py
@backend/agents/registry.py
@backend/agents/loader.py
@backend/agents/factory.py
</context>

<verified_facts>
The planner pre-verified these against the current branch. Re-confirm with grep before editing
(line numbers are guides, not gospel — match on symbol names):

- `compile_for_run(pipeline_type) -> CompiledWorkflow` is DEFINED at `engine.py:423` and CALLED
  at run entry `engine.py:1145`. Its docstring states it raises `FileNotFoundError` when no
  manifest exists for the resolved id (currently `engine.py:432-438`). It calls
  `resolve_alias(...)` then `load_manifest(manifest_id, _WORKFLOWS_DIR)` then
  `_WORKFLOW_COMPILER.compile(manifest, _CAPABILITY_REGISTRY)`.
- The engine ASSERTS the compiled plan's step agent-ids equal the registry MEMBERSHIP and raises
  `RuntimeError` on drift (`engine.py:1393-1406`, comparing `[s.agent_id for s in compiled.steps]`
  against `get_pipeline_agents(compiled.id)` / `PIPELINE_AGENTS[compiled.id]`).
- `registry.py`: `PIPELINE_AGENTS` (line 29) + `get_pipeline_agents()` (line 223) provide agent
  MEMBERSHIP/order (still real, still the engine's canonical agent list).
- `loader.py`: `SUPPORTED_PIPELINE_TYPES` is the allow-list frozenset (line 29). `context_from`
  IS still parsed/stored by the loader (`AgentSpec.context_from`, lines 90/309/388) — it is NOT
  removed; it is just no longer what drives engine routing.
- `_filter_consumed_outputs` (`engine.py:5395-5426`) is the live inter-agent routing: an upstream
  agent's output reaches this agent IFF `set(upstream.produces) & set(this.consumes)` is non-empty;
  the CONTENT is read from the typed `ectx.artifacts` graph via `_latest_typed_content(ectx,
  upstream.id)`. The old prior-output mirror fallback was deleted in 05-07.
- The factory tool-resolution function is now `_resolve_runner_tools(spec, ctx)` (`factory.py:570`,
  called at `factory.py:186`). The name `_build_runner_tools` NO LONGER EXISTS in `factory.py` —
  the doc's references to it are stale.
</verified_facts>

<tasks>

<task type="auto">
  <name>Task 1: Document the manifest layer (Fix 1 + Fix 2)</name>
  <files>backend/CLAUDE.md</files>
  <action>
First re-verify with grep: `grep -n "def compile_for_run\|compile_for_run(pipeline_type)" backend/agents/execution_engine/engine.py` (def ~423, call ~1145); `grep -n "raise RuntimeError" backend/agents/execution_engine/engine.py` near the membership assertion (~1393-1406); `grep -n "PIPELINE_AGENTS\|def get_pipeline_agents" backend/agents/registry.py`; `grep -rn "workflow.yaml\|def load_manifest" backend/agents/workflows/`. Confirm an `agents/workflows/<id>/workflow.yaml` actually exists (e.g. `ls backend/agents/workflows/`).

Fix 1 — Architecture Overview + Data Flow diagram (CLAUDE.md "## Architecture Overview" prose ~lines 31-37, and the "### Data Flow (pipeline `run_pipeline`)" code block + the narration paragraph after it ~lines 94-134):
- In the Architecture Overview prose, correct the half-true claim "The engine decides which agent runs next (reading the pipeline registry)". State the full mental model: the engine compiles a typed, validated `CompiledWorkflow` from a declarative manifest (`agents/workflows/<id>/workflow.yaml`) at run entry via `compile_for_run(pipeline_type)`, and sources the agent SEQUENCE, deliverable, clarify config, and planner flag from that compiled plan; per-step capabilities (strategy / gates / validators / compaction / task_source / deliverable) come from the manifest's `steps`. Keep the registry's real role: `registry.PIPELINE_AGENTS` / `get_pipeline_agents()` provide agent MEMBERSHIP/order. Summarize the split crisply: registry = WHICH agents belong to a pipeline (membership/order); manifest (`workflow.yaml`) = HOW they run (per-step capabilities + deliverable + clarify + planner). Preserve the surrounding deepagents/DeepAgentRunner/WebSocket framing as-is.
- In the Data Flow diagram, add the manifest/compile step at run entry. Show that on `ExecutionEngine.execute(...)` the engine calls `compile_for_run(pipeline_type)` → `resolve_alias` → `load_manifest(agents/workflows/<id>/workflow.yaml)` → `_WORKFLOW_COMPILER.compile` → typed `CompiledWorkflow`, and that the agent sequence / deliverable / clarify / planner come from the compiled plan while `registry.get_pipeline_agents` supplies membership. Note the engine ASSERTS the compiled step agent-ids == registry membership and raises `RuntimeError` on drift. Keep the rest of the diagram (AgentContext, gating, create_runner, astream_events, deliverable read-back) intact — this is an INSERT of the compile seam, not a rewrite. In the narration paragraph after the diagram, update the "reads PIPELINE_AGENTS via get_pipeline_agents for the ordered agent list" sentence so it reflects that the ordered SEQUENCE is sourced from the compiled plan and the registry provides membership (the engine asserts they agree).
- Do NOT change the `_build_runner_tools` token anywhere in this task even where it appears in the diagram/Module-Responsibilities table — the global rename is owned by Task 2's sweep.

Fix 2 — Adding a Pipeline (CLAUDE.md "## Adding a Pipeline" section, steps currently ~lines 285-332):
- Keep the existing steps (Step 1 add to `SUPPORTED_PIPELINE_TYPES` in `loader.py`; Step 2 create AGENT.md files; Step 3 add the `PIPELINE_AGENTS` entry in `registry.py`; Step 4 optional `REVISION_BASE_MAP`).
- ADD a new REQUIRED step: create the manifest `agents/workflows/<id>/workflow.yaml` with its `steps`, `deliverable`, `clarify`, and `planner`. State that WITHOUT this manifest, `compile_for_run` raises `FileNotFoundError` at run entry. State that the manifest's step agent-ids must MATCH the `PIPELINE_AGENTS` membership/order or the run aborts with `RuntimeError` (the membership assertion). Place this step so the ordering reads naturally (e.g. after the AGENT.md / registry steps, since the manifest references the agent ids) and renumber the existing steps accordingly. Do not invent fields beyond steps/deliverable/clarify/planner; if unsure of exact manifest shape, point the reader at an existing `agents/workflows/<id>/workflow.yaml` as the template rather than fabricating keys.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && grep -q "compile_for_run" CLAUDE.md && grep -q "CompiledWorkflow" CLAUDE.md && grep -q "workflow.yaml" CLAUDE.md && grep -q "def compile_for_run" agents/execution_engine/engine.py && echo OK-FIX1-2</automated>
  </verify>
  <done>The Architecture Overview and Data Flow diagram document the compile_for_run/CompiledWorkflow/manifest layer alongside the registry's membership role; the Adding a Pipeline section has a required create-`agents/workflows/<id>/workflow.yaml` step citing the FileNotFoundError-on-missing-manifest and the membership RuntimeError. No unrelated section changed.</done>
</task>

<task type="auto">
  <name>Task 2: Correct context_from routing claim + rename factory function (Fix 3 + Fix 4)</name>
  <files>backend/CLAUDE.md</files>
  <action>
First re-verify with grep: `grep -n "_filter_consumed_outputs\|_latest_typed_content" backend/agents/execution_engine/engine.py` (~5395-5426); `grep -n "produces\|consumes" backend/agents/execution_engine/engine.py | head`; `grep -n "context_from" backend/agents/loader.py` (still parsed — lines ~90/309/388); `grep -n "_resolve_runner_tools" backend/agents/factory.py` (def ~570); `grep -c "_build_runner_tools" backend/agents/factory.py` (MUST be 0 — confirms the rename is real).

Fix 3 — context_from is NOT what drives live routing:
- AGENT.md Schema table (CLAUDE.md ~line 246): change the `context_from` row so it is marked LEGACY/vestigial — still parsed and stored by the loader for backward-compat but NOT used by the engine's context injection. In the `produces` / `consumes` row (~line 252), make it the documented live inter-agent routing mechanism: an upstream agent's typed output reaches this agent IFF `set(upstream.produces) & set(this.consumes)` is non-empty, with content read from the typed artifact graph (`ectx.artifacts` via `_filter_consumed_outputs` / `_latest_typed_content` in `engine.py`). Keep mentioning that `produces`/`consumes` are also read by `WorkflowResolver` for DAG validation.
- The "Adding a Pipeline" note that currently reads "Inter-agent context routing is driven by each agent's `context_from` (and the typed `produces`/`consumes` contracts via `WorkflowResolver`)" (~lines 330-332): INVERT the emphasis — `produces`/`consumes` is the LIVE routing mechanism (via `_filter_consumed_outputs`); `context_from` is legacy/vestigial (parsed but not used by the engine).
- The "### `context_from` Examples" subsection (~lines 254-281): do NOT delete it (the field still parses), but add a brief leading note that `context_from` is legacy and produces/consumes is what actually routes context at runtime — keep the examples for reference. Do not expand this into a rewrite.
- Note: the stale `context_from` comment lives in `factory.py` (source code), NOT in CLAUDE.md — this is a DOC-ONLY change; do not edit `factory.py`.

Fix 4 — factory tool-resolution function rename (the verified-stale item the planning files_to_read directive asked to confirm): the doc references `_build_runner_tools` in ~4 places (Module Responsibilities table, the Data Flow diagram, the "## Tool Sets" intro, and "### Adding a custom runner tool"). The live function is `_resolve_runner_tools`. Do a global, surgical replace of the exact token `_build_runner_tools` → `_resolve_runner_tools` throughout CLAUDE.md (the token is unique; replacing all occurrences is safe and changes no surrounding prose). Confirm zero occurrences remain afterward.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && test "$(grep -c '_build_runner_tools' CLAUDE.md)" = "0" && grep -q "_resolve_runner_tools" CLAUDE.md && grep -q "produces" CLAUDE.md && grep -q "consumes" CLAUDE.md && grep -q "_filter_consumed_outputs" agents/execution_engine/engine.py && grep -q "def _resolve_runner_tools" agents/factory.py && test "$(grep -c '_build_runner_tools' agents/factory.py)" = "0" && echo OK-FIX3-4</automated>
  </verify>
  <done>The AGENT.md schema and the Adding-a-Pipeline note document produces/consumes (via _filter_consumed_outputs) as the live routing mechanism and mark context_from legacy/vestigial; every `_build_runner_tools` reference in CLAUDE.md is renamed to `_resolve_runner_tools`; no unrelated section changed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (none)   | Documentation-only edit to a single Markdown file (`backend/CLAUDE.md`). No code paths, endpoints, inputs, packages, or runtime behavior change. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-wrb-01 | Information Disclosure | backend/CLAUDE.md prose | accept | Doc-only change; no secrets, credentials, or non-public internals introduced. Content describes already-shipped code on this branch. |
| T-wrb-02 | Tampering | backend/CLAUDE.md content | mitigate | Surgical edits only; verify gates grep that documented symbols (`compile_for_run`, `_filter_consumed_outputs`, `_resolve_runner_tools`) exist in the cited source files so the doc cannot drift from reality. |
</threat_model>

<verification>
After both tasks, the file should:
- mention `compile_for_run`, `CompiledWorkflow`, and `agents/workflows/<id>/workflow.yaml` in the Architecture Overview / Data Flow / Adding a Pipeline sections;
- mark `context_from` legacy and document `produces`/`consumes` (via `_filter_consumed_outputs`) as the live routing mechanism;
- contain zero `_build_runner_tools` tokens and at least one `_resolve_runner_tools`;
- leave the free-chat path, tool-set behavior, guardrails, skills/hooks, testing, and commit-conventions sections byte-unchanged.

Sanity diff: `cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin && git diff --stat backend/CLAUDE.md` should show ONLY `backend/CLAUDE.md` changed, and `git diff backend/CLAUDE.md` should show edits confined to the four target regions (Architecture Overview, Data Flow, Adding a Pipeline, AGENT.md Schema / context_from / Tool Sets references) — no churn in unrelated sections.
</verification>

<success_criteria>
- All four fixes applied; both task verify gates print OK.
- No source code edited (doc-only): `git diff --name-only` lists only `backend/CLAUDE.md`.
- Documented symbols match live code: `compile_for_run`, the membership-assertion RuntimeError, `_filter_consumed_outputs`, and `_resolve_runner_tools` all still exist in the cited source files.
- Unrelated sections preserved (the doc's voice/structure intact).
</success_criteria>

<output>
Create `.planning/quick/260629-wrb-update-backend-claude-md-document-the-ma/260629-wrb-SUMMARY.md` when done.
</output>
