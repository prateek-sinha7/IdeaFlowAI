# Postman collection: pipeline runs over REST + SSE

A Postman equivalent of the `tools/api/runs/*.run.http` httpyac files, for when
you want to watch a run's live event stream in Postman's native
stream/timeline viewer instead of a terminal or VS Code — Postman renders
`text/event-stream` responses as a scrolling live timeline rather than a
single blob, which reads a lot better for this than httpyac's response pane.

## Import

1. Postman → **Import** → drag in both files:
   - `VELOCITY-AI-Pipeline-Runs.postman_collection.json`
   - `VELOCITY-AI-Local.postman_environment.json`
2. Select the **VELOCITY-AI Local** environment (top-right environment picker)
   before running anything — it carries `apiRoot` and the seeded QA login
   (`qa-admin@flowinqa.com` / `flowin-e2e-pass`) built in.
3. Requires a backend running locally at `http://localhost:8000` (see
   `tools/api/runs/run.sh`).
4. Requires a Postman version with SSE/streaming support (desktop app, v11+)
   to see the live timeline view. Everything still *works* on older versions
   or via Newman — you just get the final response body instead of a live
   scroll.

## Structure

One folder per API resource — `Auth`, `Agents`, `Capabilities`, `PPT`,
`Prototype`, `User Workflows` are plain reference/discovery lookups, each
independent of any specific run. **`Runs`** is where the actual pipelines
live:

- **Reference** — generic/admin calls on the runs resource not tied to any
  one launch flow: list runs, get by ID, chain-context, family, hook-runs,
  export-pptx (reference only), delete.
- One **fully self-contained** use-case sub-folder per launchable pipeline —
  each mirrors `tools/api/runs/run.<pipeline>.http` step for step, with its
  own Login, Discovery, Launch, and inspection steps, so it can be run
  top-to-bottom entirely on its own:
  - **User Stories** (11 requests)
  - **PPT (od_ppt)** (12 requests)
  - **Prototype (od_prototype)** (14 requests)
  - **App Builder** (10 requests)
  - **Dotnet to Azure** (10 requests)
  - **Mulesoft to Springboot** (10 requests)
  - **Custom** (15 requests — two launch examples)

Every use-case sub-folder follows this shape:

1. **Login** — captures `{{jwt}}` as a **collection variable**.
2. **Discovery** — agents in this pipeline, plus (for **PPT** and
   **Prototype**) the template/design-system list, so you actually pick a
   real `template_id` — the "theme" — before Launch, same as the `.run.http`
   files always did.
3. **Launch** — `POST /api/runs`. The prompt is the `message` field in this
   request's body — edit it before sending to try a different brief. Captures
   `{{runId_<pipeline>}}` on success.
4. **Watch Events (SSE) — part 1, until clarify** ★ — attaches right after
   launch. Every pipeline here has `clarify.mode: auto`, so it always pauses
   at `questionnaire_ready` first.
5. **Submit Clarify Answers** — send once the pause above has actually
   armed.
6. **Watch Events (SSE) — part 2, until completion** ★ — a fresh GET replays
   everything durable from the start, then continues live through agent
   execution to a terminal event.
7. **Resolve Gate** (PPT and Prototype only) — only needed if part 2 pauses
   on `review_gate_ready` instead of reaching a terminal event.
8. **Get Run** / **Get Durable Events** / **Get Artifacts** — inspect the
   result — verified live to contain the real generated deliverable once the
   pipeline completes (see below).
9. **(Optional) Create Revision**.

**Custom** demonstrates two launch examples side by side (Example A: the
8-agent custom pool; Example B: a *base* pipeline with a cross-pipeline agent
spliced in), each with its own `{{runId_customA}}`/`{{runId_customB}}`.

## Why two `Watch Events (SSE)` requests, not one

Verified live against the backend: **submitting the clarify answer before the
`questionnaire_ready` pause has actually armed is silently dropped** — the
run just sits at `gate_status` / `waiting_for_user` forever, and the answer
you already sent has no effect. So the flow can't be "answer blind
immediately after Launch" — you genuinely have to wait for the pause to
arrive first.

Since a single open SSE connection blocks until a terminal event (there's no
server-side timeout), and Postman/Newman can't run a script *while* a
request is still streaming, one continuous watch would deadlock: it would
never see a terminal event because the pipeline needs an answer that would
come from the *next* request in the sequence — which never gets sent until
the current (blocking) request finishes.

Splitting it into two legs fixes this cleanly:
- **Part 1** attaches, gives the pause time to arm, then is left to be
  stopped manually (Postman UI) or time out (Newman, via
  `--timeout-request`) — that's expected, not a bug.
- **Submit Clarify Answers** unblocks the run.
- **Part 2** reattaches on a fresh connection. Durable replay catches it up
  on everything that already happened (including the clarify round), then it
  continues live through to a real terminal event.

## Verified with Newman

```bash
newman run VELOCITY-AI-Pipeline-Runs.postman_collection.json \
  -e VELOCITY-AI-Local.postman_environment.json \
  --folder "User Stories" \
  --timeout-request 12000
```

Ran the full `Runs > User Stories` folder end to end: Login → Discovery →
Launch → Watch part 1 (timed out after 12s exactly as designed, while paused
at the clarify gate) → Submit Answers → Watch part 2 (ran ~3 minutes, `200
OK`, 1.45MB — a full real run, not the credential-failure case seen earlier
in this project) → Get Run (`status: completed`) → Get Artifacts, which
returned a real **32KB `deliverable` artifact** — the actual generated
backlog. Newman reported 10/11 requests passing; the one "failure" is the
intentional Watch-part-1 timeout described above.

### A real bug this caught: environment variable shadowing

Postman resolves variables in this order: **Local > Data > Environment >
Collection > Global**. The first version of this collection also defined
`jwt` and every `runId_*` variable in the environment file (blank, meant as
placeholders) — since environment beats collection, that blank value always
shadowed whatever `Login`'s test script had just set via
`pm.collectionVariables.set('jwt', ...)`, so every request after Login 403'd
with `"Not authenticated"`. Fixed by removing `jwt`/`runId_*`/
`userWorkflowId` from the environment entirely — they exist **only** as
collection variables now, with no environment entry to shadow them. The
environment file carries just `apiRoot`/`loginEmail`/`loginPassword`.

## Why this exists alongside the `.run.http` files

Keep both:
- **`tools/api/runs/*.run.http`** (httpyac) — for scripted, unattended,
  repeatable runs (`./run-http.sh <pipeline>`), with automatic clarify-answer
  handling and deliverable/log saving to disk. Best for CI-style verification.
- **This Postman collection** — for manually poking at a run and actually
  *watching* the event stream scroll by in a nicer UI, or for handing to
  someone who'd rather click through Postman than run a CLI.
