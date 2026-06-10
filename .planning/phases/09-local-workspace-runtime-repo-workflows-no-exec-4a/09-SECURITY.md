---
phase: 9
slug: local-workspace-runtime-repo-workflows-no-exec-4a
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-10
---

# Phase 9 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (all 6 PLAN.md files carry `<threat_model>` blocks).
> All mitigations evidence-verified against the live codebase on 2026-06-10 — named tests
> executed (104 passed / 0 failed), gates run (lint-imports 4/0, banned-patterns,
> migration ledger), and greps confirmed; not closed on SUMMARY prose alone.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| agent → Workspace filesystem | untrusted relpaths (clone/read/write/search/edit) must resolve repo-relative under the run root | repo file paths + content |
| workflow step → `exec_command` | command execution denied by default policy until N3; no step on the brownfield path grants exec | command strings (denied) |
| kernel → runtime impl | kernel imports only ports; impl reached via the Workspace handle, never imported | capability calls |
| run → DB (repositories/workspaces) | every row carries `owner_id` + `workspace_id`; cross-owner reads denied via `ScopedStore` default-deny | repo/workspace rows, artifacts |
| migration upgrade/downgrade | DDL additive + reversible only | schema |
| capability → repo filesystem | inventory/index/pack walks stay repo-relative, skip binary, honor `.gitignore`/`.flowinignore`, size-capped | repo tree content |
| heavy dep (tree-sitter) → kernel | tree-sitter import-isolated app-side (`app/agents/repo_index/` only) | parsed ASTs |
| resolver → git | only the Workspace owns git; `repo_diff` reads via the handle, diff-only — never commits/pushes | diffs |
| manifest → MCP tool reference | per-`server.tool` compile-validation against reachable servers | tool refs |
| run → external MCP server | powerful/write servers (`filesystem`, `postgres`) `user_allowed=False` + `security` gate + `secrets` permission; read-scopes ungated | external tool I/O |
| owner → MCP / integration credentials | per-owner, Fernet-encrypted, `ScopedStore` default-deny; cross-owner read raises `PermissionError` | secrets |
| MCP/integration tools → deepagents runtime | tools bind INTO `create_deep_agent` (augment, never replace — INV-13) | tool bindings |
| run → external integrations (github/gitlab/jira/slack) | `integrations` scopes default none; read-scopes bind read tools only; write-scopes follow the security+secrets gate | external API calls |
| deletion → live `/api/handoff` surface | routers + `UserGithubCredential` retained (external consumers); deletion scoped to the CodingAgent bypass only | IDE handoff API |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-09-01-01 | Tampering | `Workspace.path_for` / clone target | mitigate | traversal-rejection under the run root; `tests/agents/test_local_runtime.py::test_path_traversal_rejected` passing | closed |
| T-09-01-02 | Elevation of Privilege | `exec_command` | mitigate | default `ExecutionPolicy(exec=False)` raises `PermissionError`; `test_local_runtime.py::test_exec_command_denied_under_default_policy` passing | closed |
| T-09-01-03 | Tampering | kernel↔app import direction | mitigate | import-linter contract `agents.runtime ↛ [agents.execution_engine, app]`; lint-imports 4 kept / 0 broken (2026-06-10) | closed |
| T-09-01-SC | Tampering | dependency supply chain (09-01) | accept | no `pyproject.toml` dependency added in 09-01 — see Accepted Risks Log AR-09-01 | closed |
| T-09-02-ID | Information Disclosure | cross-owner repo/workspace read | mitigate | `ScopedStore` default-deny `WHERE owner_id AND workspace_id`; `test_repositories_persistence.py::test_cross_owner_repo_read_is_denied` passing | closed |
| T-09-02-01 | Tampering | migration 0017 reversibility | mitigate | additive-only; `0017_repositories_repo_workspace.py` has `downgrade()`; migration-ledger gate green | closed |
| T-09-02-02 | Tampering | `RunSandbox.path_for` traversal (through refold) | mitigate | traversal-rejection preserved; `test_path_traversal_rejected` passing post-refold | closed |
| T-09-02-03 | Tampering | prototype parity perturbation (INV-3) | mitigate | 5 characterization snapshot suites passing with `SNAPSHOT_UPDATE` unset (2026-06-10) | closed |
| T-09-03-01 | Tampering | inventory/index path traversal | mitigate | reads via Workspace handle + binary-skip + ignore-exclusion + size-caps; `test_repo_inventory.py` passing | closed |
| T-09-03-02 | Tampering | tree-sitter import leak into kernel | mitigate | `import tree_sitter` grep → 0 outside `app/agents/repo_index/`; lint-imports 4/0 | closed |
| T-09-03-ID | Information Disclosure | cross-owner ContextPack/artifact read | mitigate | `assert_owns` propagates `PermissionError`; `test_context_pack.py::test_repo_provider_propagates_cross_owner_permission_error` passing | closed |
| T-09-03-SC | Tampering | slopsquatted dep (`tree-sitter`, `tree-sitter-language-pack`) | mitigate | blocking human-verify checkpoint completed before the `pyproject.toml` add (09-03 Task 1, recorded in 09-03-SUMMARY) | closed |
| T-09-04-01 | Elevation of Privilege | exec on the brownfield path | mitigate | no step grants exec; `test_sample_brownfield_workflow.py::test_sample_brownfield_exec_off_at_every_step` asserts `step.tools.exec is False` at every step | closed |
| T-09-04-02 | Tampering | path traversal in edit/diff | mitigate | edits via `Workspace.path_for`; diff reads via the handle; traversal + `test_repo_diff.py` passing | closed |
| T-09-04-03 | Tampering | unintended commit/push | mitigate | `repo_diff` diff-only: `git (commit\|push)` grep → 0 in `agents/capabilities/deliverables/repo_diff.py`; `test_repo_diff.py` asserts head/commit-count unchanged + origin gains no `work` branch | closed |
| T-09-04-04 | Tampering | prototype parity perturbation | mitigate | repo path additive; `test_characterization_prototype.py` passing alongside the sample run | closed |
| T-09-04-SC | Tampering | dependency supply chain (09-04) | accept | no dependency added in 09-04 — see Accepted Risks Log AR-09-04 | closed |
| T-09-05-EoP | Elevation of Privilege | filesystem/postgres/write MCP server | mitigate | `user_allowed=False` for `filesystem`/`postgres` in `agents/capabilities/registry.py:121-122` + security gate + `secrets` permission (MCP-04); `test_mcp_gating.py` passing | closed |
| T-09-05-ID | Information Disclosure | cross-owner MCP credential read | mitigate | `McpCredential` owner-scoped + Fernet-encrypted (`app/core/crypto.py`); `test_mcp_catalog.py::test_cross_owner_mcp_credential_read_is_denied` passing | closed |
| T-09-05-Tamper | Tampering | unvalidated `server.tool` in manifest | mitigate | per-`server.tool` compile-validation raising `CompilerError`; `test_mcp_compile_validation.py` passing | closed |
| T-09-05-INV13 | Elevation of Privilege | MCP tool replacing the runtime | mitigate | tools bind INTO `create_deep_agent` via `get_tools()`; `test_banned_patterns.py` passing | closed |
| T-09-05-SC | Tampering | slopsquatted dep (`langchain-mcp-adapters`, transitive `mcp`) | mitigate | blocking human-verify checkpoint completed before the add + `<0.3` pin away from day-old release (09-05 Task 1, recorded in 09-05-SUMMARY) | closed |
| T-09-06-01 | Elevation of Privilege | unscoped integration tool binding | mitigate | `integrations` scopes default none; `gitlab_read` binds read tools only; effective-perms intersection gates binding; `test_integration_scopes.py` passing | closed |
| T-09-06-ID | Information Disclosure | cross-owner integration credential read | mitigate | per-owner scoped creds (`UserGithubCredential`/`ScopedStore` precedent); cross-owner read raises `PermissionError`; `test_integration_scopes.py` passing | closed |
| T-09-06-INV13 | Elevation of Privilege | CodingAgent bypass skipping the runtime | mitigate | bypass DELETED (`class CodingAgent` absent from codebase); `HandoffCoder` flows through `create_deep_agent`; banned-pattern + ledger gates green | closed |
| T-09-06-Avail | Denial of Service | deleting the live `/api/handoff` router | mitigate | routers + `UserGithubCredential` RETAINED (ledger D10); `tests/integration/test_handoff_contract.py` passing | closed |
| T-09-06-Parity | Tampering | characterization parity perturbation | mitigate | deletion removed only the bypass; 5 snapshot suites byte/event-identical (`SNAPSHOT_UPDATE` unset) | closed |
| T-09-06-SC | Tampering | dependency supply chain (09-06) | accept | no dependency added in 09-06 (MCP dep landed gated in 09-05) — see Accepted Risks Log AR-09-06 | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-09-01 | T-09-01-SC | 09-01 adds no `pyproject.toml` dependency; the 3 `[ASSUMED]` deps land gated in 09-03/09-05 behind blocking human-verify checkpoints | 09-01 PLAN `<threat_model>` (plan-time, user-approved) | 2026-06-10 |
| AR-09-04 | T-09-04-SC | 09-04 adds no dependency | 09-04 PLAN `<threat_model>` (plan-time, user-approved) | 2026-06-10 |
| AR-09-06 | T-09-06-SC | 09-06 adds no dependency (the MCP dep landed human-verified + pinned in 09-05) | 09-06 PLAN `<threat_model>` (plan-time, user-approved) | 2026-06-10 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-10 | 28 | 28 | 0 | gsd-secure-phase (orchestrator, evidence-verified: 104 tests passed, lint-imports 4/0, greps clean) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-10
