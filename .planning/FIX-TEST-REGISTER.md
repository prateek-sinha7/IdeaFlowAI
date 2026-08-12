# Fix-Test Register — VelocityAI / Flowin

> **Purpose.** Every test suite written via `/velocity-ai-test` is logged here, linked to its Fix ID from `FIX-REGISTER.md`. Read this before writing new tests to avoid duplicating existing coverage.
>
> **How to use:** Each entry is keyed by Fix ID. When a fix is tested, a TEST-NNN entry is added here referencing the FIX-NNN from `FIX-REGISTER.md`.

---

## Summary Table

| Test ID | Fix ID | Date | Files Tested | Tests Written | Passed | Failed | Status |
|---------|--------|------|--------------|---------------|--------|--------|--------|
| TEST-001 | FIX-001 (KAN-76) | 2026-06-22 | `backend/tests/unit/test_prompt_overrides.py` | 21 | 21 | 0 | ✅ Pass |
| TEST-002 | FIX-002 (KAN-75) | 2026-06-22 | `backend/tests/unit/test_catalogue_nav.py` | 7 | 7 | 0 | ✅ Pass |
| TEST-003 | FIX-217 (quick-260811-mxg) | 2026-08-11 | `backend/agents/execution_engine/engine.py`, `backend/agents/execution_engine/context.py` | 11 | 11 | 0 | ✅ Pass |
| TEST-004 | FIX-218 (quick-260811-si4) | 2026-08-11 | `backend/agents/execution_engine/engine.py`, `backend/agents/execution_engine/context.py` | 8 | 8 | 0 | ✅ Pass |
| TEST-005 | FIX-219 (quick-260812-12t) | 2026-08-12 | `backend/agents/execution_engine/engine.py`, `backend/agents/capabilities/gates/human.py`, `backend/agents/capabilities/gates/approval.py`, `backend/app/api/run_engine.py`, `backend/app/api/run_commands.py` | 18 | 18 | 0 | ✅ Pass |
| TEST-006 | FIX-220 (quick-260812-1nz) | 2026-08-12 | `backend/agents/execution_engine/engine.py`, `backend/tests/agents/characterization/_normalize.py`, `frontend/src/components/chat/InlineGateActions.tsx`, `frontend/src/components/layout/DashboardLayout.tsx`, `frontend/src/components/results/StepsOverviewSpine.tsx` | 8 | 8 | 0 | ✅ Pass |
| TEST-007 | FIX-221 + FIX-222 (quick-260812-2ci) | 2026-08-12 | `frontend/src/hooks/useWorkflow.ts`, `frontend/src/hooks/useRunStateStore.ts`, `frontend/src/app/dashboard/page.tsx`, `frontend/src/types/index.ts`, `frontend/src/components/results/ArtifactVersionPicker.tsx`, `frontend/src/components/results/AgentDetailPanel.tsx`, `frontend/src/components/results/AgentThinkingTab.tsx` | 27 | 27 | 0 | ✅ Pass |
| TEST-008 | FIX-223 + FIX-224 (quick-260812-35u) | 2026-08-12 | `backend/tests/agents/test_loader.py`, `backend/tests/agents/test_banned_patterns.py`, `backend/tests/agents/characterization/_normalize.py`, `backend/agents/prompts/prototype-build/AGENT.md`, `backend/agents/capabilities/strategies/task_loop.py`, `backend/tests/agents/characterization/golden/prototype_revision.events.json` | 4 | 4 | 0 | ✅ Pass |
| TEST-009 | FIX-225 (quick-260812-4ss) | 2026-08-12 | `frontend/src/hooks/useWorkflow.ts`, `frontend/src/hooks/useRunStateStore.ts`, `frontend/src/app/dashboard/page.tsx`, `frontend/src/types/index.ts` | 12 | 12 | 0 | ✅ Pass |
| TEST-010 | FIX-226 (quick-260812-77g) | 2026-08-12 | `frontend/src/components/results/AgentDetailPanel.tsx` | 4 | 4 | 0 | ✅ Pass |
| TEST-011 | FIX-227 (quick-260812-7sk) | 2026-08-12 | `backend/agents/execution_engine/engine.py`, `backend/app/api/run_engine.py`, `backend/app/main.py`, `backend/app/api/run_commands.py`, `backend/app/api/run_shutdown.py` | 9 | 9 | 0 | ✅ Pass |
| TEST-012 | FIX-228 (quick-260812-8j4) | 2026-08-12 | `backend/agents/execution_engine/engine.py`, `backend/agents/execution_engine/context.py` | 11 | 11 | 0 | ✅ Pass |
| TEST-013 | FIX-229 (quick-260812-97f) | 2026-08-12 | `backend/app/api/run_commands.py`, `backend/tests/agents/test_restart_resume.py` | 60 | 60 | 0 | ✅ Pass |
| TEST-014 | FIX-230 (quick-260812-9tq) | 2026-08-12 | `backend/tests/agents/test_iss033a_fixloop_token_fold_offline.py`, `backend/tests/unit/test_handoff_agents.py`, `backend/tests/agents/test_model_pricing.py` | 8 | 8 | 0 | ✅ Pass |

---

## Detailed Test Entries

### TEST-006 — FIX-220 (quick-260812-1nz): the doubled analyze gate is identifiable

```
TEST COVERAGE — FIX-220
Unit tests:        6 NEW in backend/tests/agents/test_gate_revision_discriminator.py
                   RED FIRST, observed and recorded, never assumed:
                     6 failed -> 6 passed
                   Each failed for its own reason, not one shared import error:
                     stamp vector      [(None,None) x3]  -> [(0,False),(1,True),(1,False)]
                     second cycle      [None x5]         -> [0,1,1,2,2]
                     real gate         TypeError: unexpected kwarg 'revision_cycle'
                     declared default  "expected a 0 default; got None"
                     SC-001 grep       "the discriminator never appears in engine.py"
                     strip-set guard   'revision_cycle' not in _VOLATILE_STRIP_KEYS
Integration tests: N/A — the defect is EVENT SHAPE plus FE state. Test 3 drives the REAL
                   _run_review_gate offline and reads the emitted review_gate_ready payload,
                   which is byte-for-byte what the SSE layer re-emits (run_stream.py:244
                   forwards payload_json verbatim), so an integration tier would re-assert
                   the same bytes one hop later. Live Bedrock acceptance DEFERRED
                   (end-of-milestone rule); the live check is one query —
                   SELECT revision_cycle, revision_in_flight FROM the run's
                   review_gate_ready rows must read (0,f)/(N,t)/(N,f).
Frontend tests:    2 NEW in frontend/src/components/chat/InlineGateActions.test.tsx,
                   both seen RED first. The first is the load-bearing one and covers a hole
                   the investigation flagged as UNTESTED: the reset effect's deps were
                   [output, gateKey] and NEITHER changes between the in-pass and re-opened
                   firings, so the one-action `submitted` latch stayed stuck and the second
                   gate rendered with every action disabled.
                   File went 1 failed / 13 passed -> 1 failed / 15 passed. The 1 red is
                   PRE-EXISTING and proven so, not labelled so: the same file measured
                   1 failed / 13 passed in a detached worktree at 28c0111c. It is
                   "renders exactly two primary buttons", which asserts the update-specs
                   button is collapsed under "Request changes" while the component
                   deliberately elevates it (:255-269). Filed as ISS-073.
Goldens:           5 failed / 5 passed — IDENTICAL counts AND identical failing ids at the
                   pre-change commit 28c0111c and after (prototype, od_prototype, od_ppt,
                   app_builder, prototype_revision event snapshots). NO golden regenerated;
                   `git status` on characterization/golden/ is clean.
                   As with FIX-219, note WHY they cannot move: all 10 golden files contain
                   ZERO review_gate_ready events (gate_agent_ids=[], _scripted_model.py:649),
                   so they are structurally blind to any _run_review_gate change. Golden
                   silence is NOT evidence here — INV-3 is proven by the strip-set guard and
                   the dormancy defaults instead.
lint-imports:      3 kept / 1 broken — IDENTICAL at 28c0111c. The broken contract is the
                   pre-existing agents.capabilities -> execution_engine.od_context ->
                   app.services.od_loader chain, untouched here.
Adjacent suites:   All measured in a DETACHED WORKTREE at 28c0111c, both sides, not assumed:
                     ISS-053 set (spec_revision_cycles, update_specs_enforcement,
                       update_specs_ingress_fence, sc001_gate_flag) 32 passed.
                     engine-adjacent (redo_gate_safety, steering_seam, restart_resume,
                       spec_revision_context, execution_engine)
                       10 failed / 76 passed BEFORE and AFTER, same ids.
                     wider gate surface (declared_gate_streaming, gates, sc001_gate_flag,
                       task_list_gate_lineage, approve_review_ownership, rest_gate_commands,
                       sc001_fanout, phase5_revision_validation, chunk_sanitizer,
                       sample_brownfield_workflow, iss033_aux_token_fold)
                       8 failed / 92 passed BEFORE and AFTER, same ids.
                     full frontend vitest 147 failed / 779 passed -> 147 failed / 781 passed
                       — same 29 failed files; +2 = exactly this fix's new cases.
                     tsc --noEmit: identical 2 pre-existing errors both sides.
                   MID-WORK REGRESSION, caught by that baselining and fixed: the first run
                   of the engine-adjacent sweep was 17 failed / 69 passed (+7). Three
                   `_gate` stubs in test_restart_resume.py (:1282/:1360/:1407) have FIXED
                   signatures and raised TypeError on the new kwargs. Given `**kwargs` —
                   the idiom the sibling stubs in test_spec_revision_cycles.py and
                   test_redo_gate_safety.py already document — the sweep returned to the
                   baseline 10 / 76. Test-only; no production diff.
Regression guards:
  - test_each_gate_firing_carries_a_distinct_revision_stamp (NEW): the load-bearing one.
    Drives a REAL revision cycle and asserts the three firings publish
    (0,False)/(1,True)/(1,False) AND that the three are pairwise distinct. It also pins
    the specific property the FE depends on — the in-pass and re-opened gates share a
    cycle and are separated by the in-flight flag ALONE — so a future change that drops
    revision_in_flight as "redundant with revision_cycle" fails here rather than silently
    re-sticking the latch.
  - test_a_second_cycle_advances_the_published_cycle_index (NEW): [0,1,1,2,2] over two
    sibling cycles. This is the DURABLE per-cycle signal ISS-063 must consume instead of
    inventing a third counter; the assertion is what stops it drifting.
  - test_real_gate_stamps_the_discriminator_on_review_gate_ready (NEW): its sibling
    test_spec_revision_cycles.py stubs _run_review_gate out entirely, so without this the
    engine could pass the values correctly and never publish them.
  - test_gate_defaults_the_discriminator_for_the_declared_path (NEW): the declared /
    user-composed gate path reaches the primitive through run_human_gate, which passes
    neither key. Pins (0, False) — truthful AND the value that renders no badge — and pins
    redoable=False alongside it so a signature change cannot make one default true.
  - test_discriminator_introduces_no_agent_id_literal (NEW): SC-001 source grep over every
    engine line mentioning either key — no `prototype-` literal, no `pipeline_type` branch.
    Mirrors test_eligibility_introduces_no_agent_id_literal.
  - test_discriminator_keys_are_in_volatile_strip_set (NEW): INV-3. Mirrors
    test_new_keys_are_in_volatile_strip_set, which is the guard that DEMANDED this entry.
  - ISS-052: re-arms the one-action latch ... (NEW, frontend): approve at the in-pass gate,
    then re-render with the SAME output and SAME gateKey and only the stamp moved; the
    approve control must be live again and fire a second time. Fails on the pre-fix
    dependency array.
  - ISS-052: names the revision cycle ... (NEW, frontend): the badge is ABSENT at cycle 0
    (dormancy for every non-revision gate) and reads DIFFERENTLY in-pass vs re-opened while
    naming the same cycle number.
  - test_spec_revision_cycles.py (5, FIX-218) + test_update_specs_enforcement.py (5,
    FIX-219) + test_update_specs_ingress_fence.py (13, FIX-219): all unchanged and green.
    In particular the ISS-053 409 path is untouched — this fix adds keys, it changes no
    verdict.
```

### TEST-005 — FIX-219 (quick-260812-12t): update_specs eligibility is enforced

```
TEST COVERAGE — FIX-219
Unit tests:        18 total, ALL GREEN
                     5 NEW in backend/tests/agents/test_update_specs_enforcement.py
                    13 NEW in backend/tests/unit/test_update_specs_ingress_fence.py
                   RED FIRST, observed and recorded, never assumed:
                     engine file  4 failed / 1 passed  -> 5 passed
                     ingress file 3 failed / 10 passed -> 13 passed
                   The engine file's 1 pre-fix pass is the DORMANCY guard
                   (test_eligible_update_specs_still_fires): green before AND after, which
                   is what proves the fence narrows nothing the rule permits. The ingress
                   file's 10 pre-fix passes are the predicate's own abstain cases plus the
                   eligible-path dormancy — the predicate existed before its 3 call sites
                   were wired, so only the 3 wiring tests were red.
Integration tests: N/A — the defect is ENGINE CONTROL FLOW plus REST dispatch. The engine
                   half drives the REAL _run_review_gate offline (no stub) with a client
                   task posting through the real ArtifactStore seam; the ingress half
                   drives the REAL router over TestClient + in-memory SQLite. Both already
                   exercise the exact code a live POST reaches, so a separate integration
                   tier would add cost without coverage. Live Bedrock acceptance DEFERRED
                   (end-of-milestone rule).
Frontend tests:    N/A — no frontend file changed. The FE already drives the button from
                   the server flag; this fix makes the server agree with what it published,
                   so a correct FE sees no behaviour change at all. A stale tab now gets a
                   409 instead of a silently-ignored 200.
Goldens:           5 failed / 5 passed — IDENTICAL counts AND identical failing ids at the
                   pre-change commit d62bfe4d and after (prototype, od_prototype, od_ppt,
                   app_builder, prototype_revision event snapshots). NO golden regenerated.
                   Worth recording WHY they cannot move: all 10 golden files contain ZERO
                   review_gate_ready events (the harness runs gate_agent_ids=[],
                   _scripted_model.py:649), so the goldens are structurally blind to any
                   _run_review_gate change. INV-3 dormancy therefore had to be proven by
                   the test-level dormancy guards above, NOT by the goldens.
lint-imports:      3 kept / 1 broken — IDENTICAL at d62bfe4d. The broken contract is the
                   pre-existing agents.capabilities -> execution_engine.od_context ->
                   app.services.od_loader chain, untouched here.
Adjacent suites:   Both measured in a DETACHED WORKTREE at d62bfe4d, not assumed:
                     sweep A (spec_revision_cycles, spec_revision_context, redo_gate_safety,
                       gates, declared_gate_streaming, sc001_gate_flag, rest_gate_commands,
                       chat_messages_endpoint, concierge_proposal_channels,
                       approve_review_ownership, sse_stream)
                       10 failed / 159 passed BEFORE and AFTER — byte-identical failing ids
                       (diff showed only the elapsed-time line).
                     sweep B (banned_patterns, capability_resolution, restart_resume,
                       execution_engine) 10 failed / 83 passed -> 10 failed / 101 passed,
                       same ids; +18 passed = exactly this fix's new tests.
                   The pre-existing reds are _Ctx/_Ectx harness drift, an expired AWS SSO
                   token, and the known clarify-engine trio — none touched by this change.
Regression guards:
  - test_three_gate_vector_is_enforced_and_leaves_a_second_cycle_reachable (NEW): the
    load-bearing one. HARVESTS the eligibility values the engine actually computes at the
    outer / in-pass / re-opened analyze gates (never hardcoded) and feeds each into the
    REAL _run_review_gate, asserting honored / REFUSED / honored. This is what proves
    enforcement did not make a second revision cycle unreachable — if the rule ever changes
    so the re-opened gate stops advertising eligibility, this fails loudly, which is the
    signal to STOP rather than loosen the rule (loosening re-opens the nesting recursion
    ISS-051 closed).
  - test_gate_endpoint_leaves_the_other_actions_untouched (NEW, parametrised approve /
    reject / redo): the fence is scoped to ONE action, so an ineligible gate is never a
    trap — every other action still resolves it.
  - test_predicate_abstains_* (NEW, 3): the ingress predicate must never FABRICATE a denial
    when the durable log cannot answer (no row — persistence is best-effort; a different
    gate; a pre-KAN-101 payload). A fabricated denial would 409 a LEGITIMATE revision
    whenever a durable write degraded. Abstaining is only safe because the engine layer
    never abstains — these two properties are load-bearing for each other.
  - test_predicate_reads_the_LATEST_verdict_not_the_first (NEW): gate_key names a SLOT, not
    a firing, so the same key fires repeatedly with DIFFERENT verdicts. Reading the first
    row instead of the highest-seq one would re-open the whole hole.
  - test_spec_revision_cycles.py (5, FIX-218): unchanged and still green — in particular
    test_update_specs_not_offered_while_a_revision_is_in_flight, which already asserted the
    True/False/True vector at the STUB level. It was verified green at d62bfe4d BEFORE this
    work started (the brief's premise that the vector had no test was wrong) and is what
    this fix's new vector test composes with rather than duplicates.
  - test_nested_revision_keeps_distinct_threads_and_restores_the_outer_pass (FIX-218): the
    si4 nesting safety. No client can reach a nested pass through _run_review_gate any more,
    so its docstring was corrected to say it now pins DEFENCE IN DEPTH — kept deliberately
    rather than deleted, because it is what keeps the engine correct if a future call site
    ever passes the flag wrongly.
  - test_banned_patterns.py (R15 CI gate) + test_sc001_gate_flag.py: green, so no workflow
    name or agent-id literal entered the kernel on any new path.
```

### TEST-004 — FIX-218 (quick-260811-si4): nested + second-cycle spec revision

```
TEST COVERAGE — FIX-218
Unit tests:        8 total, ALL GREEN
                     5 NEW in backend/tests/agents/test_spec_revision_cycles.py
                     3 REVIVED in backend/tests/agents/test_redo_gate_safety.py
                   The 3 revived ones are guards that have been DEAD since KAN-101:
                   _run_agent grew a keyword-only `update_specs_eligible` gate arg and
                   swallows a stub TypeError into an `agent_error` event, so the four
                   stale `_fake_gate` signatures produced a silently-ZERO gate count
                   rather than an error. Adding `**kwargs` (test-only, no production
                   diff) took the file 3 failed / 4 passed -> 7 passed.
Integration tests: N/A — both defects are ENGINE CONTROL FLOW (which branch runs, at what
                   stack depth, with which checkpoint thread id). The scripted-model
                   harness drives the real _run_agent + real _run_spec_revision_sub_pipeline
                   offline with no Bedrock call, so a separate integration tier would add
                   cost without adding coverage. Live acceptance is DEFERRED, with its
                   recipe recorded in 260811-si4-BASELINE.md.
Frontend tests:    N/A — no frontend file was changed. InlineGateActions.tsx:130 already
                   drives the button purely from the server flag and
                   InlineGateActions.test.tsx:153 already asserts the hide path, so
                   flipping the flag is the whole FE story.
Goldens:           5 failed / 5 passed — IDENTICAL counts AND identical failing ids at the
                   pre-change commit bf51a170 and after. Asserted by an automated
                   string-diff against the GOLDENS-BASELINE line in
                   260811-si4-BASELINE.md, in BOTH Task 2 and Task 3 — never eyeballed
                   and never compared against a remembered figure.
lint-imports:      3 kept / 1 broken — IDENTICAL at bf51a170. The broken contract is the
                   pre-existing agents.capabilities -> execution_engine.od_context ->
                   app.services.od_loader chain.
Adjacent suites:   test_restart_resume.py 7 failed / 48 passed — unchanged, same ids.
                   tests/unit/test_execution_engine.py 3 failed / 11 passed — unchanged,
                   the 3 pre-existing clarify-engine reds.
Regression guards:
  - test_spec_revision_context.py (4, quick-260811-mxg): the prior-artifact injection at
    BOTH consumer sites, the no-leak scoping and the :rev{N} fresh thread. Merged and
    LIVE-PROVEN on Bedrock (run 5ecb990f), so these staying green is what proves FIX-217
    is intact. The [reentry] parametrisation is also the only coverage of the RESUME-17
    consumer site, which this fix re-routed through the shared helper.
  - test_restart_resume.py -k rehydrat (7, quick-260811-mxg): the resume planning-context
    rehydration is untouched.
  - test_single_cycle_shape_is_unchanged (NEW): one revision cycle still yields exactly 4
    dispatches, all sub-runs on :rev1, and the scratch fields clear on return. GREEN
    BEFORE the engine change and green after — dormancy proven at the test level, not
    only at the golden level.
  - test_f2_unbounded_redos_keep_a_flat_stack (REVIVED): the flat-stack idiom this fix's
    whole design leans on. It was dead while the design was being reasoned about.
```

**Discipline note.** The four defect tests were written FIRST and observed RED against the
unmodified engine, with verbatim output recorded in `260811-si4-BASELINE.md`. The RED gate was
deliberately strict — exactly 4 failed / 0 passed, and it REJECTS a pytest collection or
fixture error as not-RED, because a swallowed stub error looks like a failing assertion from
the outside. Every pre-fix failure reason matched the prediction: 4 dispatches instead of 7 and
no `:rev2`; eligibility `[True, True, True]`; and 7 thread ids of which only 4 were unique.

**Trap worth keeping.** Every gate stub in this area MUST accept `**kwargs`, and every drive of
`_drive_agent` against the revision path MUST pass `index=2` explicitly — the default `index=0`
makes `_run_spec_revision_sub_pipeline` `return` behind a `logger.warning`, so the test observes
zero sub-dispatches and fails on a baffling count assertion instead of an obvious error.

### TEST-003 — FIX-217 (quick-260811-mxg): spec-revision context loss

```
TEST COVERAGE — FIX-217
Unit tests:        11 total, ALL GREEN
                     4 in backend/tests/agents/test_spec_revision_context.py
                     7 in backend/tests/agents/test_restart_resume.py  (-k rehydrat)
Integration tests: N/A — the defect is prompt COMPOSITION; the scripted-model harness
                   (tests/agents/_scripted_model.py) exercises the full _run_agent
                   dispatch path offline with no Bedrock call, so a separate
                   integration tier would add cost without adding coverage.
Frontend tests:    N/A — no frontend file was changed.
Goldens:           5 failed / 5 passed — IDENTICAL failing ids at the pre-change commit
                   edc44daa and at HEAD. Re-measured independently in a detached
                   worktree at edc44daa rather than trusted as "pre-existing".
                   (The remembered "10 failed / 6 passed" was stale dev data.)
lint-imports:      3 kept / 1 broken — IDENTICAL at edc44daa; the broken contract is the
                   pre-existing agents.capabilities -> execution_engine.od_context ->
                   app.services.od_loader chain. "kernel imports only capability ports"
                   stays KEPT, so the new top-level ClarifyEngine import crossed nothing.
Adjacent suite:    test_restart_resume.py 7 failed / 48 passed vs 7 failed / 41 passed at
                   edc44daa — same 7 failing ids, +7 from this work.
Regression guards:
  - test_revision_prompt_contains_prior_artifact[live] / [reentry]: the composed prompt
    for the specify re-dispatch CONTAINS the prior spec, at BOTH _run_spec_revision_sub_pipeline
    call sites. Parametrised because fixing only the live site would leave the bug intact in
    exactly the restart scenario that exposed it.
  - test_prior_artifact_does_not_leak_to_plan_or_analyze: the injection is scoped to the
    specify sub-dispatch and cleared consume-once.
  - test_revision_uses_fresh_thread: the revision dispatch's thread_id differs from pass 1's.
  - test_rehydrate_planning_context_rebuilds_planner_and_answers: the resumed prompt carries
    the planner's real intent and the merged clarification answers, not user_message[:200].
  - test_rehydrate_survives_malformed_planner_constraints[4 params]: a non-list or
    non-string explicit_constraints degrades instead of raising TypeError out of the
    helper. All 4 seen RED against the pre-fix engine; one param initially passed for the
    wrong reason (a bare string explodes charwise and chars ARE str, so the isinstance
    assertion held) and was tightened to an exact-count assertion.
  - test_rehydrate_merge_survives_monkeypatched_clarify_engine: proves the import-time
    ClarifyEngine bind is load-bearing. Verified discriminating by running the late-binding
    counterfactual, which silently drops every answer behind one warning line.
  - test_offset0_gate_resume_does_not_replan_or_reclarify (pre-existing): stays green,
    proving D2 rehydrates rather than re-invoking the planner (BUG-R05 / quick-260719-hd5).
```

**Discipline note.** All 5 original tests were written FIRST and observed RED, with verbatim
output recorded in `260811-mxg-BASELINE.md`. The two added later (malformed-planner-row,
monkeypatched-ClarifyEngine) were likewise proven RED/discriminating against the pre-fix
engine before being accepted. The absence of any assertion on the revision payload —
`spec_revision_context` appeared in ZERO test files — is why this defect shipped.

**Live proof (Bedrock, run `5ecb990f-2c80-4752-a615-2bed3280387a`).** Full incident
reproduction including a deliberate backend SIGTERM at the plan gate. spec v1 -> v2:
31,742 -> 36,640 chars (+15.4%), 19 -> 19 headings (0 lost), 97.6% verbatim carry-over, the
planted `KESTREL` sentinel retained 4x -> 4x; task_list 45,229 -> 87,567 (+93.6%). The
incident it reproduces lost 8 headings, dropped "Spinnaker" 4x -> 0x and kept only 29.3%.

---


*Entries are appended below after each `/velocity-ai-test` session.*

---

---

### TEST-009 — FIX-225 (quick-260812-4ss): the multiplicity gap that let a 15-green-test fix over-count in a real browser

```
TEST COVERAGE — FIX-225
Unit tests:        N/A — frontend-only change, zero backend files touched.
Integration tests: N/A — no cross-service behaviour changed; the engine is deliberately
                   untouched (altering `resume_offset` emission would move the goldens).
Frontend tests:    12 NEW cases in frontend/src/hooks/useWorkflow.specRevisionCount.test.ts,
                   ALL GREEN. Every one seen RED first against the unmodified source.

  describe "ISS-080 — the count is a function of the SET of events, not of deliveries"
    is idempotent under double delivery (a reopen replays REST *and* SSE)
      RED BEFORE (observed): AssertionError: expected 5 to be 2
        — 5 is EXACTLY what the live browser showed (scratchpad/live-04-steps.png).
    is idempotent under triple delivery too (any future multiplicity)
      RED BEFORE (observed): AssertionError: expected 8 to be 2
    keeps the per-agent tally at the DISTINCT-event count under double delivery
      RED BEFORE (observed): {specify: 6, plan: 4, analyze: 4} vs {3, 2, 2}
        — the exact map measured in the live store during the investigation.

  describe "ISS-081 — a per-task agent loop is not a revision cycle"
    ignores the build loop's 11 restarts on run 6e38b9a7 (ONE revision)
      RED BEFORE (observed): AssertionError: expected 10 to be 1
    still ignores the build loop under double delivery
      RED BEFORE (observed): AssertionError: expected 21 to be 1
    reads 0 revisions on a run whose ONLY repeated agent is the task loop
      RED BEFORE (observed): AssertionError: expected 10 to be +0
        — the PREDICTED live symptom: a banner on a fresh build with zero revisions.

  describe "ISS-075 — a same-run pipeline_start re-announces, it does not restart"
    does not repaint a populated roster as idle (trailing resume_offset 0)
      RED BEFORE (observed): expected [] to deeply equal
        ['prototype-specify','prototype-plan','prototype-analyze']
    does not zero completedCount on a same-run re-announcement
      RED BEFORE (observed): AssertionError: expected +0 to be 3
    keeps the roster intact when the re-announcement carries a NON-zero offset
      RED BEFORE (observed): ['prototype-specify'] vs ['prototype-specify','prototype-plan']
    still builds a fresh idle roster for a genuinely different run
      Scope guard — the merge must not leak across runs.

  describe "deriveSpecRevisionCount" (rewritten for the head-scoped rule)
    ignores restarts of any agent that is NOT the pipeline head (ISS-081)
    returns 0 when the roster is not known yet

  FIXTURE CHANGE (load-bearing): REAL_FRAMES now carry `event_id` + `seq`, which every
  persisted `run_events` row and every live SSE event actually carries. The un-stamped
  fixtures were themselves part of why ISS-080 was invisible here — an un-stamped frame
  cannot be recognised as a re-delivery. Also added the `agent_complete` at seq 24787
  that the real durable log holds, so the roster assertions match the live screen.

Goldens:           10 passed / 0 failed — IDENTICAL to the pre-change commit f353a1a9
                   (frontend-only change; the engine was deliberately not touched).
lint-imports:      4 kept / 0 broken — IDENTICAL to f353a1a9 (run from backend/).
Frontend suite:    BEFORE 147 failed / 808 passed (955), 29 failed files, at f353a1a9
                   AFTER  147 failed / 820 passed (967), 29 failed files
                   `comm` over the sorted failing-id sets: ZERO new reds, ZERO
                   coincidentally-fixed reds. The +12 are exactly the new cases.
tsc --noEmit:      2 errors, both in files this change never touched
                   (NotificationPanel.fix195.test.tsx, useNotifications.fix202.test.tsx)
                   — 0 errors in any changed file. No new errors.
token-layer gate:  9 passed / 9.
Related suites:    79 passed across useWorkflow.specRevisionCount, useWorkflow.regenerateReset,
                   useWorkflow.pipelineCancelled, wsReplayState, wsRunScope,
                   liveRunSwitch.fix201, deadRevisionRefs.source (the replay/reducer
                   blast radius, incl. the source-lock on the store's single writer).

LIVE PROOF (mandatory here — unit tests are exactly what missed this):
  Run d5dbc9f2-dbe8-480f-8b13-788794a6788e reopened from Run History on a fresh load,
  local backend :8010 + `next dev` :3000, headless Chromium driver
  scratchpad/verify-260812-4ss.mjs.
    banner        "Spec Revision Cycle 2"   (pre-fix: "Spec Revision Cycle 5")
    roster header "3 / 5 agents"            (pre-fix: "0 / 5 agents")
    steps rows    specify/plan/analyze disabled=false, WITH durations + token counts
                  ("Spec Writer Agent 1m 42s · 42.4K tok"); build/validate correctly
                  disabled (they never ran).                (pre-fix: all 5 disabled)
    page errors   none
  Screenshots: scratchpad/verify-4ss-after-01-run.png, verify-4ss-after-02-steps.png
  Pre-fix pair: scratchpad/live-04-steps.png (Cycle 5 / 0 / 5, hollow Spec Writer row).

Regression guards:
  - The three double-delivery cases enforce the general rule the investigation drew out:
    ANY reducer field that accumulates must have a test that replays its input TWICE.
    All 15 prior FIX-221 cases called runFrames(REAL_FRAMES) exactly once — they varied
    frame ORDER but never frame MULTIPLICITY, which is the property that actually broke.
  - The head-scoping cases pin the ISS-081 rule against a return to `max`, using the REAL
    11-restart build-loop shape rather than a synthetic one.
  - The roster cases make ISS-075 impossible to file again as "confirmed in code, NOT
    observed on screen" — the reducer now proves the on-screen consequence directly.
```

**Findings deliberately NOT fixed here, filed rather than left in a transcript:**
`ISS-082` (the sibling accumulators `agent_chunk` output concat and `hookRuns` push carry
no identity key either — now protected only by the class-level seen-set fix) and `ISS-083`
(`ResultCard.tsx` renders `Revising spec — cycle {cycle ?? 1}` and nothing passes `cycle`
— a third, dormant counter in this family).

## Detailed Test Entries

### TEST-001 — FIX-001 (KAN-76) — Show and Edit Agent Prompts

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-test KAN-76 and KAN-75`

#### Fix Summary (from FIX-REGISTER)
- **Root cause:** `prompt_body` omitted from `AgentResponse` + `AgentDef`; no prompt endpoints; `AgentCapabilitiesModal` had no prompt section; factory.py never injected user overrides at runtime
- **Files fixed:** `backend/app/api/agents.py`, `backend/app/agents/prompt_overrides.py` (new), `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`, `frontend/src/components/workflow/AgentsPopup.tsx`, `backend/agents/factory.py`
- **What changed:** Added prompt_body to API responses; new GET/PUT/DELETE prompt override endpoints; new `prompt_overrides.py` storage module; factory wires override at runtime

#### Test Files Written
| File | Test count | Framework |
|------|-----------|-----------|
| `backend/tests/unit/test_prompt_overrides.py` | 21 | pytest |

#### Test Cases

| # | Test name | Purpose | Result |
|---|-----------|---------|--------|
| 1 | `test_save_writes_to_correct_path` | Override lands at `skills/users/{uid}/{agent_id}/PROMPT_OVERRIDE.md` | ✅ PASS |
| 2 | `test_read_returns_content_when_override_exists` | Reading an existing override returns it verbatim | ✅ PASS |
| 3 | `test_read_returns_none_when_no_override` | Missing override returns None safely | ✅ PASS |
| 4 | `test_has_override_true_after_save` | `has_user_prompt_override` reflects save | ✅ PASS |
| 5 | `test_has_override_false_before_save` | `has_user_prompt_override` returns False before save | ✅ PASS |
| 6 | `test_delete_removes_file` | Delete removes file, returns True | ✅ PASS |
| 7 | `test_delete_idempotent_returns_false_when_nothing_to_delete` | Idempotent delete returns False | ✅ PASS |
| 8 | `test_users_isolated_from_each_other` | User A override invisible to User B | ✅ PASS |
| 9 | `test_save_raises_on_empty_user_id` | Empty user_id raises ValueError | ✅ PASS |
| 10 | `test_save_raises_on_oversized_content` | >32KB raises ValueError | ✅ PASS |
| 11 | `test_read_returns_none_on_empty_user_id` | Empty user_id returns None safely | ✅ PASS |
| 12 | `test_skill_and_override_coexist_in_same_directory` | SKILL.md and PROMPT_OVERRIDE.md coexist | ✅ PASS |
| 13 | `test_base_prompt_used_when_no_override` | Base AGENT.md body used when no override | ✅ PASS |
| 14 | `test_override_replaces_base_prompt_when_user_has_override` | User override replaces base prompt at runtime | ✅ PASS |
| 15 | `test_base_prompt_used_when_user_id_is_none` | user_id=None uses base prompt — INV-3 preserved | ✅ PASS |
| 16 | `test_override_lookup_failure_falls_back_to_base_prompt` | Exception in lookup → base prompt, never crashes run | ✅ PASS |
| 17 | `test_after_delete_base_prompt_is_used_again` | Delete override → base prompt restored | ✅ PASS |
| 18 | `test_agent_response_model_has_prompt_body_field` | `AgentResponse.prompt_body` exists (root cause guard) | ✅ PASS |
| 19 | `test_agent_prompt_response_model_has_required_fields` | `AgentPromptResponse` has all 4 fields | ✅ PASS |
| 20 | `test_prompt_override_request_model_exists` | `PromptOverrideRequest` importable | ✅ PASS |
| 21 | `test_max_prompt_override_bytes_larger_than_max_skill_bytes` | 32KB > 8KB cap | ✅ PASS |

#### Run Output
```
28 passed, 1 warning in 1.43s
(21 from TEST-001, 7 from TEST-002 — run together)
```

#### Verdict
- **Tests written:** 21
- **Tests passed:** 21
- **Tests failed:** 0
- **Status:** ✅ All passing

#### Notes
- Factory tests use `MagicMock` + `patch` to isolate the `_compose_system_prompt` call from the full capability registry. The real assembly policy is patched to return `blocks["prompt_body"]` directly, making the test purely about whether the override or base prompt ends up in the block.
- Frontend (TypeScript) tests for the `AgentCapabilitiesModal` prompt section would require a vitest setup with MSW mocking; deferred as the backend coverage gives high confidence.

#### Fix Confidence
- [x] **High** — root cause test (`test_override_replaces_base_prompt_when_user_has_override`) + happy path + edge cases (isolation, empty user_id, oversized content, exception fallback, revert) all pass; regression (INV-3 user_id=None path) clean

---

### TEST-002 — FIX-002 (KAN-75) — Catalogue Nav Tab

**Date:** 2026-06-22
**Triggered by:** `/velocity-ai-test KAN-76 and KAN-75`

#### Fix Summary (from FIX-REGISTER)
- **Root cause:** `SavedWorkflowsPage` was fully implemented but only reachable via profile dropdown; no Catalogue tab in main nav
- **Files fixed:** `frontend/src/components/layout/AppHeader.tsx` (Catalogue tab added), `frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx` (redesigned)
- **What changed:** Added `LayoutGrid` icon + Catalogue button to `<nav>`; SavedWorkflowsPage redesigned with list/grid toggle, search, metadata, themed styling

#### Test Files Written
| File | Test count | Framework |
|------|-----------|-----------|
| `backend/tests/unit/test_catalogue_nav.py` | 7 | pytest |

#### Test Cases

| # | Test name | Purpose | Result |
|---|-----------|---------|--------|
| 1 | `test_user_workflows_api_module_importable` | Backend data source importable | ✅ PASS |
| 2 | `test_user_workflow_summary_has_timestamps` | `created_at`/`updated_at` in response model | ✅ PASS |
| 3 | `test_user_workflow_summary_has_base_pipeline_type` | Pipeline type badge field present | ✅ PASS |
| 4 | `test_user_workflow_summary_has_agent_ids` | Agent count field present | ✅ PASS |
| 5 | `test_user_workflow_summary_has_name_and_description` | Card title/subtitle fields present | ✅ PASS |
| 6 | `test_user_workflows_router_has_get_list_endpoint` | GET /api/user-workflows registered | ✅ PASS |
| 7 | `test_user_workflows_router_has_crud_endpoints` | POST/PATCH/DELETE registered | ✅ PASS |

#### Run Output
```
28 passed, 1 warning in 1.43s
(7 from TEST-002, 21 from TEST-001 — run together)
```

#### Verdict
- **Tests written:** 7
- **Tests passed:** 7
- **Tests failed:** 0
- **Status:** ✅ All passing

#### Notes
- Frontend navigation tests (e.g. Catalogue tab renders in AppHeader, `currentPage="saved-workflows"` highlights it) require vitest + React Testing Library. The backend tests focus on the data contract that the Catalogue renders.
- The `AppHeader.tsx` change is a 12-line addition — TypeScript type-checks clean (confirmed via `get_diagnostics`); the Catalogue tab's correctness is verified by the clean TS build.

#### Fix Confidence
- [x] **High** — data contract (all metadata fields present for the Catalogue display) verified; router endpoints confirmed; TS diagnostics clean on the changed component

---

### TEST-007 — FIX-221 + FIX-222 (quick-260812-2ci): a revision is visible while it happens, and afterwards

```
TEST COVERAGE — FIX-221 + FIX-222
Frontend tests:    27 NEW across 4 spec files, ALL GREEN.
                   RED FIRST, observed and recorded as one run before any source edit:
                     Test Files  4 failed (4)
                     Tests      18 failed | 1 passed (19)
                   ...and GREEN after:
                     Test Files  4 passed (4)
                     Tests      27 passed (27)
                   (19 -> 27 because ArtifactVersionPicker.test.tsx could not even LOAD
                    before the fix — the module did not exist, so vitest counted the file
                    as "0 test" rather than counting its 8 cases as failures. The one
                    green-at-red case is AgentDetailPanel "renders no picker without a
                    runId", which SHOULD pass before and after: it is the no-regression
                    guard for every existing caller.)

  useWorkflow.specRevisionCount.test.ts      9 cases   9 failed -> 9 passed
  deadRevisionRefs.source.test.ts            6 cases   6 failed -> 6 passed
  ArtifactVersionPicker.test.tsx             8 cases   file failed to load -> 8 passed
  AgentDetailPanel.artifactVersions.test.tsx 4 cases   3 failed -> 4 passed

Unit tests:        N/A (backend) — this defect is entirely frontend. Zero backend files
                   were opened; the durable data, the REST route and the read scope were
                   all verified ALREADY CORRECT against the live backend on :8010 before
                   any code was written (run d5dbc9f2: /artifacts?kind=spec&include=content
                   -> HTTP 200, spec v1/v2/v3 at 30081/36729/40052 chars).
Integration tests: N/A — see above.

Goldens:           5 failed / 5 passed — IDENTICAL to the pre-change commit b13d5c33
                   (measured at b13d5c33 before the change and again after).
lint-imports:      3 kept / 1 broken — IDENTICAL to b13d5c33 (run from backend/).
tsc --noEmit:      2 errors, BOTH pre-existing and in files this change never touched
                   (NotificationPanel.fix195.test.tsx, useNotifications.fix202.test.tsx).
Retired palette:   no #1B2A4A / #2563eb / #f5f5f0 in any changed file (grep, 0 hits).

Full frontend vitest, before vs after, compared BY FAILING TEST ID (not by count):
                   BEFORE  928 tests · 781 passed · 147 failed · 72 files failed
                   AFTER   955 tests · 808 passed · 147 failed · 72 files failed
                   NEW reds introduced: 0.   Previously-red now green: 0.
                   The failing-id SET is byte-identical; the delta is exactly +27 new
                   passing cases.

Mocked Playwright suite, before vs after, compared BY FAILING TEST ID:
                   BEFORE (b13d5c33)  33 failed · 43 skipped · 108 passed
                   AFTER              31 failed · 43 skipped · 110 passed
                   NEW failures introduced: 0. The after-set is a strict SUBSET of the
                   baseline set; two baseline reds (TS-L-01, TS-T-01) did not recur.
                   METHOD NOTE, because it nearly produced a false "pre-existing" claim:
                   playwright.config.ts sets reuseExistingServer:true on :3000, so a
                   worktree baseline run silently tests the MAIN tree's code through the
                   already-running dev server. The baseline above was taken in a detached
                   worktree at b13d5c33 running its OWN Next server on :3100 via a
                   throwaway config override. A symlinked node_modules ALSO fails there
                   (Turbopack: "Symlink [project]/node_modules is invalid, it points out
                   of the filesystem root") — an APFS clone (cp -Rc, ~6s) is the way.

Regression guards:
  - "yields 2 for the real d5dbc9f2 frame sequence": drives the ACTUAL durable frame
    order read from run_events, not a hand-invented one. Guards the headline number.
  - "is identical whether frames arrive one at a time or in one synchronous burst":
    the test that would have caught mechanism B. Locks live/replay parity, which is the
    property the whole fix is buying.
  - "survives the trailing same-run resume pipeline_start": guards mechanism C, i.e. the
    seq-24791 frame that used to zero the counter at the END of every replay.
  - "resets for a genuinely different run": stops the previous guard from over-reaching
    into "never resets", which would leak one run's history into the next.
  - "agrees with max(spec.version) - 1 from the run's artifact_refs": the cross-source
    assertion. FIX-221 derives from run_events and FIX-222 reads artifact_refs; this is
    the one line that fails if the two ever drift apart. It exists only because both
    landed together.
  - deadRevisionRefs.source.test.ts: mechanical INV-12 exit gate — fails if
    revisionCycleArmedRef / setSpecRevisionCountRef / pipelineAgentsRef ever reappear in
    page.tsx, or if the banner stops reading the per-run store. This family has already
    produced a dead counter twice; the lock is what stops a third.
  - "renders nothing when the API returns {}": pins the resp.artifacts ?? [] guard. Without
    it the protected mocked suite throws a TypeError on every agent-detail open, because
    mockApi.ts:708 answers unmatched /api/** with json({}).
  - "does not request content until a version is chosen, then memoises it": pins the
    2.89 MB lazy-fetch guard in both directions — not on mount, and not twice.
  - "html_file/prototype-build subset shape": the case a (kind, version) dedupe fails.
  - "renders no picker and behaves exactly as before without a runId": the no-regression
    guard for every existing AgentDetailPanel caller.
```

#### Verdict
- **Tests written:** 27
- **Tests passed:** 27
- **Tests failed:** 0
- **Status:** ✅ All passing, all seen RED (or unloadable) first

#### Notes
- There was **zero** existing coverage for the revision banner before this — no vitest and
  no Playwright spec anywhere referenced `specRevisionCount`, `revisionCycleArmedRef` or
  the string "Spec Revision Cycle". That absence is the direct cause of the defect: FIX-164
  silently killed the feature FIX-163 had just shipped, and nothing failed.
- No new Playwright case was added. The mocked fixture has no `/artifacts` handler, so the
  picker correctly renders nothing there; adding a handler plus a case is real value but is
  scope this task did not carry, and the protected suite was verified unharmed instead.

#### Fix Confidence
- [x] **High** for FIX-221 — the derivation is exercised against the real durable frame
  sequence and agrees with an independent durable source (artifact_refs). Live Bedrock
  acceptance deferred under the end-of-milestone rule.
- [x] **High** for FIX-222 — the REST contract it consumes was verified live on :8010
  before implementation, and the component degrades to rendering nothing on every failure
  path. Not yet seen against a real multi-version run in a browser (deferred with the above).

---

### TEST-008 — FIX-223 + FIX-224 (quick-260812-35u): the golden oracle is an oracle again, and both gaps that let this ship are closed

```
TEST COVERAGE — FIX-223 + FIX-224
Unit tests:        4 NEW backend pins, ALL GREEN. Every one seen RED first.

  test_loader.py::TestSchemaValidationAllAgents
    test_all_agents_declare_an_explicit_icon              1 case
      RED BEFORE (observed, at the unfixed AGENT.md):
        AssertionError: 1 of 86 AGENT.md files do not declare an explicit
        `icon:` and will silently fall back to the loader default '🤖',
        changing what the UI shows and moving the characterization event
        goldens: ['prototype-build'].
      GREEN AFTER: tests/agents/test_loader.py — 45 passed.
      Reads the RAW frontmatter (python-frontmatter, the same parser
      agents/loader.py uses), deliberately NOT spec.icon: the loader
      substitutes "🤖" for a missing key, so a spec.icon assertion is true by
      construction and would have been green-from-birth.

  test_banned_patterns.py
    test_capabilities_do_not_import_kernel_or_web_layer   1 case
      RED BEFORE (observed, with the fix temporarily reverted):
        Offenders:
          agents/capabilities/strategies/task_loop.py:572:
            from agents.execution_engine.od_context import get_example_html
      GREEN AFTER: tests/agents/test_banned_patterns.py — 14 passed.
    test_capability_boundary_gate_catches_the_iss068_violation  1 case
      NON-VACUITY (the file's own convention): replays the exact ISS-068
      statements plus a bare kernel import and asserts the scanner reports
      all 3. Without it a never-matching regex would pass on the clean tree.
    test_capability_boundary_gate_ignores_lookalikes      1 case
      FALSE-POSITIVE guard: a commented import, a sibling
      agents.capabilities.* import, `application_config`, `appdirs`.

Integration tests: N/A — no cross-service behaviour changed. FIX-223 C1/C2 are a
                   test-normalizer entry and an AGENT.md frontmatter line; FIX-224
                   swaps a direct import for an existing port with identical
                   semantics (same function, same EXAMPLE_MAX_CHARS cap, same
                   swallow-and-return-None), already inside a try/except.
Frontend tests:    N/A — zero frontend files touched.

Goldens:           BEFORE  5 failed / 5 passed   at f5f2f7c6
                   AFTER  10 passed / 0 failed   (the target end state)
                   Progression observed step by step, which independently
                   confirmed the 3-cause decomposition:
                     + C1 (normalizer strip)     5F/5P -> 3F/7P  (od_ppt, app_builder green)
                     + C2 (icon restored)        3F/7P -> 1F/9P  (prototype, od_prototype green)
                     + C3 (regen prototype_revision) -> 10 passed
                   C1 and C2 changed ZERO golden bytes.
lint-imports:      BEFORE 3 kept / 1 broken  at f5f2f7c6
                   AFTER  4 kept / 0 broken   (run from backend/ — from the repo
                   root it prints "Could not read any configuration" and exits)
test_restart_resume.py:
                   7 failed / 48 passed — IDENTICAL to f5f2f7c6, same 7 ids,
                   before and after. Deliberately NOT fixed here; filed as ISS-078.
Regression sweep:  119 passed across test_update_specs_enforcement.py,
                   test_update_specs_ingress_fence.py, test_spec_revision_cycles.py,
                   test_gate_revision_discriminator.py (the ISS-052/053 suites, 29),
                   test_loader.py, test_banned_patterns.py, test_strategies.py,
                   test_context_providers.py.
                   Plus 143 passed across test_strategies / test_capability_resolution /
                   test_registry_capabilities / test_sc001_nonprototype_task_loop /
                   test_per_task_capture / test_context_providers (task_loop blast radius).

Golden-regeneration proof obligation (the reason this fix is safe):
  git diff --stat -> 1 file changed, 33 deletions(-), 0 insertions(+)
  Programmatic accounting of the regenerated prototype_revision.events.json:
    event count      17 -> 14
    REMOVED types    exactly {gate_status, planner_complete, planner_start}
    ADDED types      NONE
    survivors        all 14 byte-identical AND in the same order as before
    resume_offset    absent from the file (proof C1 landed first, as required)
    icons            untouched (this pipeline has no prototype-build)
  33 lines = the 3 event objects (32) + the trailing comma on the new last element.

Regression guards:
  - test_all_agents_declare_an_explicit_icon: an AGENT.md can never again lose its
    icon silently. This is the gap that let FIX-190 ship a UI regression that 86-agent
    config review, code review and CI all missed and only a golden caught, 6 days late.
  - test_capabilities_do_not_import_kernel_or_web_layer: the Ports & Adapters boundary
    now fails PYTEST, not only the separately-invoked lint-imports binary. That gap is
    exactly why a one-line violation survived ~3 weeks.
  - The two non-vacuity/false-positive guards keep the boundary scanner honest in both
    directions.
```

**Two findings deliberately NOT fixed here, both filed rather than left in a transcript:**
`ISS-078` (the 7 `test_restart_resume.py` reds — possibly a LIVE production resume
regression, multi-day) and `ISS-079` (2 `test_phase6_frontend_consistency.py` reds,
re-baselined as pre-existing at `f5f2f7c6` in a detached worktree).

---

### TEST-010 — FIX-226 (quick-260812-77g): the version picker moves the WHOLE panel, not just the raw output

```
TEST COVERAGE — FIX-226
Unit tests:        N/A — frontend-only change, zero backend files touched.
Integration tests: N/A — no transport, endpoint or engine behaviour changed; the
                   artifact-version API (FIX-222) was already correct and untouched.
Frontend tests:    4 NEW cases in
                   frontend/src/components/results/AgentDetailPanel.artifactVersions.test.tsx,
                   ALL GREEN. All four seen RED first against the unmodified source
                   (observed: "Tests  4 failed | 4 passed (8)" — the 4 pre-existing
                   ISS-065 cases passing throughout, so the RED is the new gap only).
Goldens:           10 failed→0 / 10 passed — IDENTICAL to the pre-change commit a48965a5
                   (the code commit touches 2 frontend files; the backend tree at
                   a48965a5 is byte-identical to HEAD, so this is proof, not a sample).
lint-imports:      4 kept / 0 broken — IDENTICAL to a48965a5, same argument.
                   NB: must be run from backend/ — from the repo root it prints
                   "Could not read any configuration" and exits, which reads as a pass.

  describe "AgentDetailPanel — ISS-085: the artifact cards follow the selected version"
    selecting v1 repaints the spec pages card, not just the raw output
      RED BEFORE (observed): timed out waiting for /Specification · 1 page/ — the card
        stayed on v2's "Specification · 2 pages" + "Beta Page" while the raw output
        below it had already switched. This IS the owner's report, reproduced.
    Back to latest returns the card to the newest version
      RED BEFORE (observed): same wait; the card had never left v2, so "returning" to
        it could not be observed at all.
    selecting v1 repaints the governance-checks card body (AnalysisPreview)
      RED BEFORE (observed): "Risk register" never appeared — <AnalysisPreview
        content={agent.output}/> kept rendering v2's "Risk Mitigation Plan".
    derives the artifact TYPE from the selected version, so a mid-re-run agent still
    gets its card
      RED BEFORE (observed): no card at all. discriminateArtifact("") returns null, and
        FIX-039 clears agent.output on every agent_start — so during the exact
        update_specs cycle ISS-065 exists to serve, the panel showed the version's text
        with no card. Type-follows-selection is what closes this.

Regression guards:
  - "Back to latest returns the card to the newest version": the fix cannot strand the
    panel on an old version — the failure mode a naive `viewed ?? agent` swap invites.
  - The 4 pre-existing ISS-065 cases and the whole 42-09 artifactCards suite are
    UNCHANGED and still green (50/50 across the 5 results suites), which is what proves
    SettledArtifactCards' prop change (agent → output) broke no caller.
  - Full frontend vitest: 147 failed / 820 passed BEFORE → 147 failed / 824 passed
    AFTER; the failing-id sets diff to EMPTY (normalised for timings) and the 29
    failing FILES are identical. +4 passed = exactly the new cases.
```

**Deliberate non-coverage, recorded rather than hidden:** the tasks card still lists the
run's CURRENT `protoCompletedTasks` when an older `<tasks>` version is selected, and the
checks badge still reflects the agent's current `validationPassed`. Both are run/agent
state that is not versioned anywhere in the FE, so following the selection would mean
inventing data. Filed as `ISS-087` rather than silently fixed or silently ignored.

---

### TEST-011 — FIX-227 (quick-260812-7sk): Stop actually stops a run, and the run reaches a terminal state

```
TEST COVERAGE — FIX-227
Unit tests:        9 NEW backend cases, ALL GREEN:
                   5 in backend/tests/agents/test_cancel_stops_resumed_run.py (NEW file)
                   3 in backend/tests/unit/test_run_shutdown.py (TestPerRunStopEscalation)
                   1 in backend/tests/unit/test_rest_answers_cancel.py (the anti-lie test)
                   Suites: 5/5 · 7/7 · 10/10. 99 passed across the whole changed area
                   (adds test_fanout_cancel, test_rest_gate_commands, test_rest_resume,
                   test_sse_stream, test_pipeline_failure_semantics).
Integration tests: N/A as a separate tier — the end-to-end case IS an offline unit test:
                   test_cancel_stops_resumed_run.py drives the real resume_run over a real
                   in-memory-SQLite ScopedStore with a scripted model, reusing
                   test_restart_resume's _ResumeHarness (INV-12, no cloned harness). No
                   network, no Bedrock, no money. This defect was found because a resumed
                   build burned 16.5M tokens; nothing here launches or resumes a live run.
Frontend tests:    N/A — no FE behaviour changed. api.ts's postCancel return TYPE was
                   widened to carry accepted/status and warn against branching on
                   `cancelled`; no caller reads the body (both call sites only .catch).
                   tsc --noEmit unchanged at its 2 pre-existing errors
                   (NotificationPanel.fix195.test.tsx, useNotifications.fix202.test.tsx).
Goldens:           10 passed / 0 failed — IDENTICAL to the pre-change commit 1ed94666.
                   No golden regenerated (git status on characterization/ clean).
lint-imports:      4 kept / 0 broken — IDENTICAL to 1ed94666. The kernel gains an INJECTED
                   callback, never an app.api import; this is the contract that proves it.
                   NB: must be run from backend/ — from the repo root it prints
                   "Could not read any configuration" and exits, which reads as a pass.

  backend/tests/agents/test_cancel_stops_resumed_run.py
    test_resume_funnel_hands_the_cancel_event_to_execute_impl
      RED BEFORE (observed): "the resume funnel passed NO cancel_event to _execute_impl"
        — the kwarg was absent from the call entirely. THE root cause, asserted directly.
    test_resume_funnel_is_dormant_when_the_hook_is_unset
      RED BEFORE (observed): assert 'MISSING' is None. INV-3 guard: hook unset ⇒ the
        goldens/offline harness still see cancel_event=None.
    test_the_engine_reads_the_same_event_object_the_rest_registry_holds
      RED BEFORE (observed): AttributeError — no such hook existed. Object IDENTITY, not
        presence: this is the assertion that makes the orphan impossible to reintroduce.
    test_cancel_stops_a_resumed_drive_and_writes_the_terminal_row
      RED BEFORE (observed, by mutating the root-cause line back):
        "a cancelled resume kept dispatching agents: {'a': 2, 'b': 2} ->
         {'a': 4, 'b': 4, 'c': 2, 'd': 2}"
        — the production symptom, reproduced offline. Also asserts pipeline_cancelled is
        persisted to run_events and WorkflowRun.status == "cancelled".
    test_a_cancelled_resumed_run_is_not_re_adopted_by_auto_resume
      RED BEFORE (observed, same mutation):
        "the next boot re-adopted a run the owner paid to stop:
         ['stamp:iss084-bcbda284', 'resume_run:iss084-bcbda284']"
        — i.e. restarting the backend to stop a run makes the run FINISH. Measured in
        production too: the replacement backend emitted pipeline_start two seconds after
        boot and billed 7.5M further tokens.

  backend/tests/unit/test_run_shutdown.py — TestPerRunStopEscalation
    test_a_driver_that_ignores_the_stop_is_cancelled_and_left_terminal
      RED BEFORE (observed, by short-circuiting stop_run_driver): "an unresponsive driver
        must not survive a Stop". Also asserts the terminal reconcile fires.
    test_a_cooperative_driver_is_never_force_cancelled
      RED BEFORE (observed, same mutation): task never reached done(). ISS-007's contract:
        escalation is a FALLBACK, never the mechanism.
    test_stop_run_driver_is_a_no_op_without_a_live_task

  backend/tests/unit/test_rest_answers_cancel.py
    test_cancel_does_not_claim_success_without_a_live_driver
      RED BEFORE (observed, by disabling the liveness gate): "the endpoint claimed a
        cancellation nothing could perform: {'accepted': True, 'status': 'stopping'}".

Regression guards:
  - test_a_cancelled_resumed_run_is_not_re_adopted_by_auto_resume: THE guard that matters
    most. A cancel that leaves the row non-terminal is not a cancel, it is a delayed
    re-run — restore_non_terminal_runs re-adopts every non-terminal row on the next boot.
  - test_the_engine_reads_the_same_event_object_the_rest_registry_holds: object identity
    is what makes the orphan-Event class of bug unrepeatable.
  - test_resume_funnel_hands_the_cancel_event_to_execute_impl: the funnel guard. Every
    future resume driver reaches _execute_impl through _drive_resumed_stream, so this one
    assertion covers resume_run, _rearm_gate_run, _replay_clarify_run and POST /resume,
    and stops the next resume-path feature re-opening the hole (the TEST-008/009 shape).
  - test_resume_funnel_is_dormant_when_the_hook_is_unset: proves the INV-3 dormancy the
    10/10 goldens depend on, at the seam rather than only end-to-end.
  - test_restart_resume.py held at 7 failed / 48 passed, identical to 1ed94666 — ISS-078's
    territory, neither fixed nor worsened.
  - tests/unit/test_rest_run_launch.py + test_rest_revisions.py show 4 failures
    ('_FakeUser' object has no attribute 'tier'). Re-baselined in a detached worktree at
    1ed94666: the SAME 4 fail there. Pre-existing, with the SHA.
```

**Why the existing cancel suite missed a CRITICAL defect for six weeks:**
`test_rest_answers_cancel.py:210-224` seeded `_CANCEL_EVENTS[run_id]` **itself** and then
asserted the endpoint had set it — the one thing that still worked. The test and the bug
were the same shape: both mistook *"an Event object was in a dict and `.set()` did not
raise"* for *"the run was cancelled"*. Its docstring premise ("a live run has an armed
cancel event") was unfalsifiable because the test manufactured it. It is **reconciled, not
deleted**: it now seeds the driver task too, making the premise true, and asserts the
honest `accepted` acknowledgement. No test anywhere asserted that a drive OBSERVES the
event, that `pipeline_cancelled` is emitted, or that the status flips — TEST-011 is those
assertions.


---

### TEST-012 — FIX-228 (quick-260812-8j4): what a redo re-dispatch RECEIVES

**File:** `backend/tests/agents/test_redo_prompt_contract.py` (new) — 11 tests, all green.
Scripted-model harness only: no Bedrock, no Postgres, no Chromium.

**The gap this closes.** `test_redo_gate_safety.py` is the redo suite and every one of its
properties is an **absence** property — the internal signal never reaches the wire, the stack
stays flat, no lineage or REVISE block leaks onto the next agent, a rejected version never
wins. It comes within one line of catching ISS-086:
`test_f3_empty_output_after_redo_does_not_leak_lineage` drives a full redo of agent A and then
inspects **agent B's** prompt — agent A's redo dispatch is returned and thrown away. The suite
asks *"did the REVISE block leak out?"* and never *"did the subject arrive in?"*.
`test_spec_revision_context.py` (TEST-003) does assert presence, but only for the
`update_specs` sub-pipeline; the word `redo` does not appear in it.

**The goldens are structurally incapable of guarding this.** `_scripted_model.py:649` drives
every characterization run with `gate_agent_ids=[]`, so `_should_gate` is False for every
agent, no gate ever opens, and `_gate_redo` is unreachable. Zero `review_gate` strings exist in
any golden artifact. 10/10 green proves the fix stayed **dormant**; it proves nothing about the
redo path. That is why this file exists.

**RED-before evidence** (at `742f0c6e`, before the fix): **8 failed / 3 passed**. Every failure
was an assertion raised inside the test body — zero pytest errors, so none was a fixture or
collection problem masquerading as a red. The measured `delta first->redo = 101 chars`
independently reproduces the root-cause analysis's byte formula `79 + len(instruction)`
(`79 + 22`): the redo added the instruction block and nothing else.

| # | Test | Property | Pre-fix |
|---|------|----------|---------|
| 1 | `test_redo_dispatch_carries_the_agents_own_prior_output[×3]` | the re-run sees the document it is amending — parametrized over agent ids **read from the registry** across two pipelines (`user_stories` ×2, `prototype` ×1), so the SC-001 generality claim is asserted, not asserted-about | RED ×3 |
| 2 | `test_redo_dispatch_renders_subject_before_instructions` | `index(PRIOR_BLOCK) < index(REVISE_BLOCK)` — FIX-217's "subject first, instructions second" rule, which a naive seam reuse would have inverted | RED |
| 3 | `test_redo_injects_the_version_actually_being_rejected` | after **two** redos the third dispatch carries v2 and **not** v1 — max-version, kind-scoped | RED |
| 4 | `test_redo_at_the_gate_reentry_site_carries_it_too` | the RESUME-17 restart-parked consumer (re-opens with zero model call) | RED |
| 5 | `test_redo_at_the_reopened_post_revision_gate_carries_it_too` | the post-revision re-open consumer **plus** its three thin-copy defects: exactly one `results` entry, an audit row written, `derived_from` stamped | RED |
| 6 | `test_task_loop_redo_is_skipped_but_a_whole_artifact_redo_is_not` | a per-task dispatch is skipped **while** a whole-artifact redo of the same agent is injected | RED |
| 7 | `test_first_dispatch_carries_neither_block` | INV-3 dormancy guard | GREEN before **and** after |
| 8 | `test_blank_redo_stays_a_regenerate` | blank ⇒ regenerate is the *retained* P23 semantics, matching the FE's own "leave blank to just regenerate" | GREEN before **and** after |
| 9 | `test_redo_subject_does_not_leak_to_the_next_agent` | consume-once via save/restore; field empty after, next agent's prompt clean | GREEN before **and** after |

**Test #6 is a discriminating pair on purpose.** Today *nothing* injects, so a bare "the
task-loop case does not inject" would have been green from birth and proved nothing. Asserting
both halves on the same agent — task-loop must NOT while whole-artifact MUST — makes it fail
before the fix for the right reason.

**Harness reuse (INV-12).** `_EngineHarness` / `_drive_agent` / `_make_ectx` are imported from
`test_redo_gate_safety.py`, and `_FakeGateRunner` / `_seed_gate_reentry_ectx` from
`test_restart_resume.py` — no forked harness.

**The trap, hit again while writing this file** (already documented at
`test_redo_gate_safety.py:230-235`): the fake gate's parameter names must match
`_run_review_gate`'s keyword-only call **exactly**. `_run_agent` swallows a stub `TypeError`
into an `agent_error` event, so a misnamed parameter does not error — the test silently
observes **zero** gate firings and fails on a confusing count assertion instead.

**Baselines, measured at `742f0c6e` and re-measured after:**

```
TEST COVERAGE — FIX-228
Unit tests:        11 in backend/tests/agents/test_redo_prompt_contract.py  → ALL GREEN (8 observed RED first)
Integration tests: N/A — the defect is in prompt composition; the scripted-model
                   harness drives the real ExecutionEngine._run_agent redo loop end to end
Frontend tests:    N/A — no frontend file changed (the FE already ships the instruction box)
Goldens:           0 failed / 10 passed — IDENTICAL to 742f0c6e (never regenerated)
lint-imports:      4 kept / 0 broken — IDENTICAL to 742f0c6e
Regression guards:
  - test_redo_gate_safety.py (7)      : the four absence properties still hold
  - test_spec_revision_context.py (4) : FIX-217's path unaffected by the block move
  - test_spec_revision_cycles.py (5)  : FIX-218's flat sibling cycles unaffected
  - test_update_specs_enforcement.py (5) + test_update_specs_ingress_fence.py (13)
  - test_gate_revision_discriminator.py (6), test_cancel_stops_resumed_run.py (5)
  - test_restart_resume.py            : 7 failed / 48 passed, the SAME 7 ids as at
                                        742f0c6e (compared id-by-id in a detached worktree)
  - tests/unit/test_execution_engine.py: 3 failed / 11 passed, same 3 clarify-engine ids
                                        (sqlite has no artifact_refs table offline)
  - byte-identity: the first (non-redo) dispatch of three gated agents, dumped before and
                   after, sha256 9f84b82e3736f045bde1c243770de255782252315e11cafceedc1a876b5bd24c
                   — identical (INV-3, and the one thing the goldens cannot show)
```

---

### TEST-013 — FIX-229 (quick-260812-97f): ISS-078's seven reds — six were the tests

**File:** `backend/tests/agents/test_restart_resume.py` — **60 passed / 0 failed**, up from the
**7 failed / 48 passed** ISS-078 baseline measured at `99fcf4a2`. Offline: no Bedrock, no
Postgres, no Chromium; the whole file runs in ~4.5 s.

**The headline finding: only ONE of the seven was a product defect.** Five were fixture drift
and one was a stale stub. The register's live hypothesis — *"resume re-invokes completed work
and duplicates token spend"* — is **not supported**, and the recommended remedy would have made
it worse.

**Why the five fixtures could not pass.** `_first_incomplete_step` classifies a step complete
only when its typed artifact is corroborated by a terminal `agent_complete` (FIX-121). Every
one of the five fixtures persisted **zero** `run_events`, so that evidence could not exist in
them by construction:

* **#1 `test_midwave_resume_does_not_reinvoke_completed_workers`** and
  **#6 `test_failed_run_resumes_skips_completed_tasks`** drove `engine._execute_impl` directly
  (`:431`, `:3049`). The durable `_RunEventSink` is built in the **public** entry
  (`engine.py:1020`, persisted at `:1065`); `_execute_impl` persists nothing. Both tests
  described themselves as end-to-end while silently skipping the durability layer their own
  premise depends on. **Fixed by driving `execute()`** — instance A now writes its own durable
  rows, which is what these two always claimed to prove. This makes them *stronger*, not
  weaker: the repair is the assertion.
* **#2 `test_open_gate_override_is_noop_without_review_gate`**, **#3
  `test_partial_task_loop_build_reenters_step_not_skipped`**, **#4
  `test_completed_task_loop_build_stays_complete_no_rerun`** hand-seeded `ArtifactRef` rows
  only. A real run persists an `agent_complete` beside every produced artifact
  (`engine.py:4392`); the fixtures now do too. #3/#4 were failing at **index 0 on the PLAN
  step** and never reaching the `task_loop` branch they exist to exercise.
* **#5 `test_resumed_run_is_wired_live_ectx_and_milestone_cards`** — the milestone-card stub at
  `:2642` returned a 3-tuple against the 4-tuple contract
  (`chat_narrator.persist_milestone_card:287-289`, unpacked at `engine.py:1077` and `:8491`).
  It broke the **resumed drive itself** — `resumed-stream drive failed mid-drive: not enough
  values to unpack (expected 4, got 3)` at `engine.py:8509`, swallowed by the drive's
  `except Exception` — and the test then tripped on its own list. One line.

**The engine predicate was NOT loosened, and that was the decision of this task.** The prior
investigation recommended replacing the predicate with an interruption test
(`agent_id in agent_start_events and agent_id not in agent_complete_events`). Rejected on
measured evidence, read-only against the live `backend/dev.db`:

```
runs with artifacts: 14
DIFFERENTIAL SET (no agent_start AND no agent_complete): 27
  producers: [('deep-planner', 14), ('clarify-agent', 13)]
SEC 5.2 SET (agent_start present, agent_complete missing): 0
```

1. The scenario it was argued from — a lost `agent_complete` write making a step permanently
   unskippable — has **never occurred** (count 0), and the proposal is a **no-op for it
   anyway**: `agent_start` present + `agent_complete` missing is `_interrupted=True` under the
   proposal, i.e. still re-run, byte-identical to today.
2. Its entire live differential is 27 rows produced by `deep-planner` / `clarify-agent`, and
   **neither appears in any `agents/workflows/*/workflow.yaml` step list nor in
   `registry.PIPELINE_AGENTS`** (grep: zero hits). They are never members of `ordered_agents`,
   so the classifier never evaluates them.

So the proposal changes production behaviour for **zero ordered pipeline steps**, and its only
observable effect anywhere is that five broken fixtures go green. That is loosening a
production predicate to satisfy a test. FIX-121's fail-safe — absent terminal evidence,
re-enter; never skip — stands untouched. **`engine.py` is byte-identical to `99fcf4a2`.**

**Two shipped decisions had NO test at all; both are now pinned.**

| # | Test | Property | Pre-fix |
|---|------|----------|---------|
| 1 | `test_artifact_without_agent_complete_is_reentered_not_skipped[start_only]` | FIX-121: an artifact whose agent has an `agent_start` and **no** terminal event was stopped mid-flight ⇒ re-enter. This is the user-reported bug `c71f3d9c` fixed (Stop during the Spec Kit Analyzer re-raises `CancelledError` without emitting `agent_error`, `engine.py:4521-4522`) | RED under the pre-FIX-121 artifact-alone predicate: `idx=2`, expected `0` |
| 2 | `test_artifact_without_agent_complete_is_reentered_not_skipped[none]` | the same invariant with no lifecycle rows at all — absence of evidence is never evidence of completion | RED, same mutation |
| 3 | `test_reconcile_supersedes_only_across_an_attempt_boundary[same-attempt-rejection]` | FIX-229: a rejection and the trailing `pipeline_complete` in ONE attempt keep the cancellation | RED — reconciled to `completed` |
| 4 | `…[later-attempt-completes]` | KAN-120's genuine case still supersedes ⇒ `completed` | GREEN before **and** after |
| 5 | `…[later-attempt-rejects]` | a rejection in a later attempt than a completion is still a rejection | GREEN before **and** after |
| 6 | `test_failed_run_with_open_gate_resumes_into_gate` (existing, red #7) | end-to-end: resume into the gate, reject, run recorded `cancelled` | RED — `completed` |

Cases 4 and 5 stay green under the FIX-229 mutation **on purpose**: they prove the new clause
discriminates exactly the one behaviour it changes and leaves KAN-120 alone. A pin that went
red for every mutation would not tell us that.

**RED-before evidence, observed not inferred.** Each mutation was applied to the shipped file,
run, and reverted; `git diff` confirmed byte-identical restoration afterwards.

```
baseline at 99fcf4a2                    : 7 failed / 48 passed
after the fixture + stub repairs        : 2 failed / 58 passed   (commit 1c7569db, measured)
after FIX-229                           : 60 passed / 0 failed   (commit d3184e10)

predicate mutated to pre-FIX-121 form   : pins 1+2 RED (idx=2, expected 0)
resume_supersedes mutated to bare-seq   : pin 3 + red #7 RED ('completed' != 'cancelled')
```

**Baselines, with the SHA they were compared against — all re-measured at `99fcf4a2`, not
inherited:**

```
TEST COVERAGE — FIX-229
Unit tests:        60 in backend/tests/agents/test_restart_resume.py   → ALL GREEN (was 7F/48P)
Integration tests: N/A — the reconcile is exercised end-to-end by the same file's
                   _drive_user_resume tests; no separate integration tier exists for it
Frontend tests:    N/A — backend-only change
Goldens:           0 failed / 10 passed — IDENTICAL to 99fcf4a2; no golden regenerated
lint-imports:      4 kept / 0 broken   — IDENTICAL to 99fcf4a2
Regression guards:
  - protected 7 suites (redo contract/safety, cancel-resumed, update_specs ×2,
    spec-revision cycles, gate discriminator): 52 passed — IDENTICAL to 99fcf4a2
  - resume/cancel/shutdown adjacent (7 files): 44 passed — IDENTICAL to 99fcf4a2
  - run_commands consumer sweep (14 files): 14 failed / 156 passed WITH the fix and
    14 failed / 156 passed with the fix clause reverted — the reds are pre-existing and
    untouched (measured both ways rather than labelled)
  - tests/agents/test_gates.py: 3 failed / 39 passed — pre-existing at 99fcf4a2,
    unrelated to ISS-078 and NOT currently in any register
```

**Not live-proven, deliberately.** No run was launched, resumed or gate-approved: one build is
5–21M tokens of the owner's money, and this session's parent lost 16.5M to an accident. Every
proof above is offline.

---

### TEST-014 — FIX-230 (quick-260812-9tq): ISS-033-A — the model calls nobody was billing for

**Files:** `backend/tests/agents/test_iss033a_fixloop_token_fold_offline.py` (5 new),
`backend/tests/unit/test_handoff_agents.py` (2 new, 17 total), `backend/tests/agents/test_model_pricing.py`
(1 dead guard repaired, 27 total). Fully offline: no Bedrock, no Postgres, no Chromium.

**The RED that names the defect exactly.** Driving the real `prototype` pipeline offline, the
run's reported input tokens and the sum of its *visible* per-agent `agent_complete` tokens were
**identical** — `assert (220 - 220) == 240`. A difference of zero is the whole bug: four fix
sub-agents ran (`internal fix attempt 1/2`, `2/2` on both tasks — read out of the engine's own
INFO log, not assumed) and contributed nothing to the bill. After FIX-230 the same run reports
**460 in / 213 out** against 220 / 113 visible: **+240 input, +100 output** that were previously
invisible, and `estimated_cost_usd` moves `$0.000864 → $0.001678`.

| test | what it proves | RED before |
|---|---|---|
| `test_fix_loop_routes_usage_to_aux_sink` | the loop routes `usage` — and only `usage` — into the injected sink, all four keys intact | `TypeError: unexpected keyword argument 'aux_usage_sink'` |
| `test_fix_loop_without_a_sink_still_runs` | no sink ⇒ a no-op, not a crash (the direct/unit call shape) | green before and after — a degrade guard |
| `test_kernel_services_threads_aux_usage_sink_into_fix_loop` | the PRODUCTION wiring: the constructor sink reaches the engine loop, and it is the same callable | `TypeError` on the ctor kwarg |
| `test_prototype_run_total_includes_fix_loop_tokens` | **end-to-end on the real pipeline** — run totals now exceed the visible per-agent totals by exactly the fix spend | `assert (220 - 220) == 240` |
| `test_fix_loop_tokens_do_not_inflate_agents_completed` | `agents_completed` stays 6 — the fix spend goes to `aux_token_usage`, never to `results` | green before and after — a regression guard |
| `test_test_agent_counts_its_tokens_through_the_usage_sink` | `TestAgent` counts, with the Bedrock cache split split out correctly | `TypeError: TestAgent.__init__() got an unexpected keyword argument 'usage_sink'` |
| `test_test_agent_sends_a_cache_eligible_system_prefix` | the stable prompt stays a separate `SystemMessage` (where `langchain_aws` puts the cachePoint) | green before and after — a shape pin, stated as such |

**`agents_completed == 6` while `agents_total == 5` is CORRECT and was nearly mis-pinned.** The
first draft of the guard asserted they were equal; it failed at HEAD. `agents_completed` counts
`_run_agent` INVOCATIONS — the prototype's 5 steps plus the build agent's second task — so it
legitimately exceeds the step count. The test now pins the literal 6, which is what makes a
regression (6 → 10, one per fix attempt) loud.

**The repaired INV-12 guard, and what it now pins.** `test_websocket_cost_site_uses_shared_function`
read `app/api/websocket.py` — a file Phase 44's SSE cutover **deleted** — so since then it raised
`FileNotFoundError` instead of checking, and the "both cost sites share ONE pricing implementation"
contract was unenforced for the persistence site. It is now a parametrized
`test_both_cost_sites_use_the_shared_pricing_function` over `engine.py` (live `pipeline_complete`)
and `app/api/run_commands.py` (durable `workflow_runs.token_usage`), and it pins three things:
the file **exists** (an explicit assertion naming the contract, so the next move fails loudly
rather than silently); each site **imports** `estimate_cost_usd` (the old substring check was
satisfiable by a comment); and neither carries a per-token rate literal. **Mutation-tested, not
assumed** — all three arms were made to fail on purpose: a missing file, a site that only mentions
the function, and a site that imports it but hand-rolls a rate.

**Baselines, with the SHA.** Goldens **10 passed / 0 failed** and lint-imports **4 kept / 0
broken** — both re-run and identical to `d24c576a`, no golden regenerated. The 8 protected suites:
**112 passed / 0 failed**, identical to `d24c576a` (`test_restart_resume.py` = 60/0). Wider sweep
of the fix-loop, cost and KernelServices consumers: **157 passed / 0 failed**.

**One pre-existing red, verified not mine.** `tests/unit/test_execution_engine.py` has 3 failing
clarify-round tests (`assert 'clarification_limit_reached' in ['questionnaire_ready', …]`).
Re-measured at `d24c576a` in a detached worktree: **the identical 3 fail there** with none of this
change present. Filed as ISS-093.

**Not live-proven, deliberately.** No run was launched, resumed or gate-approved: one build is
5–21M tokens of the owner's money. The dollar figures come from a read-only query of the live
`backend/dev.db` priced through the real shared `estimate_cost_usd`.
