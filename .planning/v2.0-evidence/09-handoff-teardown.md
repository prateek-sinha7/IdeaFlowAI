# Handoff / Draft-PR Teardown (+ transport/scope note)

> **Evidence doc — Milestone v2.0** (see `README.md` + POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`).
> Verbatim final report of a `ui-teardown` investigation agent, 2026-07-07 (second batch — the five sibling screens + cross-mock reconciliation). Feeds the deferral decision (ND-12) — handoff stays on WebSocket after the D-13 cutover; tab bodies need new backend contracts.
> Anchors are as-of 2026-07-07; verify before acting.

---

I've read the mock in full (240 lines to EOF), all 12 current-product handoff files, the shared `useWebSocket` hook, the backend WS route, and the convergence-plan decisions D-13/D-14/D10 plus Phase 32. Here is the complete teardown.

---

# UI Teardown — `Hexaware Handoff.dc.html` (Code-handoff / Draft-PR surface)

**Source:** `/Users/1000060523/Documents/Work/VelocityAI-New-UI/Hexaware Handoff.dc.html` (240 lines, read to EOF)
**Maps to:** Flowin `/handoff/[token]` route suite (`frontend/src/components/handoff/*`)
**Mode:** rebuild-grade + current-product mapping + delta classification

## 0. Substrate / rendering mechanics (how the mock is driven)

DC-framework file. One logic class `class Component extends DCLogic` in `<script type="text/x-dc" data-dc-script>` (`Handoff.dc.html:167-238`). Binding model:

- **State object** (`:169`): `state = { tab:'diff', diffFile:0 }` — the *entire* interactive surface. Two fields only.
- **Mutation**: single method `set(p){ this.setState(p); }` (`:200`). Every handler routes through it.
- **ALL-CAPS constant data arrays** (the screen's real feed): `HAGENTS` (`:171-175`), `FILES` (`:176-185`), `SUITES` (`:186-190`), `CHECKS` (`:191-198`). All hardcoded — no fetch, no socket, no props (`data-props="{}"` at `:167`).
- **`renderVals()`** (`:202-236`) computes a derived binding object each render; the markup interpolates it via `{{ }}`, iterates with `<sc-for list="{{ … }}" as="…">`, and branches with `<sc-if value="{{ … }}">`.
- Derived booleans gate the three tab bodies: `isDiff / isTests / isCompliance` (`:233`) from `s.tab`.

---

## 1. Page / state inventory

Single SPA screen, one route. Navigation domain is tiny:

| State field | Domain | Driver | Effect |
|---|---|---|---|
| `state.tab` | `'diff'` \| `'tests'` \| `'compliance'` | tab buttons `onClick → set({tab:id})` (`:213`) | swaps right-pane body via `isDiff/isTests/isCompliance` sc-ifs |
| `state.diffFile` | `0..3` (index into `FILES`) | changed-file rows `onClick → set({diffFile:i})` (`:215`) | selects which file's unified diff renders (`cur` at `:217`) |

Initial snapshot: **`tab:'diff'`, `diffFile:0`** — i.e. the Diff tab showing `RefundController.ts`.

**Off-screen navigation (3 links, all leave to the workspace mock):** logo (`:33`), sub-header back-arrow (`:47`), and the "Draft PR #142" button (`:54`) are all `<a href="Hexaware Workspace v2.dc.html">`. There is **no** live-vs-complete-vs-failed lifecycle in this mock — it renders exactly one frozen "mid-run, mostly-done" snapshot (2 agents Done, 1 Running), yet shows fully-populated Tests + Compliance reports (temporal inconsistency; see fiction #F14).

Pipeline-status states that the *logic* defines but this snapshot never exercises: agent `idle`→"Queued" (`SB.idle`, `:204`) is defined but unused (all 3 agents are done/running); compliance check `fail`/`error` has **no** branch in `OUT` (`:226-227`) — an unrenderable state.

---

## 2. Layout regions

Full-height flex column, `#F0EEE7` beige canvas, `Heebo` body font (`:29`).

1. **Top bar** — 58px, `#111114` near-black (`:32-43`): logo lockup (left), centered repo label (abs-positioned), spacer, avatar (right).
2. **Sub-header** — `#F6F4EE` beige, 1px bottom border (`:46-56`): back-arrow · title block (eyebrow + compliance pill + H1) · right cluster (branch + Draft-PR button).
3. **Body** — flex row (`:59`):
   - **Left panel** — 340px fixed, `#F6F4EE` (`:62-88`): sticky header (eyebrow + description) + scroll region (agent cards `sc-for` + Integrations card).
   - **Right panel** — flex, `#F0EEE7` (`:91-162`): tab bar (`sc-for tabs`, `:92-94`) + scroll body holding three mutually-exclusive `sc-if` branches.
     - **Diff branch** (`:99-116`): 260px changed-files rail + flex diff pane.
     - **Tests branch** (`:119-139`): 820px centered column — 3-tile stat grid + suites card + console block.
     - **Compliance branch** (`:142-159`): 820px centered column — "safe to merge" banner + checks card.

No modals, drawers, overlays, toasts, or tooltips exist in the mock.

---

## 3. Per-region element enumeration

### 3.1 Top bar (`:32-43`)
- **Logo** (`:33-36`): `HEXAWARE` (Manrope 800 italic, white) + 5px `#3C2CDA` dot. Link → workspace mock. Purpose: brand/home.
- **Repo label** (`:37-40`): GitHub octocat SVG (`#B7B9C4`) + text `hexaware/payments-service`. **Static text, not a link.** Absolutely centered.
- **Avatar** (`:42`): 30px `#3C2CDA` circle, initials `AK`, Manrope 600. `cursor:pointer` but **no handler**.

### 3.2 Sub-header (`:46-56`)
- **Back-arrow** (`:47`): 34px rounded button, chevron-left. Link → workspace mock. Has `style-hover` border shift.
- **Eyebrow** (`:49`): `Code handoff` (Manrope 600, 10px, tracked caps, `#9A9B92`).
- **Compliance pill** (`:49`): `Running · compliance`, amber (`#9A6B1E` on `#F5EEDD`, border `#E8DBC0`), with a pulsing 6px dot (`animation:pulse 1.4s`). **Hardcoded label** — not bound to any running state.
- **H1 task title** (`:50`): `Add partial-refund support to the payments service`, Manrope 300, 20px.
- **Branch chip** (`:53`): `feat/velocity-handoff-8f2`, mono, `#8A8B82`. Static.
- **Draft-PR button** (`:54`): black pill, octocat + `Draft PR #142`. **`<a>` → workspace mock** (does not open a PR). `#142` hardcoded. `style-hover:background:#2A2B33`.

### 3.3 Left panel — Handoff pipeline (`:62-88`)
- **Header** (`:63-66`): eyebrow `Handoff pipeline` + description "Three server agents edit the repo in a sandbox, then open a draft PR for your review." Static.
- **Agent cards** — `<sc-for list="{{ agents }}" as="a">` (`:68-81`), 3 items from `HAGENTS`. Each card:
  - Avatar (`:71`): 36px rounded, initials (`a.init`), bg swaps `#F5EEDD` if running else `#EFEDE6` (`avatarStyle`, `:208`).
  - Name (`a.name`, Manrope 600) + role (`a.role`, Heebo) (`:72`).
  - Status badge (`:73`): `a.badge` label from `SB` map → Done (green) / Running (amber) / Queued (grey). Styles at `:207`.
  - Footer row (`:75-79`): `<sc-if value="{{ a.running }}">` spinner (amber, `.spin` keyframe) / `<sc-if value="{{ a.done }}">` check (green), then `a.detail` line.
  - Card border tints amber when running (`cardStyle`, `:209`).
  - **Cards are display-only in the mock** — no `onClick` (unlike the current product, where agent cards are the tab selector).
- **Integrations mini-card** (`:82-86`): eyebrow `Integrations`; row 1 = octocat + `GitHub` + green `Connected` badge; row 2 = `CI` chip + `GitHub Actions` + green `Passing` badge. **All hardcoded, no handlers, no real connection state.**

### 3.4 Right panel — tab bar (`:92-94`)
- `<sc-for list="{{ tabs }}" as="t">` → 3 buttons from `tabDef` (`:212`): `Diff {4}`, `Tests {44}`, `Compliance {6}`. Count is a dimmed `<span opacity:.5>`. Active tab: `#15161A` text + 2px `#3C2CDA` bottom border; inactive: `#8A8B82` + transparent (`:213`). `onClick → set({tab:id})`.

### 3.5 Diff branch (`:99-116`)
- **Changed-files rail** (`:101-106`), 260px: eyebrow `Changed files` + `<sc-for list="{{ files }}" as="f">` (4 rows). Each row (`:104`): filename (mono, ellipsis) + `+{add}` (green `#1F7A4D`) + `-{del}` (red `#A33A32`). `onClick → set({diffFile:i})`; selected row bg `#F4F2FB` (`rowStyle`, `:216`).
- **Diff pane** (`:107-114`): header = `{{ diffName }}` (mono) + `+{{ diffAdd }}` / `-{{ diffDel }}` (from selected `cur`). Body = `<sc-for list="{{ diffLines }}" as="l">` (`:110-112`): each line = 34px gutter (`l.gutter`) + `l.text` (SF-Mono, `white-space:pre`). Line styling computed at `:219-224`:
  - `@@` hunk header → indigo `#6E5EDA` on `#F4F2FB`, empty gutter.
  - `add` → green `#1F5F3D` on `#E9F3ED`, incrementing gutter number.
  - `del` → red `#8A2F28` on `#F7E9E7`, gutter `·`.
  - `ctx` → grey `#6E6F76`, incrementing gutter number.

### 3.6 Tests branch (`:119-139`)
- **Stat tiles** (`:121-125`), 3-col grid: `42 Passed` (green tile), `0 Failed`, `2 Skipped`. **All three numbers are literal text in the markup**, not bound to `SUITES`.
- **Suites card** (`:126-136`): header `Test suites` + `<sc-for list="{{ suites }}" as="su">` (3 rows). Each row (`:129-134`): a **static** green circle-check SVG (no pass/fail conditional — `SUITES` has no status field), `su.name` (mono), `{su.passed} passed`, `su.dur`.
- **Console block** (`:137`): hardcoded terminal — `PASS tests/refund.spec.ts`, `PASS tests/ledger.spec.ts`, `Tests: 42 passed, 2 skipped, 44 total`, `Time: 3.51s · coverage 87%`. Fully static.

### 3.7 Compliance branch (`:142-159`)
- **Banner** (`:144-148`): shield-check icon + `Compliant — safe to merge` + subtitle `5 of 6 checks passed · 1 non-blocking advisory · full evidence attached to the PR` + a `running…` pill. All literal text (banner simultaneously says "compliant/safe to merge" *and* "running…" — inconsistent).
- **Checks card** (`:149-157`): `<sc-for list="{{ checks }}" as="c">` (6 rows from `CHECKS`). Each row (`:151-155`): status icon (circle wrap + SVG path from `OUT[status]`, `:226-229`), `c.name` + `c.note`, and a `c.badge` pill (`Pass` green / `Advisory` amber). Only `pass`/`warn` are representable.

---

## 4. The data contract (load-bearing)

Every field the screen consumes, grouped by entity. "Value shape" flags real-shaped vs synthesized/literal.

**Entity: Agent** (`HAGENTS`, `:171-175`) — 3 rows: coding, test, compliance
| Field | Type | Value shape |
|---|---|---|
| `id` | `'coding'\|'test'\|'compliance'` | real key |
| `init` | string (`CD`/`TS`/`CP`) | derived label |
| `name` | string | real-shaped |
| `role` | string | real-shaped |
| `status` | `'done'\|'running'\|'idle'` | drives spinner/check/badge |
| `detail` | string (`"Edited 4 files across 3 commits"`, `"Added 12 tests · 42 passed"`, `"Running dependency audit…"`) | synthesized prose; **"3 commits" has no field elsewhere** |

**Entity: File / Diff** (`FILES`, `:176-185`) — 4 rows
| Field | Type | Value shape |
|---|---|---|
| `name` | string (repo-relative path) | real-shaped |
| `add` | int | **overstated** (34 add claimed vs ~8 add lines rendered) |
| `del` | int | overstated |
| `lines[]` | `[type, text][]`, `type ∈ '@@'\|'ctx'\|'add'\|'del'` | real-shaped unified-diff fragments |
| *(derived)* `gutter` | string | synthesized client-side (incrementing counter, `:218-223`) |

**Entity: Test suite** (`SUITES`, `:186-190`) — 3 rows
| Field | Type | Value shape |
|---|---|---|
| `name` | string | real-shaped |
| `passed` | int | real-shaped (sums to 42) |
| `dur` | string (`"1.2s"`) | real-shaped |
| *(no `failed`/`status`/`skipped` field)* | — | icon is always green-check |

**Entity: Compliance check** (`CHECKS`, `:191-198`) — 6 rows
| Field | Type | Value shape |
|---|---|---|
| `name` | string (License scan / SAST — CodeQL / Secret scan / Test coverage / Dependency audit / Conventional commits) | real-shaped |
| `status` | `'pass'\|'warn'` | drives icon+badge (no `fail`) |
| `note` | string | real-shaped |

**Entity: Tab** (`tabDef`, `:212`): `id`, `label`, `count` (Diff count = `FILES.length` **real**; Tests `'44'` **literal**; Compliance `'6'` literal).

**Loose literals (no backing entity):** stat tiles `42/0/2` (`:122-124`); console lines (`:137`); banner `5 of 6 / 1 advisory` (`:146`); header `hexaware/payments-service`, `AK`, `Running · compliance`, `Add partial-refund support…`, `feat/velocity-handoff-8f2`, `Draft PR #142`; Integrations `Connected` / `Passing`.

---

## 5. Design language

**Source design-system file:** `Hexaware Run - Design System.dc.html` (sibling) confirms the canonical palette — `#3C2CDA` is the single most-used named color (43 hits) and the "one blue"/"Accent"; `Manrope` (94) + `Heebo` (86) are the type pair; `#F0EEE7` "Beige", `#15161A` ink, `#111114` near-black are named tokens.

**Tokens actually used in this mock:**
- **Neutrals/beige:** canvas `#F0EEE7`; panel beige `#F6F4EE`; card cream `#FCFBF7`; ink `#15161A`; secondary ink `#20222B` / `#3A3B42`; muted `#8A8B82` / `#9A9B92` / `#6E6F76`; borders `#E6E3DB` / `#E2DFD6` / `#E4E1D8` / `#E0DDD3`; near-black chrome `#111114`.
- **Accent ("one blue"):** `#3C2CDA` (tab underline, logo dot, avatar); indigo diff-hunk `#6E5EDA` on wash `#F4F2FB`; hover `#2A2B33`.
- **Status palette (governance exception, green/amber/red):** green `#1F7A4D`/`#2E6A48`/`#1F5F3D` on `#E7F0EA`/`#E9F3ED`, border `#CFE3D6`; amber `#9A6B1E` on `#F5EEDD`, border `#E8DBC0`; red `#A33A32`/`#8A2F28` on `#F7E9E7`.
- **Type:** headings/labels `Manrope` (300 for H1, 600 for labels, 800 italic logo); body `Heebo`; code `'SF Mono', ui-monospace`. Tracked-caps eyebrows (`.12em`).
- **Radii:** cards 12-14px, pills 999px, rows 8px, small chips 5-6px. **Elevation:** near-flat (1px borders + occasional subtle shadow). **Motion:** `spin .9s` (running), `pulse 1.4s` (live dots) — CSS only.

**Component idioms:** rounded-rect cards on cream; caps-tracked eyebrow labels; status pills (999px, tinted bg + 1px border + colored text); tab bar = text + accent underline; stat tiles = big Manrope number + small caps label; list-rows with left icon + flex label + right-aligned metric; terminal block = dark `#0C0D12` with syntax-tinted mono.

---

## 6. Fiction register (mock-only / decorative / synthesized — plan against NONE of these)

- **F1.** Entire screen is static: `HAGENTS/FILES/SUITES/CHECKS` are hardcoded constants (`:171-198`). No fetch, no WS, no props.
- **F2.** Only two things actually do anything: tab switch and file select (both `setState`). Everything else is inert.
- **F3.** "Draft PR #142" button (`:54`) navigates to the workspace mock — **does not open a PR**; `#142` is a literal.
- **F4.** Avatar `AK` (`:42`) — `cursor:pointer`, no handler.
- **F5.** Repo label `hexaware/payments-service` (`:39`) — static text, not a link; octocat decorative.
- **F6.** Header **compliance pill `Running · compliance`** (`:49`) — hardcoded; pulsing dot is pure CSS, not a live signal.
- **F7.** Branch chip `feat/velocity-handoff-8f2` (`:53`) — static.
- **F8.** Integrations mini-card `GitHub Connected` + `GitHub Actions Passing` (`:84-85`) — hardcoded badges; no connection/CI state; no handlers.
- **F9.** Agent `detail` "Edited 4 files across **3 commits**" (`:172`) — "3 commits" appears nowhere else; synthesized.
- **F10.** File `add`/`del` counts (`+34/-2` etc., `:177-184`) are **overstated** vs the handful of `lines` actually rendered.
- **F11.** Diff gutter numbers (`:218-223`) are synthesized client-side, not real file line numbers.
- **F12.** Tests stat tiles `42 / 0 / 2` (`:122-124`) are **literal markup**, not computed from `SUITES`.
- **F13.** Suite rows always show a green check (`:130`) — `SUITES` has **no** pass/fail field; a failing suite is unrenderable.
- **F14.** Console block (`:137`) is fully hardcoded and references `tests/ledger.spec.ts` — a suite absent from both `FILES` and `SUITES` (mock data inconsistency).
- **F15.** Compliance banner (`:146`) `5 of 6 … 1 advisory` is literal text; it also shows `running…` while asserting "safe to merge" (contradiction).
- **F16.** Compliance checks (`OUT`, `:226-227`) handle only `pass`/`warn`; a `fail` status would crash on `o.stroke` (undefined) — no failing-check path exists.
- **F17.** Agent `idle`→"Queued" state (`SB.idle`, `:204`) is defined but never shown.
- **F18.** **No** loading / empty / error / expired / failed-agent states exist anywhere — only the happy mid-run snapshot.
- **F19.** Compliance tab shows a complete report while the compliance agent is still "Running" (`:174` vs `:142-159`) — end-state content under a running pipeline.

---

## 7. Current-product mapping + delta classification

Current home = `frontend/src/components/handoff/` reached via `frontend/src/app/handoff/[token]/page.tsx` → `HandoffWorkflow.tsx`. It is a **separate run experience** with its own `useHandoffPipelineState` reducer (`useHandoffPipelineState.ts:50-140`), its own `HandoffStreamMessage` envelope (`types.ts:108-113`), and its **own** `/ws/handoff/{token}` socket opened through the shared `useWebSocket` hook (`HandoffWorkflow.tsx:155-183`).

| Mock region (file:line) | Current surface (file) | Delta | Notes |
|---|---|---|---|
| Two-tier chrome: black top-bar (`:32-43`) + beige sub-header (`:46-56`) | Single white header row `HandoffWorkflow.tsx:248-301` | **RESTRUCTURE + RESKIN** | current has one header tier; mock adds a black GitHub-style top bar above it |
| Repo label `hexaware/payments-service` (`:39`) | `session.repo_url` in header (`HandoffWorkflow.tsx:266`) | **RESKIN** (relocate to top bar) | data exists |
| Avatar `AK` (`:42`) | — | **NEW-BUILD** (minor) | no user avatar in current handoff header |
| Eyebrow `Code handoff` + H1 task + branch (`:49-53`) | `HandoffWorkflow.tsx:257-268` (`source_client·mode`, `task_description`, `repo_url·source_branch`) | **RESKIN** | data exists; current eyebrow richer |
| Header compliance pill `Running · compliance` (`:49`) | — (current status lives in left panel label `HandoffAgentPanel.tsx:174-181`) | **NEW-BUILD** | "current running phase" header pill doesn't exist; `pipelineStatus` exists to feed it |
| Draft-PR button in header (`:54`) | PR **strip** in preview `HandoffPreviewPanel.tsx:131-155` (`state.prUrl/prNumber/branchName`) | **RESTRUCTURE** | relocate strip→header; data exists (`api-handoff.ts:28-30`) |
| **Start/Retry** (absent in mock) | `HandoffWorkflow.tsx:280-299` | — | current has it; mock assumes already running — keep it |
| Left agent cards (`:68-81`) | `HandoffAgentPanel.tsx` `AgentCard` (`:32-155`) | **RESKIN** | structurally equivalent (avatar+name+role+status badge+detail); current adds progress bar, N/M, duration, SKIPPED, phase log — superset |
| Left "Integrations" mini-card (`:82-86`) | Full `IntegrationsCard.tsx` (PAT + API-key manager) — not shown in panel | **NEW-BUILD** (compact status) + **BACKEND-NEEDED** | a 2-line status readout is new; `GitHub Connected` maps to `GithubPatStatus` (`api-handoff.ts:37-43`); **`GitHub Actions Passing` = no CI-status field exists** |
| Tab bar Diff/Tests/Compliance + counts (`:92-94`) | `HandoffPreviewPanel.tsx:71-112` (same 3 tabs + auto-follow) | **RESKIN** | mock adds per-tab counts (Diff real, Tests/Compliance literal); current adds auto-follow + per-tab status glyph |
| **Diff tab**: changed-files rail + unified line diff w/ gutter+hunks (`:99-116`) | `DiffView.tsx` — card-per-edit stacked old/new boxes (`:92-197`) | **RESTRUCTURE + BACKEND-NEEDED** | current model = `edits[]{old_string,new_string}` (`types.ts:22-27`); **no file rail, no per-file add/del counts, no unified/gutter/hunk model** — needs a git-patch/line-diff contract the pipeline doesn't emit |
| **Tests tab**: pass/fail/skip tiles + suite table + console + coverage% (`:119-139`) | `ReportViews.tsx` `TestReportView` (`:81-174`) | **RESTRUCTURE + BACKEND-NEEDED** | current `HandoffTestReport` is *qualitative* (`verdict, missing_coverage, quality_issues, recommended_additions, tests_present`, `types.ts:36-43`); **no passed/failed/skipped counts, no per-suite durations, no console output, no coverage number** — effectively a new data model |
| **Compliance tab**: "safe to merge" banner + fixed 6-check checklist (`:142-159`) | `ReportViews.tsx` `ComplianceReportView` (`:176-253`) | **RESTRUCTURE + BACKEND-NEEDED** | current `HandoffComplianceReport` is *findings-oriented* (`verdict, findings[]{category,severity,location,issue,recommendation}, positives`, `types.ts:45-58`); **no fixed checks[] (license/SAST/secret/coverage/dependency/commits) with pass/warn** — banner maps partially to `verdict+summary` |

**Backend gaps to name explicitly** (mock shows data no current handoff API/event provides):
1. **Unified/line diff** (hunks, per-file `+add/-del`, gutter) — current emits minimal-substring edits only. Either the pipeline must produce a real git patch, or the FE computes a diff from full file contents the pipeline would need to send.
2. **Quantitative test results** — `passed/failed/skipped` totals, per-suite `passed`+`dur`, raw console log, coverage %. Not in `HandoffTestReport`.
3. **Structured compliance checks[]** — the named 6-check checklist with per-check `pass/warn`+note. Not in `HandoffComplianceReport` (findings model).
4. **CI status** — `GitHub Actions Passing`. No field.
5. **Commit count** — mock's "3 commits". Current tracks `edits`/`edit_results`, not commits.

Everything else (agent set, PR link, repo/branch/task, PAT status) already exists in `HandoffSessionView` (`api-handoff.ts:14-35`) + the report types — those are RESKIN, not backend work.

---

## 8. Cross-page inventory table

| Mock surface | Current-product home | Delta class | Notable data gaps |
|---|---|---|---|
| Black top-bar tier (logo/repo/avatar) | `HandoffWorkflow.tsx` header (one tier) | RESTRUCTURE + RESKIN | user avatar (minor) |
| Sub-header (eyebrow/task/branch) | `HandoffWorkflow.tsx:257-268` | RESKIN | — |
| Header compliance pill | left-panel status label | NEW-BUILD | "current running phase" surfacing (data present) |
| Header Draft-PR button | preview PR strip `HandoffPreviewPanel.tsx:131-155` | RESTRUCTURE | — |
| Left agent cards | `HandoffAgentPanel.tsx` | RESKIN | — |
| Left Integrations mini-card | `IntegrationsCard.tsx` (settings only) | NEW-BUILD + BACKEND-NEEDED | **CI status** (`GitHub Actions`) |
| Tab bar + counts | `HandoffPreviewPanel.tsx:71-112` | RESKIN | Tests/Compliance counts are literal |
| Diff tab (rail + unified diff) | `DiffView.tsx` | RESTRUCTURE + BACKEND-NEEDED | **unified/line diff + per-file +/- counts** |
| Tests tab (tiles/suites/console) | `ReportViews.tsx:81-174` | RESTRUCTURE + BACKEND-NEEDED | **pass/fail/skip counts, suite durations, console, coverage%** |
| Compliance tab (banner + 6 checks) | `ReportViews.tsx:176-253` | RESTRUCTURE + BACKEND-NEEDED | **structured checks[] w/ pass/warn** |

---

## NOTE — Handoff reskin delta, transport consistency, and milestone scope

### (a) Reskin delta to black/beige/one-blue + Manrope
The handoff FE is on the **old** Tailwind look — `bg-gray-50`, `blue-600/blue-500`, `emerald/amber/red-50`, `lucide` icons, system font (see `HandoffWorkflow.tsx`, `HandoffAgentPanel.tsx`, all handoff components). The token swap to the DS mock (canvas `#F0EEE7`, cream cards `#FCFBF7`, one-blue `#3C2CDA`, Manrope/Heebo, governance green/amber/red retained) is a **pure RESKIN for the shell + agent panel + tab bar** — those surfaces are structurally equivalent and would fall straight out of the Phase 32 token layer (`globals.css`) + primitive set (Button/Card/Tabs/Badge/Pill, per plan line 58). It's low-risk because the handoff feature is one self-contained folder that imports only shared helpers (`HandoffWorkflow.tsx:44-47`).

**But the three tab bodies are NOT reskins** — Diff (unified-diff rail), Tests (quantitative tiles/console), and Compliance (6-check checklist) are RESTRUCTURE **and** each needs new backend data (see §7 gaps 1-3). Reskinning those to *look* like the mock without the data would be a facade over a different information model. So "reskin the handoff screen" is honest only for the chrome + left panel + tab bar; the tab contents are a redesign+backend effort.

### (b) Transport-consistency implication (real cost vs isolated)
The v2.0 cutover (D-13, plan line 28) replaces `/ws/chat` with SSE-down + REST-up **in full, deletion as the exit gate** — killing the hand-rolled reconnect/ping/`after_seq` machinery and the `Sec-WebSocket-Protocol` bearer hack. D-13 **explicitly fences `websocket_handoff.py` (external IDE surface, ledger D10) as untouched**, and the backend route confirms it exists and is independent: `backend/app/api/websocket_handoff.py:80` (`@router.websocket("/ws/handoff/{token}")`).

The subtlety the plan does **not** call out: the *frontend* handoff opens its own socket through the **shared** `useWebSocket` hook (`HandoffWorkflow.tsx:157` builds `…/ws/handoff/{token}`; `:179-183` mounts it). That hook (`src/hooks/useWebSocket.ts`) is exactly the machinery D-13 celebrates deleting — subprotocol auth (`:104`), client ping (`:115-123`), exponential-backoff reconnect (`:168-175`), 4001-logout (`:149-157`). After the cutover deletes the `/ws/chat` run-handlers, **`useWebSocket.ts` cannot be removed — handoff becomes its sole remaining consumer.** So WebSocket survives in the codebase (one FE hook + one fenced BE file + the subprotocol hack) purely for this one screen.

**Assessment: acceptably isolated for v2.0, but a real, named residual cost.** Isolated because — the backend file is explicitly fenced (D10); the FE consumer is one folder; handoff has no chat/gate/clarify commands, so none of the D-13 REST command endpoints apply to it; and D-14's app-level connection provider (plan line 29, item a) is about the *main* run connection surviving route changes (it name-checks "handoff" as a route to survive, not as a second socket to manage). Real cost because — (1) the "delete WS entirely" cleanliness D-13 wants is **not** actually achieved; the hook + subprotocol hack + hand-rolled reconnect live on; (2) the team now maintains **two** client transports (SSE for runs/chat, WS for handoff) with divergent reconnect/JWT-refresh/visibilitychange semantics — D-14's resilience work (silent JWT refresh, `visibilitychange`/`online` reconnect) would apply to SSE but **not** automatically to the handoff WS; (3) any grep-ratchet added at cutover to ban WS resurrection must carve out `websocket_handoff.py` + the handoff hook usage or it will false-fire.

### (c) Fold in, or defer? — recommend **DEFER (with an optional thin reskin)**
**Defer the structural + backend work.** Reasons: (1) handoff is a separate run experience with its own state hook, route family, and an *already-fenced* transport — folding it in expands Phase 32 (already the largest phase, plan line 58) for little shared leverage; (2) its 3-agent pipeline + Diff/Tests/Compliance IA diverges from the main run screen's chat-lane + Preview/Steps/Files/Audit IA — the primitives are reusable but the content models are not; (3) the mock's Tests + Compliance + unified-diff tabs need **new backend contracts** (§7 gaps 1-3), which is pipeline/API work miscategorized inside a FE-redesign milestone; (4) handoff appears in **no** v2.0 phase, and D-13/D10 deliberately leave its transport alone — pulling it in silently re-opens a fenced surface.

**Optionally fold in a strictly token-only reskin** of the chrome + agent panel + tab bar (swap gray/blue-600 → beige/`#3C2CDA` + Manrope on the ~6 existing components, reusing the Phase 32 `globals.css` tokens) **iff** cross-app visual coherence is a v2.0 exit bar — otherwise a user bouncing from a redesigned run screen to an old-Tailwind handoff screen sees a seam. Constrain that slice hard: **no** data-model changes, **no** transport changes, **do not touch `/ws/handoff` or `useWebSocket.ts`** (respect the D10 fence).

**Recommended ledger action:** add an explicit note that (i) handoff is intentionally excluded from the D-13 cutover and remains on WebSocket, so `useWebSocket.ts` cannot be deleted at Phase 29 exit; (ii) a dedicated post-v2.0 "Handoff redesign" phase owns the unified-diff / quantitative-tests / checks-checklist backend contracts + the header Draft-PR/compliance-pill restructure. That keeps the cutover's "WS deleted" claim honest (WS deleted *for runs/chat*; retained *for handoff by design*) and prevents anyone from assuming the reskin covers the tab bodies.
