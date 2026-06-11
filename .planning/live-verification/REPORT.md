# Live-Bedrock Verification Pass — 2026-06-11

**Scope:** post-milestone full live verification of every workflow + custom workflows with all
options, on **real AWS Bedrock Claude Haiku 4.5** (`eu.anthropic.claude-haiku-4-5-20251001-v1:0`,
eu-central-1, profile `hexaware-srini`) — replacing the scripted-model caveat from the
milestone-end UAT pass. Includes a **semantic-level verification of every workflow's and
agent's output by parallel Opus 4.8 reviewer agents**.

Total live spend ≈ $8–9 (the phase-8 sweep alone: 18.7M tokens / $5.94). The Bedrock
**daily token quota was exhausted** near the end; items marked QUOTA-BLOCKED need a re-run
after reset.

---

## 1. What ran

| Layer | Vehicle | Result |
|---|---|---|
| Live pytest suites (phase-8 harness) | `RUN_LIVE_BEDROCK=1` — TestLivePipelines, TestLiveHITL, live contract validator, token-delta, runner HITL | **43 passed / 3 failed** in 2h33m (failures dissected below) |
| Offline proof of the repaired harness | TestOfflineProof + TestOfflineHITL | 15 passed / 2 skipped |
| Full-stack WS product path | raw-WS driver against the stock backend (real clarify, gates, revisions, custom, samples, reconnect) | 13 scenarios + 4 corrected re-runs |
| Instrumented internals probe | wrapped `create_runner` capturing each agent's composed context | context routing verified verbatim |
| SC-001 proofs on the real model | scripted-model→`build_model(None)` plugin over the e2e suites | brownfield 3/3 PASS; task_loop mechanics PASS (2 asserts failed on scripted-byte couplings only) |
| Semantic verification | 8 parallel **Opus 4.8** reviewer agents over per-workflow packets (brief + agent role contracts + actual outputs + deliverable) | verdicts below |

## 2. Workflow × verification matrix

| Workflow | Engine-direct live | WS product path | Semantic (Opus) | Notes |
|---|---|---|---|---|
| user_stories | PASS | PASS (clarify live) | concerns | chaining/personas verbatim-verified; defects: tool-XML leak, 1 malformed story; "truncation" flags were packet-cap artifacts (full 43.4k deliverable exists) |
| user_stories_revision | — | FAIL (F2) | — | run_revision dead (FR-014 kind mismatch) |
| ppt | — | completed, but degenerate (F3) | concerns | 2/3 agents halted on missing template inject; validator improvised the (good) deck solo — role inversion |
| ppt_revision / od_ppt_revision | — | FAIL (F2) | — | same FR-014 |
| od_ppt (deck template) | PASS (harness ctx) | FAIL → **FIXED** → retest QUOTA-BLOCKED | fail (pre-fix) | F4 root cause; fix `8ba8f626` proven: offline seeding e2e + 14 real read_file/glob live before quota |
| prototype / od_prototype | PASS (incl. revision chained) | PASS as od_prototype (gates + build loop + validation) | concerns | deliverable good; plan-agent emitted no task list (F5-class), validator rubber-stamps, unrequested Settings view |
| prototype_revision (chained) | PASS | PASS via `source_workflow_run_id` — both requested edits verified in output | pass (on full artifact) | the FE's actual chaining mechanism works |
| app_builder | PASS | PASS clean (29 min, 63k frames, 1.7M tok) + cancel-on-disconnect verified | concerns | design layer excellent & consistent; F5: 4/15 agents dead (mis-templated prompts), auth impl↔test contract mismatch, /api vs /api/v1 drift |
| app_builder_revision | — | FAIL (F2) | — | |
| mulesoft_to_springboot | PASS (suite) | — | fail (capture run) | capture run lacked source-repo input → root inventory empty → cascade; suite run passed contract checks. Environment-fidelity gap (F8), engine sound |
| dotnet_to_azure | PASS (suite) | — | fail (quota) | capture run quota-throttled 12/13 agents |
| chat | PASS (suite) | — | fail (quota) | capture run fully throttled |
| handoff coding / test | coding 1×FAIL + 1×PASS, test PASS | — | — | F4-class: model emitted tool-XML instead of JSON once |
| custom (palette) | — | PASS (subset + model_overrides + skills/hooks; DAG resolver rejected 2 unsatisfiable subsets with exact edges) | pass | genuine chaining of concrete specifics research→SWOT→roadmap |
| sample_wave | PASS (12-UAT) | PASS on real model (2 waves, 4 workers) | partial | live worker dropped part_c (model variance; engine lifecycle correct) |
| sample_fanout | PASS (11-05) | PASS on real model (3 workers + merge) | pass-with-known-defect | merged.txt fallback = pre-Gap-3 manifest quirk (recommend serialized_sandbox swap like 12-10) |
| sample_brownfield | PASS offline | — | — | **3/3 PASS with the real model** (repo context pack → edit → repo_diff) |
| sc001_task_loop | PASS offline | — | — | real model built a working app.py through the stitched flow; 2 asserts failed only on scripted-output byte couplings |
| HITL gates / clarify / reconnect / waves / fan-out / budget | all exercised live | all exercised live | — | clarify questionnaires answered on every WS run; legacy gate pause→resume live; reconnect after_seq replay live |

## 3. Findings register

| # | Severity | Finding | Evidence | Status |
|---|---|---|---|---|
| F1 | major (product) | **Declared-gate events undeliverable**: `gates: [human]` steps await the review response INSIDE gate evaluation (`HumanGate` → `run_human_gate` → `_run_review_gate`), so `review_gate_ready` reaches the WS client only AFTER approval — the UI can never know a gate is waiting; prototype-family runs from the UI hang at specify | wire frames (ready+approved arrive together post-unblock); engine.py `_evaluate_gates` / gates/human.py | OPEN — needs fix (surface gate events before the await, or re-route declared gates through the consumer-visible inline path) |
| F2 | major (product) | **run_revision dead end-to-end**: FE sends `target_artifact_type: "ppt_output"`/`"od_ppt_output"` (DashboardLayout.tsx:396); engine FR-014 lookup `list_refs(kind=target)` (engine.py:3397) — but no code ever persists those kinds (runs persist per-agent ids + summary/planning_context/clarifications). Every run_revision fails validation | FE-exact replay against a live completed ppt run; `grep ppt_output backend/` = 0 writers | OPEN — align the revision lookup with real artifact kinds (or persist a deliverable-kind ref) |
| F3 | major (product) | **Inject-missing agents halt silently + run still "completes"**: bare `ppt`/`prototype` over WS (no od_context) → agents declaring `injects` emit agent_error and halt; pipeline ends `pipeline_complete` with empty/improvised output (ws-ppt's deck was authored entirely by the validator) | ws-prototype / ws-ppt frames; Opus per-agent review | OPEN — fail-fast or degrade visibly (pipeline_failed / warning event) |
| F4 | major (model robustness) | **Live Haiku fabricates tool-call XML as text** when prompts imply file/tool actions without bound tools. Manifestations: od_ppt template path (template SKILL.md says "read assets/template.html" into tools:[] agents), handoff coder (returned XML instead of JSON once), and pervasive `<function_calls>`/`write_todos` XML leaking into text-only agents' prose across user_stories/custom/app_builder/dotnet | od_ppt2 frames; handoff failure log; Opus reviews flag it in 4 workflows | **PARTIALLY FIXED** (`8ba8f626`: od template files seeded into the run sandbox + ppt agents granted workspace tools — offline seeding proof green; live retest showed real read_file/glob calls, full deck QUOTA-BLOCKED). Remaining: prompt-hygiene for text-only agents + handoff coder hardening |
| F5 | major (agent config) | **app_builder agent-prompt defects**: code-compliance / test-compliance / sdlc-governance prompts contain Java/.NET *migration* template language → refusal/empty outputs; app-devops emits narration without files; app-system-design stalls on clarifying questions; auth implementation vs tests disagree on the class contract; `/api` vs `/api/v1` drift between API design and CI | Opus app_builder review (15-agent audit) | OPEN — re-template the 3 migration-flavored prompts; add cross-agent contract checks |
| F6 | minor (samples) | sample_fanout still declares `single_file: merged.txt` (fallback fires; same quirk 12-10 fixed for sample_wave); live sample_wave worker dropped part_c (model variance) | backend log; bundle filenames | OPEN (manifest-only swap) |
| F7 | test-infra | live_harness bit-rot (store attr + declared-gate hang) — FIXED `6e68d9f4`; token_delta_live bit-rot (renamed `_build_context_message`) — deferred; phase-8 sweep budget $5.00 < actual $5.94 — recalibrate; semantic packets capped agent outputs at 12k chars causing 3 false-negative "truncation" verdicts (full artifacts exist on disk) | suite logs | harness FIXED; rest recorded |
| F8 | environment | Migration pipelines (mulesoft/dotnet) need source-repo inputs the bare-brief harness doesn't provide (root inventory agents stall/empty); Bedrock daily quota exhausted late in the pass (dotnet/chat captures degraded, od_ppt retest blocked) | capture logs | re-run captures + retest after quota reset, with repo inputs attached |

## 4. Changes shipped this pass

| Commit | Change |
|---|---|
| `6e68d9f4` | test(agents): live harness repaired for the post-Phase-12 engine (store no-op removal + declared-gate auto-approve wrapper) |
| `8ba8f626` | fix(engine): seed od template files into the run sandbox + grant od-ppt agents workspace tools (F4 od_ppt fix; characterization parity held — 165 offline tests green) |
| `b610e9ef` | feat(capabilities): task_loop / single_file / serialized_sandbox / heading_tasks / json_tasks now `user_allowed=True` (CAP-03) — unlocks user-trust manifest composition of prototype-style flows; **no visible/behavioral change today** (file-trust unaffected; FE composer is the deferred v2 surface; exec/network/secrets/spawn stay file-only) |

## 5. Verified positives (the headline)

- **Engine core is sound live**: context routing (`$previous` + named multi-source) verbatim-verified per agent; planner + clarify questionnaire round-trip live on every WS run; DAG resolver rejects unsatisfiable custom subsets naming the exact missing edge; legacy HITL gate pause→resume live; durable reconnect `after_seq` replay live; cancel-on-disconnect by design; waves + fan-out + isolation + merge live on the real model; deliverable contracts (streamed_text / single_file html / serialized_sandbox / filename-blocks) all produced as declared.
- **SC-001 holds on a real model**: brownfield repo workflow 3/3 unmodified; the stitched task-loop workflow had live Haiku build a working app.py with zero engine edits.
- **Chaining works as designed** at all three layers: agent→agent context, run→run via `source_workflow_run_id` (revision applied exactly the requested edits), palette custom chains carrying concrete specifics through.

## 6. Quota-blocked / follow-ups

1. Re-run `ws-od_ppt` live after quota reset (fix in place; expect a real template-driven deck).
2. Re-capture dotnet_to_azure + chat (and mulesoft with a source-repo attachment) for clean semantic review.
3. Plan fixes for F1, F2, F3, F5 (recommend a gap-closure phase; F1/F2 are user-facing breakage).
4. Manifest swap for sample_fanout deliverable (F6); harden handoff coder prompt + text-only-agent prompt hygiene (F4 residue).
5. Recalibrate the phase-8 live budget; repair token_delta_live.
