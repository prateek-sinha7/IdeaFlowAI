---
phase: 01-safety-net-deletion-guard-0a
plan: 04
subsystem: testing
tags: [import-linter, vulture, gitlab-ci, banned-patterns, ratchet, deepagents, INV-13, hexagonal]

# Dependency graph
requires:
  - phase: 01-01
    provides: characterization tests (test_characterization_prototype/od_prototype)
  - phase: 01-02
    provides: characterization tests (test_characterization_prototype_revision/od_ppt/app_builder) + golden fixtures
  - phase: 01-03
    provides: migration-ledger.md + test_migration_ledger.py
provides:
  - import-linter pinned (2.11) + [tool.importlinter] kernel-import-boundary green scaffold (D-12)
  - vulture pinned (2.16) + [tool.vulture] allow-listed dead-code scan, green on current tree
  - test_banned_patterns.py — INV-13/R15 ratchet (hand-rolled deep agents blocked, single sanctioned create_deep_agent allow-list, non-vacuous negative test, INV-1 warn-only)
  - .gitlab-ci.yml — lint-imports + vulture in backend:lint; offline backend:characterization job running all four Phase-1 gate families
affects: [02-execution-context, 07-engine-extraction, 08-final-cleanup]

# Tech tracking
tech-stack:
  added: [import-linter==2.11, vulture==2.16]
  patterns:
    - "import-linter green scaffold (non-vacuous, tighten-don't-rewrite) for hexagonal import boundaries"
    - "pytest-based banned-pattern ratchet with statement-anchored regexes + injected-fixture non-vacuity proof"
    - "dedicated offline CI job to run tests/agents (previously never run in CI)"

key-files:
  created:
    - backend/tests/agents/test_banned_patterns.py
  modified:
    - backend/requirements-dev.txt
    - backend/pyproject.toml
    - .gitlab-ci.yml

key-decisions:
  - "import-linter contract type = forbidden, anchored on the kernel→web-layer boundary (engine.py must not import app.api) — every agents.* subpackage is transitively reachable from engine via factory, so any agents.* forbidden target would be BROKEN today; app.api is a real, already-respected dependency-inversion boundary that keeps the scaffold both green AND non-vacuous"
  - "root_packages = [agents, app] (widened from agents-only) so the app.api boundary is analyzable"
  - "vulture allow-list = pyproject ignore_names + ignore_decorators (in-repo config, not CLI flags) so the bare `vulture app/ agents/` CI invocation is green with zero runtime-code edits"
  - "banned-pattern allow-list is the SINGLE file app/agents/deep_agent_runner.py; no legacy deep_agent.py entry (verified absent post-002 migration)"
  - "INV-1 (if pipeline_type == / spec.id ==) is a WARN-ONLY soft ratchet (10 matches, ceiling 16) in Phase 1; hard-fail deferred to Phase 7 (D-15)"

patterns-established:
  - "Green scaffold gate: a CI contract that holds on the current tree, is non-vacuous, and is shaped so later phases tighten by addition not rewrite"
  - "Non-vacuity proof for grep-style gates: inject a known-bad fixture into tmp_path and assert the same scanner fires"

requirements-completed: [SAFE-05, SAFE-06, SAFE-07]

# Metrics
duration: 9min
completed: 2026-06-06
---

# Phase 1 Plan 04: Arm Static Gates + Wire CI Summary

**import-linter + vulture pinned & configured green, an INV-13 banned-pattern ratchet (non-vacuous, single-file allow-list), and a new offline GitLab `backend:characterization` job that finally runs all four Phase-1 gate families in CI.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-06-06T22:02:33Z
- **Completed:** 2026-06-06T22:11:01Z
- **Tasks:** 3
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Pinned `import-linter==2.11` + `vulture==2.16` (exact, verified against PyPI) and configured both in `pyproject.toml`; `cd backend && lint-imports` and `vulture app/ agents/` both exit 0 on the current tree.
- Authored `test_banned_patterns.py` — blocks hand-rolled deep agents (INV-13/R15), allow-lists the ONE sanctioned `create_deep_agent` site, proves itself non-vacuous via an injected `class DeepAgent` fixture, and treats INV-1 as a warn-only soft ratchet. 8 tests pass.
- Wired all gates into `.gitlab-ci.yml`: `backend:lint` now installs `requirements-dev.txt` and runs `lint-imports` + `vulture`; a new offline `backend:characterization` job runs the 5 characterization tests + migration-ledger + banned-pattern tests. Closes the D-16 false-green gap (tests/agents was never run in CI).
- Zero runtime code modified — config + test + CI only.

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin + configure import-linter & vulture** - `35f8107` (chore)
2. **Task 2: Create test_banned_patterns.py (INV-13/R15)** - `cd28d6a` (test)
3. **Task 3: Wire all gates into .gitlab-ci.yml** - `2accdb5` (chore)

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified
- `backend/tests/agents/test_banned_patterns.py` (created) - INV-13/R15 banned-pattern ratchet: 5 hard-ban scanners, 1 minimal allow-list, 2 non-vacuity/false-positive guards, 1 INV-1 warn-only soft ratchet.
- `backend/requirements-dev.txt` (modified) - added pinned `import-linter==2.11` + `vulture==2.16` with rationale blocks.
- `backend/pyproject.toml` (modified) - added `[tool.importlinter]` (forbidden contract: kernel must not import `app.api`, `root_packages=[agents,app]`) + `[tool.vulture]` (allow-listed dead-code scan).
- `.gitlab-ci.yml` (modified) - extended `backend:lint` (dev deps + lint-imports + vulture); added offline `backend:characterization` test job.

## Decisions Made

- **import-linter contract anchor (D-12 fallback applied):** The intended final contract ("kernel must not import `agents.factory`/`engine` internals") cannot be green today because the kernel is still the monolithic `engine.py`. Worse, every `agents.*` subpackage is *transitively* reachable from `engine.py` (engine → factory → ~everything), so a `forbidden` rule naming any `agents.*` target is BROKEN on the current tree. I anchored the scaffold on the kernel→web-layer boundary instead: `agents.execution_engine.engine` must not import `app.api` (the API calls the engine, never the reverse — verified engine reaches `app.agents/core/models/services` but never `app.api`). This is a REAL, already-respected dependency-inversion boundary, so the contract is **non-vacuous yet green**. Required widening to `root_packages = ["agents", "app"]`. The intended Phase 7/8 final form is documented inline so the tighten is additive.
- **import-linter empty-`forbidden_modules` portability:** Verified 2.11 *does* accept an empty list (reports KEPT), but I did not use it — an empty list is vacuous. The `app.api` boundary is the non-vacuous choice.
- **vulture allow-list via pyproject (not CLI):** Used `ignore_names` + `ignore_decorators` + `exclude` in `[tool.vulture]` so the bare `vulture app/ agents/` invocation (the exact CI command) is green without touching runtime code. The 9 findings were all verified false positives: `TYPE_CHECKING` imports used only in string annotations (`ModelRequest`/`ModelResponse`/`BaseChatModel`) and `@tool` stub-function params (`stated_goal` etc.).
- **Banned-pattern allow-list is a single file** (`app/agents/deep_agent_runner.py`), no legacy `deep_agent.py` entry — confirmed absent.
- **Characterization job uses explicit file names** rather than a `test_characterization_*.py` glob, for deterministic CI collection; the names still contain the `test_characterization_` substring the verify checks.

## Grounding verification (per plan <output>)
- **No legacy `class DeepAgent` / `def deep_agent` / `app/agents/deep_agent.py`:** confirmed absent on the current tree (removed in 002 migration) — so NO legacy allow-list entry was added.
- **Pinned versions:** `import-linter==2.11`, `vulture==2.16` (latest stable, verified via PyPI JSON API at author time).
- **import-linter contract type chosen:** `forbidden` (kernel `agents.execution_engine.engine` ✗→ `app.api`), green scaffold; intended final form (`source=agents.kernel`, `forbidden=[agents.factory, agents.execution_engine.engine, app.api]`) documented inline for additive Phase 7/8 tighten.
- **vulture allow-list mechanism:** in-repo `[tool.vulture]` `ignore_names`/`ignore_decorators`/`exclude`.
- **Final CI jobs:** `backend:lint` (ruff + lint-imports + vulture) and new offline `backend:characterization` (5 characterization tests + migration-ledger + banned-pattern). `backend:test`/frontend/deploy jobs unchanged.

## Deviations from Plan

None - plan executed exactly as written. The import-linter contract target was selected at execution time within the explicit D-12 discretion the plan grants (the plan anticipated the empty-`forbidden_modules` / layers / doc-only fallback; the actual current tree required choosing a real non-vacuous boundary, and `app.api` is that boundary). This is the planned discretion, not a deviation.

## Issues Encountered
- **import-linter `forbidden` rules are transitive.** First attempt forbade `agents.prototype`, then `agents.workflow_memory` — both BROKEN because engine reaches them transitively via factory. Resolved by anchoring on `app.api`, which engine genuinely never reaches (verified with grimp). Required `root_packages = ["agents","app"]`.
- **Non-vacuity test path bug.** The injected-fixture test scanned a `tmp_path` outside the backend root; `_rel()` raised `ValueError` on `relative_to`. Fixed `_rel()` to fall back to the absolute posix path for out-of-root files (Rule 1 auto-fix, within the same uncommitted task — committed in `cd28d6a`).

## User Setup Required
None - no external service configuration required. (CI runners install the pinned dev deps automatically.)

## Next Phase Readiness
- All four Phase-1 gate families (characterization, migration-ledger, banned-pattern, static import/dead-code) are now armed AND executed in CI — the safety net is real, not false-green. Phase 2 (ExecutionContext / 0B) can refactor against a live ratchet.
- Phase 7/8 tighten path is pre-documented: promote the import-linter scaffold to its final form, and flip the INV-1 warn to a hard-fail when L7 is deleted.
- No blockers.

## Self-Check: PASSED

---
*Phase: 01-safety-net-deletion-guard-0a*
*Completed: 2026-06-06*
