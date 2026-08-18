---
id: 260812-gsf
slug: iss-092-concierge-bounded-tools-and-toke
description: "ISS-092 — bounded on-demand Concierge tools + Concierge token counting"
date: 2026-08-12
status: complete
issue: ISS-092
branch: bugfix/spec-revision-context-loss
base_commit: 5b004e1c
commits:
  - 47c7672f  # part 1 — counting
  - 7b79e426  # part 2 — bounded tool surface
---

# Quick Task 260812-gsf — SUMMARY

Two commits, counting first (it is the smaller, near-zero-risk half, and the effect of
the redesign is only assertable once the number exists).

## What shipped

### `47c7672f` — the Concierge's own spend becomes a number

- `converse` gained a `usage` branch that **sums** the runner's per-turn usage (a
  tool-calling Concierge takes several turns; overwriting would report only the last).
  Totals ride the per-request ctx, the same idiom as `ctx.proposals` — the capability
  instance still holds no state (`test_no_self_scoped_proposal_buffer_on_capability`
  stays green).
- `_drive` writes one durable `chat_usage` `run_events` row per answered turn,
  `event_id=chat-usage:{message_id}`, so `append_event_next_seq`'s idempotency makes a
  retried POST a no-op rather than a double count. **No migration.**
- Priced with the existing `estimate_cost_usd`, using the same uncached-input convention
  as the run's headline cost site.
- Reported as a **separate line**, never folded into `workflow_runs.token_usage`.
- **An absent `ctx.usage` writes no row** — unmeasured stays unmeasured; nothing is ever
  derived from `len(chat_reply)`.

### `7b79e426` — bounded, on-demand tools

| Deleted (INV-12, not shadowed) | Replaced by |
|---|---|
| `read_events()` — whole log | `get_run_progress()`, `list_agents()`, `read_recent_events(types, limit)` |
| `list_refs()` — bodies inline | `list_artifacts(kind)` — metadata only |
| `get_ref(ref_id)` — whole body | `get_artifact(ref_id, max_chars)` — capped + run-verified |
| `read_gate_events()` | `read_gate_history()` — capped, ids stripped |

Plus `get_agent_output(agent_name, max_chars)`, which reads `workflow_runs.agent_outputs`
(7.45M chars worst case, embedding every agent's full `input_prompt`) and projects
**only** the named agent's output, truncated.

- New `ScopedStore.read_events_of_types(...)` puts the bound **in SQL**, mirroring
  `last_event_of_types`. `read_events` itself is untouched — it is the replay primitive
  with 18+ callers.
- `exclude_builtin_tools=True` removes the `write_file`/`edit_file`/`read_file`/`ls`/
  `glob`/`grep`/`write_todos` surface the model was holding, making the module docstring
  true. `_sanitize_fabricated_xml` asserted still `False`.
- `get_artifact` asserts `row.run_id == run_id`, closing a cross-run scope escape.
- Prompt rewritten: both `read_events` instructions replaced, plus a cheapest-first TOOLS
  block that tells the model to report `truncated=true` honestly.
- Multi-turn preserved by reusing `context_provider:conversation` +
  `compaction:chat_history`; `_ConciergeCtx` declares the inject. The provider's
  self-gate is **not** relaxed.

## Measured effect — the shipped tools, over real `dev.db` rows

Driving every shipped tool at all 15 recorded `chat_message` points:

| Run @ seq | before (est. tok) | after (est. tok) | reduction |
|---|---|---|---|
| `0a27b397`@12123 | 2,494,799 | **4,710** | **530×** |
| `0a27b397`@12121 | 2,494,228 | 4,509 | 553× |
| `0a27b397`@5957 | 1,940,140 | 4,109 | 472× |
| `fa66227a`@2181 | 573,573 | 4,675 | 123× |
| `caa5d175`@10519 | 450,283 | 4,263 | 106× |
| `a7dba362`@7721 | 358,640 | 4,765 | 75× |

**No fully tool-saturated turn anywhere in the corpus exceeds 4,785 est. tokens.**
Largest single tool result: 12,690 chars, against a 25,000-char test ceiling.

## Gates — before / after

| Check | Before (`5b004e1c`) | After (`7b79e426`) |
|---|---|---|
| Characterization goldens | 10 passed | **10 passed** |
| Golden fixtures moved | — | **0** (`git status` clean on the fixture dir) |
| `lint-imports` (from `backend/`) | 4 kept / 0 broken | **4 kept / 0 broken** |
| `test_banned_patterns.py` (INV-13) | 14 passed | **14 passed** |
| `create_deep_agent` in `concierge.py` | 0 | **0** |
| gates + declared-gate + wire-parity + prompt-contracts | 11 failed / 54 passed | **11 failed / 54 passed** (same ids) |
| Concierge suite (6 files) | 2 failed / 67 passed | **1 failed / 98 passed** |
| `test_chat_messages_endpoint.py` | 3 failed / 25 passed | **3 failed / 34 passed** (same ids) |

The Concierge suite's second pre-existing red
(`test_confirm_round_trip_executes_revision_seam`) lives in
`test_concierge_proposal_channels.py`; counted with the endpoint files above it is
unchanged. Both pre-existing reds remain, both unrelated to this work:

- `test_compose_system_prompt_injects_chain_hints_block` — asserts `"follow-up" not in
  prompt`; FIX-213/FIX-115 base-prompt text contains "follow-up questions" and "follow-up
  workflow". **Checked explicitly:** the rewrite adds neither `"follow-up"` nor
  `"chained into"`, so the failure mode is byte-identical to baseline.
- `test_confirm_round_trip_executes_revision_seam` — `'_FakeUser' object has no attribute
  'tier'`; the fake predates the entitlements check.

## Tests added (each seen RED first)

`test_no_tool_returns_unbounded_event_history` (RED: `read_events=3,607,954 chars,
list_refs=400,140, get_ref=400,138`) · `test_read_tools_expose_only_the_bounded_allow_list`
· `test_read_recent_events_rejects_bulk_types` · `test_read_recent_events_caps_limit_and_row_size`
· `test_get_artifact_truncates_and_flags` · `test_get_artifact_denies_cross_run_ref` ·
`test_list_artifacts_omits_content` · `test_get_agent_output_never_returns_the_input_prompt`
· `test_list_agents_omits_output_text` · `test_get_run_progress_returns_counts_not_rows` ·
`test_no_tool_accepts_a_run_id_argument` · `test_every_read_tool_denies_cross_owner` ·
`test_concierge_model_sees_no_filesystem_tools` (RED: all 7 built-ins observed) ·
`test_excluding_builtins_does_not_flip_the_xml_sanitizer` ·
`test_conversation_context_reaches_the_concierge_prompt_byte_verbatim` ·
`test_conversation_provider_stays_dormant_without_the_declared_inject` ·
`test_system_prompt_names_only_existing_tools` ·
`test_converse_accumulates_usage_across_turns` ·
`test_converse_reports_zero_usage_rather_than_estimating` ·
`TestChatUsageAccounting` (3).

Two existing tests were **retargeted**, not deleted or weakened:
`test_read_tools_go_through_scoped_store_and_deny_cross_owner` and
`test_read_tools_serialize_rows_to_plain_dicts` named the deleted `read_events` tool;
they now exercise `read_recent_events` with the same default-deny and plain-dict
assertions.

## Deliberately out of scope — filed as new issues

1. **Handoff spend is 100% unmetered** — `handoff_pipeline.py:403/:494/:514` and
   `handoff/coder.py:235` pass no `usage_sink`, and `handoff_sessions` has no token
   column. Different code, different lifecycle, no shared context, unverifiable offline.
2. **`context_provider:conversation` still does a full `read_events`** server-side. Not a
   regression (the deleted tool triggered the identical read, and the prompt ordered the
   model to call it), and no tokens are involved — but it is now unconditional per turn.
   The bounded `read_events_of_types` sibling exists for it.
3. **`TestRouting` in `test_chat_messages_endpoint.py` attempts a real Bedrock call** —
   it does not monkeypatch `_resolve_concierge`, so it reaches `build_model()`. It failed
   here only because the SSO token was expired. Pre-existing; would spend real money on a
   machine with fresh credentials.

## Not proven offline (deferred, not faked)

Whether the live model actually *picks* the right tool per question. Offline proves the
tools exist, are bounded, are run-scoped, and are described in the prompt. The
per-question cost after the change is now readable from the `chat_usage` row — which is
why counting landed first.
