# SSE QA — UI Launch-Journey Scenarios (listed + tracked)

> The launch-journey half of the live-SSE QA campaign ([test sheet](./SSE-QA-TEST-SHEET.md) · [bug log](./SSE-QA-BUG-LOG.md)). Grounded by a discovery agent that read the launch code + `IMPLEMENTATION-REGISTER.md` to EOF; every selector is from source (none invented).
> **Status:** ⬜ pending · 🔄 running · ✅ pass · ❌ fail (→ BUG-id) · ⚠️ pass-with-concern · ⛔ blocked (tier/input-gated)
> Every scenario also asserts **0 `/ws/chat`**. Screenshots → job scratch `shots-lj/`.

## Ground-truth selector facts (read first — they reshape driving)
1. **The launch surface has NO production `data-testid`s** — Home/`HomeLaunchGrid`, `LaunchWizard`, `WizardStepper`, template/DS galleries, `IdeaInputPage` — drive by `role`/TEXT/`aria-label`/`#home-launch-prompt`. Only `DesignSystemPicker` (`ds-band-*`) + the run-screen carry testids.
2. **`CreationHub` is dead code**; live Home = `HomeLaunchGrid` (`DashboardLayout.tsx:1468`).
3. Wizard launch button = **"Continue"** (`LaunchWizard.tsx:764`); IdeaInputPage = **"Run workflow"** (`IdeaInputPage.tsx:691`); Composer = **"Run once"** .
4. Deliverable-preview testids (`ppt-preview`, `files-tab`, …) are **test-only mocks** — real renderers emit none; assert by role/text.
5. Real tab testids = **`tab-preview` / `tab-thinking`(label "Steps") / `tab-files` / `tab-audit`** (`Tabs.tsx:41`).
6. **Clarify + review-gate answer UIs render in the STEPS tab, not the chat lane** (`StepsOverviewSpine.tsx:88/231`); the lane only shows a status card + "Answer/Review in Steps" deep-link.
7. Clarify is **mid-run** (`questionnaire_ready`), not a pre-launch step.
8. Full driveable detail (per-scenario steps + selectors) captured at job scratch `launch-journeys.md`; appendix selector list mirrored at the bottom.

## Entry map
| Card | pipeline_type | Entry path | Tier |
|---|---|---|---|
| Generate product requirements | user_stories | Home card → IdeaInputPage → **Run workflow** | basic |
| Pitch an idea | ppt→od_ppt | Home card → `/workflow/create?mode=ppt` (LaunchWizard, Deck) → **Continue** | basic |
| Build an interactive prototype | prototype→od_prototype | Home card → `/workflow/create?mode=prototype` (LaunchWizard, Web) → **Continue** | pro |
| Build an end-to-end application | app_builder | Home card → IdeaInputPage → **Run workflow** | pro |
| Platform workflows | mulesoft_to_springboot / dotnet_to_azure | Home card → IdeaInputPage → pick path → **Run workflow** | enterprise |
| Compose a custom workflow | custom | Home card → ComposerPage → **Run once** | enterprise |

---

## A — Launch journeys (entry-point × happy path)

| ID | Scenario | Expected launch outcome | Status | Evidence/Notes |
|----|----------|-------------------------|--------|----------------|
| LJ-01 | Home composer prompt → **Build** | `onBuild` routes to input/composer with brief preloaded (fallback → custom) | ⬜ | `#home-launch-prompt` + `Build` btn |
| LJ-02 | Generate product requirements (user_stories) → **Run workflow** | `onStartPipeline("user_stories")` → execution | ⬜ | |
| LJ-03 | Pitch an idea (ppt) → LaunchWizard (Deck) → **Continue** | template REQUIRED → `onStartPipeline("od_ppt")` | ⬜ | |
| LJ-04 | Build interactive prototype → LaunchWizard (Web) → **Continue** | DS REQUIRED, template optional → `onStartPipeline("od_prototype")` | ⬜ | BUG-005 area |
| LJ-05 | Build end-to-end app (app_builder) → **Run workflow** | `onStartPipeline("app_builder")` | ⬜ | |
| LJ-06 | Platform workflows (migration) → pick path → **Run workflow** | `onStartPipeline("mulesoft…"/"dotnet…")` | ⬜ | |
| LJ-07 | Compose custom workflow → ComposerPage → **Run once** | `onStartPipeline("custom")` | ⬜ | |
| LJ-08 | Home "Jump back in" recents → open run | `onSelectWorkflowRun` + execution view | ✅ | covered (BUG-001/002 found here) |
| LJ-09 | Home Inspect / WorkflowDialog (look ≠ launch) | read-only inspector, no launch | ⬜ | |
| LJ-10 | Saved workflow launch (My Workflows) | wizard/composer preloaded, launch as LJ-03/04/07 | ⬜ | |
| LJ-11 | Chain-to-next from a completed run | brief hidden, context-from-previous → chained launch | ⬜ | |
| LJ-12 | Wizard Web/Deck toggle mid-flow | resets template/agents/gates, preserves brief/DS/images | ⬜ | |

## B — Per-stage run-screen rendering (chat / Steps / Files / Audit / Preview)

| ID | Surface + state | Expected | Status | Evidence/Notes |
|----|-----------------|----------|--------|----------------|
| LJ-13 | Chat lane: BUILDING | header (Running pill, k/N agents, tokens), "Steer the run" composer, Stop | ✅ | partly (streaming shots) |
| LJ-14 | Chat lane: CLARIFY | "Paused — n questions", "Answer in Steps" deep-link; pill "Clarifying" | ⬜ | questionnaire is in Steps |
| LJ-15 | Chat lane: GATE | "Paused — task plan needs approval", "Review in Steps"; pill "Awaiting approval" | ⬜ | |
| LJ-16 | Chat lane: COMPLETE + ask/refine | "Ask for a change…"; ASK→concierge, CHANGE→refinement chip | ⚠️ | concierge ✅; refinement chip = BUG-003 |
| LJ-17 | Chat lane: TERMINAL (cancelled/failed/degraded) | terminal card + relaunch variants | ⬜ | cancelled path partly (B6) |
| LJ-18 | Chat lane: narrator milestone ResultCards | clarify/gate/pipeline/deliverable/spec_revision cards + deep-links | ✅ | narrator cards seen live |
| LJ-19 | Steps: spine + agent rows + L1→L2→L3 drilldown | spine phase pill, agent rows, agent detail (prompt/output/context), task detail | ✅ | drilldown shot (C5) |
| LJ-20 | Steps: inline CLARIFY questionnaire | chips, "Submit answers & start the build", "Cancel workflow" | ✅ | clarify-ui shot |
| LJ-21 | Steps: inline REVIEW GATE | Approve & build / Request changes (Update specs/Redo/Reject) / plan preview | ✅ | gate resume proven (A6) |
| LJ-22 | Steps: construction block + settled artifact cards | subagent waves, spec/task-plan/governance cards | ⬜ | |
| LJ-23 | Files tab | header, building-hero (running), Final-output hero + Preview/Download (settled), empty/failed states | ⬜ | |
| LJ-24 | Audit tab | audit trail, records pill, live badge, export menu, filters, rows, verdict banner | ⬜ | |
| LJ-25 | Preview tab + "Renders as" + version menu | per-type renderer, preview-chrome, renders-as-switch, Version/Share/Download | ⚠️ | user_stories ✅; pptx blank (BUG-003 area) |
| LJ-26 | Tab host: auto-tab + failed-run behavior | clarify/gate/building→Steps, complete→Preview, failed-no-deliverable→Audit (Preview dropped) | ⬜ | |

## C — Edge / error scenarios (expected-vs-bug)

| ID | Scenario | Expected (correct) | Status | Evidence/Notes |
|----|----------|--------------------|--------|----------------|
| LJ-27 | Launch prototype WITHOUT a design system | **Continue DISABLED** + "Pick a design system" pill; no backend call | 🔄 | **BUG-005 area** — user got a stuck run; investigating whether the guard held |
| LJ-28 | Launch ppt WITHOUT a template | **Continue DISABLED** + "Pick a template" pill | ⬜ | |
| LJ-29 | Empty brief (all 3 paths) | launch button disabled | ⬜ | |
| LJ-30 | Tier-locked deliverable card | card disabled + Lock + "Requires {Tier} plan"; Inspect still works | ⬜ | QA user tier? |
| LJ-31 | Cancel mid-clarify | "Cancel workflow" → terminal/cancelled | ⬜ | |
| LJ-32 | Launch then immediately navigate away | staged draft fires once / re-fires; no double-launch | ⬜ | |
| LJ-33 | Attach image then launch | image threaded out-of-band → spec-writer image_count≥1 (not inlined) | ⬜ | (fixed once in 260710-ftq) |
| LJ-34 | Migration meta selected, no path chosen | Run disabled + "Pick a migration path" | ⬜ | |
| LJ-35 | Zero agents in IdeaInputPage/Composer | Run disabled + "Add agents first" | ⬜ | |
| LJ-36 | Malformed / stale wizard draft | try/catch ignores; one-shot; no crash | ⬜ | |

---

## Driver quick-reference (real production selectors)
- **Home**: `#home-launch-prompt`, `getByRole('button',{name:'Build'})`, cards = `getByRole('button')` w/ the card `<h2>`, Inspect = `getByLabel('Inspect … details')`.
- **LaunchWizard**: `getByLabel('Brief')`, Web/Deck = `getByRole('button',{name:'Web'|'Deck'})`, stepper = `getByRole('tab',{name:'Template'|'Design System'|'Discovery'})`, DS = `getByTestId('ds-band-select')`, launch = `getByRole('button',{name:'Continue'})`.
- **IdeaInputPage**: brief by placeholder, Run = `getByRole('button',{name:/Run workflow|Add agents first|Pick a migration path/})`, migration tiles by label text.
- **Composer**: `composer-deliverable-type`, Simple/Canvas = `getByRole('button',{name:'Simple'|'Canvas'})`, run = `getByRole('button',{name:/Run once/})`.
- **Chat lane**: `execution-chat-lane`, `run-chat-lane`(`data-run-state`), `chat-transcript`, `chat-composer`(`data-composer-mode`), `chat-send`, `chat-stop`, `chat-relaunch`, `chat-terminal-{cancelled,failed,degraded}`, `chat-result-card`(+`-link`), `lane-run-{title,type,status,meta}`, `lane-{clarify,gate}-status`, `lane-deliverable`, `chat-refinement-{chip,confirm,dismiss}`.
- **Tabs**: `tab-preview` / `tab-thinking` / `tab-files` / `tab-audit`; `steps-review-dot`.
- **Steps**: `steps-agent-row`, `construction-{block,progress,task-row}`; gate `chat-gate-{approve,reject,redo,request-changes,update-specs,preview}`; clarify `chat-clarify-{chip,submit,cancel-workflow}`.
- **Files**: `files-building-hero` else role/text.
- **Audit**: `audit-{records-pill,live-badge,export-menu,verdict-banner,row,search,filter-*}`.
- **Preview**: `preview-chrome`, `preview-url`, `preview-progress`, `renders-as-switch`, `renderer-pill`, `run-header`(`data-run-state`).
