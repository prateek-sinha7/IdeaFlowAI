# Phase 37: Configure Unification + Composer/Wizard [B3] - Pattern Map

**Mapped:** 2026-07-09
**Files analyzed:** 26 surfaces (evidence-08 inventory) + D-15/C backend seam
**Analogs found:** 24 / 26 have a live analog (REUSE); 2 genuine NEW-BUILD; 3 evidence-08 anchors DRIFTED; 2 surfaces already substantially BUILT since evidence-08 (2026-07-07)

> **Load-bearing note:** REUSE is the dominant mode. Every anchor below was re-opened
> against current code on 2026-07-09 and corrected. A face-value rebuild from the mock
> REGRESSES the product (8 hardcoded caps vs live registry; bool retry vs `[1,2,3]`;
> drops validator→gate coupling). Plan REUSE against the VERIFIED file:line here.

---

## Drift & staleness ledger (read FIRST)

| Surface | evidence-08 said | VERIFIED 2026-07-09 | Class of change |
|---|---|---|---|
| `AdvancedExpander` | `AgentsPopup.tsx:1493` | section `:1293`, **export `:1337`**; `:1493` is mid-body | DRIFT (anchor → 1337) |
| `SkillsHooksTab` | `AgentsPopup.tsx:1944` | **definition `:715`**; `:1944` is the MOUNT site | DRIFT (def is 715, 1944 = usage) |
| `/api/user-workflows` client | `api.ts:709-808` | `UserWorkflowSummary` type `:771`, `listUserWorkflows` `:807`, **`createUserWorkflow` `:819`**, update `:854`, delete `:870` | DRIFT (→ ~771-880) |
| `user_workflows.py` CRUD | `:247-431` | `SaveUserWorkflowRequest` `:57`, create `:248`, list `:339`, get `:357`, update `:367`, delete `:436` (445 lines) | minor (→ 248-445) |
| `AgentModelPicker` inline mount | "built but UNMOUNTED — mount inline" | **Per-agent model logic ALREADY relocated inline** into AgentsPopup (`AdvancedExpander` Model lever + fetch shell `:1008`). Standalone `AgentModelPicker.tsx` (165 lines) imported ONLY by its own test. | **STALE — work largely DONE** |
| `DiscoveryForm` orphaned | "no code navigates to `/workflow/prototype/discovery`" | **Route page NOW EXISTS**: `app/workflow/prototype/discovery/page.tsx` (built, wires DiscoveryForm, reads `prototype.draft`, Skip support). But NO link navigates to it. | **DRIFT — page built, nav not wired** |
| Template/DS components path | `components/workflow/TemplateGallery.tsx` etc. | Moved under `components/workflow/prototype/`; `TemplateGallery.tsx` is **token-clean** + has `TemplateGallery.reskin.test.tsx`; `DesignSystemPicker.reskin.test.tsx` exists (Phase-36 reskin already landed) | path correction |

---

## File Classification

| Surface | Role | Data Flow | Closest Analog (VERIFIED) | Match / Delta |
|---|---|---|---|---|
| D-15/C run-launch seam | backend/route | request-response | `run_commands.py:934` `_resolve_launch_agents` | RESTRUCTURE (additive) |
| Configure screen accordions | page/component | CRUD/form | Phase-35 shell + Phase-36 surfaces + `DiscoveryForm` | NEW-BUILD (compose) |
| Capability palette | component | request-response | `AgentsPopup.tsx:1023` `CapabilityPaletteSection` | RESKIN |
| Advanced levers + validator→gate | component | event-driven | `AgentsPopup.tsx:1337` `AdvancedExpander` | RESKIN/RESTRUCTURE |
| Per-agent model picker | component | request-response | inline lever `AgentsPopup.tsx:1008`+`AdvancedExpander` Model | STALE (done) |
| `/api/user-workflows` CRUD | backend+client | CRUD | `user_workflows.py:248`; `api.ts:819` | RESKIN (wire button) |
| Template flow | component | request-response | `prototype/TemplateGallery.tsx` | RESKIN |
| Design-system flow | component | request-response | `prototype/DesignSystemPicker.tsx:256` (chip list) | RESTRUCTURE (band-cards) |
| Skills/hooks | component | request-response | `AgentsPopup.tsx:715` `SkillsHooksTab` | RESKIN |
| Add-agent palette | component | request-response | `AgentLibrary.tsx` + `AgentLibraryData.ts` | RESKIN |
| Run-draft launch | page | event-driven | `prototype/templates/page.tsx:25` (`prototype.draft`) | RESKIN |
| Unified Template→DS→Discovery stepper | component | request-response | none (route-split) — Phase-32/35 primitives | NEW-BUILD |
| Web/Deck toggle | component | request-response | separate `prototype/` vs `ppt/` routes | RESTRUCTURE |
| Wire orphaned DiscoveryForm | page/nav | form | `app/workflow/prototype/discovery/page.tsx` (built, un-navigated) | RESTRUCTURE (wire nav) |
| Workflow dialog (capabilities/user_allowed) | component | request-response | `CapabilityPaletteSection` + `WorkflowDetail` (`api.ts:643-700`) | RESKIN |

---

## Pattern Assignments — grouped by WAVE

### WAVE 1 — D-15/C backend (generic template/DS run inputs; plan FIRST, ADDITIVE)

#### Run-launch seam (`backend/app/api/run_commands.py`, `websocket.py`, `od_loader.py`)

**Analog / target:** `run_commands.py:934-978` `_resolve_launch_agents(body)` — the CURRENT
prototype-hardcoded branch:

```python
# run_commands.py ~948-971 (VERIFIED)
if pipeline_type == "od_prototype":
    base_pipeline_type = "prototype"
    od_context = load_prototype_od_context(body.template_id or "", body.design_system_id or "", ...)
elif pipeline_type == "od_ppt":
    base_pipeline_type = "od_ppt"
    od_context = load_ppt_od_context(body.template_id or "", body.design_system_id, ...)
if base_pipeline_type not in SUPPORTED_PIPELINE_TYPES: raise _reject(...)
return base_pipeline_type, od_context
```

- **`LaunchCommand`** already carries `template_id`, `design_system_id`, `custom_ds_body`,
  `custom_template_body` (`run_commands.py:916-919`). The WS twin passes them at
  `websocket.py:912-913` (`template_id=message_data.get("template_id")`, `design_system_id=...`).
- **D-15/C instruction:** the `pipeline_type == "od_prototype" / "od_ppt"` branch is the
  SC-001 violation to avoid EXTENDING. Attach a **declared, generic input seam** so any
  deliverable that DECLARES a `template`/`design_system` input (INV-5 manifest data)
  resolves od_context via the SAME path — NOT a new `elif <workflow-name>`. The prototype/PPT
  arms stay byte-identical (INV-3 goldens); other deliverables merely GAIN the branch via
  their manifest declaration.
- **`od_loader.py`** (`:133 _load_one_template`, `:169 _all_templates`) already reads
  template SKILL.md + DS DESIGN.md generically from disk — the RESOLVER is deliverable-agnostic;
  only the CALL SITE (`_resolve_launch_agents`) is name-gated. Keep the loader; generalize the caller.
- **Manifest declaration point (INV-5):** the declared input flag lives in manifest data,
  compiled — do NOT add a DSL. Map to where SUPPORTED_PIPELINE_TYPES / manifest inputs compile.
- **Regression a rebuild causes:** adding `elif "od_deck"...` per-workflow re-hardcodes the
  branch = SC-001 fail; touching the prototype/PPT arms breaks the 5 characterization goldens.

---

### WAVE 2 — Configure screen (generic per-run setup accordions)

#### `Configure screen` (NEW page composing Describe + Templates + DS + Review Gates + Workflow Settings)

**Analogs to compose (do NOT rebuild primitives):**
- Shell/chrome + token conventions: Phase-35 `.planning/phases/35-shell-chrome-reskin-pages-b1/35-PATTERNS.md`.
- Surface primitives (cards/accordions): Phase-36 `.planning/phases/36-home-history-my-workflows-b2/36-PATTERNS.md`.
- Describe/Discovery body: `components/workflow/prototype/DiscoveryForm.tsx` (`DiscoveryAnswers`
  `:20-29` = `template, surface, audience, tone, scale, constraints`; render `:48+`).
- Templates: `TemplateGallery.tsx`; DS: `DesignSystemPicker.tsx`; Review Gates: `AdvancedExpander`.
- **Regression:** hand-rolling accordions/token values re-introduces retired palette; reuse Phase-35/36 primitives + `@theme` tokens.

---

### WAVE 3 — Composer reskin (REUSE live P22 code — do NOT rebuild from mock)

#### Capability palette → `AgentsPopup.tsx:1023` `CapabilityPaletteSection`

- Live `GET /api/capabilities` (`backend/app/api/capabilities.py:56,112 list_capabilities`).
  Entries: `{kind, name, description, config_schema, security_gated, user_allowed}`.
  `security_gated`→Lock; `user_allowed=false`→"Engineer-only" locked.
- Declared strip: `AgentsPopup.tsx:1101-1119` (SURF-03) via `WorkflowDetail` (`api.ts:643-700`).
- **Regression:** the mock's 8 hardcoded `CAPDEF` DROP the generic registry, `config_schema`,
  and the `user_allowed` gate — a rebuild ships a stale 8-cap list and breaks Engineer-only gating.

#### Advanced levers + validator→gate → `AgentsPopup.tsx:1337` `AdvancedExpander`

- Levers Validator·Gate·Model·Retry. `StepSelection` type `:1301-1307` (`{validators?, gates?, model?, retry?}`).
- **Validator→Gate coupling:** `COUPLED_GATE = "validation"` (`:1318`); auto-attach logic
  `:1432` (`gates.add(COUPLED_GATE)`), `:1473`, `:1541-1546`, notice `:1655`.
- **Retry:** `RETRY_OPTIONS = [1, 2, 3]` (`:1322`); `sel.retry` is an INT (`:1305`, `:1628`), NOT bool.
- Persistence: `model_overrides` JSON col + `selections` in `manifest_json` (migration 0021).
- **Regression:** mock omits the coupling (backend `selections.py` enforces it) and models
  retry as bool → a rebuild lets a gate exist without its validator and truncates retry to on/off.

#### Per-agent model picker — STALE (already inline)

- Standalone `AgentModelPicker.tsx` (165 lines, + `AgentModelPicker.test.tsx`) is imported
  ONLY by its own test. The per-agent model selection was ALREADY relocated INLINE into
  AgentsPopup (`AdvancedExpander` Model lever + fetch/loading shell `AgentsPopup.tsx:1008`).
- **Instruction:** do NOT re-mount the standalone file. Confirm the inline lever satisfies the
  "inline per-agent model" intent; treat `AgentModelPicker.tsx` as dead/legacy (decide keep vs delete).
- **Regression:** mounting the standalone file duplicates the inline lever = INV-3 dual-implementation.

#### Skills/hooks → `AgentsPopup.tsx:715` `SkillsHooksTab` (mounted `:1944`)

- Data: `src/data/skills.ts`, `src/data/hooks.ts`. Keep the **suggested-per-agent** model
  (`compatible_agents`) — mock only has global toggles.
- **Regression:** rebuilding as global-only drops per-agent suggestions.

#### `/api/user-workflows` CRUD → `user_workflows.py:248` + `api.ts:819`

- Backend: `SaveUserWorkflowRequest:57` (`{name, description?, base_pipeline_type,
  agent_ids[≥1], model_overrides?, selections?}`); create `:248`, list `:339`, get `:357`,
  update `:367`, delete `:436`. Owner-scoped (`user_id==owner_id==workspace_id`).
- Client: `UserWorkflowSummary:771`, `listUserWorkflows:807`, `createUserWorkflow:819`,
  update `:854`, delete `:870`. Save UI: `components/catalog/NameWorkflowModal.tsx`.
- **Regression:** the mock's Visibility "Just me/Team" cards have NO backend (owner-only) —
  DECLARED OUT (ND-12). Wire the save button to `createUserWorkflow`; do not build sharing.

#### Add-agent palette → `AgentLibrary.tsx` + `AgentLibraryData.ts`

- Already richer than mock (search + categories + emoji icons + `estimated_duration`). RESKIN only.

#### Workflow dialog (declared capabilities/context/compaction + Engineer-only)

- Reuse `CapabilityPaletteSection` + declared strip `:1101-1119`; "Engineer-only" = `user_allowed=false`
  reflection (INV-5 data, not a code branch).

---

### WAVE 4 — Wizard / stepper (NEW-BUILD + wiring)

#### Unified Template→DS→Discovery stepper + Web/Deck toggle — NEW-BUILD

- No stepper component exists (flow is route-split `prototype/templates` vs `ppt/templates`).
- Closest reuse: Phase-32/35 segmented-control / layout primitives (see 35-PATTERNS.md); the
  step BODIES already exist — `TemplateGallery.tsx` (Web) / `PPTTemplateGallery.tsx` (Deck),
  `DesignSystemPicker.tsx`, `DiscoveryForm.tsx`. Build the stepper CHROME + Web/Deck toggle
  that swaps template family; reuse the step bodies unchanged.
- **Regression:** rebuilding the grids/cards from the mock re-hardcodes 12 templates / 5 DS
  and loses live `GET /api/prototype/templates` (~43) + live iframe previews.

#### Template grid → `prototype/TemplateGallery.tsx` (token-clean; `TemplateGallery.reskin.test.tsx`)

- Live `GET /api/prototype/templates`; `TemplateDetailModal.tsx`; `CustomTemplateModal`
  (`loadCustomTemplates` localStorage); blank-canvas card (KAN-87). RESKIN into the stepper.

#### DS flow → `prototype/DesignSystemPicker.tsx` (chip list `:256`) — RESTRUCTURE to band-cards

- Currently rounded-pill CHIP list (`:256` "Chip list", `:297/:410` `rounded-[var(--radius-pill)]`);
  swatches live only in `DesignSystemDetailModal.tsx`. Live `GET /api/prototype/design-systems`.
- Mock wants a 3-band swatch-card grid = genuine RESTRUCTURE (LOCK-F/ND-8, ~14 real DS).
- **Regression:** keep the real ~14 registry + detail-modal live preview; do NOT hardcode 5 DS.

#### Wire orphaned DiscoveryForm — RESTRUCTURE (nav wiring)

- `app/workflow/prototype/discovery/page.tsx` EXISTS (built: reads `prototype.draft`, fetches
  template `od.inputs`, Skip support) but NO link navigates to it. `DiscoveryForm.tsx`
  `DiscoveryAnswers` = `{template, surface, audience, tone, scale, constraints}` (`:20-29`) —
  NO `pages` field (page-selection is DECLARED OUT, ND-12).
- **Instruction:** wire the stepper's Discovery step to this page/component; reconcile audience/tone
  enums per POR (keep `surface`/`scale`). Do NOT add `pages`.
- **Regression:** ignoring the built page duplicates discovery UI (INV-3 dual-impl).

---

### WAVE 5 — Agent drawer + draft

#### Agent drawer Config tab (ND-7 override-persistence DEFERRED)

- Surface per-agent prompt override via `AgentPromptSection` (`AgentsPopup.tsx:197`, mounted `:514`).
  LOCK-E: SURFACE only — do NOT build durable override storage.

#### Run-draft launch (ND-1 client-side only)

- `prototype/templates/page.tsx:25` `STORAGE_KEY = "prototype.draft"`; sessionStorage read
  `:98`, cleared `:135`; `run_pipeline` WS launch. Draft payload superset (from evidence-08):
  `{templateId, designSystemId, brief, gateAgentIds?, modelOverrides?, selections?,
  customDsBody?, customTemplateBody?, images?, agentIds}`.
- **Instruction:** ND-1 = CLIENT-SIDE draft, kept until launch, NO DB rows (LOCK-E, Q3 additive).

---

## Shared Patterns

### Token gate (Phase-35 discipline — per-file retired-palette = 0)
Retired palette (`#1B2A4A`/`#2563eb`/`#f5f5f0`/Inter/Fraunces/JetBrains) VERIFIED present in — scope the grep gate here:
- `app/workflow/prototype/templates/page.tsx` — `#1B2A4A`×4, `#f5f5f0`×3
- `app/workflow/prototype/discovery/page.tsx` — `#1B2A4A`×1, `#f5f5f0`×3
- `app/workflow/ppt/templates/page.tsx` — `#1B2A4A`×4, `#f5f5f0`×3
- `components/workflow/AgentsPopup.tsx` — `#1B2A4A`×19
CLEAN already: `TemplateGallery.tsx`, `DesignSystemPicker.tsx` (Phase-36 reskin landed).

### Selections/model persistence (migration 0021)
`model_overrides` JSON col + `selections` in `manifest_json`; validated at save
(`user_workflows.py:112 _validate_model_overrides`, `:150 _compile_selections_trust_user`)
and re-validated at launch (`websocket.py:121, :270 _revalidate_selections_trust_user`).

### Live registries (never hardcode)
`GET /api/capabilities` (`capabilities.py:112`), `GET /api/prototype/templates`,
`GET /api/prototype/design-systems`, live `model_catalog`.

---

## DECLARED OUT — no analog to build (ND-12 / Category-B/D / LOCK-E)

| Surface | Reason |
|---|---|
| Workflow visibility / team-sharing (mock "Just me/Team") | Owner-only (`user_workflows.py:317-319`); no sharing column — DECLARED OUT |
| Pre-run cost estimate | No endpoint (post-run only `TokenUsageSummary.tsx`) — DECLARED OUT |
| Pre-run duration estimate (composed wf) | Only legacy static sum `WorkflowView.tsx` — DECLARED OUT |
| Discovery page-selection (`pages` multi-select) | Absent end-to-end; `DiscoveryAnswers` has no `pages` — DECLARED OUT |
| Per-agent prompt-override PERSISTENCE (ND-7) | LOCK-E — Config tab SURFACES only, no durable store |
| ND-1 draft ROWS / DB | LOCK-E — client-side sessionStorage only |
| Transport / engine / runner / new tables | LOCK-B / INV-13 / Q3 — untouched |

---

## Metadata

**Analog search scope:** `frontend/src/components/workflow/**`, `frontend/src/app/workflow/**`,
`frontend/src/components/catalog/**`, `backend/app/api/{run_commands,websocket,user_workflows,capabilities}.py`,
`backend/app/services/od_loader.py`.
**Files scanned:** ~20. **Extraction date:** 2026-07-09.
