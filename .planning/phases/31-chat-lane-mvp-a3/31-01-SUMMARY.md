---
phase: 31-chat-lane-mvp-a3
plan: 01
subsystem: ui
tags: [react, typescript, vitest, streaming-json, chat, open-design, apache-2.0]

# Dependency graph
requires:
  - phase: 29-chat-transport
    provides: SSE/REST run-event transport (useRunStream) that emits the ordered frames these primitives parse/coalesce
provides:
  - "partial-json: repairJsonPrefix + parsePartialJson — tolerant repair/parse of a truncated JSON prefix (open-design borrow #1)"
  - "streaming-json: extractStreamingJsonString — single named-string-field extractor over an open JSON fragment (borrow #2)"
  - "blocks.types: AgentEvent input union + ChatBlock render union (generic-kind discriminators, SC-001)"
  - "buildBlocks: pure order-preserving events->blocks coalescing reducer (borrow #4)"
  - "frontend/NOTICE + THIRD-PARTY-NOTICES.md: Apache-2.0 attribution to nexu-io/open-design for all 7 borrow mechanisms"
affects: [31-02-tool-renderer-registry, 31-04-chat-lane, chat-runtime, licensing]

# Tech tracking
tech-stack:
  added: []  # ZERO new deps — pure-TS clean-room reimplementation of Apache-2.0 mechanisms
  patterns:
    - "Clean-room reimplementation from a behavioral spec (no build-time dep on / no bundled copy of the borrowed source) + Apache-2.0 NOTICE/THIRD-PARTY-NOTICES + per-file attribution header"
    - "Interface-first render contract (blocks.types) pinned before the consuming lane, discriminated on GENERIC event kinds only (SC-001)"
    - "Single-forward-pass, no-backtracking tolerant parsers (bounded, DoS-safe: return undefined/partial instead of throwing/looping)"

key-files:
  created:
    - frontend/src/components/chat/runtime/partial-json.ts
    - frontend/src/components/chat/runtime/partial-json.test.ts
    - frontend/src/components/chat/runtime/streaming-json.ts
    - frontend/src/components/chat/runtime/streaming-json.test.ts
    - frontend/src/components/chat/runtime/blocks.types.ts
    - frontend/src/components/chat/runtime/buildBlocks.ts
    - frontend/src/components/chat/runtime/buildBlocks.test.ts
    - frontend/NOTICE
    - frontend/THIRD-PARTY-NOTICES.md
  modified: []

key-decisions:
  - "D-09: no external chat framework — borrow open-design mechanisms via clean-room reimplementation WITH Apache-2.0 attribution (NOTICE + THIRD-PARTY-NOTICES listing all 7 mechanisms up front, #1/#2/#4 landed here, #3/#5/#6/#7 pre-attributed for downstream plans)"
  - "partial-json truncation policy: salvage the FIRST/only partial value in a container (`{\"a\":\"he` -> `{a:\"he\"}`) but DROP an incomplete trailing pair when the container already holds a complete element (`{\"a\":1,\"b\":\"tex` -> `{a:1}`) — never shadow real prior data, never empty a salvageable container"
  - "SC-001: AgentEvent/ChatBlock unions + buildBlocks branch on generic event kinds only (text/thinking/tool_use/tool_result/usage/status/file_op) — no workflow/agent-name discriminator; status carries no transcript block; file_op runs group into one file_ops block"

patterns-established:
  - "chat/runtime/ directory as the pure, React-free, maximally-testable logic layer the chat lane renders against"
  - "attribution header block-comment ('Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md') on every borrow module"

requirements-completed: [CHATUI-01]

# Metrics
duration: 8min
completed: 2026-07-08
---

# Phase 31 Plan 01: Open-Design Borrow Primitives + Apache-2.0 Attribution Summary

**Three pure, dependency-free chat-runtime primitives (partial-json repair, single-field streaming extractor, events→blocks reducer) + the ChatBlock render contract, land under `frontend/src/components/chat/runtime/` with 30 green vitest cases, tsc-identity, and an Apache-2.0 NOTICE crediting nexu-io/open-design.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-08T08:15:49Z
- **Completed:** 2026-07-08T08:23:49Z
- **Tasks:** 2
- **Files modified:** 9 created

## Accomplishments
- `partial-json.ts` — `repairJsonPrefix` + `parsePartialJson`: single-pass tolerant repair/parse of a truncated JSON prefix (salvages the first partial value, drops incomplete trailing pairs, never throws) — open-design borrow #1.
- `streaming-json.ts` — `extractStreamingJsonString`: escape-aware, truncation-tolerant single named-string-field extractor over an open JSON fragment — borrow #2.
- `blocks.types.ts` + `buildBlocks.ts` — the interface-first `AgentEvent`/`ChatBlock` unions (generic-kind discriminators, SC-001) and the pure order-preserving reducer that merges text/thinking deltas, pairs tool_use↔tool_result, groups file_op runs, and emits point usage blocks — borrow #4.
- `frontend/NOTICE` + `frontend/THIRD-PARTY-NOTICES.md` — Apache-2.0 attribution to nexu-io/open-design listing all 7 borrow mechanisms with upstream `file:line` + local reimplementing file (D-09); each borrow module carries the attribution header comment.

## Task Commits

Each task was committed atomically:

1. **Task 1: partial-json + streaming-json repair primitives (borrow #1, #2) + Apache-2.0 NOTICE** — `ba046b55` (feat)
2. **Task 2: ChatBlock contract + buildBlocks events→blocks reducer (borrow #4)** — `12775135` (feat)

**Plan metadata:** _(this docs commit)_

_Opportunistic TDD (`tdd_mode=false`): each task committed test + implementation together as one atomic unit._

## Files Created/Modified
- `frontend/src/components/chat/runtime/partial-json.ts` — tolerant truncated-JSON repair/parse (borrow #1)
- `frontend/src/components/chat/runtime/partial-json.test.ts` — 11 vitest cases (complete/truncated object+array, unterminated string salvage, escaped-quote, garbage→undefined)
- `frontend/src/components/chat/runtime/streaming-json.ts` — single named-string-field streaming extractor (borrow #2)
- `frontend/src/components/chat/runtime/streaming-json.test.ts` — 8 vitest cases (leading/after-keys field, absent, escaped quote, non-string, whitespace)
- `frontend/src/components/chat/runtime/blocks.types.ts` — `AgentEvent` + `ChatBlock` unions + `FileOp`/`ToolStatus` (SC-001 generic discriminators)
- `frontend/src/components/chat/runtime/buildBlocks.ts` — pure events→blocks coalescing reducer (borrow #4)
- `frontend/src/components/chat/runtime/buildBlocks.test.ts` — 11 vitest cases (text/thinking merge, tool pairing+status, same/diff-name tools, file_ops grouping, usage, status-noop, empty)
- `frontend/NOTICE` — Apache-2.0 derived-software notice for open-design
- `frontend/THIRD-PARTY-NOTICES.md` — all 7 borrow mechanisms attributed (upstream file:line + local file)

## Decisions Made
- **partial-json asymmetry resolved with a single consistent rule:** salvage the first/only partial value in a container, but drop an incomplete trailing pair once the container holds a complete element. This reconciles the two documented shapes (`{"a":"he` → `{a:"he"}` vs `{"a":1,"b":"tex` → `{a:1}`) without ever shadowing real prior data or emptying a salvageable container.
- **status events carry no ChatBlock:** the render union has no `status` kind (it is a connection/lifecycle signal), so `buildBlocks` consumes it without emitting a transcript block.
- **file_op runs are the "same-family grouping":** consecutive file operations coalesce into one `file_ops` block; regular tools each keep their own block (same-name runs stay separate, ordered).

## Deviations from Plan

None - plan executed exactly as written.

_(One in-task adjustment, not a scoped deviation: the initial `partial-json` keyword parser salvaged any token sharing a keyword's first letter, so `"not json at all"` was misread as a partial `null` and returned `null` instead of `undefined`. Tightened `parseKeyword` to fail on genuine garbage — caught by the Task-1 garbage-input test before commit; no behavior/scope change beyond correctness.)_

## Issues Encountered
None beyond the in-task keyword-parser tightening noted above (surfaced and fixed by its own failing test prior to the Task-1 commit).

## User Setup Required
None - no external service configuration required. Zero new npm dependencies (pure-TS reimplementation).

## Next Phase Readiness
- The three pure primitives + the `ChatBlock`/`AgentEvent` contract are stable and importable by 31-02 (tool-renderer registry / block components) and 31-04 (the chat lane).
- Borrow mechanisms #3/#5/#6/#7 are already pre-attributed in `THIRD-PARTY-NOTICES.md` so downstream plans only add their local-path rows.
- Verified offline: `vitest run src/components/chat/runtime/` → 30/30 green; `tsc --noEmit` identity (zero new errors beyond the known `e2e/fixtures/mockApi.ts` baseline); SC-001 grep 0; INV-3 held (no backend / golden / e2e-spec file touched).

## Self-Check: PASSED

---
*Phase: 31-chat-lane-mvp-a3*
*Completed: 2026-07-08*
