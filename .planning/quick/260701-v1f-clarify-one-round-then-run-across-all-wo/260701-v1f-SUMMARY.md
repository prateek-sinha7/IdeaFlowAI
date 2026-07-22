---
phase: quick-260701-v1f
plan: 01
subsystem: execution_engine / clarify
tags: [clarify, engine, compiler, json-hardening, KAN-82, one-round]
requires: []
provides:
  - clarify.rounds knob (default 1) threaded manifest -> compiler -> ClarifySpec -> ClarifyEngine
  - one-round-then-run clarify loop across all workflows
  - tolerant LLM-JSON parser (_parse_llm_json_array) for KAN-82 content-aware questions
affects:
  - backend/agents/execution_engine/clarify_engine.py
  - backend/agents/workflows/plan.py
  - backend/agents/workflows/compiler.py
  - backend/agents/execution_engine/engine.py
tech-stack:
  added: []
  patterns: [manifest-driven knob threading (mirrors require_render), tolerant-parse-then-fallback]
key-files:
  created:
    - backend/tests/unit/test_clarify_json_parse.py
    - backend/tests/agents/test_clarify_llm_live.py
  modified:
    - backend/agents/execution_engine/clarify_engine.py
    - backend/agents/workflows/plan.py
    - backend/agents/workflows/compiler.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/unit/test_execution_engine.py
    - backend/tests/agents/test_compiler.py
decisions:
  - "clarify.rounds is a per-workflow compiled knob (default 1), not a global MAX=1 constant — name-free (SC-001), manifest-driven (INV-5), opt-in for more rounds."
  - "MAX_CLARIFICATION_ROUNDS (=3) kept as a hard safety ceiling; effective_rounds = max(1, min(max_rounds, ceiling))."
  - "LLM-JSON repair is json.loads-only (no eval/exec/literal_eval) — T-v1f-01; unrecoverable input returns None -> static-library fallback (never crash the gate, INV-3)."
metrics:
  duration: ~6 min
  completed: 2026-07-01
  tasks: 2
  files: 8
---

# Phase quick Plan 260701-v1f: Clarify one-round-then-run + KAN-82 JSON hardening Summary

Two-part clarify fix delivered as one sequential plan: (A) a per-workflow `clarify.rounds` knob (default 1) that makes every clarify workflow ask its questionnaire at most once then run, and (B) a tolerant `json.loads`-only LLM-JSON parser so the single round is genuinely content-aware instead of falling to the static library.

## Task 1 — Part A: one-round-then-run + clarify.rounds knob (commit `c302aeef`)

- `plan.py`: added `ClarifySpec.rounds: int = 1` with a docstring note.
- `compiler.py`: `rounds=int(clarify_raw.get("rounds", 1) or 1)` in the `ClarifySpec(...)` build — `manifest.clarify` is free-form, so no manifest/yaml schema edit; default 1 reaches every existing manifest.
- `clarify_engine.py`: `run(...)` gained `max_rounds: int = 1`; loop guard changed from `while round_num < MAX_CLARIFICATION_ROUNDS` to `while round_num < effective_rounds` where `effective_rounds = max(1, min(max_rounds, MAX_CLARIFICATION_ROUNDS))`. Module docstring updated to one-round-then-run. All three legitimate exits preserved (0-questions -> PROCEED; force_proceed -> PROCEED; terminal `clarification_limit_reached` -> PROCEED). A subset-answer submit now naturally falls through to the terminal PROCEED with no re-ask. `MAX_CLARIFICATION_ROUNDS` kept and still imported.
- `engine.py` (call site ~l.1610): passes `max_rounds=compiled.clarify.rounds`.
- Also added the module-top `import re` in `clarify_engine.py` (checker warning W1 prep for Part B).
- Tests: updated the two OLD 3-round tests to one-round semantics (`test_clarify_engine_asks_once_then_limit_reached`, `test_clarify_engine_empty_submit_proceeds_after_one_round`); added `test_clarify_engine_asks_once_then_proceeds_on_subset` and `test_clarify_engine_rounds_knob_allows_multi_round` (rounds=3 still loops to the ceiling); extended `test_compiler.py` with a rounds default-1 assertion + a `rounds: 2` round-trip case.

## Task 2 — Part B: tolerant LLM-JSON parser + strict prompt (commit `8ea1692a`)

- `clarify_engine.py`: added pure module-level `_parse_llm_json_array(raw) -> list | None` — strips markdown fences, locates the array opener (tolerates a missing closing `]`), first-pass parse, repair pass (smart quotes -> straight, trailing commas, missing commas between objects), then truncation recovery via a string-aware brace-depth scan collecting complete top-level `{...}` objects. `json.loads` only — no eval/exec/literal_eval (T-v1f-01). Returns `None` on unrecoverable/empty input.
- Replaced the brittle inline `re.search(...) + json.loads(json_match.group())` with a single `_parse_llm_json_array(raw)` call; the `except -> return None` outer guard and the static-library fallback (`_generate_questions`) are unchanged (INV-3).
- Strengthened the generation prompt with a final strict directive: output ONLY the raw JSON array, no fences, start `[` end `]`.
- Tests: new offline `test_clarify_json_parse.py` (11 cases — clean, fenced, bare-fenced, trailing-comma, missing-comma, smart-quotes, truncated, prose-wrapped, garbage->None, non-string->None, empty-array->None); new opt-in SSO/`RUN_LIVE_BEDROCK`-gated `test_clarify_llm_live.py` real-Haiku smoke (defers gracefully offline).

## Verification results

- `tests/unit/test_execution_engine.py tests/agents/test_compiler.py` — 40 passed (Task 1 gate).
- `tests/unit/test_clarify_json_parse.py` — 11 passed; `test_clarify_llm_live.py` — 1 skipped (SSO not active).
- Full targeted suite (engine + compiler + json-parse + 5 characterization goldens + nav-coverage + route-table) — **115 passed**. The 5 characterization goldens are byte/event-identical (clarify is inert on them: `clarify.mode="off"` + `gate_agent_ids=[]`) — NO SNAPSHOT_UPDATE. od_ppt not in the golden set (known-environmental, untouched).
- `/opt/homebrew/bin/lint-imports` — **4 kept / 0 broken**.
- Live Haiku smoke: NOT run this session (SSO inactive). Offline tolerant-parser tests stand as evidence; live confirm defers to the milestone-end live pass (defer-live-verification convention). Local `--reload` backend will have hot-reloaded these edits for an ad-hoc live re-test.

## Deviations from Plan

Minor, within the plan's stated intent:

1. **[Rule 1 — Bug] Truncation-case regex early-return.** The plan's step (b) `re.search(r'\[[\s\S]*\]', text)` requires a closing `]`, which a truncated array lacks — it returned `None` before truncation recovery could run. Fixed by locating the array opener with `text.find('[')` and using `text[lb:]` as the span when no bracketed match exists, gating the two intermediate `json.loads` attempts on `match` being present so truncation recovery (step e) always runs for unterminated input. Covered by `test_truncated_array_returns_complete_objects`. Commit `8ea1692a`.
2. **Test naming.** Renamed the max-rounds test to `test_clarify_engine_asks_once_then_limit_reached` (the plan suggested keeping the name; the new name is clearer for one-round semantics). Behavioral assertions match the plan.

## Threat model compliance

- T-v1f-01 (tampering, LLM JSON repair): mitigated — pure `re.sub` string edits + `json.loads` only; no code execution of model text; `None` -> static fallback.
- T-v1f-02 (DoS, rounds bound): mitigated — `effective_rounds = max(1, min(max_rounds, MAX_CLARIFICATION_ROUNDS))` clamps to the ceiling of 3.
- No new dependency (stdlib `re`/`json` only); no migration; no forked clarify path (INV-3 / INV-12 / SC-001 held).

## Known Stubs

None.

## Self-Check: PASSED

- backend/agents/execution_engine/clarify_engine.py — FOUND
- backend/agents/workflows/plan.py — FOUND
- backend/agents/workflows/compiler.py — FOUND
- backend/agents/execution_engine/engine.py — FOUND
- backend/tests/unit/test_clarify_json_parse.py — FOUND
- backend/tests/agents/test_clarify_llm_live.py — FOUND
- Commit c302aeef — FOUND
- Commit 8ea1692a — FOUND
