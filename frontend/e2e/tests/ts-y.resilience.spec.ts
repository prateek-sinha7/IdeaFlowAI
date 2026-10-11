/**
 * TS-Y — Resilience & long-run (TEST-REGISTER suite TS-Y).
 *
 * Exercises the WS transport's failure modes end-to-end in the browser, the
 * sibling of TS-S (which owns the durable-replay handshake). TS-Y is the raw
 * transport contract: a mid-run socket DROP must trigger the app's
 * exponential-backoff reconnect (and surface the reconnect banner), and a
 * JWT-expiry close (4001) must clear the token and bounce to /login.
 *
 * Mechanics that make these pass in mocked mode (NO backend):
 *   - the SSE stream reattaches after `mockSse.drop()` closes it —
 *     the socket (code 1006), useWebSocket.onclose schedules connect() with
 *     backoff `min(1000*2^n, 30000)` — first retry ~1s. That re-open re-fires
 *     MockSse._attach, so `mockSse.connectionCount` increments (1 → ≥ 2).
 *   - During that ~1s backoff window useWebSocket sets connectionStatus
 *     "reconnecting", which renders the DashboardLayout banner `Reconnecting...`
 *     (the only "reconnecting"-branch markup; the red `Connection lost.` +
 *     `Reconnect` button is the "failed" branch, which this transport never
 *     enters — onclose goes straight to "reconnecting").
 *   - On 4001 useWebSocket.onclose calls clearToken() (removes the `auth_token`
 *     localStorage key) and sets window.location.href = "/login" — NO backoff
 *     reconnect on JWT expiry. page.waitForURL catches the redirect; we assert
 *     the login screen renders (the mocked dashboard.goto's addInitScript
 *     re-seeds the token on the /login load, so a literal null check would
 *     observe the fixture, not the app — see the in-test note).
 *
 * No hard sleeps: the reconnect is observed via `expect.poll` on
 * connectionCount with a timeout (the first backoff retry is 1s, so a 5s budget
 * is comfortable).
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-Y — resilience / long-run", () => {
  test("TS-Y-01 WS drop → reconnect banner + socket auto-reopens (backoff)", async ({ dashboard, mockSse, page }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Generate epics for a refunds workflow" });

    // Keep the run mid-flight so the reconnect path has a live run to resume.
    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();

    // SSE (44-06) is a fetch-stream that re-attaches from its cursor after every
    // server-close, so the mock's attach counter is monotonic (NOT a single
    // persistent socket) — capture the current count as the drop baseline.
    const connectionsBefore = mockSse.connectionCount;

    // Drop the stream (server-close). useRunStream treats the close as a transport
    // drop → connectionStatus "reconnecting" + a 1s backoff, then re-attaches.
    const droppedAt = Date.now();
    mockSse.drop();

    // The reconnect banner appears during the backoff window. EXACT copy is
    // `Reconnecting...` (DashboardLayout connectionStatus === "reconnecting").
    await expect(page.getByText("Reconnecting...", { exact: true })).toBeVisible();

    // The stream re-attaches on the backoff retry → the attach counter advances
    // past the drop baseline. expect.poll auto-retries; NO hard sleep.
    await expect
      .poll(() => mockSse.connectionCount, { timeout: 8000 })
      .toBeGreaterThan(connectionsBefore);

    // Diagnostic: how long the reconnect took (first backoff is ~1s).
    console.log(`[TS-Y-01] reconnect observed after ${Date.now() - droppedAt}ms (connectionCount=${mockSse.connectionCount})`);
  });

  test("TS-Y-04 JWT expiry (close 4001) clears the token and redirects to /login", async ({ dashboard, mockSse, page }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();

    // Server closes with code 4001 → useWebSocket.onclose calls clearToken()
    // (localStorage.removeItem("auth_token")) and sets window.location = "/login"
    // (NO backoff reconnect on JWT expiry).
    mockSse.expireJwt();

    // The redirect fires.
    await page.waitForURL(/\/login/, { timeout: 15000 });

    // ...and the login screen renders — proving the session was torn down (a
    // still-authed app would stay on /dashboard). We assert the login surface
    // rather than a post-navigation localStorage read because the mocked
    // dashboard.goto() registers an addInitScript that re-seeds `auth_token` on
    // EVERY document load (it is what makes TS-S's reload-reconnect re-auth) —
    // so by the time the /login document has loaded the key is re-injected and a
    // null check is masked by the fixture, not by the app. The clearToken() call
    // itself is unit-covered (useWebSocket 4001 path); here we pin the
    // user-observable contract: expiry ⇒ bounced to the login screen.
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  });

  // TS-Y-02 (backend restart mid-wave → durable resume: completed wave skipped,
  // first incomplete wave re-runs) was DELETED from the mocked project: a backend
  // PROCESS restart has no browser surface distinct from a stream reattach, so the
  // case could only ever be skipped here. Owners:
  //   FE reattach + replay verdicts — ts-s.reconnect.spec.ts TS-S-01/02/03.
  //   Backend resume — backend/tests/integration/agents/test_restart_resume_db.py
  //     ::test_midwave_resume_does_not_reinvoke_completed_workers
  //     ::test_midwave_resume_reruns_whole_inflight_wave_no_parallel_dropout
  //     ::test_cross_step_does_not_skip_second_steps_waves

  // TS-Y-03 — long-run keepalive. The retired WS client ping (old TS-X-01) is gone;
  // keepalive is now the SERVER's `pipeline_heartbeat` / `pong` frames on the SSE
  // stream. useRunStream must CONSUME them (advance its resume cursor) without
  // handing them to the reducer, and the stream must keep delivering real frames
  // afterwards. A heartbeat the client failed to consume would be replayed on every
  // reattach and pin the cursor; one that leaked into the reducer could disturb the
  // live run.
  test("TS-Y-03 server heartbeats keep a long run live: consumed past the cursor, run unaffected", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Long-running refunds backlog" });

    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();
    // Caught up: the app has re-attached carrying the current tail as its cursor.
    await expect.poll(() => mockSse.lastAttachCursor, { timeout: 15_000 }).toBe(mockSse.currentSeq);

    // An idle stretch of the long run: the server emits only keepalives.
    mockSse.emit("pipeline_heartbeat", { pipeline_run_id: mockSse.currentRunId });
    const pong = mockSse.emit("pong", {});

    // The next reattach resumes PAST the keepalives — they were consumed, so the
    // server never has to replay them.
    await expect
      .poll(() => mockSse.lastAttachCursor, { timeout: 15_000 })
      .toBe(pong.data.seq as number);

    // The run is untouched by the keepalives: still live, Stop still armed.
    await expect(dashboard.runningBadge().first()).toBeVisible();
    await expect(dashboard.stopButton()).toBeVisible();

    // …and the stream keeps delivering real frames after them, to a normal finish.
    mockSse.agentComplete(agents[0].id);
    for (const a of agents.slice(1)) {
      mockSse.agentStart(a.id);
      mockSse.agentComplete(a.id);
    }
    mockSse.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });
    await expect(dashboard.doneBadge()).toBeVisible();
    await expect(dashboard.stopButton()).toHaveCount(0);
  });
});
