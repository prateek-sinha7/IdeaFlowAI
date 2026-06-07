---
phase: 05-typed-artifacts-persistence-ownership-1b
plan: 01
subsystem: engine
tags: [artifacts, dataclass, lineage, content-hash, sha256, kernel-purity, typed-routing]

# Dependency graph
requires:
  - phase: 00-characterization
    provides: stdlib-only @dataclass discipline (agents/execution_engine/context.py) + import-linter kernel scaffold
provides:
  - "agents/artifacts/ package — kernel-importable typed artifact substrate"
  - "ArtifactRef dataclass (plan §6:454-466 field set + D-01 inline content, sha256 content-addressed)"
  - "ArtifactGraph — per-run in-memory registry: hashing + per-(run,kind) versioning, typed consumes routing, in-memory lineage walk"
  - "ARTIFACT_KINDS closed snake_case vocabulary"
affects: [05-02, 05-03, 05-04, 05-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Kernel-importable typed data: stdlib-only (hashlib/uuid/dataclasses), no app.models/app.api"
    - "Content-addressing via hashlib.sha256(content.encode('utf-8')).hexdigest() (D-01)"
    - "Typed produces/consumes routing by ArtifactRef.kind equality (never substring match)"
    - "In-memory lineage walk over parents/derived_from (no DB recursive CTE; cycle-safe)"

key-files:
  created:
    - backend/agents/artifacts/graph.py
    - backend/agents/artifacts/__init__.py
    - backend/tests/agents/test_artifact_graph.py
  modified: []

key-decisions:
  - "Package path agents/artifacts/ per D-02 (controlling over SPEC ART-01 prose agents/execution_engine/artifacts/)"
  - "ArtifactRef.visibility default 'private' per plan §6:465 (store helper read filter widens reads to workspace/public in 05-03)"
  - "Graph owns hashing + versioning so callers cannot diverge the typed contract"
  - "version = 1 + count of prior refs with same (run_id, kind)"
  - "Graph kept purely in-memory: no RuntimeEnvironment/Workspace field, no dedup-on-hash, no retention sweep (deferred P9/P12)"

patterns-established:
  - "Kernel-pure typed substrate: agents/artifacts/ imports stdlib only so ExecutionContext (05-04) can import it without dragging in app.models"
  - "Typed-routing contract: consumed_for(consumes) filters by kind equality, the engine maps AGENT.md strings to kinds in 05-04"

requirements-completed: [ART-01, ART-02, ART-03, ART-04]

# Metrics
duration: 2min
completed: 2026-06-07
---

# Phase 5 Plan 01: Typed Artifact Substrate (agents/artifacts) Summary

**Kernel-importable `ArtifactGraph` + `ArtifactRef` dataclass — sha256 content-addressed typed artifacts with per-(run,kind) versioning, typed `consumes` routing, and an in-memory lineage walk, replacing the untyped `accumulated_outputs` handoff (ART-01..04).**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-06-07T20:01:06Z
- **Completed:** 2026-06-07T20:03:06Z
- **Tasks:** 2
- **Files modified:** 3 (all created)

## Accomplishments
- Created the `agents/artifacts/` package: the typed data substrate that future phases build against (interface-first ordering).
- `ArtifactRef` dataclass with the full plan §6:454-466 lineage field set + the D-01 inline `content` field, content-addressed by sha256.
- `ArtifactGraph` per-run registry owning hashing + versioning, with typed `consumes` routing (`consumed_for`) and a cycle-safe in-memory lineage walk (`lineage`/`tree`).
- Wave 0 unit suite (`test_artifact_graph.py`, 7 tests) covering ART-01 (lineage), ART-02 (provenance + hash + version), ART-03 (typed routing + derived_from), ART-04 (retention default + overrides) — all GREEN.
- Kernel purity preserved: `lint-imports` exits 0 (3 contracts kept, 0 broken); zero `app.models`/`app.api` imports.

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1: Write failing ART-01/02/03/04 unit tests** - `8b45ccd` (test) — RED
2. **Task 2: Implement agents/artifacts/graph.py to GREEN** - `e780f49` (feat) — GREEN

_No REFACTOR commit: the GREEN implementation was already clean (no duplication, single responsibility per method)._

## Files Created/Modified
- `backend/agents/artifacts/graph.py` - `ArtifactRef` dataclass + `ArtifactGraph` (write_ref/get/list_by_kind/consumed_for/lineage/tree) + `ARTIFACT_KINDS` vocabulary. Stdlib-only.
- `backend/agents/artifacts/__init__.py` - Package exports for `ArtifactGraph`, `ArtifactRef`, `ARTIFACT_KINDS`.
- `backend/tests/agents/test_artifact_graph.py` - 7 unit tests pinning the typed contract; kernel-pure (no `app.*` import).

## Decisions Made
- **Package path `agents/artifacts/`** per D-02 (controlling), not the SPEC ART-01 prose `agents/execution_engine/artifacts/`.
- **`visibility` default `"private"`** per plan §6:465 — consistent with the store helper's default-deny read filter that widens reads to `workspace`/`public` in 05-03.
- **Graph owns hashing + versioning** (callers pass `content`/`kind`, not a pre-computed hash/version) so the typed contract cannot diverge.
- **`lineage()` skips non-local ancestor ids** (e.g. a parent-run source ref id supplied via `derived_from` in a revision) — only locally-resolvable refs are returned; the `derived_from` link itself is still exposed on the ref.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The initial `Write` of `graph.py` introduced two stray Unicode replacement characters inside box-drawing comment dividers (cosmetic only; file still parsed). Caught by a `grep` purity scan and fixed via two `Edit`s before committing. No functional impact.

## TDD Gate Compliance
- RED gate present: `8b45ccd` `test(tests): add failing ArtifactGraph unit tests (ART-01..04)` — verified failing with `ModuleNotFoundError: No module named 'agents.artifacts'`.
- GREEN gate present: `e780f49` `feat(engine): ...` — all 7 tests pass.
- REFACTOR gate: not required (no cleanup needed).

## Known Stubs
None. The graph is intentionally in-memory with no persistence (that is 05-03's store helper, not a stub); the plan explicitly defers `RuntimeEnvironment`/`Workspace`, dedup-on-hash, and retention sweep (P9/P12).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The typed contract is fixed: 05-03 (store helper) and 05-04 (engine dual-write/read-migration) can build against `ArtifactRef`'s field set and `ArtifactGraph`'s methods without re-discovering shape.
- 05-04 will add `ExecutionContext.artifacts: ArtifactGraph` (`field(default_factory=ArtifactGraph)`) — the kernel-pure import keeps `context.py` green.
- No blockers.

## Self-Check: PASSED
- FOUND: backend/agents/artifacts/graph.py
- FOUND: backend/agents/artifacts/__init__.py
- FOUND: backend/tests/agents/test_artifact_graph.py
- FOUND: commit 8b45ccd (RED)
- FOUND: commit e780f49 (GREEN)

---
*Phase: 05-typed-artifacts-persistence-ownership-1b*
*Completed: 2026-06-07*
