# Fix Plan — Prototype Revision Pipeline (v2, eval-first)

Root causes established in `FINDINGS.md`. **v2 restructures the plan around
an eval-first workflow**: before any fix lands, an eval/unit-test suite must
first *demonstrate* the defect (a revision that doesn't satisfy the user's
instruction passes every existing gate), so that the fix is provably
reproducing and resolving the underlying issue — not just plausible.

Hard constraints:

- **Token budget**: the suite must be ~zero-cost by default. Every eval runs
  against the existing offline `ScriptedFakeChatModel` harness
  (`backend/tests/agents/_scripted_model.py`) — no network, no LLM spend.
  A tiny opt-in live tier (gated behind the existing `requires_api_key`
  marker) exists only for final smoke confirmation on Haiku.
- **Model**: Haiku stays the pipeline model. No model bump in the main plan
  (kept only as a data-driven escape hatch, Phase 3 note).
- **Thinking (Defect B) is PARKED** — moved to the last phase, untouched
  until Phases 0–3 are done.

---

## Phase 0 — Eval harness scaffold + hello-world validation

Stand up the suite package before writing any real test, and prove the
plumbing works end-to-end.

- Create `backend/tests/evals/` as a pytest package with a
  `revision_fulfillment/` sub-package (structure in `design.md` D-01/D-02).
- Register an `eval` pytest marker in `backend/pyproject.toml` so the suite
  is selectable/excludable (`-m eval` / `-m "not eval"`).
- **Hello-world gate**: one trivial test that (a) imports the harness
  (`_scripted_model.ScriptedFakeChatModel`, `compile_for_run`,
  the `revision_validation` post-step) and (b) drives one scripted model
  turn — proving package refs, imports, `RUNS_ROOT` monkeypatching, and
  marker selection all work before anything real is built on top.
- Exit criterion: `python3.11 -m pytest tests/evals -m eval` passes with
  exactly the hello-world test collected, and the rest of the suite
  (`-m "not eval"`) is unaffected.

## Phase 1 — Layered unit tests along the issue surface (API → LLM boundary)

One small test module per layer of the revision request's journey, **scoped
strictly to this issue** (instruction propagation + validation semantics —
not general coverage). Each layer's test documents "what actually happens
here today," so when the defect eval fails in Phase 2 we can see *where*
the instruction's meaning gets dropped.

- **L1 — API entry**: the revision run request carries
  `revision_instruction` + `parent_run_id` into `ExecutionEngine.execute()`
  unchanged (entry: `app/api/` run-command/WS path).
- **L2 — Workflow compile**: `compile_for_run("prototype_revision")`
  produces the expected shape — 2 steps, step 1 has
  `post_step: revision_validation`, `gates: [validation]`,
  `revises_existing: true`, step 2 has `gates: []`.
- **L3 — Context seeding**: the `previous_run` provider stashes the parent
  run's HTML as `ctx.revision_original_html` and seeds `design.md`/`spec.md`
  into the sandbox.
- **L4 — Post-step dispatch**: `RevisionValidationPostStep.run()` computes
  the pre-edit baseline and calls `run_validation_fix_loop` with
  `user_instruction=<the instruction>`, `label="revision"`, and both
  baselines (spy on the `ctx.runner` handle).
- **L5 — Selection semantics (the gap, unit-level)**:
  `_select_issues_to_fix` with populated baselines and a structurally clean
  post-edit file returns `[]` → `failing=False` — i.e. the loop *cannot*
  fail on "instruction not satisfied." This test PASSES today and is the
  precise unit-level statement of the root cause (FINDINGS A2).
- **L6 — LLM boundary**: the revision `fix_message` assembly
  (`engine.py:4522-4538`) embeds the user's instruction verbatim; the fix
  thread targets the right agent id. This is the last point before the
  model call — everything beyond it is model behavior, which the eval
  scenarios (Phase 2) cover with scripted models.

## Phase 2 — Defect-reproducing eval scenarios

Scenario-based evals that assert the **desired** end-to-end behavior and
are expected to FAIL today, marked `xfail(strict=True)` with the defect
reference — so the suite (a) proves the issue is reproducible now, and
(b) *errors loudly* the moment a fix makes them pass, forcing the marker's
removal and making the fix's effect auditable in the diff.

- **S1 (core defect)**: scripted revision agent performs a structurally
  clean **no-op edit** (touches nothing related to the instruction, e.g.
  instruction says "make the Save button work", agent edits an unrelated
  comment). Desired: the pipeline detects the instruction was not satisfied
  and retries / surfaces residual issues. Today: run completes "successfully".
- **S2 (partial fix)**: agent does half the instruction (adds the button,
  never wires the handler — the #1 failure mode its own prompt warns
  about). Desired: fulfillment check flags the unwired half.
- **S3 (control, passes today and always)**: agent genuinely satisfies the
  instruction → no retry fires, no extra fix-thread, event stream matches
  the current golden behavior. Guards against the fix regressing the happy
  path or adding cost to the common case.
- Scenario inputs are small fixture files (tiny HTML, short instructions —
  token-light by construction, even if ever replayed live).

## Phase 3 — Fix + eval-verified resolution

Implement the instruction-fulfillment verification (design carried over
from v1, unchanged in substance):

- New capability `instruction_fulfillment` (validator or post_step per the
  `agents/capabilities/registry.py` convention): one focused Haiku call —
  inputs: `revision_instruction`, `revision_original_html`, post-edit
  `prototype.html`; output: strict-but-tolerantly-parsed JSON
  `{"satisfied": bool, "residual": [...]}` (follow `clarify_engine.py`'s
  malformed-JSON tolerance pattern for Haiku).
- Wired into `prototype_revision`'s manifest after step 2, with its own
  small retry loop (1 attempt, separate from the structural loop — option
  (b) from v1, smallest blast radius vs the INV-3 goldens).
- Skip when instruction is empty; per-stage token logging.
- **Definition of done is eval-driven**: S1/S2 `xfail` markers removed and
  passing (fulfillment check catches the miss, retry fires with residual
  reasons injected), S3 still passing byte-compatibly, L1–L6 all green,
  INV-3 characterization goldens
  (`tests/agents/characterization/golden/prototype_revision.*`) unchanged.
- Escape hatch (only with real post-ship failure data): per-agent `model:`
  bump on `prototype-revision-agent/AGENT.md` via the existing
  `model_policy.py` tier-3 precedence — no engine change.

## Phase 4 — PARKED: thinking visibility (Defect B)

Deliberately last; do not start until Phases 0–3 ship. The full analysis
stays in `FINDINGS.md` (B1–B5) and the v1 task detail remains valid:

1. `_extract_thinking()` sibling helper in `deep_agent_runner.py` (confirm
   the Bedrock Converse reasoning-block key against `langchain_aws` first).
2. `thinking` event type in `astream_events()` dispatch (+ docstring table).
3. `engine.py` maps it to the `agent_thinking` WS event the frontend
   already consumes (`useWorkflow.ts:315`) — no frontend work needed.
4. Scripted-model tests + INV-3 golden byte-identity at the default
   `THINKING_BUDGET_TOKENS=0`.
5. Only then flip the env var (start at the 1024 floor), scoped per
   environment, watch cost/latency; evaluate the forced `temperature=1`
   trade-off before changing the checked-in default.

---

## Sequencing

Phase 0 → 1 → 2 → 3 strictly in order (each phase's exit criterion gates
the next). Phase 4 parked until 3 is done. The spec breakdown lives in
`requirements.md` / `design.md` / `tasks.md` in this folder.
