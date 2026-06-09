---
phase: 9
slug: local-workspace-runtime-repo-workflows-no-exec-4a
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-10
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from `09-RESEARCH.md` § Validation Architecture (Nyquist). **Offline accept** — local git fixtures + an in-repo stdio stub MCP server; live external calls deferred to the end-of-milestone live pass.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`@pytest.mark.asyncio`) |
| **Config file** | `backend/pyproject.toml` (`[tool.pytest...]`) |
| **Quick run command** | `cd backend && python3.11 -m pytest tests/agents/<targeted file> -x` |
| **Full suite command** | targeted offline parity + gate suite (see below) — **NOT** full backend pytest (hangs offline: Chromium/Bedrock/Postgres-gated) |
| **Estimated runtime** | ~35s (targeted parity/gate suite) |

**Parity suite (strict INV-3):** the 5 characterization files (`tests/agents/test_characterization_*.py`) + `test_sandbox_deliverable.py` + `test_manifest_parity.py`. Oracle = the `pipeline_complete` event `final_output` byte-snapshot (`serialize_sandbox_deliverable` raw bytes, `sandbox.py:236`) + the normalized event-stream golden (R-B).

**Gate suite:** `lint-imports` (`/opt/homebrew/bin/lint-imports`, 3→4 kept / 0 broken), `test_banned_patterns.py` (INV-13 — tree-sitter/mcp-adapters are libs, not runtimes), `test_migration_ledger.py` (0016→0017 chain + CodingAgent-deletion + retained-endpoint rows).

---

## Sampling Rate

- **After every task commit:** Run the targeted test file for the task (`-x`).
- **After every plan wave:** Run the parity suite + the gate suite.
- **Before `/gsd-verify-work`:** Full offline targeted suite + `lint-imports` green.
- **Max feedback latency:** ~35 seconds.

---

## Per-Task Verification Map

> Mapped at plan/requirement granularity (per-task IDs are assigned by the planner). Acceptance-criterion → offline sampling point from `09-RESEARCH.md`. File Exists ❌ W0 = the test file is a Wave 0 dependency created before/with its plan.

| Plan | Wave | Requirement | Acceptance (abbrev) | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|------|------|-------------|---------------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01 | 1 | RUNTIME-01 | `base.py` ports; kernel imports only ports | T-V1 | hexagonal boundary; least-privilege default policy | gate | `cd backend && lint-imports` (new `agents.runtime` contract, 0 broken) | ❌ W0 | ⬜ pending |
| 09-01 | 1 | RUNTIME-01 | `LocalSandboxRuntime` clone/branch/read/write/search/diff; **exec DENIED** | T-V12 / T-exec | `exec_command` raises under default `ExecutionPolicy` | unit | `python3.11 -m pytest tests/agents/test_local_runtime.py -x` | ❌ W0 | ⬜ pending |
| 09-02 | 2 | RUNTIME-02 | 5-pipeline **byte+event parity**; no `if repo:` fork | T-V5 | refold must not perturb prototype output | parity | parity suite + `grep -rn "if repo" agents/execution_engine/` → 0 | ❌ W0 | ⬜ pending |
| 09-02 | 2 | RUNTIME-03 | 0017 adds `repositories`; one row each; `upgrade`→`downgrade -1` reversible; ledger green | T-V4 | owner_id+workspace_id on every row; additive | integration | `alembic upgrade head && alembic downgrade -1` (local DB) + `test_migration_ledger.py` | ❌ W0 | ⬜ pending |
| 09-03 | 3 | REPO-01 | `RepoInventory` lists src; excludes `.gitignore`/`.flowinignore`+binary; size caps; lang stats | T-V12 | path-traversal rejection; repo-relative only | unit | `python3.11 -m pytest tests/agents/test_repo_inventory.py -x` | ❌ W0 | ⬜ pending |
| 09-03 | 3 | REPO-02 | grep default; tree-sitter index → file+line; tree-sitter imported only behind capability | T-V12 | heavy dep isolated behind capability module | unit | `test_repo_index.py` + `grep -rn "import tree_sitter" agents/ app/` only the capability | ❌ W0 | ⬜ pending |
| 09-03 | 3 | REPO-03 | `ContextPack` targeted subset; excludes unrelated; lineage-tracked; via `repo` provider | — | — | unit | `python3.11 -m pytest tests/agents/test_context_pack.py -x` | ❌ W0 | ⬜ pending |
| 09-04 | 4 | REPO-04 | `repo_diff` tree+per-file diff(edit)+summary; **no push** | T-V12 | diff-only; no commit/PR push | unit | `test_repo_diff.py` — diff contains the edit; `git log` working branch shows no new commit | ❌ W0 | ⬜ pending |
| 09-04 | 4 | REPO-05 | sample workflow offline end-to-end; diff has edit; **exec=off everywhere** | T-exec | effective-perms exec=off at every step | integration | `python3.11 -m pytest tests/agents/test_sample_brownfield_workflow.py -x` | ❌ W0 | ⬜ pending |
| 09-05 | 5 | MCP-01 | `McpClientAdapter` connects to **STUB**, lists, binds an allowed tool offline | T-V2 | INV-13 — binds into deepagents tools, never replaces | unit | `test_mcp_client.py` w/ the in-repo stdio stub server | ❌ W0 | ⬜ pending |
| 09-05 | 5 | MCP-02 | catalog `user_allowed` flags (FS/PG=false); per-owner cred not cross-owner readable | T-V4 / T-cred | `ScopedStore` default-deny; scoped per-owner encrypted creds | unit | `test_mcp_catalog.py` + `ScopedStore` cross-owner denial test | ❌ W0 | ⬜ pending |
| 09-05 | 5 | MCP-03 | compiler rejects `unknown_server.tool`/not-allowed; valid compiles | T-V5 | INV-4 capability-reference validation | unit | `test_mcp_compile_validation.py` — `CompilerError` names offending `server.tool` | ❌ W0 | ⬜ pending |
| 09-05 | 5 | MCP-04 | write/powerful needs `security`+`secrets`; read-scope ungated | T-mcp-priv | gate FS/PG + write-scopes; read-scopes ungated | unit | `test_mcp_gating.py` — FS/PG bind rejected w/o gate; `gitlab_read` binds | ❌ W0 | ⬜ pending |
| 09-06 | 6 | INTEG-01 | github/gitlab/jira/slack resolve from `create_runner` | T-V2 | one external-tool mechanism (MCP); no SDK dual path | unit | `python3.11 -m pytest tests/agents/test_integration_providers.py -x` | ❌ W0 | ⬜ pending |
| 09-06 | 6 | INTEG-02 | `integrations` default none; `gitlab_read` binds read-only; `run_capabilities` records scopes+servers+runtime | T-V4 | default-none; owner allow-list + scoped creds | unit | `test_integration_scopes.py` + assert `record_capabilities` row | ❌ W0 | ⬜ pending |
| ALL | — | (cross-cutting) | lint-imports/banned-pattern/migration-ledger/parity all green | — | the phase-gate intersection | gate | the gate suite + the parity suite | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/agents/test_local_runtime.py` + a local git-fixture seeder (REQ RUNTIME-01/02)
- [ ] `tests/agents/test_repo_inventory.py` + `tests/agents/test_repo_index.py` (offline tree-sitter smoke) (REPO-01/02)
- [ ] `tests/agents/test_context_pack.py` / `test_repo_diff.py` / `test_sample_brownfield_workflow.py` (REPO-03/04/05)
- [ ] `tests/agents/fixtures/stub_mcp_server.py` + `test_mcp_client.py` / `test_mcp_catalog.py` / `test_mcp_compile_validation.py` / `test_mcp_gating.py` (MCP-01..04)
- [ ] `tests/agents/test_integration_providers.py` / `test_integration_scopes.py` (INTEG-01/02)
- [ ] New import-linter `forbidden` contract for `agents.runtime` in `backend/pyproject.toml`
- [ ] Migration-ledger row(s) for the `CodingAgent` deletion + the retained `/api/handoff`-endpoint justification
- [ ] Dependency installs (`langchain-mcp-adapters`, `tree-sitter`, `tree-sitter-language-pack`) gated by `checkpoint:human-verify` (slopcheck unavailable offline)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live GitLab/GitHub/Jira/Slack/MCP calls | MCP-01..04 / INTEG-01..02 | Offline accept by project convention; live deferred to milestone-end | End-of-milestone live pass against real servers with scoped creds |
| `tree-sitter-language-pack` offline wheel install (no lazy download) | REPO-02 | Could not install offline in research; lazy-grammar-download risk | Wave 0 (09-03): install offline, assert `get_parser('python')` imports without network; fall back to per-language wheels |
| Alembic `upgrade`→`downgrade -1` round-trip | RUNTIME-03 | Needs a live DB; offline targeted suite excludes Postgres-gated tests | 09-02: run against throwaway Postgres/SQLite, or rely on the migration-ledger structural assertion |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
