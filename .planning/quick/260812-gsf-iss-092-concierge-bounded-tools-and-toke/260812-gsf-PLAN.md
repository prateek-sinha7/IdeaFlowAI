---
id: 260812-gsf
slug: iss-092-concierge-bounded-tools-and-toke
description: "ISS-092 — the Concierge is pre-fed the ENTIRE run event log through unbounded read tools (measured 2,306,776 tokens on one question) and its own model spend is never counted. Give it bounded, on-demand tool access; make its tokens exist."
date: 2026-08-12
status: planned
issue: ISS-092
branch: bugfix/spec-revision-context-loss
base_commit: 5b004e1c
---

# Quick Task 260812-gsf — ISS-092: bounded Concierge tools + Concierge token counting

## Problem (all figures re-derived at HEAD `5b004e1c` from `backend/dev.db`, read-only)

Two compounding defects on the same code path.

### D1 — the Concierge's own model spend is unmeasurable

`concierge.py:363-372` drains the runner event stream with:

```python
async for event in runner.astream_events(user_message):
    if event["type"] != "chunk":
        continue
```

`DeepAgentRunner` emits a `{"type": "usage", ...}` event per model turn
(`deep_agent_runner.py:497-514`). The Concierge discards every one. Nothing anywhere
records a Concierge token: the single `workflow_runs.token_usage` writer
(`run_commands.py:2096-2115`) is fed exclusively from `agent_complete` events, and
`converse` runs from a background task spawned by `POST /api/runs/{id}/messages`,
outside `execute()`'s lifetime, so `aux_token_usage` cannot reach it either.

**Consequence: the cost of D2 below cannot be read from the data at all.**

### D2 — three unbounded read tools feed the model the whole run

`concierge.py:431-446` exposes `read_events()` (calls `scoped_store.read_events(run_id, 0)`
— no LIMIT, no type filter), `list_refs()` (projects full `artifact_refs.content` bodies
inline) and `get_ref()` (one whole body). The system prompt at `:507-509` and `:544-548`
*orders* the model to "always call read_events for real progress".

Measured payload at the 15 recorded `chat_message` points (`chars/4` proxy, the register's
own unit):

| Run @ seq | rows | chars | est. tokens |
|---|---|---|---|
| `0a27b397`@12123 | 12,123 | 9,227,107 | **2,306,776** |
| `caa5d175`@10519 | 10,519 | 1,542,857 | 385,714 |
| `a7dba362`@7721 | 7,721 | 1,069,085 | 267,271 |
| `fa66227a`@1322 | 1,328 | 214,457 | 53,614 |

`caa5d175` recorded 142,818 input+cache-write tokens for its whole pipeline; one chat read
was 205,390 = **144%**. `a7dba362` recorded 177,135; one read was 267,271 = **151%**.
**A single Concierge question can cost more input than the entire pipeline that produced
the run.**

**The payload driver is NOT `agent_chunk`.** Measured type breakdown of `0a27b397`@12123:

```
agent_input        18 rows   7,290,638 chars   max row 479,605   <- 79% of the payload
agent_chunk    12,042 rows   1,473,694 chars   max row     169
planner_complete    1 row      389,881 chars
```

A type filter that drops `agent_chunk` but keeps `agent_input` fixes almost nothing.

Two further unbounded sources the issue row never mentions, both verified:

- `list_refs()` — `6e38b9a7` has 56 refs totalling **5,804,067 chars ≈ 1,451,016 tokens**
  returned inline in one call.
- `get_ref()` — largest single `artifact_refs.content` body is **389,651 chars ≈ 97,412
  tokens**.

And one found while planning: `workflow_runs.agent_outputs` reaches **7,450,942 chars** and
embeds each agent's full `input_prompt` — so any new "what did agent X say" tool must
project `output` only, never the blob.

### D3 — the Concierge holds a filesystem WRITE surface (security)

`concierge.py:346-351` never passes `exclude_builtin_tools`, so
`deep_agent_runner.py:328` excludes only the `task` tool. The model is handed
`write_file`, `edit_file`, `read_file`, `ls`, `glob`, `grep`, `write_todos` — while
`concierge.py:30-31` states *"the Concierge's tool surface is read + propose only."*
**That docstring is false at HEAD.**

### D4 — `get_ref` is not run-scoped (security)

`ScopedStore.get_ref` (`authz.py:212-227`) filters `owner_id` + visibility, never `run_id`.
A prompt-injected `ref_id` inside untrusted run content can pull an artifact body from a
*different run of the same owner* (and via `visibility in ('workspace','public')`, another
workspace). Not cross-owner — no IDOR — but a real cross-run scope escape, on a surface whose
own prompt declares run content untrusted (`concierge.py:517`).

## The locked design decision (owner's, not re-litigated here)

Give the Concierge **proper tool-call access so it fetches only the appropriate data on
demand**, instead of being pre-fed the entire event history. A `LIMIT` clause is a
**backstop, not the fix**.

## Non-goals / explicit scope fence

- **The handoff half is OUT.** `handoff_pipeline.py:403/:494/:514` and `handoff/coder.py:235`
  are 100% unmetered and `handoff_sessions` has no token column — different code, different
  lifecycle, no shared context, unverifiable offline. Filed as its own ISS.
- **`ScopedStore.read_events` does NOT gain a LIMIT.** It is the replay primitive with 18+
  callers (`run_stream.py:196`, `runs.py:1089`, `run_commands.py:583/1248/2197`,
  `engine.py:2342/6153/6207/6248/7401/7851`, `authz.py:417`, `conversation.py:99`). A bounded
  *sibling* is added instead, mirroring the codebase's own `last_event_of_types` precedent.
- **`conversation.py` is reused verbatim, not modified.** INV-12: reuse the existing
  transcript bounding, do not write a second renderer. (Its own server-side full read is
  noted as a follow-up ISS — it is not a regression, the Concierge does the same read today.)
- No headline-cost change: `chat_usage` is reported as a **separate line**, never folded into
  `workflow_runs.token_usage`.

---

## Task 1 — counting first (commit 1)

Ships alone, ~15 lines, near-zero risk. It must land first because the effect of Task 2 is
only assertable once the number exists.

**Files:** `backend/app/agents/chat/concierge.py`, `backend/app/api/run_commands.py`

**Action:**

1. `concierge.py::converse` — replace the bare `continue` drain with a `usage` branch that
   **sums** across turns (a tool-calling Concierge emits one `usage` event per turn, so
   overwriting would undercount). Surface on the per-request ctx as `ctx.usage`, using the
   same `try/except` degrade idiom as `ctx.proposals` (`:377-380`). Carry `model_id` from
   `runner.model_id` inside the same dict — one attribute, no extra ctx pollution.
2. `run_commands.py::_drive` — after the terminal `chat_reply` append, append ONE durable
   `run_events` row:
   - `event_id=f"chat-usage:{body.message_id}"` — `append_event_next_seq` is already
     idempotent on `event_id` (`authz.py:414-420`), so a retried POST cannot double-count.
   - `type="chat_usage"`, payload carries the four counters + `model_id` +
     `estimated_cost_usd` via the existing `estimate_cost_usd`
     (`agents/capabilities/model_pricing.py`, already imported in this module).
   - `ScopedStore` stamps `owner_id` + `workspace_id` (`authz.py:296-303`).
   - **No migration.** Option A of the design: a `run_events` row is legal at any lifecycle
     point (`chat_reply` already proves it on terminal runs), replays through SSE and
     `GET /api/runs/{id}/events` for free.
   - Wrapped so a counting failure can never break the reply — the answer is the product,
     the number is telemetry.

**Absolute rule:** if a token was not observed, it is reported as unmeasured. **Never**
estimate from `len(chat_reply)`.

**Why a separate line, not the headline:**
1. Comparability — `workflow_runs.token_usage` answers "what does this workflow cost to
   run"; folding in user chattiness makes two runs of the same workflow non-comparable.
2. Terminal immutability — `_apply_terminal_completion` is documented as the SOLE writer of
   those columns; chat happens after it and never again. A second writer is an INV-12
   violation on a seam this codebase deliberately consolidated.
3. INV-3 — the headline is priced inside `pipeline_complete`, which the 5 characterization
   goldens pin.

The FE slot already exists: `ChatTokenWidget.tsx:38-48` declares `ComposedContextTelemetry`
as an optional extension that degrades to hidden.

**Verify:** `test_converse_accumulates_usage_across_turns` (two scripted turns, sums);
`test_chat_usage_never_mutates_workflow_run_token_usage`. Both seen RED first.

---

## Task 2 — the bounded tool surface (commit 2)

**Files:** `backend/agents/authz.py`, `backend/app/agents/chat/concierge.py`,
`backend/app/api/run_commands.py`

### 2a. One new bounded read on `ScopedStore` (`agents/authz.py`)

`async def read_events_of_types(self, run_id, types, *, limit, after_seq=0) -> list`
— `.filter(type.in_(tuple(sorted(types))))`, `.order_by(seq.desc()).limit(limit)`, returned
oldest-first. Same `_scope_owner_ws` default-deny filter, same `_acquire` /
`finally: if owned: session.close()` idiom (**mandatory** — `run_stream.py` feeds a
session-less store, so a skipped `finally` leaks one pooled connection per live stream).
Mirrors `last_event_of_types` (`authz.py:332-378`) exactly, including the
`tuple(sorted(types))` determinism note. **This pushes the bound into SQL** — that is what
makes the fix real rather than cosmetic.

### 2b. The tool surface (`concierge.py::_read_tools`)

Every tool is a `@tool`-decorated **closure over `scoped_store` and `run_id`**. That closure
*is* the authorization model: **`run_id` is never a tool parameter, so the model has no
syntax for naming another run.** Every tool returns plain JSON-safe data via the existing
`_row_to_dict`, degrades to `[]`/`{}` on any error, and is hard-capped in **characters**
(the unit `compaction:chat_history` already asserts against).

| Tool | Signature | Returns | Bound |
|---|---|---|---|
| `get_run_progress` | `() -> dict` | derived COUNTS, not rows | fixed, ~400 chars |
| `list_agents` | `() -> list[dict]` | `{name, role, status, duration_s, output_chars}`, **no output text** | ≤40 agents |
| `get_agent_output` | `(agent_name, max_chars=4000) -> dict` | `{agent_name, truncated, total_chars, text}` | `min(max_chars, 8000)` |
| `list_artifacts` | `(kind="") -> list[dict]` | metadata only — **`content` stripped** | ≤50 refs |
| `get_artifact` | `(ref_id, max_chars=6000) -> dict` | one body, truncated + flagged | `min(max_chars, 12000)` |
| `read_recent_events` | `(types="", limit=20) -> list[dict]` | tail-N, allow-listed types | `min(limit,50)`, 1,000 chars/row |
| `read_gate_history` | `() -> list[dict]` | today's gate history | 20 rows (data is tiny: 9 rows repo-wide, max detail 26 chars) |

`read_recent_events` intersects its `types` argument server-side with a module-level
allow-list of lifecycle / gate / chat types. **`agent_input`, `agent_chunk`, `tool_call`,
`tool_result` and `planner_complete` are NOT in the allow-list and cannot be requested** —
that is the specific fix for the measured blowout.

`get_agent_output` reads `workflow_runs.agent_outputs`, which embeds `input_prompt` bodies
(max 7.45M chars): it selects the named agent and projects **`output` only**, head-truncated.
An unmatched `agent_name` returns `{"error": "unknown agent"}`.

`get_artifact` calls `scoped_store.get_ref(ref_id)` **then asserts `row.run_id == run_id`**,
returning `{}` otherwise. **This closes D4.**

### 2c. Deletions — INV-12, the main risk in this change

`read_events`, `list_refs`, `get_ref` are **DELETED** from `_read_tools`, not kept for
compatibility. `read_gate_events` is renamed/bounded in place. No tool may survive alongside
its replacement. A tool-name allow-list test is the mechanical enforcement.

### 2d. `exclude_builtin_tools=True` (closes D3)

Added at the `DeepAgentRunner(...)` construction (`concierge.py:346-351`). Drops all seven
built-ins via `_BUILTIN_TOOLS` and makes the module docstring true. The docstring at
`:30-31` is corrected in the same commit.
**Side-effect check:** `_sanitize_fabricated_xml = exclude_builtin_tools and not self.tools`
(`deep_agent_runner.py:334`) stays `False`, because the Concierge always has custom tools —
so there is no output-path change. To be asserted, not assumed.

### 2e. Prompt rewrite

`_compose_system_prompt` hard-codes `read_events` at `:507-509` and `:544-548`. Left alone,
the model calls a tool that no longer exists. Both are rewritten into a tool-usage block
ordered by cheapness, instructing the model to report `truncated=true` honestly and never to
state a number it did not fetch. **Kept verbatim** (out of scope, FIX-213/FIX-115/c72
behaviour): RESPONSE RULES `:475-487`, INTENT ROUTING for revision/chain `:490-506`, the
untrusted-content instruction `:517-518`, the `chain_hints` block `:585-605`.

A test asserts every tool name mentioned in the prompt exists in the built tool set.

### 2f. Multi-turn — the trap that silently breaks

The Concierge has **no checkpointer** (`thread_id` is inert) and `_ConciergeCtx` never sets
`conversation_context`, so multi-turn coherence today comes **solely** from `read_events`
returning the chat rows inside the flood. Deleting it naively kills multi-turn.

The replacement **already exists and is reused, not rebuilt** (INV-12):
`context_provider:conversation` (`conversation.py:67-92`) + `compaction:chat_history`
(`:123-136`, `keep_recent=6` byte-verbatim, 6,000-char budget) — both registered, both green
offline. `converse` resolves the provider through the registry (the legal kernel→capability
direction this module already uses for `register`) and stashes its block on the ctx.

`_ConciergeCtx` sets `current_spec_injects={"conversation"}`.
**The provider's self-gate at `conversation.py:69-71` is NOT relaxed** — that gate is what
keeps it dormant on golden runs. Verified: `current_spec_injects` is set in production only
at `engine.py:8955`, and no `AGENT.md` or `workflow.yaml` declares the `conversation` inject,
so the provider is dormant today and stays dormant on every golden path.

The dead `_DEFAULT_CONTEXT_BUDGET` (`concierge.py:61`, referenced nowhere in the repo) is
finally wired as `ctx.conversation_budget`.

---

## Tests — every one seen RED before it is trusted

In `tests/agents/test_concierge_capability.py` (the existing harness drives real `converse`
through a scripted `BaseChatModel` — reused, not rebuilt) unless noted.

**Bounding**
1. `test_no_tool_returns_unbounded_event_history` — fake store with 12,000 rows including a
   480,000-char `agent_input`; invoke **every** tool; assert each result `< 25,000` chars.
   *This is the test that would have caught ISS-092.*
2. `test_read_recent_events_rejects_bulk_types` — ask for
   `types="agent_input,agent_chunk,planner_complete"`; assert none appear.
3. `test_get_artifact_truncates_and_flags` — 400,000-char ref → `truncated=True`,
   `len(content) <= 12000`, `total_chars` reports the real size.
4. `test_list_artifacts_omits_content`.
5. `test_read_tools_expose_only_the_bounded_allow_list` — exact name-set equality, so a
   re-added unbounded tool fails CI (INV-12 enforcement).

**Authorization**
6. cross-owner denial extended to every new tool name.
7. `test_get_artifact_denies_cross_run_ref` — **RED at HEAD** (closes D4).
8. `test_no_tool_accepts_a_run_id_argument` — introspect each tool's args schema.
9. `test_concierge_impl_imports_no_raw_orm` — existing, must stay green.

**Tool surface**
10. `test_concierge_model_sees_no_filesystem_tools` — capture `bind_tools`; assert no
    `write_file`/`edit_file`/`read_file`/`ls`/`glob`/`grep`/`write_todos`/`task`.
    **RED at HEAD.** Plus an assertion that `_sanitize_fabricated_xml` is still `False`.

**Counting**
11. `test_converse_accumulates_usage_across_turns` — turns `(10,5)` and `(7,3)` → sums.
12. `test_chat_usage_never_mutates_workflow_run_token_usage`.

**Multi-turn**
13. `test_conversation_context_reaches_the_concierge_prompt` — the last 6 turns appear
    **byte-verbatim** in the composed prompt and the block is ≤ 6,000 chars.

**Prompt consistency**
14. `test_system_prompt_names_only_existing_tools`.

**Reconciliations (changed behaviour, not deletions):** two existing tests name the deleted
`read_events` tool — `test_read_tools_go_through_scoped_store_and_deny_cross_owner` and
`test_read_tools_serialize_rows_to_plain_dicts`. They are **retargeted onto the replacement
tools**, keeping their assertions (default-deny scoping; plain-dict projection). Neither is
weakened or removed.

## Data-level proof (zero model spend)

Re-run the measurement SQL against `backend/dev.db` and record before/after. Modelled
bounded projection (allow-listed types, tail-20, 1,000 chars/row) already computed:

| Run @ seq | before (chars / est tok) | bounded (chars / est tok) | reduction |
|---|---|---|---|
| `0a27b397`@12123 | 9,227,107 / 2,306,776 | 8,357 / 2,089 | **1,104×** |
| `caa5d175`@10519 | 1,542,857 / 385,714 | 6,977 / 1,744 | 221× |
| `a7dba362`@7721 | 1,069,085 / 267,271 | 8,879 / 2,219 | 120× |
| `fa66227a`@1322 | 214,457 / 53,614 | 11,400 / 2,850 | 18.8× |

Worst bounded case across all 15 recorded questions: **11,400 chars ≈ 2,850 tokens.**
After the fix this is re-measured by driving the **shipped tools** against a fake store
backed by real `dev.db` rows — a measurement of the code, not a SQL model.

## Baselines (measured by me at `5b004e1c`, before any edit)

| Check | Result |
|---|---|
| Characterization goldens (5 files) | **10 passed** |
| `lint-imports` from `backend/` | **4 kept / 0 broken** |
| Concierge suite (6 files) | **2 failed / 67 passed** — both pre-existing stale assertions |
| `test_gates` + `test_declared_gate_streaming` + `test_wire_parity` + `test_prompt_contracts` | **11 failed / 54 passed** — known pre-existing |
| `test_banned_patterns.py` | **14 passed** |
| `tests/unit/test_chat_messages_endpoint.py` | **3 failed / 25 passed** — pre-existing `TestRouting` |

The two pre-existing Concierge reds are `test_compose_system_prompt_injects_chain_hints_block`
(asserts `"follow-up" not in prompt`; FIX-213's base prompt now contains "follow-up
questions") and `test_confirm_round_trip_executes_revision_seam` (`'_FakeUser' object has no
attribute 'tier'`). **The prompt rewrite touches the first one** — the new tool block must
not make it worse, and its status is reported explicitly rather than left to look
pre-existing.

## Exit gates

- [ ] Goldens still **10 passed**; `git diff --stat` on the golden fixture dir is **empty**.
- [ ] `lint-imports` from `backend/` still **4 kept / 0 broken**.
- [ ] `test_banned_patterns.py` green; zero `create_deep_agent` in `concierge.py` (INV-13).
- [ ] Pre-existing red counts unchanged (11 / 2 / 3), same ids.
- [ ] `read_events`, `list_refs`, `get_ref` are **absent** from the built tool set.
- [ ] Every new test seen RED first, with its failure message recorded.
