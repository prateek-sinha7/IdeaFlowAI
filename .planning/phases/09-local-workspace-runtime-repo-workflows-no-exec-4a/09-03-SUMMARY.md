---
phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
plan: 03
subsystem: agents
tags: [repo-context, tree-sitter, repo-inventory, context-pack, capability-registry, import-linter, offline-grammars, hexagonal-ports]

# Dependency graph
requires:
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    plan: 01
    provides: "RuntimeEnvironment/Workspace ports + LocalSandboxRuntime/LocalWorkspace (read/write/search/clone over a cloned repo) + the reusable local_git_fixture"
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    plan: 02
    provides: "the one Workspace abstraction serving both has_git=False artifact + has_git=True repo paths"
  - phase: 08-capabilities-runtime-frontend-1d
    provides: "self-registering CapabilityRegistry (@register / discover() / _KNOWN drift guard) + ScopedStore.write_ref lineage"
  - phase: 05-typed-artifacts-persistence-ownership-1b
    provides: "ArtifactGraph + ArtifactRef typed substrate (repo_inventory/context_pack are pre-declared ARTIFACT_KINDS)"
provides:
  - "app/agents/repo_index/index.py — @register('repo_index','tree_sitter'): one seam exposing search() (grep/glob, DEFAULT) + symbol_query() (file+line+kind, on build); tree-sitter import-isolated app-side"
  - "agents/capabilities/repo_inventory/inventory.py — @register('repo_inventory','default'): kernel-side stdlib file tree + lang stats + deps; .gitignore/.flowinignore/binary-skip/size-cap; lineage-tracked"
  - "agents/capabilities/context_pack/pack.py — @register('context_pack','default') + context_selector(): targeted per-task subset (target + neighbors), excludes unrelated; lineage-tracked"
  - "agents/capabilities/context_providers/repo.py — @register('context_provider','repo'): surfaces the ContextPack; cross-owner assert_owns PermissionError propagates (L16)"
  - "RepoSpec.index opt-in flag (compiler records only, INV-5) + REPO_INDEX_FILE_THRESHOLD (N6) constant"
  - "the tree-sitter + per-language grammar deps pinned (offline-bundled); tree-sitter-language-pack NOT pinned (network-coupled)"
affects: [09-04-repo-diff-brownfield-workflow]

# Tech tracking
tech-stack:
  added:
    - "tree-sitter==0.25.2 (github.com/tree-sitter/py-tree-sitter — human-verified at the package-legitimacy checkpoint)"
    - "tree-sitter-python==0.25.0 / tree-sitter-javascript==0.25.0 / tree-sitter-typescript==0.23.2 (per-language prebuilt grammar wheels — offline-bundled, the R-C fallback)"
  patterns:
    - "heavy-dep capability lives app-side with the heavy import LOCAL to the build method; the kernel reaches it via the ctx.runner handle, isolation pinned by import-linter + a grep acceptance gate"
    - "a capability lineage-tracks its output by building an ArtifactRef on the per-run ctx.artifacts graph then best-effort persisting via ctx.scoped_store (offline-harness DB-absence degrades, never breaks)"
    - "context_selector is a pure deterministic function (no embeddings) tested in isolation; the ContextPack capability composes it — the brownfield html_skeleton-compaction analog"

key-files:
  created:
    - backend/app/agents/repo_index/__init__.py
    - backend/app/agents/repo_index/index.py
    - backend/agents/capabilities/repo_inventory/__init__.py
    - backend/agents/capabilities/repo_inventory/inventory.py
    - backend/agents/capabilities/context_pack/__init__.py
    - backend/agents/capabilities/context_pack/pack.py
    - backend/agents/capabilities/context_providers/repo.py
    - backend/tests/agents/test_repo_index.py
    - backend/tests/agents/test_repo_inventory.py
    - backend/tests/agents/test_context_pack.py
  modified:
    - backend/requirements.txt
    - backend/agents/capabilities/registry.py
    - backend/agents/workflows/plan.py
    - backend/tests/agents/test_registry_capabilities.py

key-decisions:
  - "Package-legitimacy checkpoint (Task 1) RESOLVED-APPROVED: tree-sitter==0.25.2 + tree-sitter-language-pack==1.8.1 both human-verified LEGITIMATE on PyPI (2026-06-10). Note: tree-sitter-language-pack's GitHub repo is now github.com/kreuzberg-dev/tree-sitter-language-pack (a VERIFIED owner-initiated org transfer from Goldziher, NOT a squat — the old URL 301-redirects; PyPI owner nhirschfeld = GitHub Goldziher)."
  - "OFFLINE-INSTALL Open Risk REALIZED → R-C fallback taken: tree-sitter-language-pack==1.8.1 installs from a prebuilt wheel but its native get_parser LAZY-DOWNLOADS a parsers.json manifest from GitHub at first use, which FAILS with zero network (proven: the offline-disabled-socket smoke raised a TLS fetch error). Per the documented R-C fallback, pinned the per-language tree-sitter-python/-javascript/-typescript wheels instead — they bundle the compiled grammar IN the wheel (offline-proven, network disabled). tree-sitter-language-pack is NOT pinned."
  - "repo_index is APP-SIDE (the tree_sitter import lives ONLY there, REPO-02) and exposes TWO methods through ONE seam: search() (grep/glob, the always-available DEFAULT, backs onto Workspace.search via the handle) + symbol_query() (only after build()). The symbol index is built IN-MEMORY PER-RUN on the build decision (declared OR file_count > N6) — no new table."
  - "The N6 build DECISION (declared OR file_count > REPO_INDEX_FILE_THRESHOLD=2000) lives in the capability (should_build_index); the compiler only RECORDS the RepoSpec.index opt-in flag (INV-5)."
  - "repo_inventory / context_pack / repo provider are KERNEL-side pure-stdlib, reaching git/disk ONLY via ctx.runner and the store via ctx.scoped_store — 0 app.*/engine imports, import-linter 4/0."
  - "Each capability splits its _KNOWN/discover wiring across the per-task commit so each task's test suite stays green standalone (35→36 in Task 2, 36→39 in Task 3)."

patterns-established:
  - "Offline-grammar proof: a Wave-0 test disables sockets then asserts Language(grammar()).parse(src) yields a non-empty tree — the gate that distinguishes wheel-bundled grammars from lazy-downloaded ones."
  - "Capability lineage write: graph.write_ref(...) on ctx.artifacts (deterministic id/hash/version) + best-effort await store.write_ref(ref); the sync build path runs the persist via asyncio.run when no loop is running."

requirements-completed: [REPO-01, REPO-02, REPO-03]

# Metrics
duration: ~18min
completed: 2026-06-10
---

# Phase 09 Plan 03: Repo Inventory / Index / Context Capabilities Summary

**The four repo-context capabilities landed: the kernel-side pure-stdlib `repo_inventory` (file tree + language stats + dependency list honoring `.gitignore`/`.flowinignore` + binary-skip + size-caps), the app-side optional `repo_index` (tree-sitter symbol index reached via the handle, with grep/glob the always-available default and the heavy `tree_sitter` import isolated to that one module), and the kernel-side `context_pack` + `context_selector` + `repo` ContextProvider (the brownfield `html_skeleton`-compaction analog: a targeted target+neighbors subset, lineage-tracked, with a cross-owner `PermissionError` that propagates) — and the offline-install Open Risk was realized and resolved by the documented per-language-wheel fallback.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 3 (Task 1 checkpoint resolved-approved; Tasks 2-3 executed)
- **Files modified:** 14 (10 created, 4 modified)

## Checkpoint Outcome (Task 1 — package legitimacy, blocking-human)

Task 1 was the `checkpoint:human-verify` (gate="blocking-human") package-legitimacy gate for the two `[ASSUMED]` tree-sitter dependencies (slopcheck was unavailable offline). **Resolved: APPROVED** with verification performed live against PyPI + GitHub (2026-06-10):

- **`tree-sitter==0.25.2`** — VERIFIED LEGITIMATE. Official `tree-sitter/py-tree-sitter` binding (author Max Brunsfeld, the tree-sitter creator); 0.25.2 is the latest release; MIT-licensed; prebuilt wheels for all major platforms; no typosquat indicators.
- **`tree-sitter-language-pack==1.8.1`** — VERIFIED LEGITIMATE, with a recorded **org-transfer note**: the repo URL in current metadata is `github.com/kreuzberg-dev/tree-sitter-language-pack`, NOT the `Goldziher` URL the plan expected. This is a verified, owner-initiated GitHub org transfer (the old `Goldziher/...` URL 301-redirects to `kreuzberg-dev/...`; PyPI owner `nhirschfeld` = Na'aman Hirschfeld = GitHub "Goldziher", the original author), NOT a squat.

The exact pins `tree-sitter==0.25.2` and `tree-sitter-language-pack==1.8.1` were approved (no substitutes). See the deviation below for why `tree-sitter-language-pack` was ultimately NOT pinned (offline-install failure → documented fallback).

## Accomplishments
- Pinned `tree-sitter==0.25.2` in `requirements.txt` (where every dep lives) and, after the offline-install proof failed for `tree-sitter-language-pack==1.8.1`, the per-language prebuilt grammar wheels (`tree-sitter-python`/`-javascript`/`-typescript`) which bundle the grammar IN the wheel.
- Built `app/agents/repo_index/` (app-side): `@register("repo_index","tree_sitter")` with `search()` (grep/glob, the always-available default via the `Workspace.search` handle) + `symbol_query()` (file+line+kind, only after `build()`); the index is in-memory per-run, built on `declared OR file_count > N6`. `Match`/`SymbolHit` are kernel-pure dataclasses. The `tree_sitter` import is LOCAL to `build()`/the grammar loaders — isolated to this one module.
- Added `RepoSpec.index` opt-in flag (compiler records only, INV-5) + `REPO_INDEX_FILE_THRESHOLD` (N6) constant; the build DECISION lives in the capability (`should_build_index`).
- Built `agents/capabilities/repo_inventory/inventory.py` (kernel-side, pure-stdlib): file tree + language stats (by extension) + dependency list (`requirements.txt`/`pyproject.toml`/`package.json`), honoring `.gitignore` (git ls-files via the handle) + `.flowinignore` (`fnmatch`) + binary-skip (null-byte sniff) + documented per-file/total size caps; lineage-tracked as a typed `repo_inventory` artifact.
- Built `agents/capabilities/context_pack/pack.py` (kernel-side): `context_selector()` (pure, deterministic — same-dir siblings + imported files, no embeddings) + the `ContextPack` capability that composes it into a target+neighbors subset, excludes unrelated files, and lineage-tracks a `context_pack` artifact.
- Built `agents/capabilities/context_providers/repo.py` (kernel-side): `@register("context_provider","repo")`, `async load → dict[str,str]` surfacing the ContextPack as a `repo_context` block; the cross-owner `assert_owns` `PermissionError` PROPAGATES (L16 / T-09-03-ID).
- Wired all four `(kind,name)` pairs into `_KNOWN` + the drift guard (35→36→39) + `discover()` (app-side `app.agents.repo_index`; kernel-side `repo_inventory`/`context_pack`/`context_providers.repo`).

## Task Commits

1. **Task 2 (Wave 0): pin deps + repo_index (app-side) + offline-install proof + test_repo_index.py** — `4f927a6` (feat)
2. **Task 3 (Wave 0): repo_inventory + context_pack/selector + repo ContextProvider (kernel-side) + tests** — `e5363e8` (feat)

**Plan metadata:** _(final docs commit below)_

## Files Created/Modified
- `backend/requirements.txt` — pin `tree-sitter==0.25.2` + the three per-language grammar wheels (documented fallback note; language-pack NOT pinned).
- `backend/app/agents/repo_index/__init__.py` / `index.py` — the app-side tree-sitter symbol index (search + symbol_query, tree-sitter import-isolated).
- `backend/agents/capabilities/repo_inventory/__init__.py` / `inventory.py` — kernel-side stdlib inventory (tree/langs/deps/ignore/binary/size-cap, lineage-tracked).
- `backend/agents/capabilities/context_pack/__init__.py` / `pack.py` — kernel-side targeted subset + `context_selector`.
- `backend/agents/capabilities/context_providers/repo.py` — the `repo` ContextProvider (surfaces the pack; propagating cross-owner `PermissionError`).
- `backend/agents/capabilities/registry.py` — `_KNOWN` 35→39 + `discover()` wiring (app-side + kernel-side modules).
- `backend/agents/workflows/plan.py` — `RepoSpec.index` opt-in flag (compiler records only, INV-5).
- `backend/tests/agents/test_repo_index.py` / `test_repo_inventory.py` / `test_context_pack.py` — the three Wave-0 acceptance suites.
- `backend/tests/agents/test_registry_capabilities.py` — drift-guard count 35→39 + `_EXPECTED_NAMES` (expected membership growth).

## Decisions Made
- The two tree-sitter pins were human-approved; the offline-install proof then drove the per-language-wheel substitution (documented below + in `requirements.txt`).
- `repo_index` app-side, `repo_inventory`/`context_pack`/`repo` provider kernel-side (R-F placement); the N6 build decision lives in the capability (INV-5).
- Each task's registry/test wiring is scoped to that task's commit so every per-task suite stays green standalone.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] tree-sitter-language-pack==1.8.1 lazy-downloads grammars → offline-install proof FAILED → documented R-C fallback taken**
- **Found during:** Task 2 (offline-install proof, the plan's explicit Open Risk)
- **Issue:** The approved `tree-sitter-language-pack==1.8.1` installs from a prebuilt wheel, but its native `get_parser("python")` LAZY-DOWNLOADS a `parsers.json` manifest from `github.com/kreuzberg-dev/.../releases/.../parsers.json` at first use. With the network disabled (the phase's offline-CI accept gate) this raised a TLS fetch error — the grammars are NOT bundled in the 1.8.1 wheel (confirmed: the wheel ships only a Rust `_native.abi3.so` loader, no `.so`/`.dylib` grammars).
- **Fix:** Took the plan's explicitly-documented R-C fallback: pin the per-language prebuilt grammar wheels `tree-sitter-python==0.25.0` / `tree-sitter-javascript==0.25.0` / `tree-sitter-typescript==0.23.2`, which bundle the compiled grammar IN the wheel. Proven offline (sockets disabled, non-empty parse trees for py/js/ts). `tree-sitter-language-pack` is NOT pinned (network-coupled); the symbol index uses `tree_sitter.Language(<grammar>.language())` directly.
- **Files modified:** backend/requirements.txt, backend/app/agents/repo_index/index.py, backend/tests/agents/test_repo_index.py
- **Verification:** `test_repo_index.py::test_grammars_parse_offline_no_network` GREEN; `symbol_query` returns the file+line of `greet`/`Service`/`helper`.
- **Committed in:** 4f927a6 (Task 2 commit)

**2. [Rule 3 - Blocking] Deps live in requirements.txt, not pyproject.toml**
- **Found during:** Task 2 (dep pinning)
- **Issue:** The plan said "add to `pyproject.toml` (pinned like every dep)", but the project's actual dependency home is `backend/requirements.txt` (where `deepagents`, `opentelemetry-api/sdk`, etc. are pinned); `pyproject.toml` carries only tooling config (ruff/import-linter/pytest), no `dependencies` array.
- **Fix:** Pinned the deps in `requirements.txt` (the project convention), following the `opentelemetry` 08-07 precedent (a commented block + the pins).
- **Files modified:** backend/requirements.txt
- **Committed in:** 4f927a6 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking). Both stay within the plan's explicit guidance (the R-C fallback was pre-authored; the dep home is the established project convention). No scope creep.

## Issues Encountered
None beyond the two auto-fixed deviations above. The `tree-sitter-language-pack` offline failure was the plan's predicted Open Risk, resolved by its predicted fallback.

## Known Stubs
None. The `repo_index` opt-in flag (`RepoSpec.index`) and the N6 threshold are declared seams consumed by the build decision; the `repo` provider's `context_pack_target` / `repo_source_run_id` are ctx-threaded inputs the 09-04 brownfield workflow wires. These are plan-declared forward inputs, not UI-blocking stubs.

## Threat Flags
None beyond the plan's `<threat_model>`. T-09-03-01 (path traversal) is mitigated by reading via the `Workspace` handle (traversal-proof `path_for`) + binary-skip + ignore-exclusion + size-caps. T-09-03-02 (tree-sitter import leak) is mitigated: `grep -rn "import tree_sitter" agents/ app/ | grep -v app/agents/repo_index/` returns 0 lines; import-linter 4/0. T-09-03-ID (cross-owner ContextPack read) is mitigated: the `repo` provider's `assert_owns` `PermissionError` propagates (`test_context_pack.py::test_repo_provider_propagates_cross_owner_permission_error`). T-09-03-SC (slopsquatted dep) was mitigated by the Task 1 blocking-human checkpoint (both deps human-verified before the add).

## User Setup Required
None — the deps install from prebuilt wheels (no C toolchain, no network at runtime).

## Next Phase Readiness
- The repo-context capabilities (inventory + optional symbol index + targeted context pack + `repo` provider) are ready for 09-04 (`repo_diff` resolver + the sample brownfield workflow), which composes them over the `has_git=True` Workspace.
- import-linter 4/0; banned-pattern green (INV-13 untouched — tree-sitter is a library); 5 characterization snapshots byte/event-identical (09-03 is purely additive).

## Verification Evidence
- `tests/agents/test_repo_index.py` — 6 passed (offline-grammar proof with sockets disabled → non-empty tree; index-off → grep; index-on → `symbol_query` file+line of greet/Service/helper; N6 decision; registered).
- `tests/agents/test_repo_inventory.py` — 6 passed (lists sources, EXCLUDES `.flowinignore` + binary, per-file size cap, lang stats, deps, lineage-tracked).
- `tests/agents/test_context_pack.py` — 6 passed (selector siblings+imports/excludes unrelated; pack target+neighbors/excludes unrelated; artifact_ref written; `repo` provider surfaces it; cross-owner `PermissionError` propagates).
- `cd backend && grep -rn "import tree_sitter" agents/ app/ | grep -v "app/agents/repo_index/"` → 0 lines (tree-sitter imported ONLY behind the capability — REPO-02 acceptance).
- `cd backend && python3.11 -c "...discover(); print(r.is_registered('repo_inventory','default'), r.is_registered('context_pack','default'), r.is_registered('context_provider','repo'))"` → `True True True`; `repo_index` → `True`.
- `tests/agents/test_registry_capabilities.py` — drift guard 35→39 (4 new pairs); 65/74 passed across the task suites.
- `tests/agents/test_banned_patterns.py` + `test_migration_ledger.py` — green (INV-13 untouched; no parity/ledger files touched).
- `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken (kernel↛app/engine direction held).
- 5 characterization snapshots (`prototype`/`app_builder`/`od_ppt`/`od_prototype`/`prototype_revision`) — 10 passed (byte/event-identical, `SNAPSHOT_UPDATE` UNSET, no re-baseline).

## Self-Check: PASSED
- FOUND: backend/app/agents/repo_index/index.py
- FOUND: backend/agents/capabilities/repo_inventory/inventory.py
- FOUND: backend/agents/capabilities/context_pack/pack.py
- FOUND: backend/agents/capabilities/context_providers/repo.py
- FOUND commit: 4f927a6
- FOUND commit: e5363e8

---
*Phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a*
*Completed: 2026-06-10*
