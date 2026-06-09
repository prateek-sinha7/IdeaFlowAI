# Phase 9: Local Workspace Runtime + Repo Workflows (no exec) [4A] — Specification

**Created:** 2026-06-10
**Ambiguity score:** 0.16 (gate: ≤ 0.20)
**Requirements:** 14 locked

## Goal

A first brownfield repo workflow runs end-to-end **locally with no execution** — clone → branch → inventory → agent reads/edits files → surfaces a file-tree + per-file diff — driven by a new `RuntimeEnvironment`/`Workspace` port layer (`LocalSandboxRuntime`), with a live MCP client (`langchain-mcp-adapters`) and GitHub/GitLab/Jira/Slack integration providers reachable from the unified `create_runner` path; prototype's 5-pipeline characterization stays byte/event-identical.

## Background

The engine reached SC-001 (Phase 7) and a hardened capability registry (Phase 8): all power lives in registered, declared capabilities and the kernel knows no workflow by name. Phase 9 is the **first net-new workflow class** — brownfield repo work — and the first use of the `Workspace`/`RuntimeEnvironment` abstraction the plan reserved a forward seam for.

Grounded current state (code-verified):

- **Ports** (`agents/capabilities/base.py`) cover strategies/validators/deliverables/context-providers/gates/hooks/tools/skills/prompt/runtime-adapter. There is **no** `RuntimeEnvironment`, `Workspace`, `ExecutionPolicy`, `IsolationProvider`, or `McpClientAdapter` port — all net-new this phase.
- **No `agents/runtime/` package** exists. `RunSandbox` (`app/agents/sandbox.py:49`) is the prototype's per-run disk dir; RUNTIME-02 folds it into a `has_git=False, exec=off` Workspace — no engine fork repo-vs-artifact.
- The **`workspaces` table already exists** (migration 0014, Phase 5) with `owner_id`/`workspace_id`/`kind=sandbox`/`repo_id` (nullable, marked *"Phase 9 forward field"*). Phase 9 **adds the `repositories` table** (next migration = **0017**) and persists repo-kind workspace + repository rows — it does **not** recreate `workspaces`.
- **Deliverable resolvers** (`capabilities/deliverables/`: single_file/serialized_sandbox/streamed_text/ppt) — Phase 9 adds `repo_diff`. **Context providers** (opendesign/previous_run) — Phase 9 adds `repo`.
- **MCP is backwards**: backend is an inbound MCP *server* only (`mcp.py:48`); no client, `langchain-mcp-adapters` not a dependency. **Integrations**: GitHub via a separate handoff pipeline (`handoff_github.py`) that **bypasses** the deepagents runtime; OpenDesign via `od_context`. All others absent.

The gap: the runtime/workspace port layer, the brownfield pipeline (clone→branch→inventory→read/edit/search→diff), the MCP-client + catalog + compile-validation, and the integration-provider capabilities — none exist yet.

## Requirements

> Scope decisions locked in the Socratic interview (all Phase-9 open decision records N2/N4/N5/N6/N7/N8/N10 resolved): **full live MCP + integrations** wired but **offline-verified** (live deferred to milestone-end); **both GitLab + GitHub** providers; **tree-sitter symbol index** with **grep/glob default**; **ephemeral per-run local** isolation + **in-process** job substrate; repo deliverable = **tree + per-file diff + summary**, **diff-only / no push**.

### Runtime & Workspace (RUNTIME-01..03)

1. **RuntimeEnvironment port + LocalSandboxRuntime** (RUNTIME-01): the runtime port and its local implementation.
   - Current: no `RuntimeEnvironment` port and no `agents/runtime/` package exist
   - Target: `agents/runtime/base.py` defines `RuntimeEnvironment` (read_file/write_file/search/exec_command/clone_repo/create_branch/git_diff/teardown) + `Workspace` + `ExecutionPolicy` + `IsolationProvider` ports; `agents/runtime/local.py` implements `LocalSandboxRuntime` over the per-run disk dir (clone into the run dir, local branch, `git diff`). `exec_command` is present in the port but **denied** by `ExecutionPolicy` (exec off, N3/Phase 4B). Impls self-register via `@register`; the kernel imports only the ports
   - Acceptance: `LocalSandboxRuntime` clones a local fixture, creates a branch, reads/writes/searches files, and produces a `git_diff`; calling `exec_command` under the default policy raises/denies; import-linter shows the kernel→ports direction unbroken (3 kept / 0 broken)

2. **One Workspace abstraction; RunSandbox refolded** (RUNTIME-02): a single fs+git+exec+policy abstraction, no engine fork.
   - Current: prototype's `RunSandbox` (`app/agents/sandbox.py:49`) is a bespoke per-run disk dir with no git/exec/policy concept; repo work would otherwise need a parallel path
   - Target: one `Workspace` (filesystem + optional git + optional exec + `ExecutionPolicy`, carrying `owner_id`/`workspace_id`); prototype's `RunSandbox` becomes a `Workspace(has_git=False, exec=off)`; the repo workflow uses `Workspace(has_git=True, exec=off)`. No engine fork for repo vs artifact (R3)
   - Acceptance: the 5-pipeline prototype/od_/revision/ppt/code-gen characterization snapshots remain **byte-identical + semantic-event-identical** with `RunSandbox` running as a `has_git=False` Workspace; a single code path serves both repo and artifact workspaces (no `if repo:` engine fork — grep)

3. **`repositories` + `workspaces` rows persisted** (RUNTIME-03): durable repo/workspace records.
   - Current: `workspaces` table exists (0014) but no rows are persisted at runtime for repo kind; `repo_id` is an unused nullable forward field; no `repositories` table exists
   - Target: additive migration **0017** adds `repositories` (id, owner_id, workspace_id, provider(`github`/`gitlab`/`local`), url, default_branch, auth_ref(scoped), created); a repo run persists a `repositories` row + a `kind=repo` `workspaces` row with `repo_id` FK set; both carry `owner_id` + `workspace_id`
   - Acceptance: running the sample repo workflow inserts exactly one `repositories` row and one `kind=repo` `workspaces` row linked by `repo_id`; `alembic upgrade head` then `downgrade -1` is reversible; the migration-ledger gate stays green

### Repo Inventory, Index, Context & Diff (REPO-01..05)

4. **RepoInventory** (REPO-01): structural map of the cloned repo.
   - Current: no repo inventory capability; agents have only flat `search()`
   - Target: a registered `repo_inventory` capability produces a file tree + language stats + dependency list, honoring ignore rules (`.gitignore` + `.flowinignore`), skipping binary files, applying size caps, with optional per-dir/file summaries; lineage-tracked as a typed artifact (`kind=repo_inventory`)
   - Acceptance: on a seeded fixture with a binary file + a `.flowinignore` entry, the inventory lists source files, excludes the ignored + binary files, reports language stats, and lists declared dependencies

5. **RepoIndex (tree-sitter symbol index, grep default)** (REPO-02): optional symbol index behind a port.
   - Current: no symbol/semantic index; no `tree-sitter` dependency
   - Target: `RepoIndex` is a registered, **optional** port; the impl is a **tree-sitter** symbol extractor (functions/classes/imports) across the repo's primary languages; **grep/glob remains the default** search, and the index is built only when the manifest opts in or the repo exceeds the documented N6 threshold. Embeddings/vector retrieval are out of scope
   - Acceptance: with the index disabled, search resolves via grep/glob; with the index enabled on the fixture, a symbol query returns the file+line of a known function/class; `tree-sitter` is imported only behind the `RepoIndex` capability module

6. **ContextPack + repo context provider** (REPO-03): targeted per-task context subset.
   - Current: no `ContextPack`; no `repo` context provider
   - Target: a `context_pack` capability (`kind=context_pack`) builds a **targeted subset** (files/snippets) for a task via a `context_selector` capability (the brownfield analog of `html_skeleton` compaction), lineage-tracked per task; surfaced to agents via a new `repo` `ContextProvider`
   - Acceptance: for a task naming a target file, the ContextPack contains that file (+ selector-chosen neighbors) and **excludes** unrelated files; the pack is recorded as a lineage-tracked artifact consumed by the agent step

7. **`repo_diff` DeliverableResolver** (REPO-04): the repo deliverable shape (N7).
   - Current: no `repo_diff` resolver; deliverables are single_file/serialized_sandbox/streamed_text/ppt only
   - Target: a registered `repo_diff` `DeliverableResolver` yields an app-builder-style **file tree + per-file unified diff + a change summary**; branch policy is **manifest-declared** (`base_branch`, `working_branch`), runtime-enforced; v1 is **diff-only — no commit/PR push** (deferred to N4)
   - Acceptance: after the agent edits ≥1 file, `repo_diff` returns a tree, a per-file unified diff containing the edit, and a summary; **no commit/push** is performed (git log on the working branch shows no new commit beyond the branch point, or the resolver never invokes push)

8. **Sample brownfield workflow end-to-end, no exec** (REPO-05): the phase accept proof.
   - Current: no brownfield repo workflow exists; only artifact-producing workflows (prototype/ppt/code-gen)
   - Target: a file-backed sample manifest runs **offline**: clone local fixture → `create_branch` → `repo_inventory` → an agent reads N files and **edits ≥1** (`write_files`, **no exec**) → `repo_diff` surfaces the tree + diff. Prototype is unaffected
   - Acceptance: the sample run completes end-to-end against a local fixture; the surfaced diff **contains the agent's edit**; **zero `exec` permission** is granted anywhere on the path (effective perms intersection has exec=off at every step); prototype characterization stays byte/event-identical

### MCP Client & Catalog (MCP-01..04)

9. **McpClientAdapter** (MCP-01): consume external MCP servers.
   - Current: backend is an inbound MCP *server* only; no MCP client; `langchain-mcp-adapters` not a dependency
   - Target: a registered `McpClientAdapter` (over `langchain-mcp-adapters` `MultiServerMCPClient`) connects to a server (stdio/SSE/HTTP), lists tools/resources/prompts, and **binds the allowed tools into the deepagents tool set** (INV-13 — MCP tools augment the mandated runtime, never replace it)
   - Acceptance: the adapter connects to a **stub** MCP server, lists its tools, and binds an allowed tool such that a deepagents agent can invoke it; offline (no live external server required in CI)

10. **Allow-listed server catalog + scoped creds** (MCP-02): the famous-server palette.
    - Current: no MCP catalog; only the GitHub-PAT handoff pattern exists
    - Target: an allow-listed catalog registers **GitHub, GitLab, Jira, Slack** as `user_allowed=true` (read-scoped) `mcp_server` capabilities, plus **Filesystem + Postgres registered with `user_allowed=false`**; each carries transport + exposed tools + **scoped per-owner credentials** (the `handoff.py:40` PAT pattern, owner-scoped/encrypted — never global) + a `user_allowed` flag; surfaced via `/api/capabilities`
    - Acceptance: `/api/capabilities` lists the catalog with correct `user_allowed` flags (FS/Postgres = false); a per-owner credential is stored scoped to its owner and is not readable cross-owner (ScopedStore denial test)

11. **McpCapabilityRegistry compile-validation** (MCP-03): the compiler gates MCP tool references.
    - Current: no MCP validation in the compiler
    - Target: the compiler validates a step's `tools.mcp` so it only names tools from servers the **step + owner** may reach; an unknown `server.tool` (or a not-owned/not-allowed server) → **compile error**
    - Acceptance: a manifest naming `unknown_server.tool` (or a `user_allowed=false` server in a user/db manifest) fails compilation with a clear error naming the offending `server.tool`; a valid reference compiles

12. **Powerful/write servers behind the security gate** (MCP-04): least-privilege for dangerous MCP.
    - Current: no gating exists (no MCP client)
    - Target: powerful servers (Filesystem, Postgres, anything with write/network) and **write-scopes** require the `security` gate + scoped creds + the `secrets` permission; **read-scopes** (e.g. `gitlab_read`, `jira_read`) need no gate
    - Acceptance: binding a Filesystem/Postgres tool (or a write-scope) without the `security` gate + `secrets` permission is rejected; binding a read-scoped GitHub/GitLab/Jira/Slack tool succeeds without the gate

### Integration Providers (INTEG-01..02)

13. **integration_provider capabilities from the unified runner** (INTEG-01): GitHub/GitLab/Jira/Slack reachable from `create_runner`.
    - Current: GitHub support lives in the separate handoff pipeline (`coding_agent.py:164`) that bypasses the deepagents runtime; Jira/Slack absent
    - Target: registered `integration_provider` capabilities for **GitHub + GitLab + Jira + Slack** make repo/issue/chat reachable from the **unified `create_runner` path**, not only the handoff pipeline
    - Acceptance: a workflow step declaring an integration resolves it from `create_runner` (the deepagents runner gains the integration's tools); the GitHub path no longer requires the bypass pipeline for the unified runner

14. **integrations tool-permission scopes** (INTEG-02): named scopes, default none, scoped creds.
    - Current: no `integrations` permission scope concept; the handoff PAT is the only scoped credential
    - Target: `integrations` tool-permission **scopes** (e.g. `gitlab_read`, `github_read`, `jira_read`, `slack_post`) default **none**; granting one requires the owner allow-list + scoped per-owner creds; persisted per run (`run_capabilities`, CAPRUN-01)
    - Acceptance: a step with no `integrations` grant cannot call any integration tool; granting `gitlab_read` binds only read tools; `run_capabilities` records the active integration scopes + MCP servers + runtime for the run

## Boundaries

**In scope:**
- `agents/runtime/base.py` ports — `RuntimeEnvironment`, `Workspace`, `ExecutionPolicy`, `IsolationProvider` (port lands; only ephemeral per-run/shared scope is impl'd)
- `agents/runtime/local.py` — `LocalSandboxRuntime` (clone/branch/diff/read/write/search; exec **denied** by policy)
- `RunSandbox` refolded as `Workspace(has_git=False, exec=off)` — one abstraction, no engine fork
- Additive migration **0017**: `repositories` table; wire `workspaces.repo_id` FK; persist repo + repo-kind workspace rows
- `RepoInventory` capability (tree/lang/deps/ignore-rules/binary-skip/size-caps/summaries)
- `RepoIndex` port + **tree-sitter** symbol-index impl (opt-in / N6-threshold; grep-glob default)
- `ContextPack` + `context_selector` capability + `repo` `ContextProvider`
- `repo_diff` `DeliverableResolver` (file tree + per-file diff + summary; manifest-declared branch; diff-only)
- A file-backed **sample brownfield workflow** manifest (clone→branch→inventory→read/edit→diff), no-exec
- `McpClientAdapter` over `langchain-mcp-adapters` `MultiServerMCPClient` (connect/list/bind into deepagents tools)
- Allow-listed MCP catalog: **GitHub/GitLab/Jira/Slack** (`user_allowed=true`, read-scoped) + **Filesystem/Postgres** (`user_allowed=false`); scoped per-owner creds
- `McpCapabilityRegistry` compile-validation (`tools.mcp` → unknown/not-allowed `server.tool` = compile error)
- `security` gate + `secrets` permission binding for powerful/write MCP servers
- `integration_provider` capabilities for **GitHub + GitLab + Jira + Slack** reachable from `create_runner`
- `integrations` tool-permission scopes (default none; owner allow-list + scoped creds; `run_capabilities` persistence)
- New dependencies behind ports: **`langchain-mcp-adapters`** (MCP client), **`tree-sitter`** (+ grammars)

**Out of scope:**
- `exec` / compile-test-lint validators — **Phase 4B / N3** (the `security` gate keeps exec off; `exec_command` exists in the port but is denied)
- **PR / commit push** to git hosts — **N4 / diff-only**; write creds + push deferred
- `sub_sandbox` / git-**worktree** isolation + engine fan-out — **Phase 11** (IsolationProvider port lands, but only per-run/shared scope is implemented)
- **Durable job queue/worker** — long jobs run **in-process** (FastAPI background task) for local v1; durable substrate is an infra follow-up (N8)
- **ECS / `EcsRuntime`** — v2 / separate spec (§27), behind the unchanged `RuntimeEnvironment` port
- **Live external-server / real-remote calls in CI** — accept runs **offline** against local fixtures + stub/contract MCP servers; real GitLab/GitHub/Jira/Slack calls run in the **end-of-milestone live pass** (project deferred-live-verification convention)
- **Embeddings / vector retrieval** — tree-sitter **symbol** index only this phase
- **DB-backed user-authored workflows** — file-backed hand-authored manifests only (Q5)
- The full §30 MCP catalog (Confluence/Notion/Linear/Sentry/Figma/Drive/web-search/Playwright) — beyond the GitHub/GitLab/Jira/Slack core this phase

## Constraints

- **INV-13 (runtime mandate):** every agent runs on LangChain `deepagents` (`create_deep_agent`, `deepagents==0.6.7`, adapter `langchain_deepagents`). MCP tools **bind into** the deepagents tool set via `McpClientAdapter`; no new agent runtime, no hand-rolled loop. The banned-pattern CI gate (R15) must stay green — `tree-sitter`/`langchain-mcp-adapters` are libraries, not deep-agent runtimes.
- **Hexagonal (Ports & Adapters):** the kernel depends only on capability ports; runtime/MCP/integration impls self-register via `@register`. Adding a capability = add a module + register — **no kernel edit**. Enforced by import-linter (3 kept / 0 broken).
- **Additive migrations only (Q3):** migration 0017 is additive; every new table (`repositories`) carries `owner_id` + `workspace_id`; `alembic upgrade`/`downgrade` reversible; migration-ledger gate green.
- **Default-deny ownership (INV-8):** repos/workspaces are owner-scoped through the existing `ScopedStore`; cross-owner clone/read/cred-access is rejected; anonymous runs use `anon:<session_id>`.
- **Least-privilege (INV-9):** `exec`/`network`/`secrets`/`spawn_subagents` default OFF; `mcp`/`integrations` default none. Effective perms = intersection(owner, workflow, step). MCP write-scopes + powerful servers gated by `security` + `secrets`.
- **No-exec invariant for this phase:** the entire repo path runs with exec off; the `security` gate denies exec/code-exec until N3 (Phase 4B).
- **Prototype parity (INV-3):** the 5-pipeline characterization snapshots stay byte-identical + semantic-event-identical — the repo path is **additive**, and `RunSandbox`-as-Workspace must not perturb prototype output.
- **Offline-verifiable accept (project convention):** the accept gate uses a local git fixture + stub/contract MCP servers; live external-server verification is deferred to the end-of-milestone live pass. Verify with the targeted parity/gate suite + `lint-imports`, not the full (offline-hanging) backend pytest.
- **No dual implementations (INV-12):** if any legacy path is superseded (e.g. the GitHub handoff bypass becomes the unified `integration_provider` path), the superseded code is deleted within this phase or its survival is explicitly justified — a banned-pattern/ledger entry tracks it.

## Acceptance Criteria

- [ ] `agents/runtime/base.py` defines `RuntimeEnvironment` + `Workspace` + `ExecutionPolicy` + `IsolationProvider` ports; the kernel imports only ports (import-linter 3 kept / 0 broken)
- [ ] `LocalSandboxRuntime` clones a local fixture, creates a branch, reads/writes/searches, and produces a `git_diff`; `exec_command` under the default policy is **denied**
- [ ] Prototype's `RunSandbox` runs as `Workspace(has_git=False, exec=off)`; the 5-pipeline characterization is **byte-identical + semantic-event-identical** (no re-baseline); no `if repo:` engine fork (grep → 0)
- [ ] Migration 0017 adds `repositories` (owner_id, workspace_id, provider, url, default_branch, auth_ref); a sample repo run persists one `repositories` row + one `kind=repo` `workspaces` row linked by `repo_id`; `upgrade`→`downgrade -1` reversible; migration-ledger green
- [ ] `RepoInventory` lists source files, **excludes** `.gitignore`/`.flowinignore` + binary files, applies size caps, and reports language stats + dependencies
- [ ] With the index disabled, search uses grep/glob; with the **tree-sitter** index enabled, a symbol query returns the file+line of a known symbol; `tree-sitter` is imported only behind the `RepoIndex` capability
- [ ] `ContextPack` returns a targeted file/snippet subset (target file + selector neighbors), **excludes** unrelated files, is lineage-tracked, and is surfaced via the `repo` `ContextProvider`
- [ ] `repo_diff` returns a file tree + per-file unified diff (containing the edit) + a change summary; **no commit/PR push** occurs
- [ ] The sample brownfield workflow runs end-to-end **offline**: clone fixture → branch → inventory → agent reads/edits ≥1 file (`write_files`, no exec) → `repo_diff`; the diff contains the edit; **exec=off** at every step
- [ ] `McpClientAdapter` (`MultiServerMCPClient`) connects to a **stub** server, lists tools, and binds an allowed tool into the deepagents tool set (offline)
- [ ] The catalog registers GitHub/GitLab/Jira/Slack (`user_allowed=true`) + Filesystem/Postgres (`user_allowed=false`); a per-owner MCP credential is stored scoped and is **not** readable cross-owner
- [ ] The compiler **rejects** a manifest naming `unknown_server.tool` (or a `user_allowed=false` server in a user/db manifest) with an error naming the offending `server.tool`; a valid reference compiles
- [ ] A powerful/write MCP server or write-scope requires the `security` gate + `secrets` permission; a read-scope (`gitlab_read`/`jira_read`) binds without the gate
- [ ] `integration_provider` capabilities for GitHub + GitLab + Jira + Slack resolve from the unified `create_runner` path (not only the handoff pipeline)
- [ ] `integrations` permission scopes default none; granting `gitlab_read` binds only read tools; `run_capabilities` records the active MCP servers + integration scopes + runtime for the run
- [ ] `lint-imports` (3 kept / 0 broken), banned-pattern (INV-13) green, migration-ledger green, and the offline parity/gate suite green

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                                                 |
|--------------------|-------|------|--------|-----------------------------------------------------------------------|
| Goal Clarity       | 0.88  | 0.75 | ✓      | 14 requirements w/ explicit IDs; §25 Phase 4A precise                  |
| Boundary Clarity   | 0.85  | 0.70 | ✓      | Full-MCP/both-providers/symbol-index IN; exec/push/worktree/ECS OUT    |
| Constraint Clarity | 0.80  | 0.65 | ✓      | tree-sitter + mcp-adapters deps, scoped creds, gate-writes, offline accept |
| Acceptance Criteria| 0.82  | 0.70 | ✓      | Sample flow concrete; offline-verifiable; 16 pass/fail checks          |
| **Ambiguity**      | 0.16  | ≤0.20| ✓      | All Phase-9 decision records (N2/N4/N5/N6/N7/N8/N10) resolved          |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

| Round | Perspective     | Question summary                              | Decision locked                                                                 |
|-------|-----------------|-----------------------------------------------|---------------------------------------------------------------------------------|
| 1     | Researcher/Boundary | MCP+integration depth this phase?         | **Full live MCP + integrations** (overrides plan's scaffold-only default)        |
| 1     | Boundary        | Git host (N4) + clone source?                 | **Both GitLab + GitHub** provider adapters; diff-only/no-push                    |
| 1     | Constraint      | Repo scale (N6/N10) + index approach?         | **Build a real symbol index** (not grep-only)                                   |
| 2     | Boundary        | Live-MCP catalog + creds + security gate?     | Core = **GitHub/GitLab/Jira/Slack** (+ FS/Postgres `user_allowed=false`); scoped per-owner creds; **gate writes** |
| 2     | Failure Analyst | Accept offline vs live (CI)?                  | **Offline accept** (local fixture + stub servers); live deferred to milestone-end |
| 2     | Constraint      | Symbol-index tech + default path?             | **tree-sitter multi-lang**, **grep/glob stays default**, index opt-in/threshold  |
| 3     | Boundary Keeper | repo_diff shape (N7) + branch/PR policy (N5)? | **Tree + per-file diff + summary**; manifest-declared branch; **diff-only, no push** |
| 3     | Constraint      | Isolation (N2) + long-job substrate (N8)?     | **Ephemeral per-run** local Workspace + **in-process** job; worktree/queue deferred |
| 3     | Boundary Keeper | What does the sample workflow concretely do?  | **Clone→branch→inventory→read/edit ≥1 file (no exec)→repo_diff**; accept = diff contains edit + prototype parity + zero exec |

---

*Phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a*
*Spec created: 2026-06-10*
*Next step: /gsd-discuss-phase 9 — implementation decisions (how to build what's specified above: runtime port surface, tree-sitter wiring, MCP adapter/catalog shape, plan/wave breakdown for the 6 sub-plans 09-01…09-06)*
