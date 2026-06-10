# Phase 9: Local Workspace Runtime + Repo Workflows (no exec) [4A] - Pattern Map

**Mapped:** 2026-06-10
**Files analyzed:** 18 new/modified targets across the 6-plan frame (09-01…09-06)
**Analogs found:** 18 / 18 (every target has a file:line analog — RESEARCH R-A..R-G pre-named them; this map pulls the load-bearing excerpts)

> All analogs are kernel-side `backend/agents/**` or app-side `backend/app/agents/**`. The dominant idioms repeat across nearly every new file: (a) one-method `typing.Protocol` port in `agents/capabilities/base.py`; (b) `@register(kind, name)` self-registration on a stateless class with a `name: str` attr; (c) reach `app.*`/disk/git ONLY through `ctx.runner` / `ctx.scoped_store` handles (never an `app.*` import) so import-linter contract 3 stays green. The Shared Patterns section below carries these once; per-file sections cite the specific analog + delta.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/agents/runtime/base.py` (NEW) | port (kernel) | request-response | `backend/agents/capabilities/base.py:64-83` | exact (idiom) |
| `backend/app/agents/runtime/local.py` (NEW) | provider/service (app) | file-I/O + transform | `backend/app/agents/sandbox.py:49-96` + Validator app-side split | role-match |
| `backend/app/agents/sandbox.py` (MODIFY — `RunSandbox` refold) | service (app) | file-I/O | itself `sandbox.py:49` (in-place delegate) | exact |
| `backend/agents/capabilities/deliverables/repo_diff.py` (NEW) | deliverable resolver (kernel) | transform (git diff→string) | `deliverables/serialized_sandbox.py:24-40` | exact |
| `backend/agents/capabilities/context_providers/repo.py` (NEW) | context provider (kernel) | request-response | `context_providers/previous_run.py:115-218` | exact |
| `backend/agents/capabilities/repo_inventory/…` (NEW) | capability (kernel) | transform (walk→artifact) | `serialized_sandbox.py` + `registry.py` `@register` | role-match |
| `backend/agents/capabilities/context_pack/…` (NEW, `context_pack`+`context_selector`) | capability (kernel) | transform (select subset) | `previous_run.py` provider idiom + `@register` | role-match |
| `repo_index` capability (NEW — app-side, tree-sitter) | capability (app, heavy-dep) | transform (parse→symbols) | Phase-8 Validator app-side placement (`registry.py:226`) | role-match |
| `backend/app/agents/mcp/client.py` (NEW — `McpClientAdapter`) | adapter (app) | event-driven / async bind | `factory.py` prewarmed-constitution seam + `_resolve_runner_tools:457` | role-match |
| `mcp_server` catalog capabilities (NEW — github/gitlab/jira/slack/filesystem/postgres) | capability/data (kernel) | request-response (registration data) | `registry.py:135-159` `@register` (data-carrying via `user_allowed`) | role-match |
| `integration_provider` capabilities (NEW — github/gitlab/jira/slack) | capability/bridge (kernel) | request-response | `@register` idiom + `ToolPermissions.integrations` slot (`plan.py:72`) | role-match |
| `backend/alembic/versions/0017_*.py` (NEW) | migration | batch (DDL) | `0016_capability_hardening_tables.py` + `0014_typed_artifacts_persistence.py:82-99` | exact |
| `repositories` model + scoped writer (NEW) | model (app) | CRUD | `app/models/handoff.py:40` (`UserGithubCredential`) + `ScopedStore` (`agents/authz.py:58`) | role-match |
| compiler `tools.mcp` compile-validation (MODIFY `compiler.py`) | validation seam (kernel) | request-response | `compiler.py:159,207` `is_registered`/`_check_trust` per-reference site | exact |
| `_build_runner_tools`/`_resolve_runner_tools` MCP binding (MODIFY `factory.py`) | binding seam (app) | event-driven | `factory.py:457-499` `_resolve_runner_tools` + prewarm precedent | exact |
| stub stdio MCP server fixture (NEW — `tests/agents/fixtures/`) | test fixture | request-response (stdio JSON-RPC) | `app/api/mcp.py` JSON-RPC shape (inbound, reference only) | partial |
| `RepoSpec` index opt-in flag (MODIFY `plan.py`) | schema | data | `RepoSpec` `plan.py:256-262` + `ToolPermissions` `plan.py:70-72` | exact |
| **DELETE** `backend/app/agents/handoff/coding_agent.py` (`CodingAgent`) | deletion | — | move-don't-copy / migration-ledger ratchet (`test_migration_ledger.py:53-55`) | n/a |

## Pattern Assignments

### `backend/agents/runtime/base.py` (port, kernel) — NEW

**Analog:** `backend/agents/capabilities/base.py:64-83` (the one-method `typing.Protocol` port idiom).

**Port idiom to copy** (`base.py:22-24, 64-83`):
```python
from __future__ import annotations
from typing import Any, AsyncIterator, Protocol, runtime_checkable

@runtime_checkable
class DeliverableResolver(Protocol):
    """Resolves a run's final deliverable from the execution context (Q26)."""
    name: str
    def resolve(self, ctx: Any) -> Any: ...

@runtime_checkable
class ContextProvider(Protocol):
    name: str
    async def load(self, ctx: Any) -> dict[str, str]: ...
```

**Key idioms to replicate:**
- `from __future__ import annotations` + import ONLY stdlib `typing` (the module-docstring contract at `base.py:1-20` — "imports ONLY stdlib `typing`. It must not import the kernel engine package or the web/API layer"). This is what keeps the kernel→ports direction one-way and the import-linter green.
- Each port = `@runtime_checkable` class, a `name: str` attribute, runtime objects typed `Any`, `...` bodies.
- Define `RuntimeEnvironment` (`create_workspace`/`teardown`), `Workspace` (`read_file`/`write_file`/`search`/`clone_repo`/`create_branch`/`git_diff`/`exec_command`/`teardown`, carrying `owner_id`/`workspace_id` + back-ref `runtime: RuntimeEnvironment`), `ExecutionPolicy`, `IsolationProvider` (`allocate(scope) -> Workspace`).
- **Planner action:** add a 4th import-linter contract locking `agents.runtime ↛ [agents.execution_engine, app]` (same `forbidden` shape as contract 3 in `pyproject.toml:165`).

---

### `backend/app/agents/runtime/local.py` (provider/service, app) — NEW `LocalSandboxRuntime`

**Analog:** `backend/app/agents/sandbox.py:49-96` (disk/path-safety) + the Phase-8 Validator app-side placement (`registry.py:226` — the only app-side capability package, reached via `ctx.runner`).

**Disk/path-safety pattern to reuse** (`sandbox.py:57-96`):
```python
base = Path(runs_root or settings.RUNS_ROOT).resolve()
self.root = (base / self.user_seg / self.run_seg).resolve()
if self.root != base and not str(self.root).startswith(str(base) + "/"):
    raise ValueError(f"sandbox root escaped RUNS_ROOT: {self.root}")
...
def path_for(self, relpath: str) -> Path:
    candidate = (self.root / str(relpath).lstrip("/")).resolve()
    if candidate != self.root and not str(candidate).startswith(str(self.root) + "/"):
        raise ValueError(f"path escapes run sandbox: {relpath!r}")
    return candidate
```

**Key idioms to replicate:**
- Lives **app-side** (it touches `from app.core.config import settings` for `RUNS_ROOT` — `sandbox.py:21` — and reuses `path_for`/`ensure`). This is the same `app.*` reach that put the heavy validators app-side.
- Self-register via `@register("runtime_env", "local")` (use the DISTINCT kind `runtime_env` — `("runtime", "langchain_deepagents")` already exists at `registry.py:102`).
- Add `"app.agents.runtime"` to `discover()`'s `_forward_packages` tuple (`registry.py:217-227`) — the `ModuleNotFoundError` guard makes a not-yet-created package a no-op.
- `exec_command` present but raises/denies under the default `ExecutionPolicy`; git ops (`clone_repo`/`create_branch`/`git_diff`) own the single `git` subprocess.

---

### `backend/app/agents/sandbox.py` — `RunSandbox` refold (MODIFY in-place, D-02)

**Analog:** itself — `sandbox.py:49-96` is the parity oracle.

**Consumed surface that MUST stay byte-identical** (from RESEARCH R-B caller inventory): `__init__(user_id, run_id)`, `.ensure()`, `.root`, `.path_for`, `.read`, `.write`, `.cleanup`, plus module-level `serialize_sandbox_deliverable`/`count_sandbox_deliverables`.

**Key idioms to replicate:**
- `RunSandbox` name survives as a thin facade; internals delegate to `Workspace(has_git=False, exec=off)`. Move-don't-copy — delete bespoke disk logic, do NOT dual-impl.
- Preserve `serialize_sandbox_deliverable`'s **raw-bytes** read (not `read_text`) for CRLF byte-equivalence (`sandbox.py` serialization is pinned by `test_sandbox_deliverable.py`).
- Gate: the 5-pipeline characterization snapshots stay green with `SNAPSHOT_UPDATE` UNSET (RESEARCH R-B test command).

---

### `backend/agents/capabilities/deliverables/repo_diff.py` (deliverable resolver, kernel) — NEW

**Analog:** `backend/agents/capabilities/deliverables/serialized_sandbox.py:24-40` (the resolver-via-handle pattern, the closest analog — both read run state off `ctx.runner` and return a deliverable string).

**Full analog to mirror** (`serialized_sandbox.py:21-40`):
```python
from agents.capabilities.registry import register

@register("deliverable", "serialized_sandbox")
class SerializedSandboxResolver:
    name = "serialized_sandbox"

    def resolve(self, ctx: Any) -> Any:
        runner = ctx.runner
        root = runner.sandbox.root
        if runner.count_sandbox_deliverables(root) > 0:
            return runner.serialize_sandbox_deliverable(root)
        return None
```

**Key idioms to replicate:**
- `@register("deliverable", "repo_diff")`, `name = "repo_diff"`, one `def resolve(self, ctx)`.
- Read the diff via the handle — `ctx.runner.workspace.git_diff(base_branch, working_branch)` — **never shell git** (D-10). The `Workspace` owns the single `git diff` subprocess.
- Output = file tree + per-file unified diff + change summary; **diff-only, no push** (N4).
- Add `("deliverable", "repo_diff")` to `_KNOWN` (`registry.py:84-87`) and a `discover()` import line (`registry.py:198`).

---

### `backend/agents/capabilities/context_providers/repo.py` (context provider, kernel) — NEW

**Analog:** `backend/agents/capabilities/context_providers/previous_run.py:115-218`.

**Idiom to mirror** (`previous_run.py:115-125, 159-162`):
```python
@register("context_provider", "previous_run")
class PreviousRunProvider:
    name = "previous_run"

    async def load(self, ctx: Any) -> dict[str, str]:
        ...
        scoped_store = getattr(ctx, "scoped_store", None)
        if scoped_store is not None:
            try:
                await scoped_store.assert_owns(parent_run_id)
            except PermissionError:
                raise  # cross-owner denial — propagate (L16, never swallow)
        runner = getattr(ctx, "runner", None)
        ...
```

**Key idioms to replicate:**
- `@register("context_provider", "repo")`, `name = "repo"`, `async def load(self, ctx) -> dict[str, str]`.
- Reach disk/git via `getattr(ctx, "runner", None)` and the store via `getattr(ctx, "scoped_store", None)` — dynamic attribute access off `Any`-typed fields (import-clean, Pitfall 5).
- The **ownership gate**: `await scoped_store.assert_owns(...)`; a cross-owner `PermissionError` PROPAGATES, never swallowed; other errors degrade gracefully.

---

### `repo_inventory` / `context_pack` / `context_selector` capabilities (kernel, pure-stdlib) — NEW

**Analog:** `serialized_sandbox.py:24-40` (resolver) + `registry.py:135-159` (`@register` + `_KNOWN`/`discover()` wiring).

**Registration wiring to copy** (`registry.py:153-157`):
```python
def _decorate(cls):
    _KNOWN.add((kind, name))
    _IMPLS[(kind, name)] = cls()
    _TRUST[(kind, name)] = user_allowed
    return cls
```

**Key idioms to replicate:**
- New kinds `("repo_inventory", "default")`, `("context_pack", "default")` — KINDs are free strings; add their `(kind,name)` to `_KNOWN` (`registry.py:76`) and a `discover()` import (`registry.py:193-211`).
- Pure-stdlib → **kernel-side** `backend/agents/capabilities/repo_inventory/` and `…/context_pack/`. Reach `git ls-files` / disk via `ctx.runner`.
- `repo_inventory` ignore/skip/cap (REPO-01): prefer `git ls-files --cached --others --exclude-standard` via the handle, then `.flowinignore` globs (`fnmatch`); binary-skip via null-byte sniff (mirror `serialize_sandbox_deliverable`'s UTF-8-decode-or-skip defensive idiom); documented per-file/total size caps as module constants.
- Lineage-track output via `ScopedStore.write_ref` (`agents/authz.py:133`).

---

### `repo_index` capability (app-side, tree-sitter heavy dep) — NEW

**Analog:** the Phase-8 Validator heavy-dep app-side placement — `registry.py:226` (`"app.agents.validators"`, the only app-side capability package in `_forward_packages`), reached via `ctx.runner`.

**Key idioms to replicate:**
- Lives **app-side** so the `tree_sitter` import is isolated behind the module (REPO-02 acceptance: "`tree-sitter` is imported only behind the `RepoIndex` capability"). Add its package to `discover()`'s `_forward_packages` (same as `app.agents.validators`).
- Optional registered port exposing TWO methods through one seam: `search(pattern, *, glob)` (grep/glob DEFAULT, always available) and `symbol_query(name) -> list[SymbolHit]` (only when index built). `Match`/`SymbolHit` are kernel-pure dataclasses.
- Index built IN-MEMORY PER-RUN on manifest opt-in or the N6 threshold constant; discarded at teardown (no new table). tree-sitter is a LIBRARY → banned-pattern gate (INV-13) untouched.

---

### `backend/app/agents/mcp/client.py` — `McpClientAdapter` (adapter, app) — NEW

**Analog:** the `prewarmed_constitution` async-prewarm precedent (`engine.py:687-694` await-once-at-run-entry, `factory.py:60-62` sync-read-no-await) + the `_resolve_runner_tools` binding seam (`factory.py:457-499`).

**Binding seam to mirror** (`factory.py:457-499`):
```python
def _resolve_runner_tools(spec, ctx: AgentContext) -> tuple[list, bool]:
    from agents.capabilities.registry import CapabilityRegistry, discover
    if not spec.tools:
        return ([], True)
    discover()
    registry = CapabilityRegistry()
    ...
```

**Key idioms to replicate (the async→sync risk, RESOLVED — RESEARCH R-D):**
- `MultiServerMCPClient.get_tools()` is **async**. Connect + `await get_tools()` ONCE at async run-entry (the same block as the Constitution prewarm, `engine.py:687`); stash on `ctx` (new `AgentContext.prewarmed_mcp_tools: list = []` beside `prewarmed_constitution` at `factory.py:62`).
- The sync `_resolve_runner_tools`/`_build_runner_tools` (`factory.py:457`) only READS the pre-bound toolset and UNIONS it into `custom_tools` — NO `await`, NO `asyncio.run` inside the running loop (double-loop hazard, Pitfall 3).
- Returned tools are LangChain-compatible → drop into `create_deep_agent` tool set. They AUGMENT the deepagents runtime, never replace it (INV-13).

---

### `mcp_server` catalog capabilities (kernel, registration data) — NEW

**Analog:** `registry.py:135-159` — the `@register(kind, name, *, user_allowed=...)` data-carrying decorator.

**Key idioms to replicate:**
- Each server = a module that `@register("mcp_server", "github"|"gitlab"|"jira"|"slack"|"filesystem"|"postgres")`s a stateless class carrying transport (stdio/SSE/HTTP) + exposed-tool allow-list + scope as registration DATA.
- GitHub/GitLab/Jira/Slack register `user_allowed=True` (read-scoped); Filesystem/Postgres `user_allowed=False` — the `_TRUST` flag the compiler trust check reads (`registry.py:268-278`).
- Surfaced via `GET /api/capabilities` for free. Add the `("mcp_server", …)` pairs to `_KNOWN`.

---

### `integration_provider` capabilities (kernel, bridge) — NEW

**Analog:** same `@register` idiom + the `ToolPermissions.integrations` slot (`plan.py:72`, already present, default none) + `record_capabilities` (`engine.py:556`).

**Key idioms to replicate:**
- `@register("integration_provider", "github"|"gitlab"|"jira"|"slack")`; thin bridge that takes a catalog `mcp_server` + an `integrations` scope and surfaces its tools into `create_runner` via the SAME factory seam + prewarm binding. ONE mechanism (MCP) — no parallel SDK path (D-08).
- `integrations` scopes (`github_read`/`gitlab_read`/`jira_read`/`slack_post`) default none; recorded per-run via `ScopedStore.record_capabilities` (`engine.py:554-556`).

---

### `backend/alembic/versions/0017_*.py` (migration) — NEW

**Analog:** `0016_capability_hardening_tables.py:24-25` (head/revision chain) + `0014_typed_artifacts_persistence.py:82-99` (`workspaces` create incl. nullable `repo_id` forward field) + `0014:236` (`op.drop_table` downgrade model).

**Key idioms to replicate:**
- `revision="0017"`, `down_revision="0016"` (head chain VERIFIED — RESEARCH R-G).
- `op.create_table("repositories", …)` with columns `id`(PK), `owner_id`(NN), `workspace_id`(NN), `provider`(free `String`, no enum), `url`(NN), `default_branch`(NN), `auth_ref`(nullable), `created_at`(NN) — every table carries `owner_id`+`workspace_id` (Q3).
- `workspaces.kind` is a free `String` (`0014:88`) → `kind='repo'` needs NO enum widening. `workspaces.repo_id` already nullable `String` (`0014:93`) → optionally add `op.create_foreign_key` to `repositories.id` (create `repositories` FIRST).
- `downgrade()`: drop FK (if added) then `op.drop_table("repositories")` — reversible; migration-ledger gate green.

---

### `repositories` model + scoped writer (model, app) — NEW

**Analog:** `app/models/handoff.py:40` (`UserGithubCredential` — owner-scoped/encrypted PAT) + `ScopedStore` (`agents/authz.py:58-79`, default-deny `WHERE owner_id=:owner AND workspace_id=:ws`; `write_ref` `authz.py:133`).

**Key idioms to replicate:**
- Owner/workspace-scoped, never global; the cross-owner `assert_owns`/scoped-read denial test is the gate (the `previous_run.py:162` propagate-PermissionError pattern).
- The repo run persists exactly ONE `repositories` row + ONE `kind=repo` `workspaces` row linked by `repo_id` (`create_workspace`/`record_capabilities` run-entry writers, `engine.py:554-556`).
- New MCP/integration scoped creds extend the same `UserGithubCredential` PAT shape (additive).

---

### compiler `tools.mcp` compile-validation (MODIFY `compiler.py`) — MCP-03

**Analog:** `compiler.py:159` (`is_registered` per-reference + `CompilerError` naming the bad ref) + `compiler.py:186-211` (`_check_trust` / `is_user_allowed`). `"mcp"`/`"integrations"` are ALREADY in the allowed tool-grant keys (RESEARCH R-D: `compiler.py:104-105`).

**Per-reference validation site to mirror** (`compiler.py:158-161, 205-211`):
```python
for cp in manifest.context_providers:
    if not registry.is_registered("context_provider", cp):
        raise CompilerError(f"unknown context_provider '{cp}' in {where}")
    self._check_trust(registry, "context_provider", cp, trusted, where)
...
if not registry.is_user_allowed(kind, name):
    raise CompilerError(
        f"capability ({kind!r}, {name!r}) is not user-allowed in {where} ...")
```

**Key idioms to replicate:**
- ADD a per-`server.tool` loop over `step.tools.mcp`: split `server.tool`, assert the `mcp_server` `is_registered` AND (`is_user_allowed` for user/db manifests) AND the named tool is in the server's exposed-tool allow-list → else `CompilerError` naming the offending `server.tool`. Same site, same error idiom — do NOT fork the validation path.

---

### Stub stdio MCP server fixture (NEW, `tests/agents/fixtures/stub_mcp_server.py`)

**Analog:** `backend/app/api/mcp.py` (the inbound JSON-RPC-over-HTTP server — reference for the JSON-RPC tool-list/tool-call shape; the stub is the OPPOSITE direction over stdio).

**Key idioms to replicate:**
- A tiny real MCP server built on the `mcp` SDK's stdio server (`FastMCP`/`mcp.server.stdio`) exposing 1-2 trivial tools (`echo`, `add`).
- Test: `MultiServerMCPClient({"stub": {"command": "python3.11", "args": [<stub>], "transport": "stdio"}})`; `await client.get_tools()`; assert the allowed tool binds + a scripted-model deepagents agent invokes it. Fully offline (MCP-01/MCP-04 accept). No collision with `app/api/mcp.py` (additive, opposite direction).

---

### DELETION TARGET — `backend/app/agents/handoff/coding_agent.py` (`CodingAgent`)

**Analog (process, not code):** the move-don't-copy / migration-ledger ratchet (`test_migration_ledger.py:53-55` scopes non-kernel rows to whole `backend/`).

**Precise scope (RESEARCH R-E):**
- **DELETE** `CodingAgent` (`coding_agent.py:145-185` — the `build_model().ainvoke` one-shot that skips `create_runner`, the INV-13 gap) + its references in `handoff_pipeline.py:30,420-422` and `handoff/__init__.py:10,15` + the `CodingAgent` unit tests.
- **RETAIN with explicit ledger justification:** `app/api/handoff.py` + `app/api/websocket_handoff.py` (live external `/api/handoff` surface, registered `main.py:153,157`), `handoff_github.py`, `app/models/handoff.py` (the PAT precedent).
- Add an `L#`/`D#` ledger row with a verbatim grep gate (`class CodingAgent` → 0 matches in `backend/`); banned-pattern + 5-pipeline parity snapshots are the gates.

## Shared Patterns

### Self-registration (`@register` + `_KNOWN` + `discover()`)
**Source:** `backend/agents/capabilities/registry.py:135-159` (decorator), `:76-111` (`_KNOWN`), `:193-227` (`discover()`).
**Apply to:** EVERY new capability (`repo_diff`, `repo` provider, `repo_inventory`, `context_pack`, `repo_index`, `mcp_server` catalog, `integration_provider`, `runtime_env/local`).
```python
def register(kind, name, *, user_allowed=False):
    def _decorate(cls):
        _KNOWN.add((kind, name)); _IMPLS[(kind, name)] = cls(); _TRUST[(kind, name)] = user_allowed
        return cls
    return _decorate
```
Add each `(kind, name)` to `_KNOWN` (free-string kinds, no central if/elif) and an import line to `discover()` (`_builtin_modules` for kernel-side, `_forward_packages` for app-side). Kernel-side packages import stdlib + `agents.capabilities.registry` ONLY.

### Handle-only access to app/disk/git/store (import purity)
**Source:** `serialized_sandbox.py:34-38` (`runner = ctx.runner; runner.sandbox.root`), `previous_run.py:159,187` (`getattr(ctx, "scoped_store", None)` / `getattr(ctx, "runner", None)`).
**Apply to:** all kernel-side capabilities (`repo_diff`, `repo`, `repo_inventory`, `context_pack`).
Reach `app.*`/disk/git/store via dynamic attribute access off `Any`-typed `ctx.runner` (`KernelServices`) / `ctx.scoped_store` (`ScopedStore`) — NEVER an `app.*` import (import-linter contract 3, `pyproject.toml:165`; Pitfall 5).

### Ownership gate (default-deny, propagate PermissionError)
**Source:** `previous_run.py:160-164` + `ScopedStore` (`agents/authz.py:58`).
**Apply to:** `repo` provider, `repositories` writer, MCP/integration scoped-cred reads.
```python
try:
    await scoped_store.assert_owns(parent_run_id)
except PermissionError:
    raise  # cross-owner denial — propagate (L16, never swallow)
```
Owner/workspace-scoped; cross-owner denial is the one error that always propagates (the denial test is the gate).

### Port idiom (one-method `Protocol`, stdlib-only)
**Source:** `agents/capabilities/base.py:22-24, 64-83`.
**Apply to:** every port in `agents/runtime/base.py` + the optional `RepoIndex` port.
`@runtime_checkable` class, `name: str`, runtime objects typed `Any`, `...` body, `from __future__ import annotations`, import ONLY `typing`.

### Async-value → sync-factory prewarm
**Source:** `engine.py:687-694` (await once at run-entry) + `factory.py:60-62` (sync read, no await).
**Apply to:** MCP/integration tool binding (`McpClientAdapter`).
Await `get_tools()` ONCE at async run-entry, stash on `ctx`, sync factory reads only. Never `asyncio.run`/`await` in the sync factory under the running loop (Pitfall 3).

### Additive migration (additive, reversible, owner/workspace columns)
**Source:** `0014_typed_artifacts_persistence.py:82-99,236` + `0016:24-25`.
**Apply to:** `0017` (`repositories`).
`down_revision="0016"`; free-`String` columns (no `sa.Enum`); every table carries `owner_id`+`workspace_id`; `downgrade` drops cleanly; ledger gate green.

## No Analog Found

None. Every Phase-9 target maps to a concrete in-tree analog (RESEARCH R-A..R-G pre-resolved the placements with file:line; this map pulled the load-bearing excerpts). Library-API shapes for the two NEW deps (`langchain-mcp-adapters` `MultiServerMCPClient`, `tree-sitter-language-pack`) are external and `[ASSUMED]` — gate each behind a `checkpoint:human-verify` before adding to `pyproject.toml` (RESEARCH Package Legitimacy Audit; slopcheck was unavailable offline).

## Metadata

**Analog search scope:** `backend/agents/capabilities/{base,registry}.py`, `…/deliverables/`, `…/context_providers/`, `backend/app/agents/sandbox.py`, `backend/agents/factory.py`, `backend/agents/workflows/compiler.py`; cross-referenced against RESEARCH R-A..R-G file:line citations (`alembic/versions/0014,0016`, `app/models/handoff.py`, `agents/authz.py`, `engine.py` prewarm seam) without re-reading already-cited ranges.
**Files scanned (read this session):** 6 (base.py, serialized_sandbox.py, previous_run.py, registry.py, sandbox.py, factory.py + compiler.py partial)
**Pattern extraction date:** 2026-06-10
