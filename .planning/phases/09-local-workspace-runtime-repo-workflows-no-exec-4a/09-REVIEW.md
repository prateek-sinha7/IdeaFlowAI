---
phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
reviewed: 2026-06-10T00:00:00Z
depth: standard
files_reviewed: 56
files_reviewed_list:
  - backend/agents/authz.py
  - backend/agents/capabilities/base.py
  - backend/agents/capabilities/context_pack/__init__.py
  - backend/agents/capabilities/context_pack/pack.py
  - backend/agents/capabilities/context_providers/repo.py
  - backend/agents/capabilities/deliverables/repo_diff.py
  - backend/agents/capabilities/integration_providers/__init__.py
  - backend/agents/capabilities/integration_providers/providers.py
  - backend/agents/capabilities/mcp_servers/__init__.py
  - backend/agents/capabilities/mcp_servers/catalog.py
  - backend/agents/capabilities/registry.py
  - backend/agents/capabilities/repo_inventory/__init__.py
  - backend/agents/capabilities/repo_inventory/inventory.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/factory.py
  - backend/agents/runtime/__init__.py
  - backend/agents/runtime/base.py
  - backend/agents/workflows/compiler.py
  - backend/agents/workflows/plan.py
  - backend/agents/workflows/sample_brownfield/workflow.yaml
  - backend/alembic/versions/0017_repositories_repo_workspace.py
  - backend/app/agents/handoff/__init__.py
  - backend/app/agents/handoff/coder.py
  - backend/app/agents/mcp/__init__.py
  - backend/app/agents/mcp/client.py
  - backend/app/agents/repo_index/__init__.py
  - backend/app/agents/repo_index/index.py
  - backend/app/agents/runtime/__init__.py
  - backend/app/agents/runtime/local.py
  - backend/app/agents/sandbox.py
  - backend/app/models/__init__.py
  - backend/app/models/mcp_credential.py
  - backend/app/models/repository.py
  - backend/pyproject.toml
  - backend/requirements.txt
  - backend/tests/agents/conftest.py
  - backend/tests/agents/fixtures/sample_brownfield/brownfield-analyze/AGENT.md
  - backend/tests/agents/fixtures/sample_brownfield/brownfield-build/AGENT.md
  - backend/tests/agents/fixtures/stub_mcp_server.py
  - backend/tests/agents/test_context_pack.py
  - backend/tests/agents/test_integration_providers.py
  - backend/tests/agents/test_integration_scopes.py
  - backend/tests/agents/test_local_runtime.py
  - backend/tests/agents/test_mcp_catalog.py
  - backend/tests/agents/test_mcp_client.py
  - backend/tests/agents/test_mcp_compile_validation.py
  - backend/tests/agents/test_mcp_gating.py
  - backend/tests/agents/test_migration_ledger.py
  - backend/tests/agents/test_registry_capabilities.py
  - backend/tests/agents/test_repo_diff.py
  - backend/tests/agents/test_repo_index.py
  - backend/tests/agents/test_repo_inventory.py
  - backend/tests/agents/test_repositories_persistence.py
  - backend/tests/agents/test_sample_brownfield_workflow.py
  - backend/tests/unit/test_handoff_agents.py
  - specs/003-workflow-engine-decoupling/migration-ledger.md
findings:
  critical: 1
  warning: 5
  info: 3
  total: 9
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-06-10
**Depth:** standard
**Files Reviewed:** 56
**Status:** issues_found

## Summary

Phase 09 adds the runtime port layer (`agents/runtime`), `LocalSandboxRuntime`/`LocalWorkspace`,
the `repositories`/`mcp_credentials` tables (migration 0017), the repo-context capabilities
(`repo_inventory`/`context_pack`/`repo` provider/`repo_diff`/`repo_index`), the MCP client + catalog +
compile gating + integration-provider bridge, and the `CodingAgent` → `HandoffCoder` deepagents-runtime
migration. The capability registration, compiler MCP validation, scoped-store persistence, and
import-direction discipline are well-built and well-tested.

The headline defect is a **confirmed infinite recursion** introduced by the `RunSandbox` → `Workspace`
"move-don't-copy" refold (R1): `RunSandbox.cleanup()` and `LocalWorkspace.teardown()` call each other
with no base case, so every workspace teardown raises `RecursionError`. This is reproducible and is the
exact disk-cleanup path Phase 09's new repo workflows rely on. The tests do not exercise teardown, so it
passes CI while being broken in production.

Secondary findings: an unrestricted `git clone` of a host-injected source URL (transport/argument
injection that can execute code despite the exec=OFF mandate), fire-and-forget lineage tasks that can be
dropped, a dead computed variable in the engine, and a documented-but-surprising commit side-effect during
deliverable resolution.

## Critical Issues

### CR-01: Infinite recursion between `RunSandbox.cleanup()` and `LocalWorkspace.teardown()`

**File:** `backend/app/agents/sandbox.py:137-139` and `backend/app/agents/runtime/local.py:173-174`
**Issue:** The RUNTIME-02 refold routes `RunSandbox.cleanup()` through the delegated Workspace facade,
but the facade's teardown routes straight back to the same `RunSandbox.cleanup()` — an unterminated cycle:

```
RunSandbox.cleanup()              # sandbox.py:139
  -> self._ws().teardown()
       -> LocalWorkspace.teardown()   # local.py:173-174
            -> self._sandbox.cleanup()   # == the SAME RunSandbox
                 -> self._ws().teardown()  # ... recurses forever
```

Reproduced directly:

```
$ python3.11 -c "from app.agents.sandbox import RunSandbox; sb=RunSandbox('u','r',runs_root='/tmp/x'); sb.ensure(); sb.cleanup()"
RecursionError
```

This is reachable in production two ways: (a) `LocalSandboxRuntime.teardown(ws)` → `ws.teardown()` →
`RunSandbox.cleanup()` (the documented repo-workspace teardown seam, the whole point of Phase 09), and
(b) any direct `RunSandbox.cleanup()` call. The pre-refold body was a single `shutil.rmtree(self.root,
ignore_errors=True)` — the refactor replaced a working one-liner with a crash. The five characterization
snapshots and the new repo tests never call teardown, so the defect is invisible to the suite.

**Fix:** Break the cycle — only ONE of the two layers may own the disk delete. The `LocalWorkspace`
holds the run root, so let it own the rmtree and make `RunSandbox.cleanup()` either delete directly or
call the workspace's *primitive* (not its `teardown`, which re-enters the sandbox):

```python
# app/agents/sandbox.py — RunSandbox.cleanup keeps the real delete, no Workspace round-trip
def cleanup(self) -> None:
    """Remove the run dir (idempotent)."""
    import shutil
    shutil.rmtree(self.root, ignore_errors=True)
```

or, if `LocalWorkspace.teardown` must remain the single disk-IO owner, have it `shutil.rmtree(self._root)`
inline instead of delegating back to `self._sandbox.cleanup()`. Add a test that asserts
`runtime.teardown(ws)` removes the run dir and does not raise.

## Warnings

### WR-01: Unrestricted `git clone <source>` enables transport/argument injection despite exec=OFF

**File:** `backend/app/agents/runtime/local.py:131-141`
**Issue:** `clone_repo(source)` runs `self._git("clone", source, ".")` with no protocol allow-list and no
guard on a leading `-`. The phase mandate is exec OFF at every step, but git's own transports defeat that:
a `source` of `ext::sh -c <cmd>` (the `ext` transport) executes an arbitrary command at clone time, and a
`source` beginning with `-` is parsed by git as an option (argument injection). `source` is the
host-injected RepoSpec `url` (the §15 binding seam); if it is ever reachable from user/DB-composed input,
this is remote code execution that sidesteps the ExecutionPolicy entirely. No `GIT_ALLOW_PROTOCOL` guard
exists anywhere in the tree.

**Fix:** Constrain the transport and reject option-like sources before cloning:

```python
def clone_repo(self, source: str) -> Path:
    if source.startswith("-"):
        raise ValueError(f"refusing clone source that parses as a git option: {source!r}")
    env = {**os.environ, "GIT_ALLOW_PROTOCOL": "file:https:ssh"}  # no ext::/fd::
    self._git("clone", "--", source, ".", env=env)   # `--` ends option parsing
    return self._root
```

(`_git` needs to thread `env` into `subprocess.run`.) At minimum add the `--` separator and drop the
`ext`/`fd` protocols.

### WR-02: Fire-and-forget lineage persist task can be silently dropped

**File:** `backend/agents/capabilities/context_pack/pack.py:184-188` and
`backend/agents/capabilities/repo_inventory/inventory.py:260-265`
**Issue:** When a running loop exists, lineage persistence is scheduled via `loop.create_task(_persist())`
with no reference retained and no `await`. asyncio holds only a weak reference to tasks, so the task may be
garbage-collected before it runs (the documented "Task was destroyed but it is pending" hazard), and if the
run's event loop is torn down right after `build()` returns the DB write is lost. The capability's own
result is unaffected, but the artifact's DB lineage row (the auditable provenance these modules exist to
record) can vanish nondeterministically.

**Fix:** Retain a strong reference until completion, e.g. keep a module/instance-level set of pending
tasks and discard on done:

```python
task = loop.create_task(_persist())
self._pending.add(task)
task.add_done_callback(self._pending.discard)
```

or have the engine await these writes at a known join point instead of fire-and-forget.

### WR-03: `git_diff` mutates repo state (commits) during deliverable resolution

**File:** `backend/app/agents/runtime/local.py:146-156`
**Issue:** `git_diff(base, work)` is invoked by the `repo_diff` *deliverable resolver* (a read-path), but it
runs `git add -A` + `git commit -m "workspace edit"` on the currently checked-out branch when the working
tree is dirty. Two problems: (1) a "read the diff" call performs a write, surprising for a resolver whose
own docstring stresses "the resolver performs no record-write"; the write is merely relocated into the
Workspace. (2) The commit lands on whatever branch is checked out, not necessarily `work` — if `base` (e.g.
`main`) is the checked-out branch when the resolver runs, the edit is committed onto `base` and the
`base..work` diff is then wrong/empty. The passing tests pre-commit the edit so the dirty-path commit never
fires, masking this.

**Fix:** Make the diff non-mutating (diff the working tree against base without committing), e.g.
`git add -A` to the index then `git diff --cached <base>` / `git diff <base>` against the work tree, or
assert the expected branch is checked out before committing. Do not commit as a side effect of a resolver.

### WR-04: Dead computed variable `_active_integration_servers` in the engine run-entry

**File:** `backend/agents/execution_engine/engine.py:752,763`
**Issue:** `_active_integration_servers: list[str] = []` is declared and assigned
`sorted(_integ_configs.keys())` but never read afterward. The per-run server list that actually reaches
`record_capabilities` is computed separately (`_rec_servers`, ~line 562). This is dead code that duplicates
the scope→server resolution and invites drift between the two computations.

**Fix:** Delete the `_active_integration_servers` declaration and assignment, or, if it was meant to feed the
`run_capabilities` recording, unify it with `_rec_servers` so the active-server list is computed once.

### WR-05: MCP allow-list filter accepts only exact name forms; silent over-drop on prefixed tools

**File:** `backend/app/agents/mcp/client.py:81-87`
**Issue:** `get_tools(allowed=...)` builds the permitted set as `{n, f"{server}.{n}", f"{server}__{n}"}`
for each declared name and keeps a tool only if `tool.name` is in that set. `langchain-mcp-adapters` tool
naming is version-dependent; if a future/alternate adapter version emits a differently-prefixed alias (or a
sanitized name), every tool is dropped and the run silently proceeds with zero MCP tools (logged at INFO
only). The compile-time MCP-03 gate validates the manifest, but this bind-time defence can fail-closed-to-
empty without surfacing that the integration the user granted bound nothing.

**Fix:** Match on the bare MCP tool name robustly (strip a known server prefix before comparison) and, when
`allowed` is supplied but the filtered result is empty while connected tools exist, log at WARNING (not INFO)
so a total over-drop is visible rather than indistinguishable from "no scope active".

## Info

### IN-01: `slack_post` is a write capability on the user palette, ungated

**File:** `backend/agents/capabilities/mcp_servers/catalog.py:86-94`
**Issue:** `SlackMcpServer` exposes `post_message` (a write/side-effecting action) with `powerful=False` and
`user_allowed=True`, so a user/DB-composed manifest can bind it without the `security` gate or a `secrets`
grant. This is a deliberate ("the one write the user palette allows") but worth an explicit security sign-off:
unlike the read-scoped servers, it can emit external messages on the owner's behalf.
**Fix:** Confirm this is intended; if so, document the exception near the MCP-04 gating logic so a future
reader does not assume "user_allowed ⇒ read-only".

### IN-02: `exec_command` uses `shell=True` (gated off this phase, future risk)

**File:** `backend/app/agents/runtime/local.py:160-171`
**Issue:** `exec_command` runs `subprocess.run(command, shell=True, ...)`. It is unreachable this phase
(`policy.allows("exec")` is always False), but when N3 flips exec on, `shell=True` over a `command` string
is a command-injection surface by construction.
**Fix:** When exec is enabled, pass an argv list with `shell=False`, or document the trust contract for the
command source at the point it is enabled.

### IN-03: `repo_diff` per-file split silently drops blocks with unparseable headers

**File:** `backend/agents/capabilities/deliverables/repo_diff.py:122-148`
**Issue:** `_split_per_file` only flushes a block when `current_path is not None`; a `diff --git` header whose
path cannot be parsed (e.g. a quoted path containing spaces, or a rename header) yields `current_path=None`,
so that file's diff is dropped from `diffs`/`tree` while still counted in the `summary` line totals (which
scan the raw unified text). The `tree`/`diffs` and `summary` can therefore disagree for unusual paths.
**Fix:** Fall back to a synthetic key (or the raw header) when the path is unparseable so no changed file is
silently omitted from the tree, or document that space-bearing/renamed paths are out of scope.

---

_Reviewed: 2026-06-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
