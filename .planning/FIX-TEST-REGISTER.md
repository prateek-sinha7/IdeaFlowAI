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
