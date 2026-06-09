# Phase 8: Capabilities Hardened — Registry, Gates, Tool Perms, Runtime [3] — Research

**Researched:** 2026-06-09
**Domain:** Brownfield refactor of a hexagonal capability layer (Python · FastAPI · PostgreSQL · LangGraph/deepagents) under strict INV-3 parity
**Confidence:** HIGH (every claim grounded in `file:line` from the live tree; decisions already LOCKED in CONTEXT.md)

## Summary

This phase hardens the Phase-7 capability layer behind ports/registries/policy and deletes the five factory leaks (F1–F5). The decisions are LOCKED (D-01..D-12); this research resolves the embedded **feasibility questions** so the planner can write parity-safe, deletion-gated plans. The headline finding: **almost every forward surface this phase needs already exists as inert scaffolding** — `Step.tools: ToolPermissions`, `Step.gates`, `Step.validators`, `Step.fix: FixPolicy`, `Step.model`, `DeliverableSpec`, the `GateHandler`/`Validator` Protocol ports, the compiler's `is_registered` INV-4 path, and the `KernelServices` handle with `static_check`/`render_check`/`run_validation_fix_loop` already wired. Phase 8 is mostly *binding impls into existing seams + deleting the inline originals*, not building new abstractions from scratch.

The deepest architecture fork (D-04) resolves cleanly: **`app/agents/validators/` importing `agents/capabilities/base` is import-linter-legal today** — the contract forbids `agents.capabilities → app`, not `app → agents.capabilities` (proven: `app/api/websocket.py:94` and `app/api/settings.py:19` already import `agents.capabilities.model_catalog`). Validators live on the app side (where the heavy deps already are), self-register via `@register`, and the kernel reaches them only through the registry `resolve` + the `KernelServices` handle.

The strictest constraint is **strict INV-3**: the 5 characterization snapshots stay byte-identical and the two riskiest re-points (task_loop validation onto registered validators per D-06; the F1/F3/F4 prompt-assembly lift per D-08) must produce byte/event-identical output. The good news for parity: the existing `task_loop` already routes validation **unconditionally** through `runner.run_validation_fix_loop` (engine's single home) — so D-06's "generic FixPolicy fix-loop" is a *refactor of the engine's `_run_validation_fix_loop` internals*, not a new code path in the strategy.

**Primary recommendation:** Follow the locked 8-plan order (D-12). Land `@register`/`discover()` + the `_IMPLS` autouse-reset fixture first (08-01), then bind gates/perms/validators/providers into the already-present inert fields, deleting each F-leak only after its routed path proves byte-identical against the 5 snapshots. Treat `discover()` as importing both `agents/capabilities/*` AND `app/agents/validators/` (the only app-side capability package), invoked at engine import / first `execute()` — **never at compiler import** (the `is_registered`/`_KNOWN` membership path must stay impl-free, asserted by `test_registry_capabilities.py`).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `@register`/`discover()` self-registration | Capability registry (`agents/capabilities/registry.py`) | — | The registry is the substrate; `discover()` triggers import-time binding |
| Trust flag (`user_allowed`) validation | Compiler (`agents/workflows/compiler.py`) | Registry | Compiler already validates references (INV-4); trust is an additional check at the same seam |
| Gate evaluation (`human`/`validation`/`approval`/`security`) | Kernel step boundary (`engine.py` dispatch loop ~:1011) | GateHandler impls (capabilities) | Kernel owns the step loop; gates are registered handlers resolved by name |
| Validator execution + fix-loop | `task_loop` strategy + `validation` gate (capabilities) | `KernelServices` handle → `app/agents/validators/` heavy deps | Strategy owns inline validation; gate is the declarative entry; heavy deps stay app-side |
| Tool-permission resolution | Compiler (intersection) | `factory._build_runner_tools` enforcement point + `Workspace.ExecutionPolicy` | Resolution is compile-time data; enforcement is at tool-binding |
| Prompt assembly (F1/F3/F4) | `factory._compose_system_prompt` → `PromptAssemblyPolicy` | skill/hook providers | Factory owns prompt composition; policy declares block order |
| Runtime selection (F5) | `AgentRuntimeAdapter` (wraps `create_deep_agent`) | `factory.create_runner` | INV-13 — adapter wraps, never replaces the deepagents graph |
| Executable hooks | Kernel lifecycle points (`engine.py`) + runner tool-call events | HookHandler impls | Hooks bind to engine/runner lifecycle events |
| Persistence (3 new tables) | Alembic `0016` + `ScopedStore` writers | `ExecutionContext` (owner/workspace source) | Additive migration; owner/workspace sourced at write time |
| `/api/capabilities` + WS events | `app/api/` (FastAPI) | Registry (palette source) | API tier surfaces the registry; WS forwards engine events generically |
| Frontend panels | React components (`frontend/src/components/`) | `/api/capabilities` + WS stream | Data-bearing panels consume live API data |

## Standard Stack

This is a brownfield refactor — **extend, don't add**. The "stack" is the existing in-repo machinery the phase binds into. Only ONE genuinely new external dependency is required.

### Core (existing — extend)
| Component | Location | Purpose | Why Standard |
|-----------|----------|---------|--------------|
| `CapabilityRegistry` | `agents/capabilities/registry.py` | `_KNOWN` membership (16 pairs) + `_IMPLS` impl map + `install()` | The exact seam D-01 evolves to `@register`/`discover()`; docstring names Phase 8 as owner [VERIFIED: registry.py:9-16] |
| Capability ports | `agents/capabilities/base.py` | `GateHandler` (:105), `Validator` (:54), `PostStep` (:87) Protocols | D-03/D-04 bind real impls; new ports follow the one-method-Protocol idiom [VERIFIED: base.py:104-112] |
| `KernelServices` handle | `agents/execution_engine/kernel_services.py` | `static_check`/`render_check` (:126-132), `run_validation_fix_loop` (:274), `compute_revision_baseline` (:135) | The single kernel↔app seam; validators + fix-loop reach heavy deps through it [VERIFIED: kernel_services.py] |
| `ToolPermissions` dataclass | `agents/workflows/plan.py:45-61` | Least-privilege grant set (read_files ON, rest OFF) | **Already present + inert** — D-07 makes it live [VERIFIED: plan.py:45-61] |
| `FixPolicy` dataclass | `agents/workflows/plan.py:100-105` | `mode` + `max_attempts` | **Already present** — D-06's generic fix-loop config [VERIFIED: plan.py:100-105] |
| `Step` forward fields | `agents/workflows/plan.py:232-241` | `tools`, `model`, `validators`, `fix`, `compaction`, `gates` | **All present + inert** — bind, don't add [VERIFIED: plan.py:214-241] |
| `ScopedStore` | `agents/authz.py:58` | Default-deny owner/workspace-scoped writer | D-10's 3 new-table writers mirror it [VERIFIED: authz.py:58] |
| `RunCapabilities` model | `app/models/run_capabilities.py` | `owner_id`+`workspace_id` additive-table precedent | The exact §18 pattern `0016` follows; already reserves `skills`/`hooks` JSON cols for "Phase 8" [VERIFIED: run_capabilities.py:34-35] |
| `ModelCatalog` (`model_catalog` kind) | registered in `_KNOWN` | A data-capability kind already registered + surfaced via API | Precedent for the palette's model catalog [VERIFIED: registry.py:62, websocket.py:94] |

### Supporting (new external dependency — OTel only)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `opentelemetry-sdk` + `opentelemetry-api` | latest 1.x | `otel_tracing` canonical hook spans/logs (OBS-02, HOOK) | **No OTel dep exists in the tree today** — `otel_tracing` needs a lib + exporter config [VERIFIED: grep of pyproject.toml/requirements found ZERO opentelemetry references] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `opentelemetry-sdk` exporter | structured-logging-only `otel_tracing` (no real spans) | SPEC says "OpenTelemetry-style spans/logs" — a logging-only impl satisfies "non-blocking, emits a span + hook_runs row" but loses real OTLP export; planner's call (D-09 directive flags this as open) |
| `app/agents/validators/` placement | `agents/capabilities/validators/` for pure-stdlib validators | `html_render` needs Chromium (heavy) → app-side; `task_done_when`/`spec_plan_coverage` may be pure-stdlib → kernel-side (D-05) |

**Installation (OTel only — verify before install via Package Legitimacy Gate):**
```bash
python3.11 -m pip install opentelemetry-api opentelemetry-sdk
```

## Package Legitimacy Audit

> Only ONE external package is introduced (OTel). slopcheck was not run in this research session; per protocol the package is tagged `[ASSUMED]` and the planner MUST gate its install behind a `checkpoint:human-verify` task.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `opentelemetry-api` | PyPI | ~6 yrs (well-established) | very high (tens of M/mo) | github.com/open-telemetry/opentelemetry-python | not run | `[ASSUMED]` — planner adds checkpoint:human-verify |
| `opentelemetry-sdk` | PyPI | ~6 yrs | very high | github.com/open-telemetry/opentelemetry-python | not run | `[ASSUMED]` — planner adds checkpoint:human-verify |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*OpenTelemetry is a CNCF-graduated project — high confidence it is legitimate — but per the package-provenance rule (a name from training data is `[ASSUMED]` regardless of registry existence), the planner must verify on PyPI (`pip index versions opentelemetry-sdk`) and confirm the exact package split (api vs sdk vs instrumentation) before install. All other Phase-8 work uses in-repo modules — no other external packages.*

## Architecture Patterns

### System Architecture Diagram

```
                  MANIFEST (workflow.yaml — pure data, no DSL)
                         │
                         ▼
        ┌─────────────────────────────────────────────┐
        │ WorkflowCompiler.compile(manifest, registry) │  ← compiler.py
        │  • is_registered(kind,name) per reference    │     (INV-4 membership)
        │  • NEW: user_allowed trust check (D-02)      │     ── trust context ──┐
        └─────────────────────────────────────────────┘                        │
                         │ CompiledWorkflow (Step DAG +                          │
                         │  Step.tools/gates/validators/fix/model)               │
                         ▼                                                       │
        ┌─────────────────────────────────────────────┐         ┌──────────────▼──────────────┐
        │ ExecutionEngine.execute()  (engine.py)       │         │ CapabilityRegistry          │
        │                                              │◄────────│  _KNOWN (membership, impl-  │
        │  per step (i, spec) in ordered_agents:       │ resolve │  free at compiler import)   │
        │   ① [NEW] pre-step gates (security/approval) │ (kind,  │  _IMPLS (bound by discover()│
        │   ② strategy = resolve("strategy", name)     │  name)  │   at engine import / 1st run)│
        │      └─ task_loop ──┐                        │         └──────────────┬──────────────┘
        │   ③ async for ev in strategy.run(step,ctx):  │                        │ @register binds
        │   ④ post_step (revision_validation)          │      ┌─────────────────┴──────────────────┐
        │   ⑤ [NEW] post-step gates (validation/human) │      │ capabilities/{strategies,gates,     │
        │   ⑥ _should_gate → _run_review_gate (human)  │      │   validators,tools,skills,hooks,     │
        └──────────────┬───────────────────────────────┘      │   runtimes,...}/  +  PromptAssembly  │
                       │ ctx.runner (KernelServices)           │ app/agents/validators/ (heavy-dep)  │
                       ▼                                       └─────────────────────────────────────┘
        ┌─────────────────────────────────────────────┐
        │ KernelServices handle (the ONLY kernel↔app   │
        │  seam — kernel may import app.*; capabilities│
        │  reach it ONLY via ctx.runner)               │
        │   • run_agent → _run_agent → create_runner   │──► factory.create_runner
        │   • run_validation_fix_loop (→ generic, D-06)│        ├─ _compose_system_prompt (F1/F3/F4)
        │   • static_check / render_check              │──┐     │    → PromptAssemblyPolicy (D-08)
        │   • [NEW] hook firing points (D-09)          │  │     ├─ _build_runner_tools (F2)
        └─────────────────────────────────────────────┘  │     │    → tool_provider registry (D-07/D-08)
                       │                                  │     └─ DeepAgentRunner
                       ▼                                  │          └─ create_deep_agent (F5)
        ┌──────────────────────────────────┐  static/    │               → AgentRuntimeAdapter (D-08)
        │ app/agents/validators/ (NEW pkg)  │  render     │
        │  html_static → static_check       │◄────────────┘
        │  html_render → render_check       │  (heavy deps stay app-side; reached via handle)
        │  Tier#4/5/6 validators            │
        └──────────────────────────────────┘
                       │ rows
                       ▼
        ┌──────────────────────────────────┐     ┌─────────────────────────────────┐
        │ Alembic 0016 (additive, D-10):   │     │ GET /api/capabilities (palette) │
        │  validation_results / gate_events │     │  + WS additive events           │
        │  / hook_runs (owner_id+ws_id)     │     │  (validator_result/gate_*)      │
        │  written via ScopedStore          │     │  → frontend 3 panels            │
        └──────────────────────────────────┘     └─────────────────────────────────┘
```

### Recommended Project Structure
```
backend/
├── agents/capabilities/
│   ├── registry.py              # @register decorator + discover() (deletes install())
│   ├── base.py                  # + PromptAssemblyPolicy, AgentRuntimeAdapter, HookHandler,
│   │                            #   ToolProvider, SkillProvider, HookProvider ports
│   ├── gates/                   # NEW: human, validation, approval, security GateHandlers
│   ├── tools/                   # NEW: tool_provider impls (workspace/prototype/planning sets)
│   ├── skills/                  # NEW: skill_provider impls (ui·disk·template·repo + behavioral)
│   ├── hooks/                   # NEW: secret_scan, otel_tracing HookHandlers
│   ├── runtimes/                # NEW: langchain_deepagents AgentRuntimeAdapter
│   ├── prompt/                  # NEW: PromptAssemblyPolicy (or a config object on compiled wf)
│   └── validators/              # NEW: pure-stdlib validators (task_done_when, spec_plan_coverage?)
├── app/agents/
│   └── validators/              # NEW: heavy-dep validators — html_static, html_render,
│                                #   design_quality (import base port + static_check/render_check)
├── alembic/versions/
│   └── 0016_*.py                # validation_results, gate_events, hook_runs
└── app/api/
    └── capabilities.py          # NEW: GET /api/capabilities
frontend/src/components/
├── workflow/                    # capability palette + per-agent model picker (extend AgentLibrary)
└── results/                     # validator/issue panel (extend the results surfaces)
```

### Pattern 1: Inert-field activation (the dominant pattern this phase)
**What:** Most "new" surfaces are already declared as inert forward fields. Phase 8 binds them live, it does not add them.
**When to use:** Every D-0X where the directive asks "confirm the field exists or needs adding" — answer is almost always "exists, inert."
**Evidence:**
```python
# agents/workflows/plan.py:232-241 — Step forward surface (ALL present, inert in Phase 4):
    tools: ToolPermissions = field(default_factory=ToolPermissions)  # INV-9 / §8  (D-07)
    model: ModelPolicy | None = None                                 # §20
    validators: list[str] = field(default_factory=list)              # Q21 (D-04/D-06)
    fix: FixPolicy | None = None                                     # Q23/Q25 (D-06)
    compaction: str | None = None
# gates already CONSUMED (Phase-4): Step.gates (plan.py:228), validated by compiler.py:164-167
```

### Pattern 2: App-side capability reached via the handle (D-04 backbone)
**What:** Heavy-dep validators live in `app/agents/validators/`, import the port (`agents.capabilities.base.Validator`) + the heavy checks, self-register, and the kernel reaches them only via `resolve` + `KernelServices`.
**When to use:** `html_static`/`html_render`/`design_quality` (Chromium/heavy).
**Evidence (import-linter direction is LEGAL):**
```python
# app/api/websocket.py:94   — app ALREADY imports a capability module:
from agents.capabilities.model_catalog import ModelCatalog
# app/api/settings.py:19    — same direction, proven green:
from agents.capabilities.model_catalog import ModelCatalog
# pyproject.toml import-linter contract forbids ONLY the reverse:
#   source_modules = ["agents.capabilities"]; forbidden_modules = ["agents.execution_engine", "app"]
# → app → agents.capabilities.base is NOT forbidden. D-04(3) CONFIRMED.
```

### Pattern 3: discover() must NOT run at compiler import (D-01 backbone)
**What:** `discover()` imports the capability subpackages so `@register` binds `_IMPLS`. But the compiler's `is_registered`/`_KNOWN` path MUST stay impl-free at compiler import (a hard test assertion).
**Evidence:**
```python
# registry.py:70-74 — the contract Phase 8 must preserve:
#   _KNOWN must validate manifest references at Phase-4 compiler import time WITHOUT
#   any impl being bound (test_registry_capabilities.py asserts no impls at that import).
#   The impl map is populated LAZILY by install() — at engine import / first execute(),
#   never at compiler import.
# test_registry_capabilities.py:73-78 — the drift guard:
def test_registered_count_is_exactly_sixteen():
    assert len(_KNOWN) == 16          # ← adding tool/skill/hook/runtime kinds bumps this
```
**Resolution for D-01:** Keep `_KNOWN` as the membership surface (regenerate it from the registered set OR keep it as a declared allow-list the `@register` decorator validates against — Claude's discretion per CONTEXT). `discover()` runs at engine import / first `execute()` (mirroring the current lazy `install()` at `registry.py:176`), importing `agents/capabilities/*` AND `app/agents/validators/`. `is_registered` stays a pure `_KNOWN` set lookup with zero impls bound. **The `test_registered_count_is_exactly_sixteen` assertion will need updating** as new kinds/names are added — that is an expected, in-scope test edit (not a snapshot re-baseline).

### Anti-Patterns to Avoid
- **Running `discover()` at compiler import:** breaks the impl-free membership invariant; `test_registry_capabilities.py` is the gate.
- **Kernel → `app.*` import for validators:** import-linter HARD-fails `agents.capabilities → app`. Reach heavy deps via `ctx.runner` (`KernelServices`) only.
- **Moving ALL validation into the `validation` gate:** D-06 explicitly rejects this — it risks the build-loop's event parity. `task_loop` keeps its inline validation (now registry-backed); the gate is the *additive* declarative entry.
- **Deleting an F-leak before its routed path proves parity:** D-12 critical constraint — wrap→rewire→delete, deletion is the exit gate, the 5 snapshots gate every deletion.
- **Adding the `AgentRuntimeAdapter` in a new module without updating the banned-pattern allow-list:** `_ALLOWED_CREATE_DEEP_AGENT = frozenset({"app/agents/deep_agent_runner.py"})` (test_banned_patterns.py). If the adapter wraps `create_deep_agent` from a NEW file, that file must be added to the allow-list; simplest is to keep the adapter IN `deep_agent_runner.py`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Capability discovery/binding | `pkgutil.walk_packages` auto-walk | Explicit `discover()` importing known subpackages | D-01 rejects pkgutil (non-deterministic ordering, pulls unintended modules, import-linter can't reason about it) |
| Fix-loop | New fix-loop in `task_loop` strategy | The engine's single `_run_validation_fix_loop`, made generic via `FixPolicy` | INV-3/INV-12 no dual impls; `task_loop` already delegates unconditionally (task_loop.py:292) |
| Human gate | New HITL pause mechanism | Register `human` → existing `_run_review_gate` (engine.py:2043) | GATE-03 parity — identical `review_gate_*` events, no snapshot re-baseline |
| Deep agent runtime | Any hand-rolled agent loop | `create_deep_agent` wrapped by `AgentRuntimeAdapter` | INV-13 + banned-pattern gate (R15); wrap never replace |
| Owner/workspace scoping | New scoped-write logic | `agents/authz.py:58 ScopedStore` | D-10 — default-deny, owner/workspace-scoped, the Phase-5 pattern |
| Additive migration | New migration framework | Alembic `0016` mirroring `RunCapabilities` (`owner_id`+`workspace_id`) | D-10 — `run_capabilities.py` is the exact §18 precedent |
| WS event forwarding | New event-routing code | Generic `{"type": event["type"], ...}` forward (websocket.py:595/719) | New additive events flow through unchanged — no websocket.py edit for new event *types* |
| Severity model | Ad-hoc per-validator severity strings | One P0–P3→CRITICAL/HIGH/MEDIUM/LOW mapping function | VALID-03 / Q24 — a single tested function |

**Key insight:** This phase is ~80% *binding into existing inert seams + deleting inline originals*. The single biggest hand-roll risk is re-implementing the fix-loop inside the strategy or the gate; the architecture (engine's `_run_validation_fix_loop` as the sole home, reached via the handle) is already correct from Phase 7 — D-06 only makes its internals config-driven.

## Runtime State Inventory

> This is a code/config refactor with an additive DB migration. The "runtime state" that matters here is **CI gates, global registry state, and characterization snapshots** — not external datastores/OS registrations.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | The 3 NEW tables (`validation_results`/`gate_events`/`hook_runs`) are net-new — no existing data carries renamed keys. `RunCapabilities.skills`/`hooks` JSON columns already exist + reserved "Phase 8" (run_capabilities.py:33-34) — Phase 8 begins populating them. | Additive migration `0016` (code-write, no data migration of existing rows) |
| Live service config | None — no external services (n8n/Datadog/etc.) hold capability state. The capability registry is a process-global module singleton (`registry.py` `_IMPLS`/`_INSTALLED`), not an external store. | None |
| OS-registered state | None | None |
| Secrets/env vars | `otel_tracing` may need an OTLP exporter endpoint env var (e.g. `OTEL_EXPORTER_OTLP_ENDPOINT`) if real export is wired — NEW config, not a rename. No existing secret key references a renamed thing. | Add exporter config (D-09 — planner decides logging-only vs real OTLP) |
| Build artifacts | `_KNOWN` membership set (`registry.py:46-63`) + `test_registry_capabilities.py` `_EXPECTED_NAMES` (:30-49) + `test_registered_count_is_exactly_sixteen` (:73) are the **drift guards**: adding `tool`/`skill`/`hook`/`runtime` kinds + new names bumps the count → these tests need updating in lockstep (NOT a snapshot re-baseline — an expected in-scope edit). The migration-ledger F1–F5 rows (☐ today, migration-ledger.md:83-87) flip to ☑. `test_strategies.py` global-registry pollution (D-12 fold) needs an autouse `_IMPLS` save/restore fixture. | Update `_KNOWN`/`_EXPECTED_NAMES`/count assertion; flip ledger F1–F5; add reset fixture |

**Critical global-state hazard (D-12 fold):** `test_strategies.py:333-334` calls `registry_mod.install()` + mutates `registry_mod._IMPLS[("compaction","html_skeleton")]` and its `finally` (:360-361) pops only the ONE key it added — leaving the `install()`-reseeded global registry polluted, which breaks the characterization snapshots when run in the same session (deferred-items.md:49-68). **Phase 8 reworks exactly this registry (D-01)** — fold an autouse save/restore reset fixture (full `_IMPLS` snapshot/restore, or registry reset) into 08-01. With `@register` import-time binding, the pollution surface grows (more impls bound globally), so the fixture is now *required*, not opportunistic.

## Common Pitfalls

### Pitfall 1: Breaking the impl-free compiler membership path
**What goes wrong:** `@register` binds impls at import; if `discover()` (or import-time decorators) run when the compiler imports the registry, `test_registry_capabilities.py`'s impl-free assertion fails and the compiler drags in heavy impl modules.
**Why it happens:** Decorator-based registration binds at *module import*, and the compiler imports `registry.py`.
**How to avoid:** `@register` should populate `_KNOWN` (or a declared allow-list) at registry-module import, but the impl modules themselves are imported only by `discover()` — invoked at engine import / first `execute()`, never at compiler import. Mirror the current lazy `install()` (`registry.py:176`).
**Warning signs:** `test_registry_capabilities.py` failing; compiler import time ballooning; import cycles.

### Pitfall 2: Snapshot re-baseline temptation on the prompt-assembly lift (F1/F3/F4)
**What goes wrong:** Re-ordering blocks in `PromptAssemblyPolicy` shifts a newline or block boundary → composed prompt bytes differ → characterization snapshots break → tempted to re-baseline.
**Why it happens:** `_compose_system_prompt` joins blocks with `"\n\n"` (factory.py:255) in a fixed order (injects→guardrails→skills→hooks→constitution→body); the policy must reproduce this byte-for-byte.
**How to avoid:** The default `PromptAssemblyPolicy` order MUST be `injects→guardrails→skills→hooks→constitution→prompt_body` (factory.py:174-255). Parity test: compose via the policy vs the legacy inline path, assert byte-equal for every existing agent. NEVER re-baseline (INV-3 boundary; SPEC acceptance "composed prompts byte-identical").
**Warning signs:** Any diff in the 5 characterization snapshots after the F1 lift; `blocks\.append` grep must hit 0 (F1 gate) but bytes must be identical.

### Pitfall 3: Constitution fix changes existing snapshots (F4/R12)
**What goes wrong:** Fixing the `_inject_constitution` no-op (factory.py:282-292 — the running-loop branch reads only `_mem`) makes a DB-stored Constitution inject in prod; if a characterization run had a Constitution set, snapshots would change.
**Why it happens:** The bug silently drops the Constitution under a running event loop.
**How to avoid:** The existing characterization runs have **NO Constitution set** (CONTEXT specifics:236) → snapshots stay byte-identical. The constitution-injected-in-prod test is a **NEW test**, not a re-baseline. The sync-safe fix: `create_runner` is SYNC (factory.py:69) but called from the async engine (engine.py:1381 inside `_run_agent`) — options are (a) pre-warm the constitution into a cache at run entry (before the sync `create_runner` calls), or (b) make the read sync-safe via `asyncio.run_coroutine_threadsafe` / a thread. **D-08 directive — the pre-warm at run entry is the lower-risk option** (no await-in-running-loop hazard); confirm with the new test.
**Warning signs:** Snapshot drift on a Constitution-bearing run; `RuntimeError: event loop already running`.

### Pitfall 4: Validation gate vs strategy ownership (D-06)
**What goes wrong:** Moving the prototype build-loop validation into the `validation` gate changes its event sequence → snapshot break.
**Why it happens:** The build loop's per-task validation is internal (consume-internally, emit-nothing — task_loop.py:292, kernel_services.py:274); the gate is a step-boundary mechanism with potentially different event emission.
**How to avoid:** Keep `task_loop`'s inline validation where it is (now driving registered `html_static`/`html_render` + the generic `FixPolicy` loop). The `validation` gate is **additive** — for non-build steps declaring `gates:[validation]`. The `revision_validation` post_step (post_steps/revision_validation.py) becomes a `gates:[validation]` step ONLY if parity holds against the revision snapshot (`test_characterization_prototype_revision.py`); else it stays a post_step. **Decide with snapshot evidence.**
**Warning signs:** `test_characterization_prototype.py` / `_prototype_revision.py` event-multiset drift.

### Pitfall 5: ToolPermissions parity at `_build_runner_tools` (D-07/F2)
**What goes wrong:** Replacing the closed `workspace`/`prototype`/`prototype_emit_only`/`planning` switch (factory.py:418-446) with grant-driven resolution binds a different tool set → `test_create_runner.py` parity break.
**Why it happens:** The switch maps tool-set NAMES to `(custom_tools, exclude_builtin)`; the new model maps PERMISSIONS to tool sets. The mapping must be behavior-preserving for the existing 4 named sets.
**How to avoid:** The `tool_provider` registry must resolve the same `(custom_tools, exclude_builtin)` for every existing agent's declared `tools:` list. Effective perms = `intersection(owner_allow_list, workflow_ceiling, step_grant)` (D-07) — but for existing manifests with no explicit grants, the defaults (`ToolPermissions`: read_files ON, rest OFF — plan.py:53-61) must yield the SAME bindings the switch produced. Parity test: `test_create_runner.py` for one agent of each class binds identical tool sets.
**Warning signs:** A previously-working agent binds no write tool / loses `report_task_complete`; `_build_runner_tools` grep must hit 0 (F2 gate) but bindings identical.

### Pitfall 6: Hook firing leaks events into snapshots (D-09)
**What goes wrong:** Binding `secret_scan`/`otel_tracing` to lifecycle events emits new events that appear in the characterization multiset.
**Why it happens:** Hooks fire at `before_write`/`post_task`/`*` — if they yield engine events, the snapshot changes.
**How to avoid:** `otel_tracing` is non-blocking and emits OTel spans/`hook_runs` rows — NOT engine WS events (so the multiset is unchanged). `secret_scan` blocking is additive (only halts on a real secret, which no characterization run carries). New `validator_result`/`gate_*` WS events are additive-only (SPEC API-03). Confirm the existing lifecycle points (`before_write` ≈ the runner's tool-call/write events; `post_task` ≈ the per-task loop in `task_loop`; `before_step` ≈ the engine dispatch loop at engine.py:1011) so hooks bind WITHOUT adding events to existing runs.
**Warning signs:** Snapshot multiset gains an event on a non-secret-bearing run.

## Code Examples

### Trust check slots into the compiler (D-02)
```python
# agents/workflows/compiler.py — the EXISTING reference-validation seam (INV-4).
# compile(manifest, registry) already validates EVERY reference via is_registered:
#   compiler.py:161  if not registry.is_registered("strategy", strategy): raise CompilerError(...)
#   compiler.py:166  if not registry.is_registered("gate", gate): raise CompilerError(...)
#   compiler.py:171  if not registry.is_registered("validator", v): raise CompilerError(...)
# D-02: add a trust context (manifest source: file|db, default trusted) threaded into compile();
# when source is user/db, ALSO check registry.is_user_allowed(kind, name) + owner allow-list.
# Default trust = trusted for the 15 file-backed manifests → Phase-4/7 compile parity holds
# (no existing manifest newly fails). The check slots in at the SAME per-reference site.
```

### The engine gate seam (D-03)
```python
# engine.py:1011-1041 — the per-step dispatch loop (the gate-evaluation seam):
for i, spec in enumerate(ordered_agents):
    step = _steps_by_agent.get(spec.id)
    # [NEW D-03] pre-step gates evaluate HERE (security/approval block before the strategy runs)
    strategy = _registry.resolve("strategy", strategy_name)
    async for event in strategy.run(step, ectx):
        yield event
    post_step_name = getattr(step, "post_step", None)
    if post_step_name:
        await _registry.resolve("post_step", post_step_name).run(step, ectx)
    # [NEW D-03] post-step gates (validation) evaluate HERE
# engine.py:1732 — the EXISTING human gate (GATE-03 parity — register "human" → THIS, unchanged):
if self._should_gate(spec, ectx):
    async for gate_event in self._run_review_gate(...):  # emits review_gate_* (engine.py:2078)
```

### Validator wraps the heavy check, reached via the handle (D-04)
```python
# app/agents/validators/html_static.py (NEW) — lives app-side (heavy dep), self-registers:
from agents.capabilities.base import Validator           # ← port import, import-linter LEGAL
from agents.capabilities.registry import register        # ← the new @register (D-01)

@register("validator", "html_static")
class HtmlStaticValidator:                                # satisfies Validator Protocol (base.py:54)
    name = "html_static"
    async def validate(self, target) -> list:             # target = DeliverableContext
        # heavy dep reached via the handle, NOT a kernel import:
        result = target.runner.static_check(target.path)  # kernel_services.py:126
        return _to_issues(result)                         # P0–P3 severity mapping
# The kernel/task_loop resolve("validator","html_static") and call .validate — never import app.
```

### Additive migration mirrors RunCapabilities (D-10)
```python
# app/models/validation_results.py (NEW) — mirror run_capabilities.py exactly:
class ValidationResult(Base):
    __tablename__ = "validation_results"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01 (D-10)
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    step = Column(String, nullable=False)            # §18 index (run_id, step)
    # validator name, severity (CRITICAL/HIGH/MEDIUM/LOW), attempt, issues JSON ...
# Alembic 0016 down_revision = "0015" (head — verified alembic/versions/ tops out at 0015).
# Writes go through agents/authz.py:58 ScopedStore (owner/ws from ExecutionContext at write time).
```

### `/api/capabilities` matches the existing auth pattern (D-11)
```python
# app/api/capabilities.py (NEW) — match workflows.py:160-162 exactly:
from app.core.dependencies import get_current_user
router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])
@router.get("")
async def list_capabilities(current_user: User = Depends(get_current_user)):
    # return registry palette: (kind, name, user_allowed, config schema) incl runtimes/skills/hooks/models
# Register in app/main.py alongside workflows_router (main.py:148). WS events flow through
# the generic forward (websocket.py:595 `{"type": event["type"], ...}`) — no websocket.py edit
# needed for NEW event TYPES.
```

## State of the Art

| Old Approach (current tree) | Phase-8 Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Explicit `install()`/`_register_builtins()` (registry.py:80) | `@register` decorator + `discover()` | This phase (D-01) | `install()` DELETED (INV-12); self-registration |
| Name-only registry (`_KNOWN`, no trust) | `user_allowed` per-capability trust flag | This phase (D-02) | User/DB manifests validated against trust |
| `human` gate inline only; `Validation_Gate` dead (loader.py:355) | `GateHandler` registry: human/validation/approval/security | This phase (D-03) | First-class registered gates |
| `static_check`/`render_check` plain functions; HTML-hardcoded fix-loop | Registered `Validator`s + generic `FixPolicy` loop | This phase (D-04/D-06) | Any deliverable validates; severity mapping |
| Factory hardcoded F1–F5 | PromptAssemblyPolicy + tool/skill/hook providers + AgentRuntimeAdapter | This phase (D-08) | F1–F5 deleted; R12 fixed |
| Prompt-only hooks (factory.py:230-245 "Active Behavioral Hooks") | Executable `HookHandler` + `behavioral` non-executable sub-type | This phase (D-09) | Hooks fire + persist; legacy block survives |

**Deprecated/outdated this phase deletes:**
- `factory.py` F1 (`blocks.append` :174-255), F2 (`_build_runner_tools` :384-446), F3 (`_inject_skills`/`_inject_hooks` :220-245), F4 (constitution no-op :258-306).
- `deep_agent_runner.py:240` hardcoded `create_deep_agent` → moves inside `AgentRuntimeAdapter`.
- `registry.py:80 install()`/`_register_builtins`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | OTel is the right lib for `otel_tracing`; logging-only may suffice for "non-blocking span + hook_runs row" | Supporting Stack / D-09 | If real OTLP export is required and only logging is built, OBS-02 acceptance ("emits a span") may be judged unmet — planner should confirm span fidelity bar |
| A2 | `discover()` importing `app/agents/validators/` is the trigger for app-side self-registration (vs a separate app-side hook the engine fires) | Pattern 3 / D-04(1) | If a separate hook is chosen, `discover()` stays kernel-pure and the engine triggers app-side registration at run entry — either is import-linter-legal; planner's discretion (CONTEXT line 129) |
| A3 | Constitution pre-warm-at-run-entry is lower-risk than await-in-running-loop | Pitfall 3 / D-08 | If pre-warm misses a code path that builds a runner outside run entry, the constitution could still be dropped — the new in-prod test is the gate |
| A4 | The existing characterization runs carry NO Constitution (so F4 fix keeps snapshots byte-identical) | Pitfall 3 | If any snapshot run sets a Constitution, the F4 fix WOULD change bytes — verify before the F4 plan (grep the characterization fixtures for constitution) |
| A5 | `Workspace.ExecutionPolicy` enforcement point can be wired without the `LocalSandboxRuntime` impl (Phase 9) | D-07 | If `ExecutionPolicy` has no host to attach to yet, the "exec denied regardless" check may need a stub enforcement point — SPEC says wire the point only |
| A6 | The `validation` gate's failure policy default (warn-non-critical/block-critical) maps cleanly onto the P0–P3 severity function | D-06/Q25 | If severity semantics differ, the gate could block/warn incorrectly — single mapping function (VALID-03) must be the source of truth |

**This table is non-empty:** these 6 assumptions need confirmation during planning/discuss — A1 (OTel fidelity), A4 (constitution-in-snapshots) and A5 (ExecutionPolicy host) are the highest-impact.

## Open Questions

1. **OTel export fidelity (A1 / D-09)**
   - What we know: no OTel dep in the tree; SPEC says "OpenTelemetry-style spans/logs", "emits a span + hook_runs row", non-blocking.
   - What's unclear: whether a real OTLP exporter (endpoint + SDK) is required this phase or a structured-logging span analog satisfies OBS-02.
   - Recommendation: plan for `opentelemetry-sdk` + a console/OTLP exporter behind config; if no collector is available, a logging exporter still emits a span object + `hook_runs` row. Gate the install behind `checkpoint:human-verify`.

2. **AgentRuntimeAdapter location vs banned-pattern allow-list (D-08/F5)**
   - What we know: `_ALLOWED_CREATE_DEEP_AGENT = {"app/agents/deep_agent_runner.py"}` (test_banned_patterns.py).
   - What's unclear: whether the adapter is a new `agents/capabilities/runtimes/langchain_deepagents.py` (which would call `create_deep_agent` → needs allow-list update + may cross import-linter if it imports app) or stays inside `deep_agent_runner.py`.
   - Recommendation: keep the `create_deep_agent` CALL inside `deep_agent_runner.py` (allow-list stable, import-linter unaffected); the `AgentRuntimeAdapter` capability *selects/wraps* `DeepAgentRunner` from `agents/capabilities/runtimes/` without itself calling `create_deep_agent`. Confirm the import-linter still passes (the runtime capability must reach `DeepAgentRunner` via the handle, not a direct app import).

3. **revision_validation: gate or post_step (D-06)**
   - What we know: it's a post_step today (post_steps/revision_validation.py); the candidate to re-express as `gates:[validation]`.
   - What's unclear: whether re-expression holds revision-snapshot parity.
   - Recommendation: keep it a post_step unless `test_characterization_prototype_revision.py` proves byte/event-identical as a gate. Low-value churn risk — defer the re-expression if parity is uncertain.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python3.11` | Dev runtime (no venv) | ✓ (project standard) | 3.11 | — |
| Alembic | Migration `0016` | ✓ | (in tree, head 0015) | — |
| PostgreSQL | New tables + ScopedStore | ✓ | (Phase-5 tables live) | InMemory dev (existing) |
| Chromium / Playwright | `html_render` validator | ✓ locally, degrades to skip | — | `render_check` returns `available=False` (render_check.py:65) |
| `opentelemetry-sdk` | `otel_tracing` hook (OBS-02) | ✗ | — | logging-only span analog (A1) |

**Missing dependencies with no fallback:** none (OTel has a logging-only fallback).
**Missing dependencies with fallback:** `opentelemetry-sdk` — install (verify first) or use a structured-logging span analog.

## Validation Architecture

> nyquist_validation is enabled (config.json `nyquist_validation: true`). This section maps each requirement group to its observable proof + sampling point.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (with `pytest.mark.asyncio` for async caps) |
| Config file | `backend/pyproject.toml` ([tool.pytest], [tool.importlinter], [tool.vulture]) |
| Quick run command | `cd backend && python3.11 -m pytest tests/agents/test_<target>.py -x` |
| Full suite command | `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v` |
| Parity gate (every plan) | `cd backend && python3.11 -m pytest tests/agents/test_characterization_*.py` (the 5 pipelines) |
| Gate CI guards | `test_migration_ledger.py` (F1–F5 ratchet), `test_banned_patterns.py` (INV-13/INV-1/F5), `lint-imports` (import-linter) |

### Phase Requirements → Test Map
| Req group | Behavior to prove | Test Type | Automated Command | File Exists? |
|-----------|-------------------|-----------|-------------------|-------------|
| CAP-01/02 (self-reg) | `@register`+`discover()` resolvable, no central if/elif, idempotent | unit | `pytest tests/agents/test_registry_capabilities.py -x` | ✅ (update `_EXPECTED_NAMES` + count) |
| CAP-03 (trust) | user-trust compile of non-`user_allowed` cap raises naming error; file manifest compiles | unit | `pytest tests/agents/test_compiler*.py -k trust -x` | ❌ Wave 0 (new trust test) |
| GATE-01 (registry) | 4 gate kinds resolve; `security`+`exec` blocks; `approval` pauses | unit | `pytest tests/agents/test_gates.py -x` | ❌ Wave 0 |
| GATE-02 (validation gate) | P0 blocks; P2 emits `validation_warning`+proceeds | unit | `pytest tests/agents/test_gates.py -k validation -x` | ❌ Wave 0 |
| GATE-03 (human parity) | identical `review_gate_*` sequences | characterization | `pytest tests/agents/test_characterization_prototype.py -x` | ✅ (no re-baseline) |
| TOOLPERM-01/02/03 | effective = intersection; AGENT.md only lowers; existing agents bind identical sets | unit | `pytest tests/agents/test_create_runner.py -x` + new perm test | ✅ + ❌ Wave 0 (intersection test) |
| VALID-01..04 | registry-run validators; generic `FixPolicy` loop; P0–P3 mapping; `validation_results` rows | unit + characterization | `pytest tests/agents/test_validators.py tests/agents/test_characterization_prototype.py -x` | ❌ Wave 0 + ✅ |
| VALID-05 (Tier#4/5/6) | each registered, runs, ≥1 test manifest; `design_quality` non-blocking | unit | `pytest tests/agents/test_validators.py -k tier -x` | ❌ Wave 0 |
| AGENTRT-01/02 (F5) | `create_deep_agent` only in allow-listed adapter | gate | `pytest tests/agents/test_banned_patterns.py -x` | ✅ |
| AGENTRT-03 (F1) | `blocks\.append`→0; prompts byte-identical | gate + characterization | `pytest tests/agents/test_migration_ledger.py tests/agents/test_characterization_*.py -x` | ✅ |
| AGENTRT-04 (F2) | `_build_runner_tools`→0; identical tool sets | gate + unit | `pytest tests/agents/test_create_runner.py tests/agents/test_migration_ledger.py -x` | ✅ |
| AGENTRT-05/SKILL-01 (F3) | `_inject_skills\|_inject_hooks`→0; behavioral block still renders | gate + unit | `pytest tests/agents/test_guardrails.py tests/agents/test_migration_ledger.py -x` | ✅ |
| AGENTRT-06 (F4/R12) | DB Constitution injected under running loop | unit (NEW) | `pytest tests/agents/test_constitution_prod.py -x` | ❌ Wave 0 |
| HOOK-01..04/OBS-02 | `secret_scan` blocks+writes row; `otel_tracing` fires non-blocking+span+row; unpermissioned hook unbound | unit | `pytest tests/agents/test_hooks.py -x` | ❌ Wave 0 |
| PERSIST (D-10) | 3 tables exist additively; rows carry owner+ws | migration + unit | `pytest tests/unit/test_migrations.py -x` (or alembic upgrade head) | ❌ Wave 0 |
| API-02/03/06 | `/api/capabilities` palette+auth; additive WS events; panels render | unit + (frontend) | `pytest tests/unit/test_capabilities_api.py -x` | ❌ Wave 0 |
| INV-3 (all plans) | 5 snapshots byte-identical + semantic-event parity | characterization | `pytest tests/agents/test_characterization_*.py -x` | ✅ |

### Sampling Rate
- **Per task commit:** the targeted unit test for that capability + `test_migration_ledger.py` + `test_banned_patterns.py` (fast gates).
- **Per wave/plan merge:** full `test_characterization_*.py` (5 pipelines) + `lint-imports` — the INV-3 + hexagonal gates. **Run in a CLEAN session** (the `test_strategies` pollution; fix the fixture in 08-01).
- **Phase gate:** `pytest tests/agents/ tests/unit/ -v` green + all F1–F5 ledger rows ☑ + import-linter green + banned-pattern green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/agents/test_gates.py` — GATE-01/02 (security/approval/validation handlers + outcomes)
- [ ] `tests/agents/test_validators.py` — VALID-01..05 (registry-run, FixPolicy loop, severity, Tier#4/5/6)
- [ ] `tests/agents/test_hooks.py` — HOOK-01..04/OBS-02 (secret_scan block, otel span, permission gating)
- [ ] `tests/agents/test_constitution_prod.py` — AGENTRT-06 (DB Constitution under running loop)
- [ ] `tests/agents/test_compiler*.py` trust cases — CAP-03 (user_allowed naming error)
- [ ] `tests/unit/test_capabilities_api.py` — API-02 (`/api/capabilities` palette + auth + scopes)
- [ ] `tests/unit/test_migrations.py` (or alembic upgrade-head smoke) — PERSIST (3 tables, owner+ws)
- [ ] **Update existing:** `test_registry_capabilities.py` `_EXPECTED_NAMES` + `test_registered_count_is_exactly_sixteen` (new kinds/names bump the count)
- [ ] **Fix existing:** `test_strategies.py` autouse `_IMPLS` save/restore reset fixture (D-12 fold)
- [ ] Framework install: `pip install opentelemetry-api opentelemetry-sdk` (verify first) — only if real OTLP export is chosen

## Security Domain

> security_enforcement is enabled (config.json `security_enforcement: true`, ASVS level 1, block_on: high). This phase is squarely security-relevant: it builds the trust model, least-privilege tool perms, and the `security` gate.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Hexagonal ports & adapters; import-linter enforces kernel→ports direction; capabilities never import `app`/kernel |
| V2 Authentication | yes | `/api/capabilities` uses `Depends(get_current_user)` (matches workflows.py:162) — JWT-only, same posture as every endpoint |
| V4 Access Control | yes | `ScopedStore` default-deny owner/workspace scoping (authz.py:58); `user_allowed` trust flag keeps `exec`/`secrets`/`spawn` off the user palette (never user-grantable until N3); IDOR-safe reads (Phase-5 precedent) |
| V5 Input Validation | yes | Compiler is a pure no-DSL data transform (compiler.py — no eval/exec, strict-key rejection); a capability name that isn't registered simply fails lookup; manifest values never evaluated |
| V6 Cryptography | no | No crypto introduced this phase |
| V7 Error Handling/Logging | yes | `otel_tracing` observability (OBS-02); `hook_runs`/`gate_events`/`validation_results` audit rows; capabilities swallow their own errors (never abort the run) |
| V12 Files/Resources | yes | `secret_scan` hook (read_files, blocking) scans `before_write`/`pre_commit`; `RunSandbox` traversal-proof (existing) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| User-authored manifest references a privileged capability (exec/secrets/spawn) | Elevation of Privilege | `user_allowed=False` trust flag → compile error naming the cap (CAP-03/D-02); the seam that keeps powerful caps off the user palette |
| Manifest smuggles control flow / code-exec into a capability name | Tampering / EoP | No-DSL compiler (INV-5) — `resolve` is a static dict lookup over `_KNOWN`-validated names; a non-registered name fails lookup; no eval/exec (compiler.py:14-21, registry.py:17-21) |
| Over-privileged tool binding (a step gets write/exec it wasn't granted) | EoP | `effective = intersection(owner_allow_list, workflow_ceiling, step_grant)`; AGENT.md may only LOWER; enforced at `_build_runner_tools` + `ExecutionPolicy` (TOOLPERM/D-07) |
| `exec`/`network`/`secrets` accidentally enabled | EoP | `security` gate default-denies; defaults OFF (plan.py:53-61); a `gates:[security]` step requesting exec blocks (exec stays OFF until N3/Phase 10) |
| Secret written to a deliverable | Information Disclosure | `secret_scan` hook (blocking, read_files) at `before_write`/`pre_commit` writes a `hook_runs` row `outcome=block` (HOOK-01) |
| Cross-owner data read of validation/gate/hook rows | Information Disclosure | New tables carry `owner_id`+`workspace_id`; writes/reads via `ScopedStore` default-deny; cross-owner → 404 (Phase-5 precedent) |
| Kernel reaching into `app.*` for heavy deps (boundary erosion) | Tampering (architecture) | import-linter forbids `agents.capabilities → app`; validators reach heavy deps only via `ctx.runner` handle (D-04) |

## Project Constraints (from CLAUDE.md / backend/CLAUDE.md)

- **INV-13 (deepagents-only):** canonical `from deepagents import create_deep_agent`; `AgentRuntimeAdapter` WRAPS, never replaces; `create_deep_agent` called only in the allow-listed `app/agents/deep_agent_runner.py` (test_banned_patterns.py:70). No hand-rolled deep agent / local `deepagents`/`langchain_deepagents` module / re-implemented loop.
- **INV-3 (strict, this phase):** existing workflows byte-identical deliverables + semantic event parity; 5 characterization snapshots UNCHANGED (no re-baseline); new events additive only.
- **INV-12 (move-don't-copy):** F1–F5 + `install()` DELETED in-plan once the abstraction proves parity; deletion is the exit gate; ledger F1–F5 rows flip ☑.
- **INV-9 (least-privilege):** read_files ON; everything else OFF/none; AGENT.md only lowers.
- **INV-5 (no DSL):** manifests are pure data; control flow lives in strategies; compiler is thin (compiler.py).
- **Hexagonal / import-linter:** kernel imports only ports + the resolve seam + the `KernelServices` handle; `agents.capabilities`/`agents.workflows` never import `agents.execution_engine` or `app`; `app → agents.capabilities` is permitted.
- **Persistence:** additive migrations only; every new table carries `owner_id`+`workspace_id`; head is `0015` → `0016`.
- **Commit scopes (backend/CLAUDE.md):** `factory`/`runner`/`registry`/`engine`/`tests`/`loader`/`tools`/`sandbox` — scoped prefix `<type>(<scope>): <desc>`; subject < 72 chars; imperative.
- **Dev runtime:** `python3.11`, NO venv; `cd backend && python3.11 -m pytest tests/agents/ tests/unit/ -v`.
- **Branch/PR:** off `feature/003-workflow-engine-decoupling`, NEVER `main`. GSD workflow enforced — no direct edits outside a GSD command.
- **GSD phase-naming gotcha (MEMORY):** never start a phase/plan name with a digit-led token.

## Sources

### Primary (HIGH confidence — read directly this session)
- `agents/capabilities/registry.py` — `_KNOWN` (16), `install()`/`resolve`/`is_registered` (:46-192); the D-01 evolution seam + impl-free-at-compiler-import contract (:70-74)
- `agents/capabilities/base.py` — `Validator` (:54), `GateHandler` (:105), `PostStep` (:87) ports
- `agents/factory.py` — F1 (:174-255), F3 (:220-245), F4 (:258-306, running-loop branch :282-292), F2 (:384-446), `create_runner` SYNC (:69)
- `app/agents/deep_agent_runner.py:240` — F5 `create_deep_agent`
- `agents/execution_engine/engine.py` — dispatch seam (:1011-1041), human gate (:1732, `_run_review_gate` :2043, `_should_gate` :2020), `_run_validation_fix_loop` survivor (:1827)
- `agents/execution_engine/kernel_services.py` — `static_check`/`render_check` (:126-132), `run_validation_fix_loop` (:274), `compute_revision_baseline` (:135), `persist_task_html` (:332)
- `agents/capabilities/strategies/task_loop.py` — unconditional `runner.run_validation_fix_loop` (:292), deliverable de-hardcode (:159)
- `agents/capabilities/post_steps/revision_validation.py` — the D-06 gate-vs-post_step candidate
- `agents/workflows/plan.py` — `ToolPermissions` (:45-61), `FixPolicy` (:100-105), `Step` forward fields (:214-241), `DeliverableSpec` (:143-164)
- `agents/workflows/compiler.py` — INV-4 reference validation (:110-211), the D-02 trust-check seam
- `agents/loader.py:101,355` — `gate` field; `Validation_Gate` accepted-but-dead
- `app/models/run_capabilities.py` — the §18 additive-table + owner/ws precedent (skills/hooks reserved "Phase 8")
- `agents/authz.py:58` — `ScopedStore` default-deny
- `app/api/workflows.py:160-162`, `runs.py:101-104`, `main.py:148` — the `/api/capabilities` auth + registration pattern
- `app/api/websocket.py:94,595,719` — app imports a capability module (import direction proof); generic event forward
- `backend/pyproject.toml` — import-linter contracts (forbid `agents.capabilities → app`); vulture allow-list
- `tests/agents/test_registry_capabilities.py:30-78` — `_EXPECTED_NAMES`, impl-free count assertion
- `tests/agents/test_strategies.py:333-361` — the global-registry pollution (D-12 fold)
- `tests/agents/test_banned_patterns.py:70-95` — `_ALLOWED_CREATE_DEEP_AGENT`, INV-1/INV-13 ratchets
- `tests/agents/test_migration_ledger.py:60,130` — F1–F5 ratchet
- `specs/003-workflow-engine-decoupling/migration-ledger.md:83-87` — F1–F5 rows (☐ → ☑ this phase)
- `.planning/phases/07-.../deferred-items.md:49-68` — test-isolation pollution detail
- `.planning/config.json` — nyquist_validation/security_enforcement enabled
- `08-CONTEXT.md` (D-01..D-12 + directives), `08-SPEC.md` (16 reqs/29 IDs/20 acceptance), `STATE.md` (Phase-7 closure)

### Secondary (MEDIUM confidence)
- `frontend/src/components/{workflow,library,results}/` — directory listing only (AgentLibrary.tsx, ReviewGatesSection.tsx, results surfaces) — the panels extend these (D-11); not deep-read

### Tertiary (LOW confidence — needs validation)
- OpenTelemetry as the `otel_tracing` lib (A1) — training knowledge; verify package split + exporter on PyPI before install (no OTel dep in the tree today)

## Metadata

**Confidence breakdown:**
- Standard stack / existing seams: HIGH — every field/port/handle method cited at `file:line`; the inert forward surface is already present.
- Architecture (D-04 import direction, D-01 discover timing, D-03 gate seam): HIGH — proven against import-linter config + live import sites + the dispatch loop.
- Parity risks (D-06, D-08): HIGH on *where* the risk is (named snapshots/tests); MEDIUM on whether each re-point holds parity (requires running the snapshots during execution — that's the gate, not researchable offline).
- OTel (D-09): MEDIUM — the only new external dep; logging-only fallback de-risks it.
- Frontend (D-11): MEDIUM — directories confirmed, components not deep-read (data-bearing panels extend existing surfaces).

**Research date:** 2026-06-09
**Valid until:** ~2026-07-09 (stable brownfield internals; OTel package details may drift — re-verify before install)

## RESEARCH COMPLETE
