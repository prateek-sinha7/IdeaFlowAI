---
phase: 19-prompt-and-deliverable-adherence
plan: 01
subsystem: agents
tags: [prompts, app_builder, contract-fidelity, getDatabase, regression-pin, INV-3]

requires:
  - phase: 15-live-pass-prompt-contract-closure
    provides: the test_prompt_contracts.py pin layer + the frozen-frontmatter test the new pin sits beside
  - phase: 13-03
    provides: the shared-literal contract pattern (single /api/v1 literal across producer/consumer prompts)
provides:
  - Shared canonical DB-accessor literal `getDatabase` threaded through the app_builder producer (app-code-generator) + consumer (app-test-implementation) prompt bodies
  - Consumer Contract-fidelity rule extended to explicitly cover the Jest/Vitest global-setup file (tests/setup.ts / globalSetup)
  - Offline acceptance-grep pin (test_getdatabase_accessor_contract_shared) that fails if either prompt side reverts
affects: [app_builder, prompt-contract, live-pass-iss-006-reconfirm]

tech-stack:
  added: []
  patterns:
    - "13-03 shared-literal cross-agent contract: one canonical literal (`getDatabase`) authored in both producer + consumer prompt bodies, pinned by a grep test that fails on either-side revert"

key-files:
  created: []
  modified:
    - backend/agents/prompts/app-code-generator/AGENT.md
    - backend/agents/prompts/app-test-implementation/AGENT.md
    - backend/tests/agents/test_prompt_contracts.py

key-decisions:
  - "Body-only AGENT.md edits; frontmatter UNTOUCHED (proven by the existing test_contract_agents_frontmatter_frozen pin staying green)."
  - "Producer states the accessor is a single canonical NAMED export `getDatabase` (never default/getDb) at src/db/index.ts; consumer names the global-setup file explicitly — closing the per-story-symbol scope gap that was the ISS-006 root cause."
  - "Proportionate fix now = shared prompt contract + grep pin; the tsc/code_typecheck validator is deferred to N3 (needs exec + a TS toolchain), per CONTEXT."

patterns-established:
  - "Cross-agent prompt contract pinned by a load_agent_spec(id).prompt_body grep with explicit per-side assert messages, fault-injection-proven in both revert directions."

requirements-completed: [ISS-006]

# Metrics
duration: ~5 min
completed: 2026-06-13
---

# Phase 19 Plan 01: ISS-006 Shared `getDatabase` DB-Accessor Contract Summary

**Threaded the canonical named-export literal `getDatabase` through the app_builder producer + consumer prompt bodies (incl. the Jest/Vitest global-setup contract) and pinned it with an offline acceptance-grep that fails on either-side revert — closing the cross-agent TS2305 drift (`tests/setup.ts` imported `getDb` while the impl exported `getDatabase`).**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-13T16:32:00Z
- **Completed:** 2026-06-13T16:37:40Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Producer `app-code-generator/AGENT.md`: added a MANDATORY DB ACCESSOR CONTRACT — the DB module exposes its accessor as the single canonical NAMED export `getDatabase` (never a default, never `getDb`/`getConnection`), at the canonical path `src/db/index.ts`, with a greppable inline example.
- Consumer `app-test-implementation/AGENT.md`: extended the "Contract fidelity" rule to explicitly cover test-infrastructure files — the Jest/Vitest global setup (`tests/setup.ts` / configured `globalSetup`) MUST import the DB accessor by the EXACT canonical named export `getDatabase`; never invent `getDb`/`getConnection`/a default import (a TS2305 build break).
- Added `test_getdatabase_accessor_contract_shared` to `test_prompt_contracts.py` asserting on `load_agent_spec(id).prompt_body` for BOTH agents; fault-injected both revert directions and confirmed each trips an explicit assert (regression-pin property proven, not assumed).
- INV-3 PROVEN: all 5 characterization goldens stay byte/event-identical; lint-imports 4/0; zero migrations.

## Task Commits

Each task was committed atomically:

1. **Task 1: Thread the canonical `getDatabase` literal through producer + consumer bodies** - `d98cc421` (feat)
2. **Task 2: Add the offline acceptance-grep pin + prove INV-3 parity** - `58f2ae09` (test)

**Plan metadata:** (this SUMMARY + STATE/ROADMAP) committed separately.

## Files Created/Modified
- `backend/agents/prompts/app-code-generator/AGENT.md` - Added the MANDATORY DB ACCESSOR CONTRACT block (named-export `getDatabase` at `src/db/index.ts`); frontmatter untouched.
- `backend/agents/prompts/app-test-implementation/AGENT.md` - Extended the Contract-fidelity rule to name the global-setup file and demand the exact `getDatabase` named import; frontmatter untouched.
- `backend/tests/agents/test_prompt_contracts.py` - New `test_getdatabase_accessor_contract_shared` pin (producer + consumer literal + global-setup token).

## Decisions Made
- Body-only edits on both AGENT.md files; frontmatter is frozen by the existing `test_contract_agents_frontmatter_frozen` pin — verified by `git diff` (no `---`-block lines changed) and by the full `test_prompt_contracts.py` (12 passed, including the freeze test) + loader schema-validation (19 passed).
- Used `src/db/index.ts` as the producer's canonical-path example (matches D-13-03-a: default app_builder stack is Node.js/TypeScript) while keeping the literal `getDatabase` as the single source of truth across both sides.

## Deviations from Plan

None - plan executed exactly as written.

## Verification Evidence

- **Task 1 automated verify:** producer + consumer bodies both contain `getDatabase`; consumer contains `setup.ts`; producer has named-export + not-default phrasing → `OK`.
- **Frontmatter integrity:** `git diff` showed no frontmatter (`---`-block) lines changed → `FRONTMATTER CLEAN`; `test_contract_agents_frontmatter_frozen` green; loader schema-validation 19 passed.
- **Task 2 pin:** `python3.11 -m pytest tests/agents/test_prompt_contracts.py -k getdatabase` → 1 passed; full file → 12 passed.
- **Fault-injection (regression-pin property):** monkeypatched the loader to strip the literal from the consumer (→ first/third assert tripped) and from the producer (→ producer assert tripped) — both revert directions caught.
- **INV-3 parity (PROVEN, not assumed):** the 5 characterization goldens (prototype / od_prototype / prototype_revision / od_ppt / app_builder) ran with NO `SNAPSHOT_UPDATE` → 10 tests passed, byte/event-identical (the scripted model never reads prompt bodies).
- **Import purity:** `/opt/homebrew/bin/lint-imports` → 4 contracts kept / 0 broken.
- **Additive-only:** `git status` shows no alembic/migration file; diff scope = the 2 AGENT.md bodies + `test_prompt_contracts.py` only.

## Known Stubs
None - both prompt bodies carry the live contract text; no placeholder/empty-value flows introduced.

## Issues Encountered
- The plan's `tests/agents/characterization` path collects 0 items — the goldens live in `tests/agents/test_characterization_*.py` (5 files). Ran those 5 explicitly with no snapshot update (10 tests green). No behavior change, just the correct invocation path.

## Next Phase Readiness
- ISS-006 offline gate is closed (shared contract + revert-failing pin, INV-3-safe). Ready for Plan 19-02 (ISS-005 `api_prefix` event-free post_step validator).

## Deferred (carried from PLAN, not blocking)
- LIVE re-confirm on `default` Bedrock: a real Haiku app_builder run produces a Jest global-setup importing `getDatabase` with no TS2305 (no `getDb` mismatch) — runs in the consolidated live + Playwright pass, NOT a phase-exit blocker (the offline grep pin is the gate).
- A `tsc --noEmit` / `code_typecheck` / `symbol_contract` validator — N3/v2 era (needs exec + a TS toolchain).

## Self-Check: PASSED

- Files verified on disk: 19-01-SUMMARY.md, both AGENT.md bodies, test_prompt_contracts.py — all FOUND.
- Commits reachable: `d98cc421` (feat task 1), `58f2ae09` (test task 2) — both FOUND.

---
*Phase: 19-prompt-and-deliverable-adherence*
*Completed: 2026-06-13*
