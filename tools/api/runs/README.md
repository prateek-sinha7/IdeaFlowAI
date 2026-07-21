# Integration tests: pipelines end-to-end via the backend API

Each `*.run.http` file in this folder is an end-to-end integration test for
one pipeline type — login, discovery, launch, clarification, agent execution,
and result inspection, driven entirely through the backend's real API surface
(no frontend, no mocks). They're built for
**[httpyac](https://httpyac.github.io/)**, not the REST Client VS Code
extension used by `tools/api/endpoints/` — because a pipeline's live progress
streams back over **SSE** (`GET /api/runs/{id}/events/stream`,
`text/event-stream`), and REST Client cannot consume that. httpyac uses the
same `.http` syntax plus an `SSE` method and inline scripting, so one file can
do REST + SSE + variable-passing together — and, unlike a one-off manual
request, each file runs the same scripted assertions (status codes,
event-type checks, artifact presence) every time, so a broken pipeline fails
loudly instead of silently.

> **Migration note:** this folder originally used a WebSocket
> (`ws://localhost:8000/ws/chat`) for both launching a run and receiving its
> events, with a `WS` method. The backend has since retired `/ws/chat`
> entirely in favor of REST + SSE (launch is `POST /api/runs`; live events are
> `GET /api/runs/{id}/events/stream`; clarify/gate/revision are their own
> REST POSTs). All files below reflect the current REST + SSE contract — see
> "Findings from live verification" for what changed and why.

This folder's output is split from its inputs: the `.run.http` test
definitions live here directly; everything they generate — run transcripts in
`logs/`, saved deliverables in `artifacts/` — is gitignored local output, not
checked in.

See [`PLAN.md`](./PLAN.md) for the full design rationale and the research
this was built from.

**Prefer clicking through Postman instead?** See
[`../postman/README.md`](../postman/README.md) — a Postman collection
covering the same login → discovery → launch → SSE stream → clarify →
inspect flow, worth it specifically because Postman renders `text/event-stream`
as a live scrolling timeline rather than one static blob.

## Prereqs

```bash
npm install -g httpyac        # or: code --install-extension anweber.vscode-httpyac
```

Backend running locally with a seeded QA user — from this folder:

```bash
./run.sh
```

`run.sh` runs one-time setup (venv, DB migrations, seeded QA users) if it
hasn't been done yet, then starts the dev server at `http://localhost:8000`
in the foreground. It's a thin wrapper around
`scripts/local-dev/setup-backend.sh` + `run-backend.sh` — use those directly
if you want more control.

`setup-backend.sh` seeds `qa-admin@flowinqa.com` / `flowin-e2e-pass` (see
`backend/scripts/seed_test_users.py`) — that's what `http-client.env.json`'s
`local` environment logs in as. Agent steps also need real LLM access
(`ANTHROPIC_API_KEY` or AWS Bedrock credentials in `backend/.env`) to
progress past the clarification gate — without it, every file still exercises
login, the SSE handshake, the launch, and the clarify round; agent execution
itself will error with a provider auth error, which is a backend credentials
issue, not a problem with these files.

## Running a file

Either directly with httpyac:

```bash
httpyac send --all -e local tools/api/runs/run.user_stories.http
```

`--all` runs every request in the file in order (default is "prompt which
one"). `-e local` selects the `local` environment from `http-client.env.json`.
In VS Code with the httpyac extension, use the "Send Request" / "Send All"
CodeLens above each `###` block instead.

Or with the `run-http.sh` wrapper, which also captures a full transcript log
and prints where the saved deliverable(s) landed:

```bash
./run-http.sh user_stories   # or: ppt, prototype, app_builder,
                              #     dotnet_to_azure, mulesoft_to_springboot, custom
```

This runs `run.<pipeline>.http --all -e local`, tees the entire transcript to
`logs/<pipeline>/<timestamp>.log`, and exports `RUN_TIMESTAMP` (used by
`run.ppt.http`'s deliverable-save step, since a single ppt run can produce
many differently-named decks). It first checks the backend is reachable
(`http://localhost:8000/health`) and that `httpyac` is installed, failing
fast with a clear message if either isn't true.

## How each file is structured

1. **Login** (`POST /api/auth/login`) — captures `{{jwt}}` via a post-response
   script (`exports.jwt = response.parsedBody.token`) for every later request.
2. **Discovery** (REST GETs) — lists the pipeline's agents / valid inputs
   (e.g. `run.prototype.http` lists real `template_id`/`design_system_id`
   values) so you can see what the launch payload below is choosing from.
3. **Launch** — `POST /api/runs` with the pipeline's payload
   (`pipeline_type`, `message`, and any pipeline-specific fields like
   `template_id`). The response body is `{"run_id": "..."}` — captured
   directly into `{{pipelineRunId}}`, no event-sniffing needed.
4. **Stream events over SSE** — `GET /api/runs/{{pipelineRunId}}/events/stream`
   with a normal `Authorization: Bearer {{jwt}}` header. Every pipeline here
   has `clarify.mode: auto` (confirmed by reading each
   `agents/workflows/<id>/workflow.yaml`), so the run **always pauses at a
   `questionnaire_ready` clarification gate** before any agent runs —
   verified live against this backend. A `{{@streaming}}` script listens on
   the SSE stream, logs every event type, and on `questionnaire_ready` fires
   a separate `POST /api/runs/{{pipelineRunId}}/answers` (via the script
   sandbox's global `fetch`, since SSE is receive-only) with
   `skip_clarification: true`. It resolves on a terminal event
   (`pipeline_complete`/`pipeline_failed`/`pipeline_cancelled`/
   `budget_aborted`/`error`) or a safety timeout.
5. **Inspect the result** (REST GETs) — `/api/runs/{{pipelineRunId}}`,
   `/events` (durable history poll — distinct from the live
   `/events/stream` SSE endpoint), `/artifacts?include=content`.
6. **Optional revision** — a commented-out block showing
   `POST /api/runs/{{pipelineRunId}}/revisions` chained off the run this file
   just produced.

## Auth note: SSE uses a normal `Authorization` header

Unlike the retired WS transport (which needed a `?token=` query-param
workaround because of an `Sec-WebSocket-Protocol` limitation in httpyac's
underlying `ws` client — see git history if curious), the SSE endpoint is
just another authenticated REST call: a normal
`Authorization: Bearer {{jwt}}` header, no query-param fallback needed. The
frontend itself can't use the browser's native `EventSource` for the same
reason (it can't set custom headers) — it uses `fetch` + a `ReadableStream`
reader instead (`frontend/src/hooks/useRunStream.ts`).

## Streaming script pattern

Every SSE block in these files uses the same shape:

```js
{{@streaming
  await new Promise((resolve) => {
    let done = false;
    let answered = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    $requestClient.on('message', async (msg) => {
      let data; try { data = JSON.parse(msg.data); } catch { data = null; }
      if (!data) return;
      console.log('SSE <-', data.type);
      if (data.type === 'questionnaire_ready' && !answered) {
        answered = true;
        await fetch(`${apiRoot}/api/runs/${pipelineRunId}/answers`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwt}` },
          body: JSON.stringify({ responses: [], skip_clarification: true }),
        });
      }
      if (["pipeline_complete", "pipeline_failed", "pipeline_cancelled", "budget_aborted", "error"].includes(data.type)) {
        finish();
      }
    });
    $requestClient.on('error', finish);
    $requestClient.on('close', finish);
    setTimeout(finish, 30 * 60 * 1000);
  });
}}
```

`$requestClient` is httpyac's live client for the current SSE request;
`.on('message', ...)` fires per SSE frame, with the frame's raw `data:` line
on `msg.data` (a JSON string: `{"type": ..., "data": {...}}`). Because SSE is
one-way (server → client only, unlike `WS`'s bidirectional
`$requestClient.nativeClient.send()`), the clarify-answer call is a plain
`fetch()` POST fired from inside the message handler — `apiRoot`/`jwt` are
available as bare variables in the script sandbox (the same environment
bindings interpolated by `{{apiRoot}}`/`{{jwt}}` elsewhere in the file).
`exports.xxx` makes a variable available to every later request in the file.

## Files

| File | pipeline_type | What it shows |
|---|---|---|
| `run.user_stories.http` | `user_stories` | Baseline run: 6-agent backlog pipeline |
| `run.ppt.http` | `ppt` (alias of `od_ppt`) | Deck generation (self-contained HTML deck — see caveat below) |
| `run.prototype.http` | `prototype` (`od_prototype` alias resolves here) | Template/design-system discovery, `template_id`/`design_system_id`/`discovery` fields |
| `run.app_builder.http` | `app_builder` | 15-agent full-stack app pipeline |
| `run.mulesoft_to_springboot.http` | `mulesoft_to_springboot` | 13-agent migration pipeline |
| `run.dotnet_to_azure.http` | `dotnet_to_azure` | 13-agent modernization pipeline |
| `run.custom.http` | `custom` | Open-agent run: explicit `agent_ids` from the 8-agent custom-utility pool, plus a second example overriding `agent_ids` on a *base* pipeline with a cross-pipeline agent |

**Not included:** `spec_kit` has agent prompts but no
`agents/workflows/spec_kit/workflow.yaml` manifest — `compile_for_run()`
raises `FileNotFoundError` before a run can start (confirmed by reading
`backend/CLAUDE.md` and `backend/app/api/workflows.py`), so it isn't
launchable yet. `chat` is the internal free-chat pipeline type (never a valid
`run_pipeline.pipeline_type`). `reverse_engineer` has a manifest but zero
agents registered.

## Findings from live verification

Every file in this folder was actually run against a local backend
(`scripts/local-dev/setup-backend.sh` + `run-backend.sh`, seeded QA user) with
httpyac, not just written by inspection. That surfaced real issues that
inspection alone wouldn't have caught:

- **`/ws/chat` was retired in favor of REST + SSE.** Launching a run is now
  `POST /api/runs` (returns `{run_id}` directly — no more sniffing the first
  WS event for `pipeline_run_id`); live progress streams over
  `GET /api/runs/{id}/events/stream` (SSE, `sse_starlette`), authenticated
  with a normal `Authorization: Bearer` header — no more `?token=` query-param
  workaround, since that was only needed to route around an `ws` client
  limitation with `Sec-WebSocket-Protocol` headers. Clarify/gate/revision are
  each their own REST POST (`/answers`, `/gate`, `/revisions`). This also
  **eliminates the WS single-connection race** described further down: since
  launch, the event stream, and the command POSTs are now decoupled
  transports, there's no more "must keep one connection open across
  `run_pipeline -> clarify -> agents`" constraint — a clarify answer is just
  an independent POST fired from inside the SSE message handler, and it can't
  race a connection close because there's no shared connection to close.
- **`ppt`/`prototype` must use the `od_ppt`/`od_prototype` pipeline_type in
  the launch payload, not the bare alias.** The backend only loads template
  context (`od_context`) when `pipeline_type` resolves through the dedicated
  od_* label (`backend/app/api/launch_context.py::resolve_launch_od_context`,
  the REST-era home of this logic — previously
  `backend/app/api/websocket.py`'s `_handle_workflow_execution`). Sending
  `pipeline_type: "ppt"` or `"prototype"` with a valid `template_id` still
  fails with `missing_template_context` — `template_id` is silently ignored
  for the bare alias. The frontend always sends the `od_*` alias for exactly
  this reason; `run.ppt.http` / `run.prototype.http` do the same. REST
  discovery endpoints (`GET /api/agents/pipelines/...`) still use the bare
  name (`ppt`, `prototype`) — only the launch payload's `pipeline_type` needs
  the alias.
- **`tools/api/endpoints/prototype.http`'s example `design_system_id: "linear"` is
  stale** — the real id in this backend's 150-design-system catalog is
  `linear-app`. `run.prototype.http` uses the correct id.
- **The `{{@streaming}}` script must also resolve on the SSE `close`/`error`
  event, not just on a matching message type.** If the connection drops
  before a terminal event arrives, a script that only listens for `message`
  hangs for its full timeout. Every block here also does
  `$requestClient.on('close', finish)` / `.on('error', finish)`.
- **(Historical — WS-only, no longer applicable)** The original design sent
  `run_pipeline` and `submit_questionnaire` as two separate WS requests: one
  that ran `run_pipeline` and closed as soon as `questionnaire_ready`
  arrived, and a second, fresh connection that sent `submit_questionnaire`.
  Verified live with real Bedrock credentials: this raced against the
  backend's disconnect handling — a pipeline paused at the clarify gate could
  get marked `"cancelled"` if the first connection closed before the second
  connection's `submit_questionnaire` reached it. The fix at the time was
  keeping one WS connection open for the whole `run_pipeline -> clarify ->
  agents` flow. This entire class of bug is now moot under REST + SSE (see
  the first bullet above) — kept here only as a record of what the old WS
  files worked around, for anyone reading git history. A Human_Gate review
  pause (`review_gate_ready`, distinct from the clarify questionnaire) is
  still NOT auto-approved by these scripts — that's a genuine human-wait, so
  `run.prototype.http` / `run.ppt.http` log a warning and leave a commented
  `POST .../gate` block for you to send manually if the run pauses on one.

- **`ppt`/`od_ppt` does NOT produce a real `.pptx`, and `POST /api/runs/export-pptx`
  does not apply to it.** The `od-ppt-brief-analyst -> od-ppt-composer ->
  od-ppt-validator` agent sequence (the "magazine-web-ppt" / guizang-ppt
  skill and its siblings) produces a **self-contained HTML deck** — inline
  CSS, keyboard/wheel/swipe navigation JS, no PowerPoint content at all.
  `export-pptx` specifically looks for a `ppt-code-generator` agent's
  PptxGenJS source (`backend/app/api/runs.py`'s `_PPT_CODE_AGENT_IDS`), which
  isn't part of this pipeline's agent set — calling it always returns
  `"Could not find PptxGenJS code"` for an `od_ppt` run, even a fully
  successful one. The real deliverable is the HTML artifact (`kind:
  "deliverable"` in the artifact tree) — open it in a browser.

## Saving the generated deliverable to disk

Every `*.run.http` file's "artifact tree" step (`GET
/api/runs/{id}/artifacts?include=content`) has a post-response script that
finds the artifact with `kind: "deliverable"` and writes its raw content to
`tools/api/runs/artifacts/{pipeline_type}/{pipeline_run_id}.{ext}`
(`.html` if the content looks like HTML, `.txt` otherwise — `run.custom.http`
uses `artifacts/custom/` and `artifacts/user_stories/` for its two examples;
`run.ppt.http` uses `artifacts/ppt/{timestamp}.{ext}` since a run can produce
many decks). That folder is gitignored — it's local generated output, not
something to commit. The script uses `require('fs')`/`require('path')`
directly inside the httpyac script sandbox (confirmed working) and resolves
the path relative to `httpFile.fileName`, so it works regardless of your cwd
when invoking `httpyac send`.

If a run hasn't reached `pipeline_complete` yet, there's no `deliverable`
artifact and the script just logs that instead of writing a file — rerun
that GET request once the pipeline finishes.

Every pipeline_type here has `clarify.mode: auto`, so a launch always pauses
at `questionnaire_ready` before any agent runs — verified for all seven
files. Agent execution itself could not be verified through to a real
completed deliverable in this environment: the local AWS Bedrock bearer token
had expired, so every agent call failed with `AccessDeniedException` inside
LangChain/Bedrock. That is a local credentials issue, not a defect in these
files — the full request/response contract up through `agent_start` and the
per-agent `agent_error` lifecycle was confirmed via the backend's own logs.
