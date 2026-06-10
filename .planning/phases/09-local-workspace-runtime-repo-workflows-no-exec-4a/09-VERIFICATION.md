---
phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
verified: 2026-06-10T00:00:00Z
status: passed
score: 4/4
overrides_applied: 0
---

# Phase 09: Local Workspace Runtime + Repo Workflows (No Exec) Verification Report

**Phase Goal:** Introduce the `RuntimeEnvironment`/`Workspace` ports with a `LocalSandboxRuntime`, and deliver the first brownfield repo workflow end-to-end locally without execution (clone -> branch -> inventory -> read/edit/search -> diff) — plus the MCP client and integration providers.
**Verified:** 2026-06-10
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `RuntimeEnvironment` port + `LocalSandboxRuntime`; one `Workspace` abstraction (prototype = `has_git=False, exec=off`) with no engine fork repo-vs-artifact; `repositories`/`workspaces` rows persisted | VERIFIED | `agents/runtime/base.py` defines 4 `@runtime_checkable` Protocol ports (all confirmed by grep). `LocalSandboxRuntime` registered at `("runtime_env","local")`. `RunSandbox` delegates disk IO to `Workspace(has_git=False, exec=off)` (sandbox.py:60-102). `grep -rn "if repo" agents/execution_engine/` → 0. Migration 0017 (`revision="0017"`, `down_revision="0016"`) creates `repositories` table with `owner_id`/`workspace_id` NN. `test_local_runtime.py` 8 passed; `test_repositories_persistence.py` 2 passed. |
| 2 | `RepoInventory` (tree/lang/deps/ignore-rules/binary-skip/summaries), optional `RepoIndex`, and per-task `ContextPack` produced; `repo_diff` resolver yields a file tree + per-file diff | VERIFIED | `@register("repo_inventory","default")` at `inventory.py:55`; `@register("repo_index","tree_sitter")` app-side with `search()` + `symbol_query()`; `@register("context_pack","default")` + `@register("context_provider","repo")`. `@register("deliverable","repo_diff")` at `repo_diff.py:46`. `test_repo_inventory.py` 6 passed; `test_repo_index.py` 6 passed; `test_context_pack.py` 6 passed; `test_repo_diff.py` 4 passed. tree-sitter isolated to `app/agents/repo_index/` only (grep returns 0 matches outside). |
| 3 | A sample repo workflow runs end-to-end locally with no exec and surfaces a diff; prototype unaffected | VERIFIED | `agents/workflows/sample_brownfield/workflow.yaml` exists. `test_sample_brownfield_workflow.py` 3 passed (run completes; surfaced `repo_diff` contains agent edit; `exec=off` at every step; `test_characterization_prototype.py` 2 passed in same run). `repo_diff.py` is grep-clean of `git commit`/`git push`/`subprocess`/`os.system`/`Popen`. All 5 characterization suites passed (10 tests, byte/event-identical, SNAPSHOT_UPDATE UNSET). |
| 4 | `McpClientAdapter` + allow-listed famous-server catalog (scoped per-owner creds, security-gated for powerful servers); compiler validates `tools.mcp`; integration providers reachable from the unified runner path | VERIFIED | `McpClientAdapter` wraps `MultiServerMCPClient` (app/agents/mcp/client.py:49). catalog: github/gitlab/jira/slack `user_allowed=True`; filesystem/postgres `user_allowed=False`. `McpCredential` owner-scoped + Fernet-encrypted. Compiler `_validate_mcp_grant` at compiler.py:366 performs per-`server.tool` validation (MCP-03) + powerful-server gating (MCP-04). Four `@register("integration_provider", …)` thin MCP bridges. CodingAgent bypass deleted (`grep -rn "class CodingAgent" backend/` → 0). `test_mcp_client.py` 5 passed; `test_mcp_catalog.py` 4 passed; `test_mcp_compile_validation.py` 6 passed; `test_mcp_gating.py` 4 passed; `test_integration_providers.py` 8 passed; `test_integration_scopes.py` 6 passed. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/runtime/base.py` | RuntimeEnvironment/Workspace/ExecutionPolicy/IsolationProvider ports | VERIFIED | 4 classes confirmed (lines 31/50/98/125); stdlib-only; `grep -nE "import (app\|agents\.execution_engine)" → 0` |
| `backend/app/agents/runtime/local.py` | LocalSandboxRuntime `@register("runtime_env","local")` | VERIFIED | Lines 203-204 confirm registration |
| `backend/alembic/versions/0017_repositories_repo_workspace.py` | Additive repositories table + workspaces.repo_id FK | VERIFIED | `revision="0017"`, `down_revision="0016"` confirmed |
| `backend/app/models/repository.py` | Repository model (owner/workspace-scoped) | VERIFIED | `class Repository` at line 27; `owner_id`/`workspace_id` NN at lines 33-34 |
| `backend/app/agents/sandbox.py` | RunSandbox refolded as Workspace facade | VERIFIED | Delegates disk IO to `LocalWorkspace` (sandbox.py:60-102); consumed surface byte-identical |
| `backend/agents/capabilities/repo_inventory/inventory.py` | `@register("repo_inventory","default")` | VERIFIED | Line 55 confirms registration |
| `backend/app/agents/repo_index/index.py` | `@register("repo_index","tree_sitter")` tree-sitter isolated | VERIFIED | App-side; `grep` for tree_sitter import outside `app/agents/repo_index/` → 0 |
| `backend/agents/capabilities/context_pack/pack.py` | `@register("context_pack","default")` + context_selector | VERIFIED | Line 94 confirms registration |
| `backend/agents/capabilities/context_providers/repo.py` | `@register("context_provider","repo")` | VERIFIED | Line 30 confirms registration |
| `backend/agents/capabilities/deliverables/repo_diff.py` | `@register("deliverable","repo_diff")` diff-only | VERIFIED | Line 46 confirms; grep-clean of git commit/push/subprocess |
| `backend/agents/workflows/sample_brownfield/workflow.yaml` | Sample brownfield manifest | VERIFIED | Present; declares `repo_diff` deliverable + `repo` context provider + no exec grant |
| `backend/tests/agents/test_sample_brownfield_workflow.py` | REPO-05 end-to-end accept proof | VERIFIED | 3 passed: run completes, diff contains agent edit, exec=off everywhere |
| `backend/app/agents/mcp/client.py` | McpClientAdapter over MultiServerMCPClient | VERIFIED | `class McpClientAdapter` wraps `MultiServerMCPClient` (line 33/49) |
| `backend/agents/capabilities/mcp_servers/catalog.py` | `@register("mcp_server", …)` catalog | VERIFIED | 6 entries: github/gitlab/jira/slack (user_allowed=True); filesystem/postgres (user_allowed=False) |
| `backend/tests/agents/fixtures/stub_mcp_server.py` | FastMCP stdio stub for offline proof | VERIFIED | Present |
| `backend/app/models/mcp_credential.py` | McpCredential owner-scoped + encrypted | VERIFIED | Present; owner/workspace-scoped Fernet-encrypted PAT model |
| `backend/agents/capabilities/integration_providers/providers.py` | `@register("integration_provider", …)` thin MCP bridges | VERIFIED | 4 entries: github/gitlab/jira/slack; no parallel vendor SDK (grep → 0) |
| `backend/app/agents/handoff/coder.py` | HandoffCoder (deepagents runtime successor to bypass) | VERIFIED | Present; invokes `DeepAgentRunner` → `create_deep_agent` |
| `backend/app/agents/handoff/coding_agent.py` | DELETED (CodingAgent bypass) | VERIFIED | File does not exist; `grep -rn "class CodingAgent" backend/` → 0 |
| `backend/specs/003-workflow-engine-decoupling/migration-ledger.md` | D9 + D10 ledger rows | VERIFIED | D9 (CodingAgent deletion grep gate ☑) + D10 (RETAINED justification ☑) confirmed at lines 89-90 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `agents/capabilities/registry.py` | `app.agents.runtime` | `discover()` `_forward_packages` | VERIFIED | `"app.agents.runtime"` at registry.py:259 |
| `pyproject.toml` | `agents.runtime` | import-linter forbidden contract | VERIFIED | 4th contract at pyproject.toml:182-185: `source_modules=["agents.runtime"]`, `forbidden_modules=["agents.execution_engine","app"]`; `lint-imports` → 4 kept, 0 broken |
| `backend/app/agents/sandbox.py` | `agents.runtime.base.Workspace` | RunSandbox delegates disk IO | VERIFIED | sandbox.py:80-102 lazily builds `LocalWorkspace` with `has_git=False, exec=off` |
| `backend/agents/execution_engine/engine.py` | `McpClientAdapter.get_tools()` | async prewarm at run-entry | VERIFIED | engine.py:727-785 prewarms `prewarmed_mcp_tools`; factory.py:503-508 reads sync-only (no double-loop); `grep asyncio.run|nest_asyncio|run_until_complete agents/factory.py` → 0 |
| `backend/agents/workflows/compiler.py` | `server.tool` MCP validation | `_validate_mcp_grant` per-reference | VERIFIED | compiler.py:309-406 validates `tools.mcp` at the same per-reference site as `is_registered/_check_trust` |
| `backend/agents/capabilities/deliverables/repo_diff.py` | `ctx.runner.workspace.git_diff` | resolver reads via Workspace handle | VERIFIED | repo_diff.py:60 reads `ctx.runner.workspace.git_diff`; no subprocess/os.system/Popen |
| `backend/agents/capabilities/integration_providers/providers.py` | mcp_server catalog + integrations scope | `resolve_integration_scopes` feeds MCP prewarm | VERIFIED | providers.py exposes `resolve_integration_scopes`; engine.py:750-758 merges with MCP prewarm |
| `backend/agents/execution_engine/engine.py` | `ScopedStore.record_capabilities` | records active integration scopes + MCP servers | VERIFIED | engine.py:559-581 records `_rec_scopes` + `_rec_servers` via `record_capabilities` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `repo_diff.py` | unified diff string | `ctx.runner.workspace.git_diff(base, work)` (LocalWorkspace) | Yes — runs `git diff` subprocess on cloned repo | FLOWING |
| `RunSandbox` | disk content | `LocalWorkspace.read_file`/`write_file` (via `_ws()`) | Yes — reads actual file system under `RUNS_ROOT` | FLOWING |
| `McpClientAdapter` | `prewarmed_mcp_tools` | `await MultiServerMCPClient.get_tools()` | Yes — connects to MCP server and fetches tools | FLOWING |
| `integration_providers` | integration tools | `resolve_integration_scopes` → MCP prewarm | Yes — maps granted scope to catalog server config | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Runtime ports exist and import clean | `python3.11 -c "from agents.runtime.base import RuntimeEnvironment, Workspace, ExecutionPolicy, IsolationProvider; print('ok')"` | `ok` | PASS |
| LocalSandboxRuntime registered | `python3.11 -c "from agents.capabilities.registry import CapabilityRegistry, discover; discover(); print(CapabilityRegistry().is_registered('runtime_env','local'))"` | `True` | PASS |
| `grep -rn "if repo" agents/execution_engine/` | grep | 0 matches | PASS |
| `lint-imports` 4 contracts kept, 0 broken | `/opt/homebrew/bin/lint-imports` | 4 kept, 0 broken | PASS |
| CodingAgent bypass deleted | `grep -rn "class CodingAgent" . --include=*.py` | 0 matches | PASS |
| Prototype characterization parity | `pytest tests/agents/test_characterization_prototype.py` | 2 passed | PASS |
| `test_local_runtime.py` (RUNTIME-01 accept) | `pytest tests/agents/test_local_runtime.py` | 8 passed | PASS |
| `test_sample_brownfield_workflow.py` (REPO-05 accept) | `pytest tests/agents/test_sample_brownfield_workflow.py` | 3 passed | PASS |
| MCP tests pass (MCP-01..04 accept) | `pytest tests/agents/test_mcp_client.py test_mcp_catalog.py test_mcp_compile_validation.py test_mcp_gating.py` | 19 passed | PASS |
| Integration provider tests pass (INTEG-01/02 accept) | `pytest tests/agents/test_integration_providers.py test_integration_scopes.py` | 14 passed | PASS |
| All 5 characterization suites pass | `pytest tests/agents/test_characterization_*.py` | 10 passed | PASS |
| Banned-pattern + migration-ledger gates green | `pytest tests/agents/test_banned_patterns.py tests/agents/test_migration_ledger.py` | 32 passed, 5 skipped | PASS |
| tree-sitter import isolated | `grep -rn "import tree_sitter" agents/ app/ | grep -v "app/agents/repo_index/"` | 0 matches | PASS |

### Probe Execution

Step 7c: SKIPPED — phase produces no `scripts/*/tests/probe-*.sh` probes; behavioral spot-checks above cover the same accept criteria.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| RUNTIME-01 | 09-01 | RuntimeEnvironment port + LocalSandboxRuntime | SATISFIED | `agents/runtime/base.py` (4 ports); `app/agents/runtime/local.py` (impl); `test_local_runtime.py` 8 passed |
| RUNTIME-02 | 09-02 | One Workspace abstraction, no engine fork | SATISFIED | `RunSandbox` delegates to `Workspace(has_git=False, exec=off)`; `grep "if repo" agents/execution_engine/` → 0; 5-pipeline byte parity held |
| RUNTIME-03 | 09-02 | `repositories`/`workspaces` rows persisted | SATISFIED | Migration 0017 creates `repositories` table + `workspaces.repo_id` FK; `test_repositories_persistence.py` 2 passed |
| REPO-01 | 09-03 | RepoInventory (tree/lang/deps/ignore/binary/size-caps) | SATISFIED | `@register("repo_inventory","default")`; `test_repo_inventory.py` 6 passed |
| REPO-02 | 09-03 | Optional RepoIndex; tree-sitter import isolated | SATISFIED | `@register("repo_index","tree_sitter")` app-side; grep → 0 outside capability; `test_repo_index.py` 6 passed including offline-grammar proof |
| REPO-03 | 09-03 | ContextPack per-task subset; surfaced via repo provider | SATISFIED | `@register("context_pack","default")` + `@register("context_provider","repo")`; `test_context_pack.py` 6 passed |
| REPO-04 | 09-04 | `repo_diff` resolver: file tree + per-file unified diff | SATISFIED | `@register("deliverable","repo_diff")`; reads via `ctx.runner.workspace.git_diff`; diff-only; `test_repo_diff.py` 4 passed |
| REPO-05 | 09-04 | Sample brownfield workflow end-to-end locally; no exec; prototype unaffected | SATISFIED | `test_sample_brownfield_workflow.py` 3 passed; exec=off at every step; `test_characterization_prototype.py` 2 passed alongside |
| MCP-01 | 09-05 | McpClientAdapter connects to stub, binds tools into deepagents | SATISFIED | `test_mcp_client.py` 5 passed; async prewarm pattern; INV-13 held |
| MCP-02 | 09-05 | Allow-listed catalog; scoped per-owner creds; not cross-owner readable | SATISFIED | github/gitlab/jira/slack `user_allowed=True`; filesystem/postgres `user_allowed=False`; `McpCredential` owner-scoped; `test_mcp_catalog.py` 4 passed |
| MCP-03 | 09-05 | Compiler validates `tools.mcp` server.tool | SATISFIED | `_validate_mcp_grant` at compiler.py:366; `test_mcp_compile_validation.py` 6 passed |
| MCP-04 | 09-05 | Powerful servers gated on security+secrets; read-scopes ungated | SATISFIED | `test_mcp_gating.py` 4 passed |
| INTEG-01 | 09-06 | integration_provider capabilities reachable from unified create_runner path | SATISFIED | 4 thin MCP bridges; `test_integration_providers.py` 8 passed; no parallel vendor SDK |
| INTEG-02 | 09-06 | integrations scopes default none; run_capabilities records active scopes + servers | SATISFIED | `test_integration_scopes.py` 6 passed; engine.py:559-581 records scopes |

**Note:** REQUIREMENTS.md traceability table still shows `INTEG-01, INTEG-02 | Phase 9 | Pending` — a stale documentation entry. The requirement checkboxes above the table are correctly marked `[x]`, and 09-06 implementation + tests confirm INTEG-01/INTEG-02 complete.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TBD/FIXME/XXX debt markers found in any phase-modified file | — | — |

**Code review findings (09-REVIEW.md):** 1 Critical + 5 Warnings were identified post-execution. All 6 were fixed (09-REVIEW-FIX.md, iteration 1, commits 3ef3f05..e52f212):
- CR-01 (RunSandbox/LocalWorkspace infinite recursion): FIXED — RunSandbox.cleanup owns the rmtree; LocalWorkspace.teardown delegates one-way; regression tests added.
- WR-01 (git clone transport injection): FIXED — `GIT_ALLOW_PROTOCOL=file:https:ssh` + `--` separator + leading-`-` rejection.
- WR-02 (fire-and-forget lineage tasks): FIXED — `_PENDING_LINEAGE_TASKS` strong reference set in both `pack.py` and `inventory.py`.
- WR-03 (git_diff commits during resolver): FIXED — `git_diff` uses `git diff --cached <base>` (staged only); no commit side-effect.
- WR-04 (dead `_active_integration_servers` variable): FIXED — deleted from engine.py.
- WR-05 (MCP allow-list silent over-drop): FIXED — bare-name stripping + WARNING log on total drop.

3 Info findings (IN-01 slack_post ungated, IN-02 exec shell=True future risk, IN-03 repo_diff path-with-space edge case) are informational, out of scope for this phase's fix cycle per 09-REVIEW-FIX.md scope (`fix_scope: critical_warning`).

### Human Verification Required

None. Per project memory (`uat-mode-technical.md`): all phases are infra; verify with standard technical UAT. Per `defer-live-verification-to-milestone-end.md`: live Bedrock/Chromium/Postgres checks defer to end-of-milestone live pass. All must-haves are provably satisfied by offline test evidence and code inspection.

### Gaps Summary

No gaps. All 4 observable truths are VERIFIED. All 14 requirement IDs (RUNTIME-01..03, REPO-01..05, MCP-01..04, INTEG-01..02) are SATISFIED by implementation + green targeted tests. All code-review findings were fixed before verification. Import-linter, banned-pattern, migration-ledger, and 5-pipeline characterization parity gates are green. No debt markers exist in any phase-modified file.

---

_Verified: 2026-06-10_
_Verifier: Claude (gsd-verifier)_
