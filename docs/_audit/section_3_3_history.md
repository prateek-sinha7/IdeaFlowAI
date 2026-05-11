# Phase B Audit — §3.3 History + §B4

Scope: `frontend/src/components/history/WorkflowHistory.tsx`, `frontend/src/components/results/FilesTab.tsx`, `backend/app/api/workflows.py`, `backend/app/models/workflow.py`, `backend/app/services/pptx_export.py`. Findings indexed by severity. Phase A findings are re-affirmed and extended; new ones are flagged "[NEW]".

---

## CRITICAL

### C1. `Sidebar` crashes on `status="cancelled"` runs (undefined STATUS_ICON) [NEW]
- File: `frontend/src/components/sidebar/Sidebar.tsx:43-53,159-160,177`
- `STATUS_ICON` / `STATUS_COLOR` are plain object literals keyed by the three statuses the TS type advertises (`running | completed | failed`). At runtime the backend writes `status="cancelled"` (websocket.py:619). The sidebar then does:
  ```
  const StatusIcon = STATUS_ICON[run.status];     // -> undefined
  const statusColor = STATUS_COLOR[run.status];   // -> undefined
  ...
  <StatusIcon ... />                               // React renders nothing, but if JSX hits a property access on undefined it throws
  ```
  Once any cancelled run lands in the sidebar list, `<StatusIcon />` is `<undefined />`, which React 18+ surfaces as `Element type is invalid` — a full component-tree crash that takes the whole sidebar (and dashboard navigation) down. This is the same root cause as the type-narrowing problem in WorkflowHistory but with worse failure mode.

### C2. `POST /export-pptx` is unauthenticated against an arbitrary code-execution path
- File: `backend/app/api/workflows.py:128-227`, `backend/app/services/pptx_export.py:95-151`
- The endpoint accepts `js_code` (Strategy 2) and `html` content (Strategy 3) from any logged-in user and substitutes them into a Node script template via f-string interpolation (pptx_export.py:107 — `{func_code}` injected into a script body), then spawns `node` against the result. The function name `generatePresentation` is fixed but everything inside the body is attacker-controlled. This is a deliberate eval-by-design — Node executes with the backend container's filesystem credentials (UID 10001, but with read of the venv, /opt/pptx, /tmp, /app/skills bind-mount, and outbound network).
- Concrete impact:
  - Read any file readable by `flowin` UID via `require("fs").readFileSync(...)`.
  - Exfiltrate via outbound network (`fetch(...)` available in Node 20).
  - Mount/exhaust `/tmp` (each call creates an unbounded tempdir — see C3).
  - Pivot via `host.docker.internal:5432` to Postgres (Postgres only requires password, and `flowin` user creds may be readable via `/etc/flowin/app.env` if bind-mounted; in current compose `/etc/flowin/app.env` is loaded as env_file but not bind-mounted into FS, so DATABASE_URL is in env).
- Authentication exists (`Depends(get_current_user)`) but is the only gate — there's no quota, throttle, or content allowlist. Any registered user can issue this attack.

### C3. Node subprocess explosion + `/tmp` exhaustion [NEW]
- File: `backend/app/services/pptx_export.py:90,156-159`, `backend/app/api/workflows.py:128-227`
- No semaphore, no concurrency cap, no rate limit at app level. Each call:
  - `tempfile.mkdtemp(prefix="pptx_export_")` — creates a directory in `/tmp` (no override; Docker container's writable layer)
  - spawns `subprocess.run(["node", ...], timeout=30)` — uvicorn worker is async but `subprocess.run` is synchronous and blocks the event loop for the entire 30-second timeout window.
- Backend has 4-worker uvicorn × 30s timeout = an attacker can DoS the entire pipeline thread pool with 4 concurrent in-flight exports. Each one consumes ~50-200MB RSS for Node (pptxgenjs loads); 4 concurrent ~ 800MB. Container limit is 8GB (docker-compose.yml:110), so memory-bound at ~40 concurrent before OOMKiller fires.
- `/tmp` cleanup is in a `finally` block but **catches all exceptions silently** (pptx_export.py:178). If the worker crashes mid-run (e.g. SIGKILL from OOM, or the FastAPI request is cancelled mid-`subprocess.run`), the tempdir leaks. Even a clean exit takes time: with 30s timeout, an attacker requesting in a loop accumulates leaks.

### C4. Node script template — code-injection breakout of pptxgenjs path
- File: `backend/app/services/pptx_export.py:95-151`
- `pptxgenjs_path` is interpolated via f-string into a JS string literal (`require("{pptxgenjs_path}")`). On Linux this is fine because Path() resolves clean strings. However `PPTX_NODE_MODULES_DIR` is an env var (line 30) and the path can contain `"` if the operator sets a pathological override. Not user-controlled in production but worth noting.
- More worrying: `out_path` is a controlled Python-built string (line 93) but `func_code` (line 107 substitution) is fully user-controlled (after the limited regex sanitization on lines 53-71). The sanitization only fixes specific syntactic patterns. An attacker can:
  - Use backticks (template literals) to break out of an enclosing function comment.
  - Embed `*/` to close pseudo-stripped markdown fences and inject preceding statements.
  - Define a colliding `main()` so the wrapper at line 126 calls attacker code instead.
  - Override `Module._resolveFilename` itself before the function is defined.
- The "sandbox" assumption is non-existent: `func_code` runs in the same Node process as the orchestration wrapper.

---

## HIGH

### H1. `WorkflowStatus` type does not include `"cancelled"` (Phase A finding, expanded)
- File: `frontend/src/types/index.ts:188`
- Type: `"running" | "completed" | "failed"` — three states. Backend writes a fourth.
- Knock-on effects beyond WorkflowHistory:
  - `Sidebar.tsx:43-53,159-160` — runtime crash (see C1).
  - `WorkflowHistory.tsx:392-404` — falls through to the "Running" else branch (Phase A).
  - `WorkflowHistory.tsx:156-158` — "Done" badge correctly hidden, but no badge shown for cancelled in detail view header.
  - `DashboardLayout.tsx:117-119` — `currentWorkflowRunId` filter only matches `status === "completed"` so cancelled runs are silently excluded from revision lookups; that's actually correct behaviour but not deliberate.
- TS type assertion `raw.status as WorkflowRun["status"]` in `api.ts:279` masks the issue — runtime values diverge from compile-time type with no warning.

### H2. Stale `run.error === "Cancelled by user"` heuristic
- File: `frontend/src/components/history/WorkflowHistory.tsx:396-404`
- Phase A finding confirmed: backend cancel path (websocket.py:614-629) writes `status="cancelled"` but never sets `error` — the cancellation is a non-error terminal state. The heuristic check `run.error === "Cancelled by user"` is unreachable code. All cancelled runs render as "Running" (matched only in `run.status === "failed"` branch, which is itself a cancelled run not failed run).

### H3. PATCH endpoint terminal-status whitelist omits `"cancelled"` (Phase A)
- File: `backend/app/api/workflows.py:278`
- `if request.status in ("completed", "failed"):` only sets `completed_at` for two terminal states. A PATCH with `status="cancelled"` updates the status but leaves `completed_at` as None. Currently the only writer of cancelled status is the WS handler (which sets completed_at directly via SQLAlchemy at line 620), so PATCH is dead for this case, but the endpoint silently accepts the request and lies in the response.

### H4. `POST /export-pptx` accepts free-form `dict` (no Pydantic schema) (Phase A)
- File: `backend/app/api/workflows.py:130`
- `request: dict` — FastAPI provides no validation; missing keys default to `""` (lines 147-151). Type errors (passing array as `js_code`) error at runtime with an opaque 500.
- Combined with C2 this is the entry point for arbitrary code injection. No declared content-type assumption either.
- Additionally there's no schema/swagger entry for this endpoint, so consumers must read the source to know the shape.

### H5. `agent_outputs` JSON column has no size cap [NEW]
- File: `backend/app/models/workflow.py:24`, `backend/app/api/websocket.py:626,685`
- Column is `Text` (Postgres `text` — effectively unbounded). The cancel path (websocket.py:626) writes `json.dumps(agent_outputs_collector)`. The pipeline collects every agent's `thinking` and full `output` (lines 594-601). For app-builder/prototype pipelines with multi-page output, the JSON blob is routinely 100-500KB and can exceed 1MB.
- The frontend then ships every row over the wire on `GET /workflows` (the LIST endpoint returns `agent_outputs` per row — workflows.py:97-125; no projection). With `limit=100` (default in WorkflowHistory.tsx:70), a fresh user can receive ~50MB JSON payload, blocking the API thread.
- Nginx `client_max_body_size 1m` (bootstrap-ec2.sh:579) applies to *requests*, not responses — but the API path is `proxy_buffering off` (line 630) which is good. Worst case is the response uses up the entire socket bandwidth for tens of seconds.
- Frontend parses every row's `agent_outputs` field on receipt (`api.ts:269-273` — try/catch around `JSON.parse`). On invalid JSON it silently sets `agentOutputs = undefined` — partial-write data could yield this.

### H6. Substring extraction strategy matches `app-code-generator` falsely (Phase A)
- File: `backend/app/api/workflows.py:163`
- `if "code" in aid or "generator" in aid or "ppt-code" in aid:` — `app-code-generator` (registry.py:789) matches both `"code"` and `"generator"`. If a user clicks Download PPTX on the wrong workflow (e.g. app_builder run misclassified), the export will try to run TypeScript/markdown as JS code and either silently fall back to the error-slide path or hard-crash the Node subprocess with a stderr leak (see H8).
- The same Strategy 1 also doesn't check `agent` order — first match wins. For ppt pipelines the right agent is at order=3, but with custom agents from `agent_ids` (websocket.py:484-489) the index isn't guaranteed.

### H7. Search only matches `r.title` (Phase A)
- File: `frontend/src/components/history/WorkflowHistory.tsx:117`
- `r.title || ""` only — input/output/agentOutputs are not searchable. Users searching for content keywords get empty results. Low severity individually but reported as Phase A so reaffirmed.

### H8. Error response leaks Node stderr to client [NEW]
- File: `backend/app/services/pptx_export.py:163-165`, `backend/app/api/workflows.py:217-220`
- On Node failure, the service raises `RuntimeError(f"PPTX generation failed: {err}")` with first 300 chars of stderr. The route wraps in `HTTPException(status_code=500, detail=f"Failed to generate PPTX: {str(e)[:200]}")`. The combined 500 response body contains 200 chars of Node stderr, which can include:
  - Absolute paths inside the container (`/app/...`, `/opt/pptx/...`).
  - Internal pptxgenjs error structure.
  - In rare cases, fragments of the attacker's own injected code (echoes the failing line in stack traces).
- Net: hostile input → reflected error message containing internal paths. Low-risk on its own; meaningful if combined with C4.

### H9. W19 doesn't render `thinking` field of agent_outputs (Phase A)
- File: `frontend/src/components/history/WorkflowHistory.tsx:131-135,184-216`
- `AgentThinkingEntry` (`types/index.ts:205-213`) has both `thinking` and `output`. The detail view destructures `output` only (line 211). The backend collects and persists both (websocket.py:595, 626). User-visible signal lost.

### H10. DELETE swallows errors silently and optimistically removes (Phase A)
- File: `frontend/src/components/history/WorkflowHistory.tsx:101-111`
- `await deleteWorkflow(...)` is in a try/catch with empty catch. On any failure (404, 500, network), the run is still removed from local state via `setRuns((prev) => prev.filter(...))`. Reloading the page brings the row back, surprising the user.
- The lack of a 4xx surface also masks the actual permission situation if a future revision adds row-level checks.

### H11. Cancel duration uses `time.monotonic` while success/failure use datetime delta (Phase A)
- File: `backend/app/api/websocket.py:573,609,670,687`
- Cancel: `round(time.monotonic() - monotonic_start, 1)` (line 609).
- Failed/completed: `(datetime.now(timezone.utc) - execution_start).total_seconds()` rounded to 1.
- Functionally equivalent in seconds but if NTP clock skews backward during a long pipeline, the datetime-based one can go negative and ship a misleading `duration` to the client.

---

## MEDIUM

### M1. LIST `/workflows` has no pagination upper bound
- File: `backend/app/api/workflows.py:97-125`
- `limit: int = 50` default, no `Query(le=...)` cap. Client can pass `?limit=10000`. Combined with H5 (unbounded agent_outputs per row), a single LIST call can pull arbitrary GB of JSON.
- `offset` similarly uncapped — `?offset=100000000` is allowed (Postgres can handle it but it's a slow seq-scan on the index).

### M2. CreateWorkflow `valid_types` whitelist misses revision and new types [NEW]
- File: `backend/app/api/workflows.py:72`
- `valid_types = ("user_stories", "ppt", "prototype")` — but frontend `WorkflowType` includes `user_stories_revision`, `ppt_revision`, `prototype_revision`, `app_builder`, `app_builder_revision`, `custom` (types/index.ts:186).
- However, the actual create path goes through WS (websocket.py:495-506) which uses the raw `pipeline_type` string with no validation. So this endpoint is effectively dead-code for revision/new types — `POST /workflows` is only callable for the three classic types but cannot trigger a revision. Inconsistent with reality.

### M3. PATCH endpoint has no status-value whitelist [NEW]
- File: `backend/app/api/workflows.py:254-293`
- `request.status` is `Optional[str]` with comment "completed | failed". A client can PATCH `status="foobar"` and it sticks (line 277 just assigns). The frontend then does `status: raw.status as WorkflowRun["status"]` (api.ts:279) and renders the unmapped value via the fall-through "Running" badge. Pollutes the data model.

### M4. `POST /export-pptx` HTML scan regex is brittle [NEW]
- File: `backend/app/api/workflows.py:173-206`
- The regex `r'<script[^>]*>([\s\S]*?)</script>'` is greedy-non-greedy on script tags. Won't handle:
  - Inline `</script>` strings inside a JS string literal (matches early).
  - Self-closing or void script tags.
  - Comments containing `function generatePresentation`.
- An adversarial input with `<!-- function generatePresentation() {} -->` in HTML will pass through and be executed because the depth-counter scan in lines 175-189 doesn't know about JS comments.

### M5. `tempfile.mkdtemp` cleanup ignores failures silently [NEW]
- File: `backend/app/services/pptx_export.py:173-179`
- `try: ... except Exception: pass` — `os.rmdir` fails if any files remain (e.g. partial write after timeout), but the failure is suppressed. Combined with C3 → directories leak indefinitely.
- Should use `shutil.rmtree(temp_dir, ignore_errors=True)` to delete recursively.

### M6. Race: DELETE workflow while it's running [NEW]
- Files: `backend/app/api/workflows.py:296-321` + `backend/app/api/websocket.py:617,665,681`
- DELETE endpoint allows deletion regardless of status. If user deletes a `status="running"` row from another tab while the WS handler is still streaming:
  - Cancel path (line 617): `wr` is None, `if wr:` skips. No completed_at write — harmless because row is gone.
  - Failed path (line 665): same, harmless.
  - Completed path (line 681): same, harmless.
  - HOWEVER the message persistence path (line 704-720) doesn't check workflow existence, so the chat_session continues to receive `summary` text. Acceptable but confusing.
- No FK CASCADE concern here because there are no child tables.

### M7. Two tabs viewing the same workflow concurrently — both fetch detail [NEW]
- File: `frontend/src/components/history/WorkflowHistory.tsx:76-93`
- `handleSelectRun` does a GET on click. With two tabs open and a running workflow, both will fetch the same partially-complete row. No deduplication; no cache invalidation. Low-impact; each fetch is independent.
- More concerning: a running workflow's `output` is None and `agent_outputs` is None until the terminal write. Detail view shows "No preview available" + 0 agents. Reasonable UX but undocumented.

### M8. FilesTab fetches workflow list to guess workflow_id (wrong workflow risk) [NEW]
- File: `frontend/src/components/results/FilesTab.tsx:144-157`
- The "Download PPTX" button does a `fetch /api/workflows?type=ppt&limit=20`, then tries to match a workflow by `output?.includes(h1[1])` (substring of the H1 title from the rendered HTML). If that fails, picks `runs[0]` (line 156) — most recent.
- For the same user with multiple PPT runs sharing similar titles, this can pick the **wrong** workflow's `agent_outputs` → wrong code → wrong PPTX. The endpoint will then try Strategy 1 which silently uses the wrong run's Agent 3 output. User has no signal anything's wrong; download succeeds with content from a different presentation.

### M9. Image-size growth from Node addition [NEW] [Phase B §3.8 overlap]
- File: `backend/Dockerfile:91-97,136-140`
- Adding pptxgenjs (~50MB) + Node binary (~80MB) + libstdc++6 explains the 453MB → 591MB jump. ECR storage cost: 10 images × 138MB extra = ~1.4GB extra ECR storage per env. At $0.10/GB-month ≈ $0.14/env/month — trivial. Pull time on EC2 first-time fresh pull is now ~10s longer over public ECR endpoint.
- More material: the Node runtime adds **attack surface** to the backend image — see C2/C4.

### M10. Concurrent invocation: no Semaphore in pptx_export
- File: `backend/app/services/pptx_export.py:40-179`
- See C3 — but as a standalone concern, the service is synchronous (`subprocess.run` blocking) inside an async FastAPI route, blocking the event loop. Should be `asyncio.create_subprocess_exec` + `await proc.wait()`, or run in a thread pool with a semaphore cap.

### M11. Cancel path doesn't log the partial-output collector size [NEW]
- File: `backend/app/api/websocket.py:614-627`
- `wr.agent_outputs = json.dumps(agent_outputs_collector)` can be MB-sized for an interrupted multi-page run. No cap, no log signal. See H5.

---

## LOW

### L1. `formatDuration(seconds)` rounding [NEW]
- File: `frontend/src/components/history/WorkflowHistory.tsx:48-52`
- Returns `""` for `seconds === 0`, which displays as "" but `if (!seconds)` is truthy for `0` as well as `undefined`. A genuinely zero-duration row (sub-100ms) displays nothing instead of "0s". Minor.

### L2. `formatDate` not i18n-aware [NEW]
- File: `frontend/src/components/history/WorkflowHistory.tsx:34-46`
- Returns "Just now" etc in en-US. Localization debt.

### L3. Detail view's "DONE" badge is hard-coded for every agent (line 200) [NEW]
- File: `frontend/src/components/history/WorkflowHistory.tsx:200-202`
- Every agent in `agent_outputs` is labeled "DONE" regardless of whether the workflow was cancelled mid-run (in which case the last agent may not have completed). The `agent.duration` field would be null for an incomplete agent but the badge ignores it.

### L4. `agent.output.slice(0, 1200)` truncation indicator [NEW]
- File: `frontend/src/components/history/WorkflowHistory.tsx:210-213`
- 1200-char cap; appends `"\n...[truncated]"`. No "Show more" affordance. For App Builder/Prototype with 32k token agents this loses 95%+ of the output. Functional but not great UX.

### L5. `handleDownloadAll` setTimeout 150ms stagger [NEW]
- File: `frontend/src/components/results/FilesTab.tsx:181-183`
- Each download triggers via setTimeout 150ms apart. For PPTX (server-side async), 150ms is far too short — the second download starts before the first response. With Node subprocess concurrency this becomes a self-DoS for users on slow connections. Minor because per-user concurrency is low.

### L6. `downloadBlob` doesn't revoke object URL for blob: protocol [NEW]
- File: `frontend/src/components/results/FilesTab.tsx:252-267`
- Lines 254-256 detect `blob:` prefix and skip `URL.revokeObjectURL`. But the blob: URL was created in `handleDownload` line 167 from `URL.createObjectURL(blob)` and stored as `file.content`-ish via the workflow chain. Browser will eventually GC the blob, but memory leak window is the lifetime of the FilesTab component.

### L7. `delete_workflow` 404 doesn't distinguish "doesn't exist" from "not yours" [NEW]
- File: `backend/app/api/workflows.py:307-317`
- Same response for both, which is the right choice for IDOR protection. Noted as positive — keep it.

### L8. PATCH endpoint allows status downgrade [NEW]
- File: `backend/app/api/workflows.py:276-279`
- A user can PATCH a `status="completed"` row back to `status="running"`. No state-machine enforcement. Combined with M3, the database can hold any string at any time.

### L9. Frontend filter group `typeGroups` misses some types [NEW]
- File: `frontend/src/components/history/WorkflowHistory.tsx:285`
- `["all", "user_stories", "ppt", "prototype", "app_builder"]` — `custom` workflows are countable in `typeCounts` but no filter tab; they only show under "all". Minor.

### L10. The Sidebar's `STATUS_ICON` map is not typed
- File: `frontend/src/components/sidebar/Sidebar.tsx:43-53`
- No `Record<WorkflowStatus, ...>` annotation — adding `cancelled` to the type wouldn't surface this site as a TS error. Defensive-coding gap.

---

## TF concerns

### T1. /tmp is the container writable layer (no volume) [Phase B §B4 / Bootstrap-EC2]
- Files: `docker-compose.yml:88-93`, `infra/scripts/bootstrap-ec2.sh:181-201`
- The bootstrap mounts `/var/lib/postgresql` on the dedicated 50GB EBS data volume (`DATA_DEV=/dev/nvme1n1`). **The Docker overlay filesystem (where /tmp lives inside the container) is on the root EBS volume**, which is typically ~30GB.
- pptx_export writes to `/tmp` in the container — that maps to the Docker container's writable layer, which is on the EC2 root volume. The 8GB memory limit (compose:110) doesn't bound disk usage. An attacker exploiting C3 can fill the root volume, taking down nginx, dockerd, postgres-startup logs, etc.
- Mitigation suggestion not in scope: bind-mount a small tmpfs into the backend container for `/tmp` (e.g. `tmpfs: /tmp:size=200M`).

### T2. CloudWatch alarm on root disk fires AFTER nginx is already dead [NEW]
- File: `infra/modules/monitoring/main.tf:413-437`
- `disk_root_high` fires at `>80%` (default `disk_threshold_percent`) on `/` mount, with 2x300s evaluation = ~10 minutes. By the time the alarm fires, /tmp explosion (T1) has likely already brought down dockerd. The alarm is too slow for this failure mode.
- The data-disk alarm (lines 440-463) only watches `/var/lib/postgresql` — not the root volume's `/var/lib/docker/overlay2/...` where /tmp content lives. Correct paths but misses the most likely growth vector.

### T3. No CPU/memory bound on the Node subprocess [NEW]
- Files: `backend/app/services/pptx_export.py:157-159`, `docker-compose.yml:103-112`
- `subprocess.run(["node", js_file], ...)` — Node inherits the container's cgroup. Docker compose limit is 8GB for the entire backend. A pathological PPTX generator (deep recursion, large slide loop) burns the entire 8GB budget, OOMKilling uvicorn along with itself.
- No `nice`/`cpulimit`, no per-subprocess memory cap.

### T4. ECR image size growth is monitored but not alarmed [NEW]
- Files: `infra/modules/ecr/main.tf:79-108`, `infra/modules/monitoring/main.tf` (no rule)
- Lifecycle policy keeps last 10 images at any size. No alarm on per-image size growth. The 453→591MB jump (+30%) isn't flagged; future jumps to >1GB would only be caught on monthly cost review.
- Cost magnitude is small (see M9), but a CI-driven image-size budget gate would be cleaner than infra alarm.

### T5. Bootstrap doesn't install Node on EC2 host [NEW] [confirms by absence]
- File: `infra/scripts/bootstrap-ec2.sh` (no `node`/`npm` apt install)
- Confirms Node only runs inside the container — good defence boundary. Worth noting in audit because if a future refactor moves pptx_export to a host-side service, it would need a Node toolchain installed and that's not present.

### T6. CloudWatch InputTokenCount alarm doesn't cover Node subprocess CPU [NEW]
- File: `infra/modules/monitoring/main.tf:688-710`
- `bedrock_tokens_daily` catches LLM cost runaway. Node subprocess CPU runaway (from C2/T3) is not surfaced — the `cpu_high` alarm (lines 364-386) is host-level at 60% sustained 15min. A burst of malicious exports would spike CPU briefly but might not sustain past the threshold.
- The `flowin-stuck-workflows-check.timer` (lines 854-871 in bootstrap-ec2.sh) only watches workflow_runs status, not export subprocess count.

### T7. nginx rate limit on `/api/` is generic (120r/m) — no per-endpoint quota for export-pptx [NEW]
- File: `infra/scripts/bootstrap-ec2.sh:514-517,625-633`
- `flowin_api` zone is `120r/m` shared across the entire `/api/*` namespace. `POST /api/workflows/export-pptx` has no dedicated quota, so an attacker can burn 120 PPTX generations/minute per IP. That's 4 concurrent Node processes constantly (each ~10s realistic, 30s worst-case) → backend CPU + memory thrash.
- Login/register/change-password each have dedicated zones. Export-pptx (the only synchronous-subprocess-spawning endpoint) does not.

### T8. Backend logging doesn't structure subprocess invocations [NEW]
- File: `backend/app/services/pptx_export.py:164,170`
- `logger.error(f"Node.js PPTX generation failed: {err}")` and `logger.info(f"Generated PPTX: {len(pptx_bytes)} bytes")`. Both are unstructured strings going to journald → CloudWatch. There's no metric filter in `infra/modules/monitoring/main.tf` for these log lines, so no alarm on PPTX failure rate or excessive byte counts.
- Compare with `agent_error_rate` filter (monitoring/main.tf:855-870) which catches `AGENT [` patterns — equivalent monitoring for PPTX would catch the export-pptx failure surface.

### T9. No backend tests for export-pptx route or service (Phase A)
- File: `backend/tests/` (only `test_pptx_export_path_resolution.py` exists)
- Phase A finding confirmed. The only test exercises module-load path resolution — not the route, the regex strategies, the Node subprocess wrapper, or the error paths.

### T10. `/opt/pptx/node_modules` permission [NEW]
- File: `backend/Dockerfile:140`
- `COPY --from=pptx-builder --chown=10001:10001 /opt/pptx/node_modules /opt/pptx/node_modules` — owned by the flowin runtime user. Good — but means a successful exploit through C2 can also overwrite the pptxgenjs library files (e.g. drop a malicious `pptxgenjs/dist/pptxgen.cjs.js`), turning a one-shot exploit into persistent compromise that survives container restarts (until the next image push rotates it).
- Should be `chown=root:flowin chmod=0755` or `--chown=root:root` so the runtime user can read but not write.

---

## Summary of file:line index

| ID | File:line |
|---|---|
| C1 | frontend/src/components/sidebar/Sidebar.tsx:43-53,159-160,177 |
| C2 | backend/app/api/workflows.py:128-227 + backend/app/services/pptx_export.py:95-151 |
| C3 | backend/app/services/pptx_export.py:90,156-159,173-179 |
| C4 | backend/app/services/pptx_export.py:95-151 |
| H1 | frontend/src/types/index.ts:188 |
| H2 | frontend/src/components/history/WorkflowHistory.tsx:396-404 |
| H3 | backend/app/api/workflows.py:278 |
| H4 | backend/app/api/workflows.py:130 |
| H5 | backend/app/models/workflow.py:24 + backend/app/api/workflows.py:97-125 |
| H6 | backend/app/api/workflows.py:163 |
| H7 | frontend/src/components/history/WorkflowHistory.tsx:117 |
| H8 | backend/app/services/pptx_export.py:163-165 + backend/app/api/workflows.py:217-220 |
| H9 | frontend/src/components/history/WorkflowHistory.tsx:131-135,200-216 |
| H10 | frontend/src/components/history/WorkflowHistory.tsx:101-111 |
| H11 | backend/app/api/websocket.py:573,609,670,687 |
| M1 | backend/app/api/workflows.py:97-125 |
| M2 | backend/app/api/workflows.py:72 |
| M3 | backend/app/api/workflows.py:254-293 |
| M4 | backend/app/api/workflows.py:173-206 |
| M5 | backend/app/services/pptx_export.py:173-179 |
| M6 | backend/app/api/workflows.py:296-321 + backend/app/api/websocket.py:617,665,681 |
| M7 | frontend/src/components/history/WorkflowHistory.tsx:76-93 |
| M8 | frontend/src/components/results/FilesTab.tsx:144-157 |
| M9 | backend/Dockerfile:91-97,136-140 |
| M10 | backend/app/services/pptx_export.py:40-179 |
| M11 | backend/app/api/websocket.py:614-627 |
| L1-L10 | (see entries above) |
| T1 | docker-compose.yml:88-93 + infra/scripts/bootstrap-ec2.sh:181-201 |
| T2 | infra/modules/monitoring/main.tf:413-463 |
| T3 | backend/app/services/pptx_export.py:157-159 + docker-compose.yml:103-112 |
| T4 | infra/modules/ecr/main.tf:79-108 |
| T5 | infra/scripts/bootstrap-ec2.sh (negative finding) |
| T6 | infra/modules/monitoring/main.tf:688-710 |
| T7 | infra/scripts/bootstrap-ec2.sh:514-517,625-633 |
| T8 | backend/app/services/pptx_export.py:164,170 |
| T9 | backend/tests/ (negative finding) |
| T10 | backend/Dockerfile:140 |
