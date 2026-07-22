---
phase: 260704-p10
verified: 2026-07-04T18:30:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: null
  previous_score: null
---

# Phase 260704-p10: Bedrock prompt caching + extended-thinking config knob Verification Report

**Phase Goal:** (A) Enable AWS Bedrock prompt caching via a provider-agnostic `_BedrockCachePointsMiddleware` that sets `model_settings["cache_control"]` on `ChatBedrockConverse` requests (config-gated `BEDROCK_PROMPT_CACHE_ENABLED`, default ON; TTL `BEDROCK_PROMPT_CACHE_TTL`), registered in the existing deepagents `create_deep_agent(... middleware=[...])` list, no-op on non-Bedrock. (B) Add `THINKING_BUDGET_TOKENS` (enable-only, default 0/off) wired into both `build_model` provider branches, budget clamped, temperature=1 forced only when enabled, disabled path byte-identical. Keep deepagents (INV-13); goldens byte/event-identical (INV-3).
**Verified:** 2026-07-04T18:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | On a ChatBedrockConverse request the runtime sets `model_settings['cache_control']` (config-gated, default ON) so `_apply_cache_points` fires | ✓ VERIFIED | `deep_agent_runner.py` L232-244: local `from langchain_aws import ChatBedrockConverse`, `isinstance` gate, then `request.override(model_settings={**request.model_settings, "cache_control": {"type":"ephemeral","ttl": settings.BEDROCK_PROMPT_CACHE_TTL}})`. Uses `.override()` — NOT constructor, NOT `.bind()`. Test `test_cache_middleware_bedrock_enabled_sets_cache_control` + async variant PASS. |
| 2 | On a non-Bedrock request the middleware is a pass-through no-op (ChatAnthropic keeps deepagents' built-in caching, no double-apply) | ✓ VERIFIED | `deep_agent_runner.py` L234-235: `if not isinstance(request.model, ChatBedrockConverse): return request`. Test `test_cache_middleware_non_bedrock_is_passthrough` asserts `box["req"] is req` and no `cache_control`. PASS. |
| 3 | `BEDROCK_PROMPT_CACHE_ENABLED=False` disables the middleware (pass-through) | ✓ VERIFIED | `deep_agent_runner.py` L227-228: `if not settings.BEDROCK_PROMPT_CACHE_ENABLED: return request` (read at call time). Test `test_cache_middleware_disabled_is_passthrough` monkeypatches flag False → original request unchanged. PASS. |
| 4 | `THINKING_BUDGET_TOKENS>0` enables thinking on BOTH providers with clamped budget + temperature=1; =0 → neither field, disabled path byte-identical | ✓ VERIFIED | `model_factory.py` L52-55 (`thinking_enabled`, clamp `max(1024, min(budget, max_tokens-1))`), L67-69 Anthropic `thinking=`+`temperature=1`, L90-109 Bedrock merge-not-clobber `additional_model_request_fields['thinking']`+`temperature=1`. Both only when enabled. 6 build_model tests PASS incl. floor(1024)/ceiling(MAX_OUTPUT_TOKENS-1) clamps and disabled-path assertions (`"temperature" not in`, `"thinking" not in`). |
| 5 | 5 characterization goldens byte/event-identical with SNAPSHOT_UPDATE unset (INV-3) | ✓ VERIFIED | Ran all 5 characterization suites + new test = 20 passed in 38.5s, SNAPSHOT_UPDATE unset. `git status --short` shows ZERO golden/snapshot/characterization file modifications (only STATE.md + untracked quick dir). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/core/config.py` | 3 settings (bool True, str "5m", int 0) | ✓ VERIFIED | L110 `BEDROCK_PROMPT_CACHE_ENABLED: bool = True`, L111 `BEDROCK_PROMPT_CACHE_TTL: str = "5m"`, L117 `THINKING_BUDGET_TOKENS: int = 0` with explanatory comments. |
| `backend/app/agents/deep_agent_runner.py` | Middleware defined + registered | ✓ VERIFIED | Class `_BedrockCachePointsMiddleware(AgentMiddleware[Any,Any,Any])` L205-258 with sync+async `wrap_model_call`. Registered L352: `middleware=[_ToolFilterMiddleware(excluded=excluded), _BedrockCachePointsMiddleware()]` in the existing `create_deep_agent(...)` call. |
| `backend/app/agents/model_factory.py` | Enable-only thinking on both branches | ✓ VERIFIED | `THINKING_BUDGET_TOKENS` threaded L52-109; no hardcoded model-id introduced (provider dispatch by `settings.ANTHROPIC_API_KEY`, model by `model or settings...`). |
| `backend/tests/agents/test_bedrock_cache_and_thinking.py` | ≥60 lines, cache + thinking coverage | ✓ VERIFIED | 213 lines, 10 offline tests (4 cache + 6 build_model). All PASS. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `DeepAgentRunner.__init__` middleware list | `_BedrockCachePointsMiddleware()` | list registration L352 | ✓ WIRED | Appended to the existing `create_deep_agent(middleware=[...])` list. |
| `_BedrockCachePointsMiddleware._maybe_apply` | `request.override(model_settings={...'cache_control'...})` | `ModelRequest.override` on Bedrock request | ✓ WIRED | L236-244, dict non-empty (`_apply_cache_points` early-returns on falsy). |
| `build_model` | `ChatAnthropic(thinking=...)` / `ChatBedrockConverse(additional_model_request_fields={'thinking':...})` | `thinking_enabled` branch | ✓ WIRED | L68 Anthropic, L92+L107 Bedrock; kwarg present only when enabled. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full target suite (5 goldens + new tests) | `pytest ...characterization_* test_bedrock_cache_and_thinking.py -q` | 20 passed, 1 warning, 38.5s | ✓ PASS |
| Goldens unregenerated (INV-3) | `git status --short` | no golden/snapshot files modified | ✓ PASS |
| Ports & Adapters | `/opt/homebrew/bin/lint-imports` | 4 kept, 0 broken | ✓ PASS |
| Task commits present | `git cat-file -t` × 4 | 582b90c8, 9ac8cf76, e4d6d6c0, 5346c242 all exist | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| FIX-034 | 260704-p10-PLAN | Bedrock caching off + thinking knob | ✓ SATISFIED | FIX-REGISTER.md L44 row present after FIX-033, correct 8-column shape, Status "Done". |
| ISS-031 | 260704-p10-PLAN | Same observation + closing fix | ✓ SATISFIED | ISSUES-REGISTER.md L40 row, status **FIXED** (quick-260704-p10), cites FIX-034, live confirmation deferred. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | none | — | No TBD/FIXME/XXX in modified files; no stub returns; `settings.` read at call time (intentional, monkeypatch-friendly). |

### Human Verification Required

None for this phase. Live `cache_read_input_tokens>0` confirmation on real Bedrock is explicitly DEFERRED to the end-of-milestone Bedrock pass (consistent with the project's defer-live-verification policy and documented in ISS-031/SUMMARY). Offline structural proof is complete and passing.

### Gaps Summary

No gaps. All 5 observable truths are verified against the actual codebase, all 4 artifacts exist and are substantive + wired, all 3 key links are connected, requirements FIX-034/ISS-031 are recorded, and the INV-3 golden-neutrality contract holds (20/20 tests pass with SNAPSHOT_UPDATE unset and zero golden-file diffs). INV-13 respected (middleware + model kwargs only, deepagents loop untouched). SC-001 respected (Bedrock dispatch via `isinstance`, no new hardcoded model id). lint-imports 4/0.

Minor note (not a gap): the clamp ceiling in `build_model` uses the resolved per-call `max_tokens - 1` rather than the literal `settings.MAX_OUTPUT_TOKENS - 1` named in the plan truth wording. This is a documented checker refinement (SUMMARY "Decisions Made") — it is strictly more correct (never exceeds the call's own output cap) and coincides with `MAX_OUTPUT_TOKENS - 1` on the default path, which the passing test asserts.

---

_Verified: 2026-07-04T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
