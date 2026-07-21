# Design — Revision Pipeline Eval Suite + Fix

Design decisions for the requirements in `requirements.md`. Each decision
has an id (D-xx) referenced from `tasks.md`.

## D-01 — Suite location: inside `backend/tests/`, not a new package

The eval suite lives at `backend/tests/evals/`. Rationale:

- `pyproject.toml` already sets `testpaths = ["tests"]` — zero CI/config
  wiring needed; collection is automatic.
- It can import the proven offline harness
  (`tests/agents/_scripted_model.py`) directly, same as the phase-5 suites
  do — no duplication of the scripted-model recipe.
- A separate top-level eval package (e.g. `backend/evals/`) would need its
  own pytest config, import-path bootstrapping, and CI job for no benefit
  at this scale. Revisit only if the eval suite grows beyond this issue.

(Flagged as the one structural default chosen without asking — say the
word and it moves.)

## D-02 — Folder structure

```
backend/tests/evals/
├── __init__.py
├── conftest.py                    # shared fixtures: RUNS_ROOT tmpdir, scenario loader
├── test_hello_world.py            # R-05 harness gate (Phase 0)
└── revision_fulfillment/
    ├── __init__.py
    ├── fixtures/
    │   ├── mini_prototype.html    # ≤4 KB seed prototype (R-06): 2–3 pages,
    │   │                          # routes map, one intentionally dead button
    │   ├── design.md              # minimal DS tokens file for sandbox seeding
    │   └── scenarios.yaml         # S1/S2/S3 declarations (D-05)
    ├── test_l1_api_entry.py       # R-07
    ├── test_l2_compile.py         # R-08
    ├── test_l3_context_seed.py    # R-09
    ├── test_l4_post_step.py       # R-10
    ├── test_l5_selection_gap.py   # R-11  ← unit-level root-cause statement
    ├── test_l6_llm_boundary.py    # R-12
    └── test_scenarios.py          # R-13/14/15 end-to-end scripted evals
```

One file per layer so a failure localizes the broken layer by filename
alone. Everything under `evals/` carries `pytestmark = pytest.mark.eval`.

## D-03 — Zero-token default, opt-in live tier

- Default tier: `ScriptedFakeChatModel` scripts injected as `ctx.model`,
  monkeypatch recipe copied from `_scripted_model._drive()` (planner
  no-op, clarify off, ArtifactStore no-op, review-gate no-op, `RUNS_ROOT`
  → tmpdir). **0 tokens, no network** (R-03).
- Live tier: at most ONE smoke test, `@pytest.mark.requires_api_key`
  (reuses the registered marker — skipped without credentials), Haiku,
  `max_tokens` ≤ 2048, `mini_prototype.html` fixture only (R-04). Added in
  Phase 3 to smoke the real fulfillment call once; never in the default run.
- Budget rule of thumb the suite encodes: the *entire* live tier per
  invocation stays under ~10k tokens round-trip — enforced by fixture size
  + max_tokens, not by trust.

## D-04 — Markers & selection

- Register `eval` in `pyproject.toml` markers (R-02). Commands:
  - `python3.11 -m pytest tests/evals -m eval` — the suite alone.
  - `-m "eval and not requires_api_key"` — explicit offline-only.
- Defect tests use `@pytest.mark.xfail(strict=True, reason="FINDINGS A2/A7 — no instruction-fulfillment check; see .investigations/revision-pipeline-thinking-issue")`
  (R-16). `strict=True` is the load-bearing choice: an unexpectedly-passing
  xfail FAILS the suite, so the fix cannot land without removing the
  markers in the same diff — the reproducibility→resolution transition is
  visible in `git log`.

## D-05 — Scenarios as data, scripts as code

`scenarios.yaml` declares each scenario's *intent* (id, instruction,
expected verdict, description); the scripted agent behaviors (which
`edit_file` calls the fake model emits) live as Python script-builders in
`test_scenarios.py`, keyed by scenario id. Rationale: tool-call scripts
need `AIMessageChunk`/`tool_call_chunks` construction that YAML can't
express cleanly; the YAML keeps the scenario matrix readable/reviewable at
a glance, the code keeps the mechanics type-checked.

Scenario matrix (R-13/14/15):

| id | instruction | scripted agent behavior | desired outcome | today |
|----|-------------|------------------------|-----------------|-------|
| S1 | "Make the Save button on Settings actually save" | edits an unrelated HTML comment (clean no-op) | unsatisfied → retry with residual | passes silently → **xfail** |
| S2 | "Add a Reports page reachable from the sidebar" | adds `<section>` but neither route nor nav link | unsatisfied (partially) → retry | *(note: today's static_check may catch the orphan section — script the gap so it does NOT, i.e. section+route added but no nav link; verify while implementing)* → **xfail** |
| S3 | "Change the topbar title to 'Acme Console'" | performs exactly that edit | satisfied → no retry, no extra threads | passes, must stay passing |

## D-06 — Layer-test seams (what each test hooks)

- **L1**: call the API entry (`app/api` revision run command) with a
  captured/fake engine — assert the kwargs (`revision_instruction`,
  `parent_run_id`) at the `execute()` seam; follow the existing
  `test_run_revision_fe_contract.py` fixture style rather than inventing a
  new transport fake.
- **L2**: direct call `compile_for_run("prototype_revision")`; assert on
  the typed `CompiledWorkflow` fields — no mocking at all.
- **L3**: drive the `previous_run` provider with a fake parent-run store;
  assert `ctx.revision_original_html` + sandbox contents.
- **L4**: instantiate `RevisionValidationPostStep` with a stub `ctx` whose
  `runner` records calls (the capability's own import-purity means the stub
  needs only `compute_revision_baseline` + `run_validation_fix_loop` +
  `sandbox.path_for`) — mirrors how `test_phase5_revision_validation.py`
  already spies the threaded args.
- **L5**: call `_select_issues_to_fix` directly with constructed
  static/render results + populated baselines. Pure function-level; the
  root-cause test.
- **L6**: run `_run_validation_fix_loop` with a scripted failing→fixed
  sequence and capture the `create_runner` call (monkeypatch) — assert the
  fix_message content + thread id shape.

## D-07 — Fix architecture (Phase 3): dedicated post-step, dedicated small loop

- New file `backend/agents/capabilities/post_steps/instruction_fulfillment.py`
  (post_step, not validator: validators in this codebase are file-checkers
  fed to the ValidationGate; this is a semantic, LLM-backed check with its
  own retry side effect — same species as `revision_validation`, so same
  registry kind). Registered `@register("post_step", "instruction_fulfillment", ...)`.
- Import purity preserved: reaches the kernel only through `ctx.runner`
  handles, exactly like `revision_validation.py`. Two new handle methods on
  the engine's runner facade: `evaluate_instruction_fulfillment(...)` (the
  one Haiku call) and reuse of the existing `create_runner`-based retry via
  a new `run_fulfillment_retry(...)` — OR the retry inlined in the
  capability through an existing generic handle if one fits; decide at
  implementation, keep the never-raise / non-yielding contract either way.
- Manifest: `post_step: instruction_fulfillment` on step 2 of
  `prototype_revision/workflow.yaml` (runs after the validate agent — R-19).
- Verdict model call: `build_model()` as-is (Haiku default), `max_tokens`
  small (~1024), prompt = instruction + a *trimmed* artifact view if the
  file is large (send the diff-relevant regions or cap the HTML slice —
  decide at implementation; log the input token count either way, R-21).
- Retry: 1 attempt (R-20), thread id
  `{run_id}:{agent_id}:fulfillment:fix1`, stream drained internally,
  nothing re-emitted — same UX contract as the structural fix-loop.
- JSON tolerance: reuse/extract the `clarify_engine.py` lenient-parse
  approach (R-18); unparseable ⇒ satisfied + warning (fail-open — a broken
  judge must never hold the deliverable hostage).

## D-08 — Golden/INV-3 safety

The INV-3 characterization goldens
(`tests/agents/characterization/golden/prototype_revision.*`) were recorded
without the fulfillment step. Two acceptable outcomes, decided at
implementation time: (a) the offline golden harness pins the fulfillment
post-step disabled (the precedent: it already pins `require_render=False`),
keeping goldens byte-identical; or (b) goldens are re-recorded once,
deliberately, in their own commit. Default to (a) — it matches the
established pattern for production-only behaviors.

## D-09 — What we deliberately did NOT design

- No new eval framework/deps (no promptfoo/braintrust/etc.) — pytest +
  scripted models already give deterministic, zero-cost, CI-native evals;
  an external framework adds spend and a second runner for no signal gain
  at 3 scenarios. Revisit if the scenario matrix grows 10×.
- No LLM-as-judge in the *default* suite — the scripted tier asserts on
  concrete artifacts (file contents, emitted events, spy calls), which is
  cheaper and non-flaky. The only judge-like call is the production
  fulfillment check itself, smoke-tested once in the live tier.
- No thinking-related design — parked (R-24).
