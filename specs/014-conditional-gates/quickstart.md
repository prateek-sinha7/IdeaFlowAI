# 014 — Quickstart: verifying conditional gates work

How to confirm each phase of [plan.md](plan.md) actually landed correctly, using the five
reference fixtures already checked into `backend/agents/workflows/ex_A*/`. No
new fixtures need writing — this quickstart drives the existing ones.

## After Phase 1 (compiler)

The fixtures should now **compile** (not yet run — that needs Phase 3).

```bash
cd backend
python3.11 -c "
from pathlib import Path
from agents.workflows.manifest import load_manifest
from agents.workflows.compiler import WorkflowCompiler
from agents.capabilities.registry import CapabilityRegistry

registry = CapabilityRegistry()
base_dir = Path('agents/workflows')
for wf_id in ['ex_A1_loop', 'ex_A2_branch',
              'ex_A3_divert', 'ex_A3_target',
              'ex_A4_human_gate']:
    manifest = load_manifest(wf_id, base_dir)
    compiled = WorkflowCompiler().compile(manifest, registry)
    leaves = [s.agent_id for s in compiled.steps if s.is_leaf]
    print(f'{wf_id}: OK, {len(compiled.steps)} steps, leaves={leaves}')
"
```

**Expect**: all five print `OK`, no `CompilerError`. `ex_A2_branch` should
report TWO leaves (`say_hello`, `say_hola` — R-26's whole point). `ex_A3_target`
reports one leaf (`welcome`).

**Negative check** — confirm R-03 actually rejects dead config:

```bash
python3.11 -c "
from pathlib import Path
from agents.workflows.manifest import load_manifest
from agents.workflows.compiler import WorkflowCompiler, CompilerError
from agents.capabilities.registry import CapabilityRegistry
import copy

manifest = load_manifest('ex_A1_loop', Path('agents/workflows'))
# Strip 'conditional' from the gate_check step's gates, keep its route: block.
for step in manifest.steps:
    if step.get('instance_id') == 'check':
        step['gates'] = []
try:
    WorkflowCompiler().compile(manifest, CapabilityRegistry())
    print('FAIL — should have raised CompilerError')
except CompilerError as e:
    print(f'OK — rejected: {e}')
"
```

## After Phase 2 (`ExecutionContext`)

Unit-level only — no end-to-end run yet.

```bash
python3.11 -m pytest tests/unit/test_execution_engine.py -k "step_visit_counts or trigger_depth" -v
```

## After Phase 3 (dispatch loop)

**Characterization check first** — confirm zero behavior change for every workflow that
doesn't declare `route`:

```bash
python3.11 -m pytest tests/agents/test_characterization_*.py -v
```

**Then** run `ex_A1_loop` (A1, the loop case) end-to-end and inspect the
visit sequence — this is the first fixture that actually exercises the new cursor mechanism:

```bash
# via whatever this repo's existing "launch a run programmatically" test harness is
# (see tests/unit/test_execution_engine.py for the pattern) — launch
# ex_A1_loop with a scripted model that answers {"decision": "retry"}
# twice then {"decision": "ok"}, and assert:
#   - "greet" and "check" each ran 3 times
#   - "done" ran exactly once
#   - the run completed normally (not BudgetExceeded, since 3 <= loop_max_iterations)
```

**Boundary check** — script the model to always answer `{"decision": "retry"}` and confirm the
run fails closed with `BudgetExceeded` after exactly `loop_max_iterations` (3, per this
fixture's declared value) passes — not 4, not unbounded.

## After Phase 4 (cross-workflow triggering)

Run `ex_A3_divert` end-to-end:

```bash
# launch ex_A3_divert with a scripted model answering {"decision": "divert"}
# assert:
#   - the FIRST run's WorkflowRun.status == "diverted"
#   - a SECOND WorkflowRun exists with parent_run_id == first run's id,
#     workflow type == "ex_A3_target",
#     owner_id/workspace_id == the first run's values
#   - the first run's SSE stream emitted exactly one "pipeline_diverted" event before closing
#   - the second run completed normally, writing "Welcome to the target workflow!" to output.txt
```

**Depth-cap check** — build a small chain of workflows that each `trigger: workflow` the next
(reuse `ex_A3_target` copies, or a throwaway test fixture) 6 levels deep and
confirm the 6th trigger attempt fails closed with `BudgetExceeded`, not a silent infinite mint.

## After Phase 5 (frontend)

Manual/browser check (no automated test replaces this for the canvas UI itself):

1. Open the composer, load `ex_A2_branch` (once `user_launchable: true` makes
   it selectable).
2. Confirm the `pick` node shows a route-target editor with two outcomes (`english`/`spanish`),
   each pointing at a real canvas edge to `say_hello`/`say_hola`.
3. Confirm `ex_A3_divert`'s `decide` node shows the NEW external-pipeline
   reference card pointing at `ex_A3_target`, picked from the same "My Workflows"
   list used elsewhere.
4. Save, reload, confirm the `route` field round-trips byte-identically through
   `buildWorkflowManifest`/`needsFullManifest`.
5. Run it live; confirm the run-history view shows the two-linked-cards treatment (R-20) once
   the divert fires.

## Full acceptance sweep (all phases landed)

Every `AC-##` in spec.md §6 should be independently verifiable at this point. Recommend a final
pass mapping each AC to the specific test/manual-check above (or a new one, if a gap is found)
before considering spec 014 fully shipped.
