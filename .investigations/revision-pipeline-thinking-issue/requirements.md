# Requirements — Revision Pipeline Eval Suite + Fix

Derived from `PLAN.md` (v2, eval-first) and `FINDINGS.md`. Each requirement
is atomic, testable, and referenced by id from `design.md` and `tasks.md`.

## A. Eval harness (Phase 0)

- **R-01** — An eval suite package SHALL exist under `backend/tests/evals/`
  and be collected by the existing pytest config (`testpaths = ["tests"]`)
  with no changes to how the rest of the suite runs.
- **R-02** — An `eval` pytest marker SHALL be registered in
  `backend/pyproject.toml` `[tool.pytest.ini_options] markers`, so the eval
  suite is selectable with `-m eval` and excludable with `-m "not eval"`.
- **R-03** — All eval tests SHALL run fully offline by default: scripted
  models only (`ScriptedFakeChatModel` from
  `tests/agents/_scripted_model.py`), no network, no LLM tokens consumed.
- **R-04** — Any test that makes a real LLM call SHALL be gated behind the
  existing `requires_api_key` marker and skipped by default; live tests
  SHALL use Haiku with a small `max_tokens` cap and tiny fixtures.
- **R-05** — A hello-world test SHALL validate the harness before real
  tests are written: package importability, harness imports
  (`ScriptedFakeChatModel`, `compile_for_run`, the `revision_validation`
  post-step), one scripted model turn driven successfully, and marker
  selection working.
- **R-06** — Scenario inputs (HTML fixtures, instructions, scripted agent
  behaviors) SHALL live as small data files inside the eval package, kept
  deliberately tiny (target: fixture HTML ≤ ~4 KB) so they stay token-light
  even if replayed against a live model.

## B. Layered unit tests along the issue surface (Phase 1)

Scoped strictly to the revision-instruction path — not general coverage.

- **R-07 (L1, API entry)** — A test SHALL assert the revision run request's
  `revision_instruction` and `parent_run_id` reach
  `ExecutionEngine.execute()` unchanged from the API/WS entry point.
- **R-08 (L2, compile)** — A test SHALL assert
  `compile_for_run("prototype_revision")` yields: 2 steps in order
  (`prototype-revision-agent`, `prototype-revision-validate`); step 1 with
  `gates: [validation]`, validators `[html_static, html_render]`,
  `post_step: revision_validation`, `require_render: true`; step 2 with
  `gates: []`; deliverable `prototype.html` with `revises_existing: true`.
- **R-09 (L3, context seeding)** — A test SHALL assert the `previous_run`
  provider stashes the parent run's HTML as `ctx.revision_original_html`
  and seeds the sandbox with the parent's reference files.
- **R-10 (L4, post-step dispatch)** — A test SHALL assert
  `RevisionValidationPostStep.run()` computes the pre-edit baseline from
  `revision_original_html` and calls `run_validation_fix_loop` with
  `user_instruction=<instruction>`, `label="revision"`, and both baseline
  sets (spy on the `ctx.runner` handle; no engine import in the capability
  — respect the import-purity contract).
- **R-11 (L5, selection semantics — the documented gap)** — A test SHALL
  assert that `_select_issues_to_fix` with populated baselines and a
  structurally clean post-edit file returns `[]` (⇒ `failing=False`). This
  test PASSES against current code and is the unit-level statement of root
  cause FINDINGS A2; its docstring SHALL reference FINDINGS A2 explicitly.
- **R-12 (L6, LLM boundary)** — A test SHALL assert the revision
  `fix_message` (engine.py revision branch) embeds the user instruction
  verbatim and that the fix thread id targets the compiled step's agent id
  (not a hardcoded literal).

## C. Defect-reproducing eval scenarios (Phase 2)

- **R-13 (S1, no-op edit)** — An end-to-end scripted eval SHALL exist where
  the revision agent makes a structurally clean edit unrelated to the
  instruction; it SHALL assert the DESIRED behavior (pipeline detects the
  unsatisfied instruction and retries/reports residuals) and SHALL be
  marked `xfail(strict=True)` referencing this investigation until the
  Phase-3 fix lands.
- **R-14 (S2, partial fix)** — Same pattern for a half-done instruction
  (e.g. element added but handler never wired); `xfail(strict=True)` until
  the fix lands.
- **R-15 (S3, control / happy path)** — An eval SHALL assert that when the
  scripted agent genuinely satisfies the instruction, NO extra fix-thread
  or retry fires and the event stream matches current behavior. This test
  passes today and MUST continue passing after the fix (guards cost +
  regression on the common case).
- **R-16** — `xfail` markers SHALL use `strict=True` so that the moment a
  fix makes S1/S2 pass, the suite errors until the markers are removed —
  making "the fix resolves the underlying issue" an auditable diff event,
  not a claim.

## D. The fix (Phase 3)

- **R-17** — A new `instruction_fulfillment` capability SHALL exist under
  `agents/capabilities/`, registered via the existing `register()`
  convention, that evaluates post-edit `prototype.html` against
  `revision_instruction` (+ `revision_original_html` as context) and
  returns `{"satisfied": bool, "residual": [str, ...]}`.
- **R-18** — Its JSON parsing SHALL tolerate Haiku's known malformations
  (markdown fences, trailing text) following the `clarify_engine.py`
  pattern; an unparseable verdict SHALL degrade to "satisfied" +
  `logger.warning` (never blocks or aborts a run — parity with
  `revision_validation`'s never-raise contract).
- **R-19** — The capability SHALL be wired into the `prototype_revision`
  manifest to run AFTER step 2 (`prototype-revision-validate`), so it sees
  the structurally finalized artifact.
- **R-20** — On `satisfied=false`, exactly ONE retry of the revision agent
  SHALL fire, with the residual issues + original instruction injected, on
  a distinct fix thread — a small dedicated loop, NOT a modification of
  `_run_validation_fix_loop`'s existing build/revision contract.
- **R-21** — The check SHALL be skipped when `revision_instruction` is
  empty/whitespace, and SHALL log per-stage token usage so its cost is
  measurable post-ship.
- **R-22 (definition of done)** — The fix is done ONLY when: R-13/R-14
  `xfail` markers are removed and both pass; R-15 still passes; R-07–R-12
  all pass; the INV-3 characterization goldens
  (`tests/agents/characterization/golden/prototype_revision.*`) are
  byte-identical.
- **R-23 (escape hatch, non-default)** — A per-agent `model:` bump for
  `prototype-revision-agent` MAY be applied only with real post-ship
  failure data, via the existing `model_policy.py` tier-3 precedence.

## E. Parked (Phase 4 — do not start before R-22)

- **R-24** — Thinking visibility (FINDINGS B1–B5) SHALL be addressed only
  after Phase 3 ships, per the v1 task detail preserved in `PLAN.md`
  Phase 4. Its own requirements are to be written when un-parked.
