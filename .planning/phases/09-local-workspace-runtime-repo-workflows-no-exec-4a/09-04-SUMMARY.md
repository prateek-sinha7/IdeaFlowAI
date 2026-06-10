---
phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
plan: 04
subsystem: agents
tags: [repo-diff, brownfield-workflow, deliverable-resolver, repo-context, capability-registry, import-linter, no-exec, sc001, hexagonal-ports]

# Dependency graph
requires:
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    plan: 01
    provides: "RuntimeEnvironment/Workspace ports + LocalSandboxRuntime/LocalWorkspace (clone/branch/git_diff over a cloned repo) + the reusable local_git_fixture seeder"
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    plan: 02
    provides: "the one Workspace abstraction serving both has_git=False artifact + has_git=True repo paths"
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    plan: 03
    provides: "repo_inventory + context_pack + repo context_provider (the brownfield context chain the sample workflow declares)"
  - phase: 08-capabilities-runtime-frontend-1d
    provides: "self-registering CapabilityRegistry (@register / discover() / _KNOWN drift guard) + the deliverable-resolver-via-handle pattern (serialized_sandbox)"
  - phase: 07-strangler-strategies-deliverables-1d
    provides: "the kernel-agnostic deliverable resolution seam (registry.resolve('deliverable', name).resolve(ctx)) + the SC-001 non-prototype-workflow fixture-drive precedent"
provides:
  - "agents/capabilities/deliverables/repo_diff.py — @register('deliverable','repo_diff'): reads the unified diff via the Workspace handle (ctx.runner.workspace.git_diff), composes a file tree + per-file unified diff + change summary; diff-only (no commit/PR push, N4)"
  - "agents/workflows/sample_brownfield/workflow.yaml — the file-backed NON-prototype brownfield manifest (clone->branch->repo-context->read/edit>=1->repo_diff), runs with ZERO engine edits (SC-001)"
  - "tests/agents/test_sample_brownfield_workflow.py — the REPO-05 end-to-end accept proof (offline, scripted model): run completes, the surfaced diff contains the agent edit, exec=off at every step, prototype parity held"
affects: [10-local-exec-security-4b, 09-05-mcp-integration-providers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "deliverable-resolver-via-handle for the brownfield class: the repo_diff resolver reads the diff ONLY through ctx.runner.workspace (the LocalWorkspace is the single git owner); the resolver spawns no child process and pushes nothing (diff-only, N4)"
    - "a NEW non-prototype workflow = manifest (agents/workflows/<id>/workflow.yaml) + AGENT.md fixtures, using only registered capabilities — compiles + runs with zero engine edit (SC-001), the §15 repo binding injected at run entry (not a manifest top-key, INV-5)"
    - "exec stays OFF on the whole brownfield path: no step grants exec, so the effective-perms intersection (owner ∩ workflow ∩ step) has exec=off everywhere — asserted off the compiled plan"

key-files:
  created:
    - backend/agents/capabilities/deliverables/repo_diff.py
    - backend/agents/workflows/sample_brownfield/workflow.yaml
    - backend/tests/agents/fixtures/sample_brownfield/brownfield-analyze/AGENT.md
    - backend/tests/agents/fixtures/sample_brownfield/brownfield-build/AGENT.md
    - backend/tests/agents/test_repo_diff.py
    - backend/tests/agents/test_sample_brownfield_workflow.py
  modified:
    - backend/agents/capabilities/registry.py
    - backend/tests/agents/test_registry_capabilities.py

key-decisions:
  - "repo_diff reads the diff EXCLUSIVELY via ctx.runner.workspace.git_diff(base, work) — never spawns a child process from the resolver (D-10; the Workspace is the single git owner). base/working branches read off ctx (base_branch/working_branch, default main/work), never a workflow-name branch (INV-1)."
  - "repo_diff is strictly diff-only (N4/N5): grep-clean of git commit/push + subprocess/os.system/Popen; the test asserts the resolver adds no commit on the work branch and never pushes the work branch to origin."
  - "the sample brownfield manifest lives at the REAL manifest home agents/workflows/sample_brownfield/workflow.yaml (not the plan's manifests/ subdir, which compile_for_run does not scan) so compile_for_run('sample_brownfield') loads it with zero engine edit; the AGENT.md specs + the end-to-end test are test-scoped (SC-001 sc001 precedent — no SUPPORTED_PIPELINE_TYPES / production loader edit)."
  - "the §15 RepoSpec (local fixture path + base/working branches) is supplied at RUN ENTRY by the harness, NOT the manifest — manifests are pure data and the repo binding has no manifest top-key (INV-5 / D-08), exactly as a runtime host would inject it."

patterns-established:
  - "brownfield workflow proof = a registered diff-only deliverable + a registered repo context provider + a file-backed manifest + AGENT.md, driven end-to-end offline against a local git fixture; the surfaced diff containing the agent edit + exec=off-everywhere is the REPO-05 gate, the prototype snapshots are the additive-parity gate."

requirements-completed: [REPO-04, REPO-05]

# Metrics
duration: ~20min
completed: 2026-06-10
---

# Phase 09 Plan 04: repo_diff Deliverable + Sample Brownfield Workflow Summary

**The brownfield deliverable + the phase accept proof landed: the kernel-side `repo_diff` `DeliverableResolver` reads the unified diff via the `Workspace` handle (`ctx.runner.workspace.git_diff`) and surfaces a file tree + per-file unified diff (containing the agent's edit) + change summary — diff-only, no commit/PR push (REPO-04); and a brand-new NON-prototype `sample_brownfield` workflow (manifest + AGENT.md) runs end-to-end offline — clone fixture → branch `work` → repo context → agent reads/edits ≥1 file (`write_files`, no exec) → `repo_diff` — with `exec` OFF at every step, the diff containing the edit, prototype parity held, and ZERO engine edits (REPO-05 / SC-001).**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-10T08:36Z
- **Completed:** 2026-06-10T08:56Z
- **Tasks:** 2
- **Files modified:** 8 (6 created, 2 modified)

## Accomplishments
- Built `repo_diff.py` (`@register("deliverable","repo_diff")`, kernel-side): reads `ctx.runner.workspace.git_diff(base, work)` via the handle, splits the unified diff into a `{relpath: per-file diff}` map, composes a file tree (sorted changed paths) + a change summary (`files_changed`/`lines_added`/`lines_removed`), and pushes NOTHING (diff-only, N4). The resolver spawns no child process — grep-clean of `git commit`/`git push`/`subprocess`/`os.system`/`Popen`.
- Authored the file-backed `sample_brownfield` manifest at the real manifest home (`agents/workflows/sample_brownfield/workflow.yaml`): a NON-prototype workflow declaring `context_providers: [repo]` + a `brownfield-build` step granting `write_files` (NOT `exec`) + `deliverable: repo_diff` — it compiles cleanly against the registry and runs with zero engine edit (SC-001).
- Drove the workflow end-to-end OFFLINE (`test_sample_brownfield_workflow.py`, scripted model + `local_git_fixture`): a `has_git=True` `LocalWorkspace` clones the fixture + branches `work`, the build agent edits `src/app.py` (`write_files`, no exec), and the surfaced `repo_diff` CONTAINS the edit; the effective-perms intersection has `exec=off` at every step; prototype characterization stays byte/event-identical in the same session.
- Registered `("deliverable","repo_diff")` in `_KNOWN` + `discover()`; bumped the drift guard 39→40 in lockstep.

## Task Commits

Each task was committed atomically:

1. **Task 1 (Wave 0): repo_diff DeliverableResolver (reads Workspace.git_diff via handle, diff-only) + test_repo_diff.py** — `98d8f9b` (feat)
2. **Task 2 (Wave 0): sample brownfield workflow manifest + end-to-end accept test (no exec)** — `47be9a9` (feat)

**Plan metadata:** _(final docs commit below)_

## Files Created/Modified
- `backend/agents/capabilities/deliverables/repo_diff.py` — the diff-only brownfield resolver (reads via the handle; tree + per-file diff + summary).
- `backend/agents/workflows/sample_brownfield/workflow.yaml` — the file-backed NON-prototype brownfield manifest (clone→branch→repo-context→read/edit→repo_diff, exec off).
- `backend/tests/agents/fixtures/sample_brownfield/brownfield-analyze/AGENT.md` — the read/plan agent (tools: [], no exec).
- `backend/tests/agents/fixtures/sample_brownfield/brownfield-build/AGENT.md` — the edit agent (tools: [workspace] / write_files, NO exec).
- `backend/tests/agents/test_repo_diff.py` — Wave-0: clone→branch→edit→`repo_diff` returns tree + per-file diff (containing the edit) + summary; resolver adds no commit on `work` + never pushes `work` to origin; grep-clean source.
- `backend/tests/agents/test_sample_brownfield_workflow.py` — the REPO-05 end-to-end accept proof (run completes, diff contains the edit, exec=off everywhere, prototype parity held, zero engine edits).
- `backend/agents/capabilities/registry.py` — `_KNOWN` 39→40 + `discover()` import for `repo_diff`.
- `backend/tests/agents/test_registry_capabilities.py` — drift-guard count 39→40 + `_EXPECTED_NAMES` pair.

## Decisions Made
- `repo_diff` reads the diff via the `Workspace` handle only (never spawns a child process from the resolver, D-10); base/working branches read off `ctx` (default `main`/`work`), never a workflow-name branch (INV-1).
- The manifest lives at the real manifest home (`agents/workflows/sample_brownfield/`), not the plan's `manifests/` subdir which `compile_for_run` does not scan — so it loads with zero engine edit; the AGENT.md specs + the test are test-scoped (sc001 precedent, no production loader/registry edit).
- The §15 RepoSpec (local fixture path + branches) is injected at run entry by the harness, not declared in the manifest (manifests are pure data, no `repo` top-key — INV-5 / D-08).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Manifest path corrected from the non-existent `manifests/` subdir to the real manifest home**
- **Found during:** Task 2 (sample brownfield manifest authoring)
- **Issue:** The plan's `files_modified` / artifacts named `backend/agents/workflows/manifests/sample_brownfield/workflow.yaml`, but the codebase's manifest layout is `agents/workflows/<id>/workflow.yaml` (one dir per id) and `compile_for_run` loads from `_WORKFLOWS_DIR = agents/workflows/` directly — a `manifests/` subdir would not be found by `compile_for_run`, so the new workflow could not run.
- **Fix:** Placed the manifest at the real manifest home `agents/workflows/sample_brownfield/workflow.yaml` so `compile_for_run("sample_brownfield")` loads it with zero engine edit; followed the sc001 precedent for the AGENT.md specs (test-scoped fixtures) to avoid touching `SUPPORTED_PIPELINE_TYPES` / the production loader.
- **Files modified:** backend/agents/workflows/sample_brownfield/workflow.yaml (vs the plan's path), backend/tests/agents/fixtures/sample_brownfield/*/AGENT.md
- **Verification:** `compile_for_run('sample_brownfield')` compiles cleanly; the end-to-end test drives it via `execute()` and surfaces the `repo_diff`.
- **Committed in:** 47be9a9 (Task 2 commit)

**2. [Rule 1 - Bug] Diff-only "no push" acceptance reframed off the always-present `origin` remote**
- **Found during:** Task 1 (test_repo_diff "no commit/push" assertion)
- **Issue:** The plan's acceptance phrasing implied "no remote configured", but `git clone` ALWAYS wires an `origin` remote at the source path — a bare "no remote" assertion false-fires for any cloned repo.
- **Fix:** Reframed the diff-only acceptance to the real N4 invariant: the resolver adds NO new commit on the `work` branch (HEAD + rev-count unchanged after resolve) and NEVER pushes the `work` branch upstream (the fixture origin gains no `work` ref). Plus the grep-clean source-scan (`git commit`/`git push`/`subprocess` = 0).
- **Files modified:** backend/tests/agents/test_repo_diff.py
- **Verification:** `test_repo_diff_performs_no_commit_or_push` GREEN.
- **Committed in:** 98d8f9b (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking path correction, 1 test-assertion bug). Both stay within the plan's intent (the manifest home is the established convention; the diff-only invariant is unchanged — only the assertion was made correct). No scope creep.

## Issues Encountered
- `RUNS_ROOT` defaults to the non-writable `/app/runs` offline (the dev-runtime note) — both tests monkeypatch `settings.RUNS_ROOT` to a temp dir before `create_workspace`, mirroring `test_local_runtime.py` (09-01).

## Known Stubs
None. The `KernelServices` handle does not yet expose `.workspace` on the LIVE engine run path (the brownfield workspace is provisioned + attached by the accept-proof harness, exactly as a future runtime host wiring would); this is the plan-declared run-entry injection seam, not a UI-blocking stub. The full engine→`has_git=True`-Workspace provisioning is a forward integration (this plan proves the capability chain end-to-end against it).

## Threat Flags
None beyond the plan's `<threat_model>`. T-09-04-01 (exec on the brownfield path) is mitigated: no step grants exec, the effective-perms intersection has `exec=off` at every step (`test_sample_brownfield_exec_off_at_every_step`). T-09-04-03 (unintended commit/push) is mitigated: `repo_diff` is diff-only (`grep -nE "git (commit|push)"` → 0; the test asserts no new commit on `work` + no push to origin, N4). T-09-04-02 (path traversal in edit/diff) is mitigated: edits route through `Workspace.path_for` (traversal-rejected, 09-01/09-02) + the diff reads via the handle. T-09-04-04 (prototype parity perturbation) is mitigated: the repo path is additive; `test_characterization_prototype.py` stays green alongside the sample run. T-09-04-SC (no new package) holds: 09-04 adds no dependency.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- The full brownfield workflow class is proven end-to-end offline (clone→branch→repo-context→read/edit→diff), exec OFF everywhere, the diff containing the edit — REPO-04 + REPO-05 closed; the first use of the `Workspace(has_git=True)` path (the 09-02 refold serves both) is exercised.
- Ready for 09-05 (MCP client + catalog + integration providers) and Phase 10 / [4B] (N3 local-exec security threat model — exec stays OFF until then).
- import-linter 4/0; banned-pattern + migration-ledger green (INV-13 untouched); 5 characterization snapshots byte/event-identical (09-04 is purely additive); zero engine edits (SC-001 discipline held).

## Verification Evidence
- `tests/agents/test_repo_diff.py` — 4 passed (tree + per-file diff containing the edit + summary; resolver adds no commit on `work` + never pushes `work` to origin; grep-clean source; registered).
- `tests/agents/test_sample_brownfield_workflow.py` — 3 passed (run completes end-to-end offline + the surfaced `repo_diff` contains the edit; exec=off at every step; manifest compiles + the proof artifacts live OUTSIDE the engine package).
- `tests/agents/test_characterization_prototype.py` — 2 passed in the SAME run as the brownfield drive (byte/event-identical; prototype unaffected — additive).
- `cd backend && grep -nE "git (commit|push)" agents/capabilities/deliverables/repo_diff.py` → 0; `grep -n "subprocess\|os.system\|Popen"` → 0 (reads via the handle, never shells git).
- `cd backend && python3.11 -c "...discover(); print(CapabilityRegistry().is_registered('deliverable','repo_diff'))"` → `True`.
- `tests/agents/test_registry_capabilities.py` — 63 passed (drift guard 39→40).
- `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken; `tests/agents/test_banned_patterns.py` — 11 passed; `tests/agents/test_migration_ledger.py` — 20 passed / 4 skipped.
- `git diff --name-only HEAD~2 HEAD -- agents/execution_engine/` → 0 (zero engine edits — SC-001).

## Self-Check: PASSED
- FOUND: backend/agents/capabilities/deliverables/repo_diff.py
- FOUND: backend/agents/workflows/sample_brownfield/workflow.yaml
- FOUND: backend/tests/agents/test_repo_diff.py
- FOUND: backend/tests/agents/test_sample_brownfield_workflow.py
- FOUND commit: 98d8f9b
- FOUND commit: 47be9a9

---
*Phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a*
*Completed: 2026-06-10*
