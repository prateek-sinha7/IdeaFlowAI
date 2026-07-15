---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 10
subsystem: testing
tags: [ci-ratchet, banned-pattern, sse, websocket, cutover, pytest, ast, tokenize]

# Dependency graph
requires:
  - phase: 44-06
    provides: FE transport flag + useWebSocket hook deleted (frontend/src clean)
  - phase: 44-07
    provides: /ws/chat endpoint + SSE_TRANSPORT_ENABLED flag deleted (backend clean)
  - phase: 44-09
    provides: e2e harness migrated to SSE (mockWs.ts gone; waitForClientFrame REST alias)
provides:
  - A CI ratchet (pytest) that FAILS if any of /ws/chat, useWebSocket, routeWebSocket, NEXT_PUBLIC_SSE_TRANSPORT, SSE_TRANSPORT_ENABLED reappears in first-party source
  - Machine-checkable "hard cutoff done" definition (INV-12 exit-gate enforcement)
  - Non-vacuity proof that the scanner fires on an injected regression
affects: [future-44-plans, milestone-close, ci]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Banned-pattern CI ratchet mirroring R15 (test_banned_patterns.py): exact/word-boundary anchors + comment/docstring stripping + a non-vacuity injection guard"
    - "Python code extraction via tokenize (comment strip, string-safe) + AST (docstring detection); TS extraction via URL-safe // + /* */ comment strip"

key-files:
  created:
    - backend/tests/agents/test_sse_cutover_banned_patterns.py
  modified: []

key-decisions:
  - "Scan scope = backend/app + backend/agents + frontend/src ONLY; frontend/e2e deliberately excluded (retains the waitForClientFrame REST alias + historical useWebSocket JSDoc mentions)"
  - "Exact/word-boundary anchors (/ws/chat\\b, \\buseWebSocket\\b) make the D10 survivors structurally immune rather than relying on file allow-listing — a stronger gate that keeps survivors in-scope"
  - "Comment/docstring mentions stripped (tokenize+AST for Python, comment regex for TS) so the many legitimate '/ws/chat was retired' prose lines do not false-red"

patterns-established:
  - "Ratchet non-vacuity: inject a known-bad token into a temp dir and assert the SAME scanner fires (guards a dead regex passing silently)"

requirements-completed: [W5, "C.3", "INV-12"]

# Metrics
duration: 25 min
completed: 2026-07-16
---

# Phase 44 Plan 10: SSE-Cutover Banned-Pattern CI Gate Summary

**A non-vacuous pytest ratchet that FAILS CI if any deleted WS-transport/flag token (`/ws/chat`, `useWebSocket`, `routeWebSocket`, `NEXT_PUBLIC_SSE_TRANSPORT`, `SSE_TRANSPORT_ENABLED`) reappears in first-party source — the machine-checkable definition of "the WebSocket→SSE hard cutoff is done."**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-15
- **Completed:** 2026-07-16
- **Tasks:** 2
- **Files modified:** 1 (new)

## Accomplishments
- New `backend/tests/agents/test_sse_cutover_banned_patterns.py` ratchet scanning `backend/app` + `backend/agents` (Python) and `frontend/src` (TS/TSX) for the five retired transport/flag tokens.
- Five anchored scanners (one parametrized assertion per token) + an aggregate green-tree assertion; the gate PASSES on the cutover-complete tree.
- Structural immunity for the D10 survivors: `/ws/chat\b` never matches `/ws/handoff`; `\buseWebSocket\b` never matches `useHandoffSocket`; proven by `test_sanctioned_survivors_are_immune`.
- Comment/docstring immunity: Python comments+docstrings stripped via `tokenize`+`ast`; TS `//` (URL-safe) + `/* */` stripped — so the live tree's `"/ws/chat was retired"` prose does not false-red.
- Non-vacuity guards (Python + TS): inject known-bad tokens into temp dirs and assert the same scanners fire (T-44-10-01 mitigation — no dead regex can pass silently).

## Task Commits

Each task was committed atomically:

1. **Task 1: Author the SSE-cutover banned-pattern ratchet** - `b2623ffa` (test)
2. **Task 2: Prove the ratchet is non-vacuous** - `30bde14d` (test)

**Plan metadata:** (this docs commit)

## Files Created/Modified
- `backend/tests/agents/test_sse_cutover_banned_patterns.py` - The banned-pattern CI ratchet: `_BANNED` (5 anchored regexes), `_PY_ROOTS`/`_TS_ROOT` scan roots, `tokenize`+`ast` Python code extraction, comment-stripping TS extraction, hard-ban tests, survivor-immunity test, comment-immunity test, and Python+TS non-vacuity injection guards.

## Decisions Made
- **Scope frontend to `frontend/src` (not `frontend/e2e`).** Verified: `mockWs.ts` no longer exists (44-09), `frontend/e2e` retains the `mockSse.waitForClientFrame` REST alias and historical `useWebSocket` JSDoc mentions — scanning e2e would false-red. This follows the orchestrator guardrail + CONTEXT §2 W5 authoritative scope.
- **Anchor-based survivor immunity over blanket file allow-listing.** Keeping survivor files in-scope with exact anchors is strictly stronger than skipping them (a `/ws/chat` reintroduced inside `websocket_handoff.py` would still be caught).
- **Strip comments+docstrings rather than allow-list every prose file.** `tokenize` (string-safe `#` strip) + `ast` docstring detection for Python; URL-safe `//` + `/* */` for TS.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking/Scope] Frontend scan scoped to `frontend/src`, not `frontend/src` + `frontend/e2e`**
- **Found during:** Task 1 (authoring the scanner)
- **Issue:** The plan's `<action>` text listed `frontend/e2e` as a scan root, but `frontend/e2e` legitimately retains the `mockSse.waitForClientFrame` back-compat alias (44-09) and historical `useWebSocket` mentions inside JSDoc block comments. Scanning e2e would either false-red or require e2e-specific comment carve-outs.
- **Fix:** Scoped the frontend scan to `frontend/src` only, matching the authoritative orchestrator guardrail ("Scope the frontend scan to `frontend/src` (NOT `frontend/e2e`...)") and CONTEXT §2 W5 (`frontend/src` + `backend/app` + `backend/agents`). Verified `frontend/src` is clean of all five tokens.
- **Files modified:** backend/tests/agents/test_sse_cutover_banned_patterns.py
- **Verification:** Gate PASSES green (11/11); would-red proof via the non-vacuity injection tests.
- **Committed in:** b2623ffa (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking/scope reconciliation).
**Impact on plan:** The deviation resolves a plan-text vs. guardrail/CONTEXT conflict in favor of the authoritative source-only scope. Without it the gate would false-red on the sanctioned e2e alias. No scope creep — the deliverable (a green, non-vacuous ratchet banning the five tokens, allow-listing the survivors) is exactly as specified.

## Issues Encountered
- **Non-vacuity TS fixture over-escaped a regex literal.** The initial `page.routeWebSocket(/\/ws\/chat/)` fixture contained `\/ws\/chat` (escaped slashes), not the contiguous `/ws/chat` substring, so the `/ws/chat` scanner correctly did not match it — this is correct scanner behavior (a real route string is unescaped). Fixed the fixture to inject an unescaped `const url = base + "/ws/chat"` string; gate went green (11/11).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The CI ratchet is live and green; the hard-cutoff is now machine-enforced against silent regression.
- No blockers. Remaining Phase 44 work (44-11/44-12 — W6 Part-B live-smoke automation) is independent of this gate.

## Self-Check: PASSED
- `backend/tests/agents/test_sse_cutover_banned_patterns.py` exists on disk (verified).
- Commits `b2623ffa` (Task 1) and `30bde14d` (Task 2) present in git log (verified).
- Gate: 11 passed. Characterization: 10 passed. lint-imports: 4 kept / 0 broken.

---
*Phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto*
*Completed: 2026-07-16*
