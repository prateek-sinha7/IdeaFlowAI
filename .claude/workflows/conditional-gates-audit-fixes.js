export const meta = {
  name: 'conditional-gates-audit-fixes',
  description: 'Fix the 6 gaps an independent audit found in spec 014 (conditional gates): R-19 test coverage, R-20 divert step-id linkage, R-24 workflow picker, R-22 external-pipeline card, R-23 canvas route-edge rendering + connect gesture, and a final AC-07 re-verification.',
  phases: [
    { title: 'R-19 Test Coverage', detail: 'T39 + V7' },
    { title: 'R-20 Divert Step Linkage', detail: 'T40-T42 + V8' },
    { title: 'R-24 Workflow Picker', detail: 'T43 + V9' },
    { title: 'R-22 External Pipeline Card', detail: 'T44 + V10' },
    { title: 'R-23 Canvas Route Edges', detail: 'T45-T46 + V11' },
    { title: 'AC-07 Final Verification', detail: 'V12' },
  ],
}

const REPO_NOTES = `
Repo: /Users/bilala/Developer/Projects/VELOCITY-AI (Flowin / VELOCITY-AI). Branch: feat/conditional-gates.

GIT: Never run any git command (no commit, no push, no stash, no checkout, nothing). The user
handles ALL git operations themselves. Leave every change in the working tree for review.

SCOPE DISCIPLINE: Touch ONLY the file(s) your task names. Don't "improve" adjacent code, don't
refactor things that aren't broken, don't add speculative abstractions or config that wasn't
asked for. If you notice unrelated dead code or a second bug while working, mention it in your
summary — do not fix it in this task.

BACKEND — engine.py is the busiest, most load-bearing file in this runtime (per backend/CLAUDE.md
and this spec's own Phase 3 precedent: "engine.py is described in this repo's own CLAUDE.md as
the busiest, most load-bearing file in the runtime... the risk is in the FILE, not the diff
size"). Any task touching it must be surgical and must re-run the relevant tests after editing,
not just before.

BACKEND test commands (python3.11, no venv):
  cd backend && python3.11 -m pytest tests/unit/ -v
  cd backend && python3.11 -m pytest tests/agents/ -v
  cd backend && python3.11 -m pytest <specific file> -v

FRONTEND test commands:
  cd frontend && npx vitest run <path>
  cd frontend && npx tsc --noEmit

Backend commit-convention scopes exist (feat/fix/chore/test/docs + engine/runner/tools/etc
scope) but are IRRELEVANT here since nothing gets committed by any task.

Every task must actually run the verification commands its own AC lines specify — self-check
honestly, and say so plainly in your summary if a check could not be run (e.g. no display
available, a fetch needed a live backend) rather than claiming an untested thing passed.

This is a continuation of spec 014's tasks.md numbering (T1-T38, V1-V6 already done — see
specs/014-conditional-gates/tasks.md and specs/014-conditional-gates/spec.md for the full
requirements/AC text if you want more context than your own task prompt gives you). New task
ids here (T39-T46, V7-V12) continue that numbering; do not renumber or touch the original file.
`.trim()

const TASK_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    taskId: { type: 'string' },
    status: { type: 'string', enum: ['done', 'blocked'] },
    filesChanged: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    acSelfCheck: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          criterion: { type: 'string' },
          met: { type: 'boolean' },
          note: { type: 'string' },
        },
        required: ['criterion', 'met'],
      },
    },
    blockers: { type: 'string' },
  },
  required: ['taskId', 'status', 'filesChanged', 'summary', 'acSelfCheck'],
}

const VALIDATOR_RESULT_SCHEMA = {
  type: 'object',
  properties: {
    validatorId: { type: 'string' },
    pass: { type: 'boolean' },
    checks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          criterion: { type: 'string' },
          result: { type: 'string', enum: ['pass', 'fail'] },
          evidence: { type: 'string' },
        },
        required: ['criterion', 'result', 'evidence'],
      },
    },
    failedTasks: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['validatorId', 'pass', 'checks', 'failedTasks', 'summary'],
}

// ---------------------------------------------------------------------------
// NODES — one entry per task/validator. See specs/014-conditional-gates/spec.md
// for R-19/R-20/R-22/R-23/R-24/AC-07's exact requirement text.
// ---------------------------------------------------------------------------

const NODES = {
  // ---- R-19 test coverage (standalone, trivial) ----------------------------
  T39: {
    kind: 'task',
    agentType: 'junior-engineer',
    phase: 'R-19 Test Coverage',
    deps: [],
    files: ['backend/tests/unit/test_conditional_route_compiler.py'],
    file: 'backend/tests/unit/test_conditional_route_compiler.py (NEW FILE)',
    traces: 'R-19-clarified (spec.md) — audit finding "R-19-clarified-test-coverage"',
    desc: `An independent audit of spec 014 found: "the compiler-side rejection of a declared
trigger_max_depth != 5 (R-19-clarified's exact-equality clause) IS implemented correctly
(compiler.py ~lines 1171-1174, \`if trigger_max_depth != 5: raise ...\`), but it is the one
Phase-1 route-validation negative case with NO test file anywhere in backend/tests/ asserting
it... a future edit that weakens or removes the != 5 check would go completely undetected by
the test suite, even though today's behavior is correct."

R-19 (spec.md §4.3, clarified 2026-08-20): "trigger_max_depth is FIXED at 5 in v1 — the system
ceiling equals the default, so it is not a tunable range... the compiler REJECTS any
manifest-declared trigger_max_depth value other than 5 in v1."

Write a NEW test file backend/tests/unit/test_conditional_route_compiler.py:
1. A negative-case test: compile a workflow manifest (you can build one as a plain dict matching
   workflow.yaml's schema, or adapt one of the checked-in
   backend/agents/workflows/sample_conditional_*/workflow.yaml fixtures) whose route block
   declares trigger_max_depth: 6 (or any value other than 5) via WorkflowCompiler().compile(...),
   and assert this raises CompilerError with a message referencing trigger_max_depth.
2. A positive-case test, for contrast: the same manifest with trigger_max_depth: 5 (or omitted,
   relying on the default) compiles without error.
Before writing, check backend/tests/unit/ for any existing compiler test file (e.g. a
test_compiler.py or similar) and match its fixture-construction / import style if one exists,
rather than inventing a new convention.`,
    ac: [
      'New test file exists at backend/tests/unit/test_conditional_route_compiler.py',
      'A test asserts CompilerError is raised when a route declares trigger_max_depth != 5',
      'A test asserts compilation succeeds when trigger_max_depth is 5 or omitted',
      'cd backend && python3.11 -m pytest tests/unit/test_conditional_route_compiler.py -v passes',
      'No existing test file or production code was modified — this task only ADDS a new test file',
    ],
  },
  V7: {
    kind: 'validator',
    agentType: 'qa-engineer',
    phase: 'R-19 Test Coverage',
    deps: ['T39'],
    guards: ['T39'],
    criteria: [
      'backend/tests/unit/test_conditional_route_compiler.py exists and its test(s) genuinely exercise WorkflowCompiler with an explicit trigger_max_depth != 5 and assert CompilerError is raised',
      'A positive-case test confirms trigger_max_depth: 5 (or omitted) still compiles',
      'Running `cd backend && python3.11 -m pytest tests/unit/test_conditional_route_compiler.py -v` shows the new test(s) passing, by actually running it yourself',
      'No pre-existing test or production file was modified by T39',
    ],
  },

  // ---- R-20 divert step-id linkage (standalone) -----------------------------
  T40: {
    kind: 'task',
    agentType: 'junior-engineer',
    phase: 'R-20 Divert Step Linkage',
    deps: [],
    files: ['backend/app/models/workflow.py', 'backend/alembic/versions/'],
    file: 'backend/app/models/workflow.py + a new file under backend/alembic/versions/',
    traces: 'R-20 (spec.md) — audit finding on R-20',
    desc: `An independent audit of spec 014 found: "the requirement's exact reciprocal text is
'← Continued from {parent run}, step {step_id}' and the ', step {step_id}' clause can never
render: RevisionFamilyView.tsx documents that no backend field carries a step id ('T29 does not
write a step-id column; T32's pipeline_diverted payload does not carry one either')... this is a
genuine backend-plus-frontend gap."

This task is the backend schema half of the fix. Two parts, same unit of work:

1. In backend/app/models/workflow.py, add a new NULLABLE column to the \`WorkflowRun\` model:
   \`diverted_at_step_id\` (string, nullable, no default). Read the neighboring column
   declarations (e.g. \`parent_run_id\`) FIRST and match this file's exact declaration style
   (Mapped[...] type-annotation convention, Column(...) args, etc.) rather than guessing.

2. Write a new Alembic migration under backend/alembic/versions/ adding this column to the
   \`workflow_runs\` table. As of this writing the latest migration is
   0032_collapse_od_prototype_label.py — CONFIRM this is still true by listing
   backend/alembic/versions/ yourself before picking your revision number (do not assume 0033 is
   still free without checking; use the next sequential number after whatever the actual latest
   is). Match 0032's exact structural conventions: revision/down_revision variables, a docstring
   explaining WHY (quote this task's own reasoning — R-20's card text needs a step id and none
   exists today), and a working, reversible downgrade() that drops the column. This is a pure
   schema-add (op.add_column/op.drop_column) — no data migration/backfill needed, since existing
   diverted rows simply get NULL (the frontend already has, and after T42 will keep, a documented
   fallback for a null step id).

This column will be POPULATED by a later task (T41, not this one) — this task only adds the
column and the model field.`,
    ac: [
      'WorkflowRun model in backend/app/models/workflow.py has a new nullable diverted_at_step_id column, matching this file\'s existing column-declaration style exactly',
      'A new Alembic migration file exists under backend/alembic/versions/, using the correct next sequential revision number (verified by actually listing the directory, not assumed), with down_revision pointing at the true current head, adding the column with a working downgrade',
      'The migration runs clean (e.g. `cd backend && alembic upgrade head` against a scratch/test DB, or the project\'s existing migration test if one exists) with no errors',
      'No other column, table, or model is touched',
    ],
  },
  T41: {
    kind: 'task',
    agentType: 'senior-engineer',
    phase: 'R-20 Divert Step Linkage',
    deps: ['T40'],
    files: ['backend/agents/execution_engine/engine.py', 'backend/app/api/runs.py'],
    file: 'backend/agents/execution_engine/engine.py + backend/app/api/runs.py',
    traces: 'R-20, R-28 (spec.md) — audit finding on R-20',
    desc: `Continues T40 (which added WorkflowRun.diverted_at_step_id, nullable, unpopulated).
This task populates it and exposes it via the API. Two parts:

1. In backend/agents/execution_engine/engine.py, find the trigger:"workflow" divert arm (search
   for \`self._state_machine.transition(pipeline_run_id, "diverted")\` — as of this writing at
   approximately line 2990, inside the \`elif _route_trigger == "workflow":\` block spanning
   roughly lines 2974-3009). The \`step\` variable already in scope at that point (used a few
   lines earlier in \`ectx.runner.run_trigger_workflow(step, ectx, workflow_ref=_route_target)\`)
   is the step whose conditional gate fired this divert — its \`instance_id\` is what
   diverted_at_step_id should be set to, on the SAME WorkflowRun row (pipeline_run_id) being
   transitioned to "diverted".

   IMPORTANT: \`state_machine.transition(run_id, new_state)\` only accepts those two arguments —
   do NOT change its signature or add a third parameter to it. Instead, read
   backend/agents/execution_engine/state_machine.py's own \`_persist\` method AND grep engine.py
   for any OTHER existing example of a direct, small WorkflowRun column write from within this
   function (a plain ORM attribute-set + commit, or a direct SQL UPDATE) — match whatever pattern
   this codebase already uses for that, applied as one additional small write immediately before
   or after the transition() call. Do not invent a new DB-access pattern if an existing one
   already fits this shape.

2. In backend/app/api/runs.py, add \`diverted_at_step_id: Optional[str] = None\` to BOTH
   \`WorkflowRunResponse\` (~line 88) and \`WorkflowRunListResponse\` (~line 145). Because
   \`_run_response\`/\`_run_list_response\` (~line 272) already materialize every field via
   \`WorkflowRunResponse.model_fields\`/\`WorkflowRunListResponse.model_fields\` + getattr, no
   other code in this file needs to change for the new field to flow through both the
   single-run GET and the list GET automatically.

Also: check whether tests/agents/test_conditional_divert_v4_validation.py (V4's existing
end-to-end divert test) is the natural place to add a regression assertion that a diverted run's
diverted_at_step_id is set correctly — if so, extend it there rather than writing a new file.`,
    ac: [
      "engine.py's trigger:workflow divert arm persists the firing step's instance_id into WorkflowRun.diverted_at_step_id on the diverting run's own row, using this codebase's existing DB-write pattern (not a newly-invented one)",
      "state_machine.py's transition() function signature is completely unchanged",
      'WorkflowRunResponse and WorkflowRunListResponse both expose diverted_at_step_id',
      "A test (extending tests/agents/test_conditional_divert_v4_validation.py if it's the natural home, else a small new one) confirms a diverted run's GET response returns a non-null diverted_at_step_id matching the actual step that fired the trigger",
      'cd backend && python3.11 -m pytest tests/agents/test_conditional_divert_v4_validation.py tests/unit/test_execution_engine.py -v passes',
    ],
  },
  T42: {
    kind: 'task',
    agentType: 'senior-engineer',
    phase: 'R-20 Divert Step Linkage',
    deps: ['T41'],
    files: [
      'frontend/src/components/history/RevisionFamilyView.tsx',
      'frontend/src/components/history/WorkflowHistory.divertLinks.test.tsx',
    ],
    file: 'frontend/src/components/history/RevisionFamilyView.tsx + its test file',
    traces: 'R-20 (spec.md) — audit finding on R-20',
    desc: `Completes R-20. RevisionFamilyView.tsx (~lines 190-198) currently documents, in a
comment, that no step id is available anywhere and (~lines 422-423) its DivertBadge only appends
", step \${link.stepId}" when link.stepId is truthy — which was structurally never true before
T40/T41. GET /api/runs (both single-run and list) now returns \`diverted_at_step_id\` (T41).

1. Update \`buildDivertLinks()\` (~lines 201-211) to read \`diverted_at_step_id\` off each run row
   and set \`link.stepId\` from it. Confirm (read the function) that both the historical
   (page-load, purely from persisted run rows) and live (SSE-refetch-driven) paths already flow
   through this same function on the same underlying run-list data — if so, this one change
   covers both per the file's own existing single-data-source design; if you find they don't
   actually share that path, say so precisely in your summary rather than assuming.
2. Remove or correct the now-stale comment at ~lines 190-198 explaining why no step id exists —
   it now can.
3. Update frontend/src/components/history/WorkflowHistory.divertLinks.test.tsx: the existing
   assertion (~line 173) \`expect(continuedBadge.textContent).toBe("← Continued from Run A")\`
   currently asserts the OMITTED form. Add a \`diverted_at_step_id\` value to that test's mock run
   fixture and change the assertion to expect the INCLUDED form
   ("← Continued from Run A, step {that value}"). Keep (or add, if not already present) a
   separate case confirming the omitted form still renders correctly for a run whose
   diverted_at_step_id is genuinely null (e.g. a pre-migration historical row) — do not remove
   that fallback coverage, only stop asserting it as the ONLY behavior.`,
    ac: [
      "buildDivertLinks() populates link.stepId from the run's diverted_at_step_id field",
      "DivertBadge renders '← Continued from {parent}, step {step_id}' when the field is present, and the omitted form when it's genuinely null",
      'WorkflowHistory.divertLinks.test.tsx asserts the included form given a fixture with diverted_at_step_id set, AND still covers the omitted-form case for a null value',
      'cd frontend && npx vitest run src/components/history/WorkflowHistory.divertLinks.test.tsx passes',
      'The stale comment explaining why no step id exists is removed or corrected',
    ],
  },
  V8: {
    kind: 'validator',
    agentType: 'qa-engineer',
    phase: 'R-20 Divert Step Linkage',
    deps: ['T40', 'T41', 'T42'],
    guards: ['T40', 'T41', 'T42'],
    context:
      'R-20 (spec.md §4.4): "A diverted run\'s card in run history/\\"My Runs\\" shows a distinct terminal treatment (\\"Diverted to {workflow_id} →\\") linking to the triggered run\'s card. The triggered run\'s card shows a reciprocal link (\\"← Continued from {parent run}, step {step_id}\\")." The audit found the step-id clause could never render because no backend field carried it — T40/T41/T42 exist to fix exactly that.',
    criteria: [
      'WorkflowRun model + the new migration add a working, reversible diverted_at_step_id column (inspect the migration file and, if feasible, actually run it against a scratch DB)',
      "engine.py's divert arm persists the correct firing step's instance_id into that column — verified by reading the code AND by running T41's test(s)",
      'GET /api/runs/{id} and GET /api/runs (list) both expose diverted_at_step_id in their response schemas',
      "RevisionFamilyView.tsx's DivertBadge renders the full '..., step {step_id}' text when present — verified by actually running `cd frontend && npx vitest run src/components/history/WorkflowHistory.divertLinks.test.tsx` and confirming it is green",
      'The omitted-form fallback for a null diverted_at_step_id still works and is still tested',
      "state_machine.py's transition() signature was not changed",
    ],
  },

  // ---- R-24 workflow picker (standalone, R-22 depends on it) ---------------
  T43: {
    kind: 'task',
    agentType: 'senior-engineer',
    phase: 'R-24 Workflow Picker',
    deps: [],
    files: ['frontend/src/components/workflow/composer/CanvasNode.tsx'],
    file: 'frontend/src/components/workflow/composer/CanvasNode.tsx',
    traces: 'R-24 (spec.md)',
    desc: `An independent audit of spec 014 found: "No picker of any kind exists for selecting a
trigger:'workflow' target — neither a reuse of the existing 'My Workflows' list component nor a
new purpose-built one... What actually exists (CanvasNode.tsx ~lines 433-439) is a bare
<input aria-label=\\"Target\\"> free-text field shared with the step-outcome case... the author
must manually know/type/paste a raw workflow id with zero validation, browsing, or autocomplete."

R-24 (spec.md §4.5): "The external-pipeline picker (for selecting a trigger: workflow target)
reuses the existing 'My Workflows' list component as its data source — no new
filtered/purpose-built picker."

The canonical reusable data source is \`userWorkflowsApi.list()\` in
frontend/src/store/api/userWorkflows.ts (~lines 433-436) — calls \`GET /api/user-workflows\`,
returns \`UserWorkflowSummary[]\`. (SavedWorkflowsPage.tsx lists "My Workflows" from the same
endpoint via its own page-level \`getUserWorkflows(jwt)\` helper — reuse \`userWorkflowsApi.list()\`
instead, since CanvasNode.tsx already lives in the composer's own module tree and this is the
natural fit there, not SavedWorkflowsPage's page-level helper.)

In CanvasNode.tsx's route-target editor (~lines 424-439): when \`outcome.trigger === "workflow"\`,
replace the bare \`<input aria-label="Target">\` (currently shared with the step-target case) with
a real picker (a \`<select>\` or a lightweight searchable combobox — match this file's existing
form-control styling) populated from \`userWorkflowsApi.list()\`, showing each workflow's display
name and storing its id as \`outcome.target\` on selection. Keep the literal value \`"self"\`
available as a distinct, always-present option (R-12: \`target: "self"\` is valid and means "a
fresh instance of this same workflow definition"). Fetch the list ONCE (memoized/cached — do not
re-fetch per outcome row if a node has multiple workflow-trigger outcomes) and degrade gracefully
on a fetch failure (don't block or crash the rest of the form — fall back to allowing free-text
entry with a visible warning so an author is never fully stuck by a network hiccup). Do NOT touch
the \`trigger === "step"\` case's target input — this task is scoped only to the workflow-target
case.`,
    ac: [
      "Selecting a trigger:workflow outcome's target now uses a real picker populated from userWorkflowsApi.list() (GET /api/user-workflows), not a bare free-text input",
      "'self' remains selectable as a distinct, always-present option",
      "The trigger:step case's target input is completely unchanged",
      'A fetch failure degrades gracefully (does not crash the editor or block other fields)',
      'The list is fetched once/memoized, not re-fetched per outcome row',
      'cd frontend && npx tsc --noEmit shows no new errors in this file',
    ],
  },
  V9: {
    kind: 'validator',
    agentType: 'qa-engineer',
    phase: 'R-24 Workflow Picker',
    deps: ['T43'],
    guards: ['T43'],
    criteria: [
      "A trigger:workflow outcome's Target field is a real picker sourced from userWorkflowsApi.list() (GET /api/user-workflows), not a bare text box — confirmed by reading the code directly",
      "'self' is still selectable as a distinct option",
      'trigger:step outcomes are completely unaffected by this change',
      'The workflow list is fetched once/memoized, not per-row, and a fetch failure does not crash the form',
      'cd frontend && npx tsc --noEmit is clean for CanvasNode.tsx',
    ],
  },

  // ---- R-22 external pipeline card (depends on R-24's picker) --------------
  T44: {
    kind: 'task',
    agentType: 'senior-engineer',
    phase: 'R-22 External Pipeline Card',
    deps: ['T43', 'V9'],
    files: ['frontend/src/components/workflow/composer/CanvasNode.tsx'],
    file: 'frontend/src/components/workflow/composer/CanvasNode.tsx',
    traces: 'R-22 (spec.md)',
    desc: `An independent audit of spec 014 found: "[ExternalPipelineCard] does not satisfy the
requirement's own description of that card: it is a static, non-interactive <div> with no
onClick/href/launch affordance at all (no 'link/launch affordance'), and its label is simply
workflowId.trim() — the raw string typed into the free-text Target input — not a resolved
'target workflow's name' (there is no lookup against any workflow list to resolve id→name). This
gap is a direct consequence of R-24 being missing (no picker to select from, so nothing ever
supplies a display name)."

R-22 (spec.md §4.5): "...an external-pipeline reference card, for trigger: workflow outcomes,
visually distinct from an agent card, showing the target workflow's name with a link/launch
affordance."

T43 (already done — verify by reading its diff) added a real picker sourced from
\`userWorkflowsApi.list()\`. \`ExternalPipelineCard\` (~lines 41-57) currently only receives
\`workflowId\` and renders it raw. Now:

1. Thread the same fetched workflow list (or a small derived id→name lookup map, built once and
   reused, not fetched per card) into \`ExternalPipelineCard\` so it renders the RESOLVED display
   name instead of the raw id. Provide a clear, distinct fallback rendering (e.g. muted/italic
   style) for: the literal \`"self"\` value, and any id that isn't found in the list (not yet
   loaded, or genuinely unresolvable) — never silently show a blank or a confusing raw id with no
   visual distinction from a resolved name.
2. Add a click/launch affordance: clicking the card opens/navigates to that workflow. Check
   ComposerPage.tsx and/or SavedWorkflowsPage.tsx for this app's EXISTING navigation pattern for
   opening a saved workflow (e.g. a router.push to its edit route, or a new-tab open) and reuse it
   exactly — do not invent a new navigation mechanism. Do not add this affordance for the "self"
   case if that would navigate to a confusing or nonsensical destination — use your judgment and
   state your reasoning in your summary if you choose to disable/change the affordance for "self".`,
    ac: [
      'ExternalPipelineCard shows the resolved workflow display name (not the raw id) whenever the id resolves against the fetched user-workflows list',
      "A clear, visually distinct fallback exists for 'self' and for an unresolved/not-yet-loaded id",
      "Clicking the card navigates to/opens that workflow, using this app's existing navigation pattern for opening a saved workflow (not a newly invented one)",
      'cd frontend && npx tsc --noEmit shows no new errors in this file',
    ],
  },
  V10: {
    kind: 'validator',
    agentType: 'qa-engineer',
    phase: 'R-22 External Pipeline Card',
    deps: ['T44', 'V9'],
    guards: ['T44'],
    criteria: [
      'ExternalPipelineCard displays a resolved workflow display name, not a raw id, for any id present in the user-workflows list',
      "A sane, visually distinct fallback exists for 'self' and for unresolved/not-yet-loaded ids",
      'The card is genuinely clickable/interactive and opens the target workflow via this app\'s existing navigation pattern — confirmed by reading the click handler and the pattern it reuses',
      'cd frontend && npx tsc --noEmit is clean for CanvasNode.tsx',
    ],
  },

  // ---- R-23 canvas route-edge rendering + connect gesture (the big one) ----
  T45: {
    kind: 'task',
    agentType: 'senior-engineer',
    phase: 'R-23 Canvas Route Edges',
    deps: [],
    files: ['frontend/src/components/workflow/composer/CanvasView.tsx'],
    file: 'frontend/src/components/workflow/composer/CanvasView.tsx',
    traces: 'R-23 (spec.md) — the largest single frontend item in this spec (RISK-05)',
    desc: `An independent audit of spec 014 found: "confirmed by full read of CanvasView.tsx
(1361 lines) and CanvasNode.tsx (552 lines). No connect-to-existing-node gesture for routing
exists anywhere... chainEdges (line 682) and treeEdges (line 698) are still pure array-order/tree
layout... neither has any awareness of agent.route/outcomes at all... Consequently there is ZERO
visual representation of ANY conditional-gate outcome on the canvas today — not just missing
curves for the loop case specifically, but no edge (straight OR curved) is ever drawn for a
forward step-outcome, backward step-outcome, or workflow-trigger outcome."

R-23 (spec.md §4.5): "CanvasView.tsx gains a connect-to-existing-node gesture (distinct from the
current drag-reparent, which explicitly rejects a target that is an ancestor via isDescendant) —
a conditional-gate outcome edge MUST be able to target an ancestor (the loop case) while a plain
reparent still cannot. Loop-back edges render as curves around the row rather than as a downward
tree branch."

This was explicitly flagged in the original tasks.md as needing its own scoping pass before
implementation (RISK-05, "the single largest frontend item in this spec") — this task IS that
scoping pass plus its first half (rendering; T46 is the second half, the drag gesture).

SCOPE DECISION for this task (made deliberately to keep this achievable rather than open-ended):
do NOT replace or restructure the EXISTING node x/y positioning that chainEdges/treeEdges'
underlying layoutChildren/treeLayout.ts already compute — leave that positioning untouched. This
task is an ADDITIVE new edge layer on top of the existing, unchanged node positions:

For every agent whose \`gates\` includes "conditional" and whose \`route.outcomes\` is non-empty:
- For each outcome with \`trigger === "step"\`: resolve the target step by instance_id and render
  one new edge from the source agent's node position to the target's node position.
  - FORWARD target (later in the existing tree/array order): render similarly to how treeEdges
    already draws a parent-child edge (reuse this file's existing edge-geometry/styling
    conventions for consistency), but in a visually distinct color/style marking it as a "route"
    edge, not a structural edge.
  - BACKWARD/ancestor target (the loop case — this is what R-23 calls out by name): render a
    clearly curved path (an SVG arc/bezier that visibly bulges out to the side of the row rather
    than cutting straight up through intervening nodes), distinct in styling from both structural
    edges and forward-route edges. If multiple loop-back edges would overlap at the same offset,
    stagger their curve radius/offset per edge index — a simple per-index increment is sufficient,
    you do not need a general many-edge-collision algorithm; note in your report if you hit a case
    that needs more than that.
- For \`trigger === "workflow"\` outcomes: do NOT render a duplicate in-canvas edge —
  ExternalPipelineCard (T36, already shipped) already represents that case inline on the node
  itself.

This task is RENDERING ONLY, given route.outcomes data that authors can already set via T43's
CanvasNode editor (with no visual feedback until this task lands). It explicitly does NOT include
the connect-to-existing-node DRAG GESTURE — that is T46, which depends on this task.

If you discover mid-implementation that this additive-layer approach is genuinely insufficient
(e.g. positions truly must move for legibility), STOP and report precisely why rather than
silently attempting a full layout-engine replacement or adding a new charting/graph-layout npm
dependency — mirrors this spec's own T35 precedent: "if implementing this task surfaces a hard
dependency on the layout work that can't be avoided, stop and report rather than expanding scope
silently."`,
    ac: [
      'Every step with gates:[conditional] and a non-empty route.outcomes now renders a visible edge to each trigger:step outcome\'s target',
      'A backward/ancestor target renders as a visually distinct curved path, not a straight downward tree branch',
      'A forward target renders distinctly from both structural edges and backward route edges',
      'trigger:workflow outcomes do NOT get a duplicate in-canvas edge (ExternalPipelineCard already represents them)',
      'No existing structural chainEdges/treeEdges rendering or the underlying node x/y layout was altered',
      'cd frontend && npx tsc --noEmit shows no new errors in this file',
      "Reasoned-through (or, if feasible, snapshot-tested) confirmation that ex_A1_loop's loop (check -> greet) and ex_A2_branch's forward branch (pick -> say-hello / say-hola) both render a visible, correctly-shaped edge when their manifests are loaded into the composer",
    ],
  },
  T46: {
    kind: 'task',
    agentType: 'senior-engineer',
    phase: 'R-23 Canvas Route Edges',
    deps: ['T45'],
    files: ['frontend/src/components/workflow/composer/CanvasView.tsx'],
    file: 'frontend/src/components/workflow/composer/CanvasView.tsx',
    traces: 'R-23 (spec.md)',
    desc: `Second half of R-23 (T45 is rendering; this is the gesture). R-23's exact text:
"CanvasView.tsx gains a connect-to-existing-node gesture (distinct from the current drag-reparent,
which explicitly rejects a target that is an ancestor via isDescendant) — a conditional-gate
outcome edge MUST be able to target an ancestor (the loop case) while a plain reparent still
cannot."

The existing gesture is \`handlePortMouseDown\`/\`reparentDrag\` (~lines 600-667), gated by
\`isDescendant\` (~line 646). That check MUST stay completely unchanged for its existing
structural-reparent purpose — R-23 asks for a NEW, second, additional gesture, not a modification
of the first.

Add a new port/handle affordance that appears ONLY on a node whose \`gates\` includes "conditional"
(visually distinct from the existing structural drag-port — different color/shape, positioned so
it can't be confused with or accidentally trigger the existing one). Dragging FROM this new handle
and releasing over any other node — INCLUDING an ancestor, with NO isDescendant-style rejection
for this specific gesture — should:
(a) if the source node has exactly one outcome with an empty/placeholder target, set that
    outcome's target to the dropped-on node's instance_id;
(b) if it has multiple outcomes or none, surface a small inline picker/prompt (reuse this file's
    or CanvasNode's existing compact-UI conventions — do not build a new heavy modal system)
    letting the author pick which outcome the new edge sets, or create a new outcome.

While dragging, show a live preview line/curve — reuse the existing \`reparentDrag\` preview-line
rendering pattern (~lines 1042-1051) for visual consistency, styled per T45's route-edge styling.

On drop, call the SAME \`updateRoute\`/\`updateOutcome\` mechanism CanvasNode.tsx's T43 route editor
already uses — locate it and reuse it (lift/share it if it's currently private to CanvasNode.tsx)
so the resulting route data is identical in shape to what an author gets from typing directly into
the form. Do NOT duplicate route-mutation logic in two places. If this genuinely needs much larger
state-sharing surgery than expected, STOP and report rather than silently duplicating that logic.`,
    ac: [
      'A new, visually distinct drag gesture exists for creating/redirecting a route outcome\'s target, completely separate from the existing structural reparent gesture',
      'This new gesture can successfully target an ancestor node (the loop case) — isDescendant is NOT applied to it',
      'The existing structural reparent gesture and its isDescendant ancestor-rejection are completely unchanged',
      "Dropping on a target correctly updates the source step's route.outcomes via the SAME update mechanism T43's form editor uses — no duplicated/divergent state-mutation logic",
      "A live preview line/curve is shown during the drag, styled consistently with T45's static route-edge rendering",
      'cd frontend && npx tsc --noEmit shows no new errors in this file',
    ],
  },
  V11: {
    kind: 'validator',
    agentType: 'qa-engineer',
    phase: 'R-23 Canvas Route Edges',
    deps: ['T45', 'T46'],
    guards: ['T45', 'T46'],
    context:
      'R-23 is the highest-judgment, highest-risk item in this whole workflow (flagged RISK-05 in the original spec as "the single largest frontend item"). Be thorough — re-read the whole file, not just the diff.',
    criteria: [
      'Route-outcome edges (forward and backward/loop) are genuinely rendered and visually distinguishable from structural edges and from each other',
      'A working connect-to-existing-node gesture exists and can successfully target an ancestor node, without touching the existing structural-reparent isDescendant behavior',
      "The new gesture's drop action produces route data identical in shape/behavior to what T43's form editor produces — no divergent/duplicated mutation logic",
      'cd frontend && npx tsc --noEmit is clean for CanvasView.tsx',
      'Re-read CanvasView.tsx in full one more time (not just the diff) to confirm no existing structural drag-reparent behavior regressed',
    ],
  },

  // ---- AC-07 final re-verification (derived, no new implementation) -------
  V12: {
    kind: 'validator',
    agentType: 'qa-engineer',
    phase: 'AC-07 Final Verification',
    deps: ['V9', 'V10', 'V11'],
    guards: ['T43', 'T44', 'T45', 'T46'],
    context: `AC-07 (spec.md §6): "The composer canvas can author all three outcome kinds
(trigger: step forward, trigger: step backward/loop, trigger: workflow) using the existing agent
node plus the one new external-pipeline reference node, and saving serializes them via the
full-manifest path."

An earlier validator (V6, in the original spec-014 run) marked this PASS using a scratch vitest
test that called agentsToManifestSteps() directly on a manually-constructed object — i.e. it
proved the DATA SHAPE serializes correctly, not that a user can actually author it through the
real UI. An independent audit later found this PASS was materially degraded: the backward/loop
case had zero visual feedback (R-23 missing) and the workflow-trigger case required blind
free-text entry with no picker (R-24 missing) or resolved display (R-22 partial).

This validator's job is DIFFERENT from V6's: verify AC-07 through the REAL composer
node/edge/picker mechanism this time (T43's picker, T44's resolved-name card, T45/T46's edge
rendering + gesture), not another scratch serialization test.`,
    criteria: [
      'A trigger:step forward outcome, a trigger:step backward/loop outcome, and a trigger:workflow outcome can each be authored end-to-end via the actual interactive UI mechanism (T43\'s picker, T45/T46\'s edge gesture and rendering, T44\'s resolved-name card) — not blind freehand text entry alone',
      'Saving still serializes all three via the full-manifest path exactly as before — re-confirm by running `cd frontend && npx vitest run src/store/api/userWorkflows.test.ts`',
      'Report explicitly whether AC-07 now reads as a full, non-degraded PASS, and name any residual gap precisely and honestly if it does not',
    ],
  },
}

// ---------------------------------------------------------------------------
// Scheduler — do not edit below this line for a normal generation.
// ---------------------------------------------------------------------------

const MAX_PARALLEL = 6
const NORMAL_FIX_ATTEMPTS = 3
const ESCALATED_FIX_ATTEMPTS = 2
const MAX_TASK_FIX_ATTEMPTS = NORMAL_FIX_ATTEMPTS + ESCALATED_FIX_ATTEMPTS

const state = {}
const results = {}
const taskFailCount = {}
for (const id of Object.keys(NODES)) state[id] = 'pending'

async function safeAgent(prompt, opts) {
  try {
    return await agent(prompt, opts)
  } catch (e) {
    log(`agent() threw for ${opts.label || '(unlabeled)'}: ${e?.message || e}`)
    return null
  }
}

async function safeAgentRetrying(prompt, opts, retries = 2) {
  for (let i = 0; i <= retries; i++) {
    const r = await safeAgent(prompt, i === 0 ? opts : { ...opts, label: `${opts.label}-infra-retry${i}` })
    if (r) return r
    if (i < retries) log(`${opts.label}: agent() call itself failed (infra/schema glitch, not a task defect) — retrying (${i + 1}/${retries})`)
  }
  return null
}

function isReady(id) {
  return state[id] === 'pending' && NODES[id].deps.every((d) => state[d] === 'done')
}

function filesInFlight() {
  const set = new Set()
  for (const [id, s] of Object.entries(state)) {
    if (s === 'running') for (const f of NODES[id].files || []) set.add(f)
  }
  return set
}

function collidesWithRunning(id) {
  const inFlight = filesInFlight()
  return (NODES[id].files || []).some((f) => inFlight.has(f))
}

function taskPrompt(id, feedback) {
  const t = NODES[id]
  const feedbackBlock = feedback ? `
==============================================================================
THIS IS A RETRY. A validator already REJECTED this task's work. Do not just repeat the same
approach — read the failure evidence below and fix the SPECIFIC problem it names.

Validator's failure report:
${feedback}
==============================================================================
` : ''
  return `
You are executing task ${id}, as one step of an automated workflow. Another agent will
validate your work afterward against the acceptance criteria below — be honest in your
self-check, do not claim something passed if you are unsure.

${REPO_NOTES}
${feedbackBlock}
TASK ${id}
File(s): ${t.file}
${t.traces ? `Traces to: ${t.traces}\n` : ''}
Description:
${t.desc}

Acceptance criteria (self-check each one honestly before returning):
${t.ac.map((a, i) => `${i + 1}. ${a}`).join('\n')}

Do the work now using your file/bash tools. Then return the structured result: taskId="${id}",
status ("done" if you completed the work and believe the AC are met, "blocked" if you could not
proceed — explain why in "blockers"), filesChanged (the real list of paths you touched),
summary (what you actually did, 2-4 sentences), and acSelfCheck (one entry per AC line above,
with met:true/false and a short note).
`.trim()
}

function validatorPrompt(id) {
  const v = NODES[id]
  const reportsText = v.guards
    .map((gid) => {
      const r = results[gid]
      if (!r) return `${gid}: NOT YET RUN`
      if (typeof r === 'string') return `${gid}: ${r}`
      return `${gid} [${r.status || (r.pass ? 'pass' : 'fail')}] — ${r.summary}\n  filesChanged: ${(r.filesChanged || []).join(', ') || '(none reported)'}\n  self-check: ${JSON.stringify(r.acSelfCheck || r.checks)}`
    })
    .join('\n\n')
  return `
You are validator ${id}. You guard: ${v.guards.join(', ')}.
Your job is to judge, by actually inspecting the code and running commands, whether these
genuinely satisfy the criteria below — do NOT just trust the task reports, they are context only.

${REPO_NOTES}

${v.context ? `IMPORTANT CONTEXT: ${v.context}\n` : ''}
TASK/GUARD REPORTS (context, verify independently):
${reportsText}

PASS requires ALL of the following (check each by inspection/exercise, not by reading the diff alone):
${v.criteria.map((c, i) => `${i + 1}. ${c}`).join('\n')}

For each criterion, actually check it — read the relevant files, run the project's real
verify/test commands, and where a criterion requires exercising live behavior you cannot
directly run, reason carefully from the code and say explicitly in "evidence" that this is
inferred rather than observed directly.

Return: validatorId="${id}", pass (true only if every criterion passes), checks (one entry per
criterion with result pass/fail and evidence), failedTasks (which of ${v.guards.join(', ')} are
responsible — empty array if pass), summary (2-4 sentences).
`.trim()
}

async function runNode(id) {
  const node = NODES[id]
  state[id] = 'running'
  log(`-> ${id} [${node.agentType || node.model}] (${node.phase}) starting`)

  if (node.kind === 'task') {
    const report = await safeAgent(taskPrompt(id), {
      label: id, phase: node.phase, agentType: node.agentType, model: node.model, schema: TASK_RESULT_SCHEMA,
    })
    state[id] = report ? 'done' : 'error'
    results[id] = report
    log(`${state[id] === 'done' ? 'OK' : 'FAILED'} ${id}${report ? ` (self-reported: ${report.status})` : ' (no report)'}`)
    return
  }

  let result = await safeAgentRetrying(validatorPrompt(id), {
    label: id, phase: node.phase, agentType: node.agentType, model: node.model, schema: VALIDATOR_RESULT_SCHEMA,
  })

  let round = 0
  while (result && !result.pass && result.failedTasks?.length > 0) {
    const redoable = result.failedTasks.filter(
      (tid) => NODES[tid] && NODES[tid].kind === 'task' && (taskFailCount[tid] || 0) < MAX_TASK_FIX_ATTEMPTS
    )
    const exhausted = result.failedTasks.filter((tid) => (taskFailCount[tid] || 0) >= MAX_TASK_FIX_ATTEMPTS)

    if (exhausted.length) {
      log(`${id}: ${exhausted.join(', ')} already exhausted ${MAX_TASK_FIX_ATTEMPTS}/${MAX_TASK_FIX_ATTEMPTS} attempts (${NORMAL_FIX_ATTEMPTS} normal + ${ESCALATED_FIX_ATTEMPTS} opus-escalated) — not retrying again.`)
    }
    if (redoable.length === 0) {
      log(`${id}: every currently-failing task has exhausted its fix budget — stopping retries, reporting blocked.`)
      break
    }

    round++
    log(`VALIDATOR FAIL ${id} (round ${round}) — redoing ${redoable.join(', ')}`)

    const failedChecks = (result.checks || []).filter((c) => c.result === 'fail')
    const feedbackText = [
      result.summary || '',
      failedChecks.length
        ? `Failed criteria:\n${failedChecks.map((c) => `- ${c.criterion}\n  Evidence: ${c.evidence}`).join('\n')}`
        : '',
    ].filter(Boolean).join('\n\n')

    const redone = await parallel(
      redoable.map((tid) => async () => {
        taskFailCount[tid] = (taskFailCount[tid] || 0) + 1
        const attempt = taskFailCount[tid]
        const escalate = attempt > NORMAL_FIX_ATTEMPTS
        if (escalate) {
          log(`${tid}: attempt ${attempt}/${MAX_TASK_FIX_ATTEMPTS} — escalating to opus (${NORMAL_FIX_ATTEMPTS} normal-role attempts already failed).`)
        }
        const r = await safeAgent(taskPrompt(tid, feedbackText), {
          label: `${tid}-retry${attempt}${escalate ? '-opus' : ''}`,
          phase: NODES[tid].phase,
          agentType: NODES[tid].agentType,
          model: escalate ? 'opus' : NODES[tid].model,
          schema: TASK_RESULT_SCHEMA,
        })
        return [tid, r]
      })
    )
    for (const pair of redone.filter(Boolean)) {
      const [tid, r] = pair
      if (r) results[tid] = r
    }

    result = await safeAgentRetrying(validatorPrompt(id), {
      label: `${id}-recheck${round}`, phase: node.phase, agentType: node.agentType, model: node.model, schema: VALIDATOR_RESULT_SCHEMA,
    })
  }

  if (result && result.pass) {
    state[id] = 'done'
    results[id] = result
    log(`VALIDATOR PASS ${id}${round ? ` (after ${round} fix round${round === 1 ? '' : 's'})` : ''} — ${result.summary}`)
  } else {
    state[id] = 'error'
    results[id] = result
    log(`VALIDATOR ${id} still FAILING after ${round} fix round(s) — PHASE BLOCKED. ${result ? result.summary : '(no result)'}`)
  }
}

async function scheduler() {
  const active = new Map()

  while (true) {
    const remaining = Object.keys(NODES).filter((id) => state[id] !== 'done' && state[id] !== 'error')
    if (remaining.length === 0) break

    const anyRunning = active.size > 0
    const anyReady = remaining.some((id) => isReady(id) && !collidesWithRunning(id))
    if (!anyRunning && !anyReady) {
      const stuck = remaining.filter((id) => state[id] === 'pending')
      log(`Nothing left can become ready — ${stuck.length} node(s) permanently blocked (likely a failed hard-gate upstream): ${stuck.join(', ')}`)
      break
    }

    while (active.size < MAX_PARALLEL) {
      const next = Object.keys(NODES).find((id) => isReady(id) && !collidesWithRunning(id) && !active.has(id))
      if (!next) break
      const p = runNode(next)
        .catch((e) => { log(`runNode(${next}) threw unexpectedly: ${e?.message || e}`); state[next] = 'error' })
        .then(() => { active.delete(next) })
      active.set(next, p)
    }

    if (active.size === 0) break
    await Promise.race(active.values())
  }

  await Promise.all(active.values())
}

log(`Dispatching every node whose deps are already satisfied in one wave (up to ${MAX_PARALLEL} concurrent).`)

await scheduler()

const done = Object.keys(NODES).filter((id) => state[id] === 'done')
const errored = Object.keys(NODES).filter((id) => state[id] === 'error')

log(`Finished: ${done.length}/${Object.keys(NODES).length} done, ${errored.length} error/blocked.`)
if (errored.length) log(`Blocked nodes: ${errored.join(', ')} — see their reports for what to fix.`)

return {
  done, errored, results,
  summary: `${done.length}/${Object.keys(NODES).length} nodes done. ` +
    (errored.length ? `Blocked at: ${errored.join(', ')}.` : 'All nodes passed.'),
}
