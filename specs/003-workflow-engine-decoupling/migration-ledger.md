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
> enforced via the **L7** and **L10** rows (hard-fail in Phase 7 when those rows flip to `☑`).
> In Phase 1 it is **warn-only / documented** — see the banned-pattern gate wired in 01-04.

## Migration & deletion ledger

> `☐` pending · `☑` done — updated (status + deleting commit SHA) as phases land, like the
> decision log. `L#` = engine leak (§4); `F#` = factory/runtime; `D#` = dead code. The
> **Deleting SHA** is left blank for `☐` rows and filled when a row flips to `☑`.

| Item | Legacy (`file:line`) | New home | Phase | Deletion gate (grep → 0 / check) | Status | Deleting SHA |
|---|---|---|---|---|---|---|
| L14 | `self._od_context/_completed_tasks/_current_task_block/_revision_*/_gate_agent_ids` (engine, throughout) | `ExecutionContext` (§6) | 0B | `self\._(od_context\|completed_tasks\|current_task_block\|revision_\|gate_agent_ids)` | ☑ | 8b90fd2 |
| L16 | unchecked `parent_run` seed `engine.py:583-610` | authz store check (§19) | 0B | CHECK: cross-owner denial test passes (tests/agents/test_parent_run_ownership.py) | ☑ | |
| D1 | `_handle_revision` `engine.py:2156` — **LIVE, not dead**: the frontend `run_revision` PPT-revision handler (`DashboardLayout.tsx` → `app/api/websocket.py:625`) | retain (revisit only if `run_revision` is retired) | (deferred ‡) | CHECK: voided in 0B — live `run_revision` handler, not dead code | ☐ | |
| L13 | `_extract_html_skeleton` wired inline in 0C `engine.py:2565` | `CompactionStrategy(html_skeleton)` (§30) | 0C→2 | `_extract_html_skeleton` | ☐ | |
| L1 | `_PPT_PIPELINE_TYPES`/`_PROTOTYPE_PIPELINE_TYPES`/`REVISION_FILE_NAME` `engine.py:93-110` | manifest `deliverable`/`seed_files` | 2 | `_PROTOTYPE_PIPELINE_TYPES\|_PPT_PIPELINE_TYPES` | ☐ | |
| L2/L9 | `_resolve_final_output` `engine.py:316-397` | `DeliverableResolver` registry | 2 | `_resolve_final_output` | ☐ | |
| L3 | `_sanitize_carousel_deck_html`/`_unwrap_artifact` `engine.py:232-313` | `ppt` resolver/transform capability | 2 | `_sanitize_carousel_deck_html\|_unwrap_artifact` | ☐ | |
| L4/L8 | `prototype_revision` seeding + post-fix `engine.py:519-650,917-962` | `seed_files.from_run` + `previous_run` provider + `validation` gate | 2 | `prototype_revision` | ☐ | |
| L5 | `SKIP_PLANNER_FOR_PROTOTYPE` `engine.py:704-712` | manifest `planner` | 2 | `SKIP_PLANNER_FOR_PROTOTYPE` | ☐ | |
| L6 | `ALWAYS_CLARIFY` defaults dict `engine.py:733-743` | manifest `clarify.defaults` | 2 | `ALWAYS_CLARIFY` | ☐ | |
| L7 | `spec.id == "prototype-build"` dispatch `engine.py:872` | `strategy: task_loop` (§8/§9) | 2 | `spec\.id == "prototype-build"` | ☐ | |
| L10 | `pipeline_type in ("od_prototype","prototype")` HTML readback `engine.py:1328-1335` | `task_loop` reads `deliverable.name` | 2 | `pipeline_type in \("od_prototype", ?"prototype"\)` | ☐ | |
| L11 | build-loop internals `engine.py:1450-1704,2554-2563` | `TaskLoopStrategy`+`TaskParser`+validators+fix-loop+`seed_files` | 2 | `_run_build_task_loop\|_write_build_reference_files\|_count_plan_tasks\|_extract_task_block\|_run_validation_fix_loop\|_load_template_example` | ☐ | |
| L12 | `_build_context_message` od/ppt/build injection `engine.py:2378-2512` | `ContextProvider` + generic injector | 2 | `_build_context_message` | ☐ | |
| L15 | `accumulated_outputs: dict[str,str]` mirror (throughout) | `ArtifactGraph`/`ArtifactRef` (§17) | 1A→**1B (delete mirror)** | `accumulated_outputs` | ☐ | |
| F1 | prompt-assembly inline order `factory.py:174-255` | `PromptAssemblyPolicy` (§6/§30) | 3 | `blocks\.append` | ☐ | |
| F2 | `_build_runner_tools` closed switch `factory.py:384-446` | `tool_provider` registry (§30) | 3 | `_build_runner_tools` | ☐ | |
| F3 | inline skills/hooks injection `factory.py:220-245` | `skill_provider` / `hook_provider` (§30) | 3 | `_inject_skills\|_inject_hooks` | ☐ | |
| F4 | `_inject_constitution` async no-op `factory.py:258-306` (R12) | sync-safe load via `PromptAssemblyPolicy` | 3 | CHECK: constitution-injected-in-prod test passes | ☐ | |
| F5 | `create_deep_agent` hardcoded `deep_agent_runner.py:240` | `AgentRuntimeAdapter` (§6/§30) | 3 | CHECK: create_deep_agent called only inside the langchain_deepagents adapter | ☐ | |

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
