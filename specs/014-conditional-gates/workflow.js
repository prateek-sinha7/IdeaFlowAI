export const meta = {
  name: 'conditional-gates-014',
  description: 'Execute tasks.md T1-T38 + validators V1-V6 for spec 014 (conditional gates), max 4 parallel agents, dependency-graph scheduled, file-collision safe',
  phases: [
    { title: 'Phase 1 - Compiler', detail: 'T1-T6 + V1' },
    { title: 'Phase 2 - ExecutionContext', detail: 'T7-T11 + V2 (front B, overlaps Phase 1)' },
    { title: 'Phase 3 - Dispatch loop', detail: 'T12-T26 + V3, all sonnet, isolated per RISK-02', model: 'sonnet' },
    { title: 'Phase 4 - Cross-workflow triggering', detail: 'T27-T33 + V4', model: 'sonnet' },
    { title: 'Phase 5 - Frontend', detail: 'T34-T38 + V5 + V6 (front C, starts after T1)' },
  ],
}

// ---------------------------------------------------------------------------
// This script is a direct executable translation of
// specs/014-conditional-gates/tasks.md. Every node id, dependency edge, model
// tag, and validator Guards/PASS-criteria list below is taken verbatim from
// that file. If tasks.md changes, this script must be re-derived from it —
// it is not an independent source of truth.
// ---------------------------------------------------------------------------

const BACKEND_ROOT = 'backend'

// ---- Node table --------------------------------------------------------
// Each node: id, kind ('task'|'validator'), model, deps (hard DAG edges,
// from tasks.md's mermaid diagrams), files (the file(s) it edits - used to
// serialize same-file writes even when the DAG alone would allow parallel
// execution - tasks.md flags several such pairs explicitly, e.g. T4/T5 in
// compiler.py and T13-T21 in engine.py), and prompt (the exact tasks.md
// bullet text for that id).

const PLAN = 'backend/agents/workflows/plan.py'
const COMPILER = 'backend/agents/workflows/compiler.py'
const CONTEXT = 'backend/agents/execution_engine/context.py'
const KERNEL_SERVICES = 'backend/agents/execution_engine/kernel_services.py'
const ENGINE = 'backend/agents/execution_engine/engine.py'
const GATES_BASE = 'backend/agents/capabilities/gates/base.py'
const GATES_CONDITIONAL = 'backend/agents/capabilities/gates/conditional.py'
const REGISTRY = 'backend/agents/capabilities/registry.py'
const GATES_INIT = 'backend/agents/capabilities/gates/__init__.py'
const RUN_COMMANDS = 'backend/app/api/run_commands.py'
const STATE_MACHINE = 'backend/agents/execution_engine/state_machine.py'
const TYPES_TS = 'frontend/src/types/index.ts'
const CANVAS_NODE = 'frontend/src/components/workflow/composer/CanvasNode.tsx'
const COMPOSER_PAGE = 'frontend/src/components/workflow/composer/ComposerPage.tsx'
const RUN_HISTORY = 'frontend/src/components/(run-history component, identify during T38)'

const NODES = {
  // ---------------- Phase 1 -----------------------------------------
  T1: {
    kind: 'task', model: 'haiku', phase: 'Phase 1 - Compiler', deps: [], files: [PLAN],
    prompt: `In ${PLAN}, add RouteOutcome and RouteSpec dataclasses, matching specs/014-conditional-gates/data-model.md's field tables exactly: RouteOutcome{trigger: str, target: str}; RouteSpec{condition_agent: str | None = None, outcomes: dict[str, RouteOutcome] = field(default_factory=dict), default_next: str | None = None, loop_max_iterations: int = 5, trigger_max_depth: int = 5}. Add Step.route: RouteSpec | None = None and Step.is_leaf: bool = False to the existing Step dataclass in the same file. Mirror the exact style of the neighboring FanoutSpec dataclass (docstring format, field comments). Do not touch any other dataclass in this file. Report the exact diff you made.`,
  },
  T2: {
    kind: 'task', model: 'haiku', phase: 'Phase 1 - Compiler', deps: [], files: [COMPILER],
    prompt: `In ${COMPILER}, add "route" to the _ALLOWED_STEP_KEYS frozenset, and add two new frozensets near it: _ALLOWED_ROUTE_KEYS = frozenset({"condition_agent", "outcomes", "default_next", "loop_max_iterations", "trigger_max_depth"}) and _ALLOWED_OUTCOME_KEYS = frozenset({"trigger", "target"}). Match the existing _ALLOWED_FANOUT_KEYS definition's style exactly (comment block above it explaining what it gates). Report the exact diff you made.`,
  },
  T3: {
    kind: 'task', model: 'sonnet', phase: 'Phase 1 - Compiler', deps: ['T1', 'T2'], files: [COMPILER],
    prompt: `In ${COMPILER}, add a _compile_route(raw_route: object, where: str) -> "RouteSpec | None" static method, mirroring _compile_fanout() line-for-line in structure: None input -> None output; non-dict input -> CompilerError; strict-key reject via _ALLOWED_ROUTE_KEYS; for each outcomes entry, strict-key reject via _ALLOWED_OUTCOME_KEYS, validate trigger is exactly "step" or "workflow" (else CompilerError), validate target is a non-empty string (else CompilerError), and build a RouteOutcome. Return a populated RouteSpec. Wire the call site into _compile_step so a step's route: key is compiled the same way fanout: already is. Use specs/014-conditional-gates/contracts/manifest-route-schema.md as the exact behavioral spec - every "compile-time guarantee" listed there must hold after this task. RouteOutcome/RouteSpec were added to backend/agents/workflows/plan.py by a prior task (T1) and _ALLOWED_ROUTE_KEYS/_ALLOWED_OUTCOME_KEYS by T2 - both already exist, import/use them. Report the exact diff you made.`,
  },
  T4: {
    kind: 'task', model: 'sonnet', phase: 'Phase 1 - Compiler', deps: ['T3'], files: [COMPILER],
    prompt: `In ${COMPILER}, add the R-03 cross-field check inside _compile_step (after _compile_route runs and after gates is parsed): if "conditional" is in the step's gates list but the compiled route is None or has empty outcomes, raise CompilerError naming the step and explaining route: is required when gates: [conditional] is declared. If route is non-None/non-empty but "conditional" is NOT in gates, raise CompilerError the other direction, naming the step and explaining gates: [conditional] is required when route: is declared. Write this as a small standalone check (a few lines), not a new generalized "capability requires gate" mechanism (per plan.md's explicit scope-discipline note). Report the exact diff you made.`,
  },
  T5: {
    kind: 'task', model: 'sonnet', phase: 'Phase 1 - Compiler', deps: ['T3'], files: [COMPILER],
    prompt: `In ${COMPILER}, add _validate_route_targets() (new function, mirrors _validate_fanout_source_upstream in structure - runs once after all steps compile): for every step's route.outcomes[...] with trigger == "step", confirm target is a real step id in this workflow's compiled step set, else CompilerError naming the step, the outcome's condition-value key, and the unresolved target. For trigger == "workflow", confirm target == "self" OR resolves against a real saved workflow id - first read agents/registry.py and app/api/user_workflows.py to find the existing helper used to validate a user_workflow_id reference elsewhere in this codebase (report which one you used and why), and reuse it rather than inventing a new lookup. Also validate route.default_next the same way as a trigger: "step" target. Wire this function to run once, after the full step list compiles, at the same point _validate_dag already runs. Report the exact diff you made and which existing helper you reused for workflow-id resolution.`,
  },
  T6: {
    kind: 'task', model: 'sonnet', phase: 'Phase 1 - Compiler', deps: ['T5'], files: [COMPILER],
    prompt: `In ${COMPILER}, extend the SAME _validate_route_targets() function added by a prior task (T5) with the R-27 check: for every step whose route has non-empty outcomes, confirm route.condition_agent (or the step itself, when condition_agent is None) declares produces: ["route_decision"] in the manifest - else CompilerError naming the step and its resolved decision-source step. Then, as the LAST step of this same task, compute is_leaf for every compiled step (R-26): a step is a leaf iff no route outcome (from ANY step in the workflow) and no default linear-next relationship names it as a non-terminal continuation - i.e., nothing is compiled to run after it on any reachable path. Set Step.is_leaf accordingly for every step (Step.is_leaf was added by T1). Add a regression assertion (inline comment + a one-line check, not a full test) confirming _validate_dag's Kahn-algorithm graph is built ONLY from step.depends_on and never reads route.outcomes - R-09 must hold with zero changes to _validate_dag itself. Report the exact diff you made.`,
  },
  V1: {
    kind: 'validator', model: 'sonnet', phase: 'Phase 1 - Compiler', deps: ['T4', 'T6'],
    guards: ['T1', 'T2', 'T3', 'T4', 'T5', 'T6'],
    prompt: `You are Validator V1 for Phase 1 (compiler) of spec 014 (conditional gates). Guards: T1-T6.

Using the five fixtures at backend/agents/workflows/ex_A*/workflow.yaml, run the compile-and-print-leaves script and the R-03/R-27 negative-rejection checks described in specs/014-conditional-gates/quickstart.md's "After Phase 1 (compiler)" section. Report each fixture's compile result and leaf set against plan.md's Phase 1 Accept criteria and spec.md's AC-01, AC-02, AC-09 (compile-time half), AC-10.

PASS requires ALL of:
(a) all five fixtures compile with zero CompilerError
(b) ex_A2_branch reports exactly two leaves (say_hello, say_hola)
(c) ex_A3_target reports exactly one leaf (welcome)
(d) the negative check (stripping "conditional" from check's gates while route: stays) raises CompilerError
(e) a fixture with produces: ["route_decision"] removed from a condition_agent step also raises CompilerError (write this negative check if quickstart.md doesn't already cover R-27)

Report PASS/FAIL per criterion (a)-(e), not just "script ran". If ANY criterion fails, return FAIL with the specific criterion and the exact error/output that proves it.`,
  },

  // ---------------- Phase 2 (front B - independent of Phase 1) ------
  T7: {
    kind: 'task', model: 'haiku', phase: 'Phase 2 - ExecutionContext', deps: [], files: [CONTEXT],
    prompt: `In ${CONTEXT}, add two fields to the ExecutionContext dataclass: step_visit_counts: dict[str, int] = field(default_factory=dict) and trigger_depth: int = 0. Match the existing style/placement of other per-run mutable-state fields already on this dataclass (docstring comment above each new field explaining its purpose per specs/014-conditional-gates/data-model.md). Report the exact diff you made.`,
  },
  T8: {
    kind: 'task', model: 'haiku', phase: 'Phase 2 - ExecutionContext', deps: ['T7'], files: ['backend/tests/unit/test_execution_engine.py or a new test_execution_context.py'],
    prompt: `Write a unit test in backend/tests/unit/test_execution_engine.py (or a new test_execution_context.py if that's the established pattern for context-only tests - check the existing file list first and match it) confirming step_visit_counts starts empty and increments correctly across repeated dict-key mutation (e.g. ectx.step_visit_counts["step_a"] = ectx.step_visit_counts.get("step_a", 0) + 1, called 3 times, asserts the value is 3). The step_visit_counts field was added to ExecutionContext by a prior task (T7). Run the test and confirm it passes. Report the file path and the test result.`,
  },
  T9: {
    kind: 'task', model: 'sonnet', phase: 'Phase 2 - ExecutionContext', deps: ['T7'], files: [CONTEXT],
    prompt: `Determine and document (as a code comment on the trigger_depth field in ${CONTEXT}, which a prior task T7 added, plus a short note in your completion report) the exact mechanism by which trigger_depth gets propagated at run-mint time: 0 for a non-triggered run, parent's trigger_depth + 1 for a triggered run. Since the minting call site doesn't exist until Phase 4 (run_trigger_workflow), this task's job is ONLY to confirm ExecutionContext's constructor/factory can accept an initial trigger_depth value without breaking any existing caller (all existing callers should default to 0 - verify no existing ExecutionContext(...) call site needs updating). Report your finding and the diff (if any).`,
  },
  T10: {
    kind: 'task', model: 'haiku', phase: 'Phase 2 - ExecutionContext', deps: ['T9'], files: ['backend/tests/unit/test_execution_engine.py or a new test_execution_context.py'],
    prompt: `Write a unit test confirming a mocked chain of 2-3 ExecutionContext constructions with explicit trigger_depth values propagates correctly (e.g. ExecutionContext(trigger_depth=0) -> child ExecutionContext(trigger_depth=1) -> grandchild ExecutionContext(trigger_depth=2)), asserting each level's value is exactly parent+1. This is a standalone dataclass-field test, not an end-to-end trigger test (that's Phase 4). A prior task (T9) confirmed the propagation mechanism/design. Run the test and confirm it passes. Report the file path and the test result.`,
  },
  T11: {
    kind: 'task', model: 'sonnet', phase: 'Phase 2 - ExecutionContext', deps: [], files: [], // read-only investigation, zero deps per tasks.md
    prompt: `Read ${KERNEL_SERVICES} lines 337-360 (record_gate_event) in full, per plan.md Phase 1 task 6 / UNKNOWN-2. Determine whether its (step, gate, outcome) keying can collide across loop passes the same way gate_key/failed_invocations could before the R-08 fix. Report your finding as a short written verdict (collides / does not collide, with the specific reasoning) - do NOT fix it in this task even if it does collide; the fix (if needed) belongs in a later Phase 3 task where step_visit_counts is wired into the dispatch loop, since it depends on that existing first. This task's sole output is the verdict, to unblock that later task's scoping. Report the verdict clearly as either "COLLIDES" or "DOES NOT COLLIDE" as the first line of your report.`,
  },
  V2: {
    kind: 'validator', model: 'sonnet', phase: 'Phase 2 - ExecutionContext', deps: ['T8', 'T10', 'T11'],
    guards: ['T7', 'T8', 'T9', 'T10', 'T11'],
    prompt: `You are Validator V2 for Phase 2 (ExecutionContext) of spec 014 (conditional gates). Guards: T7-T11.

Run: cd backend && python3.11 -m pytest tests/unit/ -k "step_visit_counts or trigger_depth" -v (per specs/014-conditional-gates/quickstart.md's "After Phase 2" section) and confirm all of T8's and T10's tests pass. Additionally confirm ExecutionContext's existing (pre-Phase-2) test suite still passes unmodified (no regression from adding the two new fields with safe defaults). Report T11's UNKNOWN-2 verdict alongside the test results, since it's a required input to Phase 3 (specifically task T19) even though it produced no code this phase.

PASS requires ALL of: both new unit tests pass; the full existing ExecutionContext test suite is unmodified/green; T11's verdict is clearly stated (COLLIDES or DOES NOT COLLIDE) in your report.

If ANY of these fail, return FAIL with specifics.`,
  },

  // ---------------- Phase 3 (highest risk, all sonnet) ---------------
  T12: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: [], files: ['backend/tests/agents/test_characterization_*.py'],
    prompt: `Establish the characterization safety net BEFORE anyone touches engine.py's dispatch loop. Verified during task authoring: these tests ALREADY EXIST - backend/tests/agents/test_characterization_{prototype,prototype_revision,ppt,app_builder}.py plus a backend/tests/agents/characterization/ fixture directory. So this task is "confirm current and green", not "write from scratch": (a) run all four characterization suites and confirm they pass on the untouched tree - if any is already red BEFORE Phase 3 starts, stop and report, because a pre-existing failure destroys the byte-identity signal the whole phase depends on; (b) confirm their coverage actually includes the dispatch loop's behavior (read one suite to verify it asserts on deliverable + event sequence, not just "no exception"); (c) if a workflow family with meaningfully different dispatch behavior is NOT covered (e.g. one using fanout/subagents, since the loop conversion touches the sibling-group skip logic), add one covering suite before proceeding. Record the exact pass/fail baseline in your completion report - a later task (T22) compares against it.`,
  },
  T13: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T12'], files: [ENGINE],
    prompt: `In ${ENGINE}, convert the main dispatch loop at (approximately) :2586 - currently "for i, spec in enumerate(ordered_agents):" - to an index-based "while cursor < len(ordered_agents):" loop with a mutable cursor variable. Replace every i-based reference inside the loop body with cursor (search the full loop body carefully - line numbers have drifted before in this codebase's history, confirm the actual current line by searching for the "enumerate(ordered_agents)" string, not by trusting any cited line number literally). Do NOT add any routing logic yet - this task's ONLY job is the mechanical for-to-while conversion, behavior-preserving for every workflow that never declares route:. Run the characterization suite confirmed by a prior task (T12) immediately after this change and confirm byte-identical output before you finish. Report the exact diff and the characterization suite result.`,
  },
  T14: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T13', 'T15'], files: [ENGINE],
    prompt: `In ${ENGINE}, locate the existing gate-outcome consumer arms (search for 'if _outcome == "cancel":' and 'if _outcome in ("block", "wait_human"):'). Add a new 'elif _outcome == "route":' arm reading GateOutcome.detail (the {"trigger": ..., "target": ...} dict set by the ConditionalGate class, which a prior task T15 created at backend/agents/capabilities/gates/conditional.py). For trigger == "step": resolve target's index in ordered_agents and set cursor = that index instead of the default cursor += 1 advance (the while-loop conversion from a prior task T13 already supports this - forward and backward are the same code path). For trigger == "workflow": for THIS task, stub the call (e.g. raise NotImplementedError("Phase 4 wires this") or a clearly marked TODO comment referencing Phase 4) - do not implement the actual cross-workflow spawn here, that is Phase 4's job. Report the exact diff you made.`,
  },
  T15: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T16', 'T17'], files: [GATES_CONDITIONAL],
    prompt: `Create new file ${GATES_CONDITIONAL} - ConditionalGate.evaluate(step, ctx) -> GateOutcome, mirroring the plain-awaited pattern of the existing validation.py:72 / security.py:81 gates (NOT the stream+collector pattern human/approval gates use - confirm you're matching the right one by reading both patterns first).

The class MUST carry the @register("gate", "conditional", user_allowed=True, description="...") decorator, matching human.py:57-61 / validation.py:47-51's form exactly. user_allowed=True is load-bearing, not boilerplate: _TRUST defaults to False for any unregistered flag, and compiler.py::_check_trust raises CompilerError for a non-user-allowed capability under an UNTRUSTED (user/db) manifest - so omitting it would let file-backed fixtures compile while silently breaking every composer-built workflow. Write a description in the same voice as the existing four gates. The GATE_ROUTE constant this task needs is being added to backend/agents/capabilities/gates/base.py by a parallel task (T16), and the registry entry by another parallel task (T17) - import/use GATE_ROUTE from gates.base.

Logic: (1) resolve the decision source via route.condition_agent (default: this step's own id) using _latest_typed_content (confirm the exact delegation path via kernel_services.py:1305); (2) json.loads the content; (3) extract parsed["decision"]; on malformed JSON or a missing "decision" key, treat as "no match" (do not raise/crash - see specs/014-conditional-gates/contracts/manifest-route-schema.md's runtime contract step 7 for the exact required behavior); (4) match against route.outcomes keys; on match, return GateOutcome(GATE_ROUTE, detail={"trigger": outcome.trigger, "target": outcome.target}); on no match with default_next set, return GateOutcome(GATE_PASS); on no match with default_next unset, the step should terminate the run (confirm the exact GateOutcome shape the engine already uses for "nowhere to go" - likely mirrors how a block with no recovery path already works - and use the SAME shape, don't invent a new one). Report the full file content you wrote.`,
  },
  T16: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: [], files: [GATES_BASE],
    prompt: `Add GATE_ROUTE = "route" to ${GATES_BASE}, alongside the existing GATE_PASS/GATE_BLOCK/GATE_WAIT_HUMAN constants. No other changes to this file - GateOutcome's shape (outcome: str, events: list[dict], detail: dict | None) is unchanged, only the vocabulary grows. Report the exact diff you made.`,
  },
  T17: {
    kind: 'task', model: 'haiku', phase: 'Phase 3 - Dispatch loop', deps: [], files: [REGISTRY, GATES_INIT],
    prompt: `Make "conditional" a fully-wired capability - THREE edits, all required; doing only the first leaves a gate that fails at runtime:
(a) add ("gate", "conditional") to the _KNOWN frozenset in ${REGISTRY}, in the same literal region as the existing four gate entries;
(b) add conditional to the explicit import list in ${GATES_INIT} (it imports approval, human, security, validation by name - discover() does NO auto-walk, so an unimported module's @register never fires and resolve("gate", "conditional") raises at runtime);
(c) update that file's module docstring, which enumerates "all four gates" - it becomes five.
No changes to resolve()/is_registered() themselves. Report the exact diffs you made to both files.`,
  },
  T18: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T14'], files: [ENGINE],
    prompt: `In ${ENGINE}, wire R-07's loop-cap enforcement: before the "step" arm (added by a prior task T14) advances the cursor to a backward target, check ectx.step_visit_counts (field added to ExecutionContext by Phase 2 task T7) for that target against the target step's route.loop_max_iterations (default 5). If the check would exceed the cap, raise the existing BudgetExceeded exception (confirm the exact import/raise pattern already used elsewhere in this file, e.g. near the existing fan-out budget checks) - fail closed, do not silently cap the count. On a successful (under-cap) jump, increment ectx.step_visit_counts[target]. Report the exact diff you made.`,
  },
  T19: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T13'], files: [ENGINE],
    prompt: `In ${ENGINE}, implement R-08: find gate_key = f"{pipeline_run_id}:{agent_id}" (search for this exact f-string pattern) and change it to fold in the visit count: f"{run_id}:{agent_id}:{visit_count}" where visit_count comes from ectx.step_visit_counts.get(agent_id, 0). Also find and update ectx.failed_invocations keying the same way. Phase 2's task T11 investigated whether record_gate_event's (step, gate, outcome) keying in kernel_services.py also needs this fix - if T11's verdict (available in this workflow's Phase 2 results) says it COLLIDES, apply the identical visit-count discriminator there too in this same task. Report the exact diff(s) you made and whether you touched record_gate_event.`,
  },
  T20: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: [], files: [ENGINE], // needs Phase 1 T6's is_leaf but no Phase 3 task dep per tasks.md
    prompt: `In ${ENGINE}, implement R-26's engine-side half: locate _deliverable_filename_override (search for this exact method name). Change its leaf check from "if index != len(ordered_agents) - 1: return None" to read step.is_leaf (the compiler-computed field added to Step by Phase 1 task T6) instead of comparing array position. Every leaf step should now be told to write the declared single_file deliverable name, not only whichever step happens to be array-last. Report the exact diff you made.`,
  },
  T21: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T13'], files: [ENGINE],
    prompt: `In ${ENGINE} (or wherever the resume-path docstrings live - likely near _first_incomplete_step, search for this method), add a one-line docstring note per R-11: a mid-loop/branch crash-restart resumes at the first incomplete step by original array position, which may be incorrect for a looped/branched run - this is a documented v1 limitation, not a behavior change. Do NOT modify _first_incomplete_step's actual logic in this task - R-11 is an explicit scope cut, this task only documents it. Report the exact diff you made.`,
  },
  T22: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T14', 'T15', 'T18', 'T19', 'T20', 'T21'], files: [], // hard gate, read-only verification
    prompt: `Run the FULL characterization suite (the one confirmed current by Phase 3 task T12) again now that T13-T21 have all landed, and confirm byte-identical output for every workflow that never declares route:. This is a HARD GATE - if anything drifted, stop and report exactly which characterization case differs and what the diff is; do not guess which prior task caused it, just report the drift precisely. If everything is byte-identical, report PASS clearly as the first line of your report.`,
  },
  T23: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T22'], files: [],
    prompt: `Using a scripted-model test harness (find and match this repo's existing pattern for launching a run programmatically with a scripted model response - likely in tests/agents/_scripted_model.py or similar, per backend/CLAUDE.md's testing notes), run ex_A1_loop (A1, the loop fixture) end-to-end with a model scripted to answer {"decision": "retry"} twice then {"decision": "ok"}. Assert: greet and check each ran exactly 3 times; done ran exactly once; the run completed normally (not BudgetExceeded, since 3 <= loop_max_iterations). Report the exact assertions and their results.`,
  },
  T24: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T22'], files: [],
    prompt: `Using the same scripted-model test harness as T23, script the model to ALWAYS answer {"decision": "retry"} (never "ok") and confirm the run for ex_A1_loop fails closed with BudgetExceeded after exactly loop_max_iterations (3, per this fixture's declared value) passes - not 4, not unbounded, not silently swallowed. Report the exact assertion and result.`,
  },
  T25: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T22'], files: [],
    prompt: `Using the same scripted-model test harness as T23, run ex_A2_branch (A2, the forward-branch fixture) end-to-end twice - once scripted to answer {"decision": "english"}, once {"decision": "spanish"}. Assert: in the first run, say_hello ran and say_hola did NOT run (and vice versa for the second run) - confirms R-06/R-09's mutual exclusivity holds for a forward branch, not just the loop case. Also add an assertion that the SKIPPED branch's step_visit_counts stay at 0 (this specific assertion is required per the Phase 3 validator's AC-04 check). Report the exact assertions and their results.`,
  },
  T26: {
    kind: 'task', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T22'], files: [],
    prompt: `Using the same scripted-model test harness as T23, run ex_A4_human_gate (A4, the human-gate-as-condition-source fixture) end-to-end, scripting BOTH the human-gate response (whatever mechanism this repo's existing human gate tests use to supply a scripted human answer) AND confirm revise_check's condition_agent: review correctly reads that captured response rather than its own (empty) output. Script one pass that answers "revise" (expect a loop back to greet) and one pass that answers "continue" (expect done to run). This is the one fixture proving R-05's "condition source can be an earlier, non-self, non-agent-typed step" claim end-to-end. Report the exact assertions and their results.`,
  },
  V3: {
    kind: 'validator', model: 'sonnet', phase: 'Phase 3 - Dispatch loop', deps: ['T23', 'T24', 'T25', 'T26'],
    guards: ['T12', 'T13', 'T14', 'T15', 'T16', 'T17', 'T18', 'T19', 'T20', 'T21', 'T22', 'T23', 'T24', 'T25', 'T26'],
    prompt: `You are Validator V3 for Phase 3 (dispatch loop conversion) of spec 014 (conditional gates), the highest-risk phase in the whole plan. Guards: T12-T26 (the entire phase).

Re-run T22's full characterization suite one final time (confirm still green after all Phase 3 tasks). Re-confirm T23-T26's four scripted-run assertions all pass. Cross-check against spec.md's AC-03 and AC-04 explicitly - quote the exact AC text from specs/014-conditional-gates/spec.md and confirm each clause is satisfied by a specific test: AC-03 needs T23+T24 together (loop re-executes AND fails closed at the cap); AC-04 needs T25 (skipped steps' step_visit_counts stay at 0).

PASS requires ALL of: characterization suite still byte-identical; all four scripted-run assertions (T23-T26) pass; AC-03 and AC-04 both explicitly satisfied with evidence.

Report PASS/FAIL per criterion. If ANY fail, return FAIL naming the specific task(s) to reopen - Phase 4 does not start.`,
  },

  // ---------------- Phase 4 -------------------------------------------
  T27: {
    kind: 'task', model: 'sonnet', phase: 'Phase 4 - Cross-workflow triggering', deps: ['V3'], files: [RUN_COMMANDS],
    prompt: `Read ${RUN_COMMANDS}'s launch_run function (around line 2213) end-to-end, in full (this resolves plan.md's UNKNOWN-1 / RISK-04 - do not estimate the extraction boundary in advance, determine it from the actual code). Extract the mint-and-spawn logic into a new plain async function (name it something like _launch_run_core or whatever fits the file's existing naming convention - check for precedent) callable both by the existing HTTP handler (which becomes a thin wrapper calling the new core) and by a not-yet-written kernel delegate (a later task, T28, will add it). Write a regression test hitting the existing HTTP endpoint before and after this extraction, confirming byte-identical response shape/behavior - the HTTP path must be unaffected by this refactor. Report the exact diff you made and the new core function's name/signature.`,
  },
  T28: {
    kind: 'task', model: 'sonnet', phase: 'Phase 4 - Cross-workflow triggering', deps: ['T27'], files: [KERNEL_SERVICES],
    prompt: `In ${KERNEL_SERVICES}, add a new delegate run_trigger_workflow(step, ectx, *, workflow_ref: str) -> str (returns the new run's id), placed parallel to the existing run_human_gate (:1233) and run_fanout (:1025) - NOT folded into either.

Logic: (1) resolve workflow_ref ("self" -> the current workflow's own id; otherwise a saved user_workflow_id - reuse the SAME resolution helper Phase 1 task T5 identified/used, do not invent a second one); (2) enforce R-18/R-19: walk ectx.trigger_depth (field added to ExecutionContext by Phase 2 task T7, propagation confirmed by T9) against the FIXED ceiling of 5 (R-19, clarified - not a variable check, an exact-equality-to-5 check per the manifest's own trigger_max_depth field, which the compiler already enforces can only be 5); raise BudgetExceeded on breach; (3) call the new core function added by T27 with parent_run_id = ectx.run_id; (4) set the new run's owner_id/workspace_id to ectx's own values, unconditionally (R-15 - no independent specification, never null); (5) return the new run's id.

Report the exact diff you made.`,
  },
  T29: {
    kind: 'task', model: 'sonnet', phase: 'Phase 4 - Cross-workflow triggering', deps: ['T28'], files: [ENGINE],
    prompt: `In ${ENGINE}, replace the "trigger == workflow" stub added in Phase 3 (task T14) with a real call to run_trigger_workflow (the delegate added by T28). On return: set WorkflowRun.status = "diverted" (confirm the exact status-setting mechanism already used elsewhere in this file, e.g. how "cancelled"/"failed" are set) and end this run's dispatch loop - no default_next fallback, no wait on the new run (R-13, Option 2). Report the exact diff you made.`,
  },
  T30: {
    kind: 'task', model: 'haiku', phase: 'Phase 4 - Cross-workflow triggering', deps: [], files: [STATE_MACHINE],
    prompt: `In ${STATE_MACHINE}, add "diverted" to the TERMINAL_STATES frozenset (currently {"completed", "failed", "cancelled"}). This is the ONLY change this task makes to this file. Report the exact diff you made.`,
  },
  T31: {
    kind: 'task', model: 'sonnet', phase: 'Phase 4 - Cross-workflow triggering', deps: ['T30'], files: ['(codebase-wide grep, edits wherever found)'],
    prompt: `Per RISK-03 in specs/014-conditional-gates/plan.md, grep the ENTIRE codebase (not just state_machine.py) for every reference to TERMINAL_STATES (both direct enumeration by name and "status in TERMINAL_STATES" checks) and every place "completed"/"failed"/"cancelled" are enumerated together as "the terminal set" without importing the actual constant (which now includes "diverted", added by a prior task T30). Report a list of every call site found, with a one-line verdict per site: "needs no change" (already reads the constant, so "diverted" is automatically included) vs. "needs updating" (hardcodes the three old values by name and must be updated to include "diverted"). Apply the needed updates in this same task. Do not skip any site found by the grep - an incomplete audit here is explicitly what RISK-03 warns against. Report the full list of sites checked and every diff you made.`,
  },
  T32: {
    kind: 'task', model: 'sonnet', phase: 'Phase 4 - Cross-workflow triggering', deps: ['T29'], files: [ENGINE],
    prompt: `In ${ENGINE}, implement R-28: immediately after the status transition to "diverted" added by a prior task (T29), emit a new additive SSE/websocket event "pipeline_diverted" through the engine's existing generic event-forward path (the SAME mechanism pipeline_cancelled already uses - search for the pipeline_cancelled emit call sites to find the pattern). Payload exactly matches specs/014-conditional-gates/contracts/sse-pipeline-diverted.md's shape: {"pipeline_run_id": ..., "diverted_to_run_id": ..., "diverted_to_workflow": ...} - note diverted_to_workflow must always report the ACTUAL resolved workflow id, never the literal string "self", even when the manifest declared target: "self". Report the exact diff you made.`,
  },
  T33: {
    kind: 'task', model: 'sonnet', phase: 'Phase 4 - Cross-workflow triggering', deps: ['T28', 'T29'], files: [],
    prompt: `Write a regression test (per plan.md Phase 4 task 5 / decision-log #19) confirming the R-15 budget addendum: mint a triggered run via run_trigger_workflow (added by T28) and the engine wiring (added by T29), and confirm its spend IS visible in the SAME BudgetManager.workspace_ceiling aggregate as the triggering run - i.e., reserve()'s existing "workspace_spent + requested > workspace_ceiling" check correctly scopes both runs together, because the triggered run's ExecutionContext carries the inherited workspace_id. This confirms NO new budget mechanism is needed, per the clarification recorded in spec.md - write the test to prove the existing mechanism already does the right thing, not to add new budget code. Report the test file path and result.`,
  },
  V4: {
    kind: 'validator', model: 'sonnet', phase: 'Phase 4 - Cross-workflow triggering', deps: ['T31', 'T32', 'T33'],
    guards: ['T27', 'T28', 'T29', 'T30', 'T31', 'T32', 'T33'],
    prompt: `You are Validator V4 for Phase 4 (cross-workflow triggering) of spec 014 (conditional gates). Guards: T27-T33.

Using the harness from Phase 3's T23, run ex_A3_divert (A3, the divert fixture) end-to-end scripted to answer {"decision": "divert"}. Assert against spec.md's AC-05, AC-06, AC-11 explicitly:
AC-05 - the first run's WorkflowRun.status == "diverted", a second WorkflowRun exists with parent_run_id == first run's id, workflow type == ex_A3_target, owner_id/workspace_id == the first run's values, and the first run dispatched no further steps of its own;
AC-06 - build (or reuse if one already exists) a 6-level-deep trigger chain and confirm the 6th attempt fails closed with BudgetExceeded, not a silent infinite mint;
AC-11 - the first run's SSE stream emitted exactly one pipeline_diverted event, with the correct payload shape, before the stream closed.
Also re-run T31's grep audit one more time as a final sweep (confirm nothing new was introduced by T32/T33 that hardcodes the terminal-state set).

Report PASS/FAIL per AC. If ANY fail, return FAIL naming the specific task(s) to reopen.`,
  },

  // ---------------- Phase 5 (front C - starts after T1) --------------
  T34: {
    kind: 'task', model: 'haiku', phase: 'Phase 5 - Frontend', deps: ['T1'], files: [TYPES_TS],
    prompt: `In ${TYPES_TS}, add a route?: field to both ManifestStep and AgentDef interfaces: { condition_agent?: string; outcomes: Record<string, {trigger: "step" | "workflow"; target: string}>; default_next?: string; loop_max_iterations?: number; trigger_max_depth?: number }. Mirror RouteSpec's Python shape (added to backend/agents/workflows/plan.py by Phase 1 task T1) field-for-field. No other changes to either interface. Report the exact diff you made.`,
  },
  V5: {
    kind: 'validator', model: 'sonnet', phase: 'Phase 5 - Frontend', deps: ['T34'],
    guards: ['T34'],
    prompt: `You are Validator V5 for Phase 5 (type contract, backend<->frontend) of spec 014 (conditional gates). Guards: T34 (and T1's shape from Phase 1).

Confirm frontend/src/types/index.ts's new route field (added by T34) matches backend/agents/workflows/plan.py's RouteSpec/RouteOutcome (added by Phase 1 task T1) field-for-field, including optionality (condition_agent? matches condition_agent: str | None = None, etc.) and the outcomes dict's value shape. Run "cd frontend && npx tsc --noEmit" to confirm no type errors were introduced.

PASS requires: exact field-for-field match confirmed, and tsc clean. If there's a mismatch, name the exact field and return FAIL - T35/T36 must not start against a wrong shape.`,
  },
  T35: {
    kind: 'task', model: 'sonnet', phase: 'Phase 5 - Frontend', deps: ['V5'], files: [CANVAS_NODE],
    prompt: `In ${CANVAS_NODE}, add a route-target editor UI to the existing agent-card node, surfaced when "conditional" is checked in that node's gates list. Scoping note: do not attempt the full graph-layout conversion (CanvasView.tsx, out of scope for this spec - flagged for its own separate scoping pass) as part of this task - this task is scoped to the NODE-level editor UI only (the panel/form that lets an author declare outcomes for a step), not the edge-drawing/layout mechanics. The route field's TypeScript shape was added to frontend/src/types/index.ts by a prior task (T34), confirmed correct by validator V5. If implementing this task surfaces a hard dependency on the layout work that can't be avoided, stop and report rather than expanding scope silently. Report the exact diff you made.`,
  },
  T36: {
    kind: 'task', model: 'sonnet', phase: 'Phase 5 - Frontend', deps: ['V5'], files: [CANVAS_NODE],
    prompt: `In ${CANVAS_NODE}, add the ONE new node kind this spec introduces: an external-pipeline reference card, visually distinct from both the standard agent card and the route-target-editor state (added by a parallel/prior task T35), representing a trigger: "workflow" outcome's target. This confirms R-22's explicit correction (no new node kind for in-workflow routing - only this one, for cross-workflow triggers). Report the exact diff you made.`,
  },
  T37: {
    kind: 'task', model: 'sonnet', phase: 'Phase 5 - Frontend', deps: ['T34'], files: [COMPOSER_PAGE],
    prompt: `In ${COMPOSER_PAGE}, update handleSave/handleRunOnce/buildWorkflowManifest to serialize the new route field per step (matching the shape added to frontend/src/types/index.ts by T34 exactly); any node carrying a non-empty route forces the full-manifest save/run path (needsFullManifest) - confirm this is the SAME trigger condition already used for other non-flat-list step data (e.g. fanout) by reading the existing needsFullManifest implementation before modifying it, and follow its established pattern rather than adding a parallel check. Report the exact diff you made.`,
  },
  T38: {
    kind: 'task', model: 'sonnet', phase: 'Phase 5 - Frontend', deps: ['T34'], files: [RUN_HISTORY],
    prompt: `Implement R-20's two-linked-cards treatment in the run-history UI: the diverted run's card shows "Diverted to {workflow_id} ->" linking to the triggered run; the triggered run's card shows "<- Continued from {parent}, step {step_id}" linking back. Per specs/014-conditional-gates/contracts/sse-pipeline-diverted.md's consumer contract: the LIVE case is driven by the pipeline_diverted event (payload shape added by Phase 4 task T32); the HISTORICAL case (page load with no live stream) must be reconstructable purely from persisted WorkflowRun.status == "diverted" + parent_run_id - implement BOTH paths, not just the live one, and identify the exact existing run-history component to modify (not yet named in the spec - find it first). Note: the live-case path needs T32's event shape to exist (Phase 4); the historical-case path can be built and tested independently of Phase 4. Report which component you modified and the exact diff.`,
  },
  V6: {
    kind: 'validator', model: 'sonnet', phase: 'Phase 5 - Frontend', deps: ['T35', 'T36', 'T37', 'T38', 'V4'],
    guards: ['T35', 'T36', 'T37', 'T38'],
    prompt: `You are Validator V6 for Phase 5 (acceptance) of spec 014 (conditional gates). Guards: T35, T36, T37, T38.

Distinct from V5, which only checked the type contract - this validator checks the two ACs Phase 5 actually owns.

Verify AC-07: using the composer UI, author all three outcome kinds end-to-end - a trigger: step forward branch, a trigger: step backward loop, and a trigger: workflow divert - using the existing agent node (T35's editor) plus the one new external-pipeline reference node (T36); save, and confirm the emitted manifest's route: blocks match what was drawn, via the full-manifest path (T37).

Verify AC-08: run a workflow that diverts and confirm run history (T38) shows the two linked cards, each linking to the other, in BOTH the live case (stream open when the divert fires) and the historical case (fresh page load afterward).

Report PASS/FAIL per AC with the specific evidence for each (the actual serialized manifest content, or a description of what you observed - not "looks right"). If ANY fail, return FAIL naming the specific task(s) to reopen.`,
  },
}

// ---------------------------------------------------------------------------
// Scheduler
// ---------------------------------------------------------------------------
// A real dependency-graph executor, not hand-enumerated "waves":
//  - a node runs only once every dep in NODES[id].deps has resolved 'done'
//  - concurrency is capped at 4 (MAX_PARALLEL) globally across the whole run
//  - two nodes that write the SAME file never run concurrently, even if the
//    DAG alone would allow it (tasks.md flags several such pairs explicitly,
//    e.g. T4/T5 in compiler.py, T13-T21 in engine.py) - this is enforced
//    automatically here via the `files` field rather than left to the
//    reader's discipline
//  - a validator (kind: 'validator') that returns FAIL triggers a bounded
//    fix-and-reverify loop: a fix agent is dispatched against the SPECIFIC
//    guarded task(s) the validator named, then the validator re-runs. Up to
//    MAX_FIX_ATTEMPTS times before the run stops and reports the phase as
//    blocked (matches tasks.md's "On FAIL: reopen, phase does not start").

const MAX_PARALLEL = 4
const MAX_FIX_ATTEMPTS = 5

const state = {}           // id -> 'pending' | 'running' | 'done' | 'error'
const results = {}         // id -> agent() return value (final report text)
const fixAttempts = {}     // id -> count, for validators
for (const id of Object.keys(NODES)) state[id] = 'pending'

function isReady(id) {
  const node = NODES[id]
  return state[id] === 'pending' && node.deps.every((d) => state[d] === 'done')
}

function filesInFlight() {
  const set = new Set()
  for (const [id, s] of Object.entries(state)) {
    if (s === 'running') {
      for (const f of NODES[id].files || []) set.add(f)
    }
  }
  return set
}

function collidesWithRunning(id) {
  const inFlight = filesInFlight()
  return (NODES[id].files || []).some((f) => inFlight.has(f))
}

async function runNode(id) {
  const node = NODES[id]
  state[id] = 'running'
  log(`-> ${id} [${node.model}] (${node.phase}) starting`)

  const label = node.kind === 'validator' ? `validate:${id}` : `task:${id}`
  const report = await agent(node.prompt, {
    label,
    phase: node.phase,
    model: node.model,
  })

  if (node.kind === 'task') {
    state[id] = report ? 'done' : 'error'
    results[id] = report
    log(`${state[id] === 'done' ? 'OK' : 'FAILED'} ${id}`)
    return
  }

  // Validator: parse PASS/FAIL out of its own report text (it's instructed
  // to state this explicitly). On FAIL, dispatch a bounded fix loop against
  // exactly the guarded tasks it names, then re-run the validator itself.
  fixAttempts[id] = fixAttempts[id] || 0
  const text = String(report || '')
  const passed = /\bPASS\b/i.test(text) && !/\bFAIL\b/i.test(text.split('\n')[0] || '')
  const explicitFail = /\bFAIL\b/i.test(text)

  if (passed && !explicitFail) {
    state[id] = 'done'
    results[id] = report
    log(`VALIDATOR PASS ${id}`)
    return
  }

  log(`VALIDATOR FAIL ${id} (attempt ${fixAttempts[id] + 1}/${MAX_FIX_ATTEMPTS + 1})`)
  if (fixAttempts[id] >= MAX_FIX_ATTEMPTS) {
    state[id] = 'error'
    results[id] = report
    log(`VALIDATOR ${id} EXHAUSTED FIX ATTEMPTS - PHASE BLOCKED`)
    return
  }
  fixAttempts[id]++

  // Attempts 1-2: a normal fix-agent (opus). Attempt 3+: two prior opus fix
  // attempts already failed this same validator, so escalate to technical-lead
  // (opus) instead of trying a third variation of the same guess - per the
  // Opus escalation exception in ~/.claude/CLAUDE.md.
  const escalate = fixAttempts[id] > 2
  const priorAttempts = Object.keys(results)
    .filter((k) => k.startsWith(`${id}-fix-`))
    .map((k) => `--- Prior attempt ${k.split('-fix-')[1]} ---\n${results[k]}`)
    .join('\n\n')

  const fixReport = await agent(
    (escalate
      ? `ESCALATION: two prior fix attempts already failed to clear this validator. Do not just try a ` +
        `third variation of the same guess - diagnose why the prior attempts didn't work first.\n\n` +
        `Prior fix attempts and their own reports:\n${priorAttempts}\n\n`
      : '') +
    `A validator for spec 014 (conditional gates) reported FAIL against tasks it guards: ${node.guards.join(', ')}.\n\n` +
    `Validator's full report:\n${text}\n\n` +
    `Read the validator's report carefully, identify EXACTLY which guarded task's work is deficient and why, ` +
    `then fix ONLY that specific problem in the codebase. Do not re-do unrelated work. ` +
    `Do not touch tasks not named as the cause of the failure. Report exactly what you changed and why it addresses the validator's specific complaint.`,
    escalate
      ? { label: `escalate:${id}`, phase: node.phase, model: 'opus', agentType: 'technical-lead' }
      : { label: `fix:${id}`, phase: node.phase, model: 'opus' }
  )
  results[`${id}-fix-${fixAttempts[id]}`] = fixReport

  // Re-run the validator itself (recursive - state stays 'running' as this
  // node hasn't resolved; the retry re-enters this same function call).
  await runNode(id)
}

async function scheduler() {
  const active = new Map() // id -> promise

  while (true) {
    const remaining = Object.keys(NODES).filter((id) => state[id] !== 'done' && state[id] !== 'error')
    if (remaining.length === 0) break

    // Deadlock check: nothing running and nothing ready means the graph is stuck
    // (should never happen if NODES is correctly derived from tasks.md, but a
    // real scheduler must not spin forever on a bad graph).
    const anyRunning = active.size > 0
    const anyReady = remaining.some((id) => isReady(id) && !collidesWithRunning(id))
    if (!anyRunning && !anyReady) {
      const stuck = remaining.filter((id) => state[id] === 'pending')
      log(`DEADLOCK: ${stuck.length} task(s) can never become ready: ${stuck.join(', ')}`)
      break
    }

    // Fill available slots with ready, file-collision-free nodes.
    while (active.size < MAX_PARALLEL) {
      const next = Object.keys(NODES).find(
        (id) => isReady(id) && !collidesWithRunning(id) && !active.has(id)
      )
      if (!next) break
      const p = runNode(next).then(() => { active.delete(next) })
      active.set(next, p)
    }

    if (active.size === 0) {
      // Nothing ready and nothing running - but remaining tasks exist and
      // weren't caught by the deadlock check above (e.g. all remaining are
      // blocked purely on file collisions with each other, transiently).
      // This shouldn't happen given MAX_PARALLEL >= 1, but guard anyway.
      break
    }

    // Wait for at least one active task to finish before re-scanning.
    await Promise.race(active.values())
  }

  // Drain any still-active promises.
  await Promise.all(active.values())
}

phase('Phase 1 - Compiler')
phase('Phase 2 - ExecutionContext')
phase('Phase 3 - Dispatch loop')
phase('Phase 4 - Cross-workflow triggering')
phase('Phase 5 - Frontend')

await scheduler()

const done = Object.keys(NODES).filter((id) => state[id] === 'done')
const errored = Object.keys(NODES).filter((id) => state[id] === 'error')

log(`Finished: ${done.length}/${Object.keys(NODES).length} done, ${errored.length} error(s)`)
if (errored.length) {
  log(`Blocked/failed nodes: ${errored.join(', ')} - see their reports for what to fix.`)
}

return {
  done,
  errored,
  results,
  summary: `${done.length}/${Object.keys(NODES).length} nodes done (tasks + validators). ` +
    (errored.length ? `Blocked at: ${errored.join(', ')}.` : 'All phases passed their validators.'),
}
