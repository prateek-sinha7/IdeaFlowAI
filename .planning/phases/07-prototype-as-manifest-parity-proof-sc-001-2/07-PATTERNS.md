# Phase 7: Prototype as Manifest — Parity Proof (SC-001) - Pattern Map

**Mapped:** 2026-06-08
**Files analyzed:** 26 (15 new modules/tests + 11 modified)
**Analogs found:** 26 / 26 (every new file has a live in-codebase source — this is a relocation phase, not a greenfield one)

> **Phase-level insight (from RESEARCH "Key insight"):** Phase 7 is **relocation, not reimplementation.** Almost every behavioral unit already exists as a pure helper or an engine method. The analog for nearly every new file is a specific region of `engine.py` (move-don't-copy, INV-12) plus the matching `base.py` Protocol port it must satisfy structurally. The risk is in the *wiring seams* (the D-03 runner handle + the D-02 resolve seam), not in inventing logic. Concrete excerpts below.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `capabilities/strategies/single_shot.py` | strategy (capability) | request-response | `engine.py:1262-1269` `_run_agent` dispatch (else branch) + `base.py:42-50` `ExecutionStrategy` port | exact (behavior lift) |
| `capabilities/strategies/task_loop.py` | strategy (capability) | event-driven loop | `engine.py:1254-1261` build dispatch + `_run_build_task_loop`(~2072) / `_run_validation_fix_loop`(2370) / pure helpers `2318-2368`,`274-360` | exact (behavior lift) |
| `capabilities/deliverables/single_file.py` | deliverable resolver | file-I/O | `engine.py:489-518` (`_resolve_final_output` prototype + revision branches) + `base.py:64-72` | exact |
| `capabilities/deliverables/serialized_sandbox.py` | deliverable resolver | file-I/O | `engine.py:520-525` (`count_sandbox_deliverables`/`serialize_sandbox_deliverable`) | exact |
| `capabilities/deliverables/streamed_text.py` | deliverable resolver | transform | `engine.py:527-528` (`_unwrap_artifact(last_streamed)`) | exact |
| `capabilities/deliverables/ppt.py` | deliverable resolver | transform | `engine.py:1394` + `:1916` `_sanitize_carousel_deck_html` + `:363,427` `_unwrap_artifact` | exact (TWO sites — Pitfall 3) |
| `capabilities/context_providers/opendesign.py` | context provider | file-I/O + transform | `agents/prototype/context.py` (3 fns) + `engine.py:3306-3386` L12 od/template/example injection + `base.py:75-83` | exact (physical move, D-04) |
| `capabilities/context_providers/previous_run.py` | context provider | CRUD (parent-run read) | `engine.py:862-922` revision seeding (L4) + Phase-5 `ScopedStore`/`assert_owns` | role-match |
| `capabilities/task_parsers/heading_tasks.py` | task parser (pure) | transform | `engine.py:2318-2344` `_count_plan_tasks` + `2346-2368` `_extract_task_block` + `base.py:27-39` | exact (pure lift) |
| `capabilities/compaction/html_skeleton.py` | compaction (pure) | transform | `engine.py:3514-3577` `_extract_html_skeleton` (pure) | exact (verbatim lift) |
| `registry.py` (MODIFY) | registry seam | lookup | self: `_KNOWN` + `is_registered` (:37-66) — extend with impl map + `resolve()` + `install()` | self-extension |
| `execution_engine/context.py` (MODIFY) | data container | n/a | self: `scoped_store`/`model_resolver` `object`-typed precedent (:82,90) | **self — exact template (D-03)** |
| `execution_engine/engine.py` (MODIFY) | kernel sequencer | dispatch | self: per-step dispatch :1254-1269; delete L1–L13 | self-rewire + delete |
| `execution_engine/od_context.py` (MODIFY) | boundary loader | re-export | self: :19 re-export of `load_prototype_context` (rewire to new home) | self-rewire |
| `tests/agents/test_strategies.py` (NEW) | test | n/a | `tests/agents/test_phase4_build_loop.py` | role-match |
| `tests/agents/test_deliverable_resolvers.py` (NEW) | test | n/a | `tests/agents/test_sandbox_deliverable.py` | role-match |
| `tests/agents/test_context_providers.py` (NEW) | test | n/a | `tests/agents/test_phase3_compaction.py` (direct-call style) | role-match |
| `tests/agents/test_heading_tasks_parser.py` (NEW) | test | n/a | `tests/agents/test_phase4_build_loop.py` (`_count_plan_tasks` cases) | role-match |
| `tests/agents/test_capability_resolution.py` (NEW) | test | n/a | `tests/agents/test_registry_capabilities.py` (asserts membership; extend with resolve) | role-match |
| `tests/agents/test_phase3_compaction.py` (MODIFY) | test | n/a | self — re-point `engine._extract_html_skeleton` → `html_skeleton` capability | self-rewire |
| `tests/agents/test_manifest_parity.py:26` (MODIFY) | test | n/a | self — drop `SKIP_PLANNER_FOR_PROTOTYPE` import (pipeline.py deleted) | self-rewire |
| `tests/agents/_scripted_model.py:425` (MODIFY) | test harness | n/a | self — `ALWAYS_CLARIFY` monkeypatch breaks when L6 deletes | self-rewire |

## Pattern Assignments

### `execution_engine/context.py` (MODIFY — the D-03 runner handle) — HIGHEST VALUE

**Analog:** self. The `scoped_store` / `model_resolver` `object`-typed per-run helper fields (Phase 5/6). The D-03 runner handle MUST follow this EXACT pattern — the import-linter forbids `agents.capabilities` from importing `agents.execution_engine`/`app` (verified `pyproject.toml:165-169`), so a capability cannot type against `ExecutionContext` and the handle must be `object`-typed.

**The template to copy** (`context.py:76-90`):
```python
# scoped_store: ... Typed ``object | None`` (NOT the concrete type) so this
#   pure-data module stays free of the helper's ``app.models`` import ...
scoped_store: object | None = None
# model_resolver: ... Typed ``object | None`` (NOT the concrete type) — IDENTICAL
#   to ``scoped_store`` above — so this pure-data module gains no inbound import ...
model_resolver: object | None = None
```

**New field to add (recommended — RESEARCH Open Q1: one field, many methods):**
```python
# runner: the KernelServices handle (run_agent primitive + sandbox + static/render_check).
# Typed ``object | None`` — IDENTICAL to scoped_store/model_resolver — so context.py stays
# import-pure (the impl lives under the kernel; capabilities reach it dynamically via ctx).
runner: object | None = None
```

**Import-direction docstring to preserve** (`context.py:25-31`): "...never `agents.factory`, never `app.models`/`app.api`, never any engine internals — so the import-linter kernel→ports scaffold stays green." Keeping the handle `object`-typed preserves this.

**`current_task_block` reclaim (D-03):** `context.py:115-125` holds `current_task_block` / `build_task_number` / `build_task_total` (Phase-2 D-02 temp home). Move these into `TaskLoopStrategy` local state. **Do NOT re-add `self._current_task_block` to the engine** (L14 ratchet bans `self\._...current_task_block` — Pitfall 6). Removing the `ExecutionContext` fields is optional/inert (they are `ectx.current_task_block`, not `self._`).

---

### `registry.py` (MODIFY — the D-02 resolution seam)

**Analog:** self. Extend the name-only `CapabilityRegistry` (`_KNOWN` at :37-53, `is_registered` at :64-66) with a `(kind,name)→impl` map + `resolve()`. Keep `resolve_alias` (:68-74) untouched.

**Membership pattern to extend** (`registry.py:64-66`):
```python
def is_registered(self, kind: str, name: str) -> bool:
    """Return ``True`` iff ``(kind, name)`` is a known capability."""
    return (kind, name) in _KNOWN
```

**Recommended `resolve` shape (RESEARCH Open Q2):** `resolve(kind,name)` asserts `(kind,name) in _KNOWN` AND looks up a separate impl map (a known name with no impl is a programmer error → raise). The compiler only calls `is_registered` (membership over `_KNOWN`) — keep that path untouched. Populate the impl map via an explicit `install()`/`_register_builtins()` that imports the capability modules and binds each instance — **NOT `@register`/`discover()`** (Phase 8). Invoke `install()` lazily at engine import or first `execute()`, NOT at compiler import, so `test_registry_capabilities.py` (asserts no impls at Phase-4 import) stays honest.

**Singleton scope note (D-02):** registry stays a module-level singleton (capabilities are stateless); per-run state stays on `ExecutionContext`.

---

### `capabilities/strategies/single_shot.py` (strategy, request-response)

**Analog:** `engine.py:1262-1269` (the `else` branch — run one agent, yield events) + the `ExecutionStrategy` port `base.py:42-50`.

**Port to satisfy structurally** (`base.py:42-50`):
```python
@runtime_checkable
class ExecutionStrategy(Protocol):
    name: str
    def run(self, step: Any, ctx: Any) -> AsyncIterator[dict]:
        """Drive one step, yielding the engine's event dicts."""
        ...
```

**Behavior to reproduce** (`engine.py:1262-1269`) — call the run-agent primitive once, re-yield its event dicts (WS vocabulary unchanged, INV-3 — RESEARCH Pattern 2). `single_shot` is the trivial one-agent case the non-build steps (specify/plan/validate/ppt) use today. Invoke `_run_agent` THROUGH the D-03 handle (`ctx.runner`), never by importing the engine. Keep `ctx` typed `Any`/`object` (Pitfall 4).

---

### `capabilities/strategies/task_loop.py` (strategy, event-driven loop) — backbone

**Analog:** `engine.py:1254-1261` (build dispatch) + `_run_build_task_loop`(~2072) + `_run_validation_fix_loop`(2370) + the pure helpers.

**Dispatch this replaces** (`engine.py:1254-1261`) — the `if getattr(spec, "id", None) == "prototype-build":` branch (L7-adjacent) is DELETED; the kernel keeps only `resolve("strategy", step.strategy).run(step, ctx)` (no `spec.id`/`pipeline_type` branch, INV-1).

**`task_loop.run` owns** (D-03): parse tasks via `heading_tasks`; per-task sub-agent invocation through `ctx.runner.run_agent(...)`; per-task `html_skeleton` compaction (task-2+); Both-validation (`static_check`+`render_check` via the handle) + bounded **N=2** fix-loop; `seed_files` write (`_write_build_reference_files` logic, `engine.py:~2300-2316`, since manifests are `seed_files: {}` — Pitfall 2). Reclaim `current_task_block`/`build_task_number`/`build_task_total` here as strategy-local scratch.

**Pure helpers to MOVE WITH the strategy (do not rewrite — RESEARCH "Don't Hand-Roll"):** `_static_issue_sigs`/`_console_sigs`/`_select_issues_to_fix` (`engine.py:274-360`) — the byte-identical fix-message wording for build AND revision.

**Handle requirement** (RESEARCH Open Q1 / Assumption A1): inventory every `self.<method>` call inside `_run_build_task_loop`/`_run_validation_fix_loop`/`_run_agent` in the first plan; expose each on the `KernelServices` handle. `_run_agent` thread-id shape to preserve (`engine.py:1657-1667`): `f"{run_id}:{spec.id}:{task_num}"` (build) vs `f"{run_id}:{spec.id}"`.

---

### `capabilities/task_parsers/heading_tasks.py` (parser, pure)

**Analog:** `engine.py:2318-2344` `_count_plan_tasks` + `:2346-2368` `_extract_task_block` (pure staticmethods, already unit-tested) + `base.py:27-39` `TaskParser` port (`def parse(self, text) -> list[Any]`).

**Core regex to lift verbatim** (`engine.py:2337-2343`):
```python
text = plan_output or ""
task_matches = re.findall(r"^##\s+Task\s+(\d+)", text, re.MULTILINE)
task_source = text
if not task_matches:
    tasks_section = re.search(r"<tasks>([\s\S]*?)</tasks>", text, re.IGNORECASE)
    if tasks_section:
        task_source = tasks_section.group(1)
        task_matches = re.findall(r"^##\s+Task\s+(\d+)", task_source, re.MULTILINE)
```
The `<tasks>` fallback + `## Task N:` semantics are load-bearing. `parse()` returns `list[Task]` (`plan.Task` — importing `agents.workflows.plan` from a capability is ALLOWED; only `execution_engine`+`app` are forbidden — Pitfall 4). `_extract_task_block` block-slicing (:2364-2368) builds each `Task.body`.

---

### `capabilities/compaction/html_skeleton.py` (compaction, pure)

**Analog:** `engine.py:3514-3577` `_extract_html_skeleton` — a pure function (no engine state). **Clean verbatim lift.** The 0C ≥50% reduction gate is calibrated to its EXACT output (PARITY-04); do not alter the algorithm. The body builds `:root` tokens, routes map, filled/empty section scan, chrome summary, total-size line — copy lines 3526-3577 unchanged. Re-point `test_phase3_compaction.py` (7 tests call `engine._extract_html_skeleton` directly) at this capability.

---

### `capabilities/deliverables/single_file.py` (resolver, file-I/O)

**Analog:** `engine.py:489-518` (`_resolve_final_output` prototype + revision branches) + `base.py:64-72` `DeliverableResolver` (`def resolve(self, ctx) -> Any`).

**Behavior to fold (no pipeline_type branch):** read `deliverable.name` (`"prototype.html"`) from the sandbox via the handle; fall back to last-streamed / `previous_run`-seeded original. The revision branch (:489-504) folds into `single_file` via `deliverable.name` + the `previous_run`-seeded original — no `pipeline_type == "prototype_revision"` branch (that is L4/L8, deleted). Also absorbs the L10 readback (`engine.py:1902`, the `if pipeline_type in ("od_prototype","prototype")` readback) — Pitfall 5.

```python
# single_file:  sandbox.read(deliverable.name or "prototype.html"); fallback last_streamed
```

---

### `capabilities/deliverables/serialized_sandbox.py` (resolver, file-I/O)

**Analog:** `engine.py:520-525`:
```python
if count_sandbox_deliverables(sandbox.root) > 0:
    return serialize_sandbox_deliverable(sandbox.root)
```
Reach `count_sandbox_deliverables` / `serialize_sandbox_deliverable` (`app/agents/sandbox.py`) via the handle — NOT a direct `app.*` import (Pitfall 4). The `filename:`-block format is the UI contract; do not reformat.

---

### `capabilities/deliverables/streamed_text.py` (resolver, transform)

**Analog:** `engine.py:527-528`:
```python
# Text / PPT: the streamed output IS the deliverable; unwrap an <artifact> tag.
return _unwrap_artifact(last_streamed)
```
Move `_unwrap_artifact` (`engine.py:427`) into / alongside this resolver (shared by `ppt`). `last_streamed = results[-1]["output"]` (:487) — sourced from `ctx`.

---

### `capabilities/deliverables/ppt.py` (resolver, transform)

**Analog:** `streamed_text` behavior + `_sanitize_carousel_deck_html` (`engine.py:363`) + `_unwrap_artifact` (`engine.py:427`). **TWO sanitize call sites must both move (Pitfall 3 / PARITY-07):** the final-output sanitize (`engine.py:1394`) AND the mid-stream sanitize in `_run_agent` (`engine.py:1916`, currently gated by `pipeline_type in _PPT_PIPELINE_TYPES` — that gate is L3, deleted). The `ppt` resolver owns the carousel-sanitize + artifact-unwrap transform; verify L3 grep returns 0 across `agents/execution_engine/`.

---

### `capabilities/context_providers/opendesign.py` (provider, file-I/O + transform) — D-04 move

**Analog:** `agents/prototype/context.py` (the 3 LIVE functions) + `base.py:75-83` `ContextProvider` (`async def load(self, ctx) -> dict[str, str]`).

**Physically relocate (move-don't-copy, NOT wrap — INV-12 anti-pattern):** `load_prototype_context` (`context.py:26-93`), `get_template_injection_parts` (`context.py:96-125`), `get_example_html` (`context.py:128-145`). These depend on `app.services.od_loader` — heavy dep; the provider's `load(ctx)` composes the `{block-name → content}` map the L12 branches inject today (`engine.py:3306-3386`).

**Output contract** (RESEARCH "opendesign provider output contract"):
```python
# opendesign.load(ctx) -> {block_name -> content}, e.g.:
#   "ACTIVE DESIGN SYSTEM: <ds_id>"   -> ds_body
#   "ACTIVE TEMPLATE (SKILL.md): <id>" -> template_body
#   "TEMPLATE EXAMPLE (example.html): <id>" -> example[:8000]
#   + get_template_injection_parts(template_id) blocks
```

**Importer rewires (all four — D-04):** `od_context.py:19` (re-export — keep re-exporting from the new home OR repoint the boundary at `capabilities.context_providers.opendesign`; the boundary at `ndjson_adapter.py:25` + `websocket.py:1042/1059` builds `od_context` and passes it into `execute()` — Assumption A6, keep boundary call path); `engine.py:3373`, `:3384` (`get_template_injection_parts`); `engine.py:3508` (`get_example_html`). **`load_ppt_od_context` (`od_context.py:24-76`) STAYS** — only the prototype loaders re-home; do not delete `od_context.py` wholesale. After relocation `agents/prototype/` retains only the emptied `context.py` + dead `pipeline.py` + `__init__.py` → remove the package once empty.

**Heavy-dep note:** if `od_loader` disk reads cannot be reached without importing `app.*` from the capability, ride them through the boundary `od_context` dict (the provider composes blocks FROM the pre-built `od_context`, not by importing `od_loader` itself) — Assumption A6.

---

### `capabilities/context_providers/previous_run.py` (provider, CRUD)

**Analog:** `engine.py:862-922` revision parent-run seeding (L4) + Phase-5 `ScopedStore`/`assert_owns`. Seeds the parent run's spec/design/tasks into this run's sandbox (revision), **ownership-checked via `assert_owns`** (INV-8 — L16 re-verify, `test_parent_run_ownership.py`). `seed_files.from_run` is declared surface the provider honors; for parity, manifests stay `{}` and the behavior rides in the provider (Pitfall 2).

---

## Shared Patterns

### The runner handle (D-03 backbone — applies to BOTH strategies + ALL resolvers/providers reaching kernel/`app.*`)
**Source:** `execution_engine/context.py:82,90` (`object`-typed precedent).
**Apply to:** every capability that needs `_run_agent`, the sandbox, `static_check`, `render_check`, `count_sandbox_deliverables`, `serialize_sandbox_deliverable`. They reach these through `ctx.runner` (`object`-typed), NEVER by importing `agents.execution_engine` or `app.*`.
```python
scoped_store: object | None = None      # the proven pattern to copy
model_resolver: object | None = None
# runner: object | None = None          # add — KernelServices handle (D-03)
```

### Strategy/resolver typing (import-linter — applies to ALL capability modules)
**Source:** `base.py:24` (ports use `Any`) + `pyproject.toml:165-169` (forbidden: `execution_engine`, `app`).
**Apply to:** every `capabilities/**/*.py`.
- `ctx` parameter: keep `Any`/`object`; access attributes dynamically (no `ExecutionContext` import).
- `step`/`task`: MAY import `agents.workflows.plan` (`Step`/`Task`/`CompiledWorkflow`/`DeliverableSpec`/`TaskSource`) — `agents.workflows` is NOT forbidden.
- NEVER import `agents.execution_engine.*` or `app.*`. Run `lint_imports` after every module lands (Pitfall 4).

### Capability identity (one-name-everywhere, §32)
**Source:** `registry.py:37-53` (`_KNOWN` pairs).
**Apply to:** every impl module — `name` attribute == registry key == manifest reference, snake_case. e.g. `class TaskLoopStrategy: name = "task_loop"`.

### Yield-the-engine's-event-dicts (WS parity, INV-3)
**Source:** `engine.py:1255-1269` (`async for event in ...: yield event`) + `base.py:48`.
**Apply to:** both strategies. `run()` is an async generator yielding the SAME `{"type","data"}` dicts so the `execute()` seq-stamping chokepoint is untouched.

### Move-don't-copy / deletion-is-DoD (INV-12, §31)
**Source:** the migration-ledger ratchet (`test_migration_ledger.py`) + banned-pattern gate (`test_banned_patterns.py`).
**Apply to:** every leak (L1–L13). A capability that doesn't delete its kernel leak is NOT done. `vulture` confirms leaks orphaned in 07-04 before 07-05 deletes them. **PARITY-08 scoping:** rewrite `spec.id == ordered_agents[0].id` (`engine.py:3264`, a positional NOT a name branch) to `index == 0` so the kernel-scoped `grep -rnE 'if pipeline_type|spec\.id ==' agents/execution_engine/` cleanly hits 0 (Pitfall 1).

## No Analog Found

None. Every new file has a concrete live source region in the codebase (relocation phase). The only "newness" is the wiring shape of the D-02 resolve seam and the D-03 runner handle — and both have direct in-codebase templates (`registry.is_registered`/`_KNOWN` and `context.scoped_store`/`model_resolver` respectively).

## Metadata

**Analog search scope:** `backend/agents/capabilities/`, `backend/agents/execution_engine/`, `backend/agents/prototype/`, `backend/agents/workflows/`, `backend/app/agents/`, `backend/tests/agents/`, `backend/pyproject.toml`.
**Files scanned (read or grepped):** `base.py`, `registry.py`, `context.py`, `engine.py` (regions 447-528, 1250-1274, 2300-2368, 3514-3577), `prototype/context.py`, `od_context.py`, `workflows/plan.py`, `capabilities/__init__.py`, `pyproject.toml`, `CLAUDE.md` (backend).
**Pattern extraction date:** 2026-06-08

## PATTERN MAPPING COMPLETE

**Phase:** 07 - prototype-as-manifest-parity-proof-sc-001-2
**Files classified:** 26 (15 new, 11 modified)
**Analogs found:** 26 / 26

### Coverage
- Files with exact analog (behavior lift / self-extension): 14
- Files with role-match analog (tests + previous_run provider): 12
- Files with no analog: 0

### Key Patterns Identified
- **D-03 runner handle = the `object`-typed per-run field pattern** (`context.py:82,90` `scoped_store`/`model_resolver`) — the single load-bearing template; the handle MUST be `object`-typed so capabilities never import the kernel (`pyproject.toml:165-169`).
- **Every capability is a move, not a build** — strategies/resolvers/parser/compaction lift named regions of `engine.py` verbatim (pure helpers `274-360`, `2318-2368`, `3514-3577`; `_resolve_final_output` `447-528`); `opendesign` physically relocates `prototype/context.py`'s 3 fns (INV-12 move-don't-copy, no wrapper).
- **D-02 resolve seam extends `_KNOWN`/`is_registered`** — add a `(kind,name)→impl` map + `resolve()` + explicit `install()`; compiler's membership path (`is_registered`) untouched; no `@register`/`discover()` (Phase 8).
- **Three parity traps confirmed live (do NOT "fix"):** `planner: run` (not skip); revision clarify.defaults fall to `custom`; all manifests `seed_files: {}` (seeding rides in strategy/provider).
- **Two carousel-sanitize sites (Pitfall 3) + positional `spec.id ==` false-match (Pitfall 1)** are the non-obvious deletion gotchas for 07-05.

### File Created
`.planning/phases/07-prototype-as-manifest-parity-proof-sc-001-2/07-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can reference analog regions (file:line) directly in each plan's action section.
