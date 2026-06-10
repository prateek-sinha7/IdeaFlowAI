---
phase: 10-safe-local-exec-gated-on-n3-4b
plan: 05
subsystem: review-debt
tags: [debt, parity, in-01, in-02, in-03, n3-resolution, repo-diff, migration-ledger, mcp-04, exec-01, exec-02]

# Dependency graph
requires:
  - phase: 10-01
    provides: hardened argv/no-shell exec_command (the IN-02 fix this plan ratchets as a ledger row)
  - phase: 10-04
    provides: code validators + EXEC-02 proof — the last behavior plan before this debt/parity closeout
provides:
  - "IN-01: MCP-04 sign-off documented near the slack_post user_allowed=True gating (post-only scope, same gate/audit path; no behavior change)"
  - "IN-03: repo_diff._split_per_file keys an unparseable diff --git header block under a synthetic __unparsed_N__ instead of silently dropping it"
  - "IN-02: shell=True closure recorded as a migration-ledger ☑ ratchet row (grep no-shell-exec token = 0 over backend/), enforced by test_migration_ledger.py"
  - "N3 threat-model blocker flipped to RESOLVED in STATE.md + PROJECT.md citing 10-SPEC.md as the decision record"
  - "Phase 10 parity gate proven: 5 characterization snapshots byte/event-identical, lint-imports 4/0, banned-pattern + migration-ledger green"
affects: [phase-10-complete, sc-001, exec-01, exec-02]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Silent-drop data-integrity guard: when _flush has current_lines but current_path is None, assign a per-call incrementing synthetic key (__unparsed_N__) so no changed file is lost; normal parseable path stays byte-identical"
    - "Subsumed-fix ratchet: a fix landed in an earlier plan (10-01 argv/no-shell) is permanently locked by a migration-ledger ☑ grep row when the banned-pattern test does not already scan the token (RESEARCH A5)"
    - "SPEC-as-decision-record: a phase SPEC.md (10-SPEC.md, 9 locked requirements) IS the N3 decision artifact cited when flipping the open-decision blocker to resolved"

key-files:
  created: []
  modified:
    - backend/agents/capabilities/deliverables/repo_diff.py
    - backend/agents/capabilities/mcp_servers/catalog.py
    - backend/tests/agents/test_repo_diff.py
    - backend/tests/agents/test_migration_ledger.py
    - specs/003-workflow-engine-decoupling/migration-ledger.md
    - .planning/STATE.md
    - .planning/PROJECT.md

key-decisions:
  - "IN-02 is subsumed by the 10-01 argv/no-shell exec_command; this plan does NOT re-fix it — it records the closure as a migration-ledger ☑ grep ratchet (the existing banned-pattern test does not scan shell=True, RESEARCH A5) so the surface can never reappear over backend/"
  - "IN-01 is comment/docstring-only — exposed_tools and user_allowed for slack are unchanged (no behavior change); post_message is the ONE user-grantable WRITE, accepted because the scope is post-only and rides the same gate/audit path as every MCP call"
  - "N3 is resolved by citing 10-SPEC.md as the decision record rather than authoring a separate ADR — the SPEC's 9 locked requirements ARE the N3 decision, shipped across 10-01..10-05"

patterns-established:
  - "repo-diff synthetic-key fallback: data-integrity boundary where an unparseable header must retain its block rather than drop it"

requirements-completed: [EXEC-01, EXEC-02]

# Metrics
duration: ~18min
completed: 2026-06-10
---

# Phase 10 Plan 05: Review-Trio Closure + N3 Resolution + Parity Gate Summary

**Closed the Phase 9 review trio (IN-01 MCP-04 sign-off, IN-02 shell=True ledger ratchet, IN-03 repo_diff synthetic-key fallback), flipped the N3 threat-model blocker to RESOLVED citing 10-SPEC.md, and proved the Phase 10 parity gate — completing the safe-local-exec phase (5/5 plans) with zero engine edits.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-10
- **Completed:** 2026-06-10
- **Tasks:** 2 (one TDD debt-closure task + one blocking-human verification checkpoint)
- **Files modified:** 7 (3 src/test, 1 ledger-test sync, 1 ledger, 2 planning docs)

## Accomplishments

- **IN-03 (data integrity):** `repo_diff._split_per_file._flush` now keys a block under a synthetic `__unparsed_N__` when `current_lines` exist but `current_path is None` (an unparseable / quoted / rename `diff --git` header). The normal parseable path is byte-identical; multiple unparseable blocks get distinct keys (a per-call incrementing `idx`) so none collide or overwrite. Proven by 4 RED→GREEN unit tests (quoted header, rename header, normal-diff parity, multiple-unparseable distinctness).
- **IN-01 (write-scope sign-off):** an MCP-04 sign-off docstring landed near the `SlackMcpServer` `user_allowed=True` gating in `catalog.py` — documents that `post_message` is the one user-grantable WRITE on the user palette, accepted because the scope is post-only and rides the same gate/audit path as every MCP call. Comment-only: `exposed_tools` and `user_allowed` are unchanged (no behavior change).
- **IN-02 (ratchet):** the `shell=True` exec surface — already closed by the 10-01 argv/no-shell `exec_command` — is recorded as a migration-ledger ☑ grep ratchet row whose deletion gate greps the no-shell-exec token to 0 over `backend/`. `test_migration_ledger.py` `_REQUIRED_ITEMS`/expected were synced in lockstep so the parse gate stays green and the row is enforced (grep `shell=True` over `backend/app/agents/runtime/` + `backend/agents/` = 0).
- **N3 resolution:** the STATE.md N3 ⚠️ blocker row flipped to RESOLVED and the IN-01/02/03 pending-todo block cleared (all three closed in Phase 10); PROJECT.md dropped N3 from the open-decisions row into a resolved row and marked the safe-local-exec roadmap line done — all citing 10-SPEC.md as the N3 decision record (9 locked requirements shipped across 10-01..10-05).
- **Phase parity gate (verified at the approved checkpoint):** the orchestrator independently re-verified before approval — `shell=True` grep = 0 over backend runtime+agents; targeted parity suite (characterization + migration-ledger + banned-patterns) 44 passed / 5 skipped; lint-imports 4 kept / 0 broken; N3 blocker flipped to RESOLVED in STATE.md citing 10-SPEC.md.

## Task Commits

| Task | Name | Commit | Type |
| ---- | ---- | ------ | ---- |
| 1 (RED) | IN-03 failing synthetic-key tests for repo_diff | `2285941` | test |
| 1 (GREEN) | Close Phase 9 review trio (IN-01/IN-02/IN-03) | `fc3efff` | feat |
| verify-prep | Flip N3 resolved + clear IN-01/02/03 pending-todo (STATE.md/PROJECT.md) | `0fcbc84` | docs |
| 2 (checkpoint closeout) | SUMMARY + STATE + ROADMAP (checkpoint approved) | _this commit_ | docs |

## Files Created/Modified

- `backend/agents/capabilities/deliverables/repo_diff.py` — IN-03 synthetic-key fallback in `_split_per_file._flush` (assigns `__unparsed_N__` when `current_path is None` but `current_lines` exist; per-call `idx` counter).
- `backend/agents/capabilities/mcp_servers/catalog.py` — IN-01 MCP-04 sign-off docstring near the slack `user_allowed=True` line (comment-only; `exposed_tools`/`user_allowed` unchanged).
- `backend/tests/agents/test_repo_diff.py` — 4 IN-03 test cases (quoted/rename headers survive under synthetic keys; normal diffs key by path; multiple unparseable blocks get distinct keys).
- `backend/tests/agents/test_migration_ledger.py` — `_REQUIRED_ITEMS`/expected synced for the new IN-02 ratchet row (keeps the parse gate green).
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — IN-02 ☑ no-shell-exec ratchet row (deletion gate greps the shell-exec token → 0 over backend/).
- `.planning/STATE.md` — N3 ⚠️ blocker → RESOLVED + IN-01/02/03 pending-todo cleared (citing 10-SPEC.md).
- `.planning/PROJECT.md` — N3 dropped from open decisions into a resolved row; safe-local-exec roadmap line marked done; until-N3 lines annotated resolved Phase 10.

## Decisions Made

- **IN-02 is recorded, not re-fixed.** The `shell=True` exec surface was already eliminated by 10-01's argv/no-shell `exec_command`. Because the existing banned-pattern test does not scan `shell=True` (RESEARCH A5), this plan records the closure as a permanent migration-ledger ☑ grep ratchet rather than touching runtime code — the row is the durable guard against reintroduction.
- **IN-01 is comment-only.** Documenting the MCP-04 sign-off must not widen the slack write scope: `exposed_tools` and `user_allowed=True` are unchanged. The docstring captures the accepted post-only scope + shared gate/audit path so a future reader does not re-litigate or widen it.
- **N3 resolved via 10-SPEC.md.** 10-SPEC.md's 9 locked requirements ARE the N3 decision record; the planning-doc flips cite it rather than authoring a parallel ADR.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] test_migration_ledger.py `_REQUIRED_ITEMS`/expected sync for the new IN-02 ratchet row**
- **Found during:** Task 1 (GREEN — landing the IN-02 ledger row)
- **Issue:** Adding the new ☑ `shell=True` ratchet row to `migration-ledger.md` changed the ledger's required-item set; `test_migration_ledger.py` parses the ledger against `_REQUIRED_ITEMS` and an expected count, so the new row would have failed the parse gate without a corresponding test update.
- **Fix:** Synced `_REQUIRED_ITEMS` + the expected count in `test_migration_ledger.py` in lockstep with the new ledger row, keeping the parse gate green and enforcing the new grep ratchet.
- **Files modified:** `backend/tests/agents/test_migration_ledger.py`
- **Verification:** `test_migration_ledger.py` green; grep `shell=True` over `backend/app/agents/runtime/` + `backend/agents/` = 0.
- **Committed in:** `fc3efff` (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** The sync is a mechanical test-ledger lockstep (the established ratchet pattern — L16/F4/F5/R1 precedent); no scope creep, no behavior change. No engine edits — the git diff over `backend/agents/execution_engine/` is clean for this plan (SC-001 discipline held).

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None — no external service configuration, zero external packages (a parser fix + a comment + a ledger row + planning-doc edits).

## Checkpoint Outcome

Task 2 was a `checkpoint:human-verify` (gate=blocking). Per `human_verify_mode: end-of-phase`, the executor applied the planning-doc flips (commit `0fcbc84`) and ran the parity gate; the orchestrator independently re-verified (`shell=True` grep = 0; parity suite 44 passed / 5 skipped; lint-imports 4/0; N3 RESOLVED) and **APPROVED**. All 14 SPEC acceptance criteria map to green tests/greps across 10-01..10-05.

## Next Phase Readiness

- **Phase 10 = 5/5 plans complete.** EXEC-01 + EXEC-02 closed; the Phase 9 review trio is closed; N3 is resolved.
- The safe-local-exec stack is ready for phase verification (`/gsd-verify-work 10`) and security review.
- Phase 11 (Engine-Owned Fan-Out + Merge) is the next phase; it depends on Phase 9 and is unblocked.

## Threat Flags

None — the modified surface (a parser fallback + a comment + a ledger row + planning-doc edits) introduces no new endpoint/auth/file/schema surface; fully covered by the plan's threat register (T-10-05-01..SC). T-10-05-SC (npm/pip/cargo): zero external packages — N/A.

## Known Stubs

None — the IN-03 fallback wires a real synthetic key into the live `_split_per_file` output (not a placeholder); the IN-01 doc is intentionally comment-only by design (no data path).

## Self-Check: PASSED

- Modified files verified on disk (repo_diff.py, catalog.py, test_repo_diff.py, test_migration_ledger.py, migration-ledger.md, STATE.md, PROJECT.md).
- Prior task commits verified in git history: `2285941` (test), `fc3efff` (feat), `0fcbc84` (docs).

---
*Phase: 10-safe-local-exec-gated-on-n3-4b*
*Completed: 2026-06-10*
