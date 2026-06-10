---
phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
plan: 06
subsystem: agents
tags: [integration-providers, mcp-bridge, integrations-scopes, run-capabilities, codingagent-deletion, inv13, inv12, migration-ledger, handoff, hexagonal-ports]

# Dependency graph
requires:
  - phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a
    plan: 05
    provides: "the mcp_server catalog (github/gitlab/jira/slack transport + exposed-tool allow-list as DATA) + the McpClientAdapter async-prewarm seam (prewarmed_mcp_tools) the integration bridge reuses"
  - phase: 08-capabilities-runtime-frontend-1d
    provides: "self-registering CapabilityRegistry (@register user_allowed / discover() / _KNOWN drift guard); ToolPermissions.integrations slot + intersect_permissions (08-03); DeepAgentRunner the unified deepagents runtime"
  - phase: 05-typed-artifacts-persistence-ownership-1b
    provides: "ScopedStore.record_capabilities (run_capabilities row) + the UserGithubCredential Fernet PAT precedent"
provides:
  - "agents/capabilities/integration_providers/providers.py — @register('integration_provider', github|gitlab|jira|slack) thin MCP-backed bridges (ONE mechanism, no parallel SDK — D-08) + resolve_integration_scopes() mapping a granted integrations scope → the MCP prewarm inputs"
  - "IntegrationProvider port (base.py); _KNOWN 46→50; discover() imports the integration_providers package"
  - "engine run-entry bridges integration_scopes into the SAME MCP prewarm; record_capabilities records the active integration scopes + MCP servers (INTEG-02 / CAPRUN-01)"
  - "app/agents/handoff/coder.py HandoffCoder — the unified-runtime (create_deep_agent) edit-plan producer that SUPERSEDES the deleted CodingAgent build_model().ainvoke bypass (D-09 / INV-13)"
  - "migration-ledger D9 (CodingAgent deletion grep gate) + D10 (RETAINED /api/handoff routers + UserGithubCredential justification)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "the integration bridge is THIN + DATA-only: a granted integrations scope → the catalog mcp_server's transport config + exposed-tool allow-list, fed into the SAME McpClientAdapter prewarm the MCP catalog uses (resolve_integration_scopes) — ONE mechanism (MCP), no PyGithub/python-gitlab/slack_sdk parallel path (D-08)"
    - "deletion-by-alias: the runtime-bypassing class is deleted (grep `class CodingAgent` → 0) while a successor (HandoffCoder) is exported under the legacy name so a retained external surface + its contract seam bind the same name unchanged (INV-12 move-don't-copy without breaking a live consumer)"
    - "a bypass deletion routes the invocation through the sanctioned runtime: build_model().ainvoke → DeepAgentRunner(tools=[]) → create_deep_agent, accumulating the chunk/done event stream and parsing the same JSON edit-plan (INV-13 — every agent runs on deepagents)"
    - "run_capabilities is the per-run audit row for external surface: the active integration scopes + the MCP servers they activate persist alongside the runtime; default-none ⇒ SQL NULL (INV-3 row parity)"

key-files:
  created:
    - backend/agents/capabilities/integration_providers/__init__.py
    - backend/agents/capabilities/integration_providers/providers.py
    - backend/app/agents/handoff/coder.py
    - backend/tests/agents/test_integration_providers.py
    - backend/tests/agents/test_integration_scopes.py
  modified:
    - backend/agents/capabilities/base.py
    - backend/agents/capabilities/registry.py
    - backend/agents/execution_engine/engine.py
    - backend/app/agents/handoff/__init__.py
    - backend/tests/agents/test_registry_capabilities.py
    - backend/tests/unit/test_handoff_agents.py
    - backend/tests/agents/test_migration_ledger.py
    - specs/003-workflow-engine-decoupling/migration-ledger.md
  deleted:
    - backend/app/agents/handoff/coding_agent.py

key-decisions:
  - "The integration bridge is registration-DATA-only kernel-side (0 app/engine imports, lint 4/0): each provider holds its scope + bridges the matching catalog mcp_server; resolve_integration_scopes() composes the EXACT two inputs the 09-05 MCP prewarm already consumes (mcp_server_configs + mcp_exposed_tools), so an integration's tools surface into create_runner through the IDENTICAL McpClientAdapter path — no parallel SDK (D-08)."
  - "integrations scopes default NONE (INTEG-02): resolve_integration_scopes([]) → empty maps → zero tools bound (graceful no-op; characterization activates none → snapshots byte-identical). Granting gitlab_read activates ONLY the gitlab provider (its catalog read-tool allow-list). The 08-03 intersect_permissions is the gate (a scope absent from the workflow ceiling OR step grant is not effective) — the bridge only translates a GRANTED scope."
  - "run_capabilities records the active integration scopes + MCP servers + runtime per run (CAPRUN-01): the engine reads host-injected ectx.integration_scopes, maps via SCOPE_TO_SERVER, and passes integrations=(scopes or None)/mcp_servers=(servers or None) to record_capabilities. The RunCapabilities columns (integrations/mcp_servers) already existed (05-04 forward slots); only the engine wiring landed."
  - "CodingAgent deletion via ALIAS (D-09 / INV-12): coding_agent.py (the build_model().ainvoke bypass that skipped create_deep_agent — the INV-13 gap) is DELETED. Its successor HandoffCoder (coder.py) produces the same JSON edit-plan but invokes through DeepAgentRunner → create_deep_agent (the unified runtime). handoff/__init__.py exports `CodingAgent = HandoffCoder` so handoff_pipeline.py's import + the contract test's `patch.object(hp, 'CodingAgent', ...)` seam are UNCHANGED — the retained /api/handoff endpoint drives identically. grep `class CodingAgent` → 0 (the bypass CLASS is gone)."
  - "re-point vs retain-whole (RESEARCH item 6, LOW): chose RE-POINT — the coding step's CodingAgent name now resolves to the unified-runtime HandoffCoder. test_handoff_contract.py mocks propose_edits entirely (the golden never exercises the coder internals), so the event/edit-plan shape is byte-identical and the deletion-scope guard stays green."
  - "RETAINED with justification (D-09 / Pitfall 4): app/api/handoff.py + app/api/websocket_handoff.py (the live external IDE surface, registered main.py:153,157) + app/services/handoff_github.py + app/models/handoff.py incl. UserGithubCredential (the PAT precedent / MCP-cred model). Ledger row D10 marks them RETAINED-with-justification; test_handoff_contract.py is the deletion-scope guard."
  - "The CodingAgent unit cases (build_model-patched one-shot) were DELETED — they exercised the deleted bypass invocation, which HandoffCoder no longer uses; the pipeline-level contract (coding-step events + edit-plan) is covered by test_handoff_contract.py. TestAgent/ComplianceAgent unit cases (also build_model-based but NOT the D-09 deletion target) stay untouched (scope discipline)."

patterns-established:
  - "Integration-provider bridge: a permissioned thin DATA capability that maps a granted permission scope onto a catalog MCP server's tools via the existing async prewarm seam — the template for future external-tool integrations (one mechanism, no per-vendor SDK)."
  - "Bypass-deletion-by-alias: delete a runtime-bypassing class (grep gate → 0) and re-export a runtime-compliant successor under the legacy name so a retained live consumer + its contract seam are unchanged — INV-12 move-don't-copy that does not break an external surface (D-09 deletion-scope guard)."

requirements-completed: [INTEG-01, INTEG-02]

# Metrics
duration: ~30min
completed: 2026-06-10
---

# Phase 09 Plan 06: Integration Providers + Handoff-Bypass Deletion Summary

**The phase closes: github/gitlab/jira/slack `integration_provider` capabilities reach the unified `create_runner` path as THIN MCP-backed bridges onto the 09-05 catalog (ONE mechanism, no parallel SDK — `resolve_integration_scopes()` maps a granted `integrations` scope onto the EXACT `mcp_server_configs`/`mcp_exposed_tools` the existing async MCP prewarm consumes; INTEG-01); `integrations` scopes default NONE (granting `gitlab_read` binds only the gitlab read tools, the 08-03 intersection gates the grant, `run_capabilities` records the active scopes + MCP servers + runtime per run; INTEG-02); and the `CodingAgent` `build_model().ainvoke` bypass (the INV-13 gap D-09 named) is DELETED — its successor `HandoffCoder` produces the same JSON edit-plan through the sanctioned `DeepAgentRunner` → `create_deep_agent` runtime and is exported under the legacy `CodingAgent` name so the RETAINED `/api/handoff` routers + `UserGithubCredential` (ledger D10) + the handoff contract drive identically (grep `class CodingAgent` → 0, ledger D9). The 5-pipeline characterization stays byte/event-identical, the handoff contract + migration-ledger + banned-pattern gates stay green, lint-imports 4/0.**

## Performance
- **Duration:** ~30 min
- **Tasks:** 2 (both `type=auto`, both executed)
- **Files:** 13 (5 created, 8 modified, 1 deleted)

## Accomplishments

### Task 1 (Wave 0) — integration providers + integrations scopes + run_capabilities
- Created `agents/capabilities/integration_providers/providers.py`: four `@register("integration_provider", github|gitlab|jira|slack", user_allowed=True)` THIN bridges, each holding its `scope` + bridging the matching 09-05 catalog `mcp_server` (transport + exposed-tool allow-list as DATA — no live client, no vendor SDK, D-08).
- `resolve_integration_scopes(granted_scopes, host_configs)` maps a GRANTED `integrations` scope → `(mcp_server_configs, mcp_exposed_tools)` — the EXACT two inputs the engine run-entry MCP prewarm already consumes. Default-none ⇒ empty maps ⇒ zero tools bound.
- Added the `IntegrationProvider` port to `base.py`; wired the four `("integration_provider", …)` pairs into `_KNOWN` (46→50) + the `discover()` import.
- Engine run-entry: a bridge block translates host-injected `ectx.integration_scopes` into the SAME MCP prewarm (merging with any host MCP configs); `record_capabilities` now records the active integration scopes + the MCP servers they activate (`integrations`/`mcp_servers`, `or None` ⇒ SQL NULL for a no-integration run).
- Wave-0 tests: `test_integration_providers.py` (all four resolve from `create_runner`; a granted scope surfaces the integration's tools via the unified prewarm union against the offline stub MCP server; no vendor-SDK import — AST scan) + `test_integration_scopes.py` (default none binds nothing; `gitlab_read` binds only gitlab read tools; the intersection gates an ungranted scope; a `run_capabilities` row records scopes + servers + runtime).

### Task 2 — delete the CodingAgent bypass; retain the routers
- DELETED `app/agents/handoff/coding_agent.py` — the `build_model().ainvoke` one-shot that skipped `create_deep_agent`/`create_runner` (the INV-13 gap, D-09).
- Created `app/agents/handoff/coder.py` `HandoffCoder`: the same JSON edit-plan contract, but the model invocation flows through `DeepAgentRunner(tools=[])` → `create_deep_agent` (the unified runtime), accumulating the `chunk`/`done` event stream and parsing the plan with the reused `_extract_json`/`_extract_text` helpers.
- `handoff/__init__.py` exports `CodingAgent = HandoffCoder` (alias) so `handoff_pipeline.py`'s import + the contract test's `patch.object(hp, "CodingAgent", …)` seam are unchanged — `handoff_pipeline.py` needed NO edit.
- Deleted the `CodingAgent` unit cases (`tests/unit/test_handoff_agents.py`); TestAgent/ComplianceAgent cases retained.
- RETAINED (Pitfall 4): `app/api/handoff.py`, `app/api/websocket_handoff.py`, `app/services/handoff_github.py`, `app/models/handoff.py` (incl. `UserGithubCredential`).
- Migration-ledger: `D9` (CodingAgent deletion, grep gate `class CodingAgent` → 0) + `D10` (RETAINED `/api/handoff` routers + `UserGithubCredential` CHECK-with-justification); updated the ratchet `_REQUIRED_ITEMS` + `expected` flipped list.

## Task Commits
1. **Task 1 (Wave 0): integration_provider bridges + integrations scopes + run_capabilities** — `3245f02` (feat)
2. **Task 2: delete CodingAgent bypass; retain /api/handoff** — `b17eeca` (feat)

**Plan metadata:** _(final docs commit below)_

## Decisions Made
See `key-decisions` in the frontmatter. Headline: the integration bridge is one MCP mechanism (no parallel SDK — `resolve_integration_scopes` feeds the existing prewarm); the CodingAgent bypass is deleted-by-alias (grep `class CodingAgent` → 0, `HandoffCoder` runs on the deepagents runtime, exported under the legacy name so the retained `/api/handoff` surface + contract are unchanged); scopes default none + recorded per run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `handoff_pipeline.py` needed NO edit (the plan listed it as modified)**
- **Found during:** Task 2
- **Issue:** The plan's Task-2 files named `app/services/handoff_pipeline.py` for re-pointing the `CodingAgent` import. The cleanest re-point binds `CodingAgent = HandoffCoder` in `app/agents/handoff/__init__.py`, so the pipeline's `from app.agents.handoff import CodingAgent` import + the contract test's `patch.object(hp, "CodingAgent", …)` seam stay byte-unchanged.
- **Fix:** Re-pointed at the `__init__` export (the import source) rather than the pipeline body — keeps the pipeline + the contract golden untouched (the lower-risk choice; RESEARCH item 6 LOW).
- **Files modified:** backend/app/agents/handoff/__init__.py (instead of handoff_pipeline.py)
- **Committed in:** b17eeca

**2. [Rule 1 - Bug] Initial `coder.py` read the wrong runner event shape**
- **Found during:** Task 2
- **Issue:** The first `coder.py` accumulated `event["data"]["content"]` on an `agent_chunk` type — that is the ENGINE-vocabulary event, not the `DeepAgentRunner.astream_events` shape, which emits `{"type":"chunk","chunk":str}` + a terminal `{"type":"done","output":str}`.
- **Fix:** Accumulate `chunk` events and prefer the authoritative `done.output`; raise on an `error` event.
- **Files modified:** backend/app/agents/handoff/coder.py
- **Committed in:** b17eeca

**3. [Rule 1 - Bug] The `class CodingAgent` grep gate tripped on my own prose**
- **Found during:** Task 2 verification
- **Issue:** Docstrings/comments in `__init__.py`, `coder.py`, and the two test files mentioned the literal phrase `class CodingAgent` (as the deleted target), which the ledger grep gate (`grep -rnE "class CodingAgent" backend/ --include=*.py`) matched → false non-zero.
- **Fix:** Reworded every prose mention to "bypass class" / "bypass-class grep" so only an actual `class CodingAgent` definition would match. grep → 0.
- **Files modified:** backend/app/agents/handoff/__init__.py, backend/app/agents/handoff/coder.py, backend/tests/unit/test_handoff_agents.py, backend/tests/agents/test_migration_ledger.py
- **Committed in:** b17eeca

---

**Total deviations:** 3 auto-fixed (1 Rule 3 blocking, 2 Rule 1 bug). All within plan intent. No scope creep.

## Issues Encountered
- None beyond the three auto-fixed deviations. The `RunCapabilities.integrations`/`mcp_servers` columns + the `record_capabilities` deferred kwargs already existed (05-04 forward slots), so persistence needed only the engine wiring.

## Known Stubs
None blocking. The per-run integration scope/credential wiring (`ectx.integration_scopes` / `ectx.integration_host_configs`) is host-injected at run-entry (the §15 seam, exactly like the 09-05 `mcp_server_configs` and the 09-04 RepoSpec) — absent an active scope the bridge + prewarm are a graceful no-op (snapshots byte-identical). This is a plan-declared forward input (a runtime host wires which integrations a run activates + the live endpoint/credential), not a UI-blocking stub.

## Threat Flags
None beyond the plan's `<threat_model>`. T-09-06-01 (unscoped integration tool binding) mitigated: scopes default none, `gitlab_read` binds only gitlab read tools, the 08-03 intersection gates the grant (`test_integration_scopes.py`). T-09-06-INV13 (CodingAgent bypass skipping the runtime) mitigated: the bypass is DELETED, `HandoffCoder` flows through `create_deep_agent`, banned-pattern + ledger gates green. T-09-06-Avail (deleting the live router) mitigated: the routers + `UserGithubCredential` RETAINED (ledger D10), `test_handoff_contract.py` green. T-09-06-Parity mitigated: 5 snapshots byte/event-identical (SNAPSHOT_UPDATE UNSET). T-09-06-SC: no new dependency this plan.

## Verification Evidence
- `tests/agents/test_integration_providers.py` + `tests/agents/test_integration_scopes.py` — 14 passed (all four resolve from `create_runner`; a granted scope surfaces tools via the unified prewarm union over the offline stub MCP server; default none binds nothing; `gitlab_read` binds only gitlab read tools; the intersection gates an ungranted scope; `run_capabilities` records scopes + servers + runtime; no vendor-SDK import via AST scan).
- `python3.11 -c "...discover(); print(all(r.is_registered('integration_provider',n) for n in ('github','gitlab','jira','slack')))"` → `True`.
- `grep -rniE "PyGithub|python-gitlab|slack_sdk|slack-sdk" agents/capabilities/integration_providers/` → 0 (one mechanism — no parallel SDK).
- `grep -rnE "import (app|agents\.execution_engine)" agents/capabilities/integration_providers/` → 0 (kernel-clean); `/opt/homebrew/bin/lint-imports` → 4 kept / 0 broken.
- `grep -rnE "class CodingAgent" backend/ --include=*.py` → 0 (the bypass deleted — ledger D9 gate).
- `app/api/handoff.py`, `app/api/websocket_handoff.py`, `app/services/handoff_github.py`, `app/models/handoff.py` (incl. `UserGithubCredential`) — all present (RETAINED, Pitfall 4).
- `tests/integration/test_handoff_contract.py` GREEN (the deletion-scope guard — the retained endpoint's pipeline still drives; `CodingAgent` alias resolves to `HandoffCoder`).
- `tests/agents/test_migration_ledger.py` — 31 passed / 4 skipped (both D9/D10 rows parse; D9 grep gate = 0; the flipped set matches `expected`).
- `tests/agents/test_banned_patterns.py` — 12 passed (the bypass removed closes the INV-13 gap; no hand-rolled loop reintroduced; `create_deep_agent` allow-list intact).
- `tests/unit/test_handoff_agents.py` — green (CodingAgent cases removed; TestAgent/ComplianceAgent retained).
- 5 characterization snapshots (`prototype`/`app_builder`/`od_ppt`/`od_prototype`/`prototype_revision`) — byte/event-identical with SNAPSHOT_UPDATE UNSET (25 passed combined with the unit handoff suite).
- `tests/agents/test_registry_capabilities.py` — 73 passed (drift guard 46→50; the four `integration_provider` pairs).
- Combined integration + registry + mcp_catalog + run_capabilities run — 95 passed.

## Next Phase Readiness
- Phase 09 = 6/6 plans complete. The unified runtime kernel now reaches github/gitlab/jira/slack via one MCP mechanism from `create_runner`, the `integrations` scopes are recorded per run, and the last INV-13 runtime bypass (CodingAgent) is gone while the live `/api/handoff` surface survives — ready for phase 09 verification.
- No new dependency; import-linter 4/0; banned-pattern green (INV-13 held); 5 characterization snapshots byte/event-identical; migration-ledger D9/D10 landed.

## Self-Check: PASSED
- FOUND: backend/agents/capabilities/integration_providers/providers.py
- FOUND: backend/app/agents/handoff/coder.py
- FOUND: backend/tests/agents/test_integration_providers.py
- FOUND: backend/tests/agents/test_integration_scopes.py
- DELETED (confirmed gone): backend/app/agents/handoff/coding_agent.py
- FOUND commit: 3245f02
- FOUND commit: b17eeca

---
*Phase: 09-local-workspace-runtime-repo-workflows-no-exec-4a*
*Completed: 2026-06-10*
