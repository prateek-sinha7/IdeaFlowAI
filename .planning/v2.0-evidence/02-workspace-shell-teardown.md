# Workspace Shell Teardown (Hexaware Workspace v2.dc.html + sibling pages)

> **Evidence doc — Milestone v2.0** (see `README.md` in this directory and the POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`).
> Verbatim final report of a max-effort investigation agent, 2026-07-07. Feeds Phases 34-37 (shell convergence). Delta classes: RESKIN / RESTRUCTURE / NEW-BUILD / BACKEND-NEEDED.

---

I now have everything: the complete Workspace v2 file with all mock data and render logic, all five sibling files characterized, and the current-product surfaces confirmed by spot-checks. Here is the full teardown.

---

# WORKSPACE SHELL TEARDOWN — `Hexaware Workspace v2.dc.html`

**File:** `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Workspace v2.dc.html` (1236 lines, single `<x-dc>` + one `class Component extends DCLogic`). All data is mock (ALL-CAPS class fields); no `fetch`. Everything below is anchored to line numbers in that file unless noted otherwise.

The shell is a **single-file, state-switched SPA**. One `state.screen` field selects one of 8 top-level views; four overlays and one drawer float above. The run screens are treated only as `<a href>` navigation targets (`Hexaware Run - Live.dc.html`, `Hexaware Run.dc.html`, `Hexaware Run - Failed.dc.html`) — not re-torn-down here.

---

## 1. SHELL FRAME (persistent chrome)

### 1.1 View-switching engine
- **State object** (L896–904): `screen:'home'` is the root switch. Full domain of `screen`: `home | config | library | history | catalogue | analytics | settings | rundetail` (proven by `go()` calls + `openRunDetail`, L1010/1013 and the `is*` flags L1187).
- **Derived view flags** (L1187): `isHome / isConfig / isLibrary / isHistory / isCatalogue / isAnalytics / isSettings / isRunDetail` — each gates one `<sc-if>` block.
- **Navigation kernel** `go(s)` (L1010): sets `screen` and force-closes every overlay/drawer/menu. Helpers: `goHome/goLibrary/goHistory/goConfig/goCatalogue/goAnalytics/goSettings` (L1188). Run-detail uses a dedicated `openRunDetail(r)` that also stashes the clicked run in `detailRun` (L1013).
- **Frame layout** (L29): full-height flex column, `background:#F0EEE7` (warm cream), `font-family:'Heebo'`; a fixed top bar (58px) + a single scroll region (`flex:1;overflow-y:auto`, L88) holding whichever view is active.

### 1.2 Top bar (L32–86) — conditional
- Wrapped in `<sc-if value="{{ showGlobalBar }}">`. **Critical:** `showGlobalBar: s.screen!=='config'` (L1186) — **the global top bar is HIDDEN on the Configure screen**, which supplies its own header instead. Every other view keeps it.
- **Left:** `HEXAWARE` wordmark (italic Manrope 800 white) + 5px indigo dot; `onClick=goHome` (L34–37).
- **Center nav pill** (L38–42): exactly **three** buttons — Home (`goHome`), Library (`goLibrary`), Catalogue (`goCatalogue`) — each with an inline SVG and an active-state style from `navBtn(active)` (L1066: active = translucent-white fill + inset ring). Note: History / Analytics / Settings are **NOT** in the top nav — they are reached only via the profile menu.
- **Notifications** (L45–68): bell icon → `toggleNotif` (L1012, mutually exclusive with profile). Unread badge `{{ notifCount }}` shown when `notifUnread` (L48). Dropdown (L50–67): title "Notifications" + **inert** "Mark all read" (L54, no handler), a `<sc-for>` over `notifs`, and a footer "View workflow history" → `goHistory` (L65).
- **Profile menu** (L70–83): avatar "AK" → `toggleProfile`. Dropdown shows `ak@hexaware.com` / "Plan: Enterprise" (L74–75), then rows: **Account Settings** (`goSettings`), **Analytics** (`goAnalytics`), **Workflow History** (`goHistory`), **Admin console** (`<a href="Hexaware Admin.dc.html">`, L80), **Log out** (`<a href="Hexaware Login.dc.html">`, L81).

### 1.3 Shell-level floating surfaces (rendered after all views, L708–888)
| Surface | Trigger flag | Lines | Kind |
|---|---|---|---|
| Agent drawer | `drawerOpen` | 709–773 | Right slide-in (472px) |
| Workflow dialog (2-pane) | `modalWorkflow` (`overlay==='workflow'`) | 776–824 | Center modal 800×544 |
| Template picker | `overlayTemplate` | 827–855 | Center modal (720px) |
| Design-system picker | `overlayDs` | 858–873 | Center modal (640px) |
| Review-gates popover | `overlayGates` | 876–888 | Center modal (440px) |

`overlay` is single-valued (`null|template|ds|gates|workflow`, L1223); `drawer` holds the clicked agent object. `closeAll` (L1230) clears both. `stop(e)` stops propagation so clicking modal bodies doesn't dismiss.

**Design tokens (shell-wide):** accent indigo `#3C2CDA` (`ACC`, L1074), near-black `#111114/#15161A`, cream `#F0EEE7`, card off-white `#FCFBF7`, borders `#E6E3DB/#E0DDD3`, fonts **Manrope** (headings/labels/numbers) + **Heebo** (body). This exactly matches the stated target design system (Manrope/Heebo, black/cream, one-blue `#3C2CDA`) — i.e. the mock is authored *in the destination language*, so the shell's own styling is what the product should converge to, not a source to reskin away from.

---

## 2. PER-PAGE TEARDOWN

Legend for delta class: **RESKIN** (surface exists, structurally equivalent, restyle only) · **RESTRUCTURE** (surface exists but layout/composition differs materially) · **NEW-BUILD** (no current surface) · **BACKEND-NEEDED** (mock shows data no current API provides).

---

### 2.1 HOME (`isHome`, L91–163)

**(a) Purpose:** Landing / launch surface — a prompt-first "what would you like to build?" hero, a deliverable-type grid, and a "jump back in" recents strip.

**(b) Layout & elements:**
- Eyebrow "Hexaware" + H1 "What would you like to build?" (L93–94).
- **Prompt launcher card** (L97–105): a static grey placeholder line "Describe what you want to build — a prototype, a backlog, an app, a deck…" (L98, **not a real textarea**); footer with **Attach** + **Voice** affordances (inert spans, L100–101) and a **Build** button → `goConfig` (L103).
- **Deliverable grid** (3×2, L109–146): six cards, each `~Nagents · ~Nm`:
  - Product requirements (6 agents ~9m) → `goConfig`
  - Pitch an idea (4 agents ~6m) → `goConfig`
  - **Interactive prototype** (5 agents ~24m) → `<a href="Hexaware Wizard.dc.html">` (L122)
  - End-to-end application (15 agents ~48m) → `goConfig`
  - Platform workflows (26 agents ~2h) → `goConfig`
  - **Custom workflow** ("Compose freely →") → `<a href="Hexaware Composer.dc.html">` (L140)
- **Recents strip** "Jump back in" (L149–161): "All activity" → `goHistory`; a `<sc-for>` over `recent` (3 cards).

**(c) Data contract:**
- `RECENT` (L929–933): `{ title, type, ago, status }`. Rendered by `recent` map (L1080): adds `statusLabel`, `href` (running→Run-Live, else→Run), `dotStyle`, `statusStyle` from `STAT{}` (L1077). Deliverable card metadata (agent counts, durations) is **hardcoded inline in markup**, not a data array.

**(d) Interactions out:** Build & 4 cards → Configure; Interactive prototype → Wizard; Custom workflow → Composer; recents → run screens; "All activity" → History.

**(e) Mapping:** Deliverable grid ↔ **WorkflowCatalog** (`src/components/catalog/WorkflowCatalog.tsx` — data-driven from `GET /api/workflows`, mainView `home`/`catalog`). Prompt launcher ↔ **IdeaInputPage** (`src/components/workflow/IdeaInputPage.tsx`, mainView `input`). Recents strip ↔ portion of **WorkflowHistory** (no dedicated "recent 3" home widget today).

**(f) DELTA: RESTRUCTURE.** Product splits "prompt box" and "deliverable catalog" across two mainViews (`input` vs `home`); the mock fuses them on one Home. Card metadata `~24m / 5 agents` per deliverable = **BACKEND-NEEDED** if shown live (estimated-duration/agent-count per workflow type is not in the catalog contract). Recents "3-up on home" = **NEW-BUILD** (small).

---

### 2.2 CONFIGURE / run-setup (`isConfig`, L166–297) — the biggest structural gap

**(a) Purpose:** A single per-run setup screen: describe the build, then tune Templates, Design System, Review Gates, and Workflow Settings before launching. This is the mock's **unified "Configure your run"** surface.

**(b) Layout & elements:**
- **Own header bar** (L168–173, replaces the hidden global bar): back → `goHome`; eyebrow "New prototype · Quick start" + H1 "Configure your run"; **Save draft** (inert, L171); **Start run** → `<a href="Hexaware Run - Live.dc.html">` (L172).
- **Step 1 · Describe** (L180–193): numbered chip "1"; a card with **static** prompt text (a kanban-board brief, L185 — not editable), Attach/Voice (inert), "Press ⌘Enter to start" hint, and a submit arrow button (inert).
- **Advanced configuration** accordion group (L196–291), four rows:
  1. **Templates** (L199–234): collapsible (`toggleTpl`); shows `selTplName`; body is a 2-col grid of `templates2` cards with rendered skeleton thumbnails per `kind` (blank/editorial/dashboard/portfolio/docs/mobile, L212–218), a "Show all N / fewer" toggle (`toggleAllTpl`), and **Browse full library** → opens Template picker overlay (`openTemplate`, L230).
  2. **Design System** (L237–261): collapsible; shows `selDsName` + inline swatch trio (`dsSwInline`); body is a 2-col grid of `dsOpts` cards (swatches + radio-check), show-all toggle, **Browse all systems** → DS picker overlay (`openDs`).
  3. **Review Gates** (L264–283): collapsible; header "`{{gatesCount}}` agents configured to pause"; body lists `gateAgents` with real toggle switches (`ga.onToggle`), **Open gate manager** → gates overlay (`openGates`).
  4. **Workflow Settings** (L286–290): non-collapsing row → opens Workflow dialog (`openWorkflow`); subtitle `"{{agentCountLabel}} · 1 skill · 8 capabilities"`.

**(c) Data contract:**
- `TEMPLATES2` (L914–921): `{ id, kind, name, tag, desc }` ×6. `DS_OPTS` (L922–927): `{ id, name, note, sw:[3 hex] }` ×4 (Ink & Alabaster, Inspired by Claude, Monochrome Pro, Nocturne). `PIPE` (L906–912): 5 agents `{ init, name, role, short, out, dur, load }` — drives gate list & `gatesCount`. `gates{}` state = which agents pause.
- Render helpers: `collapse(open,max)` (L1060) + `chev(open)` (L1061) animate the accordions; `templates2`/`dsOpts` mappers apply top-N visibility (`TPL_TOP=4`, `DS_TOP=2`) and selection borders (L1148–1152).

**(d) Interactions out:** Start run → Run-Live; each accordion opens its overlay; Workflow Settings → Workflow dialog; back → Home.

**(e) Mapping:** No single product equivalent. In the product these are scattered: idea + capabilities + model overrides live in **IdeaInputPage** (with `ReviewGatesSection.tsx`, `AgentModelPicker.tsx`, `AgentsPopup.tsx` / `CapabilityPaletteSection`), while **Templates + Design System are prototype-only** and live in the separate wizard route `/workflow/{prototype}/templates` (`TemplateGallery.tsx`, `DesignSystemPicker.tsx`, `DiscoveryForm.tsx`). Review gates ↔ `ReviewGatesSection.tsx`.

**(f) DELTA: RESTRUCTURE (major).** The mock promotes template + design-system selection to a **generic, every-deliverable** per-run config, whereas the product hardwires them to the prototype pipeline. Making this generic is exactly the manifest-declared-capability direction (SC-001) but is a real structural build, not a reskin. "Save draft" for a run config = **BACKEND-NEEDED** (draft-run persistence). The suppression of the global bar on this screen is a shell-integration change.

---

### 2.3 LIBRARY (`isLibrary`, L300–358)

**(a) Purpose:** Browse the Agents / Skills / Hooks catalog; tap an agent to open its drawer.

**(b) Layout & elements:**
- Header: H1 "Library" + `libCountLine`; an **inert search box** (`libSearchPlaceholder`, L304).
- **Tab bar** `libTabs` (L307): Agents / Skills / Hooks with counts; underline-active style (`libTabBtn`, L1092).
- **Agents tab** (`isLibAgents`, L310–325): filter chips `libFilters` (L312, functional, hides zero-count groups); responsive card grid over `agents` (L315) — each card: avatar initials + name + category + role + desc + duration + "Configure →"; `onClick=openDrawer(a)`.
- **Skills tab** (`isLibSkills`, L327–340): category chips `skillCats` (All/Planning/Testing/…); card grid over `skillsLib` — name, category, desc, tag chips, "View →".
- **Hooks tab** (`isLibHooks`, L342–356): event chips `hookEvents`; card grid over `hooksLib` — name, event badge, italic trigger, desc, tags, "View →".

**(c) Data contract:**
- `AGENTS` (L936–951): **14 agents**, `{ init, name, cat, role, desc, dur }`. Grouping fn `AGROUP` (L1086) buckets them into userstories/prototype/appbuilder/platform/custom for the filter chips.
- `SKILLS_LIB` (L1035–1044): 8 × `{ name, cat, desc, tags[] }`.
- `HOOKS_LIB` (L1045–1054): 8 × `{ name, event, trigger, desc, tags[] }`; `evLabel` (L1097) prettifies event names.
- `libCountLine` (L1091): "14 agents · 8 skills · 8 hooks · tap any item to see its capabilities."
- Optional agent-avatar tinting behind a prop `showAgentTint` (L893, default false; tints array L1076).

**(d) Interactions out:** Agent card → agent drawer. Skills/Hooks "View →" are **inert** (no handler on those cards).

**(e) Mapping:** ↔ **LibraryPage** (`src/components/library/LibraryPage.tsx`) which already has Agents/Skills/Hooks tabs (confirmed L11–12, 303, 349–379).

**(f) DELTA: RESKIN → light RESTRUCTURE.** Tab model and card idiom match; restyle to shell tokens. The agent **drawer** launched from cards is a separate build (see 2.10). Search box is decorative (**mock-only**). Per-agent `dur` (e.g. "~95s") and per-hook `trigger` strings may be **BACKEND-NEEDED** if surfaced live.

---

### 2.4 CATALOGUE — saved custom workflows (`isCatalogue`, L434–470)

**(a) Purpose:** "Workflow Catalogue — your saved custom workflows — launch, manage and reuse them." (L440). **Terminology inversion to watch:** the mock's top-nav "Catalogue" = *saved/custom workflows*, which in the product is **SavedWorkflowsPage** (`saved-workflows`), NOT the product's `WorkflowCatalog` (that = the mock's Home deliverable grid).

**(b) Layout & elements:**
- Eyebrow "VelocityAI" + italic H1; right-side stat pair `savedCount` workflows / `savedAgents` total agents; **New workflow** → `<a href="Hexaware Composer.dc.html">` (L447).
- **Inert search** (L450).
- 3-col grid over `saved` (L452–467): each card = tinted avatar, kebab (inert), type badge, italic name, desc, optional italic brief, footer (agents count + updated), **Run workflow** → `<a href="Hexaware Run - Live.dc.html">` (L465).

**(c) Data contract:** `SAVED` (L1001–1008): 6 × `{ init, name, type, desc, brief, agents (string "N agents"), updated, tint }`. `savedAgents` = sum of `parseInt(agents)` (L1198).

**(d) Interactions out:** New workflow → Composer; Run workflow → Run-Live; kebab & search inert.

**(e) Mapping:** ↔ **SavedWorkflowsPage** (`src/components/savedworkflows/SavedWorkflowsPage.tsx`). "New workflow" ↔ Composer route (`/workflow`, WorkflowView/AgentLibrary legacy composer).

**(f) DELTA: RESKIN → RESTRUCTURE.** Card grid maps cleanly. The `type` taxonomy (Custom / "Mulesoft → Spring Boot" / ".NET → Azure" / User Stories / Presentation / App Builder) and per-workflow `brief` quote = likely **BACKEND-NEEDED** (saved-workflow metadata: origin brief, agent count, updated timestamp). Kebab actions unbuilt (**mock-only**).

---

### 2.5 WORKFLOW HISTORY (`isHistory`, L361–431)

**(a) Purpose:** Full run log, grouped/sorted/filtered, with revision families, per-row action menu, and empty states.

**(b) Layout & elements:**
- Header: italic H1 + `{{histCount}} runs`; **inert** "Search workflows…" (L365).
- **Filter chips** `histFilters` (L369, by deliverable type, zero-count hidden) + **Sort segmented** `sortTabs` (Newest / Longest / Tokens, L375).
- **Grouped list** (L380–422): `histGroups` renders group headers (Today / Earlier this week / Older) — but only when sort=newest; for longest/tokens it collapses to one flat "Longest first / Most tokens first" group (L1119–1121). Each row (L388–401): type-icon tile (5 `<sc-if>` variants — userstories/ppt/proto/app/custom, L390–394), title + sub, **version chip** (`vN` expandable via `onToggleVer`) when `hasVer`, tokens + ago, **status badge** (live dot pulses for running), kebab (`onToggleMenu`).
  - **Row menu** (L402–409): Open (`onOpen`→run detail), Re-run (`<a href=Run-Live>`), Revise (`goConfig`), Delete (`onDelete` = hides row via `histHidden`).
  - **Revision children** (L410–419): when `showChildren`, lists `r.children` (e.g. "v1 — Original — delivered") each `<a href="Hexaware Run.dc.html">`.
- **Empty states:** `histFilterEmpty` → "No runs match this filter" + "Show all runs" (L423); `histZero` → "No runs yet" + "Start a run"→goHome (L426).

**(c) Data contract:** `RUNS` (L970–980): 9 × `{ title, type, ago, dur, durSec, tok, tokNum, ver?, status, kind, group }` where `status ∈ done|running|cancelled|failed`. Derived `runList` (L1109–1117) computes badge, tile-kind flags, version-expand, menu-open, delete. `baseType()` (L1104) maps `type`→filter bucket. `STAT{}` (L1077) supplies status colors/labels. Children are **synthetic** (always a single hardcoded "v1 — Original", L1116).

**(d) Interactions out:** row/Open → run detail; Re-run → Run-Live; Revise → Configure; version children → Run; Start-a-run → Home.

**(e) Mapping:** ↔ **WorkflowHistory** + **RevisionFamilyView** (`src/components/history/`, confirmed with `.family` grouping tests). Row → run detail differs (see 2.6).

**(f) DELTA: RESTRUCTURE.** Grouping/sort/filter/revision-family concepts all exist in product. Sort-by-tokens/longest and Today/Earlier/Older bucketing may need adding. Delete is client-hide only in the mock; real delete = **BACKEND-NEEDED**. `tokNum/durSec` per run drive sort → product history needs those fields exposed.

---

### 2.6 RUN DETAIL / reopen (`isRunDetail`, L637–704) — genuinely new surface

**(a) Purpose:** A per-run summary page (distinct from the live run screen): header + status, degraded/reopen banners, KPI stats, agent breakdown, and a version timeline. Entered via `openRunDetail(r)` from History.

**(b) Layout & elements:**
- Back → `goHistory` (L639).
- **Header** (L641–653): status badge + optional version chip; title; meta; action cluster — Delete (inert), **Hand off** → `<a href="Hexaware Handoff.dc.html">` (L649), **Revise** → `goConfig`, and a primary open button whose label/href adapt to status (`dRunOpenLabel`/`dRunHref`, L1196: running→"Watch live run"/Run-Live, failed→"View failed run"/Run-Failed, else→"Open full run"/Run).
- **Conditional banners:** `dFailed` → red "Failed during {agent}" + "Reopen & fix" (inert, L656–662); `dCancelled` → amber "Cancelled by you" + "Run again"→goConfig (L663–669).
- **Stats row** ×4 (`dStats`, L672–676): Agents / Tokens / Duration / Est. cost.
- **Two-column:** agent breakdown (`dAgents`, per-agent status pill, L680–689) + **version timeline** (`dVersions`, dotted line, current chip, "New revision"→goConfig, L692–701).

**(c) Data contract:** Sources the clicked `detailRun` (fallback `RUNS[0]`, L1170). `dAgentStat(i)` (L1172) synthesizes per-agent state from run status; `ASTAT{}` (L1173) styles it. `DTOK` (L1175) fakes tokens/cost by status. `dVersions` (L1178–1183) is fabricated (v2/v1 if `ver`, else single). `dFailReason` is a fixed string (L1195).

**(d) Interactions out:** Hand off → Handoff; Revise/New revision/Run again → Configure; open → run screens; back → History.

**(e) Mapping:** **No current equivalent.** The product jumps History → the live `execution` run screen; there is no standalone post-run "summary/reopen" page with agent breakdown + version timeline.

**(f) DELTA: NEW-BUILD + BACKEND-NEEDED.** Requires a run-summary read model: per-agent status/duration/output artifact, per-run token/cost totals, failure reason + failed-agent, and a version/revision timeline. The "Reopen & fix / resume from failed step" affordance implies resumable-run backend semantics.

---

### 2.7 ANALYTICS (`isAnalytics`, L473–545)

**(a) Purpose:** Usage/cost dashboard — KPIs, daily activity, success donut, pipeline breakdown, recent runs, token split, model/spend.

**(b) Layout & elements:** back→goHome; date segmented `dateFilters` (Today/3d/7d/30d/90d/All — set `anaDate` only, **no data recompute**); **inert** "All pipelines" dropdown (L479). Then: 4 KPI tiles (`kpis`); Daily Activity bar chart (`dailyBars`, L496) + Success-Rate SVG donut (`donutDash`/`successPct`, L502) with completed/failed/total legend; By-Pipeline-Type bars (`pipelines`) + Recent Runs list (`anaRecent`); Token Breakdown split bar + in/out/total tiles (`tokIn/Out/Total`) + Model Details table (`modelRows`) with a spend chip (`anaSpend`).

**(c) Data contract:** `ANALYTICS{}` (L1024–1033): `kpis[{label,value,sub}]`, `days[14]`, `successPct/completed/failed/total`, `pipelines[{label,pct,meta}]`, `recent[{title,meta,tok,cost}]`, `tokInPct/tokIn/tokOut/tokTotal`, `model[[k,v]…]`, `spend`. Bars/donut computed in render (L1200–1201).

**(d) Interactions:** date chips set state only; everything else display-only.

**(e) Mapping:** ↔ **AnalyticsPage** (`src/components/analytics/AnalyticsPage.tsx`) — already has Token/Cost/Pipeline/Success content.

**(f) DELTA: RESKIN → RESTRUCTURE.** Same domain. Date filters are non-functional in the mock; real date-scoped aggregation = **BACKEND-NEEDED** (daily series, per-pipeline cost/token rollups, model rate table, monthly spend). Success donut + daily bars may be new chart components.

---

### 2.8 ACCOUNT SETTINGS (`isSettings`, L548–634)

**(a) Purpose:** Profile / AI Model / Usage & Limits / Constitution.

**(b) Layout & elements:** back→goHome; tab bar `setTabs` (L555).
- **Profile** (`stProfile`, L559–582): avatar + name/email/plan, "Change photo" (inert); Profile fields (Full name, Email read-only, Role, Organization) — all **static divs, not inputs**; Password block (static); "Save changes" (inert).
- **AI Model** (`stModel`, L585–596): radio cards over `modelOpts` (Opus/Sonnet/Haiku with rates, functional select via `setModel`), Opus tagged "Default".
- **Usage & Limits** (`stLimits`, L599–619): Enterprise-plan banner + "Manage plan" (inert); `usageBars` (Tokens/Concurrent runs/Saved workflows, L607); `entitlements` grid (6 deliverable types, L614).
- **Constitution** (`stConstitution`, L622–632): info banner; "Global instructions" card with **static** 312-char textarea content (L629) + char counter; Reset/Save (inert).

**(c) Data contract:** `setTabs` (L1161); `MODELS` (L1162) `{id,name,note,rate}`; `usageBars` (L1166) `{label,detail,pct}`; `entitlements` (L1167) string[]; profile/constitution values are literal markup.

**(e) Mapping:** ↔ **AccountSettings** (`src/components/settings/AccountSettings.tsx`) — confirmed to have constitution (L18/169), entitlements (L11), usage (L547). Strong match.

**(f) DELTA: RESKIN.** Tabs and sections align closely. The mock's static "inputs" must become real form controls; constitution save + usage metering + entitlement flags are backend-backed already per product. Mostly restyle. Any usage numbers (84.2M/250M etc.) need a usage API if not present.

---

### 2.9 AGENT DRAWER (`drawerOpen`, L708–773)

**(a) Purpose:** Inspect/configure one agent — Overview / Skills / Hooks / Config.
**(b)** Right slide-in; header (avatar/name/role/close); segmented tabs `agentTabs` (L719). Overview: duration/category/"Skill support" pills, "What it does", role-in-pipeline chip-chain, dark **System prompt** block (`agentPrompt` synthesized at L1226). Skills: `skills` list with Attach/Added toggle (`onAttach`, functional) + "Write a custom skill" (inert). Hooks: `HOOKS` list, "Attach" (inert). Config: `CFG_ROWS` (Model/Validator/Gate/Retry) each with an inert "Default ▾" control. Footer: Reset/Save → both `closeAll`.
**(c)** `openDrawer(a)` seeds drawer fields (L1062); `SKILLS` (L953–957) with `added{}` state; `HOOKS` (L958–961); `CFG_ROWS` (L962–967). `agentPrompt` is a template string, not stored data.
**(e/f)** Maps to composer components **AgentsPopup / AgentModelPicker / SkillManager / AgentLibrary** (`src/components/workflow/`). **DELTA: RESTRUCTURE.** The 4-tab agent inspector with an editable system prompt + per-agent Model/Validator/Gate/Retry overrides is more consolidated than today's popups; system-prompt editing per agent may be **BACKEND-NEEDED** (AGENT.md/prompt override persistence).

---

### 2.10 WORKFLOW DIALOG (`modalWorkflow`, L776–824)

**(a)** Advanced workflow config, 2-pane (left nav `wfNav` / right body). **(b)** Nav: Overview / Skills & Hooks / Capabilities / Context (`wfNav`, icons L1135). Overview: stat tiles "8 agents" + "Single-shot" + about text. Skills & Hooks: attached skill "Writing Plans" (removable), empty hooks state. Capabilities: `caps` list (8 agents, each `strat:'single_shot'`, L968) "Declared by this workflow". Context: **Compactions** (`html_skeleton`) + **Context packs** (`default`), both tagged "Engineer-only" (L810–815). **(c)** `CAPS` (L968), `wfNav` mapper (L1136). **(e/f)** ↔ **AgentsPopup / CapabilityPaletteSection + AdvancedExpander** in IdeaInputPage. **DELTA: RESTRUCTURE.** The Capabilities/Context/Compaction vocabulary maps directly to the engine's declared-capability model (this is the product's core value SC-001) — high-signal for engineering but currently only partially surfaced in UI. "Engineer-only" gating is a new concept for the FE.

---

### 2.11 Pickers (overlays)

- **Template picker** (`overlayTemplate`, L827–855): 4-col grid over `templates` (12 items, `TEMPLATES` L982–995 `{name,tag,kind}`), skeleton thumbnails by kind, selection at fixed index 2 (`i===2`, L1125). **Cards are inert** (`onClick:()=>{}`, L1127); "Use template" → `closeAll`. ↔ prototype `TemplateGallery.tsx`/`TemplateDetailModal.tsx`. **DELTA: RESKIN**, but item selection is unwired (**mock-only**).
- **Design-system picker** (`overlayDs`, L858–873): grouped chip cloud over `dsGroups` (`DS_GROUPS` L996–999: "AI & LLM" 15, "Automotive" 7, chips = "Inspired by X"), header claims "**150 systems**". Chips inert; "Apply system" → closeAll. ↔ prototype `DesignSystemPicker.tsx`. **DELTA: RESKIN**; "150 systems" catalog = **BACKEND-NEEDED** (mock lists ~14). Chips unwired (**mock-only**).
- **Review-gates popover** (`overlayGates`, L876–888): toggle list over `gateAgents` (functional), "Done" → closeAll. ↔ `ReviewGatesSection.tsx`. **DELTA: RESKIN**.

---

## 3. DESIGN-LANGUAGE NOTES (shell-specific, beyond run-screen tokens)

- **Dark top bar `#111114`** with a centered translucent nav-pill (`rgba(255,255,255,.05)` track, active pill `rgba(255,255,255,.11)` + inset ring, L1067) — a distinct "app chrome" idiom vs the cream body.
- **Card grid language:** `#FCFBF7` cards, `#E6E3DB` borders, 13–14px radius, hover = border→`#C9C6BC`; auto-fill grids `minmax(288px|360px,1fr)` for Library, fixed `repeat(3,1fr)` for Home/Catalogue.
- **List-row idiom (History/Run-detail):** left type-tile → title/sub → trailing metadata columns of fixed widths (44/76/90px) → kebab; hover row tint `#F6F4EE`.
- **Badges:** status pills carry a `{c,b,br}` triad (text/bg/border) from `STAT{}`; the **running** state adds a pulsing 6px dot (`@keyframes pulse`, L25/399). Version chips = indigo-on-`#ECEAFC`.
- **Filter/segment patterns:** pill filter chips (`filterChip`, active = solid `#15161A`, L1068); segmented controls on a `#EAE7DE` track (`segTab`, L1070); underline tabs (`libTabBtn`, L1092). Three distinct tab styles coexist.
- **Empty states:** centered icon + message + single CTA button (History has two variants: filtered-empty vs zero, L423/426).
- **Accordion motion:** `collapse()` max-height/opacity transition + chevron rotate (L1060–61). **Overlay motion:** `scrimIn`/`drawerIn`/`popIn` keyframes (L22–25).
- **Eyebrow labels:** uppercased Manrope 10–11px, wide letter-spacing (`.12–.26em`) — used as section kickers throughout.
- **Empty inline swatch stacks** (design-system trios): overlapping 13–18px circles with inset ring, negative left-margin (L1152).

---

## 4. CROSS-PAGE INVENTORY (planner table)

| Mock view (file:line) | Current-product home | Delta class | Notable data gaps (no known API) |
|---|---|---|---|
| Home hero + deliverable grid (L91) | WorkflowCatalog (`home`/`catalog`) + IdeaInputPage (`input`) | RESTRUCTURE | per-deliverable `~Nm`/`N agents` estimates |
| Configure/run-setup (L166) | IdeaInputPage + prototype template/DS wizard (split) | RESTRUCTURE (major) | generic template/DS per run; "Save draft" run persistence |
| Library — Agents/Skills/Hooks (L300) | LibraryPage (`library`) | RESKIN/light RESTRUCTURE | agent `dur`, hook `trigger` strings |
| Catalogue — saved workflows (L434) | SavedWorkflowsPage (`saved-workflows`) | RESKIN/RESTRUCTURE | workflow `type` taxonomy, origin `brief`, kebab actions |
| Workflow History (L361) | WorkflowHistory + RevisionFamilyView (`history`) | RESTRUCTURE | `tokNum`/`durSec` sort fields; real delete; token/ago per run |
| Run detail / reopen (L637) | — (jumps straight to `execution`) | **NEW-BUILD + BACKEND** | per-agent status/output, run token+cost totals, fail reason, version timeline, resume-from-failed |
| Analytics (L473) | AnalyticsPage (`analytics`) | RESKIN/RESTRUCTURE | date-scoped series, pipeline/model rollups, monthly spend |
| Account Settings (L548) | AccountSettings (`settings`) | RESKIN | make static fields real; usage metering numbers |
| Notifications panel (L50) | NotificationPanel (`ui/`) + AppHeader | RESKIN/RESTRUCTURE | notification kinds (gate/running/done/failed) feed |
| Agent drawer (L708) | AgentsPopup/AgentModelPicker/SkillManager | RESTRUCTURE | per-agent system-prompt + Model/Validator/Gate/Retry overrides |
| Workflow dialog — caps/context (L776) | AgentsPopup CapabilityPalette + AdvancedExpander | RESTRUCTURE | declared-capability + compaction/context-pack surfacing; "Engineer-only" gating |
| Template picker (L827) | prototype TemplateGallery | RESKIN | selection unwired in mock |
| Design-system picker (L858) | prototype DesignSystemPicker | RESKIN | "150 systems" catalog |
| Review-gates popover (L876) | ReviewGatesSection | RESKIN | — |
| Top bar / profile / nav (L32) | AppHeader | RESKIN/RESTRUCTURE | nav routes History/Analytics/Settings via profile menu |

---

## 5. GAPS / MOCKS — do not plan against fiction

- **All search boxes are inert display spans** — Library (L304), History (L365), Catalogue (L450). No input, no handler.
- **All "describe" text areas are static text**, not editable: Home launcher (L98), Configure Step-1 (L185), Account Settings profile/password/constitution fields (L568–578, L629).
- **Template picker cards are unwired** (`onClick:()=>{}`, L1127) and **DS picker chips are unwired** (plain spans, L867); both pickers only "close" — selection has no effect. Selection *does* work inside the inline Configure accordions (`selectTpl/selectDs`, L1056–57), just not in the modal pickers.
- **Analytics date filters** set `anaDate` but never recompute any chart (L1208) — the dashboard is a single static snapshot.
- **Inert buttons:** "Mark all read" (L54), "Save draft" (L171, Configure), Configure Step-1 submit arrow (L191), Home Attach/Voice (L100–101), Catalogue kebab (L457) & New-workflow-card kebabs, Run-detail Delete (L648) / "Reopen & fix" (L660), Account "Change photo"/"Manage plan"/"Save changes"/"Save constitution"/"Reset", drawer "Write a custom skill" / Hooks "Attach" / Config "Default ▾", Workflow-dialog "+ Add skill/hook".
- **Fabricated/synthetic data:** run-detail agent statuses (`dAgentStat`, L1172), tokens/cost (`DTOK`, L1175), and versions (`dVersions`, L1178) are all derived from run status, not stored. History revision children are a hardcoded single "v1 — Original" (L1116). `agentPrompt` is generated from name+role (L1226).
- **Overstated counts:** DS picker says "150 systems" but `DS_GROUPS` lists ~14 chips (L862 vs L996). Workflow dialog hardcodes "8 agents / Single-shot" while `PIPE` has 5 (L792 vs L906).
- **`showAgentTint` prop** (L893) is an editor toggle (default false) affecting only Library avatar tint — not a product feature.
- Delete in History is a **client-side hide** (`histHidden`, L1117), not a delete.

---

## SIBLING FILES (nav-completeness skim only)

- **`Hexaware Composer.dc.html`** (31.5KB) — the **Custom-workflow builder** reached from Home "Custom workflow" card (L140) and Catalogue "New workflow" (L447). Dark top bar with Home/Library/**Catalogue** links all routing back to Workspace v2 (L36–38); sub-header "Custom workflow · Composer" with Save draft / **Save workflow** (opens a save modal). Body is a 2-col grid (`1fr 320px`): main = workflow identity (name/type/description) + a draggable **Agent pipeline** builder; state (L209–218) holds `agents:['OR','MR','AR','CG','TI']`, per-agent `modelFor`/`advFor`, a `caps{}` capability toggle set (filesystem/web_search/context/compaction/exec/network/secrets/spawn), `skills{}`, `hooks{}`, `strategy:'sequential'`. Agent registry `AG{}` (L220–232) + `MODELS` (L233). Maps to the product's legacy `/workflow` composer (WorkflowView + AgentLibrary).
- **`Hexaware Wizard.dc.html`** (27.5KB) — the **Interactive-prototype setup wizard**, reached from Home "Interactive prototype" card (L122). Header with a 3-step stepper; Cancel → Workspace v2. `state` (L156) = `{ step, kind:'proto', selTpl, selPpt, selDs, disc{audience,tone,pages} }`; `stepTitles={1:'Choose a template',2:'Pick a design system',3:'Add a few details'}` (L199) with `isStep1/2/3` views. Maps to the product's `/workflow/{ppt,prototype}/templates` wizard route (TemplateGallery + DesignSystemPicker + DiscoveryForm).
- **`Hexaware Handoff.dc.html`** (22KB) — the **code-handoff / Draft-PR** surface, reached from Run-detail "Hand off" (L649). Dark top bar shows a GitHub repo (`hexaware/payments-service`); sub-header "Code handoff" with a running "compliance" pill and a **Draft PR #142** button. Body is a tabbed viewer (`state.tab`, L169; flags `isDiff/isTests/isCompliance`, L233) — **Diff** (changed-files sidebar + diff), **Tests**, **Compliance** (license/secret/dependency checks). Maps to the product's `/handoff/[token]` HandoffWorkflow suite. All nav out routes back to Workspace v2.
- **`Hexaware Admin.dc.html`** (16.5KB) — the **admin console / user management**, reached from the profile menu "Admin console" (L80). Dark top bar with an "Admin" tag + "Back to app" → Workspace v2; single page: "User management" header, **Invite user** button (opens add-user modal), a 4-KPI stat row, and (below) a user table. Maps to the product's `/admin` route.
- **`Hexaware Login.dc.html`** (5.8KB) — the **sign-in** screen (destination of "Log out", L81). Split layout: left dark brand panel ("VelocityAI — Agent workflows that ship real work", SSO/SCIM/audit tags), right form with static email/password fields, **Sign in** + **Continue with SSO** — both `<a href>` straight into Workspace v2 (invite-only messaging). Maps to the product's `/login` (and `/register`) route.

**One naming caution for planners:** in this mock, the top-nav **"Catalogue"** = *saved custom workflows* → product **SavedWorkflowsPage**; the Home **deliverable grid** = product **WorkflowCatalog**. The words "catalog/catalogue" are inverted between mock and product — don't wire them by name.
