# Frontend Run-UI & Chat-Embed Investigation

> **Evidence doc — Milestone v2.0** (see `README.md` in this directory and the POR `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md`).
> Verbatim final report of a max-effort investigation agent, 2026-07-07. Feeds Phases 30-31 and 34-37. Includes the dead chat kit inventory, theming audit, e2e resilience map.

---

All six subagents are complete; I have exhaustive coverage. Here is the consolidated investigation report.

---

# FLOWIN FRONTEND — RUN-SCREEN & CHAT-EMBED INVESTIGATION

Root: `/Users/1000060523/Documents/Work/UKI/Flowin/flowin/frontend`. Every claim is `file:line`-anchored. All 6 sub-investigations reconciled.

---

## 1. STACK

**Framework / build** (`frontend/package.json`, `next.config.ts`, `tsconfig.json`)
- **Next.js `16.2.4`** — App Router (`src/app/`), `output: "standalone"`, `devIndicators:false` (`next.config.ts:3-6`). **React `19.2.4`** + react-dom `19.2.4`.
- **TypeScript `^5`** — `strict:true`, `target:ES2017`, `moduleResolution:"bundler"`, `noEmit`, path alias `@/* → ./src/*` (`tsconfig.json:2-24`).
- Auth app is effectively a **single-page `/dashboard`** with `mainView` state-switching, not URL routing (see §2). Real routes: `/login`, `/register`, `/admin`, `/dashboard`, `/workflow`, `/workflow/ppt/templates`, `/workflow/prototype/templates`, `/handoff/[token]`, `/handoff/settings`, `/preview-fullscreen`, `/test-preview` (`src/app/**`). `app/page.tsx` redirects → `/login`.

**Styling** — **Tailwind CSS v4** (`@tailwindcss/postcss`, `postcss.config.mjs`; `@import "tailwindcss"` at `src/styles/globals.css:1`). Design tokens declared via `@theme inline` + `:root` CSS custom properties in `globals.css:8-46` (`--background:#f5f5f0` beige, `--foreground:#111827`, `--surface:#fff`, `--accent:#2563eb` blue, `--sidebar-bg`, plus legacy `--theme-*` aliases). Legacy `tailwind.config.ts` still defines a **contradictory navy/black palette** (self-labelled a "reference"); `src/styles/theme.ts` (navy/black) is **dead code, zero importers**.

**Component library** — **NONE.** No shadcn, no Radix, no MUI (verified in package.json + `find`). Icons: `lucide-react ^1.14` + `react-icons ^5.6`. Animation: `motion ^12.38` (framer-motion successor, imported as `motion/react`). Markdown: `react-markdown ^10` + `remark-gfm ^4`. Client PPTX: `pptxgenjs ^3.12`.

**State management** — **NO Redux / Zustand / React Query.** All state is local `useState`/`useRef` + one React Context (`src/context/SkillsHooksContext.tsx`). The run-state machine is the `useWorkflow` hook (`src/hooks/useWorkflow.ts`) + orchestration in `src/app/dashboard/page.tsx`. Persistence via `sessionStorage`/`localStorage` (active run id, drafts, token).

**Fonts** — `next/font/google` **Inter** (`--font-inter`) + **Fraunces** (`--font-fraunces`, italic hero) wired in `src/app/layout.tsx:2-20`, exposed via `globals.css:8-12`. JetBrains Mono referenced as a bare string (not loaded).

**Test tooling** — `vitest ^4` unit; **Playwright `^1.56`** e2e (`e2e/`, projects `mocked`/`live`, `playwright.config.ts`). ESLint 9.

---

## 2. RUN SCREEN ANATOMY

**Orchestrator: `src/app/dashboard/page.tsx` (1363 lines)** — owns the WS connection (`useWebSocket`, :792), pipeline state (`useWorkflow`, :799), all content state (userStory/ppt/prototype/genericDeliverable, reopen state), and ~40 handlers. Renders a single `<DashboardLayout …/>` (:1276-1362) with everything threaded as props.

**Shell: `src/components/layout/DashboardLayout.tsx` (1591 lines)** — `AppHeader` (top nav) + `AnimatePresence` switch on `mainView` (`type MainView`, :146). Views: `home`→`WorkflowCatalog`, `library`→`LibraryPage`, `history`→`WorkflowHistory`, `settings`→`AccountSettings`, `analytics`→`AnalyticsPage`, `saved-workflows`→`SavedWorkflowsPage`, `input`→`IdeaInputPage`, **`execution`→THE RUN SCREEN**. `AppHeader.tsx` nav = Home / Library / Catalogue + profile menu (Settings/Analytics/History) — all `onNavigate` = `mainView` switches, no router.

**EXECUTION view = 2-panel flex** (`DashboardLayout.tsx:1439-1576`, page bg inline `#f5f5f0` at :1221/:1447):
- **LEFT column** (340–360px, `:1455-1509`):
  - `AgentProgressPanel` (`src/components/workflow/AgentProgressPanel.tsx`, 411 ln) — live agent cards (`AgentCard`, expandable `<pre>` output on done, :163), header progress bar, **Stop** button (:248), **inline Revise composer** (textarea+Send+⌘↵, :299-376), "Suggested next steps" chain buttons (:377-397), `TokenUsageSummary`.
  - `WaveTreePanel` (`src/components/workflow/WaveTreePanel.tsx`, 140 ln) — wave/subagent tree from `wave_*`/`subagent_*` events; empty state "No waves running."
- **RIGHT column** (flex-1, `:1512-1574`) — **single-slot conditional**, exactly one of:
  1. `PlanningOverlay` (planner working, no agents yet) — `DashboardLayout.tsx:156-227`
  2. `ReviewGatePanel` (human gate active)
  3. `QuestionnairePanel` (clarify active)
  4. `PreviewPanel` (default)

**Tabbed surface: `src/components/preview/PreviewPanel.tsx` (900 lines)** — `TAB_CONFIG` (`:300-305`) = **Preview / Files / Thinking / Audit** (this is today's tab set; the new design's "Steps" ≈ re-skinned "Thinking").
- **Preview tab** (`:705-740`): generic-primary dispatch table `FIRST_PARTY_RENDERERS` (`:574-591`) keyed on structural `renderType` → `UserStoryPreview` / `AppBuilderIDEPreview` / `PPTPreview` / `PrototypePreview`; fallback `GenericDeliverablePreview` (`:166-233`) dispatches on **declared mimetype**: `text/html`→**sandboxed iframe** `sandbox="allow-scripts"` (`:181-186`), `text/markdown`→`MarkdownPreview`, `application/zip`→bundle IDE, else download card. `DegradedRunAffordance` (`:319-390`, exported/shared with history) for terminal-empty failed/degraded/cancelled runs.
- Header carries `LiveVersionChip` (`:631`) "v{n} ▾" dropdown + read-only older-version viewing + `ReadOnlyVersionBanner` (revision-family, `src/components/preview/LiveVersionChip.tsx`).
- **Files tab**→`FilesTab`, **Thinking tab**→`AgentThinkingTab`, **Audit tab**→`AuditTab`.

**Navigation between runs / history** — reopen via `handleSelectWorkflowRun` (`page.tsx:1123`) → `getWorkflow` → routes persisted `output` into the render slots + sets `reopenedRunStatus`/`reopenedFailedAgents`. Revision family: `RevisionFamilyView` (`src/components/history/WorkflowHistory.tsx` + `history/RevisionFamilyView.tsx`, grouped `v1..vN` timeline) and the live `LiveVersionChip`.

**Second, parallel run experience — `/handoff/[token]`** (`src/components/handoff/`, 1924 ln total): `HandoffWorkflow` (367) composes `HandoffAgentPanel` + `HandoffPreviewPanel` + `IntegrationsCard` + `DiffView` + `ReportViews`, with its OWN `useHandoffPipelineState` + `useWebSocket`. A cleaner, self-contained run template — worth referencing for the reskin. Older composer at `/workflow` = `WorkflowView` + `AgentLibrary`.

---

## 3. EVENT PIPELINE

**Single WS endpoint `/ws/chat`** (`src/lib/env.ts:38-46`, same-origin `wss://<host>/ws/chat` in prod). JWT passed in `Sec-WebSocket-Protocol` subprotocol (`useWebSocket.ts:104`), not URL.

**`src/hooks/useWebSocket.ts` (210 ln)** — connection mgmt: exponential backoff reconnect with **no retry limit**, cap 30s (`:168`); 20s client-side ping keepalive (`:115-121`); JWT-expired close code `4001` → `clearToken()`+redirect `/login` (`:149`); drops `pipeline_heartbeat`/`pong` (`:130`); one `onMessage` callback (`:132`); reconnect survives 2–6h runs.

**Dispatch: `dashboard/page.tsx` `handleWebSocketMessage` (`:256-789`)** — **top-of-handler dedup by `event_id`** (`shouldApplyEvent`, `:276`) + max-seen `seq` cursor (`lastSeqRef`, `:283`) for durable reconnect replay. Routing:
- `wave_*`/`subagent_*` → local `setWaveGroups` (`:292-365`).
- pipeline/agent/planner/tool/task events → `handlePipelineMsgRef` → `useWorkflow.handlePipelineMessage` (`:374-530`).
- `questionnaire*`/`review_gate_*`/`step`/`title_update`/`error`/`stream`/`complete` → local `switch` (`:532-788`).

**`src/hooks/useWorkflow.ts` (798 ln) `handlePipelineMessage` (`:168-798`)** — the reducer over `PipelineRunState`. Notable: `agent_start` resets per-run accumulators (FIX-039, `:242-263`); `agent_thinking` accumulates `thinkingText` (`:284`); **`agent_chunk` appends raw string to `agent.output`** (`:304` — plain token append, NOT markdown, NOT a live chat bubble); `agent_complete` folds token/cost; terminal handlers `pipeline_complete`/`_failed`/`_cancelled`/`_reconnected`; plus `agent_input`, `tool_call`/`tool_result`, `hook_run`, `planner_*`, `gate_*`, `task_progress`, `validator_result`.

**Streaming-text rendering — KEY FINDING:** there is **no live token-by-token markdown chat rendering today.** `agent_chunk` accumulates into a `<pre>` surface (`AgentProgressPanel.tsx:163`) shown only when the agent is done/expanded; the LIVE surface is `agent_thinking` → `thinkingText` with a blinking `▌` cursor (`AgentThinkingTab.tsx:544-547`). `react-markdown` renders in exactly two places: `MarkdownPreview.tsx` (deliverable) and `MessageBubble.tsx` (dead chat). Type contract: `StreamMessage` union (`src/types/index.ts:37-52`), `PipelineRunState` (`:537-573`).

**Outbound WS messages** (all over `/ws/chat`): `run_pipeline` (`useWorkflow.ts:107`), `run_revision` (`DashboardLayout.tsx:503`), `submit_questionnaire` (`useWorkflow.ts:132`), `approve_review` (approve/reject/redo, `page.tsx:1339/1342/1349`), `cancel_pipeline` (`DashboardLayout.tsx:1191/1472`), `reconnect_pipeline{after_seq}` (`DashboardLayout.tsx:646`), `user_message` (legacy refinement chat, `page.tsx:994/1046`).

**Reconnect** — `DashboardLayout.tsx:629-658` re-sends `reconnect_pipeline` with `after_seq` on WS reconnect; `sessionStorage.active_pipeline_run_id` survives tab close (`useWorkflow.ts:217`).

---

## 4. EXISTING CHAT-LIKE UI

**Dead chat kit — `src/components/chat/*` is 100% UNMOUNTED.** Only the `ChatMode` *type* escapes it (imported at `dashboard/page.tsx:13`, `DashboardLayout.tsx:30`). `ChatPanel` is never rendered; `DashboardLayout` receives `messages`/`streamingContent`/`isStreaming`/`onSendMessage` props but never renders a chat. Yet the kit is feature-complete: `ChatPanel.tsx` does auto-scroll (`:68-70`), streaming-to-last-bubble, `TypingIndicator`, `react-markdown` bodies (`MessageBubble.tsx:17,321`), blinking `streaming-cursor` (`:321`), edit/regenerate/copy/TTS, collapsible `<thinking>` blocks, `ArtifactCard`, and a mode dropdown. `ChatInput.tsx`: auto-grow textarea, Send, Enter-to-send/Shift+Enter, mode menu (`ChatMode = default|thinking|deep_research|web_search|quiz`, `:19`), **working voice input** (`useSpeechRecognition`, `:50`), and a **FAKE "Add Files" affordance** — a "📎 File uploads coming soon" toast, no `<input type=file>`, no paste, no drop (`ChatInput.tsx:114-121,184-193`). `Sidebar`/`ChatSessionItem` (thread history) are also **fully dead** (zero real importers).

**Live "talk-back" surfaces (the real conversational UI), ranked by reuse fit for a chat composer:**
1. **Revise composer** — `AgentProgressPanel.tsx:299-376` (textarea + Send + ⌘↵ + focus-on-open + clear-after-send) and its twin `WorkflowHistory.tsx:586-641`; slim single-line variant `PrototypePreview.tsx:635-659`. Sends either `run_revision` WS (`DashboardLayout.tsx:501-509`) or a new `*_revision` pipeline whose message wraps the instruction in a `=== REVISION REQUEST ===` delimited blob (`:517/:525/:537/:555/:569`) + `source_workflow_run_id`.
2. **`ReviewGatePanel.tsx` (454 ln)** — human gate: Preview/Edit toggle, edit textarea (`:385`), **redo-with-instructions free-text box** (`:417-440`), one-action `submitted` latch. All map to one WS `approve_review`, discriminated `approved:true` + `edited_content` / `approved:false` / `action:"redo"`+`instructions` (`page.tsx:1338-1350`). `redoable` server flag gates the Redo control.
3. **`QuestionnairePanel.tsx` (552 ln)** — clarify wizard: single/multi/hybrid/short_text questions, "Use recommended", per-question skip, global freeform textarea (`:239-245`). `onSubmitAnswers` → `responses:[{question_id,answer}]` (freeform as `question_id:"freeform"`) → WS `submit_questionnaire{pipeline_run_id, responses, skip_clarification}` (`useWorkflow.ts:130-140`).

**Message-bubble / conversation rendering that IS live:** `ClarificationsCard.tsx` (Q + green `✓ {answer}` per round, timeline card) and `StartingPointCard.tsx` (run input / revision request, `parseRunInput`-driven variants) — both mounted **inside `AgentThinkingTab`** (`AgentThinkingTab.tsx:618-664`). `TweaksPanel` is client-only CSS/HTML tweaking (no run channel). `WorkflowView` idea box is a pre-run launcher, not talk-back.

---

## 5. UPLOADS

- **Chat upload = fake stub** (`ChatInput.tsx:114-121,184-193`).
- **Real attach pattern (reuse target for FILES):** `IdeaInputPage.tsx:536-598` — hidden **multi-file `<input type=file>`** `accept=".pdf,.doc,.docx,.pptx,.txt,.md,.json,.csv"`, text via `FileReader.readAsText` (`:554-563`), binary via backend `extractFileText` (`:564-585`), removable chips (`:511-530`), sliced to `ATTACH_MAX_CHARS=450000` (`src/lib/constants.ts:7`). Duplicated in `app/workflow/{ppt,prototype}/templates/page.tsx`. Extracted text is **inlined into the prompt**, not a true file upload.
- **Only multipart client:** `src/lib/api.ts:879-908` `extractFileText(token, file)` → `POST /api/files/extract-text` (`FormData`). No other file/image/avatar endpoints exist.
- **Absent entirely:** drag-and-drop for files (all `onDrop` handlers are agent-reordering: `WorkflowView.tsx:418-421`, `AgentsPopup.tsx:1876-1879`), clipboard paste-image (no `onPaste`), image/`accept="image/*"` inputs, `readAsDataURL`/base64. **Images are 100% greenfield.** `ChatMessage` type (`types/index.ts:27-35`) has **no attachments field** — needs extension.
- **Downloads (separate):** `pptxgenjs` (`lib/exporters/pptExporter.ts`), **JSZip lazy-loaded from CDN** `https://cdnjs.cloudflare.com/…/jszip.min.js` (`FilesTab.tsx:443` — note CSP), server `POST /api/runs/export-pptx`, and `Blob`+`createObjectURL` across `FilesTab`/`PPTPreview`/`PreviewPanel`/exporters.

---

## 6. THEMING / RESKIN READINESS — **verdict: SCATTERED (hard)**

- **Tokens are near-unused.** The primary token set (`--background`/`--surface`/`--accent`/`--foreground`/`--border`/`--card`/`--sidebar-*`) is referenced by components **zero times** — consumed only inside `globals.css` (`body`, `.markdown-content`). Only the **legacy `--theme-*` aliases** are used, by ~9 chat/sidebar/workflow files (34 `var()` refs across 17 files). Changing tokens reskins **~10-15% of the surface** (page bg, body text, markdown, a few chat components). `globals.css` itself hardcodes hex in `.markdown-content` (`:159-260`).
- **Hardcoded surface:** ~**3,162** named color utilities (`bg/text/border-{gray,blue,slate…}-NNN`) across **76 files**, +**635** white/black, +**400** arbitrary `[#hex]` in 50 files, +**554** raw `#rrggbb` in 60 files, +**131** legacy `grey/navy`. Recurring brand literals: **navy `#1B2A4A`** + light **`#E8EDF5`** + cream page bg **`#f5f5f0`** (all inline, not tokens). Blue accent is scattered (`blue-600`×16, `blue-500`×17, `#2563eb`×3, `var(--accent)` in components = 0).
- **Worst offenders (by hardcoded-color count):** `AgentsPopup.tsx` 222, `AgentThinkingTab.tsx` 128, `AccountSettings.tsx` 117, `PrototypePipelineView.tsx` 108, `LibraryPage.tsx` 105, `WorkflowHistory.tsx` 91, `AnalyticsPage.tsx` 85, `QuestionnairePanel.tsx` 82, `admin/page.tsx` 77.
- **Fonts: CENTRALIZED** (2-file change: `layout.tsx:2-20` + `globals.css:9-11`).
- **Dark mode: NONE** (`globals.css:49` `color-scheme:light`; 0 `dark:` variants). Light-only — no dark work to preserve.
- **No shared primitives:** `src/components/ui/` = only `CompletionToast`/`ErrorBoundary`/`NotificationPanel`. No `Button`/`Card`/`Badge`/`Tabs`/`Input` — **339 raw `<button>` across 67 files**. `src/lib/design-system-colors.ts` / `design-system-preview.ts` are product features (parse user `DESIGN.md`), NOT app theming; `styles/theme.ts` is dead.
- **Net:** black/beige/one-blue = a whole-tree find-replace + build missing primitives + route the palette through `globals.css` tokens so the *next* reskin is centralized. The beige (`#f5f5f0`) is already the page bg but as inline literals.

---

## 7. TEST SURFACE

- **`e2e/tests/ts-a … ts-z2`** (`playwright.config.ts`): `mocked` project (default, ~123 green) intercepts REST (`fixtures/mockApi.ts`, `page.route`) **and** WS (`fixtures/mockWs.ts`, `page.routeWebSocket` — **NOT** `window.WebSocket` monkey-patch). Frames wrapped `{type, data:{…, event_id, seq}}` (`mockWs.ts:125`); driver helpers `start`/`agentStart`/`agentChunk`/`agentThinking`/`complete`/`failed`/`cancelled`/`questionnaireReady`/`reviewGateReady`/`wave*`/`reconnected`/`drop`/`expireJwt`.
- **Run-screen specs:** `ts-j` streaming (Thinking tab), `ts-k` wave-tree, `ts-m` questionnaire (clarify), `ts-n` review-gate, `ts-o` deliverables, `ts-p` iframe-security, `ts-q` terminal-states, `ts-r` cancel, `ts-s` reconnect, `ts-t` history, `ts-u` revisions, `ts-z` catalog, `ts-z2` saved-workflows.
- **Selectors:** `getByRole` **241**, `getByText` **183**, `getByPlaceholder` **17**, `getByTestId` **0**, real `data-testid` **0** (all 19 `data-testid` hits in `src` are inside the `src/data/skills.ts` sample-code blob). 70 `.locator()`: resilient anchors (`iframe[title="Deliverable/Slide Deck/Prototype Preview"]`, `button[title="Copy"/"Add agent"/"Remove agent"]`, `input[type=file]`) vs **brittle CSS/color assertions** (`toHaveClass(/bg-\[#1B2A4A\]/)` in `ts-m`/`ts-c`, `bg-gray-900` in `ts-f`, `textarea.font-mono` in `ts-n`, `div.bg-[#1B2A4A]` in `ts-i`, `.overflow-x-auto`/`.cursor-pointer` in `ts-t`).
- **Reskin resilience: ~90% stays green** because selection is role + visible text. Break-risks to respect: (a) keep ARIA roles + accessible names; (b) keep badge/banner **text strings** (RUNNING/DONE/ERROR/LIVE, "Pipeline stopped", "No waves running.", "Output will appear here"); (c) keep `title=` attrs (3 iframe titles, Copy, Add/Remove agent); (d) **don't change `#1B2A4A` / `bg-gray-900` / `font-mono` classes that `toHaveClass` asserts on**. `ts-t` history has the most structural coupling (highest risk).
- **Streaming gotcha:** `agent_chunk` is **not rendered live today** (`FIXTURE-CONTRACT.md:91`); the live surface is `agent_thinking`+`▌`. A live-streaming chat panel needs a **new `mockWs` driver contract** and (recommended) the **first real `data-testid`s** in the codebase.

---

## 8. GAP ANALYSIS — embedding streaming chat + image/file upload + thread history

**What exists to build on**
- **Streaming half is ~80% done but unmounted.** The in-repo `ChatPanel`/`ChatInput`/`MessageBubble` already implement streaming bubbles, markdown, blinking cursor, typing indicator, auto-scroll, voice, and a mode dropdown — in **raw Tailwind + motion**. `dashboard/page.tsx` already computes and threads `messages`/`streamingContent`/`isStreaming`/`onSendMessage` into `DashboardLayout`; they're simply never rendered. Wiring `ChatPanel` into the execution surface is low-effort for the messages axis.
- **WS + wire channels exist:** legacy `user_message` outbound (+ `stream`/`complete`/`error`/`title_update` inbound already handled), plus `submit_questionnaire` (resume paused run) and `approve_review` w/ `instructions` (gate reply) as talk-back templates.
- **File upload:** reuse `extractFileText` (FormData) + the `IdeaInputPage` attach pattern (text FileReader / binary backend-extract / chips / `ATTACH_MAX_CHARS`).

**What's missing**
- **Live token-by-token chat rendering:** today `agent_chunk` → `<pre>`, not a markdown bubble. Need to route a stream into `ChatPanel` bubbles + a new mockWs driver.
- **Image upload:** fully greenfield (no image input, no `readAsDataURL`, no image endpoint, no paste, no drag-drop) — likely needs a new backend endpoint.
- **Attachments data model:** `ChatMessage` has no attachments/images field — type extension required.
- **Thread history:** thread selection lives in `dashboard.onSelectChat`/`getChat` + `/api/chats`; `Sidebar`/`ChatSessionItem` components exist but are **dead** — re-mount or rebuild.
- **Persistent multi-turn composer:** the closest live composer (Revise textarea) is one-shot.

**Where it slots in the component tree** — the execution right-panel (`DashboardLayout.tsx:1512-1574`) is a single-slot conditional. Options: (a) a 5th tab in `PreviewPanel.TAB_CONFIG`; (b) a **new persistent column / bottom drawer** in the execution flex layout (matches the new design's "chat alongside Preview/Steps/Files/Audit tabs" intent better than a tab); (c) augment the `AgentProgressPanel` left column.

**Mapping to the new design (Preview / Steps / Files / Audit + drill-down Steps + black/beige/one-blue):**
- **Preview** = existing PreviewPanel Preview tab (keep).
- **Steps** = **re-skin + rename the existing Thinking tab** — `AgentThinkingTab.tsx` is *already* a drill-down timeline (StartingPointCard → PlannerCard → ClarificationsCard → per-agent expandable cards with tool calls, context sources, validation, output), with `PrototypePipelineView` for prototype. ⚠️ `StartingPointCard` + `ClarificationsCard` are mounted *inside* AgentThinkingTab (`:618-664`) — re-home them if you rename/replace the tab. `ValidatorIssuePanel` is exported/tested but **orphaned (never mounted)** — free to adopt into Steps or Audit.
- **Files** = `FilesTab` (keep, re-skin). **Audit** = `AuditTab` (keep, re-skin; fetches `GET /api/runs/{id}/hook-runs` for history).
- **Palette:** beige page bg already `#f5f5f0`; the pervasive navy `#1B2A4A`/`#E8EDF5` pair and `#2563eb` blue are the literals to tokenize into black/beige/one-blue.

**Copy-in chat kits (Vercel AI Elements / assistant-ui):** Tailwind v4 is present ✓, but there is **no shadcn/Radix scaffolding** (those kits assume Radix primitives + `cn()`/tailwind-merge + CVA). So they are a **partial mismatch** — adopting one means adding a new shadcn/Radix dependency surface first. Since the existing in-repo `ChatPanel` already implements most of AI-Elements' feature set in raw Tailwind + motion, **adapting the in-repo kit is lower-friction** than importing a shadcn-based kit.

**Key run-screen files (absolute):** `src/app/dashboard/page.tsx`, `src/components/layout/DashboardLayout.tsx`, `src/components/preview/PreviewPanel.tsx`, `src/components/results/AgentThinkingTab.tsx`, `src/components/results/{FilesTab,AuditTab,ClarificationsCard,StartingPointCard,ValidatorIssuePanel}.tsx`, `src/components/workflow/{AgentProgressPanel,WaveTreePanel}.tsx`, `src/components/preview/{QuestionnairePanel,ReviewGatePanel,LiveVersionChip}.tsx`, `src/hooks/{useWebSocket,useWorkflow}.ts`, `src/components/chat/*` (dead kit), `src/styles/globals.css`, `src/lib/{api,env,constants}.ts`.
