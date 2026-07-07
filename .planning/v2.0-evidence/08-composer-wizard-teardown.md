# Composer + Wizard Teardown (workflow-building surfaces)

> **Evidence doc — Milestone v2.0** (see `README.md` + POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`).
> Verbatim final report of a `ui-teardown` investigation agent, 2026-07-07 (second batch — the five sibling screens + cross-mock reconciliation). Feeds Phase 37 (Configure Unification) — upgrades its soft 'composer/wizard alignment' note into contract-backed scope.
> Anchors are as-of 2026-07-07; verify before acting.

---

The mapping agent returned comprehensive, file:line-anchored current-product data. I now have everything needed. Composing the full teardown as my final deliverable.

---

# UI TEARDOWN — Hexaware Composer & Wizard (workflow-building surfaces)

**Sources torn down (read in full, EOF):**
- **[C]** `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Composer.dc.html` (306 lines) — standalone custom-workflow builder.
- **[W]** `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Wizard.dc.html` (255 lines) — interactive-prototype setup wizard.

**DC framework mechanics (confirmed against `support.js`):** Each page is a single `<x-dc>` block + one `<script data-dc-script>` defining `class Component extends DCLogic`. `renderVals()` (merged over `data-props`) returns every `{{ binding }}`. Control tags: `<sc-if value="{{ flag }}">`, `<sc-for list="{{ arr }}" as="x">`, `<sc-helmet>` (head injection). `onClick="{{ fn }}"` wires handlers; `style-hover="…"` compiles to a **real** `:hover` pseudo-class (`support.js:397`) — so hover states are genuine, not fiction. `hint-placeholder-count` / `hint-placeholder-val` are **design-time render hints** (how many placeholder rows to draw before data binds), not runtime data. **ALL-CAPS class fields are hardcoded mock data**; `state` is mutated only via `setState` (`support.js:724`). Neither file makes a single network call — all data is client-side constants.

Both mocks share the same palette: page bg `#F0EEE7`, surface `#FCFBF7`/`#FFFFFF`, ink `#15161A`, muted `#8A8B82`/`#9A9B92`, borders `#E6E3DB`/`#E0DDD3`, **accent indigo `#3C2CDA`**; fonts Manrope (UI) + Heebo (body).

---
---

# PART A — [C] COMPOSER (`Hexaware Composer.dc.html`)

## A1. Page / state inventory

One page, one live layout, **three overlay states** driven by boolean state flags. There is no multi-page state machine — the whole composer is always mounted; overlays stack on top.

State object (`[C]:209-218`):
| field | init value | domain / meaning |
|---|---|---|
| `agents` | `['OR','MR','AR','CG','TI']` | ordered pipeline of agent-ids (keys into `AG`) |
| `modelFor` | `{OR:'opus',CG:'opus',TI:'sonnet'}` | per-agent model override; missing ⇒ `'opus'` fallback (`:264`) |
| `advFor` | `{AR:{gate:true},TI:{validator:true}}` | per-agent advanced toggles (`validator`/`gate`/`retry`) |
| `caps` | `{filesystem,web_search,context = true; compaction,exec,network,secrets,spawn = false}` | 8 capability on/off flags |
| `skills` | `{'Writing Plans':true,'Adversarial Pair Review':true}` | skill on/off map |
| `hooks` | `{'Quality Gate':true}` | hook on/off map |
| `modelMenu` | `null` | agent-id whose model dropdown is open (or null) |
| `addOpen` | `false` | add-agent modal visibility |
| `saveOpen` | `false` | save-workflow modal visibility |
| `wfName` | `'Competitive Research'` | workflow name (never edited — see fiction) |
| `strategy` | `'sequential'` | execution strategy (read-only display) |

Overlay states: **(a)** model dropdown per row (`modelMenu===id`, `:91`); **(b)** Add-agent modal (`addOpen`, `:164`); **(c)** Save-workflow modal (`saveOpen`, `:187`). Navigation *out* of the page: every top-bar/back/logo link → `Hexaware Workspace v2.dc.html`; "Run once now" (`:157`) and "Save workflow" completion (`:200`) → `Hexaware Run - Live.dc.html` / Workspace v2. There is **no forward stepper** — this is a single editing canvas.

## A2. Layout regions

1. **Top chrome bar** (`:30-42`) — dark `#111114`: HEXAWARE wordmark+dot (`:31-34`, →Workspace v2), centered nav Home/Library/**Catalogue**(active, indigo underline `:38`), right avatar chip "AK" (`:41`).
2. **Page header** (`:45-50`) — back-chevron (`:46`), eyebrow "Custom workflow · Composer" + `<h1>{{ wfName }}</h1>` (`:47`), **"Save draft"** button (`:48`, inert), **"Save workflow"** primary button (`:49`, `openSave`).
3. **Scroll body** (`:52`) — centered `max-width:1200px`, **two-column grid `1fr / 320px`** (`:53`): main column + sticky summary rail.
4. **Main column** (`:56-137`): Identity card → Agent-pipeline section → Capability-palette card → Skills-&-hooks card.
5. **Summary rail** (`:140-158`) — `position:sticky` white card.
6. **Add-agent modal** (`:164-184`) — scrim + centered 640px sheet; trigger `openAdd` (`:71`), dismiss `closeAll` (scrim/close-X) or `stop` on inner click.
7. **Save-workflow modal** (`:187-203`) — scrim + 440px sheet; trigger `openSave` (`:49`,`:156`), dismiss `closeAll`.

## A3. Per-region element enumeration

### A3.1 Identity card (`:59-66`)
- Eyebrow "Workflow" (`:60`). Grid 2-col:
  - **Name** field (`:62`) — renders `{{ wfName }}` inside a styled `<div>`, **not an `<input>`** ⇒ inert (fiction).
  - **Deliverable type** (`:63`) — static text "Custom" + chevron icon; **inert** (no dropdown handler).
  - **Description** (`:65`) — hardcoded paragraph ("Market scan then a sized-opportunity summary for the GPU inventory product…"); inert.

### A3.2 Agent-pipeline section (`:69-107`)
- Header (`:70`): `<h2>Agent pipeline</h2>` + subtitle **"{{ agN }} agents · runs {{ strategy }} · drag to reorder"**. **"drag to reorder" is fiction** — reorder is via up/down arrow buttons only (`moveAgent`, `:247`); no drag handlers exist.
- **"Add agent"** button (`:71`, `openAdd`).
- **Agent rows** — `<sc-for list="{{ rows }}" as="a">` (`:75-106`), one card per pipeline agent (`rowStyle` `:273`; border → lilac `#C7BEF5` when this row's model menu is open). Each row's sub-elements:
  - **Reorder up/down** (`:79-80`) — `a.onUp`/`a.onDown` (`moveAgent(i,±1)`); disabled (grey, `cursor:default`) at first/last (`iconBtn(dis)` `:262`, `:267`).
  - **Index** (`:82`) — 2-digit zero-padded position (`String(i+1).padStart(2,'0')`, `:265`).
  - **Avatar** (`:83`) — 2-char initials; locked agents tinted indigo `#ECEAFC`/`#3C2CDA` (`avatarStyle` `:272`).
  - **Name + Core badge** (`:85`) — name; if `a.locked` a lock-icon **"Core"** pill.
  - **Role** (`:86`) — one-line role string.
  - **Model picker** (`:89-96`) — clickable pill showing `{{ a.modelLabel }}` (short model name) + chevron (`onToggleModel` `:250`); when `a.modelMenuOpen`, a 210px dropdown (`:92-94`) lists all 3 `MODELS`, selected one shows a check (`m.sel`) and highlights (`#F4F2FB`), `m.onClick`→`setModel` (`:251`).
  - **Remove** (`:97`) — X button; for locked agents `onRemove` is a **no-op** and cursor `not-allowed` (`:266`,`:268`).
  - **Overrides row** (`:99-104`) — label "Overrides" + 3 `advChips` (`:101`): **Validator / Gate / Retry** toggle-pills (`chip(on)` `:261`; on ⇒ dark fill `#15161A`), `c.onClick`→`toggleAdv(id,key)` (`:252`). Trailing **"Custom prompt →"** (`:103`) — styled `<span>`, **no handler** (inert).

### A3.3 Capability-palette card (`:110-121`)
- Shield icon + `<h2>Capability palette</h2>` (`:111`); explainer "Only allow-listed capabilities can be enabled. Execution, network and secrets stay off behind the security gate; some capabilities are engineer-only." (`:112`).
- Grid 2-col of `<sc-for list="{{ capItems }}">` (`:114-119`) — 8 cards (`CAPDEF`). Each (`:115-117`): name + optional **gated tag** ("Gated" grey, or "Engineer-only" amber for `engineer:true`, `:279-280`), note, and a **toggle switch** (`toggleStyle`/`knobStyle` `:283-284`; on ⇒ indigo). `c.onClick`→`toggleCap` **except** engineer-only caps where onClick is a no-op and cursor `not-allowed` (`:281`), card dimmed to `opacity:.72` (`:282`).

### A3.4 Skills-&-hooks card (`:124-135`)
- `<h2>Skills & hooks</h2>` + explainer (`:125-126`).
- **Skills** (`:127-130`) — `skillChips` (`:129`): 4 toggle-pills (checkmark when on), `toggleSkill` (`:254`).
- **Hooks** (`:131-134`) — `hookChips` (`:133`): 3 toggle-pills, `toggleHook` (`:255`). (`hint-placeholder-count="4"` but only 3 hooks exist — minor mismatch.)

### A3.5 Summary rail (`:140-158`)
- Eyebrow "Summary" (`:141`).
- Two stat tiles: **{{ agN }} Agents** (`:143`), **{{ gateN }} Review gates** (`:144`).
- Three rows (`:147-149`): **Strategy** `{{ strategy }}`, **Est. duration** `{{ estTime }}`, **Est. cost** `{{ estCost }}`.
- **Declared capabilities** (`:151-155`): indigo chips from `declared`, or "None enabled" when `noDeclared`.
- **"Save to catalogue"** button (`:156`, `openSave`) + **"Run once now"** link (`:157`, →Run - Live).

### A3.6 Add-agent modal (`:164-184`)
- Scrim (`:165`, `closeAll`) + sheet (`:166`, `stop`). Title "Add an agent" / "Pick from the allow-listed agent catalogue." (`:168`); close-X (`:169`).
- `<sc-for list="{{ palette }}">` rows (`:172-179`): initials avatar, name, role, **category badge** `{{ a.cat }}`, + icon; `a.onClick`→`addAgent`. Empty state (`:180`, `paletteEmpty`): "Every catalogue agent is already in the pipeline." `palette` = `AG` keys minus in-pipeline minus locked (`:276`) — with the default pipeline this yields **6 candidates** (US, UX, AC, DM, SA, SG).

### A3.7 Save-workflow modal (`:187-203`)
- Title "Save to catalogue" / "Reusable from your Workflow Catalogue and shareable with your team." (`:190`).
- **Workflow name** (`:192-193`) — styled div showing `{{ wfName }}`, **not an input** (inert).
- **Visibility** (`:194-198`) — two cards: **"Just me"** (pre-selected, 2px indigo border `:196`) and **"Team / Shared with Hexaware"** (`:197`). **Both are inert** — no onClick, no state binding; the selection is hardcoded.
- Footer: **Cancel** (`closeAll`) + **Save workflow** link (`:200`, →Workspace v2).

### A3.8 Derived / computed bindings (`renderVals` `:259-301`)
- `agN` = `agents.length` (`:289`) → 5.
- `gateN` = count of pipeline agents with `advFor[id].gate` (`:290`) → 1 (AR).
- `declared` = names of enabled caps (`:291`) → default [File system, Web search, Context packs].
- `estTime` = `'~' + max(2, agN*4) + 'm'` (`:292-293`) → "~20m" — **synthesized**.
- `estCost` = `'$' + (agN*0.9).toFixed(2)` (`:294`) → "$4.50" — **synthesized**.

## A4. Data contract — [C] Composer

**Workflow (root)** — `wfName:string` · `strategy:enum('sequential')` (only value present; display-only) · `deliverable_type:'Custom'` (static) · `description:string` (static) · `visibility:enum('just_me'|'team')` (inert) · `agents:orderedList<agentId>`.

**Agent catalogue entry** (`AG` `:220-232`, 11 entries keyed by 2-char id) — `init:string(2)` · `name:string` · `role:string` · `cat:enum('Core'|'Custom'|'App Builder'|'Testing'|'Security'|'Platform')` · `locked?:bool` (only OR). Full list: OR Orchestrator(Core,locked) · MR Market Research(Custom) · AR Architecture(App Builder) · US User Stories(App Builder) · UX UX & UI Design(App Builder) · AC API Contract(App Builder) · DM Data Model(App Builder) · CG Code Generation(App Builder) · TI Test Implementation(Testing) · SA Security Architecture(Security) · SG SDLC Governance(Platform).

**Per-agent config** — `model:enum(opus|sonnet|haiku)` (`modelFor`) · `advanced.validator:bool` · `advanced.gate:bool` · `advanced.retry:bool` (`advFor`) · `custom_prompt` (referenced by inert link, no field).

**Model** (`MODELS` `:233`, 3) — `id:enum(opus|sonnet|haiku)` · `name` ("Claude Opus 4.5" / "Claude Sonnet 4.5" / "Claude Haiku 4.5") · `short` ("Opus 4.5" / "Sonnet 4.5" / "Haiku 4.5").

**Capability** (`CAPDEF` `:234-243`, 8) — `id` · `name` · `note` · `gated?:bool` (exec, network, secrets, spawn) · `engineer?:bool` (secrets, spawn) · `enabled:bool` (`caps[id]`). Ids: filesystem, web_search, context, compaction, exec, network, secrets, spawn.

**Skill** (`SKILLS` `:244`, 4) — `name:string` · `on:bool`. Values: Writing Plans, Adversarial Pair Review, Systematic Debugging, Handoff & Artifacts.

**Hook** (`HOOKS` `:245`, 3) — `name:string` · `on:bool`. Values: Quality Gate, GateGuard: Fact Force, Session Context Loader.

**Summary (derived)** — `agN:int` · `gateN:int` · `estTime:string`(synthesized) · `estCost:string`(synthesized) · `declared:string[]`.

## A5. Design language — [C]

Tokens: bg `#F0EEE7`; cards `#FCFBF7`, inner fields `#FFFFFF`; ink `#15161A`, secondary `#3A3B42`/`#6E6F76`, muted `#8A8B82`/`#9A9B92`/`#A0A199`; borders `#E6E3DB`/`#E0DDD3`/`#EDEBE3`; accent `#3C2CDA` (hover `#3324c4`); accent tints `#ECEAFC`/`#F7F5FE`/`#F4F2FB`; engineer-amber `#9A6B1E` on `#F5EEDD`. Radii 8–18px (fields 8-9, cards 11-16, modals 18). Elevation: cards `0 8px 30px rgba(17,17,20,.05)`, modals `0 30px 80px rgba(17,17,20,.3)`. Motion: `scrimIn`/`popIn` keyframes (`:22-23`). Idioms: **toggle-pill** (`chip()` — dark-fill on), **switch** (38×22 track, 18px knob slides `2px↔18px`), **stat tile**, **badge pill** (Core / category / gated tag), **sticky summary rail**. Numeric fields use `.tnum` tabular-nums.

## A6. Fiction register — [C] (never skip)

1. **"drag to reorder"** subtitle (`:70`) — **no drag**; reorder is up/down arrows only (`moveAgent` `:247`). Mislabeled affordance.
2. **Name / Deliverable type / Description** (`:62,63,65`) — styled `<div>`s, not inputs; **not editable**. Values fixed ("Competitive Research", "Custom", GPU-inventory blurb).
3. **"Save draft"** button (`:48`) — no `onClick`, inert.
4. **"Custom prompt →"** (`:103`) — `<span>`, no handler.
5. **`estTime`** (`:293`) — `agN*4` minutes, synthesized, not a real estimate.
6. **`estCost`** (`:294`) — `agN*0.9` dollars, synthesized fake cost.
7. **Save-modal Workflow name** (`:193`) — inert div, not editable.
8. **Visibility "Just me / Team" cards** (`:196-197`) — **fully inert**; no handler, no state; "Just me" hardcoded-selected.
9. **All save/run actions are hrefs** — "Save workflow"/"Save to catalogue"/"Save workflow"(modal)/"Run once now" (`:49,156,200,157`) navigate away; the composed state (agents/models/caps/skills/hooks) is **never persisted or passed**. Zero API calls in the script.
10. **Model list hardcoded to 3** (`MODELS`) and **capability list hardcoded to 8** (`CAPDEF`) — real product pulls both from live registries.
11. **Hooks placeholder mismatch** — `hint-placeholder-count="4"` (`:133`) vs 3 real hooks.
12. **Top-bar nav + "AK" avatar** — decorative; all nav links → Workspace v2.
13. `gateN` (`:290`) is a *real projection* of the `gate` toggles (not fiction) but is easy to misread as an independent count.

## A7. Current-product mapping + delta — [C]

Modern composer surfaces already exist across **`WorkflowView.tsx`** (legacy dark composer) and the **P22 `AgentsPopup.tsx`** (1989 lines: Agents-tab flow-graph + Workflow-tab). The mock proposes a **single-page, light-theme composer with a sticky summary rail** — a layout the current product does not have (current = modal/popup + separate legacy route).

| [C] element (line) | Current home (`file:line`) | Delta | Notes / gaps |
|---|---|---|---|
| Single-page composer layout w/ sticky summary rail (`:52-158`) | Split across `WorkflowView.tsx` (page) + `AgentsPopup.tsx` (modal) | **RESTRUCTURE** | No unified full-page composer today; AgentsPopup is a tabbed modal. |
| Identity card: name/type/description (`:59-66`) | `NameWorkflowModal` (save-time) + data cols `base_pipeline_type`,`description` (mig `0021`) | **RESTRUCTURE** | Fields exist in data model + save modal; no up-front identity card. Mock's are inert anyway. |
| Agent pipeline list + reorder (`:74-107`) | `WorkflowView.tsx:414-450` (HTML5 DnD `:185-202`); `AgentsPopup.tsx:1864-1920` (flow-graph DnD, roles/locked `:126-164`) | **RESKIN** | Reorder + locked-Core already exist; current uses **drag** (mock uses arrows). |
| Per-agent inline model picker (`:89-96`) | `AdvancedExpander` **Model lever** (`AgentsPopup.tsx:1374-1385`, live `model_catalog`); `AgentModelPicker.tsx` **exists but unmounted** | **RESTRUCTURE** | Capability + persistence (`model_overrides`, mig `0021`) exist; mock's *inline-per-row* placement differs from current *modal-buried lever*. Mock validates mounting `AgentModelPicker`. Mock hardcodes 3 models vs live catalog. |
| Advanced chips Validator/Gate/Retry (`:99-104`) | `AdvancedExpander` levers Validator·Gate·Model·Retry (`AgentsPopup.tsx:1493`), `StepSelection` (`:1301-1307`) | **RESTRUCTURE** | Maps 1:1 to `selections{validators,gates,retry}`. **Mock omits Validator→Gate coupling** (current auto-attaches `COUPLED_GATE` `:1318`); Retry is `[1,2,3]` int in current vs bool in mock. |
| "Custom prompt →" (`:103`) | `AgentPromptSection` in `AgentCapabilitiesModal` (`AgentsPopup.tsx:197,514`) — per-user system-prompt override, server-side | **RESKIN** | Real surface is richer; mock link is inert. |
| Capability palette, 8 hardcoded (`:110-121`) | `CapabilityPaletteSection` (`AgentsPopup.tsx:986-1290`), live `GET /api/capabilities` | **RESKIN** | Current is a **data-driven superset**: generic kinds, `config_schema`, `security_gated`→Lock, `user_allowed=false`→"Engineer-only" locked. Mock's gated/engineer semantics align; **drop the hardcoded `CAPDEF`, use the live registry.** |
| Skills & hooks chips (`:124-135`) | `SkillsHooksTab` (`AgentsPopup.tsx:1944`) ← `src/data/skills.ts`, `src/data/hooks.ts` | **RESKIN** | Mock = workflow-global toggles; current also has **Suggested per-agent** (`compatible_agents` `:419-420`). |
| Summary: Agents/Review-gates/Strategy (`:143-147`) | Declared-cap read-only strip (`AgentsPopup.tsx:1099-1119`, SURF-03); strategy read-only (`IdeaInputPage.tsx:302`) | **RESKIN** | agN/gateN derivable; strategy is display-only in both (no selector — correct). |
| Summary **Est. duration** (`:148`) | Only legacy `WorkflowView.tsx:204,232` (static `estimated_duration` sum); absent in wizards | **BACKEND-NEEDED** | No pre-run duration for a *composed* workflow. Mock value synthesized. |
| Summary **Est. cost** (`:149`) | **None pre-run**; post-run only `TokenUsageSummary.tsx` (`estimatedCostUsd`) | **BACKEND-NEEDED** | Needs a pre-run cost-estimate endpoint. Mock value synthesized. |
| Declared-capabilities chips (`:151-155`) | `declaredCapabilities` strip (`AgentsPopup.tsx:1099-1119`) via `WorkflowDetail` (`src/lib/api.ts:643-700`) | **RESKIN** | Already a compiled per-step projection. |
| Save to catalogue (`:156,49,200`) | `POST/GET/PATCH/DELETE /api/user-workflows` (`backend/app/api/user_workflows.py:247-431`); `NameWorkflowModal`; `src/lib/api.ts:709-808` | **RESKIN** | Full CRUD exists (mig `0021`). Wire the button to `createUserWorkflow`. |
| **Visibility "Just me / Team"** (`:194-198`) | **DOES NOT EXIST** — workflows are strictly single-owner (`user_id==owner_id==workspace_id`, `user_workflows.py:317-319`); no `visibility`/`shared`/`team` column or field | **BACKEND-NEEDED + NEW-BUILD** | Real gap: needs a sharing column + endpoint **and** UI. (`WorkflowCatalog.tsx:63` `user_launchable` is product-workflow gating, unrelated to user-to-user sharing.) |
| "Save draft" (`:48`) | No draft concept for *saved workflows* (sessionStorage drafts exist only for prototype/ppt *runs*) | **NEW-BUILD** (if wanted) | Currently fiction. |
| "Run once now" (`:157`) | `run_pipeline` WS launch (via `DashboardLayout`) | **RESKIN** | Compose-then-launch path exists. |
| Add-agent modal (`:164-184`) | `AgentLibrary.tsx` + `AgentLibraryData.ts` (54+8 agents, categories, search, `+Add`) | **RESKIN** | Current is richer (search + 8 categories, emoji icons, `estimated_duration`); mock is a flat, search-less list with initials. |
| Deliverable type "Custom" (`:63`) | `base_pipeline_type` (mig `0021`) | **RESKIN** | Field exists; mock control inert. |

## A8. [C] cross-reference table

| Region | Current home | Delta | Data gap |
|---|---|---|---|
| Composer canvas (whole) | AgentsPopup (modal) + WorkflowView (legacy) | RESTRUCTURE | Full-page composer + summary rail not built |
| Agent pipeline + reorder | AgentsPopup flow-graph / WorkflowView DnD | RESKIN | — |
| Per-agent model (inline) | AdvancedExpander lever / AgentModelPicker(unmounted) | RESTRUCTURE | Mount inline model input |
| Advanced Validator/Gate/Retry | AdvancedExpander | RESTRUCTURE | Add Validator→Gate coupling |
| Capability palette | CapabilityPaletteSection (live) | RESKIN | Use live registry not hardcoded |
| Skills/hooks | SkillsHooksTab | RESKIN | — |
| Est. duration/cost | none (composed) | BACKEND-NEEDED | pre-run estimate endpoint |
| Save workflow | /api/user-workflows | RESKIN | — |
| Visibility Just-me/Team | none | BACKEND-NEEDED + NEW-BUILD | sharing column + control |
| Add-agent palette | AgentLibrary | RESKIN | — |

---
---

# PART B — [W] WIZARD (`Hexaware Wizard.dc.html`)

## B1. Page / state inventory

A **3-step linear stepper** (Template → Design system → Discovery) that covers **both prototype (Web) and deck (Deck) deliverables via a `kind` toggle**, plus two detail modals. All steps are mounted in one page; step visibility is switched by `s.step`.

State (`[W]:156`):
| field | init | domain |
|---|---|---|
| `step` | `1` | `1|2|3` — current stepper position |
| `kind` | `'proto'` | `'proto'|'ppt'` — Web vs Deck template family |
| `selTpl` | `'editorial'` | selected **web** template id |
| `selPpt` | `'exec'` | selected **deck** template id |
| `selDs` | `'ink'` | selected design-system id |
| `detail` | `null` | `{type:'tpl'|'ds', id}` — which detail modal is open |
| `disc.audience` | `'enterprise'` | single-select |
| `disc.tone` | `'minimal'` | single-select |
| `disc.pages` | `{Home:true,Pricing:true,Docs:false,Dashboard:false}` | multi-select page map |

Step gating (`:241-242`): `next()` = `min(3, step+1)`; `back()` = `max(1, step-1)`. Step 1 back = "Cancel" link (→Workspace v2); steps 2-3 back = "Back" button. Step 3 primary = **"Start build"** link → `Hexaware Run - Live.dc.html`. **No validation** — all selections are pre-seeded, so Continue is always enabled. Detail-modal "Use template"/"Apply system" (`:247-248`) act as **step-advance shortcuts** (select + jump to step 2 / step 3).

## B2. Layout regions

1. **Header + stepper** (`:30-45`) — back-chevron (`:31`), eyebrow "Interactive prototype · Setup" + `<h1>{{ stepTitle }}</h1>` (`:32`), **centered 3-dot stepper** (`:35-41`), **Cancel** link (`:44`).
2. **Scroll body** (`:47-107`) — `max-width:1080px`; renders exactly one of Step 1 / Step 2 / Step 3 via `<sc-if>`.
3. **Footer nav bar** (`:110-116`) — foot-note (left) + Back/Cancel + Continue/Start-build (right).
4. **Template-detail modal** (`:119-132`) — `tplDetailOpen`.
5. **Design-system-detail modal** (`:135-150`) — `dsDetailOpen`.

## B3. Per-region element enumeration

### B3.1 Stepper (`:35-41`)
`<sc-for list="{{ steps }}">` → 3 items. Each: **dot** (`st.dotStyle` `:202`: current ⇒ indigo fill; done ⇒ lilac `#DED9F7` with "✓" mark; future ⇒ grey), **label** (Template / Design system / Discovery; dark when current-or-done), and a connector line between (`st.hasLine`, `:39`). `mark` = "✓" when done else the number.

### B3.2 Step 1 — Template (`:51-71`)
- Heading "Choose a template" + subtitle "Sets the visual DNA — chrome, layout and components. You can change it later." (`:53`).
- **Kind tabs** (`:54`) — segmented Web/Deck (`kindTabs` `:205`), `setKind` (`:191`); active tab raised white.
- **4-col card grid** (`:56-70`) of `<sc-for list="{{ tpls }}">`. Each card (`:58-67`):
  - **Thumbnail** (`thumbWrap` bg = template `bg`, `:214`) — one of three synthesized mockups: **blank** (plus icon, `:60`), **web** (browser chrome bar + hero + text lines using `accent`, `:61`), **slide** (dark slide with title/body bars, `:62`).
  - **Selected badge** (`:63`) — indigo circle-check when `t.selected`.
  - **Name + tag** (`:65`) — name + optional category tag pill (Blog/Dashboard/Marketing/…).
  - **"Details →"** (`:66`) — `t.onDetail` (stops propagation, opens template detail).
  - Card click (`:58`) = `selTemplate` (`:189`) — sets `selTpl` (proto) or `selPpt` (ppt).
- **"Upload custom"** dashed tile (`:69`) — **inert** (no handler).

### B3.3 Step 2 — Design system (`:74-87`)
- Heading "Pick a design system" + subtitle "Brand tokens — colour, typography and density…" (`:75`).
- **3-col card grid** (`:76-86`) of `<sc-for list="{{ dsCards }}">`. Each card (`:78-83`):
  - **Swatch band strip** (`:79`) — 3 color bands from `d.sw` (`bands` `:221`).
  - **Name + selDot** (`:80`) — name + selection dot (indigo-filled check when selected, `selDot` `:222`).
  - **Note** (`:81`) — one-line description.
  - **"Inspect tokens →"** (`:82`) — `d.onDetail` → DS detail modal.
  - Card click (`:78`) = `selectDs` (`:190`).
- **"Custom system"** dashed tile (`:85`) — **inert**.

### B3.4 Step 3 — Discovery (`:90-104`)
- Centered `max-width:720px`. Heading "A few details" + subtitle "These sharpen the brief before the agents start." (`:92`).
- **Question cards** — `<sc-for list="{{ discQ }}">` (`:93-98`), where `discQ` = `discAll` (`:226`) = **[audience, tone, pages]** = 3 cards. Each (`:94-97`): label + chip options (`q.opts`):
  - **audience** (`:182`): Consumers / Enterprise buyers / Internal team / Developers — single-select (`setAudience` `:194`).
  - **tone** (`:183`): Minimal / Bold / Playful / Corporate — single-select.
  - **pages** ("Which pages?" `:225`): Home/Pricing/Docs/Dashboard/About/Contact — **multi-select** (dark-fill when on, `togglePage` `:195`).
- **Freeform card** (`:99-102`) — "Anything else the agents should know?" over a styled `<div>` with placeholder "Brand voice, must-have pages, references, hard constraints…". **Not a `<textarea>`; inert.**

### B3.5 Footer nav (`:110-116`)
- **Foot-note** (`:111`) — `footNotes[step]` ("Step N of 3 · …").
- Step 1: **Cancel** link (`:112`, →Workspace v2). Steps 2-3: **Back** button (`:113`, `back`).
- Steps 1-2: **Continue** button (`:114`, `next`). Step 3: **Start build** link (`:115`, →Run - Live).

### B3.6 Template-detail modal (`:119-132`)
- Banner thumb (`dTplThumb`, gradient over template bg, `:231`). Name + tag (`:124`), description (`:125`). **"Includes"** chips (`dTplIncludes`, `:127`). Footer: **Close** (`closeDetail`) + **Use template** (`:129`, `useTpl` → select + step 2).

### B3.7 DS-detail modal (`:135-150`)
- Name + note (`:138`). **Palette** swatches with hex labels (`dDsSwatches`, `:141`). **Type scale** preview (`:143`) — **hardcoded** "Display 22 / Heading 15 / Body 12 — Heebo". **Components** chips (`dDsComponents`, `:145`). Footer: **Close** + **Apply system** (`:147`, `useDs` → select + step 3).

## B4. Data contract — [W] Wizard

**Wizard config (root)** — `kind:enum(proto|ppt)` · `selTpl:webTemplateId` · `selPpt:deckTemplateId` · `selDs:designSystemId` · `disc:{audience, tone, pages{}}` · freeform note (uncaptured).

**Web template** (`PTPL` `:158-167`, 8) — `id` · `name` · `tag:enum(Blog|Dashboard|Marketing|Docs|iOS|Dark|Gallery|'')` · `layout:enum(web|blank)` · `bg:hex` · `accent:hex` · `desc:string` · `includes:string[]`. Ids: editorial, dashboard, landing, docs, mobile, dark, portfolio, blank.

**Deck template** (`PPTPL` `:168-173`, 4) — same shape, `layout:'slide'`, `tag:enum(Board|Investor|Data|Clean)`. Ids: exec, pitch, report, minimal.

**Design system** (`DS` `:174-180`, 5) — `id` · `name` · `note` · `sw:hex[3]` (swatch bands) · `components:string[]`. Ids: ink (Ink & Alabaster), claude (Inspired by Claude), mono (Monochrome Pro), nocturne (Nocturne), terra (Terracotta).

**Discovery** — `audience:enum(consumers|enterprise|internal|developers)` (`DISC` `:182`) · `tone:enum(minimal|bold|playful|corporate)` (`:183`) · `pages:multiSelect(Home|Pricing|Docs|Dashboard|About|Contact)` (`PAGES` `:185`) · `freeform:string` (uncaptured).

**Stepper (derived)** — `step:1|2|3` · per-step `{done,cur}` · `stepTitle` · `footNote` · `notLastStep`/`lastStep`/`backIsStep`/`backIsExit`.

## B5. Design language — [W]

Identical token system to [C] (shared design language). Notable additions: template-thumbnail mockups render **synthesized chrome** using each template's `bg`+`accent`; DS cards render **3-band swatch strips** (`flex:1` each). Segmented control (`kindTabs`) and **numbered stepper dots** (22px) with a done/current/future tri-state are the two idioms unique to this file. Detail modals reuse the same 18px-radius sheet + `scrimIn`/`popIn` motion as [C].

## B6. Fiction register — [W]

1. **"Upload custom"** (`:69`) and **"Custom system"** (`:85`) dashed tiles — **inert** (no handler). (Current product *has* real custom flows — mock stubs them out.)
2. **Freeform "Anything else…"** (`:101`) — styled `<div>` with placeholder text; **not a textarea**, input not captured.
3. **DS-detail Type scale** (`:143`) — **hardcoded** "Display 22 / Heading 15 / Body 12" regardless of selected DS; not derived from tokens.
4. **"Start build"** (`:115`) — plain href to Run - Live; the collected config (kind/selTpl/selPpt/selDs/disc) is **never passed**. No submission.
5. **Template thumbnails** (`:60-62`) — synthesized CSS mockups, not real previews. (Current uses live iframes.)
6. **Template + DS data hardcoded** (`PTPL`/`PPTPL`/`DS`) — real product fetches backend registries.
7. **Discovery answers** stored in `disc` but flow nowhere.
8. `hint-placeholder-*` attributes throughout are design-time hints, not data.
9. Pre-seeded selections (`selTpl:'editorial'`, `selPpt:'exec'`, `selDs:'ink'`, disc defaults) — the wizard never presents an unselected/empty state.

## B7. Current-product mapping + delta — [W]

The wizard maps to the prototype/ppt template flow, which today is **route-split** (`/workflow/prototype/templates` vs `/workflow/ppt/templates`) with **no unified stepper** and **no Web/Deck toggle**. Phase 37 "Configure Unification" is exactly this consolidation; the mock is its concrete design.

| [W] element (line) | Current home (`file:line`) | Delta | Notes / gaps |
|---|---|---|---|
| 3-step stepper chrome (`:35-41`) | No unified stepper; flow is multi-route (`app/workflow/prototype/templates/page.tsx` → …); legacy `WorkflowView.tsx:47` has a *different* 4-state machine | **NEW-BUILD** | The numbered Template→DS→Discovery stepper doesn't exist as a component. |
| **Web/Deck kind toggle** (`:54`) | **Separate routes** — `prototype/templates/page.tsx` vs `ppt/templates/page.tsx` (`:10`) | **RESTRUCTURE** | Phase 37 promotes template/DS to **generic per-run config for every deliverable type**; the mock's single toggle is the target. Requires backend to accept template/DS beyond od_prototype/od_ppt (currently `IdeaInputPage` launches other pipelines with **no** template/DS). **BACKEND-NEEDED** for non-prototype deliverables. |
| Template card grid (`:56-70`) | `TemplateGallery.tsx:205-207` (grid, live iframe previews `:422-436`, Check badge); PPT twin `PPTTemplateGallery.tsx` | **RESKIN** | Current is a **superset**: live `GET /api/prototype/templates` (backend registry, ~43 templates), real iframe previews (mock uses CSS mockups), **content-category tabs** (All/Design/Marketing/… `:34`) the mock lacks, plus blank-canvas card (KAN-87 `:210-217`). |
| Template detail modal (`:119-132`) | `TemplateDetailModal.tsx` (opened `TemplateGallery.tsx:77-84`) | **RESKIN** | Exists; mock's includes-chips + desc map directly. |
| "Upload custom" tile (`:69`) | `CustomTemplateModal` + `loadCustomTemplates` localStorage (`TemplateGallery.tsx:45`) | **RESKIN** | Real flow exists; mock tile inert. |
| DS **band-card** grid (`:76-86`) | `DesignSystemPicker.tsx:388-420` — **chip list, no bands** | **RESTRUCTURE** | Current uses rounded pills; swatches live only in the detail modal. Mock's visual swatch-card grid is a genuine design change for Phase 37. |
| DS detail modal (`:135-150`) | `DesignSystemDetailModal.tsx` — split-panel: live iframe (`components.html`/token showcase) + `DESIGN.md` (`:54-61`) | **RESKIN** | Current is **richer** (live preview); mock's type-scale is hardcoded. |
| "Custom system" tile (`:85`) | `CustomDesignSystemModal` (paste `DESIGN.md`) + localStorage | **RESKIN** | Real flow exists; mock tile inert. |
| Discovery: audience/tone (`:182-183`) | `DiscoveryForm.tsx:49-52` audience/tone (+ surface, scale) | **RESTRUCTURE** | Overlaps but **enum values differ** (mock audience=consumers/enterprise/internal/developers vs current devs/ops/consumers/execs/mixed; tone sets differ). Current adds **surface**+**scale** the mock lacks. |
| Discovery: **pages** multi-select (`:225`) | **DOES NOT EXIST** — `DiscoveryAnswers` has no page field (`DiscoveryForm.tsx:20-29`) | **NEW-BUILD (+ BACKEND-NEEDED)** | Page-selection is absent end-to-end. |
| Discovery: freeform (`:99-102`) | `constraints` text field (`DiscoveryForm.tsx:120-125`) | **RESKIN** | Current is a real input; mock's is inert. |
| Whole discovery step | `DiscoveryForm.tsx` — **built but ORPHANED** (no code navigates to `/workflow/prototype/discovery`; live flow skips it) | **RESTRUCTURE** | Wiring discovery into the live flow is itself real work Phase 37 must do. |
| "Start build" (`:115`) | sessionStorage draft (`STORAGE_KEY="prototype.draft"`) + `run_pipeline` WS (`prototype/templates/page.tsx:294-339`) | **RESKIN** | Real launch exists; mock passes nothing. Draft payload superset: `templateId,designSystemId,brief,gateAgentIds?,modelOverrides?,selections?,customDsBody?,customTemplateBody?,images?,agentIds`. |

## B8. [W] cross-reference table

| Region | Current home | Delta | Data gap |
|---|---|---|---|
| 3-step stepper | none (route-split) | NEW-BUILD | unified stepper component |
| Web/Deck toggle | separate prototype/ppt routes | RESTRUCTURE | generic per-run config; backend accept template/DS for all deliverables |
| Template grid | TemplateGallery (+PPT) | RESKIN | use live API + iframe previews, add category tabs |
| Template detail | TemplateDetailModal | RESKIN | — |
| DS band cards | DesignSystemPicker (chips) | RESTRUCTURE | band-card vs chip decision |
| DS detail | DesignSystemDetailModal | RESKIN | — |
| Discovery audience/tone | DiscoveryForm | RESTRUCTURE | reconcile enum values |
| Discovery pages | none | NEW-BUILD + BACKEND-NEEDED | page-selection field |
| Discovery freeform | constraints field | RESKIN | — |
| Discovery step wiring | DiscoveryForm (orphaned) | RESTRUCTURE | wire into live flow |
| Start build | sessionStorage draft + WS launch | RESKIN | pass collected config |

---
---

# PART C — COMBINED DELIVERABLES

## C1. Combined cross-page inventory table

`page → current-product home → delta class → notable data gap`

| # | Mock surface | Current-product home (`file`) | Delta | Notable data gap |
|---|---|---|---|---|
| 1 | **[C]** Full-page composer canvas + sticky summary rail | `AgentsPopup.tsx` (modal) + `WorkflowView.tsx` (legacy) | **RESTRUCTURE** | No unified full-page composer surface |
| 2 | **[C]** Identity card (name/type/description) | `NameWorkflowModal` + mig `0021` cols | RESTRUCTURE | Up-front identity card absent (fields exist) |
| 3 | **[C]** Agent pipeline + reorder | `AgentsPopup.tsx:1864` / `WorkflowView.tsx:414` | RESKIN | — (arrows→drag) |
| 4 | **[C]** Per-agent inline model picker | `AdvancedExpander` lever / `AgentModelPicker.tsx` (unmounted) | RESTRUCTURE | Mount inline model input; use live catalog |
| 5 | **[C]** Advanced Validator/Gate/Retry | `AdvancedExpander` (`AgentsPopup.tsx:1493`) | RESTRUCTURE | Add Validator→Gate coupling; retry int not bool |
| 6 | **[C]** Custom prompt override | `AgentPromptSection` (`AgentsPopup.tsx:514`) | RESKIN | — |
| 7 | **[C]** Capability palette (8 hardcoded) | `CapabilityPaletteSection` (live `/api/capabilities`) | RESKIN | Use registry, drop hardcoded CAPDEF |
| 8 | **[C]** Skills & hooks | `SkillsHooksTab` (`data/skills.ts`,`hooks.ts`) | RESKIN | Global vs suggested-per-agent |
| 9 | **[C]** Summary Est. duration | legacy `WorkflowView.tsx:204` only | BACKEND-NEEDED | pre-run duration for composed wf |
| 10 | **[C]** Summary Est. cost | none pre-run (`TokenUsageSummary.tsx` post-run) | BACKEND-NEEDED | pre-run cost-estimate endpoint |
| 11 | **[C]** Declared-capabilities strip | `AgentsPopup.tsx:1099` (SURF-03) | RESKIN | — |
| 12 | **[C]** Save to catalogue | `/api/user-workflows` CRUD (`user_workflows.py:247`) | RESKIN | wire button to `createUserWorkflow` |
| 13 | **[C]** Visibility Just-me/Team | **none** | **BACKEND-NEEDED + NEW-BUILD** | sharing column + endpoint + control |
| 14 | **[C]** Save draft | none (for saved workflows) | NEW-BUILD | draft persistence |
| 15 | **[C]** Add-agent palette | `AgentLibrary.tsx` + `AgentLibraryData.ts` | RESKIN | add search/categories (already richer) |
| 16 | **[W]** 3-step stepper chrome | none (route-split) | **NEW-BUILD** | unified stepper component |
| 17 | **[W]** Web/Deck toggle | separate prototype/ppt routes | RESTRUCTURE | generic per-run config; backend for non-proto |
| 18 | **[W]** Template card grid | `TemplateGallery.tsx` / `PPTTemplateGallery.tsx` | RESKIN | live API + iframe previews + category tabs |
| 19 | **[W]** Template detail modal | `TemplateDetailModal.tsx` | RESKIN | — |
| 20 | **[W]** DS band-card grid | `DesignSystemPicker.tsx` (chips) | RESTRUCTURE | band-cards vs chip list |
| 21 | **[W]** DS detail modal | `DesignSystemDetailModal.tsx` | RESKIN | — |
| 22 | **[W]** Discovery audience/tone | `DiscoveryForm.tsx:49` | RESTRUCTURE | reconcile enum values; add surface/scale |
| 23 | **[W]** Discovery pages multi-select | **none** | **NEW-BUILD + BACKEND-NEEDED** | page-selection field |
| 24 | **[W]** Discovery freeform | `constraints` (`DiscoveryForm.tsx:120`) | RESKIN | — |
| 25 | **[W]** Discovery step wiring | `DiscoveryForm.tsx` (orphaned) | RESTRUCTURE | wire into live flow |
| 26 | **[W]** Start build launch | sessionStorage draft + `run_pipeline` WS | RESKIN | pass collected config |

**Delta tally:** RESKIN ×13 · RESTRUCTURE ×8 · NEW-BUILD ×3 (unified stepper, save-draft, discovery-pages) · BACKEND-NEEDED ×4 (pre-run duration, pre-run cost, workflow visibility/sharing, discovery-pages) — items 13 and 23 are dual-classed.

## C2. Combined data contract (both mocks → backend)

**Custom workflow** (`[C]`): `name`, `deliverable_type`(→`base_pipeline_type`), `description`, `strategy`(read-only), `agents:orderedList<agentId>`, `visibility`(⚠ **no backend**). Maps to `SaveUserWorkflowRequest` (`user_workflows.py:57-75`): `{name, description?, base_pipeline_type, agent_ids[≥1], model_overrides?{agentId:modelId}, selections?{agentId:{validators?,gates?,model?,retry?}}}`; response adds `id,created_at,updated_at`. **No `manifest` on the wire** (synthesized server-side, re-compiled `trust="user"`). **No visibility/sharing field anywhere.**

**Agent** (`[C].AG` ↔ `AgentLibraryData.ts AgentDef`): mock `{init, name, role, cat, locked}` vs current `{id, name, role, description, pipeline_type, order, icon(emoji), estimated_duration, has_skill, gate}`. Reconcile: mock `cat`→`pipeline_type`, mock `init`→derive from name (current uses emoji `icon` + initials fallback), mock lacks `estimated_duration`/`has_skill`.

**Per-agent selection** (`[C].modelFor`+`advFor` ↔ `selections`/`model_overrides`): `model`(→`model_overrides` **or** `selections.model`), `validator`(→`selections.validators`), `gate`(→`selections.gates`, **auto-coupled** to validator via `COUPLED_GATE`), `retry`(→`selections.retry` as `1|2|3`, not bool). Persisted via mig `0021` (`model_overrides` JSON col; `selections` in `manifest_json`).

**Model** (`[C].MODELS`): reconcile 3 hardcoded (Opus/Sonnet/Haiku 4.5) → live `model_catalog` (all tiers; validated at save+launch, `user_workflows.py:112-147`).

**Capability** (`[C].CAPDEF`): reconcile 8 hardcoded → live `GET /api/capabilities` entries `{kind, name, description, config_schema, security_gated, user_allowed}`. Mock `gated`→`security_gated`(Lock); mock `engineer`→`user_allowed=false`(Engineer-only, locked). Declared strip ← compiled per-step projection (`WorkflowDetail`, `api.ts:643-700`).

**Skill / Hook** (`[C].SKILLS/HOOKS` ↔ `data/skills.ts`,`data/hooks.ts`): mock global on/off maps; current adds `SKILL_CATEGORIES`/`HOOK_EVENTS` + `compatible_agents` (suggested-per-agent).

**Template** (`[W].PTPL/PPTPL` ↔ `GET /api/prototype/templates`): mock `{id,name,tag,layout,bg,accent,desc,includes,kind}` hardcoded (12 total) → backend registry (~43 prototype); current adds live iframe preview, content-category, `od.inputs` frontmatter (template-specific discovery inputs). **Wire to API, do not hardcode.**

**Design system** (`[W].DS` ↔ `GET /api/prototype/design-systems`): mock `{id,name,note,sw[3],components}` (5) → backend registry with `DESIGN.md` + `components.html`. Fetch full body via `/design-systems/{id}`.

**Discovery** (`[W].DISC/PAGES ↔ DiscoveryAnswers`): current `{template, surface, audience, tone, scale, constraints}`; mock `{audience, tone, pages, freeform}`. **Conflicts:** enum values differ for audience/tone; mock adds `pages`(no backend), lacks `surface`/`scale`. `freeform`→`constraints`.

**Run draft (current target for `[W]` "Start build")**: `{templateId, designSystemId, brief, gateAgentIds?, modelOverrides?, selections?, customDsBody?, customTemplateBody?, images?, agentIds}` → sessionStorage → `run_pipeline` WS.

## C3. Overlap / conflict with the already-built P20-22 composer surfaces

The two mocks **substantially re-propose surfaces P20-22 already shipped** — planners must treat most of this as reskin/restructure of existing code, not greenfield, and resolve these specific conflicts:

1. **Capability palette** — mock's 8 hardcoded `CAPDEF` **conflicts with** the built data-driven `CapabilityPaletteSection` (live `/api/capabilities`, generic kinds, `config_schema`, `security_gated`/`user_allowed`). Semantics align (gated≈security_gated, engineer≈user_allowed=false); **rebuild must use the live registry**, not the mock's list.
2. **Advanced levers** — mock's inline Validator/Gate/Retry chips **conflict with** the built `AdvancedExpander` (Validator·Gate·**Model**·Retry). Mock omits the **Validator→Gate coupling** the backend enforces (`selections.py`, `COUPLED_GATE`) and models Retry as bool vs `[1,2,3]`. Keep the built coupling.
3. **Per-agent model** — mock's inline row dropdown **validates the intent of the built-but-unmounted `AgentModelPicker.tsx`** ("PRIMARY model-selection surface"). The live path is currently the modal-buried `AdvancedExpander` Model lever; the mock argues for **mounting inline model selection**. `model_overrides` already round-trips (mig `0021`).
4. **Skills/hooks** — mock's global toggles **partially conflict with** built `SkillsHooksTab`, which has both global and **suggested-per-agent** (`compatible_agents`). Don't drop the per-agent suggestion model.
5. **Save + catalogue** — mock's save flow **overlaps** `/api/user-workflows` CRUD + `NameWorkflowModal` (already shipped). The **only genuinely new backend demand is workflow visibility/team-sharing** — absent from mig `0021` and the entire API (owner-scoped only).
6. **Layout paradigm conflict** — the built composer is a **tabbed modal** (`AgentsPopup`, Agents/Workflow tabs); the mock is a **full-page canvas with a sticky summary rail**. Phase 37 must pick one; the summary rail (with pre-run cost/duration) is the main net-new UI.
7. **Wizard route-split** — the built prototype/ppt flow is **two separate routes**; the mock's **Web/Deck toggle + unified stepper** is the concrete design for Phase 37's "generic per-run config for every deliverable type." This needs backend work to let non-prototype deliverables accept template/DS.
8. **DS presentation conflict** — built `DesignSystemPicker` is a **chip list**; mock is a **band-card grid**. Real design decision.

**Net-new work the mocks surface (beyond reskin):** (a) workflow **visibility/team-sharing** (backend col + endpoint + control); (b) **pre-run cost & duration estimates** for a composed workflow (no endpoint today); (c) **unified stepper + Web/Deck generic per-run config** (route consolidation + backend acceptance of template/DS for all deliverable types); (d) **discovery page-selection** (absent end-to-end); (e) **wiring the orphaned `DiscoveryForm`** into the live flow; (f) **mounting inline per-agent model selection** (`AgentModelPicker`).

---

**Teardown complete.** Both files were read to EOF; every enumerated element is anchored to `[C]`/`[W]` line numbers, and current-product homes are anchored to the frontend/backend paths confirmed by codebase reconnaissance. The single most important planning takeaway: **Phase 37's "wizard/composer alignment" soft-note understates the work** — ~13 surfaces are reskins of already-built P20-22 code, but there are **4 backend gaps** (visibility/sharing, pre-run cost, pre-run duration, discovery-pages) and **3 net-new UI builds** (unified stepper, save-draft, discovery page-selection), plus the strategic decision to promote template/DS to a **generic per-run config** for every deliverable type.
