---
phase: quick-260704-ttk
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/agents/deep_agent_runner.py
  - backend/agents/execution_engine/engine.py
  - backend/tests/agents/characterization/_normalize.py
  - backend/app/api/websocket.py
  - backend/tests/agents/test_iss032_cache_tokens.py
  - .planning/FIX-REGISTER.md
  - .planning/ISSUES-REGISTER.md
  - .planning/STATE.md
autonomous: true
requirements: [FIX-036, ISS-032, ISS-033]

must_haves:
  truths:
    - "The shared runner surfaces the prompt-cache split: a Bedrock usage_metadata with input_token_details={cache_read:N, cache_creation:M} produces a usage event carrying cache_read_tokens=N and cache_write_tokens=M — universal for every workflow's agents (no per-workflow branch)."
    - "A non-Bedrock / no-cache / scripted turn (input_token_details absent or None) yields cache_read_tokens=0 and cache_write_tokens=0 — never raises."
    - "The engine accumulates cache_read/cache_write per agent and threads per-agent counts onto agent_complete AND run totals (total_cache_read_tokens / total_cache_write_tokens) onto pipeline_complete."
    - "Both cost sites price the UNCACHED input split without double-count: estimate_cost_usd receives input_tokens = max(0, total_input - cache_read - cache_write), plus cache_read_tokens / cache_write_tokens / cache_ttl — so a cached run costs strictly less than pricing every input token at 1x."
    - "The 5 characterization goldens stay byte/event-identical with SNAPSHOT_UPDATE unset (INV-3 golden-neutral): under the scripted model cache=0 so uncached=total and the cost/token math is unchanged, and the 4 NEW event keys are stripped by _VOLATILE_STRIP_KEYS — NO golden JSON regenerated."
    - "ISS-032 is RESOLVED and ISS-033 (SmartPlanner/ClarifyEngine/direct-call agents bypass caching + uncounted cost) is logged as the follow-up."
  artifacts:
    - path: "backend/app/agents/deep_agent_runner.py"
      provides: "usage-emit sites surface cache_read_tokens/cache_write_tokens from usage_metadata.input_token_details (streaming usage event + astream_with_usage TokenUsage)"
      contains: "cache_read_tokens"
    - path: "backend/tests/agents/test_iss032_cache_tokens.py"
      provides: "Offline proof: runner cache extraction, no-double-count cost split, normalizer strips the 4 new keys"
      contains: "def test_"
    - path: "backend/tests/agents/characterization/_normalize.py"
      provides: "_VOLATILE_STRIP_KEYS additively strips the 4 new cache event keys (golden-neutral)"
      contains: "total_cache_read_tokens"
  key_links:
    - from: "backend/app/agents/deep_agent_runner.py"
      to: "usage_metadata.input_token_details"
      via: "on_chat_model_end usage event + astream_with_usage sum read cache_read/cache_creation"
      pattern: "input_token_details"
    - from: "backend/agents/execution_engine/engine.py"
      to: "agents.capabilities.model_pricing.estimate_cost_usd"
      via: "pipeline_complete cost site passes the uncached split + cache args + cache_ttl (~L2278)"
      pattern: "cache_read_tokens="
    - from: "backend/app/api/websocket.py"
      to: "agents.capabilities.model_pricing.estimate_cost_usd"
      via: "workflow_runs.token_usage persist site sums per-agent cache + prices the split (~L1994)"
      pattern: "cache_read_tokens="
---

<objective>
BACKEND-ONLY. ISS-032: surface prompt-cache token counts through the SHARED deep-agent path (runner + engine + both cost sites) so run cost reflects the caching discount FIX-034 turned on in prod — universal for every workflow's agents. langchain_aws sets usage_metadata.input_tokens = TOTAL (incl. cache) with the split in input_token_details={cache_read, cache_creation} (bedrock_converse.py:1997-2014), but today the runner forwards only input/output tokens, so estimate_cost_usd gets cache=0 → cached runs are OVER-reported (cache-reads billed 1x not 0.1x).

Purpose: Correct run-cost accuracy for cached runs at BOTH cost sites without changing the event contract, the golden bytes, or any p10/thinking/caching behavior — plumbing only (INV-13).
Output: Runner surfaces the cache split → engine token_usage + agent_complete → estimate_cost_usd priced on the UNCACHED split at both sites; INV-3 golden-neutral via ADDITIVE _VOLATILE_STRIP_KEYS (NO regen); offline test; FIX-036 + ISS-032 RESOLVED + ISS-033 docs.
</objective>

<execution_context>
@/Users/1000060523/Documents/Work/UKI/Flowin/flowin/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@CLAUDE.md
@backend/CLAUDE.md
@.planning/STATE.md

# The exact in-scope sites (read the surrounding variables before editing):
# - backend/app/agents/deep_agent_runner.py  usage-event class docstring ~L24-29;
#     on_chat_model_end usage-emit ~L497-509; astream_with_usage sum+TokenUsage ~L723-778
# - backend/agents/execution_engine/engine.py  run totals _tok_in/_tok_out ~L2244-2246;
#     pipeline_complete data + cost site ~L2266-2282; per-attempt token init ~L2789 AND ~L2848;
#     usage accumulation arm ~L2872-2874; results.append ~L3298-3311; agent_complete yield ~L3314-3320
# - backend/app/api/websocket.py  agent_complete collector ~L1888-1899; token_usage persist ~L1986-1999
# - backend/tests/agents/characterization/_normalize.py  _VOLATILE_STRIP_KEYS ~L101-150
# Confirmed facts (do NOT re-verify):
#   estimate_cost_usd already imported top-level: engine.py:46, websocket.py:18
#   TokenUsage (app/agents/types.py:26-52) already carries cache_read_tokens/cache_write_tokens
#   estimate_cost_usd(model_id, input_tokens, output_tokens, cache_read_tokens=0, cache_write_tokens=0, *, cache_ttl="5m")
#   settings.BEDROCK_PROMPT_CACHE_TTL = "5m" (config.py:111); Haiku cache_read=0.1e-6, cache_write_5m=1.25e-6
</context>

<constraints>
- INV-3 (golden-neutral, NO regen): the 4 NEW event keys — agent_complete `cache_read_tokens`/`cache_write_tokens` + pipeline_complete `total_cache_read_tokens`/`total_cache_write_tokens` — MUST be added to `_VOLATILE_STRIP_KEYS` in `_normalize.py` (ADDITIVE; precedent deliverable_mimetype/redoable). estimated_cost_usd is already stripped; total_*_tokens are volatile-required-sentinel'd. Run the 5 goldens with SNAPSHOT_UPDATE UNSET; if ANY golden JSON diffs, a normalizer entry is missing — fix the normalizer, do NOT regenerate.
- NO double-count: usage_metadata.input_tokens is TOTAL incl. cache. Pass `input_tokens = max(0, total_input - cache_read - cache_write)` (the uncached portion) PLUS cache_read/cache_write separately. Never subtract twice; never pass total AND cache.
- Default-0 everywhere: absent/None `input_token_details` (non-Bedrock / ChatAnthropic / scripted / no-cache) → cache_read=0, cache_write=0. Never raise.
- Universal / SC-001: the fix lives in the SHARED runner + engine + shared estimate_cost_usd — NO workflow-name or agent-name branch anywhere. Every workflow's agents inherit it.
- INV-13: plumbing only — NO change to the deepagents loop, the p10 cachePoints middleware, thinking config, or any t2x pricing behavior.
- DO NOT: touch SmartPlanner / ClarifyEngine / any direct-model-call path (that is ISS-033); add a p10/thinking behavior change; regenerate a golden; edit model_pricing.py or types.py (already cache-ready).
- Scope ONLY these files: deep_agent_runner.py, engine.py, _normalize.py, websocket.py, the new test, and the docs (FIX-REGISTER / ISSUES-REGISTER / STATE).
- Runtime: `python3.11`, no venv. Do NOT run the full pytest suite (offline-hangs). Atomic commits, NO `Co-Authored-By` trailer. Branch: new-workflow-engine.
</constraints>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Producer plumbing — runner surfaces the cache split + engine accumulates/emits it + normalizer strips it</name>
  <files>backend/app/agents/deep_agent_runner.py, backend/agents/execution_engine/engine.py, backend/tests/agents/characterization/_normalize.py</files>
  <behavior>
    - Runner cache extraction: given usage_metadata {"input_tokens": T, "output_tokens": O, "input_token_details": {"cache_read": N, "cache_creation": M}} → the emitted usage event carries cache_read_tokens=N, cache_write_tokens=M (and input_tokens stays T, the TOTAL).
    - Absent input_token_details, input_token_details=None, or meta=None → cache_read_tokens=0, cache_write_tokens=0 (never raises).
    - Engine per-agent accumulation: across N usage events the agent's cache_read/cache_write sum; results[i] carries cache_read_tokens/cache_write_tokens; agent_complete.data carries them; pipeline_complete.data carries total_cache_read_tokens/total_cache_write_tokens = run sums.
    - Golden-neutral: under the scripted model (no input_token_details → 0/0) every new key is 0 and is STRIPPED by _VOLATILE_STRIP_KEYS → the 5 event goldens stay byte/event-identical.
  </behavior>
  <action>
    RUNNER (backend/app/agents/deep_agent_runner.py):
    - Add a module-level pure helper `_cache_token_counts(meta) -> tuple[int, int]` (type the param as `Any`; no new import needed) that returns `(cache_read, cache_write)` read from `meta`'s `input_token_details` sub-dict: `details = (meta or {}).get("input_token_details") or {}; return int(details.get("cache_read", 0) or 0), int(details.get("cache_creation", 0) or 0)`. Docstring: cite that langchain_aws (Bedrock) reports input_tokens as the TOTAL incl. cache and puts the split in input_token_details={cache_read, cache_creation} (bedrock_converse.py), while ChatAnthropic/scripted/no-cache turns omit the block → (0, 0); never raises.
    - At the `on_chat_model_end` usage-emit (~L497-509): inside `if meta:`, compute `_cr, _cw = _cache_token_counts(meta)` and add `"cache_read_tokens": _cr, "cache_write_tokens": _cw` to the yielded `{"type": "usage", ...}` dict. Leave input_tokens/output_tokens unchanged (input_tokens stays the TOTAL — the cost split happens at the cost sites, not here).
    - In `astream_with_usage` (~L760-778): add `sum_cache_read = 0` / `sum_cache_write = 0` beside sum_in/sum_out; in the `elif etype == "usage":` arm add `sum_cache_read += event.get("cache_read_tokens", 0) or 0` and `sum_cache_write += event.get("cache_write_tokens", 0) or 0`; populate the final `TokenUsage(..., cache_read_tokens=sum_cache_read, cache_write_tokens=sum_cache_write)` (total_tokens stays input+output).
    - Update TWO docstrings: (a) the class-contract usage-event line (~L26) to `{"type":"usage","input_tokens":int,"output_tokens":int,"cache_read_tokens":int,"cache_write_tokens":int}`; (b) the now-stale astream_with_usage note (~L743-750) that says it "leaves cache_read_tokens / cache_write_tokens at 0" — rewrite to state the cache split is now summed from the usage events' input_token_details (ISS-032).

    ENGINE (backend/agents/execution_engine/engine.py):
    - At BOTH per-attempt token-init points (~L2789 and ~L2848, immediately beside `agent_input_tokens = 0` / `agent_output_tokens = 0`) add `agent_cache_read_tokens = 0` and `agent_cache_write_tokens = 0`.
    - In the `elif etype == "usage":` accumulation arm (~L2872-2874) add `agent_cache_read_tokens += event.get("cache_read_tokens", 0) or 0` and `agent_cache_write_tokens += event.get("cache_write_tokens", 0) or 0`.
    - In the `results.append({...})` dict (~L3298-3311) add `"cache_read_tokens": agent_cache_read_tokens, "cache_write_tokens": agent_cache_write_tokens`.
    - In the `agent_complete` yield's `data` dict (~L3314-3320) add `"cache_read_tokens": agent_cache_read_tokens, "cache_write_tokens": agent_cache_write_tokens`.
    - At the run-totals block (~L2245-2246, beside `_tok_in`/`_tok_out`) add `_cache_read = sum(r.get("cache_read_tokens", 0) or 0 for r in results)` and `_cache_write = sum(r.get("cache_write_tokens", 0) or 0 for r in results)`.
    - In `_pipeline_complete_data` (~L2266-2282) add `"total_cache_read_tokens": _cache_read, "total_cache_write_tokens": _cache_write` (leave the `estimated_cost_usd` cost call UNCHANGED in this task — it is re-priced in Task 2).

    NORMALIZER (backend/tests/agents/characterization/_normalize.py):
    - Add all 4 new keys to `_VOLATILE_STRIP_KEYS` (~L101-150): `cache_read_tokens`, `cache_write_tokens`, `total_cache_read_tokens`, `total_cache_write_tokens`, with a comment citing the deliverable_mimetype/redoable precedent — additive metadata NOT in _REQUIRED_DATA_KEYS, stripped so the 5 characterization event goldens stay byte-identical (INV-3, ISS-032).
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -c "from app.agents.deep_agent_runner import _cache_token_counts as f; assert f({'input_token_details':{'cache_read':60000,'cache_creation':5000}})==(60000,5000); assert f({'input_token_details':None})==(0,0); assert f({})==(0,0); assert f(None)==(0,0); print('RUNNER-OK')" && python3.11 -c "from tests.agents.characterization._normalize import _VOLATILE_STRIP_KEYS as K; assert {'cache_read_tokens','cache_write_tokens','total_cache_read_tokens','total_cache_write_tokens'} <= K, 'missing strip keys'; print('STRIP-OK')" && python3.11 -c "import ast; [ast.parse(open(p).read()) for p in ['agents/execution_engine/engine.py','app/agents/deep_agent_runner.py']]; print('PARSE-OK')" && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py tests/agents/test_characterization_od_ppt.py -q && /opt/homebrew/bin/lint-imports</automated>
  </verify>
  <done>_cache_token_counts extracts the split and defaults to (0,0) on absent/None (RUNNER-OK); the 4 new keys are in _VOLATILE_STRIP_KEYS (STRIP-OK); both edited Python files parse; the 5 characterization goldens are byte/event-identical with SNAPSHOT_UPDATE UNSET (NO golden JSON changed — if one diffs, a normalizer key is missing; fix the normalizer, do NOT regen); lint-imports 4 kept / 0 broken.</done>
</task>

<task type="auto">
  <name>Task 2: Consumer/pricing split — both cost sites price the UNCACHED portion (no double-count)</name>
  <files>backend/agents/execution_engine/engine.py, backend/app/api/websocket.py</files>
  <action>
    ENGINE cost site (backend/agents/execution_engine/engine.py, the `estimated_cost_usd` value in `_pipeline_complete_data` ~L2278-2280): change the 2-token call to price the uncached split (the import at engine.py:46 already exists; `_settings.BEDROCK_PROMPT_CACHE_TTL` exists). Replace the value with:
      estimate_cost_usd(
          model_id or _settings.BEDROCK_INFERENCE_PROFILE_ID,
          input_tokens=max(0, _tok_in - _cache_read - _cache_write),
          output_tokens=_tok_out,
          cache_read_tokens=_cache_read,
          cache_write_tokens=_cache_write,
          cache_ttl=_settings.BEDROCK_PROMPT_CACHE_TTL,
      )
    `_cache_read`/`_cache_write` are the run totals added in Task 1. Leave the sibling `total_input_tokens`/`total_output_tokens`/`model_id` keys unchanged (input_tokens telemetry stays the TOTAL; only the COST is discounted).

    WEBSOCKET (backend/app/api/websocket.py):
    - In the `agent_complete` collector arm (~L1888-1892, beside `current_agent["input_tokens"] = ...`) add `current_agent["cache_read_tokens"] = update["data"].get("cache_read_tokens", 0)` and `current_agent["cache_write_tokens"] = update["data"].get("cache_write_tokens", 0)` so the run-total sum below sees the per-agent cache counts (sourced from the engine agent_complete event).
    - At the `wr.token_usage = json.dumps({...})` persist site (~L1986-1999): beside `total_input`/`total_output` add `total_cache_read = sum(a.get("cache_read_tokens", 0) or 0 for a in agent_outputs_collector)` and `total_cache_write = sum(a.get("cache_write_tokens", 0) or 0 for a in agent_outputs_collector)`. Add `"total_cache_read_tokens": total_cache_read, "total_cache_write_tokens": total_cache_write` to the persisted dict, and change the `estimated_cost_usd` value (the import at websocket.py:18 already exists) to:
      estimate_cost_usd(
          wr.model_id or settings.BEDROCK_INFERENCE_PROFILE_ID,
          input_tokens=max(0, total_input - total_cache_read - total_cache_write),
          output_tokens=total_output,
          cache_read_tokens=total_cache_read,
          cache_write_tokens=total_cache_write,
          cache_ttl=settings.BEDROCK_PROMPT_CACHE_TTL,
      )
    Keep the `if total_input + total_output > 0:` guard as-is. Do NOT add any new engine event key here (this is the persisted DB column, not the wire).
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -c "import ast; [ast.parse(open(p).read()) for p in ['agents/execution_engine/engine.py','app/api/websocket.py']]; print('PARSE-OK')" && grep -c 'cache_read_tokens=' agents/execution_engine/engine.py app/api/websocket.py && grep -c 'cache_ttl=' agents/execution_engine/engine.py app/api/websocket.py && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py tests/agents/test_characterization_od_ppt.py -q && /opt/homebrew/bin/lint-imports</automated>
  </verify>
  <done>Both cost sites call estimate_cost_usd with `input_tokens=max(0, total - cache_read - cache_write)` + cache_read_tokens/cache_write_tokens/cache_ttl (grep shows `cache_read_tokens=` and `cache_ttl=` in BOTH files); both files parse; the 5 goldens remain byte/event-identical (SNAPSHOT_UPDATE unset — under scripted cache=0 so uncached=total and the cost math is unchanged); lint-imports 4/0.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Offline test suite (runner extraction, no-double-count split, normalizer strip) + gate sweep</name>
  <files>backend/tests/agents/test_iss032_cache_tokens.py</files>
  <behavior>
    - Runner extraction: _cache_token_counts({"input_token_details":{"cache_read":60000,"cache_creation":5000}}) == (60000, 5000); input_token_details None/absent/meta-None → (0, 0); partial dict (only cache_read) → other defaults 0.
    - Usage-event wiring (source-pin): the on_chat_model_end usage-emit in deep_agent_runner.py source references both cache_read_tokens and cache_write_tokens (locks the emitted-event contract offline without driving the deepagents loop).
    - Cost split (no double-count): with model "eu.anthropic.claude-haiku-4-5-20251001-v1:0" and total_input decomposed as uncached=5000, cache_read=60000, cache_write=5000 (total 70000), split = estimate_cost_usd(model, input_tokens=5000, output_tokens=0, cache_read_tokens=60000, cache_write_tokens=5000, cache_ttl="5m") is MUCH LESS than all_at_1x = estimate_cost_usd(model, input_tokens=70000, output_tokens=0); and split == pytest.approx((5000*1e-6 + 60000*0.1e-6 + 5000*1.25e-6) * 1.10, rel=1e-6) — cache_read at 0.1x, cache_write_5m at 1.25e-6, ×1.10 regional, uncached input NOT re-added.
    - Normalizer strips the 4 new keys: _normalize on an agent_complete event drops cache_read_tokens/cache_write_tokens; on a pipeline_complete event drops total_cache_read_tokens/total_cache_write_tokens; all 4 ∈ _VOLATILE_STRIP_KEYS.
  </behavior>
  <action>
    Create `backend/tests/agents/test_iss032_cache_tokens.py` — offline, no network/DB/Bedrock — covering the behavior block. Import `_cache_token_counts` from `app.agents.deep_agent_runner`, `estimate_cost_usd` from `agents.capabilities.model_pricing`, and `_normalize` + `_VOLATILE_STRIP_KEYS` from `tests.agents.characterization._normalize`. For the usage-event wiring test, read `app/agents/deep_agent_runner.py` off disk (`pathlib.Path(...).read_text()`) and assert both `cache_read_tokens` and `cache_write_tokens` appear (source-pin, mirrors the t2x both-call-sites-use-the-module test — avoids importing the heavy runner graph). Use `pytest.approx` for the split assertions. Assert the split is strictly less than all_at_1x (e.g. `split < all_at_1x * 0.5`) to prove the discount, AND assert the exact no-double-count value.
    Then run the full offline gate sweep (new test + model_pricing + context_providers + 5 goldens + lint-imports) and confirm the pricing change is invisible to the goldens by construction.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin/backend && python3.11 -m pytest tests/agents/test_iss032_cache_tokens.py tests/agents/test_model_pricing.py tests/agents/test_context_providers.py -q && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py tests/agents/test_characterization_od_ppt.py -q && /opt/homebrew/bin/lint-imports</automated>
  </verify>
  <done>test_iss032_cache_tokens.py green (extraction defaults, source-pinned usage-event wiring, no-double-count split strictly less than all-at-1x + exact value, normalizer strips all 4 keys); test_model_pricing.py + test_context_providers.py green; the 5 characterization goldens byte/event-identical with SNAPSHOT_UPDATE unset (NO regen); lint-imports 4 kept / 0 broken.</done>
</task>

<task type="auto">
  <name>Task 4: Register FIX-036 + resolve ISS-032 + log ISS-033 + STATE</name>
  <files>.planning/FIX-REGISTER.md, .planning/ISSUES-REGISTER.md, .planning/STATE.md</files>
  <action>
    FIX-REGISTER.md: append one new 8-column pipe row `FIX-036` immediately after the `FIX-035` row (~L44), matching the existing column shape (`| ID | Date | short-desc | root-cause+fix | Files | Phase | Invariants | Status |`). Date 2026-07-04. Short-desc: ISS-032 — run cost not cache-discounted; the shared runner dropped the input_token_details cache split so both cost sites priced cache-reads at 1x (over-report once FIX-034 caching is ON). Root-cause+fix: runner surfaces input_token_details (cache_read/cache_creation) into the usage event → engine token_usage + agent_complete → estimate_cost_usd priced on the UNCACHED split (input−cache) so cost reflects the caching discount; universal (shared runner/engine, no workflow branch); golden-neutral via additive _VOLATILE_STRIP_KEYS (no regen). Files: `backend/app/agents/deep_agent_runner.py`, `backend/agents/execution_engine/engine.py`, `backend/app/api/websocket.py`, `backend/tests/agents/characterization/_normalize.py`, `backend/tests/agents/test_iss032_cache_tokens.py`. Phase: quick-260704-ttk. Invariants: INV-1/3/12/13 · SC-001 ✅. Status: Done.

    ISSUES-REGISTER.md: flip the ISS-032 row status from `**OPEN** (deferred; quick-260704-t2x)` to `**RESOLVED** (quick-260704-ttk)` and note the resolution (runner surfaces input_token_details into the usage event → engine → both cost sites price the uncached split; golden-neutral, no regen; live cache_read>0 confirmation deferred to the end-of-milestone Bedrock pass). Then APPEND a new row ISS-033 (respect the append-only-by-ID convention): severity minor, product; STATUS **OPEN** (deferred; scoped-out of quick-260704-ttk). Body: SmartPlanner + ClarifyEngine + the handoff Test/Compliance agents call the model DIRECTLY (not via the shared cached deep-agent runner) → those calls get no Bedrock prompt caching AND their tokens are uncounted in run cost; affects ~every workflow, up to ~150k tokens each. Action: a shared cached-invoke helper (route direct calls through the same cachePoints + usage_metadata path) + fold their tokens into run-cost accounting. Notes: companion to FIX-036/ISS-032 (which fixed only the shared runner path).

    STATE.md: update the `## Current Position` "Last activity" line to record completed quick task 260704-ttk (ISS-032 RESOLVED — cache-token surfacing through the shared runner/engine → both cost sites price the uncached split; FIX-036 + ISS-033 logged; INV-3 5 goldens byte/event-identical, no regen; new offline test_iss032_cache_tokens green; lint-imports 4/0). Do NOT churn the front-matter progress block.
  </action>
  <verify>
    <automated>cd /Users/1000060523/Documents/Work/UKI/Flowin/flowin && grep -q 'FIX-036' .planning/FIX-REGISTER.md && grep -q 'ISS-033' .planning/ISSUES-REGISTER.md && grep -Eq 'ISS-032.*(RESOLVED|quick-260704-ttk)' .planning/ISSUES-REGISTER.md && grep -q '260704-ttk' .planning/STATE.md && echo 'DOCS-OK'</automated>
  </verify>
  <done>FIX-036 row present after FIX-035; ISS-032 marked RESOLVED (quick-260704-ttk); ISS-033 appended as OPEN follow-up; STATE.md records the 260704-ttk completion (DOCS-OK).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| run telemetry -> billing/cost display | `estimated_cost_usd` feeds operator-facing cost telemetry; mis-pricing cached input (1x instead of 0.1x) over-reports cost — the very bug being fixed. |
| Bedrock usage_metadata -> engine token accounting | `input_token_details` is provider-shaped, untrusted structurally (absent on ChatAnthropic/scripted); a missing/None block must degrade to 0, never raise. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-ttk-01 | Information disclosure | wrong cost reported (over-report of cached runs) | mitigate | No-double-count split (`input = total − cache`), cache_read/cache_write priced at their tiers via the ONE shared estimate_cost_usd (INV-12) at BOTH sites; unit test pins split ≪ all-at-1x + the exact value. |
| T-ttk-02 | Denial of service | malformed/absent input_token_details crashes token accounting | mitigate | `_cache_token_counts` guards `meta or {}` and `input_token_details or {}` with `int(... or 0)`; all engine/websocket sums use `.get(...,0) or 0`; never raises — proven by (0,0)-default tests. |
| T-ttk-03 | Tampering | a new event key silently perturbs the INV-3 golden bytes | mitigate | The 4 additive keys are stripped in `_VOLATILE_STRIP_KEYS`; goldens run with SNAPSHOT_UPDATE UNSET and any diff fails the gate → normalizer fix, never a regen. |
| T-ttk-SC | Tampering | npm/pip/cargo installs | accept | No package installs — plumbing over existing cache-ready types/pricing; no new dependency to legitimacy-gate. |
</threat_model>

<verification>
Whole-plan gates (run from `backend/`, `python3.11`, no venv, offline):
1. `python3.11 -m pytest tests/agents/test_iss032_cache_tokens.py tests/agents/test_model_pricing.py tests/agents/test_context_providers.py -q` → green.
2. `python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py tests/agents/test_characterization_od_ppt.py -q` (SNAPSHOT_UPDATE UNSET) → 5 goldens byte/event-identical, NO golden JSON changed, NO regen.
3. `/opt/homebrew/bin/lint-imports` (from `backend/`) → 4 contracts kept, 0 broken.
4. `grep -c 'cache_ttl=' agents/execution_engine/engine.py app/api/websocket.py` → both cost sites price the split.
5. Docs: FIX-036 in FIX-REGISTER.md, ISS-032 RESOLVED + ISS-033 in ISSUES-REGISTER.md, 260704-ttk in STATE.md.
</verification>

<success_criteria>
- The shared deep-agent runner surfaces the prompt-cache split (cache_read/cache_creation) into its usage event and text-only TokenUsage — universal for every workflow's agents (SC-001, no workflow branch).
- The engine accumulates cache_read/cache_write per agent and threads them onto agent_complete + run totals onto pipeline_complete.
- BOTH cost sites price the UNCACHED input split (input − cache) with cache_read/cache_write tiers via the single shared estimate_cost_usd (INV-12) — a cached run costs strictly less than pricing every input token at 1x, with no double-count.
- INV-3 preserved: 5 characterization goldens byte/event-identical, SNAPSHOT_UPDATE unset, NO regen (the 4 new keys are additively stripped).
- ISS-032 RESOLVED; ISS-033 (direct-call agents bypass caching + uncounted cost) logged; FIX-036 + STATE recorded.
- INV-13 respected: plumbing only — no deepagents-loop / caching-middleware / thinking / t2x-pricing behavior change.
</success_criteria>

<output>
Create `.planning/quick/260704-ttk-iss-032-capture-prompt-cache-tokens-for-/260704-ttk-SUMMARY.md` when done.
</output>
