# Phase 9: Local Workspace Runtime + Repo Workflows (no exec) [4A] — Research

**Researched:** 2026-06-10
**Domain:** Hexagonal runtime-port layer · brownfield git workspace · MCP client integration · Alembic additive migration · INV-3 parity refold
**Confidence:** HIGH (codebase facts file:line-verified) / MEDIUM (library APIs — verified against PyPI + official docs, but neither library is installed offline yet)

## Summary

This phase is richly pre-specified: a 14-requirement SPEC (ambiguity 0.16) and 12 locked HOW-decisions (D-01…D-12). The research job was **not** to re-decide, but to resolve the 7 embedded "Researcher directive" callouts by reading the live code and verifying the two new libraries. Every directive is resolved below with file:line citations the planner copies into task `read_first`/`action` fields.

The codebase is **more ready than the SPEC's "all net-new" framing implies**. The capability-port idiom (`@register`/`discover()`), the kernel→app handle (`ctx.runner` = `KernelServices`, `ctx.scoped_store` = `ScopedStore`), the `ToolPermissions` grant model with **already-present `mcp`/`integrations`/`git` slots**, the compiler's per-reference `is_registered`/`is_user_allowed` validation with **`mcp`/`integrations` already in the allowed-keys set**, the `tool_provider` binding seam at `factory._build_runner_tools`/`_resolve_runner_tools`, the async-run-entry pre-warm pattern (`prewarmed_constitution`), and the `workspaces` table's **already-`String` (non-enum) `kind` column + nullable `repo_id`** all exist. Phase 9 fills declared forward seams rather than inventing new mechanisms — which materially lowers the parity risk on the two riskiest changes (RunSandbox refold, handoff-bypass deletion).

**Primary recommendation:** Lock the **ports** to kernel-side `backend/agents/runtime/base.py`; place `LocalSandboxRuntime` **app-side** at `backend/app/agents/runtime/local.py` (it must touch `app.agents.sandbox` disk utils + `app.core.config.settings`), self-registered via `@register("runtime_env", "local")` and reached via the `ctx.runner` handle — mirroring the Phase-8 Validator split. Refold `RunSandbox` **in-place** (name survives as a thin facade) gated on the 5-pipeline `final_output` byte-snapshot + normalized event-stream golden. Use **`tree-sitter-language-pack`** (pinned, prebuilt abi3 wheels) behind the `repo_index` capability and **`langchain-mcp-adapters` `MultiServerMCPClient`** connected **at async run-entry** (await `get_tools()` once, pass the bound toolset into the sync factory — exactly the `prewarmed_constitution` pattern). Delete **only** the `CodingAgent` coding bypass; **retain** the `/api/handoff` HTTP router (live external surface) with an explicit ledger justification. Migration **0017** is `down_revision="0016"`, adds `repositories`, sets `workspaces.repo_id` FK — `kind='repo'` needs **no enum widening** (the column is already a free `String`).

## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01…D-12 — research THESE, no alternatives)
- **D-01:** `RuntimeEnvironment` = provisioner port (`create_workspace`/`teardown`); `Workspace` = fs+git+exec+`ExecutionPolicy` facade carrying `owner_id`/`workspace_id` + back-ref to its `RuntimeEnvironment`. `LocalSandboxRuntime` impls it over the per-run disk dir. `exec_command` present but DENIED by default `ExecutionPolicy`. `IsolationProvider.allocate(scope)` lands as a port; only per-run/`shared_read` impl'd.
- **D-02:** `RunSandbox` refolds **in-place** on top of `Workspace(has_git=False, exec=off)`; the `RunSandbox` name survives as a thin alias/subtype so call sites are untouched (parity-safest). Move-don't-copy: bespoke disk logic delegated, not duplicated. Repo workflow uses `Workspace(has_git=True, exec=off)`. No `if repo:` engine fork.
- **D-03:** tree-sitter grammars as PREBUILT WHEELS (`tree-sitter-language-pack`/`tree-sitter-languages`); imported ONLY behind the `repo_index` capability module.
- **D-04:** `RepoIndex` = OPTIONAL registered port; symbol index built IN-MEMORY PER-RUN on manifest opt-in or N6 threshold, discarded at teardown. grep/glob is the default. N6 = documented config constant + manifest opt-in flag. No new table/columns. Embeddings OUT.
- **D-05:** MCP catalog = registered `mcp_server` capabilities (module + `@register`). GitHub/GitLab/Jira/Slack `user_allowed=true` (read-scoped); Filesystem/Postgres `user_allowed=false`. Surfaced via `GET /api/capabilities`.
- **D-06:** MCP-01 proven offline via an IN-REPO STDIO STUB MCP SERVER spoken to over stdio by `MultiServerMCPClient`.
- **D-07:** Binding at `factory._build_runner_tools` (the `tool_provider` seam); scoped creds extend `ScopedStore` + the `handoff.py:40` PAT pattern; compile-validation extends the compiler INV-4 path; write/powerful servers gated by `security` + `secrets`, read-scopes ungated. Resolve the async→sync wiring.
- **D-08:** `integration_provider` = the permissioned bridge binding catalog `mcp_server` tools into `create_runner` via an `integrations` scope. ONE external-tool mechanism (MCP) — no parallel SDK path.
- **D-09:** The GitHub handoff bypass is DELETED IN-PLAN (INV-12) with a migration-ledger entry; guard the `/flowin-handoff` endpoint's external consumers.
- **D-10:** `repo_inventory`/`context_pack`/`context_selector`/`repo` provider/`repo_diff` resolver placement follows existing capability layout; `repo_diff` reads from `Workspace.git_diff`; `.gitignore`+`.flowinignore`+binary-skip+size-cap handling for `repo_inventory`.
- **D-11:** Additive migration 0017 adds `repositories`; wires `workspaces.repo_id` FK. One `repositories` row + one `kind=repo` `workspaces` row per repo run. `upgrade head`→`downgrade -1` reversible. Lands with plan 09-02.
- **D-12:** 6-plan frame 09-01…09-06, execute sequentially (`use_worktrees=false`). DO NOT re-sequence.

### Claude's Discretion
- Exact `RuntimeEnvironment`/`Workspace`/`IsolationProvider` signatures + Protocol vs concrete base (provided kernel imports only `base.py` and import-linter stays 3-kept/0-broken).
- `LocalSandboxRuntime` placement (kernel vs app) per the import-linter contract.
- Grammar-pack choice + exact N6 threshold value.
- `mcp_server` registration signature + `MultiServerMCPClient` config from catalog data.
- The async→sync MCP binding mechanism.
- Whether `repo_inventory`/`context_pack` sit kernel- or app-side.
- Single `0017` vs splitting (single recommended).
- Plan-task granularity within the 6-plan frame.

### Deferred Ideas (OUT OF SCOPE — ignore completely)
exec + compile/test/lint validators (Phase 4B/N3) · PR/commit push (N4, diff-only) · sub_sandbox/git-worktree isolation + engine fan-out (Phase 11) · durable job queue (in-process background task) · ECS/`EcsRuntime` (v2/§27) · embeddings/vector retrieval · persisted/cached symbol index · full §30 MCP catalog (Confluence/Notion/Linear/Sentry/Figma/Drive/web-search/Playwright) · DB-backed user-authored workflows · live external-server verification (milestone-end live pass) · repo-diff frontend viewer.

## Phase Requirements

| ID | Description | Research Support (where the enabling fact lives) |
|----|-------------|--------------------------------------------------|
| RUNTIME-01 | `RuntimeEnvironment` port + `LocalSandboxRuntime` | R-A — ports kernel-side `agents/runtime/base.py`; impl app-side via handle; import-linter contract names |
| RUNTIME-02 | One `Workspace`; `RunSandbox` refolded | R-B — caller inventory + parity oracle (5-pipeline `final_output`+event golden) |
| RUNTIME-03 | `repositories`+`workspaces` rows persisted | R-G — 0017 chain, `repositories` columns, `workspaces.repo_id`/`kind` facts |
| REPO-01 | `RepoInventory` | R-F — pure-stdlib kernel-side; `.gitignore`/`.flowinignore`/binary/size-cap |
| REPO-02 | `RepoIndex` tree-sitter (grep default) | R-C — `tree-sitter-language-pack`, port shape, N6 constant, manifest flag |
| REPO-03 | `ContextPack` + `repo` provider | R-F — `ContextProvider` base contract (`async load → dict[str,str]`) |
| REPO-04 | `repo_diff` resolver | R-F — `DeliverableResolver` (`resolve(ctx)`); reads `Workspace.git_diff` via handle |
| REPO-05 | Sample brownfield workflow, no exec | R-F + R-A — `ExecutionPolicy` exec-off; `RepoSpec(url/ref/branch)` already in `plan.py:256` |
| MCP-01 | `McpClientAdapter` | R-D — `MultiServerMCPClient.get_tools()` async; bind at factory seam |
| MCP-02 | Catalog + scoped creds | R-D + R-E — `@register("mcp_server",…)`; PAT precedent `UserGithubCredential` `models/handoff.py:40` |
| MCP-03 | Compile-validation | R-D — compiler `is_registered`/`is_user_allowed`; `mcp`/`integrations` already in `_ALLOWED_TOOLS_KEYS` |
| MCP-04 | Security gate for write/powerful | R-D — `gate:security` (08-02) + `ToolPermissions.secrets`/`check()` `plan.py:172` |
| INTEG-01 | `integration_provider` from `create_runner` | R-E — `_resolve_runner_tools`/`_build_runner_tools` seam (`factory.py:457`) |
| INTEG-02 | `integrations` scopes, default none | R-E — `ToolPermissions.integrations` slot `plan.py:72`; `record_capabilities` `engine.py:556` |

---

## R-A (D-01) — Port-vs-impl placement; the import-linter call

### Codebase facts
- **Existing `RunSandbox` is app-side:** `backend/app/agents/sandbox.py:49`. It imports `from app.core.config import settings` (`sandbox.py:21`) for `RUNS_ROOT`/`RUN_DIR_TTL_HOURS`. Pure `pathlib`/`os`/`shutil`/`re` otherwise — **no other `app.*` reach beyond `settings`**.
- **The import-linter contract** lives in `backend/pyproject.toml` `[tool.importlinter]` (`pyproject.toml:131`), runner `cd backend && lint-imports` (binary at `/opt/homebrew/bin/lint-imports`). Three `forbidden` contracts (3 kept / 0 broken):
  1. `"kernel imports only capability ports (scaffold)"` — `source=agents.execution_engine.engine`, `forbidden=[app.api]` (`pyproject.toml:134`).
  2. `"agents.workflows must not import the execution kernel or the web layer"` — `source=agents.workflows`, `forbidden=[agents.execution_engine, app]` (`pyproject.toml:159`).
  3. **`"agents.capabilities must not import the execution kernel or the web layer"`** — `source=agents.capabilities`, `forbidden=[agents.execution_engine, app]` (`pyproject.toml:165`). **This is the authority for the placement call.**
- **The Phase-8 Validator split is the exact precedent.** Heavy-dep validators live app-side at `app.agents.validators` and self-register because `discover()` explicitly imports that package (`registry.py:226`, the only app-side capability package). The capability reaches `app.*`/kernel ONLY through the `ctx.runner` (`KernelServices`) and `ctx.scoped_store` handles — never an import. `serialized_sandbox.py:36-38` and `previous_run.py:187-218` show the pattern: `runner = ctx.runner; runner.sandbox.root; runner.read_parent_file(...)` — all dynamic attribute access off an `Any`-typed field, import-clean.
- **The handle is `KernelServices`** (`agents/execution_engine/kernel_services.py:127`), "this module IS the kernel so it MAY import `app.*` + engine internals freely" (`kernel_services.py:14`). It already imports `RunSandbox`, `count_sandbox_deliverables`, `serialize_sandbox_deliverable` (`kernel_services.py:36-40`).

### Recommendation (Discretion: planner's call, linter is the gate)
- **PORTS → kernel-side `backend/agents/runtime/base.py`** (NEW package). Define `RuntimeEnvironment`, `Workspace`, `ExecutionPolicy`, `IsolationProvider` as `typing.Protocol` ports (stdlib `typing` only, runtime objects typed `Any`) — identical idiom to `agents/capabilities/base.py:1-24`. The kernel + the import-linter authority (contract 3) require kernel-side ports the capabilities can reference. **A 4th import-linter contract should be ADDED** locking `agents.runtime` ↛ `[agents.execution_engine, app]` (same `forbidden` shape — additive tighten, never a rewrite, per the `pyproject.toml:106` "INTENDED FINAL FORM" note).
- **`LocalSandboxRuntime` (`local.py`) → APP-SIDE `backend/app/agents/runtime/local.py`.** Rationale: it must touch `app.core.config.settings` (RUNS_ROOT) and reuse `app/agents/sandbox.py`'s traversal-proof `path_for`/`ensure` logic — the same `app.*` reach that put the heavy validators app-side. It self-registers via `@register("runtime_env", "local")` and is reached via the handle (the kernel imports its package in `discover()`, mirroring `registry.py:226`). **Plan.md §32 line 894's `app/agents/runtime/` is therefore correct for `local.py`**; the SPEC's `agents/runtime/` is correct for `base.py`. Both statements reconcile under the port/impl split — exactly the Validator precedent.
- **New registry kind:** add `("runtime_env", "local")` to `_KNOWN` in `registry.py:76` (free-string kind, no central if/elif — `registry.py:154` `_KNOWN.add`). Note `("runtime", "langchain_deepagents")` already exists for the agent-runtime adapter (`registry.py:102`) — use a DISTINCT kind name like `runtime_env` to avoid collision with the agent-runtime port.
- **`discover()`** must import the new app-side package: add `"app.agents.runtime"` to the `_forward_packages` tuple (`registry.py:217-227`) — the best-effort `ModuleNotFoundError` guard already there means a not-yet-created package is a no-op.

**import-linter gate:** `cd backend && /opt/homebrew/bin/lint-imports` → 3 kept / 0 broken (4 after adding the `agents.runtime` contract). The capability/runtime port modules import stdlib only; `local.py` lives under `app.*` so it may import `app.*` freely.

---

## R-B (D-02) — RunSandbox refold parity

### Complete `RunSandbox` caller inventory (file:line)
| Call site | What it uses | Refold action |
|-----------|-------------|----------------|
| `agents/factory.py:155,172` | `RunSandbox(ctx.user_id or "anon", ctx.run_id or "adhoc")` + `.ensure()` | unchanged — name survives |
| `agents/execution_engine/engine.py:48,506-507` | `RunSandbox(disk_principal, pipeline_run_id)` + `.ensure()` | unchanged — name survives |
| `agents/execution_engine/engine.py:1340,1937` | type-hint `sandbox: RunSandbox` in `_run_agent`/build-loop | unchanged |
| `agents/execution_engine/kernel_services.py:36-40,160,471` | imports `RunSandbox` + serialize/count helpers; `RunSandbox(disk_principal, parent_run_id)` for parent reads | unchanged |
| `app/agents/deep_agent_runner.py:64,204` | `run_sandbox: RunSandbox \| None`; `FilesystemBackend(root_dir=<RunSandbox.root>)` (`deep_agent_runner.py:42`) | unchanged — relies on `.root` |
| `agents/capabilities/deliverables/serialized_sandbox.py:37-38` | `runner.count_sandbox_deliverables(root)` / `runner.serialize_sandbox_deliverable(root)` via handle | unchanged |
| `agents/capabilities/strategies/task_loop.py:56` | `sandbox.read(name)`/`write(name,text)` via handle | unchanged |
| `agents/execution_engine/context.py:70-72,102` | doc-refs to the `disk_principal` keying invariant | unchanged |
| `app/services/od_loader.py:287` | doc-ref only ("mirrors `RunSandbox.path_for`") | unchanged |

**Conclusion:** the consumed surface is `__init__(user_id, run_id)`, `.ensure()`, `.root`, `.path_for`, `.read`, `.write`, `.cleanup`, plus the two module-level helpers `serialize_sandbox_deliverable`/`count_sandbox_deliverables`. The D-02 in-place refold MUST preserve every one of these names/signatures byte-for-byte. The lowest-risk shape: `RunSandbox` becomes a thin subtype/facade whose internals delegate to a `Workspace(has_git=False, exec=off)` — `.root` still resolves to `<RUNS_ROOT>/<user>/<run>/`, `path_for` still rejects traversal (`sandbox.py:77-82`), `serialize_sandbox_deliverable` reads raw bytes (NOT `read_text`) to preserve CRLF byte-equivalence (`sandbox.py:233-236` — load-bearing, pinned by `test_sandbox_deliverable.py`).

### The parity oracle (what the snapshots compare)
- **Deliverable byte-snapshot:** `tests/agents/test_characterization_prototype.py:37-42` drives the pipeline fully offline (`_drive("prototype")` — no DB/Bedrock/API key) and snapshots `extract_final_output(events).encode("utf-8")` against a golden via `assert_deliverable_snapshot("prototype.html", …)`. The deliverable IS the `pipeline_complete` event's `final_output` string. For code-gen this is the `filename:`-block bundle from `serialize_sandbox_deliverable` (the disk-walk → sorted-relpaths → ```` ```filename: <relpath>\n<content>\n``` ```` joined by `\n\n`, empty-sentinel `"(no files written)"` — `sandbox.py:183-248`). **This serialization (disk layout → string) is the byte oracle the `has_git=False` refold must not perturb.**
- **Normalized event-stream golden:** `test_characterization_prototype.py:46-80` — asserts no undocumented event types, all required data keys present, contiguous seq, then equality vs `prototype.events.json` (volatile fields normalized out, so robust to text drift but FAILS on a dropped/reordered event or lost key).
- **The 5 pipelines:** `tests/agents/test_characterization_{prototype,prototype_revision,app_builder,od_prototype,od_ppt}.py` (app_builder = the code-gen pipeline). All must stay green with NO re-baseline.

### Exact offline test command (per backend/CLAUDE.md — full pytest hangs offline)
```bash
cd backend && python3.11 -m pytest \
  tests/agents/test_characterization_prototype.py \
  tests/agents/test_characterization_prototype_revision.py \
  tests/agents/test_characterization_app_builder.py \
  tests/agents/test_characterization_od_prototype.py \
  tests/agents/test_characterization_od_ppt.py \
  tests/agents/test_sandbox_deliverable.py \
  tests/agents/test_manifest_parity.py tests/agents/test_phase3_parity.py -v
```
Regenerate goldens ONLY with deliberate `SNAPSHOT_UPDATE=1` (must stay UNSET this phase). `test_sandbox_deliverable.py` is the dedicated byte-oracle for the serialization the refold rides on.

---

## R-C (D-03/D-04) — tree-sitter offline wiring

### Grammar-pack choice (Discretion → recommendation)
**Recommend `tree-sitter-language-pack`** [ASSUMED — verified on PyPI but discovered via WebSearch, not Context7; slopcheck unavailable offline].

| Property | `tree-sitter-language-pack` | `tree-sitter-languages` (grantjenks) |
|----------|-----------------------------|--------------------------------------|
| Latest version | **1.8.1** [VERIFIED: PyPI `pip index versions`] | 1.10.2 [VERIFIED: PyPI] |
| Wheels | abi3 prebuilt, CPython 3.10+, manylinux 2.34+/macOS 10.12+11.0/Windows x86-64+ARM64 — **no C toolchain** [CITED: pypi.org/project/tree-sitter-language-pack] | prebuilt wheels but **capped at older tree-sitter (~0.21/0.22) and Python ≤3.11**; maintenance lagging |
| Languages | **305+**, incl. python/javascript/typescript/tsx [CITED: github.com/Goldziher/tree-sitter-language-pack] | ~165, incl. py/js/ts |
| API | `get_parser("python")`, `get_language("python")` [CITED: docs.tree-sitter-language-pack.kreuzberg.dev] | `get_parser`/`get_language` (same names) |
| tree-sitter dep | tracks current `tree-sitter` (0.25.x line) | pins old tree-sitter — friction with `tree-sitter==0.25.2` |

`tree-sitter-language-pack` is actively maintained, covers more languages, and supports current Python/tree-sitter — the better offline pick. **Pin both** in `pyproject.toml`: `tree-sitter==0.25.2` + `tree-sitter-language-pack==1.8.1` [ASSUMED versions — confirm at install time].

> **OFFLINE-INSTALL RISK (flag for planner):** newer `tree-sitter-language-pack` docs mention "on-demand downloads" / "automatic caching" of grammars. The phase's offline-CI accept gate requires that `get_parser("python"|"javascript"|"typescript")` works with **zero network**. **Offline-install proof approach:** in 09-03, add a Wave-0 smoke test that (a) installs from wheels with `--no-index --find-links <local wheelhouse>` OR confirms the chosen version bundles py/js/ts grammars IN the wheel (not lazy-downloaded), and (b) calls `get_parser("python")` + parses a fixture with the network stubbed/disabled, asserting a non-empty tree. If the pinned 1.8.1 lazy-downloads any of py/js/ts, fall back to per-language `tree-sitter-python`/`-javascript`/`-typescript` wheels (all prebuilt) or pin an earlier all-bundled version.

### Symbol kinds extractable (per language, via tree-sitter queries)
- **Python:** `function_definition`, `class_definition`, `import_statement`/`import_from_statement`.
- **JavaScript:** `function_declaration`, `class_declaration`, `import_statement`, `method_definition`.
- **TypeScript/TSX:** the JS node kinds + `interface_declaration`, `type_alias_declaration`, `enum_declaration`.
The impl writes one tree-sitter `Query` per language extracting `(node, name_capture, start_point)` → emits `(symbol_name, kind, file, line)` (line = `start_point.row + 1`). REPO-02 acceptance only needs "file+line of a known function/class" — the minimal viable query set is functions + classes + imports.

### `RepoIndex` port shape (one provider seam for grep AND symbol)
Define in `agents/runtime/base.py` (or a `repo_index` capability port — planner's call) a port exposing TWO methods so grep/glob (default) and the symbol index resolve through ONE seam:
```python
def search(self, pattern: str, *, glob: str | None = None) -> list[Match]   # grep/glob — DEFAULT, always available
def symbol_query(self, name: str) -> list[SymbolHit]                          # SymbolHit(file, line, kind) — only when index built
```
The default impl backs `search` with `Workspace.search` (ripgrep/`git grep`/stdlib walk); the tree-sitter impl additionally backs `symbol_query`. `Match`/`SymbolHit` are kernel-pure dataclasses (like `DeliverableContext` `kernel_services.py:99`).

### N6 threshold + manifest opt-in flag (D-04)
- **N6 = a documented module-level config constant** (e.g. `REPO_INDEX_FILE_THRESHOLD = 2000` files, or a byte cap). Recommend a named constant in the `repo_index` capability module + an override in `app.core.config.Settings` (alongside `RUNS_ROOT`/`RUN_DIR_TTL_HOURS`). Pick a conservative default (e.g. 2000 source files OR 50 MB) and DOCUMENT it — the exact value is Discretion.
- **Manifest opt-in flag lives on the Step/workflow schema.** The cleanest home is a boolean on a `RepoSpec`-adjacent block OR a step-level field. `RepoSpec` (`plan.py:256-262`, `url`/`ref`/`branch`) is the brownfield binding — add `index: bool = False` (or `symbol_index: bool = False`) there, OR add a `repo_index` field on `Step`. Either way the COMPILER only records the flag (INV-5 — manifests are pure data, no control flow); the index-build decision (`flag OR file_count > N6`) lives in the `repo_inventory`/`repo_index` capability, never the compiler.

### Placement (heavy-dep boundary)
`repo_index` carries `tree_sitter` + the grammar pack → **app-side** capability (reached via handle), so the import isolation holds and the banned-pattern gate stays green (tree-sitter is a LIBRARY, not a deep-agent runtime — `test_banned_patterns.py` only bans `create_deep_agent`/hand-rolled loops, not tree-sitter; INV-13 untouched). The `tree_sitter` import lives ONLY inside that module (REPO-02 acceptance: "`tree-sitter` is imported only behind the `RepoIndex` capability").

---

## R-D (D-05/D-07) — MCP client + the async→sync binding risk

### Library facts [verified PyPI + official docs — neither installed offline]
- **`langchain-mcp-adapters` latest = 0.2.2** (released 2026-03-16) [VERIFIED: PyPI; CITED: pypi.org/project/langchain-mcp-adapters]. Recommend pin `langchain-mcp-adapters>=0.2.2` [ASSUMED — confirm at install].
- **`MultiServerMCPClient` API** [CITED: reference.langchain.com/python/langchain-mcp-adapters + docs.langchain.com/oss/python/langchain/mcp]:
  - Construct with a server-config dict: stdio shape `{"<name>": {"command": "python", "args": ["/path/to/server.py"], "transport": "stdio"}}` (also `"streamable_http"`/`"sse"` transports).
  - `tools = await client.get_tools()` — **ASYNC**; returns a flat list of all tools from all connected servers.
  - The client is **stateless by default**: each tool invocation opens a fresh `ClientSession`, runs the tool, cleans up. (No long-lived connection to manage during the agent run.)
  - Returned tools are **LangChain-compatible** — they drop straight into `model.bind_tools(tools)` and LangGraph `create_agent(model, tools)`. **This satisfies INV-13:** they bind INTO the `deepagents` tool set; they never replace the runtime.
  - Tool names can be prefixed with the server name to avoid collisions — useful for the `server.tool` reference shape MCP-03 validates.
- **The `mcp` Python SDK is a transitive dependency** of `langchain-mcp-adapters` and provides the stdio server primitives (`mcp.server` / `FastMCP`) for the D-06 stub. **Neither `mcp` nor `langchain-mcp-adapters` is installed offline** — install + pin in 09-05.

### The async→sync binding mechanism (the deepest mechanical risk — RESOLVED)
**The codebase already solved this exact class of problem and the solution is the model to copy.** The factory's `create_runner`/`_resolve_runner_tools`/`_build_runner_tools` is **SYNC** (`factory.py:95,457`), called from the **async** engine. The Constitution had the identical "async value needed inside the sync factory under a running loop" problem — solved by **awaiting ONCE at the async run-entry and stashing on the context** (`prewarmed_constitution`):
- `engine.py:687-694` — at async run entry, `ectx.prewarmed_constitution = await get_workflow_memory().get_constitution(_const_key)`, BEFORE any sync `create_runner` call.
- `factory.py:62` / `_inject_constitution` (`factory.py:316-342`) — the sync factory reads `ctx.prewarmed_constitution` WITHOUT awaiting (the comment at `factory.py:60-62` and `engine.py:675-686` document this as "the single sync-safe path, AGENTRT-06 / F4 / R12").

**Recommendation — connect-at-run-entry, mirror `prewarmed_constitution`:**
1. At the async engine run-entry (the same block as the Constitution pre-warm, `engine.py:687`), for each `mcp`/`integrations` scope active on the run, construct `MultiServerMCPClient(<catalog-config>)` and `bound_mcp_tools = await client.get_tools()` ONCE. Stash on the per-run context (e.g. `ectx.prewarmed_mcp_tools` / a new `AgentContext.prewarmed_mcp_tools: list = []` field beside `prewarmed_constitution` at `factory.py:62`).
2. `_resolve_runner_tools`/`_build_runner_tools` (sync, `factory.py:457`) reads the pre-bound toolset off `ctx` and UNIONS it into the custom-tool list — NO await, NO `asyncio.run`/`run_until_complete` inside the running loop (which would raise `RuntimeError: This event loop is already running` or spawn a double loop). The stateless client means no connection lifecycle to thread through the sync path.
3. The bound tools pass straight to `DeepAgentRunner(tools=custom_tools, …)` (`factory.py:189`) → `create_deep_agent` native tool set. INV-13 satisfied (augment, never replace).

**Reject:** calling `asyncio.run(client.get_tools())` inside the sync factory (double-event-loop hazard under the running engine loop) and any `nest_asyncio` bridge (fragile, banned-pattern smell). The pre-warm pattern is proven in-tree and parity-safe (it degrades to empty when no scope is active, exactly like the Constitution no-op).

### Scoped creds (MCP-02 / D-07)
Per-owner MCP credentials extend the **`UserGithubCredential` PAT precedent** (`app/models/handoff.py:40` — `user_id` FK to `users`, `encrypted_pat` Text blob, owner-scoped, droppable in one statement) and the Phase-5 `ScopedStore` (`agents/authz.py:58`, default-deny: `WHERE owner_id=:owner AND workspace_id=:ws`). New creds are owner-scoped + encrypted, NEVER global; the cross-owner `assert_owns`/scoped-read **denial test is the gate** (the pattern at `previous_run.py:162` — `await scoped_store.assert_owns(...)`, `PermissionError` propagates, never swallowed).

### Compile-validation (MCP-03)
The compiler ALREADY has the seam: `is_registered(kind,name)` per-reference (`compiler.py:159,237,243…`) raising `CompilerError` naming the bad ref, `is_user_allowed` trust check (`compiler.py:207`), and **`"mcp"`/`"integrations"` are ALREADY in the allowed tools-grant keys** (`compiler.py:104-105`, `_compile_tool_grant` list-fields `compiler.py:352`). MCP-03 ADDS a per-`server.tool` validation loop over `step.tools.mcp`: split `server.tool`, assert the `mcp_server` is registered AND (`is_user_allowed` for user/db manifests) AND the named tool is in the server's exposed-tool allow-list → else `CompilerError` naming the offending `server.tool`. Same per-reference site, same error idiom.

### Gating (MCP-04)
Write/powerful servers (Filesystem/Postgres `user_allowed=false`, anything write/network) + write-scopes require the **`security` gate** (`("gate","security")` registered 08-02, `registry.py:93`) + the **`secrets` permission** (`ToolPermissions.secrets: list[str]` `plan.py:70`; `ToolPermissions.check(action, perms)` `plan.py:172` is the enforcement primitive). Read-scopes (`gitlab_read`/`jira_read`) bind ungated.

### Stub stdio MCP server fixture (D-06)
A tiny real MCP server in `tests/` (e.g. `tests/agents/fixtures/stub_mcp_server.py`) built on the `mcp` SDK's stdio server (`FastMCP`/`mcp.server.stdio`) exposing 1-2 trivial tools (e.g. `echo`, `add`). The test: `MultiServerMCPClient({"stub": {"command": "python3.11", "args": [<stub path>], "transport": "stdio"}})`; `tools = await client.get_tools()`; assert the allowed tool is present and a `deepagents` agent (scripted model) can invoke it. Fully offline — exercises the REAL stdio transport + tool-binding (MCP-01/MCP-04 accept). This proves the live adapter path without a network.

### No collision with the inbound server
`app/api/mcp.py` is an **inbound** MCP *server* — a hand-rolled JSON-RPC-2.0-over-FastAPI-HTTP endpoint (`mcp.py:4-6`, `_handle_tools_list`/`_handle_tools_call` `mcp.py:187-294`), **using NO SDK**. The net-new **client** (`McpClientAdapter` over `langchain-mcp-adapters`) is the opposite direction and fully additive — zero collision.

---

## R-E (D-08/D-09) — Integration bridge + handoff-bypass deletion blast radius

### What the handoff system actually is (file-mapped)
- **The bypass to delete:** `app/agents/handoff/coding_agent.py` `CodingAgent.propose_edits` (`coding_agent.py:145-185`) calls `build_model(...).ainvoke([...])` directly (`coding_agent.py:164-170`) — a one-shot LLM call that **skips `create_deep_agent`/`create_runner`** (the INV-13 gap D-09 names). This is the path the unified `integration_provider` supersedes.
- **Callers of `CodingAgent`:** `app/services/handoff_pipeline.py:30,420-422` (`run_handoff_pipeline` instantiates it). `run_handoff_pipeline` is called by `app/api/handoff.py:368`.
- **The `/api/handoff` HTTP router is a LIVE EXTERNAL SURFACE** — `router = APIRouter(prefix="/api/handoff")` (`app/api/handoff.py:51`), registered in `app/main.py:153` (`app.include_router(handoff_router)`), with multiple public routes: `POST /api/handoff/...` (`handoff.py:172`), `GET /api/handoff/{token}` (`handoff.py:227`), `POST /api/handoff/{token}/start` (`handoff.py:265`). There is ALSO a websocket handoff router (`app/main.py:157`). This is the IDE→PR `/flowin-handoff` feature with outside consumers.

### Test surface gating the deletion
- `tests/integration/test_handoff_api.py` — `_safe_workspace_join`/`_apply_edits`/`_branch_name`/`parse_github_url`.
- `tests/integration/test_handoff_contract.py` — drives the REAL `run_handoff_pipeline` under a mock seam (`CodingAgent`/`TestAgent`/`ComplianceAgent`/`handoff_github` mocked).
- `tests/unit/test_handoff_agents.py` — `CodingAgent().propose_edits` unit tests (`test_handoff_agents.py:33,149…`).
- `tests/agents/test_phase8_live.py:366` + `tests/agents/live_harness.py:858-1068` — World 3 `/flowin-handoff` live harness (handoff_github mocked).

### Precise deletion scope (D-09)
**DELETE in-plan (the true superseded bypass):**
- `app/agents/handoff/coding_agent.py` (`CodingAgent`) — the `build_model().ainvoke` one-shot that skips the runtime — once the `integration_provider` path produces equivalent edits through `create_runner`.
- Its `CodingAgent` references in `app/services/handoff_pipeline.py:30,420-422` and `app/agents/handoff/__init__.py:10,15`.
- The dedicated `CodingAgent` unit tests (`tests/unit/test_handoff_agents.py` coding cases) move/delete alongside.
- **Migration-ledger entry required:** add an `L#`/`D#` row to `specs/003-workflow-engine-decoupling/migration-ledger.md` with a verbatim grep gate (e.g. `class CodingAgent` → 0 matches in `backend/`) — the ratchet (`tests/agents/test_migration_ledger.py:53-55` scopes non-kernel rows to whole `backend/`). Banned-pattern gate (`test_banned_patterns.py`) confirms no new hand-rolled agent loop.

**RETAIN with explicit ledger justification (NOT a bypass to break):**
- `app/api/handoff.py` + `app/api/websocket_handoff.py` (the `/api/handoff` routers) — **live external IDE integration surface with outside consumers** (registered in `main.py:153,157`). The deletion-scope guard (D-09 directive) is explicit: "if `/flowin-handoff` is a live external integration surface with outside consumers, retain it with an explicit ledger justification rather than breaking a consumer." → **RETAIN.** Add a ledger row marking it RETAINED-with-justification.
- `app/services/handoff_github.py` (git clone/branch/stage/commit/push helpers) — its push capability is N4-deferred elsewhere but the module is the GitHub git-op layer the retained endpoint uses; **retain** unless fully re-homed onto `Workspace.git_diff` this phase (out of REPO-04's diff-only scope).
- `app/services/handoff_pipeline.py` minus the `CodingAgent` step — the orchestration the retained endpoint drives; retain, re-point its coding step at the `integration_provider`/unified runner OR leave the legacy pipeline intact for the retained endpoint and only remove the `CodingAgent` import. **Planner decision: re-point vs retain-whole — gate either choice on the handoff contract tests (`test_handoff_contract.py`) staying green.**
- `app/models/handoff.py` (incl. `UserGithubCredential:40`) — the PAT precedent + handoff session model; **retain** (the PAT pattern is the MODEL for MCP/integration scoped creds, D-07).

### The integration bridge (D-08)
`integration_provider` capabilities for github/gitlab/jira/slack are thin: each takes a catalog `mcp_server` + an `integrations` scope and surfaces that server's tools into `create_runner`'s tool set via the same factory seam (`_build_runner_tools`/`_resolve_runner_tools` `factory.py:457`) and the same pre-warm binding (R-D). ONE mechanism (MCP) — no PyGithub/python-gitlab/Slack-SDK parallel path. The `integrations` scopes (`gitlab_read`/`github_read`/`jira_read`/`slack_post`, default none) live in `ToolPermissions.integrations: list[str]` (`plan.py:72`) and are recorded per-run via `record_capabilities` (`engine.py:556`, `ScopedStore.record_capabilities`).

---

## R-F (D-10) — Repo-capability placement & shapes

### Base-class contracts (the exact signature each new capability follows)
| Capability | Port (`agents/capabilities/base.py`) | Method signature | Registration |
|------------|--------------------------------------|------------------|--------------|
| `repo_diff` | `DeliverableResolver` (`base.py:64`) | `def resolve(self, ctx) -> Any` | `@register("deliverable", "repo_diff")` |
| `repo` provider | `ContextProvider` (`base.py:75`) | `async def load(self, ctx) -> dict[str, str]` | `@register("context_provider", "repo")` |
| `repo_inventory` | new kind `repo_inventory` (own capability) | follows the resolver/provider idiom; lineage-tracked artifact | `@register("repo_inventory", "default")` |
| `context_pack`/`context_selector` | new kind `context_pack` | builds targeted subset | `@register("context_pack", "default")` |

Pattern is uniform: a stateless class, `name: str` attribute, ONE method, `@register(kind, name)` decorator, import-pure (`from agents.capabilities.registry import register` ONLY), reach `app.*`/disk via `ctx.runner`/`ctx.scoped_store` handles. Reference impls: `serialized_sandbox.py:24-40` (resolver), `opendesign.py`/`previous_run.py:115` (provider). New kinds add their `(kind,name)` to `_KNOWN` (`registry.py:76`) and a `discover()` import (`registry.py:193-227`).

### Pure-stdlib vs heavy-dep placement
| Capability | Deps | Placement |
|------------|------|-----------|
| `repo_inventory` | pure stdlib (`os.walk`/`pathlib`/`fnmatch` for ignore-globs; `git ls-files` via the `Workspace` handle) | **kernel-side** `backend/agents/capabilities/repo_inventory/` |
| `context_pack`/`context_selector` | pure stdlib | **kernel-side** `backend/agents/capabilities/context_pack/` |
| `repo` ContextProvider | pure stdlib (reads via handle) | **kernel-side** `backend/agents/capabilities/context_providers/repo.py` |
| `repo_diff` | pure stdlib — reads diff from `Workspace.git_diff` via handle (does NOT shell git) | **kernel-side** `backend/agents/capabilities/deliverables/repo_diff.py` |
| `repo_index` | `tree_sitter` + grammar pack (HEAVY) | **APP-SIDE** (reached via handle) — see R-C |

**`repo_diff` reads from `Workspace.git_diff` (D-01), never shells git directly** — the resolver calls `ctx.runner.workspace.git_diff(base_branch, working_branch)` (or `ctx.runner.git_diff(...)`), and the `LocalSandboxRuntime.Workspace` owns the single `git diff` subprocess. Resolver output = file tree + per-file unified diff + change summary; **diff-only, no push** (N4 — git log on the working branch shows no new commit beyond the branch point).

### `repo_inventory` ignore/skip/cap handling (REPO-01 acceptance)
- **`.gitignore` + `.flowinignore`:** parse both; prefer `git ls-files --cached --others --exclude-standard` (honors `.gitignore` natively) via the `Workspace` handle, then additionally apply `.flowinignore` globs with `fnmatch`/`pathspec`-style matching. (If avoiding a `pathspec` dep, stdlib `fnmatch` per-line is sufficient for the fixture acceptance.)
- **Binary-skip:** detect via null-byte sniff (read first ~8 KB, skip if `b"\x00"` present) — same defensive idiom as `serialize_sandbox_deliverable`'s UTF-8-decode-or-skip (`sandbox.py:236-243`).
- **Size-cap:** a documented per-file byte cap (e.g. skip/truncate files > 1 MB) + a total-inventory cap; constants in the capability module.
- Output: file tree + language stats (by extension) + dependency list (parse `requirements.txt`/`pyproject.toml`/`package.json` for the fixture's primary languages). Lineage-tracked as a typed artifact `kind=repo_inventory` via `ScopedStore.write_ref` (`authz.py:133`).

---

## R-G (D-11) — Migration 0017 chain

### Codebase facts [VERIFIED in `backend/alembic/versions/`]
- **Head chain:** `0016_capability_hardening_tables.py` has `revision="0016"`, `down_revision="0015"` (`0016:24-25`). So **0017 MUST set `down_revision="0016"`**, `revision="0017"`. (Heads in tree end at 0016 — `ls alembic/versions/` confirms 0009…0016 contiguous, no 0017 yet.)
- **`workspaces` table** created in `0014_typed_artifacts_persistence.py:82-99` with columns: `id` (String PK), `owner_id` (String NN), `workspace_id` (String NN), `kind` (**`sa.String()`** NN, `server_default="sandbox"`), `runtime` (String NN, `server_default="local"`), **`repo_id` (`sa.String()` nullable)** — the "Phase 9 forward field", `ttl` (String, `server_default="run_ttl"`), `created_at` (DateTime NN).
- **`workspaces.kind` is a free `String`, NOT an enum/CHECK constraint** (`0014:88`). **Therefore `kind='repo'` requires NO additive widening** — it just works. (D-11's "or needs the enum/constraint widened additively" → NOT needed; confirm there's no app-layer enum gate, but the DB column is unconstrained.)
- **`workspaces.repo_id` is already a nullable `String`** (`0014:93`) — 0017 only needs to START POPULATING it (and optionally add an FK constraint to the new `repositories.id`). Note: `0014` did NOT declare an FK on `repo_id` (the target table didn't exist yet), so 0017 either adds `op.create_foreign_key` or leaves it a soft reference — adding the FK is the cleaner choice but requires `repositories` to be created FIRST in the same migration.
- **`ScopedStore`** lives at `agents/authz.py:58`; constructed `(owner_id, workspace_id)` (`authz.py:70-79`); `write_ref` stamps `owner_id`/`workspace_id` (`authz.py:133-211`); `create_workspace`/`record_capabilities` are the run-entry writers (`engine.py:554-556`). The `repositories` model + its scoped writer mirror this default-deny owner/workspace-scoped pattern.

### `repositories` table (0017 upgrade)
```
repositories:
  id            String PK
  owner_id      String NN            # carries owner_id (constraint)
  workspace_id  String NN            # carries workspace_id (constraint)
  provider      String NN            # 'github' | 'gitlab' | 'local'  (free String, no enum)
  url           String NN
  default_branch String NN
  auth_ref      String nullable      # scoped cred reference (the PAT/MCP-cred pointer)
  created_at    DateTime NN
  PK(id)
```
Both `repositories` and the new `kind=repo` `workspaces` row carry `owner_id`+`workspace_id` (the additive-migration invariant Q3). `provider` as a free `String` (no `sa.Enum`) keeps the migration additive and reversible — consistent with `kind`/`runtime` being plain Strings.

### Reversibility + ledger gate
- `upgrade()`: `op.create_table("repositories", …)` then optionally `op.create_foreign_key(..., "workspaces", "repositories", ["repo_id"], ["id"])`.
- `downgrade()` (`-1`): drop the FK (if added) then `op.drop_table("repositories")` — clean reverse (the `0014` precedent at `0014:236` `op.drop_table("workspaces")` is the model).
- **Gate:** `cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head` reversible; `python3.11 -m pytest tests/agents/test_migration_ledger.py -v` stays green. (Acceptance: a sample repo run inserts exactly ONE `repositories` row + ONE `kind=repo` `workspaces` row linked by `repo_id`.)

> **Migration runtime note:** Alembic upgrade/downgrade needs a DB. Per backend/CLAUDE.md the full pytest hangs offline (Postgres-gated). Verify the migration against a **local SQLite/throwaway Postgres** in 09-02, OR assert structure via the migration-ledger test (which parses the ledger, not a live DB). Flag in Open Risks.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary | Rationale |
|------------|-------------|-----------|-----------|
| Runtime ports (`base.py`) | Kernel (`agents/runtime/`) | — | import-linter authority; kernel imports only ports |
| `LocalSandboxRuntime` (`local.py`) | App (`app/agents/runtime/`) | Kernel handle | touches `app.core.config.settings` + sandbox disk utils |
| `RunSandbox` refold | App (`app/agents/sandbox.py`) | — | name survives in place; delegates to `Workspace` |
| `repo_inventory`/`context_pack`/`repo` provider/`repo_diff` | Kernel (`agents/capabilities/`) | App via handle (git/disk) | pure-stdlib; reach git/disk via `ctx.runner` |
| `repo_index` (tree-sitter) | App-side capability | Kernel handle | heavy dep; import-isolated behind the module |
| `McpClientAdapter` + catalog | Kernel capability (registration data) | App via handle (client + creds) | `@register` data kernel-side; the async client/creds reached at run-entry |
| MCP client connect/bind | App / engine run-entry (async) | Sync factory consumes | mirrors `prewarmed_constitution` |
| `integration_provider` bridge | Kernel capability | App via MCP client | one mechanism (MCP); binds at factory seam |
| Persistence (`repositories`/`workspaces`) | DB / `ScopedStore` (`agents/authz.py`) | Alembic 0017 | owner/workspace-scoped default-deny |
| Compile-validation (`tools.mcp`) | Kernel (`agents/workflows/compiler.py`) | Registry | INV-4 per-reference, extends existing seam |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `langchain-mcp-adapters` | >=0.2.2 [ASSUMED] | MCP client → LangChain/LangGraph-compatible tools (`MultiServerMCPClient.get_tools`) | Official LangChain MCP adapter; tools bind into `deepagents` (INV-13) |
| `tree-sitter` | ==0.25.2 [ASSUMED] | Symbol-index parsing engine | The tree-sitter core py binding; prebuilt wheels |
| `tree-sitter-language-pack` | ==1.8.1 [ASSUMED] | 305+ prebuilt grammars incl. py/js/ts (`get_parser`/`get_language`) | Prebuilt abi3 wheels, no C toolchain — offline-installable |
| `mcp` (transitive) | (via langchain-mcp-adapters) | stdio server SDK for the D-06 stub | Reference MCP SDK; provides `FastMCP`/stdio server |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `tree-sitter-language-pack` | `tree-sitter-languages` (grantjenks) | Fewer langs (~165), pins OLD tree-sitter (~0.22) + Python ≤3.11 — friction with the 0.25 line |
| `tree-sitter-language-pack` (bundled) | per-language `tree-sitter-python`/`-javascript`/`-typescript` wheels | More install wiring but guaranteed offline-bundled — the FALLBACK if 1.8.1 lazy-downloads grammars |
| pre-warm MCP at run-entry | `asyncio.run(get_tools())` in sync factory | Double-event-loop hazard under the running engine loop — REJECTED |
| MCP-everything (D-08) | PyGithub/python-gitlab/Slack-SDK parallel path | Two mechanisms doing one job (INV-12 dual-impl smell) — REJECTED |

**Installation:**
```bash
cd backend && python3.11 -m pip install \
  "tree-sitter==0.25.2" "tree-sitter-language-pack==1.8.1" "langchain-mcp-adapters>=0.2.2"
```

## Package Legitimacy Audit

> slopcheck was **NOT available** at research time (`pip install slopcheck` failed offline). Per protocol, all new packages are tagged `[ASSUMED]` and the planner MUST gate each install behind a `checkpoint:human-verify` task before adding to `pyproject.toml`.

| Package | Registry | Latest (verified) | Source Repo | slopcheck | Disposition |
|---------|----------|-------------------|-------------|-----------|-------------|
| `langchain-mcp-adapters` | PyPI | 0.2.2 [VERIFIED: PyPI] | github.com/langchain-ai/langchain-mcp-adapters | unavailable | [ASSUMED] — checkpoint before install |
| `tree-sitter` | PyPI | 0.25.2 [VERIFIED: PyPI] | github.com/tree-sitter/py-tree-sitter | unavailable | [ASSUMED] — checkpoint before install |
| `tree-sitter-language-pack` | PyPI | 1.8.1 [VERIFIED: PyPI] | github.com/Goldziher/tree-sitter-language-pack | unavailable | [ASSUMED] — checkpoint before install |
| `tree-sitter-languages` (alt) | PyPI | 1.10.2 [VERIFIED: PyPI] | github.com/grantjenks/py-tree-sitter-languages | unavailable | [ASSUMED] — fallback only |
| `mcp` (transitive) | PyPI | via adapter dep | github.com/modelcontextprotocol/python-sdk | unavailable | [ASSUMED] — pulled by langchain-mcp-adapters |

**Packages removed due to slopcheck [SLOP]:** none (slopcheck unavailable). **Flagged [SUS]:** none. All registry existence VERIFIED via `python3.11 -m pip index versions`; package NAMES discovered via WebSearch/SPEC → `[ASSUMED]` per provenance rule.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP protocol client | A custom JSON-RPC stdio client | `MultiServerMCPClient` | Transport + session lifecycle + LangChain tool adaptation handled; INV-13 compatibility |
| Symbol extraction | Regex/AST-walk per language | `tree-sitter` queries via `tree-sitter-language-pack` | Robust multi-lang parsing; prebuilt grammars |
| async→sync bridging | `asyncio.run`/`nest_asyncio` in the sync factory | The `prewarmed_constitution` run-entry pattern (`engine.py:687`) | Proven in-tree; no double-loop; parity-safe no-op |
| git diff/clone/branch | Shelling git from the resolver | `Workspace.git_diff`/`clone_repo`/`create_branch` (D-01 port) | One owner of git subprocess; ECS-swappable; resolver stays pure |
| `.gitignore` matching | Custom glob engine | `git ls-files --exclude-standard` via the handle | git already implements ignore semantics |
| Capability discovery | An auto-walk/entry-point scanner | `@register` + explicit `discover()` imports (`registry.py:162`) | Deterministic; import-linter can reason about it (D-01 rejects auto-discovery) |
| Scoped creds store | A new cred table from scratch | The `UserGithubCredential` PAT pattern + `ScopedStore` | Owner-scoped/encrypted precedent (`models/handoff.py:40`) |

## Common Pitfalls

### Pitfall 1: Re-baselining the characterization goldens
**What goes wrong:** the RunSandbox refold subtly changes the `final_output` string or event stream, and someone runs `SNAPSHOT_UPDATE=1` to "fix" the test. **How to avoid:** SNAPSHOT_UPDATE stays UNSET this phase; if a golden fails, the refold is wrong (INV-3), not the golden. The byte oracle is `serialize_sandbox_deliverable`'s raw-bytes read (`sandbox.py:236`) — preserve it exactly.

### Pitfall 2: tree-sitter lazy grammar download breaking offline CI
**What goes wrong:** `get_parser("python")` triggers a network download under a newer `tree-sitter-language-pack`. **How to avoid:** Wave-0 offline-install smoke test (R-C); pin a version whose wheel bundles py/js/ts, or fall back to per-language wheels.

### Pitfall 3: Double event loop from the MCP client
**What goes wrong:** calling `await`/`asyncio.run` on `get_tools()` inside the SYNC factory under the running engine loop → `RuntimeError: event loop already running`. **How to avoid:** connect + `get_tools()` ONCE at async run-entry; stash on `ctx`; the sync factory only reads (R-D).

### Pitfall 4: Deleting the live `/api/handoff` endpoint
**What goes wrong:** treating the whole handoff system as "the bypass" and removing the HTTP router breaks IDE consumers. **How to avoid:** delete ONLY `CodingAgent` (the `build_model().ainvoke` bypass); RETAIN the routers (`main.py:153,157`) with a ledger justification (R-E).

### Pitfall 5: Capability impl importing `app.*` or the kernel
**What goes wrong:** a repo capability imports `app.agents.sandbox` directly → import-linter contract 3 breaks. **How to avoid:** reach disk/git/app ONLY via `ctx.runner` (`KernelServices`) / `ctx.scoped_store` (dynamic attribute access off `Any`-typed fields — `serialized_sandbox.py:36`, `previous_run.py:159`).

## Runtime State Inventory

> Phase 9 is largely greenfield-additive, but the RunSandbox refold + handoff deletion touch runtime state.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `workspaces` rows (kind='sandbox' today); `repo_id` nullable + unpopulated; no `repositories` table | code edit (start writing `kind='repo'`+`repo_id`) + data migration (0017 creates `repositories`) |
| Live service config | None — phase accepts offline against local git fixtures + stub MCP server; live external (GitLab/GitHub/Jira/Slack/MCP) deferred to milestone-end | none this phase |
| OS-registered state | None — None verified by absence of any OS task/service registration in the repo | none |
| Secrets/env vars | `UserGithubCredential.encrypted_pat` (PAT precedent, `models/handoff.py:40`) — RETAINED (model for MCP creds). New scoped MCP/integration creds extend it (additive table or rows) | none destructive; new creds additive |
| Build artifacts | `lint-imports` cached results / pytest caches — none stale-after-rename here. `pyproject.toml` deps grow (3 new libs) | reinstall deps after `pyproject.toml` edit |

**The canonical question — after all repo files are updated, what runtime systems still hold old state?** The `RunSandbox` name survives (D-02) so no on-disk run-dir layout changes; the only DB delta is the additive `repositories` table + newly-populated `workspaces.repo_id`/`kind='repo'`.

## Validation Architecture (Nyquist)

> nyquist_validation enabled (not `false` in config). Each of the 16 SPEC acceptance criteria mapped to an OFFLINE sampling point. Framework: pytest (`python3.11 -m pytest`, no venv); targeted offline suite per backend/CLAUDE.md (full suite hangs offline).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`@pytest.mark.asyncio`) |
| Config | `backend/pyproject.toml` (`[tool.pytest...]`) |
| Quick run (per task) | `cd backend && python3.11 -m pytest tests/agents/<targeted file> -x` |
| Parity suite | the 5 characterization files + `test_sandbox_deliverable.py` + `test_manifest_parity.py` (see R-B) |
| Gate suite | `lint-imports` (`/opt/homebrew/bin/lint-imports`), `test_banned_patterns.py`, `test_migration_ledger.py` |

### Acceptance Criterion → Offline Sampling Point
| # | SPEC acceptance (abbrev) | Offline test / observation |
|---|--------------------------|----------------------------|
| 1 | `base.py` ports; kernel imports only ports | `cd backend && lint-imports` → 3 (→4) kept / 0 broken; new `agents.runtime` contract |
| 2 | `LocalSandboxRuntime` clone/branch/read/write/search/diff; exec DENIED | new `tests/agents/test_local_runtime.py` against a local git fixture; assert `exec_command` under default policy raises |
| 3 | 5-pipeline byte+event parity; no `if repo:` fork | the parity suite (R-B); `grep -rn "if repo" agents/execution_engine/` → 0 |
| 4 | 0017 adds `repositories`; one row each; `upgrade`→`downgrade -1` reversible; ledger green | `alembic upgrade head && alembic downgrade -1` (local DB); `test_migration_ledger.py` |
| 5 | `RepoInventory` lists src, excludes `.gitignore`/`.flowinignore`+binary, size caps, lang stats | `test_repo_inventory.py` on a seeded fixture w/ a binary file + `.flowinignore` entry |
| 6 | grep default; tree-sitter index returns file+line; tree-sitter imported only behind capability | `test_repo_index.py` (index off → grep; index on → symbol_query file+line); `grep -rn "import tree_sitter" agents/ app/` only the capability module |
| 7 | `ContextPack` targeted subset, excludes unrelated, lineage-tracked, via `repo` provider | `test_context_pack.py` — pack contains target+neighbors, excludes others; artifact_ref written |
| 8 | `repo_diff` tree+per-file diff(edit)+summary; no push | `test_repo_diff.py` — diff contains the edit; `git log` working branch shows no new commit |
| 9 | sample workflow offline end-to-end; diff has edit; exec=off everywhere | `test_sample_brownfield_workflow.py` (scripted model, local fixture); assert effective-perms exec=off per step |
| 10 | `McpClientAdapter` connects to STUB, lists, binds an allowed tool offline | `test_mcp_client.py` w/ the in-repo stdio stub server (D-06) |
| 11 | catalog `user_allowed` flags (FS/PG false); per-owner cred not cross-owner readable | `test_mcp_catalog.py` (assert `/api/capabilities` flags); `ScopedStore` cross-owner denial test |
| 12 | compiler rejects `unknown_server.tool`/not-allowed; valid compiles | `test_mcp_compile_validation.py` — `CompilerError` names offending `server.tool` |
| 13 | write/powerful needs `security`+`secrets`; read-scope ungated | `test_mcp_gating.py` — FS/PG bind rejected w/o gate; `gitlab_read` binds |
| 14 | github/gitlab/jira/slack resolve from `create_runner` | `test_integration_providers.py` — runner gains the integration's tools |
| 15 | `integrations` default none; `gitlab_read` binds read-only; `run_capabilities` records scopes+servers+runtime | `test_integration_scopes.py` + assert `record_capabilities` row |
| 16 | lint-imports/banned-pattern/migration-ledger/parity all green | the gate suite + parity suite |

### Sampling Rate
- **Per task commit:** the targeted file for the task (`-x`).
- **Per wave merge:** parity suite + gate suite.
- **Phase gate:** full offline targeted suite + `lint-imports` green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/agents/test_local_runtime.py` (REQ RUNTIME-01/02) + a local git fixture seeder
- [ ] `tests/agents/test_repo_inventory.py` + `tests/agents/test_repo_index.py` (offline tree-sitter smoke) (REPO-01/02)
- [ ] `tests/agents/test_context_pack.py` / `test_repo_diff.py` / `test_sample_brownfield_workflow.py` (REPO-03/04/05)
- [ ] `tests/agents/fixtures/stub_mcp_server.py` + `test_mcp_client.py`/`test_mcp_catalog.py`/`test_mcp_compile_validation.py`/`test_mcp_gating.py` (MCP-01..04)
- [ ] `tests/agents/test_integration_providers.py` / `test_integration_scopes.py` (INTEG-01/02)
- [ ] New import-linter contract for `agents.runtime` in `pyproject.toml`
- [ ] Migration-ledger row(s) for the `CodingAgent` deletion + the retained-endpoint justification
- [ ] Dep installs (3 libs) gated by `checkpoint:human-verify` (slopcheck unavailable)

## Security Domain

> security_enforcement enabled.

### Applicable ASVS Categories
| ASVS | Applies | Standard control (in this codebase) |
|------|---------|-------------------------------------|
| V1 Architecture | yes | Hexagonal ports; import-linter boundary; least-privilege defaults |
| V2 Authentication | yes (MCP/integration creds) | `UserGithubCredential` encrypted PAT pattern (`models/handoff.py:40`); scoped per-owner |
| V4 Access Control | yes | `ScopedStore` default-deny owner/workspace scoping (`authz.py`); `assert_owns` cross-owner `PermissionError` propagates |
| V5 Input Validation | yes | Compiler INV-4 `is_registered`/`is_user_allowed`; `RunSandbox.path_for` traversal rejection (`sandbox.py:77`); repo-relative path checks |
| V6 Cryptography | yes | Reuse the existing encrypted-cred mechanism (`encrypted_pat`) — never hand-roll |
| V12 Files/Resources | yes | `.gitignore`/`.flowinignore`/binary-skip/size-cap; no path traversal; clone into the run dir only |

### Known Threat Patterns
| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| MCP write/exec server abuse | Elevation of Privilege | `security` gate + `secrets` permission + scoped creds; FS/PG `user_allowed=false`; read-scopes ungated |
| Cross-owner cred / repo read | Information Disclosure | `ScopedStore` default-deny; `assert_owns` denial test gates |
| Path traversal in clone/inventory/diff | Tampering | `Workspace`/`RunSandbox.path_for` traversal rejection; repo-relative-only edits |
| Arbitrary code exec via repo workflow | Elevation of Privilege | `exec_command` DENIED by default `ExecutionPolicy` (exec off until N3); zero exec on the path |
| Unvalidated MCP tool reference in manifest | Tampering | compiler `server.tool` compile-validation (MCP-03) |
| Hallucinated/slopsquatted dependency | Tampering | 3 new libs gated by `checkpoint:human-verify` (slopcheck offline) |

## Open Risks (could NOT verify offline — flag for planner)

1. **tree-sitter-language-pack lazy-download (MEDIUM):** could not install the lib offline to confirm 1.8.1 bundles py/js/ts grammars in the wheel vs lazy-downloading. **Mitigation:** Wave-0 offline-install proof in 09-03 (R-C); fall back to per-language wheels.
2. **`langchain-mcp-adapters` exact get_tools/connect signature (LOW-MEDIUM):** verified `await client.get_tools()` + stdio config shape from official docs, but not installed/run. Confirm the 0.2.2 connection-config keys (`transport`/`command`/`args`) and that `get_tools()` returns `bind_tools`-ready tools at 09-05 install time.
3. **Alembic upgrade/downgrade reversibility (LOW):** the migration needs a live DB; the offline targeted suite excludes it (Postgres-gated). Verify against local SQLite/throwaway Postgres in 09-02, or rely on the migration-ledger structural assertion.
4. **`mcp` SDK stub server API (LOW):** the stub uses the transitive `mcp` SDK's stdio server (`FastMCP`); confirm the exact server-construction API at 09-05 (not installed offline).
5. **slopcheck unavailable (LOW):** all 3 new deps tagged `[ASSUMED]`; registry existence verified but legitimacy gate not run — checkpoint each install.
6. **handoff_pipeline re-point vs retain-whole (LOW):** whether to re-point `run_handoff_pipeline`'s coding step at the unified runner or leave the legacy pipeline for the retained endpoint is a planner decision gated on `test_handoff_contract.py` staying green.

## Sources

### Primary (HIGH — codebase, file:line verified)
- `backend/app/agents/sandbox.py` (RunSandbox + serialization byte-oracle)
- `backend/agents/factory.py` (sync create_runner, `_resolve_runner_tools` seam, `prewarmed_constitution`)
- `backend/agents/execution_engine/engine.py` (async run-entry pre-warm `:687`; RunSandbox callers)
- `backend/agents/execution_engine/kernel_services.py` (the `ctx.runner` handle)
- `backend/agents/capabilities/{base.py,registry.py}` (ports + `@register`/`discover`)
- `backend/agents/capabilities/deliverables/serialized_sandbox.py`, `context_providers/{opendesign,previous_run}.py` (impl idiom)
- `backend/agents/workflows/{plan.py,compiler.py}` (`ToolPermissions` mcp/integrations slots; compiler INV-4 seam)
- `backend/pyproject.toml` `[tool.importlinter]` (the 3 contracts)
- `backend/alembic/versions/{0014,0016}*.py` (head chain; workspaces.kind=String, repo_id nullable)
- `backend/app/{api/handoff.py,services/handoff_pipeline.py,agents/handoff/coding_agent.py,api/mcp.py,models/handoff.py}` (deletion blast radius)
- `backend/tests/agents/{test_characterization_*.py,test_migration_ledger.py,test_banned_patterns.py}` (the gates)

### Secondary (MEDIUM — official docs / PyPI, verified)
- PyPI versions via `python3.11 -m pip index versions` (langchain-mcp-adapters 0.2.2, tree-sitter 0.25.2, tree-sitter-language-pack 1.8.1, tree-sitter-languages 1.10.2)
- pypi.org/project/langchain-mcp-adapters + reference.langchain.com/python/langchain-mcp-adapters + docs.langchain.com/oss/python/langchain/mcp (MultiServerMCPClient.get_tools async; stdio config; bind_tools/create_agent compatibility)
- pypi.org/project/tree-sitter-language-pack + github.com/Goldziher/tree-sitter-language-pack + docs.tree-sitter-language-pack.kreuzberg.dev (prebuilt wheels, 305+ langs, get_parser/get_language)

### Tertiary (LOW — to verify at install)
- Package names discovered via SPEC/WebSearch → `[ASSUMED]`; offline slopcheck unavailable.

## Metadata
**Confidence breakdown:**
- Codebase facts (R-A/R-B/R-E/R-F/R-G): HIGH — file:line verified in-session.
- Library APIs (R-C/R-D): MEDIUM — verified against PyPI + official docs but not installed/run offline.
- Async→sync binding (R-D): HIGH — the in-tree `prewarmed_constitution` precedent is exact.
**Research date:** 2026-06-10
**Valid until:** 2026-07-10 (codebase facts stable on the branch; re-confirm library versions at install — fast-moving: 7 days)
