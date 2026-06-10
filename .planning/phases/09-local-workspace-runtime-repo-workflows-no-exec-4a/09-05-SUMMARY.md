---
phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
plan: 05
subsystem: agents
tags: [mcp, mcp-client, multiserver-mcp-client, catalog, scoped-credentials, compile-validation, security-gate, capability-registry, deepagents, inv13, hexagonal-ports]

# Dependency graph
requires:
  - phase: 08-capabilities-runtime-frontend-1d
    provides: "self-registering CapabilityRegistry (@register user_allowed / discover() / _KNOWN drift guard); the ('gate','security') gate (08-02); ToolPermissions.secrets/mcp/integrations slots + intersect_permissions (08-03)"
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    plan: 01
    provides: "the prewarmed_constitution async→sync seam at the engine run-entry (the EXACT pattern the MCP tool prewarm mirrors)"
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    plan: 02
    provides: "the 0017 migration + ScopedStore.create_repository/assert_repo_owned (the owner-scoped default-deny writer/reader precedent the MCP cred extends)"
  - phase: 05-typed-artifacts-persistence-ownership-1b
    provides: "ScopedStore default-deny (owner_id+workspace_id) + the UserGithubCredential Fernet-encrypted PAT precedent (handoff.py:40)"
provides:
  - "app/agents/mcp/client.py — McpClientAdapter over langchain-mcp-adapters MultiServerMCPClient (app-side; async get_tools at run-entry; exposed-tool allow-list filter; augments deepagents, never replaces — INV-13)"
  - "AgentContext.prewarmed_mcp_tools + the engine run-entry async prewarm (mirrors prewarmed_constitution) + the sync-factory union (no double-loop)"
  - "tests/agents/fixtures/stub_mcp_server.py — in-repo stdio FastMCP stub server (offline MCP-01/04 proof)"
  - "agents/capabilities/mcp_servers/catalog.py — @register('mcp_server', github|gitlab|jira|slack user_allowed=True | filesystem|postgres user_allowed=False): transport + exposed-tool allow-list + scope + powerful flag as DATA"
  - "app/models/mcp_credential.py McpCredential (owner-scoped + Fernet-encrypted) + 0017 mcp_credentials table (additive) + ScopedStore.write/read/assert_mcp_cred_owned (cross-owner PermissionError)"
  - "compiler tools.mcp server.tool compile-validation (MCP-03) + the security-gate+secrets gating for powerful servers (MCP-04)"
affects: [09-06-integration-providers]

# Tech tracking
tech-stack:
  added:
    - "langchain-mcp-adapters>=0.2.2,<0.3 (resolved 0.2.2 — github.com/langchain-ai/langchain-mcp-adapters, human-verified at the package-legitimacy checkpoint; provides MultiServerMCPClient)"
    - "mcp==1.27.2 (transitive — the reference Model Context Protocol Python SDK, github.com/modelcontextprotocol/python-sdk, Anthropic PBC; provides FastMCP/stdio for the offline stub)"
    - "sse-starlette==3.0.2 (pinned DOWN from the mcp-pulled 3.4.4 to coexist with the project's starlette 0.41.3 / fastapi 0.115.6)"
  patterns:
    - "async→sync tool binding via the prewarmed_constitution seam: McpClientAdapter.get_tools() is awaited ONCE at the async engine run-entry and stashed on AgentContext.prewarmed_mcp_tools; the SYNC factory only READS+UNIONS it (no await/asyncio.run inside the running loop — Pitfall 3 double-loop)"
    - "MCP tools bind INTO create_deep_agent's tool set (augment, never replace — INV-13); the banned-pattern gate stays green because the adapter builds no agent loop"
    - "a registered capability that is registration-DATA-only (the mcp_server catalog) carries transport + exposed-tool allow-list + trust (user_allowed) as class data; the live client is app-side, the catalog kernel-side"
    - "per-server.tool compile-validation runs at the SAME per-reference site as is_registered/_check_trust (no forked validation path) + the MCP-04 gating (powerful ⇒ security+secrets) inline on the same loop"

key-files:
  created:
    - backend/app/agents/mcp/__init__.py
    - backend/app/agents/mcp/client.py
    - backend/tests/agents/fixtures/stub_mcp_server.py
    - backend/tests/agents/test_mcp_client.py
    - backend/agents/capabilities/mcp_servers/__init__.py
    - backend/agents/capabilities/mcp_servers/catalog.py
    - backend/app/models/mcp_credential.py
    - backend/tests/agents/test_mcp_catalog.py
    - backend/tests/agents/test_mcp_compile_validation.py
    - backend/tests/agents/test_mcp_gating.py
  modified:
    - backend/requirements.txt
    - backend/agents/factory.py
    - backend/agents/execution_engine/engine.py
    - backend/agents/capabilities/registry.py
    - backend/agents/workflows/compiler.py
    - backend/app/models/__init__.py
    - backend/agents/authz.py
    - backend/alembic/versions/0017_repositories_repo_workspace.py
    - backend/tests/agents/test_registry_capabilities.py

key-decisions:
  - "Package-legitimacy checkpoint (Task 1) RESOLVED-APPROVED: langchain-mcp-adapters + transitive mcp both human-verified LEGITIMATE on PyPI (2026-06-10). VERSION-PIN DEVIATION (the checkpoint's version-resolution caution realized): the floor >=0.2.2 resolves to the day-old 0.3.0 whose transitive mcp pulls starlette 1.2.1, which BREAKS the pinned fastapi 0.115.6 (app.main failed to import). Pinned the known-good langchain-mcp-adapters>=0.2.2,<0.3 (resolved 0.2.2) + mcp==1.27.2 + sse-starlette==3.0.2 to coexist with starlette 0.41.3."
  - "Deps live in requirements.txt, NOT pyproject.toml (the 09-03 precedent; pyproject.toml carries only tooling config). Pinned there with the version-resolution + starlette-conflict rationale documented inline."
  - "The async→sync binding mirrors prewarmed_constitution EXACTLY: McpClientAdapter.get_tools() awaited ONCE at engine run-entry, stashed on AgentContext.prewarmed_mcp_tools; the sync factory unions WITHOUT awaiting (grep asyncio.run|nest_asyncio|run_until_complete in factory.py → 0). The per-run MCP scope/config is supplied by the run-entry host (ectx.mcp_server_configs), the §15 injection seam — absent any active scope the prewarm is a graceful no-op (snapshots byte-identical)."
  - "The mcp_server catalog is registration-DATA-only kernel-side (0 app/engine imports); the live MultiServerMCPClient is app-side (McpClientAdapter). user_allowed=True for github/gitlab/jira/slack (read-scoped), False for filesystem/postgres (powerful). The compiler reads user_allowed (the single trust source); the catalog CATALOG map serves the exposed-tool allow-list + powerful flag to the compile-validation."
  - "McpCredential extends the UserGithubCredential Fernet-encrypted PAT precedent — owner/workspace-scoped (AUTHZ-01), encrypted_secret never plaintext. Added additively to the 09-02 migration 0017 (this phase's migration; mcp_credentials table + reversible downgrade, SQLite upgrade→downgrade→upgrade proven). ScopedStore.read_mcp_credential is default-deny (None cross-owner); assert_mcp_cred_owned is the explicit cross-owner PermissionError gate (T-09-05-ID)."
  - "MCP-03 compile-validation + MCP-04 gating land inline in _compile_step at the same per-reference site as the other capability checks (no forked path): unknown server / tool-not-exposed / not-user-allowed-in-user-manifest → CompilerError naming the server.tool; a powerful server (filesystem/postgres) without security gate + secrets → CompilerError; read-scopes bind ungated."

patterns-established:
  - "MCP tool prewarm: connect+await get_tools() ONCE at run-entry (mirrors the Constitution prewarm), stash on ctx, sync factory reads-only — the canonical async-value-into-sync-factory-under-running-loop resolution."
  - "Offline MCP proof: an in-repo FastMCP stdio stub spawned by MultiServerMCPClient over the REAL stdio transport (no network) — connect/list/invoke + bind into a real create_deep_agent tool set, the MCP-01/04 accept gate."

requirements-completed: [MCP-01, MCP-02, MCP-03, MCP-04]

# Metrics
duration: ~40min
completed: 2026-06-10
---

# Phase 09 Plan 05: MCP Client + Catalog Summary

**The net-new MCP CLIENT layer landed (the backend was an inbound MCP server only): `McpClientAdapter` over `langchain-mcp-adapters`'s `MultiServerMCPClient` connects to an in-repo stdio stub server, lists tools, and binds the allowed ones INTO the deepagents tool set fully offline (MCP-01) — the async→sync binding resolved by mirroring the `prewarmed_constitution` seam (await `get_tools()` ONCE at run-entry, stash on `AgentContext.prewarmed_mcp_tools`, the sync factory only unions, no double-loop); the allow-listed kernel-side `mcp_server` catalog (github/gitlab/jira/slack `user_allowed=True` read-scoped + filesystem/postgres `user_allowed=False` powerful) with a scoped Fernet-encrypted `McpCredential` (cross-owner read raises `PermissionError`, MCP-02); the compiler's per-`server.tool` compile-validation (MCP-03); and the `security`-gate+`secrets` gating for powerful servers, read-scopes ungated (MCP-04) — all proven by `test_mcp_client/catalog/compile_validation/gating.py`, INV-13 held, import-linter 4/0, the 5 characterization snapshots byte/event-identical.**

## Performance
- **Duration:** ~40 min (incl. the dep-resolution starlette-conflict diagnosis)
- **Tasks:** 3 (Task 1 checkpoint resolved-approved; Tasks 2-3 executed)
- **Files modified:** 19 (10 created, 9 modified)

## Checkpoint Outcome (Task 1 — package legitimacy, blocking-human)

Task 1 was the `checkpoint:human-verify` (gate="blocking-human") package-legitimacy gate for the two `[ASSUMED]` MCP-client dependencies (slopcheck unavailable offline). **Resolved: APPROVED** with verification performed live against PyPI (2026-06-10):

- **`langchain-mcp-adapters`** — VERIFIED LEGITIMATE. Official `github.com/langchain-ai/langchain-mcp-adapters` (LangChain org; author Vadym Barda, LangChain/LangGraph core dev); 40+ releases since Feb 2025; provides `MultiServerMCPClient`. Version 0.2.2 exists (2026-03-16, `requires_dist` `mcp>=1.9.2`).
- **`mcp` (transitive)** — VERIFIED LEGITIMATE. The official Model Context Protocol Python SDK; `github.com/modelcontextprotocol/python-sdk`; author Anthropic PBC (maintainers David Soria Parra, Justin Spahr-Summers). Provides the stdio `FastMCP` server for the D-06 stub.

**The exact spec `langchain-mcp-adapters` was approved (no substitutes).** The checkpoint's version-resolution caution was REALIZED → see Deviation 1 (the day-old 0.3.0 broke the app; pinned `<0.3`).

## Accomplishments
- Pinned `langchain-mcp-adapters>=0.2.2,<0.3` (resolved 0.2.2) + `mcp==1.27.2` + `sse-starlette==3.0.2` in `requirements.txt` (the project dep home, 09-03 precedent) with the version-resolution + starlette-conflict rationale documented inline.
- Built `app/agents/mcp/client.py` `McpClientAdapter` (app-side) over `MultiServerMCPClient`: construct from the catalog stdio/http config, `await get_tools()` returns LangChain-compatible tools, an exposed-tool allow-list filters the bound set (defence in depth at bind). The bound tools AUGMENT the deepagents runtime (INV-13); the module builds no agent loop.
- Added `AgentContext.prewarmed_mcp_tools` + the async prewarm at the engine run-entry (the SAME block as the Constitution prewarm) + the sync-factory union in `_resolve_runner_tools` — NO `await`/`asyncio.run` in the sync factory (grep → 0).
- Built the in-repo stdio FastMCP stub (`tests/agents/fixtures/stub_mcp_server.py`, `echo`/`add`) + `test_mcp_client.py`: connect/list/invoke over the REAL stdio transport offline + bind into a real `create_deep_agent` tool set + the sync-factory union test.
- Built the kernel-side `mcp_server` catalog (registration DATA only): github/gitlab/jira/slack `user_allowed=True` (read-scoped) + filesystem/postgres `user_allowed=False` (powerful); each class carries transport + exposed-tool allow-list + scope + `powerful` flag. Wired six `("mcp_server", …)` pairs into `_KNOWN` (40→46) + the drift guard + `discover()`.
- Built `McpCredential` (owner-scoped + Fernet-encrypted, the PAT precedent) + the additive `mcp_credentials` table in migration 0017 (reversible; SQLite upgrade→downgrade→upgrade proven) + `ScopedStore.write_mcp_credential`/`read_mcp_credential`/`assert_mcp_cred_owned` (default-deny; cross-owner `PermissionError`).
- Added the MCP-03 per-`server.tool` compile-validation + MCP-04 gating inline in `_compile_step` (`_validate_mcp_grant`): unknown server / tool-not-exposed / not-user-allowed-in-user-manifest / missing-separator → `CompilerError` naming the ref; powerful server without `security`+`secrets` → `CompilerError`; read-scopes ungated.

## Task Commits
1. **Task 2 (Wave 0): McpClientAdapter + stub stdio server + async prewarm + test_mcp_client.py** — `a3828dc` (feat)
2. **Task 3 (Wave 0): mcp_server catalog + scoped creds + compile-validation + gating + tests** — `1ca00ad` (feat)

**Plan metadata:** _(final docs commit below)_

## Decisions Made
- See `key-decisions` in the frontmatter. Headline: the floor `>=0.2.2` resolved to the day-old 0.3.0 whose transitive starlette broke the app → pinned `<0.3` (the checkpoint's documented caution); the async→sync binding mirrors `prewarmed_constitution`; the catalog is kernel-side DATA + the client app-side; `McpCredential` extends the PAT precedent into the additive 0017 migration.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] langchain-mcp-adapters floor `>=0.2.2` resolved to the day-old 0.3.0 → transitive starlette 1.2.1 broke the app → pinned `<0.3`**
- **Found during:** Task 2 (dep install)
- **Issue:** The plan's `>=0.2.2` floor resolved to `0.3.0` (released 2026-06-10, the same day), whose transitive `mcp 1.27.2` pulled `starlette 1.2.1` + `sse-starlette 3.4.4` into the user site, SHADOWING the project's `starlette 0.41.3`. `fastapi==0.115.6` requires `starlette<0.42` — with 1.2.1 active, `import app.main` FAILED (`Router.__init__() got an unexpected keyword argument 'on_startup'`). This is exactly the version-resolution hazard the checkpoint flagged.
- **Fix:** Per the documented caution, pinned the known-good `langchain-mcp-adapters>=0.2.2,<0.3` (resolved 0.2.2). `mcp` only pins `starlette>=0.27` (no upper bound), so it did NOT itself force the breaking upgrade — kept `mcp==1.27.2`. Removed the user-site `starlette 1.2.1` (restoring `0.41.3`) and pinned `sse-starlette==3.0.2` (whose starlette pin is an `examples` extra only, so it coexists with 0.41.3). Proven: `FastMCP` + `MultiServerMCPClient` + `app.main` all import together; starlette is NOT bumped.
- **Files modified:** backend/requirements.txt
- **Committed in:** a3828dc (Task 2 commit)

**2. [Rule 3 - Blocking] Deps live in requirements.txt, not pyproject.toml**
- **Found during:** Task 2 (dep pinning)
- **Issue:** The plan named `backend/pyproject.toml` for the dep add, but the project's actual dependency home is `backend/requirements.txt` (where every dep lives; pyproject.toml carries only ruff/import-linter/pytest config). The 09-03 precedent established this exact deviation.
- **Fix:** Pinned in `requirements.txt` (the project convention, per 09-03).
- **Files modified:** backend/requirements.txt
- **Committed in:** a3828dc (Task 2 commit)

**3. [Rule 2 - Missing critical functionality] McpCredential needed a DB table → added additively to migration 0017**
- **Found during:** Task 3 (McpCredential model)
- **Issue:** The plan's Task-3 file list named the `McpCredential` model but no migration; a SQLAlchemy model with no table cannot persist in production (the offline tests use `Base.metadata.create_all`, but production needs the additive migration — CLAUDE.md mandates additive migrations for every new table).
- **Fix:** Added the `mcp_credentials` table to migration 0017 (this phase's own migration, authored in 09-02 and not yet released) additively, with a reversible `downgrade()`. Verified reversible against SQLite (upgrade head → downgrade -1 → upgrade head). Both `owner_id` + `workspace_id` carried (AUTHZ-01 / Q3). The migration-ledger test stays green.
- **Files modified:** backend/alembic/versions/0017_repositories_repo_workspace.py, backend/app/models/__init__.py
- **Committed in:** 1ca00ad (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (2 Rule 3 blocking, 1 Rule 2 missing critical functionality). All stay within the plan's intent (the version caution was pre-authored in the checkpoint; the requirements.txt home is the established convention; the additive migration is the CLAUDE.md mandate). No scope creep.

## Issues Encountered
- The day-old 0.3.0 starlette conflict (Deviation 1) was the only friction — diagnosed via the `app.main` import failure and resolved by the documented `<0.3` pin + a coexisting `sse-starlette`. No time burned debugging the 0.3.0 API surface (the caution's explicit instruction).

## Known Stubs
None blocking. The per-run MCP scope/config seam (`ectx.mcp_server_configs` / `ectx.mcp_exposed_tools`) is read at the engine run-entry prewarm but is supplied by the run-entry HOST (the §15 injection seam, exactly like the 09-04 RepoSpec injection) — absent an active scope the prewarm is a graceful no-op. This is a plan-declared forward input (the 09-06 integration providers + a runtime host wire which servers a run activates), not a UI-blocking stub. The catalog transport `command`/`args`/`url` are likewise host-supplied per-run (the catalog declares the transport KIND + allow-list, not the live endpoint/credential).

## Threat Flags
None beyond the plan's `<threat_model>`. T-09-05-EoP (powerful FS/PG server) is mitigated: `user_allowed=False` + the MCP-04 security-gate+secrets requirement (`test_mcp_gating.py`); read-scopes ungated. T-09-05-ID (cross-owner cred read) is mitigated: `McpCredential` owner-scoped + Fernet-encrypted; `ScopedStore.read_mcp_credential` default-deny (None cross-owner) + `assert_mcp_cred_owned` raises `PermissionError` (`test_mcp_catalog.py::test_cross_owner_mcp_credential_read_is_denied`). T-09-05-Tamper (unvalidated server.tool) is mitigated: the per-`server.tool` compile-validation (`test_mcp_compile_validation.py`). T-09-05-INV13 (MCP tool replacing the runtime) is mitigated: tools bind INTO `create_deep_agent` (augment); banned-pattern gate green. T-09-05-SC (slopsquatted dep) was mitigated by the Task 1 blocking-human checkpoint (both deps human-verified) + the `<0.3` pin away from the day-old release.

## User Setup Required
None — the deps install from prebuilt wheels (no C toolchain, no network at runtime). Live MCP server endpoints/credentials are supplied per-run by the host when a run activates an MCP scope (forward integration).

## Next Phase Readiness
- The MCP client foundation (adapter + async prewarm + catalog + scoped creds + compile-validation + gating) is ready for 09-06 (the integration providers github/gitlab/jira/slack that bridge onto this ONE MCP mechanism + the handoff-bypass deletion).
- import-linter 4/0; banned-pattern green (INV-13 held — MCP tools augment, the adapter builds no agent loop); 5 characterization snapshots byte/event-identical (09-05 is purely additive — the prewarm is a no-op with no active scope); migration 0017 reversible incl. the new mcp_credentials table.

## Verification Evidence
- `tests/agents/test_mcp_client.py` — 5 passed (adapter connects to the stub stdio server + lists + invokes echo/add over the REAL transport offline; exposed-tool allow-list filters; the bound MCP tool binds into a real create_deep_agent tool set + invokes via stdio; the sync factory unions ctx.prewarmed_mcp_tools without awaiting; pure-text parity preserved).
- `tests/agents/test_mcp_catalog.py` — 6 passed (github/gitlab/jira/slack user_allowed=True, filesystem/postgres False; exposed-tool + powerful flags; a per-owner cred stored scoped + encrypted + same-owner decrypt; cross-owner read → None + assert raises PermissionError).
- `tests/agents/test_mcp_compile_validation.py` — 6 passed (unknown_server.tool / tool-not-exposed / missing-separator / not-user-allowed-in-user-manifest → CompilerError naming the ref; a valid read-scoped reference compiles in file + user manifests).
- `tests/agents/test_mcp_gating.py` — 4 passed (powerful server without security+secrets / with security-but-no-secrets → CompilerError; with security+secrets compiles; read-scoped binds ungated).
- `cd backend && grep -nE "asyncio.run|nest_asyncio|run_until_complete" agents/factory.py` → 0 (async-prewarm only).
- `cd backend && grep -n "prewarmed_mcp_tools" agents/factory.py agents/execution_engine/engine.py` → the field + the run-entry await + the AgentContext threading.
- `cd backend && python3.11 -c "...discover(); print(r.is_user_allowed('mcp_server','github'), r.is_user_allowed('mcp_server','filesystem'))"` → `True False`.
- `cd backend && grep -rnE "import (app|agents\.execution_engine)" agents/capabilities/mcp_servers/` → 0 (catalog kernel-clean — data only).
- `tests/agents/test_registry_capabilities.py` — drift guard 40→46 (6 new mcp_server pairs); 83 passed across the mcp + registry suites.
- `tests/agents/test_banned_patterns.py` — 11 passed (INV-13 held; create_deep_agent allow-list intact); `tests/agents/test_migration_ledger.py` — 31 passed / 4 skipped (combined run).
- `DATABASE_URL=sqlite:///... alembic upgrade head && alembic downgrade -1 && alembic upgrade head` — all succeed (0017 incl. mcp_credentials reversible).
- `/opt/homebrew/bin/lint-imports` — 4 kept / 0 broken (McpClientAdapter app-side; catalog kernel-side data).
- 5 characterization snapshots (`prototype`/`app_builder`/`od_ppt`/`od_prototype`/`prototype_revision`) + `test_repositories_persistence.py` — 12 passed (byte/event-identical, additive; the new mcp_credentials table builds cleanly via Base.metadata.create_all).

## Self-Check: PASSED
- FOUND: backend/app/agents/mcp/client.py
- FOUND: backend/agents/capabilities/mcp_servers/catalog.py
- FOUND: backend/app/models/mcp_credential.py
- FOUND: backend/tests/agents/fixtures/stub_mcp_server.py
- FOUND commit: a3828dc
- FOUND commit: 1ca00ad

---
*Phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a*
*Completed: 2026-06-10*
