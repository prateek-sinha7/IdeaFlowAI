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

All file/line references in this section were re-verified after the
`WorkflowOrchestrator` migration (websocket.py now imports
`app.agents.orchestrator_v2.WorkflowOrchestrator`; `PipelineExecutor` /
`pipeline.py` no longer exist) and after the addition of the server-side
`POST /api/workflows/export-pptx` endpoint backed by Node + pptxgenjs.

### 2.1. WebSocket message vocabulary (frontend perspective)

The chat endpoint lives at `/ws/chat` (`backend/app/api/websocket.py:92`).
Authentication: the JWT is sent as the entry `bearer.<jwt>` in the
`Sec-WebSocket-Protocol` header (the second arg to `new WebSocket(url, [...])`),
with `flowin.v1` as the protocol-selector subprotocol the server echoes back
(`useWebSocket.ts:98`, `websocket.py:122-160`). A transitional `?token=<jwt>`
query parameter is still accepted but logs a deprecation warning
(`websocket.py:133-140`). Close code `4001` means missing/invalid/expired
or revoked JWT (`websocket.py:114`).

Two distinct streaming pipelines emit WS messages:

1. The **chat path** (client sends `user_message`) is routed to
   `AgentOrchestrator.astream_execute` (`backend/app/agents/orchestrator.py:293`),
   which emits `phase_start` / `stream` / `phase_end` / `complete` / `error`.
2. The **pipeline path** (client sends `run_pipeline`) is routed to
   `WorkflowOrchestrator.execute` (`backend/app/agents/orchestrator_v2.py:227`),
   which emits `pipeline_start` / `agent_start` / `agent_thinking` /
   `agent_chunk` / `agent_complete` / `agent_error` / `pipeline_complete`.

Every server-emitted message uses the envelope
`{type, chunk, section, data}` (assembled in `websocket.py:577-582` for the
pipeline path, and copied through verbatim in `websocket.py:373` for the chat
path).

#### Client → server

| Type | Payload | Sent from |
|---|---|---|
| `user_message` | `{type, content, chat_session_id, mode?}` | `app/dashboard/page.tsx:366-371` (default mode) and `:418-424` (with mode). Required fields validated at `websocket.py:271-278`. |
| `run_pipeline` | `{type, pipeline_type, message, agent_ids?}` | `hooks/useWorkflow.ts:47-58`. Server-side reject if a pipeline is already running (`websocket.py:216-227`). |
| `cancel_pipeline` | `{type}` | `components/layout/DashboardLayout.tsx:451`. Handled at `websocket.py:243-262`; cancels the in-flight `asyncio.Task` (`websocket.py:252`). |
| `generate_questions` | `{type, pipeline_type, message}` | `components/layout/DashboardLayout.tsx:205-209` (initial run) and `:243-247` (chain pipeline). Handled at `websocket.py:265-269` → `_handle_questionnaire`. |

#### Server → client

| Type | Source path | `data` payload | Frontend handler |
|---|---|---|---|
| `phase_start` | chat | `{phase, name}` | `app/dashboard/page.tsx:135` (no-op) |
| `stream` | chat | `null`; payload is on top-level `chunk` plus `section` | `app/dashboard/page.tsx:110-132` |
| `phase_end` | chat | `{phase}` | `app/dashboard/page.tsx:139` (no-op) |
| `complete` | chat | `FinalOutput` (see `types/index.ts:56-67`) | `app/dashboard/page.tsx:143-221` |
| `error` | both | `{error, code, recoverable, phase?}` | `app/dashboard/page.tsx:223-255` |
| `title_update` | chat | `{chat_session_id, title}` | `app/dashboard/page.tsx:257-263` |
| `step` | chat agents | `ProcessStep` (`{id,label,detail?,status,icon?,timestamp?}`) | `app/dashboard/page.tsx:283-300` |
| `pipeline_start` | pipeline | `{pipeline_type, agent_count, agents:[{id,name,role,icon,order}]}` (emitted at `orchestrator_v2.py:250-260`) | `hooks/useWorkflow.ts:97-128` |
| `agent_start` | pipeline | `{agent_id, name, role, icon, index, total}` (emitted at `orchestrator_v2.py:274-284`) | `hooks/useWorkflow.ts:130-144` |
| `agent_thinking` | pipeline | `{agent_id, thinking}` (emitted at `orchestrator_v2.py:303-309` and again on retry at `:352-358`) | `hooks/useWorkflow.ts:146-160` |
| `agent_chunk` | pipeline | `{agent_id, chunk}` (emitted at `orchestrator_v2.py:328-334`) | `hooks/useWorkflow.ts:162-180` |
| `agent_complete` | pipeline | `{agent_id, name, duration, output_length, index, total}` — note: the backend does **not** emit the agent's full `output` here, only its length (`orchestrator_v2.py:381-391`). The client's `(msg.output as string) || updated[agentIdx].output` (`useWorkflow.ts:184,196`) is therefore always the empty string and the displayed output is whatever accumulated from `agent_chunk` events. | `hooks/useWorkflow.ts:182-206` |
| `agent_error` | pipeline | `{agent_id, error, duration?, recoverable}` (emitted at `orchestrator_v2.py:399-402` for config errors, `:408-415` for runtime errors) | `hooks/useWorkflow.ts:208-227` |
| `pipeline_complete` | pipeline | `{pipeline_type, total_duration, agents_completed, agents_total, final_output}` (emitted at `orchestrator_v2.py:431-440`) | `hooks/useWorkflow.ts:229-239` then `app/dashboard/page.tsx:83-105` routes `final_output` to the correct preview tab |
| `pipeline_cancelled` | WS handler | `{message, agents_completed?, duration?}` (emitted at `websocket.py:633-642`); also a no-active-pipeline ack `{message: "No active pipeline"}` at `websocket.py:256-261` | No dedicated case in dashboard switch; pipeline state is reset via `onResetPipeline` after `websocketSend({type: "cancel_pipeline"})` in `DashboardLayout.tsx:449-454`. Frontend `StreamMessage` type lists `pipeline_cancelled` (`types/index.ts:36`). |
| `questionnaire` | WS handler | `{questions:[{id, question, options[]}]}` parsed from the questionnaire agent (`websocket.py:748-753`); empty `{questions: []}` on parse failure or no API key (`:756-770`) | `app/dashboard/page.tsx:276-281` |
| `workflow_title_update` | declared, not emitted | `{workflow_id, title}` | Listed in `types/index.ts:36` and handled at `app/dashboard/page.tsx:265-274`, but **no backend emitter exists** today. `[VERIFY: this looks like a planned event the backend hasn't been wired to send — searched `backend/` for the string and found zero hits.]` |

**Connection lifecycle** (`hooks/useWebSocket.ts:34-193`):
- Default URL: `ENV.WS_URL` (`useWebSocket.ts:29`), which is
  `ws://localhost:8000/ws/chat` unless `NEXT_PUBLIC_WS_URL` overrides it
  (`lib/env.ts:10`).
- Reconnect: exponential `1000ms × 2^retryCount`, capped at `MAX_RETRIES = 5`
  → `failed` state (`useWebSocket.ts:30-31, 145-159`).
- JWT-expired close code `4001` triggers `clearToken()` + hard
  `window.location.href = "/login"` (`useWebSocket.ts:32, 128-137`).
- Client subprotocol list: `[`bearer.${token}`, "flowin.v1"]` (`useWebSocket.ts:98`).

### 2.2. HTTP API surface

All routes are registered in `backend/app/main.py:124-129`. Frontend calls go
through `request<T>()` in `lib/api.ts:78-93`, which prepends `ENV.API_URL`
(default `http://localhost:8000`, see §2.4), sets
`Authorization: Bearer <token>` plus `Content-Type: application/json`, and
throws `ApiError(status, detail)` (`lib/api.ts:64-76`) on non-2xx.

| Method | Path | Auth | Body | Returns | Backend (`file:line`) | Frontend caller |
|---|---|---|---|---|---|---|
| POST | `/api/auth/register` | no | `{email, password}` | `{token, user}` (201) | `auth.py:24` | `lib/api.ts:104-115` |
| POST | `/api/auth/login` | no | `{email, password}` | `{token, user}` | `auth.py:56` | `lib/api.ts:117-128` |
| GET | `/api/auth/me` | yes | – | `User` | `auth.py:87` | `lib/api.ts:130-135` |
| POST | `/api/auth/logout` | yes (lenient) | – | `204` | `auth.py:93` | `lib/api.ts:47-60` (`logout()`; best-effort, swallows network errors) |
| POST | `/api/auth/change-password` | yes | `{current_password, new_password}` | `{message}` | `auth.py:152` | `lib/api.ts:352-370` |
| POST | `/api/chats` | yes | `{title?}` | `ChatSessionResponse` (201) | `chats.py:51` | `lib/api.ts:184-194` |
| GET | `/api/chats` | yes | – | `ChatSessionResponse[]` | `chats.py:74` | `lib/api.ts:196-202` |
| GET | `/api/chats/{chat_id}` | yes | – | `{id, title, last_activity, created_at, messages[], final_output?}` | `chats.py:92` | `lib/api.ts:204-212` |
| DELETE | `/api/chats/{chat_id}` | yes | – | `204` | `chats.py:132` | `lib/api.ts:227-243` |
| PUT | `/api/chats/{chat_id}/messages` | yes | `{content, role?}` | `MessageResponse` (201) | `chats.py:162` | `lib/api.ts:214-225` |
| GET | `/api/agents/pipelines/{pipeline_type}` | yes | – | `{pipeline_type, agents[], total_estimated_duration}` | `agents.py:67` | `[VERIFY: not invoked from `frontend/src/`; presumably called by an admin/diagnostic surface, or vestigial.]` |
| GET | `/api/agents/library` | yes | – | `{agents[], total_count, pipelines}` | `agents.py:99` | `[VERIFY: no `fetch(.../api/agents/library` in frontend; the `AgentLibrary` component appears to render a static or locally-derived list. Out-of-scope to fully trace.]` |
| GET | `/api/agents/skills` | yes | – | `{skills[], total_count}` (preview-only) | `agents.py:130` | not called from frontend |
| GET | `/api/agents/skills/{agent_id}` | yes | – | `{agent_id, content}` | `agents.py:151` | `components/workflow/SkillManager.tsx:47-49` |
| POST | `/api/agents/skills` | yes | `{agent_id, content}` (≤64 KB; 413 if larger; 400 on unknown `agent_id`) | `{status, agent_id, path}` | `agents.py:166` (size cap at `skills.py:25`, `MAX_SKILL_BYTES = 64 * 1024`) | `components/workflow/SkillManager.tsx:74-81` |
| DELETE | `/api/agents/skills/{agent_id}` | yes | – | `{status, agent_id}` (idempotent — `"deleted"` or `"not_found"`, never 404) | `agents.py:197` | `components/workflow/SkillManager.tsx:102-105` |
| POST | `/api/workflows` | yes | `{type, input, title?, agent_count?}` | `WorkflowRunResponse` (201) — 400 on unknown `type` | `workflows.py:61` | `lib/api.ts:291-303` |
| GET | `/api/workflows?type=&status_filter=&limit=&offset=` | yes | – | `WorkflowRunResponse[]` | `workflows.py:97` | `lib/api.ts:305-321`; also direct `fetch` calls in `components/preview/PPTPreview.tsx:39` and `components/results/FilesTab.tsx:146` |
| POST | `/api/workflows/export-pptx` | yes | `{js_code?, html?, workflow_id?, title?}` — at least one of `js_code` / `html` / `workflow_id` must let the server resolve PptxGenJS code, else 400 | binary `.pptx` (`application/vnd.openxmlformats-officedocument.presentationml.presentation`) with `Content-Disposition: attachment; filename="<title>.pptx"`; 500 on Node-side failure | `workflows.py:128-227`; implementation lives in `backend/app/services/pptx_export.py:40-179` which writes a temp Node script and spawns `node <script>` with a 30 s timeout (`pptx_export.py:157-160`) | `components/preview/PPTPreview.tsx:53-67` and `components/results/FilesTab.tsx:160-164` |
| GET | `/api/workflows/{workflow_id}` | yes | – | `WorkflowRunResponse` — 404 if not owned | `workflows.py:230` | `lib/api.ts:323-332` |
| PATCH | `/api/workflows/{workflow_id}` | yes | `{status?, output?, duration?, error?}` | `WorkflowRunResponse` | `workflows.py:254` | `[VERIFY: not invoked from `frontend/src/`; comment says "Used by the pipeline executor", but the live websocket pipeline path now writes directly via `db.commit()` rather than HTTP, so this route may be dead code.]` |
| DELETE | `/api/workflows/{workflow_id}` | yes | – | `204` | `workflows.py:296` | `lib/api.ts:334-350` |
| GET | `/health` | no | – | `{status, llm_provider, langsmith}` | `main.py:132` | not called from frontend |

Notes:
- CORS is configured in `main.py:115-121` to allow `http://localhost:3000`,
  `http://127.0.0.1:3000`, and `http://localhost:3001`.
- The `agent_outputs` field on `WorkflowRunResponse` arrives as a JSON
  *string*; the frontend parses it in `lib/api.ts:267-273`.

### 2.3. Persistent client-side storage

| Key | API | Purpose | Written | Read |
|---|---|---|---|---|
| `auth_token` | `localStorage` | JWT issued by the backend (`AuthResponse.token`) | `setToken()` in `lib/api.ts:27-29`; called after register/login in `lib/api.ts:113, 126`. | `getToken()` in `lib/api.ts:22-25`; also a direct `localStorage.getItem("auth_token")` debug log read in `hooks/useWebSocket.ts:178`. Cleared by `clearToken()` (`lib/api.ts:31-33`) on `logout()`, on WS 4001 (`hooks/useWebSocket.ts:130`), and inside `logout()` itself (`lib/api.ts:58`). |

A repo-wide grep for `localStorage`, `sessionStorage`, `indexedDB`, and
`IndexedDB` finds no other entries — no cookies are set by the frontend
either. Object URLs are created for browser-blob downloads
(`lib/exporters/storyExporter.ts:7-15`, `lib/exporters/prototypeExporter.ts:17-25`,
`lib/exporters/pptExporter.ts` via the `pres.writeFile` path, and the
server-PPTX flow in `components/preview/PPTPreview.tsx:70-77` and
`components/results/FilesTab.tsx:166-167, 252-267`) and are revoked
immediately after the anchor click.

### 2.4. Environment variables

All frontend environment access goes through `frontend/src/lib/env.ts:6-11`,
which exports a single frozen `ENV` object. Raw `process.env.NEXT_PUBLIC_*`
reads exist only in that file — every other call site imports `ENV`.

| Name | Default | Read at | Consumers |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `lib/env.ts:8` (exported as `ENV.API_URL`) | `lib/api.ts:16` (`BASE_URL` for every REST call), plus direct `fetch` in `components/preview/PPTPreview.tsx:39, 53`, `components/results/FilesTab.tsx:146, 160`, `components/workflow/SkillManager.tsx:47, 74, 102`. |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000/ws/chat` | `lib/env.ts:10` (exported as `ENV.WS_URL`) | Default for `useWebSocket` (`hooks/useWebSocket.ts:29`); passed explicitly in `app/dashboard/page.tsx:306` and `app/workflow/page.tsx:33`. |

No other `process.env.NEXT_PUBLIC_*` references exist under
`frontend/src/`.

**Backend env vars relevant to client-side flows:**

| Name | Default | Purpose | Read at |
|---|---|---|---|
| `PPTX_NODE_MODULES_DIR` | `/opt/pptx/node_modules` if present, else `<repo>/frontend/node_modules` | Resolves the location of `pptxgenjs` for server-side PPTX export. Production Docker images install pptxgenjs@3.12.0 at `/opt/pptx/node_modules` (`backend/Dockerfile:91-97, 138-140`); local dev falls back to the sibling frontend tree. Explicit override wins over both. | `backend/app/services/pptx_export.py:28-37` |

### 2.5. Voice & speech

| Hook | Web API | Behaviour | Consumers |
|---|---|---|---|
| `useSpeechRecognition` (`hooks/useSpeechRecognition.ts:63-141`) | `window.SpeechRecognition` / `window.webkitSpeechRecognition` (`useSpeechRecognition.ts:44-49, 70-72`) | `continuous = true`, `interimResults = true`, `lang = "en-US"` (`useSpeechRecognition.ts:79-81`); rebuilds the full transcript from `event.results[*][0].transcript` (`:83-92`); ignores `no-speech` errors (`:96`); calls `.abort()` on unmount (`:108-112`). | `components/chat/ChatInput.tsx:17, 50, 52` (transcript populates the chat textarea); `components/workflow/IdeaInputPage.tsx:11, 77`; `components/workflow/WorkflowView.tsx:33, 106`. |
| `useTextToSpeech` (`hooks/useTextToSpeech.ts:16-113`) | `window.speechSynthesis` (`useTextToSpeech.ts:23-24, 28-30, 57, 86, 93, 102`) | Strips Markdown / HTML / `<thinking>` blocks before speaking (`:60-70`); voice preference list `["Google US English", "Samantha", "Alex", "Microsoft Zira", "Microsoft David"]` with fallback to first English voice (`:34-49`); `rate = 1.0`, `pitch = 1.0`, `volume = 1.0` (`:77-79`); cancels any in-flight utterance before speaking (`:57`) and on unmount (`:101-103`). | `components/chat/MessageBubble.tsx:19, 85, 132-135, 364-366` (read-aloud button on assistant messages). |

No `MediaRecorder` / `getUserMedia` / file-upload audio paths exist — the
only voice surfaces are Web Speech API on the recognition side and
SpeechSynthesis on the playback side.

### 2.6. Client-side parsers & exporters

**Parsers** (`frontend/src/lib/parsers/`):

| File | Exports | Purpose |
|---|---|---|
| `streamParser.ts:9-36, 41-43` | `parseStreamMessage`, `serializeStreamMessage` | Validates incoming WS JSON shape against a whitelist of `["stream","complete","error","phase_start","phase_end"]` (`:3`). Note: this whitelist is **narrower** than the actual `StreamMessage` type in `types/index.ts:35-40` (which includes `pipeline_*`, `agent_*`, `title_update`, etc.), so this helper would reject every pipeline event. `useWebSocket.ts:107-119` does its own `JSON.parse` and does **not** use `parseStreamMessage`, so this is currently dead validation code. |
| `userStoryParser.ts:23-225, 227-260` | `parseUserStoryMarkdown`, `formatUserStoryMarkdown` | Parses BDD-aware user-story Markdown — Epic (`# Title [P0]`), Story (`## Title`), `**As a/I want/so that**`, `**Story Points:**`, `**Dependencies:**`, and `- **Given/When/Then**` bullets (`userStoryParser.ts:1-22`); also supports a legacy `# Epic / ## Story / - AC` form. `formatUserStoryMarkdown` serialises the document back to Markdown. |
| `pptParser.ts:73-116, 121-198 (normalize helpers)` | `parsePPTSlideData` | Slide-deck JSON parser hardened against LLM output noise: strips Markdown code fences (`:11-14`), trims to the outermost `{ … }` (`:17-21`), attempts a truncated-JSON repair pass (`:30-63, 80-89`), and normalises every slide to defaults (`:121-198`). Falls back to `{slides:[]}` when input is malformed beyond repair. |

**Exporters** (`frontend/src/lib/exporters/`):

| File | Exports | Output | Notes |
|---|---|---|---|
| `storyExporter.ts:4-16` | `exportUserStories(content, filename?)` | `text/markdown;charset=utf-8` → `.md` | Default filename `user-stories`; standard `Blob`/`URL.createObjectURL` download with immediate `URL.revokeObjectURL`. |
| `prototypeExporter.ts:4-26` | `exportPrototype(content, filename?)` | `application/json;charset=utf-8` → `.json` | Attempts `JSON.parse` + `JSON.stringify(..., null, 2)` for pretty-printing; exports raw on parse failure. |
| `pptExporter.ts:46-110` | `exportToPptx(slideData, filename?)` | `.pptx` via `pptxgenjs` (`pptExporter.ts:1`) — saved via `pres.writeFile({fileName})` | **Client-side**, in-browser builder. 16:9 wide layout (`LAYOUT_WIDE`, `:48`); enterprise palette (`:5-21`). Routes by slide `type` plus data presence: `title` (`:112-179`), `chart` (`:224-266`, falls back to bar via `getChartType` at `:31-40`), `table` (`:267-313`), `comparison` (`:314-373`), `two-column` (`:374-411`), `quote` (`:412-end`), `content` default (`:180-223`). Filename is derived from the first slide's title when not supplied (`:52-55`). |

**Server-side PPTX export** (new, complements the client builder above):
`POST /api/workflows/export-pptx` (see §2.2) ships Agent 3's PptxGenJS source
to the backend; `backend/app/services/pptx_export.py:40-179` sanitises it
(strips fences `:46-48`, fixes `#`-prefixed hex colors `:53-55`, clamps
8-char hex to 6 `:57`, neutralises negative shadow offsets `:59`, comments
out bare `.line.` property accesses `:60-71`, rewrites `pres.writeFile` /
`pres.save` to `return pres.write("nodebuffer")` `:74-80`, ensures the
function is `async` `:83-84`), wraps it in a Node script that monkey-patches
`Module._resolveFilename` so `require("pptxgenjs")` always resolves under
`NODE_MODULES_DIR` (`:95-103`), runs it via `subprocess.run(["node", …],
timeout=30, …)` (`:157-160`), and returns the resulting bytes. A fallback
slide is emitted when the user code throws (`:108-124, 137-144`). The path
covers the case where Agent 3's `generatePresentation()` JS is too elaborate
for the in-browser `pptxgenjs` builder above.

`components/preview/PPTPreview.tsx:22-84` and
`components/results/FilesTab.tsx:135-175` are the two callers — both first
try to attach a `workflow_id` (by matching the `<h1>` to a recent run; falls
back to the latest run) and then POST `{js_code?, html?, workflow_id?, title}`
to the new endpoint, downloading the returned blob via
`URL.createObjectURL` + anchor click.

`components/results/FilesTab.tsx:33-74` (`parseAppBuilderFiles`) also acts
as a quasi-parser: it splits an App-Builder markdown response on
` ```filename: <path>\n…\n``` ` fences into per-file rows that each download
through the same `Blob`/`URL.createObjectURL` path.

---

## 3. Detailed frontend workflow notes

(One subsection per surface; backend traces follow in §4.)

### 3.1 Auth (W01 – W07)

Each entry: name → frontend entry point (`file:line`) → trigger → expected outcome. Token storage is `localStorage["auth_token"]` (`frontend/src/lib/api.ts:18`); see §B1 for the backend trace.

- **W01 — Root redirect** (`frontend/src/app/page.tsx:3-5`). Trigger: any unauthenticated hit to `/`. Server component, immediately calls `redirect("/login")` from `next/navigation`. No client state, no token check (a logged-in user landing on `/` still gets bounced to `/login` and must re-enter; the dashboard does not auto-resume from `/`).

- **W02 — Register** (`frontend/src/app/register/page.tsx:10`). Trigger: form submit on `/register` (`handleSubmit` at `register/page.tsx:31-71`). Client-side validation requires password ≥ 8 chars (`register/page.tsx:18-23, 36-39`). POSTs to `/api/auth/register` via `register()` in `frontend/src/lib/api.ts:104-115`. Maps `409 Conflict` to `fieldErrors.email = "An account with this email already exists."` (`register/page.tsx:47-48`); maps `422` to per-field errors using each item's `field` or terminal `loc` (`register/page.tsx:49-62`). On success: `setToken(data.token)` persists JWT to `localStorage["auth_token"]` (`api.ts:113`), then `router.push("/dashboard")` (`register/page.tsx:45`). Note: register uses `router.push`, not `router.replace` — back-button returns to `/register`.

- **W03 — Login** (`frontend/src/app/login/page.tsx:10`). Trigger: form submit on `/login` (`handleSubmit` at `login/page.tsx:17-36`). POSTs to `/api/auth/login` via `login()` in `frontend/src/lib/api.ts:117-128`. Maps `401` to `"Invalid email or password."` (`login/page.tsx:26-27`); other `ApiError` instances render `err.detail` verbatim (`login/page.tsx:28-29`). On success: `setToken(data.token)` then `router.push("/dashboard")` (`login/page.tsx:24`). No client-side password length check on login (only register enforces ≥ 8); backend `LoginRequest` has no `min_length` either (`backend/app/models/schemas.py:19-23`).

- **W04 — Auto-auth check** (`frontend/src/app/dashboard/page.tsx:48-56`). Trigger: dashboard mount. Reads `getToken()`; if absent calls `router.replace("/login")` and returns (`dashboard/page.tsx:50-53`); otherwise stores it in state, flips `isAuthenticated` (`dashboard/page.tsx:54-55`), and a follow-up effect best-effort-fetches `getWorkflows({limit:50})` with the error path silently swallowed (`dashboard/page.tsx:58-70`). The standalone `/workflow` page does the same guard at `frontend/src/app/workflow/page.tsx:22-30`. Note: there is no server-side token validation on this gate — only "token string present in `localStorage`". A stale/revoked token will appear "logged in" client-side until the first API call returns 401 (currently swallowed for the workflow prefetch) or until the WS handshake closes 4001.

- **W05 — JWT-expiry forced logout** (`frontend/src/hooks/useWebSocket.ts:125-137`). Trigger: WebSocket `onclose` event with code `4001` (constant at `useWebSocket.ts:32`). Action: `clearToken()` removes `auth_token`, sets `lastError = "Your session has expired. Please log in again."`, and forces a hard navigation via `window.location.href = "/login"` (`useWebSocket.ts:128-135`). Backend emits this code for missing/invalid/expired/revoked JWTs on the WS path (`backend/app/api/websocket.py:114, 145, 168, 171, 285`) — not only expiry. No refresh-token mechanism exists. Note: this handler runs *before* the auto-reconnect branch, so a 4001 close skips the exponential-backoff retry loop entirely.

- **W06 — User logout** (`frontend/src/app/dashboard/page.tsx:565-568`). Trigger: any of three UI surfaces:
  - `AppHeader` profile menu "Log out" button — `AppHeader.tsx:127-134` calls the injected `onLogout` prop.
  - `Sidebar` footer "Log out" button — `Sidebar.tsx:192-205`, rendered only when `onLogout` is supplied.
  - `DashboardLayout` plumbs both through to the dashboard's `handleLogout` (`DashboardLayout.tsx:34, 64, 346`).

  Action: `handleLogout` awaits `logout(getToken() ?? "")` from `frontend/src/lib/api.ts:47-60`, which (a) POSTs `Bearer <token>` to `/api/auth/logout` to revoke the JWT server-side, (b) always runs `clearToken()` in `finally` even on network failure, then (c) `router.replace("/login")` (`dashboard/page.tsx:566-567`). This is a real server logout — different from earlier doc — that inserts a `revoked_tokens` row keyed by the JWT's `jti` (see §B1). Network errors are intentionally swallowed: the user is logging out either way.

- **W07 — Change password** (`frontend/src/components/settings/AccountSettings.tsx:33-65`). Trigger: "Change Password" submit in Account Settings (`AccountSettings.tsx:160-166`). Client-side guards: all three fields non-empty (`AccountSettings.tsx:36-39`), new password ≥ 8 chars (`AccountSettings.tsx:40-43`), new vs. confirm match (`AccountSettings.tsx:44-47`). POSTs to `/api/auth/change-password` via `changePassword(token, current, new)` in `frontend/src/lib/api.ts:352-370`, body `{current_password, new_password}` (`api.ts:361`). On success: green success toast and the three input fields are cleared (`AccountSettings.tsx:55-58`); the stored `auth_token` is **not** refreshed. Because the backend stamps `password_changed_at` (see §B1) and rejects any JWT with `iat < password_changed_at`, the next authenticated HTTP call (or next WS message that triggers re-validation) returns 401, which on the WS path closes 4001 → W05 forces logout. Eye-toggle on current/new password inputs (`AccountSettings.tsx:116-118, 133-135`); confirm field has no eye toggle. Email shown above is loaded via `getMe()` (`AccountSettings.tsx:24-31`), errors silently dropped.

---

### 3.2 Dashboard, navigation & sidebar (W08 – W17)

> **Architecture note — sidebar is dead code.** The current build mounts only `DashboardLayout`, which uses `AppHeader` (top bar) for navigation. `frontend/src/components/sidebar/Sidebar.tsx:59-208` and `frontend/src/components/sidebar/ChatSessionItem.tsx` exist on disk but **no module imports them** (verified by `grep -rn "from.*sidebar/Sidebar"` returning empty). The `recentRuns` / `onSelectWorkflowRun` props that `DashboardPage` passes to `DashboardLayout` (`dashboard/page.tsx:615-616`) are accepted (`DashboardLayout.tsx:43-44, 73-74`) but never rendered — the only consumer is `currentWorkflowRunId` at `DashboardLayout.tsx:117-119`, which is itself never read. W10–W14 below describe the *current* surface that replaces those flows; the legacy sidebar entries are flagged `[VERIFY: legacy]`.

| WF | Trigger / entry | Component & file:line | Expected outcome |
|---|---|---|---|
| W08 — Load dashboard | First mount after `/dashboard` route resolves | `app/dashboard/page.tsx:48-56` (auth check), `:59-70` (`getWorkflows({limit:50})`), `:305-309` (WS open via `useWebSocket({url:ENV.WS_URL, token, onMessage:handleWebSocketMessage})`) | Token read from `localStorage`; on miss → `router.replace("/login")`. On hit, sets `isAuthenticated`, pre-fetches `recentRuns`, opens WS subscription. Failures on `getWorkflows` are silenced (`:66-69`). |
| W09 — Header navigation (Home/Library + profile menu) | Click `AppHeader` Home / Library buttons or open profile dropdown for Account Settings / Workflow History / Log out | `components/layout/AppHeader.tsx:52-77` (Home, Library), `:111-124` (Account Settings, Workflow History inside dropdown), `:126-134` (Log out). `DashboardLayout.handleNavigate` at `DashboardLayout.tsx:292-295` sets `mainView`. | Switches `mainView ∈ {"home","library","history","settings"}`. Whole header is disabled when `isPipelineRunning` is true — `disabled={isPipelineRunning}` passed at `DashboardLayout.tsx:347` and gated again inside the handler at `:293`. The buttons render with `opacity-40 cursor-not-allowed` in that state (`AppHeader.tsx:55-56,68-69,86-87`). |
| W10 — Toggle sidebar | **No live sidebar** — there is no collapse/expand control in the mounted layout. | `[VERIFY: legacy]` `Sidebar.tsx:96-104` defines an `onCollapse` callback, but `Sidebar` is unmounted. | n/a in current build. |
| W11 — New Project | Click any Home card (W12) — there is no separate "New Project" CTA in the mounted layout. | `[VERIFY: legacy]` `Sidebar.tsx:109-118` had a "New Project" button (`onClick={onOpenWorkflow}`), but `Sidebar` is unmounted. The home-card click goes to `IdeaInputPage` via `DashboardLayout.handleSelectFeature` at `DashboardLayout.tsx:175-179`. | Home → IdeaInputPage transition (`setMainView("input")`). Blocked while `isPipelineRunning` (`:176`). |
| W12 — Select feature card | Click one of 5 cards on `CreationHub` | `components/home/CreationHub.tsx:11-47` defines 5 workflow tiles (`user_stories`, `ppt`, `prototype`, `app_builder`, `custom`), rendered at `:77-105`. Each `onClick` invokes `onSelectFeature(workflow.type)` → `DashboardLayout.handleSelectFeature` (`DashboardLayout.tsx:175-179`). | Sets `workflowType` and `setMainView("input")`. **Cards are NOT visually disabled while pipeline runs** — `CreationHub` accepts no `disabled` prop and renders the same in both states; the *navigation* is gated only in `handleSelectFeature` (`DashboardLayout.tsx:176`) which silently returns. The 6th card mentioned in old docs (`reverse_engineer`) has been removed. |
| W13 — Sidebar search (legacy) / Workflow-history search (live) | Type into search input | **Legacy:** `[VERIFY: legacy]` `Sidebar.tsx:74-78,131-134` filtered `recentRuns` by `(run.title || run.input || "").toLowerCase()`. Unused.  **Live equivalent:** `WorkflowHistory.tsx:113-119` filters by `(r.title || "").toLowerCase().includes(searchQuery.toLowerCase())` combined with the type-filter pill row (`:285-341`). | Live search filters the workflow-history list in-memory. No backend query. |
| W14 — Select sidebar run (legacy) / Select history run (live) | Click a row in the history list | **Legacy:** `[VERIFY: legacy]` `Sidebar.tsx:166` `onClick={() => onSelectRun?.(run)}` → `dashboard/page.tsx:493-521` `handleSelectWorkflowRun` (lazy-loads `output` via `getWorkflow(id)` when `status === "completed"` and routes to the correct preview state). Unused.  **Live:** `WorkflowHistory.tsx:76-93` `handleSelectRun` (in-page detail view; `getWorkflow(id)` only fired when `run.output` is empty). | Loads detail in-place inside `WorkflowHistory`'s right pane (`:121-282`). The page-level `handleSelectWorkflowRun` in `dashboard/page.tsx` is wired through but unreachable today. |
| W15 — Library page | `mainView === "library"` | `components/library/LibraryPage.tsx:33-151`. Static catalog from `LIBRARY_AGENTS ∪ CUSTOM_AGENTS` in `AgentLibraryData.ts` (combined at `:8`). | Renders a 200 px category rail (`:50-78`) and a responsive grid (`:101-147`). No backend calls. |
| W16 — Library search & filter | Search box (top right) + category rail | `LibraryPage.tsx:10-17` defines 6 categories: `all, user_stories, ppt, prototype, app_builder, custom` (added `custom`). Filter logic at `:37-45`: `pipeline_type === activeCategory` AND fuzzy-match on `name|description|role`. Sort at `:45`: `pipeline_type.localeCompare(...) → order asc`. | Filters and sorts the agent grid client-side. Counts per category at `:56-58`. |
| W17 — Account Settings | Profile dropdown → "Account Settings" → `mainView === "settings"` | `components/settings/AccountSettings.tsx:24-31` mounts and calls `getMe(token)`; result populates `email`. `:33-65` posts to `changePassword` via `/api/auth/change-password`. | Email displayed read-only (`:91-94`). Password form requires all 3 fields, checks `newPassword.length ≥ 8` and `new === confirm`. Success → toast + reset fields (`:55-58`). Error → toast with `err.message` (`:59-62`). `getMe` failure is silently swallowed (`:29`). |

**Connection-status banner** (not numbered in the W-series but visible from W08 onward): `DashboardLayout.tsx:316-340` shows a yellow "Reconnecting…" strip for `connectionStatus === "reconnecting"` and a red "Connection lost." strip with a Reconnect button for `connectionStatus === "failed"`.

**Pipeline-running gate.** `isPipelineRunning = pipelineState?.isRunning ?? false` (`DashboardLayout.tsx:111`). Used to disable: `AppHeader` (`:347`), `handleNavigate` (`:293`), `handleSelectFeature` (`:176`), `handleGoHome` (`:215`). Note: there is no `aria-disabled` on the `CreationHub` cards themselves — the cards still appear interactive but `handleSelectFeature` silently returns.

**`workflow_title_update` frontend handler.** `dashboard/page.tsx:265-274` handles a `workflow_title_update` WS event by updating `recentRuns`. **The backend never emits this event** — `grep -rn "workflow_title_update" backend/` returns zero matches. This is dead code on the front-end side. Only `title_update` (chat-session title regeneration) is emitted today (`backend/app/api/websocket.py:346-351`).

**No `localStorage`-backed sidebar collapse state** — all UI persistence in this scope is via `auth_token` cookie/storage; theme/sidebar prefs are not stored.

---

### 3.3 Workflow history (W18 – W20)

The Workflow History view is a self-contained, two-pane component
(`frontend/src/components/history/WorkflowHistory.tsx`, 504 lines).
It mounts as a full-screen replacement when the user navigates to history
and exposes its own list view and detail view in a single component —
state machine is `selectedRun: WorkflowRun | null` (`WorkflowHistory.tsx:57`):
when null, list view is rendered; otherwise the detail view is rendered.

There is **no "rerun" action**. The only state-changing action on the
history surface is **delete**.

- **W18 — list & filter.** On mount, `getWorkflows({ limit: 100 })` is
  fired once (`WorkflowHistory.tsx:66-74`); the response populates `runs`,
  and the loader is silent-on-failure (`.catch(() => {})`). Filtering is
  fully client-side via `filteredRuns` (`:113-119`):
  - Free-text search matches against `r.title` (lower-cased,
    *title only* — not `input` or `output`).
  - The type-filter tabs (`typeGroups = ["all", "user_stories", "ppt",
    "prototype", "app_builder"]`, `:285`) group `_revision` types with
    their base type (`baseType = r.type.replace("_revision", "")`,
    `:115`), so toggling "User Stories" surfaces both `user_stories`
    and `user_stories_revision` runs.
  - Tab counts (`typeCounts`, `:286-287`) are computed from the full
    `runs` array, not the filtered view, and a tab is hidden if its
    count is 0 (except "All").
  - Status badges per row (`:392-404`):
    `completed → "Done"` (emerald),
    `failed → "Failed"` *except* when `run.error === "Cancelled by user"`
    where it renders **"Cancelled"** (gray),
    and everything else → **"Running"**.
    **Drift note:** the frontend `WorkflowStatus` type
    (`types/index.ts:188`) is still
    `"running" | "completed" | "failed"` — it does NOT yet include
    `"cancelled"`, even though the backend now writes that value
    (see §B4). The UI's current cancel-detection path
    (`run.error === "Cancelled by user"`) is also stale — the backend
    sets `wr.status = "cancelled"` (`websocket.py:619`) but does **not**
    set `wr.error`, so cancelled runs land in the `else` branch and
    render as **"Running"** in the badge until the type is widened.
    `[VERIFY: this looks like a real bug — confirm with a manual cancel +
    history reload that the cancelled run shows "Running" not "Cancelled"]`

- **W19 — open detail.** `handleSelectRun` (`:76-93`) sets the run,
  resets the detail tab to `"preview"`, and **lazy-fetches** the full
  row only if `run.output` is empty (list endpoint returns `output` so
  this is usually a no-op; the lazy path exists for the case where the
  list response truncated long outputs or for older rows). The detail
  view is a two-column layout:
  - **Left sidebar (`:138-223`)** — agent breakdown. Parses
    `selectedRun.agentOutputs` (already deserialised in the API
    normaliser; falls back to `JSON.parse` if it arrived as a string,
    `:132-135`). Each agent row is a `<details>` element showing the
    `name`, `role`, `duration` (s, no decimals), a DONE badge, and a
    collapsible 1200-char-truncated `output` (`:210-213`). Per-agent
    `thinking` field is present in the schema but **not rendered** in
    the detail view.
  - **Right pane (`:226-273`)** — `Preview / Files` tab pair.
    `Preview` dispatches by `WorkflowType` to one of four preview
    components:
    `UserStoryPreview` for `user_stories` and its revision,
    `MarkdownPreview` for `app_builder`, `app_builder_revision`,
    `custom`,
    `PPTPreview` for `ppt` and `ppt_revision`,
    `PrototypePreview` for `prototype` and `prototype_revision`
    (`:126-129`, `:258-262`). `Files` renders `FilesTab` and is the
    only place a user can export artifacts from history — including
    the new server-side PPTX download (see export-pptx in §B4).

- **W20 — delete.** Three-step in the UI but two confirmations:
  1. Click the row's `MoreHorizontal` button (only visible on hover,
     `opacity-0 group-hover:opacity-100`, `:410`) → opens a small menu.
  2. Click **Delete** in the menu → `handleDeleteClick` (`:95-99`),
     closes the menu, sets `deleteConfirmId`.
  3. `DeleteModal` (`:457-503`) shows a backdrop-blurred confirm modal;
     **Delete** calls `handleDeleteConfirm` (`:101-111`) →
     `deleteWorkflow(id)`, then optimistically removes the row from
     `runs` and clears the detail view if the deleted run was open.
     **Errors are silently swallowed** (`.catch(() => {})`) — the row
     stays gone client-side even if the 204 didn't actually happen, so
     a network error during delete will reappear on the next history
     visit.

**Files-tab download is significant.** `FilesTab.tsx` is the only place
in history where outbound state changes happen for non-delete actions:
clicking the PowerPoint row triggers the new server-side PPTX export
(`FilesTab.tsx:135-175`), which:
1. Builds a synthetic `title` by reversing the filename (`-` → space,
   `:142`).
2. **Looks up a workflow_id** by fetching the user's last 20 `ppt`
   runs and finding one whose `output` contains the H1 from the current
   `pptContent`, falling back to the most recent run if no match
   (`:146-157`). This is a fragile heuristic — if `pptContent` has no
   `<h1>` *and* the most recent `ppt` run is unrelated, the export hits
   the wrong row. In the history detail view this is usually fine
   because `pptContent` was just hydrated from the same run, but the
   code does not pass the already-known `selectedRun.id` through.
3. POSTs `{ html: pptContent, workflow_id, title }` to
   `/api/workflows/export-pptx`. Note `js_code` is **not** sent from
   this code path — the backend has to fall back to its workflow-DB
   or HTML-extraction strategies.
4. On success, downloads the blob as the displayed filename. On
   failure, `alert("PPTX export failed. Try the Download PPTX button
   in the preview.")` — no inline error UI.

---

### 3.4 Workflow setup & composition (W21 – W32)

Entry chain: `CreationHub` (workflow type tile click) → `IdeaInputPage` (prompt + agent pipeline) → `handleRunPipeline` (`DashboardLayout.tsx:182-186`) which stages a `pendingPipelineRun` then dispatches `useWorkflow.startPipeline(type, message, agent_ids)`. The composed agent ordering is sent on the wire via `payload.agent_ids` on the `run_pipeline` WebSocket message (`useWorkflow.ts:54-56`); the backend filters/reorders the registry agents from that array (`websocket.py:558-561`).

Files of record for this section:
- `frontend/src/components/home/CreationHub.tsx` (workflow type picker — 112 lines)
- `frontend/src/components/workflow/IdeaInputPage.tsx` (prompt input + advanced — 293 lines)
- `frontend/src/components/workflow/AgentsPopup.tsx` (visual pipeline canvas — 321 lines)
- `frontend/src/components/workflow/AgentLibrary.tsx` (add-agent modal — 202 lines)
- `frontend/src/components/workflow/AgentLibraryData.ts` (frontend catalog — 60 lines)
- `frontend/src/components/library/LibraryPage.tsx` (read-only Library page — 151 lines)
- `frontend/src/components/workflow/SkillManager.tsx` (skill modal — 308 lines; reached from `AgentNode.tsx:197-202`, **not** from the setup flow)
- `backend/app/agents/registry.py` (canonical pipeline agents)
- `backend/app/agents/custom_agents.py` (canonical custom-pipeline agents)
- `backend/app/api/websocket.py:210-240, 465-571` (run_pipeline reception + custom-agent reorder)

#### Workflow ledger

- **W21 — Workflow type selection** (`CreationHub.tsx:11-47, 77-105`). The home page renders a hard-coded `WORKFLOWS` array of five entries: `user_stories`, `ppt`, `prototype`, `app_builder`, `custom`. Clicking a tile fires `onSelectFeature(workflow.type)` → `DashboardLayout.handleSelectFeature` (`DashboardLayout.tsx:175-179`), which sets `workflowType` state and switches `mainView` to `"input"`. **Drift to flag:** the backend registry also defines a `reverse_engineer` pipeline (`registry.py:975-1219`) with four agents; that pipeline was removed from the UI in commit 047fb43 ("Removed Reverse Engineer feature") but the backend agents remain wired into `ALL_AGENTS["reverse_engineer"]` (`registry.py:1245`) and into the popup's role tables (see W27). It is no longer reachable from any UI entry point.

- **W22 — Idea text input** (`IdeaInputPage.tsx:70-97, 177-185`). Single `<textarea>` bound to `ideaInput` state. Auto-focused 200 ms after mount (`:92`). Per-type placeholder/heading/labels from `TYPE_CONFIG` (`:20-68`). Submit handler `handleRun` (`:94-97`) validates `ideaInput.trim().length > 0 && pipelineAgents.length > 0`; otherwise the call returns silently and the bottom button is `disabled` (`:248`). Cmd+Enter or Ctrl+Enter shortcut also fires `handleRun` (`:184`).

- **W23 — File attachment** (`IdeaInputPage.tsx:73, 187-199, 204-223`). A hidden `<input type="file" multiple>` accepts `.pdf,.doc,.docx,.pptx,.txt,.md,.json,.csv` (`:208-209`). The `onChange` handler builds chips of `{name, size}` (`:214-217`), pushes them onto `attachedFiles`, and appends `\n\n[Attached: <name1>, <name2>]` to the textarea string (`:219`). **Open issue (carry-forward):** the binary content is never read or uploaded — only the filename string travels with the prompt. The backend `run_pipeline` payload schema has no file/blob field (`websocket.py:228-230` reads only `pipeline_type`, `message`, `agent_ids`). Chip removal is local-only (`:193`), and the bracketed `[Attached: …]` substring in the textarea is **not** reverse-edited when a chip is removed.

- **W24 — Voice input** (`IdeaInputPage.tsx:77, 88-90, 230-242`). Driven by `useSpeechRecognition` (`frontend/src/hooks/useSpeechRecognition.ts:63-99`) — browser-native `SpeechRecognition` / `webkitSpeechRecognition` (continuous + interim). The Voice button is rendered only when `speechSupported` (`:230`). Pressing it captures the current `ideaInput` into `preSpeechTextRef` then calls `startListening()`; pressing again calls `stopListening()`. The `useEffect` at `:88-90` concatenates the pre-speech text with the live `transcript` and writes the result back into `ideaInput`. See also §2.5.

- **W25 — Agents popup (advanced)** (`IdeaInputPage.tsx:72, 264-276, 280-289`; `AgentsPopup.tsx:76-320`). The "Advanced" button under the input opens `<AgentsPopup>` with the current `pipelineAgents`, the workflow type, and add/remove/reorder callbacks. The popup renders a 3-column dotted-grid canvas (`COLS = 3`, `:74`) with cards 130 px wide × 68 px high; each row is connected by dashed-arrow connectors (`:222-227`). Header shows count + pipeline label + a "Browse agent library →" trigger (`:172-174`). Footer has Cancel / Save changes — both call `onClose` (`:298-304`); changes are already live, so the buttons are cosmetic.

- **W26 — Agent library modal** (`AgentLibrary.tsx:18-201`; opened from `AgentsPopup.tsx:308-315`). 820 × 640 px modal with a left sidebar (six categories: All, User Stories, Presentation, Prototype, App Builder, Custom — `:20-27`) and a 2-column agent grid. The full catalog is `ALL_AGENTS = [...LIBRARY_AGENTS, ...CUSTOM_AGENTS]` (`:18`) — i.e. all 26 frontend agents. Filtering combines category + search (matches name / description / role lowercase, `:51-55`) + `notAlreadyAdded` (parent's `existingAgentIds` set, `:56`) + `notHidden` (`:57`). `HIDDEN_FROM_CUSTOM` (`:29-32`) — 8 IDs — are suppressed when `currentPipelineType === "custom"`: the four terminal compilers (`ppt-assembler`, `backlog-compiler`, `prototype-finalizer`, `app-assembler`) and the four pipeline-starter analysts (`ppt-content-strategist`, `domain-analyst`, `requirements-analyst`, `material-analyzer`). Clicking a card calls `handleAdd` (`:69-73`) which fires `onAddAgent` and immediately closes the modal.

- **W27 — Add agent → pipeline** (`IdeaInputPage.tsx:104-116`). `handleAddAgent` rejects duplicates (`:106`) and enforces the per-pipeline cap. Cap math:
  - `currentDefaults` = set of `LIBRARY_AGENTS` IDs whose `pipeline_type === workflowType` (`:107`).
  - `currentOptional` = `pipelineAgents.filter(a => !currentDefaults.has(a.id)).length` (`:108`).
  - `limit = workflowType === "custom" ? 8 : 5` (`:109`).
  - **Insertion position:** for `custom`, append (`prev.length`); for every other type, insert at `prev.length - 1` (i.e. immediately before the trailing terminal/compiler agent) (`:111`). The inserted agent's `order` field is overwritten with `insertIdx + 1` (`:113`).
  - `canAddMore` is recomputed at the parent (`IdeaInputPage.tsx:101-102`) and threaded down to `AgentsPopup` and `AgentLibrary` to disable add buttons (`AgentLibrary.tsx:165-170`). **Drift to flag:** the older `WORKFLOWS.md` wording says "respects per-pipeline-type max (most types max-2, custom max-8)" — that is wrong; the actual cap is **5** for every non-custom type (see `IdeaInputPage.tsx:101` and `AgentsPopup.tsx:127`).

- **W28 — Agent ordering / reorder** (`AgentsPopup.tsx:36-64, 89-111`). Each card has one of three roles, computed by `getRole(agentId, pipelineType)`:
  - `locked` — in `LOCKED_AGENT_IDS` (`:20-26`) **and** native to the current pipeline. Cards are non-draggable (`draggable={!locked}`, `:233`) and other cards cannot drop on them (`handleDrop` no-ops at `:102`). Renders the `Lock` icon + "Core" badge.
  - `required` — in `REQUIRED_AGENT_IDS` (`:28-34`) **and** native to the current pipeline. Draggable, but cannot be removed (no trash icon).
  - `optional` — everything else, including cross-pipeline agents added from the library. Draggable + removable.
  - **Cross-pipeline rescue:** if an agent that's normally locked/required is dragged onto a different pipeline (e.g. `domain-analyst` added to `custom`), `getRole` returns `optional` (`:43-59`), so it can be reordered and removed freely.
  - Drag flow: `handleDragStart` (`:89-92`) captures `draggedIdx` (refuses if source is locked). `handleDragOver` (`:94-98`) calls `e.preventDefault()` and updates `dragOverIdx` (refuses to highlight locked targets). `handleDrop` (`:100-109`) splices the dragged item out and re-inserts it at the drop index, then calls `onReorder(updated)` (which in the parent simply replaces `pipelineAgents` state — `IdeaInputPage.tsx:122-124`). The new ordering is what becomes `agent_ids` on submit.

  Note: `LOCKED_AGENT_IDS` still includes `repo-scanner` and `documentation-generator`, and `REQUIRED_AGENT_IDS` still includes `deep-analyzer` and `modernization-planner` — all four are reverse-engineer agents not present in the frontend library. They are dead branches kept for safety in case a stale localStorage payload re-introduces them.

- **W29 — Remove agent** (`AgentsPopup.tsx:84-87, 260-268`). The trash button (`X` icon in a red badge) only renders for `optional` cards (`:260`). `handleRemove` re-checks `getRole !== "optional"` before forwarding to the parent (defensive: blocks anyone tampering with disabled buttons). Parent removal handler is `IdeaInputPage.tsx:118-120` (plain `.filter`). Removed agents reappear in the library because `AgentLibrary` derives its existence-check only from the parent-supplied `existingAgentIds` (`AgentLibrary.tsx:47-48, 56`).

- **W30 — Library page** (`library/LibraryPage.tsx:33-150`). Standalone read-only catalog reachable from the sidebar (no add buttons). Renders `ALL_AGENTS_COMBINED = [...LIBRARY_AGENTS, ...CUSTOM_AGENTS]` (`:8`) using the same 6-category sidebar (`:10-17`) and a 2/3/4-column responsive grid (`:102`). Sort: `pipeline_type` then `order` (`:45`). Search matches `name | description | role` (case-insensitive, `:39-43`). Each card shows initials avatar, name, pipeline label (twice — header tag + footer tag), role, description, and `~Xs` estimated duration (`:111-143`).

- **W31 — Skill load** (`SkillManager.tsx:37-62`). When the modal opens for an agent, `loadSkill` fires `GET /api/agents/skills/${agentId}` with the auth bearer. 200 → `setSkillContent(data.content || "")`. Anything non-2xx silently sets `setSkillContent("")` (treated as "no skill yet"). Network errors set `loadError` and log.
  - **Trigger path:** SkillManager is rendered by `AgentNode.tsx:197-202` inside the run-time `PipelineGraph`. It is **not** reachable from `IdeaInputPage` / `AgentsPopup` / `AgentLibrary`, so W31–W34 here are technically run-time affordances co-located in this section by historical convention. (The older `WORKFLOWS.md` line refs `48-62 / 75-93 / 103-117` are mid-function and slightly off; the function spans above are correct.)

- **W32 — Skill save** (`SkillManager.tsx:64-93`). Save button (visible only in edit mode, `:221`) issues `POST /api/agents/skills` with JSON `{agent_id, content}`. On 2xx: `setSaveSuccess(true)`, exits edit mode, clears the flag after 2 s (`:84-86`). Failures are logged to console only — there is no user-visible save-failed toast.

Additional W-numbered items in this section (continued from the existing ledger; included here for completeness):

- **W31a — Skill upload** (`SkillManager.tsx:114-125`). The "Upload .md" button is a `<label>` wrapping a hidden `<input type="file" accept=".md,.txt">`. `handleFileUpload` uses `FileReader.readAsText` and pipes the resulting string into `setSkillContent` while enabling edit mode (`:120-123`). **The uploaded file's content is loaded into the textarea but not persisted server-side until the user clicks Save** (W32). The `<input>` accept list restricts to text formats so binary upload concerns from W23 do not apply.

- **W31b — Skill delete** (`SkillManager.tsx:95-111`). The Delete button (red badge, only visible when `skillContent` truthy, `:213`) issues `DELETE /api/agents/skills/${agentId}` and locally clears `skillContent` + edit mode. There is **no confirmation modal** — a single click deletes immediately. Failures are logged but not surfaced.

#### Frontend ↔ backend agent registry — drift audit

The previous `WORKFLOWS.md` §B5 claim was: *"Front-end's `LIBRARY_AGENTS` list matches the backend registry exactly."* **Verified:** for the 26 agent IDs present on both sides, every shared field (`name`, `role`, `description`, `pipeline_type`, `order`, `icon`, `estimated_duration`) is byte-for-byte identical. No drift on shared agents.

| Frontend (`AgentLibraryData.ts`) | Count | Backend (`registry.py` + `custom_agents.py`) | Count |
|---|---|---|---|
| `LIBRARY_AGENTS` (4 pipelines) | 18 | `USER_STORY_AGENTS` + `PPT_AGENTS` + `PROTOTYPE_AGENTS` + `APP_BUILDER_AGENTS` | 18 |
| `CUSTOM_AGENTS` (custom pool) | 8 | `CUSTOM_AGENTS` (`custom_agents.py:5-206`) | 8 |
| **Total** | **26** | matching subset | **26** |

Backend IDs **not** exposed in the frontend (10 — all intentional):
- Reverse-engineer pipeline (4): `repo-scanner`, `deep-analyzer`, `modernization-planner`, `documentation-generator` — pipeline removed from UI in commit 047fb43 but agents still loaded in `ALL_AGENTS["reverse_engineer"]` and referenced by name in `AgentsPopup` role tables (`AgentsPopup.tsx:20-34`).
- Revision-edit agents (5): `user-story-revision-agent`, `ppt-revision-agent`, `ppt-revision-assembler`, `prototype-revision-agent`, `app-builder-revision-agent` — driven by the `*_revision` pipeline types from preview "revise" affordances, never user-pickable.
- Helper agent (1): `questionnaire` (`registry.py:1281-1313`) — runs as a separate `generate_questions` WS message, not part of any user-composable pipeline.

No frontend-only IDs (the frontend has no orphan agents that the backend cannot dispatch).

`PIPELINE_CATEGORIES` (`AgentLibraryData.ts:44-51`) hardcodes count totals: `all:20`, `user_stories:6`, `ppt:4`, `prototype:4`, `app_builder:4`, `custom:8`. **Drift:** `all:20` is stale — the actual `ALL_LIBRARY_AGENTS.length` is `6 + 4 + 4 + 4 + 8 = 26`. The export is currently unreferenced inside the workflow folder (only `LibraryPage.tsx` and `AgentLibrary.tsx` compute counts from the array directly), so the inconsistency is dormant rather than user-visible.

#### Custom-agent ordering wire contract

End-to-end shape (verified `:`-by-`:` from textarea to LLM dispatch):

1. UI state — `pipelineAgents: AgentDef[]` in `IdeaInputPage` (`:78-80`). Initial value = `LIBRARY_AGENTS.filter(pipeline_type === workflowType).sort(order asc)`. Reseeds on workflow-type change (`:82-84`).
2. Mutation surface — `handleAddAgent` (insert), `handleRemoveAgent` (filter), `handleReorderAgents` (replace) — wired into `AgentsPopup`/`AgentLibrary` (`IdeaInputPage.tsx:104-124`, `IdeaInputPage.tsx:280-289`).
3. Submit — `handleRun` (`:94-97`) projects `pipelineAgents.map(a => a.id)` and calls `onRun(message, agentIds)`.
4. Bubble up — `DashboardLayout.handleRunPipeline(message, agentIds)` (`DashboardLayout.tsx:182-186`) stages a `pendingPipelineRun` then (after the questionnaire step) calls `useWorkflow.startPipeline(type, message, agentIds)`.
5. Wire — `useWorkflow.startPipeline` (`useWorkflow.ts:33-61`) emits `{type:"run_pipeline", pipeline_type, message, agent_ids?}` only when the list is non-empty (`:54-56`).
6. Reception — `websocket.py:210-240` reads `agent_ids` off the message and forwards to `_handle_pipeline_execution(..., agent_ids=agent_ids)`.
7. Reordering — when `agent_ids` is present, the handler rebuilds the agent list as `[agent_map[aid] for aid in agent_ids if aid in agent_map]` (`websocket.py:558-561`). **This preserves the exact frontend order**, including cross-pipeline agents and dropped defaults. Unknown IDs are silently skipped (no error to the client).
8. Execution — `WorkflowOrchestrator(pipeline_type, custom_agents=agents)` (`websocket.py:567-571`). Inside the orchestrator, `self.agents = custom_agents or get_pipeline_agents(pipeline_type)` (`orchestrator_v2.py:188`).

Implications worth flagging:
- The `pipeline_type` is still sent and is used for telemetry, revision detection (`orchestrator_v2.py:182-183`), and for selecting prompt-engineering context — but the **actual agent execution list comes from `agent_ids`** when provided, not from the pipeline-type defaults. A `custom` pipeline can therefore run e.g. PPT agents end-to-end if the user composed it that way.
- There is no server-side validation that the composed sequence makes sense (e.g. no enforcement that a terminal-compiler is last). Skips on unknown IDs are silent — a stale agent ID from local UI state would cause that step to be quietly omitted.
- The frontend's `LOCKED_AGENT_IDS` / `REQUIRED_AGENT_IDS` are advisory only; they exist exclusively in `AgentsPopup.tsx:20-34` and do not propagate to the backend. The backend will happily run any sequence of registered agent IDs.

### 3.5 Pipeline execution (W33 – W41)

Frontend path: `IdeaInputPage` → questionnaire → `useWorkflow.startPipeline` → `useWebSocket.send` → DashboardLayout switches `mainView="execution"` → `AgentProgressPanel` renders streaming events.

**W33 — `run_pipeline` send.** `useWorkflow.ts:33-61` builds `{type:"run_pipeline", pipeline_type, message, agent_ids?}` and ships it through `websocketSend`. `agent_ids` is only included when the caller passed a non-empty list (`useWorkflow.ts:54-56`). The `agent_ids` array is populated by `IdeaInputPage` from the user-mutated `pipelineAgents` list (`IdeaInputPage.tsx:96`), and by `DashboardLayout.handleChainPipeline`/`handle*Revision` callbacks (no `agent_ids`, server picks defaults).

> Note: `startPipeline` is currently invoked indirectly via `pendingPipelineRun` after the questionnaire round-trip, not directly from `IdeaInputPage`. See W64 below — the questionnaire is fired first, the actual `run_pipeline` is sent only after `handleQuestionnaireSubmit`/`handleQuestionnaireSkip` (`DashboardLayout.tsx:252-289`).

**W34 — `pipeline_start` received.** `useWorkflow.ts:97-128` initialises the agents array from `msg.agents` (each `{id, name, role, icon, order}`), sets every status to `idle`, `currentAgentIndex=0`, `completedCount=0`. Because `dashboard/page.tsx:77-80` flattens `{type, ...msg.data}` before forwarding to `handlePipelineMessage`, the hook sees `msg.agents` even though the wire frame carries the agents under `data.agents`.

**W35 — per-agent stream events.**
- `agent_start` (`useWorkflow.ts:130-144`): records `agentStartTimesRef[agent_id]=Date.now()` then sets that agent's `status="running"` and `currentAgentIndex` to its position.
- `agent_thinking` (`:146-160`): copies `msg.thinking` into the agent's `thinking` string and flips `status="thinking"`.
- `agent_chunk` (`:162-180`): appends `msg.chunk` to `agent.output`, status back to `"running"`. One frame per LLM token (no batching).
- `agent_complete` (`:182-206`): final duration is computed locally as `(Date.now() - agentStartTimesRef[agent_id]) / 1000`. The server-sent `duration` field is ignored — the hook prefers wall-clock measured from `agent_start`. `status="done"`, `completedCount` re-derived.

**W36 — `agent_error`.** `useWorkflow.ts:208-227`. Marks that agent `status="error"` with `error` text. Does **not** set `isRunning=false` — the orchestrator decides whether to break the loop (config errors abort, other errors keep going — see §B5).

**W37 — `pipeline_complete`.** `useWorkflow.ts:229-239`. Sets `isRunning=false`, captures `msg.total_duration`. `dashboard/page.tsx:83-105` separately reads `msg.data.final_output` and `msg.data.pipeline_type` to route the final blob into `setUserStoryContent` / `setPptContent` / `setPrototypeContent`, then refreshes the workflow history list. Revision pipeline types map to the same content bucket as their base type via the same conditional.

**W38 — cancel.** `AgentProgressPanel.tsx:170` exposes a "Pause" button that calls `onCancelPipeline`. `DashboardLayout.tsx:449-454` sends `{type:"cancel_pipeline"}` and calls `onResetPipeline()` locally. The local reset clears the panel state immediately; the backend asynchronously emits a final `pipeline_cancelled` once `_handle_pipeline_execution` finishes its `CancelledError` cleanup (see §B2/§B5). The button label says "Pause" but the wire message is `cancel_pipeline` — there is no resume path, this is purely cosmetic.

**W39 — completion UI.** Once `isComplete` (`!isRunning && completedCount === agents.length`), `AgentProgressPanel.tsx:195-232` shows "Chain to next pipeline" + a "New Pipeline" button. Cancelled state shows the same button with the banner "Pipeline stopped" (`:159`).

**W40 — reset.** `useWorkflow.ts:63-67` returns state to `INITIAL_STATE` and clears both refs. Called by `DashboardLayout.handleGoHome` (`:214-222`), all revision callbacks before re-running, and the cancel handler above.

**W41 — chain.** `DashboardLayout.handleChainPipeline` (`:225-249`): assembles `enrichedInput = workflowInput + "\n\n=== CONTEXT FROM PREVIOUS PIPELINE (...) ===\n" + lastPipelineOutput.slice(0, 4000) + "\n=== END PREVIOUS CONTEXT ==="` and re-routes through the questionnaire flow with the new `pipeline_type`. There is no server-side chaining — each chained step is a fresh `run_pipeline` with the prior output stuffed into the user message. The chain selector is hidden for `app_builder` / `reverse_engineer` / revision types (`DashboardLayout.tsx:447`).

**Revision triggers (sub-flow of W41).** Four buttons in the preview panel produce `=== EXISTING <ARTIFACT> ===...=== REVISION REQUEST ===` payloads and call `onStartPipeline` with `*_revision` pipeline types (`DashboardLayout.tsx:122-164`). The frontend caps prototype/app-builder content at 40 000 chars; user_stories revisions ship the full backlog uncapped.

**Execution view layout.** `DashboardLayout.tsx:438-456` left panel = `AgentProgressPanel` (340-360 px), right panel = `QuestionnairePanel` while questions are loading or pending, otherwise `PreviewPanel` (`:462-484`). The agent panel forwards `pptxCode` extracted from `pipelineState.agents.find(a => a.id === "ppt-code-generator" && a.status === "done")?.output` (`DashboardLayout.tsx:114`) so the PPT preview can call the server-side `/api/workflows/export-pptx` route as soon as Agent 3 finishes — before Agent 4 even starts.

---

### 3.6 Chat & streaming (W42 – W49)

This section covers the conversational chat thread (text in, streamed text/markdown out). It is the path triggered by a `user_message` envelope on the WebSocket, which the backend routes through `AgentOrchestrator` (`backend/app/agents/orchestrator.py`) — **not** through `WorkflowOrchestrator` (`backend/app/agents/orchestrator_v2.py`, which owns pipeline runs in W33–W41). The two paths share one WebSocket connection (`useWebSocket.ts`) but are distinct on both ends: the frontend routes `pipeline_*` / `agent_*` events into the pipeline handler and everything else into chat state (`frontend/src/app/dashboard/page.tsx:75-107`).

**Transport & connection.** All chat traffic flows over a single `wss://.../ws/chat` connection authenticated via `Sec-WebSocket-Protocol: bearer.<jwt>` subprotocol (`useWebSocket.ts:98`; backend gate `backend/app/api/websocket.py:122-160`). The hook auto-reconnects with exponential backoff up to 5 attempts (`useWebSocket.ts:30-31, 145-158`) and closes with code 4001 on JWT failure (`useWebSocket.ts:128-137`; backend close at `backend/app/api/websocket.py:145, 168, 285`).

**Streaming protocol (server → client).** For a chat turn the backend pushes envelopes shaped `{type, chunk, section, data}` (Python: `backend/app/agents/orchestrator.py:319-449`; TS: `frontend/src/types/index.ts:35-40`). For each of the discovery / requirements / selected output phases the orchestrator emits in order:

1. `phase_start` with `data={"phase": <n>, "name": <section>}` (`orchestrator.py:319, 355, 400`).
2. A burst of `stream` events, each carrying one token-chunk in `chunk` and the `section` name (`orchestrator.py:325, 361, 406`). The chunk text comes from `BaseAgent.astream()` (`backend/app/agents/base.py:162-176`) which wraps `ChatBedrockConverse.astream` and extracts text blocks (`base.py:107-132`).
3. `phase_end` with the same `phase` number (`orchestrator.py:352, 384, 438`).
4. Finally one `complete` envelope whose `data` is the full `FinalOutputModel.model_dump()` (`orchestrator.py:444-449`).

Mid-stream, any agent exception is caught and converted to a single `error` envelope with `{error, code, recoverable, phase}` via `app.agents.llm_errors.map_exception` (`orchestrator.py:341-351`, `:373-383`, `:427-437`; mapper at `backend/app/agents/llm_errors.py:71-115`). The WS handler also has an outer `try/except` (`websocket.py:375-403`) that catches `AgentConfigurationError` (non-recoverable `api_key_missing`) and any other exception (mapped via the same `_map_llm_exception` helper, kept on `websocket.py:14`). Title-generation runs once on the first message (see W45) and produces a separate `title_update` envelope.

**Workflows.**

- **W42 send text.** Trigger: user types in `ChatInput` and presses Enter (no Shift) or clicks send. Behaviour: `handleSend` guards against empty input and an already-streaming reply, then calls `onSendMessage(trimmed)` if mode is `default` or `onSendMessageWithMode(trimmed, activeMode)` otherwise; it clears the textarea, resets the mode badge, and snaps the textarea height back to `auto` (`frontend/src/components/chat/ChatInput.tsx:66-75`). Enter handling is `ChatInput.tsx:77-79` (Shift+Enter inserts a newline). The textarea auto-resizes between `min-h-[52px]` and `max-h-[240px]` (`ChatInput.tsx:81-84, 135`). The dashboard's `handleSendMessage` is debounced with `sendingRef` (`page.tsx:320-377`): on first send it lazily creates a chat session (`page.tsx:330-342`), appends a local user message, sets `isStreaming=true` and `streamingContent=""`, clears process steps and preview refs, then sends `{type:"user_message", content, chat_session_id}` over the WS (`page.tsx:365-371`). Expected outcome: the user bubble renders on the right immediately (optimistic UI); a streaming reply begins arriving within ~1 s; `isStreaming` flips back to `false` on the terminal `complete` envelope.

- **W43 mode-tagged send.** Trigger: user opens the `+` menu and picks one of four modes — `thinking`, `deep_research`, `web_search`, `quiz` (`ChatInput.tsx:29-34`); the active mode is shown as a dismissible badge above the input (`ChatInput.tsx:94-112`). Behaviour: when `activeMode !== "default"`, `handleSend` calls `onSendMessageWithMode(trimmed, activeMode)` (`ChatInput.tsx:69`) and resets `activeMode` to `default` after dispatch (`ChatInput.tsx:72`). The dashboard's `handleSendMessageWithMode` sends `{type:"user_message", content, chat_session_id, mode}` (`page.tsx:417-424`) and stores the mode in `currentMode` so the resulting assistant bubble carries a mode badge (`page.tsx:380-427`; `MessageBubble.tsx:270-277` renders the badge with the `MODE_LABELS` table at `MessageBubble.tsx:33-38`). Server side: the WS handler reads `mode` from the message (`websocket.py:207`), resolves the mode-specific system-prompt enhancer via `get_mode_prompt(mode)` (`websocket.py:361`; `backend/app/agents/modes.py:7-49`), and forwards it as `mode_prompt=` to `AgentOrchestrator.astream_execute` (`websocket.py:365-370`). The mode prompt is prepended to each agent's `system_prompt` inside `BaseAgent._build_messages` (`backend/app/agents/base.py:138-141`); the `mode_prompt`/`mode` keys are filtered out of the context dump so they don't leak into the human message (`base.py:144-148`). Expected outcome: assistant reply structure changes per mode — e.g. `thinking` wraps reasoning in `<thinking>...</thinking>` which `MessageBubble` parses into a collapsible "Thought process" block with a gradient left border (`MessageBubble.tsx:43-61, 286-318`). Unknown modes fall through to an empty string in `get_mode_prompt` (`modes.py:48`), so behaviour degrades to default. The badge is cleared from the input the instant `handleSend` runs (`ChatInput.tsx:72`).

- **W44 receive streaming reply.** Trigger: each `stream` envelope arriving on the WS for the active chat turn. Behaviour: `useWebSocket.onmessage` JSON-parses the frame and forwards it to the dashboard's `handleWebSocketMessage` (`useWebSocket.ts:107-118`). The handler's `stream` case (`page.tsx:110-133`) appends `msg.chunk` to either `streamingContent` (chat text) or a preview ref keyed by `msg.section` (`user_stories` / `ppt` / `prototype`). The currently-streaming assistant bubble is *not* yet in the `messages` array — instead the renderer detects "streaming with no final assistant message yet" and shows `TypingIndicator` until the first token, then `MessageBubble` renders the live `streamingContent` with `isStreaming={true}` (`ChatPanel.tsx:194-264`, `MessageBubble.tsx:89-94`). The streaming style is the `streaming-cursor` class on the `markdown-content` div (`MessageBubble.tsx:321`) — a blinking caret while tokens arrive. Markdown is rendered via `react-markdown` (`MessageBubble.tsx:17, 322`). On the terminal `complete` envelope (`page.tsx:143-221`), `isStreaming` flips to false, the accumulated `streamingContent` is committed as a new assistant message in `messages` (`page.tsx:187-201`), and `streamingContent` is reset to `""`. The complete payload's `data` (the `FinalOutputModel` from `orchestrator.py:444-449`) is inspected; if it carries structured `user_stories` / `ppt` / `prototype` sections, those are JSON-stringified into the preview-panel state (`page.tsx:208-219`). Expected outcome: tokens flow into the in-place bubble at sub-second cadence, the blinking cursor disappears on `complete`, and the message is added to history with optional artifact card if a non-text section was emitted (`page.tsx:162-185`).

- **W45 title_update.** Trigger: first user message on a fresh `ChatSession` (the WS handler checks `chat_session.title in ("New Chat", "")` or matches the auto-snippet at `websocket.py:317`). Behaviour: backend instantiates a one-shot `BaseAgent` with a short system prompt asking for a 3-5 word title (`websocket.py:325-332`), calls `title_agent.run(content)` (one non-streaming Bedrock call, `base.py:178-185`), trims/quotes/punctuation-strips the result and clamps to 60 chars (`websocket.py:335`). On success it `UPDATE`s `chat_sessions.title` and emits `{type:"title_update", data:{chat_session_id, title}}` on the WS (`websocket.py:346-351`); on failure the exception is swallowed with a `logger.warning` (`websocket.py:352-353`). Frontend `title_update` case stores the new title in `chatTitleUpdate` (`page.tsx:257-263`), which `DashboardLayout` propagates to the sidebar list. Expected outcome: within ~1-2 s of the first send, the sidebar entry renames from "New Chat" to the generated title; subsequent messages do not trigger another title call because `needs_title` only matches the seed title strings.

- **W46 typing indicator.** Trigger: `isStreaming === true` while the last message in `messages` is not yet an assistant message (`ChatPanel.tsx:274-279`). Behaviour: renders `TypingIndicator` — an `Sparkles` avatar with `avatar-streaming` glow plus four animated `motion.div` bars and the literal copy "IdeaFlow AI is generating..." (`frontend/src/components/chat/TypingIndicator.tsx:10-54`). Expected outcome: covers the latency window between `user_message` send and the first `stream` chunk; once any chunk lands, `MessageBubble` takes over (because the dashboard's `complete` case is the one that finally appends the assistant message — streaming chunks are buffered in `streamingContent`, not in `messages`, so during the stream the last entry in `messages` is still the user's). Note: the dashboard never sets `messages[last].role === "assistant"` *during* streaming; the typing indicator therefore remains visible alongside the live-streaming bubble that `ChatPanel.tsx:194-264` synthesises from `streamingContent`. Empty-state path (no messages, no streaming) short-circuits in `ChatPanel.tsx:83-192` to the suggestion-chip layout — the typing indicator is not rendered there.

- **W47 process steps.** Trigger: a `step` WS envelope (`page.tsx:283-300`) — `data` is a `ProcessStep` `{id, label, detail?, status: "running"|"done"|"error", icon?, timestamp?}` (`frontend/src/types/index.ts:42-49`). Behaviour: the dashboard upserts on `step.id`, maintaining both `processSteps` state and a `processStepsRef` mirror (`page.tsx:286-298`). `ProcessSteps` renders a vertical, left-border-accented list (`frontend/src/components/chat/ProcessSteps.tsx:97-116`); each `StepItem` shows an emoji icon, label (auto-pluralised "ing"→"ed" on done — `ProcessSteps.tsx:50-52`), `Loader2`/`CheckCircle2`/`XCircle` status icon (`ProcessSteps.tsx:12-22`), and a chevron that expands the optional `detail` paragraph (`ProcessSteps.tsx:59-89`). On `complete` the dashboard snapshots `processStepsRef.current` and attaches it to the new assistant message as `steps` so the badges persist in history (`page.tsx:145-146, 198`), then clears live state (`page.tsx:146, 206`). On chat-load, embedded steps are recovered from the `<!--steps:JSON-->` marker the WS handler prepends to persisted assistant content (`websocket.py:412-415`; load-side parsing at `page.tsx:444-451`). Expected outcome: when a chat-side action produces step events, badges appear inline above the assistant bubble and remain after streaming completes; an unrecognised `step.status` (anything not "running"/"done") renders the red `XCircle` (`ProcessSteps.tsx:21`). **Verified gap:** the chat orchestrator (`orchestrator.py`) does not currently emit any `step` envelopes itself — grep across `backend/app/` shows no `"step"`/`'step'` type producer. In the current build, step badges therefore appear in chat only via (a) the persisted `<!--steps:...-->` marker on reload, or (b) future emitters; pipeline runs use their own `agent_*` events handled by the workflow path (W33–W41) not this code path.

- **W48 error with retry.** Trigger: an `error` envelope on the WS — produced by `AgentOrchestrator.astream_execute` per-phase (`orchestrator.py:341-351, 373-383, 427-437`) or by the outer WS handler on `AgentConfigurationError` / generic exception (`websocket.py:375-403`). Payload shape `{error, code, recoverable}` is set by `app.agents.llm_errors.map_exception` (`llm_errors.py:71-115`); known codes are `api_key_missing`, `auth_error`, `rate_limit`, `timeout`, `connection_error`, `internal_error` (`llm_errors.py:50-68, 120-127`). The handler explicitly hardcodes `api_key_missing` / `recoverable=False` for `AgentConfigurationError` (`websocket.py:381-386`). Behaviour: dashboard's `error` case flips `isStreaming` off, extracts `error`/`code`/`recoverable` from `data` (or falls back to `msg.chunk`), and synthesises an assistant message with content `Error: <message> [code:<code>] [recoverable:<true|false>]` (`page.tsx:223-255`). `ChatPanel` detects messages starting with `Error:` or carrying `isError`, parses the embedded `[code:…]` / `[recoverable:…]` tags out of the string with regex (`ChatPanel.tsx:201-227`), and renders `ErrorMessage` instead of `MessageBubble`. `ErrorMessage` shows an `AlertTriangle` icon, the message text, the code in monospaced muted red, and — when `recoverable && onRetry` — a "Try Again" button (`frontend/src/components/chat/ErrorMessage.tsx:17-61`). Retry walks `messages` backwards from the error to find the most recent `role === "user"` message and re-fires `onSendMessage(content)` (`ChatPanel.tsx:235-247`). When `recoverable === false`, the button is replaced with a hardcoded explanatory line keyed off `code` — `api_key_missing` → "needs to be configured by an administrator", `auth_error` → "credentials are invalid", else "cannot be resolved by retrying" (`ErrorMessage.tsx:49-57`). Expected outcome: a recoverable error becomes a one-click retry that re-sends the original user prompt as a fresh `user_message`; non-recoverable errors are dead-ended visually with no retry affordance.

- **W49 empty state.** Trigger: `messages.length === 0 && !isStreaming` (the inverse of `hasMessages` at `ChatPanel.tsx:72`). Behaviour: `ChatPanel.tsx:83-192` renders the centred "What can I help you with?" greeting with a glowing `Sparkles` icon, animated ambient gradient orbs, and a 2×2 grid of suggestion chips. The four chips are hardcoded in `SUGGESTION_CHIPS` (`ChatPanel.tsx:26-47`): "Brainstorm a product idea", "Design a technical architecture", "Write user stories for my app", "Create a presentation deck", each paired with a Lucide icon (`Lightbulb`/`Code`/`FileText`/`Layers`) and a one-line description. Clicking a chip calls `onSendMessage(chip.label)` (`ChatPanel.tsx:174`) — which goes through the dashboard's normal `handleSendMessage` and therefore creates a chat session if needed, exactly like a typed message. Expected outcome: the click immediately drops the user into the conversation view (the streamed reply starts arriving, `hasMessages` flips true, the empty-state UI unmounts). Chips do not preselect a mode — they always send with `default` mode regardless of which output the label implies (W43 mode badges are independent).

### 3.7 Message interactions (W50 – W53)

All four message-level interactions live in a single client component, **`frontend/src/components/chat/MessageBubble.tsx`**, and operate purely on local state — there are no HTTP or WebSocket round-trips for copy, edit, regenerate, or TTS, and the backend has no message-edit / message-delete / message-regenerate endpoint (`backend/app/api/chats.py:51-191` exposes only create-chat, list, get, delete-chat, and append-message; the `Message` model in `backend/app/models/chat.py:34-49` has no `edited_at`, `deleted_at`, or version columns).

**Action bar surface.** Both user and assistant bubbles render a "glass-morphism" action pill on hover, gated by a `showActions` state set by `onMouseEnter` / `onMouseLeave` (`MessageBubble.tsx:152-153`, `MessageBubble.tsx:258-259`). The pill is hidden while the message is streaming — the assistant action bar is wrapped in `{!isStreaming && …}` (`MessageBubble.tsx:338`). A formatted `HH:MM` timestamp (`new Date(message.createdAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })`) is rendered as the last element of each pill (`MessageBubble.tsx:139-142`, `MessageBubble.tsx:229`, `MessageBubble.tsx:384`).

**Consumption status.** `MessageBubble` is imported only by `frontend/src/components/chat/ChatPanel.tsx:7`, and `ChatPanel` itself is not imported anywhere outside its own file — the current dashboard (`frontend/src/app/dashboard/page.tsx`) routes everything through `DashboardLayout` → `AgentProgressPanel` / `PreviewPanel` / `QuestionnairePanel` (`frontend/src/components/layout/DashboardLayout.tsx:13-15`, `:440-485`). Dashboard never wires `onRegenerateMessage` / `onEditMessage` callbacks. **The bubble UI and all four W50-W53 interactions therefore exist as built-but-unmounted code in the current app shell.** The behaviours below describe what executes when the component is rendered (e.g. in a future or alternate host page).

---

- **W50 copy** — `handleCopy` (`MessageBubble.tsx:121-129`). `await navigator.clipboard.writeText(displayContent)` writes the full message text (or the current `streamingContent` when one is being streamed; `displayContent` is selected at `MessageBubble.tsx:90-93`). On success a `copied` flag is set to `true` and reset after exactly 2000 ms via `setTimeout`; while `copied` is true the icon swaps from `<Copy>` to `<Check className="text-green-400">` (`MessageBubble.tsx:218`, `:353-357`). Failure is silent — the `catch` only `console.error`s, no toast or retry. The same button appears on user bubbles (`MessageBubble.tsx:213-219`) and assistant bubbles (`MessageBubble.tsx:348-358`).
  - Note: `handleCopy` copies the raw message string (which for assistant messages includes any `<thinking>…</thinking>` blocks — those are only stripped for display via `parseThinkingBlocks` at `MessageBubble.tsx:43-61, :96-101`, not for clipboard).
  - There is **no per-code-block "Copy code" button**: `ReactMarkdown` is invoked with no `components` mapping at `MessageBubble.tsx:322`, so the default `<pre>`/`<code>` elements render with no overlay UI. The repo has no syntax highlighter (`frontend/package.json` declares `react-markdown` and `remark-gfm` only; no `rehype-highlight`, `prismjs`, `shiki`, etc.).

- **W51 edit user message** — only the **user** bubble exposes the edit affordance (`MessageBubble.tsx:220-228`); the `<Pencil>` button is rendered only when an `onEdit` prop is provided. Click sets `isEditing = true`, which swaps the read-only `<p>` for a `<textarea>` pre-filled with `editContent` (initialised from `message.content` at `:80`) and an autoFocused 60 px-min textarea (`MessageBubble.tsx:167-175`). Keyboard handler `handleEditKeyDown` (`MessageBubble.tsx:110-119`):
  - **Enter** (without Shift) → `e.preventDefault()` + `handleEditSubmit()`.
  - **Shift+Enter** → newline (default textarea behaviour).
  - **Escape** → resets `editContent` to original `message.content` and exits edit mode without firing `onEdit`.
  - Two buttons mirror the keyboard actions: **Cancel** (resets + exits, `:177-185`) and **Save & Send** (`:186-191`).
  - `handleEditSubmit` (`:103-108`) fires `onEdit?.(message.id, editContent.trim())` **only when** the trimmed value is non-empty **and** different from `message.content`; otherwise it silently exits edit mode. The action bar is fully hidden while editing (`{!isEditing && (<AnimatePresence>…)}` at `MessageBubble.tsx:202`).
  - Wiring: `ChatPanel` accepts an `onEditMessage?: (messageId, newContent) => void` (`ChatPanel.tsx:21`, `:60`, `:262`) and forwards it. The dashboard page does **not** supply this prop today, so editing is a no-op in the current shell. `[VERIFY: intended “re-send after edit” semantics — no caller exists to inspect.]`

- **W52 regenerate** — only the **assistant** bubble shows the `<RefreshCw>` button, and only when `onRegenerate` is provided (`MessageBubble.tsx:374-382`). Click fires `onRegenerate(message.id)`. As with edit, `ChatPanel` declares `onRegenerateMessage?: (messageId: string) => void` (`ChatPanel.tsx:20`, `:59`, `:261`) but no live caller supplies it from `dashboard/page.tsx`. The button is conditionally suppressed while streaming because the whole action-bar block is wrapped in `!isStreaming` (`MessageBubble.tsx:338`).
  - The closest implemented "resend last user message" pattern lives in `ChatPanel.tsx:235-248` (the `ErrorMessage` retry path), which walks backwards through `messages` to find the most recent `role === "user"` and re-invokes `onSendMessage(messages[i].content)`. `[VERIFY: whether the intended W52 handler reuses that same walk-back-and-resend pattern — no implementation present.]`

- **W53 text-to-speech** — assistant-only, gated by `ttsSupported` from `useTextToSpeech` (`MessageBubble.tsx:85`, `:360`). The hook lives at **`frontend/src/hooks/useTextToSpeech.ts`** and detects support via `"speechSynthesis" in window` (`:22-23`). `handleTTS` (`MessageBubble.tsx:131-137`) toggles: if currently speaking, call `stop()` (`useTextToSpeech.ts:91-96` → `window.speechSynthesis.cancel()` + `setIsSpeaking(false)`); otherwise call `speak(mainContent)`, passing the **thinking-stripped** body (the `mainContent` from `parseThinkingBlocks`, not the full `displayContent`).
  - Inside `speak` (`useTextToSpeech.ts:52-89`) the text is further sanitised before becoming an utterance: headings (`#{1,6} `), bold (`**…**`), italics (`*…*`), inline + fenced backtick blocks, markdown links `[text](url)` → `text`, residual `<thinking>` tags, any remaining HTML, and newline collapsing (`\n{2,}` → `". "`, single `\n` → space).
  - Voice selection (`useTextToSpeech.ts:27-50`) ranks: `Google US English` → `Samantha` → `Alex` → `Microsoft Zira` → `Microsoft David`, then any voice whose `lang` starts with `"en"`, else `voices[0]`. `rate`, `pitch`, `volume` are all hard-coded to `1.0` (`:77-79`).
  - Icon swap: `<Volume2>` when idle → `<VolumeX className="text-red-400">` when `isSpeaking` (`MessageBubble.tsx:366-371`). State transitions are wired through `utterance.onstart` / `onend` / `onerror` (`useTextToSpeech.ts:81-83`). A second `speak` call begins with `window.speechSynthesis.cancel()` (`:57`) so a new utterance always pre-empts the previous one. Component-unmount cleanup at `useTextToSpeech.ts:99-105` cancels any in-flight utterance globally on the `window`.
  - Cross-reference: matches the description in §2.5 of WORKFLOWS.md.

---

**Out-of-scope but verified (mentioned to neighbour sections):**
- Thinking-block toggle (`<thinking>…</thinking>` parsed into a collapsible gradient-bordered panel) lives at `MessageBubble.tsx:286-318` and is **not** counted among W50-W53. It only fires for assistant messages (`useMemo` at `:96-101`).
- Streaming cursor blink `▊` is applied by toggling the `streaming-cursor` class on the markdown wrapper (`MessageBubble.tsx:321`); CSS at `frontend/src/styles/globals.css:99-106`.
- The "retry last user message" UX for server errors is owned by `ChatPanel.tsx:229-249` via `ErrorMessage`, covered under W48.

### 3.8 Artifacts, previews & downloads (W54 – W63)

Result-rendering surface for the three primary pipeline outputs (user_stories,
ppt, prototype) plus the App Builder / Custom variants and their `_revision`
counterparts. Two entry points: the inline `ArtifactCard` inside a chat message
(`MessageBubble.tsx:326-335`) and the workflow `PreviewPanel` tabbed view
(`PreviewPanel.tsx`). Both consume artifact text from `message.artifact.content`
(chat) or `WorkflowRun.output` / `agent_outputs` (history); there are no S3
URLs or per-artifact rows — everything is regenerated from the source text on
demand.

**Iframe sandbox** — both PPT and Prototype previews now use the same
restrictive policy `sandbox="allow-scripts allow-same-origin"`
(`PPTPreview.tsx:162`, `PrototypePreview.tsx:105`). The earlier additional
`allow-downloads allow-popups` flags on the PPT iframe are gone, because the
"Download PPTX" button is now rendered **outside** the iframe and uses the new
server-side export endpoint (see W60 below).

| WF | Trigger | Component | Output source | Error modes |
|---|---|---|---|---|
| **W54 open artifact** | Click on `ArtifactCard` (chat) or auto-mount of `PreviewPanel` (workflow run completed) | `ArtifactCard.tsx:50-179` → `onOpenPreview` callback (chat); `PreviewPanel.tsx:36-159` for workflow runs | `message.artifact.{type,filename,content,summary}` (chat) or `userStoryContent`/`pptContent`/`prototypeContent` props (workflow) | No content → `PreviewPanel` renders `"Output will appear here"` placeholder (`PreviewPanel.tsx:130-132`) |
| **W55 .md preview** | `renderType === "user_stories"` → `UserStoryPreview` (`PreviewPanel.tsx:135`). Also `app_builder` / `custom` render through `MarkdownPreview` (`PreviewPanel.tsx:136`) | `UserStoryPreview.tsx:26-274` — runs `parseUserStoryMarkdown` to extract epics/stories with priority/SP badges, collapsible epic sections, sticky stats bar; `MarkdownPreview.tsx:13-155` — react-markdown + remark-gfm with custom heading collapse, code-block copy buttons | `userStoryContent` prop (chat artifact content or `WorkflowRun.output`) | Empty `doc.epics` → falls back to `<pre>{content}` raw-text view (`UserStoryPreview.tsx:69-80`). No content → "No User Stories Yet" placeholder (`:31-43`) |
| **W56 .pptx preview** | `renderType === "ppt"` and `pptContent` present | `PPTPreview.tsx:17-217`. Renders the assembler HTML in a sandboxed iframe via `srcDoc` (`:159`); strips embedded "Download PPTX"/"Export" buttons from the HTML (`:117-119`) and replaces them with a single external server-side download button (`:166-181`); for revision flows, injects `<style>html,body{height:100%!important;overflow:hidden!important}</style>` so the iframe doesn't fight the revision bar for height (`:122-130`) | `pptContent` (the assembler's self-contained HTML page from `WorkflowRun.output`); `pptxCode` prop carries raw Agent 3 PptxGenJS code separately for the server export | Markdown-fence stripping if `htmlContent.startsWith("```")` (`:112-114`); `isHtml` guard renders a red error card if content isn't HTML (`:132-144`); streaming → animated placeholder (`:100-109`) |
| **W57 prototype preview** | `renderType === "prototype"` and `prototypeContent` present | `PrototypePreview.tsx:16-142`. Renders inside a fake browser chrome (traffic lights + URL bar `localhost:3000 / dashboard`), iframe `srcDoc`, sandbox `allow-scripts allow-same-origin` | `prototypeContent` (HTML from `WorkflowRun.output` or chat artifact) | Non-HTML content → renders raw text in `<pre>` (`:53-64`); empty → "No Preview Yet" placeholder (`:21-32`); `isStreaming` → animated "Building prototype..." (`:34-43`) |
| **W58 inline iframe** | Same as W56/W57 — covered above. PPT and Prototype both use iframe `srcDoc` so no network round-trip; HTML is delivered via the SQLite/Postgres `workflow_runs.output` column | — | — | "Open in new tab" button on both PPT (`PPTPreview.tsx:146-151`) and Prototype (`PrototypePreview.tsx:66-71`) wraps the HTML in a Blob URL and `window.open()`s it, then revokes after 5 s |
| **W59 .md download** | Click download on `ArtifactCard` (user-stories type, chat) or on the `presentation.md`/`user-stories.md` row in `FilesTab` | `ArtifactCard.tsx:76-104` → Blob `text/markdown;charset=utf-8`, anchor click, `URL.revokeObjectURL`. `FilesTab.tsx:132-134` → delegates to `exportUserStories` (`storyExporter.ts:4-16`) which is the same Blob pattern | `userStoryContent` / `message.artifact.content` | None (synchronous; clipboard/anchor APIs assumed available) |
| **W60 .pptx download (chat artifact)** | Click download on `ArtifactCard` with `type==="ppt"` | `ArtifactCard.tsx:80-82` → `parsePPTSlideData(content)` (`pptParser.ts:73-116`) → `exportToPptx()` (`pptExporter.ts:46-110`, uses npm `pptxgenjs@3.12.0` in the browser). 7 slide builders: `title`, `content`, `chart`, `table`, `comparison`, `two-column`, `quote` (`pptExporter.ts:77-91`). `LAYOUT_WIDE` (13.3"×7.5") | `message.artifact.content` — expected to be PPT slide JSON, not the assembler's HTML | JSON parse failure → `parsePPTSlideData` throws `"Failed to parse PPT slide JSON"` (`pptParser.ts:85`); missing `slides` array → `"missing \"slides\" array"` (`:110`). Errors caught at the call site and logged via `console.error` (`ArtifactCard.tsx:100`) |
| **W60 .pptx download (workflow preview / FilesTab)** | "Download PPTX" button inside `PPTPreview` (`:168-174`) OR `presentation-pptx` row in `FilesTab` (`:135-175`). **Both call the new server-side endpoint** `POST /api/workflows/export-pptx` | `PPTPreview.handleDownloadPptx` (`:22-84`) and `FilesTab.handleDownload` for the pptx row (`:135-175`). Both: (a) GET `/api/workflows?type=ppt&limit=20`, (b) match `<h1>` text from the HTML against `run.output` to resolve a `workflow_id` (fallback: first run), (c) POST `{js_code?, html, workflow_id, title}`, (d) blob-download the response | Server-rendered .pptx bytes from `pptx_export.generate_pptx_from_code` (see §B8) | Network/400/500 → `alert("Download failed.")`, button restored. Workflow-ID lookup is best-effort (caught and ignored); server-side extraction strategies (workflow→agent_outputs, js_code, html scan) are the actual fallback chain |
| **W61 .html download** | `presentation-html` row in `FilesTab` (PPT pipeline) OR `prototype-html` row (Prototype pipeline) | `FilesTab.tsx:121` (PPT HTML), `:129` (Prototype HTML). Both go through `downloadBlob(content, name+".html", "text/html")` (`:252-267`) which wraps `content` in a Blob and triggers an anchor click | `pptContent` / `prototypeContent` (the raw assembler HTML stored in `workflow_runs.output`) | None — synchronous Blob construction |
| **W62 prototype download (chat artifact)** | Click download on `ArtifactCard` with `type==="prototype"` (which expects `.json` per `TYPE_CONFIG`, `ArtifactCard.tsx:38-43`) | `ArtifactCard.tsx:83-84` → `exportPrototype` (`prototypeExporter.ts:4-26`): tries `JSON.parse` + pretty-print; falls back to raw on error; downloads as `.json` | `message.artifact.content` | `JSON.parse` failure silently exports raw content (`prototypeExporter.ts:12-14`). **Note:** the `ArtifactCard` chat path assumes prototype output is JSON (legacy assumption); the `FilesTab` workflow path exports prototype as `.html` (`:125-130`). These disagree — the chat code is stale relative to the current pipeline output format (HTML) |
| **W63 download all** | "Download All" button in `FilesTab` (`:201-207`) | `FilesTab.handleDownloadAll` (`:181-183`) — `files.forEach((file, i) => setTimeout(() => handleDownload(file), i * 150))` | Iterates the assembled `files: FileItem[]` array | **150 ms** stagger between downloads (was 100 ms in older code). Browsers may still group/throttle simultaneous downloads. Failures per file surface as individual `alert()`s. PPTX export awaits the server round-trip; markdown/HTML/JSON files are instant |

**Revision-type pass-through.** `PreviewPanel.tsx:44-48` normalises
`*_revision` types back to their base type (`ppt_revision` → `ppt`,
`prototype_revision` → `prototype`, etc.) before picking the preview component.
`FilesTab.tsx:81/89/103/111/125` accepts both base and `_revision` types when
deciding which files to surface, so the download menu shows the same rows for a
revision run as for the original.

**Cross-cutting: revision bar.** All four preview components
(`UserStoryPreview`, `MarkdownPreview`, `PPTPreview`, `PrototypePreview`)
accept an optional `onRevise(instruction: string)` callback that renders a
sticky-bottom input + "Revise" button. Pressing Enter or the button fires
`onRevise` with the trimmed text; the parent (workflow runner) sends a
follow-up `run_pipeline` with the appropriate `*_revision` type.

---

### 3.9 Questionnaire (W64)

Pre-pipeline clarifying MCQs the backend generates from the user's prompt + pipeline type, and that the frontend folds back into the `run_pipeline` payload as in-prompt guidance.

**Trigger.** Not a dedicated button — the questionnaire fires automatically whenever the user runs a pipeline. `IdeaInputPage.handleRun` (`frontend/src/components/workflow/IdeaInputPage.tsx:94-97`) calls the `onRun(message, agentIds)` prop, which `DashboardLayout` wires to `handleRunPipeline` (`frontend/src/components/layout/DashboardLayout.tsx:182-211`). That handler immediately:
1. Stashes `{ type, message, agentIds }` in `pendingPipelineRun` (`:185`) so the real `run_pipeline` can be deferred.
2. Sets `questionnaireLoading=true` + clears any stale questions (`:186-187`).
3. Schedules a **15 s timeout** (`:193-201`) that auto-clears the loading state if the backend never responds, letting the user fall through to a direct run.
4. Sends `generate_questions` over WS (`:204-210`).

`handleChainPipeline` (`:225-249`) reuses the same machinery when chaining a follow-up pipeline (PPT → User Stories etc.), passing an enriched prompt that already concatenates the previous pipeline's output.

**WS → backend.** Outbound frame:
```json
{ "type": "generate_questions", "pipeline_type": "<user_stories|ppt|prototype|…>", "message": "<idea>" }
```
Dispatched in the main WS loop at `backend/app/api/websocket.py:264-269` (intercepted before the `user_message` validator at `:271-278`). The handler `_handle_questionnaire(websocket, prompt, pipeline_type)` lives at `backend/app/api/websocket.py:723-778`:
- Imports `QUESTIONNAIRE_AGENT` lazily (`:730`) and constructs a fresh `BaseAgent` with that agent's system prompt and `max_tokens=2000` (`:735-738`). No `agent_id` row, no DB write — it's a one-shot LLM call.
- Builds the context as `f"Pipeline type: {pipeline_type}\nUser's idea: {prompt}"` (`:740`) and `await agent.run(context_message)` (`:741`).
- Greedy-extracts the first JSON object via `re.search(r'\{[\s\S]*\}', response)` (`:744-745`) and `json.loads` (`:747`). On match, emits the parsed object verbatim as the `data` field of a `questionnaire` WS message (`:748-753`).
- Three fallbacks all emit `data: { questions: [] }`: regex miss (`:756-761`), `AgentConfigurationError` (no Bedrock key, `:763-770`), and any other exception (`:771-778`). The empty-array sentinel lets the frontend gracefully skip.

**Agent definition.** `backend/app/agents/registry.py:1281-1313`:
- `id="questionnaire"`, `pipeline_type="questionnaire"`, `order=0`, `estimated_duration=3.0 s`, `max_tokens=2000`.
- System prompt mandates **strict JSON, no markdown, exactly 4 questions × 4 options each**, with pipeline-type-specific guidance baked in (PPT → audience/tone/visual style/key message; User Stories → team size/methodology/priority/technical depth; Prototype → design style/device/complexity/features).
- Schema enforced by the prompt:
  ```json
  { "questions": [ { "id": "q1", "question": "...", "options": ["…","…","…","…"] }, … ] }
  ```
- The `AgentDefinition` is **not** registered in the per-pipeline agent lists used by `get_all_agents_flat`; it's only reachable via the explicit import in `_handle_questionnaire`.

**Backend → WS → UI.** Server pushes:
```json
{ "type": "questionnaire", "chunk": null, "section": null, "data": { "questions": [ { "id": "q1", "question": "…", "options": ["…", …] }, … ] } }
```
`questionnaire` is listed in the discriminated union at `frontend/src/types/index.ts:36`. The dashboard's WS dispatcher routes it (`frontend/src/app/dashboard/page.tsx:276-281`) into local `questionnaireData` state, which `DashboardLayout` consumes via prop (`:45`). The `useEffect` at `frontend/src/components/layout/DashboardLayout.tsx:166-172` lifts `data.questions` into `questionnaireQuestions` and flips `questionnaireLoading=false`. The execution view conditionally swaps `PreviewPanel` for `QuestionnairePanel` whenever `(questionnaireLoading || questionnaireQuestions.length > 0) && pendingPipelineRun` (`:462-469`).

**UI — `QuestionnairePanel`.** `frontend/src/components/preview/QuestionnairePanel.tsx`:
- Single-select MCQs by default: `handleSelectOption` toggles a single option per `questionId`, dropping any prior choice (`:26-34`). The `MCQQuestion.allowMultiple?` flag (`:11`) is declared but unused in the current panel — every question behaves as single-select.
- Loading state with spinner (`:39-49`) and an early-return on `questions.length === 0` (`:51-53`) — combined with the empty-array fallbacks above, this is how "no API key / parse failure" silently skips the questionnaire.
- A free-form text input collects extra notes (`:120-132`).
- Two CTAs:
  - **Continue / Run Pipeline** (label flips based on `allAnswered`) → `onSubmitAnswers(selectedAnswers, freeformInput)` (`:137-143`).
  - **Skip questions & run directly** → `onSkip()` (`:144-149`).

**Answer round-trip — gap CLOSED.** The OLD doc flagged "The user's answers are NOT sent back to influence the run — the frontend just shows them as guidance." That gap is **no longer accurate.** `handleQuestionnaireSubmit` (`frontend/src/components/layout/DashboardLayout.tsx:252-278`) explicitly enriches the stored prompt:
```ts
let enrichedMessage = pendingPipelineRun.message;
const answerLines: string[] = [];
questionnaireQuestions.forEach((q) => {
  const selected = answers[q.id];
  if (selected && selected.length > 0) {
    answerLines.push(`- ${q.question}: ${selected.join(", ")}`);
  }
});
if (freeformInput) answerLines.push(`- Additional notes: ${freeformInput}`);
if (answerLines.length > 0) {
  enrichedMessage = `${pendingPipelineRun.message}\n\n=== USER PREFERENCES ===\n${answerLines.join("\n")}\n=== END PREFERENCES ===`;
}
…
onStartPipeline(pendingPipelineRun.type, enrichedMessage, pendingPipelineRun.agentIds);
```
That `onStartPipeline` is `useWorkflow.startPipeline` (`frontend/src/hooks/useWorkflow.ts:33-61`), which packs the **enriched** `message` into the actual `run_pipeline` WS payload at `:47-51`. The Bedrock-side agents therefore receive the user's choices verbatim as part of the prompt — there is no dedicated structured field, but the influence is real. **Skip** (`:281-289`) bypasses the enrichment and sends the original prompt unchanged. The empty-`answerLines` branch (no question answered, no free-form text) also sends the original prompt unchanged.

**Loose ends worth flagging.**
- The 15 s frontend timeout (`:193-201`) only clears `questionnaireLoading`; it does not cancel the in-flight backend call, so a slow `BaseAgent.run` will still produce a `questionnaire` message that the panel ignores (because `pendingPipelineRun` may already have been consumed). Harmless but wasteful.
- Bedrock failure cascades through three identical fallbacks (`data: { questions: [] }`); the frontend cannot distinguish "model unavailable" from "model returned non-JSON" from "user supplied no usable prompt".
- `allowMultiple` is declared on `MCQQuestion` but never wired — the agent prompt also doesn't ask for it. Either both ends should drop the field or the panel should honour it.
- The enriched prompt uses a literal `=== USER PREFERENCES ===` fence; downstream agents don't parse this structurally, so the influence depends entirely on the LLM picking it up. No tests assert this end-to-end.

---

## 4. Backend traces per workflow

### B1 — Auth backend trace (W01–W07)

**Stack.** FastAPI + SQLAlchemy 2.0 + python-jose (HS256 JWT) + bcrypt (raw `bcrypt` package, not `passlib`). DB default `sqlite:///./dev.db` (`backend/app/core/config.py:74`); Postgres in production via `DATABASE_URL`. Auth router mounted at app root in `backend/app/main.py:125`.

**Routes**

| WF | Method + path | Handler `file:line` | Request schema | Response | DB ops |
|---|---|---|---|---|---|
| W02 | `POST /api/auth/register` | `backend/app/api/auth.py:24-53` | `RegisterRequest` — `EmailStr` + `password: str = Field(..., min_length=8)` (`backend/app/models/schemas.py:12-16`) | `AuthResponse` `{token, user{id,email}}` (`schemas.py:35-39`), `201 Created` | `SELECT users WHERE email=?` then `INSERT users(id, email, password_hash, created_at, updated_at)`; commit |
| W03 | `POST /api/auth/login` | `backend/app/api/auth.py:56-84` | `LoginRequest` — `EmailStr` + `password: str` (no length) (`schemas.py:19-23`) | `AuthResponse`, `200` | `SELECT users WHERE email=?` |
| W04/W17 | `GET /api/auth/me` | `backend/app/api/auth.py:87-90` | n/a (Bearer in `Authorization`) | `UserResponse` `{id,email}` (`schemas.py:26-32`) | Via `get_current_user` dep (`backend/app/core/dependencies.py:153-178`) |
| W06 | `POST /api/auth/logout` | `backend/app/api/auth.py:93-143` | n/a (Bearer) | `204 No Content` | `INSERT revoked_tokens(jti, user_id, expires_at)`; `IntegrityError` swallowed via `rollback` (idempotent re-logout, `auth.py:137-141`) |
| W07 | `POST /api/auth/change-password` | `backend/app/api/auth.py:152-185` | `ChangePasswordRequest` `{current_password, new_password}` defined inline (`auth.py:146-149`); `new_password ≥ 8` enforced in handler (`auth.py:173-177`) | `{"message": "Password changed successfully"}`, `200` | `UPDATE users SET password_hash=?, password_changed_at=now()` |
| W05 | `WS /ws/chat` (close `4001`) | `backend/app/api/websocket.py:92-462` | Bearer via `Sec-WebSocket-Protocol: bearer.<jwt>` (preferred); `?token=` query string still accepted with deprecation warning (`websocket.py:122-140`) | WS opens; on bad/missing/revoked/expired token closes with `4001` | `SELECT users WHERE id=?`, optional `SELECT revoked_tokens WHERE jti=?` |

**JWT issuance & claims** (`backend/app/core/security.py:46-66`)

| Claim | Value | Source |
|---|---|---|
| `sub` | `user.id` (UUID string) | `security.py:61` |
| `exp` | `now + ACCESS_TOKEN_EXPIRE_HOURS` hours | `security.py:58-59`; default `24` (`config.py:76`) |
| `iat` | `datetime.now(timezone.utc)` at issuance | `security.py:58, 63` |
| `jti` | `str(uuid.uuid4())` per token | `security.py:64` |

Signing: HS256 with `settings.SECRET_KEY` (`security.py:16, 66`). Decode in `decode_access_token` (`security.py:69-82`) with `jose.jwt.decode`; raises `JWTError` on bad signature, expiry, or malformed input.

**Password rules**

| Surface | Rule | Reference |
|---|---|---|
| Register, client | length ≥ 8 | `register/page.tsx:18-23, 36-39` |
| Register, server | `min_length=8` via Pydantic | `backend/app/models/schemas.py:16` |
| Login | none (length unconstrained server-side) | `schemas.py:19-23` |
| Change password, client | length ≥ 8, new ≠ confirm enforced | `AccountSettings.tsx:40-47` |
| Change password, server | length ≥ 8 (manual check, `400` on fail) | `backend/app/api/auth.py:173-177` |
| Hash function | `bcrypt.hashpw` with `bcrypt.gensalt()` | `backend/app/core/security.py:19-30` |
| Verify | `bcrypt.checkpw` | `security.py:33-43` |

**Auth dependency** (`backend/app/core/dependencies.py`). All authenticated HTTP endpoints depend on `get_current_user` (`dependencies.py:153-178`), which composes:

1. `_decode_and_load_user` — verifies JWT signature/expiry/`sub` claim, loads `User` (`dependencies.py:43-69`).
2. **Per-token revocation gate** — `if jti and is_token_revoked(jti, db): 401 "Token has been revoked"` (`dependencies.py:137-143`). `is_token_revoked` is a single source of truth at `backend/app/core/security.py:85-110`; queries `revoked_tokens.jti`.
3. **Blanket revocation gate** — `_check_password_change_revocation`: if `user.password_changed_at` is not null and `int(payload["iat"]) < int(password_changed_at.timestamp())`, raise `401 "Token has been revoked"` (`dependencies.py:72-111`). Comparison is at whole-second resolution because `jose` serialises `iat` as `int(timestamp())` — same-second tokens are intentionally accepted (`dependencies.py:80-87`).
4. **Lazy GC** — `_maybe_run_lazy_gc` calls `cleanup_expired_revocations` with `random.random() < 0.001` probability (`dependencies.py:114-121`, `backend/app/models/revoked_token.py:43-61`).

A second variant `get_user_for_logout` (`dependencies.py:181-202`) is used **only** by `POST /api/auth/logout` so that re-logging-out with an already-revoked token returns `204` instead of `401`. It still applies the password-change blanket revocation.

**Token revocation (W06 — `POST /api/auth/logout` in `backend/app/api/auth.py:93-143`).**

1. The dependency `get_user_for_logout` decodes the JWT and returns `(user, payload)` (`auth.py:95`).
2. Handler reads `payload["jti"]` and `payload["exp"]` (`auth.py:110-111`).
3. Builds an aware-UTC `expires_at` from `exp` (`auth.py:121-127`).
4. `INSERT INTO revoked_tokens (jti, user_id, expires_at)` and commits (`auth.py:129-136`).
5. `IntegrityError` on duplicate `jti` is caught and rolled back to make the call idempotent (`auth.py:137-141`).
6. Returns `204 No Content`.

After step 4, every subsequent HTTP request presenting the same JWT will fail the per-`jti` gate in `get_current_user` (`dependencies.py:137-143`). The WS path enforces the same gate on the open handshake and on per-message re-validation (see below).

**Per-message WebSocket re-validation (infra hardening, `backend/app/api/websocket.py:34-89, 280-286`).** This is the merge-kept hardening from the infra branch. `_authenticate_token` (`websocket.py:34-89`) mirrors `get_current_user`'s revocation logic but returns `None` instead of raising:

- decode JWT (`websocket.py:52-55`),
- look up user (`websocket.py:61-63`),
- check `is_token_revoked(jti)` (`websocket.py:66-68`),
- enforce `iat ≥ int(password_changed_at.timestamp())` at whole-second precision (`websocket.py:74-87`).

It runs at two points:

| When | Location | Effect on failure |
|---|---|---|
| WS open / handshake | `websocket.py:164-174` (calls `_authenticate_token`) | `close(4001)` reasons: `"Invalid or expired token"`, `"Authentication error"` |
| Before processing every `user_message` | `websocket.py:280-286` | `close(4001, "Token expired")` and `return` (loop exits) |

This per-message gate is what catches a `POST /api/auth/logout` (or a `/change-password` blanket-revoke) issued mid-session: the next `user_message` sees `_authenticate_token → None` and the socket closes 4001, which the frontend handles in W05.

**Gap (verified, not invented):** the per-message re-validation runs for `user_message` only. The handlers for `run_pipeline` (`websocket.py:210-240`), `cancel_pipeline` (`websocket.py:243-262`), and `generate_questions` (`websocket.py:265-269`) reach the dispatch site **before** the re-validation block at line 280 and `continue` past it — so a revoked token still drives a long-lived pipeline started over an existing connection. The pipeline is spawned as a background task (`asyncio.create_task` at `websocket.py:234-239`) which receives the user object captured at WS open, not a fresh one. [VERIFY: by integration test — there is no `test_websocket.py` covering this path; coverage is via `tests/unit/test_logout.py` for the HTTP side only.]

**Password change side-effects (W07 — `backend/app/api/auth.py:152-185`).**

1. `get_current_user` runs both revocation gates against the presented JWT (so a logged-out or password-already-rotated token can't be used to change password).
2. Verify `current_password` via `verify_password` (`auth.py:166-170`); `401 "Current password is incorrect"` on mismatch.
3. `len(new_password) < 8` → `400` (`auth.py:173-177`).
4. `current_user.password_hash = hash_password(new_password)`; `current_user.password_changed_at = datetime.now(timezone.utc)` (`auth.py:181-182`); commit.
5. Returns `{"message": "Password changed successfully"}` with `200`.

Setting `password_changed_at` blanket-revokes every JWT this user previously held without enumerating them — the next time any of those tokens hits `get_current_user` or `_authenticate_token` the `iat < password_changed_at` check rejects (`dependencies.py:105-111`; `websocket.py:74-87`). Coverage: `backend/tests/unit/test_logout.py::TestPasswordChangeRevocation::test_change_password_revokes_old_tokens` (`test_logout.py:184-216`) — verifies old token → 200 → password change → old token → 401 → new login → new token works.

**`SECRET_KEY` boot guard** (`backend/app/core/config.py:46-137`). `Settings._validate_secret_key` (model validator, `config.py:92-137`) refuses to boot when:

- `SECRET_KEY` is empty (any `ENV`) — raises `SecretKeyMisconfigured` (`config.py:103-107`).
- `SECRET_KEY == "dev-secret-key-change-in-production"` and `ENV != "development"` (`config.py:109-122`).
- `len(SECRET_KEY) < 32` and `ENV != "development"` (`config.py:124-135`).

In `ENV=development` the default and short keys log a warning but boot proceeds (`config.py:111-115, 126-128`). Coverage: `backend/tests/unit/test_secret_key_guard.py` — 8 cases including production-default-aborts, staging-default-aborts, dev-default-warns-only.

**`AuthResponse` shape returned by W02/W03.** `{token: str, user: {id: str, email: str}}` per `backend/app/models/schemas.py:35-39`. The frontend `setToken(data.token)` stores `token` into `localStorage["auth_token"]` (`api.ts:113, 126`), and `Authorization: Bearer <token>` is applied via `authHeaders()` (`api.ts:95-100`).

**Cross-section pointer.** Logout from the WS side (close `4001`) is described under W05; the matching backend trace is the per-message re-validation block above. The pipeline-task-keeps-running-after-revocation gap is documented as an out-of-scope finding below — it does not affect the W01–W07 surface but is worth flagging.

### B2 — WebSocket protocol & event routing

**Endpoint.** `/ws/chat` (`api/websocket.py:92`). Auth is via the `Sec-WebSocket-Protocol` header — the client offers `["bearer.<jwt>", "flowin.v1"]` (`useWebSocket.ts:98`) and the server echoes `"flowin.v1"` after extracting the JWT from the `bearer.` entry (`websocket.py:123-158`). A transitional `?token=<jwt>` query parameter is still accepted but logs a deprecation warning (`websocket.py:133-140`).

**Auth gates.**
1. Initial handshake — `_authenticate_token` (`websocket.py:34-89`) on accept. Bad/missing/revoked/expired → `close(4001)` (`:145, :168`).
2. Per-message — `_authenticate_token` is called **again before every `user_message`** (`websocket.py:283`), but **not** before `run_pipeline`/`cancel_pipeline`/`generate_questions` (the long-lived pipeline runs are protected only by the open-time check + token revocation via /logout being honoured on the next chat send).
3. Internal error after accept → `close(1011)` (`:460`).

**Token revocation honoured at WS layer.** `_authenticate_token` checks `is_token_revoked(jti, db)` for explicit logout (`websocket.py:66-68`) and `password_changed_at > iat` for password rotation (`:71-87`). Both close 4001 on the next per-message validation.

**Connection state.** Per-connection: a `current_pipeline_task: asyncio.Task | None` is held in the closure (`websocket.py:184`) so the cancel handler can call `task.cancel()`. A fresh `SessionLocal()` is opened per side-effect block and immediately closed (e.g. `:164, :281, :337, :493`). `WorkflowRun` rows are created at run start (`:494-506`) and updated at completion/failure/cancellation. At most one pipeline per WS connection — overlapping `run_pipeline` is rejected (`:216-227`).

**Disconnect cleanup.** On `WebSocketDisconnect` (`websocket.py:438-450`) and on any other exception (`:451-462`), the handler cancels the in-flight pipeline task and awaits it. The task's own `CancelledError` handler (in `_handle_pipeline_execution`) marks the `WorkflowRun` as `cancelled` and best-effort sends `pipeline_cancelled` (the send may fail because the WS is gone — caught and ignored).

#### Inbound message catalog

All inbound frames are top-level JSON with at least a `type` field.

| `type` | Required fields | Optional fields | Handler | Notes |
|---|---|---|---|---|
| `run_pipeline` | `pipeline_type` (str), `message` or `content` (str) | `agent_ids: list[str]`, `chat_session_id: str` | `websocket.py:210-240` → `_handle_pipeline_execution` (`:465-720`) | Spawns a background `asyncio.Task`, sent over `current_pipeline_task`. Returns 400 error frame `pipeline_already_running` (`recoverable:true`) when a task is in-flight (`:216-227`). |
| `cancel_pipeline` | — | — | `websocket.py:243-262` | Calls `current_pipeline_task.cancel()` if running. If nothing is running, sends an idempotent `pipeline_cancelled` ack immediately (`:256-261`). Never sends an ack while a real task is being cancelled — that ack is emitted by the task itself once it processes `CancelledError`. |
| `generate_questions` | `pipeline_type` (str), `message` or `content` (str) | — | `websocket.py:265-269` → `_handle_questionnaire` (`:723-778`) | Runs the `QUESTIONNAIRE_AGENT` synchronously (awaited, not background), parses the JSON, emits `questionnaire`. |
| `user_message` | `content` (str), `chat_session_id` (str) | `mode: "default"\|"thinking"\|"deep_research"\|"web_search"\|"quiz"` (default `"default"`) | `websocket.py:271-436` | Persists user message, optionally auto-generates chat title, then streams via `AgentOrchestrator.astream_execute`. |

Anything else — including malformed JSON — produces an `error` frame with `data.error = "Invalid message format..."` (`:271-278`) or `"Invalid JSON message"` (`:195-200`). The connection is **not** closed; the loop continues.

#### Outbound message catalog

All outbound frames share the wire-format wrapper `{type, chunk, section, data}`. For pipeline events, `section = pipeline_type` and the body lives entirely in `data` (`websocket.py:577-582`); the frontend flattens this in `dashboard/page.tsx:77-80` before forwarding to the workflow hook. For chat events, `chunk` carries the streaming text and `section` carries the phase name.

| `type` | Emitted at | Payload (`data` keys unless noted) |
|---|---|---|
| `pipeline_start` | `orchestrator_v2.py:250-260` (via WS `:577`) | `pipeline_type, agent_count, agents:[{id, name, role, icon, order}]` |
| `agent_start` | `orchestrator_v2.py:274-284` | `agent_id, name, role, icon, index, total` |
| `agent_thinking` | `orchestrator_v2.py:303-309, :352-358` | `agent_id, thinking` (status text or "retrying (n/2)") |
| `agent_chunk` | `orchestrator_v2.py:328-334` | `agent_id, chunk` (one frame per LangChain text delta) |
| `agent_complete` | `orchestrator_v2.py:381-391` | `agent_id, name, duration, output_length, index, total` (no `output` — frontend rebuilt from `agent_chunk`s) |
| `agent_error` | `orchestrator_v2.py:399-402` (config), `:408-416` (transient) | `agent_id, error, recoverable[, duration]` — config errors are `recoverable:false` and abort the loop |
| `pipeline_complete` | `orchestrator_v2.py:431-440` | `pipeline_type, total_duration, agents_completed, agents_total, final_output` |
| `pipeline_cancelled` | `websocket.py:256-261` (no-op cancel), `:633-642` (real cancel) | `message[, agents_completed, duration]` |
| `title_update` | `websocket.py:346-351` | `chat_session_id, title` |
| `questionnaire` | `websocket.py:748-770` | `questions: [{id, question, options:[str,str,str,str]}]` — empty list on parse failure or no API key |
| `phase_start` | `orchestrator.py:319, :355, :400` | `phase, name?` (chat-only) |
| `phase_end` | `orchestrator.py:352, :384, :438` | `phase` (chat-only) |
| `stream` | `orchestrator.py:325, :361, :406` | top-level `chunk` (text delta), `section` set to phase name |
| `complete` | `orchestrator.py:445` (chat) | `data: FinalOutputModel` |
| `error` | `websocket.py:195-200, :216-226, :271-277, :298-305, :378-386, :391-403, :533-545, :649-660` | `error, code?, recoverable?` |

**Error `code` enumeration (from `app/agents/llm_errors.py:50-68, 120-126`):** `api_key_missing` (recoverable false), `auth_error` (false), `rate_limit` (true), `timeout` (true), `connection_error` (true), `internal_error` (true). Also surfaced from the WS handler directly: `pipeline_already_running` (true, `:222`), `llm_provider_misconfigured` (false, `:542`), `pipeline_error` (true, `:657`). Validation errors and JSON-parse failures arrive without a `code` field.

**Streaming model.** `ChatBedrockConverse.astream()` yields one chunk per Bedrock text delta. The orchestrator forwards each as a separate `agent_chunk`/`stream` frame — no batching, no flow control. A transient `RemoteProtocolError`/`ReadTimeout`/chunked-encoding error gives up to 2 retries with a 2 s sleep (`orchestrator_v2.py:340-361`). Each retry restarts the agent from scratch and resets `output_chunks` — already-streamed chunks for that retry attempt are not deduped on the client; this is a known ordering quirk.

> **Wire-format mismatch (carried over).** The frontend still references a `step` message type for `ProcessSteps` (`dashboard/page.tsx:283`) but the backend emits **no `step` frames** — the orchestrators emit `phase_*`/`stream`/`complete` for chat and `agent_*`/`pipeline_*` for workflows. The `step` branch is dead frontend code.

---

### B3 — Chats / Sessions / Messages backend trace

**Schema (`backend/app/models/chat.py:12-49`)**

```
chat_sessions (
    id            String PK (uuid4)                              # :17
    user_id       String FK→users.id NOT NULL                    # :18
    title         String NOT NULL DEFAULT "New Chat"             # :19
    last_activity DateTime NOT NULL DEFAULT now(utc)             # :20-22
    created_at    DateTime NOT NULL DEFAULT now(utc)             # :23-25
    final_output  Text NULL                                      # :26
)

messages (
    id              String PK (uuid4)                            # :39
    chat_session_id String FK→chat_sessions.id NOT NULL          # :40-42
    role            String NOT NULL  ("user"|"assistant"|"system") # :43
    content         Text NOT NULL                                # :44
    created_at      DateTime NOT NULL DEFAULT now(utc)           # :45-47
)
```

- **No `ON DELETE CASCADE`** on the FK in either table — `models/chat.py:18, :40-42`. Deletion is a two-step delete in the API (`api/chats.py:155-157`).
- **No soft-delete column** — `DELETE /api/chats/{id}` is a hard delete of the messages then the session.
- `ChatSession.messages` relationship is ordered by `Message.created_at` (`models/chat.py:30`).
- `final_output` is a `Text` column whose payload is a JSON-serialized `FinalOutputModel` (`schemas.py:80-92`, 10 optional keys). Written only by the WS handler (`api/websocket.py:432-433`) when the orchestrator yields `{type:"complete"}` — never written by the REST routes.

**REST endpoints (`backend/app/api/chats.py:16`, prefix `/api/chats`)**

| Method+Path | Handler `file:line` | Request body | Auth | DB ops | Response | Notes |
|---|---|---|---|---|---|---|
| POST `/api/chats` | `chats.py:51-71` | `CreateChatRequest {title?: str}` (`:22-25`) | `get_current_user` | `INSERT chat_sessions (user_id, title)` then refresh | `201` `ChatSessionResponse` (`schemas.py:57-65`) | Empty body allowed (default-arg `CreateChatRequest()` at `:53`). If `title` is None/empty, defaults to `"New Chat"` (`:61`). |
| GET `/api/chats` | `chats.py:74-89` | – | `get_current_user` | `SELECT chat_sessions WHERE user_id=? ORDER BY last_activity DESC` (no offset/limit) | `200` `list[ChatSessionResponse]` | **No pagination params**, no `limit` parameter — caller receives every session for the user. `messages` and `final_output` are NOT included (use GET-by-id). |
| GET `/api/chats/{chat_id}` | `chats.py:92-129` | – | `get_current_user` | `SELECT chat_sessions WHERE id=? AND user_id=?` then iterates `chat_session.messages` (eager via relationship) | `200` `ChatSessionDetailResponse` (`:35-45`, includes `messages: list[MessageResponse]` and `final_output: str | None`) | 404 on miss-or-cross-user (`:107-111`). |
| PUT `/api/chats/{chat_id}/messages` | `chats.py:162-196` | `AddMessageRequest {content: str, role: str = "user"}` (`:28-32`) | `get_current_user` | `INSERT messages (chat_session_id, role, content)` + `UPDATE chat_sessions SET last_activity=now()` | `201` `MessageResponse` (`schemas.py:45-54`) | 404 if chat not owned by user. Caller controls `role` — backend does not validate role enum. **Frontend `addMessage` (`lib/api.ts:214-225`) exposes this, but the live dashboard never calls it — all message persistence flows through the WS path described below.** |
| DELETE `/api/chats/{chat_id}` | `chats.py:132-159` | – | `get_current_user` | `DELETE FROM messages WHERE chat_session_id=?` then `DELETE FROM chat_sessions WHERE id=?` | `204` | Two-step manual cascade (`:155-157`). 404 on miss-or-cross-user. |

There is **no `/api/messages` router**: `backend/app/api/messages.py` does not exist. Messages are managed only via `/api/chats/{id}` (read) and `/api/chats/{id}/messages` (append).

**Pagination & limits.** None. `GET /api/chats` returns the full per-user list (`chats.py:83-88`) — there is no `limit`, `offset`, `before`, or `after` query parameter. Messages inside a session are returned all-at-once by `GET /api/chats/{id}` (`chats.py:118-127`) — no message-level pagination. Practical risk: a long-running user with many sessions or one long session receives unbounded payloads.

**Title generation flow (WebSocket-side, not REST).** Triggered by the first user message of a session under three conditions (`api/websocket.py:317`):
1. `chat_session.title == "New Chat"` (the default), or
2. `chat_session.title == ""`, or
3. `chat_session.title == content[:50]` (matches a title that the client set to a prefix of its first message — see `dashboard/page.tsx:334, 388` where `createChat(content.slice(0, 50))` is the auto-create path).

When `needs_title` is true the handler (`websocket.py:322-353`) spins up a `BaseAgent` with a fixed system prompt ("Generate a very short title (3-5 words max)…", `:328-330`), runs it via `title_agent.run(content)` on the user's first message, sanitises the result (`strip().strip('"').strip("'").strip(".")[:60]`, `:335`), writes it back with a fresh session (`db2`, `:337-344`), and emits `{type:"title_update", data:{chat_session_id, title}}` over the WS (`:346-351`). Failures are caught and logged at warning level (`:352-353`) — the chat keeps its original title.

**W42 → W44 lifecycle (send → receive streaming, the only path that writes messages in production).**

1. Client opens WS with `Sec-WebSocket-Protocol: bearer.<jwt>` (preferred, `websocket.py:122-130`) or `?token=<jwt>` (deprecated transitional, `:133-140`); server validates JWT incl. revocation + `password_changed_at` cutoff (`_authenticate_token`, `:34-89`).
2. `useWorkflow`/`ChatPanel` calls `useWebSocket.send(JSON.stringify({type:"user_message", content, chat_session_id, mode?}))`.
3. Server re-validates JWT on every message (`websocket.py:280-286`) — closes 4001 on expiry.
4. Server verifies chat session ownership (`:288-305`); 404-style error on mismatch.
5. **User message persisted before LLM call** (`INSERT messages role='user'`, `UPDATE chat_sessions.last_activity`, commit at `:307-318`). This is durable even if the orchestrator later fails.
6. If `needs_title` (above), fire-and-forget title-generator → `title_update` event (`:322-353`).
7. `AgentOrchestrator.astream_execute` (`agents/orchestrator.py:293-449`) yields `phase_start | stream | phase_end | error | complete` frames; each is relayed verbatim via `websocket.send_json` (`:373`). The handler collects `stream` chunks into `assistant_chunks` (`:371-372`).
8. On success path, the assistant message is persisted **at the end** of the stream (`:405-421`): a single `INSERT messages role='assistant'` with the joined chunks. **Streaming is NOT persisted incrementally** — if the connection drops mid-stream, no assistant row is written.
9. The `<!--steps:JSON-->` content prefix mechanism (`:413-415`) is **dead today**: `collected_steps` is initialized at `:357` but never appended to anywhere in this file (`grep -n "collected_steps" websocket.py` shows only init + read). The persisted content is therefore always raw `assistant_content`.
10. `chat_sessions.last_activity` is touched again (`:430`). If the *last* `stream_msg` was `{type:"complete", data: ...}`, `chat_sessions.final_output = json.dumps(stream_msg["data"])` (`:432-433`). If the last frame was an `error`, `final_output` is left unchanged.
11. On `WebSocketDisconnect` (`:438-450`), an in-flight pipeline task is cancelled and awaited; no separate message-flush occurs for the chat path because the chat path is fully synchronous within the receive loop (it does not run via `asyncio.create_task`).

**Artifact materialisation for chat.** Artifacts (`ppt`, `prototype`, `user_stories`, etc.) live inside `chat_sessions.final_output` as JSON keys (`schemas.py:80-92`); they are **not** separate rows. The front-end re-derives `userStoryContent` / `pptContent` / `prototypeContent` from `final_output` each time a chat is loaded (`dashboard/page.tsx:465-484`).

**Ownership & isolation checks.** All four chat endpoints filter on `ChatSession.user_id == current_user.id` (`chats.py:84-85, 103-105, 144-146, 173-176`). Cross-tenant access yields 404 to avoid leaking session-id existence. The WS path performs the same ownership check at `websocket.py:288-305`.

**Identified gaps**

| Gap | File:line | Risk | Suggestion |
|---|---|---|---|
| No DB-level CASCADE on `messages.chat_session_id` or `chat_sessions.user_id` FKs | `models/chat.py:18, :40-42` | Manual cascade is required (`api/chats.py:155-157`); a future direct user-delete (none today) would orphan rows | Add `ondelete="CASCADE"` to the `ForeignKey` declarations |
| `GET /api/chats` returns the entire per-user list | `api/chats.py:74-89` | Unbounded payload on heavy-user accounts | Add `limit`, `offset` (or `cursor`) query params |
| `GET /api/chats/{id}` returns all messages in one shot | `api/chats.py:113-127` | Unbounded payload on long sessions | Add per-message pagination, or split history into a separate endpoint |
| Assistant message persisted only at end of stream | `api/websocket.py:405-421` | Mid-stream disconnect loses the partial assistant reply (the user message is already persisted from step 5) | Either stream-write chunks, or write a placeholder on `phase_start` and update on completion |
| `<!--steps:` content prefix is dead code | `api/websocket.py:357 init, :413-415 use, never appended` | Frontend parser at `dashboard/page.tsx:446-452` still runs on every load — harmless but stale | Remove the dead embed, or wire `step` events into `collected_steps` |
| `workflow_title_update` event handled on the frontend but never emitted by the backend | `frontend/src/app/dashboard/page.tsx:265-274` vs. zero backend matches | Dead code path; potential confusion when adding the feature | Either emit the event from `_handle_pipeline_execution` or drop the FE handler |
| `PUT /api/chats/{id}/messages` accepts arbitrary `role` strings | `api/chats.py:184-188`, schema `:32` | Caller can insert `role="system"` or anything else | Constrain via `Literal["user","assistant","system"]` |
| No `idempotency_key` on POST `/api/chats` or PUT `…/messages` | n/a | A retry on flaky network can dup-insert | Optional, but worth tracking for future |

### B4 — Workflow-runs backend trace

**Schema** (`backend/app/models/workflow.py:12-33`)

```
workflow_runs (
  id            String PK   default=uuid4()
  user_id       String FK → users.id  NOT NULL  (no ondelete)
  title         String      NOT NULL default="Untitled"
  type          String      NOT NULL              -- see types below
  status        String      NOT NULL default="running"
  input         Text        NOT NULL
  output        Text        NULL
  agent_outputs Text        NULL   (JSON-encoded list, see shape below)
  agent_count   Integer     NOT NULL default=0
  duration      Float       NULL   (seconds, rounded to 1 dp)
  error         Text        NULL
  created_at    DateTime    NOT NULL default=now()
  completed_at  DateTime    NULL
)
```

- **Types** the model accepts: any string. The POST `/api/workflows`
  endpoint hard-validates only `{"user_stories", "ppt", "prototype"}`
  (`workflows.py:72-77`); the WS pipeline writer accepts whatever
  `pipeline_type` the client sent (`websocket.py:498`), so frontend
  values like `app_builder`, `custom`, and any `*_revision` variant
  land in the DB unvalidated.
- **Status** values written in practice (from `websocket.py`):
  `"running"` (`:499`), `"completed"` (`:683`), `"failed"` (`:667`),
  `"cancelled"` (`:619`).
  **Note** the model's own comment (`workflow.py:21`,
  `# "running" | "completed" | "failed"`) is stale — it does not list
  `"cancelled"`. **The previous open issue "cancelled runs never reach
  a terminal status" is now resolved** (see "Status transitions" below).
- No CASCADE on `user_id`; no `chat_session_id` link (despite the WS
  handler holding both contexts at row-creation time).

**REST endpoints** (`backend/app/api/workflows.py`)

| Method+Path | Lines | Notes |
|---|---|---|
| POST `/api/workflows` | `:61-94` | Validates `type ∈ {user_stories, ppt, prototype}` (no `app_builder` / `prototype_revision` / `custom`); creates row with `status="running"`, default `agent_count=12` if omitted. **Currently unused by the frontend** — pipelines are started via the WS `run_pipeline` path which creates the row itself. Dead code from an earlier REST-first design. |
| GET `/api/workflows` | `:97-125` | Query params: `limit` (default 50), `offset` (default 0), `type`, `status_filter`. Filter is `user_id == current_user.id`; ordered `created_at DESC`. Returns full rows including `output` and `agent_outputs` (JSON string). |
| **POST `/api/workflows/export-pptx`** | **`:128-227`** | **NEW.** Server-side PPTX synthesis. Documented in full below. |
| GET `/api/workflows/{id}` | `:230-251` | Per-user filter; 404 cross-user or missing. |
| PATCH `/api/workflows/{id}` | `:254-293` | Updates any subset of `status`, `output`, `duration`, `error`. Auto-sets `completed_at = now()` when `status ∈ {"completed", "failed"}` (`:278-279`) — **does NOT include `"cancelled"`**, so this codepath would leave a cancelled row with `completed_at = NULL`. **Also unused** — the WS handler updates the row directly via SQLAlchemy and sets `completed_at` itself, so the gap doesn't surface in the live system. |
| DELETE `/api/workflows/{id}` | `:296-321` | Per-user only; returns 204 No Content. |

**POST `/api/workflows/export-pptx` — full surface** (`workflows.py:128-227`)

Generates a `.pptx` binary from Agent 3's PptxGenJS code by spawning a
Node.js subprocess that loads `pptxgenjs` and runs `generatePresentation()`.

- **Auth:** `Depends(get_current_user)` — JWT required.
- **Request body** (`request: dict`, free-form JSON — not Pydantic-validated):
  ```
  {
    "js_code":      string | omitted,   // Agent 3's raw JS (highest precedence)
    "workflow_id":  string | omitted,   // pulls Agent 3 output from agent_outputs JSON
    "html":         string | omitted,   // full HTML to scrape generatePresentation() out of
    "title":        string | omitted    // default "Presentation"
  }
  ```
  At least one of `js_code`, `workflow_id`, or `html` must yield code; if
  all three fail the endpoint returns 400.
- **Code-resolution strategy** (in order, `:152-207`):
  1. **`workflow_id` → DB.** Looks up `workflow_runs` row filtered by
     `id AND user_id == current_user.id` (`:154-157`), JSON-decodes
     `agent_outputs`, finds the first agent whose `agent_id` contains
     `"code"`, `"generator"`, or `"ppt-code"` (`:163`), and takes its
     `output`. Cross-user `workflow_id` silently falls through (no row
     found ⇒ next strategy), it does **not** 403.
  2. **HTML scrape, script tags first.** Regex-extracts `<script>`
     contents, then runs a brace-matched scan for `function generatePresentation(...) { ... }` (`:173-189`).
  3. **HTML scrape, raw body.** Same brace-matched scan over the entire
     `html` string (`:192-206`).
- **Generation** (`pptx_export.generate_pptx_from_code`,
  `services/pptx_export.py:40-179`):
  1. Strips ```` ```javascript ```` / ```` ``` ```` fences.
  2. Sanitises common LLM corruption patterns:
     `color: "#RRGGBB"` → `color: "RRGGBB"`,
     8-char hex → 6-char,
     negative shadow offsets → positive,
     stray `.line.` property accesses commented out
     (`:54-71`).
  3. Replaces `pres.writeFile(...)` and `pres.save(...)` calls with
     `return pres.write("nodebuffer")` (`:74-80`).
  4. Forces the function to `async` if it isn't (`:83-84`), and wraps
     loose code in `async function generatePresentation()` if no
     function declaration was found (`:87-88`).
  5. Writes the wrapped script to `tempfile.mkdtemp(prefix="pptx_export_")`
     and executes `node <file>` with **a 30-second subprocess timeout**
     (`:159`). On crash the embedded fallback emits a single-slide
     "Export error: ..." `.pptx` so the user gets *something* back
     (`:115-123`).
  6. Reads the output file, deletes the temp directory in `finally`,
     returns `bytes`.
- **Response:**
  - Success → `200 OK`, `Response(content=pptx_bytes, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", headers={"Content-Disposition": 'attachment; filename="<title-spaces-to-underscores-truncated-to-40-chars>.pptx"'})` (`:222-227`).
- **Error modes:**
  - **400** "Could not find PptxGenJS code. Try re-running the pipeline." — all three resolution strategies failed (`:208-212`).
  - **500** "Failed to generate PPTX: \<first 200 chars of exception\>" — `generate_pptx_from_code` raised. Includes Node-subprocess failures: missing `pptxgenjs` install, syntax errors that survived sanitisation, and **the 30s timeout** (which surfaces as `subprocess.TimeoutExpired` → `RuntimeError` → 500) (`:214-220`, `pptx_export.py:157-165`).
  - **401** — invalid/expired JWT (handled by `get_current_user`).
- **Resource caps:**
  - **Subprocess wall-clock cap: 30 s** (`pptx_export.py:159`).
  - **Request-body cap:** none enforced at the endpoint or app layer
    `[VERIFY: confirm against any uvicorn/nginx reverse-proxy limit in the deployed environment]`.
  - **Output-size cap:** none — the full `bytes` payload is loaded into
    memory and returned in a single `Response`.
- **`pptxgenjs` resolution at import time** (`pptx_export.py:28-37`):
  1. `PPTX_NODE_MODULES_DIR` env var (explicit override),
  2. `/opt/pptx/node_modules` (production Docker — pre-populated by
     the `pptx-builder` stage of `backend/Dockerfile`),
  3. `<repo>/frontend/node_modules` (local-dev fallback).
- **Callers:**
  - `frontend/src/components/preview/PPTPreview.tsx:53` (live-preview "Download PPTX" button — passes `js_code`, `html`, `workflow_id`, `title`).
  - `frontend/src/components/results/FilesTab.tsx:160` (history "Files" tab — passes `html`, `workflow_id`, `title`; does **not** send `js_code`, so backend always falls back to strategy 1 or 2).

**Authoritative writer.** All non-export row mutations happen inside
the WS handler `_handle_pipeline_execution`
(`backend/app/api/websocket.py:465-720`):

| Phase | Lines | Writes |
|---|---|---|
| **insert** (pipeline start) | `:493-507` | `status="running"`, `title = (content or "Untitled")[:60].strip()`, `type = pipeline_type` (uncapped), `input`, `agent_count` (12 for `user_stories`, 4 for `ppt`, 12 for `prototype`, `len(agent_ids)` if custom — `:484-489`). |
| **success** | `:678-691` | `status="completed"`, `output=final_output` (or `NULL` if empty string), `agent_outputs=json.dumps(agent_outputs_collector)` (or `NULL` if empty list), `completed_at=now()`, `duration=round((now() - execution_start).total_seconds(), 1)` — **wall-clock** delta. |
| **failure** (orchestrator exception) | `:661-674` | `status="failed"`, `error=str(exc)`, `completed_at=now()`, `duration=round((now() - execution_start).total_seconds(), 1)` — wall-clock. Partial `agent_outputs` are **not** persisted on this path. |
| **cancellation** (`asyncio.CancelledError` from `cancel_pipeline` *or* `WebSocketDisconnect` cleanup) | `:604-648` | `status="cancelled"`, `completed_at=now()`, `duration=round(time.monotonic() - monotonic_start, 1)` — **monotonic** delta, taken from the dedicated `monotonic_start` clock at `:573`. `agent_outputs` is persisted **only if any agents finished** (`:625-626`). `error` is **left NULL** (this is what makes the frontend's `run.error === "Cancelled by user"` check fail in W18). After persistence, a best-effort `pipeline_cancelled` event is sent to the WS, then the `CancelledError` is re-raised so the asyncio task lands in `cancelled` state. |

**`agent_outputs` JSON shape** (collected in `websocket.py:583-601`):

```json
[
  {
    "agent_id": "domain-analyst",
    "name":     "Domain Analyst",
    "role":     "...",
    "icon":     "...",
    "thinking": "<full thinking text streamed during agent_thinking events>",
    "output":   "<concatenated agent_chunk payloads>",
    "duration": 12.3   // seconds, from the agent_complete event; null if cancelled mid-agent
  },
  ...
]
```

- Built up live during pipeline streaming: `agent_start` initialises
  the dict, `agent_thinking` populates `thinking`, `agent_chunk` appends
  to `output`, `agent_complete` finalises `duration` and pushes onto the
  collector. The in-flight (partial) dict is **not** pushed if the
  pipeline is cancelled mid-agent — only fully-completed agents survive.
- The frontend reads this back via `WorkflowHistory.tsx:131-135` and
  renders it in the agent breakdown sidebar (W19); the API normaliser
  (`api.ts:267-289`) deserialises it once on the client.

**Authorization.** All HTTP endpoints filter by
`user_id == current_user.id` (`workflows.py:111, 156, 242, 267, 309`).
The WS pipeline persists `user_id = user.id` from the validated JWT
(`websocket.py:496`). The export-pptx workflow-id resolution path also
applies the per-user filter (`workflows.py:156`), so a malicious client
cannot use someone else's `workflow_id` to extract `agent_outputs`.

**Status transitions** (terminal states are reached **only** through the
WS handler in normal operation; `PATCH` is dead code):

```
                                    ┌──────────────────► completed   (success)
                                    │
   (POST or WS insert) ──► running ─┼──────────────────► failed      (orchestrator raise)
                                    │
                                    └──────────────────► cancelled   (asyncio cancel
                                                                       from cancel_pipeline
                                                                       or WS disconnect)
```

`completed_at` is set on every terminal transition by the WS handler.
The `PATCH` endpoint (unused) only auto-sets `completed_at` for
`completed | failed` (`workflows.py:278-279`) — if it were ever wired
up to drive cancellation it would leave a NULL `completed_at`.

**Open issues**:
- **(carried over)** `agent_count` is hard-coded at insert time
  (`websocket.py:484-489, 501`) and never reconciled, so a pipeline that
  finishes with fewer agents than expected (e.g. early failure) leaves
  a misleading `agent_count`.
- **(carried over)** No `chat_session_id` linkage is persisted on
  `workflow_runs`, so deleting a chat orphans its related runs.
- **(new)** The frontend `WorkflowStatus` type
  (`frontend/src/types/index.ts:188`) does not include `"cancelled"`,
  and the cancel-detection heuristic in `WorkflowHistory.tsx:398`
  (`run.error === "Cancelled by user"`) never matches reality —
  the backend writes `wr.status = "cancelled"` but leaves `wr.error`
  NULL. Net effect: cancelled runs render as "Running" in W18 badges.
- **(new)** `duration` for cancelled runs is monotonic (`time.monotonic`)
  but for success/failure it's wall-clock (`datetime.now()` delta) —
  the two can disagree under clock skew. Both are rounded to 1 decimal
  place.
- **(new)** The unused `PATCH` endpoint's terminal-status whitelist
  doesn't include `"cancelled"` — a latent inconsistency with the WS
  handler that would surface if the REST path were ever revived.

---

### B5 — Pipeline orchestration backend trace

**Module:** `backend/app/agents/orchestrator_v2.py` (450 lines). Replaces the deleted `backend/app/agents/pipeline.py` (the legacy `PipelineExecutor`). The single entry point is `WorkflowOrchestrator`.

**Constructor.** `WorkflowOrchestrator(pipeline_type, custom_agents=None, db_session=None, user_id=None)` (`orchestrator_v2.py:174-192`).

| Arg | Behaviour |
|---|---|
| `pipeline_type` | Pipeline key (e.g. `"ppt"`, `"user_stories"`, `"ppt_revision"`). Stored verbatim; `is_revision` is `True` iff the key is in `REVISION_TYPES`; `base_pipeline_type` strips the `_revision` suffix via `REVISION_BASE_MAP` (`:68-76`). |
| `custom_agents` | Optional `list[AgentDefinition]`. If supplied, used in-order as the pipeline (no re-sorting). If `None`, the orchestrator calls `get_pipeline_agents(pipeline_type)` (`:188`) which sorts the registry list by `order`. |
| `db_session` | Currently unused inside the orchestrator — kept on the instance but no code path reads it. The legacy `pipeline.py` used it for revision context fetches; that responsibility has shifted to the WS handler / front-end which now ships the previous output inside the user message itself. `[VERIFY: confirm no future revision code path needs it]` |
| `user_id` | Passed through to `_load_skills` → `get_skill_content(user_id=...)`. This is **the** per-user skill resolution. Before the refactor, the WS handler assembled the skills dict inline by name lookup; now the orchestrator owns it (`:194-210`). |

**`REVISION_BASE_MAP`** (`orchestrator_v2.py:68-73`)

| Revision type | Base type |
|---|---|
| `ppt_revision` | `ppt` |
| `user_stories_revision` | `user_stories` |
| `prototype_revision` | `prototype` |
| `app_builder_revision` | `app_builder` |

Each maps to a 1- or 2-agent pipeline in `registry.py` — see §B6 table.

**`execute(user_message, cancel_event=None) -> AsyncGenerator[dict, None]`** (`orchestrator_v2.py:222-440`).

1. Build a `WorkflowState` (`:234-239`) containing the cleaned user request, pipeline metadata, `agent_outputs: dict[str, str]`, `results: list[dict]`.
2. `_load_skills()` (`:242`) — iterates `self.agents` and calls `get_skill_content(agent_def.id, user_id=self.user_id)` for each; only stores entries where content is non-None. PPT pipeline agents (`ppt-code-generator`, `ppt-slide-architect`, `ppt-content-strategist`, `ppt-assembler`) get the `backend/pptx/*.md` shipped reference docs injected via this same call (skills.py §B6).
3. Yield `pipeline_start` (`:250-260`).
4. **Per-agent loop** (`:263-418`):
   a. Pre-flight `cancel_event.is_set()` check (`:267-269`). Skips the rest of the pipeline if set.
   b. Yield `agent_start`.
   c. Build the prompt:
      - `system_prompt = skill_content + "\n\n" + agent_def.system_prompt` if a skill is loaded for this agent (`:288-290`); otherwise just the raw prompt.
      - Build the context message via `_build_agent_context` (`:83-160`). Strategy varies by pipeline:
        - **Revision pipelines** (`:94-108`): agent 0 sees only the raw user request (which the frontend has stuffed with `=== EXISTING ... === REVISION REQUEST ===` blocks). Agent 1 (assembler) gets the revised output truncated to 60 KB.
        - **PPT** (`:111-133`): agent 3 (assembler) sees only Agent 2's PptxGenJS code (truncated to 60 KB). Agent 2 (code generator) sees content strategist + slide architect (each truncated to 12 KB). Agent 1 (slide architect) sees the content strategist truncated to 8 KB.
        - **Prototype** (`:136-151`): polisher/finalizer (`index >= 2`) sees only the immediately previous agent's HTML (truncated to 50 KB). HTML builder (`index == 1`) sees the UX plan truncated to 8 KB.
        - **Default** (any other pipeline, including `user_stories`, `app_builder`, `reverse_engineer`, `custom`) (`:154-158`): all previous agent outputs, each truncated to 8 KB, concatenated.
   d. Yield `agent_thinking` ("Processing with context from N previous agents…").
   e. **Streaming with retry** (`:312-361`): up to 3 attempts (`max_retries = 2` plus the initial). On each attempt:
      - Cancellation check before stream (`:317-318`).
      - `BaseAgent(system_prompt, max_tokens=agent_def.max_tokens).astream(context_message)`.
      - Cancellation check inside the chunk loop (`:323-325`).
      - On transient error (`RemoteProtocolError`, `ReadTimeout`, chunked-encoding) and not last attempt: emit `agent_thinking` "Connection interrupted, retrying…", `await asyncio.sleep(2)`, retry.
      - On `CancelledError`: propagate (`:337-338`). This is the cooperative-cancellation path.
   f. Store `output_chunks` joined into `state.agent_outputs[agent_def.id]`; append a results dict for downstream persistence.
   g. Yield `agent_complete` with `duration` (server-measured) and `output_length`.
   h. Exception handling:
      - `AgentConfigurationError` (`:397-403`) — yields `agent_error{recoverable:false}` and **breaks the loop**. The remaining agents are skipped; `pipeline_complete` is still emitted with whatever was completed.
      - Generic `Exception` (`:405-418`) — yields `agent_error{recoverable:true}`, stores `"[Error: ...]"` as the agent's output (so context-builders for later agents see *something*), `continue`s to the next agent.
5. After the loop, yield `pipeline_complete` with `final_output = self._get_final_output(state)` = last agent's output string (`:442-446`).

**Cancellation behaviour (B5 update — previous "Cancellation gap" is closed).**

The WS handler keeps `current_pipeline_task` (`websocket.py:184`) and on `cancel_pipeline` calls `current_pipeline_task.cancel()` (`:252`). Inside `_handle_pipeline_execution` the `except asyncio.CancelledError` block (`websocket.py:604-648`):

1. Computes `duration = time.monotonic() - monotonic_start` (`:609`).
2. Sets `WorkflowRun.status = "cancelled"`, `completed_at = now`, `duration`, persists partial `agent_outputs` collected up to that point (`websocket.py:614-629`).
3. Best-effort sends `pipeline_cancelled` with `{message, agents_completed, duration}` (`:632-644`).
4. Re-raises `CancelledError` so the task reports `cancelled()` truthy (`:648`).

The orchestrator's two `CancelledError` shields are:
- `:337-338` inside the streaming retry block — always propagates, never retried.
- The branch-level `except` at `:393-395` which logs and re-raises.

Pipeline_cancelled emit on a closed WS swallows the failure (`websocket.py:643-644`); the DB write happens regardless.

**`cancel_event` parameter — dormant.** The `execute(user_message, cancel_event=None)` parameter (`orchestrator_v2.py:225`) is a cooperative cancellation hook that lets a caller signal cancellation without raising `CancelledError` through the task tree. The WS handler does **not** instantiate or pass one (it relies entirely on `task.cancel()` injecting `CancelledError` into the await points). The parameter and its three `is_set()` check-points (`:267`, `:317`, `:324`) are kept for callers that need pause/resume semantics — none exist today. `[VERIFY: no other call site uses cancel_event=...]`

**Skill loading honours `self.user_id`.** `_load_skills` (`orchestrator_v2.py:194-210`) iterates the resolved agents and calls `get_skill_content(agent_def.id, user_id=self.user_id)`. The resolution order is: per-user → admin global → PPT shipped reference docs → `DEFAULT_SKILLS` (see §B6). Passing `user_id=None` skips the per-user tier — which is why the old WS handler regressed when it stopped supplying user context.

**Differences from the deleted `pipeline.py:51-178` referenced in the previous version of this doc.**

| Old `PipelineExecutor` | New `WorkflowOrchestrator` |
|---|---|
| Skill dict assembled by the WS handler before instantiation; passed in via constructor | `_load_skills` owns the lookup; WS handler doesn't see skill content |
| Per-user resolution required threading `user_id` through three layers (handler → executor → skill loader) | `WorkflowOrchestrator(user_id=...)` is the only DI point |
| `task.cancel()` had no effect because the WS handler awaited the executor synchronously | Pipeline runs as `current_pipeline_task` background task; cancel propagates via `CancelledError` to the orchestrator's await points |
| Cancelled runs never updated `WorkflowRun.status` | Cancelled runs persist `status="cancelled"`, `duration`, partial `agent_outputs` (`websocket.py:614-629`) |
| No `REVISION_BASE_MAP` — revisions handled by special-cased `pipeline_type` strings inside the executor | `REVISION_BASE_MAP` is module-level; revision logic centralised in `_build_agent_context` |
| Revision context (prior output) fetched from DB | Revision context shipped inside the user message itself by the frontend (see W41) |

**Chaining (W41).** Still not implemented server-side — each chained run is a fresh `run_pipeline`. The orchestrator has no awareness of the chain; the previous output is just text in the new user message.

**Questionnaire (W64).** `_handle_questionnaire` (`websocket.py:723-778`) instantiates a raw `BaseAgent` (not `WorkflowOrchestrator`) directly from `QUESTIONNAIRE_AGENT.system_prompt` (`registry.py:1281-1313`), runs it synchronously, regex-extracts JSON, emits `questionnaire`. The user's answers are then folded back into the next `run_pipeline`'s `message` by the frontend as a `=== USER PREFERENCES ===` block (`DashboardLayout.tsx:252-278`). The questionnaire run does not allocate a `WorkflowRun` row.

**PPT pipeline & export (revised).** The doc previously claimed PPT download is client-side via `pres.writeFile()` from inside the iframe. That path still works (the assembler's HTML contains a `Download PPTX` button hooked to `generatePresentation()` — `ppt_pipeline.py:229`), but the frontend now **strips that button out** before rendering (`PPTPreview.tsx:117`) and replaces it with a server-side export button that POSTs to `/api/workflows/export-pptx` (`workflows.py:128-227`). The route accepts either:
1. `workflow_id` — looks up `WorkflowRun.agent_outputs`, finds the agent with id containing `"code"`, `"generator"`, or `"ppt-code"`, uses its output as the PptxGenJS source (`:152-167`).
2. `js_code` — raw PptxGenJS source supplied by the caller.
3. `html` — extracts `generatePresentation()` via brace-matching from the assembler's HTML (`:169-206`).

Server-side rendering then runs `generate_pptx_from_code(js_code, title=title)` in `app/services/pptx_export.py` and returns the `.pptx` binary. The legacy client-side path is dormant in the current UI but the JS function survives in the rendered HTML in case a user opens the page in "Full Screen" — that mode does not strip the embedded download button. `[VERIFY: confirm the Full-Screen open path retains the in-iframe button — the `replace()` calls in PPTPreview.tsx run on the iframe content too]`

---

### B6 — Agents catalog & skills backend trace

**Catalog.** Static dataclass definitions in `backend/app/agents/registry.py` (1313 lines). No DB storage of agent metadata, no admin UI, no per-user variants.

**Agent counts per pipeline type** (verified by walking `pipeline_type=` strings in `registry.py` + `custom_agents.py`):

| `pipeline_type` | # agents | Source | Notes |
|---|---|---|---|
| `user_stories` | 6 | `registry.py:28-237` | domain-analyst → epic-architect → story-estimator → nfr-specialist → backlog-reviewer → backlog-compiler |
| `ppt` | 4 | `registry.py:254-304` + prompts in `ppt_pipeline.py` | ppt-content-strategist → ppt-slide-architect → ppt-code-generator → ppt-assembler |
| `ppt_revision` | 2 | `registry.py:314-339` | ppt-revision-agent → ppt-revision-assembler (reuses `PRESENTATION_ASSEMBLER_PROMPT`) |
| `user_stories_revision` | 1 | `registry.py:347-389` | user-story-revision-agent |
| `prototype` | 4 | `registry.py:503-737` | requirements-analyst → html-prototype-builder → prototype-polisher → prototype-finalizer |
| `prototype_revision` | 1 | `registry.py:397-447` | prototype-revision-agent |
| `app_builder` | 4 | `registry.py:745-967` | material-analyzer → app-code-generator → app-infra-generator → app-assembler |
| `app_builder_revision` | 1 | `registry.py:455-496` | app-builder-revision-agent |
| `reverse_engineer` | 4 | `registry.py:975-1219` | repo-scanner → deep-analyzer → modernization-planner → documentation-generator |
| `custom` | 0 in `ALL_AGENTS["custom"]` | `registry.py:1227, 1234` | Maps to `CUSTOM_AGENTS` from `custom_agents.py` |
| (utility pool) | 8 | `custom_agents.py:5-206` | market-research-agent, swot-analyst, roadmap-planner, security-auditor, test-case-generator, performance-optimizer, documentation-agent, report-generator |
| `questionnaire` | 1 | `registry.py:1281-1313` | Special-purpose; not in `ALL_AGENTS`. Invoked directly by the WS questionnaire handler. |

Total: **27 production agents across 10 pipeline keys + 8 utility agents + 1 questionnaire = 36** `AgentDefinition` instances. Note the previous doc claimed 30 — the increase is from `app_builder_revision`, `prototype_revision`, `user_stories_revision`, `ppt_revision` (formerly summarised under base pipelines).

`get_pipeline_agents(pipeline_type)` (`registry.py:1250-1253`) is the single resolution function — returns the list sorted by `order`, empty list for unknown types.

**WS handler agent-count estimates** (`websocket.py:486-490`): pre-creation of `WorkflowRun.agent_count` uses hard-coded values `{"user_stories": 12, "ppt": 4, "prototype": 12}` for the **default** path. These do not match the registry (`user_stories` has 6 agents, not 12; `prototype` has 4, not 12). When `agent_ids` is supplied, the count is correct (`len(agent_ids)`). `[VERIFY: this looks like a stale post-DB-migration default that wasn't updated after the registry was simplified — likely cosmetic, only affects the row at creation time]`

**Skills system — REST endpoints (`api/agents.py`).**

| Method+Path | Auth | Storage path | Notes |
|---|---|---|---|
| `GET /api/agents/skills` | `get_current_user` (`:131`) | reads `backend/skills/users/{current_user.id}/*/SKILL.md` | Returns the caller's own custom skills only with 200-char content previews (`:141-148`). |
| `GET /api/agents/skills/{agent_id}` | `get_current_user` (`:152`) | reads `backend/skills/users/{current_user.id}/{agent_id}/SKILL.md` | `read_user_skill` returns empty string when no file (deliberate UX choice — frontend can call without 404 handling). Does NOT fall back to defaults (`:160-163`). |
| `POST /api/agents/skills` body `{agent_id, content}` | `get_current_user` (`:167`) | writes `backend/skills/users/{current_user.id}/{agent_id}/SKILL.md` | Validates `agent_id` exists in the registry → 400 if unknown (`:178-182`). Enforces `MAX_SKILL_BYTES = 65536` (64 KB) on the UTF-8-encoded content → 413 if oversized (`:184-191`). |
| `DELETE /api/agents/skills/{agent_id}` | `get_current_user` (`:198`) | unlinks the user's own file only | Idempotent — returns `{status:"not_found"}` 200 instead of 404 (`:204-209`). Cannot delete another user's file or the admin global tier. |
| `GET /api/agents/pipelines/{pipeline_type}` | `get_current_user` (`:70`) | none | Returns the registry's agent list with `has_skill: bool` computed per-user via `get_skill_content(agent_id, user_id=current_user.id)` (`:59-62, :85`). |
| `GET /api/agents/library` | `get_current_user` (`:101`) | none | All agents flat list with per-user `has_skill` hint. |

**Skill resolution order** (`skills.py:197-271`, `get_skill_content(agent_id, user_id=None)`):
1. `backend/skills/users/{user_id}/{agent_id}/SKILL.md` — per-user override (skipped if `user_id=None`).
2. `backend/skills/global/{agent_id}/SKILL.md` — admin-managed file tier. **Reserved** — no REST endpoint writes here today. Reading is supported on disk.
3. PPT special-case shipped docs (`backend/pptx/`):
   - `ppt-code-generator` → full `pptxgenjs.md` + `skill.md` (`skills.py:233-243`)
   - `ppt-slide-architect` → `skill.md` only (`:245-249`)
   - `ppt-content-strategist` → inline design brief string, no file read (`:251-258`)
   - `ppt-assembler` → "Common Pitfalls" section sliced out of `pptxgenjs.md` (`:260-268`)
4. `DEFAULT_SKILLS` dict baked into `skills.py:32-153` — currently defines fallbacks for `domain-analyst`, `persona-researcher`, `story-writer`, `acceptance-criteria-gen`, `react-code-generator`, `export-formatter`. Other agents fall through to `None` and run with just their bare system prompt.

**The previous "high-severity authorisation gap" callout (skills were global) is RESOLVED.**

- Storage layout: `backend/skills/users/{user_id}/{agent_id}/SKILL.md` (`skills.py:160-162`).
- Every endpoint requires `Depends(get_current_user)`.
- POST/DELETE always namespace by `current_user.id` (`save_custom_skill(..., user_id=current_user.id)` at `agents.py:193`, `delete_custom_skill(..., user_id=current_user.id)` at `agents.py:208`).
- `save_custom_skill` defensively raises `ValueError` if `user_id` is falsy (`skills.py:293-297`) so a missing-dependency bug surfaces in tests instead of silently writing to a `None/` directory.
- The `backend/skills/global/` tier exists but has **no write endpoint** — it can only be populated by an operator with shell access, which is the documented future "admin-managed" path.
- The frontend's `agent_ids` field on `run_pipeline` is now honoured: `IdeaInputPage.tsx:96` ships the user-mutated agent list, and the WS handler filters and reorders accordingly (`websocket.py:558-561`). Unknown IDs are silently dropped — there is no explicit error frame for "agent_id not in registry". `[VERIFY: behaviour is intentional pass-through, not a regression]`

The new test `backend/tests/unit/test_orchestrator_skill_resolution.py` (untracked in `git status`) covers the per-user lookup path.

---

### B7 — Per-agent LLM profiles

**Provider:** AWS Bedrock via `langchain_aws.ChatBedrockConverse` (`app/agents/base.py:88-105`). Auth uses the boto3 default credential chain (instance-profile IAM role in prod, `~/.aws/credentials` / `AWS_PROFILE` locally — no API key).

**Model resolution order** (`base.py:71-94`):
1. Explicit `model=` arg passed to `BaseAgent(...)` — currently no caller uses this.
2. `settings.BEDROCK_INFERENCE_PROFILE_ID` — default `"eu.anthropic.claude-haiku-4-5-20251001-v1:0"` (`config.py:70`). This is the EU cross-region inference profile and is the **actual ID sent to Bedrock**.
3. `settings.BEDROCK_MODEL_ID` — default `"anthropic.claude-haiku-4-5-20251001-v1:0"` (`config.py:65`). Used only as a fallback when the inference profile is unset — most EU regions (including `eu-central-1`) reject on-demand invocation of the foundation-model ID directly with `ValidationException`, so the profile is preferred in production.

Region: `settings.AWS_REGION` default `"eu-central-1"` (`config.py:71`). Missing either → `AgentConfigurationError` at agent construction (`base.py:97-100`).

**Per-agent `max_tokens`** (re-verified against current `registry.py` + `custom_agents.py`):

| Agent ID | `max_tokens` | Pipeline | Estimated I/O magnitude |
|---|---|---|---|
| domain-analyst | 4 000 | `user_stories` | 0.3K in / 1-2K out |
| epic-architect | 16 000 (default) | `user_stories` | 1K in / 3-8K out |
| story-estimator | 16 000 (default) | `user_stories` | 4K in / 3-5K out |
| nfr-specialist | 16 000 (default) | `user_stories` | 5K in / 2-4K out |
| backlog-reviewer | 4 000 | `user_stories` | 4K in / 1-2K out |
| backlog-compiler | 32 000 | `user_stories` | 12K in / 15-30K out — **dominant cost** |
| ppt-content-strategist | 8 000 | `ppt` | 0.5K in / 2-5K out |
| ppt-slide-architect | 12 000 | `ppt` | 6K in / 4-10K out, plus `pptx/skill.md` injection |
| ppt-code-generator | 32 000 | `ppt` | 10K in / 25-32K out — **dominant cost**, eats full `pptx/pptxgenjs.md` (~13 KB) |
| ppt-assembler | 32 000 | `ppt` | 28K in / 15-32K out, "Common Pitfalls" slice only |
| ppt-revision-agent | 32 000 | `ppt_revision` | 30K in (existing code) / 25-32K out |
| ppt-revision-assembler | 32 000 | `ppt_revision` | Same as ppt-assembler |
| user-story-revision-agent | 32 000 | `user_stories_revision` | Backlog markdown + instruction in, full revised backlog out |
| requirements-analyst | 4 000 | `prototype` | 0.5K in / 1-3K out |
| html-prototype-builder | 32 000 | `prototype` | 3K in / 25-32K out — **dominant cost** |
| prototype-polisher | 32 000 | `prototype` | 25K in / 25-32K out |
| prototype-finalizer | 32 000 | `prototype` | Similar |
| prototype-revision-agent | 32 000 | `prototype_revision` | 40K in (existing HTML) / 25-32K out |
| material-analyzer | 6 000 | `app_builder` | 0.5K in / 2-5K out |
| app-code-generator | 32 000 | `app_builder` | 4K in / 25-32K out |
| app-infra-generator | 16 000 | `app_builder` | 30K in / 10-16K out |
| app-assembler | 32 000 | `app_builder` | 60K in / 25-32K out |
| app-builder-revision-agent | 32 000 | `app_builder_revision` | Similar to assembler |
| repo-scanner | 8 000 | `reverse_engineer` | 1K in / 4-8K out |
| deep-analyzer | 16 000 | `reverse_engineer` | 8K in / 8-16K out |
| modernization-planner | 8 000 | `reverse_engineer` | 16K in / 4-8K out |
| documentation-generator | 32 000 | `reverse_engineer` | 30K in / 25-32K out |
| market-research-agent | 8 000 | `custom` (utility) | small |
| swot-analyst | 6 000 | `custom` (utility) | small |
| roadmap-planner | 8 000 | `custom` (utility) | small |
| security-auditor | 8 000 | `custom` (utility) | small |
| test-case-generator | 8 000 | `custom` (utility) | small |
| performance-optimizer | 6 000 | `custom` (utility) | small |
| documentation-agent | 16 000 | `custom` (utility) | medium |
| report-generator | 8 000 | `custom` (utility) | small |
| questionnaire | 2 000 | `questionnaire` | 0.3K in / 0.5-1K JSON out |

The `AgentDefinition.max_tokens` default is `16000` (`registry.py:21`); agents that omit `max_tokens` (epic-architect, story-estimator, nfr-specialist) inherit this default.

**Approximate cost per pipeline run** (Haiku 4.5 list price, unchanged from previous estimate but re-noted here since pipelines were re-tabulated):
- `user_stories`: ~$0.04–0.10 (backlog-compiler dominates)
- `ppt`: ~$0.05–0.12 (ppt-code-generator + ppt-assembler dominate; large skill injection)
- `prototype`/`app_builder`/`reverse_engineer`: ~$0.10–0.30 (HTML/code-heavy, three 32K-cap stages each)
- Revision pipelines: ~30-50% the cost of their base pipeline (1-2 agents vs 4-6).

**Other behaviours.**
- No temperature override anywhere — LangChain's `ChatBedrockConverse` default applies. JSON-output agents (questionnaire) rely on the model following the strict prompt; there is no `temperature=0` for determinism. `[VERIFY: confirm no agent passes temperature= via a kwarg I missed]`
- No application-level token counting. Bedrock CloudWatch metrics (`InputTokenCount`, `OutputTokenCount`) dimension on the *inference-profile* ID (`config.py:67-69` comment), which is what we invoke.
- Retry policy: 2 attempts on transient errors (`orchestrator_v2.py:312-361`) with a 2 s sleep. Bedrock `ThrottlingException` is **not** classified as transient by this loop — it surfaces as a generic exception and is caught by the agent-level handler (`:405-418`), which logs and emits `agent_error{recoverable:true}` but does NOT halt the pipeline. The error frame's `code` field (`rate_limit`) is set by `_map_llm_exception` only for `user_message` chat flow (`websocket.py:391-403`), **not** for `run_pipeline` flow — pipeline errors always carry `code="pipeline_error"` regardless of root cause. This is a minor inconsistency between the chat and pipeline error pipelines. `[VERIFY: confirm pipeline error code is intentional and not a TODO]`

---

### B8 — Services & artifact persistence

**Backend services directory.** Only one service module exists:
`backend/app/services/pptx_export.py`. The earlier placeholder is **gone**: the
file is now ~180 lines implementing real server-side .pptx generation. There
are no other artifact-related services — no S3 client, no signed-URL minter,
no static-files mount.

**Server-side PPTX export — NEW in this branch.** Previously, all .pptx
generation happened in the browser (`pptxgenjs` npm package called from the
iframe-embedded JS or from `pptExporter.ts`). The PPT preview HTML still
*can* trigger an in-iframe `pres.writeFile(...)`, but the visible UX has
moved off it: the "Download PPTX" button is now rendered **outside** the
iframe and POSTs to the backend, which spawns Node 20 with `pptxgenjs@3.12.0`
to render the .pptx and return the bytes.

**Route table (`api/workflows.py`).**

| Method+Path | Body | Status codes | Notes |
|---|---|---|---|
| POST `/api/workflows` (`:61-94`) | `{type, input, title?, agent_count=12}`; `type ∈ {user_stories, ppt, prototype}` | 201 / 400 (invalid type) | Currently unused by the front-end — WS path is authoritative (carried over from prior B4 trace) |
| GET `/api/workflows` (`:97-125`) | query `limit=50,offset=0,type?,status_filter?` | 200 | Filter by `user_id == current_user.id`, order `created_at DESC`. **Used by the new PPTX flow to resolve `workflow_id` from the rendered `<h1>`** |
| **POST `/api/workflows/export-pptx`** (`:128-227`) | `dict` body (no Pydantic) with `js_code?: str`, `html?: str`, `workflow_id?: str`, `title?: str = "Presentation"` | 200 (`application/vnd.openxmlformats-officedocument.presentationml.presentation`), 400 (no code found), 500 (generation failed) | **NEW.** See "Export-PPTX endpoint" below |
| GET `/api/workflows/{id}` (`:230-251`) | – | 200 / 404 | per-user only |
| PATCH `/api/workflows/{id}` (`:254-293`) | `{status?, output?, duration?, error?}` | 200 / 404 | Auto-sets `completed_at` on `"completed"`/`"failed"`; unused by FE |
| DELETE `/api/workflows/{id}` (`:296-321`) | – | 204 / 404 | per-user only |

**Export-PPTX endpoint detail (`api/workflows.py:128-227`).**

* *Request* — request is parsed as `dict` (note: `request: dict` not a
  Pydantic model, so there's no schema validation; FastAPI's default JSON-body
  binding still applies). Accepted keys: `js_code`, `html`, `workflow_id`,
  `title`. **Auth required** via `Depends(get_current_user)` (`:131`); rejects
  cross-user `workflow_id` because the strategy-1 query filters
  `WorkflowRun.user_id == current_user.id` (`:154-157`).

* *Response* — raw bytes wrapped in `fastapi.responses.Response` with
  `Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation`
  and `Content-Disposition: attachment; filename="<title-spaces-as-underscores-cap-40>.pptx"`
  (`:222-227`).

* *Three extraction strategies* run in order (`:152-207`):

  1. **From workflow_id → DB agent_outputs.** Query
     `WorkflowRun` by `id` *and* `user_id == current_user.id` (`:154-157`);
     `json.loads(wr.agent_outputs)` and pick the first agent whose
     `agent_id` matches the loose substring filter
     `"code" in aid or "generator" in aid or "ppt-code" in aid` (`:163`).
     For the PPT pipeline that resolves to the `ppt-code-generator` agent
     (`registry.py:280`, Agent 3 of 4). All exceptions during JSON parse are
     swallowed with a bare `except` (`:166-167`).
  2. **`js_code` field directly** — passed in by the caller. (Currently only
     `PPTPreview.tsx:57` ever sends `js_code` — the prop comes from
     `pptxCode` which is wired through `PreviewPanel.pptxCode`. `FilesTab`
     omits it.)
  3. **Extract from HTML.** Run two regex scans over `html_content`
     (`:170-206`): first inside `<script>...</script>` blocks, then over the
     full HTML, looking for `(async )?function generatePresentation(...) {`
     and brace-counting to the matching `}`. Captures the function body
     verbatim.

  If all three strategies fail, returns 400 `"Could not find PptxGenJS code.
  Try re-running the pipeline."` (`:208-212`).

* *No size limits.* The endpoint does **not** enforce a max body size, max
  `js_code` length, max output PPTX size, or rate limit. With Agent 3
  outputs typically 25–32 KB (B7), inputs stay well below FastAPI/uvicorn's
  default 1 MB JSON ceiling, but a hostile caller could submit arbitrary
  JavaScript. Mitigations rely on the subprocess sandbox (see below) and
  per-call timeout.

* *Error contract.* `RuntimeError` / any other exception in
  `generate_pptx_from_code` is caught and returned as
  `500 "Failed to generate PPTX: <first 200 chars of error>"` (`:216-220`).
  The 30-second subprocess timeout (see below) raises
  `subprocess.TimeoutExpired` which propagates into the same 500 path.

**`pptx_export.generate_pptx_from_code` — code sanitisation & Node subprocess
(`services/pptx_export.py:40-179`).**

* **Path resolution at import time** (`:16-37`). Order:
  1. `PPTX_NODE_MODULES_DIR` env var (explicit override, wins everywhere).
  2. `/opt/pptx/node_modules` if it exists (production Docker; see Dockerfile
     below).
  3. `<repo>/frontend/node_modules` (local dev — relative to
     `__file__.parent.parent.parent.parent` which lands on the repo root).

  `NODE_MODULES_PPTXGENJS = NODE_MODULES_DIR / "pptxgenjs"`. Tests for all
  three branches in `backend/tests/unit/test_pptx_export_path_resolution.py`.

* **Sanitisation pass** (`:43-88`). Best-effort string-level rewriting before
  the code is handed to Node:
  - Strip Markdown code fences (` ```javascript ` / ` ```js ` / trailing
    ` ``` `) (`:46-48`).
  - Remove `#` from hex color literals (`color: "#FFFFFF"` → `color: "FFFFFF"`)
    (`:54-55`).
  - Truncate 8-char hex colours to 6 (`:57`).
  - Drop `-` from negative shadow offsets (`offset: -5` → `offset: 5`)
    (`:59`).
  - Strip lines containing standalone `.line.` property reads (e.g.
    `shape.line.color = …`) which crash in pptxgenjs's Node build
    (`:61-71`).
  - Replace `pres.writeFile(...)` / `pres.save(...)` with
    `return pres.write("nodebuffer")` (`:74-79`).
  - Force `async function generatePresentation` if not async already
    (`:82-84`).
  - If no `generatePresentation` function found at all, wrap the entire
    snippet as the body of one (`:87-88`).

* **Node script generated on the fly** (`:95-151`). Written to
  `tempfile.mkdtemp(prefix="pptx_export_")/input.js`, with hard-coded paths
  to `NODE_MODULES_PPTXGENJS`. Key tricks:
  - `Module._resolveFilename` monkey-patch (`:97-102`) so any
    `require("pptxgenjs")` inside Agent 3's code resolves to the
    pre-installed `/opt/pptx/node_modules/pptxgenjs`.
  - Exposes `global.PptxGenJS` and `global.pptxgen` (`:104-105`) so user
    code can `new PptxGenJS()` or `new pptxgen()` without `require`.
  - **Fallback rendering on crash** (`:109-124`): wraps the user-supplied
    `generatePresentation` in a try/catch. On any thrown exception, builds
    a 1-slide deck with the error text (`Export error: <message>`) instead
    of failing the request — this is the "always return a valid .pptx"
    contract.
  - Handles both `Buffer` and `Uint8Array` returns; if the function returns
    neither, builds another fallback "no buffer returned" slide
    (`:130-144`).
  - Fatal Node-level errors (vs in-user-code errors) write to stderr and
    exit 1 (`:145-148`).

* **Subprocess invocation** (`:157-160`).
  `subprocess.run(["node", js_file], capture_output=True, text=True,
   timeout=30, cwd=temp_dir)`. **30-second hard timeout**, cwd set to the
  tempdir so `fs.writeFileSync` to relative paths works.

* **Output handling** (`:162-171`). If `output.pptx` exists, reads bytes
  and returns them. Logs `"Generated PPTX: <N> bytes"`. If not, raises
  `RuntimeError("PPTX generation failed: <first 300 chars of stderr>")`.

* **Cleanup** (`:173-179`). `finally` unlinks `input.js` and `output.pptx`
  and `rmdir`s the temp dir. Swallows all cleanup errors. Tempfiles live
  under `tempfile.mkdtemp(prefix="pptx_export_")` (system temp, normally
  `/tmp/pptx_export_<random>` in the container, on the EBS root volume).

**Client-side vs server-side .pptx path — when does each apply?**

| Path | Renderer | Code source | UX entry points |
|---|---|---|---|
| **Client-side** (legacy) | Browser, `pptxgenjs@3.12.0` via npm | `parsePPTSlideData(content)` — expects slide JSON in `message.artifact.content` | Only the chat `ArtifactCard` with `type==="ppt"` (`ArtifactCard.tsx:80-82` → `exportToPptx`). Used when a chat reply contains a PPT artifact with JSON content. Layout: `LAYOUT_WIDE`, 7 slide kinds. |
| **Client-side** (in-iframe) | Browser, `pptxgenjs@3.12.0` from a CDN inside the assembler's `<script>` tag | The assembler's own `generatePresentation()` JS, embedded in `workflow_runs.output` HTML | The PPT iframe **still has the capability** (the assembler ships a function), but the visible "Download PPTX" button bound to it is now stripped out by `PPTPreview.tsx:117-119` before rendering. The path is dead UI-wise unless a user "Open in new tab"s the raw HTML and clicks an embedded button. |
| **Server-side** (new) | Node 20 + `pptxgenjs@3.12.0` at `/opt/pptx/node_modules` (Docker) or `frontend/node_modules` (dev) | Three extraction strategies (workflow_id → agent_outputs → Agent 3 output; OR `js_code` param; OR regex-scan `html`) | (a) "Download PPTX" button in `PPTPreview` (`:168-174`); (b) `presentation-pptx` row in `FilesTab` (`:135-175`). Both used by the workflow `PreviewPanel` for the `ppt` and `ppt_revision` types. |

In practice the server-side path is the only PPT export users see today — the
chat artifact path remains in code but is wired to the legacy slide-JSON
content shape, which the current PPT pipeline (which outputs HTML, not JSON)
does not produce.

**Docker layout for server-side PPTX (`backend/Dockerfile`).** Three stages
(`:22-178`):
1. *builder* (`python:3.13-slim-bookworm`, `:25`) — builds Python wheels into
   `/opt/venv`. Trims `__pycache__`, in-package tests, pip/setuptools to save
   ~140 MB (`:65-69`).
2. *pptx-builder* (`node:20-bookworm-slim`, `:91`) — runs
   `npm install --prefix /opt/pptx --no-audit --no-fund --omit=dev
    pptxgenjs@3.12.0` (`:97`). Version pinned to match
   `frontend/package-lock.json`. The pin to `node:20-bookworm-slim` is
   deliberate — same Debian base as the runtime stage so the Node 20 binary
   copied across is ABI-compatible (`:81-91`).
3. *runtime* (`python:3.13-slim-bookworm`, `:103`) — installs `libpq5 curl
   ca-certificates libstdc++6` apt-side (`:120-127`); copies `/opt/venv`
   from stage 1 (`:130`); copies just the `node` binary (no npm) from
   `node:20-bookworm-slim` to `/usr/local/bin/node` (`:136`); copies
   `/opt/pptx/node_modules` from stage 2 with `--chown=10001:10001` (`:140`).
   Runs as non-root user `flowin` (UID/GID 10001, `:146-147,168`).

The `/opt/pptx/node_modules` location is what `pptx_export.py`'s probe
checks at import time — so production containers always pick path #2
(prod) automatically, while local-dev uvicorn (outside Docker) falls
through to the `frontend/node_modules` tree.

**Artifact persistence — unchanged from B4.** All artifact bytes still live
in `Text` columns:

| Source | Column | Format | Typical size |
|---|---|---|---|
| user_stories pipeline | `workflow_runs.output` | Markdown | 5–15 KB |
| ppt pipeline | `workflow_runs.output` | Self-contained HTML w/ embedded assembler JS | 30–80 KB |
| ppt pipeline | `workflow_runs.agent_outputs[ppt-code-generator].output` | Raw PptxGenJS JS code (Agent 3's contribution) — strategy #1 input | 25–32 KB (B7) |
| prototype pipeline | `workflow_runs.output` | Self-contained HTML | 40–120 KB |
| app_builder / reverse_engineer | `workflow_runs.output` | Markdown w/ filename code blocks (parsed by `parseAppBuilderFiles`, `FilesTab.tsx:33-74`) | up to 100 KB+ |
| All pipelines | `workflow_runs.agent_outputs` | JSON array of per-agent `{agent_id,name,role,icon,thinking,output,duration}` (`websocket.py:585-601`) | 5–50 KB per agent |
| Chat completion | `chat_sessions.final_output` | JSON dump of `FinalOutputModel` (`websocket.py:433`) | up to ~200 KB |

**File I/O surface — slight change from the prior trace.** The backend now
**writes to a temp dir at request time** for every server-side PPTX export
(`tempfile.mkdtemp(prefix="pptx_export_")`, cleaned up in `finally`,
`pptx_export.py:90-179`). All other I/O is unchanged: reads from
`backend/skills/` and `backend/pptx/`; writes to `backend/skills/{agent_id}/SKILL.md`.
No upload endpoints, no static files. The skills directory is a
bind-mounted EBS volume in production
(`Dockerfile:152-167`, `infra/scripts/bootstrap-ec2.sh:176` —
`/opt/flowin/data/skills`), backed up daily as a tarball to the same S3
bucket used for pg_dump (`infra/scripts/bootstrap-ec2.sh:840-852`).

**Implications for AWS sizing.** Footprint additions vs prior trace:
- *Image size:* `+ ~80 MB` for Node 20 binary + pptxgenjs node_modules
  (estimated; pptxgenjs alone is ~1.5 MB but pulls JSZip + others).
- *RAM per export:* Node + pptxgenjs typically peak ~80–150 MB per
  subprocess; the 30 s timeout caps long-running cases.
- *Disk I/O:* now non-trivial — each export writes one JS file + one PPTX
  file (typically 30 KB – 500 KB) to `/tmp` then deletes. Cumulative under
  `tmpfs` (default on Linux) → memory pressure under high concurrency;
  consider sizing `/tmp` or sticking it on EBS via `/var/tmp`.
- *S3:* still no S3-backed artifact storage. The pg_dump bucket
  (`flowin-prod-pg-dumps-…`) is the only S3 dependency and it carries DB
  dumps + skills tarballs, not artifacts.

---

## 5. Cross-cutting integration gaps & action items

This list is synthesized from each Phase A doc-refresh agent's out-of-scope findings. They will be triaged in Phase B (per-section issue hunt + Terraform audit + fix dispatch).


#### Findings from `§2 (section_2_cross_cutting.md)`

<!--
Findings noted while drafting §2; not part of this section's scope to fix.

1. **WS event drift — `workflow_title_update`**: Frontend has a handler and
   a `StreamMessage` type entry (`types/index.ts:36`,
   `app/dashboard/page.tsx:265-274`), but no backend code emits this string
   anywhere under `backend/`. Either dead client code or a planned feature
   stub.

2. **WS event drift — `agent_complete.output`**: Frontend reads
   `(msg.output as string)` in `useWorkflow.ts:184, 196`, but the backend
   only emits `output_length` (`orchestrator_v2.py:386`). The streamed
   content from `agent_chunk` is what actually fills `updated[agentIdx].output`;
   the `output ||` branch on completion is always `||` of empty string. Not
   a regression — but worth noting because the WORKFLOWS.md row claiming
   `agent_complete: {agent_id, output}` is wrong.

3. **Dead validation helper**: `streamParser.parseStreamMessage` whitelists
   only 5 message types (`streamParser.ts:3`) and is never imported by
   `useWebSocket.ts` (which uses `JSON.parse` directly at
   `useWebSocket.ts:109`). If wired up, it would silently drop every
   `pipeline_*` / `agent_*` / `questionnaire` / `step` / `title_update`
   message.

4. **Probably-dead route**: `PATCH /api/workflows/{workflow_id}`
   (`workflows.py:254`) is not called from `frontend/src/`. Its docstring
   claims "used by the pipeline executor", but the live WebSocket pipeline
   path writes status / agent_outputs / duration directly via SQLAlchemy
   in `websocket.py:677-691`, not via HTTP. Candidate for deletion (or it
   should be wired up if external clients need it).

5. **`/api/agents/library` & `/api/agents/pipelines/{type}` appear
   unreferenced**: No `fetch` call site for either is present under
   `frontend/src/` (grep against the literal path returns no hits in the
   frontend tree). If `AgentLibrary` truly renders a static list it should
   be fed from these endpoints; otherwise the endpoints are unused.

6. **Skill content size response code**: `agents.py:184-191` returns 413
   for oversized skill content, which is canonically reserved for HTTP
   request payloads exceeding server limits — semantically fine but worth
   confirming with the FE that it surfaces an actionable error message
   rather than the same generic toast as a 400.

7. **WS auth via `?token=` still accepted**: `websocket.py:133-140` logs a
   deprecation warning but the path is live. Recommend setting a removal
   target (release tag or date) before forgetting about it; old browser
   tabs / external smoke clients can pin behaviour indefinitely otherwise.

8. **WS subprotocol echo fallback leaks the credential**: when a client
   offers `bearer.<jwt>` only (no `flowin.v1` selector), the server echoes
   `bearer.<jwt>` back (`websocket.py:157`). Comment acknowledges this is
   not ideal for log hygiene; once the deprecation in (7) lands, this
   fallback could go too.

9. **`subprocess.run(["node", …], timeout=30)` in `pptx_export.py:157-160`**
   runs LLM-generated JavaScript with no sandboxing beyond the timeout —
   server-side code execution risk. The pre-pass sanitises a few known
   crashy patterns but does not constrain `require()` (other than the
   resolver hook redirecting `"pptxgenjs"`) or filesystem access. Worth a
   defence-in-depth review (e.g. `--experimental-permission`, AppArmor,
   isolated user, dropped capabilities, or rewriting via a constrained
   pptxgenjs DSL).

10. **`/api/workflows/export-pptx` accepts a raw `dict` body**
    (`workflows.py:130`) — no Pydantic validation, no field-level type
    checks, max body size relies on the ASGI server default. Same payload
    shape used by two frontend call sites; a `BaseModel` would document
    the contract and let the OpenAPI schema declare it.

11. **`getChat` returns `ChatDetailResponse` with snake_case fields**
    (`lib/api.ts:175-182, 204-212`), but other chat helpers normalise to
    camelCase. Asymmetry that could trip up callers — out of §2 scope but
    flagging for the chat-domain refresh agent.

12. **localStorage JWT is read in a `useEffect` log statement**
    (`useWebSocket.ts:178`) — fine in dev, but the JWT prefix could end
    up in browser console history. Tighten before prod, possibly drop the
    log entirely.
-->

#### Findings from `§3.1 (section_3_1_auth.md)`

- **WS pipeline tasks survive token revocation.** `_handle_pipeline_execution` is spawned via `asyncio.create_task` at `backend/app/api/websocket.py:234-239` and receives the `user` object captured at WS open. Per-message re-validation runs only on the `user_message` branch (`websocket.py:280-286`); `run_pipeline`, `cancel_pipeline`, and `generate_questions` `continue` past it. A logout or password change mid-pipeline will not interrupt the running pipeline (the connection itself stays open until the next `user_message` or a client-side close). No test currently asserts this behaviour. Suggestion: re-run `_authenticate_token` at the top of `run_pipeline` dispatch (and inside `_handle_pipeline_execution` between agent steps for long pipelines).

- **`/login` rate-limiting still absent.** No SlowAPI/limiter middleware visible on `backend/app/api/auth.py` or registered in `backend/app/main.py:125`. Credential-stuffing surface unchanged from the prior doc.

- **`?token=` query-param WS auth still accepted (transitional).** `backend/app/api/websocket.py:131-140` logs a deprecation warning but continues to honour it. Until removed, JWTs can still leak into nginx access logs and browser history.

- **JWT in `localStorage` (XSS).** `frontend/src/lib/api.ts:18, 27-29` stores `auth_token` in `localStorage`. Any successful XSS extracts the token. Migration to `HttpOnly; Secure; SameSite=Strict` cookies is still pending.

- **`AccountSettings` confirm-password field has no eye toggle** (`AccountSettings.tsx:140-148`) while current and new do (`AccountSettings.tsx:108-119, 122-136`). UX inconsistency, not a security defect.

- **`logout()` swallows non-network failures too.** `frontend/src/lib/api.ts:47-60` uses a bare `catch {}` — if the backend returned 5xx the client still treats logout as successful and clears the token. Acceptable for the "user wants out either way" intent but worth noting alongside the W06 description.

- **Cancellation of `getMe` race in `AccountSettings`.** `AccountSettings.tsx:24-31` does not abort the in-flight `getMe()` if the user unmounts; the `setEmail`/`setLoading` calls after unmount would warn. Minor.

- **`router.push` vs `router.replace` inconsistency between register and login flows.** Register uses `router.push("/dashboard")` (`register/page.tsx:45`); login also uses `router.push("/dashboard")` (`login/page.tsx:24`). Both leave `/login` or `/register` in the back-stack — pressing Back from the dashboard returns to the login screen. The W04 auth-check and W05 expiry-redirect both use `router.replace`. Cosmetic but worth aligning.

#### Findings from `§3.2 (section_3_2_dashboard.md)`

**Out-of-scope observations (Phase B follow-ups for other agents):**

- `frontend/src/components/sidebar/Sidebar.tsx` and `frontend/src/components/sidebar/ChatSessionItem.tsx` are dead code — no consumer anywhere in the tree. Recommend either deletion or marking with a `// @deprecated — not mounted` header. Affects bundle size and onboarding clarity.
- `DashboardLayout.tsx:117-119` declares `currentWorkflowRunId` but never uses it — residual from the same sidebar refactor.
- `dashboard/page.tsx:493-521` `handleSelectWorkflowRun` is wired through `DashboardLayout` but unreachable in the rendered tree — same root cause (no sidebar mounted).
- `dashboard/page.tsx:265-274` handles a `workflow_title_update` WS event that the backend does not emit (verified by grep).
- The hint "Some hardcoded localhost URLs in frontend got replaced with ENV.API_URL" is **confirmed for the §3.2 scope**: `dashboard/page.tsx:6,306` uses `ENV.WS_URL`; `lib/env.ts` provides `ENV.API_URL` and `ENV.WS_URL` with `http://localhost:8000` / `ws://localhost:8000/ws/chat` defaults. No remaining hardcoded `localhost` in `components/layout/`, `components/sidebar/`, `components/home/`, `components/settings/`, or `app/dashboard/` (verified by grep).
- `AccountSettings.tsx:29` swallows `getMe` failures silently — same behaviour as the previous revision; if the token is JTI-revoked but `getMe` 401s, the email field stays empty with no error indication. Cross-reference with B1 (auth) when reviewing revocation UX.
- `CreationHub.tsx` no longer disables cards visually while a pipeline is running; only the `setMainView("input")` transition is silently blocked. Consider a `disabled` prop for better UX.
- `WorkflowHistory.tsx:285` lists filter pills `["all", "user_stories", "ppt", "prototype", "app_builder"]` — `custom` workflows therefore cannot be filtered to from the History page. Cross-reference with `LibraryPage.tsx:10-17` which *does* include `custom`.
- Pipeline-cancellation reality has changed since the previous trace: `current_pipeline_task` is now tracked and `task.cancel()` is invoked on `cancel_pipeline` (`websocket.py:184, 234-240, 245-252`) and on `WebSocketDisconnect` (`:442-450`). The B2 doc's "cancellation reality" paragraph (currently lines 346-347 in `WORKFLOWS.md`) needs updating — agent owning §B2 should incorporate this.
- `WorkflowOrchestrator` (the v2 pipeline orchestrator, imported at `websocket.py:480`) lives in `backend/app/agents/orchestrator_v2.py` and is now the actual pipeline executor — distinct from `AgentOrchestrator` (chat) at `backend/app/agents/orchestrator.py:293`. Agent owning §B4 should re-trace through v2.

#### Findings from `§3.3 (section_3_3_history.md)`

- **Frontend cancel-status display is broken** (out of scope for §3.3
  redraft but worth flagging to the parent): `WorkflowHistory.tsx:396-404`
  branches on `status === "failed"` and then sub-branches on
  `error === "Cancelled by user"`. Backend now writes `status="cancelled"`
  and leaves `error` NULL, so cancelled runs land in the
  "everything else" branch and render the **Running** pill (gray) until
  the type widens to include `"cancelled"`. Fix: widen
  `WorkflowStatus` (`types/index.ts:188`) and switch the badge to a
  status-first ladder.
- **`PPTPreview` and `FilesTab` duplicate the `workflow_id` lookup
  heuristic** (`PPTPreview.tsx:36-51`, `FilesTab.tsx:144-157`) instead
  of threading the already-known `selectedRun.id` through. In the
  history detail flow, `selectedRun.id` is in scope at the parent
  component and could be passed as a prop, removing the GET round-trip
  and the "first matching H1" heuristic.
- **`/api/workflows/export-pptx` uses `request: dict`** rather than a
  Pydantic `BaseModel` (`workflows.py:130`) — unlike the rest of the
  module. Schema documentation is therefore not exposed in OpenAPI/Swagger.
- **No backend tests exist for `/api/workflows/export-pptx`** — the
  only pptx_export tests cover module-level path resolution
  (`tests/unit/test_pptx_export_path_resolution.py`), not the endpoint
  itself or the Node subprocess.
- **Title generation for the filename** (`workflows.py:222`) truncates
  on a *character* basis (`[:40]`), not a *byte* basis, so a multi-byte
  title can produce a filename whose UTF-8 encoding exceeds 40 bytes
  (low risk; documented for completeness).

#### Findings from `§3.4 (section_3_4_setup.md)`

- `frontend/src/components/workflow/AgentLibraryData.ts:45` — `PIPELINE_CATEGORIES.all.count` is hard-coded to `20` but the real total is `26`. Unused at the moment, so dormant. (Drift caused by the reverse-engineer removal not being followed through.)
- `frontend/src/components/workflow/AgentsPopup.tsx:20-26, 28-34` — `LOCKED_AGENT_IDS` / `REQUIRED_AGENT_IDS` still reference reverse-engineer agents (`repo-scanner`, `documentation-generator`, `deep-analyzer`, `modernization-planner`) that are not in the frontend library. Dead code; safe to prune.
- `backend/app/agents/registry.py:975-1219` + `registry.py:1245` — `REVERSE_ENGINEER_AGENTS` and `ALL_AGENTS["reverse_engineer"]` remain registered but no UI surface exposes the pipeline type. Either re-expose it in `CreationHub` (was removed in commit 047fb43) or delete the dead pipeline.
- `frontend/src/components/workflow/IdeaInputPage.tsx:214-219` — file attachment appends only the filename string to the prompt and never reads file contents. Documented as W22 open issue; out of scope for this section but escalates to a real Phase B issue (B6 / file-upload contract).
- `frontend/src/components/workflow/IdeaInputPage.tsx:113` — when adding to a non-custom pipeline, the new agent is inserted at `prev.length - 1` (i.e. before the last existing agent regardless of whether that last agent is the terminal compiler). For pipelines where the user has already dragged the terminal compiler out of the trailing position, this insertion point is wrong relative to user intent. Minor UX bug.
- `frontend/src/components/workflow/SkillManager.tsx:128-132` — `useState(() => { if (isOpen && agentId) loadSkill(); })` is a misuse of `useState` as a side-effect initializer; it runs once on mount only, so re-opening the modal for a different agent does **not** reload the skill. Should be `useEffect`. Genuine bug.
- `frontend/src/components/workflow/SkillManager.tsx:95-111` — `deleteSkill` has no confirmation prompt; one click destroys persisted content. UX regression risk.
- `backend/app/api/websocket.py:486-489` — fallback `agent_counts` uses `12` for `user_stories` and `12` for `prototype`, but the actual pipelines have 6 and 4 agents respectively (`registry.py:28-237` and `:503-737`). Dead/stale heuristic; only matters when no `agent_ids` is sent and only used to seed `WorkflowRun.agent_count`.

#### Findings from `§3.5 (section_3_5_pipeline_and_backend.md)`

1. **WS handler `agent_count` defaults are stale** (`websocket.py:488`). Hard-coded `{"user_stories": 12, "ppt": 4, "prototype": 12}` don't match the registry (`user_stories=6`, `prototype=4`). Only matters for the `WorkflowRun.agent_count` field at creation; the value is overwritten by `len(agent_outputs_collector)` on completion. Easy fix: replace with `len(get_pipeline_agents(pipeline_type))`.

2. **Two orchestrators coexist.** `AgentOrchestrator` (`orchestrator.py`) is still the chat-mode orchestrator with phase-based events (`phase_start/phase_end/stream/complete`), used only by the `user_message` path. `WorkflowOrchestrator` (`orchestrator_v2.py`) is the pipeline orchestrator. Module name `orchestrator_v2` suggests `orchestrator.py` was meant to be retired or renamed; today they serve different message types and are not interchangeable. Worth a follow-up to consolidate or rename for clarity.

3. **`db_session` arg is dead** (`orchestrator_v2.py:178, :184`). Constructor stores it but no method reads it. Either wire it up (for revision context fetches when the frontend doesn't bundle the previous output) or remove.

4. **`cancel_event` parameter is dormant** (`orchestrator_v2.py:225`). Two cancellation paths exist — `Task.cancel()` (used) and `cancel_event.is_set()` (unused). No call site instantiates the event. Consider documenting in the orchestrator docstring that this is the "future pause/resume hook" or remove if YAGNI.

5. **Pipeline error code is always `pipeline_error`** (`websocket.py:657`). Bedrock-specific errors (throttling, timeout) that the chat path translates via `_map_llm_exception` to user-friendly codes do NOT get the same treatment for pipelines. Inconsistent UX — the chat shows "Too many requests…", the pipeline shows "Pipeline execution failed: <ClientError str>".

6. **Retry loop resets `output_chunks`** (`orchestrator_v2.py:321`). On a transient error mid-stream, the agent restarts from scratch and the client has already received chunks that won't be emitted again. The frontend's `agent_chunk` handler appends to `agent.output`, so chunks from the failed attempt are now stuck at the end of the prior text. Either (a) the frontend should reset `agent.output` on each `agent_thinking` "retrying" message, or (b) the orchestrator should emit a synthetic "reset" event. Currently neither.

7. **PPT in-iframe download button still alive in Full Screen path.** `PPTPreview.tsx:117-119` strips the in-HTML `Download PPTX` button when rendering inside the iframe inside the dashboard, but `handleOpenFullScreen` (`:146-151`) creates a Blob from `htmlContent` — which is the **stripped** version, not the raw. So actually the button is gone in Full Screen too. Earlier doc claim "Both paths may exist now" — clarified: the server-side `/api/workflows/export-pptx` route is the **only** active path; the client-side `pres.writeFile()` JS still exists in the embedded `generatePresentation()` function but is no longer reachable from any visible UI.

8. **Questionnaire is fire-and-forget at the user level.** If the WS disconnects between `generate_questions` send and `questionnaire` receipt, the frontend will retry by sending `run_pipeline` directly after a 15 s timeout (`DashboardLayout.tsx:193-201`). No persistence. If the LLM is slow, the user runs the pipeline blind to their own preferences.

9. **`WorkflowRun.chat_session_id` still missing.** `_handle_pipeline_execution` reads `chat_session_id` to persist the user message into the chat thread (`websocket.py:511-529`) but doesn't store the link on `WorkflowRun`. Deleting a chat orphans the runs. Carried over from the old §B4.

10. **Custom utility agents have `pipeline_type="custom"` but `ALL_AGENTS["custom"] = CUSTOM_AGENTS`** (`registry.py:1246`). This means `pipeline_type="custom"` actually resolves to the 8 utility agents — there is no "empty custom pipeline" today, despite the comment at `registry.py:1227` ("Empty (user composes their own)"). If you `run_pipeline` with `pipeline_type="custom"` and no `agent_ids`, all 8 utility agents will run sequentially. This is almost certainly not the intent — the UI should always supply `agent_ids` for custom pipelines.

11. **Two PPT skill paths coexist for `ppt-content-strategist`.** `DEFAULT_SKILLS` doesn't define one (`skills.py:32-153`), but `get_skill_content` returns an inline brief string (`skills.py:251-258`) **before** falling back to `DEFAULT_SKILLS`. So the inline string always wins. If someone adds a `pptx/content-strategist.md` and tries to read it via `DEFAULT_SKILLS`-style override, they'll find it ignored. Document or refactor.

12. **`backlog-reviewer`'s `max_tokens=4000` is suspicious** (`registry.py:169`). The reviewer's prompt asks for "any stories that need improvement", "2-3 missing stories... in full format", and "a quality score". 4 KB is ~1-2 stories' worth. Was previously default 16 000 in the legacy doc's per-agent table — looks like an intentional cap to prevent the reviewer from rewriting the backlog wholesale, but it's likely too tight. Worth a product check.

13. **`Pause` button label is misleading.** `AgentProgressPanel.tsx:170` shows a "Pause" button that actually cancels the pipeline (no resume). Rename to "Cancel" or "Stop" to match the wire-level semantics.

14. **`current_pipeline_task` never reset to `None` on success.** After `_handle_pipeline_execution` returns normally, `current_pipeline_task.done()` is True but the reference lives on (`websocket.py:184`). Harmless (the next `run_pipeline` checks `done()`, not `is None`), but the variable name leaks state to anyone reading the code.

15. **`_handle_questionnaire` blocks the receive loop.** Unlike `run_pipeline` which spawns a background task, `generate_questions` is awaited directly (`websocket.py:268`). The questionnaire takes 1-5 s of LLM time — during which the WS can't process `cancel_pipeline` or any other message. Low impact but worth noting; consider spawning as a task if questionnaire latency grows.

16. **`title_update` agent uses no `max_tokens` cap.** `websocket.py:326-332` instantiates a raw `BaseAgent` for chat title generation with the default 32 000 token cap. A 3-5 word title doesn't need 32K — wastes (a small amount of) memory and lets a misbehaving model write a novella. Not user-visible because the result is sliced to 60 chars (`:335`).

17. **Pipeline cancellation duration uses `time.monotonic()`, completion uses `datetime` subtraction.** `websocket.py:609` vs `:687`. Different clocks, slightly different precision. Cosmetic but inconsistent.

18. **`Pause` UI shows a separate `isCancelled` local state.** `AgentProgressPanel.tsx:140, :143, :159` — the panel locally tracks `isCancelled` because the server's `pipeline_cancelled` event arrives **after** the user clicks Pause, possibly several seconds later. The intermediate state is "Pipeline stopped" banner over the actual still-running agent. The optimistic UI matches the user's mental model but means the panel can show "Pipeline stopped" while `pipelineState.isRunning` is briefly still `true`. Not a bug but worth documenting in §3.5.

19. **PPT preview's workflow lookup is fuzzy** (`PPTPreview.tsx:37-51`, `FilesTab.tsx:143-158`). It fetches the user's recent PPT runs and tries to match by H1 text, falling back to "most recent". If the user has multiple PPT runs with similar titles, the wrong workflow_id may be selected → wrong Agent 3 code → wrong PPTX. A `workflow_run_id` should be threaded through the preview props.

20. **`STORAGE_DIR` for skills doesn't exist on a fresh checkout.** `backend/skills/users/` is created on first POST via `mkdir(parents=True, exist_ok=True)` (`skills.py:300`), but `backend/skills/global/` is never created — only read. Documented as "reserved" in the docstring, but means `os.path.exists()`-style health checks on the dir will be confusing.

#### Findings from `§3.6 (section_3_6_chat.md)`

Out-of-scope observations encountered while tracing chat:

- `frontend/src/types/index.ts:35-40` declares `StreamMessage.type` with the union including `"step"`, but no backend code path emits a `step` envelope — the receiver branch at `page.tsx:283-300` is currently dead for the chat path and is fed only by the persisted `<!--steps:JSON-->` marker on reload (`websocket.py:411-415`, parse at `page.tsx:444-451`). If §3.6 of the older WORKFLOWS.md implied live step streaming for chat replies it was forward-looking, not currently wired.
- `chat_session_id` is a hard requirement for `user_message` (`websocket.py:271-278`) — the dashboard auto-creates a session lazily before the first send (`page.tsx:330-342`), so the user-visible flow looks like "type and send", but a misbehaving client that sends `user_message` with no `chat_session_id` will get an `Invalid message format` error envelope, not a session.
- The chat orchestrator's `complete` data is a full `FinalOutputModel.model_dump()` (`orchestrator.py:444-449`) — the chat path effectively runs the same multi-phase pipeline (Discovery → Requirements → selected outputs → Preview compilation) as `WorkflowOrchestrator`, just exposed under a different orchestrator class and emitting `phase_start`/`stream`/`phase_end`/`complete` instead of `pipeline_start`/`agent_*`/`pipeline_complete`. The two orchestrators are *not* unrelated — they are parallel implementations of overlapping logic. This is structural duplication, flagged here because it affects how §3.6 vs §3.5 (W33–W41) relate.
- `MessageBubble.tsx:213-219` ("copy" action on a user bubble) and `MessageBubble.tsx:348-358` (copy on assistant) belong to §3.7 (W50 copy) but share state with the chat panel; the W42–W49 owner should not touch them.
- `ChatInput.tsx:200-217` (mic/speech recognition via `useSpeechRecognition`) and `MessageBubble.tsx:360-372` (TTS via `useTextToSpeech`) are §2.5 / §3.7 (W53 TTS) territory, not §3.6.
- The W42-W49 numbering in the brief assumes 8 workflows, but the chat conversation flow as currently coded comprises ≥10 distinct user-visible behaviours (send/mode/stream/title/typing/steps/error/empty plus speech-in and TTS-out). The two voice paths are kept out of this section per the brief but called out here for completeness.

#### Findings from `§3.7 (section_3_7_messages.md)`

- **Dead-code finding (out-of-scope of §3.7).** `ChatPanel` and `MessageBubble` are unreferenced by any page or layout component (verified by `grep -rn "MessageBubble\|ChatPanel"` across `frontend/src/`). The dashboard renders `AgentProgressPanel` + `PreviewPanel` instead (`DashboardLayout.tsx:440-485`). Either §3.6/3.7 should add a callout that these components are currently latent, or the components should be wired into the execution view to surface the chat history with W50-W53 interactions.
- **Missing-callback finding (out-of-scope of §3.7).** Even when `ChatPanel` is rendered, `dashboard/page.tsx` does not pass `onRegenerateMessage` or `onEditMessage` to `DashboardLayout` (the layout doesn't accept those props — see `DashboardLayoutProps` at `DashboardLayout.tsx:20-46`). W51 and W52 therefore have no host-level implementation today. The current `WORKFLOWS.md:252-253` statements (“sets `isEditing`; Enter submits” and “`onRegenerate` → page-level handler resends last user message”) accurately describe the component but overstate the page-level wiring — the page-level handler does not exist.
- **Backend-gap finding (out-of-scope of §3.7).** The backend offers no per-message mutations: `backend/app/api/chats.py` lacks `PATCH/DELETE /messages/{id}` routes, and `Message` (`backend/app/models/chat.py:34-49`) lacks edit-history columns. Any real edit/regenerate UX will either need (a) new endpoints or (b) the front-end's existing send-via-WebSocket path to be reused with explicit replace-last-turn semantics. Worth surfacing in §5 (integration gaps).
- **Per-code-block copy gap.** WORKFLOWS.md does not currently claim it, but a future “Copy code” affordance would require passing a custom `components` map to `ReactMarkdown` at `MessageBubble.tsx:322`; it is genuinely absent today.

#### Findings from `§3.8 (section_3_8_artifacts.md)`

Items observed during this trace that don't belong in §3.8 / §B8 proper but
will matter to other agents:

1. **`ArtifactCard` for prototype expects `.json`** (`ArtifactCard.tsx:38-43`,
   `:83-84`) while `FilesTab` exports prototype as `.html`
   (`FilesTab.tsx:125-130`). The chat path is stale relative to the current
   pipeline output (HTML). Likely a B4/B6 cleanup item.
2. **`ppt-code-generator` matched by substring** (`workflows.py:163`). The
   filter `"code" in aid or "generator" in aid or "ppt-code" in aid` would
   also match e.g. `app-code-generator` (`registry.py:507` in B5). If a user
   POSTs `workflow_id` from an `app_builder` run to `/export-pptx`, the
   endpoint would happily pick up that agent's output and try to render it as
   PptxGenJS — producing the fallback "Export error: …" slide. Low-severity
   but a documented sharp edge.
3. **`POST /api/workflows/export-pptx` accepts `dict`, not a Pydantic model**
   (`workflows.py:130`). No schema validation. Consider tightening for B2
   wire-format consistency.
4. **No rate limiting on the PPTX export.** Any authenticated user can spawn
   Node subprocesses on the backend. Worth a B1/B8 hardening item — at high
   concurrency this consumes CPU + RAM faster than the agent path.
5. **Frontend `FilesTab` stagger** changed from 100 ms (per old docs) to
   150 ms (`FilesTab.tsx:182`). Update §3.7/§3.8 prose if other docs cite
   it.
6. **Sandbox attributes regressed for PPT iframe** — old docs claim
   `allow-scripts allow-same-origin allow-downloads allow-popups` but the
   code is now `allow-scripts allow-same-origin` only (`PPTPreview.tsx:162`).
   Compensated by external server-side download button, but cite the change
   when reviewing CSP.
7. **`PPT_REVISION_AGENTS` and friends exist** (`registry.py:322,354,404,462`,
   pipeline-type map `:1239-1241`). These are new since the prior B5 trace —
   the revision pipelines have **two** agents each (analyser + code-rewriter),
   which makes the strategy-1 substring match for `"code"/"generator"` more
   likely to find the right agent on a revision run. Worth a B5 refresh.

#### Findings from `§3.9 (section_3_9_questionnaire.md)`

- `frontend/src/types/index.ts:36` declares the `questionnaire` event in the same monolithic union as every other WS message type — splitting this into a discriminated set per concern (pipeline, chat, questionnaire) would simplify the dashboard's WS dispatcher.
- The `questionnaire` `AgentDefinition` (`backend/app/agents/registry.py:1281-1313`) is the only agent definition not registered into a `pipeline_type` list and is reached only by direct import; consider documenting that "synthetic agent" status or moving it to a separate module to avoid implying it's a normal pipeline step.
- `_handle_questionnaire` builds its prompt by string concatenation (`backend/app/api/websocket.py:740`) with no sanitisation of `prompt` or `pipeline_type`; an attacker who can open a WS connection can inject arbitrary instructions into the system-prompt context. Low impact (it's a one-shot non-persistent call) but worth a note.
- `BaseAgent` is instantiated fresh on every `generate_questions` request (`backend/app/api/websocket.py:735-738`); for a hot path with a small, fixed system prompt this is wasteful — a module-level singleton would save ~ms and a Bedrock client init.
- No tests cover `_handle_questionnaire` (`grep -r questionnaire backend/tests` returns nothing) — regression risk for a feature that gates the whole pipeline UX.
