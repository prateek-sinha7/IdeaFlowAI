# E2E Fixture Contract — how to write a Flowin Playwright spec

This is the API contract every spec under `frontend/e2e/tests/` uses. The harness is **proven** (see the 4 reference specs: `ts-a.auth`, `ts-i.agent-panels`, `ts-q.terminal-states`, `ts-k.wave-tree` — all green). **Mimic them.** Mocked mode needs **no backend** — REST + WS are mocked in the browser.

## Import & fixtures

```ts
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent, playGreenRun, playFailedRun, SAMPLE_HTML, SAMPLE_DECK, SAMPLE_BACKLOG } from "../fixtures/scenarios";
```

`test` provides these fixtures (the mocks are **auto-installed for every test**, even if you only destructure `page`):

| Fixture | Type | Use |
|---|---|---|
| `page` | Playwright Page | raw page |
| `dashboard` | `DashboardPage` | navigation + locators (preferred) |
| `mockWs` | `MockWs` | drive inbound WS events, assert outbound frames |
| `mockApi` | `MockApi` | mutate the REST backend (user/runs/capabilities) |
| `tier` | option | `test.use({ tier: "basic" })` to change entitlement |

## DashboardPage (`dashboard`)

```ts
await dashboard.goto({ tier? });                 // sets token + opens /dashboard at home (waits for heading + WS ready)
await dashboard.selectWorkflow("Generate product requirements");  // click a CreationHub row by H2 label
await dashboard.fillIdea("…"); await dashboard.runButton().click();
await dashboard.runWith({ workflow?, idea, waitForFrame? });  // select + fill + Run + await run_pipeline frame → leaves you on execution view
await dashboard.openAdvanced();                  // opens AgentsPopup (asserts "Workflow configuration")
await dashboard.openModelPicker();               // opens composer → asserts "Per-Agent Model"
```

Locators (all return `Locator`): `homeHeading()`, `runButton()`, `ideaTextarea()`, `runningBadge()`, `doneBadge()`, `errorBadge()`, `stopButton()`, `newPipelineButton()`, `agentCardByName(name)`, `waveHeading()`, `waveEmpty()`, `waveGroup(i)`, `previewEmpty()`, `degradedHeading()`, `cancelledHeading()`, `failedAgentsLabel()`, `genericIframe()`, `deckIframe()`, `prototypeIframe()`, `previewTab()/filesTab()/thinkingTab()`, `questionnaireTitle()`, `reviewGateTitle("Specification Review"|"Task Plan Review")`, `approveButton()`, `rejectButton()`. `dashboard.page` and `dashboard.ws` are exposed.

## MockWs (`mockWs`) — drive inbound events / assert outbound

**Lifecycle:** after `dashboard.runWith(...)` the app has sent `run_pipeline`. Then YOU drive the run:

```ts
mockWs.start(AGENTS.user_stories, { pipelineType: "user_stories" });  // pipeline_start → seeds cards (resets seq)
mockWs.agentStart("domain-analyst");        // → RUNNING badge
mockWs.agentThinking("domain-analyst", "…");// → Reasoning(live) stream + ▌ cursor
mockWs.agentChunk("domain-analyst", "…");   // appends to output (NOT shown live)
mockWs.agentComplete("domain-analyst", { totalTokens: 3100 });  // → DONE badge + token pill
mockWs.agentError("domain-analyst", "The model rejected this request.");  // → ERROR badge
mockWs.plannerStart(); mockWs.plannerComplete("intent", "PROCEED"|"CLARIFY_REQUIRED");
mockWs.questionnaireReady([{ id:"q1", text:"Audience?", options:["Execs","Devs"], answerType:"single" }]);
mockWs.questionnaireComplete();
mockWs.reviewGateReady({ gateKey:"g1", agentId:"prototype-specify", agentName:"Spec Writer", output:"## Spec\n…" });
mockWs.reviewGateApproved();
mockWs.waveStarted(0, "fanout", ["t1","t2"]); mockWs.waveCompleted(0,"fanout"); mockWs.waveFailed(0,"fanout");
mockWs.subagentSpawned(0,"fanout","worker-a",0); mockWs.subagentResult(0,"fanout","worker-a",0);
mockWs.complete({ pipelineType:"od_ppt", finalOutput: SAMPLE_DECK, deliverableMimetype?, deliverableFilename?, status?:"degraded", agentsFailed? });
mockWs.failed({ agentsFailed:["a1"], error:"Operation not allowed" });  // → pipeline_failed
mockWs.cancelled({ duration: 8 });          // → pipeline_cancelled
mockWs.reconnected({ live:false, status:"completed"|"failed"|"running"|null });
mockWs.emitStream("chunk", "user_stories"); // legacy `stream` frame
mockWs.drop();          // simulate WS drop → app reconnects
mockWs.expireJwt();     // close code 4001 → app clears token + redirects /login
```

**Assert outbound frames the app sent:**
```ts
const f = await mockWs.waitForClientFrame("run_pipeline");   // resolves with the parsed frame
expect(f.pipeline_type).toBe("user_stories");
expect(f.model_overrides).toEqual({ "agent-id": "model-id" });
await mockWs.waitForClientFrame("cancel_pipeline");
mockWs.framesOfType("run_pipeline");        // all of a type
mockWs.connectionCount;                      // socket opens (reconnect counting)
```
Frame fields are TOP-LEVEL on the parsed outbound object (e.g. `f.pipeline_type`, `f.agent_ids`, `f.model_overrides`, `f.attached_skills`).

## MockApi (`mockApi`) — REST backend

```ts
mockApi.setUser({ tier: "pro", is_admin: false });
mockApi.setRuns([ makeRun({ id:"r1", title:"Refunds backlog", type:"user_stories", status:"completed", output:"# Product Backlog\n…" }) ]);
mockApi.setRunDetail((id) => makeRun({ id, status:"failed", error:"... agent(s) failed: a1, a2", type:"user_stories" }));
mockApi.requests;   // recorded [{method,url,body}] for assertions
```
`import { makeRun } from "../fixtures/mockApi";` for run fixtures. Model catalog/capabilities come from `fixtures/constants.ts` (`MODEL_CATALOG` has 5 models, 4 `user_allowed:true`).

## CRITICAL gotchas (these caused real failures — avoid them)

1. **Run is disabled until there are agents.** `user_stories`/`app_builder`/`od_ppt`/`prototype` seed default agents (Run enables once an idea is typed). **`custom` seeds NONE** → Run shows `Add agents first`. To run `custom`, open the composer and add an agent first, OR (if you only need the execution surface) use `user_stories` and just send the events you care about — the execution surface/wave panel mounts for any pipeline type.
2. **Agent cards come from `pipeline_start`, not the pre-run seed.** Assert card names AFTER `mockWs.start([...])`. The names you assert must match the agent `name` you passed to `start()`.
3. **`prototype`/`ppt` from home do NOT open IdeaInputPage** — they `router.push` to `/workflow/{prototype,ppt}/templates`. For the IdeaInputPage flow use `user_stories`/`app_builder`/`custom`/`migration`.
4. **Almost no `data-testid`.** Use exact text / role / `iframe[title=...]` / `button[title=...]`. When unsure of an exact string, **open the component file** (`frontend/src/components/...`) and read it.
5. **Durations are wall-clock** — assert regex (`/\d+(\.\d)?s/`), never exact values.
6. **`stream` content** is top-level; everything else is `data`-wrapped (the helpers handle this — just call them).
7. **Don't assert `agent_chunk` text live** — chunks aren't rendered until the agent is `done`/expanded. The live stream is `agentThinking` (the `▌` cursor).
8. Live cancel sets NO failed/degraded flag → the degraded affordance does NOT appear after a live Stop (only history-reopen of a `cancelled` run shows cancelled copy).

## Self-verify (REQUIRED before you finish)

A dev server is already running on `http://localhost:3000` (reused automatically). Run YOUR file only:
```bash
cd frontend && npx playwright test --project=mocked --workers=1 --reporter=line e2e/tests/<your-file>.spec.ts
```
Iterate until green. If a case is genuinely un-mockable, mark it `test.fixme(true, "reason")` with a one-line reason rather than leaving it failing — but prefer making it pass. Do NOT touch other agents' files or the `fixtures/` dir (if a fixture is missing something, note it in your final report instead of editing it).
