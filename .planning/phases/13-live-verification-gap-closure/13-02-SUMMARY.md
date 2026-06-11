---
phase: 13-live-verification-gap-closure
plan: 02
subsystem: agents-runtime
tags: [f4, prompt-hygiene, fabricated-tool-xml, handoff-coder, defense-in-depth]
requires:
  - phase: 12
    provides: live-verification REPORT.md finding F4 (fabricated tool-XML in text-only outputs)
provides:
  - "tool_availability prompt block: no-tools anti-fabrication preamble for zero-tool agents"
  - "_strip_fabricated_tool_xml runner sanitizer on tool-less done outputs"
  - "HandoffCoder bounded parse-retry + XML-tolerant _extract_json + JSON-only prompt constraint"
affects: [prompt-composition, deep-agent-runner, handoff-pipeline]
tech-stack:
  added: []
  patterns:
    - "no_tools derived in create_runner (exclude_builtin AND zero custom tools) and threaded into composition"
    - "conditional named prompt block: slot in DEFAULT_ORDER, emitted only when blocks dict carries the key"
    - "bounded re-prompt: fresh DeepAgentRunner per attempt, hard 2-attempt cap, runtime faults never retried"
key-files:
  created:
    - backend/tests/agents/test_text_only_prompt_hygiene.py
    - backend/tests/unit/test_handoff_coder_hardening.py
  modified:
    - backend/agents/factory.py
    - backend/agents/capabilities/prompt/policy.py
    - backend/app/agents/deep_agent_runner.py
    - backend/app/agents/handoff/coder.py
    - backend/tests/agents/test_guardrails.py
decisions:
  - "tool_availability placed FIRST in DEFAULT_ORDER so the constraint frames the whole prompt; tool-having agents never carry the key → their composition is byte-identical"
  - "Runner sanitizer keys off exclude_builtin_tools AND zero custom tools (mirror of the factory no_tools derivation); streamed chunks intentionally NOT filtered — only the authoritative done output"
  - "_strip_fabricated_tool_xml early-returns the SAME object when the pattern is absent (identity), guaranteeing characterization byte-parity"
  - "Coder retry wraps ONLY the stream+parse; the post-parse edits-shape ValueError stays outside the loop (unchanged contract); RuntimeError from a runner error event propagates immediately"
metrics:
  duration: ~15 min
  tasks: 2
  files: 7
  completed: 2026-06-12
---

# Phase 13 Plan 02: F4 Gap Closure — Fabricated Tool-XML in Text-Only Outputs Summary

Zero-tool agents now get a first-position anti-fabrication preamble, the runner strips fabricated `<function_calls>`/`<invoke>` spans from tool-less done outputs, and the handoff coder parses-or-retries-once-or-fails-loudly on XML-polluted responses.

## Task Commits

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | No-tools preamble + runner-level XML sanitizer | 78441dad | factory.py, prompt/policy.py, deep_agent_runner.py, test_text_only_prompt_hygiene.py, test_guardrails.py |
| 2 | Handoff coder hardening | 1ce434e4 | handoff/coder.py, test_handoff_coder_hardening.py |

## What was built

### Task 1 — Prompt hygiene + output sanitation (F4 items 1 and 3)

- `create_runner` now resolves tools BEFORE prompt composition and derives `no_tools = exclude_builtin_tools and not custom_tools` — True only for literal zero-callable-tool agents (`tools: []` with no MCP tools pre-warmed). Workspace/prototype agents (exclude flips False), planning agents (PLANNING_TOOLS bind), and MCP-bound agents never qualify.
- `_compose_system_prompt(spec, ctx, *, no_tools=False)` emits `blocks["tool_availability"]` (the terse `_NO_TOOLS_PREAMBLE`, 6 lines) when `no_tools` is True. The preamble concretely forbids `<function_calls>`, `<invoke>`, `write_todos`, `read_file`, `write_file`, `edit_file`, and to-do blocks, and requires file content as plain text.
- `"tool_availability"` added FIRST in the default `PromptAssemblyPolicy` `DEFAULT_ORDER` — the slot only renders when the block is present, so every tool-having agent's composed prompt is byte-unchanged (pinned by a dedicated byte-identity test).
- `_strip_fabricated_tool_xml(text)` (module-level, `deep_agent_runner.py`) removes non-greedy `<function_calls>...</function_calls>` and standalone `<invoke ...>...</invoke>` spans; applied to `full_output` in the terminal `done` event ONLY when the runner was constructed with `exclude_builtin_tools=True` and zero custom tools. Clean input returns the same object (identity) — scripted-model characterization outputs stay byte-identical. Streamed chunks are intentionally not filtered (documented in the docstring).

### Task 2 — Handoff coder hardening (F4 item 2)

- `_CODING_SYSTEM_PROMPT` "## Output format" gains an explicit no-tools / no-XML constraint paragraph: the entire response must be the single JSON object.
- `_extract_json` strips `<function_calls>[\s\S]*?</function_calls>` spans BEFORE fence-stripping, then proceeds with the existing parse → largest-`{...}` fallback. The live failure shape (leading fabricated XML wrapping valid JSON) now parses on the first attempt.
- `propose_edits` wraps the runner-stream + parse in a `for attempt in range(1, _MAX_PARSE_ATTEMPTS + 1)` loop (hard bound 2). On `JSONDecodeError`/`ValueError` from attempt 1 it logs the existing warning and re-runs with the SAME system prompt plus `_CORRECTIVE_SUFFIX` on the user message (names the failure, restates the JSON-only contract). Second failure re-raises exactly as before (pipeline maps to `agent_error`). A FRESH `DeepAgentRunner` is constructed per attempt (independent one-shots — no re-implemented agent loop, INV-13). `RuntimeError` from a runner `error` event propagates immediately and is never retried.

## Verification

- `tests/agents/test_text_only_prompt_hygiene.py` — 10 passed: preamble PRESENT for epic-architect (`tools: []`), ABSENT for app-code-generator (workspace) and deep-planner (planning), positioned first; sanitizer span-removal + identity pins.
- `tests/unit/test_handoff_coder_hardening.py` — 6 passed: scenario (a) garbage→valid = 2 attempts; (b) garbage×2 = ValueError after exactly 2 runner constructions; (c) XML-wrapped JSON parses first attempt; (d) corrective suffix on second message only; plus runtime-fault never-retry and direct `_extract_json` pins.
- `tests/agents/test_create_runner.py` + `tests/agents/test_guardrails.py` — 22 passed (order-pin test updated additively per plan).
- `tests/unit -k handoff` — 28 passed (propose_edits signature/return shape unchanged).
- `tests/agents/test_characterization_prototype.py` — 2 passed; **no golden file modified** (`git status` clean on `tests/agents/characterization/`).
- `/opt/homebrew/bin/lint-imports` — 4 contracts kept, 0 broken.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated the existing DEFAULT_ORDER pin test**
- **Found during:** Task 1 (verify step)
- **Issue:** `tests/agents/test_guardrails.py::test_policy_registered_with_default_order` pinned the 6-slot order tuple
- **Fix:** added `"tool_availability"` first, additively — explicitly anticipated by the plan ("that is the intended behavior change for F4, not a parity break")
- **Files modified:** backend/tests/agents/test_guardrails.py
- **Commit:** 78441dad

## Known Stubs

None — all three defenses are fully wired and tested.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes. All four `<threat_model>` mitigate dispositions implemented: T-13-02-01 (strip narrows parser input, test pins it), T-13-02-02 (hard 2-attempt bound asserted), T-13-02-04 (non-greedy linear span patterns on max_tokens-capped output).

## Success Criteria Status

- ROADMAP Phase 13 criterion 4 TRUE at the offline-verifiable boundary: every `tools: []` composition carries the anti-fabrication preamble, the runner sanitizes tool-less done outputs, and the handoff coder parses-or-retries-or-fails-loudly (F4).
- Live re-verification of actual Haiku behavior deferred to the end-of-milestone live pass (project convention).

## Self-Check: PASSED

- Created files exist: test_text_only_prompt_hygiene.py, test_handoff_coder_hardening.py, 13-02-SUMMARY.md
- Commits exist: 78441dad (Task 1), 1ce434e4 (Task 2)
- Verification suites: 38 passed (hygiene/create_runner/guardrails/hardening), 28 passed (handoff), 2 passed characterization (no golden modified), lint-imports 4 kept / 0 broken
