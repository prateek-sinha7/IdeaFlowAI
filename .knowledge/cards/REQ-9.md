---
id: REQ-9
type: req
status: done
area: [workflow, artifacts, runtime]
summary: >-
  Local Workspace Runtime & Repo Workflows — No Exec (Phase 4A)
source: .planning/REQUIREMENTS.md#local-workspace-runtime-repo-workflows-no-exec-p
---

### Local Workspace Runtime & Repo Workflows — No Exec (Phase 4A)

- [x] **RUNTIME-01**: `RuntimeEnvironment` port (read/write/search/exec_command/clone_repo/create_branch/git_diff/teardown) + `LocalSandboxRuntime` impl over the per-run disk dir (§6/§14) — done 09-01
- [x] **RUNTIME-02**: One `Workspace` abstraction (fs + optional git + optional exec + `ExecutionPolicy`); prototype's `RunSandbox` becomes a `has_git=False, exec=off` Workspace — no engine fork repo-vs-artifact (R3/§14)
- [x] **RUNTIME-03**: `repositories` + `workspaces` rows persisted (§18)
- [x] **REPO-01**: `RepoInventory` (`kind=repo_inventory`) — file tree, language stats, dependency graph, ignore rules (`.gitignore` + `.flowinignore`), binary-file skip, size caps, optional summaries (§15)
- [x] **REPO-02**: `RepoIndex` (optional, large repos) behind a port; default grep/glob for small repos; threshold = N6 (§15 — N6/N10 SETTLED: shipped at deliverable parity in Phase 9 [4A], 09-03/09-04; decision recorded, no open question)
- [x] **REPO-03**: `ContextPack` (`kind=context_pack`) — targeted per-task subset via a `context_selector` capability, lineage-tracked; surfaced via the `repo` context provider (§15)
- [x] **REPO-04**: `repo_diff` `DeliverableResolver` produces app-builder-style file tree + per-file diff (Q-N7 — N5/N7 SETTLED: shipped at deliverable parity in Phase 9 [4A], 09-03/09-04; decision recorded, no open question)
- [x] **REPO-05**: A sample brownfield workflow runs end-to-end locally without execution (clone → branch → inventory → agents read/edit/search → diff surface); prototype unaffected (Phase 4A Accept)
