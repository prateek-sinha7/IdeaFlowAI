# Phase 9: Local Workspace Runtime + Repo Workflows (no exec) [4A] - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning
**Mode:** Four HOW-level gray areas deep-dived interactively (the user departed from the prior-phase "lock all" default and chose to discuss each). **Every decision below resolved to the `plan.md`-grounded recommendation** — consistent with the standing project directive ("everything from plan.md must be honored — nothing dropped"). Review/edit this file before planning if any needs changing.

<domain>
## Phase Boundary

The **first net-new workflow class** — brownfield repo work — and the first use of the `Workspace`/`RuntimeEnvironment` abstraction the plan reserved a forward seam for. A file-backed sample repo workflow runs end-to-end **locally with no execution**: clone local fixture → `create_branch` → `repo_inventory` → an agent reads N files and **edits ≥1** (`write_files`, **no exec**) → `repo_diff` surfaces a file-tree + per-file unified diff + summary. Driven by a new `RuntimeEnvironment`/`Workspace` port layer (`LocalSandboxRuntime`), with a live MCP **client** (`langchain-mcp-adapters`) and GitHub/GitLab/Jira/Slack **integration providers** reachable from the unified `create_runner` path.

**Additive, parity-preserving.** Prototype's 5-pipeline characterization (prototype/od_/revision/ppt/code-gen) stays **byte-identical + semantic-event-identical**; the repo path never perturbs it. Everything is **offline-verified** — local git fixtures + an in-repo stub MCP server; live external-server calls are deferred to the end-of-milestone live pass.

**What this phase is NOT:** no `exec` (the `security` gate keeps it off until N3/Phase 4B — `exec_command` lands in the port but is denied), no commit/PR **push** (diff-only, N4), no git-worktree/sub-sandbox isolation or engine fan-out (Phase 11 — `IsolationProvider` port lands but only per-run/shared scope is impl'd), no durable job queue (in-process FastAPI background task for v1), no ECS (`EcsRuntime` is v2 behind the unchanged port), no embeddings/vector retrieval (tree-sitter **symbol** index only), no DB-backed user workflows (file-backed manifests only).

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**14 requirements are locked** (RUNTIME-01..03, REPO-01..05, MCP-01..04, INTEG-01..02). See `09-SPEC.md` for full requirements, boundaries, and 16 acceptance criteria. Ambiguity 0.16 (gate ≤ 0.20); all Phase-9 decision records (N2/N4/N5/N6/N7/N8/N10) resolved in the Socratic interview.

Downstream agents MUST read `09-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
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

**Out of scope (from SPEC.md):**
- `exec` / compile-test-lint validators — **Phase 4B / N3** (the `security` gate keeps exec off; `exec_command` exists in the port but is denied)
- **PR / commit push** to git hosts — **N4 / diff-only**; write creds + push deferred
- `sub_sandbox` / git-**worktree** isolation + engine fan-out — **Phase 11** (`IsolationProvider` port lands, but only per-run/shared scope is implemented)
- **Durable job queue/worker** — long jobs run **in-process** (FastAPI background task) for local v1; durable substrate is an infra follow-up (N8)
- **ECS / `EcsRuntime`** — v2 / separate spec (§27), behind the unchanged `RuntimeEnvironment` port
- **Live external-server / real-remote calls in CI** — accept runs **offline** against local fixtures + stub/contract MCP servers; real GitLab/GitHub/Jira/Slack calls run in the **end-of-milestone live pass**
- **Embeddings / vector retrieval** — tree-sitter **symbol** index only this phase
- **DB-backed user-authored workflows** — file-backed hand-authored manifests only (Q5)
- The full §30 MCP catalog (Confluence/Notion/Linear/Sentry/Figma/Drive/web-search/Playwright) — beyond the GitHub/GitLab/Jira/Slack core this phase

</spec_lock>

<decisions>
## Implementation Decisions

> SPEC locked the 14-requirement WHAT + the strategic decisions (full-MCP+integrations / both-providers / tree-sitter-symbol-index / ephemeral-per-run+in-process / tree+diff+summary diff-only). Below are the **HOW** decisions from this discussion — the four areas the user deep-dived (A–D), each locked to its `plan.md`-grounded recommendation, plus the supporting decisions (E–G) those areas imply.

### Area A — Runtime port surface & RunSandbox refold (RUNTIME-01/02) ⟵ gray area 1

- **D-01: `RuntimeEnvironment` = the provisioner port (`create_workspace` / `teardown`); `Workspace` = the fs+git+exec+`ExecutionPolicy` facade carrying `owner_id`/`workspace_id`, holding a back-reference to its `RuntimeEnvironment`.** `LocalSandboxRuntime` implements `RuntimeEnvironment` over the per-run disk dir and returns a local-backed `Workspace`. This is the **ECS-swap seam** (§27): a later `EcsRuntime.create_workspace()` returns a remote-backed `Workspace` with **zero engine change**. `Workspace` exposes `read_file`/`write_file`/`search`/`clone_repo`/`create_branch`/`git_diff`/`exec_command`/`teardown`; `exec_command` is present but **denied** by the default `ExecutionPolicy` (exec off until N3). `IsolationProvider.allocate(scope)` lands as a port but only `shared_read`/per-run scope is implemented (`sub_sandbox`/`worktree` → Phase 11).
  - *Rationale:* plan.md §6 line 469–490 makes this split explicit — `Workspace` is "backed by a `RuntimeEnvironment`" (`runtime: RuntimeEnvironment`, line 480), `IsolationProvider.allocate(...) -> Workspace` (line 486). plan.md §14 line 652–660 + INV-6 line 255 confirm "interfaces now, `LocalSandboxRuntime` only". Cleanest infra-swap boundary.
  - *Rejected:* a single merged `RuntimeEnvironment` with all fs/git/exec methods (blurs the ECS boundary — v2 would have to re-introduce `Workspace`); `Workspace.create()` static factory self-provisioning (no clean place for the ECS provisioner to plug in).
  - **Researcher directive (port-vs-impl placement — the import-linter call):** `09-SPEC.md` puts BOTH `agents/runtime/base.py` (ports) AND `agents/runtime/local.py` (`LocalSandboxRuntime`) under the **kernel-side** `agents/runtime/` package, with "the kernel imports only the ports." But plan.md §32 **line 894** says `new app/agents/runtime/ — base.py (...ports), local.py (LocalSandboxRuntime)` — i.e. **app-side**. The existing `RunSandbox` is app-side (`backend/app/agents/sandbox.py:49`). Resolve via the import-linter contract (mirrors the Phase-8 Validator split: port kernel-side in `capabilities/base.py`, heavy impl app-side in `app/agents/validators/`, reached via the `KernelServices` handle): **lock the PORTS to `backend/agents/runtime/base.py` (kernel-importable, import-linter authority — the SPEC's "kernel imports only ports")**; confirm whether `LocalSandboxRuntime` (`local.py`) must reach `app.*` (the existing sandbox/disk utilities) → if so it lives **app-side** (`backend/app/agents/runtime/local.py`) and self-registers via `@register`, reached via the handle; if it's pure-stdlib (subprocess `git`, `pathlib`) it may sit kernel-side. The 3-kept/0-broken import-linter result is the gate either way.

- **D-02: Prototype's `RunSandbox` (`backend/app/agents/sandbox.py:49`) refolds IN-PLACE — its internals re-implement on top of `Workspace(has_git=False, exec=off)`; the `RunSandbox` name survives as a thin alias/subtype so existing prototype/ppt/revision call sites are untouched (parity-safest).** Move-don't-copy (INV-12): the bespoke per-run disk logic is **deleted** and delegated to `Workspace` — not a dual impl. The repo workflow uses `Workspace(has_git=True, exec=off)`; one code path serves both (no `if repo:` engine fork — grep → 0).
  - *Rationale:* plan.md §14 line 654–655 ("`RunSandbox` becomes a `Workspace` with `has_git=False, exec=off`. No engine fork for repo vs artifact (R3)") + R3 mitigation (line 907). Phase 9's hard gate is byte-identical prototype output (INV-3) — keeping call sites stable is the lowest-parity-risk refold.
  - *Rejected:* deleting `RunSandbox` outright and re-pointing every call site to `Workspace` directly (cleaner single type, but touches many prototype call sites → higher parity churn for a phase gated on byte-identical output).
  - **Researcher directive:** inventory every `RunSandbox` caller (prototype/od_/revision/ppt/code-gen paths) + the 5-pipeline characterization snapshot harness so the refold is byte/event-parity; confirm `RunSandbox`-as-`Workspace(has_git=False)` produces identical disk layout/serialization for `serialized_sandbox`/`single_file` deliverables (the snapshot oracle).

### Area B — RepoIndex: tree-sitter wiring (REPO-02) ⟵ gray area 2

- **D-03: tree-sitter grammars sourced as PREBUILT WHEELS** (e.g. `tree-sitter-language-pack` / `tree-sitter-languages`) bundling py/js/ts (+ the repo's primary languages) as binary wheels — installs + imports **fully offline**, no C toolchain at runtime (the offline-CI accept gate is the constraint). Pinned like every other dependency. `tree_sitter` (+ the grammar pack) is imported **ONLY behind the `repo_index` capability module** (banned-pattern/import isolation — same discipline as the Phase-8 Validator heavy deps).
  - *Rationale:* the accept gate runs offline with no network; prebuilt wheels are the only grammar source that installs + imports without a build step. SPEC REPO-02 acceptance: "`tree-sitter` is imported only behind the `RepoIndex` capability."
  - *Rejected:* per-language `tree-sitter-python`/`-javascript`/`-typescript` packages (more wiring; some need a compile step — friction against the offline gate); vendored compiled grammars (maximal determinism but you maintain the binary/platform matrix).

- **D-04: `RepoIndex` is an OPTIONAL registered port; the symbol index is built IN-MEMORY PER-RUN when a run opts in (or the repo exceeds the N6 threshold), and discarded at teardown.** No new table/columns, no staleness/invalidation logic. **grep/glob remains the default** search; the index is built only on manifest opt-in or N6. The **N6 threshold is a documented config constant + a manifest opt-in flag**. Persistence/caching is a clear later optimization behind the same `RepoIndex` port. Embeddings/vector retrieval are OUT.
  - *Rationale:* SPEC REPO-02 ("built only when the manifest opts in or the repo exceeds the documented N6 threshold"; "Embeddings/vector retrieval are out of scope"). In-memory is the simplest impl that satisfies the symbol-query acceptance (returns file+line of a known function/class).
  - *Rejected:* lineage-tracking the symbol index as a persisted typed artifact (`kind=repo_index`) like `repo_inventory` — adds storage shape + invalidation for a cross-run-reuse benefit this offline phase doesn't need.
  - **Researcher directive:** confirm which languages the chosen grammar pack covers offline + the symbol kinds (functions/classes/imports) extractable per language; confirm the `RepoIndex` port's `search`/`symbol_query` shape so grep/glob (default) and the index resolve through one provider seam; document the N6 threshold value + where the manifest opt-in flag lives on the step/workflow schema.

### Area C — MCP client + catalog (MCP-01/02/03/04) ⟵ gray area 3

- **D-05: The allow-listed MCP server catalog = registered `mcp_server` CAPABILITIES (each server is a module that `@register`s `kind='mcp_server'`, `name='github'|'gitlab'|'jira'|'slack'|'filesystem'|'postgres'`).** The server's transport (stdio/SSE/HTTP) + exposed-tool allow-list + `user_allowed` flag + scope are carried as the registration's **data**. GitHub/GitLab/Jira/Slack register `user_allowed=true` (read-scoped); **Filesystem/Postgres register `user_allowed=false`**. Surfaced via `GET /api/capabilities` (extends the Phase-8 endpoint) for free. Adding a server = add a module + register (no kernel/data-file edit) — consistent with Phase-8 `@register`/`discover()`.
  - *Rationale:* §7 line 528 ("MCP servers, integration providers" are registered/owned/allow-listed/permissioned capabilities); §22 line 761 (`/api/capabilities` palette incl. MCP servers). Mirrors the established Phase-8 "add a capability = add a module + register" pattern across every other kind.
  - *Rejected:* a single static YAML/JSON catalog file (diverges from the `@register` pattern every other kind uses; needs its own loader + validation path); a hybrid (registered module + external data file) — splits one concept across two homes.

- **D-06: MCP-01 proven offline via an IN-REPO STDIO STUB MCP SERVER** — a tiny real MCP server fixture in the repo, spoken to over stdio by `MultiServerMCPClient` — exercising the actual client transport + tool-binding end-to-end, fully offline. Doubles as the contract fixture for the MCP-01/MCP-04 accept checks in CI.
  - *Rationale:* highest-fidelity proof that the live adapter actually connects/lists/binds, without an external network (project offline-accept convention). A transport-level mock would not exercise the real stdio transport.
  - *Rejected:* mocking/recording `MultiServerMCPClient` responses without a real subprocess (lighter/faster but weaker proof the live path works).

- **D-07 (supporting — adapter binding, creds, compile-validation, gating):**
  - **Binding (MCP-01):** `McpClientAdapter` wraps `langchain-mcp-adapters` `MultiServerMCPClient` and **binds allowed tools into the deepagents tool set at `factory._build_runner_tools`** — the Phase-8 `tool_provider` registry seam. INV-13: MCP tools **augment** the mandated `deepagents` runtime, never replace it.
  - **Scoped creds (MCP-02):** per-owner credentials extend the Phase-5 `ScopedStore` + the existing `handoff.py:40` PAT pattern (owner-scoped/encrypted, **never global**); not readable cross-owner (the `ScopedStore` default-deny denial test is the gate).
  - **Compile-validation (MCP-03):** the compiler validates a step's `tools.mcp` against the **step + owner** reachable servers — extends the Phase-4/8 compiler INV-4 + trust path; an unknown `server.tool` (or a not-owned/`user_allowed=false` server in a user/db manifest) → **compile error** naming the offending `server.tool`.
  - **Gating (MCP-04):** powerful/write servers (Filesystem/Postgres, anything write/network) + **write-scopes** require the `security` gate + `secrets` permission + scoped creds; **read-scopes** (`gitlab_read`/`jira_read`/…) need no gate.
  - **Researcher directive (the async→sync wiring risk):** `MultiServerMCPClient` is **async**; `create_runner`/`factory._build_runner_tools` is **sync** and called from the async engine. Confirm how the adapter connects + lists + binds tools across that boundary (connect-at-run-entry in the async engine and pass the bound toolset into the sync factory, vs an async-safe bridge) without blocking or double-event-loop issues; confirm `langchain-mcp-adapters` returns LangChain-compatible tools that drop straight into the `deepagents` tool set (INV-13).

### Area D — Integration providers vs the handoff bypass (INTEG-01/02) ⟵ gray area 4 (deepest INV-12 call)

- **D-08: `integration_provider` = the permissioned BRIDGE that takes a catalog `mcp_server` + an `integrations` scope and surfaces its tools into the unified `create_runner`/deepagents tool set — ONE external-tool mechanism (the MCP client).** `integrations` scopes (`github_read`/`gitlab_read`/`jira_read`/`slack_post`, default **none**) gate which tools bind. No SDK duplication — GitHub/GitLab/Jira/Slack are reachable through the MCP catalog + the integration bridge, not a separate SDK path.
  - *Rationale:* MCP-02 already registers GitHub/GitLab/Jira/Slack as `mcp_server`s; INTEG-01 makes those same four reachable from `create_runner`. Binding the catalog's MCP tools (vs a parallel SDK integration) keeps it to one mechanism and avoids the dual-impl smell INV-12 warns against. §8 lines 548–549 (`mcp`/`integrations` scopes default none); §30 (the runtime/MCP/integration capability layer).
  - *Rejected:* a separate SDK-backed `integration_provider` (PyGithub/python-gitlab/Slack SDK) independent of the MCP catalog (each provider appears twice — two mechanisms doing the same job); a per-provider mix (MCP for GitHub/GitLab, SDK for Jira/Slack) — two binding paths + an inconsistent catalog/provider story.

- **D-09: The GitHub handoff bypass is DELETED IN-PLAN (INV-12 default).** The unified `create_runner` integration path (D-08) supersedes the separate GitHub-handoff coding-agent path (`backend/app/services/handoff_github.py`, `backend/app/agents/handoff/coding_agent.py:164`) → delete the superseded path **within this phase**, with a **migration-ledger entry**. No dual implementations.
  - *Rationale:* SPEC "No dual implementations (INV-12)" constraint names this exactly ("the GitHub handoff bypass becomes the unified `integration_provider` path, the superseded code is deleted within this phase or its survival is explicitly justified"). The handoff pipeline today **bypasses** the `deepagents` runtime — removing it also closes an INV-13 gap.
  - **Researcher directive (deletion-scope guard):** before deleting, confirm the blast radius — the standalone `/flowin-handoff` **API endpoint** (`backend/app/api/handoff.py`), the inbound MCP server (`backend/app/api/mcp.py`), `handoff_pipeline.py`, and the `handoff` model (`backend/app/models/handoff.py:40` PAT) may have **external consumers** or serve a different surface than the coding-agent bypass. Delete only the path the unified `integration_provider` truly supersedes (the GitHub coding-agent bypass that skips `create_runner`); if the `/flowin-handoff` endpoint is a live external integration surface with outside consumers, retain it with an **explicit ledger justification** rather than breaking a consumer. Map every caller + test before the deletion; the migration-ledger ratchet + the 5-pipeline parity snapshots are the gates.

### Area E — Repo capabilities shapes (REPO-01/03/04 — SPEC-locked; placement notes)

- **D-10:** `repo_inventory` (`kind=repo_inventory`), `context_pack` + `context_selector` (`kind=context_pack`) + the `repo` `ContextProvider`, and the `repo_diff` `DeliverableResolver` are SPEC-locked in shape. Placement follows the existing capability layout: `repo_diff` joins `backend/agents/capabilities/deliverables/` (beside `single_file`/`serialized_sandbox`/`streamed_text`/`ppt`); the `repo` provider joins `backend/agents/capabilities/context_providers/` (beside `opendesign`/`previous_run`); `repo_inventory`/`context_pack`/`context_selector` register as their own capabilities. `repo_diff` = file tree + per-file unified diff + change summary; branch policy is **manifest-declared** (`base_branch`/`working_branch`), runtime-enforced; **diff-only — no commit/PR push** (N4). All lineage-tracked as typed artifacts (Phase-5 `ScopedStore`).
  - **Researcher directive:** confirm whether `repo_inventory`/`repo_index`/`context_pack` are pure-stdlib (→ kernel-side `agents/capabilities/`) or carry heavy deps like tree-sitter (→ app-side, reached via the handle — `repo_index` is the tree-sitter one, see D-03/D-04); confirm `repo_diff` reads the diff from `Workspace.git_diff` (D-01) so the resolver never shells git directly; confirm `.gitignore` + `.flowinignore` + binary-skip + size-cap handling for `repo_inventory`.

### Area F — Persistence (RUNTIME-03)

- **D-11:** Additive Alembic migration **0017** adds `repositories` (id, owner_id, workspace_id, provider(`github`/`gitlab`/`local`), url, default_branch, auth_ref(scoped), created); wires the existing `workspaces.repo_id` FK (the nullable "Phase 9 forward field" from migration 0014). A repo run persists exactly one `repositories` row + one `kind=repo` `workspaces` row linked by `repo_id`; both carry `owner_id` + `workspace_id`. `alembic upgrade head` → `downgrade -1` reversible; the migration-ledger gate stays green. Follows the Phase-5 additive pattern (current head is **`0016_capability_hardening_tables.py`**, confirmed). Migration lands with plan **09-02** (the plan that writes the rows). `run_capabilities` (CAPRUN-01, Phase 5) records the run's active integration scopes + MCP servers + runtime (§18 line 713).
  - **Researcher directive:** confirm the `0016`→`0017` head chain + the Phase-5 model/`ScopedStore` location so the `repositories` model + scoped writer mirror it; confirm `workspaces.repo_id` FK target + that `kind` already accepts `repo` (or needs the enum/constraint widened additively).

### Area G — Plan sequencing (the 6 sub-plans)

- **D-12:** Follow the ROADMAP's `09-01…09-06` split in dependency order; execute **sequentially** (Claude Code worktree isolation is broken in this repo — `workflow.use_worktrees=false`). (1) **09-01** `RuntimeEnvironment`/`Workspace`/`ExecutionPolicy`/`IsolationProvider` ports (`agents/runtime/base.py`) + `LocalSandboxRuntime` (`local.py`) — the foundation. (2) **09-02** `repositories`/`workspaces` rows + migration 0017 + `RunSandbox` → git-off `Workspace` refold (D-02 parity gate). (3) **09-03** `RepoInventory` + `RepoIndex` (grep default, tree-sitter behind it) + `ContextPack` + `repo` context provider. (4) **09-04** `repo_diff` resolver + the file-backed sample brownfield workflow (no exec) — the REPO-05 accept proof. (5) **09-05** `McpClientAdapter` + server catalog + `McpCapabilityRegistry` compile-validation + the stub server. (6) **09-06** `integration_provider` capabilities (gitlab/github/jira/slack) + `integrations` scopes + **delete the handoff bypass** (D-09). 09-05/09-06 (MCP/integration track) are largely independent of the runtime/repo track (09-01…09-04) and could be planned in parallel, but execute sequentially.
  - *Rationale:* the runtime ports (09-01) are the substrate the repo capabilities + the RunSandbox refold build on; the integration bridge (09-06) depends on the MCP catalog (09-05) per D-08. Each plan leaves the 5-pipeline characterization green (the deletions/refold are gated on parity).

### Claude's Discretion
- The exact `RuntimeEnvironment`/`Workspace`/`IsolationProvider` method signatures + whether `Workspace` is a Protocol or a concrete base (D-01) — provided the kernel imports only `agents/runtime/base.py` and the import-linter stays 3-kept/0-broken.
- `LocalSandboxRuntime` impl placement (kernel-side `agents/runtime/local.py` vs app-side `app/agents/runtime/local.py`) per the import-linter contract (D-01 researcher directive) — planner's call with the linter as the gate.
- The grammar-pack choice (`tree-sitter-language-pack` vs `tree-sitter-languages`) + the exact N6 threshold value (D-03/D-04).
- The `mcp_server` registration signature + how `MultiServerMCPClient` is configured from the catalog data (D-05).
- The async→sync MCP binding mechanism (D-07 researcher directive).
- Whether `repo_inventory`/`context_pack` sit kernel-side or app-side per the heavy-dep boundary (D-10).
- Single `0017` migration vs splitting (D-11) — single is the recommendation.
- Plan-task granularity within the 6-plan frame (D-12) — e.g. whether the stub server is its own task under 09-05.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements (read FIRST)
- `.planning/phases/09-local-workspace-runtime-repo-workflows-no-exec-4a/09-SPEC.md` — the 14 locked requirements (RUNTIME/REPO/MCP/INTEG), boundaries, 16 acceptance criteria, interview log. **Locked requirements — MUST read before planning.**

### The specification (authoritative — `specs/003-workflow-engine-decoupling/plan.md`; nothing in it may be dropped)
- **§6 (lines ~313–522)** — Core abstractions: `RuntimeEnvironment` Protocol (**line 469**), `Workspace` Protocol "backed by a RuntimeEnvironment" (**line 479–480**, `runtime: RuntimeEnvironment`), `IsolationProvider.allocate(scope) -> Workspace` (**line 486**, `shared_read|sub_sandbox|worktree`), `MergeStrategy` (line 490), `McpClientAdapter` Protocol "CONSUME external MCP servers — net-new" (**line 512**), `ExecutionPolicy` (**line 439**), `Step.mcp`/`Step.integrations` default none (**lines 434–435**). (D-01/D-07).
- **§7 (lines 524–533)** — Capability registry & trust: `mcp_server`/`integration_provider` are registered/owned/allow-listed/permissioned capabilities (**line 528**); `user_allowed` + owner allow-list trust seam (D-05/D-08).
- **§8 (lines 535–556)** — Tool permission policy: the grant table; `mcp` named MCP tools default **none** (**line 548**), `integrations` scopes (`gitlab_read`/`jira_read`) default **none** (**line 549**); `Workspace.ExecutionPolicy` gates `exec`/`network`/`secrets` at runtime (**line 554**) (D-07/D-08).
- **§14 (lines 652–~695)** — **Workspace / RuntimeEnvironment layer (Q-N1, N2, N7) — interfaces now, `LocalSandboxRuntime` only**: one `Workspace` = fs + optional git + optional exec + `ExecutionPolicy`; `RunSandbox` → `Workspace(has_git=False, exec=off)`, **no engine fork** (**lines 654–655**); **Phase 4A no-exec** (line 660); `DeliverableContext` may request runners (line 680). The home for D-01/D-02/D-10. (Note INV-6 line 255: engine depends on `Workspace`/`RuntimeEnvironment` interfaces.)
- **§18 (lines 697–717)** — Persistence schema: `repositories`/`workspaces` rows; `run_capabilities` records runtime + integrations + mcp_servers (**line 713**); additive, every table carries `owner_id`+`workspace_id` (D-11).
- **§22 (lines 755–771)** — API/frontend contract: `GET /api/capabilities` palette incl. **MCP servers + integration tools** with required auth + permission scopes (**line 761**) (D-05).
- **§25 / roadmap (lines 836–837)** — **Phase 4A — Local Workspace runtime + repo workflows (no exec)**: `RuntimeEnvironment` port + `LocalSandboxRuntime`; `Workspace` + `ExecutionPolicy` (exec off); `repositories`/`workspaces` rows; repo inventory/index/context-pack. The phase definition.
- **§27 (line 858)** — ECS/EC2 runtime behind the **unchanged** `RuntimeEnvironment` port (separate spec) — the swap-later seam D-01 preserves.
- **§30 (lines 921–988)** — Agent runtime, skills, hooks, MCP & integrations (A11/INV-11): the MCP-client + integration-provider capability layer; current-state table; scoped per-owner creds; the `security` gate for powerful servers (D-05/D-07/D-08).
- **§31 (lines 989–1024) + `migration-ledger.md`** — move-don't-copy / deletion-is-DoD; the ledger entry for the handoff-bypass deletion (D-09).
- **§32 (line 894 + structure)** — Target directory structure: `new app/agents/runtime/ — base.py (ports), local.py (LocalSandboxRuntime)` — **conflicts with `09-SPEC.md`'s `agents/runtime/`; resolve via import-linter (D-01 researcher directive)**. Self-registering capabilities (`@register`/`discover()`); import-linter direction.
- **N-decision records** — N13 ✅ (line 877, MCP client + famous servers via allow-listed catalog, scoped creds + `security` gate); N1 ✅ (local runtime now, ECS later); R3 (line 907, two-engines mitigation = one `Workspace`); R13 (line 917, capability auth & secrets — the `handoff.py:40` PAT precedent).

### Project planning
- `.planning/REQUIREMENTS.md` — RUNTIME/REPO/MCP/INTEG requirement IDs with plan anchors + Phase 9 traceability rows.
- `.planning/ROADMAP.md` § Phase 9 — goal, the 4 success criteria, the **09-01…09-06** plan breakdown (D-12).
- `.planning/PROJECT.md` — invariants (INV-3/6/8/9/12/13); the GitHub-handoff "separate path, bypasses runtime" note (line 28); "Repo is GitLab → GitLab likely required for git hosting (N4)" (line 87); "nothing from plan.md dropped".
- `.planning/STATE.md` — Phase 8 closure (the capability registry/gates/tool-perms/runtime-policy-point Phase 9 builds the runtime on).

### Prior phase context (the evolution this phase extends)
- `.planning/phases/08-capabilities-hardened-registry-gates-tool-perms-runtime-3/08-CONTEXT.md` — `@register`/`discover()` (D-01 there) the `mcp_server`/`integration_provider` capabilities register via; the `mcp`/`integrations` permission **slots** (default none) Phase 8 landed that Phase 9 fills; the `ExecutionPolicy` enforcement **point** Phase 8 wired that the `LocalSandboxRuntime` now backs; the Validator↔heavy-dep app-side placement pattern (the model for tree-sitter/`RepoIndex` placement, D-01/D-03/D-10); the `tool_provider` registry seam at `factory._build_runner_tools` (D-07).
- `.planning/phases/07-prototype-as-manifest-parity-proof-sc-001-2/07-CONTEXT.md` — the `KernelServices` runner-handle pattern (how capabilities reach `app.*` without a kernel→app edge — the model for the runtime impl + MCP creds); the deliverable-resolver port `repo_diff` joins.
- `.planning/phases/05-typed-artifacts-persistence-ownership-1b/05-CONTEXT.md` — the additive-migration + `ScopedStore` (default-deny, owner/workspace-scoped) pattern D-11 mirrors + the scoped-creds home for D-07.

### Code to read (targets / assets)
- `backend/app/agents/sandbox.py:49` — **`RunSandbox`** (the per-run disk dir) refolded as `Workspace(has_git=False, exec=off)` (D-01/D-02).
- `backend/agents/capabilities/base.py` — the Protocol-port idiom the net-new `RuntimeEnvironment`/`Workspace`/`ExecutionPolicy`/`IsolationProvider`/`McpClientAdapter` ports follow; **new package `agents/runtime/base.py`** holds the runtime ports (D-01).
- `backend/agents/capabilities/registry.py` — `@register`/`discover()` the `mcp_server`/`integration_provider`/runtime capabilities self-register into (Phase 8); add the `mcp_server`/`integration_provider`/runtime kinds if not present (D-05/D-08).
- `backend/agents/capabilities/deliverables/{single_file,serialized_sandbox,streamed_text,ppt}.py` — the `DeliverableResolver` pattern `repo_diff` joins (D-10).
- `backend/agents/capabilities/context_providers/{opendesign,previous_run}.py` — the `ContextProvider` pattern the `repo` provider joins (D-10).
- `backend/agents/factory.py` — `_build_runner_tools` (the Phase-8 `tool_provider` seam MCP/integration tools bind into, D-07); `create_runner` (the unified path integrations become reachable from, D-08).
- `backend/agents/workflows/compiler.py` + `plan.py` — the INV-4 capability-reference validation `tools.mcp` compile-validation extends (D-07/MCP-03); `Step.tools`/`Step.mcp`/`Step.integrations` grant fields (§6 lines 434–435).
- `backend/app/api/mcp.py` — the **inbound** MCP *server* (the backwards direction); confirm the net-new **client** (`McpClientAdapter`) is additive and doesn't collide (D-05/D-07).
- `backend/app/services/handoff_github.py` + `backend/app/agents/handoff/coding_agent.py:164` — the GitHub-handoff **bypass** path deleted in-plan (D-09).
- `backend/app/api/handoff.py` + `backend/app/services/handoff_pipeline.py` + `backend/app/models/handoff.py:40` — the `/flowin-handoff` endpoint + pipeline + the **PAT scoped-cred precedent**; map external consumers before deleting (D-09 deletion-scope guard); the PAT pattern is the model for MCP/integration scoped creds (D-07).
- `backend/alembic/versions/0016_capability_hardening_tables.py` — the migration **head** `0017` follows; `0014_typed_artifacts_persistence.py` created `workspaces` with the `repo_id` forward field (D-11).
- `backend/tests/agents/test_characterization_*.py` + the 5-pipeline deliverable/event snapshots — the strict-INV-3 parity gate the `RunSandbox` refold (D-02) + handoff deletion (D-09) must keep green.
- `backend/tests/agents/test_migration_ledger.py` + `test_banned_patterns.py` + the import-linter contract (`/opt/homebrew/bin/lint-imports`) — the ledger ratchet (handoff deletion), INV-13 deepagents-only gate (MCP/tree-sitter are libs, not runtimes), and the kernel→ports direction (D-01 placement).
- `backend/CLAUDE.md` — dev runtime `python3.11` (no venv); commit scopes; PR off `feature/003-workflow-engine-decoupling`, never `main`; the targeted offline parity/gate suite (full pytest hangs offline).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`RunSandbox` (`backend/app/agents/sandbox.py:49`)** — the per-run disk dir that refolds into `Workspace(has_git=False, exec=off)` (D-01/D-02); its existing disk/serialization behavior IS the parity oracle for the refold.
- **`@register`/`discover()` + the `mcp`/`integrations` permission slots (Phase 8)** — the registry the `mcp_server`/`integration_provider`/runtime capabilities self-register into; the slots (default none) Phase 9 fills.
- **`factory._build_runner_tools` + the `tool_provider` registry (Phase 8)** — the binding seam where MCP/integration tools enter the `deepagents` tool set (D-07/D-08).
- **`ExecutionPolicy` enforcement point (Phase 8)** — already wired; the `LocalSandboxRuntime`'s `Workspace` now backs it (exec stays denied).
- **`DeliverableResolver` + `ContextProvider` ports + impls** — `repo_diff` and the `repo` provider join the established registries (D-10).
- **Phase-5 `ScopedStore` + additive-migration pattern (`0014`/`0016`)** — D-11's `0017` (`repositories`) + scoped writers mirror it; the `handoff.py:40` PAT is the scoped-cred precedent for MCP/integration creds (D-07).
- **`KernelServices` runner handle (Phase 7)** — how heavy/app-side capabilities (tree-sitter `RepoIndex`, `LocalSandboxRuntime` if app-side) reach `app.*` without a kernel→app edge (D-01/D-03).
- **Inbound MCP server (`backend/app/api/mcp.py`)** — confirms MCP is currently server-only; the net-new client is the opposite direction (D-05/D-07).

### Established Patterns
- **Provisioner + facade / ports-not-impls (INV-6, §6/§14)** — `RuntimeEnvironment` provisions, `Workspace` is the facade; kernel imports only ports; ECS swaps behind the unchanged port (§27) (D-01).
- **Move-don't-copy + deletion-is-exit-gate (INV-12 / §31)** — `RunSandbox` internals + the handoff bypass are deleted in-plan once the replacement is proven at parity; the ledger ratchet + import-linter + banned-pattern gates enforce it (D-02/D-09).
- **Heavy-dep capabilities live app-side, reached via the handle (Phase-8 Validator pattern)** — the model for tree-sitter `RepoIndex` + (possibly) `LocalSandboxRuntime`/`repo_inventory` placement (D-01/D-03/D-10).
- **One external-tool mechanism (MCP), not two (D-08)** — `integration_provider` binds catalog `mcp_server` tools + the `integrations` scope; no parallel SDK path.
- **Least-privilege default-OFF/none (INV-9)** — `exec`/`network`/`secrets` OFF; `mcp`/`integrations` none; `read_files` ON; the `security` gate + `secrets` gate powerful/write MCP (D-07).
- **Strict INV-3 parity (SPEC boundary)** — the repo path is additive; the 5-pipeline characterization snapshots stay UNCHANGED; the `RunSandbox` refold + handoff deletion gate on them.
- **Offline-verifiable accept (project convention)** — local git fixture + in-repo stub MCP server; live external calls deferred to milestone-end; verify with the targeted parity/gate suite + `lint-imports`, not full pytest.

### Integration Points
- **Net-new:** `agents/runtime/base.py` (ports) + `local.py` (`LocalSandboxRuntime`); `repo_inventory`/`repo_index`/`context_pack`/`context_selector` capabilities; `repo_diff` deliverable + `repo` context provider; `McpClientAdapter` + `mcp_server` catalog capabilities + the stub server; `integration_provider` capabilities; Alembic `0017` (`repositories`); the sample brownfield workflow manifest + the local git fixture; deps `langchain-mcp-adapters` + `tree-sitter` (grammar pack).
- **Grows:** `factory._build_runner_tools`/`create_runner` (MCP/integration tool binding); `compiler.py`/`plan.py` (`tools.mcp` compile-validation + scopes); `registry.py` (new kinds); `workspaces` table (`repo_id` FK wired).
- **Shrinks → deleted:** `RunSandbox` bespoke disk internals (delegated to `Workspace`); the GitHub-handoff coding-agent bypass (`handoff_github.py` / `coding_agent.py:164`).
- **CI gates that constrain the work:** the 5-pipeline characterization snapshots (strict INV-3); migration-ledger ratchet (handoff deletion entry; `0016`→`0017` chain); import-linter (kernel→`agents/runtime/base.py` ports; no kernel→`app.*`); banned-pattern (INV-13 — tree-sitter/mcp-adapters are libs, not deep-agent runtimes; exec stays off).

</code_context>

<specifics>
## Specific Ideas

- **Standing project directive (init):** "everything from plan.md must be honored — nothing dropped." Every decision above takes the plan-faithful option (§6/§14 runtime split; §7 trust; §8 perms; §30 MCP catalog + integration providers; §18 additive `repositories`; §31 handoff-bypass deletion).
- **Mode departure:** unlike Phases 1/2/4/5/6/7/8 ("lock all to recommendations" dismissed-the-question), the user **deep-dived all four** HOW areas here — Phase 9 is the first net-new workflow class, so the architecture is genuinely new. The decisions still landed on the recommendations, but were each explicitly chosen.
- **The deepest research risks:**
  1. **Port-vs-impl placement (D-01)** — `09-SPEC.md` (`agents/runtime/`) vs plan.md §32 line 894 (`app/agents/runtime/`); the import-linter contract is the tiebreaker (ports kernel-side, heavy impl app-side via the handle).
  2. **The handoff-bypass deletion blast radius (D-09)** — delete only the coding-agent bypass the unified path supersedes; guard the `/flowin-handoff` endpoint's external consumers; ledger-entry either way.
  3. **Async MCP → sync factory binding (D-07)** — `MultiServerMCPClient` is async; `create_runner` is sync inside the async engine.
- **The strictest constraint (SPEC boundary):** strict INV-3 — the 5-pipeline characterization snapshots are UNCHANGED. The riskiest changes for parity are the `RunSandbox`-as-`Workspace` refold (D-02) and the handoff-bypass deletion (D-09); both gate on the snapshots.
- **GitLab-first reality:** the repo itself is GitLab (`hexaware-uki/flowin`, PROJECT.md line 87) — both GitLab + GitHub providers are in scope (SPEC), but GitLab is the live-path priority for N4.

## Deferred-but-adjacent (planner triage, NOT locked scope)
- None flagged this phase beyond the SPEC's explicit out-of-scope list.

</specifics>

<deferred>
## Deferred Ideas

- **`exec` + compile/test/lint validators (EXEC-01/02)** — Phase 10 / N3 / Phase 4B. `exec_command` lands in the `Workspace` port but is denied by the default `ExecutionPolicy`; the `security` gate keeps exec off.
- **PR / commit push** to git hosts (N4) — diff-only this phase; write creds + push deferred.
- **`sub_sandbox` / git-worktree isolation + engine fan-out** — Phase 11. The `IsolationProvider` port lands (`allocate(scope)`), but only per-run/`shared_read` scope is implemented.
- **Durable job queue/worker (N8)** — long jobs run in-process (FastAPI background task) for local v1; durable substrate is an infra follow-up.
- **ECS / `EcsRuntime`** — v2 / separate spec (§27), behind the unchanged `RuntimeEnvironment` port the runtime split (D-01) preserves.
- **Embeddings / vector retrieval** — tree-sitter **symbol** index only this phase; persisted/cached index (vs in-memory per-run, D-04) is a later optimization behind the same `RepoIndex` port.
- **The full §30 MCP catalog** (Confluence/Notion/Linear/Sentry/Figma/Drive/web-search/Playwright) — beyond the GitHub/GitLab/Jira/Slack core; registers as more `mcp_server` capabilities later.
- **DB-backed user-authored workflows (Q5)** — file-backed hand-authored manifests only this phase; the `user_allowed` trust flag on `mcp_server` capabilities is the seam.
- **Live external-server verification** — real GitLab/GitHub/Jira/Slack/MCP calls run in the end-of-milestone live pass (project deferred-live convention); this phase accepts offline against fixtures + the stub server.
- **Subagent/wave tree + repo-diff frontend viewer** — the `repo_diff` data lands here, but the frontend viewer is later (P9 surfaces the deliverable; richer viewers follow with fan-out/waves).

### Reviewed Todos (not folded)
None — `todo.match-phase 9` returned 0 matches.

</deferred>

---

*Phase: 9-local-workspace-runtime-repo-workflows-no-exec-4a*
*Context gathered: 2026-06-10*
