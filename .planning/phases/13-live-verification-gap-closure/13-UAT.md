---
status: resolved
phase: 13-live-verification-gap-closure
source: [.planning/live-verification/REPORT.md]
started: 2026-06-11T19:00:00Z
updated: 2026-06-12T00:04:48Z
provenance: >
  Gaps found by the 2026-06-11 post-milestone live-Bedrock verification pass
  (real Haiku 4.5: phase-8 live suites 43/46, full WS product-path driver, an
  instrumented context-routing probe, SC-001 real-model proofs, and semantic
  review of every workflow's per-agent outputs by 8 parallel Opus 4.8 agents).
  Root causes were diagnosed live during that pass with file:line evidence —
  no separate diagnose step needed; ready for /gsd-plan-phase 13 --gaps.
deferral: >
  FULFILLED 2026-06-12 (milestone-end live re-pass — .planning/live-verification/
  REPORT-2026-06-12.md): (a) od_ppt retest DONE — template seeding works (real
  glob/read_file on seeded files; composer streamed a 21K template-driven deck)
  but surfaced NEW finding LV-02: the ppt deliverable resolution returned the
  validator's QA narration instead of the composer's deck (od-ppt-validator
  output-contract gap, F5 family); (b) dotnet_to_azure + chat re-captured CLEAN
  un-throttled (13 agents / ~1MB file-bundle deliverable, final XML-clean;
  residual stream-level tool-XML confined to the sdlc-governance agent family);
  mulesoft WITH an embedded source listing VERIFIED — the inventory agent
  produced a faithful 5-flow estate inventory (10/13 agents before quota).
  F1/F4/F5 live re-confirms also done: F1 PASS both gate paths; F4 PASS on
  product paths (0 XML) with the sdlc-governance residual noted; F5 PASS 5/5
  fixed agents + 3 minor residuals (see REPORT-2026-06-12.md).
---

## Current Test

[testing complete — gaps diagnosed during the live pass]

## Tests

### 1. Declared human gate is approvable from a connected client
expected: A `gates: [human]` step (prototype specify/plan) emits review_gate_ready on the live WS stream, the client approves via approve_review, and the run proceeds
result: issue
reported: "Wire evidence (ws-prototype frames): review_gate_ready and review_gate_approved arrive TOGETHER, after the gate was already unblocked by a speculative approver re-sending approve_review blind. Without that workaround the run hangs at the first declared gate with no UI signal — the gate awaits the response INSIDE gate evaluation before any event reaches the consumer, and it clears its event on arming so pre-approval is discarded."
severity: major

### 2. run_revision works against a completed parent run (FE PPT revision flow)
expected: run_revision {parent_run_id, target_artifact_type: 'ppt_output'|'od_ppt_output', instruction} passes FR-014 validation and drives a revision
result: issue
reported: "Replayed the FE's exact frame (DashboardLayout.tsx:396 sends target 'ppt_output') against a freshly completed live ppt run: 'No artifact of type ppt_output found... Revision MUST NOT proceed without original context (FR-014)'. grep shows NO backend code ever persists a ppt_output/od_ppt_output artifact kind — runs persist kinds by agent id + summary/planning_context/clarifications. Every run_revision fails; the FE only uses its legacy fallback when no run id exists, so PPT revision is user-broken whenever a completed run is present."
severity: major

### 3. Failed-agent runs terminate visibly (no silent pipeline_complete)
expected: A run whose agents hard-fail (missing template/design_system injects without od_context) fails fast at ingress or terminates as pipeline_failed
result: issue
reported: "ws-prototype (bare, no od_context): all 4 agents emitted agent_error ('declares injects=[template,...] but no template body was loaded') and the run STILL ended pipeline_complete with final_output='' in 12s. ws-ppt: 2/3 agents halted the same way and the run 'completed' with a deck improvised entirely by the validator (role inversion, caught by semantic review). Silent degradation: the user sees success with an empty or unplanned deliverable."
severity: major

### 4. Text-only agents do not fabricate tool-call XML; handoff coder returns JSON
expected: Agents with tools: [] produce clean prose on live Haiku; the handoff coder's one-shot returns a parseable JSON edit-plan
result: issue
reported: "Live Haiku fabricates Claude-internal tool syntax as plain text when prompts imply file/tool actions without bound tools. Manifestations: handoff coder returned '<function_calls><invoke name=read_file>...' instead of JSON (1 of 2 live runs failed); raw <function_calls>/write_todos XML leaked into prose outputs of user_stories (epic-architect), custom (all 3 agents), app_builder (5 design agents), dotnet survivor — flagged independently by 4 Opus reviewers. The od_ppt instance of this class is already FIXED (8ba8f626: template files seeded + workspace tools); the text-only prompt-hygiene + handoff hardening remain."
severity: major

### 5. app_builder agents are role-conformant and mutually consistent
expected: All 15 app_builder agents produce on-domain deliverables that agree on cross-agent contracts
result: issue
reported: "Opus 15-agent audit: app-code-compliance stalled asking 'Java+Spring on AWS, or .NET on Azure?' — its prompt (and test-compliance + sdlc-governance) contains migration-pipeline template language alien to app_builder; both compliance/governance agents emitted nothing; app-devops produced only narration ('Now let me create the CD workflow...') with zero file blocks; app-system-design stalled on clarifying questions. Cross-agent contract breaks: auth implementation exports class AuthController(register/login, bcryptjs, DuplicateEmailError) while the tests import default AuthController(registerUser/loginUser, bcrypt, EmailDuplicateError) — tests cannot compile against the impl; API design uses /api/* while CI/CD targets /api/v1/*."
severity: major

### 6. sample_fanout resolves its declared deliverable
expected: No 'merged.txt not written by agent — falling back to streamed output' warning; deliverable is the merged 3-part output
result: issue
reported: "Live run: fan-out mechanics perfect (3 workers spawned + 3 results + copy_disjoint merge) but the manifest still declares deliverable single_file: merged.txt which nothing produces — fallback fired (1 hit in backend log), final output degraded to one worker's streamed text. Same quirk 12-10 fixed for sample_wave; sample_fanout was out of that fix's scope."
severity: minor

### 7. test_phase3_token_delta_live runs against the current engine
expected: The opt-in live token-delta measurement drives a prototype run and reports compaction savings
result: issue
reported: "AttributeError: 'ExecutionEngine' object has no attribute '_build_context_message' — the test monkeypatches a seam the Phase-7 decoupling renamed to _compose_context_message (now async, gained an index param; the skeleton helper moved to the html_skeleton compaction capability). Evidence-only test (never a CI gate)."
severity: minor

### 8. Phase-8 live sweep budget reflects real spend
expected: test_zz_live_cost_summary_under_budget passes on a clean full live sweep
result: issue
reported: "BudgetExceededError: cost $5.9400 exceeds soft ceiling $5.0000 — the sweep genuinely cost $5.94 (18.7M tokens at Haiku 4.5 pricing; 17.5M input from context accumulation across code-gen/migration pipelines). Calibration drift, not overspend: LIVE_BUDGET_USD=5.0 was set in Phase 8."
severity: cosmetic

## Summary

total: 8
passed: 0
issues: 8
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "A manifest-declared gates:[human] step surfaces review_gate_ready to the connected client BEFORE awaiting the response, so the user can approve from the UI and the run proceeds"
  status: resolved
  reason: "Live WS evidence: review_gate_ready+review_gate_approved arrive together only AFTER an external unblock; a real UI run hangs at the first declared gate with no signal to approve"
  severity: major
  test: 1
  root_cause: "HumanGate.evaluate (agents/capabilities/gates/human.py:60-80) consumes the entire run_human_gate delegate generator INSIDE gate evaluation and only returns GateOutcome(events=[...]) afterwards — _evaluate_gates (engine.py:2842-2902) yields the collected events to the dispatch loop only post-resolution. The delegate (_run_review_gate, engine.py:2903-2960) clears the review event on arming ('a fast response doesn't miss it') then awaits it, so pre-approval is discarded and the ready event is never on the wire while the gate waits. The legacy inline path (_should_gate -> _run_review_gate in _run_agent) yields ready to the consumer pre-await and works; only the declared-gate path is blind."
  artifacts:
    - path: "backend/agents/capabilities/gates/human.py"
      issue: "evaluate() collects delegate events into a list instead of surfacing them before the gate blocks (lines ~64-80)"
    - path: "backend/agents/execution_engine/engine.py"
      issue: "_evaluate_gates yields (event, outcome) only after gate.evaluate returns (2842-2902); _run_review_gate clears+awaits its event internally (2903-2960)"
    - path: "backend/agents/execution_engine/kernel_services.py"
      issue: "run_human_gate delegate (line 1041) — the seam the fix likely threads an emit-before-await through"
  missing:
    - "Surface review_gate_ready (and waiting_for_user state) to the WS consumer BEFORE the gate awaits — e.g. make the gate evaluation path streaming (async-gen evaluate or an emit callback through ctx/runner), or route declared human gates through the consumer-visible inline mechanism"
    - "A handler-driving regression test: declared-gate run over the WS path, assert ready is received while the run is paused, approve, assert resume (the gap the harness wrapper papers over in tests)"
  debug_session: "diagnosed live 2026-06-11 (.planning/live-verification/REPORT.md F1; ws-prototype frames + async task-stack dumps)"

- truth: "run_revision with the FE's exact payload (target_artifact_type: ppt_output / od_ppt_output) against a completed parent run passes FR-014 validation and produces a revision run"
  status: resolved
  reason: "FE-exact replay against a live completed ppt run: 'No artifact of type ppt_output found for run ... (FR-014)' — every run_revision fails; PPT revision is user-broken whenever a completed run id exists"
  severity: major
  test: 2
  root_cause: "Contract mismatch across the Phase-5 typed-artifact migration: engine _handle_revision validates via store.list_refs(parent_run_id, kind=target_artifact_type) (engine.py:3393-3400) expecting kinds like 'ppt_output'/'od_ppt_output' (what DashboardLayout.tsx:388-403 sends), but the run path persists artifact_refs kinds by AGENT ID plus summary/planning_context/clarifications — no code anywhere writes a *_output kind (grep ppt_output backend/ = 0 writers). The revision characterization tests seed their parents with the expected kind artificially, masking the break."
  artifacts:
    - path: "backend/agents/execution_engine/engine.py"
      issue: "_handle_revision FR-014 lookup list_refs(kind=target_artifact_type) at 3393-3400 can never match persisted kinds"
    - path: "frontend/src/components/layout/DashboardLayout.tsx"
      issue: "sends target_artifact_type 'ppt_output'/'od_ppt_output' (388-403); legacy text-injection fallback only fires when no run id exists"
    - path: "backend/app/api/websocket.py"
      issue: "run_revision ingress (831+) forwards the target type verbatim into the broken lookup"
  missing:
    - "Align the revision lookup with real artifact kinds — resolve the parent's deliverable ref (e.g. latest kind='summary' / the producing agent's ref) or persist a deliverable-kind artifact_ref at run completion that target_artifact_type maps onto"
    - "Update the revision characterization/seed tests to stop masking the contract (seed what the run path actually persists)"
    - "A WS-driven regression test: complete a ppt run, send the FE-exact run_revision frame, assert the revision drives"
  debug_session: "diagnosed live 2026-06-11 (REPORT.md F2; FE-exact WS replay + grep evidence)"

- truth: "A run whose agents hard-fail (e.g. missing od_context for injects-declaring agents) terminates as a visible failure or fails fast at ingress — never pipeline_complete with an empty or improvised deliverable"
  status: resolved
  reason: "ws-prototype: 4/4 agents agent_error'd ('no template body loaded'), run ended pipeline_complete with final_output='' in 12s. ws-ppt: 2/3 agents halted; the validator improvised the entire deck solo and the run 'passed'"
  severity: major
  test: 3
  root_cause: "Two compounding behaviors: (1) the WS layer builds od_context only for od_* aliases (websocket.py:1233-1252) yet bare 'prototype'/'ppt' remain runnable and their agents declare injects:[template,design_system] — the factory halts each agent pre-execution (agent_error) when template_body is absent; (2) the engine dispatch loop continues past per-agent errors and the terminal emit is unconditionally pipeline_complete (engine.py ~1681/3519) regardless of agents_completed vs failed, so total failure presents as success with an empty deliverable. The semantic review additionally showed the surviving agent (validator) silently authoring the missing deliverable, masking the collapse."
  artifacts:
    - path: "backend/agents/execution_engine/engine.py"
      issue: "terminal pipeline_complete emitted regardless of agent failure count (~1681, 3519); no all-agents-failed -> pipeline_failed branch"
    - path: "backend/app/api/websocket.py"
      issue: "od_context assembly only for od_prototype/od_ppt (1233-1252); bare prototype/ppt admitted with no inject inputs"
    - path: "backend/agents/factory.py"
      issue: "injects-unsatisfiable halt is per-agent (correct) but nothing aggregates it into run-level failure"
  missing:
    - "Terminal semantics: emit pipeline_failed (or pipeline_complete with an explicit degraded/failed status field) when all/critical agents errored; FE handling for it"
    - "Ingress guard: a pipeline whose agents declare injects requires od_context (template_id) — reject bare prototype/ppt up front or auto-resolve a default template, decide product-side"
    - "Decide bare 'prototype'/'ppt' product exposure (tier sets include them; the FE always sends od_* aliases)"
  debug_session: "diagnosed live 2026-06-11 (REPORT.md F3; ws-prototype/ws-ppt frames + Opus per-agent review)"

- truth: "Text-only (tools:[]) agents emit no fabricated tool-call XML in prose on live Haiku, and the handoff coder reliably returns a parseable JSON edit-plan"
  status: resolved
  reason: "4 Opus reviewers independently flagged raw <function_calls>/write_todos XML inside prose outputs across user_stories/custom/app_builder/dotnet; handoff coder returned tool-XML instead of JSON in 1 of 2 live runs (agent_error 'handoff coder returned no JSON object')"
  severity: major
  test: 4
  root_cause: "Live Haiku 4.5 fabricates Claude-internal tool syntax as text when the composed prompt implies file/tool actions without bound tools. Sources of the implication: deepagents-era prompt residue and AGENT.md bodies referencing write/todo/read behaviors reaching tools:[] agents (exclude_builtin removes the tools but not the references), and one-shot agents (handoff coder) prompted about edits with no tool channel at all. The od_ppt manifestation (template SKILL.md instructing reads into tool-less deck agents) is FIXED by 8ba8f626 (files seeded + workspace granted); the general text-only hygiene and the handoff coder remain."
  artifacts:
    - path: "backend/agents/factory.py"
      issue: "_compose_system_prompt: no tool-availability framing for tools:[] agents (no 'you have no tools; never emit tool syntax' guard)"
    - path: "backend/app/agents/handoff/coder.py"
      issue: "one-shot JSON contract fails on fabricated XML (~line 210 parse failure); no bounded parse-retry or stronger JSON-only constraint"
    - path: "backend/agents/prompts/ (epic-architect, custom agents, app_builder design agents)"
      issue: "prompt bodies imply write/todo file actions for text-only agents — leaked XML observed in their live outputs"
  missing:
    - "Prompt-hygiene guard for text-only composition: an explicit no-tools preamble (and/or strip imperative tool-action phrasing) when exclude_builtin is True"
    - "Handoff coder hardening: JSON-only response constraint + bounded retry-on-parse-failure"
    - "Optional output sanitation: detect/strip fabricated <function_calls> blocks from streamed prose (defense in depth)"
  debug_session: "diagnosed live 2026-06-11 (REPORT.md F4; od_ppt2 frames, handoff failure log, 4 Opus reviews)"

- truth: "All 15 app_builder agents produce role-conformant, on-domain output with consistent cross-agent contracts (impl matches tests; one API prefix)"
  status: resolved
  reason: "Opus 15-agent audit: 4 agents dead (2 empty, 1 refused asking 'Java or .NET?', 1 narration-only); auth tests cannot compile against the auth implementation; API design says /api/* while CI/CD targets /api/v1/*"
  severity: major
  test: 5
  root_cause: "Three independent defects: (1) app-code-compliance, app-test-compliance and app-sdlc-governance AGENT.md prompts carry migration-pipeline template language (Java/Maven on AWS, .NET/NuGet on Azure, 'legacy system', 'parallel-run validation') — copied from the mulesoft/dotnet pipelines and never re-templated for app_builder, so live agents stall or refuse; (2) app-devops prompt elicits narration ('Now let me create...') without enforcing file-block output; (3) no cross-agent contract enforcement exists between implementation and test agents (class/method/import/error-name drift) or between API design and infra (/api vs /api/v1)."
  artifacts:
    - path: "backend/agents/prompts/app-code-compliance/AGENT.md"
      issue: "migration-template prompt (Java/.NET stack-choice language) — agent stalls asking which stack"
    - path: "backend/agents/prompts/app-test-compliance/AGENT.md"
      issue: "references a 'parallel-run harness against the legacy system' — empty output live"
    - path: "backend/agents/prompts/app-sdlc-governance/AGENT.md"
      issue: "migration-flavored mandate; empty output live (also starved by upstream empties)"
    - path: "backend/agents/prompts/app-devops/AGENT.md"
      issue: "no output contract — produced narration with zero file blocks"
  missing:
    - "Re-template the three compliance/governance prompts for app_builder scope (greenfield app, Node/TS default stack from upstream context, no legacy/parallel-run language)"
    - "Output contract line for app-devops (must emit filename: blocks)"
    - "Cross-agent contract guidance: test agent must import/exercise the implementation agent's actual exported surface; single API prefix decision threaded through API design -> infra/CI prompts"
  debug_session: "diagnosed 2026-06-11 (REPORT.md F5; Opus app_builder audit over capture packets)"

- truth: "sample_fanout resolves its declared deliverable from produced files (no single_file fallback warning)"
  status: resolved
  reason: "Live run: 'merged.txt not written by agent — falling back to streamed output' (1 hit); final output degraded to one worker's streamed text despite a perfect 3-worker fan-out + copy_disjoint merge"
  severity: minor
  test: 6
  root_cause: "Manifest quirk, not an engine bug: agents/workflows/sample_fanout/workflow.yaml declares deliverable single_file: merged.txt which no step produces — workers write part_1..3.txt that copy_disjoint merges into the base. Identical to phase-12 UAT Gap 3, which 12-10 fixed for sample_wave only (serialized_sandbox swap); sample_fanout was out of scope then."
  artifacts:
    - path: "backend/agents/workflows/sample_fanout/workflow.yaml"
      issue: "deliverable single_file name=merged.txt never produced by any step"
  missing:
    - "Swap the deliverable to the registered serialized_sandbox strategy (manifest-data-only, zero engine edits — mirror commit 8ffae37c for sample_wave) + update test_sc001_fanout's deliverable assertion"
  debug_session: "diagnosed live 2026-06-11 (REPORT.md F6)"

- truth: "test_phase3_token_delta_live drives the live compaction token-delta measurement against the current engine"
  status: resolved
  reason: "AttributeError: 'ExecutionEngine' object has no attribute '_build_context_message' — collection-time monkeypatch target deleted by the Phase-7 decoupling"
  severity: minor
  test: 7
  root_cause: "Bit-rot: the test wraps engine._build_context_message (test_phase3_token_delta_live.py:167-210), renamed to _compose_context_message (engine.py:4381, now async with an added index param); its compaction-off override also calls engine._extract_html_skeleton, relocated to the html_skeleton compaction capability in 07-03/07-05."
  artifacts:
    - path: "backend/tests/agents/test_phase3_token_delta_live.py"
      issue: "monkeypatch targets renamed/relocated seams (lines 167-210)"
  missing:
    - "Re-point the wrapper to async _compose_context_message(spec, index, ordered_agents, user_message, planning_context, ectx); source the skeleton via the registered html_skeleton compaction capability"
  debug_session: "diagnosed 2026-06-11 (REPORT.md F7)"

- truth: "The phase-8 live sweep's soft cost ceiling reflects real Haiku 4.5 spend so a clean sweep passes"
  status: resolved
  reason: "BudgetExceededError: cost $5.9400 exceeds soft ceiling $5.0000 on an otherwise-clean sweep (18.7M tokens — 17.5M input from context accumulation)"
  severity: cosmetic
  test: 8
  root_cause: "LIVE_BUDGET_USD=5.0 (test_phase8_live.py:104) was calibrated at Phase 8; current pipelines are more verbose (MAX_OUTPUT_TOKENS lifted to 32768, richer context routing). Measured clean-sweep cost: $5.94."
  artifacts:
    - path: "backend/tests/agents/test_phase8_live.py"
      issue: "LIVE_BUDGET_USD=5.0 at line 104 below the measured $5.94 clean-sweep cost"
  missing:
    - "Recalibrate the ceiling (e.g. 8.0) with a comment citing the 2026-06-11 measured sweep ($5.94 / 18.7M tokens)"
  debug_session: "diagnosed 2026-06-11 (REPORT.md F7; sweep cost table in /tmp/flowin-live-suites.log)"
