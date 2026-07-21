# Phase 37: Configure Unification + Composer/Wizard [B3] — Research

**Researched:** 2026-07-09
**Domain:** Additive backend run-launch seam (D-15/C) + FE reuse of shipped P22 composer surfaces + client-side draft (ND-1) + offline validation architecture
**Confidence:** HIGH (all current-code claims verified against files opened this session; evidence-08 anchors re-checked, drift noted)

> **Scope note.** A sibling `gsd-pattern-mapper` owns the exhaustive file-to-analog reuse map (evidence 08's ~26 surfaces ↔ current files). This document deliberately does NOT reproduce that. It covers only the four areas the pattern-map does not: (1) the D-15/C additive backend seam + goldens-byte-identical proof, (2) the Nyquist Validation Architecture, (3) the FE reuse gotchas that cause regressions, (4) the client-side draft (ND-1) pattern. Every current-code claim below is tagged `[VERIFIED: file:line]` (I opened it) or `[ASSUMED]`.

---

<user_constraints>
## User Constraints (from 37-CONTEXT.md + POR locks)

### Locked Decisions (do NOT re-open)
- **D-15/C — generic template/DS run inputs.** Template/DS become DECLARED run inputs any deliverable can opt into (SC-001: keyed on a declared capability/manifest flag, NEVER a prototype-only/workflow-name branch). **ADDITIVE only** — prototype/PPT's existing template/DS run-launch flow stays byte-identical (INV-3 goldens prove it); the change only lets OTHER deliverables accept template/DS.
- **Reuse over rebuild (D-15 / evidence 08).** REUSE the live `/api/capabilities` palette (not the mock's hardcoded 8), the `AdvancedExpander` levers INCLUDING the validator→gate coupling, the built-but-unmounted `AgentModelPicker` (mount inline), `/api/user-workflows` CRUD. A face-value rebuild from the mock REGRESSES. NEW-BUILD only: the unified Template→DS→Discovery stepper (Web/Deck toggle) + wiring the orphaned `DiscoveryForm`.
- **ND-7 gate (LOCK-E):** Agent-drawer Config tab SURFACES per-agent prompt-override; its PERSISTENCE is DEFERRED — no durable override storage.
- **ND-1 (LOCK-E):** draft-run persistence is CLIENT-SIDE only (kept until launch, no draft rows / no DB).
- **Workflow dialog:** "Engineer-only" gating reflects the capability `user_allowed` flag (declared data, not a code branch — INV-5).
- **DS picker = real ~14 (LOCK-F, ND-8);** output = "Deliverable"; deliverable-type names = P22 `display_name`s.

### Claude's Discretion
- Which declared-signal shape the D-15/C seam keys on (reuse `context_providers:[opendesign]` vs a new name-free `run_inputs`/`accepts` key) — see Standard Stack below for the recommendation and tradeoffs.
- Stepper component structure, accordion layout, Web/Deck toggle mechanics.
- How `DiscoveryForm` enum reconciliation is surfaced (mock vs current audience/tone sets differ).

### Deferred Ideas (OUT OF SCOPE — declared out, do NOT build)
- Workflow visibility / team-sharing ("Just me / Team") — ND-12 / Category-D. No column, no endpoint, no UI.
- Pre-run cost + duration estimates for a composed workflow — Category-D.
- Discovery page-selection (multi-select "Which pages?") — absent end-to-end, Category-D.
- ND-7 per-agent prompt-override PERSISTENCE (drawer surfaces it, no durable store).
- Any transport change (LOCK-B). Any engine/runner change (INV-13). Any new table (Q3 additive; draft = client-side).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SHELL-04 | Generic Configure surface (Describe/Templates/DS/Gates/Settings for every deliverable) + Agent drawer + Workflow dialog with `user_allowed` gating (ND-1/ND-7/ND-8 gated) | The Configure surface's load-bearing enabler is the D-15/C boundary seam (this doc §Standard Stack). `user_allowed` gating already lands via the live `/api/capabilities` reflection (§FE Gotchas). ND-1 = client-side draft (§Client-Side Draft). ND-7 = surface-only. ND-8 = real ~14 DS from `/api/prototype/design-systems`. |

*Prior related (already `[x]` complete, reused not rebuilt):* API-06 (composer + capability palette + per-agent model picker — palette-panel deleted as superseded by live `AgentsPopup`; `/api/capabilities` RETAINED), SURF-03 (declared-capability strip), EMP-01 (opt step into user-allowed caps), EMP-04 (validator→coupled-gate auto-attach), WIRE-02 (per-step `retry:` → `Step.retry` int). These are the surfaces Phase 37 RESKINS; regressing any of them is the primary risk (§FE Gotchas).
</phase_requirements>

---

## Summary

Phase 37's one real architectural change (D-15/C) is small, additive, and — critically — **lives at the run-launch boundary, not in the engine and not on the golden path.** Today the boundary decides whether to load template/design-system context by branching on the workflow-name literals `od_prototype` / `od_ppt` / `od_ppt_revision`. That branch is duplicated in exactly two functions: `run_commands.py::_resolve_launch_agents` (REST launch) and `websocket.py::_handle_workflow_execution` (WS launch). This is the SC-001/INV-1 leak the phase must close: replace the name-branch with a check on a **declared manifest signal** so any deliverable can opt into template/DS run-inputs.

The proof that this stays byte-identical is structurally easy because of one verified fact: **the 5 characterization goldens are driven by `_scripted_model._drive()`, which calls `engine.execute()` with a pre-built `od_context` dict — they never invoke the launch boundary.** So a boundary-only change cannot perturb the goldens at all (they prove the engine is untouched, which it is). The genuinely new proof the plan must add is a launch-boundary characterization: assert that `od_prototype`/`od_ppt` produce the same `od_context` dict through the generic seam as through today's name-branch. `test_rest_run_launch.py` today only exercises `od_context=None` — that assertion is a Wave-0 gap.

The rest of the phase is FE reuse of already-shipped P22 code, where the dominant risk is **regression by face-value rebuild from the stale mock**: the mock drops the validator→gate coupling (COUPLED_GATE="validation", verified live), models retry as a bool where the product uses `[1,2,3]`, hardcodes 8 capabilities where the product reads the live `/api/capabilities` registry, and ignores the built-but-unmounted `AgentModelPicker`. The client-side draft (ND-1) has an exact in-repo analog to copy: the `sessionStorage` `"prototype.draft"` blob.

**Primary recommendation:** Land D-15/C FIRST in its own wave as a boundary-only, name-free declared-signal change; prove it with (a) the 5 goldens run with `SNAPSHOT_UPDATE` unset + `git status` clean, and (b) a NEW launch-boundary od_context-parity test. Then reskin the composer/wizard by REUSING the live surfaces verbatim, and copy the `sessionStorage` draft idiom for the Configure "Save draft". No new table, no engine edit, no transport touch.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Generic template/DS acceptance (D-15/C) | API / Backend (launch boundary) | Manifest (declared data) | The name-branch lives at `run_commands.py`/`websocket.py` launch handlers; the opt-in signal is declared manifest data (INV-5). Engine/kernel unchanged (INV-13). |
| Configure screen (Describe/Templates/DS/Gates/Settings) | Frontend (Next.js route) | API (live registries) | Pure client composition over live `/api/*` reads; no server logic new. |
| Composer/Wizard reskin | Frontend | API (`/api/capabilities`, `/api/user-workflows`, `/api/prototype/templates`, `/api/prototype/design-systems`) | Data-driven surfaces already shipped (P22); reskin is client-side. |
| Agent drawer (4-tab) + Workflow dialog | Frontend | API (compiled `WorkflowDetail`) | Reads compiled per-step declared data; `user_allowed` gating is display of declared flags. |
| Draft-run persistence (ND-1) | Browser / Client (`sessionStorage`) | — | LOCK-E: client-side only, no DB, no migration. |

---

## Standard Stack

This is a brownfield reskin + one additive backend seam. "Stack" here = the exact in-repo surfaces to reuse and the seam to modify. No new external packages. (No `## Package Legitimacy Audit` — this phase installs nothing.)

### D-15/C — the additive run-launch seam (the load-bearing task)

**Where the name-branch lives today (VERIFIED):**

| Boundary | File:line | Current branch |
|----------|-----------|----------------|
| REST launch | `backend/app/api/run_commands.py:934-978` (`_resolve_launch_agents`) | `if pipeline_type == "od_prototype": … load_prototype_od_context(...)` / `elif == "od_ppt": … load_ppt_od_context(...)` |
| WS launch | `backend/app/api/websocket.py:1714-1750` (`_handle_workflow_execution`) | Same name-branch, plus an `od_ppt_revision` arm that loads DS non-fatally |
| od_context loaders | `backend/agents/execution_engine/od_context.py` (`load_prototype_context`/alias `load_prototype_od_context`, `load_ppt_od_context`) | The disk-reading boundary loaders; import `app.services.od_loader` (sanctioned app-side boundary) |

`[VERIFIED: run_commands.py:948-976]` `[VERIFIED: websocket.py:1713-1750]` — Both are name-literal branches: the launch payload already carries `template_id` / `design_system_id` / `custom_ds_body` / `custom_template_body` generically (`LaunchCommand`, `run_commands.py:916-919`), but they are only READ when `pipeline_type` matches the two OD literals.

**The declared-input precedent already in the codebase (VERIFIED):**

`input_providers: [run_images]` in `agents/workflows/prototype/workflow.yaml:37` is the exact pattern to imitate. It is a DATA-ONLY, name-free manifest key: `_ALLOWED_TOP_KEYS` already lists `input_providers` and `context_providers` `[VERIFIED: agents/workflows/manifest.py:113-114]`; both compile into `CompiledWorkflow` `[VERIFIED: agents/workflows/compiler.py:215,257-258]`; dormant-when-empty keeps goldens byte-identical (the manifest comment states this design intent). `context_providers: [opendesign]` is ALREADY declared on the prototype manifest `[VERIFIED: agents/workflows/prototype/workflow.yaml:34]` and (per evidence) on od_ppt.

**Recommended seam (name-free, additive):** At the launch boundary, resolve the workflow's manifest and gate od_context loading on a DECLARED signal instead of the pipeline-name literal. `resolve_alias(pipeline_type)` already maps `od_prototype → prototype` `[VERIFIED: engine.py:470-479]`, so the boundary can cheaply peek the compiled/loaded manifest.

Two viable declared signals (Claude's discretion — recommend option A for minimal blast radius):

| Option | Declared signal | Pros | Cons |
|--------|-----------------|------|------|
| **A (recommended)** | Presence of `context_providers: [opendesign]` on the resolved manifest ⇒ "this workflow accepts template_id/design_system_id run-inputs" | Reuses an existing declaration; zero new manifest key; prototype/od_ppt already declare it ⇒ their od_context build is unchanged ⇒ goldens byte-identical by construction; other deliverables opt in by adding one manifest line | Conflates "injects OD context" with "accepts template/DS inputs" (they are in fact the same concept here, so low risk) |
| **B** | New name-free top key, e.g. `run_inputs: [template, design_system]`, added to `_ALLOWED_TOP_KEYS` (mirrors `input_providers`) | Fully explicit; cleanly separates run-input acceptance from injection | Adds a manifest key (must extend `_ALLOWED_TOP_KEYS` + compiler + `CompiledWorkflow`); more surface to test; a drift-guard bump if capability-count guarded |

**Load-bearing constraint — the loader-profile difference must NOT reintroduce a name-branch.** `load_prototype_od_context` (DS always required, KAN-87 no-template mode) and `load_ppt_od_context` (DS optional) differ. The MINIMAL additive change for THIS phase: gate od_context loading on the declared signal, and preserve the exact prototype-vs-ppt loader mapping as-is — because only prototype+od_ppt declare `opendesign` today, no OTHER deliverable reaches those loaders, so prototype/ppt's produced dict is untouched. A fully generic loader-profile selection (declaring which loader profile a workflow uses) is a deeper refactor; note it as a follow-up, do NOT attempt it in the additive wave (it risks the goldens). `[ASSUMED]` that no third deliverable needs a distinct loader this phase — VERIFY against the deliverable list at plan time (grep manifests for `context_providers: [opendesign]`).

**Migrations:** none. POR line 99: "none for v1; 0024+ reserved." `[CITED: CHAT-AND-UI-CONVERGENCE-PLAN.md:99]` The launch payload already carries template/DS fields generically — no column needed.

### Reuse surfaces (do NOT rebuild — the pattern-mapper anchors these; here are the load-bearing IDs)

| Surface | Live source | Reuse contract |
|---------|-------------|----------------|
| Capability palette | `GET /api/capabilities` + `CapabilityPaletteSection` (`AgentsPopup.tsx`) | Data-driven; `security_gated`→Lock, `user_allowed=false`→Engineer-only |
| Advanced levers (validator/gate/model/retry) | `AdvancedExpander` (`AgentsPopup.tsx`) | Keep COUPLED_GATE + retry-as-int (§FE Gotchas) |
| Per-agent model | `AgentModelPicker.tsx` (UNMOUNTED — mount inline) | `model_overrides` round-trips via mig 0021; WR-01 merge contract |
| Save/catalogue CRUD | `POST/GET/PATCH/DELETE /api/user-workflows` (`user_workflows.py:247-431`) | Wire "Save workflow" to `createUserWorkflow`; NO visibility field |
| Templates | `GET /api/prototype/templates` (~43) | live iframe previews; not the mock's 12 |
| Design systems | `GET /api/prototype/design-systems` (~14, LOCK-F) | not the mock's 5 |
| Discovery | `DiscoveryForm.tsx` (built, ORPHANED — wire it) | reconcile audience/tone enums; drop mock "pages" |

---

## Runtime State Inventory

> D-15/C is an additive **input-acceptance** change, not a rename/data migration. Included for completeness because the phase touches the run-launch path.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no stored key/collection is renamed or repurposed. Draft is client-side (ND-1). | None |
| Live service config | None — no external service config embeds a Phase-37 string. | None |
| OS-registered state | None. | None |
| Secrets/env vars | `OD_ROOT` env var governs template/DS disk root `[VERIFIED: od_loader.py:51]` — UNCHANGED; the seam reads the same loaders. | None |
| Build artifacts | None new. Manifests are read at runtime; `_all_templates()`/`_all_design_systems()` are `lru_cache`d in-process `[VERIFIED: od_loader.py:168,357]` — a manifest edit needs a backend restart to re-read (dev note only). | Restart backend after manifest edits |

**Verified nothing found** in stored-data / live-service / OS-registered categories: the change adds a declared opt-in and reads existing template/DS payload fields; it neither writes nor renames persistent state.

---

## Architecture Patterns

### System Architecture Diagram — the D-15/C additive seam

```
                        LAUNCH (over REST or WS — payload identical)
   FE Configure screen ──► { pipeline_type, template_id, design_system_id,
        (any deliverable)     custom_ds_body?, custom_template_body?, agent_ids, ... }
                                          │
                                          ▼
                    ┌─────────────────────────────────────────────┐
                    │  BOUNDARY (run_commands._resolve_launch_agents│
                    │           / websocket._handle_workflow_exec)  │
                    │                                               │
                    │  TODAY:  if pipeline_type == "od_prototype"…  │  ◄── SC-001/INV-1 leak
                    │          elif == "od_ppt"…   (NAME BRANCH)    │
                    │                                               │
                    │  AFTER:  resolve_alias(pipeline_type)         │
                    │          peek manifest → declared signal?     │  ◄── name-free, INV-5
                    │            (context_providers:[opendesign]    │
                    │             OR new run_inputs:[template,ds])   │
                    │          if declared → build od_context       │
                    │             (SAME loader for proto/ppt)       │
                    └─────────────────────────────────────────────┘
                                          │ od_context (dict) or None
                                          ▼
              engine.execute(agents, …, od_context=…)   ◄── UNCHANGED (INV-13)
                                          │
                       ══════════════════════════════════════════
                       GOLDEN PATH (characterization) BYPASSES the
                       boundary: _scripted_model._drive() builds
                       od_context itself and calls execute() directly
                       (_scripted_model.py:625-642) → boundary change
                       cannot perturb the 5 goldens.
                       ══════════════════════════════════════════
```

### Pattern 1: Declared opt-in mirrors `input_providers`
**What:** A manifest key is data; the compiler materializes it; the runtime reads the compiled value; empty ⇒ dormant ⇒ byte-identical.
**When to use:** The D-15/C signal.
**Example:**
```yaml
# Source: agents/workflows/prototype/workflow.yaml:34,37 [VERIFIED]
context_providers: [opendesign]   # option A: reuse this as the template/DS-accept signal
input_providers: [run_images]     # the precedent — DATA-ONLY, name-free, dormant-when-empty
```

### Anti-Patterns to Avoid
- **Re-adding a workflow-name branch anywhere** (SC-001/INV-1). The seam must key on declared data.
- **Loading od_context inside `engine.execute`** to "make it generic." That touches the golden path and the engine (INV-13) — do it at the boundary, keep the engine's `od_context=` parameter contract.
- **Introducing a new `pipeline_complete` key** for D-15/C — none is needed (it's an input change). If one ever is, it MUST be added to `_VOLATILE_STRIP_KEYS` (`_normalize.py:101`) or the event goldens break.
- **Rebuilding composer surfaces from the mock** (see §Don't Hand-Roll + §FE Gotchas).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Capability list | Hardcode the mock's 8 `CAPDEF` | `GET /api/capabilities` (live) | Registry is a superset with `config_schema`, `security_gated`, `user_allowed`; hardcoding regresses D-15 + drops Engineer-only gating |
| Validator/gate coupling | Independent validator + gate toggles | `AdvancedExpander` COUPLED_GATE (`AgentsPopup.tsx:1318,1426-1432`) | Server `selections.py` enforces the coupling; a UI that drops it desyncs from the engine (EMP-04 regression) |
| Retry lever | Boolean retry | `RETRY_OPTIONS = [1,2,3]` int (`AgentsPopup.tsx:1322`) | Compiler materializes `retry:` → `Step.retry` int (WIRE-02); a bool compiles wrong |
| Per-agent model | New picker component | Mount the existing `AgentModelPicker.tsx` inline | It already round-trips `model_overrides` (mig 0021) + pins the WR-01 merge contract; a rebuild is a dual-impl (INV-3/12) |
| Save workflow | New persistence | `POST /api/user-workflows` (`user_workflows.py:247`) | Full CRUD shipped; only visibility is missing (deferred) |
| Draft persistence | Draft rows / DB / migration | `sessionStorage` `"prototype.draft"` idiom | ND-1/LOCK-E: client-side only |
| Template/DS acceptance | A per-deliverable code path | The declared-signal boundary seam | SC-001; additive; goldens safe |

**Key insight:** In this codebase the mock is *behind* the shipped product. Every "build from the mock" shortcut here deletes a real, tested behavior. Reuse is not a preference — it is the way to avoid regressing API-06/EMP-01/EMP-04/WIRE-02/MODEL-03.

---

## FE Reuse Gotchas (each is a verified regression trap)

### Gotcha 1: validator→gate coupling (COUPLED_GATE)
`[VERIFIED: AgentsPopup.tsx:1318]` `const COUPLED_GATE = "validation";` and `[VERIFIED: AgentsPopup.tsx:1426-1432]` — selecting a validator auto-adds the `validation` gate (comment: "EMP-04 (D-07): a validator selection requires the validation gate … mirroring selections.py. Removing all validators drops the auto gate"). **The mock drops this coupling.** Regression if dropped: a user enables a validator, the UI shows no gate, but the engine (server-side `selections.py` backstop) pauses on the coupled gate — the run appears to hang against the user's mental model (EMP-04 failure).

### Gotcha 2: retry is an int `[1,2,3]`, not a bool
`[VERIFIED: AgentsPopup.tsx:1305]` `retry?: number;` `[VERIFIED: AgentsPopup.tsx:1322]` `const RETRY_OPTIONS = [1, 2, 3];` `[VERIFIED: :1628]` `value={sel.retry ?? ""}`. The mock models retry as a boolean toggle. Regression: a bool cannot express max_attempts; the compiler's `retry:` → `Step.retry` (WIRE-02) materialization gets a wrong type and the transient-retry wrapper never activates.

### Gotcha 3: `AgentModelPicker` is built but UNMOUNTED
`[VERIFIED]` The only import of `AgentModelPicker` in `src/` is its own test file (`AgentModelPicker.test.tsx`); `HomeLaunchGrid.tsx` references it in a COMMENT only. So it is not mounted in production today. Mount it inline (evidence-08 delta = RESTRUCTURE). Regression if rebuilt instead: a duplicate implementation (INV-3/12) that loses the WR-01 seeded-override merge contract and DECIDE-02 premium-to-all-tiers behavior the existing tests pin.

### Gotcha 4: live registries, not the mock's hardcoded counts
Use `/api/capabilities` (not 8 `CAPDEF`), `/api/prototype/templates` (~43, not 12), `/api/prototype/design-systems` (~14 LOCK-F, not 5). `[VERIFIED: od_loader.py:185-206,373-378]` these list endpoints return the live disk registry. Regression: hardcoding the mock's counts silently drops ~31 templates, ~9 design systems, and every registry-driven capability + its `user_allowed`/`security_gated` semantics.

### Gotcha 5 (evidence-08 drift check): `WorkflowCatalog` → `HomeLaunchGrid`
`[VERIFIED]` The D-11 rename already landed: the file is `HomeLaunchGrid.tsx` (evidence-08 still references `WorkflowCatalog.tsx`). Map surfaces by content, not by the evidence's old name.

---

## Client-Side Draft Persistence (ND-1 / LOCK-E)

**Exact in-repo analog to copy (VERIFIED):** `frontend/src/app/workflow/prototype/templates/page.tsx`
- `[VERIFIED: :25]` `const STORAGE_KEY = "prototype.draft";`
- `[VERIFIED: :324-337]` on launch handoff: `sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ templateId, designSystemId, brief, ...(customDsBody?…), ...(customTemplateBody?…), ...(sourceRunId?…), ...(gatesTouched?{gateAgentIds}:{}), ...(modelOverrides…), ...(selections…), ...(images…), agentIds }))` then `router.push("/dashboard")`.
- `[VERIFIED: :98,:133-135]` read + `sessionStorage.removeItem(STORAGE_KEY)` exactly once on the dashboard redirect (comment: "Leaving it in sessionStorage causes every … redirect").

**The ND-1 pattern for the Configure "Save draft":** a single keyed JSON blob in `sessionStorage`, written on save/handoff, read + cleared at launch. **NO draft rows, NO DB, NO migration** — confirmed by POR line 99 (`[CITED: CHAT-AND-UI-CONVERGENCE-PLAN.md:99]`) and LOCK-E (`[CITED: :41]`). Distinguish from the sibling `chain.*` keys (`chain.from`, `chain.context_block`, `chain.brief`, `chain.source_run_id`) which carry run-chaining context, also in sessionStorage `[VERIFIED: :74-98,296-298]` — the Configure draft is a peer of `prototype.draft`, not of `chain.*`.

The mock's "Save draft" button is inert (`[C]:48`, evidence-08 fiction #3); the real behavior is exactly this sessionStorage idiom. The Configure draft payload is a superset of the launch payload (the same fields `LaunchCommand` accepts) so it can hydrate the launch directly.

---

## Validation Architecture

> `nyquist_validation: true` `[VERIFIED: .planning/config.json]` — section REQUIRED. Offline, unattended run: **never** start live servers; **never** run full pytest (hangs offline). Verify by DELTA.

### Test Framework
| Property | Value |
|----------|-------|
| Frontend framework | Vitest (`frontend/vitest.config.ts` present `[VERIFIED]`) + `tsc --noEmit` for type identity |
| Backend framework | pytest via `python3.11` (no venv) `[VERIFIED: backend/CLAUDE.md]` |
| Backend quick run | `cd backend && python3.11 -m pytest tests/agents/test_characterization_*.py tests/unit/test_rest_run_launch.py -q` |
| Goldens | `backend/tests/agents/characterization/golden/{prototype,od_prototype,od_ppt,app_builder,prototype_revision}.{html,events.json,wsframes.json}` `[VERIFIED]` |
| Import gate | `/opt/homebrew/bin/lint-imports` (target 4 kept / 0 broken) `[VERIFIED: verified-facts]` |
| e2e | Playwright — mocked suite is LIVE-DEFERRED (offline `webServer` reuse/timeout; `reuseExistingServer:true` `[VERIFIED: playwright.config.ts:45]`) |

### Phase Requirements → Test Map
| Req / deliverable | Behavior | Test type | Automated offline command | File exists? |
|-------------------|----------|-----------|---------------------------|--------------|
| D-15/C seam | 5 goldens byte + event identical after boundary change | characterization | `python3.11 -m pytest tests/agents/test_characterization_prototype*.py tests/agents/test_characterization_od_ppt.py -q` (SNAPSHOT_UPDATE **unset**) | ✅ |
| D-15/C seam | boundary builds SAME od_context dict for od_prototype/od_ppt via the generic signal | unit (NEW) | `python3.11 -m pytest tests/unit/test_rest_run_launch.py -q` (add od_context-parity cases) | ❌ **Wave 0** — today only `od_context=None` cases `[VERIFIED: test_rest_run_launch.py:274,369]` |
| D-15/C seam | a non-OD deliverable that DECLARES the signal now accepts template/DS; one that does not is unchanged | unit (NEW) | same file | ❌ **Wave 0** |
| D-15/C seam | no golden rewrite occurred | tree check | `git status --porcelain backend/tests/agents/characterization/golden/` → empty | ✅ (tooling) |
| D-15/C seam | wire parity holds (only if any event key added — none expected) | characterization | `python3.11 -m pytest tests/agents/test_wire_parity.py -q` | ✅ |
| Import purity | capabilities don't import kernel/app; boundary peek stays app-side | import gate | `/opt/homebrew/bin/lint-imports` → 4/0 | ✅ |
| Configure / composer / drawer reskin | components render + reused contracts hold (COUPLED_GATE, retry int, model merge) | unit (vitest) | `cd frontend && npx vitest run` | ✅ (extend existing `*.test.tsx`) |
| Token gate | retired palette = 0 in touched files | grep | `grep -REc "#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains" <file>` → 0 | ✅ tooling — see below |
| Type identity | no NEW tsc errors vs baseline | tsc | `cd frontend && npx tsc --noEmit` (compare error count to pre-phase baseline) | ✅ |

### Sampling Rate
- **Per task commit:** the narrow quick run for the touched tier (vitest for FE tasks; the two backend suites for the D-15/C task) + `tsc --noEmit` identity for FE.
- **Per wave merge:** full targeted backend suite (`tests/agents/` characterization + `tests/unit/test_rest_run_launch.py` + `test_wire_parity.py`) + `lint-imports` 4/0 + `npx vitest run`.
- **Phase gate:** all above green + goldens byte-identical (`git status` clean) + per-touched-file retired-palette grep = 0 with positive `@theme`/primitive usage. Live Playwright + any live-Bedrock check → deferred to Phase 34 (mark "live check pending").

### Token gate — the 3 files this phase touches (VERIFIED retired-palette present)
`[VERIFIED]` current retired-palette hit counts: `prototype/templates/page.tsx` = 6, `prototype/discovery/page.tsx` = 4, `ppt/templates/page.tsx` = 6. Each must reach 0 (per-file) with positive `@theme`/`ui/` primitive usage after the reskin.

### Wave 0 Gaps
- [ ] `backend/tests/unit/test_rest_run_launch.py` — ADD od_context-parity cases: `od_prototype`/`od_ppt` produce the exact dict the name-branch produced (dict-equality snapshot), and a declared-signal non-OD deliverable now loads od_context while an undeclared one stays `od_context=None`.
- [ ] (Backend) confirm no manifest OTHER than prototype/od_ppt declares the D-15/C signal before the seam ships (grep `agents/workflows/*/workflow.yaml` for `context_providers` / the chosen key).
- [ ] (Frontend) extend `AgentsPopup`/`AgentModelPicker`/`CapabilityPaletteSection` `*.test.tsx` to assert the reskin preserves COUPLED_GATE, retry-int, and the model-merge contract.
- [ ] No new framework install needed (Vitest + pytest present).

---

## Security Domain

> `security_enforcement: true` `[VERIFIED: .planning/config.json]`.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Ports & Adapters kept; boundary change is app-side, kernel-pure preserved (import-linter 4/0) |
| V4 Access Control | yes | Every launch/CRUD path stays owner-scoped, IDOR → 404 (`user_workflows.py:317-319` single-owner; `run_commands` two-layer owner check `[VERIFIED: run_commands.py:650-676]`) |
| V5 Input Validation | yes | `template_id`/`design_system_id` are looked up against the registry; unknown → `template_not_found` `[VERIFIED: run_commands.py:959-970]`. Custom bodies flow to the same loaders. Path-traversal on template assets is already contained `[VERIFIED: od_loader.py:289-315]` |
| V6 Cryptography | no | No crypto in scope |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-owner run launch / save | Elevation | Owner-scoped ORM filter + default-deny `ScopedStore`, 404 not 403 (already enforced) |
| Path traversal via `template_id` | Tampering | Single-segment reject + resolved-path containment (`od_loader.py:306-312`) — unchanged by the seam |
| Capability escalation (exec/network/secrets) | Elevation | `security_gated`/`user_allowed` reflected read-only; defaults OFF (unchanged) |
| Draft data leakage | Info disclosure | Draft is client `sessionStorage` (per-tab, not persisted server-side) — no server exposure |

**Security note for the seam:** making template/DS a generic declared input does NOT widen the attack surface — the payload fields already exist and are already registry-validated; the change only removes a name-branch guard. Keep the `template_not_found` validation on the generic path so an undeclared/garbage template still rejects pre-mint.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Route-split prototype/ppt template pages | Unified Configure screen + Web/Deck toggle | This phase | Consolidation; the generic seam is its enabler |
| Template/DS = prototype-only name-branch | Declared run-input any deliverable can opt into | This phase (D-15/C) | SC-001 compliance |
| `WorkflowCatalog.tsx` | `HomeLaunchGrid.tsx` (D-11) | Phase 36 (already landed) | Map by content, not evidence-08's old name |

**Deprecated/outdated:**
- Evidence-08 `[C]`/`[W]` mock data (8 caps / 12 templates / 5 DS, bool retry, no coupling) — mock fiction; never plan against it (POR §9).
- The orphaned `WorkflowComposer.tsx`/`CapabilityPalette.tsx` — DELETED-as-superseded in Phase 18 (ISS-014); do not resurrect. `/api/capabilities` is RETAINED.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No deliverable other than prototype/od_ppt declares the D-15/C signal today, so preserving the exact prototype/ppt loader mapping keeps their od_context byte-identical | Standard Stack / seam | If a third manifest already declares `opendesign`, the loader-profile choice needs to be declared too — VERIFY by grepping manifests at plan time (cheap) |
| A2 | D-15/C needs no new `pipeline_complete` key | Anti-Patterns / Validation | If a plan adds one, it MUST go into `_VOLATILE_STRIP_KEYS` or event goldens break — low risk (input change) |
| A3 | The 5 goldens never invoke the launch boundary (driven by `_scripted_model._drive` → `engine.execute`) | Summary / proof | VERIFIED at `_scripted_model.py:625-642` — high confidence; if a future golden is rerouted through the boundary, the proof strategy changes |
| A4 | Mocked Playwright e2e is offline-untestable (webServer timeout) | Validation | LOCK-G / evidence — live-deferred to Phase 34; if it were runnable offline the gate would tighten |

**Note:** most claims here are `[VERIFIED: file:line]` from files opened this session; the table above lists only the residual assumptions the planner should confirm.

---

## Open Questions

1. **Declared-signal shape (Option A vs B).**
   - What we know: both are additive and name-free; A reuses `context_providers:[opendesign]`, B adds `run_inputs`.
   - What's unclear: whether product wants "accepts template/DS" semantically separated from "injects OD context."
   - Recommendation: ship **A** (minimal, goldens-safe); it is reversible to B later. Leave a code comment naming the decision.

2. **Loader-profile genericity.**
   - What we know: prototype vs ppt loaders differ; keeping the exact mapping is byte-safe because no third deliverable reaches them.
   - What's unclear: whether the Configure screen will offer template/DS to a NEW deliverable this phase (which would need a loader profile).
   - Recommendation: for v1, expose the option in the UI but only workflows that DECLARE the signal actually load od_context; a genuinely new deliverable's loader profile is a follow-up, not the additive wave.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python3.11` | Backend targeted suites + goldens | ✓ (project runtime, no venv) | 3.11 | — |
| `/opt/homebrew/bin/lint-imports` | Import gate 4/0 | ✓ | — | — |
| Node/Vitest | FE unit + tsc identity | ✓ (`vitest.config.ts`) | — | — |
| Chromium (render_check) | prototype build validation | degrades to skip offline `[VERIFIED: backend/CLAUDE.md]` | — | skip (goldens unaffected — render skip is behavior-neutral, `workflow.yaml` require_render note) |
| Live Bedrock / servers | any live check | ✗ (unattended offline) | — | Defer to Phase 34; mark "live check pending" |

**Missing with fallback:** live Playwright + live Bedrock → deferred to Phase 34. **Blocking:** none — the whole phase is offline-verifiable by delta.

---

## Sources

### Primary (HIGH confidence — files opened this session)
- `backend/app/api/run_commands.py` (launch boundary `_resolve_launch_agents:934-978`, `LaunchCommand:900-921`, owner checks)
- `backend/app/api/websocket.py:1700-1770` (WS launch twin, name-branch)
- `backend/agents/execution_engine/od_context.py` + `backend/app/services/od_loader.py` (od_context loaders, template/DS registry, path-traversal containment, lru_cache)
- `backend/agents/workflows/{manifest.py,compiler.py,prototype/workflow.yaml}` (`_ALLOWED_TOP_KEYS`, `input_providers`/`context_providers` precedent, `resolve_alias`)
- `backend/tests/agents/characterization/{__init__.py,_normalize.py,_sse_projection.py}` + `test_characterization_od_ppt.py` + `_scripted_model.py:495-647` (golden harness, `_VOLATILE_STRIP_KEYS`, `_drive` seeds od_context)
- `backend/tests/unit/test_rest_run_launch.py` (launch-path coverage gap: only `od_context=None`)
- `frontend/src/components/workflow/AgentsPopup.tsx` (COUPLED_GATE:1318, RETRY_OPTIONS:1322, retry:number:1305) + `AgentModelPicker.tsx`/`.test.tsx` (unmounted)
- `frontend/src/app/workflow/prototype/templates/page.tsx` (STORAGE_KEY draft idiom)
- `.planning/config.json` (nyquist + security flags), `.planning/REQUIREMENTS.md` (SHELL-04, API-06/EMP/WIRE lineage)

### Secondary (MEDIUM — planning docs, cross-checked to code)
- `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` (POR §86, D-15/C, LOCK-E/F, ND-1, line 99 migrations)
- `.planning/v2.0-evidence/{08,12}` (composer/wizard teardown; backend categorization) — mock anchors treated as fiction per POR §9; current-code homes re-verified

### Tertiary (LOW) — none; all claims tied to opened files or cited POR lines.

## Metadata

**Confidence breakdown:**
- D-15/C seam + goldens proof: HIGH — boundary functions, golden driver, and `_VOLATILE_STRIP_KEYS` all read directly.
- FE gotchas: HIGH — COUPLED_GATE / retry-int / unmounted picker / retired-palette counts all grepped in current code.
- Client-side draft (ND-1): HIGH — exact analog read line-by-line.
- Declared-signal option choice: MEDIUM — a design choice with a clear recommendation; A2/A1 flagged for a cheap plan-time grep.

**Research date:** 2026-07-09
**Valid until:** ~2026-08-08 (stable brownfield; re-verify if the launch boundary or `_VOLATILE_STRIP_KEYS` changes)
