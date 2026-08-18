---
phase: quick-260811-mxg
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/agents/execution_engine/context.py
  - backend/agents/execution_engine/engine.py
  - backend/tests/agents/test_spec_revision_context.py
  - backend/tests/agents/test_restart_resume.py
  - .planning/quick/260811-mxg-fix-update-specs-prior-spec-injection-an/260811-mxg-BASELINE.md
autonomous: true
requirements: [QUICK-260811-mxg-D1, QUICK-260811-mxg-D2, QUICK-260811-mxg-D3]
must_haves:
  truths:
    - "D1: during a spec-revision sub-pipeline the specify agent's composed context message CONTAINS the prior spec text (read from the typed artifact graph), so 'Preserve unchanged sections' becomes satisfiable."
    - "D1/TRAP-2: the injection fires from BOTH _gate_update_specs sub-pipeline call sites — the RESUME-17 gate re-entry (engine.py:3270) and the live post-stream consumer (engine.py:4296)."
    - "D1 no-leak: the prior-artifact block is rendered for the specify re-dispatch ONLY — the plan and analyze re-dispatches in the same sub-pipeline do NOT carry it, and the scratch field is empty after the sub-pipeline returns (consume-once, incl. the error path)."
    - "D2: on a resumed run the composed prompt carries the planner's real inferred_intent + the user's clarification answers in Explicit Constraints, NOT the user_message[:200] stub."
    - "D2/TRAP-4: the planner and clarifier are still NOT re-invoked on resume — the context is REHYDRATED from durable artifact_refs rows, never regenerated."
    - "D3: the revision dispatch's checkpoint thread_id differs from the first pass's (a :rev{N} suffix keyed on the sub-pipeline's revision index), so behaviour no longer depends on checkpointer replay."
    - "INV-3 dormancy: on a normal run — and on a clarify replay, which F2 deliberately excludes by gating on _resuming alone — every composed prompt and thread_id is byte-identical; the 5 characterization goldens match the pre-change baseline exactly."
    - "INV-1/SC-001: the new behaviour is keyed on generic ectx scratch fields only — the diff introduces no workflow-name or agent-id literal."
  artifacts:
    - path: "backend/agents/execution_engine/context.py"
      provides: "two additive per-run scratch fields: spec_revision_prior_artifact (str, consume-once) and revision_attempt (int, thread-id index), documented in the redo_directive family style"
      contains: "spec_revision_prior_artifact"
    - path: "backend/agents/execution_engine/engine.py"
      provides: "F1 prior-artifact injection in _run_spec_revision_sub_pipeline + the === PRIOR ARTIFACT UNDER REVISION === block in _compose_context_message; F3 :rev{N} thread suffix in _run_agent; F2 _rehydrate_planning_context helper wired into the skip_planner branch"
      contains: "_rehydrate_planning_context"
    - path: "backend/tests/agents/test_spec_revision_context.py"
      provides: "the D1 routing test (parametrized over BOTH gate consumer sites), the D1 no-leak test, and the D3 thread-id test — all on the scripted-model harness, no live LLM"
      contains: "PRIOR ARTIFACT UNDER REVISION"
    - path: "backend/tests/agents/test_restart_resume.py"
      provides: "the D2 unit test (rehydrator reconstructs planner context + clarification answers) and the D2 wiring test (a real resume drive dispatches with the rehydrated context)"
      contains: "_rehydrate_planning_context"
    - path: ".planning/quick/260811-mxg-fix-update-specs-prior-spec-injection-an/260811-mxg-BASELINE.md"
      provides: "the pre-change measurement of the 5 goldens + lint-imports + the touched suites, plus the verbatim RED output of every new test"
      contains: "PRE-CHANGE BASELINE"
  key_links:
    - from: "backend/agents/execution_engine/engine.py::_run_spec_revision_sub_pipeline"
      to: "ectx.spec_revision_prior_artifact"
      via: "_latest_typed_content(ectx, specify_spec.id) read once before the loop, published for the specify sub-dispatch only, cleared in the existing finally"
      pattern: "spec_revision_prior_artifact = "
    - from: "ectx.spec_revision_prior_artifact"
      to: "backend/agents/execution_engine/engine.py::_compose_context_message"
      via: "a getattr-guarded block rendered immediately BEFORE the existing SPEC KIT ANALYSIS REPORT block"
      pattern: "PRIOR ARTIFACT UNDER REVISION"
    - from: "backend/agents/execution_engine/engine.py::_run_agent thread_id"
      to: "ectx.revision_attempt"
      via: "an f-string :rev{N} suffix appended after the existing :redo{N} suffix, dormant when the field is 0"
      pattern: ":rev\\{"
    - from: "backend/agents/execution_engine/engine.py skip_planner branch (:1763)"
      to: "_rehydrate_planning_context"
      via: "called instead of _default_planning_context when _resuming ONLY — clarify replay is deliberately excluded (see <observations>); degrades to the stub when no durable planning_context ref exists"
      pattern: "_rehydrate_planning_context\\("
    - from: "_rehydrate_planning_context"
      to: "clarify_engine.ClarifyEngine._merge_answers"
      via: "reuse of the single existing merge implementation (INV-12) through an ENGINE-MODULE IMPORT-TIME binding, which is immune to the ClarifyEngine monkeypatch at test_restart_resume.py:3412; fed the durable clarifications rows"
      pattern: "_merge_answers"
---

<objective>
Close three defects in the `update_specs` revision path and the resume path, all in
`backend/agents/execution_engine/`:

- **D1 (primary)** — the spec-revision sub-pipeline tells the spec writer to "preserve
  unchanged sections" but never puts the spec being revised in the prompt. The agent has
  `consumes: []` and `tools: []`, so it has no other channel. Result: a from-scratch,
  shorter spec.
- **D2** — a resumed run rebuilds its planning context from a stub
  (`inferred_intent = user_message[:200]`, every list empty). Measured collapse
  4,591 → 291 chars, affecting 16 of 18 dispatches. Reproduces on Postgres.
- **D3** — the revision re-run reuses the identical checkpoint `thread_id`, so correctness
  silently depends on LangGraph replay; `revision_index` is a dead parameter.

Purpose: the diagnosis is already complete and settled in
`.planning/BUGFIX-SPEC-REVISION-CONTEXT.md`. This plan implements it — nothing is
re-investigated.

Output: two additive `ExecutionContext` scratch fields, three surgical `engine.py` changes,
one new rehydration helper, five new tests (core test written and observed RED first), and a
recorded pre-change baseline so no pre-existing red is misread as a regression.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/BUGFIX-SPEC-REVISION-CONTEXT.md
@CLAUDE.md
@backend/CLAUDE.md

Source sites (already read during planning — the line anchors below are verified against
`bugfix/spec-revision-context-loss` @ `ebdd7fac`; re-read only the ranges you edit):

| Site | Line | What is there |
|------|------|---------------|
| `_run_spec_revision_sub_pipeline` | engine.py:5001-5122 | signature (`revision_index` at :5018, **dead**), `specify_spec = ordered_agents[index - 2]` at :5049, `ectx.spec_revision_context = analysis_report` at :5054, the 3-agent loop at :5059-5114, the `finally` clear at :5116-5118 |
| Revision block renderer | engine.py:8370-8387 | the existing `=== SPEC KIT ANALYSIS REPORT (REVISION CONTEXT) ===` block, guarded by `getattr(ectx, "spec_revision_context", "")` |
| `redo_directive` block | engine.py:8356-8368 | the consume-once precedent to copy |
| `_latest_typed_content` | engine.py:6317-6345 | max-version typed read, `for ref in ectx.artifacts.tree(ectx.run_id)` |
| Sub-pipeline call site A | engine.py:3270-3287 | RESUME-17 gate re-entry consumer (restart-parked gate) |
| Sub-pipeline call site B | engine.py:4296-4313 | live post-stream consumer (the one that fired in the reported run) |
| thread_id construction | engine.py:3526-3540 | base id, then `if redo_attempt: ... :redo{N}` |
| `_seed_gate_reentry_attempts` docstring | engine.py:6374-6395 | line 6379 already (wrongly) claims a `revision_index` thread suffix exists |
| skip-planner branch | engine.py:1761-1773 | `skip_planner = compiled.planner == "skip" or _resuming or _replaying_clarify`; `planning_context = self._default_planning_context(user_message)` at :1765; the `_replaying_clarify` override at :1767-1771 |
| `_default_planning_context` | engine.py:2927-2942 | the stub |
| planning_context persist | engine.py:2895-2904 | `kind="planning_context"`, `producer_agent=PLANNER_AGENT_ID`, content = `json.dumps(planning_context)` |
| artifact hydration on resume | engine.py:1406-1407 | `if _is_resume: await self._hydrate_artifacts_from_store(ectx)` — runs BEFORE :1765 and adopts **all** kinds (`store.tree(run_id)`, unfiltered), so `planning_context` + `clarifications` refs are in `ectx.artifacts` by the time the stub is built |
| planning block renderer | engine.py:8266-8291 | `## Planning Context (Deep Planner Analysis)` / `**Inferred Intent**` / `**Explicit Constraints**` |
| `_merge_answers` | clarify_engine.py:908-963 | pure (the body contains zero `self.` references); appends `f"{question_text} → {answer}"` to `explicit_constraints`, tracks `clarified_topics`, pops `missing_information` |
| `ClarifyEngine.__init__` | clarify_engine.py:177-189 | only fetches the module-singleton `get_artifact_store()` + nulls three attrs — cheap and side-effect-free to construct |
| lazy `ClarifyEngine` import | engine.py:1924 | `from agents.execution_engine.clarify_engine import ClarifyEngine` INSIDE the drain loop — late-bound on purpose; two tests monkeypatch the module attribute and rely on it |
| `_persist_qa` | clarify_engine.py:867-897 | writes `kind="clarifications"`, `producer_agent="clarify-agent"`, `producer_step=f"clarify_round_{n}"`, content = `json.dumps([{question_id, question_text, impact_level, answer, round}, ...])` |
| Test harness | tests/agents/test_redo_gate_safety.py:139-217 | `_EngineHarness` (captures every `create_runner` `thread_id` in `h.thread_ids`), `_make_ectx`, `_drive_agent` |
| Gate re-entry fixtures | tests/agents/test_restart_resume.py:1208-1434 | `_FakeGateRunner`, `_seed_gate_reentry_ectx`, and the three existing gate-reentry tests to mirror |
| Durable-seed pattern | tests/agents/test_restart_resume.py:1470-1517 | `ScopedStore(owner_id, workspace_id, session=session).write_ref(ArtifactRef(...))` |
| Resume-drive pattern | tests/agents/test_restart_resume.py:3336-3430 | `test_offset0_gate_resume_does_not_replan_or_reclarify` — the real resume tier via `_ResumeHarness`; monkeypatches `_clar_mod.ClarifyEngine` → `_FakeClarify` at :3412 |
</context>

<constraints>
Non-negotiable. Violating any of these means the task is not done.

1. **Do NOT fix D1 via `consumes`.** `_filter_consumed_outputs` breaks on
   `upstream.id == spec.id` (engine.py:8180-8182) and specify is `ordered_agents[0]` —
   self-consumption is structurally impossible through that path.
2. **Cover BOTH sub-pipeline call sites** (engine.py:3270 and engine.py:4296). The fix lands
   inside `_run_spec_revision_sub_pipeline`, which both call — but the test MUST exercise
   both entry paths, because the restart scenario that exposed the bug enters via 3270.
3. **Do NOT give the spec writer file tools.** `spec.md` is written by the build step's
   strategy (`task_loop.py:539`) ~1h40m after the revision pass needs it; it does not exist
   on disk at that moment, and a second on-disk copy duplicates `artifact_refs` (INV-3/12).
4. **Do NOT re-run the planner on resume.** Rehydrate, never re-invoke. Re-running regresses
   BUG-R05 (quick 260719-hd5) and turns
   `tests/agents/test_restart_resume.py::test_offset0_gate_resume_does_not_replan_or_reclarify`
   red — that test staying green is an acceptance criterion, not a nice-to-have.
5. **No new storage.** No migration, no new table, no new column, no new artifact kind.
   `artifact_refs` already holds every version durably.
6. **INV-3 dormancy.** Both new injections and the `:rev{N}` suffix must be inert on a normal
   run. The 5 characterization goldens must be byte-identical **to the baseline measured in
   Task 1 on the pre-change commit** — not to any remembered number. Never run the goldens
   with `SNAPSHOT_UPDATE` set.
7. **INV-1 / SC-001.** Key everything on generic scratch fields. The diff must introduce no
   workflow-name or agent-id literal (`prototype-specify`, `prototype-plan`, `od_prototype`,
   `"prototype"`). Follow the `redo_directive` / `spec_revision_context` consume-once
   precedent exactly.
8. **No dual implementations (INV-12).** Reuse `ClarifyEngine._merge_answers`; do not
   re-implement the `f"{q} → {a}"` constraint formatting in the engine.
9. **No bare `except` on the merge.** A swallowed merge failure yields a planning context with
   no clarification answers — the exact silent degradation this fix exists to remove. Narrow
   the catch and log it (Task 3, EDIT 1, point 4).
10. **Scope fence.** Out of scope: artifact-version UI, read-tool access for text-only agents,
   `redo` semantics, the already-fixed `pypdf` extraction issue, clarify-replay rehydration,
   and the second-click `_gate_update_specs` branch at engine.py:3371 (see `<observations>`).
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Record the pre-change baseline, then write the five tests and see them RED</name>
  <files>
    .planning/quick/260811-mxg-fix-update-specs-prior-spec-injection-an/260811-mxg-BASELINE.md,
    backend/tests/agents/test_spec_revision_context.py,
    backend/tests/agents/test_restart_resume.py
  </files>

  <behavior>
    New test 1 — `test_revision_injects_prior_artifact_into_specify_dispatch[live]` and
    `[reentry]` (parametrized over the two gate consumer sites): during a real
    `_run_spec_revision_sub_pipeline`, the `agent_input` event for the specify re-dispatch
    carries a `context_message` containing the seeded prior artifact text AND the analysis
    report.

    New test 2 — `test_revision_prior_artifact_does_not_leak_to_plan_or_analyze`: in the same
    drive, the plan and analyze re-dispatch `context_message`s do NOT contain the prior
    artifact text, and `ectx.spec_revision_prior_artifact` is falsy after the drive returns.
    Assert that field by DIRECT attribute access (`assert not ectx.spec_revision_prior_artifact`),
    NOT via `getattr(ectx, "...", "")` — pre-fix the field does not exist, so direct access
    makes this test a genuine RED (`AttributeError`) instead of passing vacuously on a
    codebase where the injection simply is not implemented yet.

    New test 3 — `test_revision_dispatch_uses_a_fresh_checkpoint_thread`: the sub-pipeline's
    three `create_runner` `thread_id`s all end in `:rev1` and none equals the first pass's
    unsuffixed `{run_id}:{agent_id}`.

    New test 4 — `test_rehydrate_planning_context_rebuilds_planner_and_answers`: given a graph
    holding one `planning_context` ref (rich planner JSON) and two `clarifications` refs,
    `engine._rehydrate_planning_context(ectx, user_message)` returns a dict whose
    `inferred_intent` is the planner's (NOT `user_message[:200]`) and whose
    `explicit_constraints` contain every `question_text → answer` pair; feeding that dict to
    `_compose_context_message` renders them under `**Explicit Constraints**`.

    New test 5 — `test_resume_dispatch_carries_rehydrated_planning_context`: driving the REAL
    resume tier on a run seeded with durable `planning_context` + `clarifications` rows, the
    dispatched `context_message` contains the clarification answer text and does not fall back
    to the truncated stub intent. This is the wiring proof — test 4 alone would pass against a
    helper nobody calls.
  </behavior>

  <action>
STEP 1 — Baseline BEFORE touching anything (constraint 6). Create
`.planning/quick/260811-mxg-fix-update-specs-prior-spec-injection-an/260811-mxg-BASELINE.md`
with a `## PRE-CHANGE BASELINE` heading recording the commit SHA (`git rev-parse HEAD`) and
the verbatim pass/fail summary line of each of:
  - the 5 characterization goldens, run as one invocation;
  - `tests/agents/test_restart_resume.py`;
  - `tests/agents/test_redo_gate_safety.py` and `tests/agents/test_steering_seam.py`;
  - `tests/unit/test_execution_engine.py`;
  - `/opt/homebrew/bin/lint-imports` (record the broken-contract count).
List every currently-failing test id explicitly under a `### Pre-existing reds` sub-heading.
Anything in that list is NOT a regression later; anything not in it is. Do not attempt to fix
pre-existing reds — record and move on. Ignore the remembered "10 failed / 6 passed" figure;
it was measured on `dev` on 2026-07-29 and is stale.

STEP 2 — Create `backend/tests/agents/test_spec_revision_context.py` (tests 1-3).
Reuse the existing harness rather than building a new one: import `_EngineHarness`,
`_drive_agent`, `_text_turn`, `_make_ectx` from `tests.agents.test_redo_gate_safety` and
`ScriptedFakeChatModel` from `tests.agents._scripted_model`, exactly as
`test_restart_resume.py::test_gate_reentry_all_five_actions_post_restart` does (:1261-1307).

Fixture shape for the `[live]` parameter:
  - Build a 3-agent `ordered` list from real text-only specs via `load_agent_spec` — use three
    agents of one pipeline so `index=2` gives `specify=ordered[0]`, `plan=ordered[1]`,
    `analyze=ordered[2]`. Pick them by reading `registry.PIPELINE_AGENTS["user_stories"]` at
    test time (do not hardcode ids in the assertions; capturing them in a local is fine).
  - `ectx = _make_ectx(run_id, gate_agent_ids=[ordered[2].id])` so only the analyzer gates.
  - Seed the prior artifact: `ectx.artifacts.write_ref(run_id=..., owner_id="anon",
    workspace_id="ws", kind="summary", producer_step=ordered[0].id,
    producer_agent=ordered[0].id, task_id=None, content=PRIOR, location=...)` where
    `PRIOR = "PRIOR-SPEC-SENTINEL ## Workflow Completion Checklist"` — a sentinel string no
    scripted model output can produce by accident.
  - Replace `engine._run_review_gate` with a scripted async generator (copy the `_gate` shape
    at test_restart_resume.py:1282-1292). Script: call #0 yields
    `{"type": "_gate_update_specs", "analysis_report": "REPORT-SENTINEL"}`; every later call
    yields nothing (approve). Note the analyzer re-runs INSIDE the sub-pipeline and gates
    again, so the gate is called at least three times — make later calls approve, never
    `IndexError`.
  - Do NOT stub `_run_spec_revision_sub_pipeline` — this test exists to prove what it does.
  - Drive with `_drive_agent(h.engine, ordered[2], ectx, results, ordered, index=2)` and
    collect the returned events.
  - Assert on `[e["data"]["context_message"] for e in events if e["type"] == "agent_input"]`,
    keyed by `e["data"]["agent_id"]` — the composed prompt is observable from the event stream,
    so no extra patching of `_compose_context_message` is needed.

Fixture shape for the `[reentry]` parameter: identical, except arm the RESUME-17 path — set
the `gate_reentry` sentinel the way `_seed_gate_reentry_ectx` does
(test_restart_resume.py:1234-1252), i.e. `ectx.gate_reentry = {"agent_id": ordered[2].id,
"artifact_kind": "summary", "gate_key": f"{run_id}:{ordered[2].id}"}` plus a durable ref for
the analyzer, and attach a `_FakeGateRunner`-shaped stub for the audit/seed reads (import it
from `tests.agents.test_restart_resume` or inline an equivalent). This drives the
engine.py:3270 call site instead of engine.py:4296. Both parameters must make the same
assertions — that is the TRAP-2 guard.

Test 3 asserts on `h.thread_ids` captured by the harness.

STEP 3 — Add tests 4 and 5 to `backend/tests/agents/test_restart_resume.py`, under a new
banner comment block in the file's existing style. Test 4 is a direct unit call on a graph
seeded in-memory. Test 5 mirrors `test_offset0_gate_resume_does_not_replan_or_reclarify`
(:3336) — same `_ResumeHarness` + `_seed_workflow_run` + `_seed_open_review_gate` skeleton —
with the addition of two durable rows written through
`ScopedStore(owner_id, workspace_id, session=session).write_ref(ArtifactRef(...))` following
the pattern at :1470-1517:
  - `kind="planning_context"`, `producer_agent` = the engine's `PLANNER_AGENT_ID` constant
    (import it, do not retype the string), `producer_step="planner"`, content =
    `json.dumps({...})` with a distinctive `inferred_intent` sentinel and non-empty
    `implicit_constraints`;
  - `kind="clarifications"`, `producer_agent="clarify-agent"`,
    `producer_step="clarify_round_1"`, content = `json.dumps([{ "question_id": "r1_q1",
    "question_text": "Which deployment target?", "impact_level": "high",
    "answer": "SPINNAKER-SENTINEL", "round": 1 }])`.
Both new test names must contain the substring `rehydrat` so the `-k rehydrat` RED gate below
selects exactly these two and nothing else.
Capture the dispatched context message by spying `engine._compose_context_message` (wrap the
bound method, record the return value, delegate to the original) — the resume drive stops at
the gate, so relying on emitted `agent_input` events is fragile here.

STEP 4 — Run the new tests and OBSERVE THEM RED. Append a `## RED evidence` section to
`260811-mxg-BASELINE.md` with the verbatim failure line of each of the five. Expected RED
reasons: tests 1/2 fail on the missing prior-artifact text and the missing
`spec_revision_prior_artifact` attribute; test 3 fails because the three thread ids equal the
first pass's; tests 4/5 fail with `AttributeError: 'ExecutionEngine' object has no attribute
'_rehydrate_planning_context'` (test 4) and a missing-sentinel assertion (test 5). An
`AttributeError` raised INSIDE a test body is an acceptable RED for a not-yet-existing
helper/field; a pytest **error** (collection or fixture failure) is NOT — the verify gate
below rejects it. Test 5 must fail on its ASSERTION, not on a fixture error; if it errors
during setup, fix the fixture until the failure is the assertion.

STEP 5 — Commit the tests alone: `test(agents): add RED tests for spec-revision context loss`.
  </action>

  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && S=$(python3.11 -m pytest tests/agents/test_spec_revision_context.py -q 2>&1 | tail -3); echo "$S"; echo "$S" | grep -qiE '[0-9]+ errors?' && { echo "NOT-RED: pytest ERRORED (collection/fixture). An error is not a RED - fix the fixture until the failure is an assertion."; exit 1; }; F=$(echo "$S" | grep -oE '[0-9]+ failed' | grep -oE '^[0-9]+'); P=$(echo "$S" | grep -oE '[0-9]+ passed' | grep -oE '^[0-9]+'); [ "${F:-0}" -ge 3 ] && [ "${P:-0}" -eq 0 ] && echo "RED-OK ($F assertion failures, 0 passed, 0 errors)" || { echo "NOT-RED: expected at least 3 failed and 0 passed, got failed=${F:-0} passed=${P:-0}"; exit 1; }</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && S=$(python3.11 -m pytest tests/agents/test_restart_resume.py -q -k rehydrat 2>&1 | tail -3); echo "$S"; echo "$S" | grep -qiE '[0-9]+ errors?' && { echo "NOT-RED: pytest ERRORED rather than failed"; exit 1; }; echo "$S" | grep -q "2 failed" && ! echo "$S" | grep -q " passed" && echo "RED-OK (2 failed, 0 passed, 0 errors)" || { echo "NOT-RED: expected exactly '2 failed' and no passing test in the -k rehydrat selection"; exit 1; }</automated>
    <automated>B=/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.planning/quick/260811-mxg-fix-update-specs-prior-spec-injection-an/260811-mxg-BASELINE.md; grep -q "PRE-CHANGE BASELINE" "$B" && grep -q "Pre-existing reds" "$B" && [ "$(awk '/^## RED evidence/{f=1;next} /^## /{f=0} f && NF' "$B" | wc -l | tr -d ' ')" -ge 5 ] && echo "BASELINE-OK" || { echo "BASELINE-INCOMPLETE: need the pre-change summary, an explicit pre-existing-reds list, and at least 5 non-blank lines of verbatim RED output UNDER the '## RED evidence' heading"; exit 1; }</automated>
  </verify>

  <done>
    BASELINE.md records the pre-change SHA, the pass/fail summary of all five verification
    commands, an explicit list of pre-existing reds, and the verbatim RED output of all five
    new tests. Five new tests exist, all fail, and each fails for the documented reason — an
    assertion or an `AttributeError` inside the test body, never a collection/fixture error.
    Committed as a test-only commit.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement F1 (prior-artifact injection) and F3 (fresh revision thread)</name>
  <files>
    backend/agents/execution_engine/context.py,
    backend/agents/execution_engine/engine.py
  </files>

  <behavior>
    Tests 1, 2 and 3 from Task 1 flip to GREEN. The 5 characterization goldens stay identical
    to the Task 1 baseline (both new mechanisms are dormant when their scratch fields are
    empty/zero).
  </behavior>

  <action>
EDIT 1 — `context.py`: declare two additive fields immediately after `redo_directive`
(:278), in the same documented style as its neighbours. `ExecutionContext` is a plain
non-slots `@dataclass`, so the existing `spec_revision_context` works undeclared — declare the
new ones properly anyway, and say in the comment that they join the consume-once injection-seam
family (`redo_directive` / `spec_revision_context` / `steering_notes`), that they are
default-empty ⇒ dormant ⇒ INV-3 byte-parity holds, and that they are transient per-run scratch
(INV-2, never the engine singleton):

  - `spec_revision_prior_artifact: str = ""` — the prior version of the artifact the revision
    pass is rewriting, published for exactly one dispatch.
  - `revision_attempt: int = 0` — the sub-pipeline's revision index, published so `_run_agent`
    can derive a fresh checkpoint thread. Mirrors `_run_agent`'s `redo_attempt` local; named
    distinctly from that function's `spec_revision_attempt` local to avoid shadowing confusion.

EDIT 2 — `engine.py::_compose_context_message`: add the new block IMMEDIATELY BEFORE the
existing `=== SPEC KIT ANALYSIS REPORT (REVISION CONTEXT) ===` block (insert before :8377),
so the agent reads the subject before the instructions. Leave the existing block's bytes
untouched. Copy the guard idiom verbatim:

    prior_artifact = getattr(ectx, "spec_revision_prior_artifact", "") or ""
    if prior_artifact:
        parts.append(
            "\n=== PRIOR ARTIFACT UNDER REVISION ===\n"
            "This is YOUR OWN previous output for this run — the document the analysis "
            "report below refers to. Revise THIS document in place: reproduce every "
            "section the report does not call out, verbatim, and change only what the "
            "report identifies. Do NOT regenerate from scratch and do NOT drop sections "
            "you were not asked to change.\n\n"
            f"{prior_artifact}\n"
            "=== END PRIOR ARTIFACT UNDER REVISION ==="
        )

Add a comment above it in the house style recording: why it exists (the agent has
`consumes: []` + `tools: []`, so this is its only channel); that it is keyed on the generic
scratch field, no workflow/agent literal (SC-001); and that it is dormant on every normal run
(INV-3). Cost note: ~11k tokens per revision pass.

EDIT 3 — `engine.py::_run_spec_revision_sub_pipeline` (:5049-5118):
  - after `analyze_spec = spec` (:5051), read the prior artifact once:
    `prior_artifact = self._latest_typed_content(ectx, specify_spec.id) or ""`
    (this is the max-version typed read — F5 discipline — so it returns spec v1, not a stale
    insertion-order ref);
  - beside `ectx.spec_revision_context = analysis_report` (:5054), publish the thread index:
    `ectx.revision_attempt = revision_index` — this is what makes the previously-dead
    `revision_index` parameter live (D3);
  - inside the loop, immediately before the `async for event in self._run_agent(` call
    (:5078), publish the prior artifact for the specify dispatch ONLY:
    `ectx.spec_revision_prior_artifact = prior_artifact if sub_spec is specify_spec else ""`.
    Identity comparison against `specify_spec`, not an id string (INV-1). This is the no-leak
    guarantee test 2 asserts;
  - in the existing `finally` (:5116-5118), clear both new fields alongside
    `spec_revision_context`: `ectx.spec_revision_prior_artifact = ""` and
    `ectx.revision_attempt = 0`. The `finally` already covers the cancel/error/return paths, so
    consume-once holds for every exit;
  - update the docstring (:5020-5035) to state that the specify re-dispatch receives its prior
    output and that the sub-pipeline runs on `:rev{N}` threads.

EDIT 4 — `engine.py::_run_agent` thread id (:3539-3540): after the existing redo suffix, append

    _rev = getattr(ectx, "revision_attempt", 0) or 0
    if _rev:
        thread_id = f"{thread_id}:rev{_rev}"

with a comment mirroring the redo one: a revision re-run MUST get a fresh checkpoint thread,
else the checkpointer replays the prior turn and the model "remembers" the pre-revision
document instead of rewriting it — the same class as the `:redo{N}` and `:retry{n}` fixes.
Latent case this also closes: redo-then-update_specs previously revised the REJECTED draft
(redo ran on `:redo1`, update_specs re-ran on the base thread). Dormant when the field is 0 ⇒
goldens byte-identical.

EDIT 5 — `engine.py:6379` docstring: it already claims a `revision_index` thread suffix
exists. Correct the wording to `` `:redo{N}` / `:rev{N}` `` so it now describes reality — the
`_seed_gate_reentry_attempts` fail-safe-high seeding of `spec_revision_attempt` finally has a
thread id to protect.

Do NOT touch the `consumes`/`produces` of any AGENT.md, do not add tools to any agent, and do
not modify the `_gate_update_specs` branch at engine.py:3371 (out of scope — see
`<observations>`).
  </action>

  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_spec_revision_context.py -q</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py -q 2>&1 | tail -5</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_redo_gate_safety.py tests/agents/test_steering_seam.py -q 2>&1 | tail -5</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin && git diff -U0 -- backend/agents/execution_engine/engine.py backend/agents/execution_engine/context.py | grep '^+' | grep -v '^+++' | grep -v '^+ *#' | grep -Ec 'prototype-specify|prototype-plan|od_prototype|"prototype"' || echo "SC-001-OK (0 workflow/agent literals added)"</automated>
  </verify>

  <done>
    All three tests in `test_spec_revision_context.py` pass, including BOTH the `[live]` and
    `[reentry]` parameters. The characterization golden result is identical to the Task 1
    baseline (same passed/failed counts, same failing ids). `test_redo_gate_safety.py` and
    `test_steering_seam.py` are unchanged from baseline. The diff adds zero workflow/agent-id
    literals. Committed as `fix(engine): inject the prior artifact into the revision dispatch`.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Implement F2 (resume planning-context rehydration) and run the full regression</name>
  <files>
    backend/agents/execution_engine/engine.py,
    .planning/quick/260811-mxg-fix-update-specs-prior-spec-injection-an/260811-mxg-BASELINE.md
  </files>

  <behavior>
    Tests 4 and 5 from Task 1 flip to GREEN while
    `test_offset0_gate_resume_does_not_replan_or_reclarify` stays GREEN — together those prove
    the context was rehydrated rather than regenerated.
  </behavior>

  <action>
EDIT 1 — add `_rehydrate_planning_context(self, ectx, user_message: str) -> dict` to
`engine.py`, placed next to `_default_planning_context` (:2927). Contract:

  1. Find the max-version `planning_context` ref for this run by iterating
    `ectx.artifacts.tree(ectx.run_id)` and filtering `ref.kind == "planning_context"`, taking
    the highest `version` (tie-broken by later insertion, `>=`) — the same idiom as
    `_latest_typed_content` (:6339-6345). Do not add a new store read: the resume path already
    hydrated every durable ref into the graph at :1406-1407, unfiltered by kind.
  2. If none is found, `return self._default_planning_context(user_message)` — unchanged
    behaviour, so a `compiled.planner == "skip"` run, an offline test, or any run predating
    the persist degrades exactly to today (INV-3 dormancy by construction).
  3. `json.loads` the content into `base`. On any parse failure, log a warning and fall back to
    the stub — this helper must never raise into the run.
  4. Re-merge the durable clarification rounds: collect the `clarifications` refs for this run,
    order them by `version`, `json.loads` each into its `qa_pairs` list, and for each round call
    the EXISTING merge (INV-12, constraint 8), shaping
    `questions = [{"question_id": p["question_id"], "question_text": p["question_text"]}
    for p in pairs]` and `responses = [{"question_id": p["question_id"], "answer": p["answer"]}
    for p in pairs if p.get("answer")]`.
     - **Bind `ClarifyEngine` at engine-module IMPORT time — not inside the helper.** Add
       `from agents.execution_engine.clarify_engine import ClarifyEngine as _ClarifyEngineImpl`
       to engine.py's top-level import block beside the other `agents.execution_engine.*`
       imports (:72-75), construct ONE instance before the round loop, and call
       `_merge_answers(base, questions, responses)` on it.
       Why import-time and not a local import: `test_offset0_gate_resume_does_not_replan_or_reclarify`
       runs `monkeypatch.setattr(_clar_mod, "ClarifyEngine", _FakeClarify)`
       (test_restart_resume.py:3412) and `_FakeClarify` has no `_merge_answers`. A late-bound
       `from ... import ClarifyEngine` inside the helper resolves that patched module attribute
       at call time and would pick up the fake; an import-time binding cannot. This REMOVES the
       trap rather than tolerating it. Verified safe: `clarify_engine.py` imports no engine
       module (no cycle), and grimp already records the `engine → clarify_engine` edge from the
       existing function-level import at :1924, so the top-level binding crosses no new
       import-linter contract (`lint-imports` parity is still gated in STEP 3).
     - **Do NOT remove or alter the existing lazy import at engine.py:1924.** The live clarify
       invocation MUST keep late-binding: `_FakeClarify` (:3412) and `_ParkingClarify` (:3652)
       both depend on patching the module attribute. Two bindings with deliberately different
       resolution timing is not a dual implementation (there is still exactly one
       `ClarifyEngine` and one `_merge_answers`) — say precisely that in a comment on the new
       top-level import so a later reader does not "tidy" one of them away.
     - `_merge_answers` is genuinely self-free (clarify_engine.py:908-963 contains zero `self.`
       references) and `ClarifyEngine.__init__` only fetches the module-singleton artifact store,
       so constructing an instance purely to reach the method is cheap and side-effect-free.
     - **Make the merge idempotent**: skip any pair whose rendered constraint string
       (`f"{question_text} → {answer}"`) is already in `base["explicit_constraints"]`. This
       makes the helper safe to call against a base that already contains merged answers and
       removes any double-count risk.
     - **Guard NARROWLY (constraint 9)**: wrap only the merge call in
       `except (AttributeError, TypeError, KeyError)`, log with
       `logger.warning("...", exc_info=True)`, and keep the unmerged base. That catch exists for
       exactly one thing: a malformed durable row whose JSON parses but whose shape is wrong. A
       bare `except` is forbidden here — it would silently yield a planning context with no
       clarification answers, reproducing the very silent-degradation class this fix removes.
  5. Normalize `base["execution_gate"] = "PROCEED"` before returning: a resumed run is
    mid-build, and the persisted planner row may carry a stale `CLARIFY_REQUIRED` that must not
    leak to any consumer. The caller's `gate_verdict` local is unchanged, and the
    `_replaying_clarify` branch at :1767-1771 is untouched (it never reaches this helper — see
    EDIT 2).
  6. Log ONE `logger.info` line recording what was reconstructed — number of clarification
    rounds merged, count of `explicit_constraints`, and the char length of the JSON base. This
    is the observability whose absence let a 4,591 → 291 char collapse ship silently.
  7. **Record the reconstruction's known lossiness in the helper's docstring.** `_persist_qa`
    (clarify_engine.py:867-884) writes the raw `responses` map BEFORE `_merge_answers`
    (:931-938) auto-fills a `recommended_answer` for unanswered questions, and persists neither
    `recommended_answer` nor `ambiguity_category`. Consequence, stated explicitly: answered
    questions reconstruct exactly; questions the user SKIPPED cannot have their auto-filled
    constraints recovered, and `clarified_topics` comes back empty. Name the deliberately
    untaken alternative (persist the merged context as a new `planning_context` version on the
    clarify path, at the cost of a write on that path) so the next reader does not re-derive it.

EDIT 2 — wire it at the skip-planner branch (:1763-1766). Replace the unconditional stub call
with:

    planning_context = (
        self._rehydrate_planning_context(ectx, user_message)
        if _resuming
        else self._default_planning_context(user_message)
    )

Gate on `_resuming` ONLY — do NOT include `_replaying_clarify`. The brief scopes D2 to
restart-resume. On a clarify replay the durable rows exist but the questions are about to be
RE-ASKED, so injecting the previously-merged answers into that prompt is a behaviour change no
source artifact analysed. Narrowing also keeps BOTH the `compiled.planner == "skip"` path and
the clarify-replay path byte-identical, which is the whole INV-3 dormancy argument. This is a
strict narrowing with no ambiguous overlap: the two flags cannot co-occur — the clarify-replay
drive passes `_is_resume=False` (:8108) while the resume drive passes `_clarify_replay=None`
(:7794-7795). Logged as a deliberate, known gap in `<observations>`; if clarify replay ever
needs rehydration it is a follow-up with its own analysis, not a widened condition here.

Leave `planning_context["pipeline_type"] = pipeline_type` and the `_replaying_clarify` override
at :1767-1771 unchanged. Add a comment stating: the planner is still NOT re-invoked (TRAP 4 /
BUG-R05 / quick 260719-hd5 — `test_offset0_gate_resume_does_not_replan_or_reclarify` guards
this); RESUME-04 hydration (:1406) already put the durable rows in the graph, so this is a pure
read; and both non-resume paths through this branch are byte-identical.

STEP 3 — full regression. Run every command from the Task 1 baseline again and diff the
results against `260811-mxg-BASELINE.md`. Append a `## POST-CHANGE RESULTS` section with the
same structure plus an explicit `baseline-red / new-red / newly-green` classification for every
non-passing test. Any test that is red now and was not red in the baseline blocks completion.

STEP 4 — append the deferred live-acceptance recipe to `260811-mxg-BASELINE.md` under
`## Deferred: live Bedrock acceptance (end-of-milestone)`, verbatim from section 5 of the
brief, so the later live pass has an oracle:
  - the model is stochastic, so assert PROPERTIES against the DB, not exact text;
  - pull `spec` v1 and v2 from `artifact_refs` via
    `GET /api/runs/{id}/artifacts?kind=spec&include=content` — NOT through the UI, because the
    FE keeps one slot per agent id and `agent_start` wipes `output: ""` (FIX-039,
    `useWorkflow.ts`), erasing v1 from the screen the moment the revision starts;
  - the four assertions, all of which FAIL on the reported run and so form a real before/after
    oracle: `headings(v2) ⊇ headings(v1)` (was 19 vs 27); `"Spinnaker" in v2` (was 0 hits);
    `"Workflow Completion Checklist" in v2` (was absent); `len(v2) >= len(v1)`
    (was 39,115 < 43,670);
  - run it three times — one pass on a stochastic model proves nothing.

STEP 5 — commit: `fix(engine): rehydrate planning context on resume`. Reference the brief and
the D1/D2/D3 ids in the commit body. Do not push.
  </action>

  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_restart_resume.py -q 2>&1 | tail -5</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_restart_resume.py::test_offset0_gate_resume_does_not_replan_or_reclarify -q</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_spec_revision_context.py tests/agents/test_redo_gate_safety.py tests/agents/test_steering_seam.py tests/unit/test_execution_engine.py -q 2>&1 | tail -5</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py -q 2>&1 | tail -5</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && /opt/homebrew/bin/lint-imports 2>&1 | tail -5</automated>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -c "import sys,re; s=open('agents/execution_engine/engine.py').read(); i=s.find('def _rehydrate_planning_context'); assert i!=-1, 'helper not found'; body=s[i:]; j=body.find('\n    def ',1); body=body[:j] if j!=-1 else body; ok1='except (AttributeError, TypeError, KeyError)' in body; ok2=not re.search(r'\n\s*except\s*:', body); print('narrow-except:',ok1,'no-bare-except:',ok2); sys.exit(0 if (ok1 and ok2) else 1)" && echo "NARROW-EXCEPT-OK"</automated>
    <automated>B=/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.planning/quick/260811-mxg-fix-update-specs-prior-spec-injection-an/260811-mxg-BASELINE.md; grep -q "Deferred: live Bedrock acceptance" "$B" && [ "$(awk '/^## POST-CHANGE RESULTS/{f=1;next} /^## /{f=0} f && NF' "$B" | wc -l | tr -d ' ')" -ge 5 ] && grep -qE "baseline-red|new-red|newly-green" "$B" && echo "EVIDENCE-OK" || { echo "EVIDENCE-INCOMPLETE: POST-CHANGE RESULTS must carry the per-command results AND an explicit baseline-red / new-red / newly-green classification"; exit 1; }</automated>
  </verify>

  <done>
    All five new tests pass. `test_offset0_gate_resume_does_not_replan_or_reclarify` passes.
    The rehydrator is wired on `_resuming` ONLY (no `_replaying_clarify` in the condition), its
    `ClarifyEngine` binding is the engine-module import-time one, the merge guard names
    `(AttributeError, TypeError, KeyError)` explicitly with `exc_info=True` logging, and the
    helper's docstring records the `_persist_qa` skipped-question lossiness. The
    characterization goldens and `lint-imports` match the Task 1 baseline exactly (same counts,
    same ids — no new red). BASELINE.md carries the post-change comparison with every
    non-passing test classified, plus the deferred live-acceptance recipe. Two implementation
    commits exist on `bugfix/spec-revision-context-loss`; nothing is pushed.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| durable `artifact_refs` → LLM prompt | previously-stored, owner-scoped content (a prior spec, the user's own clarification answers) is re-rendered into a model prompt |
| resumed process → in-memory run context | state is reconstructed from the DB rather than from live process memory |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-mxg-01 | Information disclosure | `_rehydrate_planning_context` / `_latest_typed_content` reads | mitigate | Read only through `ectx.artifacts` for `ectx.run_id`, populated by the OWNER-SCOPED `ScopedStore.tree()` hydration at engine.py:1406-1407. No new store call, no cross-run or cross-owner read path is introduced. |
| T-mxg-02 | Tampering (prompt injection) | the two new prompt blocks | accept | Both carry content this same run already produced (its own prior artifact) or the user's own clarification answers — content that already reaches these agents by other channels. No new external input crosses the boundary; the delta is re-presentation of first-party run data. |
| T-mxg-03 | Denial of service | prompt size growth | accept | Bounded and measured: ~11k tokens per revision pass, and only during a revision. Dormant on every normal dispatch. |
| T-mxg-SC | Tampering | npm/pip/cargo installs | n/a | No dependency is added or changed by this plan. |
</threat_model>

<observations>
Recorded during planning, deliberately NOT in scope — do not act on these, and do not let them
grow the diff:

- **A third `_gate_update_specs` branch exists** at engine.py:3371, inside the
  `pending_revision_output` gate re-open path. It is NOT a `_run_spec_revision_sub_pipeline`
  call site — it only re-seeds `ectx.spec_revision_pending_output` and breaks (the engine's own
  comment at :3179-3183 documents this deliberate deviation). Consequence: clicking
  "Update the Specs" a SECOND time at the re-opened gate appears not to run the sub-pipeline at
  all. That is consistent with the brief's "two consumer sites" (both sub-pipeline call sites
  are covered by this plan) but looks like a separate latent defect worth its own card.
- **The `clarifications` rows are lossy for skipped questions.** `_persist_qa`
  (clarify_engine.py:867-884) writes the raw `responses` answer map, while `_merge_answers`
  (:931-938) auto-fills a `recommended_answer` for unanswered questions AFTER that write. Neither
  `recommended_answer` nor `ambiguity_category` is persisted, so a reconstruction cannot recover
  the auto-filled constraints for questions the user skipped, and `clarified_topics` comes back
  empty. Answered questions reconstruct exactly. The brief's alternative (persist the merged
  context as a new `planning_context` version post-clarification) would close this, at the cost
  of a write on the clarify path; it is deliberately not taken here. This limitation IS acted on
  in exactly one way — Task 3, EDIT 1, point 7 requires it in the helper's docstring — and in no
  other way.
- **Clarify replay is deliberately excluded from F2 (known gap, not an oversight).** EDIT 2
  gates the rehydrator on `_resuming` alone; `_replaying_clarify` keeps
  `_default_planning_context`. Rationale: on a replay the durable rows exist, but the questions
  are about to be re-asked, so feeding previously-merged answers into that prompt is a
  behaviour change no source artifact analysed. The two flags never co-occur (the replay drive
  passes `_is_resume=False` at :8108; the resume drive passes `_clarify_replay=None` at
  :7794-7795), so this is a clean narrowing. If a replayed clarify round is later found to need
  the rich context, that is a follow-up card with its own analysis.
</observations>

<verification>
1. Every one of the five new tests passes, and each was observed RED first with its failure
   recorded verbatim in BASELINE.md — as an assertion or in-test `AttributeError`, never as a
   pytest collection/fixture error.
2. The D1 test passes for BOTH the `[live]` and `[reentry]` parameters (TRAP 2).
3. `test_offset0_gate_resume_does_not_replan_or_reclarify` is green (TRAP 4 — proves
   rehydration, not re-invocation), and it is green because the `ClarifyEngine` binding is
   import-time, not because an exception was swallowed.
4. The 5 characterization goldens and `lint-imports` are identical to the pre-change baseline
   measured in Task 1. No result is compared against a remembered figure.
5. `git diff` adds no workflow-name or agent-id literal, no migration, no new table/column, no
   new artifact kind, no bare `except`, and no `consumes`/`tools` change to any AGENT.md.
6. Live Bedrock verification is explicitly deferred; its recipe is recorded in BASELINE.md.
</verification>

<success_criteria>
- A revision dispatch's prompt contains the prior artifact — measurable as the sentinel string
  appearing in the specify `agent_input.context_message`, and absent from the plan/analyze ones.
- A resumed dispatch's prompt contains the clarification answers — measurable as the answer
  sentinel appearing in the composed message, with the intent no longer equal to
  `user_message[:200]`.
- The revision dispatch's `thread_id` ends in `:rev1` and differs from the first pass's.
- Dormancy proven by golden parity against the Task 1 baseline, on the normal run AND on the
  clarify-replay path (which F2 does not touch).
- Three commits on `bugfix/spec-revision-context-loss` (tests RED, F1+F3, F2), nothing pushed.
</success_criteria>

<output>
Create `.planning/quick/260811-mxg-fix-update-specs-prior-spec-injection-an/260811-mxg-SUMMARY.md`
when done, including: the baseline-vs-post comparison table, the RED→GREEN evidence for each of
the five tests, and a pointer to the deferred live-acceptance recipe.
</output>
