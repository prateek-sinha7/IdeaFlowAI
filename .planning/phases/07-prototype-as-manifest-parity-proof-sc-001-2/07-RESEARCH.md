# Phase 7: Prototype as Manifest — Parity Proof (SC-001) [2] — Research

**Researched:** 2026-06-08
**Domain:** Brownfield kernel refactor — capability-port implementation + leak deletion (Python / FastAPI / LangGraph deepagents runtime)
**Confidence:** HIGH (all findings grounded in the live codebase via direct read/grep, cross-checked against plan.md §6/§10/§11/§32 + the migration ledger)

## Summary

Phase 7 is a **parity-only, kernel-internal, additive** refactor: implement the 9 declared-but-empty capability families (`single_shot`/`task_loop` strategies, `single_file`/`serialized_sandbox`/`streamed_text`/`ppt` resolvers, `opendesign`/`previous_run` providers + a generic injector, `heading_tasks` parser, `html_skeleton` compaction) behind the existing `agents/capabilities/base.py` Protocol ports; add a thin `(kind,name)→impl` resolution seam over the existing name registry; wire `engine.py` to route every step's *behavior* through the resolved capability sourced from the `CompiledWorkflow`; then **delete kernel leaks L1–L13** (move-don't-copy, INV-12) so the kernel (`agents/execution_engine/`) contains zero `if pipeline_type`/`spec.id ==` workflow-by-name branches (INV-1) while all 5 pipelines stay at deliverable + semantic-event parity vs the post-0C baseline.

The deepest research risk (D-03) is the `task_loop`↔kernel coupling: the strategy must own the per-task sub-agent loop + validation + N=2 fix-loop, but it must reach the kernel's per-agent run primitive (`_run_agent`), the sandbox, and the heavy `static_check`/`render_check` (which live in `app/agents/` and the kernel must NOT import) — **and the import-linter contract `agents.capabilities must not import agents.execution_engine` is already live and will break the obvious "capability imports `ExecutionContext`" approach.** The narrow runner handle on `ExecutionContext` (typed `object`, the proven Phase 5/6 `scoped_store`/`model_resolver` pattern) is the load-bearing design that resolves both the import-linter direction and the `app.*` ban. I verify this contract below and recommend the handle shape.

**Primary recommendation:** Land the resolution seam + the `ExecutionContext` runner handle FIRST (07-00/07-01), build all capabilities against `Any`-typed ports so no impl imports the kernel (preserving the import-linter contract as-is), prove parity with the leaks still present-but-dead in 07-04, then delete L1–L13 + flip ledger/banned-pattern gates in 07-05. **Three parity traps are confirmed live and must not be "fixed":** (1) `planner: run` not `skip`; (2) `prototype_revision` clarify.defaults fall to `custom`; and (3) **all manifests declare `seed_files: {}`** — the seeding behavior must move into the strategy/`previous_run` provider, NOT into manifest data (do not re-author manifests).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 (Capability module layout, §32).** Adopt §32's subpackage tree under `agents/capabilities/`: `strategies/` (`single_shot.py`, `task_loop.py`), `deliverables/` (`single_file.py`, `serialized_sandbox.py`, `streamed_text.py`, `ppt.py`), `context_providers/` (`opendesign.py`, `previous_run.py`), `task_parsers/` (`heading_tasks.py`), `compaction/` (`html_skeleton.py`). One impl per module, snake_case `name` == registry key == manifest reference. Heavy-dep `static_check.py`/`render_check.py` stay in `app/agents/` and are called directly by `task_loop` (NOT wrapped as registered Validators — Phase 8). Kernel imports only `capabilities.base` ports + the resolution seam.

**D-02 (Name→impl resolution seam).** Extend `CapabilityRegistry` with a `(kind,name)→impl` map + `resolve(kind,name)`, populated by an explicit `install()/_register_builtins()`-style call (NOT `@register`/`discover()` — Phase 8). Registry stays a module-level singleton; per-run state stays on `ExecutionContext`.

**D-03 (task_loop↔kernel coupling — HIGH).** `ExecutionStrategy.run(step, ctx)` owns the step's run loop; the kernel's per-agent run primitive + sandbox are exposed to the strategy via a narrow runner handle on `ExecutionContext` (typed `object`, the Phase 5/6 pattern). `task_loop.run` owns: parse tasks (`heading_tasks`), per-task sub-agent invocation, per-task `html_skeleton` compaction (task-2+), Both-validation + bounded N=2 fix-loop. `single_shot.run` is the trivial one-agent case. Kernel keeps a thin per-step dispatch that looks up `step.strategy` via the resolver and delegates — no `spec.id`/`pipeline_type` branch. `current_task_block` (Phase-2 temp home on `ExecutionContext`) is reclaimed INTO `TaskLoopStrategy`.

**D-04 (opendesign re-homing, move-don't-copy).** Physically relocate `agents/prototype/context.py`'s 3 live functions (`load_prototype_context`, `get_template_injection_parts`, `get_example_html`) into `capabilities/context_providers/opendesign.py`; rewire all importers (`od_context.py:19`, `engine.py:3373/3384/3508`); drop `agents/prototype/`. `previous_run` provider seeds parent run spec/design/tasks (revision), ownership-checked via Phase-5 `ScopedStore`/`assert_owns` (INV-8).

**D-05 (Plan sequencing — strangler).** Follow ROADMAP 07-01..07-05; deletion is the FINAL plan, AFTER the engine routes through capabilities and parity is proven with L1–L13 still physically present but DEAD. L4/L8 revision seeding + L10 readback + L7 build dispatch are deleted only AFTER the manifest path is proven at parity in 07-04.

### Claude's Discretion
- Exact name/shape of the runner handle on `ExecutionContext` (`ctx.run_agent` callable vs a `KernelServices` dataclass); method signatures.
- Whether `install()` lives in `capabilities/registry.py`, a `capabilities/__init__.py` discover-lite, or is called from engine import — provided no `@register`/`discover()` and the compiler's name-validation path is unchanged.
- Whether `od_context.py` is rewired in place or relocated into the `opendesign` provider.
- The exact kernel-scoping mechanism for each L1–L13 grep gate (refine pattern vs `--include` path scope vs single-file allow-list).
- Plan-task granularity within the 5-plan frame (e.g. whether the resolution seam + runner handle land in 07-01 or a 07-00 scaffolding plan).
- Whether the §32 `engine.py`→`kernel.py` rename happens this phase (cosmetic; not required for parity/INV-1).
- Whether `previous_run` and `opendesign` share a base or are independent modules.

### Deferred Ideas (OUT OF SCOPE — Phase 8+)
- Self-registration (`@register`/`discover()`) + `user_allowed` trust flags + owner allow-list — Phase 8 (CAP-01/02).
- Formal `Validator` registry + generic fix-loop + P0–P3 severity mapping + Tier#4/5/6 validators + migrating `html_static`/`html_render` into the registry — Phase 8 (08-04).
- Formal `GateHandler` registry + first-class `Validation_Gate` (`human`/`validation`/`approval`/`security`) — Phase 8 (08-02).
- `fanout_batch`/`wave_scheduler` strategies — Phases 11/12. Only `single_shot` + `task_loop` this phase.
- `repo_diff` deliverable + `repo`/`uploaded_files`/`memory` context providers — Phases 9+.
- `json_tasks`/`bracket_p` task parsers — later (only `heading_tasks` needed for prototype parity).
- `engine.py`→`kernel.py` rename — cosmetic; planner's call.
- `PromptAssemblyPolicy`/`AgentRuntimeAdapter`/`ToolPermissions`/F1–F5 factory deletions — Phase 8.
- `_handle_revision`/`run_revision` PPT-revision handler — **D1 voided** (live handler); not touched.
- Non-kernel `pipeline_type`/name references (registry `REVISION_BASE_MAP`/`PIPELINE_AGENTS`, `app/core/entitlements.py`, `app/api/runs.py`, `app/api/websocket.py` display strings, tests) — retained; INV-1 is a kernel property.
- `agents/prototype/context.py` deletion — re-homed (live), not dropped.
- New DB table / schema migration — engine-internal + capability code, additive-only.
- New behavior — parity-only.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PARITY-01 | `single_shot` + `task_loop` ExecutionStrategy impls; engine routes every step through `step.strategy` (no spec.id/pipeline_type dispatch) | D-03 runner-handle design (below); `_run_agent` call-shape inventory; routing-vs-behavioral classification of the 6 kernel `pipeline_type`/`spec.id` sites; `single_shot` reproduces non-build path |
| PARITY-02 | `single_file`/`serialized_sandbox`/`streamed_text` DeliverableResolver impls; resolve via `deliverable.strategy`+`deliverable.name` | `_resolve_final_output` (engine.py:447) decomposed by class; sandbox `read`/`serialize_sandbox_deliverable`/`count_sandbox_deliverables` API; L10 readback (engine.py:1902) folds into `single_file`/task_loop |
| PARITY-03 | `opendesign`+`previous_run` providers + generic context injector + `seed_files` (incl. `from_run`) + `heading_tasks` parser | `_build_context_message` (engine.py:3243) per-pipeline branch map; `context.py` 3 fns + dependency surface; `_count_plan_tasks`/`_extract_task_block` heading logic; **seed_files trap (all manifests `{}`)** |
| PARITY-04 | `html_skeleton` CompactionStrategy re-expressing 0C; `task_loop` applies via `compaction:`; ≥50% reduction gate preserved | `_extract_html_skeleton` (engine.py:3514) is pure (no engine state) — clean lift; 0C gate is `test_phase3_compaction.py` (calls `engine._extract_html_skeleton` + `engine._build_context_message` directly — MUST be updated) |
| PARITY-05 | prototype/od_prototype/prototype_revision run purely from manifests | Manifests authored (verified); `compile_for_run` already produces the plan; routing wiring + leak deletion close the loop; od_prototype is alias→prototype |
| PARITY-06 | Delete L1–L13; drop dead `agents/prototype/pipeline.py`; update `test_manifest_parity.py` | Per-leak location map (below); `pipeline.py` is dead in live code (only `test_manifest_parity.py:26` imports `SKIP_PLANNER_FOR_PROTOTYPE`); ledger ratchet flips |
| PARITY-07 | `ppt` resolver + carousel-sanitize transform as declared capability (L3) | `_sanitize_carousel_deck_html`+`_unwrap_artifact` (engine.py:363,427); applied at :1394 AND :1916 (TWO sites — both must move) |
| PARITY-08 | Kernel zero name/id branches (INV-1); banned-pattern gate flips warn→hard-fail | `test_banned_patterns.py` scans `app`+`agents`; **6 kernel sites + 4 legit non-kernel sites + `spec.id == ordered_agents[0].id` positional false-match** — scoping analysis below |
| PARITY-09 | 5-pipeline deliverable + semantic-event parity vs post-0C baseline | Characterization harness `_drive()` + golden snapshots; `_normalize.py` multiset; re-baseline only if a sanctioned 0C-equivalent change |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Step run loop (`single_shot`/`task_loop`) | Kernel (capability impl) | — | The loop *is* the per-pipeline behavior that must leave the kernel (INV-1); impls live in `agents/capabilities/strategies/` |
| Per-agent run primitive (`_run_agent` + create_runner) | Kernel (`engine.py`) | — | Sequencer concern — stays in kernel; exposed to strategies via the runner handle (D-03), NOT relocated |
| Deliverable resolution | Kernel (capability impl) | Sandbox/disk | Resolvers read the per-run `RunSandbox` (`app/agents/sandbox.py`) via the handle; no kernel name-branch |
| Context injection (`opendesign`/`previous_run`/generic) | Kernel (capability impl) | `app/services/od_loader` (heavy) | Provider `load(ctx)` returns `{block→content}`; the heavy `od_loader` disk reads ride through the boundary `od_context` dict OR the handle |
| Task parsing (`heading_tasks`) | Kernel (capability impl, pure) | — | Pure text→`Task[]`; no I/O — trivially kernel-importable |
| Compaction (`html_skeleton`) | Kernel (capability impl, pure) | — | `_extract_html_skeleton` is already a pure function — clean lift |
| Validation (`static_check`/`render_check`) | `app/agents/` (heavy: Chromium/stdlib) | reached via handle | Kernel must NOT import `app.*`; `task_loop` calls them through the runner handle (Phase 7), formal Validators Phase 8 |
| Capability resolution | Kernel (`registry.py`) | — | `(kind,name)→impl` lookup; module-level singleton; no per-run state |
| WS event vocabulary | Kernel (`engine.py` boundary) | — | Strategies `yield` the engine's event dicts so the seq-stamping chokepoint (`execute()` wrapper) is unchanged (INV-3) |

## Standard Stack

This is a **brownfield, dependency-frozen** phase. No new packages. The stack is the existing one (CLAUDE.md: Python · FastAPI · PostgreSQL · LangGraph checkpointer; INV-13 deepagents `create_deep_agent`). Confirmed installed/in-use:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `deepagents` | `0.6.7` (pinned) | Agent runtime via `create_deep_agent` (INV-13) | Mandated; banned-pattern gate enforces single-adapter use [CITED: CLAUDE.md] |
| LangGraph checkpointer | (existing) | Per-agent-invocation graph state (`thread_id`) | Engine threads `<run>:<agent>[:task]` per invocation [VERIFIED: engine.py:1657] |
| `pytest` / `pytest-asyncio` | (existing) | Offline characterization + unit suites | Test cmd `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` [CITED: backend/CLAUDE.md] |
| `import-linter` | (existing, configured in pyproject) | Ports & Adapters boundary CI gate | Already live: `agents.capabilities` forbidden from `agents.execution_engine`+`app` [VERIFIED: pyproject.toml:165-169] |
| `vulture` | (existing) | Dead-code detection after leak deletion | Helps confirm L1–L13 helpers are truly orphaned [VERIFIED: pyproject.toml:193] |

### Supporting (no install — internal modules)
| Module | Purpose | When to Use |
|--------|---------|-------------|
| `agents/capabilities/base.py` | The 6 Protocol ports (impl targets) | Every capability impl satisfies its port structurally |
| `agents/capabilities/registry.py` | Name-only `CapabilityRegistry` + `_KNOWN` (15 pairs) + `resolve_alias` | The D-02 seam extends this |
| `agents/workflows/plan.py` | `Step`/`Task`/`CompiledWorkflow`/`DeliverableSpec`/`TaskSource`/`ClarifySpec` | The typed inputs strategies/resolvers consume |
| `agents/execution_engine/context.py` | `ExecutionContext` (per-run; `object`-typed handle fields) | Carries the D-03 runner handle + reclaimed scratch |
| `app/agents/sandbox.py` | `RunSandbox` (`read`/`write`/`path_for`) + `serialize_sandbox_deliverable` + `count_sandbox_deliverables` | The deliverable resolvers + task_loop read/write here |
| `app/agents/static_check.py` / `render_check.py` | Both-validation (stay in `app/agents/`) | `task_loop` calls inline via the handle |
| `app/services/od_loader` | Template/DS/craft disk loader | `opendesign` provider's dependency surface |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Runner handle on `ExecutionContext` (typed `object`) | Strategy imports `engine`/`_run_agent` directly | Breaks the import-linter `capabilities → no execution_engine` contract; rejected by D-03 |
| Capability impls typed against `plan.Step`/`Task` | Capability impls typed against `Any` (ports use `Any` today) | Importing `agents.workflows.plan` from `agents.capabilities` is **allowed** by import-linter (workflows is inner, capabilities may depend on it — verify below); but importing `ExecutionContext` is **forbidden**. Use `plan` types freely; keep `ctx` as `Any`/`object`. |
| Extend `CapabilityRegistry` with impl map | Separate parallel resolver module | Two sources of truth for `(kind,name)`; rejected by D-02 |

**Installation:** None. `pip` is frozen for this phase (additive-only, no new deps).

**Version verification:** No new packages to verify. `deepagents==0.6.7` is the pinned mandate (CLAUDE.md); INV-13 banned-pattern gate (`test_banned_patterns.py`) enforces `create_deep_agent` is imported only in `app/agents/deep_agent_runner.py` — no capability impl may import it.

## Package Legitimacy Audit

> Not applicable — Phase 7 installs **no external packages**. It is additive Python code inside the existing `backend/` tree plus deletions. slopcheck/registry verification is moot (zero new dependencies). All imports are first-party (`agents.*`, `app.*`) or already-vendored (`deepagents`, `langchain_core`, `pytest`). The relevant supply-chain gate is INV-13's banned-pattern ratchet, already in CI.

## Architecture Patterns

### System Architecture Diagram (target state, post-Phase-7)

```
WS run_pipeline / NDJSON  ──(od_context dict built at boundary via opendesign loader)──┐
        │                                                                              │
        ▼                                                                              │
ExecutionEngine.execute()  [seq-stamp chokepoint — UNCHANGED]                          │
        │                                                                              │
        ├─ compile_for_run(pipeline_type) ─► CompiledWorkflow  (Phase 4, unchanged)    │
        ├─ build ExecutionContext  ◄── od_context ─────────────────────────────────────┘
        │     └─ attach runner handle (D-03): run_agent primitive + sandbox + validators
        │
        ├─ planner/clarify   (planner=compiled.planner; clarify.defaults=compiled.clarify)
        │
        └─ for step in compiled.steps:                       ◄── NO if pipeline_type / spec.id
                 strategy = registry.resolve("strategy", step.strategy)   (D-02)
                 async for event in strategy.run(step, ctx):              (D-03)
                       yield event   ──────────────────────────────────► WS vocabulary unchanged
                       │
                       ├─ single_shot:  one create_runner(...) via ctx.run_agent → yield events
                       └─ task_loop:
                              ├─ parser = resolve("task_parser", step.task_source.parser).parse(tasks_md)
                              ├─ provider blocks ◄── resolve("context_provider", …).load(ctx)
                              ├─ per task: ctx.run_agent(...) → yield events
                              │      └─ task-2+: resolve("compaction", step.compaction).compact(html)
                              └─ after task: static_check + render_check (via handle) → N=2 fix-loop
        │
        └─ deliverable = registry.resolve("deliverable", compiled.deliverable.strategy)
                 .resolve(ctx)  ──► single_file reads deliverable.name from sandbox
                                    serialized_sandbox → filename: blocks
                                    streamed_text / ppt → last streamed (+ carousel sanitize)
                 yield pipeline_complete{final_output=...}
```

A reader traces a prototype build: `execute()` → compile → planner/clarify → for the `prototype-build` step, `resolve("strategy","task_loop").run()` → parse `tasks.md` via `heading_tasks` → per task call `ctx.run_agent` → compact task-2+ via `html_skeleton` → validate+fix → then `resolve("deliverable","single_file").resolve(ctx)` reads `prototype.html`.

### Recommended Project Structure (D-01, §32)
```
agents/capabilities/
├── base.py              # ports (exists)
├── registry.py          # +(kind,name)→impl map + resolve() + install()  (D-02)
├── __init__.py          # candidate home for install()/_register_builtins() (discretion)
├── model_catalog.py     # exists (Phase 6, flat — single data module)
├── strategies/
│   ├── single_shot.py
│   └── task_loop.py     # owns parse + per-task loop + compaction + validation/fix
├── deliverables/
│   ├── single_file.py
│   ├── serialized_sandbox.py
│   ├── streamed_text.py
│   └── ppt.py           # streamed_text read + carousel-sanitize transform
├── context_providers/
│   ├── opendesign.py    # re-homed context.py 3 fns + load(ctx)→{block→content}
│   └── previous_run.py  # parent-run spec/design/tasks seed (ownership-checked)
├── task_parsers/
│   └── heading_tasks.py # _count_plan_tasks + _extract_task_block logic → Task[]
└── compaction/
    └── html_skeleton.py # _extract_html_skeleton (pure lift)
```

### Pattern 1: Per-run helper on `ExecutionContext`, typed `object` (the D-03 backbone)
**What:** The kernel exposes services to capabilities by attaching them to `ExecutionContext` as `object`-typed fields, NOT by capabilities importing the kernel. Already proven twice.
**When to use:** Any kernel primitive a capability needs (run-agent, sandbox, validators).
**Example:**
```python
# Source: agents/execution_engine/context.py:82,90 (scoped_store + model_resolver precedent)
# scoped_store: ... Typed ``object | None`` (NOT the concrete type) so this pure-data
#   module stays free of the helper's ``app.models`` import ...
scoped_store: object | None = None
model_resolver: object | None = None
# Phase 7 adds (recommended):
# runner: object | None = None   # KernelServices handle: run_agent + sandbox + validators
```
The `context.py` import-direction docstring is explicit: *"never `agents.factory`, never `app.models`/`app.api`, never any engine internals — so the import-linter kernel→ports scaffold stays green."* Keeping the handle `object`-typed preserves this. [VERIFIED: context.py:25-31,76-90]

### Pattern 2: Strategy yields the engine's event dicts (WS-vocabulary parity)
**What:** `strategy.run(step, ctx)` is an `async` generator yielding the SAME `{"type","data"}` dicts the engine yields today, so the `execute()` seq-stamping chokepoint and the WS drainer are untouched (INV-3).
**Why:** The port is `def run(self, step, ctx) -> AsyncIterator[dict]` [VERIFIED: base.py:48]. The `execute()` per-step loop currently does `async for event in self._run_build_task_loop(...): yield event` [VERIFIED: engine.py:1255-1269] — the new dispatch swaps the call target to `strategy.run(...)`, identical yield contract.

### Pattern 3: Routing already sourced from `CompiledWorkflow` (Phase 4) — only behavior remains
**What:** Phase 4 already made the engine read step membership/order, deliverable spec, clarify defaults, and planner flag from `compiled` (see `compile_for_run` engine.py:223, the membership assertion engine.py:1047-1060, `skip_planner=compiled.planner=="skip"` engine.py:1082, `compiled.clarify.defaults` engine.py:1121, the deliverable log engine.py:1366). Phase 7 only needs to route the *behavioral* leaks. [VERIFIED: engine.py]

### Anti-Patterns to Avoid
- **Wrapping the old location instead of moving it.** A `opendesign.py` that imports `agents.prototype.context` is the exact dual-impl the ledger forbids (INV-12). Physically move the function bodies.
- **Re-authoring manifests to add `seed_files`.** All manifests are `seed_files: {}` (verified). The seeding behavior belongs in `task_loop`/`previous_run`, not in manifest data. Re-authoring would change the compiled plan and risk parity.
- **Typing `ctx` as `ExecutionContext` inside a capability module.** Forbidden by import-linter. Keep `ctx: Any`/`object`.
- **Importing `app.agents.static_check` from a capability module.** Forbidden (capabilities → no `app`). Reach validators through the runner handle.
- **Deleting `spec.id == ordered_agents[0].id`.** That is a *positional* first-agent check (engine.py:3264), not a workflow-name branch — but the banned-pattern regex `spec\.id ==` matches it. Plan the kernel-scoping of PARITY-08 to exclude it (see Pitfall 1).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Issue selection / fix-message wording | A new fix-loop normalizer | The existing pure module-level `_static_issue_sigs`/`_console_sigs`/`_select_issues_to_fix` (engine.py:274-360) | They are deliberately pure (no engine state) and are the single source of byte-identical fix wording for build AND revision; move them WITH `task_loop`, don't rewrite [VERIFIED: engine.py:244-360] |
| HTML skeleton extraction | A new compaction algorithm | Lift `_extract_html_skeleton` verbatim (engine.py:3514) | Pure function; the ≥50% gate is calibrated to its exact output |
| Task header parsing | A new regex | Lift `_count_plan_tasks` + `_extract_task_block` (engine.py:2318-2368) | Pure staticmethods; already unit-tested; the `<tasks>` fallback + `## Task N:` semantics are load-bearing |
| Template/DS/craft loading | A new loader | Move `load_prototype_context`/`get_template_injection_parts`/`get_example_html` (context.py) | Live, depend on `app.services.od_loader`; re-home not rewrite (D-04) |
| Sandbox deliverable serialization | A new serializer | `serialize_sandbox_deliverable` / `count_sandbox_deliverables` (app/agents/sandbox.py) | The `filename:`-block format is the UI contract |
| Agent invocation / model fallback / checkpointer threading | A new run loop | The existing `_run_agent` exposed via the handle | INV-13 + the MODEL-02 fallback chain + per-attempt thread-id logic is intricate and parity-critical; do not duplicate it inside a strategy |

**Key insight:** Phase 7 is **relocation, not reimplementation.** Almost every behavioral unit the capabilities need already exists as a pure helper or a method on the engine. The risk is in the *wiring* (the runner handle + resolution seam) and the *deletion discipline* (move-don't-copy), not in inventing logic.

## Runtime State Inventory

> This IS a refactor/relocation phase (move-don't-copy). The "runtime state" here is **import-graph + test-coupling state** that a grep audit of `engine.py` alone misses.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None** — no DB rows key off any L1–L13 symbol; `prototype.html`/`spec.md`/`design.md`/`tasks.md` live on the per-run `RunSandbox` disk (TTL-swept), referenced by *path string* not by leak constant. No migration. | code edit only |
| Live service config | **None** — no external service (n8n/Datadog/etc.) embeds these kernel symbols. The `od_context` dict is built per-request at the WS/NDJSON boundary, not stored. | none |
| OS-registered state | **None** — no Task Scheduler / pm2 / systemd registration references these symbols. | none |
| Secrets/env vars | **None reference the leaks.** `RUNS_ROOT` (sandbox root) is unaffected. The scripted-model harness sets `engine_mod.ALWAYS_CLARIFY = False` at runtime (`_scripted_model.py:425`) — when **L6 deletes `ALWAYS_CLARIFY`**, this monkeypatch line MUST be updated or it raises `AttributeError`. | code edit (test harness) |
| Build artifacts / installed packages | **`agents/prototype/` package removal** leaves `__init__.py`, `README.md`, the emptied `context.py`, and the deleted `pipeline.py`. After D-04 relocation the package is removed entirely. No egg-info/compiled artifact carries the name. The `__pycache__` for deleted modules will be stale — harmless (regenerated). | delete package |

**Cross-module import + test coupling (the real "runtime state" for this phase) — VERIFIED via grep:**

- **`agents/prototype/context.py` importers** (must all be rewired for D-04):
  - `agents/execution_engine/od_context.py:19` — `from agents.prototype.context import load_prototype_context as load_prototype_od_context` (re-export). This re-export is consumed by `ndjson_adapter.py:25` and `app/api/websocket.py:1042/1059` — i.e. the **boundary builds `od_context` and passes it into `execute()`**, so the `opendesign` provider's `load_prototype_context` must remain importable from wherever the boundary imports it (keep `od_context.py` re-exporting from the new home, OR repoint the boundary at `capabilities.context_providers.opendesign`).
  - `engine.py:3373`, `engine.py:3384` — `get_template_injection_parts` (inside L12 `_build_context_message`).
  - `engine.py:3508` — `get_example_html` (inside L11 `_load_template_example`).
- **`agents/prototype/pipeline.py` importers**: ONLY `tests/agents/test_manifest_parity.py:26` (`SKIP_PLANNER_FOR_PROTOTYPE`) + `agents/prototype/__init__.py:10` (docstring/example import of `get_prototype_agents`). No LIVE kernel importer — confirms it is dead (PARITY-06). Update both when deleting.
- **`_load_prototype_od_context` / `load_ppt_od_context`**: `od_context.py` ALSO contains `load_ppt_od_context` (PPT-specific, lines 24-76) which is live (`ndjson_adapter`/`websocket` build the PPT od_context). D-04 only re-homes the *prototype* loaders; **`load_ppt_od_context` stays** (or moves with care). Do not delete `od_context.py` wholesale.
- **Tests that call deleted engine methods DIRECTLY** (will break on deletion — must be updated/relocated):
  - `tests/agents/test_phase3_compaction.py` — calls `engine._extract_html_skeleton(...)` (L13) AND `engine._build_context_message(...)` (L12) directly, 7 tests. This is the **0C ≥50% reduction gate**. It must be re-pointed at the new `html_skeleton` CompactionStrategy + the generic injector / `task_loop` message assembly.
  - `tests/agents/test_phase4_build_loop.py`, `test_phase5_revision_validation.py` — exercise the build loop / fix-loop; verify whether they call `_run_build_task_loop`/`_run_validation_fix_loop` directly (likely) and update.
  - `tests/agents/test_manifest_parity.py:26` — imports `SKIP_PLANNER_FOR_PROTOTYPE` from the deleted `pipeline.py` (PARITY-06 explicitly calls this out).

**Nothing found** in stored-data, live-service-config, and OS-registered categories — verified by grep across `agents`/`app`/`tests` and by the additive-only/no-migration boundary.

## Common Pitfalls

### Pitfall 1: PARITY-08 banned-pattern scope catches legitimate non-kernel + positional matches
**What goes wrong:** Flipping `test_banned_patterns.py` to hard-fail `assert count == 0` over its current scan roots (`app` + `agents`) will FAIL even after L1–L13 are deleted, because the regex `if\s+pipeline_type\s*==|spec\.id\s*==` still matches legitimate sites.
**Why it happens (VERIFIED grep):** Current matches across `app`+`agents`:
- Kernel (delete): `engine.py:489,841,1302` (`pipeline_type == "prototype_revision"`, L4/L8); `engine.py:3264` (`spec.id == ordered_agents[0].id` — **positional, NOT a name branch**); `engine.py:3321,3404` (`spec.id == "prototype-build"`, L7/L11).
- Non-kernel (RETAIN — SPEC out-of-scope): `app/api/websocket.py:1056,1069,1082` (od_prototype/od_ppt display routing); `agents/registry.py:383` (`pipeline_type == "custom"`).
- Deleted this phase: `agents/prototype/pipeline.py:77`.
**How to avoid:** The gate must be **kernel-scoped** to `agents/execution_engine/` (per SPEC constraint + interview round 2) AND must NOT false-match the positional `spec.id == ordered_agents[0].id`. Three viable mechanisms (Claude's discretion): (a) scope the scan root to `agents/execution_engine/` and refine the regex to require a string/name literal RHS (e.g. `spec\.id == "` to exclude the positional `ordered_agents[0].id`); (b) keep the broad scan but add a single-file/single-line allow-list (the existing `_ALLOWED_CREATE_DEEP_AGENT` precedent in the same file); (c) split into a kernel hard-fail gate + a non-kernel informational count. **The acceptance grep in SPEC §9 is `grep -rnE 'if pipeline_type|spec\.id ==' agents/execution_engine/`** — note even that matches `spec.id == ordered_agents[0].id`; either rewrite that line to a non-`==` form (e.g. `ordered_agents and spec.id is ordered_agents[0].id` is fragile — prefer `index == 0`) or refine the gate pattern. **Recommend: change the is_first_agent check to `index == 0`** (the `index` param is already threaded into `_build_context_message`'s callers) so the positional `spec.id ==` disappears and the gate can be a clean kernel-scoped `assert 0`.
**Warning signs:** Gate red after 07-05 deletion with offenders pointing at websocket.py/registry.py/engine.py:3264.

### Pitfall 2: `seed_files: {}` in every manifest (the third parity trap)
**What goes wrong:** A planner reading §10's illustrative YAML assumes `seed_files` declares `spec.md`/`tasks.md`/`design.md` and builds `seed_files` materialization that reads from a populated manifest field — but the authored manifests are all `{}` (VERIFIED across all 15). Wiring seeding off `compiled.seed_files` would be a no-op and the build would lose its reference files → parity break.
**Why it happens:** The §10 YAML is illustrative; Phase 4 authored manifests faithfully to *current behavior*, where seeding is kernel code (`_write_build_reference_files` engine.py:2263, parent-run seeding engine.py:862-922), not manifest data.
**How to avoid:** Keep seeding behavior INSIDE the capabilities: `task_loop` writes `spec.md`/`design.md`/`tasks.md` (the `_write_build_reference_files` logic) before the per-task loop; `previous_run` provider seeds the parent run's files for revision. `seed_files.from_run` is *declared surface* the providers can honor, but for parity the manifests stay `{}` and the behavior rides in the strategy/provider. **Do not re-author manifests.**
**Warning signs:** Build loop produces no `design.md`/`spec.md`; prototype deliverable diverges from golden.

### Pitfall 3: The carousel sanitize is applied at TWO sites
**What goes wrong:** Moving only the final-output sanitize (engine.py:1394) into the `ppt` resolver leaves the mid-stream sanitize (engine.py:1916, inside `_run_agent` after reading PPT agent output) behind → L3 grep non-zero, and the stored/downstream artifact differs.
**Why it happens:** `_sanitize_carousel_deck_html` is called BOTH at `_resolve_final_output` post-processing (:1394) AND in `_run_agent` per-agent output capture (:1916, gated by `pipeline_type in _PPT_PIPELINE_TYPES`). The `_unwrap_artifact` is called inside `_resolve_final_output` (:504,528).
**How to avoid:** The `ppt` resolver owns the carousel-sanitize + artifact-unwrap transform; BOTH call sites must be removed from the kernel (the mid-stream one folds into the `ppt`/`streamed_text` resolver or the per-agent output handling moves into the strategy). Verify L3 grep returns 0 across `agents/execution_engine/`.
**Warning signs:** L3 ledger row red; od_ppt event/deliverable snapshot drift.

### Pitfall 4: `import-linter` allows `capabilities → workflows` but forbids `capabilities → execution_engine`
**What goes wrong:** Typing a capability against `ExecutionContext` (imported from `agents.execution_engine.context`) breaks the contract `agents.capabilities must not import the execution kernel` (pyproject.toml:165-169).
**Why it happens:** `ExecutionContext` lives UNDER `agents/execution_engine/`. The contract forbids `agents.capabilities` from importing `agents.execution_engine` (any submodule).
**How to avoid:** Capability impls may freely import `agents.workflows.plan` (`Step`/`Task`/`CompiledWorkflow`) — that is the inner workflows package, and `agents.capabilities` is NOT forbidden from importing `agents.workflows` (the only forbidden targets are `agents.execution_engine` + `app`). For the run context, keep the port signature `Any`/`object` (ports already use `Any`, base.py) and access ctx attributes dynamically (`getattr`) or via a small TYPE_CHECKING-only protocol that does NOT import the concrete class. **Run `python3.11 -m lint_imports` (or the project's import-linter invocation) after every capability module lands** to catch a stray import early.
**Warning signs:** import-linter contract `agents.capabilities must not import the execution kernel or the web layer` goes red.

### Pitfall 5: `_run_agent` reads `pipeline_type`/`spec.id` for L10 readback — must move WITH the strategy
**What goes wrong:** `_run_agent` (the per-agent primitive that stays in the kernel and is exposed via the handle) contains the L10 readback `if pipeline_type in ("od_prototype","prototype")` (engine.py:1902) and the mid-stream PPT sanitize (engine.py:1916). If these stay in `_run_agent`, the kernel still name-branches even though the strategy "owns" the loop.
**Why it happens:** `_run_agent` is BOTH the primitive the handle exposes AND currently carries behavioral name-branches.
**How to avoid:** Classify these as **behavioral** (D-09): the readback belongs in the deliverable resolution / `task_loop` (read `deliverable.name` from the sandbox), and the sanitize belongs in the `ppt` resolver. `_run_agent` must be reduced to a workflow-agnostic "run one agent, yield events, return output" primitive with NO `pipeline_type`/`spec.id` branch. The build-loop-specific bits in `_run_agent` (the `report_task_complete`→`task_progress`, `ectx.build_task_number` thread-id suffix, `ectx.completed_tasks` accumulation) are workflow-agnostic mechanics and may stay, but the name-branches must leave.
**Warning signs:** INV-1 grep finds `pipeline_type`/`spec.id` inside `_run_agent` after 07-05.

### Pitfall 6: `current_task_block` reclaim leaves `ExecutionContext` field referenced by L14 ratchet
**What goes wrong:** L14's grep pattern is `self\._(od_context|completed_tasks|current_task_block|revision_|gate_agent_ids)` (ledger:49) — that bans `self._current_task_block` (the OLD singleton field), already ☑. Reclaiming `current_task_block` into `TaskLoopStrategy` is fine, but **do not reintroduce `self._current_task_block`** on the engine, and removing the `ExecutionContext.current_task_block` field is optional (it is `ectx.current_task_block`, not `self._...`, so it does not match L14). The build counters `build_task_number`/`build_task_total` similarly move into the strategy.
**How to avoid:** Move task scratch to strategy-local state; leave `ExecutionContext` fields removable-or-inert; never re-add `self._*` per-run state to the engine (L14 ratchet stays green).
**Warning signs:** L14 grep non-zero (regression).

## Code Examples

### `_run_agent` call shape the build loop uses today (D-03 handle design input)
```python
# Source: engine.py:1657-1667 (thread-id + create_runner) and 1255-1269 (dispatch)
task_num = ectx.build_task_number or None
thread_id = (f"{pipeline_run_id}:{spec.id}:{task_num}" if task_num
             else f"{pipeline_run_id}:{spec.id}")
agent = create_runner(spec.id, ctx, thread_id=thread_id, checkpointer=ectx.checkpointer)
# ... astream_events loop yields chunk/usage/tool_call/tool_result → WS events ...

# The dispatch the strategy replaces (engine.py:1254-1269):
if getattr(spec, "id", None) == "prototype-build":          # ← L7-adjacent dispatch (DELETE)
    async for event in self._run_build_task_loop(spec, i, ordered_agents, ...): yield event
else:
    async for event in self._run_agent(spec, i, ordered_agents, ...): yield event
```
**Handle requirement:** the strategy needs to invoke "run agent `spec` at index `i`, with these task-scratch values, yielding events" — i.e. the handle wraps `_run_agent` (which internally does create_runner + astream + model-fallback + output-readback + dual-write). The simplest narrow handle is a callable `ctx.run_agent(spec, index, ordered_agents, sandbox, ..., ectx)` that returns the existing async generator. The strategy sets the task-scratch (`current_task_block`/`build_task_number`) on its own state and passes it through.

### Pure helpers that move WITH `task_loop` (do not rewrite)
```python
# Source: engine.py:2318-2344 — _count_plan_tasks (## Task N: + <tasks> fallback) → heading_tasks parser
# Source: engine.py:2346-2368 — _extract_task_block (slice one ## Task n: block)
# Source: engine.py:274-360  — _static_issue_sigs/_console_sigs/_select_issues_to_fix (fix wording)
# Source: engine.py:3514-3577 — _extract_html_skeleton (pure → html_skeleton CompactionStrategy)
```

### Deliverable resolution decomposition (PARITY-02, from `_resolve_final_output` engine.py:447-528)
```python
# single_file:        sandbox.read(deliverable.name or "prototype.html"); fallback last_streamed
# serialized_sandbox: count_sandbox_deliverables(sandbox.root) > 0 → serialize_sandbox_deliverable(root)
# streamed_text:      last_streamed, then _unwrap_artifact(...)
# ppt:                streamed_text + _sanitize_carousel_deck_html + _unwrap_artifact
# revision fallback (prototype_revision): read prototype.html, else streamed/original — folds into
#   single_file via deliverable.name + the previous_run-seeded original (no pipeline_type branch)
```

### `opendesign` provider output contract (PARITY-03, replacing L12 branches)
```python
# Source: engine.py:3306-3386 (the L12 od/template/example injection) + context.py (the loaders)
# opendesign.load(ctx) returns {block_name -> content}, e.g.:
#   "ACTIVE DESIGN SYSTEM: <ds_id>" -> "...ds_body..."
#   "ACTIVE TEMPLATE (SKILL.md): <id>" -> "...template_body..."
#   "TEMPLATE EXAMPLE (example.html): <id>" -> "...example[:8000]..."
#   plus get_template_injection_parts(template_id) blocks
# The generic injector composes these into the context message in declared order;
# the per-agent injects + build-task-2+ skip logic ride in the strategy/injector, not the kernel.
```

## State of the Art

| Old Approach (pre-Phase-7) | Current Approach (Phase 7 target) | When Changed | Impact |
|--------------------|------------------|--------------|--------|
| `if spec.id == "prototype-build"` build dispatch | `resolve("strategy", step.strategy).run(step, ctx)` | Phase 7 / 07-04 | Kernel knows no agent id (INV-1) |
| `_resolve_final_output(pipeline_type, ...)` chooser | `resolve("deliverable", compiled.deliverable.strategy).resolve(ctx)` | Phase 7 / 07-02 | Kernel knows no pipeline name |
| `_build_context_message` per-pipeline od/ppt/build branches | `ContextProvider.load()` + generic injector | Phase 7 / 07-02 | Injection is declarative |
| `_extract_html_skeleton` wired inline (0C) | `CompactionStrategy(html_skeleton)` via `compaction:` | Phase 7 / 07-03 | Compaction is a declared capability |
| Name-only registry (`is_registered`) | `(kind,name)→impl` + `resolve()` (explicit install) | Phase 7 / 07-01 | Behavior is a registry lookup |
| `CapabilityRegistry` impls Phase 8 (`@register`/`discover`) | Explicit `install()`; decorators DEFERRED to Phase 8 | — | Evolution not dual-impl (D-02) |

**Deprecated/outdated after this phase:**
- `agents/prototype/pipeline.py`: deleted (dead — only a test imports it).
- L1–L13 engine helpers/constants: deleted (move-don't-copy).
- The §10 illustrative `prototype/workflow.yaml` (with `planner: skip`, `seed_files: {spec.md,...}`): NEVER the source of truth — the authored manifest (`planner: run`, `seed_files: {}`) governs.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The narrow runner handle wrapping `_run_agent` is sufficient for `task_loop` (no other kernel internal needed beyond run-agent + sandbox + static/render_check). | D-03 / Patterns | If the strategy needs additional engine internals (e.g. `_dual_write_artifact`, `_latest_typed_content`, state-machine guards), the handle surface grows. **Planner should inventory all `self.`/engine-method calls inside `_run_build_task_loop` + `_run_validation_fix_loop` + `_run_agent` and include each on the handle.** MEDIUM risk — mitigated by reading those methods fully in 07-01. |
| A2 | Keeping `ctx` typed `Any`/`object` in capability modules fully satisfies the import-linter contract while letting impls use `plan.Step`/`Task`. | Pitfall 4 | If a future import-linter tightening forbids `capabilities → workflows`, the `plan` import breaks. Today it is allowed (only `execution_engine`+`app` are forbidden). LOW risk. |
| A3 | The 0C ≥50% reduction gate (`test_phase3_compaction.py`) can be re-pointed at the new `html_skeleton` capability + injector without re-baselining the golden deliverable. | PARITY-04 / Runtime State | If the message-assembly order changes byte-for-byte, the prototype event/deliverable golden could drift. Mitigated by lifting `_extract_html_skeleton` verbatim and preserving injection order. MEDIUM. |
| A4 | No DB row, external service, or OS registration references any L1–L13 symbol (so no data migration). | Runtime State Inventory | If a stored artifact path or config keys off a leak constant, deletion breaks it. Verified by grep + the additive-only/no-migration boundary. LOW. |
| A5 | `_run_agent`'s build-loop mechanics (report_task_complete→task_progress, completed_tasks accumulation, build_task_number thread-id) are workflow-agnostic and may stay in the kernel primitive. | Pitfall 5 | If parity requires these to move into the strategy too, the handle/strategy split shifts. They are name-agnostic today, so leaving them is INV-1-safe. LOW. |
| A6 | `od_context` continues to be built at the WS/NDJSON boundary and passed into `execute()` (the `opendesign` provider re-homes the LOADER but the boundary still calls it). | D-04 / Runtime State | If D-04 is read as "the provider loads od_context inside `execute()`", that changes the boundary contract + event timing. The authored design keeps the boundary building od_context (the provider's `load(ctx)` composes injection blocks FROM od_context). MEDIUM — planner should confirm the boundary call path stays. |

## Open Questions

1. **Does the runner handle expose `_run_agent` as a callable, or a richer `KernelServices` object?**
   - What we know: D-03 leaves this to discretion; the Phase 5/6 precedent is a single `object`-typed field.
   - What's unclear: how many distinct engine internals `task_loop` needs (A1).
   - Recommendation: Inventory every `self.<method>` call inside `_run_build_task_loop`/`_run_validation_fix_loop`/`_run_agent` in 07-01 task 1; expose them as a small frozen `KernelServices` dataclass attached as `ctx.runner` (`object`-typed on `ExecutionContext`). One field, many methods — keeps `context.py` import-pure.

2. **Where is `install()`/`_register_builtins()` invoked so the compiler's name-validation path is unaffected?**
   - What we know: the compiler only calls `registry.is_registered(...)` (membership), never `resolve(...)`; `is_registered` reads `_KNOWN`.
   - What's unclear: whether `resolve` shares `_KNOWN` (resolve asserts known AND has impl) or a separate impl map.
   - Recommendation: `resolve(kind,name)` asserts `(kind,name) in _KNOWN` AND looks up the impl map (a missing impl for a known name is a programmer error → raise). Invoke `install()` lazily at engine import or first `execute()` (NOT at `compiler` import) so the compiler/`is_registered` path is untouched and the `registry.py` "names only" scope note stays accurate (the impl map is populated by install, separate concern). This keeps `test_registry_capabilities.py` (asserts no impls at Phase-4 import) honest if install is engine-side.

3. **Can the parity harness run against the routed-but-not-yet-deleted state in 07-04?**
   - What we know: `_drive()` runs `execute()` end-to-end; it does NOT touch L1–L13 directly except via behavior. In 07-04 the engine routes through capabilities while the dead leaks remain.
   - What's unclear: whether any leak is still *reached* in 07-04 (it must not be — routing replaces the call sites).
   - Recommendation: In 07-04, the per-step dispatch + deliverable resolution + injection are switched to the capabilities; the leak *definitions* remain but are unreferenced (dead). `_drive()` + the goldens prove parity on the routed path; `vulture` confirms the leaks are orphaned BEFORE 07-05 deletes them. This makes 07-05 pure removal gated on green.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python3.11` | All backend work (dev runtime) | ✓ (per memory note: no venv) | 3.11 | — |
| `pytest` + `pytest-asyncio` | Characterization + unit suites | ✓ | existing | — |
| `import-linter` | Ports & Adapters CI gate | ✓ (configured pyproject) | existing | — |
| Headless Chromium | `render_check` (validation) | ✗ locally (degrades to skip) | — | `render_check` returns `available=False`; fix-loop contributes no render lines (built-in graceful degrade) [VERIFIED: engine.py:937-951 + backend/CLAUDE.md] |
| PostgreSQL | Live runs (checkpointer + run_events) | ✗ for offline harness | — | InMemory checkpointer (`ENV=development`); persist degrades to warning (best-effort, INV-3) [VERIFIED: _scripted_model.py:56-57] |
| Bedrock / API key | Live LLM runs | ✗ offline | — | ScriptedFakeChatModel drives the deepagents loop offline [VERIFIED: _scripted_model.py] |

**Missing dependencies with no fallback:** None — every external dependency degrades cleanly (the characterization suite runs fully offline by design).
**Missing dependencies with fallback:** Chromium → render skip; Postgres → InMemory + best-effort persist; Bedrock → scripted model. All three are the standard offline-CI posture; parity is proven offline.

## Validation Architecture

> `nyquist_validation` not explicitly false in config → section included. This is a **parity-proof phase**: validation IS the deliverable. The critical insight is that the existing CI gates already encode every required parity check; Phase 7's job is to keep them green and flip the deletion ratchets.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` + `pytest-asyncio` (Python 3.11) |
| Config file | `pyproject.toml` (`[tool.importlinter]` + `[tool.vulture]`; pytest config conventional) |
| Quick run command | `cd backend && python3.11 -m pytest tests/agents/test_characterization_prototype.py tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -x` |
| Full suite command | `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` |

### Critical sampling / validation points (the parity gates a plan must prove)
| Gate | What it proves | Automated command | Where it lives | Phase-7 action |
|------|----------------|-------------------|----------------|----------------|
| Deliverable byte-snapshot ×5 | `final_output` byte-identical (deterministic) per pipeline | `pytest tests/agents/test_characterization_*.py -k byte_snapshot` | `test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py` + `characterization/golden/*` | MUST stay green every plan; re-baseline ONLY if a sanctioned change |
| Semantic-event multiset ×5 | event types/order/required-keys (volatile fields normalized) per pipeline | `pytest tests/agents/test_characterization_*.py -k event_snapshot` | same files + `characterization/_normalize.py` + `golden/*.events.json` | MUST stay green; strategies must yield the SAME event vocabulary |
| Migration-ledger ratchet | each ☑ grep pattern → 0 in `backend/` | `pytest tests/agents/test_migration_ledger.py` | `test_migration_ledger.py` (parses `migration-ledger.md`) | 07-05: flip L1–L13 to ☑ with **kernel-scoped** patterns; keep L14/L15/L16/D2 ☑; D1 stays ☐ |
| Banned-pattern INV-1 gate | no `if pipeline_type`/`spec.id ==` name-branch in kernel | `pytest tests/agents/test_banned_patterns.py` | `test_banned_patterns.py` | 07-05: flip `test_inv1_*` warn-only → `assert count==0` **kernel-scoped** (see Pitfall 1: rewrite `spec.id == ordered_agents[0].id` to `index == 0` first) |
| import-linter contract | kernel→ports only; capabilities/workflows don't import kernel/app | project import-linter invocation (`lint_imports`) | `pyproject.toml:131-169` | keep green; capabilities must not import `execution_engine`/`app` (Pitfall 4) |
| 0C ≥50% compaction reduction | `html_skeleton` behavior-preserving | `pytest tests/agents/test_phase3_compaction.py` | `test_phase3_compaction.py` | **re-point** the 7 tests at the `html_skeleton` capability + injector (currently call `engine._extract_html_skeleton`/`_build_context_message` directly) |
| Manifest parity traps #1/#2 | `planner: run` everywhere; clarify.defaults == engine dict | `pytest tests/agents/test_manifest_parity.py` | `test_manifest_parity.py` | update line 26 import (`SKIP_PLANNER_FOR_PROTOTYPE` from deleted `pipeline.py`) |
| L16 cross-owner denial (CHECK) | parent-run ownership enforced (INV-8) | `pytest tests/agents/test_parent_run_ownership.py` | dedicated test | re-confirm green (PARITY-10) |
| vulture orphan check | L1–L13 helpers truly dead before 07-05 deletes | `cd backend && vulture app/ agents/` | pyproject `[tool.vulture]` | run in 07-04 to confirm leaks unreferenced before deletion |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PARITY-01 | both strategies drive a compiled Step; build via task_loop (no spec.id) | unit + characterization | `pytest tests/agents/test_characterization_prototype.py -k event` + new strategy unit test | ✅ char; ❌ Wave 0 (strategy unit test) |
| PARITY-02 | deliverable resolved via deliverable.strategy/name | characterization + unit | `pytest tests/agents/test_characterization_app_builder.py tests/agents/test_sandbox_deliverable.py` | ✅ (re-point) |
| PARITY-03 | providers + injector + heading_tasks + seed_files | unit + characterization | `pytest tests/agents/test_characterization_od_prototype.py` + new provider/parser unit tests | ✅ char; ❌ Wave 0 |
| PARITY-04 | html_skeleton ≥50% reduction preserved | unit (deterministic gate) | `pytest tests/agents/test_phase3_compaction.py` | ✅ (re-point to capability) |
| PARITY-05 | 3 prototype flavors run from manifests | characterization | `pytest tests/agents/test_characterization_prototype.py tests/agents/test_characterization_od_prototype.py tests/agents/test_characterization_prototype_revision.py` | ✅ |
| PARITY-06 | L1–L13 deleted; pipeline.py gone | ratchet | `pytest tests/agents/test_migration_ledger.py` | ✅ |
| PARITY-07 | ppt resolver + carousel sanitize | characterization | `pytest tests/agents/test_characterization_od_ppt.py` | ✅ |
| PARITY-08 | INV-1 kernel grep → 0; hard-fail | ratchet | `pytest tests/agents/test_banned_patterns.py` | ✅ (flip + scope) |
| PARITY-09 | 5-pipeline deliverable + event parity | characterization | `pytest tests/agents/test_characterization_*.py` | ✅ |

### Sampling Rate
- **Per task commit:** `pytest tests/agents/test_characterization_prototype.py tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -x` (fast parity + ratchet pulse).
- **Per wave merge:** `pytest tests/agents/ tests/unit/ -v` + `vulture app/ agents/` + the import-linter invocation.
- **Phase gate:** Full `tests/agents/` + `tests/unit/` green, all 5 characterization snapshots green, migration-ledger ratchet green with L1–L13 ☑, banned-pattern hard-fail green, import-linter green, 0C ≥50% gate green — before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/agents/test_strategies.py` (or per-strategy) — drive `single_shot` + `task_loop` from a compiled `Step` (acceptance for PARITY-01: "a unit test drives both strategies from a compiled Step").
- [ ] `tests/agents/test_deliverable_resolvers.py` — unit-cover `single_file`/`serialized_sandbox`/`streamed_text`/`ppt` resolution from a sandbox fixture.
- [ ] `tests/agents/test_context_providers.py` — `opendesign`/`previous_run` `load(ctx)` block output + the generic injector ordering.
- [ ] `tests/agents/test_heading_tasks_parser.py` — `## Task N:` + `<tasks>` fallback → `Task[]` (port the `_count_plan_tasks`/`_extract_task_block` unit cases).
- [ ] `tests/agents/test_capability_resolution.py` — `registry.resolve(kind,name)` returns the right impl; unknown name raises; `is_registered` unchanged.
- [ ] **Re-point** `test_phase3_compaction.py` from `engine._extract_html_skeleton`/`_build_context_message` to the `html_skeleton` capability + injector (do NOT lose the ≥50% assertion).
- [ ] **Update** `test_manifest_parity.py:26` to not import `SKIP_PLANNER_FOR_PROTOTYPE` from the deleted `pipeline.py` (move the `is False` premise check or drop it).
- [ ] **Update** `_scripted_model.py:425` (`engine_mod.ALWAYS_CLARIFY = False`) for L6 deletion — replace with the manifest-sourced clarify path or remove the monkeypatch.

## Security Domain

> `security_enforcement` not explicitly false → included, scoped to what this phase actually touches.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Ports & Adapters boundary (import-linter); kernel→ports one-way [VERIFIED: pyproject.toml] |
| V2 Authentication | no | No auth code changes (boundary unchanged) |
| V4 Access Control | yes | `previous_run` provider's parent-run seed MUST stay ownership-checked via `ScopedStore.assert_owns` (INV-8/L16) — the cross-owner `PermissionError` must propagate, never be swallowed [VERIFIED: engine.py:874-895] |
| V5 Input Validation | yes | Compiler validates every capability name against the registry (INV-4); `resolve` must reject unknown `(kind,name)`; no `eval`/dynamic-import of names (T-04-01 — keep `resolve` a dict lookup, never `getattr`) |
| V6 Cryptography | no | None |
| V12 File handling | yes | `RunSandbox` path-traversal guards + `compile_for_run`'s closed-set manifest id (no `open(base/arbitrary)`) — unchanged; resolvers read sandbox via existing `read`/`path_for` (traversal-proof) [VERIFIED: engine.py:233-236] |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Capability name → dynamic code exec | Elevation of Privilege | `resolve` is a static dict lookup over `_KNOWN`-validated names; NO `getattr`/`eval`/dynamic import (T-04-01); explicit `install()` binds a fixed set |
| Cross-owner parent-run data leak (revision) | Information Disclosure | `previous_run` keeps `assert_owns` BEFORE seeding; `PermissionError` propagates out of `execute()` (L16 ratchet — `test_parent_run_ownership.py`) |
| Re-implemented agent loop bypassing deepagents | Tampering (runtime integrity) | INV-13 banned-pattern gate; no capability may import/call `create_deep_agent` — strategies invoke the existing `_run_agent`/`create_runner` via the handle |
| Import cycle re-coupling kernel to app/web | Architecture erosion | import-linter contracts (capabilities/workflows ⊬ execution_engine/app; kernel ⊬ app.api) |
| Manifest id path traversal | Tampering | `compile_for_run` resolves to a closed alias set; unknown id → `FileNotFoundError`, never arbitrary `open` |

## Sources

### Primary (HIGH confidence — direct codebase read this session)
- `backend/agents/execution_engine/engine.py` (3592 lines) — all L1–L13 locations, `execute()`/`_run_agent`/`_run_build_task_loop`/`_run_validation_fix_loop`/`_build_context_message`/`_extract_html_skeleton`/`_resolve_final_output`/`compile_for_run` read directly.
- `backend/agents/capabilities/base.py`, `registry.py` — ports + name registry.
- `backend/agents/workflows/plan.py`, `compiler.py` — typed plan + compile/validation path.
- `backend/agents/workflows/{prototype,prototype_revision,ppt}/workflow.yaml` — authored manifests (confirmed `planner: run`, `seed_files: {}`, clarify.defaults).
- `backend/agents/prototype/context.py`, `pipeline.py`, `__init__.py`; `backend/agents/execution_engine/od_context.py`, `context.py`.
- `backend/app/agents/sandbox.py` (API signatures).
- `backend/tests/agents/{test_migration_ledger,test_banned_patterns,test_manifest_parity,test_phase3_compaction,_scripted_model}.py` + `test_characterization_*.py` + `characterization/` dir.
- `backend/pyproject.toml` — import-linter contracts + vulture config.
- `specs/003-workflow-engine-decoupling/plan.md` §6/§10/§11/§32; `migration-ledger.md` (L1–L16 rows + D1 void note).
- `CLAUDE.md`, `backend/CLAUDE.md` — stack, dev runtime, commit scopes, prototype build-loop description.

### Secondary (MEDIUM)
- Grep audits run this session (importers of `agents.prototype.*`; INV-1 pattern matches across `app`+`agents`; `seed_files` across all manifests) — cross-checked against the read files.

### Tertiary (LOW)
- None — all findings verified against the live tree.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; existing modules read directly.
- Architecture (runner handle / resolution seam): HIGH for the constraint (import-linter contract verified live), MEDIUM for the exact handle surface (depends on the full `self.`-call inventory in 07-01 — see A1/Q1).
- Pitfalls: HIGH — each grounded in a specific verified line/grep (banned-pattern scope, two carousel sites, `seed_files: {}`, import-linter direction, L10 in `_run_agent`).
- Parity gates: HIGH — every gate located in a named test file and read.

**Research date:** 2026-06-08
**Valid until:** ~2026-07-08 (stable brownfield tree; re-verify line numbers if `engine.py` shifts before planning — the symbol names are the durable anchors, not the line numbers).

## RESEARCH COMPLETE

**Phase:** 7 — prototype-as-manifest-parity-proof-sc-001-2
**Confidence:** HIGH

### Key Findings
- **The import-linter contract is the load-bearing constraint:** `agents.capabilities must not import agents.execution_engine` is ALREADY live (pyproject.toml:165-169). Capability impls may import `agents.workflows.plan` (Step/Task) but must keep `ctx` typed `Any`/`object` — the D-03 runner handle on `ExecutionContext` (typed `object`, proven by `scoped_store`/`model_resolver`) is the only viable way to reach `_run_agent`/sandbox/`static_check`/`render_check` without breaking the boundary.
- **Three parity traps confirmed live:** (1) `planner: run`; (2) revision clarify.defaults → `custom`; (3) **ALL manifests are `seed_files: {}`** — seeding behavior must move into `task_loop`/`previous_run`, NOT manifest data. Do not re-author manifests.
- **PARITY-08 scoping is non-trivial:** the banned-pattern gate scans `app`+`agents`; after deleting L1–L13 it still matches `app/api/websocket.py`+`registry.py` (legit) and `spec.id == ordered_agents[0].id` (positional false-match, engine.py:3264). Recommend rewriting that to `index == 0` + kernel-scoping the gate.
- **Phase 7 is relocation, not reimplementation:** `_extract_html_skeleton`, `_count_plan_tasks`/`_extract_task_block`, the fix-loop sig helpers, and `context.py` loaders are all pure/liftable. The L3 carousel sanitize is applied at TWO sites (engine.py:1394 + :1916) — both must move.
- **Test coupling is the hidden migration:** `test_phase3_compaction.py` (the 0C ≥50% gate) calls `engine._extract_html_skeleton`/`_build_context_message` directly; `test_manifest_parity.py:26` imports the deleted `SKIP_PLANNER_FOR_PROTOTYPE`; `_scripted_model.py:425` monkeypatches `ALWAYS_CLARIFY` (deleted by L6). All must be updated.

### File Created
`.planning/phases/07-prototype-as-manifest-parity-proof-sc-001-2/07-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | No new deps; frozen brownfield; modules read directly |
| Architecture | HIGH (constraint) / MEDIUM (handle surface) | import-linter verified; exact handle fields pending 07-01 `self.`-call inventory (A1/Q1) |
| Pitfalls | HIGH | Each tied to a verified line/grep |
| Validation gates | HIGH | Every gate located + read |

### Open Questions
1. Runner handle shape (callable vs `KernelServices`) — recommend inventorying all `self.<method>` calls in the three build/run/fix methods in 07-01 and exposing them as one `object`-typed `ctx.runner`.
2. `install()` invocation site so the compiler's `is_registered` path is unaffected — recommend lazy engine-side install with `resolve` sharing `_KNOWN`.
3. Parity harness against routed-but-not-yet-deleted state in 07-04 — confirmed viable; `vulture` confirms orphaning before 07-05 deletion.

### Ready for Planning
Research complete. The planner has: the per-leak location map, the runner-handle/import-linter constraint resolution, the three parity traps, the full test-coupling inventory, and the kernel-scoping analysis for PARITY-08. The 5-plan sequencing (D-05) is validated as the safe strangler ordering.
