---
phase: 33-concierge-compaction-a5
plan: 02
subsystem: agents
tags: [capabilities, chat, concierge, deepagents, registry, scoped-store, proposal-only]

# Dependency graph
requires:
  - phase: 33-concierge-compaction-a5 (Wave 1 / 33-01)
    provides: "context_provider:conversation (the compacted chat-history block the Concierge consumes) + registry drift-guard at 68"
  - phase: 30-uploads-multimodal
    provides: "the owner-scoped ScopedStore read pattern (default-deny, IDOR->404) reused by the READ tools"
provides:
  - "chat:concierge — ONE app-side per-run conversational orchestrator resolved by (kind='chat', name='concierge'); runs its model ONLY through DeepAgentRunner (Haiku default, P26 caching inherited), reads owner-scoped run data, emits proposal-only intents"
  - "READ tools (owner-scoped ScopedStore wrappers: read_events/list_refs/get_ref/read_gate_events) + PROPOSAL-ONLY tools (propose_steering_note/propose_revision/propose_gate_action incl. update_specs) that return structured intents and self-execute nothing"
  - "registry lockstep for the concierge (drift-guard count 68 -> 69; app.agents.chat added to _forward_packages)"
affects: [33-03, 33-05, concierge-wiring, steering-disposal]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "app-side capability package (app.agents.chat) that self-registers via _forward_packages — the registry IMPORTS the package (legal app->capabilities), the impl imports the kernel PORT only (import-linter 4 kept / 0 broken)"
    - "duck-typed chat kind (name + async converse(ctx, user_message) -> str, no base.py port — mirrors compaction:html_skeleton / chat_history)"
    - "proposal-only tool pattern: @tool returns a structured ProposalIntent(channel, params) dataclass and invokes no execution seam"

key-files:
  created:
    - backend/app/agents/chat/__init__.py
    - backend/app/agents/chat/concierge.py
    - backend/tests/agents/test_concierge_capability.py
  modified:
    - backend/agents/capabilities/registry.py
    - backend/tests/agents/test_registry_capabilities.py
    - backend/tests/agents/test_input_providers_run_images.py
    - backend/tests/agents/test_uploaded_files_provider.py

key-decisions:
  - "The Concierge's model call goes EXCLUSIVELY through DeepAgentRunner (INV-13); concierge.py never references create_deep_agent (grep count 0), so the banned-pattern gate stays green with no allow-list change."
  - "PROPOSAL-ONLY tools return a frozen ProposalIntent(channel, params) dataclass and self-execute nothing; the app layer (33-03) disposes them behind a confirm chip. An out-of-range gate action degrades to an inert 'request_changes' marker rather than raising inside the model loop."
  - "READ tools resolve their store from ctx.scoped_store when present, else construct ScopedStore(owner_id, workspace_id) — never raw ORM (concierge.py has zero app.models imports). Cross-owner reads yield nothing (IDOR->404)."
  - "System prompt is composed from DATA only (base role + conversation_context block + degrade-safe getattr(compiled,'chat',{})) — no pipeline_type/spec.id/workflow-name branch (INV-1); the chat: manifest key itself lands in 33-05."
  - "The registry 68 -> 69 bump is this plan's alone (33-01 owned 66 -> 68); done all-or-nothing in one commit across _KNOWN + _EXPECTED_NAMES + the three count asserts + _forward_packages."

patterns-established:
  - "App-side conversational capability: a registered impl that composes owner-scoped context + read/propose tools and runs the model through the sanctioned adapter, with the heavy dep kept app-side and the kernel edge zero."
  - "Proposal-only intent surface: read tools (scoped, side-effect-free reads) disjoint from propose tools (structured intents, no execution) — the app disposes, the agent never self-executes."

requirements-completed: [D-05, D-08, SC-1, INV-13]

# Metrics
duration: ~25 min
completed: 2026-07-08
---

# Phase 33 Plan 02: Concierge Capability Summary

**chat:concierge — an app-side per-run conversational orchestrator that answers run questions from owner-scoped run data and emits proposal-only intents, running its model ONLY through the sanctioned DeepAgentRunner (INV-13), with a clean registry lockstep 68 -> 69.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3 of 3
- **Files modified:** 7 (3 created, 4 modified)

## Accomplishments
- Built `chat:concierge` (`ConciergeCapability`, `name="concierge"`) as a duck-typed capability whose async `converse(ctx, user_message)` reaches the model exclusively through `DeepAgentRunner` (Haiku default; P26 cache-points + base-stack summarizer inherited — none re-added).
- Split the tool surface: READ tools (owner-scoped `ScopedStore` wrappers over `read_events`/`list_refs`/`get_ref`/`read_gate_events`, IDOR->404) disjoint from PROPOSAL-ONLY tools (`propose_steering_note`/`propose_revision`/`propose_gate_action` incl. `update_specs`) that return structured `ProposalIntent` records and self-execute nothing.
- Completed the registry lockstep 68 -> 69 (all-or-nothing, one commit): `_KNOWN` + `_EXPECTED_NAMES` += `("chat","concierge")`, `app.agents.chat` added to `_forward_packages`, count asserts bumped in all three drift-guard files.
- Added an offline unit test (scripted `BaseChatModel` via the runner verbatim-use path — no Bedrock): resolve, proposal-only no-side-effect spy, and cross-owner read denial.

## Task Commits

1. **Task 1: chat:concierge capability impl** - `e03ae06e` (feat)
2. **Task 2: registry lockstep (68 -> 69)** - `fe479e64` (feat)
3. **Task 3: concierge offline unit test** - `527fb4e8` (test)

**Plan metadata:** committed separately (this SUMMARY).

## Files Created/Modified
- `backend/app/agents/chat/concierge.py` - The `ConciergeCapability` impl + `ProposalIntent` + the three module-level proposal-only `@tool`s and the per-invocation owner-scoped READ tools.
- `backend/app/agents/chat/__init__.py` - The `app.agents.chat` package; imports `concierge` so `@register` fires on package import (via `_forward_packages`).
- `backend/tests/agents/test_concierge_capability.py` - Offline resolve + proposal-only + read-scoping proof (7 tests).
- `backend/agents/capabilities/registry.py` - `_KNOWN` += `("chat","concierge")`; `_forward_packages` += `"app.agents.chat"`.
- `backend/tests/agents/test_registry_capabilities.py` - `_EXPECTED_NAMES` += pair; tally + count assert 68 -> 69.
- `backend/tests/agents/test_input_providers_run_images.py` - count assert 68 -> 69 (test renamed to `..._sixty_nine`).
- `backend/tests/agents/test_uploaded_files_provider.py` - count assert 68 -> 69 (test renamed to `..._sixty_nine`).

## Decisions Made
See `key-decisions` in the frontmatter — the load-bearing ones: INV-13 (model only via DeepAgentRunner, zero `create_deep_agent` in concierge.py), proposal-only intents (no self-execution), owner-scoped reads (no raw ORM), and data-only system-prompt composition (INV-1).

## Deviations from Plan

None - plan executed exactly as written.

The two count-assert test functions in `test_input_providers_run_images.py` and `test_uploaded_files_provider.py` were renamed from `test_known_count_is_sixty_eight` to `..._sixty_nine` alongside the mandated 68 -> 69 assert bump — a naming-honesty follow-through of the plan's Task-2 count-bump action, not a scope change (no reference to those function names exists).

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The Concierge is registered and resolvable; 33-03 wires the app-layer invocation that INVOKES `converse` and disposes its `ProposalIntent`s behind confirm chips.
- The `chat:` manifest key (suggestions/notes) the system prompt reads degrade-safe via `getattr(compiled,"chat",{})` lands in 33-05.

## Known human_needed / Live-Deferred (Phase-34)
- Live Concierge Q&A against real Bedrock (grounded, non-hallucinated answers) — NOT run offline.
- Multi-turn prompt-cache-point placement across turns — deferred to a live pass.

## Self-Check: PASSED
- Created files present: `backend/app/agents/chat/concierge.py`, `backend/app/agents/chat/__init__.py`, `backend/tests/agents/test_concierge_capability.py`.
- Commits present: `e03ae06e`, `fe479e64`, `527fb4e8`.
- Full offline suite: 134 passed; lint-imports 4 kept / 0 broken; `len(_KNOWN) == 69` = 3 hits, `== 68` = 0 hits.

---
*Phase: 33-concierge-compaction-a5*
*Completed: 2026-07-08*
