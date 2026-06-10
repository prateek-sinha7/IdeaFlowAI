# Migration & Deletion Ledger (003 Workflow Engine Decoupling)

> **Operational mirror of `plan.md` §31** (DEL-04). This file is the single source of
> truth that CI asserts against via `backend/tests/agents/test_migration_ledger.py`
> (D-08 / D-09). It reproduces every `L#` / `F#` / `D#` row from §31 — same columns,
> verbatim grep patterns — so nothing from the plan can be silently dropped.

## Legend

- `☐` **pending** — the legacy element still legitimately exists; **not yet enforced** by CI.
- `☑` **done** — behavior moved (not copied), call-sites rewired, legacy deleted. Once a
  row is `☑`, its `Deletion gate` becomes a **permanent ratchet**: reintroducing the
  banned pattern fails CI (DEL-03).

## Ratchet rule (DEL-01 / DEL-02 / DEL-03)

The strangler migration **moves** code; it never copies it. For every legacy element the
sequence is **wrap → rewire call-sites → delete**, completed **within the phase that
supersedes it** (one row per legacy element, owning phase noted). `test_migration_ledger.py`
parses this table and, **for each `☑` row whose gate is a grep pattern only**, runs that
pattern over `backend/` and asserts **0 matches**. `☐` rows are not yet enforced. In Phase 1
**every row is `☐`** (nothing deleted yet, D-10) → the guard is **green / empty** and tightens
as later phases flip rows to `☑`.

## Gate cell convention (grep rows vs CHECK rows)

The `Deletion gate` column holds one of two things, distinguished by the parser:

- **grep row** — a verbatim `grep -rnE` pattern (regex / identifier tokens). When the row is
  `☑`, the pattern must return 0 matches in `backend/`.
- **CHECK row** — a prose / `test:` assertion that cannot be expressed as a grep pattern
  (e.g. "a denial test passes"). These cells are written as **metacharacter-free prose** so
  the parser classifies them as a CHECK row, yields them as `(item, None)`, and the
  parametrized deletion test `pytest.skip()`s them. Their enforcement lives in a dedicated
  test in the owning phase, not in the grep ratchet. The CHECK rows are **L16**, **F4**, **F5**.

> **INV-1 reservation note:** the `if pipeline_type ==` / `spec.id ==` dispatch reservation is
> enforced via the **L7** and **L10** rows. In Phase 7 (07-05) those rows flipped to `☑` and
> the banned-pattern gate (`tests/agents/test_banned_patterns.py`) became a KERNEL-SCOPED
> HARD-FAIL (`assert 0` over `agents/execution_engine/`) — reintroducing a kernel
> workflow-name/agent-id branch fails CI (SC-001 ratchet).
>
> **07-05 kernel-scoping note:** the **L1–L13** grep gates are asserted against the KERNEL
> (`agents/execution_engine/`), NOT the whole `backend/` — INV-1/SC-001 is a property of the
> runtime kernel's routed path, and the bare-token / lifted-construct patterns legitimately
> reappear OUTSIDE the kernel: the capability impls that are the **move-don't-copy homes**
> (`agents/capabilities/deliverables/_artifact.py`, `…/task_parsers/heading_tasks.py`,
> `…/compaction/html_skeleton.py`), the registry's `REVISION_BASE_MAP`/`PIPELINE_AGENTS`,
> `app/` consumers, and tests. The ratchet (`test_migration_ledger.py`) scopes L1–L13 to the
> kernel and keeps L14/L15 tree-wide. Two patterns were **refined to the leak construct**
> (not the bare token) because the bare token legitimately survives as LIVE behavior:
> **L4/L8** uses `pipeline_type == "prototype_revision"` (the inline name-branch the
> parent-seed leak used — now 0; the agnostic revision setup, which the manifest's
> `previous_run` provider now gates, keeps `prototype_revision` only in log/comment strings),
> and **L11** drops the two retained survivors `_run_validation_fix_loop` /
> `_load_template_example` (LIVE — reached via the `KernelServices` handle by the `task_loop`
> strategy + the revision post-loop) and greps only the four genuinely-deleted symbols.

## Migration & deletion ledger

> `☐` pending · `☑` done — updated (status + deleting commit SHA) as phases land, like the
> decision log. `L#` = engine leak (§4); `F#` = factory/runtime; `D#` = dead code. The
> **Deleting SHA** is left blank for `☐` rows and filled when a row flips to `☑`.

| Item | Legacy (`file:line`) | New home | Phase | Deletion gate (grep → 0 / check) | Status | Deleting SHA |
|---|---|---|---|---|---|---|
| L14 | `self._od_context/_completed_tasks/_current_task_block/_revision_*/_gate_agent_ids` (engine, throughout) | `ExecutionContext` (§6) | 0B | `self\._(od_context\|completed_tasks\|current_task_block\|revision_\|gate_agent_ids)` | ☑ | 8b90fd2 |
| L16 | unchecked `parent_run` seed `engine.py:583-610` | authz store check (§19) | 0B | CHECK: cross-owner denial test passes (tests/agents/test_parent_run_ownership.py) | ☑ | |
| D1 | `_handle_revision` `engine.py:2156` — **LIVE, not dead**: the frontend `run_revision` PPT-revision handler (`DashboardLayout.tsx` → `app/api/websocket.py:625`) | retain (revisit only if `run_revision` is retired) | (deferred ‡) | CHECK: voided in 0B — live `run_revision` handler, not dead code | ☐ | |
| L13 | `_extract_html_skeleton` wired inline in 0C `engine.py:2565` | `CompactionStrategy(html_skeleton)` (§30) | 0C→2 | `_extract_html_skeleton` | ☑ | 1d9234b |
| L1 | `_PPT_PIPELINE_TYPES`/`_PROTOTYPE_PIPELINE_TYPES`/`REVISION_FILE_NAME` `engine.py:93-110` | manifest `deliverable`/`seed_files` | 2 | `_PROTOTYPE_PIPELINE_TYPES\|_PPT_PIPELINE_TYPES` | ☑ | 1d9234b |
| L2/L9 | `_resolve_final_output` `engine.py:316-397` | `DeliverableResolver` registry | 2 | `_resolve_final_output` | ☑ | 1d9234b |
| L3 | `_sanitize_carousel_deck_html`/`_unwrap_artifact` `engine.py:232-313` | `ppt` resolver/transform capability | 2 | `_sanitize_carousel_deck_html\|_unwrap_artifact` | ☑ | 1d9234b |
| L4/L8 | `prototype_revision` seeding + post-fix `engine.py:519-650,917-962` | `seed_files.from_run` + `previous_run` provider + `validation` gate | 2 | `pipeline_type == "prototype_revision"` | ☑ | 1d9234b |
| L5 | `SKIP_PLANNER_FOR_PROTOTYPE` `engine.py:704-712` | manifest `planner` | 2 | `SKIP_PLANNER_FOR_PROTOTYPE` | ☑ | 1d9234b |
| L6 | `ALWAYS_CLARIFY` defaults dict `engine.py:733-743` | manifest `clarify.defaults` | 2 | `ALWAYS_CLARIFY` | ☑ | 1d9234b |
| L7 | `spec.id == "prototype-build"` dispatch `engine.py:872` | `strategy: task_loop` (§8/§9) | 2 | `spec\.id == "prototype-build"` | ☑ | 1d9234b |
| L10 | `pipeline_type in ("od_prototype","prototype")` HTML readback `engine.py:1328-1335` | `task_loop` reads `deliverable.name` | 2 | `pipeline_type in \("od_prototype", ?"prototype"\)` | ☑ | 1d9234b |
| L11 | build-loop internals `engine.py:1450-1704,2554-2563` | `TaskLoopStrategy`+`TaskParser`+validators+fix-loop+`seed_files` | 2 | `_run_build_task_loop\|_write_build_reference_files\|_count_plan_tasks\|_extract_task_block` | ☑ | 1d9234b |
| L12 | `_build_context_message` od/ppt/build injection `engine.py:2378-2512` | `ContextProvider` + generic injector | 2 | `_build_context_message` | ☑ | 1d9234b |
| L15 | `accumulated_outputs: dict[str,str]` mirror (throughout) | `ArtifactGraph`/`ArtifactRef` (§17) | 1A→**1B (delete mirror)** | `accumulated_outputs` | ☑ | aa68dc9 |
| D2 | thin-store artifact half (`store`/`retrieve_latest`/`retrieve_version`/`list_by_type`/`list_lineage`) + `WorkflowArtifact` model + `workflow_artifacts` table | `artifact_refs` + `ScopedStore` (§18) / alembic `0015` | 1B | `from app\.models\.artifact import` | ☑ | 26863bc |
| F1 | prompt-assembly inline order `factory.py:174-255` | `PromptAssemblyPolicy` (§6/§30) | 3 | `blocks\.append` | ☑ | |
| F2 | `_build_runner_tools` closed switch `factory.py:384-446` | `tool_provider` registry (§30) | 3 | `_build_runner_tools` | ☑ | 0861337 |
| F3 | inline skills/hooks injection `factory.py:220-245` | `skill_provider` / `hook_provider` (§30) | 3 | `_inject_skills\|_inject_hooks` | ☑ | |
| F4 | `_inject_constitution` async no-op `factory.py:258-306` (R12) | sync-safe load via `PromptAssemblyPolicy` | 3 | CHECK: constitution-injected-in-prod test passes | ☑ | 5d0c704 |
| F5 | `create_deep_agent` hardcoded `deep_agent_runner.py:240` | `AgentRuntimeAdapter` (§6/§30) | 3 | CHECK: create_deep_agent called only inside the langchain_deepagents adapter | ☑ | |
| R1 | `RunSandbox` bespoke per-run disk internals `app/agents/sandbox.py:49-96` | `Workspace(has_git=False, exec=off)` via `LocalSandboxRuntime` (§6, RUNTIME-02) | 9 | CHECK: RunSandbox delegates disk IO to a has_git False Workspace; the five characterization snapshots stay byte and event identical with SNAPSHOT_UPDATE unset (test_repositories_persistence + the 5 characterization files) | ☑ | |
| D9 | `CodingAgent` `build_model().ainvoke` one-shot bypass `app/agents/handoff/coding_agent.py:133-185` (skips `create_deep_agent`/`create_runner` — the INV-13 gap) | `HandoffCoder` on the deepagents runtime (`app/agents/handoff/coder.py`, `DeepAgentRunner` → `create_deep_agent`) + the `integration_provider` MCP bridge (09-06) | 9 | `class CodingAgent` | ☑ | |
| D10 | `/api/handoff` routers (`app/api/handoff.py`, `app/api/websocket_handoff.py`) + `app/services/handoff_github.py` + `UserGithubCredential` (`app/models/handoff.py:40`) | RETAINED — live external IDE integration surface with outside consumers (registered `main.py:153,157`); the PAT-cred precedent for MCP/integration creds | 9 | CHECK: RETAINED with justification (D-09 deletion-scope guard, Pitfall 4) — the routers + `UserGithubCredential` survive the `CodingAgent` deletion; `tests/integration/test_handoff_contract.py` is the deletion-scope guard | ☑ | |
| AUDIT | exec audit trail — additive `exec_runs` table (alembic `0018`, down_revision `0017`) + `ExecRun` ORM + `ScopedStore.record_exec_run` + `KernelServices.record_exec_run` (Phase 10 / EXEC-01) | the bypass-proof exec audit layer the recorder callback writes at the `exec_command` enforcement point (10-02 wires the recorder; the IN-02/forward-surface enforcement rows land in 10-04) | 10 | CHECK: the 0017→0018 chain stays a single head and is reversible offline — `tests/agents/test_exec_runs.py::test_0018_reversible_offline` (upgrade head → downgrade -1 → upgrade head) | ☐ | |
| D11 | `ExecutionPolicy.check` forward surface (`plan.py:~172` — the "FORWARD SURFACE — NOT yet wired" runtime `exec`/`network`/`secrets` helper + its `runtime_host` indirection + `_PRIVILEGED_RUNTIME_ACTIONS`) | `LocalExecutionPolicy.allows` + pre-spawn allow/deny (`app/agents/runtime/local.py`) — the single live exec-allow surface (INV-12) | 10 | `ExecutionPolicy\.check` | ☑ | |
| IN-02 | `local.py exec_command subprocess.run(command, shell=True)` (the Phase 9 review IN-02 shell-injection exec surface, `app/agents/runtime/local.py:190`) | argv-list `shell=False` spawn (10-01 hardened `exec_command`: argv list, `start_new_session`, scrubbed env, rlimits, timeout) — `app/agents/runtime/local.py` | 10 | `shell=True` | ☑ | |

> The ledger is the single source of truth for "what still needs refactoring." CI fails if any
> `☑` item's grep pattern reappears in `backend/`. Rows flip to `☑` only in their owning phase
> (L14 in Phase 0B; L16 CHECK in 0B via the 02-03 denial test; **D1 deferred — `_handle_revision`
> is live, not dead ‡**; L13 in 0C→2; L1–L12 in Phase 2/7; L15 in 1B; F1–F5 in Phase 3).
>
> ‡ **Phase 0B execution finding (2026-06-07):** D1 assumed `_handle_revision` was dead code
> superseded by the inline `prototype_revision` path. Execution found it is the **live handler for
> the frontend `run_revision` PPT-revision message** (`frontend/src/components/layout/DashboardLayout.tsx`
> → `app/api/websocket.py:625` → `engine.py::_handle_revision`), with a dedicated
> `backend/tests/unit/test_revision_intelligence.py` suite. The inline `prototype_revision` pipeline
> (which the 0A snapshots characterize) is a **separate** mechanism — the spec conflated the two.
> Deleting `_handle_revision` would break PPT revision (a CTX-05 behavior change), so the D1 deletion
> is **voided/deferred** pending a product decision on retiring `run_revision`. L14 still flips to `☑`
> (the state-lift is genuinely complete). See `.planning/phases/02-executioncontext-ownership-0b/02-02-SUMMARY.md`.
