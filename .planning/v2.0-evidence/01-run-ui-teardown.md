# Run-Screen Mock Teardown (Hexaware Run / Run-Live / Run-Failed / Design System .dc.html)

> **Evidence doc — Milestone v2.0** (see `README.md` in this directory and the POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`).
> Verbatim final report of a max-effort investigation agent, 2026-07-07. Feeds Phases 30-31 (chat lane + run redesign) and Phase 27 contracts.

---

I have now read all target files completely (Run, Live, Failed, Design System in full; Workspace v2 shell regions; image-slot.js and support.js mechanics). Here is the exhaustive teardown.

---

# VelocityAI "Hexaware Run" — Structural Teardown for React Rebuild

**Scope of evidence.** Fully read: `Hexaware Run.dc.html` (1066 ln, completed state — PRIMARY), `Hexaware Run - Live.dc.html` (1010 ln, streaming), `Hexaware Run - Failed.dc.html` (269 ln), `Hexaware Run - Design System.dc.html` (551 ln). Skimmed `Hexaware Workspace v2.dc.html` (shell/nav) and `image-slot.js`. All paths below are relative to `/Users/1000060523/Documents/Work/VelocityAI-New-UI/`. Citations use `Run:NNN`, `Live:NNN`, `Failed:NNN`, `DS:NNN`, `WS:NNN`.

## 0. DC FRAMEWORK MECHANICS (how to read the source)

Each page is one file: `<x-dc>` declarative markup + one `<script type="text/x-dc" data-dc-script>` containing `class Component extends DCLogic` (`Run:781–1064`). Rendering contract:
- **`renderVals()`** returns one flat object; every `{{ key }}` in markup binds to it (`Run:949–1062`). `style="{{ obj }}"` binds a JS style object; `onClick="{{ fn }}"` binds a handler.
- **`<sc-if value="{{ bool }}">`** = conditional; **`<sc-for list="{{ arr }}" as="x">`** = list. `hint-placeholder-count`/`hint-placeholder-val` are editor-only hints, not runtime.
- **`this.state`** + `setState` drive everything (`Run:786`). Data lives in ALL-CAPS class fields (`STEPS`, `ART`, `AUDIT`, `CLAR`, `CHAT`…). **All data is hardcoded mock** — there is no fetch, no API, no props beyond `data-props` (accent color, default tab; `Run:781–784`).
- **`style-hover="…"`** = declarative hover style (support.js runtime). Collapse/disclosure animation is a shared helper `collapse(open,max)` → `max-height`+`opacity` transition, and `chev(open)` → 180° rotate (`Run:946–947`).
- Navigation between run states is **plain `<a href="…dc.html">`** page loads (no SPA router). The four run screens are four separate documents.

---

## 1. PAGE / STATE INVENTORY

The "Run" experience is **4 documents = 4 lifecycle states of one screen**, plus the Workspace shell that launches/routes into them.

| State | File | Purpose | Entered from |
|---|---|---|---|
| **Completed** | `Hexaware Run.dc.html` | Settled, fully-navigable run trace + delivered artifact | history row / run-detail "Open full run" (`WS:1196`, status `done`) |
| **Live** | `Hexaware Run - Live.dc.html` | Streaming run with phase scrubber (Clarify/Gate/Building) | Config "Start run" (`WS:172`), "Watch live run" (`WS:1196`, status `running`) |
| **Failed** | `Hexaware Run - Failed.dc.html` | Halted-at-security-gate terminal state | "View failed run" (`WS:1196`, status `failed`) |
| **Design System** | `Hexaware Run - Design System.dc.html` | Token/component reference (not a product screen) | — |

**Run-status → page routing** (Workspace logic, `WS:1196`): `running→Live`, `failed→Failed`, everything else→`Run`. Recent-cards use `running→Live` else `Run` (`WS:1080`).

### Shared top-level layout (all 3 run states)
- **Root**: `height:100vh; flex column; overflow:hidden; background #F0EEE7` (`Run:25`).
- **Top bar** (`flex:none; height:58px; background #111114`, `Run:28–44`): HEXAWARE italic wordmark + 5px blue dot (`Run:30–31`); centered nav Home/Library/Catalogue (Home underlined blue, active) (`Run:33–37`); bell icon; 1px divider; 30px circular avatar "AK" (`Run:39–43`). Wordmark and nav are `<a href="Hexaware Workspace v2.dc.html">` (back to shell).
- **Body** = 2 columns (`Run:47`):
  - **LEFT — Chat window**: fixed `width:390px; background #F6F4EE; border-right #E6E3DB` (`Run:50`). Header block (back link, workflow-type eyebrow + status pill, run title, meta line), scrollable message list, sticky composer at bottom.
  - **RIGHT — Work panel**: `flex:1; background #F0EEE7` (`Run:142`). Sub-header (version selector + Share + Download), tab strip, scrollable tab body.

### Navigation model (how the user moves)
- **Left↔Right coupling**: chat cards deep-link into the right panel. `goSteps()`→`{tab:'steps'}`, `goPreview()`→`{tab:'preview'}` (`Run:1060`). E.g. the "6 clarifying questions" card and pipeline card both call `goSteps` (`Run:81,89`); the deliverable card calls `goPreview` (`Run:105`).
- **Right-panel tabs**: Preview / Steps / Files / Audit (`tabs`, `Run:953`). Live adds a pulsing "review" dot on Steps when paused (`Live:170,878`). Failed has only **Steps / Audit / Files** (`Failed:230`).
- **Steps drill-down (in-page, state-driven, no URL)**: 3 levels via `stepView` + `taskView` state (`Run:1014`):
  - L1 overview (`stepOverview = !stepView && !taskView`)
  - L2 agent detail (`stepDetail = stepView && !taskView`) — opened by `openStep(code)` (`Run:927`)
  - L3 task detail (`taskDetail = !!taskView`) — opened by `openTask(n)` (`Run:929`)
  - Back via breadcrumb `backStep()`/`backTask()` (`Run:928,930`).

---

## 2. STEPS TAB — DEEP DIVE (the core)

Container: `max-width:1200px` centered (`Run:292`). Three exclusive levels.

### 2A. LEVEL 1 — Overview (`Run:295–354`, inner col `max-width:760px`)

**(a) Status line + progress bar** (`Run:299–309`):
- Filled circle w/ check (`background #111114`) + "Run complete" (Manrope 600 15px) + right meta `"5 / 5 agents · 24m 6s"` (`Run:301–304`). Hardcoded strings here, but the count is conceptually `agentsDone/agentsTotal` + `totalDuration`.
- **Progress spine**: `progressSegs` = one flex segment per agent, all solid blue `#3C2CDA` when done (`Run:306–308,972`). In Live, each seg color depends on status: done/running→blue (running also pulses), idle→`#E0DDD3` (`Live:892–893`).

**(b) Clarifications block** — collapsible card (`Run:312–332`): header "Clarifications" + subtitle `"6 questions across 1 round · answered"`; chevron rotates; body lists `clarItems` (`Run:320`). Each item: optional `★ High impact` amber badge (`c.high`), question (Heebo 500), answer prefixed with a check icon (`Run:322–327`). Data: `CLAR[]` = `{q, a, high}` × 6 (`Run:858–865`).

**(c) Agent trace rows (thin spine)** — `sc-for traces` (`Run:335–352`). Each row (`onClick=tr.onOpen`):
- **State node** (18px): `isDone`→black filled check circle; `isRun`→blue ring w/ blue dot (Live pulses); `isIdle`→hollow grey ring (`Run:337–339`, `Live:261–263`).
- Agent **name** (Manrope 600 13px), spacer, **meta** (`"97s · 30.1k tok"` = `dur · tok`), chevron-right if `navigable` (`Run:340–343`).
- **Gate strip** (`tr.gateApproved`, `Run:345–351`): violet card "Review gate — {gate}" / "Paused for review · approved by you" / "Approved" badge. Rendered when a step carries a `gate` string.
- Live adds `tr.gateAwaiting` — an **interactive inline gate** (see §5).

Row visual states computed at `Run:984–998`: completed run forces `isDone:true, isRun:false, isIdle:false` for all (`Run:984`). Live computes from a per-phase status map `STBY` (`Live:881–883`) → row highlight, "LIVE"/"QUEUED"/"DONE" pill, node color, meta `"…tok · live"` / `"queued"` (`Live:911–929`).

### 2B. LEVEL 2 — Agent detail (`Run:357–581`)

Breadcrumb "Steps / {selName}" (`Run:358`). **Two-column CSS grid `1fr 288px`** (`Run:360`).

**LEFT column — the execution card** (`tr.cardStyle`, `Run:362`). Header (`Run:363–371`): rounded-square **node** showing 2-letter `code` (SW/TP/SK/BA/VA), eyebrow `"Phase {n}"`, title `"{name} — {title}"`, a `DONE` pill (`tr.pill`, `Run:985`), right meta `"{dur} · {tok} tok"`, chevron. Body (collapsible, `maxHeight 2600px`, `Run:373`) is a left-ruled timeline containing, in order:

1. **Reasoning block** (violet, `#F4F2FB`/`#E4E0F5`, `Run:378–387`): sparkle icon, uppercase label "Reasoning" (Live: "Reasoning (live)"), collapsible thought text `tr.thought` (`Run:385`). Live appends a **blinking cursor** when `isRun` (`Live:319`).
2. **Artifact block — one of four types** (discriminated by `ART[code].kind`, `Run:884–904`):
   - **`pages`** (`Run:390–403`): label + overview + 3-col grid of page thumbnails (skeleton chrome + page name). Data: `ART.SW.pages = ['Home','Product detail',…]` (`Run:885`).
   - **`tasks`** (`Run:406–420`): "Build tasks" + "{total} planned" + numbered task list. Data: `ART.TP.tasks[]` (`Run:886`).
   - **`checks`** (governance verdict, stays green, `Run:423–437`): label + green verdict pill (`artVerdict` e.g. "Coverage 100%" / "0 blockers") + green-check rows. Data: `ART.SK`/`ART.VA.rows[]` (`Run:887,903`).
   - **`construction`** (`Run:440–476`): "Construction · waves & subagents" + progress bar (`artDone/artTotal`) + **waves**. Each wave: "Wave {i}", `kind` (parallel/sequential), status badge (completed/running/pending). Each wave lists **navigable per-task rows** (`t.onOpen`→L3): state dot (done/running/pending), `"Task {n} · {title}"`, duration, chevron (`Run:459–471`). Data: `ART.BA.waves[]` with per-task `{n,title,status,dur,thinking,tools[]}` (`Run:888–902`).
3. **Tool calls** (collapsible card, `Run:479–504`): header "Tool calls" + count; each tool row (individually collapsible) = mono icon, `tool.name`, `tool.arg` (truncated), `tool.result` chip; expanded body shows `tool.detail` (`Run:489–501`). Data: `STEPS[].tools[] = {name,arg,result,detail}` (`Run:796–800` etc.).
4. **Full input prompt** (paper `#F0EEE7`, collapsible, `Run:507–518`): "Full input prompt" + `"{inputChars} chars"` + `pre-wrap` `inputText`.
5. **Agent output** (violet, collapsible, `Run:521–532`): "Agent output" + `outputChars` + `pre-wrap` `outputPreview` (for BA this is `"[HTML artifact … open in Preview]"`, `Run:831`).
6. **Summary** (`tr.showSummary`, `Run:535–540`): check icon + one-line `summary`.
7. **Gate strip** + **Handoff line** (`tr.handoffShow`, `Run:548–560`): down-arrow + `"Spec passed to Task Planner"` (`ART[].handoff`, `Run:885`).

**RIGHT column — "Context received" side card** (sticky, `Run:562–579`):
- Header: document icon + "Context received" (uppercase) + `"{ctxCount} sources fed in"` (`Run:564–568`).
- List of `tr.ctx` (`Run:570–575`): each = file icon + `cx.name` + `cx.meta`. Data: `STEPS[].ctx = [{name,meta}]` where meta shows size + **cache/reduction %** e.g. `'36.4k · -12%'`, `'151.6k · -70%'` (`Run:805,817,829,842`).
- Footer caption: *"The kernel assembled these into this agent's prompt before it ran."* (`Run:577`).

### 2C. LEVEL 3 — Task detail (`Run:585–609`, `max-width:860px`)

Breadcrumb "Build Agent / task detail" (`Run:587`). Single card built from the selected construction task (flattened from all waves, `Run:1011–1013`):
- State chip (done/running/pending, 30px) + `"Task {n} · {title}"` + `dur` (`Run:590–595`).
- **Reasoning** block (violet) = `t.thinking` (`Run:596`).
- **Tool calls** list = `t.tools[] {name,arg,result}` (`Run:597–605`).

### The 5-agent canonical pipeline (data: `STEPS[]`, `Run:788–851`)
| code | name | title/phase | dur | tok | artifact kind | gate |
|---|---|---|---|---|---|---|
| SW | Spec Writer | Specification (1) | 97s | 30.1k | pages (6) | "Specification approved" |
| TP | Task Planner | Build Decomposition (2) | 102s | 42.2k | tasks (7) | — |
| SK | Spec Kit Analyzer | Quality Analysis (3) | 25s | 31.0k | checks (100%) | — |
| BA | Build Agent | Incremental Construction (4) | 772s | 11022.4k | construction (3 waves/7 tasks) | "Build approved" |
| VA | Validation Agent | P0/P1 Checks (5) | 132s | 3658.5k | checks (0 blockers) | — |

Each `STEPS[]` entry carries: `code, name, dur, durSec, tok, phase, title, thought, thoughtTime, ctx[], inputChars, inputText, outputChars, outputPreview, gate?, tools[], summary, out` (agent-output filename), `outMeta` (`Run:789–801`). Waves data: `ART.BA.waves` = 3 waves, wave1/2 `parallel`, wave3 `sequential`; 7 tasks each with `thinking` + `tools` (`Run:888–902`).

### Step states enumerated
- **Agent step**: `done | running | idle(queued) | failed | skipped(not run)`. done/running/idle in Live via `STBY` (`Live:881`); failed/skipped only in Failed (`Failed:232` status→badge map `done/failed/skipped`).
- **Task (within construction)**: `done | running | pending` (`Run:462–464`; Live `Live:806–817`).
- **Wave**: `completed | running | pending | failed` via `waveKind()` regex (`Run:976`).
- **Gate**: `approved` (Run) | `awaiting` (Live) | `escalated/halt` (Failed audit `Failed:215`).

---

## 3. CHAT / CONVERSATION SURFACES

Chat is the **left 390px column**. It is a *linear transcript*, not a live back-and-forth input.

### 3A. Completed-run chat (`Run:66–138`, data `CHAT[]` `Run:874–880`)
`CHAT[] = [{role, text, clar?/pipeline?/deliver?}]`. Two bubble types + three inline result cards:
- **User bubble** (`m.isUser`, `Run:70`): `align-self:flex-end; background #ECEAFC; border #DED9F7; radius 14 14 4 14`.
- **Bot row** (`m.isBot`, `Run:72–77`): 22px black avatar tile (rotated blue square glyph) + grey body text.
- **Clarify card** (`m.showClar`, `Run:80–86`): "6 clarifying questions" + "In Steps →", `onClick=goSteps`.
- **Pipeline card** (`m.showPipeline`, `Run:88–102`): "Pipeline · 5 agents" + per-agent mini rows (check + name + dur from `pipeMini`, `Run:970`) + "Open Steps →".
- **Deliverable card** (`m.showDeliver`, `Run:104–112`): blue tile + `apple-reference-prototype.html` + "Delivered as v1 · open in preview →", `onClick=goPreview`.

### 3B. Composer (`Run:115–138`) — mostly decorative
- **Attachment chips** (`hasAttach`, `Run:116–131`): `attach[]` from `ATT[]` (`Run:867–872`): `brief.md 2.1KB`, `reference-screens.png 840KB` (isImg), `brand-guide.pdf 1.2MB`, `voice-note.m4a 0:48` (isAudio). Each chip has a working **remove** (`dropAtt`, `Run:931`). Icons switch on `isImg/isAudio/isFile`.
- **Input box** (`Run:132–137`): a **`<span>` placeholder** "Ask for a change or a follow-up…" (NOT a real `<input>`/`<textarea>`), + **Attach** button (paperclip), **Voice · transcribe** button (mic), **Send** button (blue). All buttons are non-functional stubs.

### 3C. Live chat states (`Live:83–128`) — phase-driven
Bot line is dynamic (`botLine=PHINFO[phase].bot`, `Live:87,977`). Composer placeholder is dynamic (`composerHint`, `Live:148,977`). Three status cards:
- **Clarify** (`isClarify`, `Live:91–97`): "Paused — 6 questions for you" + "Awaiting you" badge + "Answer in Steps →".
- **Gate** (`isGate`, `Live:100–107`): "6 clarifications answered" done-line + "Paused — task plan needs approval" + "Review in Steps →".
- **Building** (`isBuilding`, `Live:110–128`): done-line + live pipeline mini (per-agent dot states + `done✓/live/queued` meta, `Live:884–890`) + "Open Steps for the full live trace →".

### 3D. Failed chat (`Failed:59–80`)
User brief bubble → bot explanation → **"What went wrong"** red card (3 bullets: secret-scan block, exec denied, 1 critical structural error; `Failed:66–73`) → **"Resume options"** (Reopen & fix from failed step [red] / Edit brief & run again; `Failed:75–79`). Composer placeholder "Tell the agents what to change, then reopen…" (`Failed:84`).

### 3E. Chat features the prototype does NOT show (gaps for the data contract)
- **No real text entry** anywhere — every "input" is a styled `<span>` placeholder. No message-send flow, no optimistic bubbles, no streaming assistant text *in the chat* (streaming happens in Steps/Preview only).
- **Interactive clarify Q&A does NOT live in chat** — it lives in the **Steps** panel (`Live:222–231`; see §5). Chat only shows a "Paused — answer in Steps" pointer.
- **Gate approval does NOT live in chat** — Approve/Request-changes buttons are in Steps (`Live:275`).
- **Image upload**: only via the decorative attachment chip row (pre-populated mock); the live Preview has an `image-slot` drop target for a *build screenshot* (`Live:193`), but that is a design-tool affordance (image-slot.js), not a product chat upload.
- **No mid-run free-text steering UI is wired** — the "steer the run" hint text exists (`Live:979`) but the box is inert.
- No @mentions, no threading, no reactions, no per-message timestamps in the transcript.

---

## 4. OTHER TABS

### 4A. Preview (`Run:184–288`)
Browser-chrome frame (`#fff` card, `Run:186`): traffic-light dots, centered URL bar (lock icon + `pvFile` + version pill), 100% + expand icon (`Run:187–199`). Below: **"Renders as" typed-renderer switch** (`pvTabs`, `Run:202–205,1042–1045`) — a segmented control with 5 options mapping `pv` state → filename (`PVFILE`, `Run:1043`):

| pv | label | file | render body |
|---|---|---|---|
| `proto` | Prototype | apple-reference-prototype.html | rendered "northwind" Apple-style site (nav, hero "Titanium…", 3 feature cards) (`Run:209–219`) |
| `stories` | User Stories | growth-squad-backlog.md | Epic EP-04 + US cards w/ point badges + Gherkin Given/When/Then blocks (`Run:222–238`) |
| `deck` | Deck | market-opportunity.pptx | dark 16:9 slide "Market opportunity" + bar chart + thumbnail strip (`Run:241–256`) |
| `app` | App code | payments-service/ | dark IDE: file tree + tabs + syntax-highlighted NestJS controller (`Run:259–270`) |
| `doc` | Doc | README.md | rendered markdown "Payments Service" (h1/h2, code block, endpoint list, blockquote) (`Run:273–283`) |

Each render is fully static hand-built HTML (design-only). **Live Preview** replaces this with a streaming shell: animated top progress bar (`bar` keyframe) + an `image-slot` "Drop a screenshot of the in-progress build" placeholder (`Live:190–195`), URL bar "building apple-reference-prototype.html…".

### 4B. Files (`Run:614–671`)
- **Deliverable hero** — dark card `#0C0D12` with radial blue glow (`Run:624–638`): "Final output" eyebrow, `apple-reference-prototype.html`, `"HTML (.html) · 151.6 KB · validated"`, **Preview** (`goPreview`) + **Download** buttons.
- **Agent outputs (5)** — vertical timeline spine (`Run:640–656`): `pipeFiles` = per-agent `{code, name=out, meta=outMeta}` (`Run:1018`), e.g. `01-spec-writer-agent.md · Specification & Architecture · 36.4 KB`. Each row: 38px code node + name + meta + download button.
- **Run input** (`Run:658–669`): `inputs` = `INPUTS[]` (`Run:882`) = `prompt.md (57 B)`, `clarifications.md (1.9 KB)`.
- **Live Files** (`Live:558–610`): deliverable hero shows spinner + "task 4 of 7 · not yet validated"; agent outputs list only the **done** agents (`doneSteps`, `Live:948–951`); header "3 files ready · deliverable building".
- **Failed Files** (`Failed:173–184`): amber "Build incomplete" banner + only 3 planning artifacts (`FILES[]`, `Failed:203–207`), each with inert "Download".

### 4C. Audit (governance, the status-palette exception; `Run:674–774`)
- **Header** (`Run:677–699`): shield icon + "Audit trail" + `"{auditCount} records"` pill + **Export** dropdown (`exportOpts`: CSV / JSON raw hook_runs / Compliance PDF; `Run:1040`). Live adds a pulsing "live" pill (`Live:623`).
- **Attribution + compliance summary** (`Run:702–725`): run id `f3a1c9…e42`, owner `ak@hexaware.com`, workspace `default`, started, duration (`Run:704–708`). **6 stat counters** (`Run:710–717`): Checks / Passed(green) / Warnings(amber) / Blocked(red) / Denied(red) / Secret scans(blue), computed at `Run:1038`. **Coverage chips** (`Run:718–720`, `coverage[]` `Run:1039`): Activity, Security, Gates, Validation, Exec policy, Governance, Performance. **Verdict banner** green "0 blocked · 0 denied · 0 critical — run passed all governance gates" (`Run:721–724`) — Live shows this in **blue** ("monitoring live", `Live:662–664`).
- **Filters** (`Run:728–735`): chips All/Governance/Security/Activity with counts (`auditFilters`, `Run:1036`); **Blocked/denied only** toggle (`Run:733`); Search box (decorative).
- **Log entries** — `auditLog` (`Run:738–766`): each collapsible row = outcome icon (pass/warn/block, colored circle, `OUT` map `Run:1020–1022`), title, meta `"{agent} · {target} · Jul 4 · {time}"`, category pill, optional **severity** pill (`SEV` low/medium/high/critical, `Run:1024`), outcome badge. Expanded body: **"What is this?"** violet explainer + key/value `rows`.
- **Integrity footer** (`Run:769–772`): "Immutable, owner- and workspace-attributed log · … exportable to CSV / JSON".

**Audit data model** (`AUDIT[]`, `Run:906–923`): `{cat, title, agent, target, out, sev, time, whatIs, rows[[k,v]…]}`. **Categories** (`CAT`, `Run:1023`) → group: `behavioral/gate/validation→gov`, `security/exec→sec`, `activity/performance→act`. Completed run has 15 records, all `pass`. **Failed** (`Failed:208–219`) demonstrates the block path: BLOCKED secret write to `.env` (critical, auto-expanded `auditOpen:{secret:true}` `Failed:194`), DENIED exec (high), CRITICAL validation, WAIT_HUMAN→halt.

---

## 5. LIVE-RUN SPECIFICS (`Hexaware Run - Live.dc.html`)

**Phase state machine**: `state.phase ∈ {clarify, gate, building}` (`Live:726`), default `gate`. This is the single control that drives every live affordance.

**Phase scrubber** — the signature live control. A 3-segment control **in the left panel header** labeled "◷ Preview / Prototype control" (`Live:76–80`, `phaseTabs` `Live:976`): Clarify | Gate | Building. Caption: *"Prototype control — scrub the run to a moment; the Steps panel updates."* This is a **prototype demo device** (lets a reviewer jump the mock between phases), not a real product control — flag as mock.

**Per-phase derived data** (all hardcoded lookups):
- `STBY` — agent status map per phase (`Live:881`): clarify=all idle; gate=SW/TP done, rest idle; building=SW/TP/SK done, BA running, VA idle.
- `PHINFO` (`Live:977–979`): bot line, composer hint, elapsed, agents-count, tokens per phase (e.g. building = "12m elapsed / 3 / 5 agents / 8.4M tokens").
- `PHH` (`Live:981`): Steps-overview head label/pill/meta (e.g. "Pipeline running · 3 / 5 agents", pill "BUILDING").

**Streaming affordances / what animates** (CSS keyframes `Live:22–27`):
- **`pulse`** — live dots (top-bar "3/5" pill `Live:47`; running agent node/dot `Live:262,397`; head dot `Live:984`; progress seg `Live:893`; audit "live" pill).
- **`spin`** (`.spin`) — "Build Agent · streaming" spinner in right header (`Live:160`) and Files deliverable spinner (`Live:571`).
- **`bar`** — indeterminate progress bar sweeping across Preview (`Live:191`) and Files hero (`Live:569`).
- **`blink`** — typing cursor at end of live reasoning text (`Live:319`).
- **`ping`** — defined but I did not find it used (candidate dead style).

**What updates in real time (conceptually)**: right-header status pill ("building task 4 of 7 — compare page", `Live:160`); Steps overview head + progress; the running agent's row (violet highlight, "LIVE" pill, `"…tok · live"`); its reasoning (live text + cursor); the construction waves (wave 2 running, task 4 "Compare page" running w/ `result:'live'`, task 5 pending; `Live:804–818`); Files deliverable ("not yet validated"); Audit ("Elapsed 12m 04s · in progress", accruing records).

**Interactive gates/clarify (live only)** — these are the real interaction surfaces:
- **Clarify Q&A in Steps** (`clarAwaiting`, `Live:222–231`): `qnItems` from `QN[]` (3 questions, `Live:730–734`), each with **selectable option buttons** (`selectQ(qi,oi)`, state `qnSel`, `Live:989`) + **"Submit answers & start the build"**. Once past clarify → collapses to read-only `clarSettled` record (`Live:234–254`).
- **Gate approval in Steps** (`tr.gateAwaiting`, `Live:269–278` and `482–491`): inline card w/ 7-task plan preview + **Approve & build** / **Request changes** buttons (inert). Tabs show a pulsing review dot when `paused` (`Live:170,878`).
- **Share button is disabled** during live (`cursor:not-allowed`, `Live:165`); version pill reads "v1 draft".

---

## 6. DESIGN LANGUAGE (tokens + idioms)

Authoritative source: `Hexaware Run - Design System.dc.html` + the `COLORS[]` array (`DS:477–516`).

**Typography** (`DS:120–183`): two families — **Manrope** (structure: titles/labels/tabs/numbers; weights 300–800; Light for headings) + **Heebo** (reading: body/meta; 300–600). Numbers use **tabular figures** (`.tnum`, `DS:21`). Documented type roles (`DS:150–181`): Display Manrope 300 34/44; Request 21px; Section title 600 14.5; Eyebrow 600 10.5 letter-spacing .13em uppercase; Tab/nav 500 14; Body Heebo 400 13.5/1.55; Meta Heebo 400 12; Stat Manrope 700 tabular.

**One-chroma rule** (Principle 01, `DS:70–74`): a single blue leads *only where meaning demands* (active tab, deliverable, the peak); everything else is ink on paper. Icons are monochrome Feather-style line (1.6–1.8 stroke, round caps), single ink color — **blue only when the icon itself is the action** (the Reasoning sparkle is the one blue icon; `DS:185–190,235–236`).

**Color tokens** (`DS:477–516`):
- **Brand**: `#3C2CDA` (Hexaware Blue / primary accent), `#3324C4` (pressed/hover), `#ECEAFC` (Blue 50 — user bubbles/tint fill), `#DED9F7` (Blue 100 — tint border), `#F4F2FB` (Violet 25 — thinking/reasoning block), `#8E88E8` (blue-on-dark).
- **Ink** (warm near-black→grey, all text): `#15161A`, `#20222B`, `#3A3B42`, `#5B5C63`, `#8A8B82`, `#9A9B92`, `#A0A199`.
- **Surface**: `#F0EEE7` (Paper/app bg), `#F6F4EE` (Paper Warm/left panel), `#FCFBF7` (Card), `#FFFFFF` (inputs/menus), `#111114` (Near Black/top bar+nodes), `#0C0D12` (Ink Black/deliverable hero).
- **Line/hairlines**: `#E6E3DB` (border), `#E2DFD6` (divider), `#E0DDD3` (control), `#C6C3B9` (faint dots/ticks).
- **Sequence ramp** (time bar only, monochrome + accent peak, `DS:509–515`): `#B9B6AC → #9A978D → #7C7A70 → #3C2CDA (peak=Build Agent) → #55535C`.

**Status palette exception** (Audit/governance keeps semantic RGB, `Run:1020–1024`, `Failed:239–243`): **green** `#1F7A4D / #E7F0EA / #CFE3D6` (pass), **amber** `#9A6B1E / #F5EEDD / #E8DBC0` (warn/medium), **red** `#A33A32 / #F5E5E2 / #E8CDC8` (block/critical), plus **high** `#B4531E / #F5E9DD / #E8D3C0`. These are the *only* place non-blue chroma is allowed.

**Radius scale** (`DS:255–263`): 5 tags · 8 nodes · 10 buttons · 12 cards · 14 panels · 999 pills.
**Elevation** (`DS:265–271`): raised `0 1px 2px rgba(17,17,20,.08)`, floating `0 8px 30px /.10`, menu `0 12px 32px /.12`.
**Motion** (`DS:276–314`): disclosure = `max-height .4s cubic-bezier(.4,0,.2,1)` + `opacity .3s`; chevron rotate 180° `.3s`; hover `.15s`; focus ring = soft blue halo `box-shadow: 0 0 0 4px rgba(60,44,218,.15)`. "Nothing bounces."

**Component idioms** (live examples `DS:317–465`): primary/secondary/icon **buttons**; pill **chips**; segmented control; underline **tabs** (`border-bottom:2px solid #3C2CDA` active); version selector dropdown; chat bubbles; tool-call row; artifact/file row; **timeline nodes** (default black square, active blue w/ halo, done black circle+check); stat blocks; horizontal **time-distribution bar** (flex-grow proportional to `durSec`, peak in blue); dark deliverable hero. Scrollbar is custom warm (`Run:18–20`); selection color `#DAD6F7`.

---

## 7. CONSOLIDATED DATA CONTRACT (map to real APIs)

Every distinct backend field the Run screens consume (from the mock class fields). Grouped by entity.

**Run (top-level)**: `id` ("f3a1c9…e42", `Run:704`), `title`, `workflowType` ("Prototype"/"App Builder"/"User Stories", `Run:56`,`Failed:49`), `status` (running|done|failed|cancelled, `WS:970–979`), `owner` (`ak@hexaware.com`), `workspace` ("default"), `startedAt`, `duration`/`elapsed`, `agentsDone`/`agentsTotal` (5/5), `tokensTotal` ("14.8M") + `tokensInput`/`tokensOutput` split (`Live:986`), `version` (v1/v2) + `versions[]` (`Run:958–961`).

**Chat message**: `role` (user|bot), `text`, flags `clar|pipeline|deliver` (or, generally, an attached "result card" type + payload) (`Run:874–880`).

**Attachment**: `name, size, kind` (image|audio|file) (`Run:867–872`).

**Clarification**: `question, answer, highImpact:bool`, round number, answered:bool (`Run:858–865`). Live pre-answer form: `question, options[]`, `selected` (`Live:730–734`).

**Agent step**: `code, name, phase, title, status` (done|running|idle|failed|skipped), `duration`+`durSec`, `tokens`, `thought`(+`thoughtTime`/live), `contextSources[]{name, meta(size + cache/reduction %)}`, `inputChars`+`inputText` (full prompt), `outputChars`+`outputPreview`, `toolCalls[]`, `summary`, `gate?`(label+state), `handoff?`, `outputFile{name, meta}` (`Run:788–851`).

**Tool call**: `name, arg, result, detail` (`Run:796–800`).

**Artifact (per step)**: `kind` (pages|tasks|checks|construction), `label`, and kind-specific payload: `pages[]` | `tasks[]{title,status}`+done/total | `verdict`+`rows[]` | `waves[]` (`Run:884–904`).

**Wave**: `i, kind` (parallel|sequential), `status` (completed|running|pending|failed), `tasks[]` (`Run:888–902`).

**Task (subagent)**: `n, title, status` (done|running|pending), `dur, thinking, tools[]` (`Run:890–901`). (Worker/subagent names also modeled: `WAVES[].workers[]{agent,status}`, `Run:853–856`.)

**Deliverable / file**: `name, type, size, validated:bool, versionTag`; agent-output files `{code, name, meta}`; run inputs `{name, meta}` (`Run:630–631,1018,882`).

**Audit record**: `cat` (behavioral|gate|security|exec|validation|activity|performance), `title, agent, target, outcome` (pass|warn|block), `severity` (''|low|medium|high|critical), `time`, `whatIs` (explainer), `rows[[key,value]…]`. Plus derived summary counters: checks/passed/warnings/blocked/denied/secretScans, coverage domains, export formats (`Run:906–923,1038–1040`).

**Preview renderer**: `previewType` (proto|stories|deck|app|doc) → `{filename}` + a typed render payload per type (`Run:1042–1043`).

**Live/phase**: `phase` (clarify|gate|building) driving: per-agent status map, botLine, composerHint, head label/pill, elapsed/agents/tokens, gate-awaiting vs approved, streaming flags (`Live:726,881,976–989`).

**Failure info** (Failed): `failedAgent`, `failReason`, per-agent terminal status (done|failed|skipped), block reasons (secret write, exec denied, critical validation), resume actions (reopen-from-step | edit-brief-rerun) (`Failed:196–219,656–668`).

---

## 8. GAPS / MOCKS (design-only, not wired)

1. **All data is hardcoded** in class fields — no fetch/API/websocket. "Streaming" is CSS animation over static strings; live token counts, timers, and "building task 4 of 7" are fixed literals (`Live:160,977–986`).
2. **No real inputs** — every composer/search "field" is a styled `<span>` placeholder, not `<input>`/`<textarea>` (`Run:133,734`; `Failed:84`; `WS:98,185,365`). Send/attach/voice buttons are inert stubs.
3. **Phase scrubber** (Clarify/Gate/Building segmented control) is a prototype demo device to jump the mock between states, not a product control (`Live:76–80`).
4. **Gate & clarify actions inert** — "Approve & build", "Request changes", "Submit answers & start the build", option-select all set local state or do nothing; no submission (`Live:229,275`). Clarify selection (`qnSel`) is the only stateful one.
5. **Preview renders are hand-built static HTML** (northwind site, Gherkin doc, dark deck, IDE, markdown) — not real generated artifacts; the URL bar/zoom/expand are decorative (`Run:209–283`).
6. **Downloads / Export / Share** are non-functional (`Run:170,621,635,687`; export menu just lists formats). Share is explicitly disabled in Live (`Live:165`).
7. **`image-slot`** in Live Preview is a design-tool drop target (persists to a sidecar JSON via the omelette runtime per `image-slot.js` header), not a product upload — read-only outside that runtime.
8. **Version selector** toggles a local `version` flag but v2 content is identical (`Run:958–963`).
9. **Audit search box, "100%" zoom, notification actions** are decorative. `ping` keyframe appears defined-but-unused (`Live:24`).
10. **Cross-page nav is full page loads** (`<a href>`), so run state is not preserved across Live→Run transitions — each file is an isolated mock (`WS:1196` picks the file by status).
11. **Cache/reduction percentages** on context sources (`-12%`, `-70%`) imply a real prompt-caching/context-compaction backend signal that is currently just illustrative strings (`Run:805,842`).

---

**Rebuild takeaways for engineering**: The Steps tab is the load-bearing surface — model it as `RunTrace` with a 3-level in-page navigation (`stepView`/`taskView`) over an **agent → artifact(kind) → wave → task** tree, with a sticky per-agent "context received" rail. The four run screens are one component parameterized by `run.status` + (for live) `run.phase`; the completed/live/failed differences are entirely in agent-status maps, streaming flags, and the gate/clarify interactivity. Governance/Audit is the only place to break the one-chroma rule (green/amber/red status palette). The chat column is presentational history + deep-link cards; real user interaction (answer clarifications, approve gate) belongs in Steps, not chat.
