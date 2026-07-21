# Cross-Mock Consistency Reconciliation (canonical shared-surface spec + human decisions)

> **Evidence doc — Milestone v2.0** (see `README.md` + POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`).
> Verbatim final report of a `ui-teardown` investigation agent, 2026-07-07 (second batch — the five sibling screens + cross-mock reconciliation). THE design-authority source. Section B is the canonical shared-surface spec every rebuild phase cites; Section C lists the 7 conflicts needing a human ruling.
> Anchors are as-of 2026-07-07; verify before acting.

---

Both breadth agents are fully verified against independent ground truth, and I've directly owned nav/profile/notifications/tokens/status. I have everything needed. Here is the reconciliation.

---

# Cross-Mock Reconciliation — VelocityAI Hexaware mocks

**Bottom line.** The ten mocks share a **consistent foundation** — same two fonts (Manrope + Heebo), same core canvas/ink/card/brand tokens (`#F0EEE7` / `#15161A` / `#FCFBF7` / `#3C2CDA`, all present in all 10 files), same near-black top bar, same wordmark. The drift is in the **secondary layer**, and it clusters into six problems, one of which is genuinely high-risk:

1. **Status palette (highest risk):** the run-status colors mostly agree, but **Handoff makes `running` amber `#9A6B1E`** while every other file makes `running` blue `#3C2CDA`; and the "not-started/stopped" state is a four-way tangle of keys (`idle`/`skipped`/`pending`/`cancelled`), labels (`Queued`/`Not run`/`Skipped`/`Cancelled`), and colors (grey vs amber) — including the **same label "Not run" rendered grey in one file and amber in another.**
2. **The token authority is incomplete and self-contradictory:** the Design System's `COLORS` array documents brand/ink/surface/line/sequence but **zero status colors**, and its documented radius scale (`10=buttons, 12=cards`) contradicts its own component exemplars (`9=button, 14=card`).
3. **Nav is uniformly `Home · Library · Catalogue`** across all five shell files — which disagrees with plan decision D-11 (`Home · Library · My Workflows`) — and it is rendered with **three different element idioms and two different active-state styles.**
4. **Terminology drift**, led by the `Catalogue`/`Library`/`Templates` tangle and a run-output name that is literally different on the same component (`Final output` vs `Final deliverable`).
5. **Component idioms fork** — most damagingly the **avatar** (DS says circle, the whole app draws rounded-squares) and the **secondary button** (DS `500/13px`, app `600/12.5px`).
6. **The same region is depicted differently across files** — the run row has five different field-sets; the agent "card" has four.

Two files carry the only complete chrome: **`Workspace v2` is the canonical shell** (it is the only file with a working notifications dropdown and a working profile menu). `Design System` is the token/shape arbiter but is silent on status and internally loose on radius.

Everything below is observed from the markup with file:line on each side; the rulings apply the authority hierarchy you gave me. Facts sourced from my two extraction sub-agents were spot-checked against ground truth I read myself and all passed.

---

## SECTION A — CONFLICT REGISTER

### Surface 1 — Top bar / navigation

| # | What disagrees | File A | File B | Authority → Resolution |
|---|---|---|---|---|
| 1.1 | **Nav labels** | All shell files: `Home · Library · Catalogue` — `Workspace v2:38-41`, `Run:34-36`, `Failed:34-36`, `Live:41-43`, `Composer:36-38` | `Admin`, `Wizard`, `Handoff`, `Login`, `Design System` have **no product nav** (Admin shows an "Admin" chip `Admin:35`; Handoff shows the repo path `Handoff:37-39`; DS shows a page label `DS:33`) | **Plan D-11 wins.** Rename `Catalogue → My Workflows`. Canonical nav = `Home · Library · My Workflows`. The mocks were internally consistent on `Catalogue` — the change is a plan override, not a mock fix. |
| 1.2 | **Nav element type** | `<button onClick>` — `Workspace v2:39-41` | `<a href>` — `Run:34-36`, `Failed:34-36`, `Composer:36-38`; **dead `<span>`** — `Live:41-43` | **Product behavior = truth.** Nav items are real navigation. Canonical = interactive links/buttons; Live's inert `<span>`s are a mock shortcut. |
| 1.3 | **Nav active-state styling** | Filled translucent pill, no purple: `background:rgba(255,255,255,.11)` + `inset 0 0 0 1px rgba(255,255,255,.14)` — `Workspace v2:1066-1067` (in a pill container `Workspace v2:38`) | White text + `2px solid #3C2CDA` underline — `Run:34`, `Failed:34`, `Composer:38`; **no active state** — `Live:41-43` | **Conflict — see Human Decisions #1.** DS shows no nav to arbitrate. WS is the canonical shell (pill-fill), but the purple-underline better matches the DS "one chroma leads… the active tab" principle (`DS:73`). Flag for a human pick. |
| 1.4 | **Right-side cluster** | Working bell + unread badge + dropdown AND working avatar + profile dropdown — `Workspace v2:44-84` | Dead bell + dead avatar — `Run:39-43`, `Live:51-55`; **avatar only, no bell** — `Failed:39`, `Composer:41`, `Admin:37`, `Handoff:42`; **nothing** — `Wizard`, `Login`, `DS` | **Workspace v2 canonical** (only complete depiction). The other shells' bell/avatar are mock stubs. |
| 1.5 | **Wordmark size** | `800 20px italic #FFF` + `5px #3C2CDA` dot — `Workspace v2:35`, `Run:30`, `Live:37`, `Failed:30`, `Composer:32`, `Admin:32`, `Handoff:34`, `DS:30` | `800 **22px** italic` — `Login:29` | **DS wins** (`20px`). Login's 22px is a splash-panel variant; acceptable but note the deviation. |
| 1.6 | **Live-only run pill in bar** | Live adds an in-progress pill `Prototype · 3/5` with pulsing `#8E88E8` dot — `Live:46-50` | Absent from all other bars | **Product behavior = truth.** A "running" indicator in the bar is legitimate for an active run; not a conflict, but the pattern exists in only one file — canonize it if wanted. |

### Surface 2 — Profile menu

Only **`Workspace v2:70-82`** implements it: header `ak@hexaware.com` + `Plan: Enterprise` (`Workspace v2:74-75`); items **Account Settings, Analytics, Workflow History, Admin console, Log out** (red `#A33A32`). Every other file's avatar is a dead `<div>`. No cross-file value conflict — **single source, canonical = Workspace v2.** The logged-in identity is consistent everywhere: **Ayesha Khan / AK / `ak@hexaware.com` / Enterprise** (`Workspace v2:561-562`, `Admin:126`, `Handoff:42`, gate approvals `Run:910`). Note that **Analytics and Workflow History are reachable only through this menu** — they are not top-nav items — which matters for the D-11 nav.

### Surface 3 — Notifications

Only **`Workspace v2:44-67`** implements it: bell with unread count badge (`#3C2CDA`, `Workspace v2:48`), dropdown titled **Notifications** + **Mark all read** (`Workspace v2:53-54`), rows of icon+title+meta+unread-dot, footer **View workflow history** (`Workspace v2:65`). The kind→color map `NKIND` (`Workspace v2:1154`) is `gate`=amber / `running`=blue / `done`=green / `failed`=red, and the seed data uses exactly those four kinds (`Workspace v2:1016-1022`). `Run`/`Live` render a **dead bell**; `Failed`/`Composer`/`Admin`/`Handoff` have **no bell**. **Single source, canonical = Workspace v2.** (One internal nit: unread rows use `background:#FBFAFE` at `Workspace v2:1156`, an off-palette near-white.)

### Surface 4 — Design tokens

The **foundation is consistent** across all 10 files (verified by extracting every hex per file): `#F0EEE7`, `#15161A`, `#FCFBF7`, `#3C2CDA`, `#111114`, `#E0DDD3`, selection `#DAD6F7` all appear in all ten; fonts are `Manrope` + `Heebo` everywhere with identical Google-Fonts `<link>`. The conflicts are:

| # | What disagrees | Evidence | Authority → Resolution |
|---|---|---|---|
| 4.1 | **DS documents no status colors** | The `COLORS` array (`DS:477-516`) covers Brand/Ink/Surface/Line/Sequence only — **no green/amber/red.** Yet `#1F7A4D`/`#A33A32`/`#9A6B1E` and their tints are used in 5-7 files each. | **DS is authority but incomplete.** The status palette must be *added* to the DS. Until then it is ungoverned (this is why Surface 5 drifts). |
| 4.2 | **DS contradicts itself on radius** | Documented scale `10=buttons, 12=cards` (`DS:259-260`) vs DS's own exemplars: primary button `border-radius:9px` (`DS:331`), component cards `border-radius:14px` (`DS:328`). | **Human Decisions #2** — pick one and make the DS self-consistent. |
| 4.3 | **"One chroma" violated by purple proliferation** | DS Principle 01 = single chroma `#3C2CDA` (`DS:72-73`). But the thinking/reasoning accent renders as **`#6E5EDA`** (`Run:380`, `Live:314`, `Failed:162`, `Handoff:220`) where DS says that icon is `#3C2CDA` (`DS:235`); chart bars use a blue ramp `#5A4CE0`/`#7A6FE6`/`#9A90EC` (`Run:246`); glows/tints add `#C7BEF5`, `#5A4FC0` (`Run:214`, `Composer:273`). | **DS wins.** Fold `#6E5EDA`→`#3C2CDA` for the reasoning accent. The chart ramp lives inside a *previewed deliverable* (a generated deck) so it is lower-priority, but it still breaks the rule. |
| 4.4 | **Warm vs cool greys** | DS ink ramp is warm (`#8A8B82`, `#9A9B92`, `#A0A199`). Cool greys appear: `#B7B9C4` (`Handoff:37-39`), `#6A6B76` (`Login:35`, `Run` code), `#9A9BA6` (`Login:35`). | **DS wins.** Replace cool greys with the warm ramp except in the deliberately "technical" Handoff/code contexts (leave those as a documented exception if desired). |
| 4.5 | **Near-white card duplicates** | Canonical card fill is `#FCFBF7` (`DS:498`), but inner tiles use `#F9F8F3` (`Workspace v2:792`, `Composer:143`) and `#FBFAF6` (`Composer:157`); other near-whites `#FAFAF8`, `#FCFAF3` appear. | **DS wins.** Collapse to `#FCFBF7` / `#F6F4EE`. |
| 4.6 | **Monospace treatment** | `.mono{font-family:'SF Mono',ui-monospace,Menlo,monospace}` class (`Handoff:21`) and inline `'SF Mono',ui-monospace,monospace` (`Run:230`) vs bare `font-family:monospace` (`Failed:69-70`). | **Standardize** on the `'SF Mono'` stack; add it to the DS as the code token. |

Two things that are **not** violations, to avoid false alarms: `#1D86FF`/`#07125E` are DesignComposer editor theme-prop *options* (default stays `#3C2CDA`, `Run:782`); and the One-Dark syntax palette in the code preview (`#C678DD`/`#98C379`/`#E5C07B`/`#61AFEF`, `Run:267`) is an intentional editor theme, foreign to the DS by design.

### Surface 5 — Status palette + stat maps (highest risk)

The **semantic mapping mostly agrees**: `done`→green `#1F7A4D`/`#E7F0EA`/`#CFE3D6`, `failed`→red `#A33A32`/`#F5E5E2`/`#E8CDC8`, `running`→blue `#3C2CDA`/`#ECEAFC`/`#DED9F7` — consistent across `STAT` (`Workspace v2:1077`), `ASTAT` (`Workspace v2:1173`), `NKIND` (`Workspace v2:1154`), and the wave `badgeFor` (`Run:977`, `Live:898`). The conflicts:

| # | What disagrees | File A | File B | Authority → Resolution |
|---|---|---|---|---|
| 5.1 | **`running` color** | Blue `#3C2CDA` — `Workspace v2:1077/1154/1173`, `Run:977`, `Live:898` | **Amber `#9A6B1E`** — `Handoff:204` (`running:{c:'#9A6B1E'…l:'Running'}`), reinforced by the amber header pill "Running · compliance" `Handoff:49` | **Workspace v2 canonical** (most-integrated; DS silent). Make `running` blue everywhere. Fix Handoff. *(See Human Decisions #3 in case Handoff's amber was an intentional "governance-in-progress caution.")* |
| 5.2 | **Same label "Not run", different color** | Grey `#9A9B92`/`#EFEDE6` (`idle→'Not run'`) — `Workspace v2:1173` | **Amber `#9A6B1E`/`#F5EEDD`** (`skipped→'Not run'`) — `Failed:232` | **Workspace v2 canonical.** "Not run / not started" is neutral grey; amber is reserved for cancelled/attention. Fix Failed. |
| 5.3 | **Neutral state key + label fragmentation** | `idle→'Queued'` grey `#8A8B82`/`#F0EEE7` — `Handoff:204`; `pending` grey — `Run:977`, `Live:898` | `idle→'Not run'` — `Workspace v2:1173`; `skipped→'Not run'` — `Failed:232` | **Product behavior = truth for which states exist; Workspace v2 canonical for naming.** Pick ONE key set and ONE label per state (recommended in the canonical spec below). |
| 5.4 | **`cancelled` label by scope** | Run-level `cancelled→'Cancelled'` — `Workspace v2:1077` | Agent-level `cancelled→'Skipped'` — `Workspace v2:1173` | **Likely intentional** (a run is *cancelled*; an agent within it is *skipped*). **Keep but document** — see Human Decisions #4. |
| 5.5 | **`done` key vs `completed` key** | `done` — `STAT`/`ASTAT`/`NKIND` | `completed` — wave `badgeFor` map (`Run:977`, `Live:898`) | **Normalize** the key to `done`; behavior identical, key name drifts. |
| 5.6 | **Validation outcome label** | `badge:'Passed'` — `Run:1020`, `Live:953`, `Failed:239` | `badge:'Pass'` — `Handoff:226` | **Standardize** to `Passed`. |
| 5.7 | **Same badge rendered three ways** | Bordered pill (`badgeStyle` bg+border) — History `Workspace v2:1114` | Colored **text only**, no pill — Home recents `Workspace v2:1081`; **bare dot** — Analytics recent `Workspace v2:523` | **Workspace v2 canonical, but internally inconsistent** — pick one badge form for a run's status and use it in all lists. |
| 5.8 | **`degraded` state** | Referenced in a comment `<!-- degraded / reopen banner -->` `Workspace v2:655` | **Not implemented** — the actual conditions are `dFailed` (red banner, `Workspace v2:657`) and `dCancelled` (amber banner, `Workspace v2:663`) | **No product state "degraded" exists in any mock.** Treat the comment as vestigial; do not build a degraded badge unless the product defines one. |

`amber #9A6B1E` is **overloaded** across the system — it means `cancelled` (`Workspace v2:1077`), `gate/waiting` (`Workspace v2:1154`), `medium` severity (`Run:1024`), `Enterprise` tier (`Admin:135`), *and* (wrongly) `running` (`Handoff:204`) and `Not run` (`Failed:232`). Worth a deliberate decision about how many meanings one hue should carry.

### Surface 6 — Shared component idioms (extracted and cross-checked; DS is arbiter)

| # | Idiom | DS canonical | Divergence | Resolution |
|---|---|---|---|---|
| 6.1 | **Avatar / initials** | **Circle**, `38×38; border-radius:50%; #fff; 1px #E0DDD3` — `DS:404` | App draws **rounded-squares**, no border, `#EFEDE6` fill: `radius11` `Workspace v2:1197`, `radius10` `Composer:272` & `Handoff:208`, `radius8` `Workspace v2:684` | **Human Decisions #5.** This is a different primitive, not a tweak; the app is unanimous on rounded-square, so DS is likely the stale one. Pick, then align DS. |
| 6.2 | **Icon button** | `34×34; radius8; 1px #E6E3DB; #fff; #6E6F76; blue hover` — `DS:333` (matched only at `Run:652`, `Live:592`) | "Back/header" variant `36×36; radius9; 1px #E0DDD3; #FCFBF7; #3A3B42; neutral hover` — `Composer:46`, `Wizard:31`, `Workspace v2:169`, `Handoff:47` | Two legitimate roles (toolbar-action vs header-back). **Define both in the DS**; don't let them collide. |
| 6.3 | **Secondary button** | `border 1px #E0DDD3; radius10; #FCFBF7; #3A3B42; font 500 13px` — `DS:332` | App-wide `font:600 12.5px` — `Composer:48`, `Wizard:112`, `Workspace v2:171`, `Admin:105`, `Live:628`; only `Run:167/621` keep DS | **DS is outvoted** — the app is unanimous on `600/12.5`. Recommend updating DS to `600/12.5` (or human pick). |
| 6.4 | **Primary button radius** | `radius9` — `DS:331` | App standard `radius10` (`Composer:49`, `Admin:49`, `Workspace v2:172`, `Wizard:114`); hero/login `radius11` (`Login:54`, `Workspace v2:103`) | Tied to 4.2. **Pick `10`** (app majority + DS's own documented scale) and fix the DS exemplar. |
| 6.5 | **Dropdown-menu elevation** | `radius12; shadow 0 12px 32px/.12` — `DS:370` (followed by `Run:152`, `Live:630`) | `radius10-11; 0 14px 34px/.16` — `Admin:79`, `Composer:92`, `Workspace v2:403`; notif panel `0 16px 40px/.18` — `Workspace v2:51` | **DS wins** — collapse to one popover elevation (`.12`) with a documented "prominent" tier if truly needed. |
| 6.6 | **Card radius** | `14` (panels), `12` (cards per scale) — `DS:328/260` | Continuum: KPI cards `13` (`Admin:55`, `Workspace v2:674`), inner tiles `10-12` w/ `#F9F8F3`, hero panels `16`/`18` w/ `#E0DDD3` border (`Composer:140`, `Workspace v2:97`) | **DS wins** — publish a discrete radius ladder and snap all surfaces to it. |
| 6.7 | **Status-badge shape** | de-facto `radius5; Manrope 600 8-8.5px; ls .05-.06em` | Outliers `radius6` (`Admin:35`, `Composer:153`), `radius999` (`Workspace v2:218`) | Standardize on `radius5`. |
| 6.8 | **Segmented control active fill** | `active #FCFBF7; shadow …/.08` — `DS:531` | `active #fff/#FFFFFF; shadow …/.1` — `Live:975`, `Workspace v2:1070` | **DS wins.** |
| 6.9 | **Underline tabs** | `active #15161A + 2px #3C2CDA; inactive #8A8B82` — `DS:534-537` | Near-perfect everywhere (`Run:955`, `Live:879`, `Failed:230`, `Handoff:213`); only nit `Workspace v2:1092` bottom-pad 13 vs 12 | Already consistent — adopt as-is. |
| 6.10 | **Modal scrim** | (no DS exemplar) | Standard `rgba(17,17,20,.5)+blur(3px)` (`Admin:96`, `Composer:165`, `Wizard:120`, `Workspace v2:777…`); exception `rgba(17,17,20,.42)` no-blur drawer `Workspace v2:710` | **Workspace v2 canonical**; add scrim to DS; align the drawer. |
| 6.11 | **Form fields** | (none in DS) | **No native `<input>/<select>/<textarea>` in any file** — all faux `div`+placeholder; search field consistent `#FCFBF7; radius10; #E0DDD3` | Real inputs must be designed for the build; DS has no form spec — **gap to fill.** |

### Surface 7 — Terminology drift

| Concept | Wordings in the mocks (file:line) | Resolution |
|---|---|---|
| **Saved-workflow surface** (the #1 tangle) | `Library` nav → resolves to **agents/skills/hooks** (`Workspace v2:40`, page H1 `Workspace v2:303`, count line "14 agents · 8 skills · 8 hooks" `Workspace v2:1091`); `Catalogue` nav → **saved workflows** (`Workspace v2:41`, page H1 "Workflow Catalogue" `Workspace v2:439`); `Workflow History` → **runs** (`Workspace v2:364`); but Composer calls its **agent** palette an "agent catalogue" (`Composer:168,180`) and its save target "Workflow Catalogue" (`Composer:156,190`); "Browse full library" means **templates** (`Workspace v2:230`) | **Plan D-11:** `Library` = agents (keep), `My Workflows` = today's `Catalogue` (saved workflows), `History` = runs. Ban "catalogue" for the agent palette (call it **Agent library / palette**). |
| **Run output** | `Final output` (`Run:629`, `Live:573`) vs `Final deliverable` (`DS:457`) vs `Artifact` / `Artifact row` (`DS:220/402`) vs "deliverable" in copy (`Login:35`, `Workspace v2:602`) | **Human Decisions #6** — pick "Deliverable" or "Output" and use it on the hero, then align DS. Product term is truth. |
| **Deliverable types** | `Deck` (`Run:1042`) vs `Presentation` (`Workspace v2:1005/1028`); `App code` (`Run:1042`) vs `App Builder` (`Workspace v2:930`); `User Stories` (`Run:1042`) vs `Product requirements` (`Workspace v2:112`); `Prototype` (`Run:56`) vs `Interactive prototype` (`Workspace v2:124`, `Wizard:32`) | **Product taxonomy = truth** — pick one canonical name per type (see Human Decisions #7). |
| **revision / version** | Selector says "Version 1/2" (`Run:148/157`) but v2's note is "Latest revision" (`Run:960`); notifications say "revision v2 delivered" (`Workspace v2:1021`); run-type suffix "(Revised)" (`Workspace v2:974/979`); compact pills "v1/v2" | Use **Version** for the artifact iteration; drop "revision" as a synonym or define it as the *act*. |
| **Agent-count phrasing** | `3 / 5 agents` (`Failed:55`, `Live:977`), `5 / 5 agents` (`Run:304`), `Pipeline · 5 agents` (`Run:91`), `6 agents · ~9m` (`Workspace v2:114`), `15 agents` (`Run:281`) | Pick one format (`N / M agents` for active runs, `N agents` for definitions). |
| **Executable unit** | `run` (instance, dominant — `Workspace v2:970` `RUNS`), `workflow` (definition — `Composer:47`), `pipeline` (agent sequence — `Run:91`), `build` (act — `Run:878`); **"job" is never used** | Keep the three-level model: **workflow** (definition) → **run** (instance) → **pipeline** (its agents). Note "Workflow History" counts "runs" (`Workspace v2:364`) — rename to **Run History** for accuracy. |
| **Gate casing** | "Review **G**ates" (`Workspace v2:267`) vs "Review **g**ates" (`Workspace v2:879`, `Composer:144`) | Standardize casing. |
| **Checks surface** | Panel "Audit trail" (`Run:681`, `Live:621`) vs "Compliance & audit" (`Failed:132`) vs "Compliance" (`Handoff:212`); audit category `behavioral` renders as "Governance" (`Run:1023`); "Verification" only as loose prose | Pick one panel name (recommend **Audit**), one label per category. |
| **Plan tiers** | `Basic / Pro / Enterprise` — consistent (`Admin:135`, `Workspace v2:602`) | No change. |

**Agent roster (a real inconsistency, not just naming):** the run pipeline is **not fixed.** `Run`/`Live`/`Design System` show `SW Spec Writer / TP Task Planner / SK Spec Kit Analyzer / BA Build Agent / VA Validation Agent` (`Run:789-839`), but **`Failed` inserts `SA Security Agent` and drops `VA`** → `SW/TP/SK/SA/BA` (`Failed:197-201`). Meanwhile the **Library** catalogue is a *different* 14-agent "App Builder" roster (`Workspace v2:936-950`), **Composer** is an 11-agent set that uniquely includes a locked `OR Orchestrator` (`Composer:221-231`), and **Handoff** runs a third 3-agent set `CD/TS/CP` (`Handoff:171-174`). Also the initials `SA` collide (`Security Agent` in Failed vs `Security Architecture Agent` in Library/Composer), and roles are sentence-case in Composer/PIPE but Title-Case in Workspace. **Resolution: product behavior = truth** — the actual pipeline for a given deliverable type is whatever the product runs; the mocks should draw that same set. This needs the real agent registry to reconcile (flagged in Human Decisions #7).

### Surface 8 — Same region depicted in multiple files

- **Run row — STRUCTURAL DIFF (five field-sets).** Home recents (status **dot+text**, title, type, ago — `Workspace v2:156-158`) vs History (status **pill**, icon, title, ver, tokens, kebab; no cost — `Workspace v2:388-401`) vs Analytics recent (status **dot**, title, tokens, **cost** — the only one with cost — `Workspace v2:523`, data `1029`) vs Run header (type, title, ago, duration, tokens — `Run:55-62`) vs Failed header (the only one with **agent-count** `3 / 5 agents` — `Failed:49-55`). **Resolution:** define one run-row schema (Workspace v2 History is the richest base) and one status-badge form; let contexts hide fields, not rename them.
- **Agent card — STRUCTURAL DIFF (four shapes).** Library "browse" card (init/name/**cat**/role/desc/dur — `Workspace v2:317-321`) vs Composer "configure" row (init/name/**locked**/role/**model**/override-chips — `Composer:83-104`) vs Run-detail "status" row (init/name/**status badge**, role replaced by dur·output — `Workspace v2:684-686`) vs Handoff card (init/name/role/**status**, different roster — `Handoff:71-78`). **Resolution:** one agent-identity block (avatar+name+role+category), with mode-specific trailing content (browse=dur, configure=model, run=status).
- **Deliverable hero — STRUCTURAL DIFF.** Three eyebrow strings (`Final output` `Run:629` / `Final output · building` `Live:573` / `Final deliverable` `DS:457`) and two meta compositions (`type · size · validated` vs `type · task N of 7 · not-yet-validated`). Handoff has **no** deliverable hero — its output is a `Draft PR #142` (`Handoff:54`). **Resolution:** one hero component with a state (building/validated), one eyebrow string.
- **Audit row — Run ≡ Live AGREE; Failed schema-agrees but retitles panel; Handoff DIFF.** Run and Live share identical markup+schema (`cat/title/agent/out/sev/time/whatIs/rows`); Failed reuses the schema but names the panel "Compliance & audit" and adds blocking severities; Handoff's "Compliance" is a **flat, reduced** row (name+note+outcome only — `Handoff:151-154`). **Resolution:** one audit-row component; Handoff should use the full one or be explicitly a different "compliance summary."
- **Clarify block — Run-settled ≡ Live-settled AGREE.** `CLAR` data is byte-identical (`Run:858-864` ≡ `Live:823-828`); Live additionally has an "awaiting" rendering with option buttons (`Live:226-229`). **Note:** there is **no explicit `default` field** on any clarify question — the "default" is purely the first option being pre-selected (`Live:989`). If the product has real clarify defaults, the schema needs a `default` field.

---

## SECTION B — CANONICAL SHARED-SURFACE SPEC (single source of truth for the rebuild)

### B1 — Navigation & chrome
- **Top nav (per D-11):** `Home · Library · My Workflows`, left-aligned wordmark, centered nav, right cluster. Real links. Active state: **decide pill-fill vs purple-underline once** (Human #1) and apply uniformly. `Analytics`, `Run/Workflow History`, `Account Settings`, `Admin console` live in the **profile menu**, not the top nav.
- **Wordmark:** `Manrope 800 20px italic #FFFFFF` + `5px #3C2CDA` dot, on `#111114` bar height `58px`.
- **Profile menu (from Workspace v2):** header = email + `Plan: {tier}`; items Account Settings, Analytics, Run History, Admin console, Log out (`#A33A32`). Identity: Ayesha Khan / `ak@hexaware.com` / Enterprise.
- **Notifications (from Workspace v2):** bell + `#3C2CDA` unread count; dropdown "Notifications" + "Mark all read"; rows icon+title+meta+unread-dot; footer "View run history". Kind map = the status palette below (`gate`→amber, `running`→blue, `done`→green, `failed`→red).

### B2 — Design tokens (adopt DS ramp; add the two missing families)
- **Fonts:** `Manrope` (structure) · `Heebo` (reading) · `'SF Mono', ui-monospace, Menlo, monospace` (code). Tabular-nums for numbers.
- **Brand (one chroma):** `#3C2CDA` primary · `#3324C4` pressed · `#ECEAFC` fill · `#DED9F7` border · `#F4F2FB` violet-tint · `#8E88E8` on-dark. **Retire** `#6E5EDA`/`#5A4FC0`/`#C7BEF5` etc. into these.
- **Ink (warm):** `#15161A · #20222B · #3A3B42 · #5B5C63 · #6E6F76 · #8A8B82 · #9A9B92 · #A0A199`. Retire cool greys.
- **Surface:** `#F0EEE7` paper · `#F6F4EE` warm · `#FCFBF7` card · `#FFFFFF` white · `#111114` near-black · `#0C0D12` ink-black. Retire near-white dups (`#F9F8F3`, `#FBFAF6`).
- **Line:** `#E6E3DB` border · `#E2DFD6` divider · `#E0DDD3` control · `#EDEBE3` faint-row · `#C6C3B9` faint.
- **Status (NEW — must be added to DS):** green `#1F7A4D`/`#E7F0EA`/`#CFE3D6` · red `#A33A32`/`#F5E5E2`/`#E8CDC8` · amber `#9A6B1E`/`#F5EEDD`/`#E8DBC0` · running-blue `#3C2CDA`/`#ECEAFC`/`#DED9F7` · neutral-grey `#9A9B92`/`#EFEDE6`/`#E2DFD6`. Severity: low `#6E6F76` · medium `#9A6B1E` · high `#B4531E` · critical `#A33A32`.
- **Radius ladder:** `5` tags/badges · `8` nodes · `9-10` buttons *(pick one — Human #2)* · `11` list-rows · `12` menus · `13-14` cards/panels · `18` hero · `999` pills.
- **Elevation:** raised `0 1px 2px /.08` · menu `0 12px 32px /.12` · notif/prominent `0 16px 40px /.18` · modal `0 30px 80px /.30`.
- **Motion:** collapse `max-height .4s cubic-bezier(.4,0,.2,1) + opacity .3s` · chevron `rotate .3s` · hover `.15s` · focus ring `0 0 0 4px rgba(60,44,218,.15)`.
- **Scrim:** `rgba(17,17,20,.5) + blur(3px)`.

### B3 — Status model (one set of keys, labels, colors)
| Key | Label (run-level) | Label (agent-level) | Color |
|---|---|---|---|
| `running` | Running | Running | blue `#3C2CDA` |
| `done` | Done | Done | green `#1F7A4D` |
| `failed` | Failed | Failed | red `#A33A32` |
| `cancelled` | Cancelled | Skipped *(scope-specific — Human #4)* | amber `#9A6B1E` |
| `queued` | Queued | Not run | neutral grey `#9A9B92` |
| `gate`/`review` | Awaiting review | — | amber `#9A6B1E` |

Render a run's status as **one badge form** (bordered pill) in every list. No `degraded` state until the product defines one. Normalize `completed`→`done`. Outcome badge = "Passed".

### B4 — Component idioms (adopt DS; resolve the two forks)
Primary button `#3C2CDA/#fff radius10 font 600 12.5px`; secondary `#FCFBF7 border #E0DDD3 radius10 font 600 12.5px`; icon-button toolbar `34×34 radius8 blue-hover` + header-back `36×36 radius9 neutral`; chip `999px border #E0DDD3 #fff`; card `#FCFBF7 border #E6E3DB radius14`; list-row `border #EDEBE3 radius11`; underline tabs `active #15161A + 2px #3C2CDA`; segmented `track #EAE7DE, active #FCFBF7 shadow /.08`; menu `#FFFFFF radius12 /.12`; **avatar — Human #5** (recommend the app's rounded-square `radius10 #EFEDE6` and update DS). Design real form controls (DS gap).

### B5 — Terminology glossary (canonical)
**Workflow** = saved definition · **Run** = one execution · **Pipeline** = the agents in a run · **My Workflows** = saved workflows surface (was "Catalogue") · **Library** = agent/skill catalogue · **Run History** = past runs (was "Workflow History") · **Deliverable** = a run's output *(or "Output" — Human #6)* · **Version** = artifact iteration (retire "revision") · deliverable types: **Prototype · User Stories · Presentation · App Builder · Custom** *(one name each — Human #7)* · **Audit** = the checks panel · tiers **Basic/Pro/Enterprise** · avoid "job".

---

## SECTION C — Conflicts needing a human decision

1. **Nav active-state idiom** — filled translucent pill (Workspace v2 shell, `Workspace v2:1066`) vs white-text + purple underline (Run family, `Run:34`). Both defensible; the underline better honors the DS "blue leads the active tab" line. Pick one.
2. **Button/card radius** — the DS documented scale (`10=buttons, 12=cards`, `DS:259`) contradicts its own exemplars (`9=button, 14=card`, `DS:331/328`), and the app uses `10`/`13-14`. Choose the canonical ladder and make the DS self-consistent.
3. **Was Handoff's amber `running` intentional?** — I recommend it is a bug (blue everywhere else, `Handoff:204`), but if "running a governance/compliance check" is meant to read as caution, that is a product-semantics call, not a mock fix.
4. **`cancelled` label by scope** — run "Cancelled" vs agent "Skipped" (`Workspace v2:1077` vs `1173`) is probably an intended scope distinction; confirm and document, or unify.
5. **Avatar primitive** — DS circle (`DS:404`) vs the app's unanimous rounded-square (`Workspace v2/Composer/Handoff`). The app outvotes the DS; confirm the DS is the stale one before aligning.
6. **Run-output name** — "Deliverable" vs "Output" (the hero itself says "Final output" while the DS says "Final deliverable").
7. **Canonical deliverable-type names AND the real agent roster** — `Deck` vs `Presentation`, `App code` vs `App Builder`, etc.; and which agents actually run per type (the mocks show three different rosters — `Run`'s 5, `Failed`'s 5-with-Security-Agent, Library's 14, Handoff's 3). These need the real product taxonomy/registry to settle, not a mock ruling.

**Method note:** I owned nav/profile/notifications/tokens/status by reading the files directly; component idioms (Surface 6) and terminology + repeated-region structure (Surfaces 7-8) were extracted by two sub-agents whose claims I spot-checked against ground truth I read myself (Failed roster swap, the cancelled/skipped and Not-run color splits, the Library/Catalogue/History semantics, the agent-card and run-row structural diffs, DS button/segmented/avatar specs, scrim and dropdown-shadow families) — all checks passed, so their file:line facts are folded in as verified.
