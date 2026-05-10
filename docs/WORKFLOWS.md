# Flowin — End-to-End Workflow Catalog

> **Status:** Frontend mapped (Phase 1). Backend traces appended per workflow in *Section 4* (Phase 2).
>
> **Source of truth:** `frontend/src/**` and `backend/app/**` on branch `agent-pipeline-execution`.
>
> **Conventions used in this document**
> - **`file:line`** references are absolute paths from repo root (omitting `frontend/src/` and `backend/app/` prefixes when context is clear).
> - **WS** = WebSocket message type strings (e.g. `agent_chunk`).
> - **Storage** = `localStorage` unless noted otherwise.
> - The frontend speaks to a single REST base (`NEXT_PUBLIC_API_URL`, default `http://localhost:8000`) and a single WebSocket (`NEXT_PUBLIC_WS_URL`, default `ws://localhost:8000/ws/chat`). All authenticated requests carry `Authorization: Bearer <jwt>`; the WS includes `?token=<jwt>` as a query parameter.

---

## 1. Workflow inventory (one row per workflow)

64 distinct user-facing workflows were identified across the frontend. Each row includes its primary trigger, the network surface it touches, what it persists, and where it goes next. Detailed sections follow in §3.

| # | Workflow | Route / Trigger | UI controls (key) | Fetches (HTTP) | WS sent | WS received | Storage | Navigates to |
|---|---|---|---|---|---|---|---|---|
| W01 | Root redirect to login | GET `/` (server) | none | none | none | none | none | `/login` |
| W02 | Register | `/register` form submit | email, password, "Create Account" btn | POST `/api/auth/register` | none | none | write `auth_token` | `/dashboard` |
| W03 | Login | `/login` form submit | email, password, "Sign In" btn | POST `/api/auth/login` | none | none | write `auth_token` | `/dashboard` |
| W04 | Auto-auth check on protected pages | `/dashboard` mount | none | (reads token from storage) | none | none | read `auth_token` | `/login` if no token |
| W05 | JWT-expiry forced logout | WS close code `4001` | none | none | none | (close 4001) | clear `auth_token` | `/login` (hard reload) |
| W06 | User logout | Header dropdown "Log out" / Sidebar "Log out" btn | LogOut buttons | none | none | none | clear `auth_token` | `/login` |
| W07 | Change password | Settings → "Change Password" btn | 3 password fields, Eye toggles, submit btn | POST `/api/auth/change-password` | none | none | none | stay |
| W08 | Load dashboard | `/dashboard` mount (after auth) | none | GET `/api/workflows?limit=50` | (opens WS connection) | none | read `auth_token` | stay (Home view) |
| W09 | Header navigation | "Library" / "Workflow History" / "Account Settings" / "Home" btns | header nav links | (none directly; pages fetch on mount) | none | none | none | switches `mainView` |
| W10 | Toggle / collapse sidebar | "Close sidebar" btn | PanelLeftClose icon btn | none | none | none | none | stay |
| W11 | Click "New Project" (sidebar) | "+ New Project" btn | Plus icon btn | (parent decides) | none | none | none | Home view |
| W12 | Select feature card | Click any of 6 cards in CreationHub | feature card btn (click + Enter/Space) | none | none | none | sets `workflowType` state | IdeaInputPage |
| W13 | Search/filter chats in sidebar | Sidebar search input | text input | none | none | none | none | filters list |
| W14 | Select workflow run from sidebar | Click ChatSessionItem | run card btn | (may fetch workflow detail) | none | none | none | Preview view |
| W15 | Open Library page | Header "Library" btn | nav btn | none | none | none | none | Library view |
| W16 | Search & filter library agents | Library search & category btns | search text, 7 cat btns | none | none | none | none | filters list |
| W17 | Open Account Settings | Header dropdown → "Account Settings" | dropdown btn | GET `/api/auth/me` (on mount) | none | none | read token | Settings view |
| W18 | View workflow run list | Header dropdown → "Workflow History" | nav btn, type filter `<select>` | GET `/api/workflows?limit=100` | none | none | read token | History list view |
| W19 | View workflow run detail | Click run card in history | run card btn | GET `/api/workflows/{id}` (only if `output` not preloaded) | none | none | read token | Run detail view |
| W20 | Delete workflow run | Trash icon on run card → confirmation modal | trash btn, Cancel/Delete in modal | DELETE `/api/workflows/{id}` | none | none | read token | stay (item removed) |
| W21 | Submit idea text | IdeaInputPage textarea + Run | textarea, Run btn (Ctrl+Enter) | none | `run_pipeline` | (subscribes for pipeline_*) | none | Workflow "running" view |
| W22 | Attach files (context) | Paperclip btn | hidden file input + chips list | none (filenames embedded as text only — see open issue) | none | none | none | stay |
| W23 | Voice input | Mic btn | Mic toggle | none (browser API) | none | none | none | populates textarea |
| W24 | Open Agent Library modal | "Agent Library" / "Browse Library" / "Add Agent" btns | open modal | none | none | none | none | modal |
| W25 | Open Agents popup | "View & Manage Agents" btn | opens AgentsPopup modal | none | none | none | none | modal |
| W26 | Add agent to pipeline | "+Add" btn in library row | add btn | none | none | none | none | local state |
| W27 | Reorder agents | Drag handle on optional agents | GripVertical drag/drop | none | none | none | none | local state |
| W28 | Remove agent from pipeline | Trash btn on optional agent | trash btn (only optionals) | none | none | none | none | local state |
| W29 | Open Skill Manager modal | BookMarked btn on idle agent node | modal opens | GET `/api/agents/skills/{agentId}` | none | none | read token | modal |
| W30 | Edit & save skill | Textarea + "Save Skill" btn | textarea, save btn | POST `/api/agents/skills` body `{agent_id, content}` | none | none | read token | stay |
| W31 | Upload skill file | "Upload" btn (`.md`,`.txt`) | file input | (read into textarea client-side) | none | none | none | stay |
| W32 | Delete skill | Trash btn in skill manager | delete btn | DELETE `/api/agents/skills/{agentId}` | none | none | read token | stay |
| W33 | Run pipeline | "Run Workflow" btn | submit btn | none | `run_pipeline` `{pipeline_type, message, agent_ids?}` | (downstream pipeline_*) | none | step="running" |
| W34 | Receive `pipeline_start` | server-driven | none | none | none | `pipeline_start` `{agents[], pipeline_type}` | none | initializes graph |
| W35 | Receive agent stream events | server-driven | none | none | none | `agent_start`, `agent_thinking`, `agent_chunk`, `agent_complete` | none | updates AgentNode |
| W36 | Receive `agent_error` | server-driven | none | none | none | `agent_error` `{agent_id, error}` | none | shows error badge |
| W37 | Receive `pipeline_complete` | server-driven | none | none | none | `pipeline_complete` `{total_duration}` | none | step="complete" |
| W38 | Cancel running pipeline | "Stop Pipeline" btn | red stop btn | none | `cancel_pipeline` | `pipeline_cancelled` | none | "Pipeline Stopped" banner |
| W39 | View pipeline complete | Auto on complete | "View Results" / "Run Another" btns | none | none | none | none | results / reset |
| W40 | Run another pipeline | "Run Another Pipeline" btn | btn | none | none | none | resets `pipelineState` | step="select" |
| W41 | Chain to next pipeline | Pipeline selector list | option btns | none | `run_pipeline` (next type) | (downstream pipeline_*) | none | step="running" |
| W42 | Send chat message (text) | ChatInput Send btn / Enter | textarea, Send btn | (none directly; goes via WS) | server-defined chat msg type (sent via `useWebSocket.send`) | `stream`, `complete`, etc. | none | stay |
| W43 | Send chat message with mode | Mode menu (default/thinking/deep_research/web_search/quiz) | Plus btn → mode popup | (via WS) | chat msg with mode tag | `stream`, etc. | none | stay |
| W44 | Receive streaming AI reply | server-driven | none | none | none | `stream`, `complete`, `error`, `phase_start`, `phase_end` | none | updates last bubble |
| W45 | Receive `title_update` | server-driven | none | none | none | `title_update` | none | updates session title |
| W46 | Typing indicator | Auto when streaming + last msg not assistant | shimmer bars | none | none | (driven by stream state) | none | stay |
| W47 | Show process steps | server-driven | expandable step rows | none | none | `step` (and embedded in messages) | none | stay |
| W48 | Show error with retry | After server `error` msg | red box, "Try Again" btn (if recoverable) | (none directly) | retry resends last user msg | `error` | none | stay |
| W49 | Empty state suggestion chips | First-load chat panel | 4 chip btns | none | (chip click → send msg via WS) | none | none | stay |
| W50 | Copy assistant message | Copy btn (hover action bar) | Copy btn → Check feedback | none | none | none | clipboard | stay |
| W51 | Edit user message → re-send | Pencil btn → textarea → Save & Send | edit textarea, save btn | none | (resend via WS) | none | none | stay |
| W52 | Regenerate assistant message | RefreshCw btn | regenerate btn | none | (resend last user msg) | `stream`, etc. | none | stay |
| W53 | Text-to-speech playback | Volume2 btn on assistant msg | toggle btn (Web Speech Synthesis API) | none | none | none | none | stay |
| W54 | Open artifact card preview | Click ArtifactCard tile | full-width clickable card | none | none | none | none | opens PreviewPanel |
| W55 | Preview user stories | Preview panel "Preview" tab | UserStoryPreview component | none | none | none | none | renders |
| W56 | Preview PPT | Preview panel "Preview" tab | PPTPreview iframe (sandboxed HTML) | none | none | none | none | renders |
| W57 | Preview prototype | Preview panel "Preview" tab | PrototypePreview iframe (sandboxed HTML) | none | none | none | none | renders |
| W58 | Preview markdown | Preview panel "Preview" tab | MarkdownPreview component | none | none | none | none | renders |
| W59 | Download user stories `.md` | ArtifactCard / FilesTab download btns | btn | none (client export) | none | none | blob URL (revoked) | file download |
| W60 | Download PPT as `.pptx` | ArtifactCard download for `ppt` | btn | none (uses `pptxgenjs`) | none | none | none | file download |
| W61 | Download PPT as `.html` | FilesTab download for ppt | btn | none | none | none | blob URL | file download |
| W62 | Download prototype | ArtifactCard / FilesTab download | btn | none | none | none | blob URL | file download |
| W63 | Download all (Files tab) | "Download All" btn | btn (staggered 100ms) | none | none | none | blob URLs | bulk download |
| W64 | Answer questionnaire MCQs | QuestionnairePanel | radio btns + free-text + Run/Skip btns | none | (answers sent via WS) | `questionnaire` (incoming) | none | resumes pipeline |

---

## 2. Cross-cutting reference

### 2.1. WebSocket message vocabulary (frontend perspective)

| Type | Direction | Payload (observed) | Sent / handled at |
|---|---|---|---|
| `run_pipeline` | client → server | `{pipeline_type, message, agent_ids?}` | `useWorkflow.ts:47-58` |
| `cancel_pipeline` | client → server | `{}` | DashboardLayout (cancel handler) |
| (chat send) | client → server | implementation TBD by backend trace | ChatInput → ChatPanel `onSendMessage` → `useWebSocket.send()` |
| `pipeline_start` | server → client | `{agents:[{id,name,role,icon,order}], pipeline_type}` | `useWorkflow.ts:121-128` |
| `agent_start` | server → client | `{agent_id}` | `useWorkflow.ts:130-143` |
| `agent_thinking` | server → client | `{agent_id, thinking}` | `useWorkflow.ts:146-160` |
| `agent_chunk` | server → client | `{agent_id, chunk}` | `useWorkflow.ts:162-180` |
| `agent_complete` | server → client | `{agent_id, output}` | `useWorkflow.ts:182-206` |
| `agent_error` | server → client | `{agent_id, error}` | `useWorkflow.ts:208-226` |
| `pipeline_complete` | server → client | `{total_duration}` | `useWorkflow.ts:229-239` |
| `pipeline_cancelled` | server → client | `{}` | dashboard handler |
| `stream` | server → client | text chunk | ChatPanel handler |
| `complete` | server → client | end-of-stream | ChatPanel |
| `error` | server → client | `{message}` (also `[code:…][recoverable:true|false]` markers) | ChatPanel |
| `phase_start` / `phase_end` | server → client | metadata | ChatPanel |
| `title_update` | server → client | `{title}` | ChatPanel |
| `step` | server → client | ProcessStep `{id,label,detail?,status,icon?,timestamp?}` | ChatPanel `processSteps` |
| `questionnaire` | server → client | `{questions:[{id,text,options[]}]}` | QuestionnairePanel |

WS connection lifecycle (`useWebSocket.ts:33-178`):
- URL: `${ENV.WS_URL}?token=${encodeURIComponent(token)}`
- Reconnect: exponential `1s × 2^retryCount`, max 5 retries → `failed` state
- JWT expired close code `4001` → `clearToken()` + hard `window.location.href = "/login"`

### 2.2. HTTP API surface

| Function | Method | Path | Auth | Body | Returns |
|---|---|---|---|---|---|
| `register` | POST | `/api/auth/register` | no | `{email,password}` | `{token, user}` |
| `login` | POST | `/api/auth/login` | no | `{email,password}` | `{token, user}` |
| `getMe` | GET | `/api/auth/me` | yes | – | `User` |
| `changePassword` | POST | `/api/auth/change-password` | yes | `{current_password,new_password}` | `{message}` |
| `createChat` | POST | `/api/chats` | yes | `{title?}` | `ChatSession` |
| `getChats` | GET | `/api/chats` | yes | – | `ChatSession[]` |
| `getChat` | GET | `/api/chats/{id}` | yes | – | `{id,title,last_activity,created_at,messages[],final_output?}` |
| `addMessage` | PUT | `/api/chats/{id}/messages` | yes | `{content,role?}` | `ChatMessage` |
| `deleteChat` | DELETE | `/api/chats/{id}` | yes | – | `204` |
| `createWorkflow` | POST | `/api/workflows` | yes | `{type,input,title?}` | `WorkflowRun` |
| `getWorkflows` | GET | `/api/workflows?type=&limit=` | yes | – | `WorkflowRun[]` |
| `getWorkflow` | GET | `/api/workflows/{id}` | yes | – | `WorkflowRun` |
| `deleteWorkflow` | DELETE | `/api/workflows/{id}` | yes | – | `204` |
| (skill load) | GET | `/api/agents/skills/{agentId}` | yes | – | `{content}` |
| (skill save) | POST | `/api/agents/skills` | yes | `{agent_id,content}` | `{}` |
| (skill delete) | DELETE | `/api/agents/skills/{agentId}` | yes | – | `204` |

All HTTP requests go through the `request<T>()` helper in `lib/api.ts:36-74`, which:
- Prefixes `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`)
- Sets `Content-Type: application/json` and `Authorization: Bearer <token>` (when token argument is supplied)
- Throws `ApiError(status, detail)` on non-2xx

### 2.3. Persistent client-side storage

| Key | Type | Lifetime | Written | Read |
|---|---|---|---|---|
| `auth_token` | localStorage | Until logout / token expiry / `clearToken()` | `setToken()` after login/register (`api.ts:27-29`) | `getToken()` everywhere |

No cookies, no sessionStorage, no IndexedDB. Object URLs used for downloads are revoked immediately after click (`storyExporter.ts`, `prototypeExporter.ts`).

### 2.4. Environment variables

| Name | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base URL for REST |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000/ws/chat` | WebSocket endpoint |

### 2.5. Voice & speech

| Hook | API | Usage |
|---|---|---|
| `useSpeechRecognition` | `window.SpeechRecognition` / `webkit*` | continuous=true, lang="en-US"; populates ChatInput / IdeaInputPage textarea |
| `useTextToSpeech` | `window.speechSynthesis` | Strips Markdown; voice preference list (Google US English → Samantha → Alex → Microsoft); rate/pitch/volume = 1.0 |

### 2.6. Client-side parsers & exporters

| File | Symbol | Purpose |
|---|---|---|
| `lib/parsers/streamParser.ts` | `parseStreamMessage` | Validates incoming WS JSON shape |
| `lib/parsers/userStoryParser.ts` | `parseUserStoryMarkdown`, `formatUserStoryMarkdown` | Epic / story / acceptance-criteria parser (BDD aware) |
| `lib/parsers/pptParser.ts` | `parsePPTSlideData` | JSON-from-fence + truncation repair → `SlideData` |
| `lib/exporters/storyExporter.ts` | `exportUserStories` | Browser blob download `.md` |
| `lib/exporters/pptExporter.ts` | `exportToPptx` | Builds `.pptx` via `pptxgenjs` (7 slide kinds: title/content/chart/table/comparison/two-column/quote) |
| `lib/exporters/prototypeExporter.ts` | `exportPrototype` | JSON pretty-print blob download |

---

## 3. Detailed frontend workflow notes

> Each entry below adds the file:line specifics that didn't fit in the inventory table. Workflows are grouped by domain.

### 3.1 Auth (W01 – W07)

- **W01 — Root redirect** (`app/page.tsx:3-4`). `redirect("/login")` (server component). No state.
- **W02 — Register** (`app/register/page.tsx:10`). Validates ≥8-char password, password match, surfaces 409 (dup email) and 422 (per-field) ApiErrors. Stores `auth_token`, then `router.replace("/dashboard")`.
- **W03 — Login** (`app/login/page.tsx:10`). 401 → "Invalid email or password.". Other errors render `err.detail`.
- **W04 — Auto-auth check** (`app/dashboard/page.tsx:18,49-51,64-69`). Reads `auth_token`; if absent `router.replace("/login")`; otherwise `getWorkflows({limit:50})` is best-effort (catch silenced).
- **W05 — JWT-expiry forced logout** (`hooks/useWebSocket.ts:113-121`). On `event.code === 4001` → `clearToken()` and `window.location.href = "/login"`. No refresh-token mechanism exists.
- **W06 — User logout** (`AppHeader.tsx:127-133`, `Sidebar.tsx:196-206`, dashboard `handleLogout` at `dashboard/page.tsx:550-551`). Pure client cleanup; **no server logout endpoint is called.**
- **W07 — Change password** (`AccountSettings.tsx:11-171`). Eye toggle on each input; success/error toast; requires `current_password` to be sent.

### 3.2 Dashboard, navigation & sidebar (W08 – W17)

- **W08 — Load dashboard.** On mount, dashboard reads token (W04), pre-fetches workflows for the sidebar, opens WebSocket via `useWebSocket({url, token, onMessage:handleWebSocketMessage})` (`dashboard/page.tsx:294-298`).
- **W09 — Header navigation.** `AppHeader` "Library", "Workflow History", "Account Settings" set `mainView` in `DashboardLayout` (line ~239-242). Blocked while pipeline running.
- **W10 — Toggle sidebar.** `Sidebar.tsx:98-105` `onCollapse` callback handled by parent.
- **W11 — New Project.** `Sidebar.tsx:110-118` `onOpenWorkflow` → returns to Home / CreationHub.
- **W12 — Select feature card.** 6 cards in `home/CreationHub.tsx:98-166`, types: `ppt | user_stories | prototype | app_builder | reverse_engineer | custom`. Disabled if `isPipelineRunning`.
- **W13 — Sidebar search** (`Sidebar.tsx:78-135`). Filters by `run.title || run.input.slice(0,40)` (lower-cased).
- **W14 — Select sidebar run.** Calls `onSelectRun` → page-level `handleSelectWorkflowRun` (loads output if not already loaded).
- **W15 — Library page** (`library/LibraryPage.tsx:29-129`). Static catalog from `AgentLibraryData.ts`.
- **W16 — Library search & filter.** 7 categories + free-text. Sorted by `pipeline_type` then `order`.
- **W17 — Account Settings.** Loads email via `getMe()` (`AccountSettings.tsx:25-30`), silent on failure.

### 3.3 Workflow history (W18 – W20)

- **W18 list.** `getWorkflows({limit:100})` on mount; in-memory type filter via `<select>`.
- **W19 detail.** Tabs Preview / Files. Lazy-fetches detail (`getWorkflow(id)`) only if `output` is missing. Preview component picked by `selectedRun.type`.
- **W20 delete.** Two-step confirm modal → `deleteWorkflow(id)`; errors silently swallowed.

### 3.4 Workflow setup & composition (W21 – W32)

- **W21 idea text.** Validation: non-empty + ≥1 agent. Ctrl+Enter to submit.
- **W22 file attachment** (`IdeaInputPage.tsx:163-181, 214-225`). **Open issue:** files are displayed as chips and their *names* are appended to the message text; the **binary content is never uploaded** — backend only ever sees the filename string.
- **W23 voice input** — see §2.5.
- **W24 agent library modal**, **W25 agents popup** — interplay: AgentLibrary can be nested inside AgentsPopup (`AgentsPopup.tsx:245-252`).
- **W26 add**: respects per-pipeline-type max (most types max-2, custom max-8). `HIDDEN_FROM_CUSTOM` set in `AgentLibrary.tsx:37-40`.
- **W27 reorder**: `LOCKED_AGENT_IDS` cannot be dragged, required cannot drop on locked.
- **W28 remove**: only optional roles get a trash icon.
- **W29 skill load**: `SkillManager.tsx:48-62`.
- **W30 skill save**: `SkillManager.tsx:75-93`.
- **W31 skill upload**: file chosen client-side, content piped into the textarea (no upload).
- **W32 skill delete**: `SkillManager.tsx:103-117`.

### 3.5 Pipeline execution (W33 – W41)

- **W33 run pipeline** (`useWorkflow.ts:33-61`). Sends `run_pipeline` with `{pipeline_type, message, agent_ids?}`.
- **W34 receive pipeline_start** initialises agent array, `currentAgentIndex = 0`.
- **W35 receive agent stream events** — duration computed from `agentStartTimesRef[id]`. Output appended chunk by chunk; final `agent_complete` sets `output` and increments `completedCount`.
- **W36 agent_error** sets `status="error"`, marks `isRunning=false`.
- **W37 pipeline_complete** sets `isRunning=false`, stores `total_duration`.
- **W38 cancel.** Sends `cancel_pipeline`; UI shows "Pipeline Stopped" banner; partial outputs preserved.
- **W39 view complete.** "View Results" / "Run Another" buttons.
- **W40 reset** clears `pipelineState` to `INITIAL_STATE`.
- **W41 chain.** `AgentProgressPanel.tsx:191-198` — picks next pipeline, fires another `run_pipeline` (uses output of previous as context — exact mechanism is on backend).

### 3.6 Chat & streaming (W42 – W49)

- **W42 send text** (`ChatInput.tsx:67-73`). Empty/streaming guard. Auto-resizes textarea.
- **W43 mode-tagged send.** Mode: `default | thinking | deep_research | web_search | quiz`. Mode badge shown above input; cleared after send. **Backend handling of modes is part of Phase 2 trace.**
- **W44 receive streaming reply.** `MessageBubble` renders partial content with blinking cursor.
- **W45 title_update** updates session title in sidebar.
- **W46 typing indicator** (`TypingIndicator.tsx`). Shows when `isStreaming && !lastIsAssistant`.
- **W47 process steps** (`ProcessSteps.tsx`). Inline status badges; expandable detail.
- **W48 error with retry** (`ErrorMessage.tsx:17-61`). `recoverable=true` shows "Try Again" → resends last user msg.
- **W49 empty state**. 4 fixed suggestion chips (Brainstorm / Architecture / User stories / Presentation).

### 3.7 Message interactions (W50 – W53)

- **W50 copy** uses `navigator.clipboard`; tick feedback for 2 s.
- **W51 edit user msg** sets `isEditing`; Enter submits, Escape cancels.
- **W52 regenerate.** `onRegenerate` → page-level handler resends last user message.
- **W53 TTS** — see §2.5. Strips Markdown before utterance.

### 3.8 Artifacts, previews & downloads (W54 – W63)

- **W54 open artifact** (`ArtifactCard.tsx:107-177`). Card click triggers `onOpenPreview`; PreviewPanel renders type-specific preview.
- **W55–W58 previews.** Source content lives in `message.artifact.content` (chat artifacts) or in `WorkflowRun.output` / `agentOutputs` (history). Sandbox attributes — PPT iframe allows `allow-scripts allow-same-origin allow-downloads allow-popups`; prototype iframe is more restrictive.
- **W59 .md download** uses Blob `text/markdown`.
- **W60 .pptx download** runs `parsePPTSlideData(content)` → `exportToPptx()` (pptxgenjs). 7 slide kinds, `LAYOUT_WIDE`.
- **W61 .html download** — Files tab uses `downloadBlob(content, name+".html", "text/html")`.
- **W62 prototype download.** `exportPrototype()` pretty-prints valid JSON or falls back to raw.
- **W63 download all** iterates files with 100 ms staggers.

### 3.9 Questionnaire (W64)

- `QuestionnairePanel.tsx`. Single-select MCQs; optional free-text; "Run Pipeline" sends `selectedAnswers + freeformInput` back to caller; "Skip" continues without answers. **Backend handling of `questionnaire` event is part of Phase 2 trace.**

---

## 4. Backend traces per workflow (Phase 2)

> **The remainder of this document is populated by Phase 2 backend-tracing agents.** Each cluster of related workflows is paired with a deep dive that follows the request path from the API/WS handler through services, agents, LLM calls and storage.

### B1 — Auth backend trace (W01–W07)

**Stack:** FastAPI + SQLAlchemy 2.0 + python-jose (JWT, HS256) + passlib[bcrypt]. DB defaults to SQLite (`sqlite:///./dev.db` in `core/config.py:17`); Postgres in production via `DATABASE_URL`.

| WF | Handler `file:line` | Pydantic schema | DB ops | Notes |
|---|---|---|---|---|
| W02 register | `api/auth.py:16-45` | `RegisterRequest` (`schemas.py:12-16`, `password min_length=8`) | `SELECT users WHERE email=?` then `INSERT` | bcrypt hash via `hash_password` (`security.py:23-24`); on dup email returns 409 |
| W03 login | `api/auth.py:48-76` | `LoginRequest` (`schemas.py:19-23`) | `SELECT users WHERE email=?` | `bcrypt.checkpw`; on bad email/password returns 401 (generic) |
| W05 WS-expiry close 4001 | `api/websocket.py:72-83` (connect), `:154-159` (per-message re-validation) | n/a | `SELECT users WHERE id=?` | Token re-validated **on every message**, not only at connect. `4001` close code emitted on missing/expired token |
| W07 change password | `api/auth.py:91-120` | `ChangePasswordRequest` (`auth.py:85-88`, server-side `>=8` check) | `SELECT user` (via `get_current_user`) → `UPDATE password_hash` | **Existing JWTs remain valid** — no version field, no force-logout |

**JWT structure** (`core/security.py:41-72`): `{sub: user.id, exp: now + 24h, iat: now}` signed with HS256 `SECRET_KEY` (default `"dev-secret-key-change-in-production"`). Expiry configurable via `ACCESS_TOKEN_EXPIRE_HOURS` (default 24h, prod template suggests 12h).

**Logout reality (W06).** No `/api/auth/logout` endpoint exists; the front-end does `clearToken()` only. Tokens remain server-trusted until natural expiry. There is no blacklist or token-version mechanism.

**Identified threat-model gaps**

| Gap | Risk | Mitigation suggestion |
|---|---|---|
| Default `SECRET_KEY` literal `"dev-secret-key-change-in-production"` | Predictable HS256 keys → token forgery if deployed without env override | Boot-time check that `SECRET_KEY` is non-default in production |
| No server-side logout / no JWT revocation | Stolen token usable until exp | Token blacklist (Redis) on logout + on password change |
| Password change does **not** invalidate existing tokens | Attacker session survives password rotation | Embed `password_version` in JWT; bump on change |
| No rate limiting on `/login` and `/register` | Credential stuffing / spam | Per-IP and per-email throttle (e.g. `slowapi`) |
| No email verification | Spam / account squatting | Email confirm via OTP or magic link |
| Token transmitted as WS `?token=` query param | Logged in access logs / browser history | Send via subprotocol header or first WS message |
| HS256 (symmetric) | If key leaks, all tokens are forgeable | Switch to RS256 with private key in Secrets Manager |
| `localStorage` token storage (front-end) | Vulnerable to XSS exfiltration | HttpOnly + SameSite=strict cookie |
| No CSRF tokens | If front-end XSS-compromised, attacker can change password | SameSite cookies + explicit CSRF token |

---

### B2 — WebSocket protocol & event routing

**Endpoint:** `ws://<host>/ws/chat?token=<jwt>` (`api/websocket.py:55`). Auth: query-string JWT; bad/expired token → close `4001`. Internal error → close `1011` (`websocket.py:323`).

**Connection state.** Per-connection: a fresh `SessionLocal()` is created and closed for each handler call (`websocket.py:79,89,193`); a `WorkflowRun` row is inserted at `pipeline_start` (`websocket.py:359-372`); **no asyncio.Task references are stored**, which has consequences for cancellation. Multiple parallel pipelines per user are allowed at the message level (sequential within a single connection, parallel across connections / browser tabs).

**Inbound message catalog**

| `type` | Payload | Handler | Emits |
|---|---|---|---|
| `run_pipeline` | `{pipeline_type, message, agent_ids?: list[str]}` | `websocket.py:118-124` → `_handle_pipeline_execution` | `pipeline_start`, `agent_*`, `pipeline_complete`/`error` |
| `cancel_pipeline` | `{}` | `websocket.py:127-135` | `pipeline_cancelled` (acknowledgment only — see below) |
| `user_message` | `{type, content, chat_session_id, mode?}` | `websocket.py:144-246` | `title_update`, `phase_*`, `stream`, `complete`, `error` |
| `generate_questions` | `{pipeline_type, message}` | `websocket.py:138-142` → `_handle_questionnaire` (`:537-593`) | `questionnaire` |

**Outbound message catalog** (verified emit lines)

| `type` | Emitted at | Payload |
|---|---|---|
| `pipeline_start` | `pipeline.py:39-49` | `{pipeline_type, agent_count, agents:[{id,name,role,icon,order}]}` |
| `agent_start` | `pipeline.py:59-67` | `{agent_id,name,role,icon,index,total}` |
| `agent_thinking` | `pipeline.py:87-93,117` | `{agent_id, thinking}` |
| `agent_chunk` | `pipeline.py:100-106` | `{agent_id, chunk}` (one per LangChain token) |
| `agent_complete` | `pipeline.py:139-149` | `{agent_id,name,duration,output_length,index,total}` |
| `agent_error` | `pipeline.py:153-160`, `:167-175` | `{agent_id, error, recoverable, duration?}` |
| `pipeline_complete` | `pipeline.py:188-197` | `{pipeline_type, total_duration, agents_completed, agents_total, final_output}` |
| `pipeline_cancelled` | `websocket.py:129-134` | `{message:"…cancelled by user"}` |
| `phase_start` / `phase_end` | `orchestrator.py:312/331/334/349/365/389` | `{phase, name?}` |
| `stream` / `complete` | `orchestrator.py:318/340/371/395-400` | `{chunk}` / `{data: FinalOutputModel}` |
| `error` | `websocket.py:248-283` | `{error, code, recoverable}` — codes: `api_key_missing` (`recoverable:false`), `timeout`, `rate_limit`, `connection_error`, `auth_error`, `pipeline_error`, `internal_error` |
| `title_update` | `websocket.py:219-224` | `{chat_session_id, title}` |
| `questionnaire` | `websocket.py:562-567` | `{questions:[{id,question,options}]}` |

> **Wire-format note.** All frames are JSON with the wrapper `{type, chunk?, section?, data?}` (`schemas.StreamMessageModel`). The `chunk` field carries streaming text; `section` tags the phase or pipeline; `data` carries everything else.
>
> **Frontend ↔ backend mismatch:** the front-end documents a `step` message type for `ProcessSteps`, but **no backend code emits `step`** today — it appears to be a planned feature. The front-end `[code:…][recoverable:…]` markers are also absent on the backend; `code` and `recoverable` are sent as separate JSON fields.

**Streaming model.** LangChain `ChatBedrockConverse.astream()` yields one chunk per LLM token (`base.py:82-95`); each chunk becomes one `agent_chunk`/`stream` JSON frame. **No batching, no flow control.**

**Cancellation reality.** `cancel_pipeline` only acknowledges to the client; **the executor task is not cancelled.** No task reference is stored, so `task.cancel()` cannot be called. The pipeline keeps running and burning LLM tokens until natural completion (or until the WS closes — at which point `send_json` calls fail silently but the orchestrator still completes).

---

### B3 — Chats / Sessions / Messages backend trace

**Schema (`models/chat.py:12-49`)**

```
chat_sessions (id PK, user_id FK→users.id, title default="New Chat",
               last_activity, created_at, final_output Text NULL JSON)
messages (id PK, chat_session_id FK→chat_sessions.id, role, content Text,
          created_at)
```
No `ON DELETE CASCADE`; deletion of a chat manually nulls children (`api/chats.py:155`).

**REST endpoints (`api/chats.py`)**

| Method+Path | Body | DB ops | Notes |
|---|---|---|---|
| POST `/api/chats` | `{title?}` | `INSERT chat_sessions` | Default title "New Chat" |
| GET `/api/chats` | – | `SELECT * FROM chat_sessions WHERE user_id=? ORDER BY last_activity DESC` | per-user only |
| GET `/api/chats/{id}` | – | session + messages eager loaded | 404 cross-user |
| PUT `/api/chats/{id}/messages` | `{content, role?}` | `INSERT messages` + `UPDATE chat_sessions.last_activity` | Default `role="user"` |
| DELETE `/api/chats/{id}` | – | `DELETE messages WHERE chat_session_id=?` then `DELETE chat_sessions` | Manual cascade |

**`final_output` semantics.** `chat_sessions.final_output` stores the JSON-serialized `FinalOutputModel` (10 keys: `auth, realtime, dashboard, discovery, requirements, user_stories, ppt, prototype, ui_design, ui_preview` — `schemas.py:80-92`). Written by the WS handler when the orchestrator yields `{type:"complete"}` (`websocket.py:312-313`).

**`title_update` flow.** First user message in a session with `title in ("New Chat", "")` triggers a side-effect call to the title-generator agent; result is persisted to `chat_sessions.title` and broadcast as `title_update` (`websocket.py:189-226`).

**W42→W44 lifecycle (send → receive streaming).**
1. Client opens WS with `?token=`; the `useWorkflow`/`ChatPanel` calls `useWebSocket.send(JSON.stringify({type:"user_message", content, chat_session_id, mode?}))`.
2. Server validates JWT (per-message, `websocket.py:154-159`); validates session ownership (`:161-178`).
3. **User message persisted before LLM call** (`INSERT messages role='user'`, `UPDATE last_activity`, `:180-193`).
4. If first message of session, fire-and-forget title-generator → `title_update` event.
5. `AgentOrchestrator.astream_execute` yields `phase_*` and `stream` chunks, relayed verbatim.
6. Server collects `assistant_chunks: list[str]`; on `complete` event, persists assistant message **at the end** with `<!--steps:JSON-->...` prefix (`websocket.py:285-316`).
7. `chat_sessions.last_activity` updated; `final_output` written if any.

**Artifact materialisation for chat W08.** Artifacts live inside `final_output` (`ppt`, `prototype`, etc.); they are not separate rows. Front-end re-renders from JSON each time the chat is reloaded.

---

### B4 — Workflow-runs backend trace

**Schema (`models/workflow.py:12-33`)**

```
workflow_runs (id PK, user_id FK→users.id, title, type, status default="running",
               input Text, output Text NULL, agent_outputs Text NULL JSON,
               agent_count Integer, duration Float NULL, error Text NULL,
               created_at, completed_at NULL)
```
No CASCADE on user FK; no `chat_session_id` link (despite WS handler having both contexts).

**REST endpoints (`api/workflows.py`)**

| Method+Path | Notes |
|---|---|
| POST `/api/workflows` | Validates `type ∈ {user_stories, ppt, prototype}` (note: no `app_builder` / `reverse_engineer` / `custom`); creates row with `status="running"`. **Currently unused by the frontend** — the UI runs everything via the WS `run_pipeline` path. Likely dead code. |
| GET `/api/workflows?limit&offset&type&status_filter` | Filtered by `user_id`; ordered `created_at DESC` |
| GET `/api/workflows/{id}` | 404 cross-user |
| PATCH `/api/workflows/{id}` | Update `status`/`output`/`duration`/`error`; auto-sets `completed_at` on terminal status. **Also unused** — WS handler updates the row directly via SQLAlchemy. |
| DELETE `/api/workflows/{id}` | per-user only |

**Authoritative writer.** The WS handler `_handle_pipeline_execution` (`websocket.py:328-535`) is where rows are actually created and finalised:
- **insert** (`:357-372`): `status="running"`
- **success** (`:491-505`): `status="completed"`, `output=final_output`, `agent_outputs=json.dumps(collector)`, `duration`, `completed_at`
- **failure** (`:475-489`): `status="failed"`, `error=str(exc)`, `duration`, `completed_at`
- **cancellation does NOT update status** — pipelines that the user cancels remain `running` forever in the DB.

**Authorization.** All HTTP endpoints filter by `user_id == current_user.id`; the WS pipeline persists `user_id = user.id` from the validated JWT. No cross-user access path observed.

**Open issues.** (a) `agent_count` is hard-coded at create time and never reconciled; (b) cancelled runs never reach a terminal status; (c) chat-session linkage is not persisted, so deleting a chat orphans related runs.

---

### B5 — Pipeline orchestration backend trace

**Pipeline registry (`agents/registry.py`)**

| `pipeline_type` | Default agents (in order) | Source |
|---|---|---|
| `user_stories` | domain-analyst → epic-architect → story-estimator → nfr-specialist → backlog-reviewer → backlog-compiler | `registry.py:28-237` |
| `ppt` | ppt-content-strategist → ppt-slide-architect → ppt-code-generator → ppt-assembler | `registry.py:254-304` |
| `prototype` | requirements-analyst → html-prototype-builder → prototype-polisher → prototype-finalizer | `registry.py:311-493` |
| `app_builder` | material-analyzer → app-code-generator → app-infra-generator → app-assembler | `registry.py:501-723` |
| `reverse_engineer` | repo-scanner → deep-analyzer → modernization-planner → documentation-generator | `registry.py:731-975` |
| (custom utility) | 8 misc agents (market-research, swot, roadmap, security-auditor, test-case-generator, perf-optimizer, documentation, report-generator) | `agents/custom_agents.py` |

Total **30 agents**. Front-end's `LIBRARY_AGENTS` list matches the backend registry exactly.

**Custom agent injection.** `run_pipeline.agent_ids` is honoured by `_handle_pipeline_execution` (`websocket.py:419-422`): unknown IDs are *silently filtered*, ordered as supplied. There is no per-user persistence of custom agents.

**Orchestrator entry points (`agents/orchestrator.py`)**
- `execute(user_message, chat_session_id?) -> FinalOutputModel` (`:213-215`) — non-streaming.
- `astream_execute(user_message, chat_session_id?, mode='default', mode_prompt='') -> AsyncGenerator[dict]` (`:286-289`) — used by the WS path. Phases are sequential: 0 (Discovery) → 1 (Requirements) → 2 (routing, implicit) → 3-7 (conditional, e.g. user_stories / ppt / prototype / ui_design / ui_preview).

**`PipelineExecutor.execute()` (`agents/pipeline.py:51-178`)**
1. Emit `pipeline_start`.
2. For each agent in order:
   - Build context message from prior outputs. Truncation rules (`pipeline.py:213-257`):
     - PPT: agent 4 (assembler) sees only agent 3's JS; agents 2/3 see prior outputs truncated to 8K/12K chars.
     - Prototype polisher/finalizer: only immediate predecessor.
     - Other pipelines: all prior outputs, each clipped to 8K chars.
   - `BaseAgent(system_prompt=skill+system_prompt, max_tokens=agent.max_tokens)`. Skill prepended at `pipeline.py:72-74`.
   - `agent_thinking` → token loop (`agent.astream(context_message)`) emitting `agent_chunk` per LangChain `.content`. Up to **2 retries** with 2 s sleep on `RemoteProtocolError`/`ReadTimeout`/chunked-encoding errors (`pipeline.py:95-122`).
   - On success: store output in `self.context[agent.id]`; emit `agent_complete`.
   - On `AgentConfigurationError` (missing API key) → non-recoverable, halts pipeline.
   - On other exceptions → `agent_error{recoverable:true}`, store placeholder, continue.
3. Emit `pipeline_complete` with last agent's output as `final_output`.

**Cancellation gap.** Confirmed in B2: no task reference is stored, so `cancel_pipeline` is purely an UI signal. The executor never receives `asyncio.CancelledError`.

**Chaining (W41).** **Not implemented server-side.** The front-end "chain to next pipeline" simply emits a fresh `run_pipeline` after the previous completes; there is no orchestrator-level composition.

**Questionnaire (W64).** Triggered by client `generate_questions`. The `QUESTIONNAIRE_AGENT` (`registry.py:1033-1065`) returns a JSON-formatted list of 4 MCQs. **The user's answers are NOT sent back** to influence the run — the frontend just shows them as guidance. This is a documented integration gap.

**PPT pipeline detail (`agents/ppt_pipeline.py`).** Strict palette: white BG (`#FFFFFF`), black text (`#1A1A1A`), navy accent (`#1B2A4A`). 10–12 slides, 16:9. Output is a **self-contained HTML page** with embedded `generatePresentation()` JS using `pptxgenjs@3.12.0` from CDN. The user clicks "Download PPTX" *inside the iframe* to trigger client-side `pres.writeFile(...)`.

---

### B6 — Agents catalog & skills backend trace

**Catalog.** Static — entirely defined in `agents/registry.py` (`AgentDefinition` dataclasses, `:7-22`). No DB storage of agents, no per-user variants, no dynamic discovery. The `discovery.py` module is an *agent for Phase 0*, not a discovery mechanism (`agents/discovery.py:1-41`).

**Skills system**

| Endpoint (REST `api/agents.py`) | Behaviour |
|---|---|
| GET `/api/skills` (`:111-123`) | Lists all skills (`agent_id`, first 200 chars). |
| GET `/api/skills/{agent_id}` (`:126-135`) | Returns full content, empty string if none. |
| POST `/api/skills` body `{agent_id, content}` (`:138-145`) | Writes `backend/skills/{agent_id}/SKILL.md`. |
| DELETE `/api/skills/{agent_id}` (`:148-155`) | `unlink()` the file. |

**Storage.** Plain-text Markdown files at `backend/skills/{agent_id}/SKILL.md`. Built-in fallbacks (`DEFAULT_SKILLS` dict, `skills.py:19-140`). The PPT pipeline gets bonus skills loaded from `backend/pptx/skill.md` and `backend/pptx/pptxgenjs.md` (`skills.py:158-196`). Skills are *prepended to the agent's system prompt* at run time (`pipeline.py:72-74`). No DB, no validation, no versioning.

**Authorisation gap (high severity).** **Skills are global.** Any authenticated user can GET, POST, or DELETE any agent's skill — see `api/agents.py:138-155`. User A can poison the `domain-analyst` skill that User B will then run with. **Recommendation:** namespace skills under `backend/skills/{user_id}/{agent_id}/SKILL.md` and add `user_id` filtering to all skill endpoints, *or* protect skill mutation behind an admin role. Until fixed, skills must be treated as untrusted in production.

**Frontend exposure.** The `agent_ids` field on `run_pipeline` is supported server-side, but the front-end never sends it (the AgentsPopup mutation is local-state only). Either make the front-end persist orderings or remove the unused field.

---

### B7 — Per-agent LLM profiles

**Provider:** AWS Bedrock via `langchain_aws.ChatBedrockConverse`. **Env vars read:** `BEDROCK_MODEL_ID` and `AWS_REGION` (see `app/core/config.py`). Missing either → `AgentConfigurationError` (`base.py`). Auth is via the boto3 default credential chain — instance-profile IAM role in prod, `~/.aws/credentials` / `AWS_PROFILE` locally.

**Default model:** `eu.anthropic.claude-haiku-4-5-20251001-v1:0` (the EU cross-region inference profile; see `app/core/config.py`).

**Per-agent profiles** (token caps and observed I/O magnitudes; all use the default Haiku model and stream token-by-token):

| Agent (id) | `max_tokens` | Typical I/O | Notes |
|---|---|---|---|
| domain-analyst | 4 000 | 0.3K in / 1-2K out | first pass on user_stories pipeline |
| epic-architect | 16 000 | 1K in / 3-8K out | |
| story-estimator | 16 000 | 4K in / 3-5K out | |
| nfr-specialist | 16 000 | 5K in / 2-4K out | |
| backlog-reviewer | 4 000 | 4K in / 1-2K out | |
| backlog-compiler | 32 000 | 12K in / 15-30K out | **dominant cost on user_stories pipeline** |
| ppt-content-strategist | 8 000 | 0.5K in / 2-5K out | |
| ppt-slide-architect | 12 000 | 6K in / 4-10K out | |
| ppt-code-generator | 32 000 | 10K in / 25-32K out | **dominant cost on PPT pipeline**; consumes full `backend/pptx/pptxgenjs.md` skill (~13 KB) |
| ppt-assembler | 32 000 | 28K in / 15-32K out | uses *Common Pitfalls* slice of `pptxgenjs.md` |
| requirements-analyst → prototype-finalizer (4-agent prototype) | 32 000 each | up to 30-40K out per agent | |
| app-builder / reverse-engineer agents | 32 000 each | similar | |
| Custom utility agents (8) | 4 000–16 000 | small | |

**Approximate cost per pipeline run (Haiku 4.5 list price):** user_stories ~$0.04–0.10; PPT ~$0.05–0.12; prototype/app_builder/reverse_engineer ~$0.10–0.30 (HTML/code-heavy). **Concurrency consideration:** at 10 parallel runs, peak working memory in Python is ~100 MB per pipeline (output buffers + LangChain frames).

**Other behaviours.** No temperature override (LangChain default ~0.7 — *non-deterministic*; for JSON-output agents, consider setting `temperature=0`). No retry on Bedrock `ThrottlingException`; only network-level retry (B5). No token counting / usage tracking inside the app (Bedrock emits `InputTokenCount` / `OutputTokenCount` to CloudWatch — see `docs/SIMPLE_AWS_DEPLOYMENT.md` §10.4).

---

### B8 — Services & artifact persistence

**Server-side PPTX export?** `services/pptx_export.py` is **a placeholder** — single docstring, no implementation. PPTX rendering is **entirely client-side** in the iframe (front-end uses `pptxgenjs` npm package, served from CDN inside the assembler's HTML). The backend never produces a `.pptx` file.

**`backend/pptx/` directory.** Two files:
- `pptxgenjs.md` (~13 KB) — full PptxGenJS API reference, included in the `ppt-code-generator` system prompt.
- `SKILL.md` (~9 KB) — design constraints (palette, slide counts) included in `ppt-content-strategist` and `ppt-slide-architect` prompts.

These are **read-only references**, not generated artifacts.

**Artifact persistence.** All artifacts live in `Text` columns:

| Source | Column | Format | Typical size |
|---|---|---|---|
| user_stories pipeline | `workflow_runs.output` | Markdown | 5–15 KB |
| ppt pipeline | `workflow_runs.output` | Self-contained HTML w/ embedded JS | 30–80 KB |
| prototype pipeline | `workflow_runs.output` | Self-contained HTML | 40–120 KB |
| app_builder / reverse_engineer | `workflow_runs.output` | Markdown / structured | up to 100 KB+ |
| All pipelines | `workflow_runs.agent_outputs` | JSON array of per-agent records | 5–50 KB per agent |
| Chat completion | `chat_sessions.final_output` | JSON dump of `FinalOutputModel` | up to ~200 KB |

A typical 12-agent run can persist ~700 KB; **at ~1 500 active users with steady use, expect ~1 GB on disk**, growing linearly.

**File I/O surface (entire backend).** Reads only from `backend/skills/` and `backend/pptx/`; writes only to `backend/skills/{agent_id}/SKILL.md`. **No tempfiles, no static-files serving, no upload endpoints.** Whole artifact pipeline is in-memory + DB.

**Implications for AWS sizing.** The footprint is dominated by *Python+LangChain memory per pipeline* (~100 MB) and *DB row size* (sub-MB). Disk I/O is negligible. There is no S3-required asset (yet); however, putting artifacts into S3 with signed URLs would reduce DB bloat at scale.

---

## 5. Cross-cutting integration gaps & action items

The phase-2 traces surfaced these issues that will inform deployment hardening:

1. **Skills are globally writable** (B6) — must namespace per user or restrict via admin role.
2. **Cancel-pipeline doesn't actually cancel** (B2/B5) — pipeline keeps consuming Bedrock tokens after the user clicks Stop. Will affect AWS cost.
3. **No JWT revocation, no logout endpoint, no password-change session invalidation** (B1) — needs Redis-backed token blacklist.
4. **Cancelled runs never reach a terminal state** (B4) — DB will accumulate phantom `running` rows.
5. **Frontend `step` events and `[code:…]` markers are documented but not emitted** (B2) — front-end sees no process steps unless the backend code is added.
6. **File attachments (W22) are filename-only; binary content never reaches the backend** (Phase-1 finding). Either implement upload or remove the chip UI.
7. **Questionnaire answers (W64) are never sent back** (B5) — entire questionnaire is purely advisory.
8. **PATCH `/api/workflows/{id}` and POST `/api/workflows`** are unused by the frontend (B4) — likely dead code.
9. **Default `SECRET_KEY` is a hard-coded literal** (B1) — must be enforced non-default at boot.
10. **WS query-param token** (B1) — leaks in logs; consider subprotocol header.

