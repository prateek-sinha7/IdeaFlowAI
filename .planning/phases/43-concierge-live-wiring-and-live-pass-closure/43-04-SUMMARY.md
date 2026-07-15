---
phase: 43-concierge-live-wiring-and-live-pass-closure
plan: 04
subsystem: infra
tags: [bedrock, prompt-cache, token-accounting, deepagents, langchain-aws, planner, clarify, handoff]

# Dependency graph
requires:
  - phase: 43-01
    provides: Concierge backend defect fixes (shared run_commands.py / engine.py surface)
  - phase: 43-03
    provides: engine event-sink seam pattern (injected-callback, no kernel→app import)
provides:
  - "app/agents/cached_invoke.py — the ONE shared cached-invoke helper: Bedrock cache-point placement + token counting for direct one-shot model calls (ISS-033)"
  - "SmartPlanner / ClarifyEngine / handoff Test(classifier) + Compliance now route their model call through the shared helper (cache-eligible + tokens counted)"
  - "Engine run-total accounting now folds the SmartPlanner + clarify one-shot tokens (aux_token_usage) into pipeline_complete"
affects: [43-06, 43-07, B.4, ISS-033, ISS-034]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Direct-invoke → shared cached_invoke: the direct-ainvoke equivalent of the DeepAgentRunner cache-points middleware (langchain_aws reads cache_control off per-call kwargs)"
    - "Usage sink: optional Callable[[usage], None] threaded from the caller so out-of-stream one-shot tokens land in run accounting"

key-files:
  created:
    - backend/app/agents/cached_invoke.py
    - backend/tests/unit/test_cached_invoke.py
  modified:
    - backend/agents/planner/smart_planner.py
    - backend/agents/execution_engine/clarify_engine.py
    - backend/agents/execution_engine/engine.py
    - backend/app/agents/handoff/classifier.py
    - backend/app/agents/handoff/compliance_agent.py

key-decisions:
  - "cached_invoke MIRRORS the existing _BedrockCachePointsMiddleware (identical gating + cache_control payload) as the direct-ainvoke equivalent — ONE caching mechanism, not a parallel scheme (INV-12)."
  - "Parity-preserving model construction: SmartPlanner/classifier/compliance pass their own pre-built model instance (max_tokens/temperature unchanged); clarify builds inside the helper exactly as before. Only the invoke path changes (INV-3)."
  - "Counting: the helper returns (text, usage) AND calls an optional usage_sink; the engine folds SmartPlanner + clarify tokens into the run totals. Handoff has no run-cost accounting surface — the seam is present but its run-wiring is out of scope."

patterns-established:
  - "Cache-eligible stable prefix passed as SystemMessage separate from the per-call content; None prefix keeps a bare HumanMessage call byte-identical."
  - "Offline proof of Bedrock cache config via a real ChatBedrockConverse subclass whose _agenerate is stubbed (no network); live cache_read>0 is the B.4 check."

requirements-completed: [A.x]

# Metrics
duration: 50 min
completed: 2026-07-15
---

# Phase 43 Plan 04: Shared cached-invoke helper (ISS-033) Summary

**A single `cached_invoke` helper places Bedrock prompt-cache points on the stable prefix and counts tokens for the four direct one-shot model calls (SmartPlanner, ClarifyEngine, handoff Test + Compliance) — deleting their direct `ainvoke` bypasses, with the 5 characterization goldens byte-identical.**

## Performance

- **Duration:** ~50 min
- **Completed:** 2026-07-15T13:10:18Z
- **Tasks:** 2
- **Files modified:** 5 (+2 created)

## Accomplishments
- `app/agents/cached_invoke.py`: the ONE cached-invoke path — builds via the sanctioned `build_model` (INV-13; no deep-agent factory), mirrors `_BedrockCachePointsMiddleware`'s exact Bedrock `cache_control` gating (INV-12), invokes, and returns `(text, usage)` while routing usage into an optional sink. Degrade-safe on non-Bedrock / flag-off / missing `usage_metadata`.
- All four direct-call sites now delegate to the helper; the direct `self._llm.ainvoke` / `build_model().ainvoke` bypasses are deleted (no dual path, INV-12).
- Engine run accounting folds the SmartPlanner + clarify one-shot tokens (`aux_token_usage`) into `total_input_tokens`/`total_output_tokens` + the cache split at `pipeline_complete` — closing the ISS-033 counting gap; 0 on the goldens (planner neutralised, clarify off) so byte/event snapshots are unchanged.

## Task Commits

1. **Task 1: Build the shared cached-invoke helper (cache-point placement + token counting)** — `0aa2072c` (feat)
2. **Task 2: Route SmartPlanner + ClarifyEngine + handoff Test/Compliance through the helper** — `8518f29b` (feat)

**Plan metadata:** (docs commit — this SUMMARY)

## Files Created/Modified
- `backend/app/agents/cached_invoke.py` — the shared helper (`cached_invoke`, `_bedrock_cache_control`, `_usage_from_response`, `_extract_text`).
- `backend/tests/unit/test_cached_invoke.py` — 11 offline tests: cache-config placement (Bedrock subclass, network-stubbed), flag-off + non-Bedrock suppression, token counting via sink, degrade-safe zeros, INV-13 no-deep-agent + build_model routing, and the four call-site delegation checks.
- `backend/agents/planner/smart_planner.py` — `plan()` routes through `cached_invoke(model=self._llm)`; `__init__` gains `usage_sink`.
- `backend/agents/execution_engine/clarify_engine.py` — `_generate_questions_via_llm` routes through the helper; `__init__` gains `self._usage_sink`.
- `backend/agents/execution_engine/engine.py` — `aux_token_usage` accumulator; `_run_planner`/`_invoke_planner` thread `usage_sink` into `SmartPlanner`; clarify sink wired; run totals fold the aux tokens.
- `backend/app/agents/handoff/classifier.py` — `classify_task(..., usage_sink=)` routes through the helper (stable system prompt as the cache-eligible prefix); removed the now-dead `_extract_text`.
- `backend/app/agents/handoff/compliance_agent.py` — `ComplianceAgent(usage_sink=)`, `review()` routes through the helper; removed the now-dead `_extract_text`.

## Decisions Made
- **INV-12 (one mechanism):** the helper reuses the exact Bedrock `cache_control` `{"type":"ephemeral","ttl":BEDROCK_PROMPT_CACHE_TTL}` and Bedrock-only + flag gating of `_BedrockCachePointsMiddleware`. `langchain_aws` reads `cache_control` off the per-call `ainvoke` kwargs (`ChatBedrockConverse._generate`/`_stream` → `_apply_cache_points` places the `cachePoint` on the system prefix + last message) — so this is the direct-invoke equivalent, not a second caching path. On ChatAnthropic / scripted models it is a no-op (they keep deepagents' own caching; no double-apply).
- **INV-3 parity:** SmartPlanner/classifier/compliance pass their **own pre-built model instance** so `max_tokens`/`temperature=0` and the request bytes are unchanged; clarify builds inside the helper with the identical `build_model(max_tokens=1500)`. Only the invoke path changes (cache-point placement + counting added). The goldens neutralise the planner and set `clarify.mode="off"`, so both routed paths are dormant there → **10 passed, golden dir diff EMPTY**.
- **Counting scope:** the engine wires the SmartPlanner + clarify sinks into run totals (the pipeline-run accounting). The handoff Test/Compliance agents get the counting **seam** (usage_sink param) but the handoff service (`handoff_pipeline.py`) has no run-cost accounting surface today, so wiring their run-total is out of scope (documented, not built).

## Deviations from Plan

None - plan executed exactly as written.

The only judgment calls were parity-preserving choices explicitly anticipated by the plan (pass a pre-built model where a caller had a tuned model config; keep `build_model` at the classifier/compliance sites so their `ModelConfigurationError` propagation + existing `build_model`-patching tests stay intact). The classifier/compliance `_extract_text` helpers became dead (the shared helper extracts) and were removed — no dual path.

## Issues Encountered
- **Pre-existing reds (out of scope, logged):** `tests/unit/test_run_pipeline_validation.py` has 12 failures about registry agent allow-list / custom-pool drift. They reference **none** of the routed code (0 matches for cached_invoke/usage_sink/SmartPlanner/ClarifyEngine/classify_task/ComplianceAgent) and 43-04 touched no registry/loader/run-validation file — logged to `deferred-items.md`, not fixed (scope boundary).
- **Offline caching limit:** actual `cache_read>0` requires live Bedrock (no caching offline). The helper's cache **config placement** is proven offline (a real `ChatBedrockConverse` subclass records the `cache_control` kwarg = `{"type":"ephemeral","ttl":"5m"}` on the stable system prefix); the live `cache_read>0` + multi-turn placement observation is the **B.4 live check (deferred)**.

## Verification
- `python3.11 -m pytest tests/agents/ -k characterization -q` → **10 passed** (2 runs: after Task 2 edits and after the final compliance revision).
- `git diff --stat backend/tests/agents/characterization/golden/` → **EMPTY** (byte-identical, INV-3).
- `tests/unit/test_cached_invoke.py` → **11 passed** (incl. token-counting + INV-13 + the four delegation checks).
- Related suites: `test_handoff_agents.py` + `test_clarify_json_parse.py` + `test_brief_max_chars.py` + `test_clarify_llm_live.py` → **41 passed, 1 skipped**.
- Source assertion: **0** residual `self._llm.ainvoke` / `build_model(...).ainvoke` at the four routed sites; all four reference `cached_invoke`.
- `create_deep_agent` grep in `cached_invoke.py` → **0**; `build_model` present (INV-13).
- `lint-imports` → **4 kept / 0 broken**.

## Threat Flags
None — no new network endpoint, auth path, file access, or schema change. `cached_invoke` builds via the sanctioned `build_model` (INV-13); routing added no kernel→app edge (import-linter 4/0). Untrusted brief/clarify text stays the per-call content (T-43-04-PARITY: parsed output byte-identical for the same model text).

## Next Phase Readiness
- Feeds **B.4** (live `cache_read>0` incl. multi-turn cache-point placement) and closes the ISS-033/034 counting half offline. The live cache read is verified in Part B on a real Bedrock run.
- No blockers for 43-05 (steering live-drain) — that plan shares `run_commands.py`/`engine.py` but not the routed one-shot call paths.

## Self-Check: PASSED
- Created files exist: `backend/app/agents/cached_invoke.py`, `backend/tests/unit/test_cached_invoke.py`, `43-04-SUMMARY.md`.
- Task commits exist: `0aa2072c` (Task 1), `8518f29b` (Task 2).

---
*Phase: 43-concierge-live-wiring-and-live-pass-closure*
*Completed: 2026-07-15*
