# Phase 22: Capability Surfacing and User Empowerment — Universal Runtime UX Completeness - Research

**Researched:** 2026-06-14
**Domain:** Brownfield refactor — capability-registry surfacing + untrusted-manifest compile/launch wiring (Python · FastAPI · PostgreSQL · LangGraph · React/TS)
**Confidence:** HIGH (every canonical-ref anchor verified against live code this session; all decisions grounded in read source, not training knowledge)

## Summary

Phase 22 is a SURFACE-AND-WIRE phase: it adds no new capability kinds. It exposes the already-live capability registry through the existing `GET /api/capabilities` endpoint, builds one embedded composer palette that consumes it, activates the built-but-dormant `trust="user"` compile path at SAVE and LAUNCH, materializes three accepted-but-dropped compiler step keys (`model:`/`retry:`/`injects:`), lands four UX data-faithfulness fixes, records two product decisions in REQUIREMENTS.md, and produces a per-item live-Bedrock evidence record (deferred to milestone-end per the defer-live-verification convention).

I verified all 24 canonical-ref anchors against the live tree. **The backend anchors are essentially intact** — `_KNOWN`/`register`/`is_user_allowed` (registry.py), `CapabilityEntry`/`config_schema` stub/`_KNOWN` loop (capabilities.py), `_ALLOWED_STEP_KEYS`/the two compiler constructors/the trust check (compiler.py), `Step.model/retry/injects` + `CompiledWorkflow.model` (plan.py), `ModelResolver` tiers 2/4 (model_policy.py), the RESUME-02 retry wrapper + deliverable mimetype emit (engine.py), the dormant nullable `manifest_json` column (workflow_definition.py), and the absence of mimetype columns on `WorkflowRun` (workflow.py) all match within a line or two. **Three anchors drifted and are flagged below** (the compiler trust check region, the engine post_step seam, and the FE `api.ts` line range) — none are blocking; the planner should write plans against the CURRENT lines in this document.

**One material discovery the planner MUST honor:** Phase 18 (ISS-014) **DELETED** the standalone `CapabilityPalette.tsx` as an orphaned INV-12 dual-impl and relocated `AgentModelPicker` into the live `AgentsPopup`. CONTEXT D-01 already chose the embedded-palette path — the planner must build the palette INSIDE `AgentsPopup`, and must NOT resurrect or recreate a standalone palette component (that would re-introduce the exact dual-surface Phase 18 removed). This is the single biggest landmine.

**Primary recommendation:** Take D-16's "materialize-and-consume" path for `injects:` (it is provably INV-3-safe — see WIRE-03 below), extend `@register` with two optional kwargs for SURF-02 metadata, reuse the dormant `manifest_json` column for EMP-03 (zero migration), add one additive migration `0022` for the two `WorkflowRun` mimetype columns (UXFIX-02), and gate every change behind the targeted parity/gate suite + `lint-imports` + the SC-001 banned-pattern grep that already exist as CI gates.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01 .. D-24, all user-confirmed 2026-06-14)

**Capability palette — placement & shape (SURF-01, SURF-03, EMP-02)**
- **D-01:** ONE grouped capability palette panel **embedded inside the `AgentsPopup` composer** — NOT a separate standalone browse view. Single surface satisfying SURF-01 + SURF-03 + EMP-01. One palette = INV-12-clean.
- **D-02:** **Reuse the `AgentModelPicker` fetch/loading/error/empty shell** for the palette's `GET /api/capabilities` fetch.
- **D-03:** Render **grouped by kind**; each row shows name / description / `user_allowed` flag / security-gated flag / config schema — driven entirely by the fetched payload. **No hardcoded capability-name array** in the palette source (SC-001 grep target = 0).
- **D-04 (EMP-02):** `user_allowed=False` capabilities render **visible-but-locked** — never user-composable.

**Per-step lever surface (EMP-01, EMP-04)**
- **D-05:** Attach per-step levers via a **per-agent "Advanced" expander** on each agent row in `AgentsPopup`. Treat **agent ≈ step**. Expose at minimum: a validator, a human/validation gate, a non-default model, retry (plus deliverable type / context provider / compaction / fan-out / limits where user-allowed).
- **D-06:** Reuse the location where the **per-agent model picker already lives** (relocated into `AgentsPopup` in P18 / ISS-014).
- **D-07 (EMP-04):** Selecting a capability that requires a coupled gate → composer **auto-attaches the required gate inline**; the compiler's coupling checks stay enforced as the server-side backstop.

**Capability metadata source (SURF-02)**
- **D-08:** Each capability **self-describes via the registry** — add optional `description` + `config_schema` on the `@register(...)` decorator. **No static metadata map in the API layer.**
- **D-09:** Thin one-method Protocol ports stay unchanged; metadata is **additive-optional**. `config_schema` populated per-capability where applicable, legitimately `{}` for caps with no config. Replaces the literal `{}` stub.
- **D-10:** `/api/capabilities` extension is **additive** — preserve API-02 contract, `Depends(get_current_user)`, permission scopes. Extend `test_capabilities_api.py`.

**Richer-selection persistence (EMP-03)**
- **D-11:** **Reuse the dormant `manifest_json` column** — store a compact per-step capability-selections map. **Zero new migration** for EMP-03.
- **D-12:** Persisted selections are **owner-scoped**, IDOR→404, **re-validated with `trust="user"` at SAVE and at LAUNCH**.
- **D-13:** Launch reaches compiler/engine through the **existing run path** — no new run endpoint, no kernel branch. Extends P21 launch wiring at `/api/user-workflows` save + the `websocket.py run_pipeline` re-validation site.

**Compiler latent-key materialization (WIRE-01/02/03)**
- **D-14 (WIRE-01):** Materialize top-level `model:` → `CompiledWorkflow.model`, per-step `model:` → `Step.model`.
- **D-15 (WIRE-02):** Materialize per-step `retry:` → `Step.retry`.
- **D-16 (WIRE-03 — DECIDED: materialize-and-consume):** Compile per-step `injects:` → `Step.injects`; engine consumes it merged with AGENT.md injects at the factory seam — generic, no workflow-name branch. **Fallback (apply ONLY if materialize-and-consume cannot be proven INV-3-safe):** reject-loudly — remove `injects` from `_ALLOWED_STEP_KEYS` and raise `CompilerError`.
- **D-17 (WIRE-03 test):** Parametrized test enumerates every `_ALLOWED_STEP_KEYS` entry; each is either reflected on the compiled `Step`/`CompiledWorkflow` or raises `CompilerError`. INV-5 preserved.

**UX / data-faithfulness (UXFIX-01..04)**
- **D-18 (UXFIX-01):** Launchable manifests carry an authored `display_name:`. Keep the P20 BE coalesce fix intact.
- **D-19 (UXFIX-02):** Persist `deliverable_mimetype` + `deliverable_filename` as additive columns on `WorkflowRun`; drive history-reopen from persisted values. Both stay in `_VOLATILE_STRIP_KEYS`.
- **D-20 (UXFIX-03):** Make the data-driven `WorkflowCatalog` the default home landing; the hardcoded `CreationHub.WORKFLOWS` array no longer drives the default landing.
- **D-21 (UXFIX-04):** Make the generic mimetype renderer the PRIMARY dispatch in `PreviewPanel.tsx`; the 4 first-party types become registered entries the generic dispatcher routes to — no visual regression.

**Product decisions (DECIDE-01/02 — LOCKED in SPEC)**
- **D-22 (DECIDE-01 / N9):** Artifact retention = **keep-by-default**; `run_ttl`/`days:N` opt-in. Update REQUIREMENTS.md ART-04; reconcile the 3 stale "confirm" labels (REPO-02 N6/N10, REPO-04 N5/N7, FANOUT-05 N2).
- **D-23 (DECIDE-02 / N11):** Premium-model policy = **open to all tiers**; Haiku default + ordered fallback chain. Update MODEL-05; **drop the `user_allowed` tier filter at `AgentModelPicker.tsx:76`**.

**Live verification (LIVE-01)**
- **D-24:** **Defer the consolidated live-Bedrock pass to milestone-end**; phase completes on offline evidence. Live pass runs on AWS `default` profile (acct 473293451041) with `claude-haiku-4-5`. Per-item evidence record for: COMPACT-03 · P6 CR-02 · P8 OTLP · P13 F1/F4/F5 · P14 SC4 · P16 SC1/SC2 · P19 ISS-004.

### Claude's Discretion (settled in this research — do not re-ask the user)
- **`@register` metadata mechanism:** decorator kwargs `description=`/`config_schema=` (consistent with `user_allowed=`). **Settled: decorator kwargs.** See SURF-02 below.
- **`manifest_json` JSON shape:** compact `{step → {validators, gates, model, retry, ...}}` selections map compiled at launch. **Settled: compact selections map.** See EMP-03 below.
- **`config_schema` representation:** JSON-Schema-lite object vs minimal field-spec list per kind. **Settled: JSON-Schema-lite object** (matches the `config_schema: dict` field type already declared; most caps return `{}`).
- **Composer expander interaction details** — planner's call; lever rows render per agent, retry/model/validator/gate at minimum.
- **Security-gated flag** — derived, not a separate stored boolean. **Settled: derive from `user_allowed=False` (the registry already tracks `_TRUST`); expose as an additive `security_gated: bool` field on `CapabilityEntry`.** Test-assertable, no second source of truth. See SURF-02.

### Deferred Ideas (OUT OF SCOPE)
- Exhaustive per-capability compose+launch coverage — follow-up beyond representative-per-lever.
- ECS/container `RuntimeEnvironment` backend — designed-only this milestone.
- Enabling code-exec / `spawn_subagents` / `security` gate for users — stays engineer-only (visible-but-locked).
- New capability kinds / registry entries — surfaces the existing registry only.
- CTX-04 (`run_revision` retirement) — intentional VOID.
- Nyquist VALIDATION.md backfill (20 partial/missing phases) — `/gsd-validate-phase`, not here.
- ISS-018 (`hexaware-srini` entitlement) resolution — external IT escalation.
- A standalone read-only "Capabilities" reference/catalog view — rejected for this phase (D-01 chose the embedded palette).
</user_constraints>

<phase_requirements>
## Phase Requirements

> These 17 IDs are NEW families that the plan must ADD to `.planning/REQUIREMENTS.md` at plan time (they are in the ROADMAP/SPEC but not yet in REQUIREMENTS.md).

| ID | Description | Research Support |
|----|-------------|------------------|
| SURF-01 | Capability palette reads the live registry, grouped by kind, no hardcoded name list | `GET /api/capabilities` live-enumerates `_KNOWN` (capabilities.py:106-118 verified); embed in `AgentsPopup` (D-01) reusing `AgentModelPicker` fetch shell (D-02). **Do NOT recreate the deleted `CapabilityPalette.tsx`.** |
| SURF-02 | `/api/capabilities` supplies `description` + security-gated flag + populated `config_schema` additively | Extend `@register` with `description=`/`config_schema=` kwargs (registry.py:167-191); add `security_gated` (derived from `_TRUST`) + `description` + `config_schema` to `CapabilityEntry` (capabilities.py:56-64); replace the `{}` stub (capabilities.py:116). Extend `tests/unit/test_capabilities_api.py` (195 lines, exists). |
| SURF-03 | Composer shows a workflow's declared capabilities | Read the compiled plan via `GET /api/workflows/{id}` projection; render per-step declared caps in the embedded palette. |
| EMP-01 | Compose into user-allowed caps reaching the run path (validator + gate + model + retry) | Per-agent Advanced expander (D-05) in `AgentsPopup`; selection persists then flows through existing launch (`websocket.py run_pipeline`). Representative-per-lever bar (not exhaustive). |
| EMP-02 | Trust/tier gating in UI AND server; smuggled grants rejected at SAVE+LAUNCH | UI renders `user_allowed=False` as locked (D-04). Server: compile persisted selections with `trust="user"`; `_check_trust` (compiler.py:299-324) rejects not-`user_allowed` refs. Invoke at BOTH `user_workflows.py` save and `websocket.py` launch. |
| EMP-03 | Saved workflows persist richer per-step selections, owner-scoped, re-validated at launch | Reuse `manifest_json` (workflow_definition.py:39, nullable, dormant). Compact selections map. IDOR→404 via `_owned()`. Re-validate `trust="user"` at save+launch (D-12). |
| EMP-04 | Gate auto-attachment for caps that require one | Composer auto-attaches inline (D-07); compiler backstop is the exec⇒`gates:[security,approval]` check (compiler.py:458-465) + the validator/approval coupling. |
| WIRE-01 | Compiler materializes `model:` (top-level + per-step) | Pass `model=` through `CompiledWorkflow(...)` (compiler.py:231-244) and `Step(...)` (compiler.py:505-517). `ModelResolver` already reads tier 2 (model_policy.py:95) + tier 4 (model_policy.py:101). |
| WIRE-02 | Compiler materializes per-step `retry:` | Pass `retry=` through `Step(...)` (compiler.py:505-517). RESUME-02 wrapper live + gated on `step.retry.max_attempts>0` (engine.py:4513). |
| WIRE-03 | Per-step `injects:` consumed or fails loud; no silent no-op | Materialize-and-consume (D-16): pass `injects=` through `Step(...)`; merge into the factory injection seam (factory.py:310-315 / `_compose_injection` at factory.py:398). Provably INV-3-safe (goldens declare no per-step injects). Parametrized `_ALLOWED_STEP_KEYS` test (D-17). |
| UXFIX-01 | Catalog shows friendly `display_name` | `display_name` field exists (manifest.py:76); P20 BE coalesce fix must stay. |
| UXFIX-02 | `deliverable_mimetype`/`deliverable_filename` persist on the run row | Additive columns on `WorkflowRun` (workflow.py:13-69, currently absent). New migration `0022`. Emit already live (engine.py:2117-2128); keys already in `_VOLATILE_STRIP_KEYS` (_normalize.py:139-140). Drive reopen from persisted values, replacing `deriveDeliverableMimetype` (types/index.ts:342). |
| UXFIX-03 | Data-driven catalog is the home landing | `WorkflowCatalog` mounts at the `catalog` tab (DashboardLayout.tsx:1084-1093); `home` mounts `CreationHub` (DashboardLayout.tsx:1070-1079). Make catalog the default landing. |
| UXFIX-04 | Generic mimetype renderer is the PRIMARY dispatch | `PreviewPanel.tsx:557-570` — generic is fallback behind 4 first-party branches. Restructure to mimetype-dispatch table. `GenericDeliverablePreview` exists (src/components/preview/). |
| DECIDE-01 | ART-04 retention = keep-by-default | ART-04 at REQUIREMENTS.md:49 ("N9 — confirm"); reconcile REPO-02:107, REPO-04:109, FANOUT-05:123. |
| DECIDE-02 | MODEL-05 premium-open-to-all-tiers | MODEL-05 at REQUIREMENTS.md:64 ("N11 — confirm"); drop tier filter at AgentModelPicker.tsx:76. Fallback chain already exists (model_catalog cost_class; BE-MODEL-03 green). |
| LIVE-01 | Consolidated live-Bedrock evidence pass | Deferred to milestone-end (D-24); `default` profile (acct 473293451041), Haiku 4.5. Per-item record for 8 standing deferrals. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Capability palette rendering (SURF-01/03) | Frontend (React, `AgentsPopup`) | API (`GET /api/capabilities`) | Pure presentation of registry data; data lives in the API/registry tier |
| Capability metadata (SURF-02) | API (`capabilities.py`) | Registry (`registry.py` `@register`) | Metadata is registry-owned (self-describing caps); API projects it. NEVER a static API-layer map |
| Per-step lever composition UI (EMP-01/04) | Frontend (`AgentsPopup` Advanced expander) | — | Composer is a client surface; selections are reported upward |
| Trust gating UI (EMP-02 visible-but-locked) | Frontend | API (trust flag source) | UI affordance; the authoritative gate is server-side |
| Trust gating enforcement (EMP-02 reject smuggled) | Compiler (`_check_trust`) | API (save) + WS (launch) invoke it | Authoritative rejection is the compiler's CAP-03 check; UI gating is advisory only |
| Persistence of selections (EMP-03) | Database (`workflows.manifest_json`) | API (`user_workflows.py`) | Owner-scoped row; reuse dormant column |
| Compiler key materialization (WIRE-01/02/03) | Compiler (`compiler.py` two constructors) | Engine (consume retry/injects), ModelResolver (consume model) | Compiler is the data transform; engine/resolver are the runtime consumers |
| Run-row mimetype persistence (UXFIX-02) | Database (`WorkflowRun` + migration 0022) | Engine (emit, already live) + API (read) | Additive persistence of an already-emitted value |
| Catalog-as-home (UXFIX-03) | Frontend (`DashboardLayout`) | API (`GET /api/workflows`) | Pure routing/landing change |
| Generic renderer primary (UXFIX-04) | Frontend (`PreviewPanel`) | — | Client deliverable rendering |
| Product decisions (DECIDE-01/02) | Docs (`REQUIREMENTS.md`) | Frontend (DECIDE-02 picker filter removal) | Decisions are documentation; one FE behavior change |

## Anchor Verification Report

> Every canonical-ref file:line in 22-CONTEXT.md was checked against the live tree on 2026-06-14. **Plan against the CURRENT lines below**, not the CONTEXT lines, where they differ.

| Canonical ref (CONTEXT) | Status | Current line(s) | Note |
|--------------------------|--------|-----------------|------|
| `capabilities.py:56-64` CapabilityEntry | ✅ MATCH | 56-64 | `kind/name/user_allowed/config_schema={}` |
| `capabilities.py:116` `{}` config_schema stub | ✅ MATCH | 116 | literal `config_schema={}` in the loop |
| `capabilities.py:106-118` `_KNOWN` loop | ✅ MATCH | 106-118 | live `for kind, name in sorted(registry_mod._KNOWN)` |
| `registry.py:79-143` `_KNOWN` | ✅ MATCH | 79-143 | ~60 (kind,name) pairs; ~20 kinds |
| `registry.py:167-191` `register()` decorator | ✅ MATCH | 167-191 | `user_allowed` kwarg at 168; `_decorate` 185-189 — extend HERE for D-08 |
| `registry.py:336-346` `is_user_allowed`/`_TRUST` | ✅ MATCH | 336-346 | `_TRUST.get((kind,name), False)` at 346 |
| `compiler.py:65-86` `_ALLOWED_STEP_KEYS` | ✅ MATCH | 65-86 | includes `model`,`retry`,`injects`,`depends_on` |
| `compiler.py:231-244` workflow constructor | ✅ MATCH | 231-244 | `CompiledWorkflow(...)` — does NOT pass `model=` (WIRE-01 gap) |
| `compiler.py:~505` Step constructor | ✅ MATCH | 505-517 | `Step(...)` — does NOT pass `model/retry/injects/depends_on` (WIRE-01/02/03 gaps) |
| `compiler.py:~279-321 / :312-321` trust check | ⚠ DRIFTED | **299-324** | `_check_trust` is now at 299-324; the `is_user_allowed` rejection at **320-324**. (The `:279-321` region is now `_compile_limits` untrusted-lower check at 279-289.) |
| `plan.py:362` `Step.model` | ✅ MATCH | 362 | |
| `plan.py:368` `Step.retry` | ✅ MATCH | 368 | `RetryPolicy \| None` |
| `plan.py:369` `Step.injects` | ✅ MATCH | 369 | `list[str]` |
| `plan.py:408` `CompiledWorkflow.model` | ✅ MATCH | 408 | `ModelPolicy` default |
| `model_policy.py:96/101` ModelResolver tiers | ✅ MATCH | tier 2 @ **95**, tier 4 @ **101** | `step.model.model` at 95; `_workflow_model.model` at 101 |
| `engine.py:1840-1842` retry wrapper site | ✅ MATCH | 1840-1842 | dormant-comment site for RESUME-02 |
| `engine.py:4512-4513` retry gate | ✅ MATCH | 4513 | `if not (retry and getattr(retry,"max_attempts",0)>0)` |
| `engine.py:2117-2128` deliverable emit | ✅ MATCH | 2117-2128 | `deliverable_mimetype`/`deliverable_filename` emit |
| `engine.py:1666-1668` post_step seam | ⚠ DRIFTED | **1888-1890** | post_step resolve+run is now at 1888-1890 (`_registry.resolve("post_step", ...).run(step, ectx)`). The `:1666` region is unrelated. |
| `loader.py:102` injects (AGENT.md) | ✅ MATCH | 102 | `injects: list[str]` on `AgentSpec` |
| `factory.py:311-315` injection seam | ✅ MATCH | 310-315 | `spec.injects` read → `_compose_injection` (factory.py:398). WIRE-03 merge point. |
| `workflow_definition.py:39` `manifest_json` | ✅ MATCH | 39 | `Column(JSON, nullable=True)` — dormant, never populated by user rows. owner_id/workspace_id at 36-37 |
| `workflow.py:13-62` `WorkflowRun` | ✅ MATCH | 13-69 | NO mimetype columns (UXFIX-02 gap confirmed); owner_id/workspace_id at 58-59 |
| `AgentModelPicker.tsx:76` user_allowed filter | ✅ MATCH | 76 | `palette.model_catalog.filter((m)=>m.user_allowed)` — DECIDE-02 drops this |
| `api.ts:522-529` capabilities fetch | ⚠ DRIFTED | **512-525** | `CapabilitiesPalette` iface + `request<CapabilitiesPalette>("/api/capabilities")` now at 512-525. `getWorkflows` at 302 ✓ |
| `DashboardLayout.tsx:256/1070-1079` home | ✅ MATCH | 256 (`return "home"`), 1070-1079 (`CreationHub`) | |
| `DashboardLayout.tsx:1084-1093` catalog tab | ✅ MATCH | 1084-1093 | `WorkflowCatalog` mount |
| `PreviewPanel.tsx:557-569` generic dispatch | ✅ MATCH | 557-570 | 4 first-party branches + `hasGenericDeliverable` fallback. NOTE: `custom` already removed from MarkdownPreview branch (CR-01 fix) |
| `types/index.ts:342-356` reopen sniff | ✅ MATCH | 342 | `deriveDeliverableMimetype(output)` heuristic |
| `manifest.py` `display_name`/`user_launchable` | ✅ MATCH | 75-76 | both fields exist (P20) |

**Anchors that drifted (3, all non-blocking):** compiler trust check (CONTEXT ~279-321 → actual 299-324), engine post_step seam (CONTEXT 1666-1668 → actual 1888-1890), FE api.ts fetch (CONTEXT 522-529 → actual 512-525). No anchor is missing; all symbols still exist.

## Standard Stack

> This phase adds **no external packages**. It extends the existing stack. The Package Legitimacy Audit is therefore N/A (no installs).

### Core (existing, extend in place)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | (in repo) | `GET /api/capabilities` additive metadata | Existing endpoint; API-02 contract |
| Pydantic | (in repo) | `CapabilityEntry` additive fields | Existing response schema |
| SQLAlchemy + Alembic | (in repo) | `WorkflowRun` additive columns (migration 0022) | Existing additive-migration pattern (0014→0021) |
| React + TypeScript | (in repo) | Embedded palette + Advanced expander in `AgentsPopup` | Existing composer surface |
| `deepagents` | `0.6.7` (INV-13) | Untouched — runtime mandate | `create_deep_agent` only in adapter |

### Package Legitimacy Audit

**N/A — this phase installs no external packages.** It surfaces and wires the existing registry; all work is additive edits to in-repo modules. No `npm install` / `pip install` / `cargo add` is required by any requirement.

## Architecture Patterns

### System Architecture Diagram (data flow)

```
COMPOSE (SURF/EMP)
  AgentsPopup (FE)
    ├─ palette fetch ──► GET /api/capabilities (capabilities.py)
    │                      └─ registry_mod.discover() ──► _KNOWN + _TRUST + (NEW) _META  (registry.py)
    │                         returns [{kind,name,user_allowed,security_gated,description,config_schema}]
    ├─ render grouped-by-kind; user_allowed=False ⇒ locked row (D-04)
    └─ per-agent Advanced expander: pick validator/gate/model/retry  (D-05)
            │
            ▼ selections map
SAVE (EMP-03)
  POST/PATCH /api/user-workflows (user_workflows.py)
    ├─ IDOR→404 via _owned()
    ├─ (NEW) compile selections with trust="user"  ──► WorkflowCompiler.compile(..., trust="user")
    │         └─ _check_trust rejects not-user_allowed refs (compiler.py:320-324)  [server backstop, EMP-02]
    └─ persist compact selections map in workflows.manifest_json (workflow_definition.py:39)

LAUNCH (EMP-01/03, D-13)
  websocket.py run_pipeline  (existing run path — NO new endpoint, NO kernel branch)
    ├─ load saved row; (NEW) re-compile selections trust="user"  [re-validate, EMP-02/03]
    ├─ WorkflowCompiler materializes model:/retry:/injects: into Step/CompiledWorkflow  (WIRE-01/02/03)
    └─ ExecutionEngine.execute(...)
          ├─ ModelResolver.resolve(step) honors Step.model / CompiledWorkflow.model  (WIRE-01)
          ├─ RESUME-02 wrapper fires when step.retry.max_attempts>0  (WIRE-02)
          └─ factory _compose_system_prompt merges step.injects + AGENT.md injects  (WIRE-03)
                └─ emits deliverable_mimetype/_filename on pipeline_complete (engine.py:2117)

PERSIST + REOPEN (UXFIX-02)
  WorkflowRun (+ deliverable_mimetype/_filename, migration 0022)
    └─ history-reopen reads persisted mimetype (replaces deriveDeliverableMimetype heuristic)
          └─ PreviewPanel generic-primary dispatch (UXFIX-04) renders by mimetype
```

### Pattern 1: Capability self-description via the decorator (D-08)
**What:** Add `_META: dict[tuple[str,str], dict]` alongside `_TRUST` in registry.py; extend `register(kind, name, *, user_allowed=False, description="", config_schema=None)` to record into `_META`. Add a `describe(kind, name) -> dict` accessor on `CapabilityRegistry` mirroring `is_user_allowed`.
**When to use:** SURF-02.
**Why:** A static metadata map in `capabilities.py` would be a SECOND hardcoded source — a newly `@register`'d cap would appear (live `_KNOWN`) but with empty metadata, eroding SC-001's "no FE edit" guarantee. Keep the registry the single source of truth.
**Example (the registered seam — registry.py:185-189 current):**
```python
# Source: backend/agents/capabilities/registry.py:185-189 (VERIFIED this session)
def _decorate(cls: type[_T]) -> type[_T]:
    _KNOWN.add((kind, name))
    _IMPLS[(kind, name)] = cls()
    _TRUST[(kind, name)] = user_allowed
    # ADD (D-08): _META[(kind, name)] = {"description": description, "config_schema": config_schema or {}}
    return cls
```

### Pattern 2: Pass-through materialization in the two compiler constructors (WIRE-01/02/03)
**What:** The compiler already builds `Step(...)` (compiler.py:505-517) and `CompiledWorkflow(...)` (compiler.py:231-244) WITHOUT passing `model`/`retry`/`injects`. The fields exist on the dataclasses (plan.py:362/368/369/408). Materialization = add `model=...`, `retry=...`, `injects=...` kwargs sourced from `raw.get("model")` etc., coerced to the typed `ModelPolicy`/`RetryPolicy`/`list[str]`.
**When to use:** WIRE-01/02/03.
**Why:** Mirrors exactly how `fanout`/`on_conflict`/`limits` were already materialized (compiler.py:492-503, 248-295) — those were "declared-but-inert" forward fields turned live the same way. This is the established pattern in this file.
**Anti-pattern:** Do NOT loosen `_ALLOWED_STEP_KEYS` or add a silent-accept. INV-5 requires strict-key rejection stays.

### Pattern 3: Trust re-validation at SAVE and LAUNCH (EMP-02/03, D-12)
**What:** Compile the persisted selections through `WorkflowCompiler.compile(manifest, registry, trust="user")` at BOTH `user_workflows.py` (save) and `websocket.py run_pipeline` (launch). The `_check_trust` (compiler.py:299-324) raises `CompilerError` naming any not-`user_allowed` `(kind,name)`.
**Why:** The compiler trust path is fully built (BE-CMP-07 green) but **nothing invokes it with `trust="user"`** — this phase is its first caller. Re-validating at launch (not just save) defends against a row tampered after save.

### Anti-Patterns to Avoid
- **Resurrecting `CapabilityPalette.tsx`** — Phase 18 deleted it as an orphaned INV-12 dual-impl. The palette MUST live inside `AgentsPopup`. (Highest-priority landmine — see Pitfall 1.)
- **A static metadata map in the API layer** — erodes SC-001 (D-08).
- **Auto-injecting coupled gates in the compiler** — the compiler RAISES on a missing gate (compiler.py:458-465), it never auto-injects (T-10-02-03). EMP-04 auto-attach happens in the COMPOSER (FE), and the compiler stays the backstop.
- **Adding a kernel workflow-name / `pipeline_type ==` branch** to wire launch — SC-001 banned-pattern grep would fail CI (`test_banned_patterns.py`, INV-1 pattern at line 117).
- **Re-baselining the goldens** — any byte/event diff means the change is NOT parity-safe; fix the change, never re-record (INV-3).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Capability metadata source | A `CAPABILITY_META = {...}` dict in capabilities.py | `@register` kwargs → `_META` in registry.py (D-08) | Second hardcoded source erodes SC-001 |
| Untrusted-manifest validation | A new bespoke FE/server allow-list | The existing `compiler.compile(trust="user")` + `_check_trust` (compiler.py:299-324) | Fully built (BE-CMP-07 green); just needs a caller |
| Per-step model resolution | New resolution logic | `ModelResolver` tiers 2 & 4 (model_policy.py:95/101) | Already reads `Step.model`/`CompiledWorkflow.model` |
| Retry/transient-fault loop | A new retry wrapper | RESUME-02 wrapper (engine.py:4485-4582) | Live, gated on `step.retry.max_attempts>0` |
| New persistence column for selections | A new table or column | The dormant nullable `manifest_json` (workflow_definition.py:39) | Reuse-first; zero migration (D-11) |
| Generic deliverable rendering | A new renderer | `GenericDeliverablePreview` (src/components/preview/) | Built in P18 (ISS-021); promote to primary |
| Capabilities fetch shell | A new fetch component | `AgentModelPicker` fetch/loading/error shell (D-02) | Same `GET /api/capabilities` payload |
| Fallback chain (DECIDE-02) | A new chain derivation | `ModelResolver.chain_for` (model_policy.py:118) + `cost_class` (model_catalog.py) | Already exists; BE-MODEL-03 green |

**Key insight:** Almost every "new" behavior in this phase is a DORMANT capability with no caller. The work is wiring + surfacing, not building. The single net-new artifacts are: the migration `0022`, the embedded palette UI, the per-agent Advanced expander UI, the `_META` registry extension, and the WIRE-03 parametrized test.

## Runtime State Inventory

> This is a surface-and-wire phase, not a rename/migration. The Runtime State Inventory is mostly N/A, but two persistence-shape items matter:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `workflows.manifest_json` (workflow_definition.py:39) is nullable and never populated by user rows (P21 user rows store only base_pipeline_type/agent_ids/model_overrides). | Code edit only — EMP-03 begins populating it for new/edited saves. No data migration: existing user rows legitimately have `manifest_json IS NULL` (interpreted as "no per-step selections", parity). |
| Live service config | None — no external service stores phase strings. | None. |
| OS-registered state | None. | None. |
| Secrets/env vars | None — no key renamed. AWS `default` profile (acct 473293451041) is the LIVE-01 credential; unchanged. | None (env-only, LIVE-01). |
| Build artifacts | None — no package rename. | None. |
| **DB schema (additive)** | `WorkflowRun` lacks `deliverable_mimetype`/`deliverable_filename` (workflow.py:13-69, verified). | **Additive migration `0022`** (next after 0021) — two nullable columns, run already carries owner_id/workspace_id scope. NOT a backfill (existing rows stay NULL → reopen falls back to the text heuristic, parity). |

## Common Pitfalls

### Pitfall 1: Recreating the deleted standalone capability palette
**What goes wrong:** Building a new `CapabilityPalette.tsx` (or any standalone capabilities browse view) to satisfy SURF-01.
**Why it happens:** SURF-01 says "one palette/inspector renders EVERY capability kind" — naively read as a dedicated component. Phase 08-08 DID originally build `CapabilityPalette.tsx`.
**How to avoid:** Phase 18 (ISS-014) DELETED that component as an orphaned INV-12 dual-impl and relocated the model picker into `AgentsPopup`. D-01 mandates the palette is EMBEDDED in `AgentsPopup`. Build it there. (Evidence: IMPLEMENTATION-REGISTER lines 1836/1856; CONTEXT D-01.)
**Warning signs:** A new top-level route, a new `CapabilityPalette`/`WorkflowComposer` file, a `CreationHub`-style tile for "Capabilities".

### Pitfall 2: Materialize-and-consume for injects breaking INV-3
**What goes wrong:** Wiring `step.injects` into the prompt composition changes the composed system prompt bytes for a golden workflow → INV-3 fails.
**Why it happens:** The 5 goldens (prototype/od_prototype/prototype_revision/od_ppt/app_builder) run real agents whose AGENT.md frontmatter declares `injects` (od_prototype/od_ppt use `[template, design_system, craft]`). A merge that double-applies or reorders would diff.
**How to avoid:** The goldens' MANIFEST steps declare NO per-step `injects:` (only AGENT.md frontmatter does). A merge of `step.injects` (empty for all golden steps) with `spec.injects` (the AGENT.md source) is a provable no-op when `step.injects == []` — same set, same order. Implement the merge as `effective_injects = list(spec.injects) + [i for i in step.injects if i not in spec.injects]` (or simpler: only extend when `step.injects` is non-empty). Run the goldens to prove byte-identity. **This is why D-16 picks materialize-and-consume over reject-loudly** — see WIRE-03 recommendation below.
**Warning signs:** Any golden event/byte diff after the change; the `_compose_injection` call (factory.py:398) receiving a different `injects` list for a golden agent.

### Pitfall 3: Forgetting the LAUNCH-side trust re-validation
**What goes wrong:** Compiling with `trust="user"` only at SAVE; a tampered row launches with a smuggled privileged cap.
**Why it happens:** Save is the obvious validation point; launch reuses the existing run path which historically launched the static file manifest.
**How to avoid:** D-12 requires re-validation at BOTH save AND launch. The acceptance test asserts `_check_trust`/`is_user_allowed` rejection at BOTH the save endpoint and the launch handler (EMP-02 acceptance).
**Warning signs:** A test that only asserts save-side rejection; `websocket.py run_pipeline` loading `manifest_json` without a `compile(trust="user")` call.

### Pitfall 4: The 4th stale "confirm" label (WAVE-03)
**What goes wrong:** DECIDE-01 says "reconcile the 3 stale confirm labels" but REQUIREMENTS.md has a 4th — WAVE-03 at line 135 ("§21 / N8 — confirm").
**Why it happens:** Grepping `confirm` returns 4 hits (REPO-02, REPO-04, FANOUT-05, WAVE-03).
**How to avoid:** DECIDE-01 scopes ONLY the 3 retention-adjacent labels (REPO-02 N6/N10, REPO-04 N5/N7, FANOUT-05 N2). WAVE-03 (N8, wave-resume) is OUT of DECIDE-01's scope — do NOT touch it. The acceptance criterion is "no dangling confirm" for the 3 named, not all 4.
**Warning signs:** An edit to WAVE-03 line 135.

### Pitfall 5: Offline full-suite hang
**What goes wrong:** Running `pytest` over the whole backend hangs (Chromium/Bedrock/Postgres-gated tests).
**How to avoid:** Use the targeted parity/gate suite (Validation Architecture below). Per project memory: full pytest hangs offline; the ~35s targeted suite + `lint-imports` is the offline verification floor.

## Code Examples

### Live registry enumeration (the SURF-02 source)
```python
# Source: backend/app/api/capabilities.py:106-118 (VERIFIED this session)
for kind, name in sorted(registry_mod._KNOWN):
    if kind == "model_catalog":
        continue
    capabilities.append(
        CapabilityEntry(
            kind=kind,
            name=name,
            user_allowed=registry.is_user_allowed(kind, name),
            config_schema={},   # ← D-09 replaces this stub with registry.describe(kind,name)["config_schema"]
        )
    )
```

### The trust check this phase first invokes (EMP-02 backstop)
```python
# Source: backend/agents/workflows/compiler.py:318-324 (VERIFIED this session)
if trusted:
    return
if not registry.is_user_allowed(kind, name):
    raise CompilerError(
        f"capability ({kind!r}, {name!r}) is not user-allowed in {where} "
        f"— a user/db manifest may not reference it (CAP-03)"
    )
```

### The Step constructor to extend (WIRE-01/02/03 site)
```python
# Source: backend/agents/workflows/compiler.py:505-517 (VERIFIED this session)
return Step(
    agent_id=agent_id,
    strategy=strategy,
    gates=gates,
    hooks=hooks,
    task_source=task_source,
    validators=validators,
    compaction=compaction,
    post_step=post_step,
    tools=effective_tools,
    fanout=fanout,
    on_conflict=on_conflict,
    # WIRE-01/02/03 ADD: model=..., retry=..., injects=...
)
```

## WIRE-03 Decision: Materialize-and-Consume is INV-3-safe — TAKE IT

**Question (from CONTEXT D-16):** Is the merge provably a no-op when no step declares `injects:`?

**Answer: YES.** Evidence:
1. The live injects surface is AGENT.md frontmatter only (`AgentSpec.injects`, loader.py:102), composed by `_compose_injection` (factory.py:398) and called from `_compose_system_prompt` at factory.py:310-315.
2. `Step.injects` defaults to `field(default_factory=list)` (plan.py:369) → an empty list for every step the compiler builds today (the constructor at compiler.py:505-517 never passes it).
3. The 5 characterization goldens' MANIFEST steps declare no per-step `injects:` (only the agents' AGENT.md frontmatter does). After WIRE-03, every golden step still has `step.injects == []`.
4. A merge `spec.injects + [i for i in step.injects if i not in spec.injects]` with `step.injects == []` returns exactly `spec.injects` — same list, same order → identical `_compose_injection` input → byte-identical prompt → INV-3 holds.
5. The proof is mechanical: run `tests/agents/test_characterization_*.py` after the change; zero diffs confirms the no-op.

**Recommendation: implement materialize-and-consume (D-16 primary), NOT reject-loudly.** It satisfies WIRE-03 (the key is consumed, not dropped), keeps `injects:` available for future user workflows, and is provably parity-safe. Reserve reject-loudly only if the goldens unexpectedly diff (they will not, per the above). The merge belongs at the factory injection seam (a generic merge in `create_runner`/`_compose_system_prompt` that reads `step.injects` off the compiled step's context) — **no workflow-name branch** (SC-001). There is an existing `test_factory_injects.py` to extend for the merge.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Standalone `CapabilityPalette.tsx` + `WorkflowComposer.tsx` | Embedded composer in `AgentsPopup`; palette/model picker relocated there | Phase 18 (2026-06-13, ISS-014) | Build the palette in `AgentsPopup`; do NOT recreate the deleted components |
| Hardcoded launch surface (`CreationHub.WORKFLOWS`) | Data-driven `WorkflowCatalog` off `GET /api/workflows` + `user_launchable` flag | Phase 20 (WF-DB-01) | UXFIX-03 makes the catalog the default landing |
| No DB-backed user workflows | `source="user"` rows on the reused `workflows` table, migration 0021 | Phase 21 | EMP-03 extends these rows with `manifest_json` selections |
| First-party per-type preview branches only | Generic mimetype renderer (fallback) added | Phase 18 (ISS-021) | UXFIX-04 promotes generic to primary |

**Deprecated/outdated:**
- `CapabilityPalette.tsx`, `WorkflowComposer.tsx`: DELETED in P18 — do not resurrect (INV-12).
- `deriveDeliverableMimetype` text heuristic (types/index.ts:342): UXFIX-02 replaces its use on reopen with the persisted mimetype (the function may remain as a last-resort fallback for legacy rows with NULL columns).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The 5 golden MANIFESTS declare no per-step `injects:` (only AGENT.md frontmatter does), making the WIRE-03 merge a provable no-op | WIRE-03 Decision | LOW — if a golden manifest DID declare step injects, the merge would diff; the planner must run the goldens to confirm (the test IS the proof, so risk is self-correcting). Verified the Step.injects default is `[]` and the constructor omits it today, so current behavior is empty regardless. |
| A2 | `security_gated` is best derived from `user_allowed=False` rather than a new stored boolean | SURF-02 / Discretion | LOW — the SPEC leaves the shape to Claude's discretion (D-98 in CONTEXT). If product later wants a distinct flag, it's additive. |
| A3 | The next migration number is `0022` (after `0021_saved_user_workflows`) | UXFIX-02 / Runtime State | LOW — verified `ls alembic/versions/` ends at 0021; standard sequential numbering. |
| A4 | WAVE-03's "confirm" label is OUT of DECIDE-01 scope (only REPO-02/REPO-04/FANOUT-05 are in) | Pitfall 4 | LOW — SPEC DECIDE-01 names exactly 3 labels; WAVE-03 is N8 (wave-resume), unrelated to retention. |

**All other claims in this research are VERIFIED against live source or CITED from in-repo registers this session.**

## Open Questions

1. **Exact `manifest_json` selections shape vs a full synthesized partial manifest.**
   - What we know: D-11/D-95 lean "compact selections map compiled at launch." The compiler takes a `WorkflowManifest` (manifest.py), so launch must synthesize a manifest from the stored selections + the base pipeline's agent list.
   - What's unclear: whether to store the compact map `{agent_id: {validators, gates, model, retry}}` and synthesize the manifest at launch, OR store a full partial manifest dict.
   - Recommendation: store the compact map (CONTEXT discretion lean), synthesize a `WorkflowManifest` at save AND launch, compile with `trust="user"`. The synthesis is small (agent list is already in `agent_ids`); the compact map is forward-compatible and avoids persisting a fully-expanded manifest that could drift from the base.

2. **Where the SURF-03 "compiled-capability projection" comes from.**
   - What we know: SURF-03 wants the composer to show a built-in workflow's declared capabilities, "via `GET /api/workflows/{id}` or an equivalent compiled-capability projection."
   - What's unclear: whether `GET /api/workflows/{id}` already returns per-step capabilities or needs an additive projection.
   - Recommendation: the planner should check `app/api/workflows.py` `WorkflowSummary` shape (P20) during planning; if it lacks per-step caps, add an additive compiled projection (compile the file manifest, project `[step.agent_id → {strategy, gates, validators, ...}]`). Additive, registry-driven, SC-001-clean.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python3.11` | Backend run/test | ✓ | 3.11 (no venv) | — |
| `lint-imports` | Ports & Adapters gate | ✓ | binary at `/opt/homebrew/bin/lint-imports` | — |
| Node/npm | Frontend palette + e2e | ✓ | (in repo) | — |
| AWS `default` profile (acct 473293451041) | LIVE-01 only | ✓ | Bedrock Haiku 4.5 (`claude-haiku-4-5`) | Deferred to milestone-end (D-24); offline evidence gates phase completion |
| AWS `hexaware-srini` profile | (NOT used) | ✗ | ValidationException (ISS-018) | Use `default` — not a blocker (out of scope to fix) |
| Chromium / Postgres (full pytest) | (avoided) | partial | — | Use the targeted ~35s suite; full pytest hangs offline (project memory) |

**Missing dependencies with no fallback:** None block this phase (LIVE-01 is explicitly deferred).
**Missing dependencies with fallback:** `hexaware-srini` Bedrock (use `default`); full offline pytest (use the targeted suite).

## Validation Architecture

> nyquist_validation = true (config.json:21). This section is REQUIRED.

### Test Framework
| Property | Value |
|----------|-------|
| Framework (BE) | pytest, run via `python3.11 -m pytest` from `backend/` (no venv) |
| Framework (FE) | vitest (`npm test`) + Playwright e2e (`npm run e2e`, mocked-green at `frontend/e2e/`) |
| Config file | `backend/` pytest (project default); `frontend/` vitest config |
| Quick run command (BE) | `python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py -q` |
| Full targeted suite (~35s) | `python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py tests/agents/test_migration_ledger.py tests/agents/test_banned_patterns.py -q` (expect 44 passed, 7 skipped) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SURF-01 | Palette has no hardcoded cap-name array | grep + FE unit | `grep -rnE "\[.*('strategy'|\"strategy\").*('validator'|\"validator\")" frontend/src/components/workflow/` → 0 in palette source; FE render test against a fixture payload | ❌ Wave 0 (FE palette test) |
| SURF-02 | Each entry carries description + security_gated + config_schema; auth + keys preserved | unit | `python3.11 -m pytest tests/unit/test_capabilities_api.py -q` | ✅ (extend — 195 lines) |
| SURF-03 | Composer shows compiled per-step caps | FE unit / integration | FE test rendering the compiled projection | ❌ Wave 0 |
| EMP-01 | Validator fires / model resolved / retry activates under fault | integration | `python3.11 -m pytest tests/unit/ -k "user_workflow_launch or compose_launch"` (new) | ❌ Wave 0 |
| EMP-02 | Smuggled `user_allowed=False` rejected at SAVE and LAUNCH | unit | `python3.11 -m pytest tests/agents/test_compiler.py -k "trust or user_allowed"` (extend) + new save/launch rejection test | ✅ compiler / ❌ save+launch Wave 0 |
| EMP-03 | Selections round-trip (save→list→reopen); cross-owner GET 404; additive migration | unit | new `tests/unit/test_user_workflows_selections.py`; `python3.11 -m pytest tests/unit/test_user_workflows*.py` | ❌ Wave 0 |
| EMP-04 | Coupled-gate auto-attach (FE) + compiler backstop raises | unit | `python3.11 -m pytest tests/agents/test_compiler.py -k "gate or coupling"` (compiler.py:458-465) + FE auto-attach test | ✅ compiler backstop / ❌ FE Wave 0 |
| WIRE-01 | Per-step + top-level model changes resolved model; goldens byte-identical | unit | `python3.11 -m pytest tests/agents/test_compiler.py -k model`; goldens suite | ❌ Wave 0 (compiler model test) |
| WIRE-02 | `retry:{max_attempts:N}` activates wrapper under injected throttle; no-retry stays parity | unit | `python3.11 -m pytest tests/unit/ -k "retry"` (engine.py:4513) | ❌ Wave 0 |
| WIRE-03 | Parametrized over `_ALLOWED_STEP_KEYS`: each key consumed OR raises; goldens byte-identical | unit | new `tests/agents/test_allowed_step_keys.py`; extend `tests/unit/test_factory_injects.py` for the merge | ✅ factory_injects / ❌ allowed_step_keys Wave 0 |
| UXFIX-01 | `display_name` renders in catalog; BE fallback null only where intended | unit | `python3.11 -m pytest tests/agents/test_manifest.py tests/unit/test_workflows_api.py -k display_name` | ✅ (extend) |
| UXFIX-02 | Binary deliverable re-renders from persisted mimetype; migration additive; goldens byte-identical | unit | `python3.11 -m pytest tests/unit/test_deliverable_mimetype.py` (asserts keys in `_VOLATILE_STRIP_KEYS`) + new migration/reopen test | ✅ (extend) |
| UXFIX-03 | Default landing renders `WorkflowCatalog`; `CreationHub.WORKFLOWS` no longer drives home | FE unit | FE test asserting default `mainView==="catalog"`/catalog mount | ❌ Wave 0 |
| UXFIX-04 | Custom deliverable via generic path as primary; first-party render identical | FE unit | extend PreviewPanel per-type render tests; e2e mocked | ✅ (extend) |
| DECIDE-01 | ART-04 keep-by-default; 3 confirm labels reconciled; no retention default contradicts | assertion | `grep -n "confirm" .planning/REQUIREMENTS.md` for REPO-02/REPO-04/FANOUT-05 → reconciled; doc review | N/A (doc) |
| DECIDE-02 | MODEL-05 premium-open; picker offers premium to non-premium tier; fallback documented | FE unit + doc | FE test: `AgentModelPicker` renders premium model for non-premium tier (tier filter removed at :76) | ❌ Wave 0 (picker test) |
| LIVE-01 | Per-item evidence record (8 deferrals) | manual (deferred) | Milestone-end live pass on `default` profile, Haiku 4.5 | N/A (deferred, D-24) |

### Sampling Rate
- **Per task commit:** the quick goldens command (5 goldens byte+event parity) — the INV-3 floor on every backend change.
- **Per wave merge:** the full targeted suite (~35s, 44 passed/7 skipped) + `lint-imports` (4 kept/0 broken) + the SC-001 grep.
- **Phase gate:** full targeted suite green + `test_capabilities_api.py` + the new WIRE-03 parametrized test + FE `npm test` + `npx tsc --noEmit` before `/gsd-verify-work`.

### Invariant-Proof Commands (the falsifiable checks)
```bash
# INV-3 — 5 characterization goldens byte + event identical
cd backend && python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,prototype_revision,od_ppt,app_builder}.py -q

# SC-001 — kernel knows no workflow by name (grep == 0) + banned-pattern gate
cd backend && python3.11 -m pytest tests/agents/test_banned_patterns.py -q
grep -nE "if pipeline_type ==|spec\.id ==" agents/workflows/compiler.py agents/execution_engine/engine.py   # → 0 on routed paths

# INV-13 — create_deep_agent only in the adapter (sole site app/agents/deep_agent_runner.py:291)
cd backend && python3.11 -m pytest tests/agents/test_banned_patterns.py -k "deep_agent" -q

# Ports & Adapters — import-linter 4 kept / 0 broken
lint-imports                                   # /opt/homebrew/bin/lint-imports

# Additive migration only — new 0022 is additive (no drop/alter-narrow), owner_id/workspace_id scope present
cd backend && python3.11 -m pytest tests/unit/ -k "migration" -q   # + manual review of alembic/versions/0022_*.py

# SURF-02 contract
cd backend && python3.11 -m pytest tests/unit/test_capabilities_api.py -q

# FE
cd frontend && npm test && npx tsc --noEmit
```

### Wave 0 Gaps
- [ ] `tests/agents/test_allowed_step_keys.py` — WIRE-03 parametrized over `_ALLOWED_STEP_KEYS` (each consumed or raises)
- [ ] `tests/unit/test_user_workflows_selections.py` — EMP-03 round-trip + IDOR→404 + launch re-validation
- [ ] BE compiler tests for WIRE-01 (model) / WIRE-02 (retry) — extend `tests/agents/test_compiler.py`
- [ ] BE save/launch trust-rejection test (EMP-02) — extend compiler test + new save/launch endpoint test
- [ ] FE palette render test (SURF-01 no-hardcoded-array + grouped rows + locked rows)
- [ ] FE Advanced-expander test (EMP-01 lever selection) + EMP-04 auto-attach
- [ ] FE catalog-as-home test (UXFIX-03) + DECIDE-02 picker-offers-premium test
- [ ] UXFIX-02 reopen-from-persisted-mimetype test + migration 0022 additive test
- [ ] Extend `tests/unit/test_factory_injects.py` for the `step.injects` + AGENT.md merge (WIRE-03 consume side)

## Security Domain

> security_enforcement = true (config.json:43). This section is REQUIRED.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Ports & Adapters (import-linter 4/0); compiler depends only on registry port |
| V2 Authentication | yes | `Depends(get_current_user)` on `/api/capabilities` + `/api/user-workflows` (preserved, API-02) |
| V3 Session Management | no (unchanged) | JWT-only, existing posture |
| V4 Access Control | **yes (central)** | Trust gating: `_check_trust`/`is_user_allowed` (CAP-03) at SAVE + LAUNCH; IDOR→404 via `_owned()` (user_workflows.py); owner_id+workspace_id scope on every row |
| V5 Input Validation | **yes (central)** | Strict-key rejection (`_ALLOWED_STEP_KEYS`, INV-5); compiler `CompilerError` naming bad refs; `_validate_model_overrides` two-check allow-list |
| V6 Cryptography | no | No new crypto |
| V8 Data Protection | yes | `manifest_json` selections carry no secrets; `CompilerError` carries repo-authored config text only (no PII) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Smuggled privileged capability in a save/launch payload | Elevation of Privilege | Compile with `trust="user"`; `_check_trust` rejects not-`user_allowed` `(kind,name)` at BOTH save and launch (EMP-02). NEVER trust the FE lock affordance alone. |
| IDOR on saved workflows | Information Disclosure / Tampering | `_owned()` filters by owner → 404 (never 403/leak); cross-owner GET test asserts 404 (EMP-03). |
| Ceiling-raising Limits in a user manifest | Elevation of Privilege | `_compile_limits` rejects raises above `_LIMITS_DEFAULT_CEILING` for untrusted trust (compiler.py:279-289). |
| Exec/network/secrets/spawn grant in a user manifest | Elevation of Privilege | `trust="user"` privileged-grant `CompilerError` (compiler.py:433-452); exec stays engineer-only (out of scope to enable). |
| DSL/control-flow smuggled into a step key | Tampering | Strict-key allow-list at every nesting level (INV-5); WIRE-03 must NOT loosen it into silent-accept. |
| Kernel workflow-name branch added during launch wiring | (architecture erosion / SC-001) | `test_banned_patterns.py` INV-1 grep (`if pipeline_type ==`/`spec.id ==`) → 0; CI hard-fail. |

## Sources

### Primary (HIGH confidence — read live this session)
- `backend/app/api/capabilities.py` (full) — endpoint, `CapabilityEntry`, `{}` stub, `_KNOWN` loop
- `backend/agents/capabilities/registry.py` (full) — `_KNOWN`, `register`, `_TRUST`, `is_user_allowed`, `discover`
- `backend/agents/workflows/compiler.py` (full) — `_ALLOWED_STEP_KEYS`, two constructors, `_check_trust`, trust ceiling, `_compile_limits`
- `backend/agents/workflows/plan.py:330-411` — `Step`/`CompiledWorkflow` field set (model/retry/injects)
- `backend/agents/model_policy.py:80-118` — ModelResolver tiers + `chain_for`
- `backend/agents/execution_engine/engine.py` (grep) — retry wrapper, deliverable emit, post_step seam
- `backend/agents/factory.py:295-450` — injection seam, `_compose_injection`
- `backend/agents/loader.py:90-110` — `AgentSpec.injects`/`model`
- `backend/app/models/workflow_definition.py` (full) — `manifest_json` dormant column
- `backend/app/models/workflow.py` (full) — `WorkflowRun` (no mimetype columns)
- `backend/app/api/user_workflows.py` (grep) — save + IDOR→404
- `backend/app/api/websocket.py` (grep) — `run_pipeline` launch path
- `backend/tests/agents/characterization/_normalize.py:95-141` — `_VOLATILE_STRIP_KEYS`
- `frontend/src/lib/api.ts`, `AgentModelPicker.tsx`, `AgentsPopup.tsx`, `PreviewPanel.tsx`, `DashboardLayout.tsx`, `types/index.ts` (grep)
- `.planning/REQUIREMENTS.md` (grep) — ART-04:49, MODEL-05:64, confirm labels
- `.planning/TEST-REGISTER.md` — targeted suite + invariant-proof commands
- `.planning/IMPLEMENTATION-REGISTER.md` — P18 palette deletion (1836/1856), migration chain, P20/P21
- `.planning/ISSUES-REGISTER.md` — ISS-018, ISS-015/WF-DB-01
- `.planning/config.json` — nyquist_validation, security_enforcement, use_worktrees

### Secondary (MEDIUM)
- `backend/CLAUDE.md` — runtime architecture (injection order, engine sequencer, deepagents adapter)

### Tertiary (LOW)
- None — no WebSearch used; this is a closed-codebase brownfield phase.

## Metadata

**Confidence breakdown:**
- Anchor verification: HIGH — all 24 refs read live; 3 documented drifts, 0 missing symbols.
- Standard stack: HIGH — no new packages; all extensions to verified in-repo code.
- Architecture: HIGH — patterns mirror existing materialization (fanout/limits) + dormant-path activation, all read in source.
- Pitfalls: HIGH — P18 palette deletion and INV-3 injects no-op both grounded in read source/registers.
- WIRE-03 INV-3 safety: HIGH — provable from the empty-default + goldens-no-step-injects facts; the goldens test is the mechanical proof.

**Research date:** 2026-06-14
**Valid until:** 2026-07-14 (stable brownfield; re-verify the 3 drifted anchors if the compiler/engine/api.ts files change before planning)
