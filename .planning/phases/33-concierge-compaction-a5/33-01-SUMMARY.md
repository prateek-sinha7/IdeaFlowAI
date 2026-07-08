---
phase: 33-concierge-compaction-a5
plan: 01
subsystem: agents
tags: [capabilities, compaction, context-provider, registry, chat, run-events]

# Dependency graph
requires:
  - phase: 29-chat-backbone
    provides: "chat_message / chat_reply run_events (the compacted-history source rows)"
  - phase: 30-uploads-multimodal
    provides: "context_provider:uploaded_files (the ContextProvider clone target + owner-scoped read pattern)"
provides:
  - "compaction:chat_history — a pure compact(transcript, *, budget, keep_recent) -> str transform (recent turns byte-verbatim, older tail summarized, char-budget-bounded)"
  - "context_provider:conversation — a ContextProvider that self-gates on the 'conversation' inject token, reads owner-scoped chat run_events via ctx.scoped_store, and returns a single {conversation_context: ...} block bounded by compaction:chat_history"
  - "registry lockstep for the 2 kernel capabilities (drift-guard count 66 -> 68)"
affects: [33-02, 33-03, 33-05, concierge, steering-context]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "duck-typed compaction capability (name + compact(...), no base.py port — mirrors compaction:html_skeleton)"
    - "ContextProvider clone with declared-inject self-gate (INV-1) + degrade-not-crash -> {} (mirrors uploaded_files.py)"

key-files:
  created:
    - backend/agents/capabilities/compaction/chat_history.py
    - backend/agents/capabilities/context_providers/conversation.py
    - backend/tests/agents/test_chat_history_compaction.py
    - backend/tests/agents/test_conversation_provider.py
  modified:
    - backend/agents/capabilities/registry.py
    - backend/tests/agents/test_registry_capabilities.py
    - backend/tests/agents/test_input_providers_run_images.py
    - backend/tests/agents/test_uploaded_files_provider.py

key-decisions:
  - "Compaction measured in CHARACTERS (len), one unit, asserted against the same unit (RESEARCH Open-Q2: parameterize budget/keep_recent, assert SHAPE not a magic number)."
  - "Recent-turn fidelity always wins: under a tight budget the summary marker shrinks first, the keep_recent verbatim tail is never truncated."
  - "In-graph message growth is NOT re-handled here — the deepagents base-stack SummarizationMiddleware (deep_agent_runner.py) owns that; chat_history is the separate composed-transcript-bounding layer of D-08."
  - "conversation provider self-gates ONLY on the declared inject token 'conversation' in ctx.current_spec_injects — never spec.id/pipeline_type/workflow name (INV-1), so it stays dormant on golden runs (INV-3)."
  - "Both modules import-pure: registry decorator + stdlib only; the bounding transform is reached via registry.resolve (the legal kernel->capability direction), never app.* / execution_engine."
  - "Concierge NOT registered in this plan — it is app-side and keeps its own 68 -> 69 bump in 33-02 (different wave, no shared-file double-edit)."

patterns-established:
  - "Bounded composed-context substrate: a pure compaction transform + a self-gating context provider that composes owner-scoped run_events through it."
  - "Owner-scoped chat-events read via ctx.scoped_store.read_events (default-deny; cross-owner -> nothing -> 404); no raw ORM."

requirements-completed: [D-08, SC-2]

# Metrics
duration: "reconstructed (commit window ~4 min: 20:15 -> 20:19 CEST 2026-07-08)"
completed: 2026-07-08
---

# Phase 33 (Concierge + Compaction) — Plan 01 Summary

**Landed the two kernel-pure bounded-chat-history capabilities — `compaction:chat_history` (a pure `compact()` transform) and `context_provider:conversation` (a self-gating provider that composes owner-scoped chat `run_events` through it) — with a clean registry lockstep (drift-guard 66 -> 68). This is the composed-context substrate the Concierge (33-02) consumes.**

> Reconstructed post-hoc during the Phase-33 resume: the three production commits landed cleanly before the executor stalled on a connection drop at the Wave 1 -> Wave 2 boundary (checkpoint `47c37e9f`); no SUMMARY had been written. This summary is grounded in a direct read of the committed files and a green re-run of the plan's test suite (128 passed) + `lint-imports` (4 kept / 0 broken).

## Performance

- **Duration:** reconstructed (production commits span 20:15:27 -> 20:19:17 CEST, 2026-07-08)
- **Tasks:** 3 of 3 (compaction capability + test; conversation provider + test; registry lockstep 66 -> 68)
- **Files modified:** 8 (4 created, 4 modified)

## Accomplishments

### Task 1 — `compaction:chat_history` pure `compact()` capability
- `backend/agents/capabilities/compaction/chat_history.py` (91 lines): `ChatHistoryCompaction` (`name="chat_history"`) `@register("compaction","chat_history", ...)`, duck-typed (no `base.py` port — the `compaction` kind has no formal Protocol, mirroring `html_skeleton`).
- `compact(self, transcript, *, budget, keep_recent) -> str`: if the full transcript fits `budget` it is returned verbatim; otherwise the `keep_recent` most-recent turns stay BYTE-VERBATIM and the older tail becomes ONE short summary marker (`[… N earlier turns summarized (C chars) …]`) so the whole block fits under `budget`. Safety net: if the verbatim recent block alone exceeds budget, the summary shrinks to a minimal marker — recent fidelity always wins.
- Import-pure: registry decorator + stdlib only (grep for `import app|from app|agents.execution_engine|from deepagents` = 0).
- `backend/tests/agents/test_chat_history_compaction.py` (98 lines, 4 tests): under-budget shape proof + recent-verbatim / old-summarized fidelity.

### Task 2 — `context_provider:conversation` clone
- `backend/agents/capabilities/context_providers/conversation.py` (136 lines): `ConversationProvider` (`name="conversation"`) `@register("context_provider","conversation", ...)`, satisfies the `ContextProvider` port (`name` + `async load(ctx) -> dict[str,str]`), a near-verbatim clone of `uploaded_files.py`.
- Self-gate (INV-1): returns `{}` unless `"conversation"` is in `ctx.current_spec_injects` — keeps it dormant on golden runs (INV-3).
- Owner-scoped read (T-33-01-01): reads chat `run_events` STRICTLY via `ctx.scoped_store.read_events(run_id, 0)` (default-deny; cross-owner -> nothing -> 404); no raw ORM. Renders `chat_message`/`chat_reply` rows into `role: text` turns, bounds them through `registry.resolve("compaction","chat_history").compact(...)`, returns a single `{"conversation_context": "## Conversation\n\n" + body}` block.
- Degrade-not-crash: missing store/run handle, empty transcript, or any read error -> `{}`.
- `backend/tests/agents/test_conversation_provider.py` (153 lines, 9 tests): `.name` assert, gated load -> single `conversation_context` key, un-gated -> `{}`, empty/error read -> `{}` (dormant).

### Task 3 — registry lockstep (66 -> 68)
- `registry.py`: `_KNOWN` += `("compaction","chat_history")` + `("context_provider","conversation")` (seeded so manifest refs validate impl-free); `_builtin_modules` += the 2 kernel module paths (eager `discover()` binding). Concierge deliberately NOT added here.
- Drift-guard count bumped 66 -> 68 in all three files (`test_registry_capabilities.py`, `test_input_providers_run_images.py`, `test_uploaded_files_provider.py`); `_EXPECTED_NAMES` += the 2 pairs; running tally extended.

## Verification (re-run on resume)

- `python3.11 -m pytest tests/agents/test_chat_history_compaction.py tests/agents/test_conversation_provider.py tests/agents/test_registry_capabilities.py tests/agents/test_input_providers_run_images.py tests/agents/test_uploaded_files_provider.py` -> **128 passed**.
- `grep -rn "len(_KNOWN) == 68" backend/tests/agents/` -> 3 hits; `... == 66` -> 0.
- `/opt/homebrew/bin/lint-imports` -> **4 kept / 0 broken** (both new modules kernel-pure).

## Commits

- `98a6e0a5` feat(33-01): add compaction:chat_history pure compact() capability
- `3a51511a` feat(33-01): add context_provider:conversation clone (bounded chat history)
- `b250c87e` feat(33-01): registry lockstep for the 2 kernel capabilities (66 -> 68)

## Follow-ups / hand-off to 33-02

- The Concierge (`chat:concierge`, app-side) consumes the `conversation_context` block for its composed system prompt and owns the 68 -> 69 drift-guard bump.
- Live Concierge Q&A / multi-turn cache placement remain Phase-34 live-deferred (not in scope here).
