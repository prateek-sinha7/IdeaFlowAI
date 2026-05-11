# Phase B Audit — §3.2 Dashboard + §B3

Branch: `infra-agent-integration`
Scope: Dashboard workflows W08-W17 (page.tsx, DashboardLayout, AppHeader, CreationHub, AccountSettings) and backend §B3 chats/sessions/messages (chats.py, models/chat.py, websocket.py chat-related paths).

---

## CRITICAL

### C1 — Final assistant message (pipeline path) skips chat ownership check
`backend/app/api/websocket.py:711-718` — In `_handle_pipeline_execution()`, after a pipeline completes, the post-pipeline assistant message is persisted with a query that omits `ChatSession.user_id == user.id`:
```python
chat_session = (
    db.query(ChatSession)
    .filter(ChatSession.id == chat_session_id)
    .first()
)
```
Every other ownership-sensitive query in this file pairs `id` with `user_id` (e.g. line 292-294, 516). This is the only stray. In practice the `chat_session_id` here is the same value validated at line 514-518 earlier in the function, so it is hard to reach a cross-user write through a *single* WS connection — but if `chat_session_id` is forged in the `run_pipeline` payload and *no* user-owned session matches at line 514-518, the user-message persist is skipped (good), yet the assistant-message persist still happens at line 711-718 using only `ChatSession.id`. That writes an `assistant` Message into another user's session. Two-line fix; CRITICAL because IDOR-class.

### C2 — Authoritative `add_message` route permits arbitrary role injection
`backend/app/api/chats.py:28-33,162-188` — `AddMessageRequest.role: str = "user"` has no `Literal`/regex constraint. Any client can `PUT /api/chats/{id}/messages {"role":"assistant","content":"…"}` and impersonate the AI in their own (and only their own — authz is correctly enforced) chat history. Combined with C3 (no length cap) this also lets a user spam unbounded fake-assistant text into their `messages` table. The chat model accepts `"system"` too (chat.py:43 comment). Frontend never sends anything but `"user"`, so the parameter is effectively dead surface area; tighten to `Literal["user"]` or drop the field.

### C3 — No size limit on chat content (REST or WS)
`backend/app/api/chats.py:28-32` (`AddMessageRequest.content: str`), `backend/app/api/websocket.py:205-211` (raw `content = message_data.get("content")` with no length check), `backend/app/models/chat.py:44` (`content = Column(Text, nullable=False)` is unbounded). A logged-in attacker can `PUT` or WS-send a 100 MB message — Postgres `TEXT` will accept it, AWS Backup will copy it nightly, and the next `getChat()` returns it via `MessageResponse` blowing up the frontend. There is no Pydantic `Field(max_length=...)`, no length check anywhere in the path. Same issue applies to `CreateChatRequest.title` (no max — DB column is just `String` which on Postgres is `text`).

### C4 — Orphan Message rows on chat-session create failure
`frontend/src/app/dashboard/page.tsx:333-372`, `:388-424` — Both `handleSendMessage` and `handleSendMessageWithMode` follow:
1. `await createChat(token, content.slice(0, 50))` — REST creates session
2. `setActiveChatId(chatId)`
3. `setMessages([... userMessage])` — optimistic local
4. `send(JSON.stringify({type:"user_message", chat_session_id, ...}))` — WS persists user message

If step 1 succeeds but the WS is in `disconnected`/`reconnecting` (the `send` warns silently — `useWebSocket.ts:167-169` returns false but the caller ignores it), the new ChatSession row exists with title-prefix=first-50-chars but ZERO messages. The user retries → next `createChat` makes another empty session. Over time the user's sidebar/list fills with empty "New Chat"-titled rows that they never see content in. There is no atomic create-session-and-first-message operation, no rollback if `send` fails.

### C5 — Mid-stream disconnect loses assistant reply entirely (confirmed)
`backend/app/api/websocket.py:355-436` — Assistant chunks are accumulated in `assistant_chunks: list[str]` and persisted ONLY in the `finally`-equivalent block at line 408-421, AFTER the orchestrator's async generator completes (or raises). If `WebSocketDisconnect` fires mid-stream, control transfers to line 438-450 (the outer-loop's disconnect handler) which cancels the pipeline task but does NOT reach this persistence block — the inner stream was already in the `_handle_pipeline_execution` path or got cut off. For the *chat* `user_message` path, the disconnect propagates out of `await websocket.send_json(stream_msg)` (line 373), unwinding straight to line 438 — the `db.add(assistant_msg)` block is skipped. User sees the streaming text disappear on reload. Phase A flagged this; reconfirming.

---

## HIGH

### H1 — Concurrent edit race: two tabs same session
`backend/app/api/websocket.py:308-318` — Two tabs of the same user open the same chat. Tab-A sends `user_message`; Tab-B sends `user_message` ~simultaneously. Each WS handler runs an independent message-loop iteration:
- Both call `_authenticate_token` (OK, idempotent).
- Both `db.add(user_msg)` and update `chat_session.last_activity`.
- Both commit.

Result: two interleaved user-message rows persist with the same `chat_session_id`, both then trigger the orchestrator (line 364-373), both stream assistant replies into the same chat. The orchestrator has no per-session lock. `last_activity` gets clobbered by whoever commits last — that part is benign, but the assistant streams will interleave on both tabs' WS connections. No `SELECT … FOR UPDATE` on the session, no advisory lock. Hardening: per-session asyncio lock keyed by `chat_session_id` *or* a `WHERE last_activity = :seen_at` optimistic CAS.

### H2 — `last_activity` write paths inconsistent — title-generation race
`backend/app/api/websocket.py:314, 339-344` — The user-message write path: (a) updates `last_activity` on the same session row inside the first transaction (line 314), commits (line 318); (b) opens a SECOND session (`db2 = _get_db()` at line 337-344) to update the title. Between (a) and (b), title is generated by an LLM call (line 333 — multi-second). If a second tab issues a `user_message` during the title-generation window, that tab's commit happens between (a) and (b), then (b) overwrites the title set by the second tab — title flap. Worse, if the user has triggered `handleSelectChat` between the LLM call and the title commit, the title-update WS event arrives with a stale title for what is now a different active chat (FE handles partially via `chatTitleUpdate.chat_session_id` matching, but the persisted row is wrong). The fix is to do the title update inside the original transaction or use UPDATE-WHERE-title-still-the-default.

### H3 — Title-generation trigger has a false-positive heuristic
`backend/app/api/websocket.py:317` — `needs_title = chat_session.title in ("New Chat", "") or chat_session.title == content[:50]`. The third clause means: if the user happens to send the SAME message twice in a row, and the previous title was the truncated first message (the default the frontend sets via `createChat(currentToken, content.slice(0, 50))` at dashboard/page.tsx:334), the title regenerates again. Same content => same generated title most of the time, but it spends a Bedrock call (and risks throttle) every duplicate-send. Phase A flagged the 3-condition heuristic; this is the cost.

### H4 — `recentRuns` async fetch in dashboard not cancelled on unmount/auth change
`frontend/src/app/dashboard/page.tsx:59-70` — `useEffect` triggers `getWorkflows(...).then((runs) => setRecentRuns(runs))`. There is no `AbortController`, no `isMounted` flag, no cleanup. If the user logs out (sets `isAuthenticated=false`, redirects to /login) before the fetch resolves, `setRecentRuns` is called on an unmounted component → React 18 just warns, but in strict-mode dev double-mount the fetch fires twice. Same pattern in:
  - `frontend/src/components/settings/AccountSettings.tsx:24-31` (`getMe` no abort)
  - `frontend/src/components/history/WorkflowHistory.tsx:66-74` (initial `getWorkflows`)
  - `frontend/src/components/history/WorkflowHistory.tsx:76-93` (`handleSelectRun` → `getWorkflow`)
  - `frontend/src/app/dashboard/page.tsx:99-104` (post-pipeline refresh inside `handleWebSocketMessage`)
None of these wrap fetches in AbortController. For long pipelines + tab close, the `getWorkflows` fetch in step 4 lingers until network completes.

### H5 — `dashboard/page.tsx` `handleWebSocketMessage` has stale-closure risk
`frontend/src/app/dashboard/page.tsx:73-302` — The `useCallback` declares `[]` as deps (line 302) but references `getToken()` and triggers `getWorkflows` which uses the FRESHEST token via `getToken()` from localStorage rather than the in-state `token`. That's defensible (localStorage is the source of truth), but the inline arrow at line 101-104 captures `setRecentRuns` which is React-stable. The bigger smell is line 187-201 — `setMessages((msgs) => { ... lastMsg = msgs[msgs.length - 1]; ... })` mixes async-stale `pptContentRef`/`prototypeContentRef`/`userStoryContentRef` reads (refs, fine) with `setStreamingContent` setter access. There's no test coverage for the "second `complete` event arrives while first is still being processed" case — `lastMsg.role === "assistant"` guards duplicate appends, but a fast double-`complete` could still race.

### H6 — Multiple WebSocket connections per session — no enforcement
`frontend/src/hooks/useWebSocket.ts:178-191` — Each page mount opens a new WS. Three tabs of /dashboard → three WS connections, each authenticated with the same JWT. The backend (`websocket.py:92-176`) has no per-user connection cap. A user can open 50 tabs and bind 50 pipelines (one per tab — within tab a second `run_pipeline` is gated at line 216, but cross-tab is unconstrained). Each pipeline burns Bedrock quota independently. Combined with the `bedrock_tokens_daily` alarm (monitoring/main.tf:688-710) this is detectable but not prevented. Phase A didn't flag this.

### H7 — `useWebSocket` retry-loop holds wsRef closure across reconnects
`frontend/src/hooks/useWebSocket.ts:53-160` — On reconnect, `cleanup()` nulls onopen/onclose/onerror/onmessage and closes. The retry sets `setTimeout(connect, delay)`. If the component unmounts during the retry timeout, `intentionalCloseRef.current = true` at line 187, but the queued `connect()` call inside the `setTimeout` will still fire — opening a new WS that is then immediately leaked (no `wsRef` consumer survives because the `useEffect` cleanup just ran). Fix: clear `retryTimeoutRef` in the unmount cleanup at line 188 too.

### H8 — `cancel_pipeline` lacks per-user/session scoping in WS handler state
`backend/app/api/websocket.py:184, 243-262` — `current_pipeline_task` is a single Optional[Task] per WS connection. Cancellation is correct for the *current* connection's task — but if the same user has two tabs both running pipelines, sending `cancel_pipeline` from Tab-A's WS only cancels Tab-A's task. The FE has no UI to cancel a pipeline started in another tab. Combined with H6 this is the cost surface for runaway Bedrock token usage.

---

## MEDIUM

### M1 — Missing DB indexes on hot query columns
`backend/alembic/versions/0001_initial_schema.py:64-125` — None of these are indexed:
- `chat_sessions.user_id` — every `list_chats` (`chats.py:83-88`) scans all rows.
- `chat_sessions.last_activity` — used as ORDER BY in `list_chats`; full sort.
- `messages.chat_session_id` — every `getChat` join (chats.py:118-127 via the `messages` relationship `order_by="Message.created_at"`) needs this.
- `messages.created_at` — used for in-session ordering.
- `workflow_runs.user_id` — every dashboard load (`page.tsx:64-70`) and history page (`WorkflowHistory.tsx:69-71`) full-scans.
- `workflow_runs.created_at` / `status` — common filters.

On SQLite (dev) it's invisible; on Postgres single-EC2 with thousands of rows per user it's a slow-query bomb. Phase A didn't itemise these.

### M2 — No `ON DELETE CASCADE` on FKs + no ORM cascade
`backend/app/models/chat.py:18,40-42` and `backend/app/models/workflow.py:18` — `ForeignKey("users.id")` and `ForeignKey("chat_sessions.id")` lack `ondelete="CASCADE"`. The migration at `alembic/0001_initial_schema.py:64-125` also defines plain `ForeignKeyConstraint` with no cascade clause. `relationship()` in `models/chat.py:29-31` lacks `cascade="all, delete-orphan"`. Net effect: the workaround at `chats.py:155-157` (`db.query(Message).filter(...).delete()` before `db.delete(chat_session)`) is the only protection against FK violations on DELETE. Deleting a User via SQL would FK-violate. Future user-deletion endpoint will have to replicate the same dance for `chat_sessions`, `messages`, `workflow_runs`, `revoked_tokens`. Phase A flagged the chat-session case.

### M3 — `final_output` and `agent_outputs` JSON columns unbounded
`backend/app/models/chat.py:26` (`final_output = Column(Text, nullable=True)  # JSON string of Final_Output`) and `backend/app/models/workflow.py:24` (`agent_outputs = Column(Text, nullable=True)  # JSON array of per-agent thinking/output`). `agent_outputs` collects per-agent `thinking` + `output` strings from a 12-agent pipeline (`websocket.py:550, 583-601`). Each agent's `output` can be tens of kilobytes; a complete workflow can serialise to >1 MB. There is no size cap. The pg_dump backup picks this up nightly. The `MessageResponse` schema (schemas.py:45-54) trivially returns `content`, but `agent_outputs` ships in workflow detail GETs. No paging, no truncation.

### M4 — `DashboardLayout` has 5+ unused props + dead state
`frontend/src/components/layout/DashboardLayout.tsx:51-76` destructures the following props that are NEVER read in the function body (verified via grep — only the type-declaration and destructure refer to them):
- `activeChatId` (line 51) — destructured, no body reference
- `messages` (line 52) — destructured, no body reference
- `onSendMessage` (line 59)
- `onSendMessageWithMode` (line 60)
- `onSelectChat` (line 61)
- `onNewChat` (line 62)
- `onDeleteChat` (line 63)
- `messageMode` (line 66)
- `chatTitleUpdate` (line 67)
- `processSteps` (line 68)

The page passes them in (`dashboard/page.tsx:580-597`) so the wiring chain is intact but unused — they were used by the old `Sidebar` which is dead code (confirmed). `currentWorkflowRunId` (DashboardLayout.tsx:117-119) is computed every render but never read. `recentRuns` is consumed only by `currentWorkflowRunId` calculation — itself unused. `onSelectWorkflowRun` is destructured at line 74 and not referenced in the body. Phase A flagged some of this; itemising the full list.

### M5 — `processStepsRef` initialised but never cleared across selects
`frontend/src/app/dashboard/page.tsx:36, 145-148` — `processStepsRef.current = []` after `complete`. Good. But on `handleSelectChat` (line 430-490) the ref is NOT reset. If the user switches to a chat that had embedded `<!--steps:JSON-->` markers (the Phase-A-flagged unreachable prefix), the `setProcessSteps([])` at line 435 clears state but `processStepsRef.current` retains the previous chat's steps. Next `complete` event uses the stale ref content. Mostly hidden by the unreachable-prefix bug, but a latent issue if/when steps persistence is re-enabled.

### M6 — CreationHub workflow list inconsistent with LibraryPage categories
`frontend/src/components/home/CreationHub.tsx:11-47` lists 5 workflows (user_stories, ppt, prototype, app_builder, custom). `frontend/src/components/library/LibraryPage.tsx:10-17` lists 6 categories (all, user_stories, ppt, prototype, app_builder, custom) — "all" is a UI affordance, so really 5 + "all", consistent. `frontend/src/components/history/WorkflowHistory.tsx:22-32` shows the TYPE_META map with revision variants doubling the surface (user_stories + user_stories_revision, etc.). Phase A called this "5/6/5 inconsistency" — the actual mismatch is that CreationHub never offers revisions as a starting point (correct — revisions chain from a completed run), but the comment in Phase A undercounts. The real risk is that `app_builder` exists in CreationHub but is wired through `setUserStoryContent` (DashboardLayout.tsx:158-164 — `handleReviseAppBuilder` writes to `userStoryContent` because it has no `appBuilderContent` state — that's because `app_builder` output IS a user-story-shaped markdown). Adding a sixth category later (e.g. `voice`) will require 4 file edits in 4 places.

### M7 — `AccountSettings.handleChangePassword` `useCallback` deps incomplete
`frontend/src/components/settings/AccountSettings.tsx:33-65` — Deps `[currentPassword, newPassword, confirmPassword]`. References `getToken()` directly (line 49) — fine, that's a function call. Does not reference `setMessage`, `setChanging`, `setCurrentPassword`, etc. — React's setters are stable so it's correct. The issue is `useEffect` at line 24-31 has `[]` deps but reads `getToken()` from outside; the email is fetched once on mount and never refreshed. If the user changes their email in another tab and then returns, the display stays stale. Minor.

### M8 — `dashboard/page.tsx:524-532` `handleNewChat` accepts ChatSession but doesn't persist or call backend
The handler is wired to `onNewChat` (DashboardLayout.tsx:32) but DashboardLayout never invokes it (it's one of the unused props — see M4). The function exists in dashboard/page.tsx but is dead. Should be deleted along with the `Sidebar` cleanup.

### M9 — `handleSelectChat` writes empty preview state when `final_output` absent
`frontend/src/app/dashboard/page.tsx:480-484` — Clears `userStoryContent` / `pptContent` / `prototypeContent` when the loaded session has no `final_output`. But `setMessages(loadedMessages)` happens at line 463 BEFORE the conditional clear; if the user is mid-stream and they click a session in the (now-dead) sidebar, the existing preview content would flicker before the new one paints. Hard to repro in current UI because the sidebar is gone, but the function is still called somehow elsewhere — verify call sites.

### M10 — Pipeline `last_activity` not updated on `agent_complete`
`backend/app/api/websocket.py:576-603` — During pipeline execution, `last_activity` on the chat session is updated ONLY at the user-message persistence (line 526) and the final assistant persistence (line 716-718). A 10-minute pipeline keeps the session stamp at message-send time, so the `ORDER BY last_activity DESC` in `list_chats` may bury a session that's actively producing output behind a session the user just clicked on but didn't actually use. Minor UX, not a bug per se.

### M11 — Backend WebSocket trusts `chat_session_id` from `run_pipeline` payload
`backend/app/api/websocket.py:210-240` — When handling `run_pipeline`, the `chat_session_id` from the message is passed straight to `_handle_pipeline_execution` (line 237) without any prior ownership check. The check happens inside the helper at line 514-518 (user message persist) and is the GATING check — if no row matches, the user-message persist is skipped, but the pipeline ITSELF still runs, the WorkflowRun row is still created (line 495-506) with the user's `user_id` BUT the chat history goes nowhere. End-result: user gets workflow result, but the assistant message attempt at line 711-720 may also miss (see C1). Better to fail the request explicitly if `chat_session_id` doesn't belong.

---

## LOW

### L1 — Console logs left in production code
`frontend/src/hooks/useWebSocket.ts:70-79, 178` — Three `console.log` calls referring to token presence. Leaks an authentication-flow signal to anyone with devtools. Not a vuln; remove for hygiene.

`backend/app/api/websocket.py:161, 177, 211` — Three `print()` calls (`[WS] Connection accepted ...`). These bypass the logger so they're not captured by the CloudWatch log-shipper systemd unit (which is journald → /flowin/${env}/app log group). Switch to `logger.info`.

### L2 — `dashboard/page.tsx` ref naming inconsistent
`frontend/src/app/dashboard/page.tsx:36-41` — Some refs are `*Ref` (`processStepsRef`, `activePreviewSectionRef`) and some are `*ContentRef` (`pptContentRef`). One-letter inconsistency, low priority.

### L3 — `useWebSocket.ts:88-98` subprotocol comment claims server "echoes the selector, never the credential" — but `websocket.py:157` falls back to credential echo
The fallback at `websocket.py:156-158` echoes `bearer.<jwt>` if `flowin.v1` is not in `proto_list`. Modern FE always offers both, so this should never trigger in production. But if a smoke client offered only `bearer.<jwt>`, the server would echo the JWT in the handshake response — visible in CloudFront/nginx access logs (assuming WS upgrade was logged in detail). The comment at FE says "we always echo the selector" but the BE comment says the fallback echoes the credential. Either drop the fallback (close 4001 instead) or update both comments to acknowledge the leak path.

### L4 — `chats.py` uses `String` for IDs without index
`backend/app/models/chat.py:17,40` and `models/workflow.py:17` — Primary key is `String` (UUID v4 string form). UUID-as-string keys in Postgres are slower than `uuid` native type and bigger than `bigint` serials. Not a bug, but a future-proofing flag for high-row tables.

### L5 — `MessageResponse.role: str` not constrained
`backend/app/models/schemas.py:51` — Should be `Literal["user","assistant","system"]`. Lets a bad row in the DB (rare, but possible via raw SQL or a future code path) flow out as a garbage role string.

### L6 — `DashboardLayout` `headerPage` maps `settings` to `"history"`
`frontend/src/components/layout/DashboardLayout.tsx:307-311` — `mainView === "settings"` produces `headerPage="history"`. The AppHeader has no "settings" state to render, so this paints the History nav item as active when the user is on the Settings page. Minor UX bug.

### L7 — `useWebSocket` cleanup nulls handlers AFTER calling `ws.close()`
`frontend/src/hooks/useWebSocket.ts:58-66` — Order: assigns null to handlers, then `ws.close()`. The close call synchronously triggers the (just-nulled) onclose. That's fine, but it means `intentionalCloseRef.current=true` (set later in some paths) might race the close-event handler. Not a confirmed bug but the order is suspicious — the standard pattern is `intentionalCloseRef.current=true; ws.close(); null out handlers`.

### L8 — Frontend never calls REST `PUT /api/chats/{id}/messages` despite it being exported
`frontend/src/lib/api.ts:214-225` exports `addMessage` but no caller. The dashboard sends all messages via WebSocket. The REST route exists in `chats.py:162-196` and runs auth correctly, but it's effectively dead. Either delete the route + export, or document the use case.

### L9 — `delete_chat` 204 success returns `None` (correct) but `chats.py:159` explicit `return None`
Cosmetic. FastAPI handles 204 implicitly; the explicit `return None` is fine but unnecessary.

---

## TF concerns

### TF1 — DB connection pool not configured for Postgres
`backend/app/models/database.py:11-16` — `create_engine(settings.DATABASE_URL, ..., pool_pre_ping=True)`. No `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`. SQLAlchemy default: `pool_size=5`, `max_overflow=10` → 15 connections per worker.

`backend/app/core/config.py:74` — `DATABASE_URL: str = "sqlite:///./dev.db"`. In production this comes from SSM (see infra). No infra-side configuration of Postgres `max_connections`; the default Debian/Ubuntu Postgres ships with 100. Single uvicorn process × 15 connections × 1 instance = 15. But:

- The WebSocket handler opens `_get_db()` per message inside `while True` (e.g. line 281, 337, 406, etc.) — under load, hundreds of short-lived sessions per connection. `pool_pre_ping` runs a `SELECT 1` every checkout. With many concurrent WS clients each running `_handle_pipeline_execution` (which itself opens 4-5 sessions per pipeline at lines 493, 512, 615, 663, 679, 695) the pool can exhaust during a burst. No log/metric/alarm.

- No CloudWatch alarm on Postgres connection saturation (monitoring/main.tf:500-531 only watches the *uvicorn log* for `OperationalError` substring — that's the symptom, not the metric).

Fix surface: set explicit pool config in `database.py` (e.g. `pool_size=10, max_overflow=20, pool_timeout=30, pool_recycle=3600`), set `max_connections=200` in PG via user-data or SSM-driven postgresql.conf.

### TF2 — Postgres on EC2 backup story: only `pg_dump` heartbeat + EBS snapshots
`infra/modules/backups/main.tf:238-295` (daily AWS Backup plan) + `monitoring/main.tf:727-748` (pg_dump heartbeat alarm). The compute module tags the EBS data volume `Backup="true"` (compute/main.tf:62), so the daily AWS Backup runs an EBS snapshot of `/var/lib/postgresql`. Also: `pg_dump` runs hourly via systemd timer and PUTs to S3.

Concerns:
- **Snapshot ≠ logical backup**. EBS snapshots are crash-consistent, not Postgres-consistent. Restoring from EBS-snapshot of a running PG instance yields a database that requires WAL replay; if WAL is missing or corrupted on the snapshot, the chats/messages may be lost. The hourly `pg_dump` is the actual safety net, but it's `pg_dump`-from-running-db (not `pg_basebackup` + WAL archive), so RPO ≤ 1 hour at best.
- **No point-in-time recovery (PITR)**. RDS would give PITR for free. The current architecture has hourly granularity at best; mid-hour writes are lost on restore.
- **No alarm on `pg_dump` upload size dropping to zero**. The heartbeat fires when SampleCount < 1 in 2h; it does NOT fire when uploads succeed but write 0 bytes (e.g. `pg_dump` succeeded against an empty/corrupted db).
- **Restore drill cadence not enforced in TF**. The backup-vault doc (modules/backups/main.tf:347-355) recommends drills BEFORE enabling vault lock, but there's no scheduled run or pager. Vault lock is `enable_vault_lock = false` by default — operator action required.

### TF3 — No CloudWatch alarm on Postgres-specific metrics
`infra/modules/monitoring/main.tf` (all 977 lines) — covers host CPU/mem/disk/inode, nginx 5xx, Bedrock throttles + token cap, WS disconnect spike, agent errors, stuck workflows, certs, billing. NONE specifically for:
- Postgres connection count near saturation (would catch TF1's leak path).
- Postgres query latency (no `pg_stat_statements`-driven metric).
- `chat_sessions` / `messages` table row count growth (cost/data sanity).
- WAL disk usage.

The PG log ships (groups list at line 15-23), and `db_conn_error` (line 500-531) catches "could not connect" — but the bare `db_conn_error` alarm fires on a SINGLE log line per minute. Connection refused on one request is enough to page. May be too aggressive; `evaluation_periods=2` would be more reasonable.

### TF4 — `infra/modules/compute` doesn't expose DB tuning vars
`infra/modules/compute/variables.tf` and the user-data template do nothing for Postgres tuning. All of:
- `shared_buffers`
- `effective_cache_size`
- `max_connections`
- `work_mem`
- `wal_level` / `archive_mode` for PITR

… are left at Debian defaults. For a single-EC2 deployment serving multiple users with a chat-heavy workload, default `shared_buffers=128MB` is undersized. No Terraform-level escape hatch — operator has to ssh and edit `postgresql.conf` post-bootstrap (and that edit is not captured anywhere).

### TF5 — No automated WAL/PITR archival
Related to TF2 — `pg_dump` is the only logical-backup path. WAL is purged by Postgres after each checkpoint. To get RPO < 1h would require either `wal-g`/`pgbackrest` shipping WAL to S3, or migrating to RDS. Neither is in the infra modules.

### TF6 — Backups module S3 lifecycle: pg_dump expiry 365d but no glacier window check
`infra/modules/backups/main.tf:83-105` — `expire-pg-dumps` rule transitions current pg_dumps to Glacier IR after `transition_to_glacier_ir_days` (default unclear without reading variables.tf; check) and expires after `pg_dump_expiry_days`. Glacier IR has a 90-day minimum storage duration; deletes before that incur early-deletion fees. The variable validation at `backups/variables.tf` may enforce this, but the rule itself doesn't carry the constraint. If an operator sets `pg_dump_expiry_days=45` and `transition_to_glacier_ir_days=30`, S3 will charge for 90-15=75 days of phantom storage. Audit the validation block.

### TF7 — `enable_object_lock` and `enable_vault_lock` documented as one-way but defaults are off
`infra/modules/backups/main.tf:14, 308-320, 358-366` — Both are creation-time-only / one-way operations. The defaults are correctly cautious (`false`), but a fresh `terraform apply` to prod leaves backups UNLOCKED. An attacker with `s3:DeleteObject` (e.g. compromised admin role) can wipe backups before the daily snapshot. The Phase-A audit may have caught this in the IAM module; flagging here as a chat-data durability concern.

### TF8 — No CloudWatch alarm for `chat_sessions` row count growth or storage pressure
The `disk_data_high` alarm (monitoring/main.tf:440-463) covers raw disk-byte usage on `/var/lib/postgresql` — but Postgres's autovacuum can keep disk flat while table sizes balloon (dead-tuple bloat). For chat workloads with frequent inserts + occasional deletes (chat-session deletions cascade-delete messages via the manual two-step in chats.py:155), bloat can be significant. No `pg_stat_user_tables`-driven metric, no `pg_total_relation_size` heartbeat. Operationally captured by `disk_used_percent` only after the problem is acute.

---

## Summary

- 5 CRITICAL findings — most severe is C1 (cross-user assistant-message write, IDOR-class).
- 8 HIGH findings — concurrency races (H1/H2), retry-loop leak (H7), unbounded WS-per-user (H6), and the confirmed Phase-A mid-stream-loss (C5).
- 11 MEDIUM findings — schema/indexing gaps (M1/M2/M3), the full unused-props list for DashboardLayout (M4 — 10 dead props), and several state-management smells in dashboard/page.tsx.
- 9 LOW findings — hygiene, dead exports, comment drift.
- 8 TF concerns — DB pool unset (TF1), PG-on-EC2 backup story (TF2/TF5), missing PG alarms (TF3/TF8), no tuning escape hatch (TF4).

Phase A's call-outs on `Sidebar.tsx`/`ChatSessionItem.tsx` (dead) and `currentWorkflowRunId` (unused) are confirmed; `currentWorkflowRunId` is computed at DashboardLayout.tsx:117-119 every render but never read. `recentRuns` flows from page.tsx down to DashboardLayout but only feeds that dead calculation — the entire chain (page.tsx:44, 64-70, 99-104, 615; DashboardLayout.tsx:43, 73, 117-119) is removable. `onSelectWorkflowRun` similarly destructured but unused in DashboardLayout. `<!--steps:JSON-->` parser at dashboard/page.tsx:446-452 is unreachable (collected_steps never populated upstream) and is parse-overhead on every chat load.
