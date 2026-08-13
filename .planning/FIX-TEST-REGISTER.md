# Fix-Test Register — VelocityAI / Flowin

> **Purpose.** Every test suite written via `/velocity-ai-test` is logged here, linked to its Fix ID from `FIX-REGISTER.md`. Read this before writing new tests to avoid duplicating existing coverage.
>
> **How to use:** Each entry is keyed by Fix ID. When a fix is tested, a TEST-NNN entry is added here referencing the FIX-NNN from `FIX-REGISTER.md`.
>
> **Cost reference — corrected 2026-08-12 (quick-260812-tni). Older entries below say "5–21M tokens"; that figure is superseded.** Measured read-only against `backend/dev.db` using each row's own persisted `estimated_cost_usd`: the **ceiling is 37,327,891 tokens / $7.07** for one `od_prototype` build (run `6e38b9a7`); the `d5dbc9f2` incident that drives the ISS-084/ISS-089 family cost **$3.58 total, ≈$1.61 of it after the API answered `cancelled: true`**; **all 14 metered runs, all time, total $17.75**. Cache reads dominate (35.8M of 37.3M on the largest run), which is why the dollar figure is small relative to the token count. **State the dollars, not just the tokens.** On this Haiku workload these are **correctness-and-trust** defects first and cost defects second — roughly an order of magnitude worse on an Opus-tier model, which is what the cancel/stop fixes insure against. The "do not launch a live build to prove a stop-path fix" rule stands on the *variance*, not on this median. Historical entries below are left as written — they were honest statements of what was believed at the time.

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
| TEST-015 | FIX-231 (quick-260812-fbk) | 2026-08-12 | `backend/tests/agents/test_gate_stub_signature_drift.py` (new), `backend/tests/agents/test_live_harness.py` | 5 | 5 | 0 | ✅ Pass |
| TEST-016 | FIX-232 (quick-260812-g1c) | 2026-08-12 | `backend/tests/agents/test_restart_resume.py`, `backend/tests/agents/test_fanout_cancel.py`, `backend/tests/agents/test_fanout.py` | 7 | 7 | 0 | ✅ Pass |
| TEST-017 | FIX-233 (quick-260812-gsf) | 2026-08-12 | `backend/tests/agents/test_concierge_capability.py`, `backend/tests/unit/test_chat_messages_endpoint.py` | 22 | 22 | 0 | ✅ Pass |
| TEST-018 | FIX-234 (quick-260812-hsx) | 2026-08-12 | `backend/tests/unit/test_shutdown_reachability.py`, `backend/tests/unit/test_run_shutdown.py` | 10 | 10 | 0 | ✅ Pass |
| TEST-019 | FIX-235 (quick-260812-iqh) | 2026-08-12 | `frontend/src/hooks/useWorkflow.accumulators.test.ts`, `frontend/src/lib/wsReplayState.test.ts`, `frontend/src/app/dashboard/liveRunSwitch.fix201.test.ts` | 37 | 37 | 0 | ✅ Pass |
| TEST-020 | FIX-236 (quick-260812-jn9) | 2026-08-12 | `frontend/src/components/chat/ResultCard.test.tsx`, `frontend/e2e/tests/ts-chat-cards.spec.ts` | 3 | 3 | 0 | ✅ Pass |
| TEST-021 | FIX-237 (quick-260812-kpb) | 2026-08-12 | `frontend/src/components/results/artifactPreview.tsx`, `frontend/src/components/results/AgentDetailPanel.tsx`, `frontend/src/components/results/AgentThinkingTab.tsx` | 7 (4 new + 3 reconciled) | 7 | 0 | ✅ Pass |
| TEST-022 | FIX-238 (quick-260812-lfv) | 2026-08-12 | `backend/tests/unit/test_iss102_live_model_guard.py` (new), `backend/tests/conftest.py`, `backend/tests/unit/test_chat_messages_endpoint.py` | 6 | 6 | 0 | ✅ Pass |
| TEST-023 | FIX-239 (quick-260812-mq5) | 2026-08-12 | `backend/tests/agents/test_iss034_cost_full.py` (new), `backend/tests/unit/test_analytics_api.py`, `frontend/src/components/analytics/AnalyticsPage.test.tsx` | 17 | 17 | 0 | ✅ Pass |
| TEST-024 | FIX-240 (quick-260812-ppu) | 2026-08-12 | `backend/tests/unit/test_run_events.py`, `backend/tests/unit/test_sse_stream.py` | 3 | 3 | 0 | ✅ Pass |
| TEST-025 | FIX-241 (quick-260812-sgu) | 2026-08-12 | `backend/tests/unit/test_rest_gate_commands.py` | 13 | 13 | 0 | ✅ Pass |
| TEST-026 | FIX-242 (quick-260812-syf) | 2026-08-12 | `backend/tests/agents/test_restart_resume.py`, `backend/tests/agents/test_merge_conflict.py`, `backend/tests/agents/test_fanout.py`, `backend/tests/unit/test_pipeline_failure_semantics.py` | 4 (3 new + 1 strengthened) | 4 | 0 | ✅ Pass |
| TEST-027 | FIX-243 (quick-260812-tni) | 2026-08-12 | `backend/tests/unit/test_rest_answers_cancel.py` | 10 new + 2 reconciled (10 → 20 in file) | 20 | 0 | ✅ Pass |
| TEST-028 | FIX-244 (quick-260812-wir) | 2026-08-12 | `backend/tests/unit/test_rest_answers_cancel.py` | 4 new (20 → 24 in file) | 24 | 0 | ✅ Pass |
| TEST-029 | FIX-245 (quick-260812-wir) | 2026-08-12 | `frontend/src/hooks/__tests__/terminalStatusReconcile.test.ts`, `frontend/src/app/dashboard/terminalReopenReconcile.source.test.ts` | 23 new | 23 | 0 | ✅ Pass |
| TEST-030 | FIX-247 (quick-260813-1b1) | 2026-08-13 | `frontend/e2e/tests/ts-r.cancel.spec.ts`, `frontend/src/app/dashboard/terminalReopenReconcile.source.test.ts`, `frontend/src/app/dashboard/liveRunSwitch.fix201.test.ts` | 1 new e2e (TS-R-05) + 2 source-lock `it()` blocks reconciled | 4 e2e (1 pre-existing fixme skipped) + 35 vitest | 0 | ✅ Pass |
| TEST-031 | FIX-248 (quick-260813-3wo) | 2026-08-13 | `backend/tests/unit/test_sse_stream.py`, `frontend/e2e/tests/ts-sse-resilience.spec.ts` | 1 new backend unit (`TestReplayIdentityProjection`) + 1 reconciled exact-body assertion + 1 new mounted-browser e2e (TS-SSE-RESILIENCE-06) | 44 backend + 5 e2e | 0 | ✅ Pass (live proof BLOCKED — see below) |
| TEST-032 | FIX-249 (quick-260813-5qr) | 2026-08-13 | `backend/tests/agents/test_concierge_capability.py` | 2 updated (never weakened) + 4 new | 37 (whole file, 1 pre-existing unrelated fail — ISS-151) | 0 | ✅ Pass (live-proven) |
| TEST-033 | FIX-250 (quick-260813-as6) | 2026-08-13 | `backend/tests/unit/test_rest_revisions.py` | 1 new (`test_driver_happy_path_persists_output_columns`) | 13 (whole file, 2 pre-existing unrelated fails — ISS-102/ISS-119 `_FakeUser.tier`) | 0 | ✅ Pass (live-proven) |

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

### TEST-015 — FIX-231 (quick-260812-fbk): ISS-074 — the gate stub that could not accept the gate's own arguments

**Fail-before (HEAD `fab9b646`, before any edit), verbatim:**

```
env -u RUN_LIVE_BEDROCK ANTHROPIC_API_KEY="" python3.11 -m pytest \
  tests/agents/test_live_harness.py::TestEngineGate \
  tests/agents/test_phase8_live.py::TestOfflineHITL -p no:randomly -q
FAILED tests/agents/test_live_harness.py::TestEngineGate::test_gate_on_pauses_then_auto_resumes_to_complete
FAILED tests/agents/test_live_harness.py::TestEngineGate::test_custom_approver_is_honoured
FAILED tests/agents/test_phase8_live.py::TestOfflineHITL::test_gate_on_auto_resume_offline
FAILED tests/agents/test_phase8_live.py::TestOfflineHITL::test_gate_on_custom_approver_offline
FAILED tests/agents/test_phase8_live.py::TestOfflineHITL::test_gate_on_manual_resume_seam_offline
========================= 5 failed, 3 passed in 2.19s ==========================
```

Cause visible in captured stderr, and the observable damage in the same frame:
`TypeError: drive_engine_pipeline.<locals>._auto_resume_review_gate() got an unexpected keyword argument 'redoable'`
→ `CaptureResult(..., gated=False, completed=True, error="...")`. The gate never opened **and the
run reported success** — a false-green HITL oracle, which is why ISS-074's severity was raised to major.

**After: 8 passed, 0 failed.**

**5 tests written (all seen RED first, none green-from-birth):**

| Test | What it proves |
|---|---|
| `test_gate_stub_signature_drift.py::test_every_gate_stub_accepts_the_real_signature` | Every substitute for `_run_review_gate` binds the engine's full keyword call. RED at HEAD naming `live_harness.py:672 (installed at :683)` (6 params unaccepted) and `test_gates.py:920 _FakeReviewEngine` (5 unaccepted). |
| `…::test_engine_signature_is_discoverable` | The AST derivation still resolves — without it every other assertion here is vacuous. |
| `…::test_bind_predicate_actually_discriminates` | Pins the guard's teeth: a stub pinning today's exact parameters binds today and raises on one more. Stops the predicate being "simplified" into something that always passes. |
| `…::test_stub_census_is_not_vacuous` | Floor + known-sites check, so a broken AST sweep fails loudly instead of finding zero stubs and passing forever. |
| `test_live_harness.py::TestEngineGate::test_gate_on_pauses_then_auto_resumes_to_complete` (strengthened) | Reads `redoable`/`update_specs_eligible` off the `review_gate_ready` payload — the **only** assertion that rejects the def-only shadow fix. |

**Discriminating experiment — why both tokens are load-bearing.** With `**kwargs` on the `def` but
NOT on the forwarded call: the arity guard is **3 passed** (blind to it) and the suite is
**1 failed / 7 passed** — the shadow fix greens every pre-existing assertion, and only the new
forwarding assertion catches it (`test_live_harness.py:208: assert False is True` on `redoable`).
Dropped kwargs include `cancel_event` (a gate that cannot honour Stop, silently undoing
quick-260720-ec4's BUG-2 Cond B) and the name-free SC-001 discriminators.

**Guard proven against the NEXT drift, not just this one.** A throwaway stub pinning today's ten
parameters plus a temporary 11th engine parameter (`throwaway_drift_probe`) →
`1 failed`, message naming `_drift_probe_tmp.py:10` and `cannot accept: ['throwaway_drift_probe']`,
with the derived parameter list correctly showing all eleven. Control: engine reverted, probe
retained → `3 passed`. Both the probe and the engine edit were removed; `git status` confirms
**0 files changed under `backend/agents/` or `backend/app/`**.

**Coverage fix (the actual root cause).** `tests/agents/test_live_harness.py` and
`tests/agents/test_phase8_live.py` (34 passed / 16 skipped, ~40 s) plus the new guard are now in
the curated offline suite in `.planning/TEST-REGISTER.md` §1.6, and the filename heuristic
*"Avoid offline: anything `*_live*`"* — which is what hid this for 43 days — was replaced with
"check the actual skip marks". The same note now records that `lint-imports` must be run from
`backend/` or it prints "Could not read any configuration" and reads as a false pass.

```
TEST COVERAGE — FIX-231
Unit tests:        5 in backend/tests/agents/          → ALL GREEN (4 new guard + 1 strengthened)
Integration tests: N/A — test-infra defect, no service boundary involved
Frontend tests:    N/A — no frontend surface
Goldens:           0 failed / 10 passed — IDENTICAL to the pre-change commit fab9b646; 0 golden files modified
lint-imports:      4 kept / 0 broken — IDENTICAL to fab9b646 (run from backend/; 215 files, 526 deps)
Regression guards:
  - test_every_gate_stub_accepts_the_real_signature: any new _run_review_gate parameter goes red
    in the same commit, offline, in <1s, naming every stub that needs updating.
  - test_bind_predicate_actually_discriminates: the guard's own predicate cannot be weakened silently.
  - test_stub_census_is_not_vacuous: a broken AST sweep fails loudly instead of passing on zero stubs.
  - test_gate_on_pauses_then_auto_resumes_to_complete: rejects the def-only shadow fix (measured).
Pre-existing reds re-measured UNCHANGED after the fix (not caused by it):
  test_gates.py 3 failed/39 passed (ISS-094) · test_declared_gate_streaming.py 3 failed (ISS-095)
  test_wire_parity.py 4 failed/2 passed · test_prompt_contracts.py 1 failed (ISS-096, reproduced at fab9b646)
```

---

### TEST-016 — FIX-232 (quick-260812-g1c): ISS-091 — a review-gate rejection did not stop the run

**Fail-before (HEAD `c0bbb6e2`, before any edit), verbatim:**

```
env -u RUN_LIVE_BEDROCK ANTHROPIC_API_KEY="" python3.11 -m pytest \
  tests/agents/test_restart_resume.py -q -k "inline_gate_rejection or gate_rejection_writes \
  or rejected_run_resumes or declared_gate_rejection_still"

E   AssertionError: a rejected run must END on pipeline_cancelled; it ended on 'pipeline_complete'.
E   Tail after the cancel: ['wave_started', 'subagent_spawned', 'subagent_spawned', 'subagent_result',
E   'subagent_result', 'merge_started', 'merge_completed', 'wave_completed', 'wave_started',
E   'subagent_spawned', 'subagent_spawned', 'subagent_result', 'subagent_result', 'merge_started',
E   'merge_completed', 'wave_completed', 'pipeline_complete']

E   AssertionError: a rejected run dispatched waves it must never have started:
E   [(0, 'completed'), (1, 'completed')]

E   AssertionError: the resumed run produced nothing — the rejection poisoned the durable wave
E   record and every wave was skipped as already-done. Produced: []

============ 3 failed, 1 passed, 60 deselected, 1 warning in 1.25s =============
```

The third failure is the one that matters. It is not a cosmetic terminal-event bug: the rejection
writes `subagent_runs='complete'` / `wave_runs='completed'` rows for work that never happened, and
`wave_scheduler.py:251-256` trusts exactly those rows on resume — so the run's deliverable becomes
permanently unproducible while the run reports `completed`.

**After: 7 passed, 0 failed** (4 in `test_restart_resume.py`, 3 in `test_fanout_cancel.py`).

**7 tests written (6 seen RED first; the 7th proven by mutation — none green-from-birth):**

| Test | What it proves |
|---|---|
| `test_restart_resume.py::test_inline_gate_rejection_stops_the_pipeline` | The stream ENDS on `pipeline_cancelled`, `pipeline_complete` is never emitted, and no `agent_start`/`wave_started`/`subagent_spawned`/`merge_started` follows it. RED: terminal was `pipeline_complete` with a 17-event tail. |
| `…::test_gate_rejection_writes_no_wave_or_subagent_rows` | Zero `wave_runs` and zero `subagent_runs` rows survive a rejection — the rows the resume skip later trusts. RED: 2 waves `completed` + 4 workers `complete`. |
| `…::test_rejected_run_resumes_and_still_produces_its_deliverable` | **The data-loss regression test.** Reject → restart → resume actually runs the waves and writes all four `part_*.txt`. RED: produced `[]`, worker calls `{}`, run `completed`. |
| `…::test_declared_gate_rejection_still_cancels_the_run` | Guard over the declared-gate sibling WR-03 (`engine.py:2454-2479`), so the new observation cannot disturb it. Green before and after **by design**; its teeth were proven by deleting WR-03's `return`, which makes it fail with *"WR-03 regressed: … it ended on 'pipeline_complete'"*. |
| `test_fanout_cancel.py::test_terminal_run_stops_the_fanout_without_any_cancel_event` | The fan-out boundary honours run terminality even with NO `cancel_event` — the review-gate-rejection shape. RED: `DID NOT RAISE CancelledError`. |
| `…::test_non_terminal_run_is_undisturbed_by_the_terminality_check` | The added check is inert on a healthy run: both workers run and the merge still completes. RED: `terminal_checks == 0`. |
| `…::test_kernel_services_is_run_terminal_reads_the_real_state_machine` | Drives `KernelServices.is_run_terminal()` against the REAL `StateMachine` so the terminal-state set cannot drift from the engine's own guard. RED: `AttributeError: 'KernelServices' object has no attribute 'is_run_terminal'`. |

**Two repro traps encoded so they cannot be re-hit:** `make_engine()` installs `_run_review_gate` as an
INSTANCE attribute (patching the class is silently shadowed), and `gate_agent_ids=[]` means *"no gates
this run"* since FIX-041 — the gated agent must be named explicitly. T4 additionally requires
`gate_agent_ids=None`, or `_should_gate` claims the agent for the inline path and the WR-02 dedupe
(`engine.py:5052-5066`) skips the declared gate entirely. The shared stub takes `*_a, **kwargs` so it
binds whatever the engine's signature grows into (`test_gate_stub_signature_drift.py`).

**Collateral fixed, not worked around:** `test_fanout.py`'s two `_FakeEngine` doubles construct a REAL
`KernelServices` and had no `_state_machine`, so the new predicate raised `AttributeError` there
(3 tests). The production predicate was kept direct — every other `self._engine.X` access in
`kernel_services.py` is unguarded, production's only construction is `engine.py:2101` with
`engine=self`, and a silent degrade would make broken engine wiring read as "not terminal", hiding the
exact bug class the check exists to catch. The doubles now carry their own `StateMachine`.

**Regression gates, all measured against `c0bbb6e2`:**

```
goldens        10 passed / 0 failed   + 0 golden files modified   (IDENTICAL to c0bbb6e2)
lint-imports   4 kept / 0 broken                                   (IDENTICAL to c0bbb6e2)
test_restart_resume.py            60 passed  →  64 passed
test_fanout_cancel.py              6 passed  →   9 passed
fanout/wave/kernel_services/budget sweep     141 passed, 3 skipped
every other real-KernelServices double site  130 passed
known pre-existing reds  11 failed / 54 passed → 11 failed / 54 passed, IDENTICAL ids
  (test_gates.py x3 = ISS-094, test_declared_gate_streaming.py x3 = ISS-095,
   test_wire_parity.py x4 = stale wire goldens, test_prompt_contracts.py x1 = ISS-096)
```

**The oracle limitation, stated plainly:** the characterization goldens compile `gate_agent_ids=[]`
(`_scripted_model.py:649`), so **not one golden contains a `review_gate_ready` or a
`pipeline_cancelled`**. They are structurally incapable of detecting this change and prove only that
nothing else moved. The seven tests above are the only real oracle for FIX-232.

Not live-proven, deliberately: every assertion here is offline-decidable and one `od_prototype` build
costs 5–21M Bedrock tokens. Deferred to the end-of-milestone live pass.

### TEST-017 — FIX-233 (quick-260812-gsf): ISS-092 — the Concierge's unbounded pre-fed context and its uncounted tokens

**22 tests, every one seen RED before the fix.** Baselines captured at `5b004e1c` BEFORE any edit:
goldens **10 passed**, `lint-imports` **4 kept / 0 broken**, Concierge suite **2 failed / 67 passed**,
`test_gates`+`test_declared_gate_streaming`+`test_wire_parity`+`test_prompt_contracts` **11 failed / 54 passed**,
`test_chat_messages_endpoint.py` **3 failed / 25 passed**.

**Fail-before — the test that would have caught ISS-092** (12,000 rows including a 480,000-char
`agent_input`, invoke EVERY tool, assert each result < 25,000 chars). One test named all three
offenders at once:

```
E   AssertionError: unbounded read tool(s) — this is ISS-092:
E     read_events=3,607,954 chars, list_refs=400,140 chars, get_ref=400,138 chars
```

**Fail-before — the filesystem WRITE surface** (a fake `BaseChatModel` records what `bind_tools`
is actually handed, so this observes the LIVE model's real surface, not an inference):

```
E   AssertionError: the Concierge model was handed filesystem/todo tools:
E     ['edit_file', 'glob', 'grep', 'ls', 'read_file', 'write_file', 'write_todos']
```

**Fail-before — counting, and the prompt/tool consistency guard:**

```
E   AssertionError: converse must surface the model spend on the ctx
E   assert False + where False = isinstance(None, dict)

E   AssertionError: one answered turn must record exactly one chat_usage row
E   assert 0 == 1

E   AssertionError: the prompt names tools that do not exist: ['read_events']
E   AssertionError: turn 7 lost from the prompt
```

**Regression guards:**
  - `test_no_tool_returns_unbounded_event_history` — the ISS-092 oracle; any re-added unbounded tool fails CI.
  - `test_read_tools_expose_only_the_bounded_allow_list` — exact name-set equality, mechanically enforcing
    INV-12 (`read_events`/`list_refs`/`get_ref` deleted, not shadowed).
  - `test_no_tool_accepts_a_run_id_argument` — pins the authorization invariant: `run_id` is a CLOSURE,
    never a model-supplied parameter.
  - `test_get_artifact_denies_cross_run_ref` — closes the cross-run scope escape left by
    `ScopedStore.get_ref` (owner + visibility scoped, never run-scoped).
  - `test_concierge_model_sees_no_filesystem_tools` + `test_excluding_builtins_does_not_flip_the_xml_sanitizer` —
    the second asserts the side effect that made the first safe (`_sanitize_fabricated_xml` stays `False`
    because the Concierge always has custom tools), rather than assuming it.
  - `test_conversation_context_reaches_the_concierge_prompt_byte_verbatim` — multi-turn survives the deletion
    of `read_events`: the last 6 turns appear BYTE-VERBATIM in the prompt the model actually receives, older
    turns summarized, block under budget.
  - `test_conversation_provider_stays_dormant_without_the_declared_inject` — proves the provider's self-gate
    was NOT relaxed, which is what keeps the goldens byte-identical (INV-3).
  - `test_system_prompt_names_only_existing_tools` — guards the exact bug this refactor invites.
  - `test_chat_usage_never_mutates_workflow_run_token_usage` — pins the product decision (separate line, not
    headline) so a later change must be deliberate.
  - `test_converse_reports_zero_usage_rather_than_estimating` + `test_no_chat_usage_row_when_spend_was_not_observed`
    — an unobserved token is reported as unmeasured, never derived from `len(chat_reply)`.

**Reconciled, not deleted:** `test_read_tools_go_through_scoped_store_and_deny_cross_owner` and
`test_read_tools_serialize_rows_to_plain_dicts` named the deleted `read_events` tool. Both were
retargeted onto `read_recent_events`, keeping their default-deny and plain-dict assertions intact.

**Data-level proof, zero model spend.** The shipped tools were driven over real `backend/dev.db`
rows at all 15 recorded `chat_message` points:

```
run@seq                BEFORE tok  AFTER tok        x  worst tool
0a27b397@12123          2,494,799      4,710     530x  read_recent_events (9,667 ch)
0a27b397@12121          2,494,228      4,509     553x  read_recent_events (8,863 ch)
0a27b397@5957           1,940,140      4,109     472x  read_recent_events (7,271 ch)
fa66227a@2181             573,573      4,675     123x  read_recent_events (12,241 ch)
caa5d175@10519            450,283      4,263     106x  read_recent_events (8,221 ch)
a7dba362@7721             358,640      4,765      75x  read_recent_events (10,206 ch)
worst-case FULLY tool-saturated turn across the whole corpus: 4,785 est. tokens
```

**Baseline comparison (all vs `5b004e1c`):** goldens **10 passed / 0 golden files moved**;
`lint-imports` **4 kept / 0 broken**; `test_banned_patterns.py` **14 passed** and zero
`create_deep_agent` in `concierge.py` (INV-13); the 11 / 3 pre-existing reds unmoved with
identical ids. The one surviving Concierge red
(`test_compose_system_prompt_injects_chain_hints_block`) was checked rather than labelled:
the rewrite adds neither `"follow-up"` nor `"chained into"`, so its failure mode is byte-identical
to baseline — it is stale FIX-213/FIX-115 assertion drift, not this change.

**Not proven offline (deferred, not faked):** whether the live model actually PICKS the right tool
per question. Offline proves the tools exist, are bounded, are run-scoped and are described in the
prompt. The per-question cost is now readable from the `chat_usage` row — which is why counting
shipped as the first of the two commits.


---

### TEST-018 — FIX-234 (quick-260812-hsx): ISS-088 — shutdown reachability, the teardown budget, and both stop-runs branches

```
TEST COVERAGE — FIX-234
Unit tests:        8 in backend/tests/unit/test_shutdown_reachability.py   → ALL GREEN (new file)
                   2 in backend/tests/unit/test_run_shutdown.py            → ALL GREEN (7 → 9)
Integration tests: N/A by design — the defect lives in the PROCESS SIGNAL PATH, so the
                   reachability test spawns a real uvicorn SUBPROCESS and sends a real
                   SIGTERM. That is the integration-level proof; an in-process
                   uvicorn.Server (the test_run_stream_pool_leak.py:196-238 precedent)
                   cannot reproduce it, because capture_signals() installs handlers only
                   when it is on the main thread.
Frontend tests:    N/A — no frontend source changed. The two frontend files touched are
                   live-spec PREREQUISITE DOCSTRINGS (comments), not code.
Goldens:           0 failed / 10 passed — IDENTICAL to the pre-change commit 9df9c1c8,
                   and `git status` on backend/tests/agents/characterization/ is empty
                   (0 golden files moved).
lint-imports:      4 kept / 0 broken — IDENTICAL to 9df9c1c8 (run from backend/).
Regression guards:
  - test_sigterm_reaches_the_lifespan_shutdown_half_while_a_stream_is_live:
      the test that would have caught ISS-088. Real uvicorn subprocess + live
      EventSourceResponse + real SIGTERM; asserts the process exits AND the lifespan
      shutdown body ran to completion.
  - test_docker_entrypoint_still_passes_timeout_graceful_shutdown:
      one line; blocks a silent regression to the pre-KAN-151 production state.
  - test_production_teardown_budget_fits_inside_stop_grace_period:
      PARSES stop_grace_period from docker-compose.yml and the graceful window from
      docker-entrypoint.sh — nothing hardcoded, so drift in either file fails here.
  - test_production_leaves_shutdown_stop_runs_off (+ the >= grace assertion):
      pins WHY production keeps stop-runs off, in arithmetic rather than prose.
  - test_development_defaults_shutdown_stop_runs_on / test_explicit_shutdown_stop_runs_always_wins:
      the env-differentiated default, and that an explicit value wins in BOTH directions.
  - test_close_checkpointer_is_awaited_exactly_once_on_the_shutdown_path:
      pins the INV-12 deletion; two call sites made the documented ordering false.
  - TestShutdownStopsRunsWhenEnabled (2 tests): step 3 of shutdown_run_infrastructure
      had ZERO coverage and is now the live branch on every developer machine.
```

**Every new assertion was seen RED first — verbatim:**

| Test | RED evidence |
|---|---|
| reachability | flag omitted → `Failed: uvicorn did not exit within 25.0s of SIGTERM while an SSE stream was live. Markers written: {"event": "startup_complete", "t": 1786532068.807335}` — only `startup_complete`, i.e. the defect itself |
| `close_checkpointer` once | `AssertionError: main.py awaits close_checkpointer() 1 time(s).` / `assert 1 == 0` |
| dev default on | `AssertionError: assert False is True` |
| stop-runs ON branch | guard mutated to `if False:` → `assert 0 == 1` |
| stop-runs OFF branch | guard mutated to `if True:` → `assert 1 == 0` |

The entrypoint-flag and budget tests are guards over parsed files: they pass at HEAD by
construction and fail on drift, so they are stated as guards rather than claimed RED-first.

**Reconciled, not loosened.** The env-differentiated default made every test in
`test_run_shutdown.py` depend on the ambient `ENV` of whoever runs pytest — the run that
surfaced it failed `test_pump_that_finishes_promptly_is_drained_not_cancelled` with a
`CancelledError`, because step 3 now cancelled the task the test had registered as its own
driver. The autouse fixture now pins `SHUTDOWN_STOP_RUNS` to the branch each test asserts.
**No assertion was changed, weakened or deleted.**

**Baselines re-measured, not assumed (all vs `9df9c1c8`):** goldens 10 passed → 10 passed;
lint-imports 4/0 → 4/0; the four known pre-existing red suites 11 failed / 54 passed → 11
failed / 54 passed with identical ids; `test_run_shutdown.py` 7 → 9; resume/cancel/restart
suites 73 passed.

**Two red suites NOT in the known-red list were checked rather than labelled.**
`test_model_factory.py` (6, all Mistral-fallback) and `test_rest_run_launch.py` (2) fail
after the change. Re-run at the pre-change commit `9df9c1c8` in a throwaway `git worktree`
(`backend/.env` is absent, so no env confound): **identical 8 failed / 47 passed, same test
ids.** Pre-existing, with the SHA to prove it.

**Not proven offline (deferred, not faked):** the flag's effect on the REAL application under
a real run. Everything above runs against a synthetic app that mirrors only the lifespan +
`EventSourceResponse` shape, deliberately: booting `app.main` calls `restore_non_terminal_runs()`
(`main.py:238`), which auto-resumes non-terminal runs and would spend Bedrock budget. The
mechanism is identical (same uvicorn, same `sse_starlette`, same signal path), and production
has run with the flag since KAN-151 D8.

### TEST-019 — FIX-235 (quick-260812-iqh): ISS-082 — every accumulating reducer field, fed its input twice

**The rule this suite makes executable:** *a reducer field that accumulates is not done until
a test has fed it the same input twice and it did not change.*

ISS-080 is why it needs a suite rather than a case. It shipped behind **15 green tests** and
still put a wrong number on screen, because every one of those tests varied frame ORDER and
never frame MULTIPLICITY — and multiplicity is what a history reopen produces.

**Files**

| file | tests | what it holds |
|---|---|---|
| `frontend/src/hooks/useWorkflow.accumulators.test.ts` | 30 | the registry, the multiplicity matrix, GUARD-1 |
| `frontend/src/lib/wsReplayState.test.ts` | +6 | `resolveFrameRunId` — the A3 measurement |
| `frontend/src/app/dashboard/liveRunSwitch.fix201.test.ts` | 1 reconciled | the deleted bypass, source-locked ABSENT |
| `frontend/src/hooks/__fixtures__/reducerHarness.ts` | — | the ONE `runFrames` driver, extracted not copied |

**Part 1 — a declared registry, one row per accumulating field.** All **seven**
(`output`, `thinkingText`, `toolCalls`, `validationIssues`, `hookRuns`, `agentStartEventIds`,
`clarifications`), each with the minimal frames that grow it, what the user ends up seeing,
and its value after ONE logical delivery. `clarifications` is registered `driver: "ui"` — it is
grown by a direct UI call, so there is no frame identity to gate on (ISS-108).

**Part 2 — three multiplicities per row, via `describe.each`.** They fail for different reasons:
partial redelivery (no intervening `agent_start` — an SSE resume mid-agent); full replay (the
whole log twice); and **triple** delivery, which catches a fix correct only at n=2.

**Part 3 — GUARD-1, the part that stops the family recurring.** A source assertion that a new
accumulator cannot be added without a registry row, in the shape this repo already sanctions
(`deadRevisionRefs.source.test.ts` calls it "the sanctioned grep-style source assertion").
Its detector keys on the **structural invariant** — *a property whose value both READS its own
previous value and GROWS it* — because idiom-matching is exactly what failed before: the
ISS-082 row's own `grep -nE '\+= 1|\.push\(|\.concat\('` matches a comment (`:431`) and a
local variable (`:954`) and **zero** real accumulators. Written against the seven known sites
FIRST and validated to find **exactly 7 with zero false positives** before being trusted; both
halves are asserted (nothing unregistered, and nothing registered unfound) so it can never
silently match nothing. The one growth-only line it correctly excludes is
`totalTokens: totalInput + totalOutput` — a recompute over overwritten values, the pattern the
six broken fields should have imitated.

**One harness, not two.** `runFrames` was EXTRACTED from `useWorkflow.specRevisionCount.test.ts`
to `__fixtures__/reducerHarness.ts` rather than copied: two replay harnesses would be two
different definitions of "re-delivery", which is the one thing this suite must not have. The
extraction is proven faithful by that spec's 21 tests still passing (and it caught its own
error first — the initial extraction missed two other users of `EMPTY_STATE` and went 5 red).

**Seen RED first — 12 failures, the investigation's observed values reproduced exactly**

| field | partial redelivery | full replay | triple |
|---|---|---|---|
| `output` | `"Hello worldHello world"` | converges | `...x3` |
| `thinkingText` | `"step one\nstep one\n"` | converges | `...x3` |
| `toolCalls` | 2 | converges | 3 |
| `validationIssues` | 2 | converges | 3 |
| `hookRuns` | 2 | **2** | 3 |
| `agentStartEventIds` | 1 | 1 | 1 (control — FIX-225 already held) |

Plus *"a genuinely NEW frame after a re-delivery still applies"* → `"Hello worldHello world!"`.
`hookRuns` is the only field that also doubles on a FULL replay, and that asymmetry is pinned
deliberately: `agent_start`'s FIX-039 reset is what makes the others converge, and nothing
resets `hookRuns`. `hook_run` is fed WITHOUT a `seq` because that is what the wire delivers —
`emit_hook_event` never reaches the engine's stamping chokepoint — so the case genuinely
exercises the unsequenced-id path rather than the cursor.

**Three mutation tests, so none of this is decoration**

| mutation | expected | observed |
|---|---|---|
| remove the per-run cursor reset | run 2's frames get swallowed | 1 failed / 29 passed — *"a different run resets the cursor"* |
| re-inject the deleted `runStoreHandleFrameRef` loop | the reconciled guard fires | 1 failed / 55 passed |
| drop `resolveFrameRunId`'s `sourceRunId` fallback | the A3 claim collapses | 3 failed / 9 passed — the live frame, the replayed frame, and the empty-id case |

**A3's safety is MEASURED, not reasoned.** The investigation said plainly that A3 was
"unverified by test; must be measured", and its blast radius turned out to be LARGER than
modelled — `page.tsx:1682` rebuilds the live message as `{ type, data }`, so the shadow was
`undefined` on the LIVE path too, not only the replayed one. That is why the run-id decision
was extracted into `wsReplayState` as `resolveFrameRunId`: so the claim could be tested
directly rather than argued. Its 6 tests pin what the OLD code returned for a live and a
REST-replayed agent frame (`undefined` in both cases) and what the new one returns.

**A stale guard was RECONCILED, never relaxed.** `liveRunSwitch.fix201.test.ts` asserted
`expect(body).toContain("runStore.get(runId)")` — whose only occurrence computed `hasLiveAgents`
for the very bypass ISS-082 deletes. Changed-behaviour, so the lock changes with it, and it is
now **tighter**: it forbids the mechanism instead of requiring it. The `pipeline_start` skip it
protected is subsumed by ISS-075, which MERGES the roster on a same-run re-announcement rather
than rebuilding it — so replaying `pipeline_start` can no longer reset live agents to idle.

```
TEST COVERAGE — FIX-235
Unit tests:        43 in backend/tests/agents/{test_hooks,test_audit_endpoints}.py  → ALL GREEN (A1 blast radius)
Integration tests: N/A — no integration surface; hook_run is a transient live-queue frame with no durable row
Frontend tests:    30 in frontend/src/hooks/useWorkflow.accumulators.test.ts        → ALL GREEN (12 seen RED first)
                    6 in frontend/src/lib/wsReplayState.test.ts (resolveFrameRunId) → ALL GREEN (3 RED under mutation)
                    1 reconciled in frontend/src/app/dashboard/liveRunSwitch.fix201.test.ts → GREEN (RED under mutation)
                   107 across the 8 specs touching the reducer                      → ALL GREEN
Goldens:           0 failed / 10 passed — IDENTICAL to the pre-change commit 07197b0e; 0 golden files modified
lint-imports:      4 kept / 0 broken — IDENTICAL to 07197b0e (run from backend/)
Full vitest:       147 failed / 860 passed (1007) vs 147 failed / 824 passed (971) at 07197b0e
                   → +36 passing, ZERO newly-red, ZERO newly-green, identical failing ID set
Mocked Playwright: 33 failed / 43 skipped / 108 passed — byte-identical to 07197b0e
Backend reds:      11 failed / 54 passed — IDENTICAL ID set to 07197b0e
tsc --noEmit:      2 errors, both pre-existing in test files not touched by this change
Regression guards:
  - GUARD-1 (accumulators): a new accumulator in useWorkflow.ts is RED until it has a registry row
  - GUARD-1 non-vacuity: the detector must find every registered site, so it cannot silently match nothing
  - the triple-delivery row: a fix correct only at n=2 fails
  - "a genuinely NEW frame after a re-delivery still applies": the cursor cannot over-block
  - "a different run resets the cursor": run 1's high-water mark cannot swallow run 2 (INV-2)
  - resolveFrameRunId x6: the store-routing decision, incl. what the pre-fix code returned
  - liveRunSwitch.fix201: the undeduped second replay pass stays deleted
  - deadRevisionRefs.source.test.ts: agentStartEventIds SURVIVED (ISS-083 depends on it)
```

**One Playwright ID pair moved between full-suite runs** (`ts-l.token-usage` `:38` <-> `:65`)
and was chased rather than waved away: run in isolation **three times on the reverted tree and
three times on the changed tree**, the file gives the identical result both ways
(`:65` + `:77` fail, `:38` passes). Full-suite parallelism noise, not this change.

---

### TEST-020 — FIX-236 (quick-260812-jn9): ISS-083 — proving a deletion, when a deletion has no naturally-occurring failing test

**The problem this suite had to solve.** FIX-236 removes code. Nothing fails before the change
and nothing newly passes after it, so the ordinary "watch it go red, then green" evidence does
not exist for free — it has to be **constructed**, and the construction is itself the finding.

**Files**

| file | tests | what it holds |
|---|---|---|
| `frontend/src/components/chat/ResultCard.test.tsx` | 3 (1 rewritten + 2 new) | the single-render proof, the static-header lock, the source guard |
| `frontend/e2e/tests/ts-chat-cards.spec.ts` | 1 reconciled | the stale assertion that only the deleted default could satisfy |

**T1 — `renders the revision cycle exactly once, from the narrator text` (the load-bearing one).**
Mounts the dormant renderer BY HAND with `content: "Revising spec — cycle 2"` and asserts
`getAllByText(/Revising spec — cycle \d+/)` has length **1**.

> **That the test must construct the message itself — that no fixture and no live path can
> supply one — IS the reachability finding restated as a test.** Nothing anywhere puts
> `spec_revision_attempt`/`revision_index` into an event payload, so the backend has never
> emitted this card: 0 instances across 232,023 durable `run_events` over 14 runs.

RED at HEAD `f12d99ae` with the exact predicted signature, and a **hard stop was pre-armed**:
green, a throw, or a received length of 0/1 would have meant the dual-copy model was wrong and
the fix had to be re-derived. Observed verbatim:

```
AssertionError: expected [ <p …(1)></p>, <p></p> ] to have a length of 1 but got 2
```

Two `<p>` elements — the header's FE-defaulted `cycle 1` and the body's backend `cycle 2` —
**the duplicate caught in the act**. The em dash was codepoint-checked (U+2014 at
`ResultCard.tsx:119`, `chat_narrator.py:157` and `ts-chat-cards.spec.ts:65`) *before* trusting
the count, because an en dash would have matched once and gone falsely green.

**T1b — `locks the spec_revision header to the static CARD_SPECS title`.** RED at HEAD with
`Unable to find an element with the text: Revising spec` (the header then read
`Revising spec — cycle 1`). Pins the header to `CARD_SPECS.spec_revision.title` so the chrome
cannot silently re-acquire a cycle number.

**T2 — `holds no dormant cycle prop`.** The sanctioned grep-style source assertion (same idiom
as the SC-001 guard at `:135-143` and `deadRevisionRefs.source.test.ts`). RED at HEAD:
`expected '"use client";…' not to match /cycle\?:\s*number/`. This is the permanent one — it
fails any future re-introduction of `cycle?: number` or `cycle ??`.

**The e2e reconciliation — landmine removal, not a regression fix.** The task brief said to
ignore Playwright because "it cannot exercise a card that is never emitted." **That was wrong,
and the planner caught it:** `mockSse.chatReply({ cardKind: "spec_revision", … })` fabricates
the narrator turn **client-side**, bypassing the backend narrator, so it reaches the branch the
backend cannot — and the `:65` assertion `toContainText("Revising spec — cycle 1")` was
satisfiable **only by the `?? 1` default being deleted**, since the injected body carried no
cycle string at all. The planner's counter-claim that the test was therefore green was **also**
wrong and was corrected by measurement: all three tests in that file are red on an unrelated
pre-existing `beforeEach` (`getByTestId('run-chat-lane')` not found, `:27`), registered under
**ISS-076**; the harness itself is healthy (`ts-b.selection.spec.ts` → 6 passed). So leaving the
stale assertion would have handed whoever repairs ISS-076 a **false green that silently
re-blesses the dual copy this fix exists to remove**. Corrected, never deleted or `test.fixme`d.

**The honest verdict on that gate: UNVERIFIABLE-GREEN by execution** — green is unreachable
until ISS-076 is fixed. It was proven instead by a before/after **identity** check: same 3
failures, same `beforeEach` error, no new failure mode (`:69`→`:75` is the 6 lines the edit
adds). That is the strongest claim the evidence supports and it is not dressed up as more.

**What this suite deliberately does NOT do.** It does not test wiring, because there is none
left to test — that is the point of the change. The family's recurring blind spot is the
opposite shape and is recorded on ISS-111: *a test that supplies a component's input itself
proves nothing about wiring.* The superseded test did exactly that (`cycle={3}`, feeding the
prop to itself), which is how a dead prop survived from Phase 29 to now.

```
TEST COVERAGE — FIX-236
Unit tests:        3 in frontend/src/components/chat/ResultCard.test.tsx  → ALL GREEN (all 3 seen RED first)
Integration tests: N/A — frontend-only presentation change, no seam crossed
Frontend tests:    ResultCard.test.tsx 1 failed / 10 passed (11) → 1 failed / 12 passed (13),
                   failing ID UNCHANGED (the pre-existing deliverable/LOCK-F red, ISS-114)
                   reducer specs 63 passed → 63 passed (the evidence that nothing was wired)
                   tsc --noEmit: the same 2 pre-existing errors, no third
E2E:               ts-chat-cards 3 failed → 3 failed, identical beforeEach failure — UNVERIFIABLE-GREEN (ISS-076)
Goldens:           10 passed / 0 failed — IDENTICAL to the pre-change commit f12d99ae
lint-imports:      4 kept / 0 broken — IDENTICAL to f12d99ae
Backend narrator:  36 passed — IDENTICAL to f12d99ae (proof the change never crossed the wire)
Regression guards:
  - holds no dormant `cycle` prop: permanently fails any re-introduction of the deleted prop
  - locks the spec_revision header to the static CARD_SPECS title: the chrome cannot re-acquire a cycle number
  - reducer specs held at 63: deriveSpecRevisionCount gained no new consumer (we deleted, not wired)
```


---

### TEST-021 — FIX-237 (quick-260812-kpb): ISS-087 — the tasks card must count the PLAN, not the build's progress

```
TEST COVERAGE — FIX-237
Unit tests:        N/A — frontend-only change; zero backend files touched.
Integration tests: N/A — no transport, endpoint, engine or manifest behaviour changed.
Frontend tests:    7 cases in
                   frontend/src/components/results/AgentDetailPanel.artifactCards.test.tsx (5)
                   frontend/src/components/results/AgentDetailPanel.artifactVersions.test.tsx (2)
                   = 4 NEW + 3 RECONCILED 42-09 pins. ALL GREEN.
                   ALL SEVEN seen RED first against the UNMODIFIED source (sources reverted
                   to HEAD 1f79ae64 with the final test files in place; observed
                   "Tests  7 failed | 18 passed (25)"), then restored.
Goldens:           10 passed / 0 failed — IDENTICAL to the pre-change commit 1f79ae64, AND
                   all 15 golden files sha256-IDENTICAL before/after (0 files moved).
lint-imports:      4 kept / 0 broken — IDENTICAL to 1f79ae64. Run from backend/ (from the
                   repo root it prints "Could not read any configuration" and reads as a pass).
tsc --noEmit:      2 errors — IDENTICAL to 1f79ae64 (NotificationPanel.fix195 +
                   useNotifications.fix202, both pre-existing). No third error introduced.
Mocked Playwright: e2e/tests/ts-n.review-gate.spec.ts — 8 passed / 1 skipped, including
                   "TS-N-02 preview mode: tasks render via the TasksPreview list". This is a
                   REAL BROWSER proof that the parser EXTRACTION is behaviour-preserving.
                   NB: the ISS-087 investigation asserted e2e reaches none of these surfaces.
                   That is WRONG — the gate plan-preview renders TasksPreview and is covered.
Blast radius:      src/components/results — 12 failed / 112 passed (124). The failing ID SET is
                   IDENTICAL to baseline (10 AuditTab + 2 FilesTab, both pre-existing); the
                   count moved only by the 4 new passing cases. Compared by ID, never by count.
                   Reducer specs 65 passed; AgentThinkingTab + StepsDrilldown 14 passed;
                   ResultCard 1 failed / 12 passed (ISS-114, pre-existing, untouched).
```

**RED-BEFORE, observed per case** (the whole point — a test that has never failed proves nothing):

| Case | RED message |
|---|---|
| counts the tasks in the artifact body, not the build's completed tasks | `AssertionError: expected false to be true` (no card rendered at all) |
| reads the plan after the build's `task_progress` frames are delivered TWICE | `AssertionError: expected +0 to be 7` |
| selecting v1 repaints the rows + count (run `6e38b9a7`) | `Unable to find an element with the text: /11 planned/` |
| repaints the TITLES at equal counts (run `5ecb990f`) | `Unable to find an element with the text: /8 planned/` |
| *reconciled* — selects the tasks card and counts the `<tasks>` body | `AssertionError: expected false to be true` |
| *reconciled* — single_shot shows its plan; empty body → no card | `AssertionError: expected false to be true` |
| *reconciled* — renders the tasks card + handoff | `Unable to find an element with the text: /3 planned/` |

**The three reconciled 42-09 pins** (`artifactCards.test.tsx:42-55`, `:57-67`, `:173-188`) — none deleted,
skipped or loosened:

1. *"selects the tasks card when output is `<tasks>` AND protoCompletedTasks is non-empty"* →
   **APPROVED BEHAVIOUR CHANGE + FIXTURE CORRECTION.** It asserted `taskCount === 3` and titles
   `["Scaffold","Wire","Style"]` from run state while its `TASKS_OUT` fixture was a **one-task** body —
   i.e. the fixture contradicted the assertion, which only passed because the numbers came from
   somewhere else. `TASKS_OUT` is now a genuine three-task plan and the same assertions hold for the
   right reason.
2. *"renders NO tasks card ... when protoCompletedTasks is empty (single_shot)"* →
   **APPROVED BEHAVIOUR CHANGE.** A `single_shot` agent carrying a `<tasks>` body now SHOWS its plan
   (owner D1). The conditional-degrade guarantee this case existed to protect is **preserved**, re-pointed
   at a `<tasks>` body containing no `## Task N:` rows.
3. *"renders the tasks card ('N planned' + task rows) + handoff"* → **APPROVED BEHAVIOUR CHANGE.** The
   panel is now given **no task props at all** and still renders the plan. `getAllByText` for the row
   assertion because an early task title also appears in the truncated raw-output preview below the card.

**Regression guards:**
  - *"reads the plan after task_progress delivered TWICE"*: uses the ONE existing reducer driver
    (`src/hooks/__fixtures__/reducerHarness.ts`), not a hand-rolled replay, and asserts the accumulator
    still reads **6** while the card reads **7** — proving they are different quantities and that the card
    no longer depends on the accumulator at all. This is ISS-082's multiplicity rule applied here.
  - *"repaints the TITLES when both versions plan the same number"* (run `5ecb990f`): the count is 8 in
    BOTH versions, so a count-only assertion would pass while the screen was still wrong. Only the titles
    discriminate.
  - *"Back to latest"* returns the card to 11 — the fix cannot strand the panel on an old version.

**REAL-DATA verification** (free — read-only `backend/dev.db`, no run launched, no Bedrock):
every `prototype-plan` artifact version of three terminal runs was fed through the **actual shipped**
`parseTasks` + `deriveArtifactCardModel`, and the latest version rendered through the real
`AgentDetailPanel` with the DOM read back:

| Run | build `completed_count` (what the card USED to show) | card now |
|---|---:|---|
| `d5dbc9f2` | 6 | v1/v2/v3 all **7 planned**; DOM reads **"7 planned"** |
| `6e38b9a7` | 11 | v1 **10 planned** (task 4 "Transaction Wizard Page (Steps 1–2)", absent from v2), v2 **11**; DOM **11** |
| `5ecb990f` | 8 | v1 **8**, v2 **8** — counts equal, task-4 titles differ ("Intake Wizard (…)" vs "Intake Wizard Page (…)") |

---

### TEST-022 — FIX-238 (quick-260812-lfv): ISS-102 — no offline test may construct a live model client

```
TEST COVERAGE — FIX-238
Unit tests:        6 in backend/tests/unit/test_iss102_live_model_guard.py   → ALL GREEN
Integration tests: N/A — this is test INFRASTRUCTURE; its blast radius is the whole
                   suite, so it is measured as the four-tree delta below rather than
                   by an integration case.
Frontend tests:    N/A — backend test-infra only; no frontend file touched.
Goldens:           0 failed / 10 passed — IDENTICAL to the pre-change commit d31a5a7b,
                   and all 15 golden file checksums byte-identical (shasum diff empty).
lint-imports:      4 kept / 0 broken — IDENTICAL to d31a5a7b (run from backend/).
Regression guards:
  - test_guard_blocks_the_smart_planner_bypass_path: proves the chokepoint covers the
    path build_model does NOT — SmartPlanner._build_llm builds its own client. This is
    the case that makes "guard the factory" demonstrably insufficient.
  - test_allow_list_entries_all_still_exist: the exemption dict FAILS CLOSED — every
    _CONSTRUCTS_BUT_NEVER_INVOKES nodeid must still resolve to a real file + test name,
    so a rename can never leave a stale exemption that protects nothing.
  - test_guard_preserves_isinstance_and_object_new: the guard patches __init__ and never
    the class object, so the two isinstance sites and the object.__new__ fixture survive.
```

**Fail-first, observed — not assumed.** The four "blocks" cases were run with the guard stood
down through its own `RUN_LIVE_BEDROCK=1` allowance (no code change, no revert):

| Guard | Result |
|---|---|
| stood down (`RUN_LIVE_BEDROCK=1`) | **4 failed / 2 passed** — construction succeeds, so the `pytest.raises` cases fail |
| active (default) | **6 passed** |

Both runs construct a client but **never invoke** it, so neither made a network call and
neither could produce a charge. Confirmed by `grep -c "ExpiredTokenException\|ConverseStream"`
= **0** on both.

**Suite deltas — every number observed at least twice (executor + orchestrator re-run).**

| Suite | BEFORE (d31a5a7b) | AFTER | Note |
|---|---|---|---|
| `tests/unit/test_chat_messages_endpoint.py` | 3 failed / 17 passed | 3 failed / 17 passed | same 3 ids; see ISS-119 for why they stay red |
| …its `ExpiredTokenException\|ConverseStream` grep hits | **4** (= 2 real `ConverseStream` calls) | **0** | this is the money fix |
| `tests/unit` | 62 failed / 1167 passed | 62 failed / **1173** passed | +6 = exactly the new file; FAILED **id set identical** |
| `tests/agents` + `properties` + `integration` | 57 failed / 1723 passed / 42 skipped | 57 / 1723 / 42 | FAILED/ERROR id set identical (`diff` empty); **0 guard trips** |
| goldens (5 characterization files) | 10 passed | 10 passed | 15 checksums unchanged |
| `lint-imports` (from `backend/`) | 4 kept / 0 broken | 4 kept / 0 broken | |

**Reach demonstration (the planted test).** A temporary 4-probe plant was run and removed:
`build_model()` → TRIPPED; `SmartPlanner()` → TRIPPED; `isinstance` → passed; `object.__new__`
→ passed. The guard message named the nodeid verbatim
(`tests/unit/test_zz_iss102_plant.py::test_plant_2_smart_planner_bypass_path`), the class
(`ChatBedrockConverse`) and three remedies. All three allowances were then exercised
independently: `RUN_LIVE_BEDROCK=1` → 4 passed (guard stands down); `@pytest.mark.requires_api_key`
→ that case passed while the two unmarked plants still failed in the SAME run; nodeid allow-list
→ the 8 exempted tests stayed green across all four trees.

**Coverage honesty.** These 6 cases prove the guard's mechanism, not that any particular
production seam reaches it. That second property is proven by the suite as a whole: a trip
anywhere fails that test by name, and the four-tree runs above recorded **0 trips**, which is
the positive evidence that the 8-entry allow-list is complete.

### TEST-023 — FIX-239 (quick-260812-mq5): ISS-034 — the SIGNED prompt-cache dollar delta

```
TEST COVERAGE — FIX-239
Unit tests:        8 in backend/tests/agents/test_iss034_cost_full.py        -> ALL GREEN
                   4 in backend/tests/unit/test_analytics_api.py (appended)  -> ALL GREEN
Integration tests: N/A - no new IO boundary. The durable-row site is exercised through the
                   analytics endpoint cases above (real FastAPI + real SQLAlchemy session
                   against an in-memory SQLite), which is where the legacy-row trap lives.
Frontend tests:    5 in frontend/src/components/analytics/AnalyticsPage.test.tsx -> ALL GREEN
Goldens:           0 failed / 10 passed - IDENTICAL to the pre-change commit c05906c0,
                   and all 15 golden FILES byte-identical by SHA-256 (not merely "passing")
lint-imports:      4 kept / 0 broken - IDENTICAL to c05906c0
Regression guards:
  - test_engine_cost_site_emits_full_cost_key / test_run_commands_cost_site_emits_full_cost_key:
    both cost sites keep emitting the counterfactual. Source-pins, so they survive a refactor
    that moves the code but not the contract - and they sit beside the existing INV-12 guard
    (test_model_pricing.py:216-233) which independently forbids a rate literal at either site.
  - test_short_run_that_never_re_reads_its_cache_costs_MORE: the NEGATIVE direction, anchored
    to observed run a7dba362. This is the case an unconditional "saved" gets wrong.
  - test_long_run_that_re_reads_its_cache_SAVES: the POSITIVE direction (run 6e38b9a7).
  - test_run_with_no_cache_activity_has_exactly_zero_delta: run 0a27b397 - the counterfactual
    collapses onto the real price, so the renderer must show nothing.
  - test_normalizer_strips_full_cost_key / test_normalize_drops_pipeline_complete_full_cost_key:
    INV-3. The key stays out of the golden multiset.
  - test_legacy_rows_contribute_zero_delta_not_a_zero_baseline: THE money guard.
  - test_mixed_window_counts_only_the_metered_run_in_the_delta: a legacy row in the same
    window must neither dilute nor invert the delta.
  - AnalyticsPage "says COST MORE when caching was a net loss": pins the signed copy.
```

**Fail-before, observed - not asserted.** The new backend file was run at `c05906c0` BEFORE any
source edit: **4 failed / 4 passed**. The 4 passes are deliberate — they are the pure sign
arithmetic, which is already true at HEAD, so they corroborate the -7.47% / +83.25% / 0.00%
claims independently of the feature. The 4 reds are exactly the 4 things the fix builds.

**The money guard was proven by mutation, not by inspection.** With the guard reverted to the
naive `r_cost_full = _num(usage.get("estimated_cost_full_usd"))`, the legacy-window case failed
with `spend_full = 0.0` against `spend = 15.0` — the **-100%** figure D2 predicted — and the
mixed-window case failed with `0.32011` against `2.32011` (the legacy row priced as if an
uncached run were free). Both went green the moment `or r_cost` was restored.

**Golden neutrality was proven in BOTH directions.** Emitted **and** stripped -> 10 passed,
all 15 golden files byte-identical. Emitted and **NOT** stripped (the strip line commented out
as a control) -> **5 failed / 5 passed**, every `*_event_snapshot` red; the 5 survivors are the
deliverable BYTE snapshots, which do not read the event payload. That pair is what proves the
green run is caused by the strip rather than by the key silently never being emitted.

**The frontend cases have teeth.** They were written after the component, so `cacheSaved` was
mutated to a constant `true`; the "says COST MORE when caching was a net loss" case went red
and the other 8 stayed green — i.e. the suite catches precisely the unconditional-"saved"
defect that ISS-034's original wording would have shipped.

**Coverage honesty.** No live Bedrock run was launched (a prototype build is 5-21M tokens, and
the 11 persisted rows are sufficient evidence). What is therefore NOT proven offline: that a
real cached run's emitted `estimated_cost_full_usd` reconciles end-to-end against a fresh
`workflow_runs` row. Deferred to the end-of-milestone live pass per the standing rule. The
arithmetic itself is anchored to observed production numbers rather than invented fixtures,
which is the strongest offline substitute available.



### TEST-024 — FIX-240 (quick-260812-ppu): ISS-121 — the engine event the chat lane destroyed

```
TEST COVERAGE — FIX-240
Unit tests:        2 in backend/tests/unit/test_run_events.py   (10 -> 12)  -> ALL GREEN
                   1 in backend/tests/unit/test_sse_stream.py   (42 -> 43)  -> ALL GREEN
Integration tests: N/A - no new IO boundary. Both new run_events cases already run the REAL
                   ScopedStore + the REAL _RunEventSink against a real SQLAlchemy session on
                   in-memory SQLite with the actual uq_run_events_scope_seq constraint doing
                   the arbitration, and the second drives the REAL execute() wrapper.
Frontend tests:    N/A - zero frontend files changed (`git status` confirms 4 backend files).
                   The pre-existing ResultCard.test.tsx red and the 2 tsc errors therefore
                   cannot have moved; this is a structural claim, not a measurement.
Goldens:           0 failed / 10 passed - IDENTICAL to the pre-change commit 9e3dc9b0,
                   and 0 golden FILES moved (git status clean under golden/)
lint-imports:      4 kept / 0 broken - IDENTICAL to 9e3dc9b0
Pre-existing reds: 22 failed / 176 passed across the 9-file sweep - IDENTICAL ID SET to
                   9e3dc9b0, re-measured in a detached worktree (never a stash)
Regression guards:
  - test_engine_sink_survives_a_raced_seq_instead_of_losing_the_event: the primary proof. It
    reconstructs the live shape of run 808612bf - parked at a review gate, rejected through
    the chat lane - and asserts the durable ROW LIST, then that persist() reports the seq the
    row actually landed on, then that derive_open_gate(rows) == (None, None). The ROW, not the
    frame: the live stream is intact on every path, so any probe reading execute()'s output
    passes on the broken code. That is precisely how ISS-091's three offline probes missed it.
  - test_execute_restamps_seq_onto_the_frame_it_yields: drives the REAL execute() wrapper with
    a scripted _execute_impl (the _sink kwarg is the production arming seam) and asserts row.seq
    == data["seq"] for EVERY event. This is the Last-Event-ID contract: run_stream renders the
    SSE id: cursor from row.seq on replay (:198) and from data["seq"] live (:264), so a retry
    that did not re-stamp would corrupt resumption - a worse bug than the one being fixed.
    It also pins that the allocator advances PAST the displaced seq, so the event after the
    collision does not collide in turn.
  - test_terminal_run_does_not_rearm_even_with_a_dangling_gate: part (b). Seeds exactly the
    corruption shape - a log ending on an unresolved review_gate_ready after a chat_message,
    with the pipeline_cancelled row missing - on a run whose persisted status is cancelled,
    and asserts no re-arm frame.
  - The two _BoomStore fakes in test_run_events.py were re-pointed from append_event to
    append_event_at_or_after. Their ASSERTIONS are unchanged: the SQLAlchemyError case must
    still degrade silently and the RuntimeError case must still propagate (WR-02). This is a
    fake tracking the seam it doubles, not a loosened test.
```

**Fail-before, observed - and then observed a second time on the assertions themselves.**
All three were run at `9e3dc9b0` before any production edit: `2 failed, 10 passed` in
`test_run_events.py`, with the failure text naming the cause verbatim -
`UNIQUE constraint failed: run_events.run_id, run_events.owner_id, run_events.workspace_id, run_events.seq`
on the `pipeline_cancelled` insert.

That first RED surfaces as a `PendingRollbackError` on the read-back, because the rejected flush
poisons the shared test session - real, but it means the assertion itself had not yet been seen
to discriminate. So each was re-run under a **mutation** of the shipped code rather than trusted:

* retry disabled in `append_event_at_or_after` (`if True: raise`) ->
  `AssertionError: the engine's terminal event was silently DROPPED by the seq collision`,
  `Right contains one more item: 'pipeline_cancelled'`, and
  `AssertionError: terminal row lost to the seq collision` /
  `assert 'pipeline_cancelled' in {'agent_chunk': 3, 'chat_message': 2, 'review_gate_ready': 1}`.
  That second dict is also the direct evidence for the blast-radius claim: the engine's counter
  kept running and **exactly one** event died.
* the terminal guard removed from `run_stream.py:255` ->
  `AssertionError: a terminal run must NOT re-arm a dangling gate`,
  `Left contains one more item: {'type': 'review_gate_ready', ...}`.

Both mutations were reverted and the reverted state re-verified (`55 passed`) before the commit.

**What CANNOT protect this, stated so nobody re-litigates it.** The characterization goldens
compile `gate_agent_ids=[]` and contain zero `review_gate_ready` and zero `pipeline_cancelled`;
they snapshot the yielded stream with `seq`/`event_id` stripped, against no database. They are
the **neutrality** gate here, never the detection gate. `test_gates.py` and
`test_declared_gate_streaming.py` read the yielded generator and are blind to a durable-row loss
by construction.

**The golden hazard that IS real, and how it was measured rather than argued.**
`assert_seq_contiguous` (`characterization/_normalize.py:297-320`) pins `data["seq"]` DELTAS at
exactly 1 on the RAW, pre-normalize stream. A retry-and-re-stamp design is safe only if no
re-stamp can fire in the harness. The harness's persist failure was captured directly
(`pytest -o log_cli=true --log-cli-level=WARNING`) and is a `sqlite3.IntegrityError`
**FOREIGN KEY constraint failed** - not the `OperationalError` the degrade branch's own comment
implies. A naive "retry on IntegrityError" would therefore have fired 8 attempts per event across
every golden **and** re-stamped the seq. The shipped discriminator - retry only when the measured
tail actually reaches the attempted seq - re-raises immediately in that case, which is why the
goldens stay 10 passed with 0 files moved.

---

### TEST-025 — FIX-241 (quick-260812-sgu): ISS-070 — the gate action that approved a denial

```
TEST COVERAGE — FIX-241
Unit tests:        13 in backend/tests/unit/test_rest_gate_commands.py  (15 -> 28)  -> ALL GREEN
                   (1 unknown-action refusal + 10 parametrised denial variants
                    + 1 bare-POST default pin + 1 vocabulary set-equality)
Integration tests: N/A - no new IO boundary. Every case already drives the REAL FastAPI route
                   through a TestClient over the real `run_commands` router, the REAL
                   ArtifactStore singleton, and the REAL owner/terminal predicates against
                   in-memory SQLite - i.e. the HTTP boundary IS what is under test.
Frontend tests:    N/A - zero frontend files changed (`git status` shows 2 backend files).
                   `frontend/src/lib/api.ts:694` already declares the closed union
                   `"approve" | "reject" | "redo" | "update_specs"`; this fix makes the server
                   ENFORCE what the TS type only annotated, so no FE edit is required or wanted.
Goldens:           0 failed / 10 passed - IDENTICAL to the pre-change commit e6b24ae5,
                   and 0 golden FILES modified (`git status --porcelain -- golden/` empty)
lint-imports:      4 kept / 0 broken - IDENTICAL to e6b24ae5
Pre-existing reds: 14 failed / 104 passed across the 5 gate-adjacent suites
                   (test_chat_messages_endpoint, test_gates, test_declared_gate_streaming,
                    test_mechanical_router, test_rest_run_launch) - IDENTICAL ID SET to
                   e6b24ae5, re-measured by swapping in `git show HEAD:...run_commands.py`
                   and diffing the sorted FAILED lines (never a stash).
                   Plus 2 failed / 70 passed on the directly-affected four suites, the two ids
                   being the known pre-existing
                   test_concierge_proposal_channels::test_confirm_round_trip_executes_revision_seam
                   and test_attach_replay_matrix::test_last_event_id_header_resumes_over_http.
ruff:              3 errors on run_commands.py - IDENTICAL to e6b24ae5 (F401 :482, E402 :1852,
                   F841 :2425), all outside the changed regions; line numbers shifted only.
Regression guards:
  - test_case_and_whitespace_variants_of_reject_never_approve: the headline. Ten spellings a
    real user could plausibly send to STOP a run - 'Reject', 'REJECT', ' reject', 'reject\n',
    'rejct', 'no', 'deny', 'Redo', 'redo ', 'update-specs' - must each be refused, write
    NOTHING to the store, and leave the review event ARMED.
  - test_unknown_gate_action_is_refused_not_approved: pins the three-part contract (refused /
    nothing written / gate still armed) on a single typo, so the intent survives if the
    parametrise list is ever edited.
  - test_bare_gate_post_still_defaults_to_approve: the REGRESSION PIN. `action` must stay
    OPTIONAL with its `approve` default. Green BEFORE and AFTER - it is the only test here
    that was never red, and that is the point.
  - test_gate_action_literal_matches_the_single_vocabulary_authority: INV-12. Set-equality
    between the schema Literal and `chat_router.GATE_ACTIONS`, so a fifth action cannot be
    added to one home and silently diverge from the other.
```

**Seen RED first — 12 of the 13, at `e6b24ae5`, verbatim:** `12 failed, 16 passed`. The ten
parametrised variants each failed as `AssertionError: action='...' was accepted: {"ok":true,
"action":"...","gate_key":"..."}` / `assert 200 in (400, 422)`; the set-equality case failed as
`set() != {'redo', 'update_specs', 'reject', 'approve'}` (a bare `str` annotation has no
`get_args`). The 13th, `test_bare_gate_post_still_defaults_to_approve`, was green before and
after by design.

**The laundering, observed rather than inferred.** A throwaway in-process probe against the
HEAD endpoint printed what the STORE actually received, not just the HTTP status:

```
action='reject'         HTTP200 approved=False stored_action='approve'    gate_still_armed=False
action='Reject'         HTTP200 approved=True  stored_action='approve'    gate_still_armed=False
action='rejct'          HTTP200 approved=True  stored_action='approve'    gate_still_armed=False
action='update-specs'   HTTP200 approved=True  stored_action='approve'    gate_still_armed=False
```

Every garbage action persisted `action="approve"` while the HTTP response echoed the raw string
back. After the fix the same probe reads `HTTP422 / approved=None / stored_action=None /
gate_still_armed=True` for all ten. Note row 1: a legitimate `reject` ALSO stores
`action="approve"` — functionally inert (the engine keys on `approved`, `engine.py:5852`/`:5859`)
and deliberately left alone as out of scope; recorded here so it is not rediscovered.

**Both layers mutation-proved independently — the reason there are two.**

| Mutation | Result on the ten variants |
|---|---|
| Layer A reverted (`action: str`), Layer B kept | all **HTTP400** from the dispatch's fail-closed `else`; nothing stored; gate armed. 12 passed. |
| Layer B reverted (`else: # approve`), Layer A kept | all **HTTP422** from the schema; nothing stored; gate armed. 12 passed. |

Neither layer is decoration: A validates the wire and publishes the enum, B holds for any
in-process caller or a future fifth `Literal` member added without a branch.

**Traps this suite exists to survive.** (1) `test_attach_replay_matrix.py:551` posts
`{"gate_key": ...}` with no `action` key at all; a `Literal[...] = "approve"` keeps it green,
making `action` *required* would not — verified after the change that OpenAPI still reports
`required: ['gate_key']` with `"default": "approve"` alongside the new enum. (2)
`test_rest_gate_commands.py:362` is a grep-ratchet reading `resolve_gate`'s SOURCE TEXT for the
literal substring `action == "redo"`; refactoring the if/elif chain into a dict or `match`
turns it red, so only the `else` branches were touched and `:253`/`:257`/`:268` are byte-identical.

**Why the goldens cannot protect this, stated as a limitation rather than a pass:**
`grep -c review_gate_ready` returns **0 for all 15 golden files** — they compile
`gate_agent_ids=[]`, so no golden contains any gate event at all. They are the NEUTRALITY gate
here (proof nothing else moved), never the detection gate — the same framing FIX-232 and FIX-240
both recorded.

---

### TEST-026 — FIX-242 (quick-260812-syf): ISS-097 — the fan-out gate nobody could see

```
TEST COVERAGE — FIX-242
Unit tests:        4 backend, ALL GREEN
                   2 new  backend/tests/agents/test_restart_resume.py       (64 -> 66)
                     - test_fanout_workers_do_not_arm_the_inline_review_gate
                     - test_selecting_a_non_fanout_agent_still_opens_its_inline_gate
                   1 new  backend/tests/agents/test_merge_conflict.py       (13 -> 14)
                     - test_kernel_services_run_merge_agent_opts_out_of_the_inline_gate
                   1 strengthened backend/tests/agents/test_fanout.py
                     - test_run_worker_passes_wave_width_and_single_shot_view now ASSERTS
                       invocation_gated is False
                   + 3 stub-arity repairs in backend/tests/unit/test_pipeline_failure_semantics.py
                     (_run_agent doubles pinned a stale positional signature; they now absorb
                      additive keyword-only params instead of pinning an arity)
Integration tests: N/A - the headline test already drives the REAL public entry
                   (engine.execute), the REAL run_fanout, the REAL _run_review_gate and a REAL
                   in-memory-SQLite ScopedStore against a scripted model. The kernel path IS
                   what is under test; there is no new IO boundary.
Frontend tests:    N/A - 0 frontend files changed.
Goldens:           0 failed / 10 passed - IDENTICAL to the pre-change commit eb12bc7e,
                   and 0 of the 15 golden FILES moved (sha256 manifest diffed before/after)
lint-imports:      4 kept / 0 broken - IDENTICAL to eb12bc7e (run from backend/)
Neighbouring:      test_fanout_cancel 9 -> 9 (FIX-232 undisturbed)
                   test_rest_gate_commands 28 -> 28
                   7 fan-out suites (sc001/composed/sample_wave/fanout/merge_conflict/
                     budget/isolation) 108 -> 109
                   12 seam-adjacent suites 93 passed
                   test_gate_stub_signature_drift 4 passed
Pre-existing reds: 27 failed / 159 passed across the 10 briefed suites - IDENTICAL ID SET.
                   The 5 reds in the seam-adjacent suites (test_phase6_frontend_consistency x2,
                   test_sample_brownfield_workflow x2, test_text_only_prompt_hygiene x1) were
                   re-measured IN A DETACHED WORKTREE AT eb12bc7e: 5 failed / 38 passed, same
                   ids, both sides. Never a stash.
Regression guards:
  - test_fanout_workers_do_not_arm_the_inline_review_gate: a gated fan-out step must not arm
    ONE inline gate per worker, must not hang, and must leave no subagent_runs row 'running'.
  - test_selecting_a_non_fanout_agent_still_opens_its_inline_gate: the neutrality pin - a
    single_shot step's agent named in gate_agent_ids STILL gates exactly once, so the fix can
    never be satisfied by disabling gating everywhere.
  - test_run_worker_passes_wave_width_and_single_shot_view: pins invocation_gated=False at the
    run_worker seam.
  - test_kernel_services_run_merge_agent_opts_out_of_the_inline_gate: same pin for the merge
    sibling, whose events are consumed with a bare `pass`.
```

**RED first, and re-proven RED after the tests reached their final shape.** The first run failed
with `the run HUNG at an invisible fan-out worker gate: 4 gate arm(s) on ['sample-wave-worker'],
0 review_gate_ready frame(s) on the wire` after a 20 s timeout. The test was then refactored (see
the guard note below), so the RED was **re-established by mutation**: removing the two
`invocation_gated=False` opt-outs from `kernel_services.py` turned 3 of the 4 tests red — the hang
test with the identical 4-arm/0-frame message, and both seam pins with `assert True is False`.
The 4th (the neutrality pin) correctly stayed green, because it pins behaviour the fix does not
change.

**The method trap, measured — any future gate work on this harness must repeat it.**
`_ResumeHarness.make_engine` (`test_restart_resume.py:365`) assigns an empty async generator to
`engine._run_review_gate` as an **instance** attribute, silently shadowing the real bound method.
With the `del engine._run_review_gate` line commented out, the *identical* test passes **GREEN in
1.07 s** against a live 4-arm hang. That is not a hypothetical: it is why the original
investigation nearly filed ISS-097 as "not reachable". The helper `_count_gate_entries` now owns
the un-shadow and documents it.

**Why the original row's suggested test would have proved the wrong thing.** ISS-097 proposed
"count `review_gate_ready` events — 1 is correct, N is the bug". That measures **zero**, because
`fanout.py:414-429` discards every worker event before it can reach the emit boundary. A zero
reads as "no gates opened", i.e. a pass. The working assertion counts `_run_review_gate`
**entries** and asserts the run **terminates**.

**A guard caught the first attempt, which is the guard working.**
`test_gate_stub_signature_drift.py` — the AST census that exists for exactly this defect family —
rejected an initial `_run_review_gate` double patched at CLASS level: its leading `engine_self`
parameter could not bind the engine's real all-keyword call, and its restore assignment
(`= self._orig`) was unresolvable to the census. The test was rewritten to the file's dominant
instance-patch idiom with `*a, **kw`, which both binds whatever the signature grows into and stays
visible to the census. The guard is green.

**Why the goldens cannot protect this, stated as a limitation rather than a pass:**
`tests/agents/_scripted_model.py:649` is literally `gate_agent_ids=[],  # suppress all gates`, so
**zero** gate events exist in any of the 15 golden files. They are the NEUTRALITY gate here (proof
nothing else moved), never the detection gate — the same framing FIX-232, FIX-240 and FIX-241 all
recorded. INV-3 is argued from the new flag's default-`True` dormancy, not from golden silence.

**Live verification deliberately not run.** The offline harness reproduces the full defect path
through the real kernel at zero model spend; a live fan-out would cost real money to observe the
same hang. Deferred per the standing end-of-milestone rule.

---

### TEST-027 — FIX-243 (quick-260812-tni): ISS-089 — a Stop that survives the process

```
TEST COVERAGE — FIX-243
Unit tests:        20 in backend/tests/unit/test_rest_answers_cancel.py  → ALL GREEN
                   (10 pre-existing + 10 new; 2 of the pre-existing RECONCILED)
Integration tests: N/A — the defect is entirely decidable from a synthetic driver
                   registry + a durable store; the money hole is proven by the boot
                   scan's TASK COUNT, not by spending tokens.
Frontend tests:    N/A — 0 frontend files changed. Both postCancel call sites
                   (DashboardLayout.tsx:1654, :1788) are `void ….catch(console.error)`;
                   the response body is never read, so the new response sub-case cannot
                   reach the UI.
Goldens:           0 failed / 10 passed — IDENTICAL to 2df5324b, and 0 of the 15 golden
                   files moved (git status of the golden dir empty on both sides)
lint-imports:      4 kept / 0 broken — IDENTICAL to 2df5324b (run from backend/)
Regression guards:
  - test_a_cancelled_run_creates_no_driver_task_on_the_next_boot: the money assertion.
  - test_the_non_terminal_status_set_has_exactly_one_definition: INV-12 source guard.
  - test_terminal_cancel_response_is_byte_identical_to_the_pre_iss089_ack: idempotence.
  - test_cross_owner_cancel_writes_nothing: the new write path is behind the owner gate.
```

**Every new case was seen RED first**, in a **detached worktree at `2df5324b`** with the
new test file copied in (never a stash). Verbatim failures:

| test | RED message at `2df5324b` |
|---|---|
| `test_cancel_without_a_live_driver_is_made_durable` | `AssertionError: the owner's Stop was dropped: {'ok': True, 'run_id': '…', 'accepted': False, 'cancelled': False, 'status': 'not_running', 'message': 'No active pipeline'}` |
| `test_a_durably_cancelled_run_is_outside_the_boot_restore_set` | `ImportError: cannot import name 'NON_TERMINAL_RUN_STATUSES' from 'agents.execution_engine.engine'` |
| `test_durable_cancel_appends_a_pipeline_cancelled_row` | `assert [(1, 'pipeline_start')] == [(1, 'pipeline_start'), (2, 'pipeline_cancelled')]` — `Right contains one more item` |
| `test_durable_cancel_appends_past_an_already_occupied_seq` | `AssertionError: the audit row was dropped on a seq collision instead of re-appended: [(1,'pipeline_start'),(2,'pipeline_start'),(3,'pipeline_start'),(4,'chat_message')]` |
| `test_durable_cancel_survives_a_failed_audit_append` | `AssertionError: assert 'not_running' == 'cancelled'` |
| `test_a_cancelled_run_creates_no_driver_task_on_the_next_boot` | `AssertionError: {'accepted': False, …} assert 'not_running' == 'cancelled'` |
| `test_the_non_terminal_status_set_has_exactly_one_definition` | `ImportError: cannot import name 'NON_TERMINAL_RUN_STATUSES' …` |

**The boot-scan case asserts ZERO DRIVER TASKS, not "no exception".** Its early
`status == "cancelled"` assertion short-circuits at `2df5324b`, so the scan itself was
re-run there with that assertion removed, to prove the task-count assertion is
discriminating rather than vacuous:

```
AssertionError: the next boot re-adopted a run the owner stopped and spawned
['ExecutionEngine.restore_non_terminal_runs.<locals>._admitted_resume'] —
this is the token-burn hole ISS-089 exists to close
PRE-FIX cancel response: {'ok': True, …, 'accepted': False, 'status': 'not_running'}
```

That is the defect in one line: the API said *not running*, and the next boot spawned a
resume driver for the same run. The assertion counts `asyncio.create_task` calls made by
`restore_non_terminal_runs` (spy installed only for the duration of the scan, coroutines
closed so a unit test never DRIVES a resume). Non-vacuous by construction — the run is
seeded **resumable in-flight** (compilable type + one durable `run_events` row), which is
exactly branch (b)'s admission condition.

**The source guard was mutation-tested against the surviving duplicate**, not merely
observed green: with the `engine.py` extraction applied but `scripts/cutover_legacy_runs.py`
left holding its own copy, it fails with
`the non-terminal status set is defined 2 times: ['agents/execution_engine/engine.py:478', 'scripts/cutover_legacy_runs.py:28']`.
It is an AST walk over `agents/`, `app/` and `scripts/` for any assignment whose value is a
string collection equal to the 7-status set — so it catches a copy under **any** name, not
just a re-used identifier.

**The seq-collision case is a real mutation, not a stub.** The first tail probe reports the
tail as it was *before* the racing chat-lane row committed at `max+1`, so the endpoint
attempts an occupied seq. A naive `append_event` stops there and the row is lost to the
persist degrade (FIX-240 / ISS-121's exact failure mode); `append_event_at_or_after`
re-probes, finds the real tail, and lands past it. Asserted on the landed seq (`5`), not on
"no exception".

**Two reconciles — changed behaviour, never a loosened test.**
`test_cancel_does_not_claim_success_without_a_live_driver` and
`test_cancel_is_idempotent_with_no_active_event` both seeded `status="running"` and
asserted `accepted:false`. That assertion **is** the defect ISS-089 removes. Both now seed
a **terminal** run, which preserves their ISS-084 invariant ("never claim an outcome
nothing achieved") in the case where it still holds; the non-terminal case is covered by
the new tests, where `cancelled:true` is *earned* — the endpoint really does make the
cancellation durable. Neither assertion was weakened and neither test was deleted.

**Test-harness safety note, recorded because it is a live-data hazard.** The `env` fixture
now also patches `run_commands._get_db` and `app.models.database.SessionLocal`. Before
ISS-089 the cancel endpoint never wrote, so patching only `run_engine._get_db` was
sufficient; `run_commands` binds `_get_db` at import (`from app.api.run_engine import
_get_db`), and `ScopedStore` / `_recover_workspace_id` open `SessionLocal()` themselves.
Leaving either unpatched would have pointed the new writer at the real `dev.db`. `dev.db`
was snapshotted before the work and re-verified after: 21 runs, status sha256
`ed90b0bb1c036eecdf544f1f2ba309635e999a68c94007291fe9aba7176fa504`, 233,574 `run_events`
— unchanged, with run `41f77342` still `waiting_for_user`.

**Pre-existing reds, re-measured after the change and unchanged by ID (32 total):**
`test_gates.py` 3 · `test_declared_gate_streaming.py` 3 · `test_wire_parity.py` 4 ·
`test_prompt_contracts.py` 1 · `test_model_factory.py` 6 · `test_rest_run_launch.py` 2 ·
`test_chat_messages_endpoint.py` 3 · `test_mechanical_router.py` 3 ·
`test_concierge_proposal_channels.py` 1 · `test_attach_replay_matrix.py` 1 ·
`test_phase6_frontend_consistency.py` 2 · `test_sample_brownfield_workflow.py` 2 ·
`test_text_only_prompt_hygiene.py` 1. A 12-suite blast-radius sweep (`test_rest_resume`,
`test_resumability`, `test_runs_api*`, `test_sse_stream`, `test_run_events`,
`test_chat_contract`, `test_approve_review_ownership`, `test_execution_engine`,
`test_cancel_stops_resumed_run`) is **138 passed / 3 failed**; those 3 are the ISS-093
stale clarify-round tests, **re-measured in a detached worktree at `2df5324b`** as the same
3 failures with the same ids — pre-existing, with a SHA, not a label.

**No live verification, deliberately.** Nothing here needs a live build: the defect is
fully decidable from a synthetic registry plus a durable store, and the assertion that
matters is a task count. One `od_prototype` build costs 5–21M tokens on the register's old
figure — the **measured ceiling on this corpus is 37.3M tokens / $7.07**, and the incident
that motivated the row cost **$3.58**, ≈**$1.61** of it after the cancel.

### TEST-028 — FIX-244 (ISS-124): the app-layer driver terminals must be DURABLE

`backend/tests/unit/test_rest_answers_cancel.py`, 4 new (file 20 → 24). **All 4 seen RED at `ce2db22e`**, each failing on its own assertion.

| test | what it proves | RED evidence at `ce2db22e` |
|---|---|---|
| `test_launch_driver_cancellation_is_durable` | the launch driver's `CancelledError` branch appends a durable `pipeline_cancelled` ROW carrying a real `event_id` | `expected exactly one durable pipeline_cancelled row, got []` |
| `test_launch_driver_durable_row_survives_a_real_task_cancel` | **the discriminating case** — the append lives inside an `except asyncio.CancelledError` block, so it must complete while the task is being cancelled FOR REAL (`stop_run_driver` reaches this branch via `task.cancel()`, not by the engine raising) | `a real task.cancel() left no durable terminal: []` |
| `test_a_cancelled_driver_reconciles_to_cancelled_not_failed` | the user-visible half: `_reconcile_terminal_status` (which `stop_run_driver` runs once the driver is gone) no longer takes the D2 fail-safe and overwrite the owner's Stop | `assert 'failed' == 'cancelled'` |
| `test_revision_driver_cancellation_is_durable` | the second locus, `_drive_revision_to_queue`, has the same shape and the same hole | `expected exactly one durable pipeline_cancelled row, got []` |

**Discipline notes.** Every assertion is on the durable ROW, never on the queued frame — the frame is already correct today, which is exactly why earlier probes for this class of defect missed it. The real-`task.cancel()` test also **corrected a wrong assumption of my own**: its first version asserted the task re-raises `CancelledError` and failed with `DID NOT RAISE`, because the driver deliberately CONVERTS the cancellation into a terminal (`_drain_then_cancel` only needs `task.done()`). The assertion was fixed against observed behaviour, and the observation is recorded in the test body so the next reader does not re-derive it.

**Regression gates:** goldens 10 passed / **0 golden files moved** (SHA-256 compared vs `ce2db22e`); `lint-imports` 4 kept / 0 broken; `test_run_events.py` 12, `test_sse_stream.py` 43, `test_restart_resume.py` 66, `test_rest_gate_commands.py` 28 — all identical to `ce2db22e`. Combined final run: **183 passed**.

### TEST-029 — FIX-245 (ISS-126): a reopened terminal run renders as terminal

23 new frontend tests across two files. **20 seen RED at `ce2db22e`**; the 3 added after the live-browser findings pin strings **proven absent at `e3c38594`** (`git show e3c38594:… | grep -cF` → 0 for each), which is the same fail-before evidence in a form a source-lock test can carry.

**`terminalStatusReconcile.test.ts` (reducer + INV-12 guards).** `terminalMarkers` per status; `applyTerminalStatus` flipping a gate-paused run to terminal-cancelled and standing agents down; the **one-way** rule (a non-terminal status returns `prev` by identity, so a slow `getWorkflow` on a live run cannot clear an open gate); a source assertion that the three live terminal event cases **spread** `terminalMarkers` (a *copy* would drift — this is the anti-shadow guard); a behavioural cross-check that the EVENT path and the STATUS path agree; and a test pinning the marker map's membership **EQUAL** to `page.tsx`'s `REOPEN_TERMINAL_STATUSES`, which is what stops the fix becoming a fifth divergent terminal list.

**`terminalReopenReconcile.source.test.ts` (page wiring).** Ordering is the whole point: the reconciliation must run **AFTER** the `for (const frame of durableFrames)` loop — placed before it, the replayed `review_gate_ready`/`pipeline_start` overwrite it and a naive presence assertion still passes. Also pins: both containers are reconciled (store **and** legacy — see ISS-138); the clarify panel is cleared; `reviewGateData` is **not** cleared within the reconciliation window; and the fix is **not** inside the unreachable `case "pipeline_cancelled": case "pipeline_failed":` arm (ISS-139), with the unreachability itself re-proven in the test.

**Regression method — IDs, never counts.** Full vitest **871 → 894 passed** (+23 = exactly the new tests) with the failing set **147 → 147** and the failing **test IDs byte-identical**, diffed against a baseline measured in a **detached git worktree at `e3c38594`** (`git worktree add --detach`, never `git stash`). `tsc --noEmit` the same 2 pre-existing errors. The pinned reducer guards — the ISS-035 cancel-marker suite, the FIX-039 accumulator-reset guard, `useWorkflow.reconnect`, `attachRunOnOpen.source` — are all green, which is what proves the routing was a **move, not a copy**.

**And the tests were still not enough.** With all of the above green, the fix was INVISIBLE in a real browser. The live A/B on `808612bf` (corrupted) vs `1ea6d262` (clean control) is the gate that caught it — twice, for two different reasons (ISS-138's wholesale bridge overwrite, then the `laneClarifyOpen` branch). Final live result: both runs render `lane-run-status` **"Cancelled"** (tone=neutral) with no Stop control and no gate actions.

### TEST-030 — FIX-247 (quick-260813-1b1): ISS-139 + ISS-140 — a cancel at the clarify gate must repaint the screen

```
TEST COVERAGE — FIX-247
Frontend e2e (mocked Playwright): 1 NEW test (TS-R-05, frontend/e2e/tests/ts-r.cancel.spec.ts)
  → seen RED against the unfixed source (git checkout ae208b53^ -- page.tsx), independently
    reproduced by both the fix's executor AND the orchestrating agent separately — IDENTICAL
    failure both times: lane-run-status stuck at "Clarifying" (data-status-tone="running"),
    timeout waiting for /Cancelled/. Then GREEN after the fix, independently re-run: 1 skipped
    (pre-existing TS-R-04 fixme), 4 passed.
Frontend unit (vitest source-locks): 2 files reconciled (terminalReopenReconcile.source.test.ts,
  liveRunSwitch.fix201.test.ts) → npx vitest --run on both: 2 passed (2 files), 35 passed (35
  tests) — includes the 8 OTHER unmodified it() blocks in terminalReopenReconcile.source.test.ts
  (an unrelated ISS-126/FIX-245 suite) still green.
Full mocked e2e suite regression check: PAIRED measurement, page.tsx reverted vs HEAD, same
  session — baseline (reverted) 34 failed/108 passed/43 skipped; post-fix (HEAD) 31 failed/111
  passed/43 skipped. Set-diff of the two failed-test-name lists: ZERO tests newly failing
  post-fix; three tests flip baseline-only (ts-r.cancel:117 = TS-R-05 = the fix itself;
  ts-l.token-usage:77 and ts-t.history:65 = proven pre-existing parallel-worker flake, unrelated
  to this diff, see ISS-145 below).
Full frontend vitest suite: 147 failed / 894 passed / 1041 total post-fix — IDENTICAL count
  independently measured twice (once by the executor, once by the orchestrator). This baseline
  itself is badly stale relative to what's on record elsewhere in this repo (see ISS-145) — NOT
  caused by, NOT fixed by, this change.
Goldens: 10 passed / 0 failed (collected 10 items — not a false-pass from bad path collection),
  IDENTICAL to the pre-change commit d2d2da53. Zero golden files touched (git status --short on
  the characterization/golden tree: empty).
lint-imports: 4 kept / 0 broken (run from backend/, /opt/homebrew/bin/lint-imports).
Live browser (real backend + real frontend + real SSE, not mocked): TWO fresh cheap
  (user_stories, ~$0.01 each) runs. FIXPROBE: clarify card confirmed rendered (15 chips / 4
  questions / AWAITING YOU) before Stop; sampled at t+3s/8s/15s/25s after Stop — all four samples
  identical: "Cancelled", Stop absent, clarify submit absent, chip count 0, terminal-cancelled
  card present, API status cancelled. GATEPROBE (regression control, the review-gate path this
  fix does NOT touch): review gate confirmed armed before Stop; sampled at the same four
  intervals — all identical: "Cancelled", Stop absent, both gate actions absent,
  terminal-cancelled card present. Neither script could touch the forbidden paused od_prototype
  run (41f77342...) — both assert the launched run id doesn't match it; confirmed via read-only
  API check before and after that it stayed untouched at waiting_for_user.
Regression guards:
  - TS-R-05 (frontend/e2e/tests/ts-r.cancel.spec.ts): pins the user-visible repaint contract —
    cancel while paused at clarify must clear Stop/clarify-submit/clarify-chips and show the
    Cancelled terminal card, sampled after a real SSE round-trip via mockSse.
  - terminalReopenReconcile.source.test.ts (rewritten it block): pins that the dead switch arm
    stays deleted and the live block keeps carrying the store write.
  - liveRunSwitch.fix201.test.ts (rewritten it block): pins the SAME, plus that the write stays
    inside the run-scoping if (!isForeignFrame) guard (the T-1b1-01 threat-model mitigation).
```

**Why TS-R-05 is a SEPARATE `test.describe` block.** `frontend/e2e/tests/ts-r.cancel.spec.ts` already carried a `TS-R — cancel` suite whose `beforeEach` starts a **BUILDING** run — the wrong starting state for a clarify-gate scenario, and adjusting it would have changed the meaning of four existing tests. TS-R-05 lives in its own `test.describe("TS-R — cancel at clarify")` with its own setup instead.

**Two source-lock reconciliations, and only one of them was planned.** `terminalReopenReconcile.source.test.ts` was known (TEST-029 deliberately pinned the unreachable arm's existence as part of ISS-126's proof). `liveRunSwitch.fix201.test.ts` was **not anticipated by the plan** — a second lock on the same dead code via a different string, found mid-execution. Both were reconciled with identical reasoning and both came out **TIGHTER, never relaxed**: from "the dead arm exists and is where it should be" to "the dead arm is GONE and the live block carries the store write", with the `liveRunSwitch` one additionally asserting the write stays inside `if (!isForeignFrame)`. **Both had been GREEN while pinning code that had never once executed** — the lesson worth carrying: a source lock satisfied only by unreachable code proves nothing about behaviour.

**Why the regression proof is PAIRED rather than compared to a recorded baseline.** The frontend baselines written down elsewhere in this repo ("~8 vitest reds", "mocked e2e 132/0") are stale by roughly an order of magnitude — measured fresh here as 147 vitest reds and a 34-failed e2e baseline, independently twice (ISS-145). A recorded baseline that cannot be trusted cannot certify a regression, so both suites were measured **in the same session, reverted vs HEAD**, and the verdict is a **set-diff of failing test NAMES**, not a count: zero newly failing.

**Live verification, and the money rules.** Two fresh `user_stories` runs only (~$0.01 each) — never `od_prototype`. The paused `od_prototype` run `41f77342-b3c4-42ee-bf9c-215209dfc2aa` was never launched, resumed or approved; both probe scripts assert the launched run id does not match it, and a read-only API check before and after confirmed it stayed at `waiting_for_user`. GATEPROBE exists as the **regression control** on the review-gate path this fix deliberately does not touch — and it is also what independently reproduced ISS-143 (the header "N Running" pill going stale after a cancel), which is a different defect and was filed rather than folded.

### TEST-031 — FIX-248 (quick-260813-3wo): ISS-146 — a replayed narrator card must carry its row's identity

```
TEST COVERAGE — FIX-248
Backend unit: 1 NEW test (TestReplayIdentityProjection::test_replayed_identity_less_chat_reply_carries_its_row_identity,
  backend/tests/unit/test_sse_stream.py) → seen RED against the unfixed projection:
  `assert data.get("event_id") == row_event_id` failed with `AssertionError: assert None == '<uuid>'`
  (event_id simply absent from the replayed frame's data). Then GREEN after the one-line fix.
  Also reconciled the PRE-EXISTING exact-body assertion in test_replay_from_cursor_projects_seq_frames
  (line ~180: `assert replay[0]["data"] == {"seq": 2, "text": "hi"}`) to include the row's REAL,
  DB-read-back event_id — not a hardcoded literal (it is a random uuid4 per test run).
  Whole file, isolated: 43 passed/0 failed (baseline) → 44 passed/0 failed (post-fix), independently
  re-run by the orchestrating agent after the executor's own report (identical count both times).
Frontend e2e (mocked Playwright): 1 NEW test (TS-SSE-RESILIENCE-06, frontend/e2e/tests/ts-sse-resilience.spec.ts)
  → mounts the REAL app (not a modeled/raw-fetch consumer, unlike the file's other 4 tests) and
  reproduces the ACTUAL production mechanism end to end: launches via the real launch flow (so
  sessionStorage `tab_launched_run_ids` is genuinely populated), fires a real browser `online` event
  WHILE the run is still active (arming `RunConnectionProvider.autoIdsRef`, the precondition that
  defeats `detachRun`'s insurance — verified via `mockSse.runListFetchCount` actually incrementing,
  not just the event being dispatched), drives to `pipeline_complete`, then emits the narrator
  deliverable card so it lands on the durable tail strictly AFTER the terminal frame — mirroring how
  the engine actually queues it. Required 2 corrections to `frontend/e2e/fixtures/mockSse.ts` that
  did not exist before this fix: (a) replay-vs-live awareness in `serialize()`/`handleStream()` (a
  frame already pending when a stream response begins is a REPLAY frame; one arriving later, waking
  a parked long-poll, is LIVE) — temporarily paired with a `simulatePreFixReplay` flag to model
  today's pre-fix server, DELETED in the fix commit, no dead toggle left behind; (b) the durable REST
  twin `GET /api/runs/{id}/events` (`handleRunEvents`), previously UNMOCKED entirely (fell through to
  `mockApi`, which does not implement it either) — meaning the completion-backfill path
  (`page.tsx` → `getRunEvents`) was invisible to the WHOLE mocked suite before this fix, not just this
  test. Seen RED (received 2 cards, expected 1) against the pre-fix-modeling mock, then GREEN
  (exactly 1 card) once the mock's replay path was corrected to mirror the shipped
  `run_stream.py:202` merge. Full file, isolated, both via `npx playwright test` and the project's own
  `npm run e2e -- ts-sse-resilience`: 5 passed (7.6s) — TS-SSE-RESILIENCE-01/02/03/04 unperturbed.
Mocked e2e suite-wide impact of the new REST-twin mock endpoint: 34 failed/108 passed/43 skipped
  (pre-change baseline) → 33 failed/110 passed/43 skipped (final, Task-6 state, the endpoint they
  needed was simply absent before). ZERO tests moved pass→fail versus the baseline in either
  measurement taken. **CORRECTED CLAIM, not the original one:** an interim measurement (taken while
  the since-deleted `simulatePreFixReplay` stripping was still active) showed 30 failed/112 passed
  with 3 `ts-t.history` rows (`:37`/`:65`/`:110`) flipped green; the commit message on `57498dd8`
  reported this as "three pre-existing ts-t.history failures fixed" — that claim was WRONG. Those 3
  rows are FLAKY under this suite's parallel workers, not durably fixed: they read red again in the
  final (Task 6) measurement, and the orchestrating agent independently re-ran
  `ts-t.history.spec.ts` alone afterward and observed 5 failed / 2 passed with `:37` among the
  failures — confirming the correction, not the original claim.
Goldens: 10 passed / 0 failed (5 characterization files, 2 tests each — `tests/agents/characterization/`
  ALONE collects 0 items and is NOT the right invocation, the exact ISS-145 collected-0/exit-0 trap;
  the right selection is the 5 `test_characterization_*.py` files under `tests/agents/`). Zero golden
  files touched (`git status --porcelain`/`git diff --stat` on the fixtures: empty), independently
  re-run by the orchestrating agent, not just the executor.
lint-imports: 4 kept / 0 broken (run from `backend/`, `/opt/homebrew/bin/lint-imports` — "Analyzed 215
  files, 526 dependencies"), independently re-run.
Live browser (real backend + real frontend + real SSE, not mocked): ATTEMPTED, NOT COMPLETED.
  Two fresh `user_stories` attempts (`SSEFIXPROBEV2`, `SSEFIXPROBEV3`) both failed within ~9s of
  leaving clarify — EVERY agent returned "The model rejected this request." The backend log
  (`scratchpad/backend-3wo.log`) shows the real cause on both: `botocore.errorfactory.InvalidGrantException:
  An error occurred (InvalidGrantException) when calling the CreateToken operation: Invalid refresh
  token provided`. Confirmed as an infrastructure issue, not a code issue: `AWS_PROFILE=hex-ai-fe aws
  sts get-caller-identity` independently fails the same way ("Token has expired and refresh failed"),
  and `aws sso login --profile hex-uki` requires an interactive browser OAuth completion no agent can
  perform. A first attempt (`SSEFIXPROBE`, before the SSO issue was diagnosed) separately surfaced a
  PRE-EXISTING gap in the reproduction script `20-live-control.mjs` — it clicks "skip all" exactly
  once, but this pipeline can ask a SECOND clarify round, leaving the run stuck at `waiting_for_user`.
  A corrected script (`scratchpad/24-live-control-v2.mjs`, loops the skip-click and gates the
  network-drop on the run's REAL status rather than a fixed timer) is written and ready, but has not
  yet been run to completion because Bedrock access is down for both available SSO profiles. **This
  live pass is a follow-up, not a closure condition waived** — recorded honestly as blocked, not as
  passed.
Regression guards:
  - TestReplayIdentityProjection (backend/tests/unit/test_sse_stream.py): pins that a durable-replay
    frame for an identity-less app-layer row carries the row's REAL event_id/seq, merged from the
    columns — the root-cause-level guard.
  - TS-SSE-RESILIENCE-06 (frontend/e2e/tests/ts-sse-resilience.spec.ts): pins the user-visible
    contract end to end — one narrator milestone renders as exactly ONE chat card across a
    terminal-close reconnect racing the completion backfill, through the REAL app code, not a
    hand-simulated consumer.
```

**Why no `useRunChat.test.ts` hook-level unit test was added, on purpose.** The obvious construction — hand-build two frames with mismatched identity (one with no `event_id`, one with a different one) and assert `handleFrame` collapses them to one message — was considered and REJECTED. FIX-248 is a server-only wire-contract fix; it changes nothing in `useRunChat.ts`. Such a test would still be RED after the fix, with no path to GREEN inside this change's scope, because the frontend reducer code it exercises is byte-unchanged. This codebase has ZERO precedent for an intentionally-red/inverted-assertion **unit** test (`grep -rn "\.fails(" frontend/src frontend/e2e` returns nothing; the one "documented known gap" idiom, `test.fixme`, is Playwright-e2e-only). Rather than invent a new pattern or commit a permanently-failing test, the mounted e2e test above is the correct, buildable, mechanically-sound proof at the frontend layer instead — it exercises the SAME reducer code through the REAL wire-parsing path (`useRunStream`), which is strictly better coverage than a hand-simulated hook test would have been.

**Why the naive "emit card, then drop the connection" test shape could never go red, and what replaced it.** `useRunStream.ts` advances its resume cursor from `data.seq` on every dispatched frame, so a card already processed live is never replayed on a plain drop-then-reconnect — there is no race to catch. The REAL mechanism (traced end to end by direct source reading of `RunConnectionProvider.tsx` and `page.tsx`, not guessed) is: the SSE endpoint's own `_STREAM_TERMINAL_TYPES` includes `pipeline_complete`, so the live drain returns the instant it drains that frame — the narrator card, queued right after it, is NEVER delivered live at all on that connection. The client's `pipeline_complete` close then schedules a reconnect (`useRunStream.ts:301` omits `pipeline_complete` from its non-live list — filed separately as ISS-147, not fixed here), and that reconnect's replay is what raced the completion backfill. Getting the test to reproduce this needed one more precondition the first attempt at this test missed: the run's id must ALSO be in `RunConnectionProvider.autoIdsRef` (armed by an `online`/`visibilitychange` wake while the run is still active) or `detachRun`'s insurance unmounts the connection before any reconnect can happen — exactly mirroring why the live `DROP=1` (network blip mid-run) and `DROP=0` (no blip) probes differ.

**Live verification is a genuine follow-up, not a skipped step.** Unlike every other TEST entry in this register, this one does not carry a completed live-Bedrock pass. The blocker (AWS SSO refresh-token invalidity across both available profiles) was diagnosed with the same rigor as the code fix — read the actual backend traceback, cross-checked with a direct `aws sts`/`aws sso login` probe — rather than assumed or retried blindly. Do not treat FIX-248 as live-proven until this is closed out.

### TEST-032 — FIX-249 (quick-260813-5qr): ISS-148 — the Concierge must be able to answer a token/cost question, and honest when it cannot

```
TEST COVERAGE — FIX-249
Backend unit: 6 in backend/tests/agents/test_concierge_capability.py → ALL GREEN after the fix
  (2 UPDATED, never weakened + 4 NEW):
  - test_read_tools_expose_only_the_bounded_allow_list (updated: exact tool-name set now
    includes "get_token_usage")
  - test_system_prompt_names_only_existing_tools (strengthened: the prompt must actually
    MENTION get_token_usage, not merely that it exists in the built tool surface — its
    `missing = {...} - mentioned` set gained the new tool name)
  - test_get_token_usage_returns_the_narrow_run_totals (NEW): populated-usage case, asserts
    total_tokens/input_tokens/output_tokens/estimated_cost_usd against a fixture whose numbers
    are mutually distinct, so a field transposition (input<->output) would fail
  - test_get_token_usage_omits_cache_and_model_fields (NEW): asserts the returned key set is
    EXACTLY {available, total_tokens, input_tokens, output_tokens, estimated_cost_usd} — key-set
    EQUALITY, not a subset — plus an absent-substring sweep for total_cache_read_tokens /
    total_cache_write_tokens / cache_read_tokens / cache_write_tokens / model_id /
    estimated_cost_full_usd, all present in the source blob and deliberately excluded
  - test_get_token_usage_degrades_to_unavailable_not_zeros (NEW): covers BOTH a None
    token_usage column and a malformed-JSON blob; asserts available=False + a truthy error
    string (load-bearing, see below) and no numeric field the model could mistake for a real
    measurement
  - test_response_rules_do_not_forbid_token_counts (NEW): asserts "token counts" is absent from
    the composed system prompt, "model names" is still present (deliberately untouched — see
    the surfaced-not-decided item below), and the new honesty literal ("I can't see that from
    here") is present
Whole file, isolated (python3.11 -m pytest tests/agents/test_concierge_capability.py -q):
  baseline (HEAD before this fix, commit a9f95835) = 34 collected, 33 passed, 1 failed (1
  PRE-EXISTING, see below — unrelated to this fix).
  RED (Task 1: tests added, concierge.py byte-unchanged) = 38 collected, 31 passed, 7 failed
  (the 6 above + the 1 pre-existing). The 3 tool tests failed via StopIteration (tool not found
  in the built surface) — red for the right reason, not an incidental assertion mismatch.
  GREEN (Task 2: concierge.py fixed) = 38 collected, 37 passed, 1 failed (same 1 pre-existing,
  unchanged failure reason).
  Independently re-run by the orchestrating agent after the executor's own report, at BOTH the
  RED and GREEN stages — identical counts each time, not just trusted.
Goldens: 10 passed / 0 failed (the 5 test_characterization_*.py files under tests/agents/ — the
  bare tests/agents/characterization/ directory alone collects 0 items, the known ISS-145 trap:
  "collected 0 items" with exit 0 reads as a false pass). git status --porcelain confirms zero
  golden fixture files touched. Independently re-run by the orchestrating agent.
lint-imports: 4 kept / 0 broken (run from backend/ — "Analyzed 215 files, 526 dependencies";
  from any other cwd it prints "Could not read any configuration" and false-passes).
  Independently re-run.
Extra gates (not required by the plan, run for completeness by the orchestrating agent):
  test_sc001_lane_router_concierge.py (9 passed) + test_banned_patterns.py (14 passed) = 23
  passed. Confirms no workflow-name literal was introduced into concierge.py and INV-13 holds
  (the new tool constructs no model/agent/runner).
Regression guards:
  - test_every_read_tool_denies_cross_owner: BYTE-UNCHANGED, stays GREEN. Its predicate
    (`not out or out == {} or out.get("error") or out.get("agents_started") == 0`) is WHY the
    unavailable shape must carry a truthy `error` key — a bare {"available": false} matches none
    of those branches and would have turned this standing security guard red. Satisfied by
    returning honest data, never by loosening the assertion.
  - test_no_tool_accepts_a_run_id_argument: unaffected — get_token_usage takes zero parameters,
    so run scoping stays a closure, never model-controlled input.
  - test_no_tool_returns_unbounded_event_history (the ISS-092 bound, 25,000-char ceiling): sweeps
    every tool _read_tools returns and automatically covers the new one — its result is a few
    hundred bytes, trivially bounded, no new ceiling needed.
```

**The one pre-existing failure is a stale test, not a regression — filed separately (ISS-151),
not fixed here.** `test_compose_system_prompt_injects_chain_hints_block` fails at
`assert "chained into" not in no_hints and "follow-up" not in no_hints` because the BASE prompt
(unrelated to chain hints) now unconditionally contains both literals — "Never ask the user
**follow-up** questions..." (RESPONSE RULES) and "chain it into a **follow-up** workflow" /
"**chained into**" (INTENT ROUTING). Reproduced independently, byte-identical, both BEFORE and
AFTER this fix; the fix's own new honesty-rule sentence was confirmed to contain neither literal,
so it neither caused nor worsened this. The test's positive half (`no_hints == empty_hints`)
still passes and is unaffected.

**The narrow return shape is a deliberate, tested scope decision, not an oversight.** The source
`workflow_runs.token_usage` blob (`app/api/run_commands.py:2332-2354`) carries seven keys; the new
tool surfaces four of the numeric ones plus `available`. Cache read/write, `model_id`, and the
uncached-counterfactual cost are asserted ABSENT by `test_get_token_usage_omits_cache_and_model_fields`
so a later widening fails CI instead of shipping silently — those three areas are real, separately
tracked gaps (ISS-149), not accidental omissions. The original investigation's own recommended
tool shape included cache read/write; the resolving orchestrator deliberately narrowed it so this
fix does not silently close part of ISS-149 without that being a decision anyone made on purpose.

**An ID collision was resolved before allocation.** The four-source sweep (register + card store +
commit messages on this branch AND `origin/dev` + `git log --all`) confirmed FIX-248/TEST-031/
ISS-147 are genuinely taken — by `quick-260813-3wo`'s SSE-replay fix, a different defect entirely —
with no further collisions above that floor, landing this entry at TEST-032/FIX-249/ISS-148.

---

**Note (2026-08-13, quick-260813-as6): TEST-032's summary-table row was missing above — added
retroactively during this pass, backfilled from this section's own numbers. The detailed section
itself was always present and correct; only the one-line table row had been skipped.**

### TEST-033 — FIX-250 (quick-260813-as6): ISS-152 — the revision driver must persist all 7 output columns

```
TEST COVERAGE — FIX-250
Backend unit: 1 new in backend/tests/unit/test_rest_revisions.py → GREEN after the fix
  - test_driver_happy_path_persists_output_columns (NEW): drives the full agent_start →
    agent_chunk → agent_complete → pipeline_complete vocabulary through the existing
    _StubEngine/_drive harness (mirrors test_driver_persists_model_id_and_prices_non_circular in
    test_rest_run_launch.py) and asserts all 7 previously-lost columns are populated:
    output, agent_outputs (agent_id + duration + token fields), token_usage (exact
    total_input/output/total_tokens), duration (not None), model_id (threaded from
    owner.preferred_model), deliverable_mimetype, deliverable_filename.
Isolated (python3.11 -m pytest tests/unit/test_rest_revisions.py::test_driver_happy_path_persists_output_columns -v):
  RED (against unmodified run_commands.py) — 1 failed:
    AssertionError: assert None == '<html>revised</html>'
     +  where None = <app.models.workflow.WorkflowRun object>.output
  GREEN (after the fix) — 1 passed.
Whole file, isolated (python3.11 -m pytest tests/unit/test_rest_revisions.py -v), at the
  committed state (e127684e): 15 collected, 13 passed, 2 failed. Both failures PRE-EXISTING and
  UNRELATED — proven, not asserted: identical 2 tests run against an unmodified `git worktree`
  checked out at the pre-fix commit 48c76403 (never `git stash`) produced BYTE-IDENTICAL error
  messages (`AttributeError: '_FakeUser' object has no attribute 'tier'`, the KAN-161/ISS-055
  entitlement gate reading a stale test double — already a documented defect class, ISS-102/
  ISS-119, in a completely different test file). Worktree removed after comparison.
Adjacent regression file, isolated (python3.11 -m pytest tests/unit/test_rest_run_launch.py -v):
  25 collected, 23 passed, 2 failed — both ALSO pre-existing/unrelated, same worktree-comparison
  method, byte-identical failures both sides (test_unsatisfiable_custom_composition_rejected_pre_mint,
  test_owned_source_links_the_child — neither touches _drive_revision_to_queue or
  _apply_terminal_output_columns's behavior, only its docstring, which this fix also edited).
Goldens: 10 passed / 0 failed (the 5 test_characterization_*.py files under tests/agents/).
  git diff --stat confirms zero golden fixture files touched (only run_commands.py and
  test_rest_revisions.py changed). Independently re-run by the orchestrating agent, twice.
lint-imports: 4 kept / 0 broken (run from backend/; "Analyzed 215 files, 526 dependencies").
Regression guards:
  - _apply_terminal_output_columns itself is UNMODIFIED except its docstring — it stays the sole
    writer of these 7 columns for all four callers now (launch, both resume entry points, and
    the revision driver), so a resume-completion or launch-completion row is unaffected by this
    change; only the revision driver's terminal write gained the missing call.
  - duration_seconds is computed from the driver's own time.monotonic() delta, never
    pipeline_complete.total_duration, so this fix does not add a THIRD disagreeing duration
    source on top of the pre-existing ISS-150 gap.
LIVE VERIFICATION — full pass performed and PASSED (Bedrock, user_stories only, ~$0.01-0.02
  total). Backend restarted first (uvicorn runs without --reload here) so the live pass actually
  exercised the fixed code. SSO confirmed via a real Bedrock model call inside the run itself,
  not `aws sts get-caller-identity`. The prescribed chat-driven script (31-revise-confirm.mjs)
  did NOT create a revision this time — the Concierge classified the message as channel=gate_action,
  not revision (backend log: "Concierge proposal disposed: run=... channel=gate_action held=True");
  unrelated to this fix (that classification code, run_commands.py ~lines 1009-1262, is untouched
  by this diff) and most likely live-LLM tool-selection variance — NOT filed as an issue on one
  unreproduced data point. Switched to the deterministic POST /{id}/revisions REST endpoint
  instead — one of the same three entry points that funnel into the exact driver this fix
  touches. Dispatched against the existing completed user_stories parent a5d059e1...
  (SSEPROOFDROP) with instruction "ISS152PROOF add an acceptance criterion for orders placed
  after 5pm requiring next-day manager approval" → run 5914e5f1... completed in 8s.
  GET /api/runs/5914e5f1... verbatim: output = the full revised user story INCLUDING the new
  criterion verbatim; agent_outputs = 1 entry (user-story-revision-agent, duration 2.13,
  input_tokens 3951, output_tokens 294, total_tokens 4245); token_usage = {total_input_tokens:
  3951, total_output_tokens: 294, total_tokens: 4245, estimated_cost_usd: 0.005963, ...};
  duration = 2.2; model_id = null (CORRECT, not a gap — the QA user has no preferred_model set,
  so None is exactly what the launch driver would also persist for the same user; the cost
  estimate still uses the settings fallback internally, hence the real non-zero
  estimated_cost_usd); deliverable_mimetype = "text/markdown"; deliverable_filename =
  "user_stories.md"; error = null. Disambiguated against a false-positive read: parent v1 has
  total_tokens=24016, the old un-backfilled v2 (8a970205) still has token_usage=None — the
  "4.2K tokens" seen throughout the UI is uniquely this new row's real number.
  UI: History row showed "v3 · 4.2K" inline before even opening it (screenshot
  33-history-search.png). Opened family (screenshot 33-opened.png): header "USER STORIES
  REVISION · Done · ... · 2s · 4.2K tokens", version v3, full Product Backlog rendered with the
  new criterion verbatim. Zero HTTP≥400 responses during the whole pass.
  THE FIX-249 PROOF (screenshot 33-concierge-reply.png): asked in the revision run's own chat
  lane, "How many tokens did this run use in total, and what did it cost?" — live reply,
  verbatim: "This run used 4,245 total tokens and cost an estimated $0.01." Matches the row's
  own numbers exactly. This is the interaction FIX-249 was defeated on for every revision before
  this fix; it is now repaired.
  Analytics (screenshot 33-analytics.png): Est. Cost $18.28 across 22 completed runs, rendering
  without error; the "User Stories" (revision) pipeline-type bucket shows "4 runs · 4.2K ·
  <$0.01" — every revision previously forced a hard $0.00 in every bucket it touched.
  No-regression control (screenshot 34-opened-default.png, as directed, re-run post-fix):
  reopening the family still works (defaults to the new latest v3) — did NOT regress.
```

**A genuine NEW defect surfaced while running the no-regression control — filed ISS-154, NOT
caused by this fix, NOT fixed here.** Explicitly switching the in-family version picker to the
OLDER, non-latest v2 (`8a970205`, deliberately never backfilled) shows a blank "Output will
appear here" preview (screenshot `34-v2-selected.png`). Root cause, read directly:
`frontend/src/components/preview/PreviewPanel.tsx:528-543` `handleSelectVersion` sets
`viewingVersion.content = run.output` with no fallback. Confirmed NOT introduced by this fix: the
diff is 100% backend, touches no frontend file, and `8a970205`'s own data is byte-unchanged
before/after. See ISS-154 for the full analysis.

**Two items surfaced, not silently performed.** The `wr.error` omission (`_persist_terminal_status`
has no `error` parameter — a failed revision gets no reason) is a SEPARATE, deliberately unfixed
defect in the same function, filed ISS-153. The one-row backfill of `8a970205`'s 7 columns from
its own durable `run_events` (lossless per the originating investigation's own replay,
precedent `scripts/cutover_legacy_runs.py`) was deliberately NOT performed — left as an open
owner decision.

**ID allocation, four-source sweep run and recorded.** FIX: register/card-store/this-branch-
commits/all-commits all topped out at 249 → **FIX-250**. ISS: register max 151 (also the max
across FIX-REGISTER mentions, card store, and `git log --all`) → **ISS-152/153/154**. TEST:
FIX-TEST-REGISTER max 032 (card store's TEST-NN series is a DIFFERENT series, correctly not
used) → **TEST-033**. No collisions found.

