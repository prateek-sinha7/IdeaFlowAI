# Plan: `.run.http` files for driving pipelines end-to-end via the backend API

> Historical design doc — written when this folder lived at `docs/api/runs/`
> and the REST Client files lived at `docs/api/*.http`. Both have since moved
> to `tools/api/runs/` and `tools/api/endpoints/` respectively (paths below
> are as originally written); see [`README.md`](./README.md) for the current
> layout and purpose.

Goal: one executable `.http` file per launchable `pipeline_type`, plus one for an
open/custom agent run, each containing every call needed to go from "logged out"
to "pipeline finished" in chronological order, with variables captured along the
way (JWT, `pipeline_run_id`, artifact ids, etc.).

## Key finding that shapes this plan

There is **no REST endpoint that starts a pipeline run**. A run is started by
sending a `run_pipeline` JSON message over `ws://localhost:8000/ws/chat`
(`backend/app/api/websocket.py:828-921`), and all progress/results stream back
as WS events (`agent_chunk`, `tool_call`, `review_gate_*`, `pipeline_complete`,
...). REST only covers discovery (agents/workflows/capabilities) and
after-the-fact history (`/api/runs/...`).

This repo's existing `docs/api/*.http` files target the **REST Client** VS Code
extension, which cannot execute WebSocket requests — `docs/api/websocket.http`
today is just a comment block, not something you can run.

**Decision (confirmed with you):** switch the new `runs/` files to
**httpyac**, which uses REST-Client-compatible `.http` syntax but adds a `WS`
method plus pre/post-request scripting, so login → discovery → `run_pipeline`
→ (gate/questionnaire responses) → wait-for-completion → REST follow-up can
all live in one real, runnable file. httpyac ships as an npm package
(`npm i -g httpyac`) and a VS Code extension (`anweber.vscode-httpyac`); the
existing REST Client files are untouched.

## Folder layout

```
docs/api/runs/
  PLAN.md                       # this file
  README.md                     # how to install/run httpyac, shared vars, auth flow
  _shared.env.json               # httpyac env: apiRoot, wsRoot, credentials
  _shared.http                   # reusable login + "wait for pipeline_complete" requests (httpyac @import)
  run.user_stories.http
  run.ppt.http                   # od_ppt (alias "ppt")
  run.prototype.http             # od_prototype, incl. template/design-system discovery
  run.app_builder.http
  run.mulesoft_to_springboot.http
  run.dotnet_to_azure.http
  spec_kit.run.http
  run.custom.http                # open-agent / arbitrary agent_ids run
```

Revision pipelines (`*_revision`) are **not** separate files — each base
pipeline's `.run.http` ends with an optional, clearly-marked "Revision"
section showing the `run_revision` WS message chained off the run it just
produced, since a revision always needs a prior `parent_run_id`.

Excluded as not launchable / not applicable: `chat` (internal free-chat
pipeline type, never a valid `run_pipeline.pipeline_type`), `reverse_engineer`
(declared type, zero agents, not runnable), `od_prototype_revision` (empty
agent set).

## Per-file chronological structure

Every `*.run.http` follows the same skeleton:

1. **Login** — `POST /api/auth/login` → capture `{{jwt}}` via httpyac
   post-response script into a shared/global variable (so later requests and
   the WS request reuse it without re-pasting).
2. **Discovery** (pipeline-specific, GET-only, informational — lets you see
   valid `agent_ids`/`template_id`/etc. before building the run payload):
   - `GET /api/agents/pipelines/{pipeline_type}` — the agents that make up
     this pipeline.
   - `GET /api/capabilities` — valid `model_overrides` values.
   - `run.prototype.http` only: `GET /api/prototype/templates`,
     `GET /api/prototype/design-systems` to pick real `template_id` /
     `design_system_id` values (default to `saas-landing` / `linear`,
     matching `tools/api/endpoints/prototype.http`).
3. **Run the pipeline over WS** — `WS ws://localhost:8000/ws/chat` with
   `Sec-WebSocket-Protocol: bearer.{{jwt}}, flowin.v1`, first frame is the
   `run_pipeline` JSON message with a realistic example payload for that
   pipeline type (see table below). httpyac scripting captures
   `pipeline_run_id` from the first `pipeline_start` event into a variable,
   and the request is written to log/park on `pipeline_complete` /
   `pipeline_failed` / `error`.
   - Where a pipeline commonly stops at a human-in-the-loop gate
     (`review_gate_*` / `questionnaire_ready`), the file includes a clearly
     commented-out follow-up `WS` block showing `submit_questionnaire` /
     `approve_review` payloads — commented because whether a gate fires
     depends on `gate_agent_ids` and run content, so it's not safe to assume
     it always happens.
4. **Inspect the result via REST**, using the captured `pipeline_run_id`:
   - `GET /api/runs/{{pipeline_run_id}}`
   - `GET /api/runs/{{pipeline_run_id}}/events`
   - `GET /api/runs/{{pipeline_run_id}}/artifacts?include=content`
   - `run.ppt.http` only: `POST /api/runs/export-pptx`
5. **Optional revision section** (commented header, real requests below it) —
   `WS run_revision` with `parent_run_id: {{pipeline_run_id}}`.

## Example `run_pipeline` payload per file

| File | pipeline_type | Notable fields |
|---|---|---|
| `run.user_stories.http` | `user_stories` | `message` only (agent_ids optional, full 6-agent set) |
| `run.ppt.http` | `ppt` (alias of `od_ppt`) | `message` describing the deck brief |
| `run.prototype.http` | `prototype` (`od_prototype` alias resolves here) | `message`, `template_id`, `design_system_id`, `discovery: {...}` |
| `run.app_builder.http` | `app_builder` | `message`; note 15-agent roster from discovery call |
| `run.mulesoft_to_springboot.http` | `mulesoft_to_springboot` | `message` describing the Mule app to migrate |
| `run.dotnet_to_azure.http` | `dotnet_to_azure` | `message` describing the .NET app to modernize |
| `spec_kit.run.http` | `spec_kit` | `message`; flagged as agents-only (no `workflow.yaml` manifest, won't show in `GET /api/workflows`, but is in `SUPPORTED_PIPELINE_TYPES` and runnable) |
| `run.custom.http` | `custom` | `agent_ids` drawn from the 8-agent custom pool (`market-research-agent`, `swot-analyst`, ...), demonstrating the open-agent/arbitrary-composition path; a second example shows overriding `agent_ids` on a *base* pipeline (e.g. `user_stories` + an agent borrowed from another pipeline) since `allowed_custom_agent_ids()` permits cross-pipeline composition |

All payloads match the shape built by
`frontend/src/hooks/useWorkflow.ts:39-110` and validated by
`backend/app/api/websocket.py:121-181` / `backend/agents/registry.py:219-298`.

## `README.md` contents

- Prereqs: backend running (`scripts/local-dev/run-backend.sh`), a seeded
  user, `npm i -g httpyac` (or the `anweber.vscode-httpyac` VS Code
  extension).
- How env vars work (`_shared.env.json`, `local`/`dev` environments mirroring
  `.vscode/settings.json`'s `rest-client.environmentVariables`).
- How the login → JWT-capture → WS auth chain works, and the
  `Sec-WebSocket-Protocol: bearer.<jwt>, flowin.v1` requirement.
- One line per file on what it demonstrates.

## Verification step

After writing the files, actually install httpyac and run each `.run.http`
against a live local backend (login must succeed, WS must connect and reach
`pipeline_start`, at minimum) to confirm the syntax is valid httpyac and the
payloads are accepted — not just written by inspection. Full pipeline
completion may take a while for larger pipelines (app_builder,
mulesoft_to_springboot, dotnet_to_azure); those runs will be started and
their `pipeline_start`/early events confirmed rather than run to completion,
to keep verification fast.

## Status: done, verified live

All files were built and then actually executed against a local backend
(httpyac CLI, seeded QA user). Verification surfaced and fixed three real
bugs — see the "Findings from live verification" section in `README.md`:
the `od_ppt`/`od_prototype` pipeline_type requirement, a stale
`design_system_id` in the existing `tools/api/endpoints/prototype.http`, and a
streaming-script hang when the WS connection drops before a terminal event.
`spec_kit` was dropped as a separate file per the manifest-check above
(confirmed, not just suspected) and is documented instead in `README.md`.

## Update: `/ws/chat` retired — migrated to REST + SSE

The backend has since removed `/ws/chat` entirely (`backend/app/api/websocket.py`
no longer exists). Pipeline execution is now:

- **Launch**: `POST /api/runs` (was: WS `run_pipeline`) — returns `{run_id}`
  directly, so there's no more sniffing the first event for `pipeline_run_id`.
- **Live events**: `GET /api/runs/{id}/events/stream` — Server-Sent Events
  (`sse_starlette`), authenticated with a normal `Authorization: Bearer <jwt>`
  header (no more `?token=` query-param workaround — that was a WS-only
  limitation). httpyac's `SSE` method drives this; events arrive via
  `$requestClient.on('message', ...)` with the JSON body on `msg.data`.
- **Clarify answers**: `POST /api/runs/{id}/answers` (was: WS
  `submit_questionnaire`).
- **Review gate**: `POST /api/runs/{id}/gate` (was: WS `approve_review`).
- **Revision**: `POST /api/runs/{id}/revisions` (was: WS `run_revision`) —
  `parent_run_id` is now the URL path segment, not a body field.

Because launch/answers/gate are now independent REST calls instead of frames
on the one WS connection that also carried events, **the old "must share one
connection to avoid a cancellation race" constraint no longer applies** — the
SSE stream and the command POSTs are decoupled transports by construction.
Every `*.run.http` file's `{{@streaming}}` script now fires the
`/answers` POST directly from inside the SSE message handler (using the
sandbox's global `fetch`, since SSE is receive-only, unlike `WS`'s
bidirectional `$requestClient.nativeClient.send()`), rather than needing to
reuse the launch request's own connection.
