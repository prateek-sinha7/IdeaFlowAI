# Phase B Triage — deduplicated, classified by origin

**Raw counts before dedupe:** ~43 CRITICAL, ~88 HIGH, ~104 MEDIUM, ~100 LOW, ~72 TF concerns across 10 section reports. After dedupe, the issues fall into 5 groups by **origin and scope**.

---

## Group 1 — Caused or exposed by THIS branch (`infra-agent-integration`) [MUST FIX]

These are bugs introduced or directly enabled by the merge + our refactor work. Leaving them = ship a broken/insecure feature.

### G1-C1 — RCE surface in `backend/app/services/pptx_export.py` (NEW code this branch)
- `subprocess.run(["node", js_file], ...)` executes LLM-generated JS
- No sandbox, no memory cap, no CPU cap, no network egress restriction
- Inherits all env vars (Bedrock creds, DB password, IMDS reachable)
- f-string template interpolation lets adversarial LLM output escape the wrapper
- Flagged by §2, §3.3, §3.5, §3.8 (4 of 10 sections)
- **Fix:** Run Node as a separate user / cgroup / network namespace; whitelist env vars passed; switch from f-string to template file with sandboxed evaluation; add concurrent-invocation semaphore

### G1-C2 — `STATUS_ICON` missing `"cancelled"` key → dashboard crash
- `WorkflowHistory.tsx` STATUS_ICON map has no entry for `status="cancelled"`
- Renders `<undefined />` → JSX crash takes the whole dashboard down
- We introduced the `wr.status = "cancelled"` write; the FE wasn't updated
- **Fix:** Add `cancelled` to `WorkflowStatus` type + STATUS_ICON map + badge logic; remove stale `run.error === "Cancelled by user"` heuristic

### G1-C3 — `pipeline_cancelled` event dropped by frontend
- BE emits it on cancel (websocket.py:644-651)
- FE: not in `dashboard/page.tsx:75` allow-list, not in `useWorkflow.handlePipelineMessage` switch
- User clicks Stop → BE cancels → FE never updates `pipelineState.isRunning`
- **Fix:** Add to the FE message dispatcher and state transition

### G1-C4 — `agent_complete.output` field mismatch FE↔BE
- FE reads `event.data.output` (per `useWorkflow.ts`)
- BE only emits `output_length` (per `orchestrator_v2.py:373-383`)
- Result: live agent outputs in the progress panel may render as `undefined`
- **Fix:** Decide canonical name (`output_length`) and update FE

### G1-C5 — Cross-tenant write at `backend/app/api/websocket.py:711-715`
- Persists pipeline summary assistant message + bumps `chat_session.last_activity`
- Does NOT check `ChatSession.user_id == user.id` (the earlier user-message write at :514-518 DOES check — asymmetric guard)
- Attacker who knows another user's chat_session_id can inject arbitrary assistant messages
- We touched this WS handler in the refactor; this is the right time to fix
- **Fix:** Add user_id filter on the lookup

### G1-C6 — Mass-assignment via `agent_ids` (orchestrator_v2 path)
- `websocket.py:558-561` accepts ANY backend agent ID in custom_agents flow
- Includes dead `reverse_engineer` agents and per-pipeline `*_revision` agents
- Lets client resurrect the deprecated pipeline OR cross-inject (e.g., PPT agent into User Stories)
- **Fix:** Whitelist agent IDs by current pipeline_type's allowed set; reject unknowns with an error event

### G1-C7 — Skill content prompt-injection at `orchestrator_v2.py:290`
- User's saved skill content is PREPENDED to system prompt verbatim
- 64KB of arbitrary attacker-controlled prompt prefix per agent (self-injection scope)
- Wired through the per-user skill resolution we just patched in
- **Fix:** Cap skill length to a sane limit (e.g., 8 KB); add content-type validation; surround with a marker the agent is trained to treat as untrusted

### G1-C8 — `SkillManager.tsx:128` `useState(() => loadSkill())` bug
- `useState(fn)` only runs `fn` on first mount with `isOpen=false` → loadSkill **never** fires
- Users see empty content for agents that have saved skills
- Save then OVERWRITES server with empty content (data loss)
- **Fix:** `useEffect(() => { if (isOpen) loadSkill() }, [isOpen, agentId])`

### G1-H1 — `WebSocketDisconnect` short-circuits failure-mark
- `websocket.py:649-675` `except Exception` calls send_json BEFORE the DB write
- If WS already disconnected, send_json raises again → DB write bypassed
- WorkflowRun row stays at `status="running"` forever
- **Fix:** Move DB write BEFORE send_json (or wrap send_json in try)

### G1-H2 — Chunk duplication on retry persists to DB
- Both FE buffer AND `websocket.py:597` persistence buffer accumulate duplicated chunks across retry attempts
- Persisted `agent_outputs` JSON gets corrupted (not just live UI)
- **Fix:** Reset per-agent chunk buffer at the start of each retry

### G1-H3 — `pipeline_complete` emits regardless of agent failures
- No `pipeline_failed`/`pipeline_partial` event
- No FE check on `agents_completed < agents_total`
- A 1-of-12 agent failure marks workflow `status="completed"` with garbage final output
- **Fix:** Emit `pipeline_partial` (or set `status="failed"`) when any agent emits `agent_error`

### G1-H4 — Bedrock throttling not classified retryable in orchestrator_v2
- `orchestrator_v2.py:340-345` only catches `RemoteProtocolError`/`ReadTimeout`/"chunked"
- `llm_errors.py` already classifies `ThrottlingException` as retryable
- Throttle on any agent = that agent gets a fake error then orchestrator continues with garbage context (G1-H3 cascade)
- **Fix:** Add `ThrottlingException`, `ServiceQuotaExceededException`, `ModelTimeoutException` to the retry set; surface as transient

### G1-H5 — `POST /api/workflows/export-pptx` accepts free-form `dict`
- No Pydantic schema → no validation, no type-safety
- Caller can pass arbitrary fields (storage waste, log noise, future bugs)
- **Fix:** Define `ExportPptxRequest(BaseModel)` with the 4 known fields, cap on `js_code`/`html` size, UUID validation on `workflow_id`

### G1-H6 — Substring match in extraction strategy is too greedy
- `code/generator/ppt-code` substring matches `app-code-generator`, `barcode-extractor`, `prototype-generator`, `code-reviewer`
- A user with both PPT and app_builder runs can get the wrong artifact
- **Fix:** Use exact match against the registered `ppt-code-generator` ID

### G1-H7 — Iframe sandbox regression
- `PPTPreview.tsx:162` and `PrototypePreview.tsx:105` use `allow-scripts allow-same-origin`
- Combination effectively bypasses sandbox (the iframe can read parent localStorage including JWT)
- **Fix:** Drop `allow-same-origin`; if downloads/popups needed for PPT, add only those flags explicitly

---

## Group 2 — Pre-existing security debt [DEFER to a dedicated security PR]

These existed before this branch; we didn't worsen them. Fixing them here would balloon scope and tangle the diff. They deserve a focused security PR with proper review.

- **JWT issues:** HS256 + 24h tokens, no `iss`/`aud`/`nbf` validation, no refresh-token rotation, plaintext SECRET_KEY accessible via SSM session manager
- **bcrypt:** implicit rounds, silent 72-byte truncation, no max_length on password fields
- **Password policy:** length-8 only, no complexity, no breach check (HIBP), no history, no failed-attempt lockout
- **Account creation:** no email verification, `/register` 409 leaks user enumeration
- **No application-level rate limiting** (only nginx)
- **No CSP / security-header middleware** (`backend/app/main.py`)
- **`change_password` weaponization:** caller can blanket-revoke OTHER sessions while keeping their own (allows new == current, doesn't revoke caller's token)
- **Stored XSS in `UserStoryPreview.tsx:217-225`** via `dangerouslySetInnerHTML` on LLM acceptance criteria
- **Mass-role injection** via `PUT /api/chats/{id}/messages` (`role` field unvalidated)
- **No size cap on Text columns** (DoS surface)
- **Cancellation gap on chat path** (chat orchestrator can't be cancelled; pre-existing — see Group 4 first)
- **Per-message JWT re-validation skipped on pipeline messages** (the policy WE inherited from infra branch hardening; was a deliberate exclusion, not a regression)

---

## Group 3 — Dead code cleanup [DEFER to a cleanup PR]

The diff would be additive (large deletions but conceptually simple). Best done in its own PR for reviewability.

- `Sidebar.tsx`, `ChatSessionItem.tsx`, `ChatPanel.tsx`, `MessageBubble.tsx`, `ChatInput.tsx`, `ErrorMessage.tsx`, `TypingIndicator.tsx`, `ProcessSteps.tsx` — confirmed no consumers
- `collected_steps` / `<!--steps:JSON-->` machinery (both BE-emit and FE-parse paths dead)
- `parseStreamMessage` whitelist (dead validation)
- `PATCH /api/workflows/{id}` endpoint (not called from frontend)
- `workflow_title_update` FE handler (BE never emits)
- `REVERSE_ENGINEER_AGENTS` and `AgentsPopup` references (UI removed reverse_engineer)
- ~800 LOC total

---

## Group 4 — Architectural decisions needed [REQUIRES PRODUCT INPUT]

Can't fix without you choosing direction.

- **Chat path runs full 7-phase pipeline for every chat message** (~5× Bedrock spend for invisible UI). Options: delete chat path, or re-scope chat orchestrator to a single Q&A agent.
- **Two parallel orchestrators** (chat `AgentOrchestrator` + workflow `WorkflowOrchestrator`) with overlapping logic. Should they be unified?
- **Chat UI:** dead code suggests chat is being deprecated. Confirm direction?
- **No pagination** on chat list / message history / workflow list. Scaling decision.
- **PG-on-EC2 backup story:** no WAL archive, no PITR, RPO ≤1h. Acceptable for now or upgrade to RDS?
- **Per-user connection limits:** trivial DoS via 50-tab attack. Acceptable for trusted-user scope or hard-required?

---

## Group 5 — Terraform-specific concerns [GOES TO PHASE C]

These will be handled by the Phase C agents (TF security + breakages audit). Carrying them through Phase B-fix would duplicate Phase C's scope.

- IAM permission scope (ssm-read, bedrock-invoke region pinning, kms-decrypt ViaService)
- SNS topic policy validation
- KMS multi-region / rotation
- CloudWatch alarm thresholds / coverage
- Disk usage observability (/tmp + EBS)
- Container resource limits (cgroup CPU/memory caps)
- Backup vault / object lock
- DB connection pool tuning
- ECR image lifecycle (size growth)
- `enable_object_lock` / `enable_vault_lock` defaults
- 8 more TF items
