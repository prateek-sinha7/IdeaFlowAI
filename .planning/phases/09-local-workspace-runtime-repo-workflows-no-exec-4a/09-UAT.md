---
status: complete
phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
source: [09-01-SUMMARY.md, 09-02-SUMMARY.md, 09-03-SUMMARY.md, 09-04-SUMMARY.md, 09-05-SUMMARY.md, 09-06-SUMMARY.md]
started: 2026-06-10T12:03:32Z
updated: 2026-06-10T12:14:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Local workspace runtime round-trip (no exec)
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_local_runtime.py -q
  All tests pass: LocalSandboxRuntime clones the local git fixture into a per-run dir,
  creates a branch, round-trips read/write/search, and produces a non-empty unified
  git_diff. exec_command raises PermissionError under the default policy
  (exec=False/network=False/secrets=[]). Traversal relpaths (../escape) raise.
  ("runtime_env","local") is reachable via the capability registry.
result: pass
evidence: 8 passed in 0.59s (run 2026-06-10, user delegated execution to Claude)

### 2. Repositories persistence + RunSandbox refold (migration 0017)
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_repositories_persistence.py tests/agents/test_migration_ledger.py -q
  All pass: ScopedStore.create_repository writes one repositories row + links the
  kind=repo workspace via repo_id; a cross-owner repository read raises PermissionError;
  the migration-ledger ratchet (R1 RunSandbox refold row) is green. Alembic has a single
  head (0017) and 0017 is reversible (proven in-suite: upgrade → downgrade -1 → upgrade).
result: pass
evidence: 23 passed, 5 skipped in 1.24s (skips are benign ledger placeholders — "no ☑ grep rows yet")

### 3. Repo intelligence: inventory, tree-sitter index, context pack
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_repo_index.py tests/agents/test_repo_inventory.py tests/agents/test_context_pack.py -q
  All pass: repo_index search() (grep/glob via the Workspace handle) always available;
  symbol_query() returns file+line+kind after build(); repo_inventory returns file tree +
  language stats + dependency list honoring .gitignore/.flowinignore, skipping binaries,
  enforcing size caps; context_pack composes target+neighbors deterministically (no
  embeddings); the repo ContextProvider surfaces the pack as a repo_context block and
  PROPAGATES cross-owner PermissionError.
result: pass
evidence: 18 passed in 0.21s

### 4. Brownfield workflow end-to-end with zero engine edits (SC-001)
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_repo_diff.py tests/agents/test_sample_brownfield_workflow.py -q
  All pass: the file-backed sample_brownfield manifest (a NON-prototype workflow declaring
  context_providers: [repo] + write_files step + deliverable: repo_diff) compiles against
  the registry and runs end-to-end offline with the scripted model. The surfaced repo_diff
  contains the agent's edit (tree + per-file diff map + files_changed/lines_added summary).
  exec is off at every compiled step. The resolver creates NO new commit on work and origin
  gains NO work branch (diff-only, N4). Zero engine-package edits asserted by the test.
result: pass
evidence: 7 passed in 1.48s

### 5. MCP integration: client adapter, catalog, compile-validation, gating
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_mcp_client.py tests/agents/test_mcp_catalog.py tests/agents/test_mcp_compile_validation.py tests/agents/test_mcp_gating.py -q
  All pass: McpClientAdapter connects to the in-repo stdio FastMCP stub offline
  (connect/list/invoke echo+add over REAL stdio), bound tools AUGMENT create_deep_agent
  (INV-13 — no agent loop in the module); the mcp_server catalog flags
  filesystem/postgres user_allowed=False (powerful) vs github/gitlab/jira/slack read-scoped
  True; McpCredential is owner-scoped + Fernet-encrypted with cross-owner read denied
  (PermissionError); an unknown server.tool ref in a manifest fails compile with a
  CompilerError naming the ref; a powerful server without security+secrets fails compile.
result: pass
evidence: 19 passed in 3.05s (real stdio stub transport)

### 6. Integration scopes + CodingAgent bypass deletion (handoff intact)
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_integration_providers.py tests/agents/test_integration_scopes.py tests/unit/test_handoff_agents.py tests/integration/test_handoff_contract.py -q
  All pass: integrations scopes default none → zero tools bound; granting gitlab_read
  binds ONLY gitlab read tools via the unified MCP prewarm; the effective-perms
  intersection gates ungranted scopes; a run_capabilities row records active scopes +
  activated servers. The CodingAgent bypass is deleted
  (grep -rn "class CodingAgent" backend/app → 0) while HandoffCoder flows through
  create_deep_agent and the live /api/handoff contract test stays green (routers retained).
result: pass
evidence: 42 passed in 1.85s; `grep -rn "class CodingAgent" app/ agents/` → 0 hits

### 7. Phase-wide invariants: parity, runtime mandate, import boundaries
expected: |
  cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_od_ppt.py tests/agents/test_characterization_prototype_revision.py tests/agents/test_characterization_app_builder.py tests/agents/test_banned_patterns.py tests/agents/test_registry_capabilities.py -q
  (with SNAPSHOT_UPDATE unset) All pass: the 5 characterization pipelines stay
  byte/event-identical (INV-3); no banned patterns (no hand-rolled deep agent, INV-13);
  the registry drift guard expects 50 capabilities including the 16 added this phase.
  /opt/homebrew/bin/lint-imports reports 4 contracts kept, 0 broken (kernel imports only
  ports; runtime/workflows/capabilities never import the execution kernel or web layer).
result: pass
evidence: 94 passed in 35.69s with `env -u SNAPSHOT_UPDATE`; lint-imports → Contracts: 4 kept, 0 broken

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
