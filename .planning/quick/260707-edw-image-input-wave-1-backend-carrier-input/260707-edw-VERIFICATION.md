---
phase: quick-260707-edw
status: passed
verified_by: orchestrator (independent gate re-run + pre-existing-red proof — executor report treated as a claim, not accepted on faith)
date: 2026-07-07
---

# Verification — quick-260707-edw (Image Input Wave 1 — backend spine, DORMANT)

**Status: passed.** Every must-have was independently re-verified against ground truth by the orchestrator — the hard gates were re-run, the commit scope/trailer/dormancy audited, and the two tests the executor flagged as "pre-existing reds" were proven pre-existing by running them at the pre-executor commit. Wave 1 of 3.

## Independent evidence (orchestrator re-ran these, `SNAPSHOT_UPDATE` unset)
- **5 characterization goldens byte/event-identical:** one invocation over the 5 `test_characterization_*` files + `test_context_message_oracle` + `test_registry_capabilities` + the 2 new suites = **124 passed / 0 failed**. All 5 goldens green — `od_ppt` is **fully green** here (both deliverable + event snapshot), a stronger INV-3 result than the anticipated identical-red.
- **Oracle:** `test_context_message_oracle` green (the `isinstance(cm, str)` path unaffected; `context_message` stays text).
- **Registry drift-guard GREEN at 65:** `test_registered_count_is_exactly_fifty` passes; `len(_KNOWN) == 65`, `set(_KNOWN) == set(_EXPECTED_NAMES)`. T1.4 reconciled the pre-existing KAN-73 `hook:audit_logger` drift (was `assert 64 == 63` red on entry) and added `input_provider:run_images`.
- **New TDD suites:** `test_input_providers_run_images` (8) + `test_image_input_wiring` (8) = **16 passed**, including the MANDATORY BLOCKER two-agent isolation test (agent B receives `[]` even with `ectx.current_spec_injects == {"images"}`).
- **lint-imports:** `4 kept / 0 broken`.
- **INV-1 grep:** `grep -rnE 'pipeline_type ==|spec\.id ==' agents/execution_engine/engine.py` → **0**.

## Scope / invariant audit
- **4 atomic commits, trailer-free:** `440d3658`, `756cd630`, `5e62edd9`, `0781a066` — no `Co-Authored-By`/`Claude-Session` trailer; branch `new-workflow-engine`; nothing pushed.
- **Scope (14 files, no forbidden surface):** `base.py`, `input_providers/{__init__,run_images}.py`, `registry.py`, `context.py`, `engine.py`, `workflows/{manifest,compiler,plan}.py`, `deep_agent_runner.py`, `_normalize.py`, `test_input_providers_run_images.py`, `test_image_input_wiring.py`, `test_registry_capabilities.py`. **NO** `websocket.py`, **NO** Alembic migration, **NO** `workflow.yaml`, **NO** `AGENT.md`.
- **DORMANT:** no `input_providers:` in any manifest; no `injects:[images]` in any AGENT.md (the `mulesoft-aws-infra` "images" match is prose — "retain last 30 images"). ⇒ `_compose_input_blocks` returns `[]` for every agent, `_dispatch_payload` returns the bare str ⇒ goldens byte/event-identical BY CONSTRUCTION.
- **Design fidelity (the BLOCKER fix, verified in code + test):** image blocks are a per-agent LOCAL in `_run_agent`; `_compose_input_blocks` gates LOCALLY on `set(spec.injects) | set(step.injects)` and NEVER reads the stale `ectx.current_spec_injects`; there is NO shared `ectx.pending_input_blocks` field; split-transport keeps `agent_input.data.context_message` a `str` always.

## Pre-existing reds — proven NOT introduced
Ran `test_manifest.py` + `test_manifest_parity.py` at the **pre-executor** commit `e2616e30` AND at HEAD `0781a066` → **identical `9 failed / 49 passed`** at both. The 9 failures (`test_clarify_defaults_match_engine` ×7 · `test_display_name` ×2) are pre-existing branch drift unrelated to `input_providers`; logged to `deferred-items.md`, NOT fixed this wave.

## Carry-forward
Wave 1 of 3 (dormant spine). **Wave 2** = FE + WS ingress + ingest caps (mime/size/count + per-run aggregate) + `IMAGE_INPUT_ENABLED` + vision guard. **Wave 3** = `prototype-specify` opt-in (`input_providers: [run_images]` + `injects: [images]`) + live Bedrock proof + middleware/checkpointer gate. See `.planning/IMAGE-INPUT-PLAN.md`.
